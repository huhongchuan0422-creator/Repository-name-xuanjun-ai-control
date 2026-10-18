"""Bounded, offline §8.2.7 request receipts in the existing Center database.

Authenticated server boundaries supply uid; never accept a browser actor ID.
The optional privacy_policy_context(uid, pid) is protected server configuration,
not request JSON. Acknowledgement records a choice, not acceptance of a legal
agreement or a legal determination. Requests do not correct, delete, or purge
source evidence. No processing authority or additional role is introduced.
"""
import json
import re
import secrets

from scripts.pr122_customer_core import Denied, Conflict, Unavailable, canonical, digest, safe_text

POLICY_FIELDS = ('notice_text', 'notice_ref', 'notice_version', 'notice_sha256', 'consent_version',
                 'consent_scope', 'retention_policy', 'retention_period_ref',
                 'correction_process_ref', 'deletion_process_ref')
MAX_HISTORY = 1000
DDL = '''
CREATE TABLE IF NOT EXISTS privacy_receipts(
 seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, project TEXT NOT NULL,
 requester TEXT NOT NULL, idem TEXT NOT NULL, payload BLOB NOT NULL,
 sha TEXT NOT NULL, UNIQUE(project,requester,idem));
CREATE INDEX IF NOT EXISTS privacy_scope ON privacy_receipts(project,requester,seq);
CREATE TRIGGER IF NOT EXISTS privacy_no_update BEFORE UPDATE ON privacy_receipts
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS privacy_no_delete BEFORE DELETE ON privacy_receipts
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS privacy_no_replace BEFORE INSERT ON privacy_receipts
WHEN EXISTS(SELECT 1 FROM privacy_receipts WHERE id=NEW.id OR seq=NEW.seq
 OR (project=NEW.project AND requester=NEW.requester AND idem=NEW.idem))
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
'''


def install(c):
    """Protected additive installation; call outside an active transaction."""
    if c.db.in_transaction:
        raise Denied('PRIVACY_INSTALL_TRANSACTION')
    c.db.executescript(DDL)


def verify(c):
    """Verify stored history independently of live grants, projects, or policy.

    Revoked and orphan history remains verifiable for backup integrity; this
    function grants no customer access and returns no decrypted receipt bodies.
    """
    if not c.db.in_transaction:
        with c.tx():
            return verify(c)
    heads = {}
    count = 0
    for row in c.db.execute('SELECT * FROM privacy_receipts ORDER BY seq'):
        try:
            value = json.loads(c.decrypt(row['payload'], 'privacy:' + row['id']))
            unsigned = {k: v for k, v in value.items() if k != 'record_digest'}
            scope = (row['project'], row['requester'])
            if (value.get('schema') != 1 or type(value.get('schema')) is not int
                    or value.get('id') != row['id'] or value.get('project_id') != row['project']
                    or value.get('requester_id') != row['requester'] or value.get('idempotency_digest') != row['idem']
                    or value.get('previous_record_digest') != heads.get(scope, '0' * 64)
                    or value.get('record_digest') != row['sha'] or digest(canonical(unsigned)) != row['sha']):
                raise ValueError('invalid row binding or chain')
            for field in ('tenant_id', 'customer_id', 'project_id', 'requester_id'):
                ref = value.get(field)
                if type(ref) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}', ref):
                    raise ValueError('invalid captured identity')
            if (not re.fullmatch(r'privacy_[0-9a-f]{32}', row['id'])
                    or not re.fullmatch(r'[0-9a-f]{64}', row['idem'])
                    or type(value.get('server_received_at')) is not int or value['server_received_at'] < 0
                    or value.get('type') not in ('NOTICE_CHOICE', 'REQUEST')):
                raise ValueError('invalid receipt metadata')
        except Exception as exc:
            raise Denied('PRIVACY_HISTORY_INTEGRITY') from exc
        heads[scope] = row['sha']
        count += 1
    return {'count': count, 'chains': len(heads), 'assurance': 'LOCAL_RECEIPTS_NOT_EXTERNAL_ATTESTATION'}


def _policy(c, uid, pid):
    resolver = getattr(c, 'privacy_policy_context', None)
    value = resolver(uid, pid) if resolver else {}
    if type(value) is not dict or set(value) - set(POLICY_FIELDS):
        raise Denied('PRIVACY_TRUSTED_POLICY_FIELDS')
    result = {key: value.get(key) for key in POLICY_FIELDS}
    for key, ref in result.items():
        if key == 'notice_text':
            if ref is not None and (type(ref) is not str or not ref.strip() or len(ref) > 12000 or '\x00' in ref):
                raise Denied('PRIVACY_TRUSTED_NOTICE_TEXT')
            continue
        pattern = r'[0-9a-f]{64}' if key == 'notice_sha256' else r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}'
        if ref is not None and (type(ref) is not str or not re.fullmatch(pattern, ref)):
            raise Denied('PRIVACY_TRUSTED_POLICY_REFERENCE')
    if result['notice_text'] is not None and result['notice_sha256'] is not None:
        if digest(result['notice_text'].encode('utf-8')) != result['notice_sha256']:
            raise Denied('PRIVACY_NOTICE_DIGEST_MISMATCH')
    return result


