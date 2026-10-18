"""Original basket recovery across real SQLite boundaries; no provider IO."""
import concurrent.futures
import copy
import json
import threading
import unittest
import urllib.request
from unittest.mock import patch

import test_community_mini_center_identity as fixtures
from scripts.community_center_operations import CenterOperations
from scripts.community_commerce import Commerce
from scripts.community_demo_bootstrap import DEMO_SCOPE
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_mini_http import serve
from scripts.community_order_store import connect, create_order, state
from scripts.pr122_customer_core import Center, canonical


class PurchaseRecovery(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ExistingCenterComposition(); self.fx.setUp()
        self.token = self.fx.token()
        self.configure()
        self.price_set(0, 101, 10)
        self.original = dict(reference='interrupted', lines=[dict(item_id='sample_item', quantity=2, revision=1)])

    def tearDown(self):
        self.fx.tearDown()

    def configure(self):
        grant = dict(user_id=self.fx.uid1, project='project1', project_roles=['OWNER'], principal=self.fx.stage.merchant)
        self.commerce = Commerce(CenterOperations(self.fx.center, self.fx.stage.api, {'merchant': grant}), self.fx.identity)
        self.fx.gateway.commerce = self.commerce
        self.web = self.fx.center.login('one@example.org', 'FixturePassword123!')

    def price_set(self, revision, price, stock):
        return self.commerce.dispatch(self.web['token'], self.web['csrf'], dict(workspace='merchant', operation='price_set',
            params=dict(item_id='sample_item', expected_revision=revision, unit_minor=price, stock=stock, enabled=True)))

    def price(self):
        return self.commerce._read(DEMO_SCOPE, 'project1', 'PRODUCT', 'sample_item')

    def reserve(self):
        with patch('scripts.community_commerce.create_order', side_effect=RuntimeError('INTERRUPTED_AFTER_RESERVATION')):
            with self.assertRaisesRegex(RuntimeError, 'INTERRUPTED_AFTER_RESERVATION'):
                self.commerce.consumer(self.token, 'shop1', 'purchase', self.original)
        self.assertEqual((self.price()['stock'], self.price()['revision']), (8, 2))
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 0)

    def recover(self, token=None, params=None):
        return self.commerce.consumer(token or self.token, 'shop1', 'purchase_recover',
            params if params is not None else dict(reference='interrupted'))

    def test_reopen_and_price_or_catalog_change_recover_original_amount_without_stock_write(self):
        self.reserve()
        records = self.commerce.consumer(self.token, 'shop1', 'orders', {'after_id': ''})['records']
        self.assertEqual(records[0]['order']['state'], 'CREATION_UNKNOWN_RECOVER_SAME_REFERENCE')
        self.price_set(2, 999, 7)
        self.fx.stage.demo.merchant_db.execute("UPDATE catalog_items SET status='HIDDEN'")
        self.fx.stage.demo.merchant_db.commit()
        self.fx.reopen(); self.configure()
        before = self.price()
        first = self.recover()
        self.assertEqual(first['amount_minor'], 202)
        self.assertEqual(first['lines'][0]['revision'], 1)
        self.assertEqual(first['lines'][0]['unit_minor'], 101)
        self.assertEqual(first['order']['state'], 'PENDING')
        for _ in range(3):
            self.assertEqual(self.recover(), first)
        self.assertEqual(self.price(), before)
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 1)
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM order_events').fetchone()[0], 0)

    def test_original_purchase_retry_and_explicit_recovery_share_same_unique_order(self):
        self.reserve()
        first = self.commerce.consumer(self.token, 'shop1', 'purchase', self.original)
        self.assertEqual(self.recover(), first)
        self.assertEqual((self.price()['stock'], self.price()['revision']), (8, 2))

    def test_original_mini_http_routes_reference_only_recovery(self):
        self.reserve()
        server = serve(self.fx.gateway, commerce=self.commerce)
        try:
            def send():
                request = urllib.request.Request('http://127.0.0.1:' + str(server.server_port) + '/mini/api',
                    data=json.dumps(dict(scene='shop1', operation='commerce.purchase_recover',
                        params=dict(reference='interrupted'))).encode(),
                    headers={'Content-Type': 'application/json', 'X-Community-Session': self.token})
                with urllib.request.urlopen(request, timeout=3) as response:
                    return json.load(response)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(send); server.handle_request(); result = pending.result()
            self.assertIs(result['payment_enabled'], False)
            self.assertEqual(result['result']['reference'], 'interrupted')
            self.assertEqual(result['result']['order']['state'], 'PENDING')
            self.assertEqual((self.price()['stock'], self.price()['revision']), (8, 2))
        finally:
            server.server_close()

    def test_failure_after_order_commit_is_recoverable_without_another_reservation(self):
        self.reserve()
        audit = self.fx.center.audit
        def fail_after_order(project, actor, event, reference):
            if event == 'COMMUNITY_BASKET_ORDER_RECOVERED':
                raise RuntimeError('INTERRUPTED_AFTER_ORIGINAL_ORDER_COMMIT')
            return audit(project, actor, event, reference)
        with patch.object(self.fx.center, 'audit', side_effect=fail_after_order):
            with self.assertRaisesRegex(RuntimeError, 'AFTER_ORIGINAL_ORDER_COMMIT'):
                self.recover()
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 1)
        self.fx.reopen(); self.configure()
        self.assertEqual(self.recover()['order']['state'], 'PENDING')
        self.assertEqual((self.price()['stock'], self.price()['revision']), (8, 2))

    def test_different_customer_cannot_recover_and_existing_amount_only_order_cannot_be_claimed(self):
        self.reserve()
        other = self.fx.token('second', 'openid2')
        with self.assertRaises(PermissionError): self.recover(other)
        create_order(self.fx.stage.o, DEMO_SCOPE, 'legacy', 202)
        with self.assertRaises(PermissionError): self.recover(params=dict(reference='legacy'))
        with self.assertRaises(PermissionError): self.recover(params=dict(reference='missing'))
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 1)
        self.assertEqual((self.price()['stock'], self.price()['revision']), (8, 2))

    def test_client_cannot_supply_new_price_lines_amount_or_identity(self):
        self.reserve()
        for field, value in [('lines', self.original['lines']), ('amount_minor', 1), ('user_id', self.fx.uid1), ('project', 'project1')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.recover(params=dict(reference='interrupted', **{field: value}))
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 0)

    def test_revoked_membership_is_rechecked_before_recovery(self):
        self.reserve()
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?', (self.fx.uid1,))
        with self.assertRaises(PermissionError): self.recover()
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 0)

    def test_revoked_session_provider_link_and_ownership_cannot_recover(self):
        self.reserve()
        c = self.fx.center
        c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_ORDER'")
        with self.assertRaises(PermissionError): self.recover()
        c.db.execute("UPDATE links SET active=1 WHERE channel='COMMUNITY_ORDER'")
        c.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI'")
        with self.assertRaises(PermissionError): self.recover()
        c.db.execute("UPDATE links SET active=1 WHERE channel='WECHAT_MINI'")
        c.logout(self.token)
        with self.assertRaises(PermissionError): self.recover()
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 0)

    def test_expiry_after_acquiring_order_lock_does_not_create_order(self):
        self.reserve()
        resolve = self.fx.identity._resolve; calls = []
        def expired(token, scene):
            calls.append(scene)
            if len(calls) == 3: self.fx.stage.now += 3601
            return resolve(token, scene)
        with patch.object(self.fx.identity, '_resolve', side_effect=expired):
            with self.assertRaises(PermissionError): self.recover()
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 0)

    def test_changed_original_amount_is_not_overwritten(self):
        self.reserve()
        create_order(self.fx.stage.o, DEMO_SCOPE, 'interrupted', 203)
        with self.assertRaisesRegex(PermissionError, 'ORIGINAL_BASKET_ORDER_MISMATCH'): self.recover()
        self.assertEqual(state(self.fx.stage.o, DEMO_SCOPE, 'interrupted')['amount_minor'], 203)

    def test_terminal_original_order_is_never_reopened(self):
        self.reserve(); self.recover()
        self.fx.stage.o.execute("UPDATE orders SET state='CANCELLED' WHERE reference='interrupted'")
        self.fx.stage.o.commit()
        self.assertEqual(self.recover()['order']['state'], 'CANCELLED')
        self.assertEqual((self.price()['stock'], self.price()['revision']), (8, 2))

    def test_corrupt_frozen_reservation_or_ownership_fails_closed(self):
        self.reserve()
        original = self.commerce._read(DEMO_SCOPE, 'project1', 'ORDER', 'interrupted')
        variants = [dict(original, request_hash='0'*64), dict(original, amount_minor=203),
            dict(original, stock_reserved=False), dict(original, stock_released=True),
            dict(original, lines=[dict(original['lines'][0], revision=True)]),
            dict(original, lines=[dict(original['lines'][0], subtotal_minor=1)])]
        for value in variants:
            with self.fx.center.tx():
                self.commerce._save(DEMO_SCOPE, 'project1', self.fx.uid1, 'ORDER', 'interrupted', value, True)
            with self.subTest(value=value), self.assertRaises((ValueError, PermissionError)): self.recover()
        with self.fx.center.tx():
            self.commerce._save(DEMO_SCOPE, 'project1', self.fx.uid1, 'ORDER', 'interrupted', original, True)
        self.fx.center.db.execute("UPDATE links SET user_id=? WHERE channel='COMMUNITY_ORDER'", (self.fx.uid2,))
        with self.assertRaises(PermissionError): self.recover()
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 0)

    def test_concurrent_connections_create_one_order_and_never_reserve_again(self):
        self.reserve()
        gate = threading.Barrier(4)
        def worker():
            c = Center(self.fx.tmp.name, {'testkey': b'k'*32}, 'testkey', clock=lambda: self.fx.stage.now, mail_ready=True)
            db = connect(self.fx.stage.order_path)
            try:
                runtime = copy.copy(self.fx.stage.api)
                runtime.demo = copy.copy(runtime.demo); runtime.demo.db = db
                identity = CenterIdentity(c, runtime, self.fx.identity.appid, self.fx.scenes)
                grant = dict(user_id=self.fx.uid1, project='project1', project_roles=['OWNER'], principal=self.fx.stage.merchant)
                commerce = Commerce(CenterOperations(c, runtime, {'merchant': grant}), identity)
                gate.wait(timeout=10)
                return commerce.consumer(self.token, 'shop1', 'purchase_recover', dict(reference='interrupted'))
            finally:
                db.close(); c.db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: worker(), range(4)))
        self.assertTrue(all(r['order']['state'] == 'PENDING' and r['amount_minor'] == 202 for r in results))
        self.assertEqual(self.fx.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0], 1)
        self.assertEqual((self.price()['stock'], self.price()['revision']), (8, 2))
        self.assertEqual(self.fx.center.check_integrity()['integrity'], 'PASS')


if __name__ == '__main__': unittest.main()
