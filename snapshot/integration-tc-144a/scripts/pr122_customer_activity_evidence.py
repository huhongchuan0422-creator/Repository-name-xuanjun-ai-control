"""Integrity-bound references to existing material/change/delivery histories.

No second business ledger; authoritative state remains in its original tables.
Exports are filtered by the existing material ACL and never contain file bytes
or dedicated secret-reference values. Unknown legacy subject bindings stay held.
"""
import json
from scripts.pr122_customer_core import Denied,Unavailable,canonical,digest
MAX_ACTIVITY = 10000
DDL = '''
CREATE TABLE IF NOT EXISTS project_activity_evidence(
 seq INTEGER PRIMARY KEY,source_kind TEXT NOT NULL,source_id TEXT NOT NULL,
 project TEXT NOT NULL,tenant_idx TEXT,customer_idx TEXT,audit_seq INTEGER UNIQUE,
 payload BLOB NOT NULL,sha TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS activity_project ON project_activity_evidence(project,seq);
CREATE INDEX IF NOT EXISTS activity_source ON project_activity_evidence(source_kind,source_id);
CREATE INDEX IF NOT EXISTS versions_project ON versions(project);
CREATE INDEX IF NOT EXISTS change_events_project ON change_events(project);
CREATE TRIGGER IF NOT EXISTS activity_no_update BEFORE UPDATE ON project_activity_evidence BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS activity_no_delete BEFORE DELETE ON project_activity_evidence BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS activity_no_replace BEFORE INSERT ON project_activity_evidence
WHEN EXISTS(SELECT 1 FROM project_activity_evidence WHERE seq=NEW.seq OR audit_seq=NEW.audit_seq)
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS versions_no_replace BEFORE INSERT ON versions
WHEN EXISTS(SELECT 1 FROM versions WHERE id=NEW.id OR (project=NEW.project AND item=NEW.item AND seq=NEW.seq))
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS changes_no_replace BEFORE INSERT ON change_events
WHEN EXISTS(SELECT 1 FROM change_events WHERE id=NEW.id OR (project=NEW.project AND case_id=NEW.case_id AND seq=NEW.seq))
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_replace BEFORE INSERT ON audit
WHEN EXISTS(SELECT 1 FROM audit WHERE seq=NEW.seq)
BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
'''


def source(c,kind,sid):
    table={'MATERIAL':'versions','CHANGE':'change_events','DELIVERY':'messages'}[kind]
    row=c.db.execute('SELECT * FROM '+table+' WHERE id=?',(sid,)).fetchone()
    if not row:raise Denied('ACTIVITY_SOURCE_MISSING')
    value=dict(row)
    value['payload']=c.decrypt(row['payload'],sid).decode()
    if kind!='DELIVERY':
        value['payload']=json.loads(value['payload'])
        if kind=='MATERIAL' and value['payload'].get('object_id'):
            obj=c.db.execute('SELECT id,version,project,mime,size,sha,scan FROM objects WHERE id=?',(value['payload']['object_id'],)).fetchone()
            if not obj or obj['project']!=row['project'] or obj['version']!=sid:raise Denied('ACTIVITY_OBJECT_SCOPE')
            value['object_metadata']=dict(obj)
    else:
        value.pop('status');value.pop('provider_ref')
    return row,value


def capture(c,kind,sid,audit=None,legacy=False):
    if not c.db.in_transaction:raise Denied('ACTIVITY_TRANSACTION_REQUIRED')
    row,value=source(c,kind,sid)
    p=c.db.execute('SELECT tenant,customer FROM projects WHERE id=?',(row['project'],)).fetchone()
    previous=c.db.execute('SELECT sha FROM project_activity_evidence WHERE project=? ORDER BY seq DESC LIMIT 1',(row['project'],)).fetchone()
    proof={'schema':1,'source_kind':kind,'source_id':sid,'project_id':row['project'],
           'tenant_id':p['tenant'] if p else None,'customer_id':p['customer'] if p else None,
           'snapshot_sha256':digest(canonical(value)),'created_at':row['created'],
           'captured_at':c.now(),'provenance':'LEGACY_BACKFILL_UNKNOWN_CONTEXT' if legacy else 'SERVER_CAPTURED',
           'audit_seq':audit['seq'] if audit else None,'audit_digest':audit['sha'] if audit else None,
           'previous_record_digest':previous[0] if previous else '0'*64}
    if kind=='DELIVERY':proof.update(delivery_status=row['status'],provider_ref=row['provider_ref'])
    proof['record_digest']=digest(canonical(proof))
    aad='activity:'+kind+':'+sid+':'+str(proof['audit_seq'])
    c.db.execute('INSERT INTO project_activity_evidence(source_kind,source_id,project,tenant_idx,customer_idx,audit_seq,payload,sha) VALUES(?,?,?,?,?,?,?,?)',
                 (kind,sid,row['project'],c.idx('tenant:'+p['tenant']) if p else None,c.idx('customer:'+p['customer']) if p else None,
                  proof['audit_seq'],c.encrypt(canonical(proof),aad),proof['record_digest']))


def capture_audit(c,project,event,obj):
    kind=None
    if event in ('SAVE','SUBMIT','BEGIN_REVIEW','REQUEST_CHANGES','APPROVE'):kind='MATERIAL'
    elif event.startswith('CHANGE_') and event not in ('CHANGE_HISTORY_READ',):
        if c.db.execute('SELECT 1 FROM change_events WHERE id=? AND project=?',(obj,project)).fetchone():kind='CHANGE'
    elif event in ('OUTBOUND_PENDING','OUTBOUND_ATTEMPT_UNKNOWN','OUTBOUND_ACCEPTED','OUTBOUND_RESTORE_UNKNOWN','OUTBOUND_CANCELLED'):kind='DELIVERY'
    if kind:
        audit=c.db.execute('SELECT seq,sha FROM audit WHERE seq=last_insert_rowid()').fetchone()
        capture(c,kind,obj,audit)


