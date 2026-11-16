"""Encrypted message provenance on the existing customer DB, never a second CRM.

Only trusted server callbacks can supply policy/context references. Missing facts
remain null. Local digest chains are not independent timestamps or attestations.
"""
import json
import re
from scripts.pr122_customer_core import Denied, Unavailable, canonical, digest

MAX_HISTORY = 10000

CONTEXT_FIELDS = ('conversation_id', 'module_id', 'preview_version', 'task_ref',
                  'consent_version', 'retention_policy')
DDL = '''
CREATE TABLE IF NOT EXISTS message_evidence(
 seq INTEGER PRIMARY KEY, message_id TEXT UNIQUE NOT NULL,
 project TEXT NOT NULL, payload BLOB NOT NULL, sha TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS messages_project_created ON messages(project,created,id);
CREATE INDEX IF NOT EXISTS message_evidence_project ON message_evidence(project,seq);
CREATE TRIGGER IF NOT EXISTS message_evidence_no_update BEFORE UPDATE ON message_evidence
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS message_evidence_no_delete BEFORE DELETE ON message_evidence
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS message_evidence_no_replace BEFORE INSERT ON message_evidence
WHEN EXISTS(SELECT 1 FROM message_evidence WHERE message_id=NEW.message_id OR seq=NEW.seq)
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
'''


def context(c, uid, pid):
    value = c.evidence_context(uid, pid) if c.evidence_context else {}
    if type(value) is not dict or set(value) - set(CONTEXT_FIELDS):
        raise Denied('TRUSTED_EVIDENCE_CONTEXT_FIELDS')
    result = {name: value.get(name) for name in CONTEXT_FIELDS}
    for ref in result.values():
        if ref is not None and (type(ref) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}', ref)):
            raise Denied('TRUSTED_EVIDENCE_REFERENCE')
    return result


