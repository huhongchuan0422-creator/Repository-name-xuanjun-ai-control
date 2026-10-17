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



class ProtectedEntryTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        self.assertEqual(os.geteuid(),0,'Root fixtures required; run offline tests via sudo')
        self.tmp=tempfile.TemporaryDirectory(prefix='p2-offline-root-fixture-',dir='/root')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);os.chmod(str(self.root),0o700)
        self.control=self.root/'control';self.control.mkdir(mode=0o700)
        self.folder=self.root/'attempt';self.folder.mkdir(mode=0o700)
        def load(name,source):
            target=self.root/(name+'.py');target.write_bytes(Path(source).read_bytes());target.chmod(0o400)
            spec=importlib.util.spec_from_file_location(name,str(target));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
        self.m=load('transport_fixture',d.__file__)
        self.m.receipt=load('receipt_fixture',d.receipt.__file__)
        self.m.CONTROL=self.control
        self.calls=[];outer=self
        class RPC:
            def __init__(self,key,secret):outer.calls.append(('credentials',key,secret))
            def assume(self):outer.calls.append(('assume',))
            def __call__(self,endpoint,action,**kw):
                outer.calls.append((action,kw))
                if action=='RunCommand':return {'InvokeId':'t-fixture'}
                b=dict(hostname=d.receipt.HOST,uid=0,python=[3,6,8],nonce='fixture_nonce',private_inputs_read=False)
                return {'InvocationResult':dict(InvokeId='t-fixture',InstanceId=d.receipt.INSTANCE,InvocationStatus='Success',ExitCode=0,Output=json.dumps(b))}
        self.m.AuthenticatedRPC=RPC
        self.save('WRITER_EPOCH.json',{'state':'EXCLUSIVE','writer':'fixture-writer'})
        self.save('CREDENTIALS.json',{'AccessKeyId':'fixture-key','AccessKeySecret':'fixture-secret'})
        self.configure('RUN_COMMAND',100)
        self.m.fetch_approval=lambda ident:self.body

    def save(self,name,value):
        p=self.control/name
        if p.exists():p.chmod(0o600)
        p.write_bytes(d.canonical(value));p.chmod(0o400)

    def configure(self,operation,ident):
        import time
        now=int(time.time())
        epoch_sha=hashlib.sha256((self.control/'WRITER_EPOCH.json').read_bytes()).hexdigest()
        binding=dict(operation=operation,attempt='fixture_attempt',nonce='fixture_nonce',host=d.receipt.HOST,
                     instance_id=d.receipt.INSTANCE,region=d.receipt.REGION,role=d.ROLE,
                     script_sha256=hashlib.sha256(d.command('fixture_nonce').encode()).hexdigest(),
                     code_sha256={'transport':hashlib.sha256(Path(self.m.__file__).read_bytes()).hexdigest(),
                                  'receipt':hashlib.sha256(Path(self.m.receipt.__file__).read_bytes()).hexdigest()},
                     writer_epoch_sha256=epoch_sha)
        p=dict(decision='UK_TRANSPORT_APPROVED',binding=binding,issued_unix=now-1,expires_unix=now+60,
               max_attempts=1,private_inputs_allowed=False,install_allowed=False)
        self.body='P2_UK_TRANSPORT_ONCE\n'+json.dumps(p)
        trust=dict(enabled=True,revoked=False,reviewer_principal='fixture-reviewer',source_writer_principal='fixture-writer',
                   custody_evidence_sha256='f'*64,approval_body_sha256=hashlib.sha256(self.body.encode()).hexdigest(),
                   approval_comment_id=ident,writer_epoch_sha256=epoch_sha,binding=binding,
                   ledger_path=str(self.folder),code_paths={'transport':self.m.__file__,'receipt':self.m.receipt.__file__})
        self.save('TRUST.json',trust)

    def test_real_root_files_to_dispatch_and_separate_query(self):
        r=self.m.protected_entry('run-once');self.assertEqual(r['invoke_id'],'t-fixture')
        with self.assertRaises(RuntimeError):self.m.protected_entry('run-once')
        self.configure('QUERY_EXISTING',101)
        r=self.m.protected_entry('query-existing');self.assertEqual(r['state'],'TRANSPORT_VERIFIED')
        self.assertFalse(r['p2_accepted'])
        self.assertEqual(sum(c[0]=='RunCommand' for c in self.calls),1)
        with self.assertRaises(RuntimeError):self.m.protected_entry('query-existing')
        self.assertEqual(sum(c[0]=='assume' for c in self.calls),2)

    def test_isolated_cli_rejects_missing_sibling_without_pythonpath_import(self):
        import subprocess
        import sys
        evil=self.root/'evil';(evil/'scripts').mkdir(parents=True)
        marker=self.root/'injected'
        (evil/'scripts'/'__init__.py').write_text('open('+repr(str(marker))+',"w").write("bad")')
        result=subprocess.run([sys.executable,'-I','-B',self.m.__file__,'run-once'],
                              cwd=str(evil),env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(evil)},
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.assertEqual(result.returncode,2)
        self.assertFalse(marker.exists())
        self.assertNotIn(b'Traceback',result.stderr)

    def test_isolated_cli_rejects_fifo_before_read(self):
        import subprocess
        import sys
        fifo=self.root/'p2_swas_receipt_validator.py'
        os.mkfifo(str(fifo),0o400)
        result=subprocess.run([sys.executable,'-I','-B',self.m.__file__,'run-once'],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3)
        self.assertEqual(result.returncode,2)
        self.assertNotIn(b'Traceback',result.stderr)

    def test_credential_mode_refused_before_sts(self):
        (self.control/'CREDENTIALS.json').chmod(0o644)
        with self.assertRaises(RuntimeError):self.m.protected_entry('run-once')
        self.assertEqual(self.calls,[])
        self.assertFalse((self.folder/'dispatch-intent.json').exists())

    def test_epoch_drift_stops_before_credentials(self):
        self.save('WRITER_EPOCH.json',{'state':'EXCLUSIVE','writer':'other'})
        with self.assertRaises(RuntimeError):self.m.protected_entry('run-once')
        self.assertEqual(self.calls,[])

    def test_source_byte_drift_stops(self):
        p=Path(self.m.__file__);p.chmod(0o600);p.write_bytes(p.read_bytes()+b'\n# fixture drift\n');p.chmod(0o400)
        with self.assertRaises(RuntimeError):self.m.protected_entry('run-once')
        self.assertEqual(self.calls,[])

    def test_ledger_substitution_stops(self):
        moved=self.root/'moved';self.folder.rename(moved);self.folder.symlink_to(moved,target_is_directory=True)
        with self.assertRaises((RuntimeError,OSError)):self.m.protected_entry('run-once')
        self.assertEqual(self.calls,[])

    def test_approval_changed_after_sts_stops_before_command(self):
        original=self.m.AuthenticatedRPC;outer=self
        class Changed(original):
            def assume(self):
                super().assume();outer.body+=' '
        self.m.AuthenticatedRPC=Changed
        with self.assertRaises(RuntimeError):self.m.protected_entry('run-once')
        self.assertEqual(sum(c[0]=='RunCommand' for c in self.calls),0)


