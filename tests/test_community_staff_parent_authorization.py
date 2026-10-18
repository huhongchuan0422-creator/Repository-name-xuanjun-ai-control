"""Staff management requires the parent's current original runtime authority."""
import unittest

import test_community_center_operations as fixtures


class StaffParentAuthorization(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ExistingCenterOperations()
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.parent = self.fx.operations.grants['merchant']
        self.principal = self.parent['principal']
        self.bindings = self.fx.fx.stage.api.bindings
        self.workspace = self.call('staff_grant', dict(
            user_id=self.fx.fx.uid2, operations=['community.merchant_settings']))['workspace']

    def call(self, operation, params):
        return self.fx.call(self.fx.body('merchant', 'community.' + operation, params))

    def assert_all_management_denied_without_writes(self):
        before = list(self.fx.fx.center.db.iterdump())
        operations = (
            ('staff_list', dict(after_id='')),
            ('staff_grant', dict(user_id=self.fx.fx.uid2, operations=['community.orders'])),
            ('staff_remove', dict(workspace=self.workspace)),
            ('staff_invite', dict(email='two@example.org', project_role='VIEWER')),
        )
        for operation, params in operations:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(PermissionError, '^STAFF_PARENT_GRANT_CHANGED$'):
                    self.call(operation, params)
        self.assertEqual(list(self.fx.fx.center.db.iterdump()), before)

    def test_removed_runtime_binding_denies_management_until_restored(self):
        original = self.bindings.pop(self.principal)
        self.assert_all_management_denied_without_writes()
        self.bindings[self.principal] = original
        records = self.call('staff_list', dict(after_id=''))['records']
        self.assertEqual([row['workspace'] for row in records], [self.workspace])
        self.assertEqual(records[0]['operations'], ['community.merchant_settings'])
        self.assertIs(records[0]['active'], True)
        self.assertIs(self.call('staff_remove', dict(workspace=self.workspace))['active'], False)

    def test_rebound_parent_store_denies_all_management(self):
        self.bindings[self.principal] = dict(self.parent['scope'], store_id='other-store')
        self.assert_all_management_denied_without_writes()

    def test_changed_parent_principal_role_denies_all_management(self):
        self.principal.role = 'STORE_STAFF'
        self.assert_all_management_denied_without_writes()

    def test_changed_parent_principal_tenant_denies_all_management(self):
        self.principal.tenant_id = 'other-tenant'
        self.assert_all_management_denied_without_writes()


if __name__ == '__main__':
    unittest.main()