def install(c):
    c.db.executescript(DDL)
    with c.tx():
        marker=c.db.execute("SELECT v FROM settings WHERE k='activity_evidence_schema'").fetchone()
        if marker:
            if marker[0]!='1':raise Denied('ACTIVITY_SCHEMA_DRIFT')
            return
        for kind,table in (('MATERIAL','versions'),('CHANGE','change_events')):
            for row in c.db.execute('SELECT id FROM '+table+' ORDER BY created,id').fetchall():capture(c,kind,row['id'],legacy=True)
        for row in c.db.execute("SELECT id FROM messages WHERE status IN ('PENDING','UNKNOWN','ACCEPTED','FAILED') ORDER BY created,id").fetchall():
            capture(c,'DELIVERY',row['id'],legacy=True)
        c.db.execute("INSERT INTO settings VALUES('activity_evidence_schema','1')")


def guard_subject(c,project):
    pid=project['id']
    if c.db.execute('SELECT count(*) FROM project_activity_evidence WHERE project=?',(pid,)).fetchone()[0]>MAX_ACTIVITY:
        raise Unavailable('BOUNDED_ACTIVITY_REQUIRES_OPERATOR')
    bad=c.db.execute('SELECT 1 FROM project_activity_evidence WHERE project=? AND (tenant_idx IS NULL OR customer_idx IS NULL OR tenant_idx!=? OR customer_idx!=?) LIMIT 1',
                     (pid,c.idx('tenant:'+project['tenant']),c.idx('customer:'+project['customer']))).fetchone()
    if bad:raise Denied('ACTIVITY_PROJECT_IDENTITY_DRIFT')
    for kind,table in (('MATERIAL','versions'),('CHANGE','change_events')):
        if c.db.execute('SELECT 1 FROM '+table+' s LEFT JOIN project_activity_evidence e ON e.source_kind=? AND e.source_id=s.id WHERE s.project=? AND e.seq IS NULL LIMIT 1',(kind,pid)).fetchone():
            raise Denied('ACTIVITY_EVIDENCE_MISSING')


def verify(c,pid=None):
    if not c.db.in_transaction:
        with c.tx():return verify(c,pid)
    rows=c.db.execute('SELECT * FROM project_activity_evidence'+(' WHERE project=?' if pid is not None else '')+' ORDER BY seq',(pid,) if pid is not None else ()).fetchall()
    heads={};out=[]
    for row in rows:
        aad='activity:'+row['source_kind']+':'+row['source_id']+':'+str(row['audit_seq'])
        proof=json.loads(c.decrypt(row['payload'],aad));original,value=source(c,row['source_kind'],row['source_id'])
        unsigned={k:v for k,v in proof.items() if k!='record_digest'}
        if (proof['project_id']!=row['project'] or original['project']!=row['project'] or proof['source_kind']!=row['source_kind'] or proof['source_id']!=row['source_id']
                or proof['audit_seq']!=row['audit_seq'] or proof['previous_record_digest']!=heads.get(row['project'],'0'*64)
                or proof['record_digest']!=row['sha'] or digest(canonical(unsigned))!=row['sha'] or digest(canonical(value))!=proof['snapshot_sha256']
                or row['tenant_idx']!=(c.idx('tenant:'+proof['tenant_id']) if proof['tenant_id'] else None)
                or row['customer_idx']!=(c.idx('customer:'+proof['customer_id']) if proof['customer_id'] else None)):
            raise Denied('ACTIVITY_INTEGRITY')
        if row['audit_seq'] is not None:
            audit=c.db.execute('SELECT project,sha FROM audit WHERE seq=?',(row['audit_seq'],)).fetchone()
            if not audit or audit['project']!=row['project'] or audit['sha']!=proof['audit_digest']:raise Denied('ACTIVITY_AUDIT_INTEGRITY')
        heads[row['project']]=row['sha'];out.append((proof,value))
    return out,heads


def export_project(c,uid,pid):
    if not c.db.in_transaction:
        with c.tx():return export_project(c,uid,pid)
    c.project(uid,pid) # Includes subject and count guards before any bulk decryption.
    records,heads=verify(c,pid);visible=[]
    for proof,value in records:
        kind=proof['source_kind']
        if kind=='MATERIAL':
            try:q,role=c.requirement(uid,pid,value['item'])
            except Denied:continue
            payload=value['payload']
            if payload.get('category')=='INTERNAL' and role!='REVIEWER':continue
            details={k:value[k] for k in ('id','item','seq','actor','kind','expires','created')}
            details['review_reason']=payload.get('reason')
            details['source_version']=payload.get('source_version')
            details['object_ref']=payload.get('object_id')
            details['object_sha256']=value.get('object_metadata',{}).get('sha')
            details['dedicated_reference_recorded']='reference' in payload
        elif kind=='CHANGE':
            details={k:value[k] for k in ('id','case_id','seq','kind','actor','created')}
            # Actual sensitive business details remain at the original permissioned endpoint.
            details['payload_sha256']=digest(canonical(value['payload']))
        else:
            details={'message_id':value['id'],'channel':value['channel'],'created':value['created'],
                     'delivery_status':proof['delivery_status'],'provider_ref':proof['provider_ref']}
        visible.append({'evidence':proof,'details':details})
    c.audit(pid,uid,'ACTIVITY_EVIDENCE_READ',str(len(visible)))
    return {'records':visible,'scope':'AUTHORIZED_SUBSET','assurance':'LOCAL_HASH_CHAIN_NOT_EXTERNAL_ATTESTATION'}
