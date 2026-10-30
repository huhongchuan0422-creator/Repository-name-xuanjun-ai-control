"""Protected in-process companion; never register on HTTP or open another Center.

The caller owns the original host lock and serial maintenance window. Approval
verifier is trusted host composition code, not request data or a signature key.
It must independently verify the owner message and exact canonical plan digest.
No production verifier/entrypoint is supplied by this local candidate.
"""
import json
import re
from scripts.pr122_customer_core import Center, canonical, digest, identifier, Denied, Conflict
from scripts.community_mini_host_config import load_protected
from scripts.community_wechat_registration import ACCOUNT, CONSUMER

STATE = 'COMMUNITY_PLATFORM_REVIEWER_V1'
REQUEST = 'COMMUNITY_PLATFORM_REVIEWER_REQUEST_V1'

class ReviewerAdmission:
    def __init__(self, center, identity=None):
        if type(center) is not Center:
            raise TypeError('ORIGINAL_CENTER_REQUIRED')
        self.c = center
        self.identity = identity

    def _read(self, channel, key, project):
        row = self.c.db.execute('SELECT * FROM links WHERE channel=? AND subject_idx=? AND project=?',
                                (channel,key,project)).fetchone()
        if row is None:
            return None
        if row['active'] != 1:
            raise Conflict('ADMISSION_RECORD_REVOKED_OR_DAMAGED')
        value = json.loads(self.c.decrypt(row['payload'], channel+':'+key+':'+project))
        if (type(value) is not dict or set(value)!={'uid','project','revision','request_id','plan_sha256','action','status','approval'} or
            type(value['revision']) is not int or value['revision']<1 or
            value['action'] not in ('GRANT','REVOKE') or value['status']!=('GRANTED' if value['action']=='GRANT' else 'REVOKED') or
            (channel==STATE and (value['uid']!=key or value['project']!=project)) or
            (channel==REQUEST and (value['request_id']!=key or project!=''))):
            raise Conflict('ADMISSION_RECORD_KEY_DRIFT')
        if row['user_id'] != value['uid']:
            raise Conflict('ADMISSION_RECORD_DRIFT')
        return value

    def _write(self, channel, key, project, value):
        self.c.db.execute('INSERT OR REPLACE INTO links VALUES(?,?,?,?,?,1)',
            (channel,key,value['uid'],project,self.c.encrypt(canonical(value),channel+':'+key+':'+project)))

    def _project(self, project, live=True):
        p = self.c.db.execute('SELECT * FROM projects WHERE id=?',(identifier(project),)).fetchone()
        if p is None or p['owner'] != 'system_community_platform':
            raise Denied('ORIGINAL_PLATFORM_REALM_REQUIRED')
        realm = json.loads(self.c.decrypt(p['payload'],'project:'+project))
        if (set(realm) != {'kind','title','requirements','source','authority_ref'} or
            realm['kind'] != 'COMMUNITY_PLATFORM_REALM' or realm['source'] != 'OWNER_APPROVED_FIRST_INSTALL' or
            realm['requirements'] != [] or realm['authority_ref'] != p['authority_ref']):
            raise Denied('ORIGINAL_PLATFORM_REALM_REQUIRED')
        if live and (p['active'] != 1 or p['expires'] <= self.c.now()):
            raise Denied('ACTIVE_PLATFORM_REQUIRED')
        if self.c.activity_ready:
            from scripts.pr122_customer_activity_evidence import guard_subject
            guard_subject(self.c,p)
        result={k:p[k] for k in ('id','tenant','customer','owner','authority_ref','revision','expires')}
        result['realm_sha256']=digest(canonical(realm))
        return result

    def _identity(self, uid, project):
        a = self.c.db.execute('SELECT * FROM accounts WHERE id=?',(identifier(uid),)).fetchone()
        if a is None or a['verified'] != 1:
            raise Denied('VERIFIED_ORIGINAL_ACCOUNT_REQUIRED')
        native = list(self.c.db.execute('SELECT * FROM links WHERE channel=? AND user_id=?',(ACCOUNT,uid)))
        evidence = []
        if native:
            from scripts.community_mini_center_identity import CenterIdentity
            from scripts.community_wechat_registration import project as consumer_project
            if type(self.identity) is not CenterIdentity or self.identity.center is not self.c:
                raise Denied('ORIGINAL_HOST_IDENTITY_REQUIRED')
            scenes=[scene for scene,value in getattr(self.identity,'registration',{}).items() if value['project']==project['id']]
            if not scenes: raise Denied('ORIGINAL_REGISTRATION_SCENE_REQUIRED')
            for scene in scenes: consumer_project(self.identity,uid,scene)
            if len(native)!=1 or native[0]['active']!=1 or native[0]['project']!='':
                raise Denied('ACTIVE_NATIVE_ACCOUNT_REQUIRED')
            n = native[0]; meta=json.loads(self.c.decrypt(n['payload'],'community-wechat-account'))
            expected=dict(appid=meta.get('appid'),identity_verified=True,email_verified=False,
                          authentication='WECHAT_MINIPROGRAM',tenant=project['tenant'])
            if meta!=expected or type(meta['appid']) is not str or not meta['appid']:
                raise Denied('NATIVE_ACCOUNT_BINDING_CHANGED')
            provider=self.c.db.execute("SELECT * FROM links WHERE channel='WECHAT_MINI' AND subject_idx=? AND user_id=? AND project=? AND active=1",
                                       (n['subject_idx'],uid,project['id'])).fetchone()
            if provider is None or json.loads(self.c.decrypt(provider['payload'],'wechat-mini-link'))!={'appid':meta['appid']}:
                raise Denied('ACTIVE_ORIGINAL_PROVIDER_REQUIRED')
            consumers=list(self.c.db.execute('SELECT * FROM links WHERE channel=? AND user_id=? AND project=? AND active=1',(CONSUMER,uid,project['id'])))
            valid=[]
            for r in consumers:
                v=json.loads(self.c.decrypt(r['payload'],'community-wechat-consumer'))
                if (v.get('appid')==meta['appid'] and v.get('project')==project['id'] and v.get('project_customer')==project['customer']
                    and v.get('project_owner')==project['owner'] and v.get('scope',{}).get('tenant_id')==project['tenant']):
                    valid.append(r)
            if not valid: raise Denied('ORIGINAL_CONSUMER_REALM_REQUIRED')
            evidence=[n,provider]+valid
            source='WECHAT_MINIPROGRAM'
        else:
            # Verified bit alone is insufficient: original verification audit required.
            if not self.c.decrypt(a['email_enc'],uid) or self.c.db.execute("SELECT 1 FROM audit WHERE actor=? AND event='EMAIL_VERIFIED' AND object_id=?",(uid,uid)).fetchone() is None:
                raise Denied('ORIGINAL_EMAIL_VERIFICATION_REQUIRED')
            source='EMAIL'
        return dict(uid=uid,epoch=a['epoch'],source=source,account_sha256=digest(canonical(
            [a['email_idx'],digest(a['email_enc']),digest(a['salt']),digest(a['password'])])),
            links_sha256=digest(canonical(sorted([list((r['channel'],r['subject_idx'],r['project'],digest(r['payload']))) for r in evidence]))))

    def inspect(self, project, uid):
        p=self._project(project)
        return dict(project=p,identity=self._identity(uid,p))

    def query(self, request_id):
        record=self._read(REQUEST,identifier(request_id),'')
        if record is None: return {'status':'NOT_FOUND'}
        state=self._read(STATE,record['uid'],record['project'])
        member=self.c.db.execute('SELECT role,active FROM members WHERE project=? AND user_id=?',(record['project'],record['uid'])).fetchone()
        if (state is None or member is None or member['role']!='REVIEWER' or
                member['active'] != (1 if state['status']=='GRANTED' else 0)):
            raise Conflict('MEMBER_RECORD_DRIFT')
        if self.c.db.execute('SELECT 1 FROM audit WHERE project=? AND actor=? AND event=? AND object_id=?',
            (record['project'],'system_community_platform','PLATFORM_REVIEWER_'+record['action'],record['plan_sha256'])).fetchone() is None:
            raise Conflict('ADMISSION_AUDIT_MISSING')
        current_request=self._read(REQUEST,state['request_id'],'')
        if current_request != state:
            raise Conflict('LATEST_REQUEST_STATE_DRIFT')
        if self.c.db.execute('SELECT 1 FROM audit WHERE project=? AND actor=? AND event=? AND object_id=?',
            (state['project'],'system_community_platform','PLATFORM_REVIEWER_'+state['action'],state['plan_sha256'])).fetchone() is None:
            raise Conflict('LATEST_ADMISSION_AUDIT_MISSING')
        return dict(status=state['status'],revision=state['revision'],request_id=request_id,
                    request_revision=record['revision'],superseded=state['request_id']!=request_id,
                    project=record['project'],uid=record['uid'])

    def apply_protected(self, path, expected_sha256, verify_owner):
        """Only trusted maintenance composition calls this, with a fixed plan path.
        verify_owner(plan_sha256, approval_metadata) must independently verify
        owner provenance + exact intent; a JSON boolean is never authority.
        """
        plan=load_protected(path)
        sha=digest(canonical(plan))
        if sha!=expected_sha256 or not callable(verify_owner): raise Denied('REVIEWED_PLAN_REQUIRED')
        if set(plan)!={'version','action','role','request_id','project','uid','expected_revision','snapshot','approval'} or type(plan['version']) is not int or plan['version']!=1 or plan['role']!='REVIEWER' or plan['action'] not in ('GRANT','REVOKE'):
            raise Denied('EXACT_REVIEWER_PLAN_REQUIRED')
        for k in ('request_id','project','uid'):identifier(plan[k])
        if type(plan['expected_revision']) is not int or plan['expected_revision']<0:
            raise ValueError('EXACT_REVISION_REQUIRED')
        approval=plan['approval']
        if (type(approval) is not dict or set(approval)!={'owner_message_id','owner_body_sha256'} or
            not all(type(v) is str and v for v in approval.values()) or
            not re.fullmatch('[0-9a-f]{64}',approval['owner_body_sha256']) or verify_owner(sha,dict(approval)) is not True):
            raise Denied('OWNER_CONFIRMATION_REQUIRED')
        if self.c.db.in_transaction: raise Conflict('SERIAL_MAINTENANCE_BOUNDARY_REQUIRED')
        with self.c.tx():
            previous=self._read(REQUEST,plan['request_id'],'')
            if previous:
                if previous['plan_sha256']!=sha:raise Conflict('REQUEST_REPLAY_CONFLICT')
                return self.query(plan['request_id'])
            pid,uid=plan['project'],plan['uid']
            if plan['action']=='GRANT':
                if self.inspect(pid,uid)!=plan['snapshot']:raise Conflict('ACCOUNT_OR_PROJECT_DRIFT')
            else:
                if self._project(pid,live=False)!=plan['snapshot']['project']:raise Conflict('PROJECT_DRIFT')
            old=self._read(STATE,uid,pid)
            revision=old['revision'] if old else 0
            member=self.c.db.execute('SELECT role,active FROM members WHERE project=? AND user_id=?',(pid,uid)).fetchone()
            if revision!=plan['expected_revision']:raise Conflict('GRANT_REVISION_CONFLICT')
            if old:
                prior=self.query(old['request_id'])
                if prior.get('status')=='NOT_FOUND' or prior.get('superseded') or prior.get('revision')!=old['revision']:
                    raise Conflict('PRIOR_REQUEST_STATE_DRIFT')
                if member is None or member['role']!='REVIEWER' or member['active']!=(1 if old['status']=='GRANTED' else 0):raise Conflict('MEMBER_RECORD_DRIFT')
                if old['status']==('GRANTED' if plan['action']=='GRANT' else 'REVOKED'):raise Conflict('DUPLICATE_TRANSITION')
            elif member is not None or plan['action']=='REVOKE':raise Conflict('UNMANAGED_MEMBER_CONFLICT')
            active=1 if plan['action']=='GRANT' else 0
            self.c.db.execute('INSERT OR REPLACE INTO members VALUES(?,?,?,?)',(pid,uid,'REVIEWER',active))
            record=dict(uid=uid,project=pid,revision=revision+1,request_id=plan['request_id'],plan_sha256=sha,
                        action=plan['action'],status='GRANTED' if active else 'REVOKED',approval=approval)
            self._write(STATE,uid,pid,record)
            self._write(REQUEST,plan['request_id'],'',record)
            self.c.audit(pid,'system_community_platform','PLATFORM_REVIEWER_'+plan['action'],sha)
            return self.query(plan['request_id'])
