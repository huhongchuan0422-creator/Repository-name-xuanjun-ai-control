"""Provider-verified consumer registration in original Center tables.

Not another IAM/database. No email is fabricated, no password login is enabled,
no project membership or staff/merchant/platform role is created. All functions
participate in the caller's original Center transaction and audit trail.
"""
import json
import re
import secrets
from scripts.pr122_customer_core import canonical

ACCOUNT = 'COMMUNITY_WECHAT_ACCOUNT_V1'
CONSUMER = 'COMMUNITY_WECHAT_CONSUMER_V1'


def policy(identity, scenes):
    if type(scenes) is not list or not scenes or len(scenes) != len(set(scenes)):
        raise ValueError('PROTECTED_REGISTRATION_SCENES_REQUIRED')
    result = {}
    tenants = set()
    for scene in scenes:
        if type(scene) is not str or scene not in identity.scenes:
            raise ValueError('REGISTERED_CONSUMER_SCENE_REQUIRED')
        binding = identity.scenes[scene]
        principal = binding['principal']
        scope = identity.runtime.bindings[principal]
        project = identity.center.db.execute('SELECT * FROM projects WHERE id=?',(binding['project'],)).fetchone()
        if principal.role != 'CUSTOMER' or project is None or project['tenant'] != scope['tenant_id'] or project['active'] != 1 or project['expires'] <= identity.center.now():
            raise PermissionError('ACTIVE_CUSTOMER_PROJECT_REQUIRED')
        try:
            realm=json.loads(identity.center.decrypt(project['payload'],'project:'+binding['project']))
        except Exception:
            raise PermissionError('CUSTOMER_PLATFORM_REALM_REQUIRED') from None
        if (type(realm) is not dict or set(realm)!={'kind','title','requirements','source','authority_ref'}
                or realm['kind']!='COMMUNITY_PLATFORM_REALM' or realm['source']!='OWNER_APPROVED_FIRST_INSTALL'
                or realm['requirements']!=[] or realm['authority_ref']!=project['authority_ref']):
            raise PermissionError('CUSTOMER_PLATFORM_REALM_REQUIRED')
        if identity.center.activity_ready:
            from scripts.pr122_customer_activity_evidence import guard_subject
            guard_subject(identity.center,project)
        tenants.add(scope['tenant_id'])
        result[scene] = dict(appid=identity.appid,scene=scene,project=binding['project'],
                            project_customer=project['customer'],project_owner=project['owner'],scope=dict(scope))
    if len(tenants) != 1:
        raise PermissionError('SINGLE_CUSTOMER_PLATFORM_TENANT_REQUIRED')
    return result


def native(center, uid):
    # Keep revoked markers visible so they cannot fall back to legacy privileges.
    return center.db.execute('SELECT active,payload FROM links WHERE channel=? AND user_id=? AND project=?',(ACCOUNT,uid,'')).fetchone()


def register_if_unknown(identity, attempt, appid, openid):
    c = identity.center
    if (not c.db.in_transaction or type(attempt) is not str
            or c.db.execute("SELECT 1 FROM events WHERE channel='WECHAT_MINI_LOGIN_ISSUED' AND event_id=?",(attempt,)).fetchone() is None):
        raise PermissionError('ORIGINAL_LOGIN_TRANSACTION_REQUIRED')
    if type(openid) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,128}',openid) or appid != identity.appid:
        raise PermissionError('VERIFIED_PROVIDER_SUBJECT_REQUIRED')
    subject = identity._subject(appid,openid)
    # Any historic binding, including revoked, prevents automatic recreation.
    if c.db.execute("SELECT 1 FROM links WHERE channel='WECHAT_MINI' AND subject_idx=?",(subject,)).fetchone():
        return
    admitted = getattr(identity,'registration',None)
    if not admitted:
        return
    current = policy(identity,list(admitted))
    if current != admitted:
        raise PermissionError('REGISTRATION_MAPPING_CHANGED')
    uid = 'u_'+secrets.token_hex(12)
    # Original accounts schema requires these slots. A namespace index and
    # encrypted EMPTY email represent no email, never a fictional address.
    # Random unusable password material and a non-email index keep the original
    # email/password login/reset from authenticating this provider-only account.
    c.db.execute('INSERT INTO accounts(id,email_idx,email_enc,salt,password,verified) VALUES(?,?,?,?,?,1)',
        (uid,c.idx('community-wechat-account:'+subject),c.encrypt(b'',uid),secrets.token_bytes(16),secrets.token_bytes(32)))
    metadata = dict(appid=appid,identity_verified=True,email_verified=False,
                    authentication='WECHAT_MINIPROGRAM',tenant=next(iter(current.values()))['scope']['tenant_id'])
    c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',
        (ACCOUNT,subject,uid,'',c.encrypt(canonical(metadata),'community-wechat-account')))
    for scene, value in current.items():
        pid = value['project']
        grant_key = c.idx('community-consumer:'+uid+':'+scene)
        c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',
            (CONSUMER,grant_key,uid,pid,c.encrypt(canonical(value),'community-wechat-consumer')))
        c.db.execute("INSERT OR IGNORE INTO links VALUES('WECHAT_MINI',?,?,?,?,1)",
            (subject,uid,pid,c.encrypt(canonical({'appid':appid}),'wechat-mini-link')))
        c.audit(pid,uid,'COMMUNITY_CONSUMER_REGISTERED',grant_key)
    c.audit('',uid,'WECHAT_IDENTITY_VERIFIED_NOT_EMAIL',subject)


def project(identity, uid, scene):
    c = identity.center
    marker = native(c,uid)
    admitted = getattr(identity,'registration',{})
    if marker is None or marker['active'] != 1 or scene not in admitted:
        raise PermissionError('ACTIVE_CONSUMER_REGISTRATION_REQUIRED')
    metadata = json.loads(c.decrypt(marker['payload'],'community-wechat-account'))
    if metadata != dict(appid=identity.appid,identity_verified=True,email_verified=False,
                        authentication='WECHAT_MINIPROGRAM',tenant=admitted[scene]['scope']['tenant_id']):
        raise PermissionError('CONSUMER_ACCOUNT_BINDING_CHANGED')
    current = policy(identity,[scene])[scene]
    if current != admitted[scene]:
        raise PermissionError('REGISTRATION_MAPPING_CHANGED')
    grant_key = c.idx('community-consumer:'+uid+':'+scene)
    grant = c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND user_id=? AND project=? AND active=1',
        (CONSUMER,grant_key,uid,current['project'])).fetchone()
    if grant is None or json.loads(c.decrypt(grant[0],'community-wechat-consumer')) != current:
        raise PermissionError('CONSUMER_SCOPE_REVOKED_OR_CHANGED')
    return c.db.execute('SELECT * FROM projects WHERE id=?',(current['project'],)).fetchone()
