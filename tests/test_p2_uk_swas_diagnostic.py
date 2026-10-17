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


class SplitCloudTests(unittest.TestCase):
    # Reuse only setup, not inherited test methods.
    def setUp(self):
        RemoteIdentityProtocolTests.setUp(self)
        self.rows={};self.head=0;self.calls=[];self.fail_run=False;self.no_id=False
        parent=self
        class Journal:
            def read(obj):
                return None if not parent.rows else (str(parent.head),json.loads(json.dumps(parent.rows)))
            def write(obj,value,prior=None):
                if prior is None and parent.rows:raise RuntimeError('CONFLICT')
                if prior is not None and prior!=str(parent.head):raise RuntimeError('CAS')
                parent.head+=1;parent.rows=json.loads(json.dumps(value));return str(parent.head)
        class RPC:
            def assume(obj):parent.calls.append('STS')
            def __call__(obj,endpoint,action,**kw):
                parent.calls.append(action)
                if action=='RunCommand':
                    if parent.fail_run:raise OSError('PRIVATE_ERROR')
                    return {} if parent.no_id else {'InvokeId':'t-real-fixture'}
                body={'hostname':d.receipt.HOST,'uid':0,'python':[3,6,8],
                      'nonce':parent.request['nonce'],'private_inputs_read':False}
                result={'state':'REMOTE_IDENTITY_COMPLETE','request_sha256':
                    hashlib.sha256(d.canonical(parent.request)).hexdigest(),'receipt':body,'redispatch_allowed':False}
                return {'InvocationResult':{'InvokeId':kw['InvokeId'],'InstanceId':d.receipt.INSTANCE,
                    'InvocationStatus':'Success','ExitCode':0,'Output':json.dumps(result)}}
        self.journal=Journal();self.rpc=RPC();self.factory=lambda:self.rpc
        self.policy=self.make_policy('REMOTE_RUN','',1)

    def make_policy(self,operation,invoke,ident):
        binding={'operation':operation,'attempt':self.request['attempt'],
            'request_sha256':hashlib.sha256(d.canonical(self.request)).hexdigest(),
            'command_sha256':hashlib.sha256(d.remote_command(self.request).encode()).hexdigest(),
            'source_commit':'a'*40,'invoke_id':invoke,'target_config_sha256':'d'*64,
            'host':d.receipt.HOST,'instance_id':d.receipt.INSTANCE,'region':d.receipt.REGION,'role':d.ROLE}
        permit={'decision':'UK_SPLIT_APPROVED','binding':binding,'issued_unix':90,
                'expires_unix':200,'max_executions':1,'install_allowed':False,'private_inputs_allowed':False}
        self.body='P2_UK_SPLIT_ONCE\n'+json.dumps(permit)
        return dict(binding=binding,request=self.request,enabled=True,revoked=False,
            reviewer_principal='independent',source_writer_principal='writer',
            custody_evidence_sha256='b'*64,approval_comment_id=ident,
            approval_body_sha256=hashlib.sha256(self.body.encode()).hexdigest())

    def call(self,action='remote-run',invoke=''):
        return d.split_cloud(self.policy,self.journal,self.factory,lambda ident:self.body,
                             lambda:100,action,invoke)

    def test_cloud_intent_precedes_credentials(self):
        def factory():
            self.assertEqual(self.rows['state'],'CLOUD_DISPATCH_INTENT')
            return self.rpc
        self.factory=factory
        self.assertEqual(self.call()['state'],'CLOUD_DISPATCHED_AWAIT_SEPARATE_QUERY')
        self.assertEqual(self.calls,['STS','RunCommand'])

    def test_cloud_run_consumed_on_exception(self):
        self.fail_run=True
        with self.assertRaisesRegex(RuntimeError,'CLOUD_DISPATCH_UNKNOWN'):self.call()
        self.assertEqual(self.rows['state'],'CLOUD_DISPATCH_INTENT')
        with self.assertRaises(RuntimeError):self.call()
        self.assertEqual(self.calls.count('RunCommand'),1)

    def test_missing_invoke_is_permanent_unknown(self):
        self.no_id=True
        with self.assertRaises(RuntimeError):self.call()
        self.assertEqual(self.rows['invoke_id'],'')
        self.policy=self.make_policy('CLOUD_QUERY','t-guess',2)
        with self.assertRaises(RuntimeError):self.call('cloud-query','t-guess')
        self.assertEqual(self.calls.count('RunCommand'),1)

    def test_cross_job_query_and_no_redispatch(self):
        self.call();self.calls=[]
        self.policy=self.make_policy('CLOUD_QUERY','t-real-fixture',2)
        result=self.call('cloud-query','t-real-fixture')
        self.assertEqual(result['state'],'SPLIT_TRANSPORT_VERIFIED')
        self.assertEqual(self.calls,['STS','DescribeInvocationResult'])
        with self.assertRaises(RuntimeError):self.call('cloud-query','t-real-fixture')

    def test_fresh_query_can_reconcile_after_run_request_expiry(self):
        self.request['expires_unix']=101
        self.policy=self.make_policy('REMOTE_RUN','',1)
        self.call()
        self.policy=self.make_policy('CLOUD_QUERY','t-real-fixture',2)
        result=d.split_cloud(self.policy,self.journal,self.factory,lambda ident:self.body,
                             lambda:110,'cloud-query','t-real-fixture')
        self.assertEqual(result['state'],'SPLIT_TRANSPORT_VERIFIED')

    def test_query_unknown_consumes_own_permission(self):
        self.call();self.policy=self.make_policy('CLOUD_QUERY','t-real-fixture',2)
        rpc=self.rpc
        def pending(endpoint,action,**kw):
            return {'InvocationResult':{'InvokeId':kw['InvokeId'],'InstanceId':d.receipt.INSTANCE,
                                        'InvocationStatus':'Running'}}
        rpc.__class__.__call__=lambda obj,*a,**k:pending(*a,**k)
        self.assertEqual(self.call('cloud-query','t-real-fixture')['state'],'CLOUD_QUERY_UNKNOWN')
        with self.assertRaises(RuntimeError):self.call('cloud-query','t-real-fixture')

    def test_same_query_two_jobs_single_winner(self):
        import threading
        self.call();self.policy=self.make_policy('CLOUD_QUERY','t-real-fixture',2)
        read=self.journal.read;write=self.journal.write
        barrier=threading.Barrier(2);lock=threading.Lock();claims=[];results=[]
        def parallel_read():
            saved=read();barrier.wait(timeout=2);return saved
        def atomic_write(value,prior=None):
            if value.get('state')=='CLOUD_QUERY_UNKNOWN':claims.append(value['query_claim_nonce'])
            with lock:return write(value,prior)
        self.journal.read=parallel_read;self.journal.write=atomic_write
        def worker():
            try:results.append(self.call('cloud-query','t-real-fixture')['state'])
            except RuntimeError:results.append('HOLD')
        threads=[threading.Thread(target=worker) for unused in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=3)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sorted(results),['HOLD','SPLIT_TRANSPORT_VERIFIED'])
        self.assertEqual(len(set(claims)),2)

    def test_target_unknown_distinct_from_cloud_unknown(self):
        detail={'InvokeId':'t-id','InstanceId':d.receipt.INSTANCE,'InvocationStatus':'Success',
                'ExitCode':0,'Output':json.dumps({'state':'REMOTE_EXECUTION_UNKNOWN','redispatch_allowed':False})}
        self.assertEqual(d.validate_split_output(detail,'t-id',self.request)['state'],'TARGET_EXECUTION_UNKNOWN')

    def test_approval_rejects_self_review_before_claim(self):
        self.policy['reviewer_principal']='writer'
        with self.assertRaises(RuntimeError):self.call()
        self.assertEqual(self.rows,{})
        self.assertEqual(self.calls,[])

    def test_post_sts_revocation_stops_cloud(self):
        def assume():
            self.calls.append('STS');self.policy['revoked']=True
        self.rpc.assume=assume
        with self.assertRaises(RuntimeError):self.call()
        self.assertEqual(self.calls,['STS'])
        self.assertEqual(self.rows['state'],'CLOUD_DISPATCH_INTENT')

    def test_remote_command_is_fixed_and_payload_is_data(self):
        import base64
        request=dict(self.request,task_id="'; touch /bad; '")
        command=d.remote_command(request)
        self.assertNotIn('touch /bad',command)
        self.assertIn(d.REMOTE_ENTRY+' receive-identity',command)
        encoded=command.split("printf '%s' '",1)[1].split("'",1)[0]
        self.assertEqual(json.loads(base64.b64decode(encoded)),request)

    def test_actions_push_event_cannot_read_policy_or_keys(self):
        with patch.dict(os.environ,{'GITHUB_EVENT_NAME':'push'},clear=True):
            with self.assertRaises(RuntimeError):d.actions_entry('remote-run','a')

    def test_actions_rerun_is_rejected(self):
        with patch.dict(os.environ,{'GITHUB_EVENT_NAME':'workflow_dispatch','P2_SPLIT_ENABLED':'true',
                       'GITHUB_REPOSITORY':d.REPOSITORY,'GITHUB_RUN_ATTEMPT':'2'},clear=True):
            with self.assertRaises(RuntimeError):d.actions_entry('remote-run','a')



