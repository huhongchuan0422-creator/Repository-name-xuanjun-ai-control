"""Store-specific staff delegation on original Center project membership.

No grant creates an account/project member or grants Finance/platform powers.
Original owner invitations and acceptance remain the sole membership process.
"""
import hashlib
import json
import re
from scripts.pr122_customer_core import canonical

READ_OPERATIONS = ('community.orders', 'community.summary', 'community.orders_page',
                   'community.order_detail', 'community.merchant_settings')


class Staff:
    def __init__(self, operations):
        self.operations, self.center = operations, operations.center

    def resolve(self, workspace, uid):
        if type(workspace) is not str or not re.fullmatch('staff_[0-9a-f]{40}', workspace):
            return None
        row = self.center.db.execute("SELECT user_id,project,payload FROM links WHERE channel='COMMUNITY_STAFF_GRANT' AND subject_idx=? AND user_id=? AND active=1", (workspace, uid)).fetchone()
        if row is None:
            return None
        saved = json.loads(self.center.decrypt(row['payload'], 'community-staff:' + workspace))
        parent = self.operations.grants.get(saved['parent_workspace'])
        if parent is None or parent['role'] != 'MERCHANT_ADMIN' or parent['scope'] != saved['scope'] or parent['project'] != row['project'] or parent['user_id'] != saved['delegated_by']:
            raise PermissionError('STAFF_PARENT_GRANT_CHANGED')
        self.center.project(parent['user_id'], row['project'], ('OWNER',))
        if parent['onboarding_required']:
            from scripts.community_merchant_opening import authorize_workspace
            authorize_workspace(self.operations.onboarding,self.operations,saved['parent_workspace'],parent['user_id'])
        candidates = [p for p, identity in self.operations.runtime.bindings.items() if p.role=='STORE_STAFF' and identity==saved['scope']]
        if len(candidates) != 1:
            raise PermissionError('ORIGINAL_REGISTERED_STORE_STAFF_PRINCIPAL_REQUIRED')
        return dict(user_id=uid, project=row['project'], project_roles=('OWNER','EDITOR','VIEWER'), principal=candidates[0],
            role='STORE_STAFF', tenant=saved['scope']['tenant_id'], scope=saved['scope'], onboarding_required=False,
            allowed_operations=tuple(saved['operations']))

    def dispatch(self, session, csrf, parent_workspace, operation, params):
        c = self.center
        if type(csrf) is not str or not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
        uid = c.session(session, csrf)
        parent = self.operations.grants.get(parent_workspace)
        if parent is None or parent['user_id'] != uid or parent['role'] != 'MERCHANT_ADMIN':
            raise PermissionError('ORIGINAL_MERCHANT_OWNER_REQUIRED')
        c.project(uid,parent['project'],('OWNER',))
        if parent['onboarding_required']:
            from scripts.community_merchant_opening import authorize_workspace
            authorize_workspace(self.operations.onboarding,self.operations,parent_workspace,uid)
        fields = {'community.staff_invite': {'email','project_role'},
                  'community.staff_grant': {'user_id','operations'},
                  'community.staff_remove': {'workspace'}, 'community.staff_list': {'after_id'}}
        p = params
        if operation not in fields or type(p) is not dict or set(p)!=fields[operation]:
            raise ValueError('INVALID_STAFF_FIELDS')
        if operation=='community.staff_invite':
            return c.invite(uid,parent['project'],p['email'],p['project_role'])
        with c.tx():
            c.limit('community-staff:'+uid,30,60)
            if operation=='community.staff_list':
                after=p['after_id']
                if type(after) is not str or after and not re.fullmatch('staff_[0-9a-f]{40}',after):raise ValueError('INVALID_STAFF_CURSOR')
                rows=c.db.execute("SELECT subject_idx,payload,active FROM links WHERE channel='COMMUNITY_STAFF_GRANT' AND project=? AND subject_idx>? ORDER BY subject_idx LIMIT 51",(parent['project'],after)).fetchall()
                records=[]
                for key,payload,active in rows[:50]:
                    value=json.loads(c.decrypt(payload,'community-staff:'+key))
                    if value['scope']==parent['scope'] and value['parent_workspace']==parent_workspace:
                        records.append(dict(workspace=key,user_id=value['user_id'],operations=value['operations'],active=bool(active)))
                return dict(records=records,has_more=len(rows)>50,next_cursor=rows[49][0] if len(rows)>50 else None)
            if operation=='community.staff_grant':
                target=p['user_id']
                if type(target) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',target) or target==uid:raise ValueError('INVALID_STAFF_USER')
                c.project(target,parent['project'],('EDITOR','VIEWER'))
                account=c.db.execute('SELECT verified FROM accounts WHERE id=?',(target,)).fetchone()
                if account is None or not account[0]:raise PermissionError('VERIFIED_ORIGINAL_ACCOUNT_REQUIRED')
                permissions=p['operations']
                if type(permissions) is not list or not permissions or len(set(permissions))!=len(permissions) or any(v not in READ_OPERATIONS for v in permissions):raise PermissionError('STAFF_OPERATION_NOT_DELEGABLE')
                if sum(1 for principal,identity in self.operations.runtime.bindings.items() if principal.role=='STORE_STAFF' and identity==parent['scope'])!=1:raise PermissionError('ORIGINAL_REGISTERED_STAFF_PRINCIPAL_REQUIRED')
                key='staff_'+hashlib.sha256(canonical([parent['scope'],parent['project'],target])).hexdigest()[:40]
                value=dict(user_id=target,scope=parent['scope'],parent_workspace=parent_workspace,delegated_by=uid,operations=permissions)
                old=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_STAFF_GRANT' AND subject_idx=? AND project=?",(key,parent['project'])).fetchone()
                if old and json.loads(c.decrypt(old[0],'community-staff:'+key))['parent_workspace']!=parent_workspace:raise PermissionError('STAFF_GRANT_OWNER_CONFLICT')
                c.db.execute("INSERT INTO links VALUES('COMMUNITY_STAFF_GRANT',?,?,?,?,1) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload,active=1",(key,target,parent['project'],c.encrypt(canonical(value),'community-staff:'+key)))
                c.audit(parent['project'],uid,'COMMUNITY_STAFF_GRANTED',key)
                return dict(workspace=key,operations=permissions)
            key=p['workspace']
            if type(key) is not str or not re.fullmatch('staff_[0-9a-f]{40}',key):raise ValueError('INVALID_STAFF_WORKSPACE')
            row=c.db.execute("SELECT payload FROM links WHERE channel='COMMUNITY_STAFF_GRANT' AND subject_idx=? AND project=?",(key,parent['project'])).fetchone()
            if row is None:raise PermissionError('STAFF_GRANT_NOT_FOUND')
            value=json.loads(c.decrypt(row[0],'community-staff:'+key))
            if value['scope']!=parent['scope'] or value['parent_workspace']!=parent_workspace:raise PermissionError('STAFF_SCOPE_DENIED')
            c.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_STAFF_GRANT' AND subject_idx=? AND project=?",(key,parent['project']))
            c.audit(parent['project'],uid,'COMMUNITY_STAFF_REMOVED',key)
            return dict(workspace=key,active=False)
