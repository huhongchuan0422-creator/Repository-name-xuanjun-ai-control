"""Application history on the original append-only Center versions and events.

Legacy event/audit/material evidence remains available without inventing old
review reasons or inferring which historical file an old reviewer considered.
"""
import json
import secrets
import re
from scripts.pr122_customer_core import canonical

ITEM='COMMUNITY_ONBOARDING_HISTORY_V1'
KIND='ONBOARDING_EVENT'
OPERATION={'SAVE_DRAFT':'SAVE','UPLOAD':'UPLOAD','SUBMIT':'SUBMIT','REVIEW_MATERIAL':'REVIEW_MATERIAL',
           'BEGIN_REVIEW':'REVIEW','CORRECTION':'REVIEW','REJECT':'REVIEW','REOPEN':'REVIEW','APPROVE':'REVIEW'}
STATUS={'SAVE_DRAFT':'DRAFT','UPLOAD':'DRAFT','SUBMIT':'SUBMITTED','REVIEW_MATERIAL':'IN_REVIEW',
        'BEGIN_REVIEW':'IN_REVIEW','CORRECTION':'CORRECTION_REQUIRED','REJECT':'REJECTED','REOPEN':'CORRECTION_REQUIRED','APPROVE':'APPROVED'}


def event_time(center, application, actor, revision, event):
    operation=OPERATION.get(event)
    if operation is None:return None
    rows=center.db.execute('SELECT at FROM audit WHERE project=? AND actor=? AND event=? AND object_id=? LIMIT 2',
        (application,actor,'MERCHANT_ONBOARDING_'+operation,str(revision))).fetchall()
    return rows[0][0] if len(rows)==1 else None


def material_version(center, application, kind, object_id, expected_sha=None):
    row=center.db.execute('SELECT v.id,v.project,v.item,v.seq,v.actor,v.payload,v.created,o.project,o.sha FROM versions v JOIN objects o ON o.version=v.id WHERE o.id=?',
        (object_id,)).fetchone()
    if row is None or row[1]!=application or row[2]!=kind or row[7]!=application or expected_sha is not None and row[8]!=expected_sha:
        raise PermissionError('ONBOARDING_HISTORY_MATERIAL_BINDING_CHANGED')
    saved=json.loads(center.decrypt(row[5],row[0]))
    if type(saved) is not dict or saved.get('object_id')!=object_id or saved.get('category')!='MATERIAL':
        raise PermissionError('ONBOARDING_HISTORY_MATERIAL_BINDING_CHANGED')
    return dict(kind=kind,version=row[0],sequence=row[3],actor=row[4],created_at=row[6])


def append(service, application, owner, actor, operation, params, before, meta, revision):
    """Participate in the existing workflow transaction; never commit separately."""
    c=service.center
    if not c.db.in_transaction:raise ValueError('ORIGINAL_ONBOARDING_TRANSACTION_REQUIRED')
    event=c.db.execute('SELECT actor,event,digest,prior_digest FROM onboarding_events WHERE tenant=? AND application=? AND revision=?',
        (owner,application,revision)).fetchone()
    if event is None or event[0]!=actor or OPERATION.get(event[1])!=operation.upper():
        raise PermissionError('ONBOARDING_HISTORY_EVENT_BINDING_CHANGED')
    at=event_time(c,application,actor,revision,event[1])
    if at is None:raise ValueError('ONBOARDING_HISTORY_CURRENT_AUDIT_NOT_UNIQUE')
    materials=[]
    for kind,material in sorted(meta['materials'].items()):
        version=material_version(c,application,kind,material['object_id'],material['sha256'])
        review=meta.get('reviews',{}).get(kind)
        if review and review.get('sha256')!=material['sha256']:
            raise PermissionError('ONBOARDING_HISTORY_REVIEW_MATERIAL_CHANGED')
        materials.append(dict(version,expires_at=material['expires_at'],review=review and
            {key:review[key] for key in ('decision','note','reviewer')}))
    value=dict(format=1,application=application,owner=owner,revision=revision,actor=actor,event=event[1],
        event_digest=event[2],prior_digest=event[3],occurred_at=at,
        previous_revision=0 if before is None else before['revision'],
        status_before=None if before is None else before['status'],status_after=STATUS[event[1]],
        note=params.get('note','') if operation in ('review','review_material') else '',
        decision=params.get('decision') if operation=='review_material' else None,
        material_kind=params.get('kind') if operation in ('upload','review_material') else None,
        materials=materials)
    version='v_'+secrets.token_hex(16)
    c.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?)',
        (version,application,ITEM,revision,actor,KIND,c.encrypt(canonical(value),version),None,at))



