"""Isolated regressions: real release rendering plus durable activation recovery."""
import copy
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock
import sys

HERE = pathlib.Path(__file__).resolve().parent
PACKAGE = pathlib.Path(os.environ['P2_SOURCE_ROOT']).resolve()
PLAN = json.loads(pathlib.Path(os.environ['P2_ORIGINAL_PLAN']).read_text())
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PACKAGE / 'stage1'))
import recover_exact_hold as recovery
import p2_fixed_host_runtime as runtime_module
from activation_control import ActivationStore


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.release = self.dir / 'release'
        self.release.mkdir()
        self.manifest = json.loads((PACKAGE / 'deploy/integration-manifest.json').read_text())
        self.renderer = recovery.load_renderer(str(PACKAGE), self.manifest)
        for name in self.manifest['files']:
            path = self.release / name
            path.parent.mkdir(parents=True, exist_ok=True)
            data = (PACKAGE / name).read_bytes()
            path.write_bytes(self.renderer['render_identity_bytes'](
                name, data, recovery.MANIFEST_SHA, self.manifest))
        self.payloads = recovery.validate_release(str(PACKAGE), str(self.release),
                                                  self.manifest, recovery.MANIFEST_SHA)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_24_real_plan_targets_render_to_their_reviewed_hash(self):
        reader = recovery.source_reader(self.payloads, runtime_module._read_regular)
        for binding in PLAN['runtime']['provisioning']:
            with self.subTest(target=binding['target']):
                data, unused = reader(str(self.release / binding['source']))
                self.assertEqual(recovery.sha(data), binding['source_sha256'])
                rendered = runtime_module.FixedHostRuntime._render(data, binding)
                self.assertEqual(recovery.sha(rendered), binding['rendered_sha256'])

    def test_actual_installer_rendered_hashes_equal_all_seven_host_receipts(self):
        observed = {
            'deploy/dispatcher.example.json': '8e1846b64c039848e16ada6c6a5bf41161dc4134e5593ec4e8ba27757a966560',
            'deploy/xj-root-broker.service': 'e146733e3bbe7b85546565ef67a1137c8aa5691de00ae31581e9e64201b2a073',
            'deploy/xuanjun-ledger.service': 'e9268497aced704319f769d98cf35d620863677c89abf16dee0b40dc57c22c88',
            'deploy/uk-owner-workbench/xuanjun-uk-owner-callback.service': '333089f7f1ffc08ee7f91d1ca3214d2d350da3ab68ee0126909ea314589a1c42',
            'deploy/uk-owner-workbench/xuanjun-uk-owner-dashboard.service': '32db87fe158b50dc4e4e45873e76d47a3d6ff67c29ab7e3404cbb10401eaf7ac',
            'deploy/xuanjun-development-dispatcher.service': '776a80b82b6f9c265df71b8747535ad52e4c1f1c1281f4260b7f2b4deaedc52f',
            'deploy/xuanjun-github-intake.service': '2f7bfbb7beaa475ba181b70465e31e4fb83a45d4e14240d9bf5ce577fb3df816'}
        for name, wanted in observed.items():
            self.assertEqual(recovery.sha((self.release / name).read_bytes()), wanted)

    def test_drift_after_validation_is_rejected(self):
        path = self.release / 'deploy/dispatcher.example.json'
        path.write_bytes(path.read_bytes() + b' ')
        reader = recovery.source_reader(self.payloads, runtime_module._read_regular)
        with self.assertRaisesRegex(ValueError, 'CHANGED_AFTER_VERIFICATION'):
            reader(str(path))

    def test_non_source_reads_are_not_substituted(self):
        target = self.dir / 'receipt.json'
        target.write_bytes(b'actual target')
        reader = recovery.source_reader(self.payloads, runtime_module._read_regular)
        self.assertEqual(reader(str(target))[0], b'actual target')

    def test_release_tamper_rejected(self):
        (self.release / 'deploy/xuanjun-ledger.service').write_bytes(b'tamper')
        with self.assertRaisesRegex(ValueError, 'RELEASE_RENDERED_HASH'):
            recovery.validate_release(str(PACKAGE), str(self.release), self.manifest, recovery.MANIFEST_SHA)

    def test_symlink_release_rejected(self):
        target = self.release / 'deploy/xuanjun-ledger.service'
        target.unlink()
        target.symlink_to(PACKAGE / 'deploy/xuanjun-ledger.service')
        with self.assertRaises(ValueError):
            recovery.validate_release(str(PACKAGE), str(self.release), self.manifest, recovery.MANIFEST_SHA)

    def test_resume_uses_epoch_2_and_preserves_prerequisites(self):
        self.run_resume()

    def test_provision_failure_fences_without_prerequisite_deletion(self):
        self.run_resume('provision')

    def test_postcheck_failure_stops_and_restores_without_nss_replay(self):
        self.run_resume('postcheck')

    def test_activation_failure_contains_started_prefix(self):
        self.run_resume('activate')

    def test_hold_identity_and_cutover_drift_rejected(self):
        cutover = {'transaction_id':recovery.TX,'stage':'STAGED','source_replaced':False,
                   'activation_executed':False,'task_replay':False,
                   'plan_sha256':recovery.sha(recovery.canonical(PLAN['cutover']))}
        receipt = {'schema':1,'transaction_id':recovery.TX,'stage':'HOLD',
                   'failed_stage':'LEGACY_QUIESCED','epoch':1,'error_type':'ValueError',
                   'rollback_error_type':'ValueError','rollback':['ACTIVATION_FENCED_EPOCH_2'],
                   'legacy_writer_restarted':False,'oauth_copied':False,'new_paid_api_usage':'NONE',
                   'recovery':'MANUAL_RECONCILIATION_REQUIRED_NO_RESTART',
                   'plan_sha256':recovery.sha(recovery.canonical(PLAN)),
                   'release':'/opt/xuanjun-control-releases/'+PLAN['runtime']['release_directory'],
                   'cutover_receipt_sha256':recovery.sha(recovery.canonical(cutover))}
        active = dict(PLAN['activation']);active.pop('expected_epoch')
        active.update(schema=1,state='PREPARED',epoch=2)
        recovery.validate_hold(receipt,PLAN,active,cutover)
        for key,value in (('stage','COMPLETE'),('epoch',2),('legacy_writer_restarted',True),
                          ('plan_sha256','0'*64),('release','/tmp/unrelated')):
            bad=dict(receipt);bad[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                recovery.validate_hold(bad,PLAN,active,cutover)
        for key,value in (('state','ACTIVE'),('epoch',1),('instance','00000000-0000-0000-0000-000000000000')):
            bad=dict(active);bad[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                recovery.validate_hold(receipt,PLAN,bad,cutover)
        bad=dict(cutover,task_replay=True)
        with self.assertRaises(ValueError):recovery.validate_hold(receipt,PLAN,active,bad)

    def test_old_install_approval_cannot_authorize_recovery(self):
        response=mock.MagicMock()
        response.__enter__.return_value.read.return_value=recovery.canonical({
            'id':6160188919,'user':{'id':332398908,'login':'huhongchuan0422-creator'},
            'body':'CHATGPT_NATIVE_TASK5_COMPLETE_INSTALL_ACCEPTANCE\n{}'})
        opener=mock.Mock();opener.open.return_value=response
        with mock.patch.object(recovery.urllib.request,'build_opener',return_value=opener):
            with self.assertRaisesRegex(ValueError,'NEW_APPROVAL_REQUIRED'):
                recovery.approval(6160188919,'0'*64)

    def test_nested_restore_failure_remains_hold_without_second_restore(self):
        self.run_resume('restore')

    def run_resume(self, failure=None):
        transaction = self.dir / 'transaction'; transaction.mkdir(mode=0o700)
        candidate = self.dir / 'candidate'; candidate.mkdir(mode=0o700)
        activation_dir = self.dir / 'activation'; activation_dir.mkdir(mode=0o700)
        retained = transaction / 'retained-prerequisites'; retained.write_bytes(b'keep')
        store = ActivationStore(str(activation_dir / 'active.json'),
                                str(activation_dir / 'epochs.jsonl'),
                                str(activation_dir / 'activation.lock'))
        value = PLAN['activation']
        first = store.prepare(value['release_sha256'], value['config_sha256'],
                              value['binary_sha256'], value['ledger_uuid'], value['generation'],
                              value['instance'], value['db_path'], value['ledger_socket'], expected_epoch=0)
        proof = dict.fromkeys(('identity_verified','coordinator_inactive','parent_unit_inactive',
                              'cgroups_empty','restart_inhibited'), True)
        store.transition('PREPARED','QUIESCED',1,first['instance'],proof)
        active = store.fence(1,first['instance'])
        original = {'cutover_receipt_sha256':'0'*64,'stage':'HOLD'}
        raw = recovery.canonical(original) + b'\n'
        receipt_path = candidate / 'install-receipt.json'; receipt_path.write_bytes(raw); receipt_path.chmod(0o600)
        calls = []
        class Runtime:
            def provision(self, release, runtime):
                calls.append('provision')
                if failure == 'provision': raise ValueError('injected provision')
                return {'schema':1,'receipt_sha256':'1'*64,'rollback_complete':True}
            def reopen_database(self, descriptor):
                calls.append('reopen'); return {'database_reopened':True}
            def activate(self, runtime, descriptor):
                calls.append('activate')
                if failure == 'activate': raise ValueError('injected activation')
                return {'services_active':True}
            def stop_new(self, runtime): calls.append('stop')
            def restore(self, provision): calls.append('restore')
        class Adapter:
            def restore_legacy_files(self, gateway_only=False, preserve_mask=False):
                calls.append('gateway' if gateway_only else 'masks')
                return {'unit_files_restored':True,'services_restarted':False}
        prefix = '/opt/xuanjun-control-releases/' + PLAN['runtime']['release_directory']
        payloads = {prefix+'/'+b['source']:self.payloads[str(self.release/b['source'])]
                    for b in PLAN['runtime']['provisioning']}
        evidence = {'hold_receipt_sha256':recovery.sha(raw),'active':active}
        context = (PLAN,str(PACKAGE),Runtime(),store,Adapter(),{'proof':proof},payloads)
        def postcheck(*args):
            calls.append('postcheck')
            if failure in ('postcheck','restore'): raise ValueError('injected postcheck')
            return {'https':True}
        with mock.patch.object(recovery,'DIRECTORY',str(transaction)), \
             mock.patch.object(recovery,'CAND',str(candidate)), \
             mock.patch.object(recovery,'original_postcheck',postcheck):
            if failure == 'restore':
                def restore_failure(provision):
                    calls.append('restore');raise ValueError('injected nested restore')
                context[2].restore=restore_failure
            if failure:
                with self.assertRaises(ValueError): recovery.resume(evidence,context,{'review_id':999})
                self.assertEqual(store.read()['state'],'PREPARED')
                self.assertEqual(store.read()['epoch'],3)
                self.assertEqual(json.loads(receipt_path.read_text())['stage'],'HOLD')
                if failure in ('postcheck','activate','restore'):
                    self.assertLess(calls.index('stop'),calls.index('restore'))
                if failure == 'restore':self.assertEqual(calls.count('restore'),1)
            else:
                self.assertEqual(recovery.resume(evidence,context,{'review_id':999})['stage'],'COMPLETE')
                self.assertEqual(store.read()['state'],'ACTIVE')
                self.assertEqual(store.read()['epoch'],2)
                self.assertEqual(calls,['provision','reopen','gateway','activate','postcheck'])
            self.assertEqual(retained.read_bytes(),b'keep')
            self.assertEqual((transaction/'original-install-hold.json').read_bytes(),raw)
            with self.assertRaisesRegex(ValueError,'ATTEMPT_ALREADY_EXISTS'):
                recovery.resume(evidence,context,{'review_id':999})


if __name__ == '__main__':
    unittest.main(verbosity=2)
