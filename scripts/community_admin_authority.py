"""Original Center community authority. Local candidate; no HTTP/CLI bootstrap.

Capabilities are exact original route/operation pairs, not role substitutions.
This slice deliberately has no production writer entrypoint. Caller owns the
original host locks. Transport integration and protected bootstrap are pending.
"""
import json
import secrets
import hmac
from scripts.pr122_customer_core import Center, canonical, digest, identifier, email, Denied, Conflict

CHANNEL = 'COMMUNITY_ADMIN_AUTHORITY_V1'
ACCOUNT_INDEX = 'community-owner-provisioned:'
ROUTES = frozenset(('/community/admin','/merchant/onboarding','/community/operations','/customer/saas-api','/community/fulfillment','/community/provider-actions','/community/merchant-bills','/community/directory','/community/commerce','/community/project-materials'))

class CommunityAdminAuthority:
    def __init__(self, center, project, tenant, capabilities, workspace_scopes=(), scope_binding_sha='0'*64):
        if type(center) is not Center:
            raise TypeError('ORIGINAL_CENTER_REQUIRED')
        self.c = center
        self.project, self.tenant = identifier(project), identifier(tenant)
        if type(capabilities) is not tuple or not capabilities or len(set(capabilities)) != len(capabilities):
            raise ValueError('EXACT_CAPABILITY_MANIFEST_REQUIRED')
        for value in capabilities:
            if type(value) is not str or len(value) > 200 or value.count('#') != 1:
                raise ValueError('EXACT_ROUTE_OPERATION_REQUIRED')
            route, op = value.split('#')
            if route not in ROUTES or not op or '*' in value:
                raise ValueError('EXACT_ROUTE_OPERATION_REQUIRED')
        self.capabilities = frozenset(capabilities)
        if type(workspace_scopes) is not tuple or len(set(workspace_scopes))!=len(workspace_scopes):raise ValueError('EXACT_WORKSPACE_CATALOG_REQUIRED')
        for value in workspace_scopes:
            if type(value) is not str or value.count('#')!=1 or value.split('#')[0] not in ROUTES or not value.split('#')[1] or '*' in value:raise ValueError('EXACT_WORKSPACE_CATALOG_REQUIRED')
        if type(scope_binding_sha) is not str or len(scope_binding_sha)!=64 or any(c not in '0123456789abcdef' for c in scope_binding_sha):raise ValueError('EXACT_SCOPE_BINDING_DIGEST_REQUIRED')
        self.scope_binding_sha=scope_binding_sha
        self.workspace_scopes=frozenset(workspace_scopes)
        self.manifest_sha = digest(canonical(dict(capabilities=sorted(capabilities),workspace_scopes=sorted(workspace_scopes),scope_binding_sha=scope_binding_sha)))

    def _realm(self):
        p = self.c.db.execute('SELECT * FROM projects WHERE id=?', (self.project,)).fetchone()
        if p is None or p['tenant'] != self.tenant or not p['active'] or p['expires'] <= self.c.now() or p['owner'] != 'system_community_platform':
            raise Denied('ACTIVE_ORIGINAL_COMMUNITY_REALM_REQUIRED')
        realm = json.loads(self.c.decrypt(p['payload'], 'project:'+self.project))
        if realm.get('kind') != 'COMMUNITY_PLATFORM_REALM' or realm.get('source') != 'OWNER_APPROVED_FIRST_INSTALL' or realm.get('authority_ref') != p['authority_ref'] or realm.get('requirements') != []:
            raise Denied('ORIGINAL_COMMUNITY_REALM_REQUIRED')
        if self.c.activity_ready:
            from scripts.pr122_customer_activity_evidence import guard_subject
            guard_subject(self.c, p)
        return p

    def _read(self, uid):
        identifier(uid)
        row = self.c.db.execute('SELECT * FROM links WHERE channel=? AND subject_idx=? AND project=?', (CHANNEL, uid, self.project)).fetchone()
        if row is None:
            raise Denied('COMMUNITY_ADMIN_NOT_GRANTED')
        value = json.loads(self.c.decrypt(row['payload'], CHANNEL+':'+uid+':'+self.project))
        fields = {'uid','project','tenant','kind','revision','parent','parent_revision','capabilities','workspace_scopes','scope_binding_sha','manifest_sha','request_id'}
        if type(value) is not dict or set(value) != fields or value['uid'] != uid or value['project'] != self.project or value['tenant'] != self.tenant or row['user_id'] != uid or value['manifest_sha'] != self.manifest_sha or value['scope_binding_sha']!=self.scope_binding_sha:
            raise Denied('COMMUNITY_ADMIN_BINDING_CHANGED')
        if not row['active'] or type(value['revision']) is not int or value['revision'] < 1:
            raise Denied('COMMUNITY_ADMIN_REVOKED')
        if value['kind'] not in ('ROOT','DELEGATE') or type(value['capabilities']) is not list or len(set(value['capabilities'])) != len(value['capabilities']) or not set(value['capabilities']) <= self.capabilities:
            raise Denied('COMMUNITY_ADMIN_CAPABILITIES_INVALID')
        if type(value['workspace_scopes']) is not list or len(set(value['workspace_scopes']))!=len(value['workspace_scopes']) or not set(value['workspace_scopes'])<=self.workspace_scopes:raise Denied('ADMIN_SCOPE_INVALID')
        a = self.c.db.execute('SELECT * FROM accounts WHERE id=?', (uid,)).fetchone()
        if a is None or a['verified'] != 1:
            raise Denied('ACTIVE_ORIGINAL_ACCOUNT_REQUIRED')
        address=self.c.decrypt(a['email_enc'],uid).decode()
        if a['email_idx']==self.c.idx(ACCOUNT_INDEX+address):
            proof=self.c.db.execute('SELECT payload,active FROM links WHERE channel=? AND subject_idx=? AND project=? AND user_id=?',(CHANNEL+'_IDENTITY',uid,self.project,uid)).fetchone()
            if proof is None or proof['active']!=1:raise Denied('OWNER_PROVISIONED_IDENTITY_REVOKED')
            identity=json.loads(self.c.decrypt(proof['payload'],CHANNEL+'_IDENTITY:'+uid+':'+self.project))
            if identity.get('kind')!='OWNER_PROVISIONED_ACCOUNT' or identity.get('mailbox_verified') is not False or identity.get('owner_binding',{}).get('email')!=address or identity['owner_binding'].get('project')!=self.project or identity['owner_binding'].get('tenant')!=self.tenant:raise Denied('OWNER_PROVISIONED_IDENTITY_CHANGED')
        return value

    def authority(self, uid):
        self._realm()
        value = self._read(uid)
        if value['kind'] == 'ROOT':
            if value['parent'] is not None or value['parent_revision'] is not None or set(value['capabilities']) != self.capabilities or set(value['workspace_scopes'])!=self.workspace_scopes:
                raise Denied('ROOT_AUTHORITY_INVALID')
        else:
            parent = self._read(value['parent'])
            if parent['kind'] != 'ROOT' or parent['parent'] is not None or parent['parent_revision'] is not None or set(parent['capabilities']) != self.capabilities or parent['revision'] != value['parent_revision'] or not set(value['capabilities']) <= set(parent['capabilities']) or set(parent['workspace_scopes'])!=self.workspace_scopes or not set(value['workspace_scopes'])<=set(parent['workspace_scopes']):
                raise Denied('ADMIN_PARENT_CHANGED')
        return value

    def authorize(self, session, csrf, route, operation, workspace=None):
        if type(csrf) is not str or not csrf:
            raise Denied('CSRF_REQUIRED')
        uid = self.c.session(session, csrf)
        value = self.authority(uid)
        capability = route+'#'+operation
        if capability not in self.capabilities or capability not in value['capabilities']:
            raise Denied('COMMUNITY_ADMIN_OPERATION_DENIED')
        if workspace is not None and (type(workspace) is not str or route+'#'+workspace not in value['workspace_scopes']):raise Denied('COMMUNITY_ADMIN_WORKSPACE_DENIED')
        return dict(uid=uid, project=self.project, tenant=self.tenant, revision=value['revision'], capability=capability)

    def _write(self, value, active):
        uid = value['uid']
        self.c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,?) ON CONFLICT(channel,subject_idx,project) DO UPDATE SET payload=excluded.payload,active=excluded.active',
            (CHANNEL, uid, uid, self.project, self.c.encrypt(canonical(value), CHANNEL+':'+uid+':'+self.project), int(active)))

    def _request(self, request_id, intent):
        row = self.c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=?', (CHANNEL+'_REQUEST', request_id, self.project)).fetchone()
        if row is None: return None
        saved = json.loads(self.c.decrypt(row[0], CHANNEL+'_REQUEST:'+request_id+':'+self.project))
        if saved['intent_sha'] != digest(canonical(intent)): raise Conflict('ADMIN_REQUEST_CONFLICT')
        return saved['result']

    def _save_request(self, request_id, intent, result, uid):
        value = dict(intent_sha=digest(canonical(intent)), result=result)
        self.c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)', (CHANNEL+'_REQUEST',request_id,uid,self.project,self.c.encrypt(canonical(value),CHANNEL+'_REQUEST:'+request_id+':'+self.project)))

    def bootstrap(self, address, password, request_id, owner_binding, verifier):
        """Protected composition only; caller supplies independently trusted verifier.
        No HTTP/request-selected verifier. Original host locks/backup required by
        eventual carrier (not supplied in this slice). No fake mailbox proof.
        """
        address=email(address);identifier(request_id)
        if not callable(verifier) or type(owner_binding) is not dict or set(owner_binding) not in ({'owner_message_id','owner_body_sha256','project','tenant','email','manifest_sha','request_id','action'},{'owner_message_id','owner_body_sha256','project','tenant','email','manifest_sha','request_id','action','execution_binding_sha256'}):
            raise Denied('EXACT_OWNER_BOOTSTRAP_BINDING_REQUIRED')
        expected=dict(project=self.project,tenant=self.tenant,email=address,manifest_sha=self.manifest_sha,request_id=request_id,action='BOOTSTRAP_COMMUNITY_SUPERADMIN')
        if any(owner_binding.get(k)!=v for k,v in expected.items()) or not verifier(dict(owner_binding)):
            raise Denied('EXACT_OWNER_BOOTSTRAP_BINDING_REQUIRED')
        intent=dict(expected,owner_message_id=owner_binding['owner_message_id'],owner_body_sha256=owner_binding['owner_body_sha256'])
        if 'execution_binding_sha256' in owner_binding:
            value=owner_binding['execution_binding_sha256']
            if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise Denied('EXACT_EXECUTION_BINDING_REQUIRED')
            intent['execution_binding_sha256']=value
        salt=secrets.token_bytes(16);pw=self.c.password(password,salt)
        with self.c.tx():
            self._realm()
            old=self._request(request_id,intent)
            if old is not None:
                current=self.authority(old['uid'])
                if current['kind']!='ROOT': raise Conflict('ROOT_READBACK_CHANGED')
                return dict(old,replayed=True)
            if self.c.db.execute('SELECT 1 FROM links WHERE channel=? AND project=?',(CHANNEL,self.project)).fetchone():
                raise Conflict('COMMUNITY_AUTHORITY_ALREADY_INITIALIZED')
            if self.c.db.execute('SELECT 1 FROM accounts WHERE email_idx IN (?,?)',(self.c.idx(address),self.c.idx(ACCOUNT_INDEX+address))).fetchone():
                raise Conflict('ACCOUNT_EXISTS_NO_PASSWORD_OVERWRITE')
            uid='u_'+secrets.token_hex(12)
            self.c.db.execute('INSERT INTO accounts(id,email_idx,email_enc,salt,password,verified) VALUES(?,?,?,?,?,1)',(uid,self.c.idx(ACCOUNT_INDEX+address),self.c.encrypt(address.encode(),uid),salt,pw))
            provenance=dict(kind='OWNER_PROVISIONED_ACCOUNT',mailbox_verified=False,owner_binding=owner_binding)
            self.c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',(CHANNEL+'_IDENTITY',uid,uid,self.project,self.c.encrypt(canonical(provenance),CHANNEL+'_IDENTITY:'+uid+':'+self.project)))
            value=dict(uid=uid,project=self.project,tenant=self.tenant,kind='ROOT',revision=1,parent=None,parent_revision=None,capabilities=sorted(self.capabilities),workspace_scopes=sorted(self.workspace_scopes),manifest_sha=self.manifest_sha,scope_binding_sha=self.scope_binding_sha,request_id=request_id)
            self._write(value,True)
            self.c.audit(self.project,uid,'COMMUNITY_OWNER_PROVISIONED_ACCOUNT',digest(canonical(provenance)))
            self.c.audit(self.project,uid,'COMMUNITY_SUPERADMIN_BOOTSTRAPPED',digest(canonical(value)))
            result=dict(uid=uid,project=self.project,tenant=self.tenant,kind='ROOT',revision=1,manifest_sha=self.manifest_sha,mailbox_verified=False)
            self._save_request(request_id,intent,result,uid)
            return result

    def delegate(self, session, csrf, target, capabilities, request_id, expected_revision, workspace_scopes=None):
        identifier(target); identifier(request_id)
        workspace_scopes=[] if workspace_scopes is None else workspace_scopes
        if type(workspace_scopes) is not list or len(set(workspace_scopes))!=len(workspace_scopes) or not set(workspace_scopes)<=self.workspace_scopes:raise Denied('EXACT_WORKSPACE_SUBSET_REQUIRED')
        if type(csrf) is not str or not csrf: raise Denied('CSRF_REQUIRED')
        if type(capabilities) is not list or not capabilities or len(set(capabilities)) != len(capabilities) or not set(capabilities) <= self.capabilities:
            raise Denied('EXACT_SUBSET_REQUIRED')
        # Management is root-only regardless of a child's supplied capability list.
        if any(x.startswith('/community/admin#') for x in capabilities):
            raise Denied('ADMIN_MANAGEMENT_NOT_DELEGABLE')
        with self.c.tx():
            uid = self.c.session(session, csrf)
            parent = self.authority(uid)
            if parent['kind'] != 'ROOT' or uid == target:
                raise Denied('ROOT_ONLY_NO_SELF_CHANGE')
            intent=dict(action='DELEGATE',actor=uid,target=target,capabilities=sorted(capabilities),workspace_scopes=sorted(workspace_scopes),expected_revision=expected_revision,parent_revision=parent['revision'])
            old=self._request(request_id,intent)
            if old is not None:
                current=self.authority(target)
                if current['revision']!=old['revision']: raise Conflict('ADMIN_REQUEST_SUPERSEDED')
                return dict(old,replayed=True)
            a = self.c.db.execute('SELECT verified FROM accounts WHERE id=?', (target,)).fetchone()
            if a is None or a['verified'] != 1:
                raise Denied('EXISTING_VERIFIED_TARGET_REQUIRED')
            row = self.c.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=?', (CHANNEL,target,self.project)).fetchone()
            prior = json.loads(self.c.decrypt(row[0],CHANNEL+':'+target+':'+self.project)) if row else None
            revision = prior['revision'] if prior else 0
            if prior and prior['kind'] == 'ROOT':
                raise Denied('CANNOT_REPLACE_ROOT')
            if type(expected_revision) is not int or revision != expected_revision:
                raise Conflict('ADMIN_REVISION_CHANGED')
            value = dict(uid=target,project=self.project,tenant=self.tenant,kind='DELEGATE',revision=revision+1,parent=uid,parent_revision=parent['revision'],capabilities=sorted(capabilities),workspace_scopes=sorted(workspace_scopes),manifest_sha=self.manifest_sha,scope_binding_sha=self.scope_binding_sha,request_id=request_id)
            self._write(value, True)
            self.c.audit(self.project,uid,'COMMUNITY_ADMIN_DELEGATED',digest(canonical(value)))
            result=dict(uid=target,revision=value['revision'],kind='DELEGATE',capabilities=value['capabilities'])
            self._save_request(request_id,intent,result,uid)
            return result

    def create_subadmin(self, session, csrf, address, password, capabilities, request_id, workspace_scopes=None):
        """Root creates exact limited subordinate in same original account store."""
        address=email(address);identifier(request_id)
        workspace_scopes=[] if workspace_scopes is None else workspace_scopes
        if type(workspace_scopes) is not list or len(set(workspace_scopes))!=len(workspace_scopes) or not set(workspace_scopes)<=self.workspace_scopes:raise Denied('EXACT_WORKSPACE_SUBSET_REQUIRED')
        if type(csrf) is not str or not csrf:raise Denied('CSRF_REQUIRED')
        if type(capabilities) is not list or not capabilities or len(set(capabilities))!=len(capabilities) or not set(capabilities)<=self.capabilities or any(x.startswith('/community/admin#') for x in capabilities):
            raise Denied('EXACT_NONMANAGEMENT_SUBSET_REQUIRED')
        salt=secrets.token_bytes(16);pw=self.c.password(password,salt)
        with self.c.tx():
            actor=self.c.session(session,csrf);parent=self.authority(actor)
            if parent['kind']!='ROOT':raise Denied('ROOT_ONLY_ACCOUNT_CREATION')
            intent=dict(action='CREATE_SUBADMIN',actor=actor,email=address,project=self.project,tenant=self.tenant,capabilities=sorted(capabilities),workspace_scopes=sorted(workspace_scopes),parent_revision=parent['revision'])
            old=self._request(request_id,intent)
            if old is not None:
                current=self.authority(old['uid'])
                if current['revision']!=old['revision']:raise Conflict('ADMIN_REQUEST_SUPERSEDED')
                return dict(old,replayed=True)
            if self.c.db.execute('SELECT 1 FROM accounts WHERE email_idx IN (?,?)',(self.c.idx(address),self.c.idx(ACCOUNT_INDEX+address))).fetchone():
                raise Conflict('ACCOUNT_EXISTS_NO_PASSWORD_OVERWRITE')
            uid='u_'+secrets.token_hex(12)
            self.c.db.execute('INSERT INTO accounts(id,email_idx,email_enc,salt,password,verified) VALUES(?,?,?,?,?,1)',(uid,self.c.idx(ACCOUNT_INDEX+address),self.c.encrypt(address.encode(),uid),salt,pw))
            proof=dict(kind='OWNER_PROVISIONED_ACCOUNT',mailbox_verified=False,owner_binding=dict(email=address,project=self.project,tenant=self.tenant,parent=actor,request_id=request_id))
            self.c.db.execute('INSERT INTO links VALUES(?,?,?,?,?,1)',(CHANNEL+'_IDENTITY',uid,uid,self.project,self.c.encrypt(canonical(proof),CHANNEL+'_IDENTITY:'+uid+':'+self.project)))
            value=dict(uid=uid,project=self.project,tenant=self.tenant,kind='DELEGATE',revision=1,parent=actor,parent_revision=parent['revision'],capabilities=sorted(capabilities),workspace_scopes=sorted(workspace_scopes),manifest_sha=self.manifest_sha,scope_binding_sha=self.scope_binding_sha,request_id=request_id)
            self._write(value,True)
            self.c.audit(self.project,actor,'COMMUNITY_SUBADMIN_ACCOUNT_CREATED',digest(canonical(value)))
            result=dict(uid=uid,project=self.project,tenant=self.tenant,kind='DELEGATE',revision=1,capabilities=sorted(capabilities),mailbox_verified=False)
            self._save_request(request_id,intent,result,uid)
            return result

    def revoke(self, session, csrf, target, expected_revision, request_id=None):
        if request_id is not None:identifier(request_id)
        if type(expected_revision) is not int or expected_revision<1: raise Denied('EXACT_CHILD_REVISION_REQUIRED')
        if type(csrf) is not str or not csrf: raise Denied('CSRF_REQUIRED')
        with self.c.tx():
            uid = self.c.session(session, csrf)
            parent = self.authority(uid)
            if parent['kind'] != 'ROOT' or target == uid:
                raise Denied('ROOT_ONLY_NO_SELF_CHANGE')
            intent=dict(action='REVOKE',actor=uid,target=target,expected_revision=expected_revision,parent_revision=parent['revision'])
            prior=self._request(request_id,intent) if request_id is not None else None
            if prior is not None:
                record=self.c.db.execute('SELECT payload,active FROM links WHERE channel=? AND subject_idx=? AND project=?',(CHANNEL,target,self.project)).fetchone()
                if record is None or record['active']!=0 or json.loads(self.c.decrypt(record['payload'],CHANNEL+':'+target+':'+self.project))['revision']!=prior['revision']:raise Conflict('ADMIN_REQUEST_SUPERSEDED')
                return dict(prior,replayed=True)
            value = self._read(target)
            if value['kind'] != 'DELEGATE' or value['parent'] != uid or value['revision'] != expected_revision:
                raise Denied('EXACT_CHILD_REVISION_REQUIRED')
            value['revision'] += 1
            self._write(value, False)
            self.c.audit(self.project,uid,'COMMUNITY_ADMIN_REVOKED',target)
            result=dict(uid=target,active=False,revision=value['revision'])
            if request_id is not None:self._save_request(request_id,intent,result,uid)
            return result


