"""Synthetic host/network boundaries around the complete prepare-only callchain.

Real R7 compiler/hydration is separately exercised by PureTests. No real review
ID is claimed here and no host, network, probe or installation is executed.
"""
import contextlib
import copy
import json
import socket
import time
import types
import unittest
from unittest import mock
import epoch7_prepare as p
import epoch7_prepare_data as data


class PreparationCallchainTests(unittest.TestCase):
    def invoke(self, fault=None):
        names=('probe_driver','probe_helpers','node_sqlite_probe','unit_metadata','snapshot_io')
        @contextlib.contextmanager
        def imports():yield
        kit=types.SimpleNamespace(raw_manifest=b'authenticated kit',digest=p.KIT_SHA,
            cache={name+'.py':name.encode('ascii') for name in names},
            manifest={'modules':{name:name+'.py' for name in names}},imports=imports,
            _authenticate_probe_receipt=mock.Mock())
        final=types.SimpleNamespace(raw_manifest=kit.raw_manifest,cache=dict(kit.cache))
        changed=types.SimpleNamespace(raw_manifest=b'changed',cache=dict(kit.cache))
        if fault=='cache':changed=types.SimpleNamespace(raw_manifest=kit.raw_manifest,cache={})
        verifications=(kit,changed if fault in ('manifest','cache') else final,
                       changed if fault=='post_kit' else final)
        entry=types.SimpleNamespace(verify_kit=mock.Mock(side_effect=verifications))
        gather=mock.Mock();gather.saved_unit_dropins.return_value={'fixture':'fresh authority only'}
        if fault=='fresh':gather.saved_unit_dropins.side_effect=ValueError('EPOCH7_PREP_FRESH_DROPIN_PRESENCE')
        if fault=='after_compile':gather.recheck.side_effect=ValueError('EPOCH7_PREP_GATHER_OBSERVATION_DRIFT')
        if fault=='after_publish':gather.recheck.side_effect=(None,ValueError('EPOCH7_PREP_GATHER_OBSERVATION_DRIFT'))
        body={'decision':'SYNTHETIC_TEST_ONLY'};saved={'fixture':'saved proof only'}
        proposal={'expected_review_body':body,'topology_sha256':'2'*64,'topology_raw':b'fixture topology'}
        projection=types.SimpleNamespace(canonical=data.canonical,
            project_saved_unit_dropins=mock.Mock(return_value=saved),
            project_topology=mock.Mock(return_value=proposal),
            fetch_topology_review=mock.Mock(return_value={'review_id':7000000001,'approval_body_sha256':'3'*64,'evidence_sha256':'2'*64}))
        if fault=='review':projection.fetch_topology_review.side_effect=ValueError('TOPOLOGY_REVIEW_BODY')
        if fault and fault.startswith('real_review_'):
            import epoch7_topology_projection as actual_topology
            import test_epoch7_topology_projection as fixture_module
            public_fixture=fixture_module.fixture();proposal=fixture_module.project(public_fixture)
            body=proposal['expected_review_body'];saved=public_fixture['dropins']
            projection.project_topology.return_value=proposal
            projection.project_saved_unit_dropins.return_value=saved
            record=json.loads(fixture_module.response(proposal).decode())
            if fault=='real_review_id':record['id']+=1
            elif fault=='real_review_author':record['user']['id']=1
            elif fault=='real_review_destination':record['issue_url']=record['issue_url'].replace('/58','/59')
            elif fault=='real_review_schema':
                edited=copy.deepcopy(body);edited['schema']=1
                record['body']=actual_topology.approval.MARKER+data.canonical(edited).decode()
            else:
                edited=copy.deepcopy(body);edited['decision']='UNAPPROVED_TEST_EDIT'
                record['body']=actual_topology.approval.MARKER+data.canonical(edited).decode()
            raw=data.canonical(record)
            projection.fetch_topology_review.side_effect=lambda identifier,proposed:actual_topology.authenticate_topology_review(raw,identifier,proposed)
        @contextlib.contextmanager
        def modules(cache):yield data,projection
        collected={'observation':{},'receipt_raw':b'fixture','receipt_metadata':{},'manifest_raw':b'fixture manifest'}
        args=types.SimpleNamespace(operation='prepare',observation=p.OBSERVATION_PATH,
            observation_sha256=p.OBSERVATION_SHA,topology_review_id=7000000001,
            retained_renewal_timer='enable-after-reviewed-checks')
        source_manifest={'schema':1,'files':{'epoch7_prepare.py':'4'*64}}
        rows=p.Publication([{'path':'/fixture/plan.private.json','sha256':'5'*64,'bytes':1}])
        bundle={'summary':{'state':'PREPARED_NOT_ADMITTED','install_admission':'NOT_GRANTED'},
                'unsigned_approval':{'decision':'SYNTHETIC_FINAL_BODY'}}
        with mock.patch.object(p.os,'geteuid',return_value=0),mock.patch.object(socket,'gethostname',return_value=p.HOST),\
             mock.patch.object(p,'bootstrap_entry',return_value=entry),mock.patch.object(p,'Gatherer',return_value=gather),\
             mock.patch.object(p,'preparation_sources',return_value=({},source_manifest)),mock.patch.object(p,'preparation_modules',modules),\
             mock.patch.object(p,'collect_inputs',return_value=collected),mock.patch.object(p,'publish_bundle',return_value=rows) as publish,\
             mock.patch.object(p,'verify_publication') as verify,\
             mock.patch.object(p,'compile_private_bundle',return_value=bundle) as compile_bundle,\
             mock.patch.object(p,'EXPECTED_REVIEW_BODY_SHA','0'*64 if fault=='body' else p.sha(data.canonical(body))):
            if fault=='compile':compile_bundle.side_effect=ValueError('EPOCH7_PREP_PREPARATION_UNRESOLVED')
            result=None;error=None
            try:result=p.run_preparation(args,time.monotonic()+10)
            except BaseException as caught:error=caught
        gather.close.assert_called_once_with(error)
        return types.SimpleNamespace(result=result,error=error,entry=entry,gather=gather,kit=kit,
            projection=projection,publish=publish,verify=verify,compile=compile_bundle,rows=rows,
            source_manifest=source_manifest,saved=saved)

    def test_complete_callchain_keeps_saved_and_fresh_provenance_separate(self):
        value=self.invoke();self.assertIsNone(value.error)
        self.assertEqual(value.result['state'],'PREPARED_NOT_ADMITTED')
        self.assertEqual(value.result['outputs'],list(value.rows))
        call=value.projection.project_topology.call_args[0]
        self.assertEqual(call[-1],p.SAVED_PROJECTION_MANIFEST_SHA)
        self.assertEqual(call[-2],value.saved)
        self.assertEqual(set(call[4]),{'probe_driver.py','probe_helpers.py','node_sqlite_probe.py',
            'unit_metadata.py','snapshot_io.py','deploy/integration-manifest.json'})
        self.assertNotEqual(call[-1],p.sha(data.canonical(value.source_manifest)))
        value.projection.fetch_topology_review.assert_called_once()
        value.compile.assert_called_once();value.publish.assert_called_once();value.verify.assert_called_once()
        self.assertEqual(value.entry.verify_kit.call_count,3)
        self.assertEqual(value.gather.recheck.call_count,2)
        value.gather.accept_owned_publication.assert_called_once_with(value.rows)
        self.assertIs(value.compile.call_args[0][4],True)
        value.kit._authenticate_probe_receipt.assert_called_once()

    def test_fixed_body_drift_refuses_before_fetch_compile_or_publication(self):
        value=self.invoke('body');self.assertEqual(value.error.args,('EPOCH7_PREP_ACCEPTED_REVIEW_BODY_PIN',))
        value.projection.fetch_topology_review.assert_not_called();value.compile.assert_not_called();value.publish.assert_not_called()

    def test_fresh_drift_refuses_before_review_or_compilation(self):
        value=self.invoke('fresh');self.assertIsInstance(value.error,ValueError)
        value.projection.project_topology.assert_not_called();value.compile.assert_not_called();value.publish.assert_not_called()

    def test_rejected_genuine_review_never_compiles_or_publishes(self):
        value=self.invoke('review');self.assertIsInstance(value.error,ValueError)
        value.compile.assert_not_called();value.publish.assert_not_called()

    def test_real_account_id_destination_body_and_schema_validation_blocks_outputs(self):
        for kind in ('id','author','destination','body','schema'):
            with self.subTest(kind=kind):
                value=self.invoke('real_review_'+kind)
                self.assertIsInstance(value.error,ValueError)
                value.projection.fetch_topology_review.assert_called_once()
                value.compile.assert_not_called();value.publish.assert_not_called()

    def test_compile_or_postcompile_drift_prevents_publication(self):
        for fault in ('compile','after_compile'):
            with self.subTest(fault=fault):
                value=self.invoke(fault);self.assertIsInstance(value.error,ValueError);value.publish.assert_not_called()

    def test_prepublication_manifest_or_cache_drift_refuses(self):
        for fault in ('manifest','cache'):
            with self.subTest(fault=fault):
                value=self.invoke(fault);self.assertEqual(value.error.args,('EPOCH7_PREP_KIT_FINAL_CHANGED',));value.publish.assert_not_called()

    def test_postpublication_drift_preserves_all_created_paths(self):
        for fault in ('after_publish','post_kit'):
            with self.subTest(fault=fault):
                value=self.invoke(fault);self.assertIsInstance(value.error,ValueError)
                self.assertEqual(value.error.preparation_outputs,list(value.rows))
                self.assertEqual(value.error.preparation_created_paths,[row['path'] for row in value.rows])
                self.assertIsNone(value.result)


