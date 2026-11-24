import os
import sys
import json
import time
import unittest
import importlib.util

BASE=os.environ.get('TC_INSTALLED_BASE','/opt/xuanjun-task-center-test/releases/tc-canonical-producer-scoped-20261114')
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0]=[os.path.join(ROOT,'scripts'),os.path.join(BASE,'scripts')]
from model_orchestration import ModelScheduler
from model_fallback import select,ROUTES
spec=importlib.util.spec_from_file_location('old_fixture',os.path.join(BASE,'tests/test_model_orchestration.py'))
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
sys.path.insert(0,os.path.join(ROOT,'scripts'))


def snapshot(sub=50, api=None):
    now=time.time()
    out={'subscription':dict(routeId='subscription',state='KNOWN',authMode='oauth-subscription',
         accountScopeRef='fixture-account',source='fixture-official-snapshot',observedAt=now,
         windows=[dict(label='168h',remainingPercent=sub,resetAt=now+3600)])}
    if api is not None:
        out['api']=dict(routeId='api',state='KNOWN',authMode='api-key',accountScopeRef='fixture-api',
                        source='fixture-api',observedAt=now,remaining=api,unit='native-credit')
    return out

class PolicyTests(unittest.TestCase):
    def decision(self,role='main',sub=50,api=None):
        return select(role,snapshot(sub,api),time.time(),set(ROUTES),60)
    def test_main_zero_unknown_boundary_recovery(self):
        self.assertEqual(self.decision(api=0)['routeId'],'subscription')
        unknown=self.decision();self.assertEqual(unknown['routeId'],'subscription')
        self.assertIn('api:UNKNOWN',unknown['reason']);self.assertNotIn('api:ZERO',unknown['reason'])
        self.assertEqual(self.decision(sub=20,api=0)['routeId'],'alternative')
        self.assertEqual(self.decision(sub=20.001,api=0)['routeId'],'subscription')
        self.assertEqual(self.decision(sub=1,api=1)['routeId'],'api')
    def test_other_boundary_recovery_and_exceptions(self):
        self.assertEqual(self.decision('developer',4.999)['routeId'],'alternative')
        self.assertEqual(self.decision('developer',5)['routeId'],'subscription')
        for role in ('repair-installer','independent-reviewer'):
            self.assertEqual(self.decision(role,100,10)['routeId'],'alternative')
    def test_multiple_windows_stale_errors_and_invalid(self):
        s=snapshot(90);s['subscription']['windows'].append(dict(label='5h',remainingPercent=4,resetAt=time.time()+300))
        self.assertEqual(select('developer',s,time.time(),set(ROUTES),60)['routeId'],'alternative')
        for change in ({'observedAt':time.time()-1000},{'errorCategory':'AUTHORIZATION'},
                       {'authMode':'api-key'},{'windows':[]},
                       {'windows':[dict(remainingPercent=float('nan'),resetAt=time.time()+300)]}):
            s=snapshot();s['subscription'].update(change)
            self.assertEqual(select('developer',s,time.time(),set(ROUTES),60)['routeId'],'alternative')
    def test_authorization_not_inferred(self):
        self.assertIsNone(select('main',snapshot(),time.time(),[],60)['routeId'])

class RuntimeFixture:
    max_snapshot_age=60
    max_attempts=3
    def __init__(self):self.calls=[];self.queries=[];self.response='SUCCEEDED';self.quota=snapshot();self.category=None
    def snapshot(self,context):return self.quota
    def allowed_routes(self,context):return set(ROUTES)
    def admit(self,context):return True
    def receipt(self,context):
        r=dict(requestId=context['request_id'],state=self.response,errorCategory=self.category)
        if self.response in ('SUCCEEDED','ACCEPTED'):
            r.update(runId='fixture-run',sessionKey='fixture-session',actualRoute='fixture-only',result={'content':'ok'})
        return r
    def dispatch(self,context):
        self.calls.append(context)
        if self.response=='THROW':raise TimeoutError()
        return self.receipt(context)
    def query(self,context):self.queries.append(context);return self.receipt(context)