def community_login(center, address, password):
    """Original community session; provisioned address is not verified email."""
    if type(center) is not Center:raise TypeError('ORIGINAL_CENTER_REQUIRED')
    address=email(address)
    with center.tx():center.limit('community-owner-login:'+address)
    index=center.idx(ACCOUNT_INDEX+address)
    if center.db.execute('SELECT 1 FROM accounts WHERE email_idx=?',(index,)).fetchone() is None:
        return center.login(address,password)
    # Account, provenance, current authority and session issuance share the
    # original BEGIN IMMEDIATE, so revocation cannot slip between their checks.
    with center.tx():
        row=center.db.execute('SELECT * FROM accounts WHERE email_idx=?',(index,)).fetchone()
        if row is None or not row['verified'] or not hmac.compare_digest(center.password(password,row['salt']),row['password']):
            raise Denied('INVALID_CREDENTIALS')
        if center.db.execute('SELECT 1 FROM accounts WHERE email_idx=?',(center.idx(address),)).fetchone():
            raise Denied('ACCOUNT_NAMESPACE_COLLISION')
        proofs=list(center.db.execute('SELECT project,payload,active FROM links WHERE channel=? AND subject_idx=? AND user_id=?',(CHANNEL+'_IDENTITY',row['id'],row['id'])))
        if len(proofs)!=1 or proofs[0]['active']!=1:raise Denied('OWNER_PROVISIONED_IDENTITY_REQUIRED')
        proof=proofs[0]
        identity=json.loads(center.decrypt(proof['payload'],CHANNEL+'_IDENTITY:'+row['id']+':'+proof['project']))
        if identity.get('kind')!='OWNER_PROVISIONED_ACCOUNT' or identity.get('mailbox_verified') is not False or identity.get('owner_binding',{}).get('email')!=address:
            raise Denied('OWNER_PROVISIONED_IDENTITY_REQUIRED')
        grant=center.db.execute('SELECT payload,active FROM links WHERE channel=? AND subject_idx=? AND project=?',(CHANNEL,row['id'],proof['project'])).fetchone()
        if grant is None or grant['active']!=1:raise Denied('COMMUNITY_ADMIN_REVOKED')
        value=json.loads(center.decrypt(grant['payload'],CHANNEL+':'+row['id']+':'+proof['project']))
        if value['kind']=='ROOT':
            capabilities=value['capabilities'];workspace_scopes=value['workspace_scopes'];scope_binding_sha=value['scope_binding_sha']
        else:
            parent=center.db.execute('SELECT payload FROM links WHERE channel=? AND subject_idx=? AND project=?',(CHANNEL,value['parent'],proof['project'])).fetchone()
            if parent is None:raise Denied('ADMIN_PARENT_CHANGED')
            parent_value=json.loads(center.decrypt(parent[0],CHANNEL+':'+value['parent']+':'+proof['project']))
            capabilities=parent_value['capabilities'];workspace_scopes=parent_value['workspace_scopes'];scope_binding_sha=parent_value['scope_binding_sha']
        api=CommunityAdminAuthority(center,proof['project'],identity['owner_binding']['tenant'],tuple(capabilities),tuple(workspace_scopes),scope_binding_sha)
        api.authority(row['id'])
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        center.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(token.encode()),row['id'],row['epoch'],digest(csrf.encode()),center.now()+3600))
        center.audit(proof['project'],row['id'],'COMMUNITY_OWNER_ACCOUNT_LOGIN',row['id'])
        return dict(token=token,csrf=csrf,user_id=row['id'])


