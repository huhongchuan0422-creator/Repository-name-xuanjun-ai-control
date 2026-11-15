"""Synthetic original HTTP/Center/SQLite contract, never a live host probe."""
import json
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_community_mini_center_identity as fixtures
from scripts.community_mini_http import serve
from scripts.community_merchant_store import profile


class StorefrontUnavailableContract(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ExistingCenterComposition()
        self.fx.setUp()
        self.scene = 'owner-test-354d1fac'  # Same syntax, no real scene/account data.
        self.fx.identity.scenes[self.scene] = self.fx.identity.scenes.pop('shop1')
        self.token = self.fx.token()
        self.server = serve(self.fx.gateway)
        self.server.timeout = 3

    def tearDown(self):
        self.server.server_close()
        self.fx.tearDown()

    def call(self, *, scene=None, params=None, token=None, operation='community.storefront'):
        body = dict(scene=self.scene if scene is None else scene,
                    operation=operation,params={} if params is None else params)
        def send():
            request = urllib.request.Request(
                'http://127.0.0.1:%s/mini/api' % self.server.server_port,
                json.dumps(body).encode(), headers={'Content-Type':'application/json',
                'X-Community-Session':self.token if token is None else token})
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                return error.code, json.load(error)
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(send)
            self.server.handle_request()
            return future.result()

    def missing(self):
        self.fx.stage.api.bindings[self.fx.stage.customer] = dict(
            self.fx.stage.api.bindings[self.fx.stage.customer],store_id='not-created')

    def test_valid_empty_params_with_active_original_profile_is_success(self):
        changes = (self.fx.center.db.total_changes,self.fx.stage.m.total_changes)
        status, body = self.call()
        self.assertEqual(status,200)
        self.assertEqual(body['result']['merchant']['name'],'Demo Merchant A')
        self.assertFalse(body['payment_enabled'])
        self.assertEqual(changes,(self.fx.center.db.total_changes,self.fx.stage.m.total_changes))

    def test_active_profile_with_no_visible_products_is_still_a_valid_storefront(self):
        self.fx.stage.m.execute("UPDATE catalog_items SET status='HIDDEN'")
        status, body = self.call()
        self.assertEqual(status,200)
        self.assertEqual(body['result']['merchant']['name'],'Demo Merchant A')
        self.assertEqual(body['result']['products'],[])

    def test_missing_and_paused_profiles_have_same_fixed_failure_without_data(self):
        self.fx.stage.m.execute("UPDATE merchant_profiles SET status='PAUSED'")
        for state in ('paused','missing'):
            with self.subTest(state=state):
                if state == 'missing':self.missing()
                changes = (self.fx.center.db.total_changes,self.fx.stage.m.total_changes)
                self.assertEqual(self.call(),(400,{'error':'STOREFRONT_UNAVAILABLE'}))
                self.assertEqual(changes,(self.fx.center.db.total_changes,self.fx.stage.m.total_changes))
                # Preserve authorized context discovery; unavailable is not no authority.
                status, result = self.call(scene='',operation='customer.contexts')
                self.assertEqual(status,200)
                row = result['result']['contexts'][0]
                self.assertEqual(row['storefront_state'],'UNAVAILABLE')
                self.assertIsNone(row['merchant'])

    def test_missing_profile_does_not_leak_before_session_or_scene_authority(self):
        self.missing()
        for change in ({'token':''},{'token':'x'*32},{'scene':'unregistered'}):
            with self.subTest(change=change):
                self.assertEqual(self.call(**change),(403,{'error':'ACCESS_DENIED'}))
        # Verified second account loses its project membership, but keeps a real session.
        second = self.fx.token('second-code','openid2')
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid2,))
        self.assertEqual(self.call(token=second),(403,{'error':'ACCESS_DENIED'}))
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        self.assertEqual(self.call(),(403,{'error':'ACCESS_DENIED'}))

    def test_cross_tenant_scene_cannot_disclose_profile_state(self):
        self.fx.identity.scenes['foreign'] = dict(project='project1',principal=self.fx.stage.other)
        self.assertEqual(self.call(scene='foreign'),(403,{'error':'ACCESS_DENIED'}))

    def test_bad_fields_and_bad_scene_keep_original_generic_400(self):
        self.missing()
        for change in ({'params':{'tenant_id':'tenant2'}},{'params':[]},
                       {'scene':''},{'scene':'../invalid'},{'scene':'x'*33}):
            with self.subTest(change=change):
                self.assertEqual(self.call(**change),(400,{'error':'INVALID_REQUEST'}))

    def test_untyped_same_text_and_unknown_errors_are_not_classified(self):
        for error in (ValueError('UNAVAILABLE_STOREFRONT'),ValueError('PRIVATE_DETAIL'),
                      TypeError('PRIVATE_DETAIL'),KeyError('PRIVATE_DETAIL')):
            with self.subTest(error=type(error).__name__):
                with patch.object(self.fx.stage.api,'dispatch',side_effect=error):
                    self.assertEqual(self.call(),(400,{'error':'INVALID_REQUEST'}))

    def test_unavailable_store_from_identity_stage_is_not_classified(self):
        from scripts.community_merchant_store import StorefrontUnavailable
        with patch.object(self.fx.identity,'resolve',side_effect=StorefrontUnavailable()):
            self.assertEqual(self.call(),(400,{'error':'INVALID_REQUEST'}))

    def test_unavailable_store_exception_does_not_change_other_operations(self):
        from scripts.community_merchant_store import StorefrontUnavailable
        with patch.object(self.fx.stage.api,'dispatch',side_effect=StorefrontUnavailable()):
            self.assertEqual(self.call(operation='community.qr',params={'context':'mini'}),
                             (400,{'error':'INVALID_REQUEST'}))
            self.assertEqual(self.call(params={'unexpected':'field'}),
                             (400,{'error':'INVALID_REQUEST'}))

    def test_original_profile_callers_still_receive_same_value_error_contract(self):
        self.missing()
        with self.assertRaisesRegex(ValueError,'^UNAVAILABLE_STOREFRONT$'):
            profile(self.fx.stage.m,self.fx.stage.api.bindings[self.fx.stage.customer])


