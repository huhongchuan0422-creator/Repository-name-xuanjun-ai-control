"""TEST_ONLY multi-provider model control on the canonical task ledger.

Provider/model/role/request rows are adapter metadata.  Task, attempt and
writer authority remain owned by the existing Supervisor.  No production
credentials or paid calls are admitted by this module.
"""
from __future__ import print_function

import hashlib
import json
import math
import sqlite3
import time
import urllib.error
import urllib.request

from cryptography.fernet import Fernet, InvalidToken

from reusable_task_gateway import _text
from task_supervisor import UNKNOWN, canonical


ADAPTERS = frozenset(('siliconflow', 'openai-compatible'))
PRICE_STATES = frozenset(('KNOWN_FREE', 'KNOWN_PAID', UNKNOWN))
PHASES = frozenset(('EXECUTOR', 'REVIEWER', 'ACCEPTOR'))
REQUEST_STATES = frozenset(('QUEUED', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED',
                            'FAILED', UNKNOWN, 'CANCELLED'))


def _number(value, name, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError('VALID_%s_REQUIRED' % name.upper())
    return value


def load_master_key(path):
    import os
    stat = os.stat(path)
    if stat.st_mode & 0o077:
        raise ValueError('MASTER_KEY_FILE_MODE_0600_REQUIRED')
    with open(path, 'rb') as stream:
        raw = stream.read().strip()
    try:
        Fernet(raw)
    except Exception:
        raise ValueError('VALID_FERNET_MASTER_KEY_REQUIRED')
    return raw


class ProviderError(Exception):
    def __init__(self, kind, detail, retryable=False):
        Exception.__init__(self, kind)
        self.kind = kind
        self.detail = detail
        self.retryable = retryable


class OpenAICompatibleAdapter(object):
    adapter_type = 'openai-compatible'

    def __init__(self, opener=None):
        self.opener = opener or urllib.request.urlopen

    def invoke(self, base_url, secret, model_id, messages, timeout):
        url = base_url.rstrip('/') + '/v1/chat/completions'
        body = canonical({'model': model_id, 'messages': messages,
                          'stream': False}).encode('utf-8')
        request = urllib.request.Request(url, data=body, method='POST',
            headers={'Authorization': 'Bearer ' + secret,
                     'Content-Type': 'application/json',
                     'Accept': 'application/json',
                     'User-Agent': 'Xuanjun-TEST-ONLY-Adapter'})
        try:
            response = self.opener(request, timeout=timeout)
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ProviderError('RESPONSE_TOO_LARGE', 'body limit')
            value = json.loads(raw.decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ProviderError('AUTH', 'HTTP_401')
            if exc.code == 429:
                raise ProviderError('RATE_LIMIT', 'HTTP_429', True)
            raise ProviderError('HTTP', 'HTTP_%d' % exc.code,
                                500 <= exc.code < 600)
        except (TimeoutError, socket_timeout()):
            raise ProviderError('TIMEOUT_UNKNOWN', 'timeout', False)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError('TRANSPORT', type(exc).__name__, True)
        try:
            content = value['choices'][0]['message']['content']
            usage = value.get('usage') or {}
            if not isinstance(content, str):
                raise TypeError()
            parsed_usage = {
                'input_tokens': int(usage.get('prompt_tokens', 0)),
                'output_tokens': int(usage.get('completion_tokens', 0)),
                'total_tokens': int(usage.get('total_tokens', 0)),
            }
            if min(parsed_usage.values()) < 0:
                raise TypeError()
        except Exception:
            raise ProviderError('PROTOCOL', 'INVALID_RESPONSE_SHAPE')
        return {'content': content, 'usage': parsed_usage,
                'provider_request_id': value.get('id', UNKNOWN)}


class SiliconFlowAdapter(OpenAICompatibleAdapter):
    adapter_type = 'siliconflow'


def socket_timeout():
    import socket
    return socket.timeout


class ModelControl(object):
    def __init__(self, gateway, context, master_key, clock=None):
        self.gateway = gateway
        self.db = gateway.db
        self.context = context
        self.tenant_id = gateway.tenants.verify(context)
        self.fernet = Fernet(master_key)
        self.clock = clock or time.time
        self._schema()

    def _schema(self):
        statements = (
            '''CREATE TABLE IF NOT EXISTS model_providers(
              tenant_id TEXT NOT NULL,provider_id TEXT NOT NULL,
              display_name TEXT NOT NULL,adapter_type TEXT NOT NULL,
              base_url TEXT NOT NULL,enabled INTEGER NOT NULL,
              price_state TEXT NOT NULL,rate_limit_per_min INTEGER NOT NULL,
              concurrency_limit INTEGER NOT NULL,timeout_seconds REAL NOT NULL,
              retry_limit INTEGER NOT NULL,secret_cipher BLOB,secret_mask TEXT,
              config_version INTEGER NOT NULL,circuit_state TEXT NOT NULL,
              failure_count INTEGER NOT NULL,next_probe_at REAL,
              created_at REAL NOT NULL,updated_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,provider_id))''',
            '''CREATE TABLE IF NOT EXISTS model_catalog(
              tenant_id TEXT NOT NULL,provider_id TEXT NOT NULL,
              model_id TEXT NOT NULL,capabilities_json TEXT NOT NULL,
              enabled INTEGER NOT NULL,price_state TEXT NOT NULL,
              input_unit_cost REAL,output_unit_cost REAL,
              PRIMARY KEY(tenant_id,provider_id,model_id),
              FOREIGN KEY(tenant_id,provider_id) REFERENCES
              model_providers(tenant_id,provider_id))''',
            '''CREATE TABLE IF NOT EXISTS role_templates(
              tenant_id TEXT NOT NULL,role_id TEXT NOT NULL,version TEXT NOT NULL,
              phase TEXT NOT NULL,capabilities_json TEXT NOT NULL,
              writer_allowed INTEGER NOT NULL,enabled INTEGER NOT NULL,
              PRIMARY KEY(tenant_id,role_id,version))''',
            '''CREATE TABLE IF NOT EXISTS role_skill_bindings(
              tenant_id TEXT NOT NULL,role_id TEXT NOT NULL,role_version TEXT NOT NULL,
              skill_id TEXT NOT NULL,skill_version TEXT NOT NULL,
              review_sha256 TEXT NOT NULL,status TEXT NOT NULL,
              PRIMARY KEY(tenant_id,role_id,role_version,skill_id))''',
            '''CREATE TABLE IF NOT EXISTS model_assignments(
              tenant_id TEXT NOT NULL,task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,
              role_id TEXT NOT NULL,role_version TEXT NOT NULL,principal_id TEXT NOT NULL,
              provider_id TEXT NOT NULL,model_id TEXT NOT NULL,state TEXT NOT NULL,
              reason TEXT NOT NULL,created_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,task_id,attempt_id,role_id))''',
            '''CREATE TABLE IF NOT EXISTS model_requests(
              tenant_id TEXT NOT NULL,request_id TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,task_id TEXT NOT NULL,
              attempt_id TEXT NOT NULL,role_id TEXT NOT NULL,
              provider_id TEXT NOT NULL,model_id TEXT NOT NULL,
              state TEXT NOT NULL,payload_json TEXT NOT NULL,
              payload_sha256 TEXT NOT NULL,attempts INTEGER NOT NULL,
              next_attempt_at REAL NOT NULL,result_json TEXT,
              error_kind TEXT,lease_owner TEXT,lease_until REAL,
              last_heartbeat REAL,checkpoint_json TEXT,
              cancel_requested INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,updated_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,request_id),
              UNIQUE(tenant_id,idempotency_key))''',
            '''CREATE TABLE IF NOT EXISTS model_usage_events(
              tenant_id TEXT NOT NULL,request_id TEXT NOT NULL,
              provider_id TEXT NOT NULL,model_id TEXT NOT NULL,
              input_tokens INTEGER NOT NULL,output_tokens INTEGER NOT NULL,
              cost_state TEXT NOT NULL,cost_value REAL,outcome TEXT NOT NULL,
              observed_at REAL NOT NULL,PRIMARY KEY(tenant_id,request_id))''',
            '''CREATE TABLE IF NOT EXISTS model_audit(
              audit_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,
              principal_id TEXT NOT NULL,action TEXT NOT NULL,target_id TEXT NOT NULL,
              detail_json TEXT NOT NULL,observed_at REAL NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS model_benchmark_cases(
              tenant_id TEXT NOT NULL,suite_version TEXT NOT NULL,
              case_id TEXT NOT NULL,capability TEXT NOT NULL,
              messages_json TEXT NOT NULL,expected_contains TEXT NOT NULL,
              PRIMARY KEY(tenant_id,suite_version,case_id))''',
            '''CREATE TABLE IF NOT EXISTS model_evaluations(
              tenant_id TEXT NOT NULL,evaluation_id TEXT NOT NULL,
              provider_id TEXT NOT NULL,model_id TEXT NOT NULL,
              suite_version TEXT NOT NULL,quality_score REAL NOT NULL,
              duration_ms INTEGER NOT NULL,input_tokens INTEGER NOT NULL,
              output_tokens INTEGER NOT NULL,retries INTEGER NOT NULL,
              rework_count INTEGER NOT NULL,state TEXT NOT NULL,
              evidence_json TEXT NOT NULL,observed_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,evaluation_id))''',
            '''CREATE TABLE IF NOT EXISTS delivery_candidates(
              tenant_id TEXT NOT NULL,candidate_id TEXT NOT NULL,
              task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,
              artifact_sha256 TEXT NOT NULL,checklist_sha256 TEXT NOT NULL,
              submitted_by TEXT NOT NULL,reviewed_by TEXT,accepted_by TEXT,
              state TEXT NOT NULL,findings_json TEXT NOT NULL,
              created_at REAL NOT NULL,updated_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,candidate_id))''',
            '''CREATE TABLE IF NOT EXISTS module_settings(
              tenant_id TEXT NOT NULL,module_id TEXT NOT NULL,
              enabled INTEGER NOT NULL,version TEXT NOT NULL,
              updated_at REAL NOT NULL,PRIMARY KEY(tenant_id,module_id))''',
            '''CREATE TABLE IF NOT EXISTS task_work_specs(
              tenant_id TEXT NOT NULL,task_id TEXT NOT NULL,goal TEXT NOT NULL,
              deliverables_json TEXT NOT NULL,acceptance_json TEXT NOT NULL,
              created_at REAL NOT NULL,PRIMARY KEY(tenant_id,task_id))''',
        )
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            for statement in statements:
                self.db.execute(statement)

    def _principal(self):
        self.gateway.tenants.verify(self.context)
        return self.context['principal_id']

    def _admin(self):
        principal = self._principal()
        if not principal.startswith('admin:'):
            raise ValueError('MODEL_ADMIN_REQUIRED')
        return principal

    def _audit(self, principal, action, target, detail, now):
        safe = dict(detail)
        for forbidden in ('secret', 'api_key', 'token', 'secret_cipher'):
            safe.pop(forbidden, None)
        seed = canonical({'tenant': self.tenant_id, 'principal': principal,
                          'action': action, 'target': target, 'at': now,
                          'detail': safe})
        audit_id = hashlib.sha256(seed.encode('utf-8')).hexdigest()
        self.db.execute('INSERT INTO model_audit VALUES (?,?,?,?,?,?,?)',
            (audit_id, self.tenant_id, principal, action, target,
             canonical(safe), now))

    def upsert_provider(self, value, secret=None, now=None):
        principal = self._admin(); now = self.clock() if now is None else now
        required = {'provider_id','display_name','adapter_type','base_url',
                    'enabled','price_state','rate_limit_per_min',
                    'concurrency_limit','timeout_seconds','retry_limit'}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError('EXACT_PROVIDER_CONFIG_REQUIRED')
        for key in ('provider_id','display_name','adapter_type','base_url'):
            _text(value[key], key)
        if value['adapter_type'] not in ADAPTERS:
            raise ValueError('SUPPORTED_ADAPTER_REQUIRED')
        if value['price_state'] not in PRICE_STATES:
            raise ValueError('VALID_PRICE_STATE_REQUIRED')
        if type(value['enabled']) is not bool:
            raise ValueError('BOOLEAN_ENABLED_REQUIRED')
        for name in ('rate_limit_per_min','concurrency_limit','retry_limit'):
            if type(value[name]) is not int or value[name] < (0 if name=='retry_limit' else 1):
                raise ValueError('VALID_%s_REQUIRED' % name.upper())
        _number(value['timeout_seconds'], 'timeout_seconds', 0.05)
        if not value['base_url'].startswith(('http://127.0.0.1:', 'http://localhost:', 'https://')):
            raise ValueError('SAFE_PROVIDER_URL_REQUIRED')
        existing = self.db.execute('''SELECT * FROM model_providers
          WHERE tenant_id=? AND provider_id=?''',
          (self.tenant_id,value['provider_id'])).fetchone()
        if existing is None and self.db.execute('''SELECT COUNT(*) FROM
          model_providers WHERE tenant_id=?''',(self.tenant_id,)).fetchone()[0] >= 10:
            raise ValueError('PROVIDER_LIMIT_10')
        cipher = existing['secret_cipher'] if existing else None
        mask = existing['secret_mask'] if existing else None
        if secret is not None:
            if not isinstance(secret,str) or len(secret)<8 or '\n' in secret or '\r' in secret:
                raise ValueError('VALID_PROVIDER_SECRET_REQUIRED')
            cipher = self.fernet.encrypt(secret.encode('utf-8'))
            mask = '••••' + secret[-4:]
        version = (existing['config_version'] + 1) if existing else 1
        created = existing['created_at'] if existing else now
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''INSERT OR REPLACE INTO model_providers VALUES
              (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (self.tenant_id,value['provider_id'],value['display_name'],
               value['adapter_type'],value['base_url'],int(value['enabled']),
               value['price_state'],value['rate_limit_per_min'],
               value['concurrency_limit'],value['timeout_seconds'],
               value['retry_limit'],cipher,mask,version,'CLOSED',0,None,
               created,now))
            self._audit(principal,'PROVIDER_UPSERT',value['provider_id'],
                        {'config_version':version,'secret_replaced':secret is not None},now)
        return {'provider_id':value['provider_id'],'config_version':version,
                'secret_mask':mask,'secret_configured':cipher is not None}

    def disable_provider(self, provider_id, now=None):
        principal=self._admin();now=self.clock() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            changed=self.db.execute('''UPDATE model_providers SET enabled=0,
              updated_at=? WHERE tenant_id=? AND provider_id=?''',
              (now,self.tenant_id,_text(provider_id,'provider_id'))).rowcount
            if changed!=1: raise KeyError(provider_id)
            self.db.execute('''UPDATE model_requests SET state='CANCELLED',
              error_kind='PROVIDER_DISABLED',updated_at=? WHERE tenant_id=?
              AND provider_id=? AND state IN ('QUEUED','RETRY_WAIT')''',
              (now,self.tenant_id,provider_id))
            self._audit(principal,'PROVIDER_DISABLED',provider_id,{},now)
        return {'provider_id':provider_id,'enabled':False}

    def list_providers(self):
        self._principal()
        result=[]
        for row in self.db.execute('''SELECT provider_id,display_name,
          adapter_type,base_url,enabled,price_state,rate_limit_per_min,
          concurrency_limit,timeout_seconds,retry_limit,secret_mask,
          config_version,circuit_state,failure_count,updated_at FROM
          model_providers WHERE tenant_id=? ORDER BY provider_id''',(self.tenant_id,)):
            item=dict(row);item['enabled']=bool(item['enabled'])
            item['secret_configured']=item['secret_mask'] is not None
            result.append(item)
        return result

    def provider_secret(self, provider_id):
        row=self.db.execute('''SELECT secret_cipher FROM model_providers
          WHERE tenant_id=? AND provider_id=? AND enabled=1''',
          (self.tenant_id,provider_id)).fetchone()
        if row is None or row['secret_cipher'] is None:
            raise ValueError('ACTIVE_PROVIDER_SECRET_REQUIRED')
        try:return self.fernet.decrypt(row['secret_cipher']).decode('utf-8')
        except InvalidToken:raise ValueError('PROVIDER_SECRET_DECRYPT_FAILED')

    def upsert_model(self, value):
        self._admin()
        required={'provider_id','model_id','capabilities','enabled','price_state',
                  'input_unit_cost','output_unit_cost'}
        if not isinstance(value,dict) or set(value)!=required:
            raise ValueError('EXACT_MODEL_CONFIG_REQUIRED')
        if not isinstance(value['capabilities'],list) or not value['capabilities']:
            raise ValueError('MODEL_CAPABILITIES_REQUIRED')
        if value['price_state'] not in PRICE_STATES:raise ValueError('VALID_PRICE_STATE_REQUIRED')
        for key in ('input_unit_cost','output_unit_cost'):
            if value[key] is not None:_number(value[key],key)
        if value['price_state']==UNKNOWN and (value['input_unit_cost'] is not None or value['output_unit_cost'] is not None):
            raise ValueError('UNKNOWN_PRICE_MUST_NOT_HAVE_COST')
        self.db.execute('''INSERT OR REPLACE INTO model_catalog VALUES
          (?,?,?,?,?,?,?,?)''',(self.tenant_id,_text(value['provider_id'],'provider_id'),
          _text(value['model_id'],'model_id'),canonical(sorted(set(value['capabilities']))),
          int(value['enabled']),value['price_state'],value['input_unit_cost'],
          value['output_unit_cost']))
        self.db.commit()
        return {'provider_id':value['provider_id'],'model_id':value['model_id']}

    def create_role(self, value):
        self._admin();required={'role_id','version','phase','capabilities','writer_allowed','enabled'}
        if not isinstance(value,dict) or set(value)!=required:raise ValueError('EXACT_ROLE_TEMPLATE_REQUIRED')
        if value['phase'] not in PHASES:raise ValueError('VALID_ROLE_PHASE_REQUIRED')
        if value['phase']!='EXECUTOR' and value['writer_allowed'] is not False:
            raise ValueError('REVIEW_ACCEPT_NO_WRITER')
        self.db.execute('INSERT INTO role_templates VALUES (?,?,?,?,?,?,?)',
          (self.tenant_id,_text(value['role_id'],'role_id'),_text(value['version'],'version'),
           value['phase'],canonical(sorted(set(value['capabilities']))),
           int(value['writer_allowed']),int(value['enabled'])))
        self.db.commit();return {'role_id':value['role_id'],'version':value['version']}

    def bind_skill(self, role_id, role_version, skill_id, skill_version,
                   review_sha256, status):
        self._admin()
        if status!='APPROVED' or len(review_sha256)!=64:
            raise ValueError('APPROVED_SKILL_REVIEW_REQUIRED')
        self.db.execute('INSERT INTO role_skill_bindings VALUES (?,?,?,?,?,?,?)',
          (self.tenant_id,role_id,role_version,skill_id,skill_version,
           review_sha256,status));self.db.commit()
        return {'skill_id':skill_id,'status':status}

    def assign(self, task_id, role_id, role_version, principal_id,
               allow_paid=False, now=None):
        now=self.clock() if now is None else now
        self.gateway.assert_task_context(self.context,task_id)
        task=self.gateway.supervisor._task(task_id)
        role=self.db.execute('''SELECT * FROM role_templates WHERE tenant_id=?
          AND role_id=? AND version=? AND enabled=1''',
          (self.tenant_id,role_id,role_version)).fetchone()
        if role is None:raise ValueError('ACTIVE_ROLE_REQUIRED')
        if role['phase'] in ('REVIEWER','ACCEPTOR'):
            executor=self.db.execute('''SELECT principal_id FROM model_assignments
              WHERE tenant_id=? AND task_id=? AND attempt_id=? AND role_id IN
              (SELECT role_id FROM role_templates WHERE tenant_id=? AND phase='EXECUTOR')''',
              (self.tenant_id,task_id,task['attempt_id'],self.tenant_id)).fetchone()
            if executor and executor['principal_id']==principal_id:
                raise ValueError('SELF_APPROVAL_FORBIDDEN')
        capabilities=set(json.loads(role['capabilities_json']))
        candidates=[]
        for row in self.db.execute('''SELECT p.provider_id,p.price_state AS
          provider_price,m.model_id,m.price_state,m.capabilities_json FROM
          model_providers p JOIN model_catalog m ON p.tenant_id=m.tenant_id
          AND p.provider_id=m.provider_id WHERE p.tenant_id=? AND p.enabled=1
          AND m.enabled=1 AND p.circuit_state='CLOSED' ''',(self.tenant_id,)):
            if capabilities.issubset(set(json.loads(row['capabilities_json']))):
                qualified=self.db.execute('''SELECT state,quality_score,
                  duration_ms,retries,rework_count FROM model_evaluations
                  WHERE tenant_id=? AND provider_id=? AND model_id=? ORDER BY
                  observed_at DESC,evaluation_id DESC LIMIT 1''',(self.tenant_id,
                  row['provider_id'],row['model_id'])).fetchone()
                if qualified is None or qualified['state']!='QUALIFIED':
                    continue
                effective=(UNKNOWN if UNKNOWN in (row['price_state'],row['provider_price'])
                           else 'KNOWN_PAID' if 'KNOWN_PAID' in
                           (row['price_state'],row['provider_price']) else 'KNOWN_FREE')
                if effective!='KNOWN_FREE' and not allow_paid:continue
                item=dict(row);item['effective_price']=effective
                item['acceptance_penalty']=(qualified['retries']+
                  qualified['rework_count']+(1-qualified['quality_score'])*100+
                  qualified['duration_ms']/100000.0)
                candidates.append(item)
        if not candidates:raise ValueError('NO_AUTHORIZED_CAPABLE_MODEL')
        price_rank={'KNOWN_FREE':0,'KNOWN_PAID':1,UNKNOWN:2}
        candidates.sort(key=lambda x:(price_rank[x['effective_price']],
          x['acceptance_penalty'],x['provider_id'],x['model_id']))
        chosen=candidates[0]
        self.db.execute('''INSERT INTO model_assignments VALUES
          (?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,task_id,task['attempt_id'],
          role_id,role_version,_text(principal_id,'principal_id'),
          chosen['provider_id'],chosen['model_id'],'ASSIGNED',
          'QUALIFIED_FREE_FINAL_COST' if chosen['effective_price']=='KNOWN_FREE'
          else 'AUTHORIZED_QUALIFIED_FINAL_COST',now))
        self.db.commit();return dict(provider_id=chosen['provider_id'],
          model_id=chosen['model_id'],reason='QUALIFIED_FREE_FINAL_COST' if
          chosen['effective_price']=='KNOWN_FREE' else
          'AUTHORIZED_QUALIFIED_FINAL_COST')

    def queue_request(self, task_id, role_id, messages, idempotency_key,
                      now=None):
        now=self.clock() if now is None else now
        self.gateway.assert_task_context(self.context,task_id)
        task=self.gateway.supervisor._task(task_id)
        assignment=self.db.execute('''SELECT * FROM model_assignments WHERE
          tenant_id=? AND task_id=? AND attempt_id=? AND role_id=?''',
          (self.tenant_id,task_id,task['attempt_id'],role_id)).fetchone()
        if assignment is None:raise ValueError('MODEL_ASSIGNMENT_REQUIRED')
        payload={'messages':messages};body=canonical(payload);digest=hashlib.sha256(body.encode()).hexdigest()
        request_id=hashlib.sha256(canonical({'tenant':self.tenant_id,'idempotency':idempotency_key}).encode()).hexdigest()
        existing=self.db.execute('''SELECT payload_sha256,state FROM model_requests
          WHERE tenant_id=? AND idempotency_key=?''',(self.tenant_id,idempotency_key)).fetchone()
        if existing:
            if existing['payload_sha256']!=digest:raise ValueError('IDEMPOTENCY_CONFLICT')
            return {'request_id':request_id,'state':existing['state'],'duplicate':True}
        checkpoint=canonical({'goal':'execute assigned role','input_version':
          task.get('spec_sha256',UNKNOWN),'done':[],'pending':['MODEL_RESULT'],
          'evidence':[]})
        self.db.execute('''INSERT INTO model_requests VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,request_id,
          _text(idempotency_key,'idempotency_key'),task_id,task['attempt_id'],
          role_id,assignment['provider_id'],assignment['model_id'],'QUEUED',body,
          digest,0,now,None,None,None,None,None,checkpoint,0,now,now));self.db.commit()
        return {'request_id':request_id,'state':'QUEUED','duplicate':False}

    def request_cancel(self, request_id, now=None):
        principal=self._admin();now=self.clock() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            row=self.db.execute('''SELECT state FROM model_requests WHERE
              tenant_id=? AND request_id=?''',(self.tenant_id,request_id)).fetchone()
            if row is None:raise KeyError(request_id)
            if row['state'] in ('QUEUED','RETRY_WAIT'):
                state='CANCELLED'
            elif row['state']=='RUNNING':state='RUNNING'
            else:raise ValueError('REQUEST_ALREADY_TERMINAL')
            self.db.execute('''UPDATE model_requests SET cancel_requested=1,
              state=?,error_kind=CASE WHEN ?='CANCELLED' THEN
              'CANCELLED_BEFORE_CALL' ELSE error_kind END,updated_at=? WHERE
              tenant_id=? AND request_id=?''',(state,state,now,self.tenant_id,
              request_id))
            self._audit(principal,'REQUEST_CANCEL',request_id,
                        {'resulting_state':state},now)
        return {'request_id':request_id,'state':state,
                'cancel_requested':True}

    def register_benchmark_suite(self, suite_version, cases):
        principal=self._admin();_text(suite_version,'suite_version')
        if not isinstance(cases,list) or not cases:raise ValueError('BENCHMARK_CASES_REQUIRED')
        normalized=[]
        for case in cases:
            if set(case)!={'case_id','capability','messages','expected_contains'}:
                raise ValueError('EXACT_BENCHMARK_CASE_REQUIRED')
            if not isinstance(case['messages'],list):raise ValueError('BENCHMARK_MESSAGES_REQUIRED')
            normalized.append(case)
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            for case in normalized:
                self.db.execute('''INSERT INTO model_benchmark_cases VALUES
                  (?,?,?,?,?,?)''',(self.tenant_id,suite_version,
                  _text(case['case_id'],'case_id'),_text(case['capability'],'capability'),
                  canonical(case['messages']),_text(case['expected_contains'],
                  'expected_contains')))
            self._audit(principal,'BENCHMARK_SUITE_REGISTER',suite_version,
                        {'case_count':len(normalized)},self.clock())
        return {'suite_version':suite_version,'case_count':len(normalized)}

    def run_benchmark(self, provider_id, model_id, suite_version,
                      adapter=None, now=None):
        """Run the registered TEST_ONLY cases through the real adapter path."""
        self._admin();now=self.clock() if now is None else now
        provider=self.db.execute('''SELECT * FROM model_providers WHERE
          tenant_id=? AND provider_id=? AND enabled=1''',(self.tenant_id,
          provider_id)).fetchone()
        model=self.db.execute('''SELECT * FROM model_catalog WHERE tenant_id=?
          AND provider_id=? AND model_id=? AND enabled=1''',(self.tenant_id,
          provider_id,model_id)).fetchone()
        cases=list(self.db.execute('''SELECT * FROM model_benchmark_cases WHERE
          tenant_id=? AND suite_version=? ORDER BY case_id''',(self.tenant_id,
          suite_version)))
        if provider is None or model is None or not cases:
            raise ValueError('ACTIVE_MODEL_AND_SUITE_REQUIRED')
        adapter=adapter or ({'siliconflow':SiliconFlowAdapter(),
          'openai-compatible':OpenAICompatibleAdapter()}[provider['adapter_type']])
        started=time.monotonic();passed=0;input_tokens=0;output_tokens=0;evidence=[]
        secret=self.provider_secret(provider_id)
        for case in cases:
            try:
                result=adapter.invoke(provider['base_url'],secret,model_id,
                  json.loads(case['messages_json']),provider['timeout_seconds'])
                ok=case['expected_contains'] in result['content']
                passed+=int(ok);input_tokens+=result['usage']['input_tokens']
                output_tokens+=result['usage']['output_tokens']
                evidence.append({'case_id':case['case_id'],'passed':ok,
                  'provider_request_id':result['provider_request_id']})
            except ProviderError as exc:
                evidence.append({'case_id':case['case_id'],'passed':False,
                  'error_kind':exc.kind})
        score=float(passed)/len(cases);duration=int((time.monotonic()-started)*1000)
        identity=canonical({'tenant':self.tenant_id,'provider':provider_id,
          'model':model_id,'suite':suite_version,'at':now})
        evaluation_id=hashlib.sha256(identity.encode()).hexdigest()
        state='QUALIFIED' if score==1.0 else 'NOT_QUALIFIED'
        self.db.execute('''INSERT INTO model_evaluations VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,evaluation_id,
          provider_id,model_id,suite_version,score,duration,input_tokens,
          output_tokens,0,0,state,canonical(evidence),now));self.db.commit()
        return {'evaluation_id':evaluation_id,'state':state,
                'quality_score':score,'duration_ms':duration}

    def submit_candidate(self, task_id, artifact_sha256, checklist_sha256,
                         submitted_by, now=None):
        now=self.clock() if now is None else now
        self.gateway.assert_task_context(self.context,task_id)
        if any(len(x)!=64 for x in (artifact_sha256,checklist_sha256)):
            raise ValueError('CANDIDATE_SHA256_REQUIRED')
        task=self.gateway.supervisor._task(task_id)
        assignment=self.db.execute('''SELECT 1 FROM model_assignments a JOIN
          role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id
          AND r.version=a.role_version WHERE a.tenant_id=? AND a.task_id=? AND
          a.attempt_id=? AND a.principal_id=? AND r.phase='EXECUTOR' ''',
          (self.tenant_id,task_id,task['attempt_id'],submitted_by)).fetchone()
        if assignment is None:raise ValueError('EXECUTOR_ASSIGNMENT_REQUIRED')
        candidate_id=hashlib.sha256(canonical({'tenant':self.tenant_id,
          'task':task_id,'attempt':task['attempt_id'],'artifact':artifact_sha256}).encode()).hexdigest()
        self.db.execute('''INSERT INTO delivery_candidates VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,candidate_id,task_id,
          task['attempt_id'],artifact_sha256,checklist_sha256,submitted_by,None,
          None,'SUBMITTED',canonical([]),now,now));self.db.commit()
        return {'candidate_id':candidate_id,'state':'SUBMITTED'}

    def review_candidate(self, candidate_id, reviewer, findings, passed,
                         now=None):
        now=self.clock() if now is None else now
        row=self.db.execute('''SELECT * FROM delivery_candidates WHERE
          tenant_id=? AND candidate_id=?''',(self.tenant_id,candidate_id)).fetchone()
        if row is None:raise KeyError(candidate_id)
        if reviewer==row['submitted_by']:raise ValueError('SELF_REVIEW_FORBIDDEN')
        assignment=self.db.execute('''SELECT 1 FROM model_assignments a JOIN
          role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id
          AND r.version=a.role_version WHERE a.tenant_id=? AND a.task_id=? AND
          a.attempt_id=? AND a.principal_id=? AND r.phase='REVIEWER' ''',
          (self.tenant_id,row['task_id'],row['attempt_id'],reviewer)).fetchone()
        if assignment is None:raise ValueError('INDEPENDENT_REVIEW_ASSIGNMENT_REQUIRED')
        if not isinstance(findings,list):raise ValueError('FINDINGS_ARRAY_REQUIRED')
        state='REVIEW_PASSED' if passed and not findings else 'CHANGES_REQUESTED'
        self.db.execute('''UPDATE delivery_candidates SET reviewed_by=?,state=?,
          findings_json=?,updated_at=? WHERE tenant_id=? AND candidate_id=?''',
          (reviewer,state,canonical(findings),now,self.tenant_id,candidate_id));self.db.commit()
        return {'candidate_id':candidate_id,'state':state,
                'finding_count':len(findings)}

    def accept_candidate(self, candidate_id, acceptor, now=None):
        now=self.clock() if now is None else now
        row=self.db.execute('''SELECT * FROM delivery_candidates WHERE tenant_id=?
          AND candidate_id=?''',(self.tenant_id,candidate_id)).fetchone()
        if row is None:raise KeyError(candidate_id)
        if row['state']!='REVIEW_PASSED':raise ValueError('REVIEW_PASS_REQUIRED')
        if acceptor in (row['submitted_by'],row['reviewed_by']):
            raise ValueError('INDEPENDENT_ACCEPTANCE_REQUIRED')
        assignment=self.db.execute('''SELECT 1 FROM model_assignments a JOIN
          role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id
          AND r.version=a.role_version WHERE a.tenant_id=? AND a.task_id=? AND
          a.attempt_id=? AND a.principal_id=? AND r.phase='ACCEPTOR' ''',
          (self.tenant_id,row['task_id'],row['attempt_id'],acceptor)).fetchone()
        if assignment is None:raise ValueError('ACCEPTOR_ASSIGNMENT_REQUIRED')
        self.db.execute('''UPDATE delivery_candidates SET accepted_by=?,state=
          'ACCEPTED',updated_at=? WHERE tenant_id=? AND candidate_id=?''',
          (acceptor,now,self.tenant_id,candidate_id));self.db.commit()
        return {'candidate_id':candidate_id,'state':'ACCEPTED'}

    def set_module(self,module_id,version,enabled,now=None):
        self._admin();now=self.clock() if now is None else now
        self.db.execute('''INSERT OR REPLACE INTO module_settings VALUES
          (?,?,?,?,?)''',(self.tenant_id,_text(module_id,'module_id'),
          int(bool(enabled)),_text(version,'version'),now));self.db.commit()
        return {'module_id':module_id,'version':version,'enabled':bool(enabled)}

    def record_task_spec(self,task_id,goal,deliverables,acceptance,now=None):
        self._admin();now=self.clock() if now is None else now
        self.gateway.assert_task_context(self.context,task_id)
        if not isinstance(deliverables,list) or not isinstance(acceptance,list):
            raise ValueError('TASK_SPEC_ARRAYS_REQUIRED')
        self.db.execute('''INSERT INTO task_work_specs VALUES (?,?,?,?,?,?)''',
          (self.tenant_id,task_id,_text(goal,'goal'),canonical(deliverables),
          canonical(acceptance),now));self.db.commit()
        return {'task_id':task_id,'spec_recorded':True}

    def projection(self):
        return {'providers':self.list_providers(),
          'models':[dict(x) for x in self.db.execute('''SELECT provider_id,
          model_id,capabilities_json,enabled,price_state,input_unit_cost,
          output_unit_cost FROM model_catalog WHERE tenant_id=? ORDER BY
          provider_id,model_id''',(self.tenant_id,))],
          'roles':[dict(x) for x in self.db.execute('''SELECT role_id,version,
          phase,capabilities_json,writer_allowed,enabled FROM role_templates
          WHERE tenant_id=? ORDER BY role_id,version''',(self.tenant_id,))],
          'requests':[dict(x) for x in self.db.execute('''SELECT request_id,
          task_id,attempt_id,role_id,provider_id,model_id,state,attempts,
          error_kind,payload_sha256,result_json,lease_owner,lease_until,
          last_heartbeat,checkpoint_json,cancel_requested,created_at,updated_at
          FROM model_requests WHERE tenant_id=?
          ORDER BY created_at,request_id''',(self.tenant_id,))],
          'assignments':[dict(x) for x in self.db.execute('''SELECT task_id,
          attempt_id,role_id,role_version,principal_id,provider_id,model_id,
          state,reason,created_at FROM model_assignments WHERE tenant_id=?
          ORDER BY task_id,role_id''',(self.tenant_id,))],
          'usage':[dict(x) for x in self.db.execute('''SELECT provider_id,
          model_id,COUNT(*) AS request_count,SUM(input_tokens) AS input_tokens,
          SUM(output_tokens) AS output_tokens,cost_state,SUM(cost_value) AS
          known_cost FROM model_usage_events WHERE tenant_id=? GROUP BY
          provider_id,model_id,cost_state ORDER BY provider_id,model_id''',
          (self.tenant_id,))],
          'evaluations':[dict(x) for x in self.db.execute('''SELECT
          evaluation_id,provider_id,model_id,suite_version,quality_score,
          duration_ms,input_tokens,output_tokens,retries,rework_count,state,
          observed_at FROM model_evaluations WHERE tenant_id=? ORDER BY
          observed_at,evaluation_id''',(self.tenant_id,))],
          'candidates':[dict(x) for x in self.db.execute('''SELECT candidate_id,
          task_id,attempt_id,artifact_sha256,checklist_sha256,submitted_by,
          reviewed_by,accepted_by,state,findings_json,created_at,updated_at FROM
          delivery_candidates WHERE tenant_id=? ORDER BY created_at,candidate_id''',
          (self.tenant_id,))],
          'modules':[dict(x) for x in self.db.execute('''SELECT module_id,
          enabled,version,updated_at FROM module_settings WHERE tenant_id=?
          ORDER BY module_id''',(self.tenant_id,))],
          'task_specs':[dict(x) for x in self.db.execute('''SELECT task_id,
          goal,deliverables_json,acceptance_json,created_at FROM task_work_specs
          WHERE tenant_id=? ORDER BY task_id''',(self.tenant_id,))],
          'audit':[dict(x) for x in self.db.execute('''SELECT audit_id,
          principal_id,action,target_id,detail_json,observed_at FROM model_audit
          WHERE tenant_id=? ORDER BY observed_at,audit_id''',(self.tenant_id,))],
          'production_status':'NOT_IMPLEMENTED','mode':'TEST_ONLY'}


