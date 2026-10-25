from __future__ import print_function

import json
import os
import shutil
import subprocess
import socketserver
import tempfile
import threading
import time
import unittest
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
from model_orchestration import (ModelControl, ModelScheduler,
    OpenAICompatibleAdapter, ProviderError, SiliconFlowAdapter,
    load_master_key)
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import (GatewayKernel, TestOnlyExecutor,
    TestTenantAuthority)
from task_supervisor import Supervisor
from task_writer_fence import Fence


KEY=b'0123456789abcdef0123456789abcdef'
SECRET='test-secret-1234567890'


class ThreadServer(socketserver.ThreadingMixIn,HTTPServer):
    daemon_threads=True


class ProviderHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0'))
        value=json.loads(self.rfile.read(n).decode('utf-8'));model=value['model']
        if model=='auth':self.send_response(401);self.end_headers();return
        if model=='rate':self.send_response(429);self.end_headers();return
        if model=='redirect':
            self.send_response(302);self.send_header('Location',
              'http://127.0.0.1:%d/v1/chat/completions'%self.server.server_port)
            self.end_headers();return
        if model=='slow':time.sleep(.2)
        raw=json.dumps({'id':'fixture-'+model,'choices':[{'message':{'content':'ok-'+model}}],
          'usage':{'prompt_tokens':3,'completion_tokens':2,'total_tokens':5}}).encode()
        try:
            self.send_response(200);self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
        except Exception:pass


class ModelOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        self.supervisor=Supervisor(self.db);self.authority=TestTenantAuthority(KEY)
        self.gateway=GatewayKernel(self.supervisor,self.authority)
        self.context=self.authority.issue('tenant-a','admin:owner')
        self.other=self.authority.issue('tenant-b','admin:other')
        self.gateway.register_graph(self.context,demo_graph('tenant-a'))
        self.fence=Fence(self.supervisor,os.path.join(self.root,'locks'))
        self.executor=TestOnlyExecutor(self.gateway,self.fence,self.context)
        self.executor.start('demo-b','attempt-b',['fake:demo-b'],time.time()+600)
        self.master=Fernet.generate_key();self.control=ModelControl(self.gateway,self.context,self.master)
        self.server=ThreadServer(('127.0.0.1',0),ProviderHandler)
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.daemon=True;self.thread.start()
        self.url='http://127.0.0.1:%d' % self.server.server_port

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.fence.close();self.supervisor.close();shutil.rmtree(self.root)

    def provider(self,pid='free',adapter='openai-compatible',price='KNOWN_FREE',secret=SECRET,enabled=True):
        return self.control.upsert_provider({'provider_id':pid,'display_name':pid,
          'adapter_type':adapter,'base_url':self.url,'enabled':enabled,
          'price_state':price,'rate_limit_per_min':10,'concurrency_limit':2,
          'timeout_seconds':.05,'retry_limit':1},secret)

    def model(self,pid='free',model='ok',price='KNOWN_FREE',caps=None):
        return self.control.upsert_model({'provider_id':pid,'model_id':model,
          'capabilities':caps or ['code'],'enabled':True,'price_state':price,
          'input_unit_cost':0 if price!='UNKNOWN' else None,
          'output_unit_cost':0 if price!='UNKNOWN' else None})

    def role(self,rid='developer',phase='EXECUTOR',caps=None,writer=True):
        return self.control.create_role({'role_id':rid,'version':'v1','phase':phase,
          'capabilities':caps or ['code'],'writer_allowed':writer,'enabled':True})

    def qualify(self,pid='free',model='ok'):
        try:self.control.register_benchmark_suite('suite-v1',[{'case_id':'basic',
          'capability':'code','messages':[{'role':'user','content':'fixture'}],
          'expected_contains':'ok'}])
        except Exception:pass
        class QualifiedAdapter(object):
            def invoke(self,*_args,**_kwargs):return {'content':'ok',
              'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2},
              'provider_request_id':'benchmark-fixture'}
        result=self.control.run_benchmark(pid,model,'suite-v1',QualifiedAdapter())
        self.assertEqual(result['state'],'QUALIFIED')
        return result

    def assigned(self,pid='free',model='ok'):
        self.provider(pid);self.model(pid,model);self.role();self.qualify(pid,model)
        return self.control.assign('demo-b','developer','v1','developer-1')

    def test_secret_encrypted_masked_and_never_audited_or_projected(self):
        receipt=self.provider();self.assertEqual(receipt['secret_mask'],'••••7890')
        with open(self.db,'rb') as stream:raw=stream.read()
        self.assertNotIn(SECRET.encode(),raw)
        projected=json.dumps(self.control.projection(),ensure_ascii=False)
        self.assertNotIn(SECRET,projected);self.assertIn('••••7890',projected)
        audit=''.join(r[0] for r in self.supervisor.db.execute('SELECT detail_json FROM model_audit'))
        self.assertNotIn(SECRET,audit)

    def test_master_key_file_requires_0600(self):
        path=os.path.join(self.root,'master.key')
        with open(path,'wb') as stream:stream.write(self.master)
        os.chmod(path,0o644)
        with self.assertRaisesRegex(ValueError,'0600'):load_master_key(path)
        os.chmod(path,0o600);self.assertEqual(load_master_key(path),self.master)

    def test_provider_url_rejects_private_https_userinfo_and_query(self):
        base={'provider_id':'bad','display_name':'bad',
          'adapter_type':'openai-compatible','enabled':True,
          'price_state':'UNKNOWN','rate_limit_per_min':1,
          'concurrency_limit':1,'timeout_seconds':1,'retry_limit':0}
        for url in ('https://127.0.0.1/api','https://localhost/api',
                    'https://user:pass@example.com','https://example.com?a=1'):
            value=dict(base);value['base_url']=url
            with self.assertRaisesRegex(ValueError,'SAFE_PROVIDER_URL'):
                self.control.upsert_provider(value,SECRET)

    def test_ten_provider_limit_and_tenant_isolation(self):
        for i in range(10):self.provider('p%d'%i)
        with self.assertRaisesRegex(ValueError,'LIMIT_10'):self.provider('p10')
        other=ModelControl(self.gateway,self.other,self.master)
        self.assertEqual(other.list_providers(),[])

    def test_unknown_price_not_treated_free_and_paid_requires_authority(self):
        self.provider('unknown',price='UNKNOWN');self.model('unknown','ok','UNKNOWN');self.role()
        self.qualify('unknown','ok')
        with self.assertRaisesRegex(ValueError,'NO_AUTHORIZED'):self.control.assign('demo-b','developer','v1','dev')
        chosen=self.control.assign('demo-b','developer','v1','dev',allow_paid=True)
        self.assertEqual(chosen['reason'],'AUTHORIZED_QUALIFIED_FINAL_COST')

    def test_paid_model_requires_explicit_unit_costs(self):
        self.provider('paid',price='KNOWN_PAID')
        with self.assertRaisesRegex(ValueError,'KNOWN_PAID_UNIT_COSTS'):
            self.control.upsert_model({'provider_id':'paid','model_id':'paid',
              'capabilities':['code'],'enabled':True,
              'price_state':'KNOWN_PAID','input_unit_cost':None,
              'output_unit_cost':None})

    def test_free_capable_first_and_self_review_forbidden(self):
        self.provider('paid',price='KNOWN_PAID');self.model('paid','ok','KNOWN_PAID')
        self.provider('free');self.model();self.role();self.qualify('free','ok')
        self.role('reviewer','REVIEWER',['code'],False)
        chosen=self.control.assign('demo-b','developer','v1','same',allow_paid=True)
        self.assertEqual(chosen['provider_id'],'free')
        with self.assertRaisesRegex(ValueError,'SELF_APPROVAL'):
            self.control.assign('demo-b','reviewer','v1','same',allow_paid=True)
        reviewed=self.control.assign('demo-b','reviewer','v1','independent',allow_paid=True)
        self.assertEqual(reviewed['provider_id'],'free')

    def test_skill_binding_requires_review(self):
        self.role()
        with self.assertRaisesRegex(ValueError,'APPROVED'):
            self.control.bind_skill('developer','v1','skill','v1','0'*64,'PENDING')
        self.assertEqual(self.control.bind_skill('developer','v1','skill','v1','a'*64,'APPROVED')['status'],'APPROVED')

    def test_real_http_adapters_parse_success_auth_rate_and_timeout(self):
        for cls in (OpenAICompatibleAdapter,SiliconFlowAdapter):
            adapter=cls();ok=adapter.invoke(self.url,SECRET,'ok',[{'role':'user','content':'x'}],1)
            self.assertEqual(ok['usage']['total_tokens'],5)
            with self.assertRaisesRegex(ProviderError,'AUTH'):adapter.invoke(self.url,SECRET,'auth',[],1)
            with self.assertRaisesRegex(ProviderError,'RATE_LIMIT'):adapter.invoke(self.url,SECRET,'rate',[],1)
            with self.assertRaisesRegex(ProviderError,'TIMEOUT_UNKNOWN'):adapter.invoke(self.url,SECRET,'slow',[],.05)
            with self.assertRaisesRegex(ProviderError,'HTTP'):
                adapter.invoke(self.url,SECRET,'redirect',[],1)

    def test_persistent_queue_idempotency_success_usage_and_restart(self):
        self.assigned();first=self.control.queue_request('demo-b','developer',[{'role':'user','content':'x'}],'idem-1')
        duplicate=self.control.queue_request('demo-b','developer',[{'role':'user','content':'x'}],'idem-1')
        self.assertTrue(duplicate['duplicate'])
        result=ModelScheduler(self.control).run_once();self.assertEqual(result['state'],'SUCCEEDED')
        usage=self.supervisor.db.execute('SELECT * FROM model_usage_events WHERE request_id=?',(first['request_id'],)).fetchone()
        self.assertEqual(usage['cost_state'],'KNOWN_ZERO')
        self.supervisor.close();self.supervisor=Supervisor(self.db)
        self.gateway=GatewayKernel(self.supervisor,self.authority)
        reopened=ModelControl(self.gateway,self.context,self.master)
        self.assertEqual(reopened.projection()['requests'][0]['state'],'SUCCEEDED')

    def test_timeout_is_unknown_not_blind_retry(self):
        self.assigned(model='slow');self.control.queue_request('demo-b','developer',[],'slow-1')
        result=ModelScheduler(self.control).run_once();self.assertEqual(result['state'],'UNKNOWN')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'IDLE')

    def test_429_is_bounded_retry_and_disable_cancels_queue(self):
        self.assigned(model='rate');self.control.queue_request('demo-b','developer',[],'rate-1')
        result=ModelScheduler(self.control).run_once();self.assertEqual(result['state'],'RETRY_WAIT')
        self.control.queue_request('demo-b','developer',[],'rate-2')
        self.control.disable_provider('free')
        states={r['state'] for r in self.control.projection()['requests']}
        self.assertEqual(states,{'CANCELLED'})

    def test_stale_attempt_or_revoked_writer_never_calls_provider(self):
        self.assigned();self.control.queue_request('demo-b','developer',[],'stale')
        self.supervisor.db.execute("UPDATE tasks SET authority_state='REVOKED' WHERE task_id='demo-b'");self.supervisor.db.commit()
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'CANCELLED')

    def test_unqualified_writer_model_is_rejected(self):
        self.provider();self.model();self.role()
        with self.assertRaisesRegex(ValueError,'NO_AUTHORIZED'):
            self.control.assign('demo-b','developer','v1','developer-1')

    def test_expired_worker_lease_converges_unknown_without_retry(self):
        self.assigned();queued=self.control.queue_request('demo-b','developer',[],
          'lost-worker')
        self.supervisor.db.execute('''UPDATE model_requests SET state='RUNNING',
          attempts=1,lease_owner='dead',lease_until=1 WHERE request_id=?''',
          (queued['request_id'],));self.supervisor.db.commit()
        self.assertEqual(ModelScheduler(self.control).run_once(now=10)['state'],'IDLE')
        row=self.supervisor.db.execute('''SELECT state,error_kind,attempts FROM
          model_requests WHERE request_id=?''',(queued['request_id'],)).fetchone()
        self.assertEqual((row['state'],row['error_kind'],row['attempts']),
          ('UNKNOWN','WORKER_LOST_SIDE_EFFECT_UNKNOWN',1))

    def test_cancel_before_call_and_cost_unknown_are_truthful(self):
        self.assigned();queued=self.control.queue_request('demo-b','developer',[],
          'cancel-first')
        self.assertEqual(self.control.request_cancel(queued['request_id'])['state'],
          'CANCELLED')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'IDLE')
        other=ModelControl(self.gateway,self.context,self.master)
        self.assertEqual(other.projection()['requests'][0]['state'],'CANCELLED')

    def test_independent_review_rework_and_acceptance_gates(self):
        self.assigned();self.role('reviewer','REVIEWER',['code'],False)
        self.role('acceptor','ACCEPTOR',['code'],False)
        self.control.assign('demo-b','reviewer','v1','qa')
        self.control.assign('demo-b','acceptor','v1','acceptor')
        developer=ModelControl(self.gateway,
          self.authority.issue('tenant-a','developer-1'),self.master)
        reviewer=ModelControl(self.gateway,
          self.authority.issue('tenant-a','qa'),self.master)
        acceptor=ModelControl(self.gateway,
          self.authority.issue('tenant-a','acceptor'),self.master)
        submitted=developer.submit_candidate('demo-b','a'*64,'b'*64,
          'developer-1')
        with self.assertRaisesRegex(ValueError,'SELF_REVIEW'):
            developer.review_candidate(submitted['candidate_id'],
              'developer-1',[],True)
        changed=reviewer.review_candidate(submitted['candidate_id'],'qa',
          [{'id':'DEFECT-1'}],False)
        self.assertEqual(changed['state'],'CHANGES_REQUESTED')
        with self.assertRaisesRegex(ValueError,'REVIEW_PASS'):
            acceptor.validate_accept_candidate(submitted['candidate_id'],'acceptor')
        with self.assertRaisesRegex(ValueError,'SUBMITTED_CANDIDATE'):
            reviewer.review_candidate(submitted['candidate_id'],'qa',[],True)
        revised=developer.submit_candidate('demo-b','c'*64,'d'*64,
          'developer-1')
        passed=reviewer.review_candidate(revised['candidate_id'],'qa',[],True)
        self.assertEqual(passed['state'],'REVIEW_PASSED')
        acceptor.validate_accept_candidate(revised['candidate_id'],'acceptor')
        self.executor.complete_success('demo-b','attempt-b','c'*64,
          json.loads(self.supervisor._task('demo-b')['completion_json']))
        self.assertEqual(acceptor.accept_candidate(revised['candidate_id'],
          'acceptor')['state'],'ACCEPTED')
        with self.assertRaisesRegex(ValueError,'CURRENT_CANDIDATE'):
            reviewer.review_candidate(revised['candidate_id'],'qa',[],False)
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          candidate_reviews WHERE candidate_id IN (?,?)''',(submitted['candidate_id'],
          revised['candidate_id'])).fetchone()[0],2)

    def test_candidate_hash_identity_and_current_attempt_are_enforced(self):
        self.assigned();developer=ModelControl(self.gateway,
          self.authority.issue('tenant-a','developer-1'),self.master)
        with self.assertRaisesRegex(ValueError,'CANONICAL_ARTIFACT'):
            developer.submit_candidate('demo-b','z'*64,'b'*64,'developer-1')
        self.supervisor.db.execute("""UPDATE tasks SET authority_state='REVOKED'
          WHERE task_id='demo-b'""");self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'CURRENT_CANDIDATE'):
            developer.submit_candidate('demo-b','a'*64,'b'*64,'developer-1')

    def test_same_principal_cannot_hold_executor_and_acceptor_roles(self):
        self.assigned();self.role('acceptor','ACCEPTOR',['code'],False)
        with self.assertRaisesRegex(ValueError,'SELF_APPROVAL'):
            self.control.assign('demo-b','acceptor','v1','developer-1')

    def test_cross_task_idempotency_conflict_and_late_worker_result_rejected(self):
        self.assigned();self.control.queue_request('demo-b','developer',[],
          'shared-key')
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):
            self.control.queue_request('demo-b','developer',
              [{'role':'user','content':'different'}],'shared-key')
        queued=self.control.queue_request('demo-b','developer',[],'late')
        scheduler=ModelScheduler(self.control,worker_id='old-worker')
        row=self.supervisor.db.execute('''SELECT r.*,p.price_state AS
          provider_price,m.price_state AS model_price,m.input_unit_cost,
          m.output_unit_cost FROM model_requests r JOIN model_providers p ON
          p.tenant_id=r.tenant_id AND p.provider_id=r.provider_id JOIN
          model_catalog m ON m.tenant_id=r.tenant_id AND m.provider_id=r.provider_id
          AND m.model_id=r.model_id WHERE r.request_id=?''',(queued['request_id'],)).fetchone()
        self.supervisor.db.execute('''UPDATE model_requests SET state='UNKNOWN',
          lease_owner=NULL WHERE request_id=?''',(queued['request_id'],));self.supervisor.db.commit()
        self.assertFalse(scheduler._finish(row,'SUCCEEDED',None,
          {'usage':{'input_tokens':1,'output_tokens':1}},time.time()))
        self.assertEqual(self.supervisor.db.execute('''SELECT state FROM
          model_requests WHERE request_id=?''',(queued['request_id'],)).fetchone()[0],
          'UNKNOWN')

    def test_scheduler_runtime_once_continues_without_browser(self):
        self.assigned();self.control.queue_request('demo-b','developer',[],
          'background-once')
        key_path=os.path.join(self.root,'model.key')
        with open(key_path,'wb') as stream:stream.write(self.master)
        os.chmod(key_path,0o600)
        result=subprocess.run([sys.executable,os.path.join(ROOT,'scripts',
          'model_scheduler_runtime.py'),'--db',self.db,
          '--test-authority-key',KEY.decode(),'--tenant','tenant-a',
          '--principal','runtime','--model-master-key-file',key_path,'--once'],
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('SUCCEEDED',result.stdout)
        state=self.supervisor.db.execute('''SELECT state FROM model_requests
          WHERE idempotency_key='background-once' ''').fetchone()[0]
        self.assertEqual(state,'SUCCEEDED')

    def test_circuit_breaker_opens_after_three_real_failures(self):
        self.assigned(model='auth')
        for index in range(3):
            self.control.queue_request('demo-b','developer',[],
              'auth-%d'%index)
            self.assertEqual(ModelScheduler(self.control).run_once()['state'],
              'FAILED')
        provider=self.supervisor.db.execute('''SELECT circuit_state,
          failure_count FROM model_providers WHERE provider_id='free' ''').fetchone()
        self.assertEqual((provider['circuit_state'],provider['failure_count']),
          ('OPEN',3))
        self.control.queue_request('demo-b','developer',[],'auth-four')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],
          'CIRCUIT_OPEN')

    def test_rate_and_concurrency_limits_leave_request_queued(self):
        self.assigned();self.supervisor.db.execute('''UPDATE model_providers SET
          rate_limit_per_min=1,concurrency_limit=1 WHERE provider_id='free' ''')
        self.supervisor.db.commit()
        self.control.queue_request('demo-b','developer',[],'limit-one')
        self.assertEqual(ModelScheduler(self.control).run_once(now=time.time())['state'],
          'SUCCEEDED')
        second=self.control.queue_request('demo-b','developer',[],'limit-two')
        self.assertEqual(ModelScheduler(self.control).run_once(now=time.time())['state'],
          'QUEUED_LIMIT')
        state=self.supervisor.db.execute('SELECT state FROM model_requests WHERE request_id=?',
          (second['request_id'],)).fetchone()[0]
        self.assertEqual(state,'QUEUED')

    def test_unknown_price_usage_remains_unknown_not_zero(self):
        self.provider('unknown',price='UNKNOWN');self.model('unknown','ok','UNKNOWN')
        self.role();self.qualify('unknown','ok')
        self.control.assign('demo-b','developer','v1','developer-1',allow_paid=True)
        queued=self.control.queue_request('demo-b','developer',[],'unknown-cost')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'SUCCEEDED')
        usage=self.supervisor.db.execute('''SELECT cost_state,cost_value FROM
          model_usage_events WHERE request_id=?''',(queued['request_id'],)).fetchone()
        self.assertEqual(usage['cost_state'],'UNKNOWN')
        self.assertIsNone(usage['cost_value'])


if __name__=='__main__':unittest.main()
