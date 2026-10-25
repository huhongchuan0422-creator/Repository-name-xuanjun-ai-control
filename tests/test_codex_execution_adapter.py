from __future__ import print_function

import json
import os
import shutil
import tempfile
import time
import unittest
from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
import sys;sys.path.insert(0,os.path.join(ROOT,'scripts'))
from codex_execution_adapter import (CodexExecutionControl,CodexSDKTransport,
  CodexAppServerTransport,CodexSendUnknown)
from execution_policy_gateway import ExecutionPolicyGateway
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel,TestOnlyExecutor,TestTenantAuthority
from task_supervisor import Supervisor
from task_writer_fence import Fence
from model_orchestration import ModelControl

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
        ModelControl(self.gateway,self.context,Fernet.generate_key()).record_task_spec(
          'demo-b','bounded fixture execution',['artifact'],['tests'])
        policy=ExecutionPolicyGateway(self.gateway,self.context)
        policy.record_unit({'task_id':'demo-b','delivery_stage':'implementation',
          'feature_unit':'codex-adapter','goal':'bounded fixture execution',
          'scope':['WRITE_SOURCE'],'acceptance':['tests'],
          'dependencies':['NONE'],'asset_version':'asset-v1',
          'responsible_party':'test-executor'})
        policy.record_asset_query('demo-b','query-1','REGISTRY','registry-v1',
          {'asset':'asset-v1'},'e'*64)
        policy.record_dispatch_preflight('demo-b','asset-v1',['query-1'],
          'NOT_FOUND','verified TEST_ONLY gap')
        self.worker_context=self.authority.issue('tenant-a','test-executor')
        self.control=CodexExecutionControl(self.gateway,self.worker_context)
        self.context_body={'goal':'bounded fixture execution',
          'scope':['WRITE_SOURCE'],'acceptance':['tests'],
          'asset_version':'asset-v1','reuse_evidence':['query-1']}

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
        self.assertEqual(self.control.reconcile_restart()['unknown_intents'],1)
        self.assertEqual(self.control.projection()[1]['state'],'UNKNOWN')

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

    def test_non_writer_cannot_cancel_codex_intent(self):
        intent=self.control.create_intent('demo-b','CODEX_SDK','owned',
          self.context_body)
        other=CodexExecutionControl(self.gateway,
          self.authority.issue('tenant-a','other-principal'))
        with self.assertRaisesRegex(ValueError,'CURRENT_CODEX_WRITER_REQUIRED'):
            other.cancel(intent['intent_id'])
        self.assertEqual(self.control.projection()[0]['state'],'PENDING')

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


if __name__=='__main__':unittest.main()
