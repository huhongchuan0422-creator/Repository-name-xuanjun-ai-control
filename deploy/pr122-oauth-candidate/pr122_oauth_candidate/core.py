import fcntl, hashlib, html, json, os, secrets, tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path

STATUS_PENDING = "PENDING"
DOUYIN_CLIENT_KEY_REF = 'DOUYIN_CLIENT_KEY'

DOUYIN_CLIENT_SECRET_REF = 'DOUYIN_CLIENT_SECRET'

DOUYIN_ACCESS_TOKEN_REF = 'DOUYIN_ACCESS_TOKEN'

DOUYIN_REFRESH_TOKEN_REF = 'DOUYIN_REFRESH_TOKEN'

TIKTOK_CLIENT_KEY_REF = 'TIKTOK_CLIENT_KEY'

TIKTOK_CLIENT_SECRET_REF = 'TIKTOK_CLIENT_SECRET'

TIKTOK_ACCESS_TOKEN_REF = 'TIKTOK_ACCESS_TOKEN'

TIKTOK_REFRESH_TOKEN_REF = 'TIKTOK_REFRESH_TOKEN'

@dataclass
class CredentialSubmissionSession:
    submission_id: str
    customer_id: str
    account_id: str
    exchange: str
    credential_schema: str
    required_credential_types: tuple
    created_at: datetime
    expires_at: datetime
    status: str
    nonce: str
    attempt_count: int
    request_correlation_id: str
    token_hash: str
    used_at: datetime = None
    idempotency_key: str = None
    result: dict = None

    def sanitized(self):
        return {'submission_id': self.submission_id, 'customer_id': self.customer_id, 'account_id': self.account_id, 'exchange': self.exchange, 'credential_schema': self.credential_schema, 'required_credential_types': list(self.required_credential_types), 'created_at': _iso(self.created_at), 'expires_at': _iso(self.expires_at), 'used_at': _iso(self.used_at), 'status': self.status, 'nonce': self.nonce, 'attempt_count': self.attempt_count, 'request_correlation_id': self.request_correlation_id}

def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)

def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value

def _sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def _write_json_0600(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=True, sort_keys=True, indent=2)
            handle.write('\n')
        os.chmod(tmp_name, 384)
        os.replace(tmp_name, path)
        os.chmod(path, 384)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)

def _write_text_0600(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(value)
        os.chmod(tmp_name, 384)
        os.replace(tmp_name, path)
        os.chmod(path, 384)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)

def secure_headers():
    return {'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'", 'X-Frame-Options': 'DENY', 'X-Content-Type-Options': 'nosniff'}

class OperationsSecretRefStore:
    """File-backed operations SecretRef store, separate from CredentialStore."""

    def __init__(self, root):
        self.root = Path(root)
        self.value_dir = self.root / 'values'
        self.metadata_dir = self.root / 'metadata'
        self.audit_file = self.root / 'audit.jsonl'
        self._ensure()

    def _ensure(self):
        for directory in (self.root, self.value_dir, self.metadata_dir):
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 448)

    def _safe_name(self, ref):
        return ''.join((char if char.isalnum() or char in '-_.' else '_' for char in ref))

    def store_secret(self, ref, value, provider, scope, purpose, actor, metadata=None):
        if not value or '\n' in value or '\r' in value:
            return {'status': 'INVALID', 'reason': 'SECRET_FORMAT_INVALID'}
        safe = self._safe_name(ref)
        value_path = self.value_dir / (safe + '.secret')
        metadata_path = self.metadata_dir / (safe + '.json')
        _write_text_0600(value_path, value)
        payload = {'provider': provider, 'ref': ref, 'scope': scope, 'purpose': purpose, 'configured': True, 'value_path': str(value_path), 'value_recorded': False, 'created_at': _iso(utc_now()), 'actor': actor, 'metadata': metadata or {}}
        _write_json_0600(metadata_path, payload)
        self.record_audit({'operation': 'OPERATIONS_SECRETREF_STORE', 'provider': provider, 'ref': ref, 'scope': scope, 'purpose': purpose, 'actor': actor, 'result': 'CONFIGURED'})
        return {'status': 'CONFIGURED', 'ref': ref, 'metadata_path': str(metadata_path), 'returns_secret': False}

    def read_secret(self, ref):
        safe = self._safe_name(ref)
        value_path = self.value_dir / (safe + '.secret')
        if not value_path.exists():
            return None
        return value_path.read_text(encoding='utf-8')

    def record_audit(self, event):
        redacted = dict(event)
        for key in list(redacted):
            if any((token in key.lower() for token in ('secret', 'token', 'api_key', 'api_secret', 'authorization'))):
                redacted[key] = '[REDACTED]'
        redacted['timestamp'] = _iso(utc_now())
        with self.audit_file.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(redacted, ensure_ascii=True, sort_keys=True) + '\n')
        os.chmod(self.audit_file, 384)

    def status(self, ref):
        metadata_path = self.metadata_dir / (self._safe_name(ref) + '.json')
        if not metadata_path.exists():
            return 'MISSING'
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        return 'CONFIGURED' if metadata.get('configured') else 'MISSING'

    def all_configured(self, refs):
        return all((self.status(ref) == 'CONFIGURED' for ref in refs))