def _rows(c, uid, pid):
    project, _, _ = c.project(uid, pid)
    rows = c.db.execute('SELECT * FROM privacy_receipts WHERE project=? AND requester=? ORDER BY seq LIMIT ?',
                        (pid, uid, MAX_HISTORY + 1)).fetchall()
    if len(rows) > MAX_HISTORY:
        raise Unavailable('PRIVACY_HISTORY_OPERATOR_REQUIRED')
    previous, result = '0' * 64, []
    for row in rows:
        value = json.loads(c.decrypt(row['payload'], 'privacy:' + row['id']))
        unsigned = {k: v for k, v in value.items() if k != 'record_digest'}
        if (value.get('id') != row['id'] or value.get('project_id') != pid
                or value.get('requester_id') != uid or value.get('idempotency_digest') != row['idem']
                or value.get('tenant_id') != project['tenant'] or value.get('customer_id') != project['customer']
                or value.get('previous_record_digest') != previous
                or value.get('record_digest') != row['sha'] or digest(canonical(unsigned)) != row['sha']):
            raise Denied('PRIVACY_IDENTITY_OR_INTEGRITY_DRIFT')
        previous = row['sha']
        result.append(value)
    return project, result


def _idem(key):
    if type(key) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
        raise ValueError('PRIVACY_IDEMPOTENCY_KEY')
    return digest(key.encode())


def _append(c, uid, pid, project, rows, idem, operation, fields):
    fingerprint = digest(canonical(operation))
    for old in rows:
        if old['idempotency_digest'] == idem:
            if old['operation_digest'] != fingerprint:
                raise Conflict('PRIVACY_IDEMPOTENCY_CONFLICT')
            c.audit(pid, uid, 'PRIVACY_RECEIPT_REPLAY', old['id'])
            return old
    if len(rows) >= MAX_HISTORY:
        raise Unavailable('PRIVACY_HISTORY_OPERATOR_REQUIRED')
    rid = 'privacy_' + secrets.token_hex(16)
    value = dict(schema=1, id=rid, project_id=pid, requester_id=uid,
                 tenant_id=project['tenant'], customer_id=project['customer'],
                 server_received_at=c.now(), idempotency_digest=idem,
                 operation_digest=fingerprint,
                 previous_record_digest=rows[-1]['record_digest'] if rows else '0' * 64,
                 **fields)
    value['record_digest'] = digest(canonical(value))
    c.db.execute('INSERT INTO privacy_receipts(id,project,requester,idem,payload,sha) VALUES(?,?,?,?,?,?)',
                 (rid, pid, uid, idem, c.encrypt(canonical(value), 'privacy:' + rid), value['record_digest']))
    c.audit(pid, uid, 'PRIVACY_RECEIPT_RECORDED', rid)
    return value


def _processing(c, uid, pid, project, rows):
    """Consume a protected status source without granting processing authority."""
    latest = {}
    for row in rows:
        if row['type'] == 'REQUEST':
            latest[row['request_id']] = row
    resolver = getattr(c, 'privacy_processing_context', None)
    results = []
    fields = {'requester_id', 'project_id', 'tenant_id', 'customer_id', 'request_id',
              'revision', 'status', 'status_ref', 'actor_ref', 'occurred_at', 'outcome_ref'}
    for rid, request in latest.items():
        value = resolver(uid, pid, rid) if resolver else None
        scope = {'requester_id': uid, 'project_id': pid, 'tenant_id': project['tenant'],
                 'customer_id': project['customer'], 'request_id': rid, 'revision': request['revision']}
        if value is None or value == {}:
            results.append({**scope, 'status': 'UNKNOWN', 'execution_enabled': False})
            continue
        if type(value) is not dict or set(value) != fields:
            raise Denied('PRIVACY_PROCESSING_FIELDS')
        if type(value['revision']) is not int or any(value[k] != v for k, v in scope.items()):
            raise Denied('PRIVACY_PROCESSING_SCOPE_OR_REVISION')
        if value['status'] not in ('RECEIVED', 'UNDER_REVIEW', 'NEEDS_INFORMATION', 'CLOSED'):
            raise Denied('PRIVACY_PROCESSING_STATUS')
        if type(value['occurred_at']) is not int or not request['server_received_at'] <= value['occurred_at'] <= c.now():
            raise Denied('PRIVACY_PROCESSING_TIME')
        for key in ('status_ref', 'actor_ref', 'outcome_ref'):
            ref = value[key]
            if key == 'outcome_ref' and ref is None and value['status'] != 'CLOSED':
                continue
            if type(ref) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}', ref):
                raise Denied('PRIVACY_PROCESSING_REFERENCE')
        results.append({**value, 'assurance': 'EXTERNAL_STATUS_NOT_LEGAL_OR_EXECUTION_ATTESTATION',
                        'execution_enabled': False})
    return results