class GitJournalProtocolTests(unittest.TestCase):
    def setUp(self):
        import base64
        self.objects={};self.refs={};self.counter=0
        owner=self
        class Journal(d.GitJournal):
            def api(obj,method,path,value=None,missing=False):
                def add(v):
                    owner.counter+=1;key=('%040x'%owner.counter);owner.objects[key]=v;return {'sha':key}
                if method=='POST' and path=='/git/trees':
                    raw=value['tree'][0]['content'].encode()
                    blob=add({'encoding':'base64','size':len(raw),'content':base64.b64encode(raw).decode()})
                    return add({'tree':[dict(path='state.json',mode='100644',type='blob',sha=blob['sha'])]})
                if method=='POST' and path=='/git/commits':
                    return add(dict(tree={'sha':value['tree']},parents=value['parents']))
                if method=='POST' and path=='/git/refs':
                    key=value['ref'][5:]
                    if key in owner.refs:raise RuntimeError('CONFLICT')
                    owner.refs[key]=value['sha'];return {}
                if method=='PATCH':
                    key=path[len('/git/refs/'):]
                    if owner.refs[key] not in owner.objects[value['sha']]['parents']:raise RuntimeError('CAS')
                    if value['force'] is not False:raise RuntimeError('FORCE')
                    owner.refs[key]=value['sha'];return {}
                if path.startswith('/git/ref/'):
                    key=path[len('/git/ref/'):]
                    if key not in owner.refs:
                        if missing:return None
                        raise KeyError(key)
                    return {'object':{'sha':owner.refs[key]}}
                return owner.objects[path.rsplit('/',1)[1]]
        self.Journal=Journal;self.j=Journal('SYNTHETIC_TOKEN','attempt')

    def test_ref_claim_persists_between_instances(self):
        sha=self.j.write({'state':'INTENT'})
        self.assertEqual(self.Journal('SYNTHETIC_TOKEN','attempt').read(),(sha,{'state':'INTENT'}))

    def test_second_claim_rejected(self):
        self.j.write({'state':'INTENT'})
        with self.assertRaises(RuntimeError):self.j.write({'state':'OTHER'})

    def test_stale_append_is_not_fast_forward(self):
        head=self.j.write({'state':'INTENT'})
        self.j.write({'state':'DISPATCHED'},head)
        with self.assertRaises(RuntimeError):self.j.write({'state':'WRONG'},head)
        self.assertEqual(self.j.read()[1]['state'],'DISPATCHED')

    def test_branch_escape_rejected(self):
        with self.assertRaises(RuntimeError):self.Journal('token','../../main')

    def test_authenticated_api_redacts_failure(self):
        import urllib.error
        class Opener:
            def open(obj,req,timeout):
                raise urllib.error.URLError('SYNTHETIC_SECRET_MUST_NOT_ESCAPE')
        j=d.GitJournal('SYNTHETIC_TOKEN','attempt',opener=Opener())
        with self.assertRaises(RuntimeError) as error:j.read()
        self.assertNotIn('SYNTHETIC_SECRET',str(error.exception))


