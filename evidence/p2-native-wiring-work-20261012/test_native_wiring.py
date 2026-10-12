import ast
import os
import hashlib
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(os.environ['P2_SOURCE_ROOT']) / 'stage1'
sys.path.insert(0, str(SOURCE))
from native_pipeline_runtime import NativePipelineRuntime, NativePipelineWorker, ExistingOutboxNotifier
from native_child_adapter import NativeContractError
from development_pipeline import DevelopmentPipeline, digest_spec
import development_service

REPO = ExistingOutboxNotifier.REPOSITORY
CLAIM = {'task_id':'t', 'spec_hash':'s', 'worker_id':'w', 'fence':1,
         'epoch':2, 'generation':1, 'instance':'i'}

class Controller:
    def __init__(self):
        self.launches=0;self.stops=0;self.request=None;self.key=None
        self.observed={'state':'completed','process_alive':False,'unit_active':False,'descendants_exited':True}
        self.result={'status':'COMPLETED','provider':'openai','model':'gpt-5.6-sol','model_verified':True,'turn_completed':True,'real_execution':True}
    def preflight(self,config):
        return {'ready':True,'canonical_existing':True,'isolation_enforced':True,'outbox_existing':True}
    def admit(self,request,key):
        self.request,self.key=request,key
        return {'request':request,'idempotency_key':key,'isolation_enforced':True}
    def launch(self,admission):
        self.launches+=1
        self.receipt={'run_id':'r','session_id':'s','execution_unit_id':'u','idempotency_key':self.key}
        return self.receipt
    def inspect(self,receipt):return dict(self.observed,**receipt)
    def report(self,receipt):return dict(receipt,request=self.request,durable_receipt_id='canonical:r',result=self.result)
    def stop(self,receipt):self.stops+=1
    def notify(self,repo,pr,report,key):return {'repository':repo,'pr_number':pr,'message_id':'123','idempotency_key':key}
    def notification_receipt(self,repo,pr,key):return self.notify(repo,pr,{},key)

class Ledger:
    def __init__(self):self.cp=None;self.state='RUNNING'
    def heartbeat(self,*args,**kw):return True
    def assert_live(self,*args):return True
    def checkpoint(self,*args):self.cp=args[-1]
    def finish(self,*args,**kw):self.state=args[-1];return self.state
class Backend:
    def reconcile(self,*args):return True

class WiringTests(unittest.TestCase):
    def worker(self,c):return NativePipelineWorker(c,CLAIM,'/isolated/snapshot','workspace-write',clock=lambda:0,wait=lambda x:None)
    def run_worker(self,c,live=lambda:True):return self.worker(c).run('approved',30,lambda:None,live)
    def test_trusted_terminal_result_and_stop(self):
        c=Controller();r=self.run_worker(c);self.assertTrue(r['worker_boundary_stopped']);self.assertEqual(c.launches,1)
    def test_no_launch_without_isolation_admission(self):
        c=Controller();c.admit=lambda request,key:{'request':request,'idempotency_key':key,'isolation_enforced':False}
        with self.assertRaises(NativeContractError):self.run_worker(c)
        self.assertEqual(c.launches,0)
    def test_expired_lease_no_admission_or_launch(self):
        c=Controller()
        with self.assertRaises(NativeContractError):self.run_worker(c,lambda:False)
        self.assertEqual(c.launches,0);self.assertIsNone(c.request)
    def test_terminal_session_without_empty_cgroup_rejected(self):
        c=Controller();c.observed['descendants_exited']=False
        with self.assertRaises(NativeContractError):self.run_worker(c)
    def test_missing_process_observation_rejected(self):
        c=Controller();c.observed['process_alive']=None
        with self.assertRaises(NativeContractError):self.run_worker(c)
    def test_assistant_shaped_report_not_durable(self):
        c=Controller();c.report=lambda r:{'outcome':'done'}
        with self.assertRaises(NativeContractError):self.run_worker(c)
    def test_actual_model_mismatch_rejected(self):
        c=Controller();c.result['model']='gpt-6.1-sol'
        with self.assertRaises(NativeContractError):self.run_worker(c)
    def test_wrong_run_observation_rejected(self):
        c=Controller();c.inspect=lambda r:dict(c.observed,**dict(r,run_id='another'))
        with self.assertRaises(NativeContractError):self.run_worker(c)
    def test_notification_fixed_recipient_ack_and_lookup(self):
        n=ExistingOutboxNotifier(Controller());self.assertEqual(n.send({},'k'),n.reconcile('k'))
    def test_wrong_recipient_ack_rejected(self):
        c=Controller();c.notify=lambda *args:{'repository':REPO,'pr_number':18,'message_id':'123','idempotency_key':'k'}
        with self.assertRaises(NativeContractError):ExistingOutboxNotifier(c).send({},'k')
    def pipeline(self,n):
        l=Ledger();spec={'repo':REPO,'prompt':'approved','base_sha':'a'*40,'timeout_seconds':30}
        claim=dict(CLAIM,spec=spec,spec_hash=digest_spec(spec))
        trusted={'repo':REPO,'instructions':'approved','base_sha':'a'*40}
        cp={'phase':'ACCEPTED','spec_digest':digest_spec(trusted),'branch':'codex/task-'+hashlib.sha256(b't').hexdigest()[:24],
            'spec_hash':claim['spec_hash'],'workdir':'/isolated','sha':'b'*40,'pr':17,'qa_commit':'b'*40,
            'real_execution':True,'simulated':False}
        claim['checkpoint']=cp
        p=DevelopmentPipeline(l,Backend(),None,[REPO],result_notifier=n)
        return p,l,claim
    def test_pipeline_done_only_after_notification_ack(self):
        p,l,c=self.pipeline(ExistingOutboxNotifier(Controller()));r=p.run(c)
        self.assertEqual(r['state'],'DONE');self.assertIn('notification_receipt',l.cp)
    def test_uncertain_notification_holds_and_does_not_blind_retry(self):
        controller=Controller();sent=[]
        def send(*args):sent.append(args);raise RuntimeError('send may have succeeded')
        controller.notify=send
        p,l,c=self.pipeline(ExistingOutboxNotifier(controller));r=p.run(c)
        self.assertEqual(r['state'],'WAITING_HUMAN');self.assertEqual(l.cp['phase'],'IN_FLIGHT_NOTIFY')
        c['checkpoint']=l.cp;p.run(c);self.assertEqual(len(sent),1)
    def test_dispatcher_missing_native_runtime_fails_before_authority(self):
        with patch.object(development_service,'ActivationStore') as activation:
            with self.assertRaises(ValueError):development_service.build_loop({'config_version':2,'model':'gpt-5.6-sol'})
            activation.assert_not_called()
    def test_runtime_preflight_missing_existing_outbox_rejected(self):
        c=Controller();c.preflight=lambda cfg:{'ready':True,'canonical_existing':True,'isolation_enforced':True,'outbox_existing':False}
        with self.assertRaises(NativeContractError):NativePipelineRuntime(c).preflight({})
    def test_python36_grammar(self):
        for name in ('native_pipeline_runtime.py','native_child_adapter.py','development_service.py','development_pipeline.py'):
            raw=(SOURCE / name).read_text()
            ast.parse(raw,feature_version=(3,6));compile(raw,name,'exec')

