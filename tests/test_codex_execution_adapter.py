from __future__ import print_function

import json
import hashlib
import os
import shutil
import tempfile
import time
import unittest
import sys
import threading
from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
import sys;sys.path.insert(0,os.path.join(ROOT,'scripts'))
from codex_execution_adapter import (CodexExecutionControl,CodexSDKTransport,
  CodexAppServerTransport,CodexSendUnknown)
from execution_policy_gateway import ExecutionPolicyGateway
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel,TestOnlyExecutor,TestTenantAuthority
from task_supervisor import Supervisor,canonical
from task_writer_fence import Fence
from model_orchestration import ModelControl
from connection_management import ConnectionManager
from task_center_app import CodexWorkerLoop

KEY=b'0123456789abcdef0123456789abcdef'


class CodexExecutionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        self.supervisor=Supervisor(self.db);self.authority=TestTenantAuthority(KEY)
        self.gateway=GatewayKernel(self.supervisor,self.authority)
        self.context=self.authority.issue('tenant-a','admin:owner')
        self.gateway.register_graph(self.context,demo_graph('tenant-a'))
        self.fence=Fence(self.supervisor,os.path.join(self.root,'locks'))
        TestOnlyExecutor(self.gateway,self.fence,self.context).start(
          'demo-b','attempt-b',['fake:demo-b'],time.time()+600)
        self.master=Fernet.generate_key()
        models=ModelControl(self.gateway,self.context,self.master)
        models.record_task_spec(
          'demo-b','bounded fixture execution',['artifact'],['tests'])
        models.upsert_provider({'provider_id':'codex-fixture','display_name':'Codex fixture',
          'adapter_type':'openai-compatible','base_url':'http://127.0.0.1:9',
          'enabled':True,'price_state':'KNOWN_FREE','rate_limit_per_min':10,
          'concurrency_limit':1,'timeout_seconds':1,'retry_limit':0},'fixture-secret')
        models.set_quota_status('codex-fixture','AVAILABLE',
          'TEST_ONLY_INCLUDED_FIXTURE',verified_at=time.time(),unavailable_reason=None)
        connections=ConnectionManager(self.gateway,self.context,self.master)
        connections.upsert({'connection_id':'codex-connection',
          'provider_id':'codex-fixture','purpose':'CODEX_EXECUTION','auth_type':'API_KEY',
          'destination_origin':'http://127.0.0.1:9','issuer':None,
          'authorization_endpoint':None,'token_endpoint':None,
          'revocation_endpoint':None,'redirect_uri':None,'client_id':None,
          'scopes':[],'supports_refresh':False},credential='fixture-credential')
        policy=ExecutionPolicyGateway(self.gateway,self.context)
        policy.record_unit({'task_id':'demo-b','delivery_stage':'implementation',
          'feature_unit':'codex-adapter','goal':'bounded fixture execution',
          'scope':['WRITE_SOURCE'],'acceptance':['tests'],
          'dependencies':['NONE'],'asset_version':'asset-v1',
          'responsible_party':'test-executor'})
        observed={'matches':[]};policy.record_asset_query('demo-b','query-1',
          'REGISTRY','registry-v1',{'lookup':{'asset':'asset-v1'},
          'observed_result':observed,'evidence_ref':'registry://query-1'},
          hashlib.sha256(canonical(observed).encode()).hexdigest())
        policy.record_dispatch_preflight('demo-b','asset-v1',['query-1'],
          'NOT_FOUND','verified TEST_ONLY gap')
        self.worker_context=self.authority.issue('tenant-a','test-executor')
        self.control=CodexExecutionControl(self.gateway,self.worker_context)
        self.context_body={'goal':'bounded fixture execution',
          'scope':['WRITE_SOURCE'],'acceptance':['tests'],
          'asset_version':'asset-v1','reuse_evidence':['query-1'],
          'connection_id':'codex-connection','provider_id':'codex-fixture'}

    def tearDown(self):
        self.fence.close();self.supervisor.close();shutil.rmtree(self.root)

    def test_persistent_intent_duplicate_send_and_restart_unknown(self):
        receipt=self.control.create_intent('demo-b','CODEX_SDK','idem-1',
          self.context_body)
        duplicate=self.control.create_intent('demo-b','CODEX_SDK','idem-1',
          self.context_body);self.assertTrue(duplicate['duplicate'])
        sent=[]
        transport=CodexSDKTransport(lambda intent:(sent.append(intent) or {
          'state':'ACKED','execution_id':'exec-1','session_id':'session-1'}))
        result=self.control.dispatch_once({'CODEX_SDK':transport})
        self.assertEqual(result['state'],'ACKED');self.assertEqual(len(sent),1)
        second=self.control.create_intent('demo-b','CODEX_APP_SERVER','idem-2',
          self.context_body)
        self.supervisor.db.execute('''UPDATE codex_execution_intents SET
          state='SENDING' WHERE intent_id=?''',(second['intent_id'],))
        self.supervisor.db.commit()
        self.assertEqual(self.control.reconcile_restart()['unknown_intents'],2)
        self.assertTrue(all(x['state']=='UNKNOWN' for x in self.control.projection()))

    def test_timeout_cancel_and_late_old_attempt_never_advance(self):
        unknown=self.control.create_intent('demo-b','CODEX_SDK','unknown',
          self.context_body)
        result=self.control.dispatch_once({'CODEX_SDK':CodexSDKTransport(
          lambda _intent:(_ for _ in ()).throw(CodexSendUnknown()))})
        self.assertEqual(result['state'],'UNKNOWN')
        cancelled=self.control.create_intent('demo-b','CODEX_SDK','cancel',
          self.context_body)
        self.assertEqual(self.control.cancel(cancelled['intent_id'])['state'],
          'CANCELLED')
        self.assertEqual(self.control.dispatch_once({'CODEX_SDK':CodexSDKTransport(
          lambda _intent:(_ for _ in ()).throw(AssertionError()))})['state'],'IDLE')
        self.supervisor.db.execute("""UPDATE tasks SET attempt_id='new-attempt',
          authority_caller_id='new-writer' WHERE task_id='demo-b'""")
        self.supervisor.db.commit()
        late=self.control.record_result(unknown['intent_id'],'late-1','SUCCEEDED',
          {'artifact_sha256':'a'*64})
        self.assertFalse(late['accepted'])
        row=self.supervisor.db.execute('''SELECT accepted FROM
          codex_execution_events WHERE event_id='late-1' ''').fetchone()
        self.assertEqual(row[0],0)

    def test_connection_and_malformed_receipt_after_send_are_unknown(self):
        for key,error in (('disconnect',ConnectionError('lost')),
                          ('malformed',None)):
            self.control.create_intent('demo-b','CODEX_SDK',key,
              self.context_body)
            if error is None:
                transport=CodexSDKTransport(lambda _intent:{'unexpected':True})
            else:
                transport=CodexSDKTransport(lambda _intent,e=error:(_ for _ in
                  ()).throw(e))
            result=self.control.dispatch_once({'CODEX_SDK':transport})
            self.assertEqual(result['state'],'UNKNOWN')

    def test_non_writer_cannot_cancel_codex_intent(self):
        intent=self.control.create_intent('demo-b','CODEX_SDK','owned',
          self.context_body)
        other=CodexExecutionControl(self.gateway,
          self.authority.issue('tenant-a','other-principal'))
        with self.assertRaisesRegex(ValueError,'CURRENT_CODEX_WRITER_REQUIRED'):
            other.cancel(intent['intent_id'])
        self.assertEqual(self.control.projection()[0]['state'],'PENDING')

    def test_unassigned_actor_and_noncanonical_scope_have_zero_intents(self):
        other=CodexExecutionControl(self.gateway,
          self.authority.issue('tenant-a','other-principal'))
        with self.assertRaisesRegex(ValueError,'ASSIGNED_CODEX_ACTOR'):
            other.create_intent('demo-b','CODEX_SDK','unassigned',
              self.context_body)
        changed=dict(self.context_body);changed['scope']=['DEPLOY']
        with self.assertRaisesRegex(ValueError,'CONTEXT_NOT_CANONICAL'):
            self.control.create_intent('demo-b','CODEX_SDK','bad-scope',changed)
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          codex_execution_intents''').fetchone()[0],0)

    def test_reviewer_assignment_never_authorizes_codex_transport(self):
        now=time.time()
        self.supervisor.db.execute('''INSERT INTO role_templates VALUES
          (?,?,?,?,?,?,?,?)''',('tenant-a','qa-review','v1','REVIEWER','["code"]',
          0,1,'QA'))
        self.supervisor.db.execute('''INSERT INTO model_assignments VALUES
          (?,?,?,?,?,?,?,?,?,?,?)''',('tenant-a','demo-b','attempt-b','qa-review',
          'v1','qa-principal','fixture','fixture','ASSIGNED','test',now))
        self.supervisor.db.commit()
        reviewer=CodexExecutionControl(self.gateway,
          self.authority.issue('tenant-a','qa-principal'))
        with self.assertRaisesRegex(ValueError,'ASSIGNED_CODEX_ACTOR'):
            reviewer.create_intent('demo-b','CODEX_SDK','reviewer-send',
              self.context_body)
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          codex_execution_intents''').fetchone()[0],0)

    def test_executor_role_revocation_after_intent_blocks_transport(self):
        now=time.time()
        self.supervisor.db.execute('''INSERT INTO role_templates VALUES
          (?,?,?,?,?,?,?,?)''',('tenant-a','codex-executor','v1','EXECUTOR',
          '["code"]',1,1,None))
        self.supervisor.db.execute('''INSERT INTO model_assignments VALUES
          (?,?,?,?,?,?,?,?,?,?,?)''',('tenant-a','demo-b','attempt-b',
          'codex-executor','v1','codex-principal','fixture','fixture','ASSIGNED',
          'test',now));self.supervisor.db.commit()
        executor=CodexExecutionControl(self.gateway,
          self.authority.issue('tenant-a','codex-principal'))
        executor.create_intent('demo-b','CODEX_SDK','executor-send',
          self.context_body)
        self.supervisor.db.execute('''UPDATE role_templates SET enabled=0 WHERE
          tenant_id='tenant-a' AND role_id='codex-executor' ''')
        self.supervisor.db.commit();calls=[]
        result=executor.dispatch_once({'CODEX_SDK':CodexSDKTransport(
          lambda intent:(calls.append(intent) or {'state':'ACKED'}))})
        self.assertEqual(result['state'],'FAILED');self.assertEqual(calls,[])
        self.assertEqual(executor.projection()[0]['requesting_principal'],
          'codex-principal')

    def test_acked_cancel_is_request_not_false_terminal(self):
        intent=self.control.create_intent('demo-b','CODEX_SDK','acked-cancel',
          self.context_body)
        self.assertEqual(self.control.dispatch_once({'CODEX_SDK':
          CodexSDKTransport(lambda _intent:{'state':'ACKED',
          'execution_id':'remote-exec'})})['state'],'ACKED')
        cancelled=self.control.cancel(intent['intent_id'])
        self.assertEqual(cancelled['state'],'CANCEL_REQUESTED')
        self.assertEqual(self.control.projection()[0]['state'],
          'CANCEL_REQUESTED')

    def test_app_server_receipt_and_event_idempotency(self):
        intent=self.control.create_intent('demo-b','CODEX_APP_SERVER','app-1',
          self.context_body)
        result=self.control.dispatch_once({'CODEX_APP_SERVER':
          CodexAppServerTransport(lambda _intent:{'state':'RUNNING',
          'execution_id':'exec-app','thread_id':'thr-1','turn_id':'turn-1'})})
        self.assertEqual(result['state'],'RUNNING')
        first=self.control.record_result(intent['intent_id'],'event-1',
          'WAITING_APPROVAL',{'approval':'owner'})
        replay=self.control.record_result(intent['intent_id'],'event-1',
          'WAITING_APPROVAL',{'approval':'owner'})
        self.assertTrue(first['accepted']);self.assertTrue(replay['duplicate'])
        with self.assertRaisesRegex(ValueError,'EVENT_ID_CONFLICT'):
            self.control.record_result(intent['intent_id'],'event-1','FAILED',{})

    def test_quota_rechecked_before_send_and_unknown_is_zero_call(self):
        intent=self.control.create_intent('demo-b','CODEX_SDK','quota-change',
          self.context_body);called=[]
        ModelControl(self.gateway,self.context,self.master).set_quota_status(
          'codex-fixture','UNKNOWN','UNKNOWN',verified_at=None,
          unavailable_reason='not verified')
        result=self.control.dispatch_once({'CODEX_SDK':CodexSDKTransport(
          lambda value:called.append(value))})
        self.assertEqual(result['state'],'FAILED');self.assertEqual(called,[])
        self.assertEqual(self.control.projection()[0]['error_kind'],
          'CODEX_CONNECTION_OR_QUOTA_HOLD')

    def test_available_but_not_included_or_free_quota_is_rejected(self):
        ModelControl(self.gateway,self.context,self.master).set_quota_status(
          'codex-fixture','AVAILABLE','METERED_API_ELIGIBLE',
          verified_at=time.time(),unavailable_reason=None)
        with self.assertRaisesRegex(ValueError,'QUOTA_UNKNOWN_OR_UNAVAILABLE'):
            self.control.create_intent('demo-b','CODEX_SDK','metered-disallowed',
              self.context_body)
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          codex_execution_intents''').fetchone()[0],0)

    def test_test_only_quota_on_known_paid_provider_is_rejected(self):
        self.supervisor.db.execute('''UPDATE model_providers SET
          price_state='KNOWN_PAID',config_version=config_version+1 WHERE
          tenant_id='tenant-a' AND provider_id='codex-fixture' ''')
        self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'QUOTA_UNKNOWN_OR_UNAVAILABLE'):
            self.control.create_intent('demo-b','CODEX_SDK','paid-provider',
              self.context_body)
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          codex_execution_intents''').fetchone()[0],0)

    def test_provider_change_after_queue_blocks_transport(self):
        self.control.create_intent('demo-b','CODEX_SDK','provider-change',
          self.context_body);called=[]
        self.supervisor.db.execute('''UPDATE model_providers SET enabled=0,
          config_version=config_version+1 WHERE tenant_id='tenant-a' AND
          provider_id='codex-fixture' ''')
        self.supervisor.db.commit()
        result=self.control.dispatch_once({'CODEX_SDK':CodexSDKTransport(
          lambda value:called.append(value))})
        self.assertEqual(result['state'],'FAILED');self.assertEqual(called,[])
        self.assertEqual(self.control.projection()[0]['error_kind'],
          'CODEX_CONNECTION_OR_QUOTA_HOLD')

    def test_cancel_during_send_keeps_late_ids_and_converges_cancelled(self):
        intent=self.control.create_intent('demo-b','CODEX_SDK','cancel-race',
          self.context_body)
        def sending(_value):
            self.control.cancel(intent['intent_id'])
            return {'state':'ACKED','execution_id':'exec-late','session_id':'sess-late',
              'thread_id':'thread-late','turn_id':'turn-late'}
        result=self.control.dispatch_once({'CODEX_SDK':CodexSDKTransport(sending)})
        self.assertEqual(result['state'],'CANCEL_REQUESTED')
        row=self.control.projection()[0];self.assertEqual(row['turn_id'],'turn-late')
        transport=CodexSDKTransport();transport.cancel=lambda _row:{
          'state':'CANCELLED','execution_id':'exec-late','session_id':'sess-late',
          'thread_id':'thread-late','turn_id':'turn-late'}
        settled=self.control.dispatch_cancel_once({'CODEX_SDK':transport})
        self.assertTrue(settled['accepted']);self.assertEqual(
          self.control.projection()[0]['state'],'CANCELLED')

    def test_concrete_app_server_stdio_protocol(self):
        intent=self.control.create_intent('demo-b','CODEX_APP_SERVER','stdio-app',
          self.context_body)
        fixture=("import sys,json\n"
          "for line in sys.stdin:\n"
          " v=json.loads(line)\n"
          " if 'id' not in v: continue\n"
          " m=v.get('method');r={}\n"
          " if m=='thread/start': r={'threadId':'fixture-thread'}\n"
          " elif m=='turn/start': r={'turnId':'fixture-turn'}\n"
          " elif m=='turn/interrupt': r={'cancelled':True}\n"
          " print(json.dumps({'jsonrpc':'2.0','id':v['id'],'result':r}),flush=True)\n")
        transport=CodexAppServerTransport(command=[sys.executable,'-u','-c',fixture])
        result=self.control.dispatch_once({'CODEX_APP_SERVER':transport})
        self.assertEqual(result['state'],'RUNNING')
        row=self.control.projection()[0]
        self.assertEqual((row['thread_id'],row['turn_id']),
          ('fixture-thread','fixture-turn'))
        proc=transport.processes['fixture-thread'];proc.terminate();proc.wait()
        proc.stdin.close();proc.stdout.close();proc.stderr.close()
        self.assertEqual(self.control.reconcile_restart()['unknown_intents'],1)
        resumed=CodexAppServerTransport(command=[sys.executable,'-u','-c',fixture])
        receipt=self.control.reconcile_transport_once({'CODEX_APP_SERVER':resumed})
        self.assertTrue(receipt['accepted']);self.assertEqual(
          self.control.projection()[0]['state'],'ACKED')
        proc=resumed.processes['fixture-thread'];proc.terminate();proc.wait()
        proc.stdin.close();proc.stdout.close();proc.stderr.close()

    def test_service_worker_dispatches_persisted_intent_without_client(self):
        intent=self.control.create_intent('demo-b','CODEX_SDK','worker-loop',
          self.context_body);called=threading.Event()
        transport=CodexSDKTransport(lambda _intent:(called.set() or {
          'state':'ACKED','execution_id':'worker-exec','session_id':'worker-session'}))
        worker=CodexWorkerLoop(self.db,KEY,'tenant-a',{'CODEX_SDK':transport},.05)
        worker.start();self.assertTrue(called.wait(2));worker.stop()
        row=self.supervisor.db.execute('''SELECT state,execution_id FROM
          codex_execution_intents WHERE intent_id=?''',(intent['intent_id'],)).fetchone()
        self.assertEqual(tuple(row),('ACKED','worker-exec'))


if __name__=='__main__':unittest.main()
