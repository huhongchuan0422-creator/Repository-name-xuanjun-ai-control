"""Nonproduction integration: ephemeral signing keys and real temporary SQLite.

These synthetic receipts exercise the verifier, not a genuine Finance issuer.
No provider, Finance service, network, payment, or production credentials are used.
"""
import base64
import concurrent.futures
import contextlib
import sqlite3
import threading
import hashlib
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa, padding
import test_community_mini_center_identity as center_fixture
import test_stage5_saas_offline_handoff as saas_fixture
from scripts.community_mini_application import MiniApplication
from scripts.community_saas_finance_authority import SignedFinanceAuthority, SignedFinanceReversalAuthority
from scripts.community_saas_fulfillment import FulfillmentPending, SaasFulfillment
from scripts.community_center_operations import CenterOperations
from scripts.community_stage_runtime import StageRuntime
from scripts.community_saas_phase2 import OfflineSaas
from scripts.community_saas_modules import set_price, grant
from scripts.community_saas_offer_catalog import create_offer, approve_offer, quote
from scripts.community_saas_order_preparation import prepare, status
from scripts.community_saas_offline_handoff import plan_finance_claim
from scripts.pr122_customer_core import Center, canonical
from scripts.community_demo_bootstrap import DEMO_SCOPE


class SyntheticFinanceIntegration(unittest.TestCase):
    def setUp(self):
        self.fx = center_fixture.ExistingCenterComposition()
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.web = self.fx.center.login('one@example.org', 'FixturePassword123!')
        self.key = ed25519.Ed25519PrivateKey.generate()
        public = self.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.trust = {'synthetic_key': {'public_key_pem': public, 'tenants': ['tenant1']}}
        self.finance = SignedFinanceAuthority(self.trust)
        self.reversal = SignedFinanceReversalAuthority(self.trust)
        self.path = self.fx.tmp.name + '/synthetic-runtime'
        self.open_app()
        self.addCleanup(lambda: self.app.close())
        self.now = self.fx.stage.now
        set_price(self.q, 'storefront_catalog', 1, 1000, 150, 30)
        create_offer(self.q, 'offer1', 1, 'storefront_catalog', 'MONTHLY', [saas_fixture.fee()], term_days=30)
        approve_offer(self.q, 'offer1', 1, 'approval1', 'cost1', self.now - 10)
        self.order('order1')

    def open_app(self):
        self.app = MiniApplication(self.fx.center, self.path, self.fx.stage.api.bindings,
                                   DEMO_SCOPE, self.fx.scenes, self.fx.identity.appid, 'a' * 32)
        self.app.configure_operations({'owner': {'user_id': self.fx.uid1, 'project': 'project1',
            'project_roles': ['OWNER'], 'principal': self.fx.stage.owner}})
        self.api = self.app.configure_fulfillment(self.finance, 'synthetic_authority',
            {('storefront_catalog', 'offer1', 1): 1}, reversal_finance=self.reversal)
        self.q = self.app.stage.runtime.saas.modules
        self.s = self.app.stage.runtime.saas.orders

    def reopen(self):
        self.app.close()
        self.fx.reopen()
        self.open_app()

    def order(self, oid):
        quote(self.q, 'quote_' + oid, 'tenant1', 'offer1', 1, self.now - 5, self.now + 300)
        prepare(self.s, self.q, oid, 'tenant1', 'quote_' + oid, 'CNY', self.now - 1)

    def proof(self, oid='order1', pid='synthetic_confirmation', reverse=False, changes=None):
        claim = plan_finance_claim(self.s, oid, 'tenant1')
        authority = self.reversal if reverse else self.finance
        payload = dict(audience=authority.audience, status=authority.status,
            tenant_id='tenant1', order_id=oid, quote_sha256=claim['quote_sha256'],
            claim_sha256=hashlib.sha256(canonical(claim)).hexdigest(), proof_id=pid,
            verified_at=self.fx.stage.now, expires_at=self.fx.stage.now + 300)
        payload.update(changes or {})
        return dict(key_id='synthetic_key', payload=payload,
                    signature=base64.b64encode(self.key.sign(canonical(payload))).decode())

    def call(self, proof=None, oid='order1', reverse=False):
        method = self.api.reverse if reverse else self.api.fulfill
        return method(self.web['token'], self.web['csrf'], 'owner', oid,
                      self.proof(oid, reverse=reverse) if proof is None else proof)

    def snapshot(self):
        return ([tuple(r) for r in self.fx.center.db.execute("SELECT * FROM links WHERE channel LIKE 'COMMUNITY_SAAS_%' ORDER BY channel,subject_idx")],
                [tuple(r) for r in self.fx.center.db.execute("SELECT * FROM events WHERE channel LIKE 'COMMUNITY_SAAS_%' ORDER BY channel,event_id")],
                self.s.execute('SELECT * FROM saas_order_lifecycle_events').fetchall(),
                self.q.execute('SELECT * FROM module_entitlements').fetchall(),
                self.q.execute('SELECT * FROM module_events').fetchall())

    @contextlib.contextmanager
    def independent_api(self):
        """Each worker owns three independent connections to the same DB files.

        The application host's exclusive process lock is not bypassed to start a
        second host. This deliberately tests the fulfillment component's SQLite
        boundary using two separately composed component instances.
        """
        with contextlib.ExitStack() as stack:
            center = Center(self.fx.tmp.name, {'testkey': b'k' * 32}, 'testkey',
                            clock=lambda: self.fx.stage.now, mail_ready=True)
            stack.callback(center.db.close)
            modules = sqlite3.connect(self.path + '/modules.sqlite', timeout=15)
            stack.callback(modules.close)
            orders = sqlite3.connect(self.path + '/saas-orders.sqlite', timeout=15)
            stack.callback(orders.close)
            for db in (modules, orders): db.execute('PRAGMA foreign_keys=ON')
            runtime = StageRuntime(self.app.stage.runtime.demo, OfflineSaas(modules, orders, modules),
                                   self.fx.stage.api.bindings, lambda: self.fx.stage.now)
            operations = CenterOperations(center, runtime, {'owner': {
                'user_id': self.fx.uid1, 'project': 'project1', 'project_roles': ['OWNER'],
                'principal': self.fx.stage.owner}})
            yield SaasFulfillment(operations, SignedFinanceAuthority(self.trust), 'synthetic_authority',
                {('storefront_catalog', 'offer1', 1): 1},
                reversal_finance=SignedFinanceReversalAuthority(self.trust))

    def test_two_connections_same_receipt_consumed_once_during_overlap(self):
        from scripts.community_saas_order_preparation import advance
        ready = threading.Barrier(2, timeout=10)
        reserved = threading.Event(); second_done = threading.Event()
        receipt = self.proof()
        first_order_db = []
        def pause_first(db, *args, **kwargs):
            if db is first_order_db[0] and not reserved.is_set():
                reserved.set()
                if not second_done.wait(10): raise AssertionError('second connection did not finish')
            return advance(db, *args, **kwargs)
        def worker(first):
            with self.independent_api() as api:
                if first: first_order_db.append(api.runtime.saas.orders)
                ready.wait()
                if not first and not reserved.wait(10): raise AssertionError('first reservation missing')
                try:
                    return api.fulfill(self.web['token'], self.web['csrf'], 'owner', 'order1', receipt)
                finally:
                    if not first: second_done.set()
        with patch('scripts.community_saas_fulfillment.advance', side_effect=pause_first):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(worker, True); second = pool.submit(worker, False)
                results = [first.result(timeout=20), second.result(timeout=20)]
        self.assertEqual(sorted(r['duplicate'] for r in results), [False, True])
        self.assertEqual(self.q.execute('SELECT count(*) FROM module_events').fetchone()[0], 1)
        self.assertEqual(self.s.execute('SELECT count(*) FROM saas_order_lifecycle_events').fetchone()[0], 3)
        self.assertEqual(self.fx.center.db.execute("SELECT count(*) FROM events WHERE channel='COMMUNITY_SAAS_FINANCE_PROOF'").fetchone()[0], 1)
        before = self.snapshot(); self.reopen()
        self.assertTrue(self.call(receipt)['duplicate'])
        self.assertEqual(before, self.snapshot())

    def test_two_connections_module_lock_then_consumed_proof_survive_reopen(self):
        from scripts.community_saas_order_preparation import advance
        self.order('order2')
        first_receipt = self.proof(); second_receipt = self.proof('order2')
        ready = threading.Barrier(2, timeout=10)
        reserved = threading.Event(); contender_done = threading.Event()
        def pause_first(db, oid, *args, **kwargs):
            if oid == 'order1' and not reserved.is_set():
                reserved.set()
                if not contender_done.wait(10): raise AssertionError('contender did not finish')
            return advance(db, oid, *args, **kwargs)
        def worker(first):
            with self.independent_api() as api:
                ready.wait()
                if not first and not reserved.wait(10): raise AssertionError('reservation missing')
                if first:
                    return api.fulfill(self.web['token'], self.web['csrf'], 'owner', 'order1', first_receipt)
                try:
                    def persisted_state():
                        return tuple(tuple(tuple(row) for row in db.execute(sql)) for db, sql in (
                            (api.center.db, "SELECT * FROM links WHERE channel LIKE 'COMMUNITY_SAAS_%' ORDER BY channel,subject_idx"),
                            (api.center.db, "SELECT * FROM events WHERE channel LIKE 'COMMUNITY_SAAS_%' ORDER BY channel,event_id"),
                            (api.runtime.saas.orders, 'SELECT * FROM saas_order_lifecycle_events'),
                            (api.runtime.saas.modules, 'SELECT * FROM module_entitlements'),
                            (api.runtime.saas.modules, 'SELECT * FROM module_events')))
                    before = persisted_state()
                    with self.assertRaisesRegex(FulfillmentPending, 'PRIOR_MODULE_FULFILLMENT_PENDING'):
                        api.fulfill(self.web['token'], self.web['csrf'], 'owner', 'order2', second_receipt)
                    self.assertEqual(before, persisted_state())
                    return True
                finally: contender_done.set()
        # Only worker-owned connections may be used within a thread.
        with patch('scripts.community_saas_fulfillment.advance', side_effect=pause_first):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(worker, True); second = pool.submit(worker, False)
                second.result(timeout=20); self.assertEqual(first.result(timeout=20)['state'], 'COMPLETED')
        self.assertEqual(status(self.s, 'order2', 'tenant1')['state'], 'PREPARED')
        self.assertEqual(self.q.execute('SELECT count(*) FROM module_events').fetchone()[0], 1)
        self.reopen(); before = self.snapshot()
        with self.assertRaisesRegex(PermissionError, 'FINANCE_PROOF_ALREADY_CONSUMED'):
            self.call(second_receipt, 'order2')
        self.assertEqual(before, self.snapshot())
        self.assertTrue(self.call(first_receipt)['duplicate'])

    def test_two_connections_reversal_consumed_once_and_persisted(self):
        self.call(); receipt = self.proof(reverse=True)
        ready = threading.Barrier(2, timeout=10)
        reservation_locked = threading.Event(); contender_begin = threading.Event()
        def worker(first):
            with self.independent_api() as api:
                original_audit = api.center.audit
                def pause_reserved(project, user, kind, reference):
                    original_audit(project, user, kind, reference)
                    if kind == 'SAAS_REVERSAL_RESERVED':
                        # The real Center write transaction still owns its lock.
                        self.assertTrue(api.center.db.in_transaction)
                        reservation_locked.set()
                        if not contender_begin.wait(10):
                            raise AssertionError('second connection never attempted BEGIN IMMEDIATE')
                        self.assertTrue(api.center.db.in_transaction)
                def trace(statement):
                    # sqlite3 invokes this when the competing real SQL statement
                    # is issued, before it can acquire the first connection's lock.
                    if statement.strip().upper() == 'BEGIN IMMEDIATE':
                        contender_begin.set()
                if not first: api.center.db.set_trace_callback(trace)
                ready.wait()
                if not first and not reservation_locked.wait(10):
                    raise AssertionError('first reversal never reserved inside its write transaction')
                if first:
                    with patch.object(api.center, 'audit', side_effect=pause_reserved):
                        return api.reverse(self.web['token'], self.web['csrf'], 'owner', 'order1', receipt)
                return api.reverse(self.web['token'], self.web['csrf'], 'owner', 'order1', receipt)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, first) for first in (True, False)]
            results = [future.result(timeout=20) for future in futures]
        self.assertTrue(reservation_locked.is_set())
        self.assertTrue(contender_begin.is_set())
        self.assertEqual(sorted(r['duplicate'] for r in results), [False, True])
        self.assertTrue(all(not r['provider_refund_executed'] for r in results))
        self.assertEqual(self.q.execute("SELECT count(*) FROM module_events WHERE action='REVERSE'").fetchone()[0], 1)
        self.assertEqual(self.fx.center.db.execute("SELECT count(*) FROM events WHERE channel='COMMUNITY_SAAS_FINANCE_REVERSAL'").fetchone()[0], 1)
        self.assertEqual(self.q.execute('SELECT * FROM module_entitlements').fetchall(), [])
        before = self.snapshot(); self.reopen()
        self.assertTrue(self.call(receipt, reverse=True)['duplicate'])
        self.assertEqual(before, self.snapshot())

    def test_rsa_confirmation_reversal_and_signature_algorithm_binding(self):
        # Ephemeral test-only RSA key; production trust and keys are never read.
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        trust = {'synthetic_key': {'public_key_pem': public, 'tenants': ['tenant1']}}
        self.api.finance = SignedFinanceAuthority(trust)
        self.api.reversal_finance = SignedFinanceReversalAuthority(trust)
        def signed(reverse=False, signer=key, scheme=None, algorithm=None):
            receipt = self.proof(reverse=reverse)
            receipt['signature'] = base64.b64encode(signer.sign(canonical(receipt['payload']),
                scheme or padding.PKCS1v15(), algorithm or hashes.SHA256())).decode()
            return receipt
        tampered = signed(); tampered['payload']['proof_id'] = 'tampered_rsa'
        wrong_algorithm = signed(algorithm=hashes.SHA512())
        wrong_padding = signed(scheme=padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH))
        before = self.snapshot()
        for receipt in (tampered, signed(signer=other), wrong_algorithm, wrong_padding, self.proof()):
            with self.subTest(signature=receipt['signature'][:16]):
                with self.assertRaisesRegex(PermissionError, 'FINANCE_SIGNATURE_REJECTED'): self.call(receipt)
                self.assertEqual(before, self.snapshot())
        receipt = signed()
        self.assertEqual(self.call(receipt)['state'], 'COMPLETED')
        self.assertTrue(self.call(receipt)['duplicate'])
        before = self.snapshot()
        with self.assertRaisesRegex(PermissionError, 'FINANCE_SIGNATURE_REJECTED'):
            self.call(signed(reverse=True, signer=other), reverse=True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.call(signed(reverse=True), reverse=True)['state'], 'REVERSED')

    def test_configure_grant_replay_and_reopen_use_original_stores(self):
        result = self.call()
        self.assertEqual(result['state'], 'COMPLETED')
        self.assertFalse(result['duplicate'])
        self.assertEqual(result['valid_until'], self.now + 30 * 86400)
        self.assertEqual(status(self.s, 'order1', 'tenant1')['state'], 'CONFIRMED_EXTERNAL')
        before = self.snapshot()
        self.assertTrue(self.call()['duplicate'])
        self.reopen()
        self.assertTrue(self.call()['duplicate'])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(before[-1]), 1)

    def test_reverse_replay_reopen_and_no_regrant(self):
        self.call()
        receipt = self.proof(pid='synthetic_reversal', reverse=True)
        result = self.call(receipt, reverse=True)
        self.assertEqual(result['state'], 'REVERSED')
        self.assertFalse(result['provider_refund_executed'])
        self.assertEqual(self.q.execute('SELECT * FROM module_entitlements').fetchall(), [])
        before = self.snapshot()
        self.reopen()
        self.assertTrue(self.call(receipt, reverse=True)['duplicate'])
        self.assertEqual(before, self.snapshot())
        with self.assertRaisesRegex(PermissionError, 'REVERSED_ORDER'):
            self.call()
        with self.assertRaisesRegex(PermissionError, 'REVERSAL_PROOF_COLLISION'):
            self.call(self.proof(pid='another_reversal', reverse=True), reverse=True)

    def test_reversal_restores_preexisting_original_entitlement(self):
        grant(self.q, 'tenant1', 'storefront_catalog', self.now - 100, self.now + 100, 1)
        before = self.q.execute('SELECT * FROM module_entitlements').fetchall()
        self.assertEqual(self.call()['valid_until'], self.now + 100 + 30 * 86400)
        self.call(reverse=True)
        self.assertEqual(before, self.q.execute('SELECT * FROM module_entitlements').fetchall())

    def test_reversal_requires_original_grant_and_configured_authority(self):
        before = self.snapshot()
        with self.assertRaisesRegex(PermissionError, 'ORIGINAL_FULFILLMENT_REQUIRED'):
            self.call(reverse=True)
        self.api.reversal_finance = None
        with self.assertRaisesRegex(PermissionError, 'REVERSAL_AUTHORITY_NOT_CONFIGURED'):
            self.call(reverse=True)
        self.assertEqual(before, self.snapshot())

    def test_signed_wrong_bindings_and_validity_have_no_business_effect(self):
        before = self.snapshot()
        variants = [dict(tenant_id='tenant2'), dict(order_id='other'), dict(quote_sha256='0' * 64),
            dict(claim_sha256='0' * 64), dict(audience=self.reversal.audience), dict(status='REVERSED'),
            dict(verified_at=self.now + 1), dict(expires_at=self.now), dict(expires_at=self.now + 901),
            dict(verified_at=True), dict(expires_at=True), dict(verified_at=self.now - 2),
            dict(proof_id=''), dict(extra='unadmitted')]
        for changes in variants:
            with self.subTest(changes=changes):
                with self.assertRaises(PermissionError): self.call(self.proof(changes=changes))
                self.assertEqual(before, self.snapshot())

    def test_malformed_and_forged_receipts_have_no_business_effect(self):
        good = self.proof()
        variants = [False, [], {}, {'paid': True}, dict(good, key_id='unknown'),
            dict(good, signature='not base64!'), dict(good, signature='a' * 2049),
            dict(good, signature=base64.b64encode(b'wrong').decode()), dict(good, payload=[]),
            dict(good, extra=True)]
        tampered = self.proof(); tampered['payload']['proof_id'] = 'tampered'; variants.append(tampered)
        before = self.snapshot()
        for bad in variants:
            with self.subTest(receipt=bad):
                with self.assertRaises(PermissionError): self.call(bad)
                self.assertEqual(before, self.snapshot())

    def test_confirmation_and_reversal_audiences_cannot_cross(self):
        with self.assertRaises(PermissionError): self.call(self.proof(reverse=True))
        self.call()
        before = self.snapshot()
        with self.assertRaises(PermissionError): self.call(self.proof(), reverse=True)
        self.assertEqual(before, self.snapshot())

    def test_consumed_proof_cannot_authorize_second_order(self):
        self.call(); self.order('order2')
        before = self.snapshot()
        with self.assertRaisesRegex(PermissionError, 'FINANCE_PROOF_ALREADY_CONSUMED'):
            self.call(self.proof('order2'), 'order2')
        self.assertEqual(before, self.snapshot())

    def test_second_confirmation_for_same_order_is_collision(self):
        self.call(); before = self.snapshot()
        with self.assertRaisesRegex(PermissionError, 'FULFILLMENT_CONFIRMATION_COLLISION'):
            self.call(self.proof(pid='other_confirmation'))
        self.assertEqual(before, self.snapshot())

    def test_failure_after_reservation_recovers_after_database_reopen(self):
        with patch('scripts.community_saas_fulfillment.advance', side_effect=RuntimeError('synthetic crash')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic crash'): self.call()
        self.assertEqual(self.api.inspect(self.web['token'], self.web['csrf'], 'owner', 'order1')['state'], 'RESERVED')
        self.assertEqual(self.q.execute('SELECT count(*) FROM module_events').fetchone()[0], 0)
        self.reopen()
        self.assertEqual(self.call()['state'], 'COMPLETED')
        self.assertEqual(self.q.execute('SELECT count(*) FROM module_events').fetchone()[0], 1)

    def test_failure_after_module_commit_recovers_without_duplicate_grant(self):
        original = self.fx.center.audit
        def fail(project, user, kind, reference):
            if kind == 'SAAS_FULFILLMENT_COMPLETED': raise RuntimeError('synthetic completion crash')
            return original(project, user, kind, reference)
        with patch.object(self.fx.center, 'audit', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'synthetic completion crash'): self.call()
        self.assertEqual(self.q.execute('SELECT count(*) FROM module_events').fetchone()[0], 1)
        self.reopen()
        self.assertEqual(self.call()['state'], 'COMPLETED')
        self.assertEqual(self.q.execute('SELECT count(*) FROM module_events').fetchone()[0], 1)

    def test_reversal_partial_commit_recovers_without_duplicate_reversal(self):
        self.call(); receipt = self.proof(reverse=True)
        original = self.fx.center.audit
        def fail(project, user, kind, reference):
            if kind == 'SAAS_REVERSAL_COMPLETED': raise RuntimeError('synthetic reversal crash')
            return original(project, user, kind, reference)
        with patch.object(self.fx.center, 'audit', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'synthetic reversal crash'): self.call(receipt, reverse=True)
        self.assertEqual(self.q.execute("SELECT count(*) FROM module_events WHERE action='REVERSE'").fetchone()[0], 1)
        self.reopen()
        self.assertEqual(self.call(receipt, reverse=True)['state'], 'REVERSED')
        self.assertEqual(self.q.execute("SELECT count(*) FROM module_events WHERE action='REVERSE'").fetchone()[0], 1)

    def test_later_renewal_prevents_old_order_reversal(self):
        self.call(); self.order('order2')
        self.call(self.proof('order2', pid='second_confirmation'), 'order2')
        before = self.q.execute('SELECT * FROM module_entitlements').fetchall()
        with self.assertRaisesRegex(FulfillmentPending, 'LATER_LICENSE_CHANGE_REQUIRES_REVIEW'):
            self.call(reverse=True)
        self.assertEqual(before, self.q.execute('SELECT * FROM module_entitlements').fetchall())

    def test_pending_module_lock_blocks_another_order(self):
        with patch('scripts.community_saas_fulfillment.advance', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError): self.call()
        self.order('order2')
        with self.assertRaisesRegex(FulfillmentPending, 'PRIOR_MODULE_FULFILLMENT_PENDING'):
            self.call(self.proof('order2', pid='second_confirmation'), 'order2')

    def test_partial_order_transition_recovers_after_reopen(self):
        from scripts.community_saas_order_preparation import advance
        def interrupt(db, oid, tenant, event, target, at, **kwargs):
            if target == 'CONFIRMATION_UNKNOWN': raise RuntimeError('synthetic transition crash')
            return advance(db, oid, tenant, event, target, at, **kwargs)
        with patch('scripts.community_saas_fulfillment.advance', side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, 'synthetic transition crash'): self.call()
        self.assertEqual(status(self.s, 'order1', 'tenant1')['state'], 'AWAITING_EXTERNAL')
        self.reopen()
        self.call()
        self.assertEqual(self.s.execute('SELECT count(*) FROM saas_order_lifecycle_events').fetchone()[0], 3)
        self.assertEqual(self.q.execute('SELECT count(*) FROM module_events').fetchone()[0], 1)

    def test_expired_receipt_cannot_resume_but_fresh_same_proof_can(self):
        receipt = self.proof()
        with patch('scripts.community_saas_fulfillment.advance', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError): self.call(receipt)
        self.fx.stage.now += 300
        self.reopen()
        before = self.snapshot()
        with self.assertRaisesRegex(PermissionError, 'FINANCE_CLAIM_OR_VALIDITY_MISMATCH'): self.call(receipt)
        self.assertEqual(before, self.snapshot())
        result = self.call(self.proof())
        self.assertEqual(result['valid_until'], self.now + 30 * 86400)

    def test_extra_module_event_blocks_partial_commit_recovery(self):
        original = self.fx.center.audit
        def fail(project, user, kind, reference):
            if kind == 'SAAS_FULFILLMENT_COMPLETED': raise RuntimeError('crash')
            return original(project, user, kind, reference)
        with patch.object(self.fx.center, 'audit', side_effect=fail):
            with self.assertRaises(RuntimeError): self.call()
        self.q.execute("INSERT INTO module_events(tenant_id,module_id,action,old_until,new_until,occurred_at) VALUES('tenant1','storefront_catalog','UNRELATED',NULL,NULL,?)", (self.now,))
        self.q.commit()
        self.reopen(); before = self.snapshot()
        with self.assertRaisesRegex(FulfillmentPending, 'ENTITLEMENT_RECOVERY_EVENT_CONFLICT'): self.call()
        self.assertEqual(before, self.snapshot())

    def test_extra_reversal_event_blocks_partial_commit_recovery(self):
        self.call()
        original = self.fx.center.audit
        def fail(project, user, kind, reference):
            if kind == 'SAAS_REVERSAL_COMPLETED': raise RuntimeError('crash')
            return original(project, user, kind, reference)
        with patch.object(self.fx.center, 'audit', side_effect=fail):
            with self.assertRaises(RuntimeError): self.call(reverse=True)
        self.q.execute("INSERT INTO module_events(tenant_id,module_id,action,old_until,new_until,occurred_at) VALUES('tenant1','storefront_catalog','UNRELATED',NULL,NULL,?)", (self.now,))
        self.q.commit()
        self.reopen(); before = self.snapshot()
        with self.assertRaisesRegex(FulfillmentPending, 'REVERSAL_RECOVERY_EVENT_CONFLICT'): self.call(reverse=True)
        self.assertEqual(before, self.snapshot())

    def test_trusted_key_with_wrong_tenant_scope_is_rejected(self):
        trust = {'synthetic_key': dict(self.trust['synthetic_key'], tenants=['tenant2'])}
        self.api.finance = SignedFinanceAuthority(trust)
        before = self.snapshot()
        with self.assertRaisesRegex(PermissionError, 'FINANCE_CLAIM_OR_VALIDITY_MISMATCH'): self.call()
        self.assertEqual(before, self.snapshot())

    def test_requirements_dispatch_returns_exact_original_claim(self):
        result = self.api.dispatch(self.web['token'], self.web['csrf'],
            dict(workspace='owner', operation='requirements', params={'order_id': 'order1'}))
        self.assertEqual(result['claim'], plan_finance_claim(self.s, 'order1', 'tenant1'))
        self.assertEqual(result['claim_sha256'], hashlib.sha256(canonical(result['claim'])).hexdigest())
        self.assertTrue(result['signed_finance_confirmation_required'])
        self.assertEqual(result['confirmation_audience'], self.finance.audience)
        self.assertEqual(result['reversal_audience'], self.reversal.audience)
        for extra in ('paid', 'trusted_finance_attestation', 'tenant_id'):
            with self.assertRaisesRegex(ValueError, 'INVALID_FULFILLMENT_FIELDS'):
                self.api.dispatch(self.web['token'], self.web['csrf'], dict(workspace='owner',
                    operation='confirm', params=dict(order_id='order1', proof=self.proof(), **{extra: True})))

    def test_session_csrf_and_owner_boundary(self):
        before = self.snapshot()
        for token, csrf in [('invalid', self.web['csrf']), (self.web['token'], ''), (self.web['token'], 'wrong')]:
            with self.assertRaises(PermissionError):
                self.api.fulfill(token, csrf, 'owner', 'order1', self.proof())
        self.fx.stage.owner.role = 'CUSTOMER'
        try:
            with self.assertRaisesRegex(PermissionError, 'OPERATOR_GRANT_CHANGED'): self.call()
        finally: self.fx.stage.owner.role = 'PLATFORM_OWNER'
        self.assertEqual(before, self.snapshot())

    def test_configure_fulfillment_cannot_replace_admitted_instance(self):
        with self.assertRaisesRegex(ValueError, 'CONFIGURED_ORIGINAL_OPERATIONS_REQUIRED_BEFORE_LISTEN'):
            self.app.configure_fulfillment(self.finance, 'replacement', {('storefront_catalog', 'offer1', 1): 1})
        self.assertIs(self.app.fulfillment, self.api)

    def test_external_transactions_rejected_without_consuming_receipt(self):
        for db in (self.s, self.q):
            db.execute('BEGIN')
            try:
                with self.assertRaisesRegex(ValueError, 'EXTERNAL_TRANSACTION_DENIED'): self.call()
            finally: db.rollback()
        self.assertEqual(self.call()['state'], 'COMPLETED')


if __name__ == '__main__':
    unittest.main()
