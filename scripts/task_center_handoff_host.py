"""Default-off handoff host seam; host-injected authentication is mandatory.

Not a production identity provider. A trusted host adapter must validate the
session and current role/permission, including revocation, on every call.
"""
import hashlib, json, math, re, sqlite3, time
from task_supervisor import canonical, Supervisor

ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,100}$')
ACTIONS={'PROPOSE':None,'RECEIVE':'PROPOSE','SUPERVISE':'RECEIVE'}
REQUIRED_CONTEXT=frozenset(('ORIGIN_SCOPE','SOURCE','DIRTY_SCOPE','INSTALLED_VERSION','AUTH_ENTRY','PERMISSION_SCOPE',
                           'INSTALL_ENTRY','CREDENTIAL_REFERENCE','CREDENTIAL_RECOVERY','CONFIG_REFERENCE','RESTORE',
                           'ACCEPTANCE','EFFECTS','WRITER_CUSTODY'))

class FormalHandoffIdentityProvider(object):
    """Host session provenance seam; no concrete production provider ships here."""
    def is_formal_session(self, session):
        return False

class HostAuthAdapter(object):
    def authenticate_and_authorize(self, session, action, binding):
        """Verify current host auth and exact task/attempt/handoff/version binding.

        Return non-secret identity references, never session tokens or secrets.
        Base class rejects all; only trusted host code may install an adapter.
        """
        return None

    def assess_backup(self, binding):
        """Host verifies recoverability from the same backup cycle/manifest.

        Return {'state':'COMPLETE'|'INCOMPLETE'|'UNKNOWN','missing':[codes],
        'cycle_at': trusted timestamp or None}.
        COMPLETE requires actual scoped source, execution context, legitimate
        permission/reacquisition and protected credential recovery, not mere
        selector presence. Do not copy/revive tokens, leases or approvals.
        Unknown provenance, scope, effects or recovery capability is not
        complete. Base class never asserts backup completeness.
        """
        return None

    def assess_provider(self, binding):
        """Resolve an existing admitted MCP provider binding; default disconnected."""
        return None

