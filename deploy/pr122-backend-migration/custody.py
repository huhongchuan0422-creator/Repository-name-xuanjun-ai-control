"""Offline operations-state conversion; no live reader, transport or activation.

Inputs must come from a separately admitted, fenced private source snapshot.
This library cannot establish source fencing/identity or authorize deployment.
Never pass trading state, environment files or a live production directory.
"""
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from pr122_oauth_candidate.storage import Database

ORIGIN = 'https://wenwenwenyiyiyi.work'
SOURCE_HOST = 'iZ6wee8q9z4t03hvqumwfhZ'
TARGET_HOST = 'iZvt5t8tlrm8oiZ'
SOURCE_SHA256 = '57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1'
PROVIDERS = ('douyin', 'tiktok')
HEX = re.compile(r'[0-9a-f]{64}\Z')
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,160}\Z')
FIELDS = ('CLIENT_KEY', 'CLIENT_SECRET', 'ACCESS_TOKEN', 'REFRESH_TOKEN')
REFS = {p.upper()+'_'+field: p for p in PROVIDERS for field in FIELDS}


class Hold(RuntimeError):
    """Constant codes only: never interpolate private input or exception text."""


def require(condition, code):
    if not condition:
        raise Hold(code)


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def instant(value):
    try:
        parsed = datetime.fromisoformat(value)
        require(parsed.tzinfo is not None and parsed.utcoffset() is not None, 'TIMEZONE_REQUIRED')
        return parsed
    except (TypeError, ValueError):
        raise Hold('TIMESTAMP_INVALID') from None


def masked(value):
    if len(value) <= 8:
        return value[:1]+'***'
    return value[:4]+'***'+value[-4:]


