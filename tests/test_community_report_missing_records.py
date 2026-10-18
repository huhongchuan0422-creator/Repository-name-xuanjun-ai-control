"""Missing or malformed original financial evidence must never become zero."""
import unittest

import test_community_earnings_integrity as fixtures
from scripts.community_demo_bootstrap import DEMO_SCOPE


class CommunityReportMissingRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.CommunityEarningsIntegrity.setUpClass()

    def setUp(self):
        self.fx = fixtures.CommunityEarningsIntegrity()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.c = self.fx.c
        self.assertEqual(self.fx.report()['page_gross_minor'], 10)

    def assert_earnings_denied(self):
        with self.assertRaisesRegex(ValueError, '^COMMUNITY_EARNINGS_INTEGRITY_CONFLICT$'):
            self.fx.report()

    def test_non_object_provider_action_cannot_silently_remove_earnings(self):
        for value in ([], None, 'private-corrupt-action', 0, True):
            with self.subTest(value=value):
                self.fx.save_action(value)
                self.assert_earnings_denied()
        self.fx.save_action(self.fx.action)
        self.assertEqual(self.fx.report()['page_gross_minor'], 10)

    def test_non_object_commerce_record_cannot_silently_remove_order(self):
        key = self.fx.fx.commerce._key(DEMO_SCOPE, 'ORDER', 'basket')
        for value in ([], None, 'private-corrupt-order', 0, True):
            with self.subTest(value=value):
                self.fx.write('COMMUNITY_COMMERCE_V1', key, value, 'community-commerce:' + key)
                with self.assertRaisesRegex(ValueError, '^COMMUNITY_ORDER_INTEGRITY_CONFLICT$'):
                    self.fx.fx.call('community_orders', dict(community_id=self.fx.fx.cid, after_id=''))

    def test_unclassifiable_action_kind_or_scope_cannot_silently_remove_earnings(self):
        missing_kind = dict(self.fx.action)
        missing_kind.pop('kind')
        values = ({}, missing_kind, dict(self.fx.action, kind='UNKNOWN'),
                  dict(self.fx.action, kind=None), dict(self.fx.action, scope=None),
                  dict(self.fx.action, scope={}),
                  dict(self.fx.action, scope=dict(tenant_id='tenant1')),
                  dict(self.fx.action, scope=dict(DEMO_SCOPE, store_id='bad scope')))
        for value in values:
            with self.subTest(value=value):
                self.fx.save_action(value)
                self.assert_earnings_denied()

    def test_recognized_refund_kind_remains_excluded_from_split_earnings(self):
        self.fx.save_action(dict(self.fx.action, kind='REFUND'))
        result = self.fx.report()
        self.assertEqual(result['records'], [])
        self.assertEqual(result['page_gross_minor'], 0)
        self.fx.fx.communities.provider_actions = None
        self.assertEqual(self.fx.report(), result)

    def test_valid_foreign_tenant_scope_remains_excluded(self):
        self.fx.save_action(dict(self.fx.action, scope=dict(DEMO_SCOPE, tenant_id='foreign')))
        result = self.fx.report()
        self.assertEqual(result['records'], [])
        self.assertEqual(result['page_gross_minor'], 0)
        self.fx.fx.communities.provider_actions = None
        self.assertEqual(self.fx.report(), result)

    def test_missing_provider_configuration_cannot_hide_persisted_split(self):
        self.fx.fx.communities.provider_actions = None
        with self.assertRaisesRegex(PermissionError, '^COMMUNITY_EARNINGS_PROVIDER_UNAVAILABLE$'):
            self.fx.report()

    def test_no_split_records_and_no_provider_configuration_remains_genuine_zero(self):
        with self.c.tx():
            self.c.db.execute("DELETE FROM links WHERE channel='COMMUNITY_PROVIDER_ACTION'")
        self.fx.fx.communities.provider_actions = None
        result = self.fx.report()
        self.assertEqual(result['records'], [])
        self.assertEqual(result['page_gross_minor'], 0)

    def test_inactive_frozen_snapshot_is_explicit_failure_until_restored(self):
        with self.c.tx():
            self.c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_SPLIT_RULES_V1' AND subject_idx=?", (self.fx.snapshot_key,))
        self.assert_earnings_denied()
        with self.c.tx():
            self.c.db.execute("UPDATE links SET active=1 WHERE channel='COMMUNITY_SPLIT_RULES_V1' AND subject_idx=?", (self.fx.snapshot_key,))
        self.assertEqual(self.fx.report()['page_gross_minor'], 10)

    def test_missing_frozen_snapshot_is_explicit_failure(self):
        with self.c.tx():
            self.c.db.execute("DELETE FROM links WHERE channel='COMMUNITY_SPLIT_RULES_V1' AND subject_idx=?", (self.fx.snapshot_key,))
        self.assert_earnings_denied()

    def test_foreign_project_snapshot_cannot_fill_missing_original(self):
        with self.c.tx():
            self.c.db.execute("UPDATE links SET project='unrelated' WHERE channel='COMMUNITY_SPLIT_RULES_V1' AND subject_idx=?", (self.fx.snapshot_key,))
        self.assert_earnings_denied()


if __name__ == '__main__':
    unittest.main()
