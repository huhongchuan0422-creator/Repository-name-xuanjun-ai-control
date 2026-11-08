import base64, copy, hashlib, json, multiprocessing, os, sqlite3, tempfile, threading, unittest
import sys
from unittest import mock
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','scripts'))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from development_authority import SQLiteReplayGuard
from development_authority import canonical_bytes
from development_authority_provider import load_config, make_server
import development_authority_release as release
from development_authority_release import manifest, verify, lifecycle
from task_supervisor import Supervisor

def consume(path,key,out):
    guard=SQLiteReplayGuard(path)
    try: out.put(guard(key))
    except Exception: out.put('UNKNOWN')
    finally: guard.close()

class SecurityRegressions(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory()
    def tearDown(self): self.tmp.cleanup()
    def secret(self,name,value):
        path=os.path.join(self.tmp.name,name)
        with open(path,'w') as stream: stream.write(value)
        os.chmod(path,0o600); return path
    def signed_provider_config(self,forbidden,required=None):
        deployment=Ed25519PrivateKey.generate(); issuer=Ed25519PrivateKey.generate()
        public=deployment.public_key().public_bytes(
          serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        private=issuer.private_bytes(serialization.Encoding.PEM,
          serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
        replay=os.path.join(self.tmp.name,'replay.db'); SQLiteReplayGuard(replay).close()
        ledger=os.path.join(self.tmp.name,'formal.db'); db=sqlite3.connect(ledger)
        db.executescript("CREATE TABLE IF NOT EXISTS tasks(task_id TEXT); CREATE TABLE IF NOT EXISTS resource_claims(resource_key TEXT); CREATE TABLE IF NOT EXISTS authority_runtime_profile(singleton INTEGER PRIMARY KEY,profile TEXT); INSERT OR REPLACE INTO authority_runtime_profile VALUES(1,'FORMAL');")
        db.commit(); db.close()
        policy_unsigned={'schema':1,'deployment_class':'formal-primary',
          'forbidden_ledger_paths':list(required if required is not None else [os.path.join(self.tmp.name,'test-a.db'),os.path.join(self.tmp.name,'test-b.db')])}
        policy_raw=canonical_bytes(policy_unsigned)
        policy=dict(policy_unsigned,signature={'algorithm':'Ed25519','anchor_id':'deploy-1',
          'canonical_sha256':hashlib.sha256(policy_raw).hexdigest(),
          'value':base64.b64encode(deployment.sign(policy_raw)).decode()})
        config={'ledger_db':ledger,'replay_db':replay,
          'replay_device':os.stat(replay).st_dev,'replay_inode':os.stat(replay).st_ino,
          'forbidden_ledger_paths':list(forbidden),
          'forbidden_ledger_policy_file':self.secret('policy.json',json.dumps(policy)),
          'deployment_class':'formal-primary','issuer':'formal','instance_id':'one',
          'version':'3','anchor_id':'authority-1','service_id':'reader-1',
          'bearer_token_file':self.secret('token','t'*32),
          'private_key_file':self.secret('issuer.pem',private),
          'deployment_public_key_file':self.secret('deploy.pem',public),
          'deployment_anchor_id':'deploy-1'}
        raw=canonical_bytes(config); config['deployment_signature']={
          'algorithm':'Ed25519','anchor_id':'deploy-1',
          'canonical_sha256':hashlib.sha256(raw).hexdigest(),
          'value':base64.b64encode(deployment.sign(raw)).decode()}
        return self.secret('provider.json',json.dumps(config))
    def test_release_every_manifest_field_and_signature_tamper_rejects(self):
        artifact=os.path.join(self.tmp.name,'artifact.tar'); open(artifact,'wb').write(b'bytes')
        key=Ed25519PrivateKey.generate(); source='f'*64
        value=manifest(artifact,'a'*40,'b'*40,source,key,'release-anchor',1000)
        self.assertTrue(verify(artifact,value,key.public_key(),'release-anchor','a'*40,'b'*40,source)['verified'])
        for field in sorted(value):
            bad=copy.deepcopy(value)
            if field=='signature': bad[field]['value']='AAAA'
            elif field=='deployment_authorized': bad[field]=True
            elif field=='schema': bad[field]=999
            elif isinstance(bad[field],str): bad[field]='tampered'
            else: bad[field]=999
            with self.assertRaises(ValueError,msg=field):
                verify(artifact,bad,key.public_key(),'release-anchor','a'*40,'b'*40,source)
    def test_inspect_apply_query_recover_rotates_backup_and_receipts(self):
        root=os.path.join(self.tmp.name,'lifecycle'); one=os.path.join(self.tmp.name,'one'); two=os.path.join(self.tmp.name,'two')
        open(one,'wb').write(b'one'); open(two,'wb').write(b'two')
        self.assertIsNone(lifecycle(root,'inspect')['state']['active'])
        lifecycle(root,'apply',one,{'verified':True}); lifecycle(root,'apply',two,{'verified':True})
        before=lifecycle(root,'query')['state']; self.assertEqual(before['active'],__import__('hashlib').sha256(b'two').hexdigest())
        receipt=lifecycle(root,'recover',operation_id='recover-1',
          expected_generation=2,expected_status='ACTIVE')
        self.assertEqual(receipt,lifecycle(root,'recover',operation_id='recover-1',
          expected_generation=2,expected_status='ACTIVE'))
        with self.assertRaisesRegex(ValueError,'REQUEST_MISMATCH'):
            lifecycle(root,'recover',operation_id='recover-1',
              expected_generation=3,expected_status='ACTIVE')
        after=lifecycle(root,'query'); self.assertEqual(after['state']['active'],__import__('hashlib').sha256(b'one').hexdigest()); self.assertEqual(after['state']['generation'],3)

    def test_recover_expected_state_cas_and_restart_idempotency(self):
        root=os.path.join(self.tmp.name,'recover-cas'); one=os.path.join(self.tmp.name,'one')
        open(one,'wb').write(b'one'); lifecycle(root,'apply',one,{'verified':True})
        with self.assertRaisesRegex(ValueError,'CAS'):
            lifecycle(root,'recover',operation_id='wrong-generation',
              expected_generation=0,expected_status='ACTIVE')
        # A new invocation reads the durable operation receipt and cannot toggle again.
        state=lifecycle(root,'query')['state']; self.assertEqual(state['generation'],1)
    def test_signed_formal_provider_cannot_empty_omit_or_replace_forbidden_policy(self):
        required=[os.path.join(self.tmp.name,'test-a.db'),os.path.join(self.tmp.name,'test-b.db')]
        with mock.patch.dict('development_authority_provider.TRUSTED_DEPLOYMENT_CLASSES',
                             {'formal-primary':frozenset(required)},clear=True):
            for index,forbidden in enumerate(([],required[:1],
                                             [os.path.join(self.tmp.name,'other.db')])):
                with self.subTest(index=index), self.assertRaisesRegex(ValueError,
                  'REQUIRED_FORBIDDEN|EXACT_AUTHORITY'):
                    load_config(self.signed_provider_config(forbidden,required))
            config=load_config(self.signed_provider_config(required,required))
            server=make_server(config,port=0); server.server_close()
            os.symlink(config['ledger_db'],required[0])
            with self.assertRaisesRegex(ValueError,'FORMAL_LEDGER_FILE_IDENTITY'):
                make_server(config,port=0)

    def test_recover_fault_boundaries_restart_and_concurrent_retry_return_one_receipt(self):
        for failpoint in ('recover_after_prepared','recover_after_state',
                          'recover_after_receipt','recover_after_completed'):
            root=os.path.join(self.tmp.name,failpoint); one=root+'-one'; two=root+'-two'
            open(one,'wb').write(b'one'); open(two,'wb').write(b'two')
            lifecycle(root,'apply',one,{'verified':True}); lifecycle(root,'apply',two,{'verified':True})
            original=release._lifecycle_failpoint
            def fail(name,target=failpoint):
                if name==target: raise RuntimeError('injected '+name)
            release._lifecycle_failpoint=fail
            try:
                with self.assertRaisesRegex(RuntimeError,'injected'):
                    lifecycle(root,'recover',operation_id='same-op',
                      expected_generation=2,expected_status='ACTIVE')
            finally: release._lifecycle_failpoint=original
            results=[]
            def retry():
                results.append(lifecycle(root,'recover',operation_id='same-op',
                  expected_generation=2,expected_status='ACTIVE'))
            threads=[threading.Thread(target=retry) for _ in range(4)]
            [thread.start() for thread in threads]; [thread.join() for thread in threads]
            self.assertEqual(results,[results[0]]*4)
            self.assertEqual(results[0],lifecycle(root,'recover',operation_id='same-op',
              expected_generation=2,expected_status='ACTIVE'))
            self.assertEqual(lifecycle(root,'query')['state']['generation'],3)
    def test_arbitrary_verifier_injection_is_rejected(self):
        path=os.path.join(self.tmp.name,'ledger')
        with self.assertRaisesRegex(ValueError,'CONTROLLED'):
            Supervisor(path,development_identity_verifier=lambda *x:{})
    def test_formal_open_rejects_test_only_ledger_despite_environment(self):
        from task_supervisor import TestOnlyDevelopmentIdentityVerifier
        from development_authority import open_verified_ledger
        os.environ['XUANJUN_TEST_ONLY_IDENTITY']='1'
        path=os.path.join(self.tmp.name,'test-only-ledger')
        supervisor=Supervisor(path,development_identity_verifier=
          TestOnlyDevelopmentIdentityVerifier(lambda *x:{})); supervisor.close()
        with self.assertRaisesRegex(ValueError,'TEST_ONLY_LEDGER_FORBIDDEN'):
            open_verified_ledger(path,formal_only=True)
    def test_shared_multiprocess_ledger_has_one_global_authorization(self):
        path=os.path.join(self.tmp.name,'shared.db'); SQLiteReplayGuard(path).close()
        queue=multiprocessing.Queue(); key=('issuer','instance','AUTHORIZATION_CONSUME','a'*64,'nonce')
        procs=[multiprocessing.Process(target=consume,args=(path,key,queue)) for _ in range(4)]
        [p.start() for p in procs]; [p.join() for p in procs]
        self.assertEqual(sorted(queue.get() for _ in procs),[False,False,False,True])
    def test_purposes_are_isolated_but_authorization_never_repeats(self):
        path=os.path.join(self.tmp.name,'purpose.db'); guard=SQLiteReplayGuard(path)
        self.assertTrue(guard(('i','n','STATUS_QUERY','a'*64,'same')))
        self.assertTrue(guard(('i','n','AUTHORIZATION_CONSUME','a'*64,'same')))
        self.assertFalse(guard(('i','n','AUTHORIZATION_CONSUME','a'*64,'same')))
        self.assertTrue(guard(('i','n','AUTHORIZATION_CONSUME','b'*64,'same')))
        self.assertTrue(guard(('i','n','INSPECT','a'*64,'same'))); self.assertTrue(guard(('i','n','RECOVER','a'*64,'same'))); guard.close()

if __name__=='__main__': unittest.main()
