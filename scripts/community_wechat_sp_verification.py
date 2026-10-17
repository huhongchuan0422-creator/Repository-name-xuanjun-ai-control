"""Pure public-key-mode APIv3 signature/decryption candidate. No network or writes.

Official protocol: https://pay.wechatpay.cn/doc/v3/partner/4019605946
Cryptographic verification alone never attests reconciliation or posts Finance.
Key material and expected order bindings must come from protected server config.
"""
import base64
import hashlib
import json
import re
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
    if type(value) is not dict:
        raise ValueError('JSON_OBJECT_REQUIRED')
    return value


def verify_signed_body(headers, raw_body, public_key_pem, expected_key_id, now):
    if type(raw_body) is not bytes or len(raw_body) > 1048576:
        raise ValueError('INVALID_BODY')
    if type(now) is not int or now < 0 or type(headers) is not dict:
        raise ValueError('INVALID_TRUSTED_CONTEXT')
    normalized = {}
    for name, value in headers.items():
        if type(name) is not str or type(value) is not str:
            raise ValueError('INVALID_HEADERS')
        name = name.lower()
        if name in normalized:
            raise ValueError('DUPLICATE_HEADER')
        normalized[name] = value
    if (type(expected_key_id) is not str or not expected_key_id.startswith('PUB_KEY_ID_')
            or normalized.get('wechatpay-serial') != expected_key_id):
        raise ValueError('PINNED_PUBLIC_KEY_REQUIRED')
    timestamp = normalized.get('wechatpay-timestamp', '')
    nonce = normalized.get('wechatpay-nonce', '')
    if not re.fullmatch('[0-9]{1,12}', timestamp) or abs(now-int(timestamp)) > 300:
        raise ValueError('SIGNATURE_TIME_WINDOW')
    if not re.fullmatch('[A-Za-z0-9_-]{1,128}', nonce):
        raise ValueError('INVALID_NONCE')
    algorithm = normalized.get('wechatpay-signature-type', 'WECHATPAY2-SHA256-RSA2048')
    if algorithm != 'WECHATPAY2-SHA256-RSA2048':
        raise ValueError('INVALID_SIGNATURE_TYPE')
    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
        raise ValueError('RSA_2048_REQUIRED')
    signature = normalized.get('wechatpay-signature', '')
    if len(signature) > 2048:
        raise ValueError('INVALID_SIGNATURE')
    try:
        signature = base64.b64decode(signature, validate=True)
        key.verify(signature, timestamp.encode()+b'\n'+nonce.encode()+b'\n'+raw_body+b'\n',
                   padding.PKCS1v15(), hashes.SHA256())
    except (InvalidSignature, ValueError) as exc:
        raise ValueError('INVALID_SIGNATURE') from exc
    return {'body_sha256': hashlib.sha256(raw_body).hexdigest(),
            'signature_key_id': expected_key_id, 'finance_write': False,
            'reconciliation': 'REQUIRED', 'replay_authorization': False}


def notification_candidate(headers, raw_body, public_key_pem, expected_key_id,
                           api_v3_key, expected_order, now):
    verified = verify_signed_body(headers, raw_body, public_key_pem, expected_key_id, now)
    if type(api_v3_key) is not bytes or len(api_v3_key) != 32:
        raise ValueError('API_V3_KEY_REQUIRED')
    required = {'sp_mchid', 'sub_mchid', 'sp_appid', 'out_trade_no', 'amount_minor', 'currency'}
    if type(expected_order) is not dict or set(expected_order) != required:
        raise ValueError('SERVER_ORDER_BINDING_REQUIRED')
    if type(expected_order['amount_minor']) is not int or not 1 <= expected_order['amount_minor'] <= 100000000:
        raise ValueError('INVALID_SERVER_AMOUNT')
    if expected_order['currency'] != 'CNY' or any(type(expected_order[k]) is not str or not expected_order[k] for k in required-{'amount_minor'}):
        raise ValueError('INVALID_SERVER_BINDING')
    event = _json(raw_body)
    if event.get('event_type') != 'TRANSACTION.SUCCESS' or event.get('resource_type') != 'encrypt-resource':
        raise ValueError('UNSUPPORTED_NOTIFICATION')
    event_id = event.get('id')
    if type(event_id) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,128}', event_id):
        raise ValueError('INVALID_EVENT_ID')
    resource = event.get('resource')
    if type(resource) is not dict or resource.get('algorithm') != 'AEAD_AES_256_GCM':
        raise ValueError('INVALID_RESOURCE')
    nonce, aad, ciphertext = resource.get('nonce'), resource.get('associated_data', ''), resource.get('ciphertext')
    if type(nonce) is not str or len(nonce.encode()) != 12 or type(aad) is not str or type(ciphertext) is not str:
        raise ValueError('INVALID_RESOURCE_FIELDS')
    try:
        plain = AESGCM(api_v3_key).decrypt(nonce.encode(), base64.b64decode(ciphertext, validate=True), aad.encode())
    except (ValueError, InvalidTag) as exc:
        raise ValueError('RESOURCE_DECRYPTION_FAILED') from exc
    payment = _json(plain)
    for field in ('sp_mchid', 'sub_mchid', 'sp_appid', 'out_trade_no'):
        if payment.get(field) != expected_order[field]:
            raise ValueError('ORDER_BINDING_MISMATCH')
    amount = payment.get('amount')
    if (type(amount) is not dict or type(amount.get('total')) is not int
            or amount['total'] != expected_order['amount_minor'] or amount.get('currency') != expected_order['currency']):
        raise ValueError('ORDER_AMOUNT_MISMATCH')
    tx = payment.get('transaction_id')
    if payment.get('trade_state') != 'SUCCESS' or type(tx) is not str or not re.fullmatch('[0-9]{1,64}', tx):
        raise ValueError('INVALID_TRANSACTION')
    return dict(verified, event_id=event_id, transaction_id=tx,
                out_trade_no=expected_order['out_trade_no'], state='SIGNED_NOTIFICATION_CANDIDATE',
                provider_settlement_verified=False, payment='HOLD', refund='HOLD', profitsharing='HOLD')
