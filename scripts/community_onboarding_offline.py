"""Offline merchant onboarding state machine. No external provider calls or payments.

A caller-supplied Principal is NOT production authentication. Deployment must supply
a verified server-side principal, enforce tenant ownership, and independently audit.
"""
import json
import sqlite3
import hashlib
from contextlib import nullcontext

def _transaction(db,manage_transaction):
    if manage_transaction:return db
    if not db.in_transaction:raise ValueError('OUTER_TRANSACTION_REQUIRED')
    return nullcontext()

_ALLOWED = {"DRAFT", "SUBMITTED", "IN_REVIEW", "CORRECTION_REQUIRED", "REJECTED", "APPROVED", "WITHDRAWN"}
_FIELDS = ("legal_name", "store_name", "address", "contact", "license_ref")
def _str(value, label, required=True):
    if type(value) is not str or len(value)>512 or (required and not value.strip()):
        raise ValueError("INVALID_"+label)
    return value.strip()
def _actor(tenant, actor):
    return _str(tenant, "TENANT"),_str(actor,"ACTOR")
def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS onboarding (
        tenant TEXT NOT NULL, application TEXT NOT NULL, revision INTEGER NOT NULL,
        status TEXT NOT NULL, payload TEXT NOT NULL, reviewer_note TEXT,
        PRIMARY KEY(tenant,application))""")
    db.execute("""CREATE TABLE IF NOT EXISTS onboarding_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
        application TEXT NOT NULL, revision INTEGER NOT NULL, actor TEXT NOT NULL,
        event TEXT NOT NULL, digest TEXT NOT NULL, prior_digest TEXT NOT NULL,
        UNIQUE(tenant,application,revision))""")
    db.commit()
def _current(db, tenant, application):
    row=db.execute("SELECT revision,status,payload,reviewer_note FROM onboarding WHERE tenant=? AND application=?",(tenant,application)).fetchone()
    if row is None: raise ValueError("NOT_FOUND")
    return row
def _append(db,tenant,application,revision,actor,event,payload):
    row=db.execute("SELECT digest FROM onboarding_events WHERE tenant=? AND application=? ORDER BY revision DESC LIMIT 1",(tenant,application)).fetchone()
    prior=row[0] if row else "0"*64
    canonical=json.dumps([tenant,application,revision,actor,event,payload,prior],ensure_ascii=False,sort_keys=True,separators=(",",":"))
    digest=hashlib.sha256(canonical.encode()).hexdigest()
    db.execute("INSERT INTO onboarding_events(tenant,application,revision,actor,event,digest,prior_digest) VALUES(?,?,?,?,?,?,?)",
               (tenant,application,revision,actor,event,digest,prior))
def save_draft(db, tenant, application, actor, fields, expected_revision=0, *, encode=None,manage_transaction=True):
    tenant,actor=_actor(tenant,actor); application=_str(application,"APPLICATION")
    if type(expected_revision) is not int or expected_revision<0:raise ValueError("REVISION")
    if type(fields) is not dict or set(fields)!=set(_FIELDS):raise ValueError("INVALID_FIELDS")
    data={key:_str(fields[key],key,required=False) for key in _FIELDS}
    payload=encode(data) if encode is not None else json.dumps(data,sort_keys=True)
    with _transaction(db,manage_transaction):
        row=db.execute("SELECT revision,status FROM onboarding WHERE tenant=? AND application=?",(tenant,application)).fetchone()
        if row:
            if row[0]!=expected_revision:raise ValueError("REVISION_CONFLICT")
            if row[1] not in ("DRAFT","CORRECTION_REQUIRED"):raise ValueError("STATE_FORBIDDEN")
            revision=row[0]+1
            db.execute("UPDATE onboarding SET revision=?,status='DRAFT',payload=?,reviewer_note=NULL WHERE tenant=? AND application=?",(revision,payload,tenant,application))
        else:
            if expected_revision!=0:raise ValueError("REVISION_CONFLICT")
            revision=1
            db.execute("INSERT INTO onboarding VALUES(?,?,?,'DRAFT',?,NULL)",(tenant,application,revision,payload))
        _append(db,tenant,application,revision,actor,"SAVE_DRAFT",data)
    return revision
def transition(db,tenant,application,actor,role,action,expected_revision,note="", *, decode=None,manage_transaction=True):
    tenant,actor=_actor(tenant,actor); application=_str(application,"APPLICATION")
    if type(expected_revision) is not int or expected_revision<1:raise ValueError("REVISION")
    matrix={"WITHDRAW":({"DRAFT","CORRECTION_REQUIRED"},"WITHDRAWN","MERCHANT"),
            "SUBMIT":({"DRAFT"},"SUBMITTED","MERCHANT"),
            "BEGIN_REVIEW":({"SUBMITTED"},"IN_REVIEW","REVIEWER"),
            "CORRECTION":({"SUBMITTED","IN_REVIEW","APPROVED"},"CORRECTION_REQUIRED","REVIEWER"),
            "REJECT":({"SUBMITTED","IN_REVIEW"},"REJECTED","REVIEWER"),
            "REOPEN":({"REJECTED"},"CORRECTION_REQUIRED","REVIEWER"),
            "APPROVE":({"SUBMITTED","IN_REVIEW"},"APPROVED","REVIEWER")}
    if action not in matrix:raise ValueError("ACTION")
    allowed,target,required_role=matrix[action]
    if role!=required_role:raise PermissionError("ROLE_FORBIDDEN")
    note=_str(note,"NOTE",required=action in ("CORRECTION","REJECT","REOPEN"))
    with _transaction(db,manage_transaction):
        rev,state,payload,_=_current(db,tenant,application)
        if rev!=expected_revision:raise ValueError("REVISION_CONFLICT")
        if state not in allowed:raise ValueError("STATE_FORBIDDEN")
        if action=="SUBMIT" and any(not v for v in (decode(payload) if decode is not None else json.loads(payload)).values()):raise ValueError("MISSING_REQUIRED")
        newrev=rev+1
        db.execute("UPDATE onboarding SET revision=?,status=?,reviewer_note=? WHERE tenant=? AND application=?",
                   (newrev,target,note,tenant,application))
        _append(db,tenant,application,newrev,actor,action,{"note":note,"target":target})
    return newrev
def get_application(db,tenant,application, *, decode=None):
    tenant=_str(tenant,"TENANT");application=_str(application,"APPLICATION")
    rev,state,payload,note=_current(db,tenant,application)
    return {"revision":rev,"status":state,"fields":decode(payload) if decode is not None else json.loads(payload),"reviewer_note":note}
def events(db,tenant,application):
    tenant=_str(tenant,"TENANT");application=_str(application,"APPLICATION")
    return db.execute("SELECT revision,event,digest,prior_digest FROM onboarding_events WHERE tenant=? AND application=? ORDER BY revision",(tenant,application)).fetchall()
