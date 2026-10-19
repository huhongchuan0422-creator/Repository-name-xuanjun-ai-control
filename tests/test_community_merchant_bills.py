"""Real Center authorizations and original ledgers; no network or real grants."""
import copy
import hashlib
import io
import json
import tempfile
from email.message import Message
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_community_provider_bills as fixtures
import test_community_profitsharing_bill_schema as split_fixtures
from scripts.community_merchant_bills import MerchantBills, PERMISSION, CHANNEL, AUDIT_CHANNEL
from scripts.community_mini_http import make_handler
from scripts.community_order_store import create_order
from scripts.community_provider_reference import provider_order_reference
from scripts.pr122_customer_core import canonical


class MerchantBillAccess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BillJourney.setUpClass()

    def setUp(self):
        self.j = fixtures.BillJourney()
        self.j.setUp()
        self.addCleanup(self.j.tearDown)
        self.a, self.c = self.j.fx.actions, self.j.fx.c
        self.web, self.date = self.j.fx.web, self.j.date
        self.g, self.policy = self.a._authorize(self.web['token'], self.web['csrf'], 'finance')
        self.grant = dict(finance_workspace='finance', user_id=self.g['user_id'],
            project=self.g['project'], tenant_id=self.g['scope']['tenant_id'],
            merchant_id=self.g['scope']['merchant_id'], sp_mchid=self.a.reader._mchid,
            sub_mchid=self.policy['sub_mchid'], revision=1, permission=PERMISSION)
        self.service = MerchantBills(self.a, {'all-stores': self.grant})
        self.other = dict(self.g['scope'], store_id='second-store')
        self.a.bindings[tuple(self.other.values())] = copy.deepcopy(self.policy)
        for target in ('socket.socket.connect', 'socket.socket.bind'):
            guard = patch(target, side_effect=AssertionError('NO_NETWORK_OR_LISTENER'))
            guard.start()
            self.addCleanup(guard.stop)

    def call(self, op, kind='TRADE', workspace='all-stores', **extra):
        return self.service.dispatch(self.web['token'], self.web['csrf'],
            dict(workspace=workspace, operation=op, params=dict(kind=kind, bill_date=self.date, **extra)))

    def download(self, raw):
        self.a._call = Mock(return_value=(dict(hash_type='SHA1', hash_value=hashlib.sha1(raw).hexdigest(),
            download_url='https://api.mch.weixin.qq.com/v3/bill/downloadurl?token=synthetic'), 'a' * 64))
        self.service.bills._download = Mock(return_value=raw)

    def seed(self, target, ref, amount):
        db = self.a.runtime.demo.db
        create_order(db, target, ref, amount)
        tx = 'tx-' + target['store_id'] + '-' + ref
        db.execute('UPDATE orders SET state=?,provider_transaction_id=? WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',
            ('SUCCESS', tx, target['tenant_id'], target['merchant_id'], target['store_id'], ref))
        db.commit()
        return ','.join((provider_order_reference(self.a.reader._mchid, target, ref), tx,
            'SUCCESS', '%d.%02d' % divmod(amount, 100), self.policy['sub_mchid'], 'private-openid', 'private-card'))

    def trade(self, *rows):
        return ('商户订单号,微信订单号,交易状态,订单金额,特约商户号,用户标识,银行卡号\n' + '\n'.join(rows) + '\n').encode()

    def cache_count(self):
        return self.c.db.execute('SELECT COUNT(*) FROM links WHERE channel=?', (CHANNEL,)).fetchone()[0]

    def test_default_empty_explicit_grants_deny_even_platform_owner(self):
        self.service = MerchantBills(self.a)
        self.a._call = Mock(side_effect=AssertionError('NO_PROVIDER_CALL'))
        with self.assertRaises(PermissionError):
            self.call('bill_fetch')
        self.a._call.assert_not_called()
        self.assertEqual(self.cache_count(), 0)

    def test_exact_grant_schema_and_integer_revision(self):
        for key, value in [('permission', 'ALL'), ('revision', True), ('revision', 0),
                           ('sub_mchid', '../wrong'), ('sp_mchid', 1234567890)]:
            with self.subTest(key=key), self.assertRaises(PermissionError):
                MerchantBills(self.a, {'all-stores': dict(self.grant, **{key: value})})
        with self.assertRaises(PermissionError):
            MerchantBills(self.a, {'all-stores': dict(self.grant, allowed_operations=['refund'])})

    def test_two_stores_match_once_and_never_claim_provider_completeness(self):
        raw = self.trade(self.seed(self.g['scope'], 'same-ref', 101), self.seed(self.other, 'same-ref', 202))
        self.download(raw)
        self.call('bill_fetch')
        result = self.call('bill_reconcile')
        self.assertEqual(result['matched_rows'], 2)
        self.assertEqual(result['configured_store_count'], 2)
        self.assertEqual([x['result']['total_rows'] for x in result['stores']], [1, 1])
        self.assertEqual(result['unknown_rows'], [])
        self.assertFalse(result['complete_reconciliation_available'])
        self.assertEqual(result['provider_population_completeness'], 'NOT_ESTABLISHED')
        self.assertEqual(result['summary_amounts'], 'NOT_RECONCILED')
        self.assertFalse(result['funds_retry_authorized'])
        self.assertEqual(result['finance_status'], 'UNCONFIRMED')
        self.assertFalse(result['cross_database_atomic'])
        rows = self.call('bill_rows', offset=0)['records']
        self.assertEqual(len(rows), 2)
        self.assertNotIn('private-', json.dumps(rows))
        audit = self.call('bill_audit', after_id='')
        self.assertEqual(audit['records'][0]['result'], result)
        self.assertEqual(self.a._call.call_args.args[0], 'GET')
        self.assertIn('sub_mchid=' + self.policy['sub_mchid'], self.a._call.call_args.args[1])

    def test_original_store_grant_and_cache_are_not_upgraded(self):
        before = copy.copy(self.a.operations.grants)
        self.download(self.trade(self.seed(self.other, 'foreign-store-order', 105)))
        self.call('bill_fetch')
        with self.assertRaises(ValueError):
            self.j.call('bill_rows', offset=0)
        with self.assertRaises(PermissionError):
            self.a._authorize(self.web['token'], self.web['csrf'], 'all-stores')
        self.assertEqual(before, self.a.operations.grants)
        self.assertNotIn('all-stores', self.a.operations.grants)

    def test_money_and_unknown_operations_rejected_before_side_effects(self):
        before = self.c.db.total_changes
        self.a._call = Mock(side_effect=AssertionError('NO_PROVIDER_CALL'))
        for op in ('refund', 'split', 'split_return', 'query_refund', 'prepay', 'rule_activate',
                   'split_by_rule', 'execute_refund_application', 'unknown'):
            with self.subTest(op=op), self.assertRaises(PermissionError):
                self.call(op)
        self.assertEqual(before, self.c.db.total_changes)
        self.a._call.assert_not_called()

    def test_merchant_admin_cannot_borrow_explicit_merchant_bill_grant(self):
        self.service.grants['all-stores']['finance_workspace'] = 'merchant'
        with self.assertRaises(PermissionError):
            self.call('bill_fetch')

    def test_cross_tenant_and_cross_merchant_submerchant_bindings_fail_closed(self):
        for target in (dict(self.other, tenant_id='another-tenant'), dict(self.other, merchant_id='another-merchant')):
            identity = tuple(target.values())
            self.a.bindings[identity] = copy.deepcopy(self.policy)
            with self.subTest(target=target), self.assertRaisesRegex(PermissionError, 'CROSS_SUBJECT'):
                self.call('bill_fetch')
            del self.a.bindings[identity]

    def test_grant_must_match_original_account_project_tenant_merchant_and_provider(self):
        for key, value in [('user_id', 'another-user'), ('project', 'another-project'),
                           ('tenant_id', 'another-tenant'), ('merchant_id', 'another-merchant'),
                           ('sp_mchid', '9999999999'), ('sub_mchid', '9999999998')]:
            self.service.grants['all-stores'] = dict(self.grant, **{key: value})
            with self.subTest(key=key), self.assertRaises(PermissionError):
                self.call('bill_fetch')

    def test_revocation_after_ticket_prevents_download_and_cache(self):
        self.download(self.trade())
        ticket = self.a._call.return_value
        def called(*args):
            self.service.grants.clear()
            return ticket
        self.a._call.side_effect = called
        with self.assertRaises(PermissionError):
            self.call('bill_fetch')
        self.service.bills._download.assert_not_called()
        self.assertEqual(self.cache_count(), 0)

    def test_revision_change_during_download_rejects_cache_and_audit(self):
        raw = self.trade()
        self.download(raw)
        def download(url):
            self.service.grants['all-stores']['revision'] += 1
            return raw
        self.service.bills._download.side_effect = download
        with self.assertRaisesRegex(PermissionError, 'AUTHORIZATION_CHANGED'):
            self.call('bill_fetch')
        self.assertEqual(self.cache_count(), 0)
        self.assertEqual(self.c.db.execute("SELECT COUNT(*) FROM audit WHERE event='MERCHANT_BILL_HASH_VERIFIED'").fetchone()[0], 0)

    def test_store_mapping_change_during_download_rejects_result(self):
        raw = self.trade()
        self.download(raw)
        def download(url):
            self.a.bindings[(*tuple(self.other.values())[:2], 'new-store')] = copy.deepcopy(self.policy)
            return raw
        self.service.bills._download.side_effect = download
        with self.assertRaisesRegex(PermissionError, 'AUTHORIZATION_CHANGED'):
            self.call('bill_fetch')
        self.assertEqual(self.cache_count(), 0)

    def test_original_project_revocation_blocks_cached_rows_and_audit(self):
        self.download(self.trade())
        self.call('bill_fetch')
        self.c.db.execute('UPDATE projects SET active=0 WHERE id=?', (self.grant['project'],))
        for op, args in [('bill_rows', {'offset': 0}), ('bill_audit', {'after_id': ''}), ('bill_reconcile', {})]:
            with self.subTest(op=op), self.assertRaises(PermissionError):
                self.call(op, **args)

    def test_original_account_epoch_revocation_blocks_cached_rows(self):
        self.download(self.trade())
        self.call('bill_fetch')
        self.c.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?', (self.grant['user_id'],))
        with self.assertRaises(PermissionError):
            self.call('bill_rows', offset=0)

    def test_revoke_while_decrypting_cached_rows_rejects_response(self):
        self.download(self.trade())
        self.call('bill_fetch')
        original = self.c.decrypt
        def decrypt(raw, aad):
            result = original(raw, aad)
            if aad.startswith('merchant-bill:'):
                self.service.grants.clear()
            return result
        with patch.object(self.c, 'decrypt', side_effect=decrypt), self.assertRaises(PermissionError):
            self.call('bill_rows', offset=0)

    def test_revoke_during_reconcile_audit_rolls_back_new_projection(self):
        self.download(self.trade())
        self.call('bill_fetch')
        original = self.c.audit
        def audit(*args):
            result = original(*args)
            if args[2] == 'MERCHANT_BILL_RECONCILED':
                self.service.grants.clear()
            return result
        with patch.object(self.c, 'audit', side_effect=audit), self.assertRaises(PermissionError):
            self.call('bill_reconcile')
        self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM links WHERE channel LIKE ?', (AUDIT_CHANNEL + '%',)).fetchone()[0], 0)
        self.assertEqual(self.c.db.execute("SELECT COUNT(*) FROM audit WHERE event='MERCHANT_BILL_RECONCILED'").fetchone()[0], 0)

    def test_audit_cursor_pages_include_only_this_bill_and_merchant(self):
        self.download(self.trade())
        self.call('bill_fetch')
        self.call('bill_reconcile')
        channel, payload, ref = self.c.db.execute(
            "SELECT channel,payload,subject_idx FROM links WHERE channel LIKE ?",
            (AUDIT_CHANNEL + '%',)).fetchone()
        saved = json.loads(self.c.decrypt(payload, 'merchant-bill-audit:' + ref))
        own = {ref}
        for number in range(100):
            value = dict(saved, result=dict(saved['result'], synthetic_audit_number=number))
            identity = hashlib.sha256(canonical(value)).hexdigest()
            own.add(identity)
            self.c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)', (channel, identity,
                self.grant['user_id'], self.grant['project'],
                self.c.encrypt(canonical(value), 'merchant-bill-audit:' + identity)))
        foreign_key = 'f' * 64
        foreign_channel = AUDIT_CHANNEL if channel == AUDIT_CHANNEL else AUDIT_CHANNEL + ':' + foreign_key
        for number in range(160):
            value = dict(saved, bill_key=foreign_key,
                merchant_scope=dict(saved['merchant_scope'], merchant_id='other-merchant', sub_mchid='9999999999'),
                result=dict(foreign_private_result=number))
            identity = hashlib.sha256(canonical(value)).hexdigest()
            self.c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)', (foreign_channel, identity,
                self.grant['user_id'], self.grant['project'],
                self.c.encrypt(canonical(value), 'merchant-bill-audit:' + identity)))
        self.c.db.commit()
        cursor, found, sizes = '', [], []
        for _ in range(3):
            page = self.call('bill_audit', after_id=cursor)
            sizes.append(len(page['records']))
            found.extend(item['id'] for item in page['records'])
            self.assertNotIn('foreign_private_result', json.dumps(page))
            if page['has_more']:
                self.assertIn(page['next_cursor'], own)
                self.assertEqual(page['next_cursor'], page['records'][-1]['id'])
                cursor = page['next_cursor']
            else:
                self.assertIsNone(page['next_cursor'])
                break
        self.assertEqual(sizes, [50, 50, 1])
        self.assertEqual(found, sorted(own))

    def test_unknown_local_store_row_remains_pending_without_false_exception(self):
        outside = dict(self.other, store_id='not-configured')
        self.download(self.trade(self.seed(outside, 'not-in-config', 200)))
        self.call('bill_fetch')
        result = self.call('bill_reconcile')
        self.assertEqual(result['matched_rows'], 0)
        self.assertEqual(result['unknown_rows'][0]['reason'], 'LOCAL_SCOPE_MISSING_OR_AMBIGUOUS')
        self.assertEqual(result['exceptions'], [])

    def test_full_day_request_always_refused_even_empty_bill(self):
        for kind in ('TRADE', 'SPLIT'):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'COMPLETE_MERCHANT'):
                self.call('bill_reconcile', kind=kind, require_complete=True)

    def test_page_shapes_currency_and_sensitive_fields(self):
        raw = self.trade(*['ref%d,tx%d,SUCCESS,1.00,%s,private-openid,private-card' % (i, i, self.policy['sub_mchid']) for i in range(51)])
        self.download(raw)
        self.call('bill_fetch')
        first = self.call('bill_rows', offset=0)
        self.assertEqual(len(first['records']), 50)
        self.assertEqual(first['next_offset'], 50)
        second = self.call('bill_rows', offset=50)
        self.assertEqual(len(second['records']), 1)
        self.assertFalse(second['has_more'])
        self.assertNotIn('private-', json.dumps([first, second]))
        with self.assertRaises(ValueError):
            self.call('bill_rows', offset=True)

    def test_wrong_submerchant_csv_refused_before_persisting(self):
        self.download(self.trade('ref,tx,SUCCESS,1.00,9999999999,private,private'))
        with self.assertRaisesRegex(PermissionError, 'SUBMERCHANT_MISMATCH'):
            self.call('bill_fetch')
        self.assertEqual(self.cache_count(), 0)

    def test_ticket_hash_mismatch_and_changed_immutable_bill_are_rejected(self):
        raw = self.trade()
        self.download(raw)
        self.service.bills._download.return_value = raw + b'changed'
        with self.assertRaisesRegex(PermissionError, 'HASH_MISMATCH'):
            self.call('bill_fetch')
        self.assertEqual(self.cache_count(), 0)
        self.download(raw)
        self.call('bill_fetch')
        self.download(self.trade('outside,tx,SUCCESS,1.00,' + self.policy['sub_mchid'] + ',private,private'))
        with self.assertRaisesRegex(ValueError, 'IMMUTABLE_MERCHANT'):
            self.call('bill_fetch')
        self.assertEqual(self.cache_count(), 1)

    def test_foreign_project_refund_cannot_be_borrowed_by_same_local_scope(self):
        row = self.seed(self.g['scope'], 'paid', 101)
        columns = self.trade(row).decode().splitlines()
        raw = (columns[0] + ',商户退款单号,退款金额\n' + columns[1] + ',refund-foreign,0.01\n').encode()
        ref = hashlib.sha256(canonical([self.a.reader._mchid, 'REFUND', 'refund-foreign'])).hexdigest()
        record = dict(project='foreign-project', scope=self.g['scope'], reference='paid',
            result=dict(status='SUCCESS'), payload=dict(amount=dict(refund=1)))
        self.c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ACTION',?,?,?,?,1)",
            (ref, self.g['user_id'], 'foreign-project', self.c.encrypt(canonical(record), 'provider-action:' + ref)))
        self.download(raw)
        self.call('bill_fetch')
        result = self.call('bill_reconcile')
        self.assertEqual(result['matched_rows'], 0)
        self.assertTrue(any(x['result'].get('exceptions') for x in result['stores']))

    def test_unproven_trade_columns_remain_redacted(self):
        self.download('商户订单号,微信订单号,交易状态,订单金额\nprivate-order,private-tx,SUCCESS,1.00\n'.encode())
        self.call('bill_fetch')
        result = self.call('bill_rows', offset=0)
        self.assertEqual(result['records'], [{}])
        self.assertEqual(result['unattributed_rows_redacted'], 1)
        self.assertNotIn('private-', json.dumps(result))

    def test_unknown_layout_with_matching_named_merchant_column_stays_redacted(self):
        self.download(('特约商户号,金额\n' + self.policy['sub_mchid'] + ',12345.67\n').encode())
        self.call('bill_fetch')
        result = self.call('bill_rows', offset=0)
        self.assertEqual(result['records'], [{}])
        self.assertEqual(result['unattributed_rows_redacted'], 1)
        self.assertNotIn('12345.67', json.dumps(result))

    def test_application_configuration_is_default_empty_and_separate_from_money_grants(self):
        from scripts.community_mini_application import MiniApplication
        fx = self.j.fx.fx
        with tempfile.TemporaryDirectory() as directory:
            app = MiniApplication(self.c, directory, fx.stage.api.bindings, self.g['scope'],
                fx.scenes, fx.identity.appid, 'a' * 32)
            try:
                with self.assertRaises(ValueError):
                    app.configure_merchant_bills()
                app.configure_operations({'finance': {k: self.g[k] for k in ('user_id', 'project', 'project_roles', 'principal')}})
                app.configure_provider_actions(self.a.reader, self.a.bindings)
                original = dict(app.operations.grants)
                service = app.configure_merchant_bills()
                self.assertEqual(service.grants, {})
                self.assertEqual(app.operations.grants, original)
                self.assertIs(service.actions, app.provider_actions)
                with self.assertRaises(ValueError):
                    app.configure_merchant_bills({'all-stores': self.grant})
            finally:
                app.close()

    def http(self, body, csrf=True, mini=False, configured=True, cookie=False, origin=None):
        handler = make_handler(self.j.fx.fx.gateway, operations=self.a.operations,
            provider_actions=self.a, merchant_bills=self.service if configured else None)
        request = handler.__new__(handler)
        request.server = SimpleNamespace(server_port=8123)
        request.path = '/community/merchant-bills'
        request.connection = SimpleNamespace(settimeout=lambda value: None)
        headers = Message()
        raw = canonical(body)
        for key, value in {'Host': '127.0.0.1:8123', 'Content-Type': 'application/json',
                           'Content-Length': str(len(raw))}.items():
            headers[key] = value
        headers['Cookie' if cookie else 'X-Center-Session'] = '__Host-xj_customer=' + self.web['token'] if cookie else self.web['token']
        if csrf: headers['X-CSRF-Token' if cookie else 'X-Center-CSRF'] = self.web['csrf']
        if origin: headers['Origin'] = origin
        if mini: headers['X-Community-Session'] = 'mini-token'
        request.headers, request.rfile = headers, io.BytesIO(raw)
        result = []
        request.answer = lambda status, value: result.append((status, value))
        request.do_POST()
        return result[0]

    def test_real_http_handler_route_is_opt_in_cookie_csrf_read_only_boundary(self):
        self.download(self.trade())
        body = dict(workspace='all-stores', operation='bill_fetch', params=dict(kind='TRADE', bill_date=self.date))
        status, result = self.http(body)
        self.assertEqual(status, 200)
        self.assertFalse(result['payment_enabled'])
        self.assertEqual(self.http(body, cookie=True)[0], 200)
        self.assertEqual(self.http(body, cookie=True, csrf=False)[0], 403)
        self.assertEqual(self.http(body, origin='https://untrusted.example')[0], 403)
        self.assertEqual(self.http(body, csrf=False)[0], 403)
        self.assertEqual(self.http(body, mini=True)[0], 403)
        self.assertEqual(self.http(body, configured=False)[0], 404)
        self.assertEqual(self.http(dict(body, operation='refund'))[0], 403)


class MerchantSplitLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        split_fixtures.ExactSplitDetailJourney.setUpClass()

    def setUp(self):
        self.j = split_fixtures.ExactSplitDetailJourney()
        self.j.setUp()
        self.addCleanup(self.j.doCleanups)
        self.j.accept()
        self.a, self.c, self.g = self.j.a, self.j.c, self.j.g
        self.date = fixtures.dt.datetime.fromtimestamp(self.c.now(), fixtures.dt.timezone(fixtures.dt.timedelta(hours=8))).date() - fixtures.dt.timedelta(days=1)
        grant = dict(finance_workspace='finance', user_id=self.g['user_id'], project=self.g['project'],
            tenant_id=self.g['scope']['tenant_id'], merchant_id=self.g['scope']['merchant_id'],
            sp_mchid=self.a.reader._mchid, sub_mchid=self.j.policy['sub_mchid'], revision=1, permission=PERMISSION)
        self.service = MerchantBills(self.a, {'all-stores': grant})
        self.other = dict(self.g['scope'], store_id='second-store')
        self.a.bindings[tuple(self.other.values())] = copy.deepcopy(self.j.policy)
        create_order(self.a.runtime.demo.db, self.other, 'basket2', 101)
        self.a.runtime.demo.db.execute('UPDATE orders SET provider_transaction_id=? WHERE store_id=?', ('second-tx', 'second-store'))
        self.a.runtime.demo.db.commit()
        # Synthetic original encrypted records; no money dispatch or provider call.
        saved = copy.deepcopy(self.a._load(self.j.key))
        saved.update(scope=self.other, reference='basket2', provider_reference='second-split', transaction_id='second-tx')
        saved['payload'].update(out_order_no='second-split', transaction_id='second-tx')
        saved['bill_evidence']['details'].update(out_order_no='second-split', transaction_id='second-tx', order_id='second-wechat-split')
        saved['bill_evidence']['details']['receivers'][0]['detail_id'] = 'second-detail'
        key = hashlib.sha256(canonical([self.a.reader._mchid, 'SPLIT', 'second-split'])).hexdigest()
        self.c.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ACTION',?,?,?,?,1)",
            (key, self.g['user_id'], self.g['project'], self.c.encrypt(canonical(saved), 'provider-action:' + key)))
        first = self.j.bill()['rows'][0]
        second = dict(first, **{'商户分账/回退单号': 'second-split', '微信分账/回退单号': 'second-wechat-split',
            '微信订单号': 'second-tx', '分账明细单号': 'second-detail'})
        self.rows = [first, second]
        for target in ('socket.socket.connect', 'socket.socket.bind'):
            guard = patch(target, side_effect=AssertionError('NO_NETWORK_OR_LISTENER'))
            guard.start()
            self.addCleanup(guard.stop)

    def call(self, op, **extra):
        return self.service.dispatch(self.j.fx.web['token'], self.j.fx.web['csrf'],
            dict(workspace='all-stores', operation=op, params=dict(kind='SPLIT', bill_date=str(self.date), **extra)))

    def fetch(self):
        raw = split_fixtures.bill_bytes([[row[k] for k in split_fixtures.SPLIT_COLUMNS] for row in self.rows])
        self.a._call = Mock(return_value=(dict(hash_type='SHA1', hash_value=hashlib.sha1(raw).hexdigest(),
            download_url='https://api.mch.weixin.qq.com/v3/bill/downloadurl?token=synthetic'), 'a' * 64))
        self.service.bills._download = Mock(return_value=raw)
        self.call('bill_fetch')

    def test_two_store_signed_detail_ledgers_are_partitioned_without_summary_double_count(self):
        self.fetch()
        result = self.call('bill_reconcile')
        self.assertEqual(result['matched_rows'], 2)
        self.assertEqual([x['result']['total_rows'] for x in result['stores']], [1, 1])
        self.assertEqual([x['result']['local_inventory']['counts']['split_records'] for x in result['stores']], [1, 1])
        self.assertTrue(all(x['result']['summary_evidence'] == 'LEGACY_SUMMARY_VALUES_NOT_RETAINED' for x in result['stores']))
        self.assertEqual(result['summary_amounts'], 'NOT_RECONCILED')
        self.assertFalse(result['complete_reconciliation_available'])
        self.assertFalse(result['sample_arithmetic']['establishes_reconciliation'])
        self.assertNotIn('分账接收方', self.call('bill_rows', offset=0)['records'][0])

    def test_cross_store_duplicate_detail_is_not_counted_twice(self):
        self.rows[1]['分账明细单号'] = self.rows[0]['分账明细单号']
        self.fetch()
        result = self.call('bill_reconcile')
        self.assertEqual(result['matched_rows'], 1)
        self.assertEqual(result['exceptions'][0]['reason'], 'DUPLICATE_PROVIDER_ROW')

    def test_returns_and_unfreeze_remain_unresolved_with_complete_merchant_read_permission(self):
        self.rows += [dict(self.rows[0], **{'业务类型': kind}) for kind in ('分账回退', '解冻', '逾期解冻')]
        self.fetch()
        result = self.call('bill_reconcile')
        self.assertEqual(result['matched_rows'], 2)
        self.assertEqual(len(result['unknown_rows']), 3)
        self.assertEqual(result['finance_status'], 'UNCONFIRMED')
        page = self.call('bill_rows', offset=0)
        self.assertEqual(page['unattributed_rows_redacted'], 3)
        self.assertEqual(page['records'][2:], [{}, {}, {}])

    def test_foreign_ordinary_split_merchant_or_provider_is_rejected_before_cache(self):
        original = copy.deepcopy(self.rows)
        for column in ('分账方', '分账发起方'):
            self.rows = copy.deepcopy(original)
            self.rows[0][column] = '9999999999'
            with self.subTest(column=column), self.assertRaisesRegex(PermissionError, 'SUBMERCHANT_MISMATCH'):
                self.fetch()
        self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM links WHERE channel=?', (CHANNEL,)).fetchone()[0], 0)

    def test_preexisting_cached_foreign_split_is_rejected_on_read(self):
        self.fetch()
        key, encrypted = self.c.db.execute('SELECT subject_idx,payload FROM links WHERE channel=?', (CHANNEL,)).fetchone()
        record = json.loads(self.c.decrypt(encrypted, 'merchant-bill:' + key))
        record['rows'][0]['分账方'] = '9999999999'
        self.c.db.execute('UPDATE links SET payload=? WHERE channel=? AND subject_idx=?',
            (self.c.encrypt(canonical(record), 'merchant-bill:' + key), CHANNEL, key))
        with self.assertRaisesRegex(PermissionError, 'SUBMERCHANT_MISMATCH'):
            self.call('bill_rows', offset=0)


if __name__ == '__main__':
    unittest.main()