class PublicDirectoryUnavailableCompatibility(unittest.TestCase):
    def setUp(self):
        import test_community_public_directory as public_fixtures
        self.public = public_fixtures.PublicDirectory()
        self.public.setUp()
        self.addCleanup(self.public.doCleanups)
        self.public.publish()
        self.record = self.public.directory()['records'][0]

    def assert_filtered(self):
        from scripts.community_merchant_store import StorefrontUnavailable
        with self.assertRaises(StorefrontUnavailable) as caught:
            profile(self.public.fx.db,self.public.ops.grants['merchant']['scope'])
        self.assertIsInstance(caught.exception,ValueError)
        self.assertEqual(str(caught.exception),'UNAVAILABLE_STOREFRONT')
        self.assertEqual(self.public.directory()['records'],[])
        with self.assertRaises(PermissionError):
            self.public.directory('customer.store',{'id':self.record['id']})

    def test_paused_original_profile_still_filters_published_directory_and_detail(self):
        self.public.fx.db.execute("UPDATE merchant_profiles SET status='PAUSED'")
        self.assert_filtered()

    def test_missing_original_profile_still_filters_published_directory_and_detail(self):
        # Synthetic original store only; no change to publication or authority.
        for table in ('catalog_item_content','catalog_items','merchant_profiles'):
            self.public.fx.db.execute('DELETE FROM '+table)
        self.assert_filtered()

    def test_unknown_profile_value_error_is_not_swallowed_by_directory(self):
        with patch('scripts.community_public_directory.profile',side_effect=ValueError('OTHER_FAILURE')):
            with self.assertRaisesRegex(ValueError,'^OTHER_FAILURE$'):
                self.public.directory()


if __name__ == '__main__':unittest.main()