class R7AdmissionBoundaryTests(unittest.TestCase):
    def args(self):
        return types.SimpleNamespace(operation='prepare',observation=p.OBSERVATION_PATH,
            observation_sha256=p.OBSERVATION_SHA,topology_review_id=7000000001,
            retained_renewal_timer='enable-after-reviewed-checks')
    def test_runner_authenticates_cache_before_runtime_code_import(self):
        import pathlib,subprocess,sys,tempfile
        here=pathlib.Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='bad-r7-kit-',dir=str(here)) as directory:
            kit=pathlib.Path(directory)
            (kit/'tests').mkdir();(kit/'helpers').mkdir()
            runtime=kit/'xuanjun-p2-package/stage1';runtime.mkdir(parents=True)
            (runtime/'activation_control.py').write_text("raise RuntimeError('UNAUTHENTICATED_RUNTIME_EXECUTED')")
            (kit/'recovery-kit-manifest.json').write_bytes(b'{}')
            result=subprocess.run([sys.executable,'-I','-S','-B',str(here/'run_local_tests.py'),
                '--portable','--kit-root',str(kit)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'TEST_R7_KIT_MANIFEST_PIN',result.stderr)
            self.assertNotIn(b'UNAUTHENTICATED_RUNTIME_EXECUTED',result.stdout+result.stderr)

    def test_saved_manifest_is_exact_and_separate(self):
        p.require_binding()
        self.assertEqual(p.sha(data.canonical(p.SAVED_PROJECTION_SOURCES)),p.SAVED_PROJECTION_MANIFEST_SHA)
        self.assertEqual(set(p.SAVED_PROJECTION_SOURCES['files']),{'epoch7_prepare_data.py','epoch7_topology_projection.py','export_schema.py'})
        self.assertNotIn('epoch7_prepare.py',p.SAVED_PROJECTION_SOURCES['files'])
    def test_manifest_mutation_refuses_before_host_reads(self):
        changed=copy.deepcopy(p.SAVED_PROJECTION_SOURCES);changed['files']['export_schema.py']='0'*64
        with mock.patch.object(p,'SAVED_PROJECTION_SOURCES',changed),mock.patch.object(p.os,'geteuid',side_effect=AssertionError('no host')):
            with self.assertRaisesRegex(ValueError,'SAVED_SOURCE_MANIFEST_PIN'):p.run_preparation(self.args(),time.monotonic()+1)
    def test_observation_and_approval_inputs_are_finite_before_reads(self):
        changes=[('observation','/other'),('observation_sha256','0'*64),('operation','propose-topology')]
        changes += [('topology_review_id',value) for value in (None,False,True,0,-1,'7000000001')]
        changes += [('retained_renewal_timer',value) for value in (None,False,True,'disable')]
        for key,value in changes:
            args=self.args();setattr(args,key,value)
            with self.subTest(key=key,value=value),mock.patch.object(p.os,'geteuid',side_effect=AssertionError('no host')):
                with self.assertRaises(ValueError):p.run_preparation(args,time.monotonic()+1)


if __name__=='__main__':unittest.main()
