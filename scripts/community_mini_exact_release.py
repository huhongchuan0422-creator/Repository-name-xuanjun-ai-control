"""Protected Python-only Mini identity release. No HTTP/SQL operator entrypoint.

The original custodian constructs the exact two-target policy from protected
application/owner/subject joins; never from a client request. Existing Center
transaction, encrypted links and audit only. No payment/provider writes or IO.
"""
import base64
import hashlib
import json
from dataclasses import dataclass
from scripts.pr122_customer_core import canonical

CHANNEL='WECHAT_MINI_EXACT_RELEASE_V1'
AUTHORIZED_REFS=frozenset({'2acf50c7f6f6b71e0efb','a811ce4e8bc9107addd2'})

def application_ref(application):
    return hashlib.sha256(('test-reapply-internal-ref-v1:'+application).encode()).hexdigest()[:20]

def packed(row):
    return {k:(base64.b64encode(v).decode() if isinstance(v,bytes) else v) for k,v in dict(row).items()}

def version(row):
    return hashlib.sha256(canonical(packed(row))).hexdigest()

@dataclass(frozen=True)
class Target:
    application: str
    owner: str
    subject: str
    project: str
    version: str

class ExactRelease:
    def __init__(self,center,targets):
        if (type(targets) is not tuple or len(targets)!=2 or any(type(t) is not Target for t in targets)
            or {application_ref(t.application) for t in targets}!=AUTHORIZED_REFS
            or len({t.subject for t in targets})!=2 or len({t.owner for t in targets})!=2):
            raise PermissionError('PROTECTED_EXACT_TWO_POLICY_REQUIRED')
        self.center,self.targets=center,targets

    def release(self,target,key):
        if target not in self.targets or type(key) is not str or not 16<=len(key)<=128:
            raise PermissionError('EXACT_TARGET_AND_KEY_REQUIRED')
        c=self.center;t=target
        with c.tx():
            _ready(c)
            prior=_receipt(c,t.subject,t.project)
            request=dict(application=t.application,owner=t.owner,subject=t.subject,project=t.project,version=t.version,key=key)
            if prior is not None:
                if prior['request']!=request:raise PermissionError('RELEASE_IDEMPOTENCY_CONFLICT')
                return _public(prior)
            rows=c.db.execute("SELECT * FROM links WHERE channel='WECHAT_MINI' AND subject_idx=?",(t.subject,)).fetchall()
            if len(rows)!=1:raise PermissionError('EXACT_SINGLE_PROJECT_SUBJECT_REQUIRED')
            row=rows[0]
            if row['user_id']!=t.owner or row['project']!=t.project or row['active']!=1 or version(row)!=t.version:
                raise PermissionError('BINDING_CAS_CHANGED')
            _finished(c,t)
            # No historic/native marker, no opt-in fresh enrollment.
            if c.db.execute("SELECT 1 FROM links WHERE channel='COMMUNITY_WECHAT_ACCOUNT_V1' AND user_id=? AND active=1",(t.owner,)).fetchone() is None:
                raise PermissionError('NATIVE_TEST_ACCOUNT_REQUIRED')
            saved=dict(request=request,old_link=packed(row),state='RELEASED',new_owner=None)
            c.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI' AND subject_idx=? AND project=? AND user_id=? AND active=1 AND payload=?",(t.subject,t.project,t.owner,row['payload']))
            if c.db.execute('SELECT changes()').fetchone()[0]!=1:raise PermissionError('BINDING_CAS_CHANGED')
            c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',(CHANNEL,t.subject,t.owner,t.project,c.encrypt(canonical(saved),'mini-exact-release:'+t.subject+':'+t.project)))
            c.audit(t.project,t.owner,'WECHAT_MINI_EXACT_RELEASE',application_ref(t.application))
            return _public(saved)

    def restore(self,target,key):
        if target not in self.targets:raise PermissionError('EXACT_TARGET_REQUIRED')
        c=self.center;t=target
        with c.tx():
            _ready(c);r=_receipt(c,t.subject,t.project)
            expected=dict(application=t.application,owner=t.owner,subject=t.subject,project=t.project,version=t.version,key=key)
            if r is None or r['request']!=expected:raise PermissionError('EXACT_RECEIPT_REQUIRED')
            if r['state']=='RESTORED':return _public(r)
            if r['state']!='RELEASED':raise PermissionError('FRESH_LOGIN_ALREADY_CONSUMED_RELEASE')
            _released_row(c,r)
            c.db.execute("UPDATE links SET active=1 WHERE channel='WECHAT_MINI' AND subject_idx=? AND user_id=? AND project=? AND active=0",(t.subject,t.owner,t.project))
            r['state']='RESTORED';_save(c,r)
            c.audit(t.project,t.owner,'WECHAT_MINI_EXACT_RESTORE',application_ref(t.application))
            return _public(r)

