"""Real original Center/SQLite admin composition, without provider/Finance calls."""
import json
import unittest
import test_community_center_saas as fixture
from scripts.community_center_saas import CenterSaas
from scripts.community_saas_offline_handoff import create_review


class AdminComposition(unittest.TestCase):
    def setUp(self):
        self.base=fixture.CustomerSaas();self.base.setUp()
        self.fx=self.base.fx
        self.grants=dict(self.base.grants,owner=dict(user_id=self.fx.uid1,project='project1',principal=self.fx.stage.owner))
        self.api=CenterSaas(self.fx.center,self.fx.stage.api,self.grants)
    def tearDown(self):self.base.tearDown()
    def call(self,operation,params=None,workspace='owner'):
        return self.api.dispatch(self.base.one['token'],self.base.one['csrf'],dict(workspace=workspace,operation=operation,params=params or {}))
    def order(self):
        q=self.base.quote()
        return self.base.call('order_prepare',dict(quote_id=q['quote_id'],currency='CNY'))['order_id']
    def task(self,oid,tid='task1'):
        return self.call('owner_review_open',dict(task_id=tid,order_id=oid,kind='FINANCE_EVIDENCE',reason='Original evidence needs checking'))
    def business_state(self):
        return [list(self.fx.stage.s.execute('SELECT * FROM '+table)) for table in ('saas_order_preparations','saas_order_lifecycle_events')]+[list(self.fx.stage.q.execute('SELECT * FROM module_entitlements'))]
    def test_review_queue_close_and_reopen_preserve_business_state(self):
        oid=self.order();before=self.business_state()
        self.assertEqual(self.task(oid)['state'],'PENDING')
        view=self.call('owner_admin_snapshot');self.assertEqual([r['order_id'] for r in view['orders']],[oid])
        self.assertEqual(view['review_tasks'][0]['task_id'],'task1')
        self.assertEqual(self.call('owner_diagnostics')['report']['open_tasks'],['task1'])
        args=dict(task_id='task1',event_id='close1',state='RESOLVED')
        self.assertEqual(self.call('owner_review_close',args)['state'],'RESOLVED')
        self.assertEqual(self.call('owner_review_close',args)['state'],'RESOLVED')
        with self.assertRaises(ValueError):self.call('owner_review_close',dict(args,event_id='different'))
        with self.assertRaises(ValueError):self.call('owner_review_close',dict(args,state='CANCELLED'))
        self.assertEqual(before,self.business_state())
        self.fx.reopen();self.api=CenterSaas(self.fx.center,self.fx.stage.api,self.grants)
        self.assertEqual(self.call('owner_admin_snapshot')['review_tasks'][0]['state'],'RESOLVED')
    def test_project_filter_excludes_unlinked_same_tenant_orders_and_tasks(self):
        own=self.order();foreign=self.order()
        self.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_SAAS_ORDER' AND subject_idx=?",(foreign,));self.fx.center.db.commit()
        create_review(self.fx.stage.s,'foreign_task','tenant1',foreign,'CONTRACT',self.fx.stage.now,'foreign')
        self.task(own)
        view=self.call('owner_admin_snapshot');self.assertEqual([r['order_id'] for r in view['orders']],[own])
        self.assertNotIn(foreign,json.dumps(view));self.assertNotIn('foreign_task',json.dumps(self.call('owner_diagnostics')))
        for op,p in [('owner_review_open',dict(task_id='bad',order_id=foreign,kind='REFUND',reason='bad')),('owner_review_close',dict(task_id='foreign_task',event_id='bad',state='RESOLVED')),('owner_refund_reversal_plan',dict(order_id=foreign,reason='bad'))]:
            with self.assertRaises(PermissionError):self.call(op,p)
    def test_customer_csrf_revoked_project_and_role_mutation_denied(self):
        for op in ('owner_admin_snapshot','owner_diagnostics'):
            with self.assertRaises(PermissionError):self.call(op,workspace='one')
        with self.assertRaises(PermissionError):self.api.dispatch(self.base.one['token'],'wrong',dict(workspace='owner',operation='owner_admin_snapshot',params={}))
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,));self.fx.center.db.commit()
        with self.assertRaises(PermissionError):self.call('owner_admin_snapshot')
    def test_refund_preflight_no_business_effect_and_original_reason_contract(self):
        oid=self.order();before=self.business_state()
        r=self.call('owner_refund_reversal_plan',dict(order_id=oid,reason='Customer request'))
        self.assertEqual(r['action'],'REFUND_REVIEW_ONLY');self.assertEqual(r['order_lifecycle_state'],'PREPARED')
        for k in ('provider_refund_executed','entitlement_revoked','revenue_reversed'):self.assertFalse(r[k])
        self.assertEqual(before,self.business_state())
        for reason in ('','x'*301):
            with self.assertRaises(ValueError):self.call('owner_refund_reversal_plan',dict(order_id=oid,reason=reason))
    def test_diagnostics_clean_pending_and_corrupt_schema(self):
        self.assertEqual(self.call('owner_diagnostics')['status'],'OFFLINE_CHECKED')
        self.task(self.order());r=self.call('owner_diagnostics');self.assertEqual(r['status'],'HOLD')
        self.assertFalse(r['automatic_repair_executed']);self.assertFalse(r['report']['resend_payment_requests'])
        self.fx.stage.s.execute('DROP TABLE saas_review_tasks')
        r=self.call('owner_diagnostics');self.assertEqual(r['status'],'HOLD');self.assertNotIn('report',r)
    def test_global_orphan_hold_is_boolean_without_foreign_identifier(self):
        self.fx.stage.s.execute("INSERT INTO saas_order_lifecycle_events VALUES('orphan_event','secret_foreign_order','PREPARED','AWAITING_EXTERNAL',NULL,?)",(self.fx.stage.now,));self.fx.stage.s.commit()
        r=self.call('owner_diagnostics')
        self.assertEqual(r['status'],'HOLD');self.assertIs(r['report']['orphan_lifecycle_events_global_hold'],True)
        self.assertNotIn('secret_foreign_order',json.dumps(r));self.assertEqual(r['report']['awaiting_review'],[])
    def test_actual_inconsistent_order_reports_hold_without_repair(self):
        oid=self.order()
        self.fx.stage.s.execute("INSERT INTO saas_order_lifecycle_events VALUES('inconsistent',?,'PREPARED','AWAITING_EXTERNAL',NULL,?)",(oid,self.fx.stage.now));self.fx.stage.s.commit()
        before=self.business_state();r=self.call('owner_diagnostics')
        self.assertEqual(r['status'],'HOLD');self.assertEqual(r['report']['integrity_hold'],[oid])
        self.assertEqual(before,self.business_state())
    def test_other_project_pending_review_preserves_original_hold_without_ids(self):
        oid=self.order();self.task(oid,'private_other_project_task')
        self.fx.center.db.execute("UPDATE links SET project='other_project' WHERE channel='COMMUNITY_SAAS_ORDER' AND subject_idx=?",(oid,));self.fx.center.db.commit()
        original=self.fx.stage.api.dispatch(self.fx.stage.owner,'health_detail',{},None)
        self.assertEqual(original['status'],'HOLD')
        r=self.call('owner_diagnostics');self.assertEqual(r['status'],'HOLD')
        self.assertIs(r['report']['original_recovery_hold'],True)
        self.assertEqual(r['report']['open_tasks'],[])
        self.assertIn('ORIGINAL_RECOVERY_HOLD',r['reasons'])
        self.assertNotIn(oid,json.dumps(r));self.assertNotIn('private_other_project_task',json.dumps(r))
    def test_reserved_order_without_preparation_is_hold_and_never_repaired(self):
        oid='so_'+'f'*32
        self.api._reserve(self.api.grants['one'],'ORDER',oid,dict(order_id=oid,quote_id='sq_'+'f'*32,currency='CNY',created_at=self.fx.stage.now))
        before=self.business_state();r=self.call('owner_diagnostics')
        self.assertEqual(r['status'],'HOLD');self.assertEqual(r['report']['missing_order_reservations'],[oid])
        self.assertIn('PROJECT_ORDER_PREPARATION_MISSING',r['reasons'])
        self.assertFalse(r['automatic_repair_executed']);self.assertEqual(before,self.business_state())
    def test_malformed_encrypted_order_binding_is_hold(self):
        oid=self.order()
        for value in (None,[]):
            payload=self.fx.center.encrypt(json.dumps(value).encode(),'community-saas:'+oid)
            self.fx.center.db.execute("UPDATE links SET payload=? WHERE channel='COMMUNITY_SAAS_ORDER' AND subject_idx=?",(payload,oid));self.fx.center.db.commit()
            r=self.call('owner_diagnostics');self.assertEqual(r['status'],'HOLD')
            self.assertEqual(r['reason'],'OFFLINE_STORE_CHECK_FAILED');self.assertNotIn('report',r)
    def test_registered_scope_change_denied(self):
        self.fx.stage.api.bindings[self.fx.stage.owner]['store_id']='different_store'
        with self.assertRaises(PermissionError):self.call('owner_admin_snapshot')
    def test_unknown_order_and_extra_authority_fields_rejected(self):
        with self.assertRaises(PermissionError):self.call('owner_refund_reversal_plan',dict(order_id='legacy_order',reason='request'))
        with self.assertRaises(ValueError):self.call('owner_admin_snapshot',dict(tenant_id='tenant1'))
        with self.assertRaises(ValueError):self.call('owner_review_close',dict(task_id='one',event_id='one',state='RESOLVED',verified=True))
    def test_foreign_project_link_not_admitted(self):
        oid=self.order();self.task(oid)
        self.fx.center.db.execute("UPDATE links SET project='unrelated_project' WHERE channel='COMMUNITY_SAAS_ORDER' AND subject_idx=?",(oid,));self.fx.center.db.commit()
        self.assertEqual(self.call('owner_admin_snapshot')['orders'],[])
        self.assertEqual(self.call('owner_admin_snapshot')['review_tasks'],[])
        with self.assertRaises(PermissionError):self.call('owner_review_close',dict(task_id='task1',event_id='close1',state='RESOLVED'))

if __name__=='__main__':unittest.main()