class EntryTests(unittest.TestCase):
    setUp=fixture.ModelOrchestrationTests.setUp
    tearDown=fixture.ModelOrchestrationTests.tearDown
    provider=fixture.ModelOrchestrationTests.provider
    model=fixture.ModelOrchestrationTests.model
    role=fixture.ModelOrchestrationTests.role
    qualify=fixture.ModelOrchestrationTests.qualify
    assigned=fixture.ModelOrchestrationTests.assigned
    def queue(self,key='native-request'):
        return self.control.queue_request('demo-b','developer',[{'role':'user','content':'fixture'}],key,dispatch_mode='gateway-native')
    def prepare(self):
        self.assigned();self.runtime=RuntimeFixture();self.control.gateway_runtime=self.runtime
        # Fail loudly if either queue or worker resolves any TC credential.
        self.control._binding_credential=lambda *a,**k: (_ for _ in ()).throw(AssertionError('SECRET_RESOLVED'))
        return self.queue()
    def row(self,r):
        return self.control.db.execute('SELECT * FROM model_requests WHERE request_id=?',(r['request_id'],)).fetchone()
    def test_entry_decision_checkpoint_and_idempotency(self):
        r=self.prepare();self.assertTrue(self.queue()['duplicate'])
        done=ModelScheduler(self.control).run_once();self.assertEqual(done['state'],'SUCCEEDED')
        self.assertEqual(len(self.runtime.calls),1)
        self.assertEqual(self.runtime.calls[0]['decision']['routeId'],'subscription')
        checkpoint=json.loads(self.row(r)['checkpoint_json']);self.assertIn('gateway',checkpoint)
        self.assertIn('gatewayReceipt',checkpoint)
        self.assertTrue(self.queue()['duplicate'])
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'IDLE')
    def test_not_connected_is_not_execution(self):
        r=self.prepare();self.control.gateway_runtime=None
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'NOT_CONNECTED')
        self.assertEqual(self.row(r)['state'],'QUEUED');self.assertEqual(self.row(r)['attempts'],0)
    def test_unknown_effect_and_restart_query_only(self):
        r=self.prepare();self.runtime.response='THROW'
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'UNKNOWN')
        self.runtime.response='SUCCEEDED'
        self.assertEqual(ModelScheduler(self.control,worker_id='restart').run_once()['state'],'SUCCEEDED')
        self.assertEqual(len(self.runtime.calls),1);self.assertEqual(len(self.runtime.queries),1)
    def test_accepted_effect_query_only(self):
        r=self.prepare();self.runtime.response='ACCEPTED'
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'RUNNING')
        self.runtime.response='SUCCEEDED'
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'SUCCEEDED')
        self.assertEqual(len(self.runtime.calls),1)
    def test_security_refusal_never_switches(self):
        r=self.prepare();self.runtime.response='NO_EFFECT';self.runtime.category='SAFETY_REFUSAL'
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'FAILED')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'IDLE')
        self.assertEqual(len(self.runtime.calls),1)
    def test_recoverable_no_effect_fallback(self):
        r=self.prepare();self.runtime.response='NO_EFFECT';self.runtime.category='COMPATIBILITY'
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'RETRY_WAIT')
        self.runtime.response='SUCCEEDED';self.runtime.category=None
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'SUCCEEDED')
        self.assertEqual([x['decision']['routeId'] for x in self.runtime.calls],['subscription','alternative'])
    def test_new_request_reads_recovery(self):
        self.prepare();self.runtime.quota=snapshot(4)
        ModelScheduler(self.control).run_once();self.queue('new-after-recovery');self.runtime.quota=snapshot(50)
        ModelScheduler(self.control).run_once()
        self.assertEqual([x['decision']['routeId'] for x in self.runtime.calls],['alternative','subscription'])
    def test_cancel_before_call(self):
        r=self.prepare();self.control.request_cancel(r['request_id'])
        ModelScheduler(self.control).run_once();self.assertEqual(len(self.runtime.calls),0)
    def test_auto_queue_and_gateway_actor_inheritance(self):
        self.prepare()
        from model_orchestration import ModelControl
        ModelControl(self.gateway,self.context,self.master,gateway_runtime=self.runtime)
        actor=ModelControl(self.gateway,self.context,self.master)
        queued=actor.queue_request('demo-b','developer',[],'auto-native')
        self.assertIsNotNone(actor.db.execute('SELECT * FROM model_gateway_dispatch WHERE request_id=?',(queued['request_id'],)).fetchone())
    def test_http_worker_hits_controlled_branch(self):
        self.prepare()
        from task_center_app import build_handler,TaskCenterHTTPServer
        import threading
        from urllib.request import Request,urlopen
        handler=build_handler(self.db,fixture.KEY,'tenant-a','owner',self.master,
              admin_token='test-admin-token-123456',outbound_enabled=True,gateway_runtime=self.runtime)
        server=TaskCenterHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever);thread.daemon=True;thread.start()
        try:
            req=Request('http://127.0.0.1:%s/api/admin/model-control'%server.server_port,
                data=json.dumps({'action':'RUN_SCHEDULER_ONCE'}).encode(),
                headers={'Content-Type':'application/json','X-Test-Admin-Token':'test-admin-token-123456'},method='POST')
            response=urlopen(req,timeout=3);value=json.loads(response.read())
            self.assertEqual(value['state'],'SUCCEEDED');self.assertEqual(len(self.runtime.calls),1)
        finally:server.shutdown();server.server_close();thread.join(2)
    def test_dispatch_mode_conflict(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_DISPATCH_CONFLICT'):
            self.control.queue_request('demo-b','developer',[{'role':'user','content':'fixture'}],'native-request',dispatch_mode='direct')

if __name__=='__main__':unittest.main()