def status(c, uid, pid):
    """Requester-private receipts; project ownership does not expose others."""
    if not c.db.in_transaction:
        with c.tx():
            return status(c, uid, pid)
    project, rows = _rows(c, uid, pid)
    policy = _policy(c, uid, pid)
    processing = _processing(c, uid, pid, project, rows)
    c.audit(pid, uid, 'PRIVACY_STATUS_READ', rows[-1]['id'] if rows else 'EMPTY')
    return {'policy': policy, 'policy_status': 'UNKNOWN' if any(v is None for v in policy.values()) else 'REFERENCES_ONLY',
            'consent_status': 'UNKNOWN', 'retention_compliance': 'UNKNOWN',
            'processing_status': 'EXTERNAL_REFERENCES_ONLY' if processing and all(p['status'] != 'UNKNOWN' for p in processing) else 'UNKNOWN',
            'processing': processing, 'receipts': rows,
            'assurance': 'LOCAL_RECEIPTS_NOT_LEGAL_DETERMINATION', 'execution_enabled': False}


def acknowledge(c, uid, pid, policy_ref, notice_sha256, decision, *, idempotency_key):
    """Record an explicit notice choice against protected current references."""
    if decision not in ('ACKNOWLEDGED', 'DECLINED'):
        raise ValueError('PRIVACY_NOTICE_CHOICE')
    idem = _idem(idempotency_key)
    with c.tx():
        project, rows = _rows(c, uid, pid)
        for old in rows:
            if old['idempotency_digest'] == idem:
                if (old['type'] != 'NOTICE_CHOICE' or old['decision'] != decision
                        or old['policy']['notice_ref'] != policy_ref
                        or old['policy']['notice_sha256'] != notice_sha256):
                    raise Conflict('PRIVACY_IDEMPOTENCY_CONFLICT')
                c.audit(pid, uid, 'PRIVACY_RECEIPT_REPLAY', old['id'])
                return old
        policy = _policy(c, uid, pid)
        if (not all(policy[k] for k in ('notice_text', 'notice_ref', 'notice_version', 'notice_sha256', 'consent_version', 'consent_scope'))
                or policy_ref != policy['notice_ref'] or notice_sha256 != policy['notice_sha256']):
            raise Denied('PRIVACY_CURRENT_NOTICE_REQUIRED')
        operation = {'type': 'NOTICE_CHOICE', 'policy': policy, 'decision': decision}
        return _append(c, uid, pid, project, rows, idem, operation,
                       {'type': 'NOTICE_CHOICE', 'policy': policy, 'decision': decision,
                        'consent_status': 'UNKNOWN', 'status': 'RECORDED_NOT_LEGAL_ACCEPTANCE'})


def submit_request(c, uid, pid, kind, text, *, idempotency_key, request_id=None, expected_revision=0):
    """Persist a request/amendment, never execute the requested data action."""
    if kind not in ('QUERY', 'CORRECTION', 'DELETION'):
        raise ValueError('PRIVACY_REQUEST_KIND')
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('PRIVACY_REQUEST_REVISION')
    if request_id is not None and (type(request_id) is not str or not re.fullmatch(r'req_[0-9a-f]{32}', request_id)):
        raise ValueError('PRIVACY_REQUEST_ID')
    text = safe_text(text)
    idem = _idem(idempotency_key)
    operation = {'type': 'REQUEST', 'kind': kind, 'text': text, 'request_id': request_id, 'expected_revision': expected_revision}
    with c.tx():
        project, rows = _rows(c, uid, pid)
        # Retry before optimistic-version validation, including after amendments.
        if any(row['idempotency_digest'] == idem for row in rows):
            return _append(c, uid, pid, project, rows, idem, operation, {})
        history = [row for row in rows if row.get('type') == 'REQUEST' and row['request_id'] == request_id]
        if request_id is None:
            if expected_revision != 0:
                raise Conflict('PRIVACY_REQUEST_REVISION')
            request_id = 'req_' + secrets.token_hex(16)
        elif not history:
            raise Denied('PRIVACY_REQUEST_NOT_FOUND')
        elif history[-1]['revision'] != expected_revision or history[-1]['kind'] != kind:
            raise Conflict('PRIVACY_REQUEST_REVISION')
        return _append(c, uid, pid, project, rows, idem, operation,
                       {'type': 'REQUEST', 'kind': kind, 'text': text, 'request_id': request_id,
                        'revision': expected_revision + 1, 'status': 'RECEIVED',
                        'processing_status': 'UNKNOWN', 'execution_enabled': False,
                        'policy': _policy(c, uid, pid)})
