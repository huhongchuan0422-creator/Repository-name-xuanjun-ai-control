"""Offline checkout integration tests; no live provider."""
import unittest
from scripts.community_merchant_contract import signed_qr
from scripts.community_checkout import begin, result, split_preview
from scripts.community_ad_contract import AMOUNT, SUCCESS

SCOPE = {'tenant_id': 't1', 'merchant_id': 'm1', 'store_id': 's1'}
KEY = b'k' * 32


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.token = signed_qr(SCOPE, 'scan', 200, KEY)
        self.order = begin(self.token, SCOPE, 'scan', 100, KEY, 105, 'ref1', 'mini')
        self.receipt = {'state': 'SUCCESS', 'server_verified': True, 'provider_reconciled': True,
                        'reference': 'ref1', 'amount_minor': 105, 'currency': 'CNY'}

    def test_amount_slot_and_no_provider_action(self):
        self.assertEqual(self.order['ad_slot'], AMOUNT)
        self.assertFalse(self.order['provider_started'])

    def test_unverified_success_cannot_show_ad(self):
        self.assertEqual(result(self.order, {'state': 'SUCCESS'}),
                         {'paid': False, 'ad_slot': None, 'provider_settlement_verified': False})

    def test_success_verified_exact_match(self):
        r = result(self.order, self.receipt)
        self.assertTrue(r['paid'])
        self.assertEqual(r['ad_slot'], SUCCESS)
        self.assertFalse(r['provider_settlement_verified'])

    def test_receipt_mismatch_rejected(self):
        for name, value in [('reference', 'bad'), ('amount_minor', 106),
                            ('amount_minor', True), ('currency', 'USD')]:
            with self.subTest(name=name, value=value):
                self.assertFalse(result(self.order, dict(self.receipt, **{name: value}))['paid'])

    def test_split_preview_amount_conserved(self):
        p = split_preview(self.order, self.receipt, {'merchant': 7000, 'platform': 3000}, 5)
        self.assertEqual(sum(p['shares_minor'].values()), 100)
        self.assertFalse(p['provider_settlement_verified'])

    def test_no_split_without_verified_receipt(self):
        with self.assertRaisesRegex(ValueError, 'UNVERIFIED_PAYMENT'):
            split_preview(self.order, {'state': 'SUCCESS'}, {'merchant': 10000})

    def test_expired_wrong_scope_and_bool_amount(self):
        for identity, now, amount in [(SCOPE, 200, 105),
                                      (dict(SCOPE, store_id='other'), 100, 105),
                                      (SCOPE, 100, True)]:
            with self.assertRaises(ValueError):
                begin(self.token, identity, 'scan', now, KEY, amount, 'ref2', 'official_h5')


if __name__ == '__main__':
    unittest.main()