class ExistingRuntimeFactoryTests(unittest.TestCase):
    def test_original_pinned_runtime_missing_activation_holds(self):
        import sys
        base=Path(__file__).resolve().parents[1]/'evidence/p2-epoch7-access-repair-20261014/runtime/stage1'
        with tempfile.TemporaryDirectory(dir='/root',prefix='p2-original-read-fixture-') as folder:
            root=Path(folder);os.chmod(root,0o700);pins={}
            for name in d.RUNTIME_MODULES:
                raw=(base/(name+'.py')).read_bytes();p=root/(name+'.py');p.write_bytes(raw);p.chmod(0o400)
                pins[name]={'path':str(p),'sha256':hashlib.sha256(raw).hexdigest()}
            policy={'runtime_files':pins,'activation_paths':{
                'descriptor':str(root/'descriptor.json'),'epoch_journal':str(root/'epochs.jsonl'),
                'lock':str(root/'activation.lock')}}
            old={name:sys.modules.pop(name,None) for name in d.RUNTIME_MODULES}
            try:
                with self.assertRaises((FileNotFoundError,RuntimeError)):
                    d.remote_factory(policy)
                self.assertFalse((root/'descriptor.json').exists())
            finally:
                for name,module in old.items():
                    sys.modules.pop(name,None)
                    if module is not None:sys.modules[name]=module