def _ready(c):
    if c.db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0]!='0':raise PermissionError('CENTER_MAINTENANCE')

def _finished(c,t):
    row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_APPLYMENT' AND user_id=? AND project=? AND active=1",(t.owner,t.application)).fetchone()
    ob=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_WECHAT_OBSERVATION' AND subject_idx=? AND user_id=? AND project=? AND active=1",(t.application,t.owner,t.application)).fetchone()
    if row is None or ob is None:raise PermissionError('ORIGINAL_FINISHED_EVIDENCE_REQUIRED')
    value=json.loads(c.decrypt(row[0],'wechat-applyment:'+t.application));obs=json.loads(c.decrypt(ob[0],'wechat-observation:'+t.application));b=obs.get('binding',{})
    if not (obs.get('record_digest')==hashlib.sha256(canonical(value)).hexdigest() and obs.get('provider_state')=='APPLYMENT_STATE_FINISHED' and obs.get('sync_error') is None
            and all(b.get(k)==v for k,v in [('owner',t.owner),('application',t.application),('active',True),('business_code',value.get('business_code')),('applyment_id',value.get('applyment_id')),('provider_merchant',value.get('provider_sp_mchid'))])):
        raise PermissionError('ORIGINAL_FINISHED_BINDING_CHANGED')

def _receipt(c,subject,project):
    row=c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=? AND active=1',(CHANNEL,subject,project)).fetchone()
    return json.loads(c.decrypt(row[0],'mini-exact-release:'+subject+':'+project)) if row else None

def _save(c,r):
    t=r['request'];c.db.execute('UPDATE links SET payload=? WHERE channel=? AND subject_idx=? AND user_id=? AND project=? AND active=1',(c.encrypt(canonical(r),'mini-exact-release:'+t['subject']+':'+t['project']),CHANNEL,t['subject'],t['owner'],t['project']))
    if c.db.execute('SELECT changes()').fetchone()[0]!=1:raise PermissionError('RECEIPT_CAS_CHANGED')

def _released_row(c,r):
    t=r['request'];rows=c.db.execute("SELECT * FROM links WHERE channel='WECHAT_MINI' AND subject_idx=?",(t['subject'],)).fetchall()
    if len(rows)!=1:raise PermissionError('RELEASED_LINK_CHANGED')
    current=packed(rows[0]);old=dict(r['old_link']);old['active']=0
    if current!=old:raise PermissionError('RELEASED_LINK_CHANGED')

def pending_registration(identity,subject):
    c=identity.center
    rows=c.db.execute('SELECT project FROM links WHERE channel=? AND subject_idx=? AND active=1',(CHANNEL,subject)).fetchall()
    if not rows:return None
    if len(rows)!=1:raise PermissionError('EXACT_RELEASE_REQUIRED')
    r=_receipt(c,subject,rows[0]['project'])
    if r['state']!='RELEASED':return None
    if not c.db.in_transaction:raise PermissionError('ORIGINAL_LOGIN_TRANSACTION_REQUIRED')
    _released_row(c,r)
    if {v['project'] for v in getattr(identity,'registration',{}).values()}!={r['request']['project']}:
        raise PermissionError('RELEASE_REGISTRATION_PROJECT_CHANGED')
    return r

def complete_registration(identity,r,uid,appid):
    c=identity.center
    if not c.db.in_transaction:raise PermissionError('ORIGINAL_LOGIN_TRANSACTION_REQUIRED')
    _released_row(c,r);t=r['request']
    c.db.execute("UPDATE links SET user_id=?,payload=?,active=1 WHERE channel='WECHAT_MINI' AND subject_idx=? AND user_id=? AND project=? AND active=0",(uid,c.encrypt(canonical({'appid':appid}),'wechat-mini-link'),t['subject'],t['owner'],t['project']))
    if c.db.execute('SELECT changes()').fetchone()[0]!=1:raise PermissionError('BINDING_CAS_CHANGED')
    r['state']='CONSUMED';r['new_owner']=uid;_save(c,r)
    c.audit(t['project'],uid,'WECHAT_MINI_RELEASE_REENROLLED',application_ref(t['application']))

def _public(r):
    return dict(safe_id=application_ref(r['request']['application']),state=r['state'],old_binding_active=r['state']=='RESTORED',new_login_consumed=r['state']=='CONSUMED')
