from __future__ import print_function

import os
import shutil
import tempfile
import time
import unittest
import sys

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
from execution_policy_gateway import ExecutionPolicyGateway
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel,TestOnlyExecutor,TestTenantAuthority
from task_supervisor import Supervisor
from task_writer_fence import Fence

KEY=b'0123456789abcdef0123456789abcdef'


class ExecutionPolicyGatewayTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        self.supervisor=Supervisor(self.db);self.authority=TestTenantAuthority(KEY)
        self.gateway=GatewayKernel(self.supervisor,self.authority)
        self.context=self.authority.issue('tenant-a','admin:owner')
        self.gateway.register_graph(self.context,demo_graph('tenant-a'))
        self.fence=Fence(self.supervisor,os.path.join(self.root,'locks'))
        self.executor=TestOnlyExecutor(self.gateway,self.fence,self.context)
        self.executor.start('demo-b','attempt-b',['fake:demo-b'],time.time()+600)
        self.policy=ExecutionPolicyGateway(self.gateway,self.context)
        self.unit={'task_id':'demo-b','delivery_stage':'implementation',
          'feature_unit':'small-function','goal':'deliver verified patch',
          'scope':['WRITE_SOURCE'],'acceptance':['tests','independent-review'],
          'dependencies':['demo-a'],'asset_version':'asset-v1',
          'responsible_party':'test-executor'}

    def tearDown(self):
        self.fence.close();self.supervisor.close();shutil.rmtree(self.root)

    def prepare(self,outcome='FOUND',source='CURRENT_TEST_ONLY',read_only=False,
                valid_until=None):
        self.policy.record_unit(self.unit)
        self.policy.record_preflight('demo-b',['registry','source'],'FOUND' if outcome=='FOUND' else outcome,
          'existing-source' if outcome=='FOUND' else None,
          'asset-v1' if outcome=='FOUND' else None,False,'reuse checked',
          'preflight-evidence')
        now=time.time();self.policy.add_authorization('auth-1','demo-b',
          'asset-v1','test-writer-attempt-b',source,['WRITE_SOURCE'],
          read_only,now-1,valid_until or now+600,'auth-evidence')

    def action(self,**changes):
        value={'task_id':'demo-b','asset_version':'asset-v1',
          'action':'WRITE_SOURCE','scope':'WRITE_SOURCE',
          'authorization_id':'auth-1','writer_principal':'test-writer-attempt-b',
          'idempotency_key':'action-1','change_id':None}
        value.update(changes);return value

    def test_missing_goal_or_acceptance_is_rejected(self):
        invalid=dict(self.unit);invalid['goal']=''
        with self.assertRaisesRegex(ValueError,'GOAL'):
            self.policy.record_unit(invalid)
        invalid=dict(self.unit);invalid['acceptance']=[]
        with self.assertRaisesRegex(ValueError,'ACCEPTANCE'):
            self.policy.record_unit(invalid)

    def test_cross_tenant_action_is_rejected_without_writes(self):
        self.prepare();other=ExecutionPolicyGateway(self.gateway,
          self.authority.issue('tenant-b','admin:other'))
        before=self.supervisor.db.execute('SELECT COUNT(*) FROM execution_action_requests').fetchone()[0]
        with self.assertRaisesRegex(ValueError,'CROSS_TENANT'):
            other.request_action(self.action())
        after=self.supervisor.db.execute('SELECT COUNT(*) FROM execution_action_requests').fetchone()[0]
        self.assertEqual(before,after)

    def test_expired_authorization_is_not_current_permission(self):
        self.prepare(valid_until=time.time()-.1)
        with self.assertRaisesRegex(ValueError,'EXPIRED'):
            self.policy.request_action(self.action())

    def test_historical_or_read_only_capability_cannot_authorize_write(self):
        self.prepare(source='HISTORICAL')
        with self.assertRaisesRegex(ValueError,'CURRENT_WRITE'):
            self.policy.request_action(self.action())
        self.supervisor.db.execute("UPDATE action_authorizations SET source_kind='CURRENT_TEST_ONLY',read_only=1")
        self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'CURRENT_WRITE'):
            self.policy.request_action(self.action())

    def test_unknown_asset_state_cannot_be_new_or_admitted(self):
        with self.assertRaisesRegex(ValueError,'UNKNOWN_CANNOT'):
            self.policy.record_preflight('demo-b',['registry'],'UNKNOWN',None,
              None,True,'unknown','evidence')
        self.policy.record_unit(self.unit)
        self.policy.record_preflight('demo-b',['registry'],'UNKNOWN',None,None,
          False,'unknown','evidence')
        now=time.time();self.policy.add_authorization('auth-1','demo-b',
          'asset-v1','test-writer-attempt-b','CURRENT_TEST_ONLY',
          ['WRITE_SOURCE'],False,
          now-1,now+60,'evidence')
        with self.assertRaisesRegex(ValueError,'UNKNOWN_ASSET'):
            self.policy.request_action(self.action())

    def test_wrong_writer_and_wrong_asset_version_are_rejected(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError,'UNIQUE_WRITER'):
            self.policy.request_action(self.action(writer_principal='other'))
        with self.assertRaisesRegex(ValueError,'ASSET_VERSION_MISMATCH'):
            self.policy.request_action(self.action(asset_version='asset-v2'))

    def test_unapproved_scope_expansion_and_self_review_are_rejected(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError,'UNAPPROVED_SCOPE'):
            self.policy.request_action(self.action(scope='DEPLOY'))
        self.policy.propose_change('change-1','demo-b','asset-v1',['DEPLOY'],
          'owner requested')
        reviewer=ExecutionPolicyGateway(self.gateway,
          self.authority.issue('tenant-a','independent-reviewer'))
        with self.assertRaisesRegex(ValueError,'AUTHENTICATED_CHANGE'):
            reviewer.review_change('change-1','spoofed',True,'review')
        reviewer.review_change('change-1','independent-reviewer',True,'review')
        admitted=self.policy.request_action(self.action(scope='DEPLOY',
          change_id='change-1'))
        self.assertEqual(admitted['state'],'ADMITTED_TEST_ONLY')

    def test_preflight_change_and_authorization_bind_exact_asset_generation(self):
        self.prepare()
        self.supervisor.db.execute("""UPDATE asset_preflight_checks SET
          reused_version='asset-v0'""");self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'PREFLIGHT_ASSET_VERSION'):
            self.policy.request_action(self.action())
        self.supervisor.db.execute("""UPDATE asset_preflight_checks SET
          reused_version='asset-v1'""")
        self.supervisor.db.execute("""UPDATE action_authorizations SET
          attempt_id='stale-attempt'""");self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'AUTHORIZATION_BINDING'):
            self.policy.request_action(self.action())

    def test_scope_change_wrong_base_version_never_authorizes(self):
        self.prepare();self.policy.propose_change('wrong-base','demo-b',
          'asset-v0',['DEPLOY'],'wrong base')
        reviewer=ExecutionPolicyGateway(self.gateway,
          self.authority.issue('tenant-a','independent-reviewer'))
        reviewer.review_change('wrong-base','independent-reviewer',True,'review')
        with self.assertRaisesRegex(ValueError,'CHANGE_BASE_ASSET_VERSION'):
            self.policy.request_action(self.action(scope='DEPLOY',
              change_id='wrong-base'))

    def test_duplicate_and_restart_are_idempotent_not_reexecuted(self):
        self.prepare();first=self.policy.request_action(self.action())
        self.assertFalse(first['duplicate'])
        self.supervisor.close();self.supervisor=Supervisor(self.db)
        self.gateway=GatewayKernel(self.supervisor,self.authority)
        reopened=ExecutionPolicyGateway(self.gateway,self.context)
        duplicate=reopened.request_action(self.action())
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          execution_action_requests''').fetchone()[0],1)

    def test_accepted_request_never_claims_external_execution(self):
        self.prepare();result=self.policy.request_action(self.action())
        self.assertEqual(result['external_execution'],'NOT_EXECUTED')
        projected=self.policy.projection()
        self.assertEqual(projected['external_execution'],'NOT_IMPLEMENTED')


if __name__=='__main__':unittest.main()
