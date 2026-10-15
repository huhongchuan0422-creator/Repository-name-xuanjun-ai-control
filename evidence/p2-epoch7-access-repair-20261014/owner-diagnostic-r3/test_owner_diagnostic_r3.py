"""Mocked public download/host boundaries. No network, UK or service operations."""
import contextlib
import copy
import io
import json
import re
import sys
import types
import unittest
from unittest import mock
import owner_diagnostic_r3 as d


@contextlib.contextmanager
def no_alarm(unused):yield


def observed():
    return dict(operation='observe-and-probe',kind='EPOCH7_OBSERVATION_ONLY_UNREVIEWED',
        probe_stage='RESULT_RECORDED',independent_acceptance='PENDING',install_admission='NOT_GRANTED',
        production_resume='NOT_EXECUTED',private_file_sha256='1'*64,snapshot_sha256='2'*64,
        policy_sha256='3'*64,kit_manifest_sha256=d.MANIFEST_SHA,success=True,probe_observations_complete=True)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.gate=self.stack.enter_context(mock.patch.object(d,'publication_gate'))
        self.host=self.stack.enter_context(mock.patch.object(d,'host_boundary'))
        self.download=self.stack.enter_context(mock.patch.object(d,'download',return_value=b'verified'))
        self.extractor=mock.Mock();self.stack.enter_context(mock.patch.object(d,'authenticated_module',return_value=self.extractor))
        self.outputs=self.stack.enter_context(mock.patch.object(d,'check_outputs'))
        self.entry=mock.Mock();self.kit=mock.Mock();self.kit.observe.return_value=observed()
        self.stage=self.stack.enter_context(mock.patch.object(d,'stage_kit',return_value=(self.entry,self.kit,'EXTRACTED_AND_VERIFIED')))
        self.acl=self.stack.enter_context(mock.patch.object(d,'exact_uid_test',return_value={'success':True,'tests':1,'skipped':0}))
        self.repair=self.stack.enter_context(mock.patch.object(d,'prerequisite',return_value={'stage':'COMPLETE_PREREQUISITES_ONLY'}))
        self.receipt=self.stack.enter_context(mock.patch.object(d,'write_receipt',return_value='4'*64))
        self.stack.enter_context(mock.patch.object(d,'bounded_stage',no_alarm))
        self.stack.enter_context(mock.patch.object(d,'MANIFEST_SHA','a'*64));self.kit.observe.return_value=observed()
    def run_once(self,**kw):
        args=dict(identifier='a'*16,nonce='b'*32,execute_reviewed_diagnostic=True,execute_reviewed_probe=True,execute_reviewed_prerequisites=True)
        args.update(kw);return d.run(**args)
    def test_one_consolidated_success(self):
        value=self.run_once();self.assertTrue(value['success'])
        self.repair.assert_called_once();self.assertEqual(self.repair.call_args[0][:3],(self.entry,self.kit,True))
        self.kit.observe.assert_called_once_with(d.BASE+'/epoch7-observation-'+'a'*16+'.private.json','b'*32,True)
        self.receipt.assert_called_once();self.assertEqual(value['production_resume'],'NOT_EXECUTED')
    def test_no_prerequisite_ack_before_download(self):
        value=self.run_once(execute_reviewed_prerequisites=False)
        self.assertFalse(value['success']);self.download.assert_not_called();self.repair.assert_not_called()
    def test_no_diagnostic_ack_before_download(self):
        self.run_once(execute_reviewed_diagnostic=False);self.download.assert_not_called()
    def test_bad_nonce_before_download(self):
        self.run_once(nonce='not-a-nonce');self.download.assert_not_called()
    def test_output_collision_before_stage(self):
        self.outputs.side_effect=d.DiagnosticHold('OUTPUT_OR_NONCE_ALREADY_EXISTS')
        self.run_once();self.stage.assert_not_called();self.repair.assert_not_called()
    def test_uid_failure_blocks_repair_and_probe(self):
        self.acl.return_value={'success':False};value=self.run_once()
        self.assertFalse(value['success']);self.repair.assert_not_called();self.kit.observe.assert_not_called();self.receipt.assert_called_once()
    def test_partial_repair_is_preserved_and_never_retried(self):
        self.repair.return_value={'stage':'PARTIAL_HOLD','completed':['fixed-first'],'failure_code':'FIXED_FAILURE'}
        value=self.run_once();self.assertEqual(value['prerequisite']['completed'],['fixed-first'])
        self.repair.assert_called_once();self.kit.observe.assert_not_called();self.receipt.assert_called_once()
        self.assertEqual(value['outcome'],'POTENTIALLY_PARTIAL_NO_AUTOMATIC_RETRY')
    def test_repair_hold_never_observes_or_probes(self):
        self.repair.return_value={'stage':'HOLD'};self.run_once();self.kit.observe.assert_not_called()
    def test_observation_interruption_keeps_repair_result(self):
        self.kit.observe.side_effect=KeyboardInterrupt();value=self.run_once()
        self.assertEqual(value['failure_code'],'INTERRUPTED');self.assertEqual(value['prerequisite']['stage'],'COMPLETE_PREREQUISITES_ONLY')
        self.receipt.assert_called_once()
    def test_secondary_receipt_failure_preserves_primary(self):
        self.kit.observe.side_effect=KeyboardInterrupt();self.receipt.side_effect=ValueError('secret')
        value=self.run_once();self.assertEqual(value['failure_code'],'INTERRUPTED');self.assertEqual(value['diagnostic_receipt'],'FAILED_OR_INTERRUPTED')
        self.assertNotIn('secret',str(value))
    def test_post_repair_cleanup_failure_receipt_retains_completed_targets(self):
        def fail(entry,kit,ack,result):
            result['prerequisite']={'stage':'COMPLETE_PREREQUISITES_ONLY','completed':['first','second','third']}
            error=ValueError('CLEANUP_FAILED');error.diagnostic_reverification_failed=True;raise error
        self.repair.side_effect=fail;result=self.run_once()
        self.assertFalse(result['success']);self.assertEqual(result['prerequisite']['completed'],['first','second','third'])
        self.assertEqual(result['reverification'],'FAILED_OR_INTERRUPTED');self.kit.observe.assert_not_called()
        self.assertEqual(self.receipt.call_args[0][-1]['prerequisite'],result['prerequisite'])

    def test_observation_hold_is_recorded(self):
        self.kit.observe.return_value=dict(observed(),success=False,kind='EPOCH7_OBSERVATION_ONLY_HOLD',probe_stage='HOLD_NOT_EXECUTED',probe_observations_complete=False)
        value=self.run_once();self.assertFalse(value['success']);self.assertEqual(value['stage'],'HOLD_RECORDED')
    def test_no_probe_flag_observes_only_after_repair(self):
        self.kit.observe.return_value=dict(observed(),operation='observe-only',probe_stage='NOT_REQUESTED',probe_observations_complete=False)
        self.run_once(nonce=None,execute_reviewed_probe=False)
        self.kit.observe.assert_called_once_with(d.BASE+'/epoch7-observation-'+'a'*16+'.private.json',None,False)
    def test_unknown_exception_body_sanitized(self):
        self.repair.side_effect=RuntimeError('SECRET BODY');value=self.run_once();self.assertNotIn('SECRET BODY',str(value))
    def test_no_resume_option(self):
        with mock.patch('sys.stdout',new=io.StringIO()) as stream:
            self.assertEqual(d.main(['--resume','SECRET']),2)
        self.assertNotIn('SECRET',stream.getvalue());self.repair.assert_not_called()


