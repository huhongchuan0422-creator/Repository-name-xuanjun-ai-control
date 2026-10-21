"""Platform mini login must not depend on optional SaaS/CRM consumption work."""
import unittest
from unittest.mock import patch
import test_community_mini_center_identity as original
from scripts.authorization_consumption_community import ConsumptionReservation, SCHEMA


class PlatformLoginIndependence(unittest.TestCase):
    def setUp(self):
        self.fixture = original.ExistingCenterComposition()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_original_mini_login_and_store_do_not_call_optional_saas_consumer(self):
        with patch.object(ConsumptionReservation, 'dispatch', side_effect=AssertionError('SaaS consumer must not be called')) as consumer:
            token = self.fixture.token()
            result = self.fixture.call(token, 'community.storefront')
            self.assertEqual(result['merchant']['name'], 'Demo Merchant A')
            consumer.assert_not_called()

    def test_optional_unknown_reservation_does_not_block_original_platform_login(self):
        c = self.fixture.center
        scope = dict(caller='synthetic-saas', audience='synthetic-saas', user_id=self.fixture.uid1, tenant_id='tenant1', project_id='project1', operation='community.access')
        request = dict(scope, schema=SCHEMA, request_id='optional_request', issued_unix=c.now(), expires_unix=c.now()+20, authorization_token='synthetic-opaque')
        ConsumptionReservation(c).reserve(request, scope, dict(workspace='optional', operation='community.orders', params={}), 'optional_reference')
        token = self.fixture.token()
        self.assertIn('merchant', self.fixture.call(token, 'community.storefront'))

    def test_unknown_wechat_subject_is_not_auto_registered_or_linked(self):
        c = self.fixture.center
        before = c.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        with self.assertRaisesRegex(original.LoginUnavailable, 'LOGIN_RESULT_UNKNOWN_OR_REJECTED'):
            self.fixture.token(openid='unlinked-platform-subject')
        self.assertEqual(c.db.execute('SELECT count(*) FROM accounts').fetchone()[0], before)
        self.assertIsNone(c.db.execute("SELECT 1 FROM links WHERE channel='WECHAT_MINI' AND subject_idx=?", (self.fixture.identity._subject(self.fixture.identity.appid, 'unlinked-platform-subject'),)).fetchone())


if __name__ == '__main__':
    unittest.main()