class SitePreparationTests(unittest.TestCase):
    """Exercise the exact standalone attachment; fixtures are not UK evidence."""
    def setUp(self):
        import types
        doc=Path(__file__).resolve().parents[1]/'evidence/p2-epoch7-access-repair-20261014/c-private-completeness/SWAS_HANDOFF.md'
        text=doc.read_text()
        block=text.split('<!-- BEGIN P2_SITE_ENTRY_V1 -->\n```python\n',1)[1].split('```\n<!-- END P2_SITE_ENTRY_V1 -->',1)[0]
        self.code=block.encode();self.s=types.ModuleType('site_fixture')
        exec(compile(block,'P2_SITE_ENTRY.py','exec'),self.s.__dict__)
        self.tmp=tempfile.TemporaryDirectory(dir='/root',prefix='p2-site-isolated-')
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);root.chmod(0o700);self.root=root
        lib=root/'libexec';lib.mkdir(mode=0o755)
        ctrl=root/'control';ctrl.mkdir(mode=0o700);(ctrl/'prepare.lock').touch(mode=0o600)
        self.s.DEST=lib/'receiver';self.s.CONTROL=ctrl
        # Frozen transport bytes stay unchanged in the source kit.
        src=Path(__file__).resolve().parents[1]/'scripts';self.src=root/'source';self.src.mkdir(mode=0o700)
        (self.src/'transport.py').write_bytes((src/'p2_uk_swas_diagnostic.py').read_bytes())
        (self.src/'p2_swas_receipt_validator.py').write_bytes((src/'p2_swas_receipt_validator.py').read_bytes())
        self.attempt='fixture-site-attempt'
        self.baseline=self.s.preflight()
        self.baseline.update(hostname=self.s.HOST,uid=0,python=[3,6,8])
        self.baseline['paths'][str(self.s.DEST)]={'present':False}
        # Keep the exact known path set, replacing the production receiver.
        self.s.META_PATHS=tuple(self.s.DEST if str(p)=='/usr/local/libexec/xuanjun-p2-swas' else p for p in self.s.META_PATHS)
        self.plan={'schema':1,'attempt':self.attempt,'baseline':self.baseline,
            'source_pins':self.s.SOURCE_PINS,'installation_scope':'RECEIVER_CODE_ONLY_NO_POLICY_OR_RUNTIME'}
        self.baseline['paths'].pop('/usr/local/libexec/xuanjun-p2-swas',None)
        self.plan_path=root/'plan.json';self.plan_path.write_bytes(self.s.canon(self.plan));self.plan_path.chmod(0o400)
        self.auth={'comment_id':123,'body_sha256':'a'*64,'trust_sha256':'b'*64}

    def run_install(self):
        with patch.object(self.s,'preflight',return_value=self.baseline),patch.object(self.s,'authority',return_value=self.auth):
            return self.s.prepare('install',self.attempt,self.plan_path,self.src,self.code)

    def test_preflight_no_private_reads_no_network_no_writes(self):
        with patch.object(self.s,'read',side_effect=AssertionError),patch.object(self.s,'fetch_comment',side_effect=AssertionError),patch.object(self.s,'create',side_effect=AssertionError):
            result=self.s.preflight()
        self.assertEqual(result['mutations'],0)
        self.assertEqual(result['unique_writer'],'UNKNOWN')

    def test_install_real_atomic_publish_exact_bytes(self):
        r=self.run_install();self.assertEqual(r['state'],'RECEIVER_CODE_INSTALLED')
        self.s.verify_code(self.s.DEST)
        self.assertFalse(r['runtime_activated'])
        self.assertEqual((self.s.DEST/'transport.py').read_bytes(),(self.src/'transport.py').read_bytes())

    def test_installed_attempt_cannot_repeat(self):
        self.run_install()
        with self.assertRaises(RuntimeError):self.run_install()

    def test_old_target_not_overwritten(self):
        self.s.DEST.mkdir();(self.s.DEST/'old').write_text('keep')
        with self.assertRaises(RuntimeError):self.run_install()
        self.assertEqual((self.s.DEST/'old').read_text(),'keep')

    def test_input_hash_drift_before_consumption(self):
        (self.src/'transport.py').write_text('bad')
        with self.assertRaises(RuntimeError):self.run_install()
        self.assertFalse((self.s.CONTROL/self.attempt).exists())

    def test_source_symlink_rejected(self):
        p=self.src/'transport.py';p.unlink();p.symlink_to(self.src/'p2_swas_receipt_validator.py')
        with self.assertRaises(RuntimeError):self.run_install()

    def test_metadata_drift_rejects_before_stage(self):
        changed=dict(self.baseline);changed['uid']=1000
        with patch.object(self.s,'preflight',return_value=changed),patch.object(self.s,'authority',return_value=self.auth):
            with self.assertRaises(RuntimeError):self.s.prepare('install',self.attempt,self.plan_path,self.src,self.code)
        self.assertFalse(self.s.DEST.exists())

    def test_fsync_error_consumes_does_not_publish_or_retry(self):
        with patch.object(self.s,'sync_dir',side_effect=OSError('fixture fsync')):
            with self.assertRaises(OSError):self.run_install()
        self.assertTrue((self.s.CONTROL/self.attempt).exists());self.assertFalse(self.s.DEST.exists())
        with self.assertRaises(RuntimeError):self.run_install()

    def test_rename_noreplace_real_race(self):
        a=self.root/'a';b=self.root/'b';a.mkdir();b.mkdir()
        with self.assertRaises(RuntimeError):self.s.rename_new(a,b)
        self.assertTrue(a.exists());self.assertTrue(b.exists())

    def test_revocation_after_stage_holds(self):
        with patch.object(self.s,'preflight',return_value=self.baseline),patch.object(self.s,'authority',side_effect=[self.auth,RuntimeError('revoked')]):
            with self.assertRaises(RuntimeError):self.s.prepare('install',self.attempt,self.plan_path,self.src,self.code)
        self.assertFalse(self.s.DEST.exists());self.assertTrue((self.s.CONTROL/self.attempt/'staged.json').exists())

    def test_new_rollback_quarantines_preserves_evidence(self):
        self.run_install()
        with patch.object(self.s,'authority',return_value=self.auth):
            r=self.s.prepare('rollback',self.attempt,self.plan_path,'',self.code)
        self.assertEqual(r['state'],'QUARANTINED_ORIGINAL_ABSENCE_RESTORED')
        self.assertFalse(self.s.DEST.exists())
        self.s.verify_code(self.s.DEST.parent/('.p2-quarantine-'+self.attempt))
        self.assertTrue((self.s.CONTROL/self.attempt/'intent.json').exists())

    def test_unknown_target_blocks_rollback(self):
        self.run_install();(self.s.DEST/'transport.py').chmod(0o644);(self.s.DEST/'transport.py').write_text('unknown')
        with patch.object(self.s,'authority',return_value=self.auth):
            with self.assertRaises(RuntimeError):self.s.prepare('rollback',self.attempt,self.plan_path,'',self.code)
        self.assertTrue(self.s.DEST.exists())

    def test_interrupted_rollback_cannot_repeat(self):
        self.run_install()
        with patch.object(self.s,'authority',return_value=self.auth),patch.object(self.s,'rename_new',side_effect=OSError('cut')):
            with self.assertRaises(OSError):self.s.prepare('rollback',self.attempt,self.plan_path,'',self.code)
        with patch.object(self.s,'authority',return_value=self.auth):
            with self.assertRaises(RuntimeError):self.s.prepare('rollback',self.attempt,self.plan_path,'',self.code)
        self.assertTrue(self.s.DEST.exists())

    def test_inspect_hashes_only_no_success_inference(self):
        self.run_install();result=self.s.inspect(self.attempt)
        self.assertFalse(result['retry_allowed']);self.assertEqual(result['canonical_writer'],'NOT_OBSERVED')
        self.assertNotIn('approval',json.dumps(result));self.assertEqual(len(result['records']),3)

    def replace_fixture(self,path,raw):
        path.chmod(0o600);path.write_bytes(raw);path.chmod(0o400)

    def authority_fixture(self):
        self.s.TRUST=self.root/'TRUST.json'
        now=int(self.s.time.time())
        permit={'decision':'SITE_PREPARATION_APPROVED','operation':'install','attempt':self.attempt,
            'hostname':self.s.HOST,'script_sha256':self.s.sha(self.code),
            'plan_sha256':self.s.sha(self.plan_path.read_bytes()),'issued_unix':now-1,'expires_unix':now+300,
            'max_executions':1,'canonical_changes_allowed':False,'cloud_calls_allowed':False}
        body=b'P2_SITE_ONCE\n'+self.s.canon(permit)
        trust={'schema':1,'enabled':True,'revoked':False,'reviewer_principal':'fixture-auditor',
            'source_writer_principal':'fixture-author','custody_evidence_sha256':'d'*64,'comment_id':123,
            'comment_body_sha256':self.s.sha(body),'operation':'install','attempt':self.attempt,
            'plan_sha256':permit['plan_sha256'],'script_sha256':permit['script_sha256']}
        self.s.TRUST.touch(exist_ok=True);self.replace_fixture(self.s.TRUST,self.s.canon(trust))
        return permit,trust,body

    def test_exact_owner_anchor_and_body_required(self):
        p,t,b=self.authority_fixture()
        with patch.object(self.s,'fetch_comment',return_value=b):
            self.assertEqual(self.s.authority('install',self.attempt,self.plan_path.read_bytes(),self.code)['comment_id'],123)
        with patch.object(self.s,'fetch_comment',return_value=b+' '.encode()):
            with self.assertRaises(RuntimeError):self.s.authority('install',self.attempt,self.plan_path.read_bytes(),self.code)

    def test_self_review_expiry_and_cloud_grant_rejected(self):
        p,t,b=self.authority_fixture()
        t['reviewer_principal']=t['source_writer_principal'];self.replace_fixture(self.s.TRUST,self.s.canon(t))
        with patch.object(self.s,'fetch_comment',return_value=b):
            with self.assertRaises(RuntimeError):self.s.authority('install',self.attempt,self.plan_path.read_bytes(),self.code)
        p,t,b=self.authority_fixture();p['expires_unix']=p['issued_unix'];b=b'P2_SITE_ONCE\n'+self.s.canon(p)
        t['comment_body_sha256']=self.s.sha(b);self.replace_fixture(self.s.TRUST,self.s.canon(t))
        with patch.object(self.s,'fetch_comment',return_value=b):
            with self.assertRaises(RuntimeError):self.s.authority('install',self.attempt,self.plan_path.read_bytes(),self.code)
        p,t,b=self.authority_fixture();p['cloud_calls_allowed']=True;b=b'P2_SITE_ONCE\n'+self.s.canon(p)
        t['comment_body_sha256']=self.s.sha(b);self.replace_fixture(self.s.TRUST,self.s.canon(t))
        with patch.object(self.s,'fetch_comment',return_value=b):
            with self.assertRaises(RuntimeError):self.s.authority('install',self.attempt,self.plan_path.read_bytes(),self.code)

    def test_install_each_persistent_checkpoint_failure_preserved(self):
        # Each subcase has a distinct attempt; never erase/retry a consumed attempt.
        original=self.s.create
        for cut in ('intent.json','transport.py','p2_swas_receipt_validator.py','staged.json','installed.json'):
            with self.subTest(cut=cut):
                self.attempt='fixture-cut-'+cut.replace('.','-').replace('_','-')
                self.plan['attempt']=self.attempt;self.replace_fixture(self.plan_path,self.s.canon(self.plan))
                def fail(p,raw,mode):
                    if p.name==cut:raise OSError('injected checkpoint')
                    return original(p,raw,mode)
                with patch.object(self.s,'create',side_effect=fail):
                    with self.assertRaises(OSError):self.run_install()
                self.assertTrue((self.s.CONTROL/self.attempt).exists())
                with self.assertRaises(RuntimeError):self.run_install()
                # Isolate next subcase in a different libexec dir, preserving all prior objects.
                lib=self.root/('lib-'+self.attempt);lib.mkdir(mode=0o755)
                old=self.s.DEST;self.s.DEST=lib/'receiver'
                self.s.META_PATHS=tuple(self.s.DEST if p==old else p for p in self.s.META_PATHS)
                self.baseline['paths'][str(self.s.DEST)]=self.baseline['paths'].pop(str(old))