class EntryProvenanceSupervisorTests(unittest.TestCase):
    def test_exact_comment_metadata(self):
        value={'id':123,'user':{'id':d.OWNER_ID,'login':d.OWNER_LOGIN},
               'issue_url':'https://api.github.com/repos/'+d.REPOSITORY+'/issues/58','body':'fixture'}
        class Opener:
            def open(self,req,timeout):
                self.request=req;return AdapterGateTests.Response(json.dumps(value).encode())
        opener=Opener();self.assertEqual(d.fetch_approval(123,opener),'fixture')
        self.assertTrue(opener.request.full_url.startswith('https://api.github.com/repos/'+d.REPOSITORY+'/'))
        for k,v in (('id',124),('issue_url','https://evil.invalid/'),('user',{'id':999,'login':d.OWNER_LOGIN})):
            old=value[k];value[k]=v
            with self.subTest(k=k),self.assertRaises(RuntimeError):d.fetch_approval(123,opener)
            value[k]=old

    def test_child_success_and_failure_exit(self):
        self.assertEqual(d.supervise('run-once',2,operation=lambda action:{'state':'fixture'}),0)
        def fail(action):raise RuntimeError('PRIVATE')
        self.assertEqual(d.supervise('run-once',2,operation=fail),2)

    def test_real_fork_timeout_no_new_dispatch(self):
        import time
        def hang(action):time.sleep(10)
        started=time.monotonic()
        self.assertEqual(d.supervise('run-once',1,operation=hang),2)
        self.assertLess(time.monotonic()-started,4)


if __name__=='__main__':unittest.main()


