"""Concrete handoff backend over existing canonical sessions/roles/approvals.

Read-only: never registers identities, issues grants, creates tables or changes
FORMAL profile. Login provenance remains the host's existing formal verifier.
Action rights come only from explicit existing formal_approval_roles records,
not role labels, a developer owner grant or an inferred phase mapping.
"""
import copy,json,math,os,sqlite3,time
from task_center_handoff_host import FormalHandoffIdentityProvider,ACTIONS,ID
from task_center_session_auth import SessionStore,FileTestIdentityProvider


class CanonicalHandoffBackend:
    def __init__(self,sessions,identity_provider,issuer,db,clock=time.time):
        if not isinstance(sessions,SessionStore):raise ValueError('CANONICAL_SESSION_STORE_REQUIRED')
        if (not isinstance(identity_provider,FormalHandoffIdentityProvider)
                or isinstance(identity_provider,FileTestIdentityProvider)
                or not callable(getattr(identity_provider,'verify',None))):
            raise ValueError('EXISTING_FORMAL_IDENTITY_VERIFIER_REQUIRED')
        if not isinstance(issuer,str) or not ID.fullmatch(issuer) or issuer.upper().startswith('TEST'):
            raise ValueError('NON_TEST_HOST_ISSUER_REQUIRED')
        if not isinstance(db,sqlite3.Connection):raise ValueError('CANONICAL_DATABASE_REQUIRED')
        paths=[r[2] for r in db.execute('PRAGMA database_list') if r[1]=='main']
        if len(paths)!=1 or not paths[0]:raise ValueError('PERSISTENT_CANONICAL_DATABASE_REQUIRED')
        self.db_path=os.path.realpath(paths[0])
        self.sessions=sessions;self.identity_provider=identity_provider;self.issuer=issuer;self.clock=clock

    def verify(self,username,password):
        # Original login path; no password/token/key is stored or logged here.
        try:
            db=self._read();db.close()
        except (sqlite3.Error,ValueError,TypeError):return None
        return self.identity_provider.verify(username,password)

    def _read(self):
        db=self.sessions.connection_factory();db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON')
            paths=[r[2] for r in db.execute('PRAGMA database_list') if r[1]=='main']
            if len(paths)!=1 or os.path.realpath(paths[0])!=self.db_path:
                raise ValueError('CANONICAL_SESSION_DATABASE_MISMATCH')
            db.execute('BEGIN')
            profile=db.execute('SELECT profile FROM authority_runtime_profile WHERE singleton=1').fetchone()
            if profile is None or profile[0]!='FORMAL':raise ValueError('FORMAL_LEDGER_PROFILE_REQUIRED')
            return db
        except Exception:db.close();raise

    def _session(self,db,session,now):
        if (not isinstance(session,dict) or session.get('tenant_id')!=self.sessions.tenant_id
                or not isinstance(session.get('session_hash'),str)):
            return None
        row=db.execute('''SELECT principal_id,roles_json,csrf_hash,expires_at,revoked_at
          FROM task_center_sessions WHERE tenant_id=? AND session_hash=?''',
          (self.sessions.tenant_id,session['session_hash'])).fetchone()
        if (row is None or row['revoked_at'] is not None or row['principal_id']!=session.get('principal_id')
                or type(row['expires_at']) not in (int,float) or not math.isfinite(row['expires_at']) or row['expires_at']<=now
                or type(session.get('expires_at')) not in (int,float) or not math.isfinite(session['expires_at'])
                or session['expires_at']<=now or session['expires_at']>row['expires_at']):return None
        live=dict(tenant_id=self.sessions.tenant_id,principal_id=row['principal_id'],roles=json.loads(row['roles_json']),
            session_hash=session['session_hash'],csrf_hash=row['csrf_hash'],expires_at=row['expires_at'])
        if self.identity_provider.is_formal_session(live) is not True:return None
        # Existing opaque session reference; no new identity or token issuance.
        return dict(tenant_id=live['tenant_id'],principal_id=live['principal_id'],session_hash=live['session_hash'],
            session_id=live['session_hash'],expires_at=min(session['expires_at'],live['expires_at']))

    def current_session(self,session):
        db=None
        try:
            now=self.clock()
            if type(now) not in (int,float) or not math.isfinite(now):return None
            db=self._read();return self._session(db,session,now)
        except (sqlite3.Error,ValueError,TypeError,KeyError):return None
        finally:
            if db is not None:db.close()

    def authorize(self,current,action,binding):
        if (action not in set(ACTIONS)|{'ISSUE','READ'} or not isinstance(binding,dict)
                or any(not isinstance(binding.get(k),str) or not ID.fullmatch(binding[k]) for k in ('task_id','attempt_id'))
                or type(binding.get('handoff_version')) is not int or binding['handoff_version']<1):return None
        db=None
        try:
            now=self.clock()
            if type(now) not in (int,float) or not math.isfinite(now):return None
            db=self._read();session=self._session(db,current,now)
            if session is None or current.get('session_id')!=session['session_id']:return None
            tenant=self.sessions.tenant_id;task=binding['task_id'];attempt=binding['attempt_id'];principal=session['principal_id']
            row=db.execute('''SELECT t.attempt_id FROM tasks t JOIN gateway_task_metadata m ON m.task_id=t.task_id
              WHERE t.task_id=? AND m.tenant_id=?''',(task,tenant)).fetchone()
            if row is None or row['attempt_id']!=attempt:return None
            roles=db.execute('''SELECT a.role_id FROM model_assignments a JOIN role_templates r
              ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND r.version=a.role_version
              WHERE a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND a.principal_id=?
                AND a.state='ASSIGNED' AND r.enabled=1''',(tenant,task,attempt,principal)).fetchall()
            if len(roles)!=1:return None
            scope='handoff:'+action
            grant=db.execute('''SELECT valid_until,granted_by FROM formal_approval_roles
              WHERE tenant_id=? AND task_id=? AND attempt_id=? AND principal_id=? AND approval_kind=?''',
              (tenant,task,attempt,principal,scope)).fetchone()
            if (grant is None or type(grant['valid_until']) not in (int,float)
                    or not math.isfinite(grant['valid_until']) or grant['valid_until']<=now
                    or not isinstance(grant['granted_by'],str) or not grant['granted_by'].startswith('admin:')):return None
            claims=dict(issuer=self.issuer,tenant_id=tenant,principal_id=principal,session_id=session['session_id'],
                role_id=roles[0]['role_id'],scope=scope,expires_at=min(session['expires_at'],grant['valid_until']))
            return dict(binding=copy.deepcopy(binding),claims=claims)
        except (sqlite3.Error,ValueError,TypeError,KeyError):return None
        finally:
            if db is not None:db.close()