def append(c, mid, *, event=None, provider_occurred_at=None, legacy=False,
           related_message_id=None):
    """Must run inside the same write transaction as the message itself."""
    if not c.db.in_transaction:
        raise Denied('EVIDENCE_TRANSACTION_REQUIRED')
    row = c.db.execute('SELECT * FROM messages WHERE id=?', (mid,)).fetchone()
    if not row:
        raise Denied('EVIDENCE_MESSAGE_REQUIRED')
    if event is not None and (type(event) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', event)):
        raise Denied('EVIDENCE_PROVIDER_EVENT')
    if provider_occurred_at is not None and (type(provider_occurred_at) is not int or provider_occurred_at < 0 or provider_occurred_at > c.now() + 300):
        raise Denied('EVIDENCE_PROVIDER_TIME')
    if legacy:
        project = c.db.execute('SELECT * FROM projects WHERE id=?', (row['project'],)).fetchone()
        role = None
        refs = dict.fromkeys(CONTEXT_FIELDS)
    else:
        project, role, _ = c.project(row['user_id'], row['project'])
        refs = context(c, row['user_id'], row['project'])
    previous = c.db.execute('SELECT sha FROM message_evidence WHERE project=? ORDER BY seq DESC LIMIT 1', (row['project'],)).fetchone()
    body = c.decrypt(row['payload'], mid)
    value = {
        'schema': 1, 'message_id': mid, 'project_id': row['project'],
        'customer_id': project['customer'] if project else None,
        'tenant_id': project['tenant'] if project else None,
        'sender_id': row['user_id'], 'sender_role': 'AI' if row['channel']=='WEB_AI' and not legacy else role,
        'authorization_role': role,
        'source_channel': row['channel'], 'external_event_id': event,
        'server_received_at': row['created'], 'provider_occurred_at': provider_occurred_at,
        'text_or_attachment_ref': {'kind': 'ENCRYPTED_MESSAGE', 'message_id': mid},
        'content_sha256': digest(body), 'previous_record_digest': previous[0] if previous else '0'*64,
        'related_message_id': related_message_id,
        'provenance': 'LEGACY_BACKFILL_UNKNOWN_CONTEXT' if legacy else 'SERVER_CAPTURED',
        'captured_at': c.now(), 'delivery_status_at_capture': row['status'], **refs,
    }
    value['record_digest'] = digest(canonical(value))
    c.db.execute('INSERT INTO message_evidence(message_id,project,payload,sha) VALUES(?,?,?,?)',
                 (mid, row['project'], c.encrypt(canonical(value), 'message-evidence:'+mid), value['record_digest']))
    return value


def install(c):
    """Additive/idempotent old-DB migration; never invent historical provenance.

    Once migration is marked complete, missing evidence is corruption, not a
    reason to silently backfill or bless newly inserted untracked messages.
    """
    c.db.executescript(DDL)
    with c.tx():
        marker = c.db.execute("SELECT v FROM settings WHERE k='message_evidence_schema'").fetchone()
        missing = c.db.execute('SELECT m.id FROM messages m LEFT JOIN message_evidence e ON e.message_id=m.id WHERE e.message_id IS NULL ORDER BY m.created,m.id').fetchall()
        if marker:
            if marker[0] != '1' or missing:
                raise Denied('MESSAGE_EVIDENCE_MIGRATION_DRIFT')
        else:
            for row in missing:
                append(c, row[0], legacy=True)
            c.db.execute("INSERT INTO settings VALUES('message_evidence_schema','1')")


def verify(c, pid=None):
    if not c.db.in_transaction:
        with c.tx():return verify(c,pid)
    where, args = (' WHERE e.project=?', (pid,)) if pid is not None else ('', ())
    rows = c.db.execute('SELECT e.* FROM message_evidence e'+where+' ORDER BY e.seq', args).fetchall()
    heads = {}
    result = []
    for row in rows:
        value = json.loads(c.decrypt(row['payload'], 'message-evidence:'+row['message_id']))
        unsigned = {k: v for k, v in value.items() if k != 'record_digest'}
        mid = row['message_id']
        message = c.db.execute('SELECT * FROM messages WHERE id=?', (mid,)).fetchone()
        if (not message or value.get('message_id') != mid or value.get('project_id') != row['project']
                or message['project'] != row['project'] or value.get('sender_id') != message['user_id']
                or value.get('source_channel') != message['channel'] or value.get('server_received_at') != message['created']
                or value.get('previous_record_digest') != heads.get(row['project'], '0'*64)
                or value.get('record_digest') != row['sha'] or digest(canonical(unsigned)) != row['sha']):
            raise Denied('MESSAGE_EVIDENCE_INTEGRITY')
        body = c.decrypt(message['payload'], mid)
        if digest(body) != value.get('content_sha256'):
            raise Denied('MESSAGE_CONTENT_INTEGRITY')
        heads[row['project']] = row['sha']
        result.append({'evidence': value, 'body': body.decode(), 'delivery_status': message['status'],
                       'provider_ref': message['provider_ref']})
    count = c.db.execute('SELECT count(*) FROM messages'+(' WHERE project=?' if pid is not None else ''), args).fetchone()[0]
    if count != len(rows):
        raise Denied('MESSAGE_EVIDENCE_MISSING')
    return result, heads



def authorized_records(c, uid, pid):
    """One guard for every customer message read or external consumption.

    Project IDs alone never prove historical tenant/customer provenance. Keep
    orphan legacy facts unknown and deny them even after an ID is reassigned.
    Operator integrity/backup may still preserve those quarantined records.
    """
    if not c.db.in_transaction:
        with c.tx():return authorized_records(c,uid,pid)
    project, _, _ = c.project(uid,pid)
    if c.db.execute('SELECT count(*) FROM messages WHERE project=?',(pid,)).fetchone()[0] > MAX_HISTORY:
        raise Unavailable('BOUNDED_HISTORY_REQUIRES_OPERATOR')
    records, heads = verify(c,pid)
    if any(r['evidence']['tenant_id'] != project['tenant'] or r['evidence']['customer_id'] != project['customer'] for r in records):
        raise Denied('MESSAGE_EVIDENCE_PROJECT_IDENTITY_DRIFT')
    return project,records,heads


def export_project(c, uid, pid):
    """Authenticated project-scoped local evidence; no credential/object export.

    Policy refs that are null remain UNKNOWN. This does not accept consent,
    impose a retention duration, delete data, or certify legal admissibility.
    """
    with c.tx():
        project, _, _ = c.project(uid, pid)
        if c.db.execute('SELECT count(*) FROM messages WHERE project=?', (pid,)).fetchone()[0] > 10000:
            raise Unavailable('BOUNDED_EXPORT_REQUIRES_OPERATOR')
        project, records, heads = authorized_records(c, uid, pid)
        from scripts.pr122_customer_activity_evidence import export_project as export_activity
        activity=export_activity(c,uid,pid)
        from scripts.pr122_customer_privacy import status as privacy_status
        privacy=privacy_status(c,uid,pid)
        c.audit(pid, uid, 'MESSAGE_EVIDENCE_EXPORTED', heads.get(pid, '0'*64))
        audit=c.db.execute('SELECT seq,project,actor,at,sha FROM audit WHERE seq=last_insert_rowid()').fetchone()
        receipt={'project_id':audit['project'],'actor_id':audit['actor'],'exported_at':audit['at'],'audit_seq':audit['seq'],'audit_digest':audit['sha'],'message_chain_head':heads.get(pid,'0'*64)}
        return {'schema': 1, 'project_id': pid, 'tenant_id': project['tenant'], 'customer_id': project['customer'],
                'records': records, 'chain_head': heads.get(pid, '0'*64), 'export_receipt':receipt,'project_activity':activity,'privacy':privacy,
                'assurance': 'LOCAL_HASH_CHAIN_NOT_EXTERNAL_ATTESTATION',
                'policy_status': 'UNKNOWN' if not records or any(r['evidence'][k] is None for r in records for k in ('consent_version','retention_policy')) else 'REFERENCES_RECORDED_NOT_LEGAL_ATTESTATION'}