def public_snapshot(value):
    from scripts.community_merchant_onboarding import MATERIALS
    if (type(value.get('occurred_at')) is not int or type(value.get('previous_revision')) is not int
            or type(value.get('format')) is not int or type(value.get('revision')) is not int
            or value.get('status_before') not in set(STATUS.values())|{None}
            or type(value.get('note')) is not str or len(value['note'].strip())>80
            or value.get('decision') not in (None,'ACCEPTED','NEEDS_CORRECTION')
            or value.get('material_kind') not in set(MATERIALS)|{None}
            or type(value.get('materials')) is not list):
        raise ValueError('INVALID_ONBOARDING_HISTORY_SNAPSHOT')
    seen=set()
    for material in value['materials']:
        if (type(material) is not dict or set(material)!={'kind','version','sequence','actor','created_at','expires_at','review'}
                or material['kind'] not in MATERIALS or material['kind'] in seen
                or type(material['version']) is not str or not re.fullmatch('v_[0-9a-f]{32}',material['version'])
                or type(material['sequence']) is not int or material['sequence']<1
                or type(material['created_at']) is not int or type(material['actor']) is not str
                or material['expires_at'] is not None and type(material['expires_at']) is not int):
            raise ValueError('INVALID_ONBOARDING_HISTORY_MATERIAL')
        seen.add(material['kind'])
        review=material['review']
        if review is not None and (type(review) is not dict or set(review)!={'decision','note','reviewer'}
                or review['decision'] not in ('ACCEPTED','NEEDS_CORRECTION')
                or type(review['note']) is not str or type(review['reviewer']) is not str):
            raise ValueError('INVALID_ONBOARDING_HISTORY_MATERIAL_REVIEW')
    return {k:value[k] for k in ('revision','actor','event','occurred_at','previous_revision',
        'status_before','status_after','note','decision','material_kind','materials')}


def read(service, session, csrf, application, after_revision, review=False):
    if type(after_revision) is not int or after_revision<0:raise ValueError('INVALID_ONBOARDING_HISTORY_CURSOR')
    c=service.center
    def authorize():
        uid=c.session(session,csrf)
        owner,_,_=service._load(application,uid,review)
        project=service.reviewers.get(uid) if review else None
        return uid,owner,project
    with c.tx():
        authority=authorize();uid,owner,_=authority
        c.limit('onboarding-history:'+uid,60,60)
        rows=c.db.execute('SELECT revision,actor,event,digest,prior_digest FROM onboarding_events WHERE tenant=? AND application=? AND revision>? ORDER BY revision LIMIT 51',
            (owner,application,after_revision)).fetchall()
        records=[]
        for revision,actor,event,digest,prior in rows[:50]:
            saved=c.db.execute('SELECT id,actor,kind,payload,created FROM versions WHERE project=? AND item=? AND seq=?',
                (application,ITEM,revision)).fetchone()
            if saved is None:
                records.append(dict(revision=revision,actor=actor,event=event,
                    occurred_at=event_time(c,application,actor,revision,event),
                    previous_revision=None,status_before=None,status_after=STATUS.get(event),
                    note=None,decision=None,material_kind=None,materials=None,
                    evidence='LEGACY_EVENT_ONLY',unavailable=['review_reason','event_material_binding']))
                continue
            value=json.loads(c.decrypt(saved[3],saved[0]))
            expected=dict(format=1,application=application,owner=owner,revision=revision,actor=actor,event=event,
                event_digest=digest,prior_digest=prior)
            if (type(value) is not dict or any(value.get(k)!=v for k,v in expected.items())
                    or saved[1]!=actor or saved[2]!=KIND or saved[4]!=value.get('occurred_at')
                    or value.get('previous_revision')!=revision-1 or value.get('status_after')!=STATUS.get(event)):
                raise PermissionError('ONBOARDING_HISTORY_SNAPSHOT_BINDING_CHANGED')
            records.append(dict(public_snapshot(value),evidence='CAPTURED_AT_EVENT',unavailable=[]))
        # This is a separate archive of original uploads, never a guessed join
        # between old decisions and whichever file happens to be current today.
        from scripts.community_merchant_onboarding import MATERIALS
        placeholders=','.join('?' for _ in MATERIALS)
        uploads=c.db.execute('SELECT o.id,v.item FROM versions v JOIN objects o ON o.version=v.id WHERE v.project=? AND o.project=? AND v.item IN ('+placeholders+') ORDER BY v.created,v.id LIMIT 101',
            (application,application,*MATERIALS)).fetchall()
        material_archive=[material_version(c,application,kind,oid) for oid,kind in uploads[:100]]
        if authorize()!=authority:raise PermissionError('ONBOARDING_HISTORY_AUTHORITY_CHANGED')
        return dict(application=application,records=records,has_more=len(rows)>50,
            next_revision=rows[49][0] if len(rows)>50 else None,
            material_versions=material_archive,material_versions_truncated=len(uploads)>100,
            legacy_material_event_linkage='NOT_ESTABLISHED',payment_enabled=False)
