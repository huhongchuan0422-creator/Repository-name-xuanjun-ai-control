import json
import os
import tempfile
import unittest
import uuid

import p2_install_entrypoint as module


class FakeActivation(object):
    def __init__(self): self.calls=[]
    def prepare(self,*args,**kwargs):
        self.calls.append(('prepare',args,kwargs))
        return {'epoch':1,'instance':args[5]}
    def transition(self,old,new,epoch,instance,proof):
        self.calls.append((old,new,proof))
        return {'epoch':epoch,'instance':instance,'state':new}


class FakeRuntime(object):
    def __init__(self,fail=False): self.calls=[]; self.fail=fail
    def preflight(self,*args): self.calls.append('preflight')
    def provision(self,*args):
        self.calls.append('provision')
        return {'schema':1,'receipt_sha256':'a'*64,'rollback_complete':True}
    def activate(self,*args):
        self.calls.append('activate')
        if self.fail: raise RuntimeError('planned')
        return {'database_reopened':True,'services_active':True}
    def stop_new(self,*args): self.calls.append('stop_new')
    def restore(self,*args): self.calls.append('restore')


class FakeAdapter(object):
    def __init__(self): self.restored=False
    def restore_legacy_files(self): self.restored=True


class FakeCutover(object):
    def __init__(self): self.adapter=FakeAdapter(); self.calls=[]; self.receipt_path=None
    def execute(self,plan):
        self.calls.append(plan)
        proof={key:True for key in module.PROOF_KEYS}
        return {'stage':'STAGED','quiescence':{'proof':proof},'migration':{}}


class P2InstallEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.parent=os.path.realpath(self.temp.name); os.chmod(self.parent,0o700)
        self.release=os.path.join(self.parent,'releases','integration-'+'1'*16)
        self.plan={
          'schema':1,'transaction_id':str(uuid.uuid4()),
          'artifact':{'root':os.path.join(self.parent,'root'),
            'manifest':os.path.join(self.parent,'manifest.json'),
            'source_commit':'2'*40,'source_tree':'3'*40,
            'manifest_sha256':'4'*64,
            'releases':os.path.join(self.parent,'releases')},
          'cutover':{'opaque':'cutover-validates-its-own-exact-contract'},
          'activation':{'release_sha256':'5'*64,'config_sha256':'6'*64,
            'binary_sha256':'7'*64,'ledger_uuid':str(uuid.uuid4()),
            'generation':1,'instance':str(uuid.uuid4()),
            'db_path':'/var/lib/xuanjun-development/generations/1/state.sqlite',
            'ledger_socket':'/run/xuanjun-development/ledger.sock',
            'expected_epoch':0},
          'runtime':{'release_directory':'integration-'+'1'*16,
            'provisioning':[{'binding':'opaque'}],
            'services':['xuanjun-ledger.socket']},
          'auth':{'mode':'EXISTING_OAUTH_REFERENCE','references':[
            {'path':'/var/lib/xuanjun-development/codex-home/auth.json',
             'sha256':'8'*64,'owner_uid':1001,'mode':0o600}]},
          'tls':{'mode':'EXISTING_TLS_REFERENCE','references':[
            {'path':'/etc/pki/tls/private/xuanjun.key','sha256':'9'*64,
             'owner_uid':0,'mode':0o600}]}}

    def make(self,runtime=None):
        runtime=runtime or FakeRuntime(); activation=FakeActivation(); cutover=FakeCutover()
        receipt=os.path.join(self.parent,'install.json')
        cutover.receipt_path=os.path.join(self.parent,'cutover.json')
        value=module.P2InstallEntrypoint(receipt,lambda artifact:self.release,
                                         cutover,activation,runtime)
        return value,runtime,activation,cutover,receipt

    def test_complete_orders_all_gates_and_never_copies_oauth(self):
        value,runtime,activation,cutover,receipt=self.make()
        result=value.execute(self.plan)
        self.assertEqual(result['stage'],'COMPLETE')
        self.assertFalse(result['oauth_copied'])
        self.assertEqual(result['new_paid_api_usage'],'NONE')
        self.assertEqual(runtime.calls,['preflight','provision','activate'])
        self.assertEqual([c[0] for c in activation.calls],
                         ['prepare','PREPARED','QUIESCED'])
        with open(receipt) as stream: self.assertEqual(json.load(stream)['stage'],'COMPLETE')

    def test_activation_failure_restores_new_files_and_legacy_without_restart(self):
        value,runtime,activation,cutover,receipt=self.make(FakeRuntime(fail=True))
        with self.assertRaisesRegex(RuntimeError,'planned'): value.execute(self.plan)
        self.assertEqual(runtime.calls,
                         ['preflight','provision','activate','stop_new','restore'])
        self.assertTrue(cutover.adapter.restored)
        with open(receipt) as stream: result=json.load(stream)
        self.assertEqual(result['stage'],'ROLLED_BACK')
        self.assertFalse(result['legacy_writer_restarted'])
        self.assertIn('BEFORE_ANY_RESTART',result['recovery'])

    def test_existing_receipt_blocks_replay_before_any_effect(self):
        value,runtime,activation,cutover,receipt=self.make()
        with open(receipt,'w') as stream: stream.write('{}')
        os.chmod(receipt,0o600)
        with self.assertRaisesRegex(ValueError,'RECONCILIATION_REQUIRED'):
            value.execute(self.plan)
        self.assertEqual(runtime.calls,[])

    def test_auth_and_tls_must_be_existing_references_not_fallbacks(self):
        for section in ('auth','tls'):
            broken=json.loads(json.dumps(self.plan))
            broken[section]['mode']='API_KEY_FALLBACK'
            with self.assertRaisesRegex(ValueError,'REFERENCE_BINDING'):
                module.validate_plan(broken)

    def test_release_identity_mismatch_rolls_back_without_cutover(self):
        runtime=FakeRuntime(); activation=FakeActivation(); cutover=FakeCutover()
        receipt=os.path.join(self.parent,'mismatch.json')
        cutover.receipt_path=os.path.join(self.parent,'cutover-mismatch.json')
        value=module.P2InstallEntrypoint(receipt,lambda artifact:'/wrong',
                                         cutover,activation,runtime)
        with self.assertRaisesRegex(ValueError,'RELEASE_IDENTITY_MISMATCH'):
            value.execute(self.plan)
        self.assertEqual(cutover.calls,[])
        self.assertFalse(cutover.adapter.restored)
        self.assertEqual(runtime.calls,['preflight','stop_new'])

    def test_cutover_stop_failure_uses_durable_boundary_for_exact_restore(self):
        value,runtime,activation,cutover,receipt=self.make()
        def fail(plan):
            cutover.calls.append(plan)
            module._atomic_receipt(cutover.receipt_path,
                {'transaction_id':self.plan['transaction_id'],'stage':'HOLD',
                 'failed_stage':'STOP_REQUESTED'})
            raise RuntimeError('partial stop')
        cutover.execute=fail
        with self.assertRaisesRegex(RuntimeError,'partial stop'):
            value.execute(self.plan)
        self.assertTrue(cutover.adapter.restored)
        with open(receipt) as stream: result=json.load(stream)
        self.assertEqual(result['stage'],'ROLLED_BACK')
        self.assertIn('LEGACY_FILES_RESTORED_NOT_RESTARTED',result['rollback'])


if __name__=='__main__': unittest.main()
