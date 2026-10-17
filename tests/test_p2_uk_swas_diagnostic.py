import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import p2_uk_swas_diagnostic as d


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.chmod(self.tmp.name,0o700)
        self.ledger=d.Ledger(self.tmp.name)
        self.addCleanup(self.ledger.close)
        self.calls=[]
        self.nonce='fixture_nonce'
        self.sha=hashlib.sha256(d.command(self.nonce).encode()).hexdigest()

    def rpc(self,endpoint,action,**kw):
        self.calls.append((endpoint,action,kw))
        if action=='RunCommand':return {'InvokeId':'t-fixture'}
        body=dict(hostname=d.receipt.HOST,uid=0,python=[3,6,8],nonce=self.nonce,private_inputs_read=False)
        return {'InvocationResult':dict(InvokeId='t-fixture',InstanceId=d.receipt.INSTANCE,InvocationStatus='Success',ExitCode=0,Output=json.dumps(body))}

    def start(self):return d.dispatch_once(self.ledger,'fixture_attempt',self.nonce,self.sha,self.rpc)

    def test_complete_fixed_uk_transport(self):
        self.start();r=d.poll_existing(self.ledger,self.rpc)
        self.assertEqual(r['state'],'TRANSPORT_VERIFIED')
        self.assertFalse(r['p2_accepted'])
        self.assertTrue(all(c[0]==d.ENDPOINT for c in self.calls))
        self.assertEqual(self.calls[0][2]['InstanceId'],d.receipt.INSTANCE)

    def test_second_dispatch_rejected(self):
        self.start()
        with self.assertRaises(FileExistsError):self.start()
        self.assertEqual(len(self.calls),1)

    def test_unknown_dispatch_consumed(self):
        def unknown(*a,**k):self.calls.append('network');raise OSError('PRIVATE')
        with self.assertRaises(RuntimeError) as c:d.dispatch_once(self.ledger,'a',self.nonce,self.sha,unknown)
        self.assertNotIn('PRIVATE',str(c.exception))
        with self.assertRaises(FileExistsError):self.start()
        self.assertEqual(self.calls,['network'])

    def test_fsync_failure_prevents_dispatch(self):
        with patch.object(d.os,'fsync',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.start()
        self.assertEqual(self.calls,[])
        with self.assertRaises(FileExistsError):self.start()

    def test_crash_before_invoke_persist_no_redispatch(self):
        original=self.ledger.create
        def fail(name,value):
            if name=='invoke.json':raise OSError('fixture')
            return original(name,value)
        with patch.object(self.ledger,'create',side_effect=fail),self.assertRaises(RuntimeError):self.start()
        with self.assertRaises(FileExistsError):self.start()
        self.assertEqual(len(self.calls),1)
        with self.assertRaises(FileNotFoundError):d.poll_existing(self.ledger,self.rpc)

    def test_bad_hash_before_consumption(self):
        with self.assertRaises(RuntimeError):d.dispatch_once(self.ledger,'a',self.nonce,'wrong',self.rpc)
        self.assertEqual(os.listdir(self.tmp.name),[])
        self.assertEqual(self.calls,[])

    def test_timeout_only_requery_same_invoke(self):
        self.start()
        def pending(*a,**kw):return {'InvocationResult':dict(InvokeId='t-fixture',InstanceId=d.receipt.INSTANCE,InvocationStatus='Running')}
        r=d.poll_existing(self.ledger,pending,2)
        self.assertEqual(r['state'],'QUERY_LIMIT_UNKNOWN')
        self.assertFalse(r['redispatch_allowed'])
        d.poll_existing(self.ledger,self.rpc)
        self.assertEqual(sum(x[1]=='RunCommand' for x in self.calls),1)

    def test_terminal_rejected_and_no_repoll(self):
        self.start()
        def bad(*a,**kw):
            v=self.rpc(*a,**kw);v['InvocationResult']['Output']='PRIVATE';return v
        with self.assertRaises(RuntimeError):d.poll_existing(self.ledger,bad)
        with self.assertRaises(RuntimeError):d.poll_existing(self.ledger,self.rpc)
        self.assertTrue((Path(self.tmp.name)/'rejected.json').exists())

    def test_complete_receipt_no_repoll(self):
        self.start();d.poll_existing(self.ledger,self.rpc)
        with self.assertRaises(RuntimeError):d.poll_existing(self.ledger,self.rpc)

    def test_nonce_command_injection_rejected(self):
        with self.assertRaises(RuntimeError):d.command("a'; rm -rf /")

    def test_ledger_permissions(self):
        os.chmod(self.tmp.name,0o755)
        with self.assertRaises(RuntimeError):d.Ledger(self.tmp.name)

    def test_query_network_failure_keeps_saved_invoke(self):
        self.start()
        for error in (OSError('PRIVATE'),RuntimeError('PRIVATE')):
            def fail(*a,**kw):raise error
            with self.assertRaises(RuntimeError) as c:d.poll_existing(self.ledger,fail)
            self.assertNotIn('PRIVATE',str(c.exception))
        d.poll_existing(self.ledger,self.rpc)
        self.assertEqual(sum(x[1]=='RunCommand' for x in self.calls),1)



class AdapterGateTests(unittest.TestCase):
    def permit(self):
        binding={'fixture':'exact'}
        p=dict(decision='UK_TRANSPORT_APPROVED',binding=binding,issued_unix=100,
               expires_unix=200,max_attempts=1,private_inputs_allowed=False,install_allowed=False)
        body='P2_UK_TRANSPORT_ONCE\n'+json.dumps(p)
        t=dict(enabled=True,revoked=False,reviewer_principal='fixture-reviewer',
               source_writer_principal='fixture-writer',custody_evidence_sha256='a'*64,
               approval_body_sha256=hashlib.sha256(body.encode()).hexdigest())
        return p,body,t,binding

    def test_exact_authorization(self):
        p,body,t,binding=self.permit()
        self.assertEqual(d.authorize(body,t,binding,150),t['approval_body_sha256'])

    def test_author_self_approval_refused(self):
        p,body,t,binding=self.permit();t['reviewer_principal']='fixture-writer'
        with self.assertRaises(RuntimeError):d.authorize(body,t,binding,150)

    def test_expired_future_revoked_disabled(self):
        p,body,t,binding=self.permit()
        for now in (99,200):
            with self.subTest(now=now),self.assertRaises(RuntimeError):d.authorize(body,t,binding,now)
        for k,v in (('revoked',True),('enabled',False)):
            tt=dict(t);tt[k]=v
            with self.subTest(k=k),self.assertRaises(RuntimeError):d.authorize(body,tt,binding,150)

    def test_changed_body_and_binding(self):
        p,body,t,binding=self.permit()
        with self.assertRaises(RuntimeError):d.authorize(body+' ',t,binding,150)
        with self.assertRaises(RuntimeError):d.authorize(body,t,{'fixture':'other'},150)

    def test_boolean_attempt_and_permission_expansion_refused(self):
        p,body,t,binding=self.permit()
        for k,v in (('max_attempts',True),('private_inputs_allowed',True),('install_allowed',True)):
            changed=dict(p);changed[k]=v
            b='P2_UK_TRANSPORT_ONCE\n'+json.dumps(changed);tt=dict(t,approval_body_sha256=hashlib.sha256(b.encode()).hexdigest())
            with self.subTest(k=k),self.assertRaises(RuntimeError):d.authorize(b,tt,binding,150)

    class Response:
        def __init__(self,raw):self.raw=raw
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):return self.raw[:limit]

    def test_sts_and_fixed_endpoint_signature(self):
        import urllib.parse
        calls=[]
        outer=self
        class Opener:
            def open(self,req,timeout):
                params=urllib.parse.parse_qs(req.data.decode());calls.append((req.full_url,params,timeout))
                if params['Action']==['AssumeRole']:
                    return outer.Response(json.dumps({'Credentials':{'AccessKeyId':'fixture-temp','AccessKeySecret':'fixture-secret','SecurityToken':'fixture-token'}}).encode())
                return outer.Response(b'{"InvokeId":"t-fixture"}')
        rpc=d.AuthenticatedRPC('fixture-key','fixture-master',opener=Opener(),clock=lambda:100)
        rpc.assume();rpc(d.ENDPOINT,'RunCommand',RegionId=d.receipt.REGION,InstanceId=d.receipt.INSTANCE)
        self.assertEqual(calls[0][1]['RoleArn'],[d.ROLE])
        self.assertIn('Signature',calls[1][1]);self.assertIn('SecurityToken',calls[1][1])
        self.assertTrue(all(0<c[2]<=20 for c in calls))

    def test_wrong_host_before_network(self):
        class Reject:
            def open(self,*a,**k):raise AssertionError('network must not be called')
        rpc=d.AuthenticatedRPC('fixture','fixture',opener=Reject())
        rpc.credentials=('fixture','fixture','fixture')
        with self.assertRaises(RuntimeError):rpc('swas.cn-shanghai.aliyuncs.com','RunCommand',RegionId='cn-shanghai',InstanceId='other')

    def test_rpc_errors_and_raw_secrets_redacted(self):
        class Broken:
            def open(self,*a,**k):raise RuntimeError('PRIVATE_CREDENTIAL')
        rpc=d.AuthenticatedRPC('fixture','fixture',opener=Broken())
        with self.assertRaises(RuntimeError) as c:rpc.assume()
        self.assertNotIn('PRIVATE_CREDENTIAL',str(c.exception))

    def test_deadline_stops_network(self):
        times=iter((0,181))
        class Reject:
            def open(self,*a,**k):raise AssertionError('network must not be called')
        rpc=d.AuthenticatedRPC('fixture','fixture',opener=Reject(),clock=lambda:next(times))
        with self.assertRaises(RuntimeError):rpc.assume()

    def test_missing_root_policy_no_credential_acquisition(self):
        with tempfile.TemporaryDirectory() as root:
            os.chmod(root,0o700);ledger=d.Ledger(root)
            try:
                with patch.object(d,'protected_json',side_effect=FileNotFoundError()),patch('builtins.input',side_effect=AssertionError('no TTY')),self.assertRaises(RuntimeError):
                    d.authorized_dispatch(ledger,'fixture','fixture',Path('/missing'),lambda n:'',lambda:(_ for _ in ()).throw(AssertionError('no credentials')),Path('/missing-epoch'))
            finally:ledger.close()

    def test_lock_contention_stops_before_policy(self):
        import fcntl
        with tempfile.TemporaryDirectory() as root:
            os.chmod(root,0o700);ledger=d.Ledger(root)
            fd=os.open(str(Path(root)/'caller.lock'),os.O_CREAT|os.O_RDWR,0o600)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.object(d,'protected_json',side_effect=AssertionError('locked')),self.assertRaises(RuntimeError):
                    d.authorized_dispatch(ledger,'fixture','fixture',Path('/missing'),lambda n:'',lambda:None,Path('/missing'))
            finally:os.close(fd);ledger.close()

if __name__=='__main__':unittest.main()