def normalise(snapshot, *, generation, cutover_id, fence, verify_identity=None):
    """Validate entirely in memory before creating a target generation.

    `fence` is a trusted-caller argument, never accepted from snapshot fields.
    A real root admission/transport must independently verify that attestation.
    `verify_identity` is an explicitly supplied private verification adapter:
    (provider, credential records) -> raw_open_id, access_token_sha256, account.
    No such live adapter is implemented or called by this candidate.
    """
    require(isinstance(generation, str) and HEX.fullmatch(generation), 'SOURCE_GENERATION_INVALID')
    require(isinstance(cutover_id, str) and IDENTIFIER.fullmatch(cutover_id), 'CUTOVER_ID_INVALID')
    require(isinstance(fence, dict) and fence.get('source_host') == SOURCE_HOST
            and fence.get('target_host') == TARGET_HOST
            and fence.get('source_sha256') == SOURCE_SHA256
            and fence.get('source_generation') == generation
            and fence.get('cutover_id') == cutover_id
            and fence.get('writer_fenced') is True
            and type(fence.get('inflight_requests')) is int and fence['inflight_requests'] == 0,
            'PRIVATE_FENCED_SOURCE_ATTESTATION_REQUIRED')
    try:
        wire = json.dumps(snapshot, sort_keys=True, allow_nan=False)
        require(len(wire.encode()) <= 2000000, 'SNAPSHOT_SIZE_LIMIT')
        payload = json.loads(wire)
    except (TypeError, ValueError, RecursionError):
        raise Hold('SNAPSHOT_FORMAT_INVALID') from None
    require(isinstance(payload, dict) and set(payload) == {
        'schema_version', 'source_generation', 'cutover_id', 'sessions',
        'secrets', 'oauth_states', 'lifecycles', 'legacy_bindings'}, 'SNAPSHOT_SCHEMA_INVALID')
    require(type(payload['schema_version']) is int and payload['schema_version'] == 1
            and payload['source_generation'] == generation and payload['cutover_id'] == cutover_id,
            'SNAPSHOT_SOURCE_BINDING_MISMATCH')
    require(isinstance(payload['secrets'], dict) and set(payload['secrets']) <= set(REFS), 'OAUTH_SECRETREFS_ONLY')
    require(isinstance(payload['sessions'], list) and len(payload['sessions']) <= 1000, 'SESSION_LIMIT')
    for key in ('oauth_states', 'lifecycles', 'legacy_bindings'):
        require(isinstance(payload[key], dict) and set(payload[key]) <= set(PROVIDERS), 'PROVIDER_SCOPE_INVALID')
    main = {}
    for ref, record in payload['secrets'].items():
        require(isinstance(record, dict) and record.get('provider') == REFS[ref], 'SECRET_PROVIDER_MISMATCH')
        value = record.get('value')
        require(isinstance(value, str) and 0 < len(value) <= 16384 and '\n' not in value and '\r' not in value, 'SECRET_VALUE_FORMAT')
        # Legacy value_path/configured flags never redirect the new store.
        main['secret:'+ref] = {k: record.get(k, {} if k == 'metadata' else '')
                              for k in ('value', 'provider', 'scope', 'purpose', 'actor', 'metadata')}
        require(isinstance(main['secret:'+ref]['metadata'], dict), 'SECRET_METADATA_FORMAT')
    for provider in PROVIDERS:
        for first, second in (('CLIENT_KEY', 'CLIENT_SECRET'), ('ACCESS_TOKEN', 'REFRESH_TOKEN')):
            require((provider.upper()+'_'+first in payload['secrets']) ==
                    (provider.upper()+'_'+second in payload['secrets']), 'PARTIAL_CREDENTIAL_PAIR')
    session_fields = {'submission_id', 'customer_id', 'account_id', 'exchange', 'credential_schema',
                      'required_credential_types', 'created_at', 'expires_at', 'status', 'nonce',
                      'attempt_count', 'request_correlation_id', 'token_hash'}
    token_hashes = set()
    for session in payload['sessions']:
        require(isinstance(session, dict) and session_fields <= set(session), 'SESSION_SCHEMA_INVALID')
        sid = session['submission_id']
        require(isinstance(sid, str) and IDENTIFIER.fullmatch(sid) and 'session:'+sid not in main, 'SESSION_ID_INVALID_OR_DUPLICATE')
        forms = session['required_credential_types']
        require(isinstance(forms, list) and len(forms) == 1 and forms[0] in PROVIDERS, 'LEGACY_MIXED_SESSION_REQUIRES_SEPARATE_SUCCESSOR')
        require(session.get('portal_origin', session['request_correlation_id']) == ORIGIN, 'SESSION_ORIGIN_MISMATCH')
        require(isinstance(session['token_hash'], str) and HEX.fullmatch(session['token_hash'])
                and session['token_hash'] not in token_hashes, 'SESSION_CSRF_IDENTITY_INVALID')
        token_hashes.add(session['token_hash'])
        require(isinstance(session['nonce'], str) and digest(session['nonce']) == session['token_hash'], 'SESSION_CSRF_HASH_MISMATCH')
        require(instant(session['created_at']) < instant(session['expires_at']), 'SESSION_TIME_RANGE_INVALID')
        if session.get('used_at') is not None:
            instant(session['used_at'])
        require(type(session['attempt_count']) is int and session['attempt_count'] >= 0, 'SESSION_COUNTER_INVALID')
        require(session['status'] in {'PENDING', 'EXPIRED', 'USED', 'COMPLETED', 'CONFIGURED'}, 'SESSION_STATUS_INVALID')
        for field in ('customer_id', 'account_id', 'exchange', 'credential_schema', 'request_correlation_id'):
            require(isinstance(session[field], str) and bool(session[field]), 'SESSION_IDENTITY_REQUIRED')
        attempts = session.get('attempts', {})
        used = session.get('used_forms', {})
        require(isinstance(attempts, dict) and set(attempts) <= set(forms)
                and all(type(n) is int and n >= 0 for n in attempts.values()), 'SESSION_ATTEMPTS_INVALID')
        require(isinstance(used, dict) and set(used) <= set(forms), 'SESSION_USED_FORMS_INVALID')
        main['session:'+sid] = session
    states = {p: {} for p in PROVIDERS}
    for provider, records in payload['oauth_states'].items():
        require(isinstance(records, list) and len(records) <= 2000, 'OAUTH_STATE_LIMIT')
        for state in records:
            require(isinstance(state, dict), 'OAUTH_STATE_FORMAT')
            sh = state.get('state_hash')
            require(isinstance(sh, str) and HEX.fullmatch(sh) and 'state:'+sh not in states[provider], 'OAUTH_STATE_IDENTITY_INVALID')
            require(state.get('redirect_uri') == ORIGIN+'/integrations/'+provider+'/oauth/callback', 'OAUTH_REDIRECT_MISMATCH')
            require(state.get('scopes') in (["user.info.basic"],) if provider == 'tiktok'
                    else state.get('scopes') in (["user_info"], ["trial.whitelist"]), 'OAUTH_SCOPE_INVALID')
            require(instant(state.get('created_at')) < instant(state.get('expires_at')), 'OAUTH_TIME_RANGE_INVALID')
            if state.get('consumed_at') is not None:
                instant(state['consumed_at'])
            ck = payload['secrets'].get(provider.upper()+'_CLIENT_KEY')
            require(ck is not None and state.get('client_key_fingerprint') == digest(ck['value'])[:12], 'OAUTH_CLIENT_BINDING_MISMATCH')
            states[provider]['state:'+sh] = state
    for provider in PROVIDERS:
        prefix = provider.upper()+'_'
        lifecycle = payload['lifecycles'].get(provider)
        legacy = payload['legacy_bindings'].get(provider)
        token = payload['secrets'].get(prefix+'ACCESS_TOKEN')
        if token is None:
            require(lifecycle is None and legacy is None, 'LIFECYCLE_WITHOUT_CREDENTIALS')
            continue
        require(isinstance(lifecycle, dict) and type(lifecycle.get('revoked')) is bool
                and type(lifecycle.get('reauthorization_required')) is bool, 'TOKEN_LIFECYCLE_REQUIRED')
        ck = payload['secrets'].get(prefix+'CLIENT_KEY')
        require(ck is not None and lifecycle.get('client_key_fingerprint') == digest(ck['value'])[:12], 'TOKEN_CLIENT_BINDING_MISMATCH')
        require(lifecycle.get('granted_scopes') == (['user.info.basic'] if provider == 'tiktok' else ['user_info']),
                'TOKEN_SCOPE_INVALID')
        access_expiry = instant(lifecycle.get('access_token_expires_at'))
        if lifecycle.get('refresh_token_expires_at') is not None:
            instant(lifecycle['refresh_token_expires_at'])
        require(legacy is None or isinstance(legacy, dict), 'LEGACY_BINDING_FORMAT')
        main['lifecycle:'+provider] = lifecycle
        if (lifecycle['revoked'] or lifecycle['reauthorization_required']
                or access_expiry <= datetime.now(timezone.utc)
                or (legacy or {}).get('status') == 'DISCONNECTED'):
            main['migration:inactive:'+provider] = {'migration_state': 'PRESERVED_INACTIVE'}
            continue
        # Masked legacy identifiers cannot prove which account owns the token.
        require(callable(verify_identity), 'LIVE_IDENTITY_VERIFICATION_ADAPTER_REQUIRED')
        try:
            verified = verify_identity(provider, {ref: record for ref, record in payload['secrets'].items() if REFS[ref] == provider})
        except Exception:
            raise Hold('IDENTITY_VERIFICATION_FAILED_PRESERVE_SOURCE') from None
        require(isinstance(verified, dict), 'IDENTITY_PROOF_INVALID')
        raw_id = verified.get('raw_open_id')
        require(isinstance(raw_id, str) and bool(raw_id) and verified.get('access_token_sha256') == digest(token['value']), 'TOKEN_IDENTITY_PROOF_MISMATCH')
        # A masked legacy identifier alone is not an exact account anchor.
        anchors = fence.get('account_identity_hashes')
        require(isinstance(anchors, dict) and anchors.get(provider) == digest(raw_id),
                'EXACT_PRIVATE_ACCOUNT_IDENTITY_ANCHOR_REQUIRED')
        account = verified.get('account')
        require(isinstance(account, dict) and account.get('open_id_masked') == masked(raw_id)
                and lifecycle.get('open_id_masked') == masked(raw_id), 'LEGACY_ACCOUNT_IDENTITY_MISMATCH')
        allowed = {'status','open_id_masked','union_id_masked','display_name','nickname','avatar_present','client_key_fingerprint'}
        require(set(account) <= allowed and account.get('status') == 'PASS', 'SANITIZED_ACCOUNT_REQUIRED')
        if legacy and legacy.get('status') == 'CONNECTED':
            require(isinstance(legacy.get('account'), dict)
                    and legacy['account'].get('open_id_masked') == masked(raw_id), 'LEGACY_ACCOUNT_IDENTITY_MISMATCH')
        main['binding:'+provider] = {'verified': True, 'identity_hash': digest(raw_id),
            'account': account, 'lifecycle': lifecycle, 'client_key_fingerprint': digest(ck['value'])[:12]}
    return main, states


