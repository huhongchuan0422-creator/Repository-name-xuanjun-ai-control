"""Original catalog pagination and explicitly delegated staff reads, offline."""
import json
import pathlib
import shutil
import subprocess
import unittest

import test_community_center_operations as fixtures
from scripts.community_commerce import Commerce
from scripts.community_demo_bootstrap import DEMO_SCOPE

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CatalogPagination(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ExistingCenterOperations(); self.fx.setUp()
        self.c = self.fx.fx.center
        self.commerce = Commerce(self.fx.operations, self.fx.fx.identity)
        self.token = self.fx.fx.token()
        self.db = self.fx.fx.stage.api.demo.merchant_db
        self.db.execute('DELETE FROM catalog_items'); self.db.commit()

    def tearDown(self): self.fx.tearDown()

    def seed(self, count, *, priced=True, offset=0, identity=None):
        identity = identity or DEMO_SCOPE
        t, m, s = [identity[k] for k in ('tenant_id', 'merchant_id', 'store_id')]
        if identity != DEMO_SCOPE:
            self.db.execute('INSERT OR IGNORE INTO merchant_profiles VALUES(?,?,?,?,?,?,?,1)',
                            (t, m, s, 'Other store', 'Private', 'Private', 'ACTIVE'))
        expected = []
        with self.db:
            for n in range(offset, offset + count):
                item = 'item_' + format(n, '04d'); sort = n % 3 - 1
                self.db.execute('INSERT INTO catalog_items VALUES(?,?,?,?,?,?,?,1)',
                                (t, m, s, item, 'Product ' + str(n), 'ACTIVE', sort))
                expected.append((sort, item))
        if priced:
            with self.c.tx():
                for _, item in expected:
                    self.commerce._save(identity, 'project1', self.fx.fx.uid1, 'PRODUCT', item,
                                        dict(item_id=item, unit_minor=101, revision=1, stock=10,
                                             currency='CNY', enabled=True))
        return [item for _, item in sorted(expected)]

    def products(self, params=None, token=None):
        return self.commerce.consumer(token or self.token, 'shop1', 'products', params or {})

    def settings(self, params=None, workspace='merchant', web=None):
        return self.fx.call(self.fx.body(workspace, 'community.merchant_settings', params), web=web)

    def test_consumer_catalog_more_than_100_preserves_sort_ties_and_complete_scope(self):
        expected = self.seed(215)
        self.seed(4, identity=dict(DEMO_SCOPE, store_id='other'), offset=500)
        first = self.products(); self.assertEqual(first, self.products({'after_id': ''}))
        pages = [first]
        while pages[-1]['has_more']:
            pages.append(self.products({'after_id': pages[-1]['next_cursor']}))
        ids = [v['item_id'] for page in pages for v in page['products']]
        self.assertEqual(ids, expected); self.assertEqual(len(set(ids)), 215)
        self.assertEqual([len(p['products']) for p in pages], [100, 100, 15])
        self.assertIsNone(pages[-1]['next_cursor'])
        self.assertEqual(pages[1], self.products({'after_id': pages[0]['next_cursor']}))

    def test_sparse_unpriced_page_advances_to_sellable_product(self):
        self.seed(101, priced=False)
        ordered = self.db.execute('SELECT item_id,sort_order FROM catalog_items ORDER BY sort_order,item_id').fetchall()
        target = ordered[-1][0]
        with self.c.tx():
            self.commerce._save(DEMO_SCOPE, 'project1', self.fx.fx.uid1, 'PRODUCT', target,
                                dict(item_id=target, unit_minor=10, revision=1, stock=0, enabled=True))
        first = self.products(); self.assertEqual(first['products'], []); self.assertTrue(first['has_more'])
        second = self.products({'after_id': first['next_cursor']})
        self.assertEqual([p['item_id'] for p in second['products']], [target])
        self.assertFalse(second['products'][0]['available']); self.assertFalse(second['has_more'])

    def test_exact_page_boundary_hidden_and_disabled_items(self):
        self.seed(100)
        self.db.execute("UPDATE catalog_items SET status='HIDDEN' WHERE item_id='item_0000'"); self.db.commit()
        with self.c.tx():
            price = self.commerce._read(DEMO_SCOPE, 'project1', 'PRODUCT', 'item_0001')
            self.commerce._save(DEMO_SCOPE, 'project1', self.fx.fx.uid1, 'PRODUCT', 'item_0001', dict(price, enabled=False), True)
        result = self.products(); self.assertEqual(len(result['products']), 98)
        self.assertFalse(result['has_more']); self.assertIsNone(result['next_cursor'])

    def test_invalid_product_cursor_and_extra_authority_fields_fail_closed(self):
        for cursor in (None, True, 2, {}, [], 'x', '{}', '[true,"item_1"]', '[0,"bad id"]',
                       '[9223372036854775808,"item_1"]', '[0,"item_1",1]', 'x' * 161):
            with self.subTest(cursor=cursor), self.assertRaisesRegex(ValueError, 'INVALID_PRODUCT_CURSOR'):
                self.products({'after_id': cursor})
        for key in ('tenant_id', 'store_id', 'user_id', 'limit', 'role'):
            with self.assertRaisesRegex(ValueError, 'INVALID_CONSUMER_COMMERCE_FIELDS'):
                self.products({'after_id': '', key: 'other'})

    def test_continuation_rechecks_original_membership(self):
        self.seed(101); cursor = self.products()['next_cursor']
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?', (self.fx.fx.uid1,))
        with self.assertRaises(PermissionError): self.products({'after_id': cursor})

    def test_workbench_more_than_200_and_legacy_empty_request(self):
        expected = self.seed(215)
        self.seed(2, identity=dict(DEMO_SCOPE, store_id='other'), offset=500)
        self.db.execute("UPDATE catalog_items SET status='HIDDEN' WHERE item_id='item_0000'"); self.db.commit()
        first = self.settings(); self.assertEqual(first, self.settings({'after_id': ''}))
        self.assertEqual(len(first['items']), 200); self.assertTrue(first['has_more'])
        second = self.settings({'after_id': first['next_cursor']})
        self.assertEqual([x['id'] for x in first['items'] + second['items']], sorted(expected))
        self.assertFalse(second['has_more']); self.assertIsNone(second['next_cursor'])
        self.assertEqual(first['profile'], second['profile'])
        self.assertEqual(first['items'][0]['status'], 'HIDDEN')
        for cursor in (None, 1, True, [], "' OR 1=1", 'a' * 65):
            with self.assertRaises(ValueError): self.settings({'after_id': cursor})

    def grant(self, permissions=None):
        result = self.fx.call(self.fx.body('merchant', 'community.staff_grant',
                             dict(user_id=self.fx.fx.uid2, operations=permissions or ['community.merchant_settings'])))
        return result['workspace']

    def test_explicit_delegation_reads_catalog_only_and_static_staff_stays_denied(self):
        self.seed(201); workspace = self.grant()
        first = self.settings(workspace=workspace, web=self.fx.other)
        second = self.settings({'after_id': first['next_cursor']}, workspace, self.fx.other)
        self.assertEqual(len(first['items']) + len(second['items']), 201)
        self.assertEqual(first['profile']['name'], 'Demo Merchant A')
        with self.assertRaises(PermissionError): self.settings(workspace='staff')
        for operation in ('community.item', 'community.profile', 'community.orders', 'community.orders_export'):
            with self.assertRaises(PermissionError):
                self.fx.call(self.fx.body(workspace, operation), web=self.fx.other)
        with self.assertRaises(PermissionError): self.settings(workspace=workspace)
        with self.assertRaises(ValueError): self.settings({'after_id': '', 'store_id': 'other'}, workspace, self.fx.other)

    def test_staff_revocation_and_changed_permissions_apply_on_next_page(self):
        self.seed(201); workspace = self.grant()
        cursor = self.settings(workspace=workspace, web=self.fx.other)['next_cursor']
        self.grant(['community.orders'])
        with self.assertRaises(PermissionError): self.settings({'after_id': cursor}, workspace, self.fx.other)
        self.grant()
        self.fx.call(self.fx.body('merchant', 'community.staff_remove', {'workspace': workspace}))
        with self.assertRaises(PermissionError): self.settings({'after_id': cursor}, workspace, self.fx.other)

    def test_staff_live_member_and_parent_scope_change_are_denied(self):
        workspace = self.grant()
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?', (self.fx.fx.uid2,))
        with self.assertRaises(PermissionError): self.settings(workspace=workspace, web=self.fx.other)
        self.c.db.execute('UPDATE members SET active=1 WHERE user_id=?', (self.fx.fx.uid2,))
        self.fx.operations.grants['merchant']['scope'] = dict(DEMO_SCOPE, store_id='other')
        with self.assertRaises(PermissionError): self.settings(workspace=workspace, web=self.fx.other)

    def test_staff_parent_principal_binding_and_owner_role_are_live(self):
        workspace = self.grant()
        parent = self.fx.operations.grants['merchant']
        self.fx.fx.stage.api.bindings[parent['principal']] = dict(DEMO_SCOPE, store_id='other')
        with self.assertRaises(PermissionError): self.settings(workspace=workspace, web=self.fx.other)
        self.fx.fx.stage.api.bindings[parent['principal']] = dict(DEMO_SCOPE)
        self.c.db.execute("UPDATE members SET role='EDITOR' WHERE user_id=?", (self.fx.fx.uid1,))
        with self.assertRaises(PermissionError): self.settings(workspace=workspace, web=self.fx.other)

    def test_workbench_pagination_dom(self):
        node = shutil.which('node')
        if not node: self.skipTest('Node unavailable')
        subprocess.run([node, str(ROOT/'tests/community_workbench_catalog_dom.cjs'),
                        str(ROOT/'demos/community-stage/workbench.js'),
                        str(ROOT/'demos/community-stage/workbench.html')], check=True, timeout=30)


if __name__ == '__main__': unittest.main()
