"""Verified raw payment callbacks bound to original customer-order reservations."""
import hashlib
import json
import re
from scripts.pr122_customer_core import canonical
from scripts.community_wechat_sp_verification import notification_candidate
from scripts.community_order_store import state


class PaymentNotifications:
    def __init__(self, payments, api_v3_key, path='/wechat/community/notify'):
        from scripts.community_mini_payments import MiniPayments
        if type(payments) is not MiniPayments or type(api_v3_key) is not bytes or len(api_v3_key) != 32:
            raise ValueError('ORIGINAL_PAYMENTS_AND_API_V3_KEY_REQUIRED')
        if type(path) is not str or not re.fullmatch('/wechat/[A-Za-z0-9_/-]{1,120}', path):
            raise ValueError('FIXED_NOTIFICATION_PATH_REQUIRED')
        self.payments, self.center, self.path = payments, payments.identity.center, path
        self._api = api_v3_key

    def __repr__(self):
        return '<PaymentNotifications API key redacted>'

    def receive(self, headers, raw):
        # Signature is verified before decrypting any body or choosing an order.
        from scripts.community_wechat_sp_verification import verify_signed_body, _json
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import base64
        reader = self.payments.prepay.reader
        now = self.center.now()
        verify_signed_body(headers, raw, reader._public, reader._kid, now)
        event = _json(raw)
        resource = event.get('resource')
        if type(resource) is not dict or resource.get('algorithm') != 'AEAD_AES_256_GCM':
            raise ValueError('INVALID_ENCRYPTED_RESOURCE')
        nonce, aad, ciphertext = resource.get('nonce'), resource.get('associated_data', ''), resource.get('ciphertext')
        if type(nonce) is not str or len(nonce.encode()) != 12 or type(aad) is not str or type(ciphertext) is not str:
            raise ValueError('INVALID_NOTIFICATION_RESOURCE')
        payment = _json(AESGCM(self._api).decrypt(nonce.encode(), base64.b64decode(ciphertext, validate=True), aad.encode()))
        out_trade_no = payment.get('out_trade_no')
        if type(out_trade_no) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,32}', out_trade_no):
            raise ValueError('INVALID_PROVIDER_REFERENCE')
        key = self.center.idx('community-payment-notify:' + reader._mchid + ':' + out_trade_no)
        row = self.center.db.execute("SELECT user_id,project,payload FROM links WHERE channel='COMMUNITY_PAYMENT_BINDING' AND subject_idx=? AND active=1", (key,)).fetchone()
        if row is None:
            raise PermissionError('ORIGINAL_PAYMENT_BINDING_REQUIRED')
        binding = json.loads(self.center.decrypt(row['payload'], 'community-payment-binding:' + key))
        if binding['user_id'] != row['user_id'] or binding['project'] != row['project']:
            raise PermissionError('PAYMENT_OWNERSHIP_CHANGED')
        expected = binding['expected']
        candidate = notification_candidate(headers, raw, reader._public, reader._kid, self._api, expected, now)
        order = state(self.payments.identity.runtime.demo.db, binding['scope'], binding['reference'])
        if order['amount_minor'] != expected['amount_minor'] or order['currency'] != 'CNY':
            raise PermissionError('ORIGINAL_ORDER_AMOUNT_CHANGED')
        # Original ownership remains mandatory; callback does not reassign accounts.
        owner_key = self.center.idx('community-order:' + canonical([binding['scope'], binding['reference']]).decode())
        owner = self.center.db.execute("SELECT user_id,project FROM links WHERE channel='COMMUNITY_ORDER' AND subject_idx=? AND active=1", (owner_key,)).fetchone()
        if owner is None or tuple(owner) != (binding['user_id'], binding['project']):
            raise PermissionError('ORIGINAL_CUSTOMER_ORDER_REQUIRED')
        event_key = hashlib.sha256(canonical([reader._mchid, candidate['event_id']])).hexdigest()
        evidence = dict(source='SIGNED_PROVIDER_NOTIFICATION', signature_key_id=reader._kid,
            out_trade_no=out_trade_no, amount_minor=expected['amount_minor'], currency='CNY',
            provider_state='SUCCESS', transaction_id=candidate['transaction_id'], body_sha256=candidate['body_sha256'])
        # Projection is idempotent across different notifications for the same payment.
        from scripts.community_order_provider_projection import project_verified_query
        project_verified_query(self.payments.identity.runtime.demo.db, binding['scope'], binding['reference'], expected, evidence, now, reader._kid)
        with self.center.tx():
            old = self.center.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_PAYMENT_CALLBACK' AND subject_idx=? AND active=1", (event_key,)).fetchone()
            value = dict(reference=binding['reference'], transaction_id=candidate['transaction_id'], body_sha256=candidate['body_sha256'])
            if old:
                if json.loads(self.center.decrypt(old[0], 'community-payment-callback:' + event_key)) != value:
                    raise ValueError('PAYMENT_NOTIFICATION_EVENT_COLLISION')
            else:
                self.center.db.execute("INSERT INTO links VALUES('COMMUNITY_PAYMENT_CALLBACK',?,?,?,?,1)", (event_key, binding['user_id'], binding['project'], self.center.encrypt(canonical(value), 'community-payment-callback:' + event_key)))
            from scripts.community_customer_profile import notify
            notify(self.center,binding['project'],binding['user_id'],'PAYMENT_CONFIRMED',binding['reference'],'微信支付已确认；订单 '+binding['reference'])
            self.center.audit(binding['project'], binding['user_id'], 'COMMUNITY_PAYMENT_CALLBACK_CONFIRMED', event_key)
        return dict(accepted=True, finance_status='UNCONFIRMED')