def private_json(path, payload):
    fd = os.open(str(path), os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        data = (json.dumps(payload, sort_keys=True, allow_nan=False)+'\n').encode()
        handle.write(data)
        handle.flush()
        os.fchmod(handle.fileno(), 0o600)
        os.fsync(handle.fileno())


def sync_directory(path):
    fd = os.open(str(path), os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def prepare_generation(parent, snapshot, *, generation, cutover_id, fence,
                       verify_identity=None, checkpoint=None):
    """Create a NEW private offline generation; never publish a current pointer.

    On interruption/unknown commit preserve all objects; same cutover cannot be
    retried into the old path. No process/service, network, source data or route
    is changed. Caller may publish a sanitized summary, never the input data.
    """
    main, states = normalise(snapshot, generation=generation, cutover_id=cutover_id,
                             fence=fence, verify_identity=verify_identity)
    parent = Path(parent).absolute()
    for node in (parent, *parent.parents):
        require(not node.is_symlink(), 'TARGET_PARENT_SYMLINK_REJECTED')
    info = parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'TARGET_PRIVATE_PARENT_REQUIRED')
    target = parent/('handoff-'+cutover_id)
    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        raise Hold('TARGET_ALREADY_EXISTS_NO_BLIND_RETRY') from None
    sync_directory(parent)
    stage = 'CREATED'
    try:
        database = Database(target)
        with database.transaction():
            for key, value in main.items():
                database.put(key, value)
        stage = 'MAIN_COMMITTED'
        if checkpoint:
            checkpoint(stage)
        for provider in PROVIDERS:
            state_db = Database(target/(provider+'-oauth-state'))
            with state_db.transaction():
                for key, value in states[provider].items():
                    state_db.put(key, value)
            stage = provider.upper()+'_STATES_COMMITTED'
            if checkpoint:
                checkpoint(stage)
        # These directories are empty; the candidate uses the main DB for data.
        (target/'sessions').mkdir(mode=0o700)
        (target/'operations').mkdir(mode=0o700)
        summary = {'schema_version': 1, 'cutover_id': cutover_id,
                   'source_generation': generation, 'source_sha256': SOURCE_SHA256,
                   'status': 'OFFLINE_GENERATION_PREPARED',
                   'session_count': sum(k.startswith('session:') for k in main),
                   'secretref_count': sum(k.startswith('secret:') for k in main),
                   'oauth_state_counts': {p: len(states[p]) for p in PROVIDERS},
                   'source_changed': False, 'activated': False,
                   'production_approved': False, 'real_snapshot_custody_implemented': False,
                   'live_identity_adapter_implemented': False}
        private_json(target/'HANDOFF.json', summary)
        if checkpoint:
            checkpoint('BEFORE_READY')
        sync_directory(target)
        private_json(target/'READY.json', {'cutover_id': cutover_id,
            'meaning': 'OFFLINE_PREPARATION_ONLY_NOT_PRODUCTION_AUTHORITY'})
        sync_directory(target)
        return summary
    except BaseException:
        # Constant failure receipt does not publish exception strings or inputs.
        try:
            private_json(target/'FAILED.json', {'stage': stage, 'status': 'UNKNOWN_PRESERVE_EVIDENCE',
                                                'automatic_cleanup': False, 'retry_allowed': False})
            sync_directory(target)
        except BaseException:
            pass
        raise Hold('PREPARATION_UNKNOWN_PRESERVE_EVIDENCE') from None