from native_github_notifier import FixedPr17GithubNotifier
from types import SimpleNamespace

class GhTests(unittest.TestCase):
    def make(self, mode='ok'):
        calls=[]
        def run(argv,**kw):
            calls.append((argv,kw))
            if argv[-1]=='user':value={'login':'other' if mode=='wrong_owner' else FixedPr17GithubNotifier.OWNER}
            elif '--method' in argv:
                if mode=='unknown_send':raise TimeoutError('write result unknown')
                body=json.loads(kw['input'])['body']
                value={'id':321,'body':body,'user':{'login':FixedPr17GithubNotifier.OWNER}}
            else:
                marker='<!-- XJ_P2_RESULT '+self.key+' -->'
                row={'id':99,'body':marker+'\nexisting','user':{'login':FixedPr17GithubNotifier.OWNER}}
                value=[[row,row]] if mode=='duplicate' else [[row]] if mode=='existing' else [[]]
            return SimpleNamespace(returncode=0,stdout=json.dumps(value).encode())
        n=FixedPr17GithubNotifier('/usr/bin/true','/root','/usr/bin:/bin',runner=run)
        self.report={'task_id':'t','spec_hash':'s','fence':1,'epoch':2,'commit':'a'*40,'pr':17,'qa_commit':'a'*40,'state':'CODE_ACCEPTED_PENDING_LEDGER_FINISH','production_pass':False}
        self.key=hashlib.sha256(json.dumps(self.report,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return n,calls
    def test_real_transport_fixed_endpoint_structured_input(self):
        n,calls=self.make();r=n.send(self.report,self.key)
        self.assertEqual(r['message_id'],'321');self.assertIn('repos/'+REPO+'/issues/17/comments',calls[-1][0])
        self.assertIsInstance(calls[-1][1]['input'],bytes);self.assertNotIn('shell',calls[-1][1])
    def test_existing_external_receipt_no_second_post(self):
        n,calls=self.make('existing');self.assertEqual(n.send(self.report,self.key)['message_id'],'99')
        self.assertFalse(any('--method' in a for a,k in calls))
    def test_wrong_account_no_send(self):
        n,calls=self.make('wrong_owner')
        with self.assertRaises(NativeContractError):n.send(self.report,self.key)
        self.assertEqual(len(calls),1)
    def test_unknown_send_not_retried(self):
        n,calls=self.make('unknown_send')
        with self.assertRaises(TimeoutError):n.send(self.report,self.key)
        self.assertEqual(sum('--method' in a for a,k in calls),1)
    def test_duplicate_external_receipts_hold(self):
        n,calls=self.make('duplicate')
        with self.assertRaises(NativeContractError):n.send(self.report,self.key)
        self.assertFalse(any('--method' in a for a,k in calls))
    def test_report_hash_mismatch_no_command(self):
        n,calls=self.make()
        with self.assertRaises(NativeContractError):n.send(self.report,'0'*64)
        self.assertEqual(calls,[])

if __name__=='__main__':unittest.main(verbosity=2)