class HandoffHost(object):
    def __init__(self, db, tenant_id, issuer, adapter, clock=time.time, mcp_config=None):
        from task_center_mcp_dispatch_host import validate_config
        if not isinstance(adapter,HostAuthAdapter) or type(adapter) is HostAuthAdapter:
            raise ValueError('HOST_AUTH_ADAPTER_REQUIRED')
        if not isinstance(issuer,str) or not ID.fullmatch(issuer) or issuer.upper().startswith('TEST'):
            raise ValueError('NON_TEST_HOST_ISSUER_REQUIRED')
        self.db=db;self.tenant_id=tenant_id;self.issuer=issuer;self.adapter=adapter;self.clock=clock
        self.mcp_config=validate_config(mcp_config)

    def _mcp_registered(self, binding):
        if not self.mcp_config['enabled']:return False
        row=self.db.execute('SELECT project_id FROM gateway_task_metadata WHERE task_id=? AND tenant_id=?',(binding['task_id'],self.tenant_id)).fetchone()
        if row is None:return False
        try:
            assigned=self.db.execute('''SELECT role_id,role_version,principal_id,provider_id,model_id,state
              FROM model_assignments WHERE tenant_id=? AND task_id=? AND attempt_id=? AND provider_id=?''',
              (self.tenant_id,binding['task_id'],binding['attempt_id'],binding['provider_ref'])).fetchall()
        except sqlite3.Error:return False
        for host in self.mcp_config['bindings']:
            if host['tenant_id']!=self.tenant_id or host['project_id']!=row['project_id']:continue
            for assigned_role in assigned:
                role=host['roles'].get(assigned_role['role_id'])
                if (role and assigned_role['state']=='ASSIGNED' and all(role[k]==assigned_role[k]
                    for k in ('role_version','principal_id','provider_id','model_id'))):return True
        return False

    def record(self, session, value):
        required={'task_id','attempt_id','handoff_id','handoff_version','event_id','action','causation','snapshot_digest','backup_cycle_id','backup_manifest_sha256','checked','provider_ref'}
        if not isinstance(value,dict) or set(value)!=required:raise ValueError('EXACT_HANDOFF_REQUEST_REQUIRED')
        ids=required-{'handoff_version','snapshot_digest','backup_manifest_sha256','checked'}
        if any(not isinstance(value[k],str) or not ID.fullmatch(value[k]) for k in ids):raise ValueError('HANDOFF_REFERENCE_REQUIRED')
        if (type(value['handoff_version']) is not int or value['handoff_version']<1 or value['action'] not in ACTIONS or
            any(not isinstance(value[k],str) or not re.fullmatch(r'[0-9a-f]{64}',value[k]) for k in ('snapshot_digest','backup_manifest_sha256')) or
            not isinstance(value['checked'],list) or any(not isinstance(x,str) or x not in REQUIRED_CONTEXT for x in value['checked']) or
            value['checked']!=sorted(set(value['checked']))):
            raise ValueError('HANDOFF_BINDING_REQUIRED')
        db=self.db;db.execute('BEGIN IMMEDIATE')
        try:
            now=self.clock()
            if type(now) not in (int,float) or not math.isfinite(now):raise ValueError('TRUSTED_TIME_REQUIRED')
            binding={k:value[k] for k in ('task_id','attempt_id','handoff_id','handoff_version','snapshot_digest','backup_cycle_id','backup_manifest_sha256','checked','provider_ref')}
            claims=self.adapter.authenticate_and_authorize(session,value['action'],binding)
            fields={'issuer','tenant_id','principal_id','session_id','role_id','expires_at','scope'}
            if not isinstance(claims,dict) or set(claims)!=fields:raise ValueError('AUTHENTICATED_HOST_CONTEXT_REQUIRED')
            if (any(not isinstance(claims[k],str) or not ID.fullmatch(claims[k]) for k in fields-{'expires_at'}) or
                claims['issuer']!=self.issuer or claims['tenant_id']!=self.tenant_id or
                claims['scope']!='handoff:'+value['action'] or type(claims['expires_at']) not in (int,float) or
                not math.isfinite(claims['expires_at']) or claims['expires_at']<=now):raise ValueError('HANDOFF_AUTHORITY_REJECTED')
            meta=db.execute('SELECT tenant_id FROM gateway_task_metadata WHERE task_id=?',(value['task_id'],)).fetchone()
            task=db.execute('SELECT attempt_id,authority_state,authority_valid_until,fence,epoch,resource_scope_json,resource_scope_digest,last_trusted_time FROM tasks WHERE task_id=?',(value['task_id'],)).fetchone()
            if meta is None or meta['tenant_id']!=self.tenant_id or task is None or task['attempt_id']!=value['attempt_id']:raise ValueError('TASK_TENANT_ATTEMPT_MISMATCH')
            if task['authority_state']!='VALID' or type(task['authority_valid_until']) not in (int,float) or not math.isfinite(task['authority_valid_until']) or task['authority_valid_until']<=now or task['fence'] is None or task['epoch'] is None or type(task['last_trusted_time']) not in (int,float) or not math.isfinite(task['last_trusted_time']) or task['last_trusted_time']>now:raise ValueError('CURRENT_FENCED_WRITER_REQUIRED')
            resources=json.loads(task['resource_scope_json'])
            claims_rows=db.execute('SELECT resource_key,attempt_id,fence,epoch,state FROM resource_claims WHERE task_id=? ORDER BY resource_key',(value['task_id'],)).fetchall()
            if (not isinstance(resources,list) or not resources or any(not isinstance(x,str) or not x for x in resources) or resources!=sorted(set(resources)) or
                hashlib.sha256(canonical(resources).encode('utf-8')).hexdigest()!=task['resource_scope_digest'] or
                [r['resource_key'] for r in claims_rows]!=resources or any(r['attempt_id']!=task['attempt_id'] or r['fence']!=task['fence'] or r['epoch']!=task['epoch'] or r['state']!='VALID' for r in claims_rows)):
                raise ValueError('WRITER_RESOURCE_SCOPE_INVALID')
            if db.execute("SELECT 1 FROM writer_operations WHERE task_id=? AND state IN ('PREPARED','DISPATCHING','UNKNOWN') LIMIT 1",(value['task_id'],)).fetchone():raise ValueError('UNKNOWN_EFFECTS_RECONCILIATION_REQUIRED')
            try:connected=self._mcp_registered(binding) and self.adapter.assess_provider(binding)=='CONNECTED'
            except Exception:connected=False
            if not connected:
                db.rollback();return {'state':'NOT_CONNECTED','event_id':value['event_id']}
            try:assessment=self.adapter.assess_backup(binding)
            except Exception:assessment=None
            if (not isinstance(assessment,dict) or set(assessment)!={'state','missing','cycle_at'} or
                assessment['state'] not in ('COMPLETE','INCOMPLETE','UNKNOWN') or
                not isinstance(assessment['missing'],list) or
                any(not isinstance(x,str) or x not in REQUIRED_CONTEXT for x in assessment['missing']) or
                len(set(assessment['missing']))!=len(assessment['missing']) or
                (assessment['state']=='COMPLETE' and assessment['missing']) or
                (assessment['state']=='INCOMPLETE' and not assessment['missing'])):
                assessment={'state':'UNKNOWN','missing':[],'cycle_at':None}
            if assessment['state']=='COMPLETE' and (type(assessment['cycle_at']) not in (int,float) or not math.isfinite(assessment['cycle_at']) or assessment['cycle_at']>now or now-assessment['cycle_at']>300):
                assessment={'state':'UNKNOWN','missing':[],'cycle_at':None}
            unchecked=REQUIRED_CONTEXT-set(value['checked'])
            if unchecked:
                assessment={'state':'INCOMPLETE','missing':sorted(set(assessment['missing'])|unchecked),'cycle_at':assessment['cycle_at']}
            if assessment['state']!='COMPLETE':
                alert_id='handoff-missing:'+value['event_id']
                alert={'action':'HANDOFF_CONTEXT_INCOMPLETE','tenant_id':self.tenant_id,
                       'task_id':value['task_id'],'attempt_id':value['attempt_id'],
                       'snapshot_digest':value['snapshot_digest'],'handoff_id':value['handoff_id'],
                       'checked':value['checked'],'provider_ref':value['provider_ref'],
                       'handoff_version':value['handoff_version'],'backup_cycle_id':value['backup_cycle_id'],
                       'backup_manifest_sha256':value['backup_manifest_sha256'],
                       'state':assessment['state'],'missing':sorted(assessment['missing'])}
                prior_alert=db.execute('SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(value['task_id'],value['attempt_id'],alert_id)).fetchone()
                if prior_alert is not None and prior_alert['payload_json']!=canonical(alert):raise ValueError('HANDOFF_ALERT_RECONCILIATION_REQUIRED')
                if prior_alert is None:
                    db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',(value['task_id'],value['attempt_id'],alert_id,'SUPERVISION_ACTION',now,'PHASE_EXECUTION','HANDOFF_CONTEXT_INCOMPLETE',canonical(alert)))
                    supervisor=Supervisor.__new__(Supervisor);supervisor.db=db
                    supervisor._enqueue(value['task_id'],value['attempt_id'],alert_id,alert,now)
                db.commit();return {'state':'HANDOFF_INCOMPLETE_ALERT_QUEUED','alert_delivery':'UNKNOWN','event_id':value['event_id']}
            key='handoff-host:'+value['event_id'];kind='AUTHENTICATED_HANDOFF_'+value['action']
            payload=dict(value,tenant_id=self.tenant_id,issuer=claims['issuer'],principal_id=claims['principal_id'],session_id=claims['session_id'],role_id=claims['role_id'],scope=claims['scope'],expires_at=claims['expires_at'],fence=task['fence'],epoch=task['epoch'],backup_cycle_at=assessment['cycle_at'],backup_state='COMPLETE')
            prior=db.execute('SELECT kind,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(value['task_id'],value['attempt_id'],key)).fetchone()
            if prior is not None:
                if prior['kind']!=kind or prior['payload_json']!=canonical(payload):raise ValueError('HANDOFF_EVENT_CONFLICT')
                db.rollback();return {'state':'ALREADY_RECORDED','event_id':value['event_id']}
            existing=db.execute("SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND kind=? LIMIT 2049",(value['task_id'],value['attempt_id'],kind)).fetchall()
            if len(existing)>2048:raise ValueError('HANDOFF_HISTORY_LIMIT')
            for row in existing:
                old=json.loads(row['payload_json'])
                if (old.get('tenant_id'),old.get('handoff_id'),old.get('handoff_version'))==(self.tenant_id,value['handoff_id'],value['handoff_version']):raise ValueError('HANDOFF_PHASE_ALREADY_RECORDED')
            parent_kind=ACTIONS[value['action']]
            if parent_kind is None:
                if value['causation']!='NONE':raise ValueError('PROPOSAL_CAUSATION_REQUIRED')
            else:
                parent=db.execute('SELECT kind,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(value['task_id'],value['attempt_id'],'handoff-host:'+value['causation'])).fetchone()
                if parent is None or parent['kind']!='AUTHENTICATED_HANDOFF_'+parent_kind:raise ValueError('HANDOFF_CAUSATION_MISSING')
                p=json.loads(parent['payload_json'])
                if any(p[k]!=payload[k] for k in ('tenant_id','task_id','attempt_id','handoff_id','handoff_version','snapshot_digest','backup_cycle_id','backup_manifest_sha256','backup_cycle_at','backup_state','checked','provider_ref','fence','epoch')):raise ValueError('HANDOFF_BINDING_MISMATCH')
                if any(p[k]==payload[k] for k in ('principal_id','session_id','role_id')):raise ValueError('INDEPENDENT_PARTY_REQUIRED')
                if value['action']=='SUPERVISE':
                    first=db.execute('SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(value['task_id'],value['attempt_id'],'handoff-host:'+p['causation'])).fetchone()
                    if first is None:raise ValueError('HANDOFF_CAUSATION_MISSING')
                    first=json.loads(first['payload_json'])
                    if any(first[k]==payload[k] for k in ('principal_id','session_id','role_id')):raise ValueError('INDEPENDENT_PARTY_REQUIRED')
            db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',(value['task_id'],value['attempt_id'],key,kind,now,'PHASE_EXECUTION','HOST_AUTHENTICATED',canonical(payload)))
            db.commit();return {'state':'RECORDED','event_id':value['event_id']}
        except Exception:
            db.rollback();raise

    def verify_recorded(self, tenant_id, task_id, attempt_id, event_id, expected):
        """Historical exact existence only; never a current permission grant."""
        if tenant_id!=self.tenant_id or not isinstance(expected,dict):return False
        row=self.db.execute('SELECT kind,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(task_id,attempt_id,'handoff-host:'+event_id)).fetchone()
        if row is None or not row['kind'].startswith('AUTHENTICATED_HANDOFF_'):return False
        try:payload=json.loads(row['payload_json'])
        except (TypeError,ValueError):return False
        return (payload==expected and payload.get('issuer')==self.issuer and
                payload.get('tenant_id')==tenant_id and payload.get('task_id')==task_id and
                payload.get('attempt_id')==attempt_id and payload.get('event_id')==event_id and
                row['kind']=='AUTHENTICATED_HANDOFF_'+str(payload.get('action')))

    def read_receipt(self, session, task_id, attempt_id, event_id):
        if any(not isinstance(x,str) or not ID.fullmatch(x) for x in (task_id,attempt_id,event_id)):
            raise ValueError('HANDOFF_REFERENCE_REQUIRED')
        now=self.clock()
        meta=self.db.execute('SELECT tenant_id FROM gateway_task_metadata WHERE task_id=?',(task_id,)).fetchone()
        if meta is None or meta['tenant_id']!=self.tenant_id:raise ValueError('TASK_TENANT_ATTEMPT_MISMATCH')
        row=self.db.execute('SELECT kind,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',(task_id,attempt_id,'handoff-host:'+event_id)).fetchone()
        alert=False
        if row is None:
            row=self.db.execute("SELECT kind,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=? AND kind='SUPERVISION_ACTION'",(task_id,attempt_id,'handoff-missing:'+event_id)).fetchone()
            alert=True
        if row is None:raise ValueError('RECEIPT_UNAVAILABLE')
        payload=json.loads(row['payload_json'])
        if alert:
            if (payload.get('action')!='HANDOFF_CONTEXT_INCOMPLETE' or payload.get('tenant_id')!=self.tenant_id or payload.get('task_id')!=task_id or payload.get('attempt_id')!=attempt_id):raise ValueError('RECEIPT_UNAVAILABLE')
        elif not self.verify_recorded(self.tenant_id,task_id,attempt_id,event_id,payload):raise ValueError('RECEIPT_UNAVAILABLE')
        binding={k:payload[k] for k in ('task_id','attempt_id','handoff_id','handoff_version','snapshot_digest','backup_cycle_id','backup_manifest_sha256','provider_ref')}
        binding['checked']=payload.get('checked',[])
        claims=self.adapter.authenticate_and_authorize(session,'READ',binding)
        fields={'issuer','tenant_id','principal_id','session_id','role_id','expires_at','scope'}
        if (not isinstance(claims,dict) or set(claims)!=fields or
            any(not isinstance(claims[k],str) or not ID.fullmatch(claims[k]) for k in fields-{'expires_at'}) or
            claims['issuer']!=self.issuer or claims['tenant_id']!=self.tenant_id or claims['scope']!='handoff:READ' or
            type(now) not in (int,float) or not math.isfinite(now) or type(claims['expires_at']) not in (int,float) or
            not math.isfinite(claims['expires_at']) or claims['expires_at']<=now):raise ValueError('HANDOFF_AUTHORITY_REJECTED')
        if alert:
            return {'state':'HANDOFF_INCOMPLETE_ALERT_QUEUED','alert_delivery':'UNKNOWN',
                    'task_id':task_id,'attempt_id':attempt_id,'event_id':event_id,
                    'handoff_id':payload['handoff_id'],'handoff_version':payload['handoff_version'],
                    'provider_ref':payload['provider_ref'],
                    'backup_cycle_id':payload['backup_cycle_id'],'backup_manifest_sha256':payload['backup_manifest_sha256'],
                    'missing':payload['missing'],'backup_state':payload['state']}
        return {'state':'HISTORICAL_RECORDED','task_id':task_id,'attempt_id':attempt_id,'event_id':event_id,
                'handoff_id':payload['handoff_id'],'handoff_version':payload['handoff_version'],
                'action':payload['action'],'snapshot_digest':payload['snapshot_digest'],
                'backup_cycle_id':payload['backup_cycle_id'],'backup_manifest_sha256':payload['backup_manifest_sha256'],
                'backup_cycle_at':payload['backup_cycle_at'],'backup_state':payload['backup_state'],
                'provider_ref':payload['provider_ref'],
                'checked':payload['checked'],
                'current_authority':'UNKNOWN'}
