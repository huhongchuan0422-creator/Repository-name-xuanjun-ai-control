import copy, multiprocessing, os, tempfile, unittest
import sys
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','scripts'))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from development_authority import SQLiteReplayGuard
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
        lifecycle(root,'recover'); after=lifecycle(root,'query'); self.assertEqual(after['state']['active'],__import__('hashlib').sha256(b'one').hexdigest()); self.assertEqual(len(after['receipt_files']),3)
    def test_arbitrary_verifier_injection_is_rejected(self):
        path=os.path.join(self.tmp.name,'ledger')
        with self.assertRaisesRegex(ValueError,'CONTROLLED'):
            Supervisor(path,development_identity_verifier=lambda *x:{})
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
