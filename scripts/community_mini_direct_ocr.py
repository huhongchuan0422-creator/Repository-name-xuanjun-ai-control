"""Original Center-bound single-selection OCR proof; no credentials or network client.

The existing protected host supplies onboarding.direct_ocr_signer. No HTTP/env
configuration, key loading, payment action, new DB/table or permissive fallback.
"""
import datetime
import json
import re
import secrets
from scripts.pr122_customer_core import canonical

CHANNEL = 'COMMUNITY_MINI_DIRECT_OCR_SELECTION_V1'
KINDS = {'bank_card': 'bank_card', 'business_license': 'business_license',
         'id_front': 'identity_front', 'id_back': 'identity_back'}
ACTIONS = {'bank_card': 'RecognizeBankCard', 'business_license': 'RecognizeBusinessLicense',
           'id_front': 'RecognizeIdcard', 'id_back': 'RecognizeIdcard'}
SIGNED = 'content-type;host;x-acs-action;x-acs-content-sha256;x-acs-date;x-acs-signature-nonce;x-acs-version'
HOST = 'ocr-api.cn-hangzhou.aliyuncs.com'
FIELDS = {'application', 'revision', 'provider_version', 'kind', 'digest', 'size', 'intent_key'}

class DirectOcrSelectionChanged(ValueError):
    """Operation-local binding/result failure; never a claim that login was revoked."""