class RecoveryCheckpointTests(unittest.TestCase):
    setUp=TransportTests.setUp
    rpc=TransportTests.rpc
    start=TransportTests.start
    # The inherited transport cases also run against this fixture.
    def snapshot(self):return d.recovery_snapshot(self.ledger)

    def test_empty_is_not_authority(self):
        self.assertEqual(self.snapshot()['state'],'NO_DISPATCH_RECORD_NO_AUTHORITY')
        self.assertFalse(self.snapshot()['redispatch_allowed'])
        self.assertEqual(self.calls,[])

    def test_restart_saved_invoke_query_only(self):
        self.start()
        other=d.Ledger(self.tmp.name)
        try:r=d.recovery_snapshot(other)
        finally:other.close()
        self.assertEqual(r['state'],'QUERY_SAVED_INVOKE_ONLY')
        self.assertEqual(r['invoke_id'],'t-fixture')
        self.assertEqual(len(self.calls),1)

    def test_unknown_without_id_never_reruns(self):
        with self.assertRaises(RuntimeError):
            d.dispatch_once(self.ledger,'a',self.nonce,self.sha,
                            lambda *a,**k: (_ for _ in ()).throw(OSError()))
        self.assertEqual(self.snapshot()['state'],'DISPATCH_UNKNOWN_NO_INVOKE_NO_RETRY')
        with self.assertRaises(FileExistsError):self.start()

    def test_terminal_verified_no_replay(self):
        self.start();d.poll_existing(self.ledger,self.rpc)
        self.assertEqual(self.snapshot()['state'],'TERMINAL_VERIFIED_NO_REPLAY')

    def test_orphan_invoke_rejected(self):
        self.ledger.create('invoke.json',{'invoke_id':'t-fixture'})
        with self.assertRaises(RuntimeError):self.snapshot()

    def test_torn_record_rejected(self):
        Path(self.tmp.name,'dispatch-intent.json').write_text('{')
        os.chmod(Path(self.tmp.name,'dispatch-intent.json'),0o600)
        with self.assertRaises(ValueError):self.snapshot()

    def test_cross_host_intent_rejected(self):
        self.ledger.create('dispatch-intent.json',{'state':'DISPATCH_INTENT',
            'attempt':'a','nonce':self.nonce,'script_sha256':self.sha,
            'instance_id':'wrong','region':d.receipt.REGION})
        with self.assertRaises(RuntimeError):self.snapshot()

    def test_terminal_conflict_rejected(self):
        self.start();d.poll_existing(self.ledger,self.rpc)
        self.ledger.create('rejected.json',{'state':'TERMINAL_REJECTED','invoke_id':'t-fixture'})
        with self.assertRaises(RuntimeError):self.snapshot()


class RemoteIdentityProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        os.chmod(self.tmp.name,0o700)
        self.ledger=d.Ledger(self.tmp.name);self.addCleanup(self.ledger.close)
        self.active={'ledger_uuid':'uuid','generation':1,'epoch':7,'instance':'instance',
                     'db_path':'/canonical/state.sqlite','ledger_socket':'/run/ledger.sock'}
        self.request={'schema':1,'operation':'UK_READONLY_IDENTITY','attempt':'attempt',
            'nonce':'nonce','task_id':'task','lease_owner':'writer','fence':3,
            'activation':dict(self.active),'expires_unix':200,'approval_sha256':'a'*64}
        self.obs=dict(self.active,task_id='task',state='RUNNING',lease_owner='writer',
                      lease_until=150,fence=3,checkpoint={})
        self.store=type('Store',(),{'read':lambda obj,require_active:dict(self.active,state='ACTIVE')})()
        self.broker=type('Broker',(),{'observation':lambda obj,task:dict(self.obs)})()
        self.approval=lambda request,digest:True
        self.p1=patch.object(d.os,'uname',return_value=type('Host',(),{'nodename':d.receipt.HOST})())
        self.p1.start();self.addCleanup(self.p1.stop)
        self.p2=patch('sys.version_info',(3,6,8));self.p2.start();self.addCleanup(self.p2.stop)

    def run_request(self,request=None):
        return d.consume_remote_identity(self.ledger,request or self.request,self.request,
            self.store,self.broker,self.approval,lambda:100)

    def test_first_consumption_and_restart_replay(self):
        self.assertEqual(self.run_request()['state'],'REMOTE_IDENTITY_COMPLETE')
        self.assertEqual(self.run_request()['state'],'REMOTE_RESULT_REPLAY')
        self.assertFalse(self.run_request()['redispatch_allowed'])

    def test_unactivated_mechanism_holds_without_intent(self):
        def inactive(require_active):raise RuntimeError('NOT_ACTIVE')
        self.store.read=inactive
        with self.assertRaises(RuntimeError):self.run_request()
        with self.assertRaises(FileNotFoundError):self.ledger.read('remote-intent.json')

    def test_client_cannot_select_new_task(self):
        with self.assertRaises(RuntimeError):self.run_request(dict(self.request,task_id='other'))

    def test_stale_writer_denied(self):
        self.obs['lease_owner']='other'
        with self.assertRaises(RuntimeError):self.run_request()

    def test_expired_lease_denied(self):
        self.obs['lease_until']=99
        with self.assertRaises(RuntimeError):self.run_request()

    def test_revoked_approval_denies_replay(self):
        self.run_request();self.approval=lambda *args:False
        with self.assertRaises(RuntimeError):self.run_request()

    def test_partial_execution_is_not_reexecuted(self):
        digest=hashlib.sha256(d.canonical(self.request)).hexdigest()
        self.ledger.create('remote-intent.json',{'request_sha256':digest,'state':'REMOTE_IDENTITY_INTENT'})
        self.assertEqual(self.run_request()['state'],'REMOTE_EXECUTION_UNKNOWN')
        with self.assertRaises(FileNotFoundError):self.ledger.read('remote-result.json')

    def test_activation_changes_during_observation(self):
        def change(task):
            self.active['epoch']=8
            return dict(self.obs)
        self.broker.observation=change
        with self.assertRaises(RuntimeError):self.run_request()
