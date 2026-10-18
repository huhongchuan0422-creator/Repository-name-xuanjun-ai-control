"""RSA-verified cancellation recovery from real, versioned basket reservations."""
import concurrent.futures
import copy
import hashlib
import hmac
import threading
import unittest
from unittest.mock import Mock,patch

import test_community_mini_payments as fixtures
from scripts.community_center_operations import CenterOperations
from scripts.community_commerce import Commerce
from scripts.community_demo_bootstrap import DEMO_SCOPE
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_mini_payments import MiniPayments
from scripts.community_order_store import connect,state
from scripts.community_wechat_sp_prepay import PartnerPrepay
from scripts.community_wechat_sp_readonly import PartnerOrderReader,ReadOnlyUnknown
from scripts.pr122_customer_core import Center,canonical


class CancelledStockRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.MiniPaymentJourney.setUpClass()

    def setUp(self):
        self.p=fixtures.MiniPaymentJourney();self.p.setUp();self.fx=self.p.fx
        self.binding=dict(self.p.binding,out_trade_no='provider_basket')
        self.configure()
        self.web=self.fx.center.login('one@example.org','FixturePassword123!')
        self.price_set(0,101,10)
        self.commerce.consumer(self.p.token,'shop1','purchase',dict(reference='basket',
            lines=[dict(item_id='sample_item',quantity=1,revision=1)]))

    def tearDown(self):self.p.tearDown()

    def configure(self):
        ops=CenterOperations(self.fx.center,self.fx.stage.api,{'merchant':dict(
            user_id=self.fx.uid1,project='project1',project_roles=['OWNER'],principal=self.fx.stage.merchant)})
        self.commerce=Commerce(ops,self.fx.identity)
        self.payments=MiniPayments(self.fx.identity,PartnerPrepay(self.fx.center,self.p.reader,{'basket':self.binding}))
        self.payments.commerce=self.commerce

    def call(self,operation):
        return self.payments.dispatch(self.p.token,dict(scene='shop1',operation=operation,reference='basket'))

    def signed(self,provider_state):
        data=dict(sp_mchid='1234567890',sub_mchid=self.binding['sub_mchid'],
            sp_appid=self.binding['sp_appid'],out_trade_no=self.binding['out_trade_no'],
            amount=dict(total=101,currency='CNY'),trade_state=provider_state)
        if provider_state in ('SUCCESS','REFUND'):data['transaction_id']='123456789'
        return self.p.signed(data)

    def price_set(self,revision,unit_minor,stock,enabled=True):
        return self.commerce.dispatch(self.web['token'],self.web['csrf'],dict(workspace='merchant',
            operation='price_set',params=dict(item_id='sample_item',expected_revision=revision,
            unit_minor=unit_minor,stock=stock,enabled=enabled)))

    def price(self):return self.commerce._read(DEMO_SCOPE,'project1','PRODUCT','sample_item')
    def basket(self):return self.commerce._read(DEMO_SCOPE,'project1','ORDER','basket')
    def release(self,**kwargs):
        return self.commerce.release_cancelled(kwargs.get('identity',DEMO_SCOPE),
            kwargs.get('project','project1'),kwargs.get('uid',self.fx.uid1),'basket')
    def save(self,kind,reference,value):
        with self.fx.center.tx():self.commerce._save(DEMO_SCOPE,'project1',self.fx.uid1,kind,reference,value,True)
    def assert_reserved(self):
        self.assertEqual((self.price()['stock'],self.price()['revision']),(9,2))
        self.assertIs(self.basket()['stock_reserved'],True)
        self.assertNotIn('stock_released',self.basket())
        self.assertEqual(self.fx.center.db.execute("SELECT count(*) FROM audit WHERE event='CANCELLED_ORDER_STOCK_RELEASED'").fetchone()[0],0)
    def assert_released(self):
        self.assertEqual((self.price()['stock'],self.price()['revision']),(10,3))
        self.assertIs(self.basket()['stock_released'],True)
        self.assertEqual(self.fx.center.db.execute("SELECT count(*) FROM audit WHERE event='CANCELLED_ORDER_STOCK_RELEASED'").fetchone()[0],1)
    def cancel_without_release(self,provider_state=None):
        self.payments.commerce=None
        try:
            if provider_state is None:self.call('cancel')
            else:
                self.p.reader._fetch=Mock(return_value=self.signed(provider_state));self.call('query')
        finally:self.payments.commerce=self.commerce
        self.assert_reserved()

    def configure_finance(self):
        from scripts.community_provider_reference import provider_order_reference
        from scripts.community_wechat_sp_actions import ProviderActions
        self.binding['out_trade_no']=provider_order_reference(self.p.reader._mchid,DEMO_SCOPE,'basket')
        self.payments.prepay.bindings['basket']=dict(self.binding)
        self.finance_web=self.fx.center.login('two@example.org','FixturePassword123!')
        ops=CenterOperations(self.fx.center,self.fx.stage.api,{'finance':dict(user_id=self.fx.uid2,
            project='project1',project_roles=['EDITOR'],principal=self.fx.stage.owner)})
        policy=dict(sp_appid=self.fx.identity.appid,sub_mchid=self.binding['sub_mchid'],sub_appid=None,
            refund_notify_url='https://example.org/notify',profit_sharing=False,max_total_bps=0,
            receivers={},enabled_operations=['REFUND'])
        self.actions=ProviderActions(ops,self.p.reader,{tuple(DEMO_SCOPE[k] for k in
            ('tenant_id','merchant_id','store_id')):policy})
        self.actions.commerce=self.commerce

    def reconcile(self):
        return self.actions.dispatch(self.finance_web['token'],self.finance_web['csrf'],
            dict(workspace='finance',operation='reconcile_order',params=dict(reference='basket')))

    def check_signed_cancellation(self,provider_state):
        self.p.reader._fetch=Mock(return_value=self.signed(provider_state))
        result=self.call('query')
        self.assertEqual(result['provider_state'],provider_state)
        self.assertTrue(result['provider_signature_verified'])
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'basket')['state'],'CANCELLED')
        self.assertIsNone(self.fx.center.db.execute("SELECT 1 FROM events WHERE channel='COMMUNITY_PREPAY_ATTEMPT'").fetchone())
        self.assert_released()
        self.p.reader._fetch=Mock(side_effect=AssertionError('TERMINAL_RECOVERY_MUST_NOT_USE_NETWORK'))
        for operation in ('query','cancel','query','cancel'):
            result=self.call(operation)
            self.assertEqual(result['order_state'],'CANCELLED')
            self.assertEqual(result['provider_state'],provider_state)
            self.assertTrue(result['provider_signature_verified'])
        self.p.reader._fetch.assert_not_called();self.assert_released()

    def test_signed_closed_query_releases_without_prepay_and_repeats_safely(self):
        self.check_signed_cancellation('CLOSED')

    def test_signed_revoked_query_releases_without_prepay_and_repeats_safely(self):
        self.check_signed_cancellation('REVOKED')

    def check_projection_crash_reopen(self,recovery_operation):
        self.p.reader._fetch=Mock(return_value=self.signed('CLOSED'))
        with patch.object(self.commerce,'release_cancelled',side_effect=RuntimeError('INTERRUPTED_AFTER_PROJECTION')):
            with self.assertRaisesRegex(RuntimeError,'INTERRUPTED_AFTER_PROJECTION'):self.call('query')
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'basket')['state'],'CANCELLED');self.assert_reserved()
        self.fx.reopen()
        self.fx.stage.o.close();self.fx.stage.o=connect(self.fx.stage.order_path);self.fx.stage.demo.db=self.fx.stage.o
        self.configure()
        self.p.reader._fetch=Mock(side_effect=AssertionError('NO_NETWORK_ON_RECOVERY'))
        self.assertEqual(self.call(recovery_operation)['order_state'],'CANCELLED')
        self.p.reader._fetch.assert_not_called();self.assert_released()

    def test_query_recovers_crash_after_projection_across_database_reopen(self):
        self.check_projection_crash_reopen('query')

    def test_cancel_recovers_signed_terminal_without_local_prepay_attempt(self):
        self.check_projection_crash_reopen('cancel')

    def test_query_recovers_interrupted_local_cancellation_without_network(self):
        with patch.object(self.commerce,'release_cancelled',side_effect=RuntimeError('LOCAL_INTERRUPTED')):
            with self.assertRaisesRegex(RuntimeError,'LOCAL_INTERRUPTED'):self.call('cancel')
        self.assert_reserved()
        self.p.reader._fetch=Mock(side_effect=AssertionError('LOCAL_ORDER_HAS_NO_PROVIDER'))
        result=self.call('query')
        self.assertEqual(result['provider_state'],'NOT_CREATED');self.assertFalse(result['provider_signature_verified'])
        self.p.reader._fetch.assert_not_called();self.assert_released()

    def test_unknown_pending_and_bad_signatures_never_release(self):
        for provider_state in ('NOTPAY','USERPAYING','PAYERROR'):
            with self.subTest(provider_state=provider_state):
                self.p.reader._fetch=Mock(return_value=self.signed(provider_state));self.call('query')
                self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'basket')['state'],'PENDING');self.assert_reserved()
        for response in (TimeoutError(),self.signed('UNKNOWN')):
            self.p.reader._fetch=Mock(side_effect=response) if isinstance(response,Exception) else Mock(return_value=response)
            with self.assertRaises(ReadOnlyUnknown):self.call('query')
            self.assert_reserved()
        headers,raw=self.signed('CLOSED');headers['Wechatpay-Signature']='invalid'
        self.p.reader._fetch=Mock(return_value=(headers,raw))
        with self.assertRaises(ReadOnlyUnknown):self.call('query')
        with self.assertRaisesRegex(PermissionError,'CONFIRMED_CANCELLATION_REQUIRED'):self.release()
        self.assert_reserved()

    def test_signed_success_never_releases(self):
        self.p.reader._fetch=Mock(return_value=self.signed('SUCCESS'));self.call('query')
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'basket')['state'],'SUCCESS')
        with self.assertRaisesRegex(PermissionError,'CONFIRMED_CANCELLATION_REQUIRED'):self.release()
        with self.assertRaises(PermissionError):self.call('cancel')
        self.assert_reserved()

    def test_cancelled_flag_without_durable_evidence_never_releases(self):
        self.fx.stage.o.execute("UPDATE orders SET state='CANCELLED' WHERE reference='basket'");self.fx.stage.o.commit()
        with self.assertRaisesRegex(PermissionError,'CONFIRMED_CANCELLATION_REQUIRED'):self.release()
        with self.assertRaises(PermissionError):self.call('query')
        self.assert_reserved()

    def test_foreign_owner_project_or_scope_cannot_release(self):
        self.cancel_without_release('CLOSED')
        for kwargs in (dict(uid=self.fx.uid2),dict(project='other_project'),
                dict(identity=dict(DEMO_SCOPE,store_id='other_store'))):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((PermissionError,ValueError)):self.release(**kwargs)
                self.assert_reserved()
        key=self.fx.identity._order_key(self.fx.stage.customer,'basket')[0]
        self.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_ORDER' AND subject_idx=?",(key,))
        with self.assertRaisesRegex(PermissionError,'ORIGINAL_BASKET_OWNER_REQUIRED'):self.release()
        self.assert_reserved()

    def test_missing_reservation_or_changed_frozen_basket_is_rejected(self):
        self.cancel_without_release()
        original=self.basket()
        mutations=[dict(stock_reserved=False),dict(stock_reserved=1),dict(stock_released=1),
            dict(scope=dict(DEMO_SCOPE,merchant_id='other')),dict(reference='other'),
            dict(user_id=self.fx.uid2),dict(amount_minor=102),dict(currency='USD'),
            dict(request_hash='0'*64),dict(lines=[])]
        missing=dict(original);missing.pop('stock_reserved')
        variants=[missing]+[dict(original,**values) for values in mutations]
        for changes in (dict(quantity=0),dict(quantity=True),dict(revision=2),dict(unit_minor=102),
                dict(subtotal_minor=102),dict(item_id='missing'),dict(name='')):
            variants.append(dict(original,lines=[dict(original['lines'][0],**changes)]))
        variants.append(dict(original,lines=original['lines']*2))
        for number,record in enumerate(variants):
            with self.subTest(number=number):
                self.save('ORDER','basket',record)
                with self.assertRaises((PermissionError,ValueError)):self.release()
                self.assertEqual((self.price()['stock'],self.price()['revision']),(9,2))
                self.save('ORDER','basket',original)
        self.assert_reserved();self.release();self.assert_released()

    def test_matching_rewritten_basket_hash_cannot_forge_reservation(self):
        self.cancel_without_release()
        record=self.basket();line=dict(record['lines'][0],quantity=2,subtotal_minor=202)
        request=[{k:line[k] for k in ('item_id','quantity','revision')}]
        self.save('ORDER','basket',dict(record,lines=[line],request_hash=hashlib.sha256(canonical(request)).hexdigest()))
        with self.assertRaisesRegex(PermissionError,'ORIGINAL_STOCK_RESERVATION_MISMATCH'):self.release()
        self.assertEqual((self.price()['stock'],self.price()['revision']),(9,2))

    def test_original_and_current_price_versions_are_required(self):
        self.cancel_without_release()
        for kind,reference,changes in [('PRICE_VERSION','sample_item:1',dict(stock=11)),
                ('PRICE_VERSION','sample_item:2',dict(stock=10)),
                ('PRODUCT','sample_item',dict(revision=1)),
                ('PRODUCT','sample_item',dict(stock=8)),
                ('PRODUCT','sample_item',dict(revision=True))]:
            original=self.commerce._read(DEMO_SCOPE,'project1',kind,reference)
            with self.subTest(kind=kind,changes=changes):
                self.save(kind,reference,dict(original,**changes))
                with self.assertRaises((PermissionError,ValueError)):self.release()
                self.save(kind,reference,original)
                self.assert_reserved()
        key=self.commerce._key(DEMO_SCOPE,'PRICE_VERSION','sample_item:1')
        self.fx.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_COMMERCE_V1' AND subject_idx=?",(key,))
        with self.assertRaisesRegex(ValueError,'ORIGINAL_PRODUCT_VERSION_REQUIRED'):self.release()
        self.assert_reserved()

    def test_recovery_preserves_later_price_stock_and_disabled_product(self):
        self.cancel_without_release('REVOKED')
        self.price_set(2,202,30,False)
        self.release();self.release()
        price=self.price()
        self.assertEqual((price['unit_minor'],price['stock'],price['revision'],price['enabled']),(202,31,4,False))
        self.assertEqual(self.commerce._read(DEMO_SCOPE,'project1','PRICE_VERSION','sample_item:2')['stock'],9)

    def test_released_replay_does_not_depend_on_later_product_edits(self):
        self.cancel_without_release('CLOSED');self.release();self.assert_released()
        changed=self.price_set(3,303,55,False)
        original_read=self.commerce._read
        def immutable_only(identity,project,kind,reference):
            if kind=='PRODUCT':raise AssertionError('RELEASED_REPLAY_MUST_NOT_READ_CURRENT_PRODUCT')
            return original_read(identity,project,kind,reference)
        with patch.object(self.commerce,'_read',side_effect=immutable_only),patch.object(
                self.commerce,'_catalog_item',side_effect=AssertionError('RELEASED_REPLAY_MUST_NOT_READ_CATALOGUE')):
            self.release();self.release()
        self.assertEqual(self.price(),changed)
        self.assertEqual(self.fx.center.db.execute("SELECT count(*) FROM audit WHERE event='CANCELLED_ORDER_STOCK_RELEASED'").fetchone()[0],1)

    def check_release_rollback(self,crash_kind):
        self.cancel_without_release('CLOSED');original_save=self.commerce._save
        def interrupted(identity,project,uid,kind,reference,value,update=False):
            original_save(identity,project,uid,kind,reference,value,update)
            if kind==crash_kind:raise RuntimeError('INTERRUPTED_RELEASE')
        with patch.object(self.commerce,'_save',side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError,'INTERRUPTED_RELEASE'):self.call('query')
        self.assert_reserved()
        self.assertIsNone(self.commerce._read(DEMO_SCOPE,'project1','PRICE_VERSION','sample_item:3'))
        self.call('query');self.assert_released()

    def test_product_write_interruption_rolls_back_stock_and_history(self):
        self.check_release_rollback('PRODUCT')

    def test_release_marker_interruption_rolls_back_entire_transaction(self):
        self.check_release_rollback('ORDER')

    def test_close_audit_failure_after_release_does_not_release_twice(self):
        audit=self.fx.center.audit
        def interrupted(project,actor,event,obj):
            if event=='COMMUNITY_ORDER_CANCELLED':raise RuntimeError('INTERRUPTED_CLOSE_FINALIZATION')
            return audit(project,actor,event,obj)
        with patch.object(self.fx.center,'audit',side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError,'INTERRUPTED_CLOSE_FINALIZATION'):self.call('cancel')
        self.assert_released();self.call('cancel');self.assert_released()

    def test_multiple_product_restore_is_one_atomic_transaction(self):
        from scripts.community_merchant_store import put_item
        actor=dict(authenticated=True,role='MERCHANT_ADMIN',actor_id='OFFLINE_FIXTURE',
            tenant_id=DEMO_SCOPE['tenant_id'],merchant_id=DEMO_SCOPE['merchant_id'])
        put_item(self.fx.stage.m,DEMO_SCOPE,actor,dict(id='other_item',name='Other item',status='ACTIVE',sort=2))
        self.commerce.dispatch(self.web['token'],self.web['csrf'],dict(workspace='merchant',
            operation='price_set',params=dict(item_id='other_item',expected_revision=0,
            unit_minor=202,stock=8,enabled=True)))
        self.commerce.consumer(self.p.token,'shop1','purchase',dict(reference='multi',lines=[
            dict(item_id='sample_item',quantity=1,revision=2),dict(item_id='other_item',quantity=1,revision=1)]))
        self.payments.prepay.bindings['multi']=dict(self.binding,out_trade_no='provider_multi',amount_minor=303)
        def call(operation):return self.payments.dispatch(self.p.token,dict(scene='shop1',operation=operation,reference='multi'))
        original_save=self.commerce._save
        def interrupted(identity,project,uid,kind,reference,value,update=False):
            original_save(identity,project,uid,kind,reference,value,update)
            if kind=='PRODUCT' and reference=='other_item':raise RuntimeError('SECOND_PRODUCT_INTERRUPTED')
        with patch.object(self.commerce,'_save',side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError,'SECOND_PRODUCT_INTERRUPTED'):call('cancel')
        other=lambda:self.commerce._read(DEMO_SCOPE,'project1','PRODUCT','other_item')
        self.assertEqual((self.price()['stock'],self.price()['revision']),(8,3))
        self.assertEqual((other()['stock'],other()['revision']),(7,2))
        self.assertNotIn('stock_released',self.commerce._read(DEMO_SCOPE,'project1','ORDER','multi'))
        self.assertIsNone(self.commerce._read(DEMO_SCOPE,'project1','PRICE_VERSION','sample_item:4'))
        call('query');call('cancel')
        self.assertEqual((self.price()['stock'],self.price()['revision']),(9,4))
        self.assertEqual((other()['stock'],other()['revision']),(8,3))
        self.assertTrue(self.commerce._read(DEMO_SCOPE,'project1','ORDER','multi')['stock_released'])

    def test_stock_limit_failure_is_recoverable_without_partial_release(self):
        self.cancel_without_release('CLOSED');self.price_set(2,101,100000000)
        with self.assertRaisesRegex(ValueError,'INVENTORY_RESTORE_OVERFLOW'):self.release()
        self.assertEqual((self.price()['stock'],self.price()['revision']),(100000000,3))
        self.assertNotIn('stock_released',self.basket())
        self.assertIsNone(self.commerce._read(DEMO_SCOPE,'project1','PRICE_VERSION','sample_item:4'))
        self.price_set(3,101,99999999);self.release();self.release()
        self.assertEqual((self.price()['stock'],self.price()['revision']),(100000000,5))
        self.assertTrue(self.basket()['stock_released'])

    def test_financial_reconciliation_restores_for_original_buyer_once(self):
        self.configure_finance();self.p.reader._fetch=Mock(return_value=self.signed('CLOSED'))
        with patch.object(self.commerce,'release_cancelled',wraps=self.commerce.release_cancelled) as restore:
            first=self.reconcile();again=self.reconcile()
        self.assertEqual(first['local_order_state'],'CANCELLED')
        self.assertEqual(again['local_order_state'],'CANCELLED')
        self.assertEqual(restore.call_count,2)
        restore.assert_called_with(DEMO_SCOPE,'project1',self.fx.uid1,'basket')
        self.assertNotEqual(self.fx.uid1,self.finance_web['user_id']);self.assert_released()
        audit=self.fx.center.db.execute("SELECT actor FROM audit WHERE event='CANCELLED_ORDER_STOCK_RELEASED'").fetchone()
        self.assertEqual(audit[0],self.fx.uid1)

    def assert_financial_identity_change_denied(self,change):
        self.configure_finance()
        response=self.signed('CLOSED')
        _,policy=self.actions._authorize(self.finance_web['token'],self.finance_web['csrf'],'finance')
        def changed_during_signed_query(request):
            change()
            # The changed identity remains valid through the real Center
            # session, membership and protected grant, with an equal policy.
            self.assertEqual(self.actions._authorize(self.finance_web['token'],
                self.finance_web['csrf'],'finance')[1],policy)
            return response
        self.p.reader._fetch=Mock(side_effect=changed_during_signed_query)
        with patch.object(self.commerce,'release_cancelled',wraps=self.commerce.release_cancelled) as restore:
            with self.assertRaisesRegex(PermissionError,'RECONCILIATION_AUTHORIZATION_CHANGED'):
                self.reconcile()
            restore.assert_not_called()
        self.p.reader._fetch.assert_called_once()
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'basket')['state'],'PENDING')
        self.assertEqual(self.fx.stage.o.execute("SELECT count(*) FROM order_events WHERE reference='basket'").fetchone()[0],0)
        self.assert_reserved()
        self.assertEqual(self.fx.center.db.execute("SELECT count(*) FROM links WHERE channel IN ('COMMUNITY_ORDER_RECONCILIATION','COMMUNITY_RECONCILIATION_HISTORY')").fetchone()[0],0)
        self.assertEqual(self.fx.center.db.execute("SELECT count(*) FROM audit WHERE event='COMMUNITY_ORDER_RECONCILED'").fetchone()[0],0)

    def change_financial_scope(self,in_place):
        grant=self.actions.operations.grants['finance']
        identity=dict(grant['scope'],store_id='other-store')
        original=tuple(grant['scope'][k] for k in ('tenant_id','merchant_id','store_id'))
        self.actions.runtime.bindings[grant['principal']]=dict(identity)
        self.actions.bindings[tuple(identity[k] for k in ('tenant_id','merchant_id','store_id'))]=self.actions.bindings[original]
        if in_place:grant['scope'].update(identity)
        else:self.actions.operations.grants['finance']=dict(grant,scope=identity)

    def test_financial_signed_closed_rejects_replaced_scope_before_projection(self):
        self.assert_financial_identity_change_denied(lambda:self.change_financial_scope(False))

    def test_financial_signed_closed_rejects_in_place_scope_before_projection(self):
        self.assert_financial_identity_change_denied(lambda:self.change_financial_scope(True))

    def test_financial_signed_closed_rejects_project_change_before_projection(self):
        original=self.fx.center.project(self.fx.uid1,'project1',('OWNER',))[2]
        payload=dict(revision=2,expires=self.fx.center.now()+10000,
                     projects=[original,dict(original,id='project2')])
        key=b'a'*32
        self.fx.center.import_authority(dict(payload=payload,signature=hmac.new(
            key,canonical(payload),hashlib.sha256).hexdigest()),key)
        self.fx.center.db.execute("INSERT INTO members VALUES('project2',?,'EDITOR',1)",(self.fx.uid2,))
        def change():self.actions.operations.grants['finance']['project']='project2'
        self.assert_financial_identity_change_denied(change)

    def test_financial_signed_closed_rejects_user_change_before_projection(self):
        def change():
            uid=self.fx.uid1
            epoch=self.fx.center.db.execute('SELECT epoch FROM accounts WHERE id=?',(uid,)).fetchone()[0]
            self.fx.center.db.execute('UPDATE sessions SET user_id=?,epoch=? WHERE token=?',
                (uid,epoch,hashlib.sha256(self.finance_web['token'].encode()).hexdigest()))
            self.actions.operations.grants['finance'].update(user_id=uid,project_roles=('OWNER','EDITOR'))
        self.assert_financial_identity_change_denied(change)

    def test_financial_revoked_projection_interruption_recovers_on_reconcile(self):
        self.configure_finance();self.p.reader._fetch=Mock(return_value=self.signed('REVOKED'))
        with patch.object(self.commerce,'release_cancelled',side_effect=RuntimeError('FINANCIAL_RELEASE_INTERRUPTED')):
            with self.assertRaisesRegex(RuntimeError,'FINANCIAL_RELEASE_INTERRUPTED'):self.reconcile()
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'basket')['state'],'CANCELLED');self.assert_reserved()
        self.assertEqual(self.reconcile()['local_order_state'],'CANCELLED');self.assert_released()

    def test_financial_unknown_pending_success_never_release(self):
        self.configure_finance()
        with patch.object(self.commerce,'release_cancelled',wraps=self.commerce.release_cancelled) as restore:
            self.p.reader._fetch=Mock(side_effect=TimeoutError())
            with self.assertRaises(ReadOnlyUnknown):self.reconcile()
            self.assert_reserved()
            for provider_state in ('NOTPAY','USERPAYING','PAYERROR','SUCCESS'):
                self.p.reader._fetch=Mock(return_value=self.signed(provider_state));self.reconcile()
                self.assert_reserved()
            restore.assert_not_called()

    def test_financial_operator_cannot_replace_original_basket_owner(self):
        self.configure_finance();self.p.reader._fetch=Mock(return_value=self.signed('CLOSED'))
        original=self.basket();self.save('ORDER','basket',dict(original,user_id=self.fx.uid2))
        with self.assertRaisesRegex(PermissionError,'ORIGINAL_BASKET_OWNER_REQUIRED'):self.reconcile()
        self.assertEqual((self.price()['stock'],self.price()['revision']),(9,2))
        self.save('ORDER','basket',original)
        self.reconcile();self.assert_released()

    def two_connection_recovery(self,operations,provider_state=None):
        barrier=threading.Barrier(2)
        network_barrier=threading.Barrier(2)
        response=None if provider_state is None else self.signed(provider_state)
        def recover(operation):
            center=Center(self.fx.tmp.name,{'testkey':b'k'*32},'testkey',clock=lambda:self.fx.stage.now,mail_ready=True)
            order_db=connect(self.fx.stage.order_path)
            try:
                runtime=copy.copy(self.fx.stage.api);runtime.demo=copy.copy(self.fx.stage.demo);runtime.demo.db=order_db
                identity=CenterIdentity(center,runtime,self.fx.identity.appid,self.fx.scenes)
                ops=CenterOperations(center,runtime,{'merchant':dict(user_id=self.fx.uid1,project='project1',
                    project_roles=['OWNER'],principal=self.fx.stage.merchant)})
                reader=PartnerOrderReader('1234567890','ABC',self.p.keys.private,'PUB_KEY_ID_fixture',
                    self.p.keys.public,lambda:self.fx.stage.now)
                def signed_response(request):
                    # Both callers must have observed PENDING before either can
                    # commit its verified terminal projection.
                    network_barrier.wait(timeout=10)
                    return response
                reader._fetch=Mock(side_effect=AssertionError('TERMINAL_RECOVERY_HAS_NO_NETWORK')) if response is None else Mock(side_effect=signed_response)
                payments=MiniPayments(identity,PartnerPrepay(center,reader,{'basket':self.binding}))
                payments.commerce=Commerce(ops,identity)
                barrier.wait(timeout=10)
                result=payments.dispatch(self.p.token,dict(scene='shop1',operation=operation,reference='basket'))
                if response is None:reader._fetch.assert_not_called()
                return result
            finally:order_db.close();center.db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(recover,operation) for operation in operations]
            results=[future.result(timeout=20) for future in futures]
        self.assert_released()
        self.assertEqual(self.fx.stage.o.execute("SELECT count(*) FROM order_events WHERE reference='basket'").fetchone()[0],1)
        return results

    def test_two_connections_query_and_cancel_restore_stock_exactly_once(self):
        self.cancel_without_release('CLOSED')
        results=self.two_connection_recovery(('query','cancel'))
        self.assertEqual([result['order_state'] for result in results],['CANCELLED','CANCELLED'])

    def test_two_connections_race_signed_projection_and_restore_once(self):
        results=self.two_connection_recovery(('query','query'),'CLOSED')
        self.assertEqual([result['provider_state'] for result in results],['CLOSED','CLOSED'])
        self.assertTrue(all(result['provider_signature_verified'] for result in results))
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'basket')['state'],'CANCELLED')


if __name__=='__main__':unittest.main()