def full_community_capabilities():
    from scripts.community_admin_route_inventory import BUSINESS_CAPABILITIES
    return tuple(sorted(set(BUSINESS_CAPABILITIES)|{'/community/admin#'+op for op in ('catalog','list','create','grant','revoke')}))


def attach_core_admin(center, project_ids):
    """Restore account-management-only composition from original root record.
    Business capabilities are full; missing business scopes remain unavailable.
    No accounts/config/roles are written, no optional provider is required.
    """
    if type(center) is not Center:raise TypeError('ORIGINAL_CENTER_REQUIRED')
    candidates=[]
    for row in center.db.execute('SELECT subject_idx,project,payload FROM links WHERE channel=?',(CHANNEL,)):
        if row['project'] not in project_ids:continue
        value=json.loads(center.decrypt(row['payload'],CHANNEL+':'+row['subject_idx']+':'+row['project']))
        if value.get('kind')=='ROOT':candidates.append(value)
    if not candidates:return None
    if len(candidates)!=1:raise Denied('EXACT_COMMUNITY_ROOT_COMPOSITION_REQUIRED')
    value=candidates[0]
    empty_binding=digest(canonical(dict(workspace_bindings={},registered={})))
    if value['workspace_scopes'] or set(value['capabilities'])!=set(full_community_capabilities()) or value['scope_binding_sha']!=empty_binding:
        raise Denied('BUSINESS_SCOPE_CONFIGURATION_REQUIRED')
    api=CommunityAdminAuthority(center,value['project'],value['tenant'],full_community_capabilities(),(),empty_binding)
    api._realm()
    if api.manifest_sha!=value['manifest_sha']:raise Denied('ADMIN_MANIFEST_PIN_CHANGED')
    center.community_admin_authority=api;center.community_admin_workspace_bindings={}
    return api
