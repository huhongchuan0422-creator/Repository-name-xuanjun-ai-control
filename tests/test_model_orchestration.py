from __future__ import print_function

import json
import os
import shutil
import subprocess
import socketserver
import sqlite3
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
        value={'id':'fixture-'+model,'choices':[{'message':{'content':'ok-'+model}}]}
        if model!='no-usage':value['usage']={'prompt_tokens':3,
          'completion_tokens':2,'total_tokens':5}
        raw=json.dumps(value).encode()
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
        self.control.record_task_spec('demo-b','test goal',['artifact'],['tests pass'])
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

    def role(self,rid='developer',phase='EXECUTOR',caps=None,writer=True,
             review_kind=None):
        return self.control.create_role({'role_id':rid,'version':'v1','phase':phase,
          'capabilities':caps or ['code'],'writer_allowed':writer,'enabled':True,
          'review_kind':review_kind})

    def qualify(self,pid='free',model='ok'):
        try:self.control.register_benchmark_suite('suite-v1',[{'case_id':'basic',
          'capability':'code','messages':[{'role':'user','content':'fixture'}],
          'expected_contains':'ok'}])
        except Exception:pass
        class QualifiedAdapter(object):
            def invoke(self,*_args,**_kwargs):return {'content':'ok',
              'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2},
              'provider_request_id':'benchmark-fixture'}
        row=self.supervisor.db.execute('''SELECT price_state FROM model_providers
          WHERE tenant_id='tenant-a' AND provider_id=?''',(pid,)).fetchone()
        result=self.control.run_benchmark(pid,model,'suite-v1',QualifiedAdapter(),
          allow_paid=row['price_state']!='KNOWN_FREE')
        self.assertEqual(result['state'],'QUALIFIED')
        return result

    def assigned(self,pid='free',model='ok'):
        self.provider(pid);self.model(pid,model);self.role();self.qualify(pid,model)
        return self.control.assign('demo-b','developer','v1','developer-1')

    def checklist_sha(self):
        return self.control.register_checklist('demo-b',[{'id':'tests pass',
          'required':True,'result':'PASS','evidence':'test-log'}],
          'admin:owner')['content_sha256']

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
        with self.assertRaisesRegex(ValueError,'NO_AUTHORIZED'):
            self.control.assign('demo-b','developer','v1','dev')
        with self.assertRaisesRegex(ValueError,'NO_AUTHORIZED'):
            self.control.assign('demo-b','developer','v1','dev',allow_paid=True)

    def test_quota_unknown_or_exhausted_holds_before_adapter_call(self):
        self.provider();self.model();self.control.register_benchmark_suite(
          'quota-suite',[{'case_id':'basic','capability':'code',
          'messages':[{'role':'user','content':'fixture'}],
          'expected_contains':'ok'}])
        called=[]
        class Never(object):
            def invoke(self,*args,**kwargs):called.append(args);raise AssertionError()
        for state,reason in (('UNKNOWN','QUALIFICATION_UNKNOWN'),
                             ('EXHAUSTED','FREE_ALLOWANCE_EXHAUSTED')):
            self.control.set_quota_status('free',state,'OWNER_VERIFIED_PLAN',
              unavailable_reason=reason)
            result=self.control.run_benchmark('free','ok','quota-suite',Never())
            self.assertEqual(result['state'],'NOT_QUALIFIED')
        self.assertEqual(called,[])
        projected=self.control.projection()['quota_status'][0]
        self.assertEqual(projected['quota_state'],'EXHAUSTED')
        self.assertEqual(projected['unavailable_reason'],
                         'FREE_ALLOWANCE_EXHAUSTED')

    def test_stale_quota_verification_holds_before_adapter_call(self):
        self.provider();self.model();self.control.register_benchmark_suite(
          'stale-suite',[{'case_id':'basic','capability':'code',
          'messages':[{'role':'user','content':'fixture'}],
          'expected_contains':'ok'}])
        self.control.set_quota_status('free','AVAILABLE','EXISTING_PLAN_INCLUDED',
          verified_at=100,now=100)
        called=[]
        class Never(object):
            def invoke(self,*args,**kwargs):called.append(args);raise AssertionError()
        result=self.control.run_benchmark('free','ok','stale-suite',Never(),
          now=3701)
        self.assertEqual(result['state'],'NOT_QUALIFIED');self.assertEqual(called,[])

    def test_paid_model_requires_explicit_unit_costs(self):
        self.provider('paid',price='KNOWN_PAID')
        with self.assertRaisesRegex(ValueError,'KNOWN_PAID_UNIT_COSTS'):
            self.control.upsert_model({'provider_id':'paid','model_id':'paid',
              'capabilities':['code'],'enabled':True,
              'price_state':'KNOWN_PAID','input_unit_cost':None,
              'output_unit_cost':None})

    def test_paid_provider_cannot_disguise_model_as_free_without_costs(self):
        self.provider('paid-provider',price='KNOWN_PAID')
        with self.assertRaisesRegex(ValueError,'PAID_PROVIDER_MODEL'):
            self.control.upsert_model({'provider_id':'paid-provider',
              'model_id':'disguised-free','capabilities':['code'],
              'enabled':True,'price_state':'KNOWN_FREE',
              'input_unit_cost':None,'output_unit_cost':None})

    def test_free_provider_cannot_become_paid_while_free_model_remains(self):
        self.provider('price-transition');self.model('price-transition','ok')
        with self.assertRaisesRegex(ValueError,'PAID_PROVIDER_MODELS'):
            self.provider('price-transition',price='KNOWN_PAID')
        row=self.supervisor.db.execute('''SELECT price_state FROM model_providers
          WHERE provider_id='price-transition' ''').fetchone()
        self.assertEqual(row['price_state'],'KNOWN_FREE')

    def test_provider_and_model_price_transitions_are_transactional(self):
        self.provider('race-price');blocked=[];attempted=[]
        def inject_model(action,table,*_args):
            if (not attempted and action==sqlite3.SQLITE_READ and
                    table=='model_catalog'):
                attempted.append(True);other=sqlite3.connect(self.db,timeout=0)
                try:
                    other.execute('''INSERT INTO model_catalog VALUES
                      (?,?,?,?,?,?,?,?)''',('tenant-a','race-price','late-free',
                      '["code"]',1,'KNOWN_FREE',0,0));other.commit()
                except sqlite3.OperationalError as exc:blocked.append(str(exc))
                finally:other.close()
            return sqlite3.SQLITE_OK
        self.supervisor.db.set_authorizer(inject_model)
        try:self.provider('race-price',price='KNOWN_PAID')
        finally:self.supervisor.db.set_authorizer(None)
        self.assertTrue(any('locked' in item for item in blocked),blocked)
        verify=sqlite3.connect(self.db)
        try:self.assertEqual(verify.execute('''SELECT COUNT(*) FROM model_catalog
          WHERE provider_id='race-price' ''').fetchone()[0],0)
        finally:verify.close()

    def test_model_insert_and_provider_price_change_are_transactional(self):
        # The inverse path is serialized too: a concurrent provider price
        # change cannot race a free model insert.
        self.provider('race-model');blocked=[];attempted=[]
        def raise_price(action,table,*_args):
            if (not attempted and action==sqlite3.SQLITE_READ and
                    table=='model_providers'):
                attempted.append(True);other=sqlite3.connect(self.db,timeout=0)
                try:
                    other.execute('''UPDATE model_providers SET
                      price_state='KNOWN_PAID' WHERE tenant_id='tenant-a'
                      AND provider_id='race-model' ''');other.commit()
                except sqlite3.OperationalError as exc:blocked.append(str(exc))
                finally:other.close()
            return sqlite3.SQLITE_OK
        self.supervisor.db.set_authorizer(raise_price)
        try:self.model('race-model','free-safe')
        finally:self.supervisor.db.set_authorizer(None)
        self.assertTrue(any('locked' in item for item in blocked),blocked)
        verify=sqlite3.connect(self.db)
        try:self.assertEqual(verify.execute('''SELECT price_state FROM
          model_providers WHERE provider_id='race-model' ''').fetchone()[0],
          'KNOWN_FREE')
        finally:verify.close()

    def test_benchmark_calls_share_persistent_provider_rate_limit(self):
        self.control.upsert_provider({'provider_id':'limited','display_name':'limited',
          'adapter_type':'openai-compatible','base_url':self.url,'enabled':True,
          'price_state':'KNOWN_FREE','rate_limit_per_min':1,
          'concurrency_limit':1,'timeout_seconds':1,'retry_limit':0},SECRET)
        self.model('limited','ok');self.control.register_benchmark_suite('two',[{
          'case_id':'one','capability':'code','messages':[],
          'expected_contains':'ok'},{'case_id':'two','capability':'code',
          'messages':[],'expected_contains':'ok'}])
        calls=[]
        class Counting(object):
            def invoke(inner,*args):
                calls.append(1);return {'content':'ok','usage':{
                  'input_tokens':1,'output_tokens':1,'total_tokens':2},
                  'provider_request_id':'fixture'}
        result=self.control.run_benchmark('limited','ok','two',Counting(),now=1000)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          model_call_attempts WHERE provider_id='limited' ''').fetchone()[0],1)
        self.assertEqual(result['state'],'NOT_QUALIFIED')

    def test_free_capable_first_and_self_review_forbidden(self):
        self.provider('paid',price='KNOWN_PAID');self.model('paid','ok','KNOWN_PAID')
        self.provider('free');self.model();self.role();self.qualify('free','ok')
        self.role('reviewer','REVIEWER',['code'],False,'QA')
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
        self.control.register_skill('skill','v1',{'instructions':'test only'},'a'*64)
        self.assertEqual(self.control.bind_skill('developer','v1','skill','v1','a'*64,'APPROVED')['status'],'APPROVED')

    def test_real_http_adapters_parse_success_auth_rate_and_timeout(self):
        for cls in (OpenAICompatibleAdapter,SiliconFlowAdapter):
            adapter=cls();ok=adapter.invoke(self.url,SECRET,'ok',[{'role':'user','content':'x'}],1)
            self.assertEqual(ok['usage']['total_tokens'],5)
            unknown=adapter.invoke(self.url,SECRET,'no-usage',[],1)
            self.assertEqual(unknown['usage'],{'input_tokens':None,
              'output_tokens':None,'total_tokens':None})
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

    def test_qualification_unknown_after_queue_holds_before_adapter_call(self):
        self.assigned();queued=self.control.queue_request('demo-b','developer',[],
          'qualification-revoked')
        latest=self.supervisor.db.execute('''SELECT * FROM model_evaluations
          WHERE tenant_id='tenant-a' AND provider_id='free' AND model_id='ok'
          ORDER BY observed_at DESC LIMIT 1''').fetchone()
        values=list(latest);values[1]='qualification-unknown';values[11]='UNKNOWN'
        values[13]=latest['observed_at']+1
        self.supervisor.db.execute('''INSERT INTO model_evaluations VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',values);self.supervisor.db.commit()
        calls=[]
        class Never(object):
            def invoke(self,*args):calls.append(args);raise AssertionError()
        result=ModelScheduler(self.control,{'openai-compatible':Never(),
          'siliconflow':Never()}).run_once()
        self.assertEqual(result['state'],'HOLD');self.assertEqual(calls,[])
        row=self.supervisor.db.execute('''SELECT state,error_kind FROM
          model_requests WHERE request_id=?''',(queued['request_id'],)).fetchone()
        self.assertEqual(tuple(row),('HOLD',
          'MODEL_QUALIFICATION_NOT_CURRENT_HOLD'))

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
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'HOLD')

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
        self.supervisor.db.execute('''INSERT INTO model_call_reservations VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',('tenant-a','lost-reservation',
          queued['request_id'],1,'demo-b','free','ok',1,1,0,'KNOWN_ZERO',
          'ACTIVE',1,None));self.supervisor.db.commit()
        self.assertEqual(ModelScheduler(self.control).run_once(now=10)['state'],'IDLE')
        row=self.supervisor.db.execute('''SELECT state,error_kind,attempts FROM
          model_requests WHERE request_id=?''',(queued['request_id'],)).fetchone()
        self.assertEqual((row['state'],row['error_kind'],row['attempts']),
          ('UNKNOWN','WORKER_LOST_SIDE_EFFECT_UNKNOWN',1))
        reservation=self.supervisor.db.execute('''SELECT state,cost_state,
          reserved_cost FROM model_call_reservations WHERE
          reservation_id='lost-reservation' ''').fetchone()
        self.assertEqual(tuple(reservation),('SETTLED','UNKNOWN',None))

    def test_writer_permission_and_writer_snapshot_are_enforced(self):
        self.provider();self.model();self.qualify('free','ok')
        self.role('nonwriter','EXECUTOR',['code'],False)
        with self.assertRaisesRegex(ValueError,'WRITER_PERMISSION'):
            self.control.assign('demo-b','nonwriter','v1','assistant')
        self.role();self.control.assign('demo-b','developer','v1','developer-1')
        queued=self.control.queue_request('demo-b','developer',[],'writer-snapshot')
        self.supervisor.db.execute("""UPDATE tasks SET authority_caller_id='other-writer'
          WHERE task_id='demo-b'""");self.supervisor.db.commit()
        called=[]
        class Never(object):
            def invoke(self,*args):called.append(args);raise AssertionError()
        result=ModelScheduler(self.control,{'openai-compatible':Never(),
          'siliconflow':Never()}).run_once()
        self.assertEqual(result['state'],'HOLD');self.assertEqual(called,[])
        self.assertEqual(self.supervisor.db.execute('''SELECT error_kind FROM
          model_requests WHERE request_id=?''',(queued['request_id'],)).fetchone()[0],
          'STALE_OR_UNAUTHORIZED')

    def test_cancel_during_success_cannot_advance_request(self):
        self.assigned();queued=self.control.queue_request('demo-b','developer',[],
          'cancel-during-success');control=self.control
        class CancelThenSuccess(object):
            def invoke(self,*args):
                control.request_cancel(queued['request_id'])
                return {'content':'late','usage':{'input_tokens':1,
                  'output_tokens':1,'total_tokens':2},
                  'provider_request_id':'late-success'}
        result=ModelScheduler(control,{'openai-compatible':CancelThenSuccess(),
          'siliconflow':CancelThenSuccess()}).run_once()
        self.assertEqual(result['state'],'CANCELLED')
        row=self.supervisor.db.execute('''SELECT state,cancel_requested,
          error_kind FROM model_requests WHERE request_id=?''',(
          queued['request_id'],)).fetchone()
        self.assertEqual(tuple(row),('CANCELLED',1,
          'CANCELLED_DURING_CALL_RESULT_RETAINED'))

    def test_connection_purpose_mismatch_never_queues(self):
        from connection_management import ConnectionManager
        self.provider();self.model();self.role();self.qualify('free','ok')
        self.control.assign('demo-b','developer','v1','developer-1')
        manager=ConnectionManager(self.gateway,self.context,self.master)
        manager.upsert({'connection_id':'billing','provider_id':'free',
          'purpose':'MCP_TOOL','auth_type':'API_KEY',
          'destination_origin':self.url,'issuer':None,
          'authorization_endpoint':None,'token_endpoint':None,
          'revocation_endpoint':None,'redirect_uri':None,'client_id':None,
          'scopes':[],'supports_refresh':False},'billing-secret')
        with self.assertRaisesRegex(ValueError,'ACTIVE_PROVIDER_CONNECTION'):
            self.control.queue_request('demo-b','developer',[],'bad-purpose',
              connection_id='billing')
        self.assertEqual(self.supervisor.db.execute('''SELECT count(*) FROM
          model_requests WHERE idempotency_key='bad-purpose' ''').fetchone()[0],0)

    def test_cancel_before_call_and_cost_unknown_are_truthful(self):
        self.assigned();queued=self.control.queue_request('demo-b','developer',[],
          'cancel-first')
        self.assertEqual(self.control.request_cancel(queued['request_id'])['state'],
          'CANCELLED')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'IDLE')
        other=ModelControl(self.gateway,self.context,self.master)
        self.assertEqual(other.projection()['requests'][0]['state'],'CANCELLED')

    def test_independent_review_rework_and_acceptance_gates(self):
        self.assigned();self.role('reviewer','REVIEWER',['code'],False,'QA')
        self.role('security','REVIEWER',['code'],False,'SECURITY')
        self.role('acceptor','ACCEPTOR',['code'],False)
        self.control.assign('demo-b','reviewer','v1','qa')
        self.control.assign('demo-b','security','v1','security')
        self.control.assign('demo-b','acceptor','v1','acceptor')
        developer=ModelControl(self.gateway,
          self.authority.issue('tenant-a','developer-1'),self.master)
        reviewer=ModelControl(self.gateway,
          self.authority.issue('tenant-a','qa'),self.master)
        security=ModelControl(self.gateway,
          self.authority.issue('tenant-a','security'),self.master)
        acceptor=ModelControl(self.gateway,
          self.authority.issue('tenant-a','acceptor'),self.master)
        submitted=developer.submit_candidate('demo-b','a'*64,self.checklist_sha(),
          'developer-1')
        with self.assertRaisesRegex(ValueError,'SELF_REVIEW'):
            developer.review_candidate(submitted['candidate_id'],
              'developer-1',[],True)
        changed=reviewer.review_candidate(submitted['candidate_id'],'qa',
          [{'id':'DEFECT-1'}],False)
        self.assertEqual(changed['state'],'CHANGES_REQUESTED')
        with self.assertRaisesRegex(ValueError,'REVIEW_PASS'):
            acceptor.validate_accept_candidate(submitted['candidate_id'],'acceptor')
        with self.assertRaisesRegex(ValueError,'REVIEWABLE_CANDIDATE'):
            reviewer.review_candidate(submitted['candidate_id'],'qa',[],True)
        revised=developer.submit_candidate('demo-b','c'*64,self.checklist_sha(),
          'developer-1')
        passed=reviewer.review_candidate(revised['candidate_id'],'qa',[],True)
        self.assertEqual(passed['state'],'QA_PASSED')
        passed=security.review_candidate(revised['candidate_id'],'security',[],
          True,'SECURITY')
        self.assertEqual(passed['state'],'REVIEW_PASSED')
        acceptor.validate_accept_candidate(revised['candidate_id'],'acceptor')
        self.executor.complete_success('demo-b','attempt-b','c'*64,
          json.loads(self.supervisor._task('demo-b')['completion_json']))
        self.supervisor.db.execute('''UPDATE delivery_candidates SET
          artifact_sha256=? WHERE candidate_id=?''',('a'*64,
          revised['candidate_id']));self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'CANDIDATE_SNAPSHOT_MISMATCH'):
            acceptor.validate_accept_candidate(revised['candidate_id'],'acceptor')
        self.supervisor.db.execute('''UPDATE delivery_candidates SET
          artifact_sha256=? WHERE candidate_id=?''',('c'*64,
          revised['candidate_id']));self.supervisor.db.commit()
        # A crash between canonical completion and candidate update is
        # recoverable: validation accepts the same terminal attempt.
        acceptor.validate_accept_candidate(revised['candidate_id'],'acceptor')
        self.assertEqual(acceptor.accept_candidate(revised['candidate_id'],
          'acceptor')['state'],'ACCEPTED')
        with self.assertRaisesRegex(ValueError,'CURRENT_CANDIDATE'):
            reviewer.review_candidate(revised['candidate_id'],'qa',[],False)
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          candidate_reviews WHERE candidate_id IN (?,?)''',(submitted['candidate_id'],
          revised['candidate_id'])).fetchone()[0],3)

    def test_review_kind_requires_matching_versioned_role_mandate(self):
        self.assigned();self.role('qa-only','REVIEWER',['code'],False,'QA')
        self.control.assign('demo-b','qa-only','v1','qa')
        developer=ModelControl(self.gateway,self.authority.issue(
          'tenant-a','developer-1'),self.master)
        qa=ModelControl(self.gateway,self.authority.issue('tenant-a','qa'),
          self.master)
        candidate=developer.submit_candidate('demo-b','a'*64,
          self.checklist_sha(),'developer-1')
        with self.assertRaisesRegex(ValueError,'MANDATE_MISMATCH'):
            qa.review_candidate(candidate['candidate_id'],'qa',[],True,
              'SECURITY')

    def test_older_review_passed_candidate_cannot_supersede_new_submission(self):
        self.assigned();self.role('reviewer','REVIEWER',['code'],False,'QA')
        self.role('security','REVIEWER',['code'],False,'SECURITY')
        self.role('acceptor','ACCEPTOR',['code'],False)
        self.control.assign('demo-b','reviewer','v1','qa')
        self.control.assign('demo-b','security','v1','security')
        self.control.assign('demo-b','acceptor','v1','acceptor')
        developer=ModelControl(self.gateway,
          self.authority.issue('tenant-a','developer-1'),self.master)
        reviewer=ModelControl(self.gateway,self.authority.issue('tenant-a','qa'),self.master)
        security=ModelControl(self.gateway,self.authority.issue('tenant-a','security'),self.master)
        acceptor=ModelControl(self.gateway,self.authority.issue('tenant-a','acceptor'),self.master)
        old=developer.submit_candidate('demo-b','a'*64,self.checklist_sha(),'developer-1',now=1)
        reviewer.review_candidate(old['candidate_id'],'qa',[],True,now=2)
        security.review_candidate(old['candidate_id'],'security',[],True,
          'SECURITY',now=2.5)
        developer.submit_candidate('demo-b','c'*64,self.checklist_sha(),'developer-1',now=3)
        with self.assertRaisesRegex(ValueError,'LATEST_CANDIDATE'):
            acceptor.validate_accept_candidate(old['candidate_id'],'acceptor')

    def test_candidate_hash_identity_and_current_attempt_are_enforced(self):
        self.assigned();developer=ModelControl(self.gateway,
          self.authority.issue('tenant-a','developer-1'),self.master)
        with self.assertRaisesRegex(ValueError,'CANONICAL_ARTIFACT'):
            developer.submit_candidate('demo-b','z'*64,self.checklist_sha(),'developer-1')
        self.supervisor.db.execute("""UPDATE tasks SET authority_state='REVOKED'
          WHERE task_id='demo-b'""");self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'CURRENT_CANDIDATE'):
            developer.submit_candidate('demo-b','a'*64,self.checklist_sha(),'developer-1')

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
        self.supervisor.db.execute("DELETE FROM model_call_attempts WHERE worker_id LIKE 'benchmark:%'")
        self.supervisor.db.execute("DELETE FROM model_call_reservations WHERE task_id LIKE 'BENCHMARK:%'")
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

    def test_unknown_price_is_held_before_call_not_recorded_as_zero(self):
        self.provider('unknown',price='UNKNOWN');self.model('unknown','ok','UNKNOWN')
        self.control.register_benchmark_suite('unknown-suite',[{'case_id':'basic',
          'capability':'code','messages':[{'role':'user','content':'fixture'}],
          'expected_contains':'ok'}])
        called=[]
        class Never(object):
            def invoke(self,*args,**kwargs):called.append(args);raise AssertionError()
        result=self.control.run_benchmark('unknown','ok','unknown-suite',Never(),
          allow_paid=True)
        self.assertEqual(result['state'],'NOT_QUALIFIED');self.assertEqual(called,[])
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          model_usage_attempts WHERE provider_id='unknown' ''').fetchone()[0],0)

    def test_destination_change_invalidates_old_provider_secret(self):
        self.provider();changed={'provider_id':'free','display_name':'free',
          'adapter_type':'openai-compatible','base_url':'http://localhost:%d'%
          self.server.server_port,'enabled':True,'price_state':'KNOWN_FREE',
          'rate_limit_per_min':10,'concurrency_limit':2,'timeout_seconds':.05,
          'retry_limit':1}
        receipt=self.control.upsert_provider(changed)
        self.assertFalse(receipt['secret_configured'])
        with self.assertRaisesRegex(ValueError,'SECRET_REQUIRED'):
            self.control.provider_secret('free')

    def test_queued_request_rechecks_provider_config_before_send(self):
        self.assigned();queued=self.control.queue_request('demo-b','developer',[],
          'config-change')
        self.control.upsert_provider({'provider_id':'free','display_name':'free',
          'adapter_type':'openai-compatible','base_url':self.url,'enabled':True,
          'price_state':'KNOWN_FREE','rate_limit_per_min':10,
          'concurrency_limit':2,'timeout_seconds':.05,'retry_limit':1},SECRET+'x')
        called=[]
        class Never(object):
            def invoke(self,*args):called.append(args);raise AssertionError()
        result=ModelScheduler(self.control,{'openai-compatible':Never(),
          'siliconflow':Never()}).run_once()
        self.assertEqual(result['state'],'HOLD');self.assertEqual(called,[])
        row=self.supervisor.db.execute('''SELECT state,error_kind FROM
          model_requests WHERE request_id=?''',(queued['request_id'],)).fetchone()
        self.assertEqual((row['state'],row['error_kind']),('HOLD',
          'PROVIDER_CONFIG_CHANGED_REQUEUE_REQUIRED'))

    def test_sent_500_is_unknown_and_usage_is_not_zero_cost(self):
        self.assigned();queued=self.control.queue_request('demo-b','developer',[],
          'http-500')
        class FiveHundred(object):
            def invoke(self,*args):raise ProviderError('HTTP','HTTP_500',True)
        result=ModelScheduler(self.control,{'openai-compatible':FiveHundred(),
          'siliconflow':FiveHundred()}).run_once()
        self.assertEqual(result['state'],'UNKNOWN')
        usage=self.supervisor.db.execute('''SELECT cost_state,input_tokens FROM
          model_usage_attempts WHERE request_id=?''',(queued['request_id'],)).fetchone()
        self.assertEqual(usage['cost_state'],'UNKNOWN');self.assertIsNone(usage['input_tokens'])

    def test_cancel_during_429_never_enters_retry_wait(self):
        self.assigned();queued=self.control.queue_request('demo-b','developer',[],
          'cancel-429')
        control=self.control
        class CancelThenRate(object):
            def invoke(self,*args):
                control.request_cancel(queued['request_id'])
                raise ProviderError('RATE_LIMIT','HTTP_429',True)
        result=ModelScheduler(control,{'openai-compatible':CancelThenRate(),
          'siliconflow':CancelThenRate()}).run_once()
        self.assertEqual(result['state'],'CANCELLED')
        self.assertEqual(self.supervisor.db.execute('''SELECT state FROM
          model_requests WHERE request_id=?''',(queued['request_id'],)).fetchone()[0],
          'CANCELLED')

    def test_fair_queue_skips_open_provider_and_runs_healthy_provider(self):
        self.assigned('blocked','ok');first=self.control.queue_request('demo-b',
          'developer',[],'blocked-first')
        self.provider('healthy');self.model('healthy');self.qualify('healthy','ok')
        self.supervisor.db.execute('''UPDATE model_assignments SET provider_id='healthy'
          WHERE task_id='demo-b' AND role_id='developer' ''')
        self.supervisor.db.execute('''UPDATE model_providers SET circuit_state='OPEN',
          next_probe_at=? WHERE provider_id='blocked' ''',(time.time()+600,))
        self.supervisor.db.commit()
        second=self.control.queue_request('demo-b','developer',[],'healthy-second')
        result=ModelScheduler(self.control).run_once()
        self.assertEqual(result['request_id'],second['request_id'])
        self.assertEqual(result['state'],'SUCCEEDED')
        self.assertEqual(self.supervisor.db.execute('''SELECT state FROM
          model_requests WHERE request_id=?''',(first['request_id'],)).fetchone()[0],
          'QUEUED')

    def test_skill_revocation_and_module_disable_block_new_execution(self):
        self.assigned();self.control.register_skill('reviewed','v1',
          {'instructions':'bounded'},'a'*64)
        self.control.bind_skill('developer','v1','reviewed','v1','a'*64,'APPROVED')
        queued=self.control.queue_request('demo-b','developer',[],'skill-revoke')
        self.control.revoke_skill('reviewed','v1')
        self.assertEqual(ModelScheduler(self.control).run_once()['state'],'HOLD')
        self.assertEqual(self.supervisor.db.execute('''SELECT error_kind FROM
          model_requests WHERE request_id=?''',(queued['request_id'],)).fetchone()[0],
          'SKILL_SNAPSHOT_REVOKED_OR_CHANGED')
        self.control.set_module('xuanjun.scheduler.kernel','v1',False)
        self.assertEqual(self.supervisor.db.execute('''SELECT desired_state FROM
          role_instances WHERE instance_id='developer-1' ''').fetchone()[0],
          'STOPPED')

    def test_approved_skill_content_is_in_actual_outbound_request(self):
        self.assigned();content={'instructions':'bounded','forbidden':['deploy']}
        self.control.register_skill('reviewed','v1',content,'a'*64)
        self.control.bind_skill('developer','v1','reviewed','v1','a'*64,'APPROVED')
        self.control.queue_request('demo-b','developer',
          [{'role':'user','content':'work'}],'skill-content')
        captured=[]
        class Capture(object):
            def invoke(self,_url,_secret,_model,messages,*_args):
                captured.extend(messages);return {'content':'ok',
                  'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2},
                  'provider_request_id':'skill-fixture'}
        result=ModelScheduler(self.control,{'siliconflow':Capture(),
          'openai-compatible':Capture()}).run_once()
        self.assertEqual(result['state'],'SUCCEEDED')
        injected=json.loads(captured[0]['content'])['approved_skills'][0]
        self.assertEqual(injected['content'],content)
        self.assertEqual(injected['skill_version'],'v1')

    def test_success_without_complete_usage_remains_unknown_not_zero(self):
        self.assigned()
        for suffix,usage in (('missing',{}),('partial',{'input_tokens':3,
          'output_tokens':None,'total_tokens':None})):
            queued=self.control.queue_request('demo-b','developer',
              [],'usage-'+suffix)
            class UsageFixture(object):
                def invoke(self,*_args):return {'content':'ok','usage':usage,
                  'provider_request_id':'usage-'+suffix}
            result=ModelScheduler(self.control,{'siliconflow':UsageFixture(),
              'openai-compatible':UsageFixture()}).run_once()
            self.assertEqual(result['state'],'SUCCEEDED')
            row=self.supervisor.db.execute('''SELECT input_tokens,output_tokens,
              cost_state,cost_value FROM model_usage_attempts WHERE request_id=?''',
              (queued['request_id'],)).fetchone()
            self.assertEqual(row['cost_state'],'UNKNOWN');self.assertIsNone(row['cost_value'])
            if suffix=='missing':self.assertIsNone(row['input_tokens'])
            self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
              model_usage_events WHERE request_id=?''',(queued['request_id'],)).fetchone()[0],0)

    def test_paid_model_is_held_before_send_under_zero_new_spend_policy(self):
        self.provider('paid',price='KNOWN_PAID');self.model('paid','ok','KNOWN_PAID')
        self.supervisor.db.execute('''UPDATE model_catalog SET input_unit_cost=1,
          output_unit_cost=1 WHERE provider_id='paid' ''');self.supervisor.db.commit()
        called=[]
        class Never(object):
            def invoke(self,*args,**kwargs):called.append(args);raise AssertionError()
        self.control.register_benchmark_suite('paid-suite',[{'case_id':'paid',
          'capability':'code','messages':[{'role':'user','content':'spend'}],
          'expected_contains':'ok'}])
        result=self.control.run_benchmark('paid','ok','paid-suite',Never(),
          allow_paid=True)
        self.assertEqual(result['state'],'NOT_QUALIFIED')
        self.assertEqual(called,[])
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          model_call_reservations WHERE provider_id='paid' ''').fetchone()[0],0)

    def test_incomplete_or_unexecuted_checklist_cannot_freeze_candidate(self):
        self.assigned();developer=ModelControl(self.gateway,
          self.authority.issue('tenant-a','developer-1'),self.master)
        with self.assertRaisesRegex(ValueError,'REQUIRED_CHECK_EVIDENCE_REQUIRED'):
            self.control.register_checklist('demo-b',[{'id':'tests pass',
              'required':True,'result':'NOT_EXECUTED','evidence':'missing'}],
              'admin:owner')
        with self.assertRaisesRegex(ValueError,'REQUIRED_CHECK_EVIDENCE_REQUIRED'):
            self.control.register_checklist('demo-b',[{'id':'tests pass',
              'required':False,'result':'FAIL','evidence':''}],'admin:owner')
        with self.assertRaisesRegex(ValueError,'ACCEPTANCE_COVERAGE_MISMATCH'):
            self.control.register_checklist('demo-b',[{'id':'other',
              'required':True,'result':'PASS','evidence':'log'}],'admin:owner')

    def test_fair_queue_reaches_healthy_101st_request(self):
        self.provider('blocked');self.model('blocked');self.qualify('blocked','ok')
        self.role();self.control.assign('demo-b','developer','v1','developer-1')
        for index in range(100):
            self.control.queue_request('demo-b','developer',[],
              'blocked-%03d'%index)
        self.provider('healthy-101');self.model('healthy-101');
        self.qualify('healthy-101','ok')
        self.supervisor.db.execute('''UPDATE model_assignments SET
          provider_id='healthy-101' WHERE task_id='demo-b' AND role_id='developer' ''')
        self.supervisor.db.commit()
        healthy=self.control.queue_request('demo-b','developer',[],'healthy-101')
        self.supervisor.db.execute('''UPDATE model_providers SET circuit_state='OPEN',
          next_probe_at=? WHERE provider_id='blocked' ''',(time.time()+600,))
        self.supervisor.db.commit()
        result=ModelScheduler(self.control).run_once()
        self.assertEqual(result['request_id'],healthy['request_id'])
        self.assertEqual(result['state'],'SUCCEEDED')

    def test_frozen_task_spec_change_invalidates_later_review(self):
        self.assigned();self.role('reviewer','REVIEWER',['code'],False,'QA')
        self.control.assign('demo-b','reviewer','v1','qa')
        developer=ModelControl(self.gateway,self.authority.issue('tenant-a',
          'developer-1'),self.master)
        reviewer=ModelControl(self.gateway,self.authority.issue('tenant-a','qa'),
          self.master)
        candidate=developer.submit_candidate('demo-b','a'*64,
          self.checklist_sha(),'developer-1')
        self.supervisor.db.execute('''UPDATE task_work_specs SET goal='changed'
          WHERE tenant_id='tenant-a' AND task_id='demo-b' ''');self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'FROZEN_SCOPE_CHANGED'):
            reviewer.review_candidate(candidate['candidate_id'],'qa',[],True)


if __name__=='__main__':unittest.main()
