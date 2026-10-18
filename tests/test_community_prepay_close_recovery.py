"""Unknown order closure never reissues payer-confirmation signatures."""
import json
import unittest
from unittest.mock import Mock,patch

import test_community_mini_payments as fixtures
from scripts.community_demo_bootstrap import DEMO_SCOPE
from scripts.community_mini_payments import MiniPayments
from scripts.community_order_store import state
from scripts.community_wechat_sp_prepay import PartnerPrepay,PrepayUnknown
from scripts.community_wechat_sp_readonly import ReadOnlyUnknown


class PrepayCloseRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.MiniPaymentJourney.setUpClass()
    def setUp(self):
        self.p=fixtures.MiniPaymentJourney();self.p.setUp();self.fx=self.p.fx
    def tearDown(self):self.p.tearDown()

    def prepare(self):
        self.p.reader._fetch=Mock(return_value=self.p.signed(dict(prepay_id='fixture')))
        return self.p.call('prepare')

    def unknown_close(self):
        self.prepare();self.p.reader._fetch=Mock(side_effect=TimeoutError())
        with self.assertRaises(ReadOnlyUnknown):self.p.call('cancel')
        self.assertEqual([call.args[0].method for call in self.p.reader._fetch.call_args_list],['POST','GET'])
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'order1')['state'],'PENDING')
        key=self.p.prepay._identity(self.p.binding)
        row=self.fx.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_ORDER_CLOSE' AND subject_idx=? AND active=1",(key,)).fetchone()
        saved=json.loads(self.fx.center.decrypt(row[0],'community-close:'+key))
        self.assertEqual(saved['state'],'CLOSE_RESERVED');self.assertTrue(saved['provider_attempted'])
        self.assertIsNotNone(self.fx.center.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_PREPAY_RESULT' AND subject_idx=?",(key,)).fetchone())

    def signed(self,provider_state):
        data=dict(sp_mchid='1234567890',sub_mchid=self.p.binding['sub_mchid'],sp_appid=self.p.binding['sp_appid'],
            out_trade_no=self.p.binding['out_trade_no'],amount=dict(total=101,currency='CNY'),trade_state=provider_state)
        if provider_state in ('SUCCESS','REFUND'):data['transaction_id']='123456789'
        return self.p.signed(data)

    def assert_recovery_blocked(self,message='ORDER_CLOSING_OR_CANCELLED'):
        self.p.reader._fetch=Mock(side_effect=AssertionError('NO_NETWORK_OR_NEW_PREPAY'))
        with patch.object(self.p.prepay,'_sign',side_effect=AssertionError('NO_NEW_PAYMENT_SIGNATURE')) as sign:
            for _ in range(2):
                with self.assertRaisesRegex(PermissionError,message):self.p.call('recover')
            sign.assert_not_called()
        self.p.reader._fetch.assert_not_called()

    def test_unknown_close_blocks_repeated_recover_and_prepare(self):
        self.unknown_close();self.assert_recovery_blocked()
        with self.assertRaisesRegex(PermissionError,'ORDER_CLOSING_OR_CANCELLED'):self.p.call('prepare')
        self.p.reader._fetch.assert_not_called()
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'order1')['state'],'PENDING')

    def test_close_intent_survives_reopen_and_blocks_both_recovery_entrypoints(self):
        self.unknown_close();self.fx.reopen()
        self.p.prepay=PartnerPrepay(self.fx.center,self.p.reader,{'order1':self.p.binding})
        self.p.payments=MiniPayments(self.fx.identity,self.p.prepay)
        self.assert_recovery_blocked()
        web=self.fx.center.login('one@example.org','FixturePassword123!')
        with patch.object(self.p.prepay,'_sign',side_effect=AssertionError('NO_NEW_SIGNATURE')) as sign:
            with self.assertRaisesRegex(PermissionError,'ORDER_CLOSING_OR_CANCELLED'):
                self.p.prepay.existing(web['token'],web['csrf'],'order1')
            sign.assert_not_called()
        self.p.reader._fetch.assert_not_called()

    def test_signed_pending_query_does_not_remove_close_gate(self):
        self.unknown_close()
        for provider_state in ('NOTPAY','USERPAYING','PAYERROR'):
            with self.subTest(provider_state=provider_state):
                self.p.reader._fetch=Mock(return_value=self.signed(provider_state))
                self.assertEqual(self.p.call('query')['provider_state'],provider_state)
                self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'order1')['state'],'PENDING')
                self.assert_recovery_blocked()

    def check_terminal(self,provider_state,recovery_operation):
        self.unknown_close();self.p.reader._fetch=Mock(return_value=self.signed(provider_state))
        result=self.p.call(recovery_operation)
        self.assertEqual(result['provider_state'],provider_state)
        self.p.reader._fetch.assert_called_once()
        self.assertEqual(self.p.reader._fetch.call_args.args[0].method,'GET')
        terminal='SUCCESS' if provider_state=='SUCCESS' else 'CANCELLED'
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'order1')['state'],terminal)
        self.assert_recovery_blocked('PAYMENT_ALREADY_TERMINAL_QUERY_ONLY')
        if terminal=='CANCELLED':
            result=self.p.call('cancel');self.assertEqual(result['order_state'],'CANCELLED')
            self.p.reader._fetch.assert_not_called()
        with patch.object(self.p.prepay,'_sign',side_effect=AssertionError('NO_DIRECT_SIGNATURE')) as sign:
            with self.assertRaisesRegex(PermissionError,'ORDER_CLOSING_OR_CANCELLED'):
                self.p.prepay._existing_authorized(self.p.binding,lambda:dict(self.p.binding))
            sign.assert_not_called()

    def test_signed_closed_query_still_recovers_without_enabling_payment(self):
        self.check_terminal('CLOSED','query')

    def test_signed_revoked_cancel_still_recovers_without_reposting_close(self):
        self.check_terminal('REVOKED','cancel')

    def test_signed_success_query_still_recovers_without_reissuing_payment(self):
        self.check_terminal('SUCCESS','query')

    def test_no_close_existing_payment_still_recovers_with_serialized_signature(self):
        first=self.prepare();self.p.reader._fetch=Mock(side_effect=AssertionError('NO_SECOND_PREPAY'))
        original_sign=self.p.prepay._sign
        def locked_signature(message):
            self.assertTrue(self.fx.center.db.in_transaction)
            return original_sign(message)
        with patch.object(self.p.prepay,'_sign',side_effect=locked_signature) as sign:
            for _ in range(2):self.assertEqual(self.p.call('recover')['package'],first['package'])
            self.assertEqual(sign.call_count,2)
        self.p.reader._fetch.assert_not_called()

    def test_other_order_close_does_not_block_original_unclosed_payment(self):
        first=self.prepare();self.fx.checkout(self.p.token,'order2')
        self.p.prepay.bindings['order2']=dict(self.p.binding,out_trade_no='provider_order2')
        self.p.reader._fetch=Mock(side_effect=AssertionError('NO_NETWORK'))
        other=self.p.payments.dispatch(self.p.token,dict(scene='shop1',operation='cancel',reference='order2'))
        self.assertEqual(other['order_state'],'CANCELLED')
        self.assertEqual(self.p.call('recover')['package'],first['package'])
        self.p.reader._fetch.assert_not_called()

    def test_close_racing_prepay_response_never_returns_client_signature(self):
        def response_after_close(request):
            self.p.reader._fetch=Mock(side_effect=TimeoutError())
            with self.assertRaises(ReadOnlyUnknown):self.p.call('cancel')
            return self.p.signed(dict(prepay_id='fixture'))
        self.p.reader._fetch=Mock(side_effect=response_after_close)
        with patch.object(self.p.prepay,'_sign',wraps=self.p.prepay._sign) as sign:
            with self.assertRaises(PrepayUnknown):self.p.call('prepare')
            # The sole signature authorizes the original prepay request. No
            # payer-confirmation signature may follow the persisted close intent.
            self.assertEqual(sign.call_count,1)
        self.assertEqual(state(self.fx.stage.o,DEMO_SCOPE,'order1')['state'],'PENDING')
        self.assert_recovery_blocked()


if __name__=='__main__':unittest.main()
