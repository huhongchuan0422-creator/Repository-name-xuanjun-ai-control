"""Server-side TEST_ONLY action admission on the canonical task ledger.

This is an adapter around the existing Gateway/Supervisor authority.  It does
not execute external actions, create a second task state, or turn historical
capability evidence into current authorization.
"""
from __future__ import print_function

import hashlib
import json
import math
import time

from reusable_task_gateway import _text
from task_supervisor import UNKNOWN, canonical

ACTION_SCOPE_MAP={'READ_SOURCE':'READ_SOURCE','WRITE_SOURCE':'WRITE_SOURCE',
                  'DEPLOY':'DEPLOY','RUN_TEST':'RUN_TEST','PUBLISH':'PUBLISH'}


class ExecutionPolicyGateway(object):
    def __init__(self,gateway,context,clock=None):
        self.gateway=gateway;self.db=gateway.db;self.context=context
        self.tenant_id=gateway.tenants.verify(context);self.clock=clock or time.time
        self._schema()

    def _schema(self):
        statements=(
          '''CREATE TABLE IF NOT EXISTS execution_units(
            tenant_id TEXT NOT NULL,task_id TEXT NOT NULL,delivery_stage TEXT NOT NULL,
            feature_unit TEXT NOT NULL,goal TEXT NOT NULL,scope_json TEXT NOT NULL,
            acceptance_json TEXT NOT NULL,dependency_json TEXT NOT NULL,
            asset_version TEXT NOT NULL,responsible_party TEXT NOT NULL,
            created_at REAL NOT NULL,PRIMARY KEY(tenant_id,task_id))''',
          '''CREATE TABLE IF NOT EXISTS asset_preflight_checks(
            tenant_id TEXT NOT NULL,task_id TEXT NOT NULL,check_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,writer_principal TEXT NOT NULL,
            checked_json TEXT NOT NULL,outcome TEXT NOT NULL,reused_asset TEXT,
            reused_version TEXT,need_new INTEGER NOT NULL,reason TEXT NOT NULL,
            evidence_ref TEXT NOT NULL,observed_at REAL NOT NULL,
            PRIMARY KEY(tenant_id,task_id,check_id))''',
          '''CREATE TABLE IF NOT EXISTS action_authorizations(
            tenant_id TEXT NOT NULL,authorization_id TEXT NOT NULL,
            task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,
            asset_version TEXT NOT NULL,writer_principal TEXT NOT NULL,
            source_kind TEXT NOT NULL,scopes_json TEXT NOT NULL,
            read_only INTEGER NOT NULL,valid_from REAL NOT NULL,
            valid_until REAL NOT NULL,evidence_ref TEXT NOT NULL,
            PRIMARY KEY(tenant_id,authorization_id))''',
          '''CREATE TABLE IF NOT EXISTS scope_changes(
            tenant_id TEXT NOT NULL,change_id TEXT NOT NULL,task_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,writer_principal TEXT NOT NULL,
            base_asset_version TEXT NOT NULL,new_scope_json TEXT NOT NULL,
            reason TEXT NOT NULL,state TEXT NOT NULL,reviewed_by TEXT,
            evidence_ref TEXT,created_at REAL NOT NULL,updated_at REAL NOT NULL,
            PRIMARY KEY(tenant_id,change_id))''',
          '''CREATE TABLE IF NOT EXISTS execution_action_requests(
            tenant_id TEXT NOT NULL,request_id TEXT NOT NULL,idempotency_key TEXT NOT NULL,
            task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,asset_version TEXT NOT NULL,
            action TEXT NOT NULL,scope TEXT NOT NULL,authorization_id TEXT NOT NULL,
            writer_principal TEXT NOT NULL,change_id TEXT,state TEXT NOT NULL,
            evidence_json TEXT NOT NULL,created_at REAL NOT NULL,
            PRIMARY KEY(tenant_id,request_id),UNIQUE(tenant_id,idempotency_key))''',
          '''CREATE TABLE IF NOT EXISTS asset_query_receipts(
            tenant_id TEXT NOT NULL,query_id TEXT NOT NULL,task_id TEXT NOT NULL,
            source_kind TEXT NOT NULL,source_version TEXT NOT NULL,
            query_json TEXT NOT NULL,result_digest TEXT NOT NULL,
            observed_at REAL NOT NULL,PRIMARY KEY(tenant_id,query_id))''',
          '''CREATE TABLE IF NOT EXISTS formal_approval_roles(
            tenant_id TEXT NOT NULL,task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,approval_kind TEXT NOT NULL,
            valid_until REAL NOT NULL,granted_by TEXT NOT NULL,
            PRIMARY KEY(tenant_id,task_id,attempt_id,principal_id,approval_kind))''')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            for statement in statements:self.db.execute(statement)
            columns={row['name'] for row in self.db.execute(
              'PRAGMA table_info(action_authorizations)')}
            for name in ('task_id','attempt_id','asset_version','writer_principal'):
                if name not in columns:
                    self.db.execute('ALTER TABLE action_authorizations ADD COLUMN %s TEXT'%name)
            for table in ('asset_preflight_checks','scope_changes'):
                columns={row['name'] for row in self.db.execute(
                  'PRAGMA table_info(%s)'%table)}
                for name in ('attempt_id','writer_principal'):
                    if name not in columns:
                        self.db.execute('ALTER TABLE %s ADD COLUMN %s TEXT'%(table,name))

    def record_asset_query(self,task_id,query_id,source_kind,source_version,
                           query,result_digest,now=None):
        self.gateway.assert_task_context(self.context,task_id)
        if source_kind not in ('REGISTRY','GIT','ARTIFACT_STORE','CANONICAL_DB'):
            raise ValueError('TRUSTED_ASSET_QUERY_SOURCE_REQUIRED')
        if not isinstance(query,dict) or not query:raise ValueError('ASSET_QUERY_REQUIRED')
        if len(result_digest)!=64:raise ValueError('RESULT_DIGEST_REQUIRED')
        now=self.clock() if now is None else now
        self.db.execute('''INSERT INTO asset_query_receipts VALUES
          (?,?,?,?,?,?,?,?)''',(self.tenant_id,query_id,task_id,source_kind,
          source_version,canonical(query),result_digest,now));self.db.commit()
        return {'query_id':query_id,'result_digest':result_digest}

    def grant_approval_role(self,task_id,principal_id,approval_kind,valid_until):
        admin=self.context['principal_id']
        if not admin.startswith('admin:'):raise ValueError('POLICY_ADMIN_REQUIRED')
        task=self.gateway.supervisor._task(task_id);now=self.clock()
        if valid_until<=now:raise ValueError('APPROVAL_ROLE_WINDOW_REQUIRED')
        self.db.execute('''INSERT OR REPLACE INTO formal_approval_roles VALUES
          (?,?,?,?,?,?,?)''',(self.tenant_id,task_id,task['attempt_id'],
          principal_id,approval_kind,valid_until,admin));self.db.commit()
        return {'task_id':task_id,'principal_id':principal_id,
                'approval_kind':approval_kind}

    @staticmethod
    def validate_unit_input(value):
        required={'task_id','delivery_stage','feature_unit','goal','scope',
          'acceptance','dependencies','asset_version','responsible_party'}
        if not isinstance(value,dict) or set(value)!=required:
            raise ValueError('EXACT_EXECUTION_UNIT_REQUIRED')
        for key in ('delivery_stage','feature_unit','goal','asset_version',
                    'responsible_party'):_text(value[key],key)
        for key in ('scope','acceptance','dependencies'):
            if not isinstance(value[key],list) or not value[key]:
                raise ValueError('NONEMPTY_%s_REQUIRED'%key.upper())
        return value

    def record_unit(self,value,now=None):
        self.validate_unit_input(value)
        self.gateway.assert_task_context(self.context,value['task_id'])
        task=self.gateway.supervisor._task(value['task_id'])
        if task['owner']!=value['responsible_party']:
            raise ValueError('UNIQUE_RESPONSIBLE_PARTY_MISMATCH')
        now=self.clock() if now is None else now
        self.db.execute('''INSERT INTO execution_units VALUES
          (?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,value['task_id'],
          value['delivery_stage'],value['feature_unit'],value['goal'],
          canonical(value['scope']),canonical(value['acceptance']),
          canonical(value['dependencies']),value['asset_version'],
          value['responsible_party'],now));self.db.commit()
        return {'task_id':value['task_id'],'state':'UNIT_RECORDED'}

    def record_preflight(self,task_id,checked,outcome,reused_asset,
                         reused_version,need_new,reason,evidence_ref,now=None,
                         query_ids=None):
        self.gateway.assert_task_context(self.context,task_id)
        if not isinstance(checked,list) or not checked:raise ValueError('CHECKED_ASSETS_REQUIRED')
        if outcome not in ('FOUND','NOT_FOUND',UNKNOWN):raise ValueError('PREFLIGHT_OUTCOME_REQUIRED')
        if outcome==UNKNOWN and need_new:raise ValueError('UNKNOWN_CANNOT_AUTHORIZE_NEW_ASSET')
        if outcome=='FOUND' and (not reused_asset or not reused_version):
            raise ValueError('REUSED_ASSET_VERSION_REQUIRED')
        query_ids=list(query_ids or [])
        if query_ids:
            found=self.db.execute('''SELECT COUNT(*) FROM asset_query_receipts
              WHERE tenant_id=? AND task_id=? AND query_id IN (%s)'''%(','.join(
              ['?']*len(query_ids))),(self.tenant_id,task_id)+tuple(query_ids)).fetchone()[0]
            if found!=len(set(query_ids)):raise ValueError('ASSET_QUERY_RECEIPT_REQUIRED')
        now=self.clock() if now is None else now
        task=self.gateway.supervisor._task(task_id)
        if task['attempt_id'] in (None,UNKNOWN) or task['authority_state']!='VALID':
            raise ValueError('CURRENT_WRITER_AUTHORITY_REQUIRED')
        body={'checked':checked,'outcome':outcome,'reused_asset':reused_asset,
          'reused_version':reused_version,'need_new':bool(need_new),
          'reason':_text(reason,'reason'),'evidence_ref':_text(evidence_ref,'evidence_ref'),
          'attempt_id':task['attempt_id'],'writer_principal':task['authority_caller_id'],
          'query_ids':sorted(query_ids)}
        check_id=hashlib.sha256(canonical(body).encode()).hexdigest()
        self.db.execute('''INSERT OR IGNORE INTO asset_preflight_checks(
          tenant_id,task_id,check_id,attempt_id,writer_principal,checked_json,
          outcome,reused_asset,reused_version,need_new,reason,evidence_ref,
          observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
          self.tenant_id,task_id,check_id,task['attempt_id'],
          task['authority_caller_id'],
          canonical(checked),outcome,reused_asset,reused_version,int(bool(need_new)),
          reason,evidence_ref,now));self.db.commit()
        return {'check_id':check_id,'outcome':outcome}

    def add_authorization(self,authorization_id,task_id,asset_version,
                          writer_principal,source_kind,scopes,read_only,
                          valid_from,valid_until,evidence_ref):
        principal=self.context['principal_id']
        if not principal.startswith('admin:'):raise ValueError('POLICY_ADMIN_REQUIRED')
        self.gateway.assert_task_context(self.context,task_id)
        task=self.gateway.supervisor._task(task_id)
        if (task['attempt_id'] in (None,UNKNOWN) or
                task['authority_state']!='VALID' or
                task['authority_caller_id']!=writer_principal):
            raise ValueError('CURRENT_WRITER_AUTHORITY_REQUIRED')
        unit=self.db.execute('''SELECT asset_version FROM execution_units WHERE
          tenant_id=? AND task_id=?''',(self.tenant_id,task_id)).fetchone()
        if unit is None or unit['asset_version']!=asset_version:
            raise ValueError('ASSET_VERSION_MISMATCH')
        if source_kind not in ('CURRENT_TEST_ONLY','HISTORICAL'):
            raise ValueError('AUTHORIZATION_SOURCE_REQUIRED')
        if not isinstance(scopes,list) or not scopes:raise ValueError('AUTHORIZATION_SCOPES_REQUIRED')
        if not all(isinstance(x,str) and x for x in scopes):raise ValueError('AUTHORIZATION_SCOPES_REQUIRED')
        if not all(type(x) in (int,float) and math.isfinite(x) for x in
                   (valid_from,valid_until)) or valid_until<=valid_from:
            raise ValueError('AUTHORIZATION_WINDOW_REQUIRED')
        self.db.execute('''INSERT INTO action_authorizations(
          tenant_id,authorization_id,task_id,attempt_id,asset_version,
          writer_principal,source_kind,scopes_json,read_only,valid_from,
          valid_until,evidence_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',(
          self.tenant_id,
          _text(authorization_id,'authorization_id'),task_id,
          task['attempt_id'],asset_version,writer_principal,source_kind,
          canonical(scopes),int(bool(read_only)),valid_from,valid_until,
          _text(evidence_ref,'evidence_ref')));self.db.commit()
        return {'authorization_id':authorization_id,'source_kind':source_kind}

    def propose_change(self,change_id,task_id,base_asset_version,new_scope,
                       reason,now=None):
        self.gateway.assert_task_context(self.context,task_id)
        if not isinstance(new_scope,list) or not new_scope:raise ValueError('NEW_SCOPE_REQUIRED')
        now=self.clock() if now is None else now
        task=self.gateway.supervisor._task(task_id)
        if task['attempt_id'] in (None,UNKNOWN) or task['authority_state']!='VALID':
            raise ValueError('CURRENT_WRITER_AUTHORITY_REQUIRED')
        self.db.execute('''INSERT INTO scope_changes(
          tenant_id,change_id,task_id,attempt_id,writer_principal,
          base_asset_version,new_scope_json,reason,state,reviewed_by,
          evidence_ref,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
          self.tenant_id,change_id,task_id,task['attempt_id'],
          task['authority_caller_id'],
          base_asset_version,canonical(new_scope),_text(reason,'reason'),
          'PENDING',None,None,now,now));self.db.commit()
        return {'change_id':change_id,'state':'PENDING'}

    def review_change(self,change_id,reviewer,approved,evidence_ref,now=None):
        now=self.clock() if now is None else now
        principal=self.context['principal_id']
        if reviewer!=principal:
            raise ValueError('AUTHENTICATED_CHANGE_REVIEWER_REQUIRED')
        row=self.db.execute('''SELECT c.*,t.authority_caller_id FROM
          scope_changes c JOIN tasks t ON t.task_id=c.task_id WHERE
          c.tenant_id=? AND c.change_id=?''',(self.tenant_id,change_id)).fetchone()
        if row is None:raise KeyError(change_id)
        if reviewer==row['authority_caller_id']:
            raise ValueError('INDEPENDENT_CHANGE_REVIEW_REQUIRED')
        formal=self.db.execute('''SELECT 1 FROM formal_approval_roles WHERE
          tenant_id=? AND task_id=? AND attempt_id=? AND principal_id=? AND
          approval_kind='SCOPE_CHANGE' AND valid_until>?''',(self.tenant_id,
          row['task_id'],row['attempt_id'],reviewer,now)).fetchone()
        if formal is None:raise ValueError('FORMAL_APPROVAL_ROLE_REQUIRED')
        model_tables=self.db.execute('''SELECT COUNT(*) FROM sqlite_master
          WHERE type='table' AND name IN ('model_assignments','role_templates')''').fetchone()[0]
        executor_role=None
        if model_tables==2:
            executor_role=self.db.execute('''SELECT 1 FROM model_assignments a JOIN
              role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id
              AND r.version=a.role_version WHERE a.tenant_id=? AND a.task_id=? AND
              a.attempt_id=? AND a.principal_id=? AND r.phase='EXECUTOR' LIMIT 1''',(
              self.tenant_id,row['task_id'],row['attempt_id'],reviewer)).fetchone()
        if executor_role is not None:
            raise ValueError('INDEPENDENT_CHANGE_REVIEW_REQUIRED')
        state='APPROVED' if approved else 'REJECTED'
        changed=self.db.execute('''UPDATE scope_changes SET state=?,reviewed_by=?,
          evidence_ref=?,updated_at=? WHERE tenant_id=? AND change_id=? AND
          state='PENDING' ''',(state,reviewer,evidence_ref,now,self.tenant_id,
          change_id)).rowcount;self.db.commit()
        if changed!=1:raise ValueError('PENDING_CHANGE_REQUIRED')
        return {'change_id':change_id,'state':state}

    def request_action(self,value,now=None):
        now=self.clock() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result=self._request_action_locked(value,now)
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def _request_action_locked(self,value,now):
        required={'task_id','asset_version','action','scope','authorization_id',
          'writer_principal','idempotency_key','change_id'}
        if not isinstance(value,dict) or set(value)!=required:
            raise ValueError('EXACT_ACTION_REQUEST_REQUIRED')
        self.gateway.assert_task_context(self.context,value['task_id'])
        task=self.gateway.supervisor._task(value['task_id'])
        unit=self.db.execute('''SELECT * FROM execution_units WHERE tenant_id=?
          AND task_id=?''',(self.tenant_id,value['task_id'])).fetchone()
        if unit is None:raise ValueError('EXECUTION_UNIT_REQUIRED')
        if value['asset_version']!=unit['asset_version']:
            raise ValueError('ASSET_VERSION_MISMATCH')
        if task['attempt_id'] in (None,UNKNOWN) or task['authority_state']!='VALID':
            raise ValueError('CURRENT_WRITER_AUTHORITY_REQUIRED')
        if task['authority_valid_until'] is None or not now<task['authority_valid_until']:
            raise ValueError('CURRENT_WRITER_AUTHORITY_EXPIRED')
        if value['writer_principal']!=task['authority_caller_id']:
            raise ValueError('UNIQUE_WRITER_REQUIRED')
        preflight=self.db.execute('''SELECT * FROM asset_preflight_checks WHERE
          tenant_id=? AND task_id=? ORDER BY observed_at DESC,check_id DESC LIMIT 1''',
          (self.tenant_id,value['task_id'])).fetchone()
        if preflight is None:raise ValueError('ASSET_PREFLIGHT_REQUIRED')
        if (preflight['attempt_id']!=task['attempt_id'] or
                preflight['writer_principal']!=task['authority_caller_id']):
            raise ValueError('PREFLIGHT_ATTEMPT_BINDING_MISMATCH')
        if preflight['outcome']==UNKNOWN:raise ValueError('UNKNOWN_ASSET_STATE_HOLD')
        if (preflight['outcome']=='FOUND' and
                preflight['reused_version']!=unit['asset_version']):
            raise ValueError('PREFLIGHT_ASSET_VERSION_MISMATCH')
        allowed=set(json.loads(unit['scope_json']))
        if value['scope'] not in allowed:
            change=self.db.execute('''SELECT * FROM scope_changes WHERE tenant_id=?
              AND change_id=? AND task_id=? AND state='APPROVED' ''',
              (self.tenant_id,value['change_id'],value['task_id'])).fetchone()
            if change is None or value['scope'] not in json.loads(change['new_scope_json']):
                raise ValueError('UNAPPROVED_SCOPE_EXPANSION')
            if (change['attempt_id']!=task['attempt_id'] or
                    change['writer_principal']!=task['authority_caller_id']):
                raise ValueError('CHANGE_ATTEMPT_BINDING_MISMATCH')
            model_tables=self.db.execute('''SELECT COUNT(*) FROM sqlite_master
              WHERE type='table' AND name IN ('model_assignments',
              'role_templates')''').fetchone()[0]
            if model_tables==2 and self.db.execute('''SELECT 1 FROM
              model_assignments a JOIN role_templates r ON
              r.tenant_id=a.tenant_id AND r.role_id=a.role_id AND
              r.version=a.role_version WHERE a.tenant_id=? AND a.task_id=?
              AND a.attempt_id=? AND a.principal_id=? AND r.phase='EXECUTOR'
              LIMIT 1''',(self.tenant_id,value['task_id'],task['attempt_id'],
              change['reviewed_by'])).fetchone() is not None:
                raise ValueError('CHANGE_REVIEWER_ROLE_CONFLICT')
            if change['base_asset_version']!=unit['asset_version']:
                raise ValueError('CHANGE_BASE_ASSET_VERSION_MISMATCH')
        auth=self.db.execute('''SELECT * FROM action_authorizations WHERE
          tenant_id=? AND authorization_id=?''',(self.tenant_id,
          value['authorization_id'])).fetchone()
        if auth is None or auth['source_kind']!='CURRENT_TEST_ONLY' or auth['read_only']:
            raise ValueError('CURRENT_WRITE_AUTHORIZATION_REQUIRED')
        if (auth['task_id']!=value['task_id'] or
                auth['attempt_id']!=task['attempt_id'] or
                auth['asset_version']!=unit['asset_version'] or
                auth['writer_principal']!=value['writer_principal']):
            raise ValueError('AUTHORIZATION_BINDING_MISMATCH')
        if not (auth['valid_from']<=now<auth['valid_until']):
            raise ValueError('CURRENT_AUTHORIZATION_EXPIRED')
        if ACTION_SCOPE_MAP.get(value['action'])!=value['scope']:
            raise ValueError('ACTION_SCOPE_MISMATCH')
        if value['action'] not in json.loads(auth['scopes_json']):
            raise ValueError('ACTION_OUTSIDE_AUTHORIZATION')
        request_id=hashlib.sha256(canonical({'tenant':self.tenant_id,
          'idempotency':value['idempotency_key']}).encode()).hexdigest()
        prior=self.db.execute('''SELECT * FROM execution_action_requests WHERE
          tenant_id=? AND idempotency_key=?''',(self.tenant_id,
          value['idempotency_key'])).fetchone()
        evidence={'task_state':task['state'],'attempt_id':task['attempt_id'],
          'asset_preflight':preflight['check_id'],'authorization':
          value['authorization_id'],'external_execution':'NOT_EXECUTED'}
        if prior:
            expected=(value['task_id'],task['attempt_id'],value['asset_version'],
                      value['action'],value['scope'],value['authorization_id'],
                      value['writer_principal'],value['change_id'],
                      preflight['check_id'])
            actual=(prior['task_id'],prior['attempt_id'],prior['asset_version'],
                    prior['action'],prior['scope'],prior['authorization_id'],
                    prior['writer_principal'],prior['change_id'],
                    json.loads(prior['evidence_json'])['asset_preflight'])
            if actual!=expected:raise ValueError('IDEMPOTENCY_CONFLICT')
            return {'request_id':prior['request_id'],'state':prior['state'],
                    'duplicate':True}
        self.db.execute('''INSERT INTO execution_action_requests VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,request_id,
          value['idempotency_key'],value['task_id'],task['attempt_id'],
          value['asset_version'],value['action'],value['scope'],
          value['authorization_id'],value['writer_principal'],value['change_id'],
          'ADMITTED_TEST_ONLY',canonical(evidence),now))
        return {'request_id':request_id,'state':'ADMITTED_TEST_ONLY',
                'duplicate':False,'external_execution':'NOT_EXECUTED'}

    def projection(self):
        return {'units':[dict(x) for x in self.db.execute('''SELECT * FROM
          execution_units WHERE tenant_id=? ORDER BY task_id''',(self.tenant_id,))],
          'preflights':[dict(x) for x in self.db.execute('''SELECT * FROM
          asset_preflight_checks WHERE tenant_id=? ORDER BY observed_at,check_id''',
          (self.tenant_id,))],
          'actions':[dict(x) for x in self.db.execute('''SELECT * FROM
          execution_action_requests WHERE tenant_id=? ORDER BY created_at,
          request_id''',(self.tenant_id,))],
          'mode':'TEST_ONLY','external_execution':'NOT_IMPLEMENTED'}