class ModelScheduler(object):
    def __init__(self, control, adapters=None, clock=None, worker_id='worker-local'):
        self.control=control;self.db=control.db;self.clock=clock or time.time
        self.worker_id=_text(worker_id,'worker_id')
        self.adapters=adapters or {'siliconflow':SiliconFlowAdapter(),
          'openai-compatible':OpenAICompatibleAdapter()}

    def run_once(self, now=None):
        now=self.clock() if now is None else now
        # A dead process may have made an external request.  Expiry therefore
        # converges to UNKNOWN for reconciliation, never to an automatic retry.
        self.db.execute('''UPDATE model_requests SET state=?,error_kind=?,
          lease_owner=NULL,lease_until=NULL,updated_at=? WHERE tenant_id=? AND
          state='RUNNING' AND lease_until IS NOT NULL AND lease_until<?''',
          (UNKNOWN,'WORKER_LOST_SIDE_EFFECT_UNKNOWN',now,
           self.control.tenant_id,now));self.db.commit()
        row=self.db.execute('''SELECT r.*,p.adapter_type,p.base_url,
          p.timeout_seconds,p.retry_limit,p.rate_limit_per_min,
          p.concurrency_limit,p.circuit_state,p.next_probe_at,p.price_state
          AS provider_price,m.price_state AS model_price,m.input_unit_cost,
          m.output_unit_cost FROM model_requests r JOIN model_providers p ON
          r.tenant_id=p.tenant_id AND r.provider_id=p.provider_id JOIN
          model_catalog m ON m.tenant_id=r.tenant_id AND
          m.provider_id=r.provider_id AND m.model_id=r.model_id WHERE
          r.tenant_id=? AND r.state IN ('QUEUED','RETRY_WAIT') AND
          r.next_attempt_at<=? AND p.enabled=1 ORDER BY r.created_at LIMIT 1''',
          (self.control.tenant_id,now)).fetchone()
        if row is None:return {'state':'IDLE'}
        task=self.control.gateway.supervisor._task(row['task_id'])
        if task['attempt_id']!=row['attempt_id'] or task['authority_state']!='VALID':
            self._finish(row,'CANCELLED','STALE_OR_UNAUTHORIZED',None,now)
            return {'request_id':row['request_id'],'state':'CANCELLED'}
        if row['circuit_state']=='OPEN' and (row['next_probe_at'] is None or row['next_probe_at']>now):
            return {'request_id':row['request_id'],'state':'CIRCUIT_OPEN'}
        recent=self.db.execute('''SELECT COUNT(*) FROM model_usage_events WHERE
          tenant_id=? AND provider_id=? AND observed_at>?''',
          (row['tenant_id'],row['provider_id'],now-60)).fetchone()[0]
        running=self.db.execute('''SELECT COUNT(*) FROM model_requests WHERE
          tenant_id=? AND provider_id=? AND state='RUNNING' ''',
          (row['tenant_id'],row['provider_id'])).fetchone()[0]
        if recent>=row['rate_limit_per_min'] or running>=row['concurrency_limit']:
            return {'request_id':row['request_id'],'state':'QUEUED_LIMIT'}
        changed=self.db.execute('''UPDATE model_requests SET state='RUNNING',
          attempts=attempts+1,lease_owner=?,lease_until=?,last_heartbeat=?,
          updated_at=? WHERE tenant_id=? AND request_id=?
          AND state IN ('QUEUED','RETRY_WAIT')''',(self.worker_id,
          now+row['timeout_seconds']+5,now,now,row['tenant_id'],
          row['request_id'])).rowcount
        self.db.commit()
        if changed!=1:return {'request_id':row['request_id'],'state':'LOST_RACE'}
        secret=self.control.provider_secret(row['provider_id'])
        payload=json.loads(row['payload_json'])
        adapter=self.adapters[row['adapter_type']]
        try:
            result=adapter.invoke(row['base_url'],secret,row['model_id'],
                                  payload['messages'],row['timeout_seconds'])
        except ProviderError as exc:
            attempts=row['attempts']+1
            if exc.kind=='TIMEOUT_UNKNOWN':
                self._finish(row,UNKNOWN,exc.kind,None,now)
                return {'request_id':row['request_id'],'state':UNKNOWN,'error':exc.kind}
            if exc.retryable and attempts<=row['retry_limit']:
                self.db.execute('''UPDATE model_requests SET state='RETRY_WAIT',
                  error_kind=?,next_attempt_at=?,lease_owner=NULL,
                  lease_until=NULL,updated_at=? WHERE tenant_id=?
                  AND request_id=?''',(exc.kind,now+min(60,2**attempts),now,
                  row['tenant_id'],row['request_id']));self.db.commit()
                return {'request_id':row['request_id'],'state':'RETRY_WAIT','error':exc.kind}
            self._finish(row,'FAILED',exc.kind,None,now)
            return {'request_id':row['request_id'],'state':'FAILED','error':exc.kind}
        self._finish(row,'SUCCEEDED',None,result,now)
        return {'request_id':row['request_id'],'state':'SUCCEEDED'}

    def _finish(self,row,state,error,result,now):
        usage=(result or {}).get('usage',{})
        prices=(row['provider_price'],row['model_price'])
        if UNKNOWN in prices:
            cost_state=UNKNOWN;cost_value=None
        elif 'KNOWN_PAID' in prices:
            cost_state='KNOWN'
            cost_value=(usage.get('input_tokens',0) * (row['input_unit_cost'] or 0) +
                        usage.get('output_tokens',0) * (row['output_unit_cost'] or 0))
        else:
            cost_state='KNOWN_ZERO';cost_value=0
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''UPDATE model_requests SET state=?,result_json=?,
              error_kind=?,lease_owner=NULL,lease_until=NULL,updated_at=?
              WHERE tenant_id=? AND request_id=?''',
              (state,canonical(result) if result else None,error,now,
               row['tenant_id'],row['request_id']))
            self.db.execute('''INSERT OR REPLACE INTO model_usage_events VALUES
              (?,?,?,?,?,?,?,?,?,?)''',(row['tenant_id'],row['request_id'],
               row['provider_id'],row['model_id'],usage.get('input_tokens',0),
               usage.get('output_tokens',0),cost_state,cost_value,
               state,now))
            if state=='SUCCEEDED':
                self.db.execute('''UPDATE model_providers SET failure_count=0,
                  circuit_state='CLOSED',next_probe_at=NULL,updated_at=? WHERE
                  tenant_id=? AND provider_id=?''',
                  (now,row['tenant_id'],row['provider_id']))
            elif state=='FAILED':
                self.db.execute('''UPDATE model_providers SET
                  failure_count=failure_count+1,circuit_state=CASE WHEN
                  failure_count+1>=3 THEN 'OPEN' ELSE circuit_state END,
                  next_probe_at=CASE WHEN failure_count+1>=3 THEN ? ELSE
                  next_probe_at END,updated_at=? WHERE tenant_id=? AND
                  provider_id=?''',(now+60,now,row['tenant_id'],row['provider_id']))
