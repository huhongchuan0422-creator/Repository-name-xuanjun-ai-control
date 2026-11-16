from __future__ import print_function

import os
import shutil
import tempfile
import time
import unittest
import sys
import sqlite3
import hashlib
from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
from execution_policy_gateway import ExecutionPolicyGateway
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel,TestOnlyExecutor,TestTenantAuthority
from task_supervisor import Supervisor,canonical
from task_writer_fence import Fence
from model_orchestration import ModelControl

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
          'asset-v1','test-writer-attempt-b',source,['WRITE_SOURCE','DEPLOY'],
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
        self.policy.grant_approval_role('demo-b','independent-reviewer',
          'SCOPE_CHANGE',time.time()+600)
        with self.assertRaisesRegex(ValueError,'AUTHENTICATED_CHANGE'):
            reviewer.review_change('change-1','spoofed',True,'review')
        reviewer.review_change('change-1','independent-reviewer',True,'review')
        admitted=self.policy.request_action(self.action(action='DEPLOY',scope='DEPLOY',
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
        self.policy.grant_approval_role('demo-b','independent-reviewer',
          'SCOPE_CHANGE',time.time()+600)
        reviewer.review_change('wrong-base','independent-reviewer',True,'review')
        with self.assertRaisesRegex(ValueError,'CHANGE_BASE_ASSET_VERSION'):
            self.policy.request_action(self.action(action='DEPLOY',scope='DEPLOY',
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

    def test_idempotency_binds_authorization_writer_change_and_preflight(self):
        self.prepare();self.policy.request_action(self.action())
        now=time.time();self.policy.add_authorization('auth-2','demo-b','asset-v1',
          'test-writer-attempt-b','CURRENT_TEST_ONLY',['WRITE_SOURCE'],False,
          now-1,now+60,'auth-2-evidence')
        with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):
            self.policy.request_action(self.action(authorization_id='auth-2'))

    def test_old_attempt_preflight_and_change_cannot_be_reused(self):
        self.prepare();self.supervisor.db.execute("""UPDATE asset_preflight_checks
          SET attempt_id='old-attempt'""");self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'PREFLIGHT_ATTEMPT'):
            self.policy.request_action(self.action())
        self.supervisor.db.execute("""UPDATE asset_preflight_checks SET
          attempt_id='attempt-b'""");self.supervisor.db.commit()
        self.policy.propose_change('old-change','demo-b','asset-v1',['DEPLOY'],'x')
        reviewer=ExecutionPolicyGateway(self.gateway,
          self.authority.issue('tenant-a','independent-reviewer'))
        self.policy.grant_approval_role('demo-b','independent-reviewer',
          'SCOPE_CHANGE',time.time()+600)
        reviewer.review_change('old-change','independent-reviewer',True,'review')
        self.supervisor.db.execute("""UPDATE scope_changes SET
          attempt_id='old-attempt'""");self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'CHANGE_ATTEMPT'):
            self.policy.request_action(self.action(action='DEPLOY',scope='DEPLOY',change_id='old-change'))

    def test_same_preflight_body_can_be_recorded_for_new_attempt(self):
        self.policy.record_unit(self.unit)
        first=self.policy.record_preflight('demo-b',['registry'],'FOUND',
          'existing-source','asset-v1',False,'reuse checked','evidence')
        self.supervisor.db.execute('''UPDATE tasks SET attempt_id=?,
          authority_caller_id=? WHERE task_id='demo-b' ''',(
          'attempt-b-2','test-writer-attempt-b-2'))
        self.supervisor.db.commit()
        second=self.policy.record_preflight('demo-b',['registry'],'FOUND',
          'existing-source','asset-v1',False,'reuse checked','evidence')
        self.assertNotEqual(first['check_id'],second['check_id'])
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          asset_preflight_checks WHERE task_id='demo-b' ''').fetchone()[0],2)

    def test_executor_role_cannot_approve_scope_change(self):
        self.prepare();self.policy.propose_change('role-change','demo-b',
          'asset-v1',['DEPLOY'],'x')
        ModelControl(self.gateway,self.context,Fernet.generate_key())
        self.supervisor.db.execute('''INSERT INTO role_templates(
          tenant_id,role_id,version,phase,capabilities_json,writer_allowed,
          enabled,review_kind) VALUES (?,?,?,?,?,?,?,?)''',(
          'tenant-a','developer','v1','EXECUTOR','["code"]',1,1,None))
        self.supervisor.db.execute('''INSERT INTO model_assignments VALUES
          (?,?,?,?,?,?,?,?,?,?,?)''',('tenant-a','demo-b','attempt-b','developer',
          'v1','developer-1','p','m','ACTIVE','test',time.time()))
        self.supervisor.db.commit()
        self.policy.grant_approval_role('demo-b','developer-1',
          'SCOPE_CHANGE',time.time()+600)
        developer=ExecutionPolicyGateway(self.gateway,
          self.authority.issue('tenant-a','developer-1'))
        with self.assertRaisesRegex(ValueError,'INDEPENDENT_CHANGE_REVIEW'):
            developer.review_change('role-change','developer-1',True,'review')

    def test_scope_approval_invalidates_if_reviewer_later_becomes_executor(self):
        self.prepare();self.policy.propose_change('later-executor','demo-b',
          'asset-v1',['DEPLOY'],'x')
        ModelControl(self.gateway,self.context,Fernet.generate_key())
        reviewer=ExecutionPolicyGateway(self.gateway,
          self.authority.issue('tenant-a','developer-later'))
        self.policy.grant_approval_role('demo-b','developer-later',
          'SCOPE_CHANGE',time.time()+600)
        reviewer.review_change('later-executor','developer-later',True,'review')
        self.supervisor.db.execute('''INSERT INTO role_templates(
          tenant_id,role_id,version,phase,capabilities_json,writer_allowed,
          enabled,review_kind) VALUES (?,?,?,?,?,?,?,?)''',(
          'tenant-a','developer','v1','EXECUTOR','["code"]',1,1,None))
        self.supervisor.db.execute('''INSERT INTO model_assignments VALUES
          (?,?,?,?,?,?,?,?,?,?,?)''',('tenant-a','demo-b','attempt-b','developer',
          'v1','developer-later','p','m','ACTIVE','test',time.time()))
        self.supervisor.db.commit()
        with self.assertRaisesRegex(ValueError,'CHANGE_REVIEWER_ROLE_CONFLICT'):
            self.policy.request_action(self.action(action='DEPLOY',scope='DEPLOY',
              change_id='later-executor'))

    def test_scope_reviewer_role_check_and_action_insert_are_atomic(self):
        self.prepare();self.policy.propose_change('atomic-change','demo-b',
          'asset-v1',['DEPLOY'],'x')
        ModelControl(self.gateway,self.context,Fernet.generate_key())
        reviewer=ExecutionPolicyGateway(self.gateway,
          self.authority.issue('tenant-a','atomic-reviewer'))
        self.policy.grant_approval_role('demo-b','atomic-reviewer',
          'SCOPE_CHANGE',time.time()+600)
        reviewer.review_change('atomic-change','atomic-reviewer',True,'review')
        self.supervisor.db.execute('''INSERT INTO role_templates(
          tenant_id,role_id,version,phase,capabilities_json,writer_allowed,
          enabled,review_kind) VALUES (?,?,?,?,?,?,?,?)''',(
          'tenant-a','developer','v1','EXECUTOR','["code"]',1,1,None))
        self.supervisor.db.commit();blocked=[]
        def authorizer(action,table,*_args):
            if action==sqlite3.SQLITE_INSERT and table=='execution_action_requests':
                other=sqlite3.connect(self.db,timeout=0)
                try:
                    other.execute('''INSERT INTO model_assignments VALUES
                      (?,?,?,?,?,?,?,?,?,?,?)''',('tenant-a','demo-b','attempt-b',
                      'developer','v1','atomic-reviewer','p','m','ACTIVE','test',
                      time.time()));other.commit()
                except sqlite3.OperationalError as exc:blocked.append(str(exc))
                finally:other.close()
            return sqlite3.SQLITE_OK
        self.supervisor.db.set_authorizer(authorizer)
        try:
            result=self.policy.request_action(self.action(action='DEPLOY',scope='DEPLOY',
              change_id='atomic-change'))
        finally:self.supervisor.db.set_authorizer(None)
        self.assertEqual(result['state'],'ADMITTED_TEST_ONLY')
        self.assertTrue(any('locked' in value for value in blocked),blocked)
        verify=sqlite3.connect(self.db)
        try:self.assertEqual(verify.execute('''SELECT COUNT(*) FROM
          model_assignments WHERE principal_id='atomic-reviewer' ''').fetchone()[0],0)
        finally:verify.close()

    def test_accepted_request_never_claims_external_execution(self):
        self.prepare();result=self.policy.request_action(self.action())
        self.assertEqual(result['external_execution'],'NOT_EXECUTED')
        projected=self.policy.projection()
        self.assertEqual(projected['external_execution'],'NOT_IMPLEMENTED')

    def test_action_scope_disguise_is_rejected_without_side_effect(self):
        self.prepare();before=self.supervisor.db.execute(
          'SELECT COUNT(*) FROM execution_action_requests').fetchone()[0]
        with self.assertRaisesRegex(ValueError,'ACTION_SCOPE_MISMATCH'):
            self.policy.request_action(self.action(action='DEPLOY',
              scope='WRITE_SOURCE'))
        self.assertEqual(self.supervisor.db.execute(
          'SELECT COUNT(*) FROM execution_action_requests').fetchone()[0],before)

    def test_unassigned_subject_cannot_approve_scope_change(self):
        self.prepare();self.policy.propose_change('formal-role','demo-b',
          'asset-v1',['DEPLOY'],'x')
        reviewer=ExecutionPolicyGateway(self.gateway,
          self.authority.issue('tenant-a','authenticated-but-unassigned'))
        with self.assertRaisesRegex(ValueError,'FORMAL_APPROVAL_ROLE'):
            reviewer.review_change('formal-role','authenticated-but-unassigned',
              True,'review')

    def test_expired_writer_blocks_valid_action_authorization(self):
        self.prepare();self.supervisor.db.execute('''UPDATE tasks SET
          authority_valid_until=? WHERE task_id='demo-b' ''',(time.time()-1,))
        self.supervisor.db.commit();before=self.supervisor.db.execute(
          'SELECT COUNT(*) FROM execution_action_requests').fetchone()[0]
        with self.assertRaisesRegex(ValueError,'WRITER_AUTHORITY_EXPIRED'):
            self.policy.request_action(self.action())
        self.assertEqual(self.supervisor.db.execute(
          'SELECT COUNT(*) FROM execution_action_requests').fetchone()[0],before)

    def test_preflight_can_bind_real_query_receipt_and_reject_unknown_id(self):
        self.policy.record_unit(self.unit)
        observed={'found':['existing-source']}
        self.policy.upsert_canonical_asset('existing-source','registry-v3',observed)
        self.policy.record_asset_query('demo-b','query-1','CANONICAL_DB','registry-v3',
          {'lookup':{'asset_key':'existing-source'},'observed_result':observed,
          'evidence_ref':'canonical-db://existing-source@registry-v3'},hashlib.sha256(
          canonical(observed).encode()).hexdigest())
        forged={'found':['forged']}
        with self.assertRaisesRegex(ValueError,'NOT_FROM_CANONICAL_SOURCE'):
            self.policy.record_asset_query('demo-b','forged','CANONICAL_DB','registry-v3',
              {'lookup':{'asset_key':'existing-source'},'observed_result':forged,
              'evidence_ref':'canonical-db://existing-source@registry-v3'},hashlib.sha256(
              canonical(forged).encode()).hexdigest())
        receipt=self.policy.record_preflight('demo-b',['registry'],'FOUND',
          'existing-source','asset-v1',False,'reuse checked','evidence',
          query_ids=['query-1'])
        self.assertTrue(receipt['check_id'])
        with self.assertRaisesRegex(ValueError,'QUERY_RECEIPT'):
            self.policy.record_preflight('demo-b',['registry'],'FOUND',
              'existing-source','asset-v1',False,'reuse checked','evidence',
              query_ids=['missing'])

    def test_dispatch_outcome_must_match_trusted_query_result(self):
        self.policy.record_unit(self.unit)
        found={'matches':[{'asset_key':'existing-source'}]}
        self.policy.upsert_canonical_asset('existing-source','registry-v4',found)
        self.policy.record_asset_query('demo-b','found-query','CANONICAL_DB','registry-v4',
          {'lookup':{'asset_key':'existing-source'},'observed_result':found,
          'evidence_ref':'canonical-db://existing-source@registry-v4'},hashlib.sha256(
          canonical(found).encode()).hexdigest())
        missing={'matches':[]}
        self.policy.record_asset_query('demo-b','missing-query','CANONICAL_DB','registry-v4',
          {'lookup':{'asset_key':'missing-source'},'observed_result':missing,
          'evidence_ref':'canonical-db://missing-source@registry-v4'},hashlib.sha256(
          canonical(missing).encode()).hexdigest())
        with self.assertRaisesRegex(ValueError,'OUTCOME_MISMATCH'):
            self.policy.record_dispatch_preflight('demo-b','asset-v1',['found-query'],
              'NOT_FOUND','caller contradicted found result')
        with self.assertRaisesRegex(ValueError,'OUTCOME_MISMATCH'):
            self.policy.record_dispatch_preflight('demo-b','asset-v1',['missing-query'],
              'FOUND','caller contradicted empty result')
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          dispatch_preflights WHERE task_id='demo-b' ''').fetchone()[0],0)


if __name__=='__main__':unittest.main()