class PublicationTests(unittest.TestCase):
    def test_unpublished_candidate_fails_before_any_download_or_host(self):
        with mock.patch.object(d,'READY',False),mock.patch.object(d,'download') as download,mock.patch.object(d,'host_boundary') as host:
            result=d.run('a'*16,'b'*32,True,True,True)
        self.assertEqual(result['failure_code'],'IMMUTABLE_R3_PUBLICATION_NOT_READY');download.assert_not_called();host.assert_not_called()
    def test_exact_r3_not_old_path(self):
        self.assertEqual(d.KIT,d.BASE+'/epoch7-recovery-candidate-r3')
    def test_current_source_binds_verified_r3_publications(self):
        expected = {'READY': True, 'SOURCE': '460a53e0f702fb416811e785a6ef8d6c39b2d003', 'TREE': '20f382a534da9f1c39fa2c2c97e7a484917f8aa5', 'PUBLICATION': '02822b674a7c8a0c9c395cbf5664b3d24bff2516', 'ARCHIVE_PATH': 'evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-460a53e0.tar.gz', 'ARCHIVE_SHA': 'c56a11e78914d567f91a94118d676d49f65775161b3c46b16583ece1403c1d85', 'EXTRACTOR_SHA': '87122167bf6c63f5f96452369d6e3d7d59c5254fade9a2ed52d3e959d8538261', 'ENTRY_SHA': '24ad01d9b216e2a2771180c169c0d8d858173f6dee2a6b0cf9e35f9ad97108d4', 'MANIFEST_SHA': 'e6618cf3012bc5edf8f3c9fb9982494dad7d916fbc7adcaeab39ebe0733cc3b8', 'ARCHIVE_SIZE': 1015797, 'EXTRACTOR_SIZE': 9582, 'KIT_SOURCE_FILES': 247}
        for name,value in expected.items():
            self.assertEqual(getattr(d,name),value,name)
        self.assertEqual(d.ARCHIVE_URL,d.PREFIX+d.PUBLICATION+'/'+d.ARCHIVE_PATH)
        self.assertEqual(d.EXTRACTOR_URL,d.PREFIX+d.SOURCE+'/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py')
        d.publication_gate()
    def test_r3_stage_never_uses_r2_destination(self):
        self.assertNotEqual(d.KIT,d.BASE+'/epoch7-recovery-candidate-r2')
        self.assertEqual(d.UK_FIXTURE_SOURCE,'tests/snapshot/test_snapshot.py')
        self.assertEqual(d.UK_FIXTURE_SHA,'608caeca2010ed094190f9b3fd37a4c4764a6847dfd76f074099e5e25ea2592c')

    def test_pin_schema_binds_exact_immutable_urls(self):
        values=dict(READY=True,SOURCE='1'*40,TREE='2'*40,PUBLICATION='3'*40,
            ARCHIVE_SHA='4'*64,EXTRACTOR_SHA='5'*64,ENTRY_SHA='6'*64,MANIFEST_SHA='7'*64,
            ARCHIVE_SIZE=100,EXTRACTOR_SIZE=200,KIT_SOURCE_FILES=250,
            ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/fixed.tar.gz')
        values['ARCHIVE_URL']=d.PREFIX+values['PUBLICATION']+'/'+values['ARCHIVE_PATH']
        values['EXTRACTOR_URL']=d.PREFIX+values['SOURCE']+'/evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tools/extract_epoch7_kit.py'
        with mock.patch.multiple(d,**values):
            d.publication_gate()
            with mock.patch.object(d,'ARCHIVE_URL',d.PREFIX+'main/'+values['ARCHIVE_PATH']):
                with self.assertRaisesRegex(ValueError,'IMMUTABLE_DOWNLOAD_SCOPE'):d.publication_gate()


class CachedPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.entry=mock.Mock();self.kit=mock.Mock()
        self.kit.manifest={'modules':{d.PREREQUISITE_MODULE:d.PREREQUISITE_SOURCE}}
        targets=['/home/xuanjun_dev/.openclaw/'+x for x in ('bin','tools','tools/node-v24.21.0')]
        self.value=dict(kind='EPOCH7_OWNER_PREREQUISITE',stage='COMPLETE_PREREQUISITES_ONLY',automatic_retry=False,
            permission_widening_rollback=False,production_admission='NOT_GRANTED',service_actions=0,database_writes=0,
            authorized_targets=targets,attempted=targets,completed=targets)
        self.active=False
        @contextlib.contextmanager
        def imports():
            self.active=True
            try:yield
            finally:self.active=False
        self.kit.imports=imports;self.module=mock.Mock()
        def apply(**kw):
            self.assertTrue(self.active);self.assertEqual(kw,{'operator_acknowledged':True});return copy.deepcopy(self.value)
        self.module.apply_reviewed_prerequisites.side_effect=apply
    def call(self):
        with mock.patch.object(d.importlib,'import_module',return_value=self.module),mock.patch.object(d,'bounded_stage',no_alarm):
            return d.prerequisite(self.entry,self.kit,True)
    def test_helper_once_inside_authenticated_imports(self):
        result=self.call();self.assertEqual(result['stage'],'COMPLETE_PREREQUISITES_ONLY')
        self.module.apply_reviewed_prerequisites.assert_called_once();self.assertFalse(self.active)
        self.entry.verify_kit.assert_called_once_with(d.KIT,d.MANIFEST_SHA)
    def test_unmapped_helper_never_called(self):
        self.kit.manifest={'modules':{}}
        with self.assertRaisesRegex(ValueError,'AUTHENTICATED_PREREQUISITE'):self.call()
        self.module.apply_reviewed_prerequisites.assert_not_called()
    def test_foreign_target_rejected(self):
        self.value['completed']=['/elsewhere']
        with self.assertRaisesRegex(ValueError,'RESULT_TARGETS'):self.call()
    def test_short_complete_rejected(self):
        self.value['completed']=self.value['completed'][:1]
        with self.assertRaisesRegex(ValueError,'COMPLETE_TARGET_SET'):self.call()
    def test_completed_evidence_survives_import_cleanup_failure(self):
        @contextlib.contextmanager
        def failing_imports():
            self.active=True
            try:yield
            finally:self.active=False;raise ValueError('IMPORT_CLEANUP_FAILED')
        self.kit.imports=failing_imports;outer={}
        with mock.patch.object(d.importlib,'import_module',return_value=self.module),mock.patch.object(d,'bounded_stage',no_alarm):
            with self.assertRaisesRegex(ValueError,'IMPORT_CLEANUP_FAILED'):
                d.prerequisite(self.entry,self.kit,True,outer)
        self.assertEqual(outer['prerequisite']['completed'],self.value['completed'])
        self.assertEqual(outer['prerequisite']['stage'],'COMPLETE_PREREQUISITES_ONLY')
        self.assertNotIn('prerequisite_outcome',outer)

    def test_completed_evidence_survives_final_reverify_failure(self):
        self.entry.verify_kit.side_effect=ValueError('REVERIFY_FAILED');outer={}
        with mock.patch.object(d.importlib,'import_module',return_value=self.module),mock.patch.object(d,'bounded_stage',no_alarm):
            with self.assertRaisesRegex(ValueError,'REVERIFY_FAILED'):
                d.prerequisite(self.entry,self.kit,True,outer)
        self.assertEqual(outer['prerequisite']['completed'],self.value['completed'])
        self.module.apply_reviewed_prerequisites.assert_called_once()

    def test_raw_extra_detail_is_not_printed(self):
        self.value['raw_private']='SECRET BODY';result=self.call();self.assertNotIn('SECRET',str(result))


class UKClosureTests(unittest.TestCase):
    def setUp(self):
        self.test_raw=b'# fixed synthetic UK test bytes\n'
        self.fixture_raw=b'# fixed synthetic snapshot fixture bytes\n'
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(d,'UK_TEST_SHA',d.sha(self.test_raw)))
        self.stack.enter_context(mock.patch.object(d,'UK_FIXTURE_SHA',d.sha(self.fixture_raw)))
        self.original={d.UK_ALIAS:d.UK_TEST,'test_epoch7_host_phases':'tests/host_filesystem/test_epoch7_host_phases.py'}
        self.kit=types.SimpleNamespace(manifest={'test_suites':{'uk_exact_uid_acl':{
            'tests':[d.UK_TEST],'imports':dict(self.original)}},'files':{
                d.UK_FIXTURE_SOURCE:d.sha(self.fixture_raw)}},
            cache={d.UK_TEST:self.test_raw,d.UK_FIXTURE_SOURCE:self.fixture_raw})
    def test_exact_fixed_alias_added_without_manifest_mutation(self):
        result=d.exact_uk_imports(self.kit)
        self.assertEqual(result,dict(self.original,test_snapshot=d.UK_FIXTURE_SOURCE))
        self.assertEqual(self.kit.manifest['test_suites']['uk_exact_uid_acl']['imports'],self.original)
    def test_missing_cached_fixture_refused(self):
        del self.kit.cache[d.UK_FIXTURE_SOURCE]
        with self.assertRaisesRegex(d.DiagnosticHold,'EXACT_UK_FIXTURE_SOURCE_REQUIRED'):d.exact_uk_imports(self.kit)
    def test_changed_cached_fixture_refused(self):
        self.kit.cache[d.UK_FIXTURE_SOURCE]+=b'changed'
        with self.assertRaisesRegex(d.DiagnosticHold,'EXACT_UK_FIXTURE_SOURCE_REQUIRED'):d.exact_uk_imports(self.kit)
    def test_wrong_manifest_fixture_digest_refused(self):
        self.kit.manifest['files'][d.UK_FIXTURE_SOURCE]='0'*64
        with self.assertRaisesRegex(d.DiagnosticHold,'EXACT_UK_FIXTURE_SOURCE_REQUIRED'):d.exact_uk_imports(self.kit)
    def test_any_preexisting_alias_refused(self):
        for target in (d.UK_FIXTURE_SOURCE,'tests/other/test_snapshot.py'):
            self.kit.manifest['test_suites']['uk_exact_uid_acl']['imports'][d.UK_FIXTURE_ALIAS]=target
            with self.assertRaisesRegex(d.DiagnosticHold,'EXACT_UK_FIXTURE_ALIAS_CONFLICT'):d.exact_uk_imports(self.kit)
    def test_exact_case_selection_does_not_run_case(self):
        module=types.ModuleType(d.UK_ALIAS)
        def forbidden(self):raise AssertionError('SELECTION_MUST_NOT_RUN_FIXTURE')
        case=type('ActualFDTests',(unittest.TestCase,),{'__module__':d.UK_ALIAS,
            'test_actual_fd_acl_changes_only_two_named_access_sets':forbidden})
        module.ActualFDTests=case
        module.load_tests=lambda loader,tests,pattern:loader.loadTestsFromTestCase(case)
        with mock.patch.dict(sys.modules,{d.UK_ALIAS:module}):
            suite=d.load_exact_uid_suite()
        self.assertEqual([item.id() for item in suite],[d.UK_CASE])
    def test_extra_case_is_rejected_before_execution(self):
        module=types.ModuleType(d.UK_ALIAS)
        module.Extra=type('Extra',(unittest.TestCase,),{'__module__':d.UK_ALIAS,'test_other':lambda self:None})
        with mock.patch.dict(sys.modules,{d.UK_ALIAS:module}):
            with self.assertRaisesRegex(d.DiagnosticHold,'EXACT_ONE_TEST_REQUIRED'):d.load_exact_uid_suite()
    def uid_error(self,error):
        entry=mock.Mock();workspace=types.SimpleNamespace(imports=no_alarm)
        @contextlib.contextmanager
        def temporary():yield workspace
        kit=types.SimpleNamespace(test_workspace=temporary)
        with mock.patch.object(d,'exact_uk_imports',return_value={}),mock.patch.object(d,'bounded_stage',no_alarm), \
             mock.patch.object(d,'load_exact_uid_suite',side_effect=error):
            d.exact_uid_test(entry,kit)
    def test_unknown_import_error_has_static_stage_and_preserved_cause(self):
        original=ModuleNotFoundError('PRIVATE_IMPORT_DETAIL');original.diagnostic_import_cleanup_failed=True
        with self.assertRaisesRegex(d.DiagnosticHold,'^EXACT_UID_LOAD_FAILED$') as caught:self.uid_error(original)
        self.assertIs(caught.exception.__cause__,original)
        self.assertTrue(caught.exception.diagnostic_import_cleanup_failed)
        self.assertNotIn('PRIVATE',str(caught.exception))
    def test_interrupt_not_replaced_by_static_exception_translation(self):
        original=KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt) as caught:self.uid_error(original)
        self.assertIs(caught.exception,original)


if __name__=='__main__':unittest.main()