class FileBackedSubmissionSessionRepository:
    """Durable repository for existing CredentialSubmissionSession objects."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 448)

    def _path(self, submission_id):
        safe = ''.join((char if char.isalnum() or char in '-_.' else '_' for char in str(submission_id)))
        return self.root / (safe + '.json')

    def _serialize(self, session):
        payload = session.sanitized()
        payload.update({'token_hash': session.token_hash, 'idempotency_key': session.idempotency_key, 'result': session.result, 'used_forms': dict(getattr(session, 'used_forms', {})), 'attempts': dict(getattr(session, 'attempts', {})), 'portal_origin': getattr(session, 'portal_origin', session.request_correlation_id)})
        return payload

    def _deserialize(self, payload):

        def parse(value):
            return datetime.fromisoformat(value) if value else None
        session = CredentialSubmissionSession(submission_id=payload['submission_id'], customer_id=payload['customer_id'], account_id=payload['account_id'], exchange=payload['exchange'], credential_schema=payload['credential_schema'], required_credential_types=tuple(payload.get('required_credential_types') or ()), created_at=parse(payload['created_at']), expires_at=parse(payload['expires_at']), status=payload['status'], nonce=payload['nonce'], attempt_count=int(payload.get('attempt_count') or 0), request_correlation_id=payload['request_correlation_id'], token_hash=payload['token_hash'], used_at=parse(payload.get('used_at')), idempotency_key=payload.get('idempotency_key'), result=payload.get('result'))
        session.used_forms = dict(payload.get('used_forms') or {})
        session.attempts = dict(payload.get('attempts') or {})
        session.portal_origin = payload.get('portal_origin') or session.request_correlation_id
        return session

    def save(self, session):
        _write_json_0600(self._path(session.submission_id), self._serialize(session))
        return session

    def get(self, submission_id):
        path = self._path(submission_id)
        if not path.exists():
            return None
        return self._deserialize(json.loads(path.read_text(encoding='utf-8')))

    def get_by_token_hash(self, token_hash):
        for path in sorted(self.root.glob('*.json')):
            payload = json.loads(path.read_text(encoding='utf-8'))
            if payload.get('token_hash') == token_hash:
                return self._deserialize(payload)
        return None

    @contextmanager
    def locked(self, submission_id):
        """Hold a cross-thread/process lock for one session transaction."""
        lock_path = self._path(submission_id).with_suffix('.lock')
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 384)
        os.chmod(lock_path, 384)
        with os.fdopen(descriptor, 'r+') as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield self.get(submission_id)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

class SecureSecretsPortalService:

    def __init__(self, state_root, operations_root):
        self.operations_store = OperationsSecretRefStore(operations_root)
        self.sessions = FileBackedSubmissionSessionRepository(Path(state_root) / 'sessions')
        self.ttl_seconds = 1800
        self.max_attempts_per_form = 3

    def create_session(self, customer_id, account_id, origin, allowed_forms=None):
        if not allowed_forms or not set(allowed_forms) <= {'douyin', 'tiktok'}:
            raise ValueError('OAUTH_FORMS_ONLY')
        csrf = secrets.token_urlsafe(32)
        now = utc_now()
        session = CredentialSubmissionSession(submission_id='portal_' + secrets.token_urlsafe(16), customer_id=customer_id, account_id=account_id, exchange='UNIFIED', credential_schema='UNIFIED_SECURE_SECRETS_PORTAL_V1', required_credential_types=tuple(allowed_forms), created_at=now, expires_at=now + timedelta(seconds=self.ttl_seconds), status=STATUS_PENDING, nonce=csrf, attempt_count=0, request_correlation_id=origin, token_hash=_sha(csrf))
        session.used_forms = {}
        session.attempts = {}
        session.portal_origin = origin
        self.sessions.save(session)
        return {**self._sanitized_session(session), 'csrf_token': csrf}

    def submit_douyin(self, session_id, csrf_token, origin, payload, actor='owner'):
        form_key = 'douyin'
        checked = self._validate_submit(session_id, csrf_token, origin, None, None, form_key)
        if checked['status'] != 'PASS':
            return checked
        session = self.sessions.get(session_id)
        if form_key not in session.required_credential_types:
            return {'status': 'REJECTED', 'sanitized_error_code': 'FORM_NOT_ALLOWED'}
        client_key = (payload.get('client_key') or '').strip()
        client_secret = (payload.get('client_secret') or '').strip()
        if not client_key or not client_secret:
            return {'status': 'INVALID', 'reason': 'DOUYIN_CLIENT_KEY_SECRET_REQUIRED'}
        key_fingerprint = _sha(client_key)[:12]
        stored = [self.operations_store.store_secret(DOUYIN_CLIENT_KEY_REF, client_key, 'douyin', 'douyin_open_api_oauth', 'douyin client key for readonly oauth user_info verification', actor=actor, metadata={'credential_type': 'Operations Secret', 'field': 'client_key', 'client_key_fingerprint': key_fingerprint, 'application_name': payload.get('application_name') or '', 'configured_redirect_uri': payload.get('configured_redirect_uri') or ''}), self.operations_store.store_secret(DOUYIN_CLIENT_SECRET_REF, client_secret, 'douyin', 'douyin_open_api_oauth', 'douyin client secret for readonly oauth user_info verification', actor=actor, metadata={'credential_type': 'Operations Secret', 'field': 'client_secret', 'client_key_fingerprint': key_fingerprint, 'application_name': payload.get('application_name') or '', 'configured_redirect_uri': payload.get('configured_redirect_uri') or ''})]
        if all((item['status'] == 'CONFIGURED' for item in stored)):
            session.used_forms[form_key] = 'CONFIGURED'
            self.sessions.save(session)
            return {'status': 'CONFIGURED', 'secretrefs': [DOUYIN_CLIENT_KEY_REF, DOUYIN_CLIENT_SECRET_REF], 'client_key_fingerprint': key_fingerprint, 'mode': 'OPEN_API_OAUTH_READONLY_FOUNDATION', 'returns_secret': False}
        return {'status': 'INVALID', 'reason': 'DOUYIN_SECRETREF_STORE_FAILED'}

    def submit_tiktok(self, session_id, csrf_token, origin, payload, actor='owner'):
        form_key = 'tiktok'
        checked = self._validate_submit(session_id, csrf_token, origin, None, None, form_key)
        if checked['status'] != 'PASS':
            return checked
        session = self.sessions.get(session_id)
        if form_key not in session.required_credential_types:
            return {'status': 'REJECTED', 'sanitized_error_code': 'FORM_NOT_ALLOWED'}
        client_key = (payload.get('client_key') or '').strip()
        client_secret = (payload.get('client_secret') or '').strip()
        if not client_key or not client_secret:
            return {'status': 'INVALID', 'reason': 'TIKTOK_CLIENT_KEY_SECRET_REQUIRED'}
        key_fingerprint = _sha(client_key)[:12]
        stored = [self.operations_store.store_secret(TIKTOK_CLIENT_KEY_REF, client_key, 'tiktok', 'tiktok_login_kit_sandbox', 'tiktok sandbox client key for Login Kit user.info.basic demo', actor=actor, metadata={'credential_type': 'Operations Secret', 'field': 'client_key', 'client_key_fingerprint': key_fingerprint, 'application_name': payload.get('application_name') or '', 'sandbox_name': payload.get('sandbox_name') or '', 'configured_redirect_uri': payload.get('configured_redirect_uri') or '', 'sandbox_credential': True}), self.operations_store.store_secret(TIKTOK_CLIENT_SECRET_REF, client_secret, 'tiktok', 'tiktok_login_kit_sandbox', 'tiktok sandbox client secret for Login Kit user.info.basic demo', actor=actor, metadata={'credential_type': 'Operations Secret', 'field': 'client_secret', 'client_key_fingerprint': key_fingerprint, 'application_name': payload.get('application_name') or '', 'sandbox_name': payload.get('sandbox_name') or '', 'configured_redirect_uri': payload.get('configured_redirect_uri') or '', 'sandbox_credential': True})]
        if all((item['status'] == 'CONFIGURED' for item in stored)):
            session.used_forms[form_key] = 'CONFIGURED'
            self.sessions.save(session)
            return {'status': 'CONFIGURED', 'secretrefs': [TIKTOK_CLIENT_KEY_REF, TIKTOK_CLIENT_SECRET_REF], 'client_key_fingerprint': key_fingerprint, 'mode': 'LOGIN_KIT_SANDBOX_USER_INFO_BASIC', 'returns_secret': False}
        return {'status': 'INVALID', 'reason': 'TIKTOK_SECRETREF_STORE_FAILED'}

    def _require_session(self, session_id):
        session = self.sessions.get(session_id)
        if not session:
            return {'status': 'REJECTED', 'sanitized_error_code': 'SESSION_NOT_FOUND'}
        if utc_now() >= session.expires_at:
            session.status = 'EXPIRED'
            return {'status': 'REJECTED', 'sanitized_error_code': 'SESSION_EXPIRED'}
        return session

    def _validate_submit(self, session_id, csrf_token, origin, customer_id, account_id, form_key):
        return self._validate_submit_session(self.sessions.get(session_id), csrf_token, origin, customer_id, account_id, form_key)

    def _validate_submit_session(self, session, csrf_token, origin, customer_id, account_id, form_key):
        if not session:
            return {'status': 'REJECTED', 'sanitized_error_code': 'SESSION_NOT_FOUND'}
        if utc_now() >= session.expires_at:
            session.status = 'EXPIRED'
            return {'status': 'REJECTED', 'sanitized_error_code': 'SESSION_EXPIRED'}
        if origin != session.portal_origin:
            return {'status': 'REJECTED', 'sanitized_error_code': 'ORIGIN_INVALID'}
        if _sha(csrf_token or '') != session.token_hash:
            return {'status': 'REJECTED', 'sanitized_error_code': 'CSRF_INVALID'}
        if customer_id is not None and (customer_id != session.customer_id or account_id != session.account_id):
            return {'status': 'REJECTED', 'sanitized_error_code': 'BINDING_MISMATCH'}
        if form_key in session.used_forms:
            return {'status': 'REJECTED', 'sanitized_error_code': 'FORM_ALREADY_USED'}
        count = session.attempts.get(form_key, 0) + 1
        session.attempts[form_key] = count
        self.sessions.save(session)
        if count > self.max_attempts_per_form:
            return {'status': 'REJECTED', 'sanitized_error_code': 'RATE_LIMIT'}
        return {'status': 'PASS'}

    def _sanitized_session(self, session):
        return {'session_id': session.submission_id, 'customer_id': session.customer_id, 'account_id': session.account_id, 'allowed_forms': list(session.required_credential_types), 'origin': session.portal_origin, 'created_at': _iso(session.created_at), 'expires_at': _iso(session.expires_at), 'status': session.status, 'used_forms': dict(session.used_forms), 'attempts': dict(session.attempts)}

    def _status_only(self, result):
        sanitized = {key: value for key, value in result.items() if key not in {'api_key', 'api_secret', 'key_ciphertext', 'secret_ciphertext'}}
        dumped = json.dumps(sanitized, sort_keys=True, default=str).lower()
        if any((token in dumped for token in ('api_key', 'api_secret', 'secret_ciphertext', 'key_ciphertext'))):
            return {'status': 'REJECTED', 'sanitized_error_code': 'SECRET_LEAK_BLOCKED'}
        return sanitized
