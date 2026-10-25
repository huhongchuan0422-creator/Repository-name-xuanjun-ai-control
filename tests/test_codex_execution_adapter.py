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
          'CANONICAL_DB','registry-v1',{'lookup':{'asset_key':'asset-v1'},
          'observed_result':observed,
          'evidence_ref':'canonical-db://asset-v1@registry-v1'},
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
        event={'approval':'owner','thread_id':'thr-1','turn_id':'turn-1'}
        first=self.control.record_result(intent['intent_id'],'event-1',
          'WAITING_APPROVAL',event)
        replay=self.control.record_result(intent['intent_id'],'event-1',
          'WAITING_APPROVAL',event)
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
          " if m=='thread/start': r={'thread':{'id':'fixture-thread','sessionId':'fixture-session'}}\n"
          " elif m=='turn/start': r={'turn':{'id':'fixture-turn','status':'inProgress','items':[]}}\n"
          " elif m=='thread/resume': r={'thread':{'id':'fixture-thread','status':{'type':'active'}}}\n"
          " elif m=='thread/turns/list': r={'data':[{'id':'fixture-turn','status':'inProgress'}]}\n"
          " elif m=='turn/interrupt': r={'cancelled':True}\n"
          " print(json.dumps({'jsonrpc':'2.0','id':v['id'],'result':r}),flush=True)\n")
        transport=CodexAppServerTransport(command=[sys.executable,'-u','-c',fixture])
        result=self.control.dispatch_once({'CODEX_APP_SERVER':transport})
        self.assertEqual(result['state'],'RUNNING')
        row=self.control.projection()[0]
        self.assertEqual((row['session_id'],row['thread_id'],row['turn_id']),
          ('fixture-session','fixture-thread','fixture-turn'))
        proc=transport.processes['fixture-thread'];proc.terminate();proc.wait()
        proc.stdin.close();proc.stdout.close();proc.stderr.close()
        self.assertEqual(self.control.reconcile_restart()['unknown_intents'],1)
        resumed=CodexAppServerTransport(command=[sys.executable,'-u','-c',fixture])
        receipt=self.control.reconcile_transport_once({'CODEX_APP_SERVER':resumed})
        self.assertTrue(receipt['accepted']);self.assertEqual(
          self.control.projection()[0]['state'],'RUNNING')
        proc=resumed.processes['fixture-thread'];proc.terminate();proc.wait()
        proc.stdin.close();proc.stdout.close();proc.stderr.close()

    def test_app_server_interleaved_notifications_approval_terminal_and_cancel(self):
        fixture=("import sys,json\n"
          "for line in sys.stdin:\n"
          " v=json.loads(line);m=v.get('method')\n"
          " if 'id' not in v: continue\n"
          " if m=='initialize':\n"
          "  print(json.dumps({'jsonrpc':'2.0','method':'warning','params':{'message':'fixture'}}),flush=True);r={}\n"
          " elif m=='thread/start': r={'thread':{'id':'nested-thread','sessionId':'nested-session'}}\n"
          " elif m=='turn/start': r={'turn':{'id':'nested-turn','status':'inProgress','items':[]}}\n"
          " elif m=='turn/interrupt': r={}\n"
          " else: r={}\n"
          " print(json.dumps({'jsonrpc':'2.0','id':v['id'],'result':r}),flush=True)\n"
          " if m=='turn/start':\n"
          "  print(json.dumps({'jsonrpc':'2.0','id':901,'method':'item/commandExecution/requestApproval','params':{'threadId':'nested-thread','turnId':'nested-turn','itemId':'cmd-1'}}),flush=True)\n"
          " if m=='turn/interrupt':\n"
          "  print(json.dumps({'jsonrpc':'2.0','method':'turn/completed','params':{'turn':{'id':'nested-turn','status':'interrupted','items':[]}}}),flush=True)\n")
        transport=CodexAppServerTransport(command=[sys.executable,'-u','-c',fixture])
        intent=self.control.create_intent('demo-b','CODEX_APP_SERVER','events',
          self.context_body)
        self.assertEqual(self.control.dispatch_once({'CODEX_APP_SERVER':transport})[
          'state'],'RUNNING')
        approval=self.control.poll_transport_once({'CODEX_APP_SERVER':transport})
        self.assertEqual(approval['state'],'WAITING_APPROVAL')
        self.control.cancel(intent['intent_id'])
        requested=self.control.dispatch_cancel_once({'CODEX_APP_SERVER':transport})
        self.assertEqual(requested['state'],'CANCEL_REQUESTED')
        terminal=self.control.poll_transport_once({'CODEX_APP_SERVER':transport})
        self.assertTrue(terminal['accepted']);self.assertEqual(
          self.control.projection()[0]['state'],'CANCELLED')
        proc=transport.processes['nested-thread'];proc.terminate();proc.wait()
        proc.stdin.close();proc.stdout.close();proc.stderr.close()

    def test_app_server_restart_reconciles_completed_turn_without_business_acceptance(self):
        intent=self.control.create_intent('demo-b','CODEX_APP_SERVER','completed-restart',
          self.context_body)
        self.control.dispatch_once({'CODEX_APP_SERVER':CodexAppServerTransport(
          lambda _intent:{'state':'RUNNING','execution_id':'turn-done',
          'session_id':'session-done','thread_id':'thread-done','turn_id':'turn-done'})})
        self.assertEqual(self.control.reconcile_restart()['unknown_intents'],1)
        fixture=("import sys,json\n"
          "for line in sys.stdin:\n"
          " v=json.loads(line)\n"
          " if 'id' not in v: continue\n"
          " m=v.get('method');r={}\n"
          " if m=='thread/resume': r={'thread':{'id':'thread-done','status':{'type':'idle'}}}\n"
          " elif m=='thread/turns/list': r={'data':[{'id':'turn-done','status':'completed','items':[]}]}\n"
          " print(json.dumps({'jsonrpc':'2.0','id':v['id'],'result':r}),flush=True)\n")
        transport=CodexAppServerTransport(command=[sys.executable,'-u','-c',fixture])
        result=self.control.reconcile_transport_once({'CODEX_APP_SERVER':transport})
        self.assertTrue(result['accepted']);self.assertEqual(
          self.control.projection()[0]['state'],'EXECUTION_COMPLETED')
        self.assertIsNone(self.control.projection()[0]['artifact_sha256'])
        proc=transport.processes['thread-done'];proc.terminate();proc.wait()
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

    def test_poll_skips_silent_first_intent_and_consumes_second_terminal(self):
        first=self.control.create_intent('demo-b','CODEX_APP_SERVER','silent-first',
          self.context_body)
        second=self.control.create_intent('demo-b','CODEX_APP_SERVER','done-second',
          self.context_body)
        counter=[0]
        def send(_intent):
            counter[0]+=1;number=counter[0]
            return {'state':'RUNNING','execution_id':'turn-%s'%number,
              'session_id':'session-%s'%number,'thread_id':'thread-%s'%number,
              'turn_id':'turn-%s'%number}
        transport=CodexAppServerTransport(send)
        self.control.dispatch_once({'CODEX_APP_SERVER':transport})
        self.control.dispatch_once({'CODEX_APP_SERVER':transport})
        class Poller(object):
            def poll(self,row,_timeout):
                if row['intent_id']==first['intent_id']:return None
                return {'state':'EXECUTION_COMPLETED','thread_id':'thread-2',
                  'turn_id':'turn-2'}
        result=self.control.poll_transport_once({'CODEX_APP_SERVER':Poller()})
        self.assertTrue(result['accepted'])
        states={x['intent_id']:x['state'] for x in self.control.projection()}
        self.assertEqual(states[first['intent_id']],'RUNNING')
        self.assertEqual(states[second['intent_id']],'EXECUTION_COMPLETED')

    def test_wrong_thread_and_old_turn_events_are_historical_only(self):
        intent=self.control.create_intent('demo-b','CODEX_APP_SERVER','identity-events',
          self.context_body)
        self.control.dispatch_once({'CODEX_APP_SERVER':CodexAppServerTransport(
          lambda _intent:{'state':'RUNNING','thread_id':'thread-current',
          'turn_id':'turn-current','execution_id':'turn-current'})})
        wrong=self.control.record_result(intent['intent_id'],'wrong-thread',
          'WAITING_APPROVAL',{'thread_id':'thread-other','turn_id':'turn-current'})
        old=self.control.record_result(intent['intent_id'],'old-turn',
          'EXECUTION_COMPLETED',{'thread_id':'thread-current','turn_id':'turn-old'})
        self.assertFalse(wrong['accepted']);self.assertFalse(old['accepted'])
        self.assertEqual(self.control.projection()[0]['state'],'RUNNING')
        self.assertEqual(self.supervisor.db.execute('''SELECT SUM(accepted) FROM
          codex_execution_events WHERE event_id IN ('wrong-thread','old-turn')''').fetchone()[0],0)

    def test_cancel_requested_survives_restart_and_reconciles_same_turn(self):
        intent=self.control.create_intent('demo-b','CODEX_APP_SERVER','cancel-restart',
          self.context_body)
        self.control.dispatch_once({'CODEX_APP_SERVER':CodexAppServerTransport(
          lambda _intent:{'state':'RUNNING','thread_id':'thread-cancel',
          'turn_id':'turn-cancel','execution_id':'turn-cancel'})})
        self.control.cancel(intent['intent_id'])
        self.control.reconcile_restart()
        self.assertEqual(self.control.projection()[0]['state'],'CANCEL_REQUESTED')
        class Reconciler(object):
            def reconcile(self,row):
                self.row=row
                return {'state':'CANCEL_REQUESTED','thread_id':'thread-cancel',
                  'turn_id':'turn-cancel'}
            def poll(self,row,_timeout):
                return {'state':'CANCELLED','thread_id':'thread-cancel',
                  'turn_id':'turn-cancel'}
        transport=Reconciler()
        recovered=self.control.reconcile_transport_once({'CODEX_APP_SERVER':transport})
        self.assertTrue(recovered['accepted'])
        self.assertEqual(transport.row['turn_id'],'turn-cancel')
        settled=self.control.poll_transport_once({'CODEX_APP_SERVER':transport})
        self.assertTrue(settled['accepted'])
        self.assertEqual(self.control.projection()[0]['state'],'CANCELLED')

    def test_app_server_reconcile_pages_to_exact_turn_and_absence_is_unknown(self):
        intent=self.control.create_intent('demo-b','CODEX_APP_SERVER','paged-turn',
          self.context_body)
        self.control.dispatch_once({'CODEX_APP_SERVER':CodexAppServerTransport(
          lambda _intent:{'state':'RUNNING','thread_id':'thread-page',
          'turn_id':'target-turn','execution_id':'target-turn'})})
        self.control.reconcile_restart()
        fixture=("import sys,json\n"
          "for line in sys.stdin:\n"
          " v=json.loads(line)\n"
          " if 'id' not in v: continue\n"
          " m=v.get('method');p=v.get('params') or {};r={}\n"
          " if m=='thread/resume': r={'thread':{'id':'thread-page','status':{'type':'active'}}}\n"
          " elif m=='thread/turns/list':\n"
          "  if not p.get('cursor'): r={'data':[{'id':'other-%d'%i,'status':'inProgress'} for i in range(50)],'nextCursor':'page-2'}\n"
          "  else: r={'data':[{'id':'target-turn','status':'completed','items':[]}]}\n"
          " print(json.dumps({'jsonrpc':'2.0','id':v['id'],'result':r}),flush=True)\n")
        transport=CodexAppServerTransport(command=[sys.executable,'-u','-c',fixture])
        result=self.control.reconcile_transport_once({'CODEX_APP_SERVER':transport})
        self.assertTrue(result['accepted'])
        self.assertEqual(self.control.projection()[0]['state'],'EXECUTION_COMPLETED')
        proc=transport.processes['thread-page'];proc.terminate();proc.wait()
        proc.stdin.close();proc.stdout.close();proc.stderr.close()

    def test_app_server_turn_receipt_rejects_other_identity(self):
        intent={'thread_id':'thread-current','turn_id':'turn-current'}
        self.assertIsNone(CodexAppServerTransport._turn_receipt({'method':'turn/completed',
          'params':{'threadId':'thread-current','turn':{'id':'turn-old',
          'status':'completed'}}},intent))
        self.assertIsNone(CodexAppServerTransport._turn_receipt({'id':9,
          'method':'item/commandExecution/requestApproval','params':{
          'threadId':'thread-other','turnId':'turn-current'}},intent))


if __name__=='__main__':unittest.main()