class A5Tests(unittest.TestCase):
    def setUp(self):
        self.request={'purpose':'A5_METADATA_PREFLIGHT_ONLY','attempt':'a5-test-attempt','nonce':'nonce_a5'}
        self.row=dict(schema=1,hostname=d.receipt.HOST,uid=0,python=[3,6,8],paths={},
                      state='METADATA_ONLY_NOT_WRITER_OR_TRUST_VERIFICATION',mutations=0,
                      activation='NOT_OBSERVED',unique_writer='UNKNOWN',
                      private_materials_read=False,install_authorized=False)
        self.detail=dict(InvokeId='t-a5',InstanceId=d.receipt.INSTANCE,
                         InvocationStatus='Success',ExitCode=0,Output=json.dumps(self.row))
    def test_command_fixed(self):
        self.assertEqual(d.a5_command(self.request),d.a5_command(dict(self.request)))
        self.assertIn(d.A5_SHA,d.a5_command(self.request))
        self.assertNotIn('receive-identity',d.a5_command(self.request))
    def test_purpose_rejected(self):
        with self.assertRaises(RuntimeError):d.a5_command(dict(self.request,purpose='REMOTE_RUN'))
    def test_attempt_rejected(self):
        with self.assertRaises(RuntimeError):d.a5_command(dict(self.request,attempt='../bad'))
    def test_receipt_valid_no_writer(self):
        self.assertFalse(d.a5_validate(self.detail,'t-a5')['writer_verified'])
    def test_receipt_mutation_rejected(self):
        with self.assertRaises(RuntimeError):
            d.a5_validate(dict(self.detail,Output=json.dumps(dict(self.row,mutations=1))),'t-a5')
    def test_receipt_unsafe_target_rejected(self):
        with self.assertRaises(RuntimeError):d.a5_validate(dict(self.detail,InstanceId='bad'),'t-a5')
    def test_receipt_fake_root_rejected(self):
        with self.assertRaises(RuntimeError):
            d.a5_validate(dict(self.detail,Output=json.dumps(dict(self.row,uid=True))),'t-a5')
    def test_receipt_extra_fields_rejected(self):
        with self.assertRaises(RuntimeError):
            d.a5_validate(dict(self.detail,Output=json.dumps(dict(self.row,extra='bad'))),'t-a5')
