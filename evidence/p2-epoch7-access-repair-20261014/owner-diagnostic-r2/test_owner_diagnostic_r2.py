"""Mocked public download/host boundaries. No network, UK or service operations."""
import contextlib
import copy
import io
import json
import re
import unittest
from unittest import mock
import owner_diagnostic_r2 as d


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
        self.assertEqual(result['failure_code'],'IMMUTABLE_R2_PUBLICATION_NOT_READY');download.assert_not_called();host.assert_not_called()
    def test_exact_r2_not_old_path(self):
        self.assertEqual(d.KIT,d.BASE+'/epoch7-recovery-candidate-r2')
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


if __name__=='__main__':unittest.main()