class DirectOcrSelection:
    def __init__(self, onboarding, authorize):
        if not callable(authorize):
            raise ValueError('ORIGINAL_DIRECT_OCR_AUTHORIZER_REQUIRED')
        self.service = onboarding
        self.center = onboarding.center
        self.authorize = authorize

    def uid(self, session, csrf):
        uid = self.center.session(session, csrf)
        if self.authorize()[0] != uid:
            raise PermissionError('DIRECT_OCR_IDENTITY_CHANGED')
        return uid

    def validate(self, p):
        if (type(p) is not dict or set(p) != FIELDS or type(p['application']) is not str
                or type(p['kind']) is not str or p['kind'] not in KINDS
                or type(p['revision']) is not int or p['revision'] < 0
                or type(p['provider_version']) is not int or p['provider_version'] < 0
                or type(p['size']) is not int or not 1 <= p['size'] <= 10_000_000
                or type(p['digest']) is not str or not re.fullmatch('[a-f0-9]{64}', p['digest'])
                or type(p['intent_key']) is not str or not re.fullmatch('[A-Za-z0-9_-]{16,128}', p['intent_key'])):
            raise ValueError('DIRECT_OCR_BINDING_INVALID')

    def key(self, uid, p):
        return self.center.idx('mini-direct-ocr:' + uid + ':' + p['application'] + ':' + p['intent_key'])

    def read(self, uid, p):
        key = self.key(uid, p)
        row = self.center.db.execute('SELECT active,payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND user_id=?',
            (CHANNEL, key, p['application'], uid)).fetchone()
        if row is not None and row['active'] != 1:
            raise DirectOcrSelectionChanged('DIRECT_OCR_SELECTION_REVOKED')
        return json.loads(self.center.decrypt(row['payload'], 'mini-direct-ocr:' + key)) if row else None

    def write(self, uid, p, record):
        key = self.key(uid, p)
        self.center.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload',
            (CHANNEL, key, uid, p['application'], self.center.encrypt(canonical(record), 'mini-direct-ocr:' + key)))

    def current(self, uid, p, record, *, for_sign=True):
        owner, meta, data = self.service._load(p['application'], uid)
        provider = self.service.wechat_applyment
        state = provider._read(p['application']) if provider is not None else None
        version = state['version'] if state else 0
        if (data['status'] not in ('DRAFT', 'CORRECTION_REQUIRED') or version != p['provider_version']
                or state and state.get('state') not in ('DRAFT', 'CORRECTION')):
            raise DirectOcrSelectionChanged('DIRECT_OCR_SOURCE_CHANGED')
        if record is not None:
            if record['binding'] != p or for_sign and self.center.now() > record['expires_at']:
                raise DirectOcrSelectionChanged('DIRECT_OCR_SELECTION_CHANGED_OR_EXPIRED')
        same_original = data['revision'] == p['revision']
        own_save = (record is not None and record.get('saved_revision') == data['revision'] == p['revision'] + 1
                    and meta['materials'].get(KINDS[p['kind']]) == record.get('saved_material'))
        if not (same_original or own_save):
            raise DirectOcrSelectionChanged('DIRECT_OCR_SOURCE_CHANGED')
        return meta, data

    def reserve(self, uid, p, *, for_sign=True):
        record = self.read(uid, p)
        self.current(uid, p, record, for_sign=for_sign)
        return record or dict(binding=dict(p), expires_at=self.center.now() + 60,
                              sign_attempted=False, save_attempted=False)

    def sign(self, session, csrf, p):
        self.validate(p)
        uid = self.uid(session, csrf)
        with self.center.tx():
            record = self.reserve(uid, p)
            if record.get('headers') is not None:
                return {'headers': dict(record['headers'])}
            if record['sign_attempted']:
                raise DirectOcrSelectionChanged('DIRECT_OCR_SIGN_RESULT_UNKNOWN')
            signer = getattr(self.service, 'direct_ocr_signer', None)
            if not callable(signer):
                raise ValueError('DIRECT_OCR_SIGNER_UNAVAILABLE')
            record['sign_attempted'] = True
            self.write(uid, p, record)
            self.center.audit(p['application'],uid,'MINI_DIRECT_OCR_SIGN_ATTEMPT',self.key(uid,p))
        # Call only the original protected signer, once. Never hold its external
        # RPC inside the Center transaction, nor retry an unknown signing call.
        date = datetime.datetime.fromtimestamp(self.center.now(), datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        nonce = secrets.token_hex(16)
        request = dict(subject=uid, application=p['application'], selection_id=p['intent_key'],
                       application_revision=p['revision'], provider_version=p['provider_version'],
                       action=ACTIONS[p['kind']], host=HOST, method='POST', path='/',
                       content_type='application/octet-stream', signed_headers=SIGNED, api_version='2021-07-07',
                       digest=p['digest'], size=p['size'], signed_at=date, nonce=nonce)
        try:
            result = signer(request)
        except Exception:
            raise ValueError('DIRECT_OCR_SIGN_RESULT_UNKNOWN') from None
        headers = result.get('headers') if type(result) is dict and set(result) == {'headers'} else None
        expected = {'content-type': 'application/octet-stream', 'x-acs-action': ACTIONS[p['kind']],
                    'x-acs-content-sha256': p['digest'], 'x-acs-date': date,
                    'x-acs-signature-nonce': nonce, 'x-acs-version': '2021-07-07'}
        if (type(headers) is not dict or set(headers) != set(expected) | {'authorization'}
                or any(headers.get(k) != v for k, v in expected.items())
                or type(headers.get('authorization')) is not str
                or not re.fullmatch('ACS3-HMAC-SHA256 Credential=[A-Za-z0-9_-]{1,128},SignedHeaders=' + SIGNED + ',Signature=[a-f0-9]{64}', headers['authorization'])):
            raise ValueError('DIRECT_OCR_PROOF_INVALID')
        with self.center.tx():
            if self.uid(session, csrf) != uid:
                raise PermissionError('DIRECT_OCR_IDENTITY_CHANGED')
            record = self.reserve(uid, p)
            record['headers'] = dict(headers)
            self.write(uid, p, record)
            self.center.audit(p['application'],uid,'MINI_DIRECT_OCR_SIGN_ISSUED',self.key(uid,p))
        return {'headers': dict(headers)}

    def upload(self, session, csrf, params, invoke):
        p = params['direct_ocr_binding']
        self.validate(p)
        if (params.get('application') != p['application'] or params.get('revision') != p['revision']
                or params.get('kind') != KINDS[p['kind']]):
            raise ValueError('DIRECT_OCR_UPLOAD_BINDING_INVALID')
        uid = self.uid(session, csrf)
        with self.center.tx():
            # Photo authorization remains the original owner/revision CAS; an
            # expired/failed OCR proof never blocks this independent save.
            # The original proof expiry is retained, never extended here.
            record = self.reserve(uid, p, for_sign=False)
            if record['save_attempted']:
                raise DirectOcrSelectionChanged('DIRECT_OCR_SAVE_RESULT_UNKNOWN')
            record['save_attempted'] = True
            self.write(uid, p, record)
            self.center.audit(p['application'],uid,'MINI_DIRECT_PHOTO_SAVE_ATTEMPT',self.key(uid,p))
        clean = {k: v for k, v in params.items() if k != 'direct_ocr_binding'}
        result = invoke(clean)
        with self.center.tx():
            if self.uid(session, csrf) != uid:
                raise PermissionError('DIRECT_OCR_IDENTITY_CHANGED')
            _, meta, data = self.service._load(p['application'], uid)
            if data['revision'] != p['revision'] + 1 or result.get('revision') != data['revision']:
                raise DirectOcrSelectionChanged('DIRECT_OCR_SOURCE_CHANGED')
            record = self.read(uid, p)
            record['saved_revision'] = data['revision']
            record['saved_material'] = meta['materials'][KINDS[p['kind']]]
            self.write(uid, p, record)
        return dict(result, direct_ocr_receipt=dict(intent_key=p['intent_key'], digest=p['digest'],
            kind=p['kind'], original_revision=p['revision'], saved_revision=result['revision'],
            provider_version=p['provider_version']))
