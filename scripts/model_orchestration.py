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
import ipaddress
from urllib.parse import urlparse
import urllib.error
import urllib.request
import http.client
import socket
import ssl
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken

from reusable_task_gateway import _text, _sha
from task_supervisor import UNKNOWN, canonical
from connection_management import ConnectionManager


ADAPTERS = frozenset(('siliconflow', 'openai-compatible'))
PRICE_STATES = frozenset(('KNOWN_FREE', 'KNOWN_PAID', UNKNOWN))
PHASES = frozenset(('EXECUTOR', 'REVIEWER', 'ACCEPTOR'))
REQUEST_STATES = frozenset(('QUEUED', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED',
                            'FAILED', UNKNOWN, 'CANCELLED','HOLD'))


def _number(value, name, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError('VALID_%s_REQUIRED' % name.upper())
    return value


def load_master_key(path):
    import os, stat as stat_module
    info = os.lstat(path)
    if (not stat_module.S_ISREG(info.st_mode) or info.st_nlink!=1 or
            info.st_uid!=os.getuid()):
        raise ValueError('OWNED_REGULAR_MASTER_KEY_FILE_REQUIRED')
    if info.st_mode & 0o077:
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
        self.opener = opener

    def _pinned_open(self, parsed, body, headers, timeout):
        """Resolve once, validate, then connect to that exact address.

        Keeping the TLS server name separate from the connected address closes
        the DNS-rebinding gap between policy validation and socket creation.
        """
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        try:addresses=socket.getaddrinfo(parsed.hostname,port,type=socket.SOCK_STREAM)
        except OSError as exc:raise ProviderError('DNS',type(exc).__name__,False)
        if not addresses:raise ProviderError('DNS','EMPTY_RESULT',False)
        vetted=[]
        for item in addresses:
            address=ipaddress.ip_address(item[4][0])
            if parsed.scheme=='https' and (address.is_private or address.is_loopback or
                    address.is_link_local or address.is_multicast or
                    address.is_reserved or address.is_unspecified):
                raise ProviderError('UNSAFE_DESTINATION','PRIVATE_DNS_RESULT',False)
            vetted.append(item)
        selected=vetted[0]
        def connect_selected(timeout_value):
            family,socktype,proto,_,sockaddr=selected
            raw=socket.socket(family,socktype,proto)
            try:
                raw.settimeout(timeout_value);raw.connect(sockaddr);return raw
            except Exception:
                raw.close();raise
        class PinnedHTTP(http.client.HTTPConnection):
            def connect(connection):
                connection.sock=connect_selected(connection.timeout)
        class PinnedHTTPS(http.client.HTTPSConnection):
            def connect(connection):
                raw=connect_selected(connection.timeout)
                connection.sock=connection._context.wrap_socket(
                  raw,server_hostname=parsed.hostname)
        cls=PinnedHTTPS if parsed.scheme=='https' else PinnedHTTP
        connection=cls(parsed.hostname,port=port,timeout=timeout,
          context=ssl.create_default_context()) if parsed.scheme=='https' else cls(
          parsed.hostname,port=port,timeout=timeout)
        path=(parsed.path.rstrip('/')+'/v1/chat/completions') or '/v1/chat/completions'
        if parsed.query:path+='?'+parsed.query
        request_headers=dict(headers);request_headers['Host']=parsed.netloc
        try:
            connection.request('POST',path,body=body,headers=request_headers)
            return connection,connection.getresponse()
        except Exception:
            connection.close()
            raise

    def invoke(self, base_url, secret, model_id, messages, timeout,
               max_output_tokens=None):
        parsed=urlparse(base_url)
        url = base_url.rstrip('/') + '/v1/chat/completions'
        payload={'model': model_id, 'messages': messages,'stream': False}
        if max_output_tokens is not None:payload['max_tokens']=max_output_tokens
        body = canonical(payload).encode('utf-8')
        headers={'Authorization': 'Bearer ' + secret,
                 'Content-Type': 'application/json','Accept': 'application/json',
                 'User-Agent': 'Xuanjun-TEST-ONLY-Adapter'}
        request = urllib.request.Request(url,data=body,method='POST',headers=headers)
        connection=None
        try:
            if self.opener is None:
                connection,response=self._pinned_open(parsed,body,headers,timeout)
                if response.status in (401,429) or response.status>=300:
                    kind='AUTH' if response.status==401 else ('RATE_LIMIT' if response.status==429 else 'HTTP')
                    raise ProviderError(kind,'HTTP_%d'%response.status,response.status==429 or response.status>=500)
            else:response = self.opener(request, timeout=timeout)
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
            # A POST may already have reached the provider.  Connection reset,
            # wrapped timeouts and malformed replies are therefore UNKNOWN,
            # never safe automatic retries.
            raise ProviderError('TRANSPORT_UNKNOWN', type(exc).__name__, False)
        finally:
            if connection is not None:connection.close()
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
        self.master_key = master_key
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
            '''CREATE TABLE IF NOT EXISTS model_call_attempts(
              tenant_id TEXT NOT NULL,request_id TEXT NOT NULL,
              attempt_number INTEGER NOT NULL,provider_id TEXT NOT NULL,
              model_id TEXT NOT NULL,worker_id TEXT NOT NULL,
              started_at REAL NOT NULL,PRIMARY KEY(tenant_id,request_id,
              attempt_number))''',
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
            '''CREATE TABLE IF NOT EXISTS candidate_reviews(
              tenant_id TEXT NOT NULL,candidate_id TEXT NOT NULL,
              review_id TEXT NOT NULL,reviewer TEXT NOT NULL,
              decision TEXT NOT NULL,findings_json TEXT NOT NULL,
              observed_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,candidate_id,review_id))''',
            '''CREATE TABLE IF NOT EXISTS module_settings(
              tenant_id TEXT NOT NULL,module_id TEXT NOT NULL,
              enabled INTEGER NOT NULL,version TEXT NOT NULL,
              updated_at REAL NOT NULL,PRIMARY KEY(tenant_id,module_id))''',
            '''CREATE TABLE IF NOT EXISTS task_work_specs(
              tenant_id TEXT NOT NULL,task_id TEXT NOT NULL,goal TEXT NOT NULL,
              deliverables_json TEXT NOT NULL,acceptance_json TEXT NOT NULL,
              created_at REAL NOT NULL,PRIMARY KEY(tenant_id,task_id))''',
            '''CREATE TABLE IF NOT EXISTS model_runtime_limits(
              tenant_id TEXT NOT NULL,provider_id TEXT NOT NULL,
              tpm_limit INTEGER NOT NULL,max_output_tokens INTEGER NOT NULL,
              tenant_budget REAL,task_budget REAL,
              updated_at REAL NOT NULL,PRIMARY KEY(tenant_id,provider_id))''',
            '''CREATE TABLE IF NOT EXISTS model_request_bindings(
              tenant_id TEXT NOT NULL,request_id TEXT NOT NULL,
              provider_config_version INTEGER NOT NULL,
              connection_id TEXT,connection_config_version INTEGER,
              expected_input_tokens INTEGER NOT NULL,
              max_output_tokens INTEGER NOT NULL,allow_paid INTEGER NOT NULL,
              writer_fence INTEGER,writer_epoch INTEGER,
              writer_valid_until REAL,skill_snapshot_sha256 TEXT,
              work_spec_sha256 TEXT,module_version TEXT,
              PRIMARY KEY(tenant_id,request_id))''',
            '''CREATE TABLE IF NOT EXISTS model_call_reservations(
              tenant_id TEXT NOT NULL,reservation_id TEXT NOT NULL,
              request_id TEXT NOT NULL,attempt_number INTEGER NOT NULL,
              task_id TEXT NOT NULL,provider_id TEXT NOT NULL,model_id TEXT NOT NULL,
              input_tokens INTEGER NOT NULL,output_tokens INTEGER NOT NULL,
              reserved_cost REAL,cost_state TEXT NOT NULL,state TEXT NOT NULL,
              created_at REAL NOT NULL,settled_at REAL,
              PRIMARY KEY(tenant_id,reservation_id))''',
            '''CREATE TABLE IF NOT EXISTS model_usage_attempts(
              tenant_id TEXT NOT NULL,request_id TEXT NOT NULL,
              attempt_number INTEGER NOT NULL,provider_id TEXT NOT NULL,
              model_id TEXT NOT NULL,input_tokens INTEGER,
              output_tokens INTEGER,cost_state TEXT NOT NULL,cost_value REAL,
              outcome TEXT NOT NULL,observed_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,request_id,attempt_number))''',
            '''CREATE TABLE IF NOT EXISTS approved_skills(
              tenant_id TEXT NOT NULL,skill_id TEXT NOT NULL,
              skill_version TEXT NOT NULL,content_json TEXT NOT NULL,
              content_sha256 TEXT NOT NULL,review_sha256 TEXT NOT NULL,
              state TEXT NOT NULL,updated_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,skill_id,skill_version))''',
            '''CREATE TABLE IF NOT EXISTS role_instances(
              tenant_id TEXT NOT NULL,instance_id TEXT NOT NULL,
              role_id TEXT NOT NULL,role_version TEXT NOT NULL,
              state TEXT NOT NULL,desired_state TEXT NOT NULL,
              current_request_id TEXT,last_checkpoint_json TEXT,
              updated_at REAL NOT NULL,PRIMARY KEY(tenant_id,instance_id))''',
            '''CREATE TABLE IF NOT EXISTS acceptance_checklists(
              tenant_id TEXT NOT NULL,checklist_id TEXT NOT NULL,
              task_id TEXT NOT NULL,attempt_id TEXT NOT NULL,
              content_json TEXT NOT NULL,content_sha256 TEXT NOT NULL,
              all_required_passed INTEGER NOT NULL,has_unexecuted INTEGER NOT NULL,
              created_by TEXT NOT NULL,created_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,checklist_id))''',
        )
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            for statement in statements:
                self.db.execute(statement)

    @staticmethod
    def _origin(value):
        parsed=urlsplit(value)
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        return '%s://%s:%d'%(parsed.scheme.lower(),parsed.hostname.lower(),port)

    def _principal(self):
        self.gateway.tenants.verify(self.context)
        return self.context['principal_id']

    def _admin(self):
        principal = self._principal()
        if not principal.startswith('admin:'):
            raise ValueError('MODEL_ADMIN_REQUIRED')
        return principal

    def _audit(self, principal, action, target, detail, now):
        forbidden=('secret','api_key','token','secret_cipher','authorization')
        def redact(value):
            if isinstance(value,dict):
                return {key:redact(item) for key,item in value.items()
                        if not any(mark in key.lower() for mark in forbidden)}
            if isinstance(value,list):return [redact(item) for item in value]
            return value
        safe = redact(dict(detail))
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
        parsed=urlparse(value['base_url'])
        hostname=(parsed.hostname or '').lower()
        loopback_http=(parsed.scheme=='http' and hostname in
                       ('127.0.0.1','localhost'))
        safe_https=(parsed.scheme=='https' and hostname not in
                    ('localhost','127.0.0.1','::1') and '.' in hostname and
                    not hostname.endswith(('.local','.internal')))
        try:
            address=ipaddress.ip_address(hostname)
            if address.is_private or address.is_loopback or address.is_link_local:
                safe_https=False
        except ValueError:
            pass
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('SAFE_PROVIDER_URL_REQUIRED')
        if not (loopback_http or safe_https):
            raise ValueError('SAFE_PROVIDER_URL_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing = self.db.execute('''SELECT * FROM model_providers
              WHERE tenant_id=? AND provider_id=?''',
              (self.tenant_id,value['provider_id'])).fetchone()
            if value['price_state']=='KNOWN_PAID':
                incompatible=self.db.execute('''SELECT 1 FROM model_catalog WHERE
                  tenant_id=? AND provider_id=? AND (price_state!='KNOWN_PAID' OR
                  input_unit_cost IS NULL OR output_unit_cost IS NULL) LIMIT 1''',(
                  self.tenant_id,value['provider_id'])).fetchone()
                if incompatible is not None:
                    raise ValueError('PAID_PROVIDER_MODELS_REQUIRE_EXPLICIT_COSTS')
            if existing is None and self.db.execute('''SELECT COUNT(*) FROM
              model_providers WHERE tenant_id=?''',(self.tenant_id,)).fetchone()[0] >= 10:
                raise ValueError('PROVIDER_LIMIT_10')
            cipher = existing['secret_cipher'] if existing else None
            mask = existing['secret_mask'] if existing else None
            destination_changed=(existing is not None and
              self._origin(existing['base_url'])!=self._origin(value['base_url']))
            if destination_changed and secret is None:
                # Credentials are destination-bound.  Moving a provider must
                # never silently carry the old bearer secret to a new origin.
                cipher=None;mask=None
            if secret is not None:
                if not isinstance(secret,str) or len(secret)<8 or '\n' in secret or '\r' in secret:
                    raise ValueError('VALID_PROVIDER_SECRET_REQUIRED')
                cipher = self.fernet.encrypt(secret.encode('utf-8'))
                mask = '••••' + secret[-4:]
            version = (existing['config_version'] + 1) if existing else 1
            created = existing['created_at'] if existing else now
            self.db.execute('''INSERT OR REPLACE INTO model_providers VALUES
              (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (self.tenant_id,value['provider_id'],value['display_name'],
               value['adapter_type'],value['base_url'],int(value['enabled']),
               value['price_state'],value['rate_limit_per_min'],
               value['concurrency_limit'],value['timeout_seconds'],
               value['retry_limit'],cipher,mask,version,'CLOSED',0,None,
               created,now))
            self._audit(principal,'PROVIDER_UPSERT',value['provider_id'],
                        {'config_version':version,'secret_replaced':secret is not None,
                         'destination_changed':destination_changed,
                         'reauthorization_required':destination_changed and secret is None},now)
            self.db.commit()
        except Exception:
            self.db.rollback();raise
        return {'provider_id':value['provider_id'],'config_version':version,
                'secret_mask':mask,'secret_configured':cipher is not None}

    def set_runtime_limits(self,provider_id,tpm_limit,max_output_tokens,
                           tenant_budget=None,task_budget=None,now=None):
        self._admin();now=self.clock() if now is None else now
        for name,value in (('tpm_limit',tpm_limit),
                           ('max_output_tokens',max_output_tokens)):
            if type(value) is not int or value<1:
                raise ValueError('VALID_%s_REQUIRED'%name.upper())
        for name,value in (('tenant_budget',tenant_budget),
                           ('task_budget',task_budget)):
            if value is not None:_number(value,name)
        if self.db.execute('''SELECT 1 FROM model_providers WHERE tenant_id=?
          AND provider_id=?''',(self.tenant_id,provider_id)).fetchone() is None:
            raise ValueError('PROVIDER_REQUIRED')
        self.db.execute('''INSERT OR REPLACE INTO model_runtime_limits VALUES
          (?,?,?,?,?,?,?)''',(self.tenant_id,provider_id,tpm_limit,
          max_output_tokens,tenant_budget,task_budget,now));self.db.commit()
        return {'provider_id':provider_id,'tpm_limit':tpm_limit,
                'max_output_tokens':max_output_tokens}

    def register_skill(self,skill_id,skill_version,content,review_sha256,
                       now=None):
        self._admin();now=self.clock() if now is None else now
        _sha(review_sha256,'review_sha256')
        if not isinstance(content,dict) or not content:
            raise ValueError('SKILL_CONTENT_REQUIRED')
        body=canonical(content);digest=hashlib.sha256(body.encode()).hexdigest()
        self.db.execute('''INSERT INTO approved_skills VALUES
          (?,?,?,?,?,?,?,?)''',(self.tenant_id,_text(skill_id,'skill_id'),
          _text(skill_version,'skill_version'),body,digest,review_sha256,
          'APPROVED',now));self.db.commit()
        return {'skill_id':skill_id,'skill_version':skill_version,
                'content_sha256':digest,'state':'APPROVED'}

    def revoke_skill(self,skill_id,skill_version,now=None):
        self._admin();now=self.clock() if now is None else now
        changed=self.db.execute('''UPDATE approved_skills SET state='REVOKED',
          updated_at=? WHERE tenant_id=? AND skill_id=? AND skill_version=?''',
          (now,self.tenant_id,skill_id,skill_version)).rowcount;self.db.commit()
        if changed!=1:raise KeyError(skill_id)
        return {'skill_id':skill_id,'state':'REVOKED'}

    def register_checklist(self,task_id,items,created_by,now=None):
        now=self.clock() if now is None else now
        self.gateway.assert_task_context(self.context,task_id)
        if created_by!=self._principal():raise ValueError('AUTHENTICATED_ACTOR_REQUIRED')
        if not isinstance(items,list) or not items:raise ValueError('CHECKLIST_ITEMS_REQUIRED')
        normalized=[]
        for item in items:
            if (not isinstance(item,dict) or set(item)!=
                    {'id','required','result','evidence'}):
                raise ValueError('EXACT_CHECKLIST_ITEM_REQUIRED')
            if item['result'] not in ('PASS','FAIL','NOT_EXECUTED'):
                raise ValueError('CHECKLIST_RESULT_REQUIRED')
            normalized.append(item)
        body=canonical(normalized);digest=hashlib.sha256(body.encode()).hexdigest()
        task=self.gateway.supervisor._task(task_id)
        checklist_id=hashlib.sha256(canonical({'tenant':self.tenant_id,
          'task':task_id,'attempt':task['attempt_id'],'content':digest}).encode()).hexdigest()
        all_pass=all((not x['required']) or x['result']=='PASS' for x in normalized)
        has_unexecuted=any(x['result']=='NOT_EXECUTED' for x in normalized)
        self.db.execute('''INSERT OR IGNORE INTO acceptance_checklists VALUES
          (?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,checklist_id,task_id,
          task['attempt_id'],body,digest,int(all_pass),int(has_unexecuted),
          created_by,now));self.db.commit()
        return {'checklist_id':checklist_id,'content_sha256':digest,
                'all_required_passed':all_pass,'has_unexecuted':has_unexecuted}

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
        if value['price_state']=='KNOWN_PAID' and (
                value['input_unit_cost'] is None or
                value['output_unit_cost'] is None):
            raise ValueError('KNOWN_PAID_UNIT_COSTS_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            provider=self.db.execute('''SELECT price_state FROM model_providers
              WHERE tenant_id=? AND provider_id=?''',(self.tenant_id,
              value['provider_id'])).fetchone()
            if provider is None:raise ValueError('PROVIDER_REQUIRED')
            if (provider['price_state']=='KNOWN_PAID' and
                    value['price_state']!='KNOWN_PAID'):
                raise ValueError('PAID_PROVIDER_MODEL_MUST_BE_KNOWN_PAID')
            self.db.execute('''INSERT OR REPLACE INTO model_catalog VALUES
              (?,?,?,?,?,?,?,?)''',(self.tenant_id,
              _text(value['provider_id'],'provider_id'),
              _text(value['model_id'],'model_id'),
              canonical(sorted(set(value['capabilities']))),int(value['enabled']),
              value['price_state'],value['input_unit_cost'],value['output_unit_cost']))
            self.db.commit()
        except Exception:
            self.db.rollback();raise
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
        if status!='APPROVED':
            raise ValueError('APPROVED_SKILL_REVIEW_REQUIRED')
        _sha(review_sha256,'review_sha256')
        skill=self.db.execute('''SELECT * FROM approved_skills WHERE tenant_id=?
          AND skill_id=? AND skill_version=? AND state='APPROVED' ''',(
          self.tenant_id,skill_id,skill_version)).fetchone()
        if skill is None or skill['review_sha256']!=review_sha256:
            raise ValueError('APPROVED_SKILL_CONTENT_REQUIRED')
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
        held={r['phase'] for r in self.db.execute('''SELECT rt.phase FROM
          model_assignments a JOIN role_templates rt ON rt.tenant_id=a.tenant_id
          AND rt.role_id=a.role_id AND rt.version=a.role_version WHERE
          a.tenant_id=? AND a.task_id=? AND a.attempt_id=? AND
          a.principal_id=?''',(self.tenant_id,task_id,task['attempt_id'],
          principal_id))}
        if ((role['phase']=='EXECUTOR' and held.intersection({'REVIEWER','ACCEPTOR'}))
                or (role['phase'] in ('REVIEWER','ACCEPTOR') and
                    'EXECUTOR' in held)):
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
        self.db.execute('''INSERT OR IGNORE INTO role_instances VALUES
          (?,?,?,?,?,?,?,?,?)''',(self.tenant_id,principal_id,role_id,role_version,
          'IDLE','RUNNING',None,canonical({'state':'ASSIGNED','task_id':task_id,
          'attempt_id':task['attempt_id']}),now))
        self._audit(self._principal(),'ROLE_ASSIGNED',task_id,
          {'role_id':role_id,'role_version':role_version,
           'principal_id':principal_id,'attempt_id':task['attempt_id']},now)
        self.db.commit();return dict(provider_id=chosen['provider_id'],
          model_id=chosen['model_id'],reason='QUALIFIED_FREE_FINAL_COST' if
          chosen['effective_price']=='KNOWN_FREE' else
          'AUTHORIZED_QUALIFIED_FINAL_COST')

    def queue_request(self, task_id, role_id, messages, idempotency_key,
                      max_output_tokens=None,connection_id=None,now=None):
        now=self.clock() if now is None else now
        self.gateway.assert_task_context(self.context,task_id)
        task=self.gateway.supervisor._task(task_id)
        assignment=self.db.execute('''SELECT * FROM model_assignments WHERE
          tenant_id=? AND task_id=? AND attempt_id=? AND role_id=?''',
          (self.tenant_id,task_id,task['attempt_id'],role_id)).fetchone()
        if assignment is None:raise ValueError('MODEL_ASSIGNMENT_REQUIRED')
        provider=self.db.execute('''SELECT config_version,price_state,enabled
          FROM model_providers WHERE tenant_id=? AND provider_id=?''',(
          self.tenant_id,assignment['provider_id'])).fetchone()
        if provider is None or not provider['enabled']:
            raise ValueError('ACTIVE_PROVIDER_REQUIRED')
        module=self.db.execute('''SELECT * FROM module_settings WHERE tenant_id=?
          AND module_id='xuanjun.scheduler.kernel' ''',(self.tenant_id,)).fetchone()
        if module is not None and not module['enabled']:
            raise ValueError('MODULE_DISABLED')
        spec=self.db.execute('''SELECT goal,deliverables_json,acceptance_json
          FROM task_work_specs WHERE tenant_id=? AND task_id=?''',(
          self.tenant_id,task_id)).fetchone()
        if spec is None:raise ValueError('TASK_WORK_SPEC_REQUIRED')
        spec_body=canonical(dict(spec));spec_sha=hashlib.sha256(spec_body.encode()).hexdigest()
        limits=self.db.execute('''SELECT * FROM model_runtime_limits WHERE
          tenant_id=? AND provider_id=?''',(self.tenant_id,
          assignment['provider_id'])).fetchone()
        output_limit=(limits['max_output_tokens'] if limits is not None else 4096)
        if max_output_tokens is None:max_output_tokens=output_limit
        if type(max_output_tokens) is not int or not 1<=max_output_tokens<=output_limit:
            raise ValueError('OUTPUT_TOKEN_LIMIT_EXCEEDED')
        task_state=self.gateway.supervisor._task(task_id)
        if (task_state['authority_state']!='VALID' or
                task_state['authority_valid_until'] is None or
                not now<task_state['authority_valid_until']):
            raise ValueError('CURRENT_WRITER_AUTHORITY_REQUIRED')
        bindings=list(self.db.execute('''SELECT b.skill_id,b.skill_version,
          s.content_sha256,s.state FROM role_skill_bindings b JOIN approved_skills s
          ON s.tenant_id=b.tenant_id AND s.skill_id=b.skill_id AND
          s.skill_version=b.skill_version WHERE b.tenant_id=? AND b.role_id=?
          AND b.role_version=? AND b.status='APPROVED' ORDER BY b.skill_id''',(
          self.tenant_id,assignment['role_id'],assignment['role_version'])))
        if any(x['state']!='APPROVED' for x in bindings):
            raise ValueError('SKILL_REVOKED')
        skill_sha=(hashlib.sha256(canonical([dict(x) for x in bindings]).encode()).hexdigest()
                   if bindings else None)
        connection_version=None
        if connection_id is not None:
            if self.db.execute('''SELECT 1 FROM sqlite_master WHERE type='table'
              AND name='service_connections' ''').fetchone() is None:
                raise ValueError('CONNECTION_MANAGER_REQUIRED')
            connection=self.db.execute('''SELECT provider_id,config_version,status
              FROM service_connections WHERE tenant_id=? AND connection_id=?''',(
              self.tenant_id,connection_id)).fetchone()
            if (connection is None or connection['status']!='ACTIVE' or
                    connection['provider_id']!=assignment['provider_id']):
                raise ValueError('ACTIVE_PROVIDER_CONNECTION_REQUIRED')
            connection_version=connection['config_version']
        payload={'messages':messages};body=canonical(payload);digest=hashlib.sha256(body.encode()).hexdigest()
        identity={'tenant':self.tenant_id,'task':task_id,
          'attempt':task['attempt_id'],'role':role_id,
          'provider':assignment['provider_id'],'model':assignment['model_id'],
          'idempotency':idempotency_key}
        request_id=hashlib.sha256(canonical(identity).encode()).hexdigest()
        existing=self.db.execute('''SELECT * FROM model_requests
          WHERE tenant_id=? AND idempotency_key=?''',(self.tenant_id,idempotency_key)).fetchone()
        if existing:
            actual=(existing['task_id'],existing['attempt_id'],existing['role_id'],
              existing['provider_id'],existing['model_id'],existing['payload_sha256'])
            expected=(task_id,task['attempt_id'],role_id,
              assignment['provider_id'],assignment['model_id'],digest)
            if actual!=expected:raise ValueError('IDEMPOTENCY_CONFLICT')
            return {'request_id':existing['request_id'],'state':existing['state'],
                    'duplicate':True}
        checkpoint=canonical({'goal':'execute assigned role','input_version':
          task.get('spec_sha256',UNKNOWN),'done':[],'pending':['MODEL_RESULT'],
          'evidence':[]})
        expected_input=max(1,len(body.encode('utf-8'))//4)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('''INSERT INTO model_requests VALUES
              (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,request_id,
              _text(idempotency_key,'idempotency_key'),task_id,task['attempt_id'],
              role_id,assignment['provider_id'],assignment['model_id'],'QUEUED',body,
              digest,0,now,None,None,None,None,None,checkpoint,0,now,now))
            self.db.execute('''INSERT INTO model_request_bindings VALUES
              (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,request_id,
              provider['config_version'],connection_id,connection_version,expected_input,
              max_output_tokens,int(assignment['reason']!='QUALIFIED_FREE_FINAL_COST'),
              task_state['fence'],task_state['epoch'],
              task_state['authority_valid_until'],skill_sha,spec_sha,
              module['version'] if module else 'legacy-test-only'))
            self.db.commit()
        except Exception:
            self.db.rollback();raise
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
            self.db.execute('''UPDATE role_instances SET state=CASE WHEN
              ?='CANCELLED' THEN 'IDLE' ELSE state END,last_checkpoint_json=?,
              updated_at=? WHERE tenant_id=? AND current_request_id=?''',(
              state,canonical({'state':state,'reason':'CANCEL_REQUESTED'}),now,
              self.tenant_id,request_id))
            self._audit(principal,'REQUEST_CANCEL',request_id,
                        {'resulting_state':state},now)
        return {'request_id':request_id,'state':state,
                'cancel_requested':True}

    def _reserve_call_locked(self,provider_id,model_id,request_id,task_id,
                             attempt_number,input_tokens,output_tokens,
                             allow_paid,config_version,now):
        """One transactional gate shared by benchmark and queued calls."""
        provider=self.db.execute('''SELECT * FROM model_providers WHERE
          tenant_id=? AND provider_id=?''',(self.tenant_id,provider_id)).fetchone()
        model=self.db.execute('''SELECT * FROM model_catalog WHERE tenant_id=?
          AND provider_id=? AND model_id=?''',(self.tenant_id,provider_id,
          model_id)).fetchone()
        limits=self.db.execute('''SELECT * FROM model_runtime_limits WHERE
          tenant_id=? AND provider_id=?''',(self.tenant_id,provider_id)).fetchone()
        if provider is None or model is None or not provider['enabled'] or not model['enabled']:
            raise ValueError('ACTIVE_MODEL_REQUIRED')
        if provider['config_version']!=config_version:
            raise ValueError('PROVIDER_CONFIG_CHANGED_REQUEUE_REQUIRED')
        if provider['circuit_state']=='OPEN' and (provider['next_probe_at'] is None or
                                                  provider['next_probe_at']>now):
            raise ValueError('CIRCUIT_OPEN')
        effective=(UNKNOWN if UNKNOWN in (provider['price_state'],model['price_state'])
          else 'KNOWN_PAID' if 'KNOWN_PAID' in
          (provider['price_state'],model['price_state']) else 'KNOWN_FREE')
        if effective!= 'KNOWN_FREE' and not allow_paid:
            raise ValueError('PAID_OR_UNKNOWN_NOT_AUTHORIZED')
        if limits is None:
            tpm_limit=max(1,provider['rate_limit_per_min']*8192)
            output_limit=4096;tenant_budget=None;task_budget=None
        else:
            tpm_limit=limits['tpm_limit'];output_limit=limits['max_output_tokens']
            tenant_budget=limits['tenant_budget'];task_budget=limits['task_budget']
        if output_tokens>output_limit:raise ValueError('OUTPUT_TOKEN_LIMIT_EXCEEDED')
        recent=self.db.execute('''SELECT COUNT(*) AS calls,
          COALESCE(SUM(input_tokens+output_tokens),0) AS tokens FROM
          model_call_reservations WHERE tenant_id=? AND provider_id=? AND
          created_at>?''',(self.tenant_id,provider_id,now-60)).fetchone()
        if recent['calls']>=provider['rate_limit_per_min']:
            raise ValueError('LOCAL_RPM_LIMIT')
        if recent['tokens']+input_tokens+output_tokens>tpm_limit:
            raise ValueError('LOCAL_TPM_LIMIT')
        running=self.db.execute('''SELECT COUNT(*) FROM model_call_reservations
          WHERE tenant_id=? AND provider_id=? AND state='ACTIVE' ''',(
          self.tenant_id,provider_id)).fetchone()[0]
        if running>=provider['concurrency_limit']:
            raise ValueError('LOCAL_CONCURRENCY_LIMIT')
        if effective==UNKNOWN:
            cost_state=UNKNOWN;reserved=None
        elif effective=='KNOWN_FREE':cost_state='KNOWN_ZERO';reserved=0.0
        elif model['input_unit_cost'] is None or model['output_unit_cost'] is None:
            cost_state=UNKNOWN;reserved=None
        else:
            cost_state='KNOWN';reserved=(input_tokens*model['input_unit_cost']+
                                         output_tokens*model['output_unit_cost'])
        if cost_state==UNKNOWN and (tenant_budget is not None or task_budget is not None):
            raise ValueError('UNKNOWN_COST_BUDGET_HOLD')
        known_tenant=self.db.execute('''SELECT COALESCE(SUM(reserved_cost),0)
          FROM model_call_reservations WHERE tenant_id=? AND
          cost_state IN ('KNOWN','KNOWN_ZERO') AND state IN ('ACTIVE','SETTLED')''',
          (self.tenant_id,)).fetchone()[0]
        known_task=self.db.execute('''SELECT COALESCE(SUM(reserved_cost),0)
          FROM model_call_reservations WHERE tenant_id=? AND task_id=? AND
          cost_state IN ('KNOWN','KNOWN_ZERO') AND state IN ('ACTIVE','SETTLED')''',
          (self.tenant_id,task_id)).fetchone()[0]
        if tenant_budget is not None and known_tenant+(reserved or 0)>tenant_budget:
            raise ValueError('TENANT_BUDGET_EXHAUSTED')
        if task_budget is not None and known_task+(reserved or 0)>task_budget:
            raise ValueError('TASK_BUDGET_EXHAUSTED')
        if (tenant_budget is not None and self.db.execute('''SELECT 1 FROM
              model_call_reservations WHERE tenant_id=? AND cost_state=? AND
              state='SETTLED' LIMIT 1''',(self.tenant_id,UNKNOWN)).fetchone()):
            raise ValueError('UNKNOWN_COST_BUDGET_HOLD')
        if (task_budget is not None and self.db.execute('''SELECT 1 FROM
              model_call_reservations WHERE tenant_id=? AND task_id=? AND
              cost_state=? AND state='SETTLED' LIMIT 1''',(
              self.tenant_id,task_id,UNKNOWN)).fetchone()):
            raise ValueError('UNKNOWN_COST_BUDGET_HOLD')
        reservation_id=hashlib.sha256(canonical({'tenant':self.tenant_id,
          'request':request_id,'attempt':attempt_number}).encode()).hexdigest()
        self.db.execute('''INSERT INTO model_call_reservations VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,reservation_id,
          request_id,attempt_number,task_id,provider_id,model_id,input_tokens,
          output_tokens,reserved,cost_state,'ACTIVE',now,None))
        return {'reservation_id':reservation_id,'cost_state':cost_state,
                'reserved_cost':reserved,'provider':provider,'model':model}

    def _settle_reservation_locked(self,reservation_id,state,now,
                                   cost_state=None,cost_value=None):
        if cost_state is None:
            changed=self.db.execute('''UPDATE model_call_reservations SET state=?,
              settled_at=? WHERE tenant_id=? AND reservation_id=? AND
              state='ACTIVE' ''',(state,now,self.tenant_id,reservation_id)).rowcount
        else:
            changed=self.db.execute('''UPDATE model_call_reservations SET state=?,
              settled_at=?,cost_state=?,reserved_cost=? WHERE tenant_id=? AND
              reservation_id=? AND state='ACTIVE' ''',(state,now,cost_state,
              cost_value,self.tenant_id,reservation_id)).rowcount
        if changed!=1:raise ValueError('ACTIVE_RESERVATION_REQUIRED')

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
                      adapter=None, allow_paid=False, now=None):
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
        for index,case in enumerate(cases,1):
            request_id=hashlib.sha256(canonical({'tenant':self.tenant_id,
              'provider':provider_id,'model':model_id,'suite':suite_version,
              'case':case['case_id'],'observed_at':now}).encode()).hexdigest()
            estimated=max(1,len(case['messages_json'].encode())//4)
            try:
                self.db.execute('BEGIN IMMEDIATE')
                reservation=self._reserve_call_locked(provider_id,model_id,
                  request_id,'BENCHMARK:'+suite_version,1,estimated,512,
                  bool(allow_paid),provider['config_version'],now)
                self.db.execute('''INSERT INTO model_call_attempts VALUES
                  (?,?,?,?,?,?,?)''',(self.tenant_id,request_id,1,provider_id,
                  model_id,'benchmark:'+suite_version,now))
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                evidence.append({'case_id':case['case_id'],'passed':False,
                  'error_kind':str(exc)})
                continue
            try:
                result=adapter.invoke(provider['base_url'],secret,model_id,
                  json.loads(case['messages_json']),provider['timeout_seconds'],512)
                ok=case['expected_contains'] in result['content']
                passed+=int(ok);input_tokens+=result['usage']['input_tokens']
                output_tokens+=result['usage']['output_tokens']
                evidence.append({'case_id':case['case_id'],'passed':ok,
                  'provider_request_id':result['provider_request_id']})
            except ProviderError as exc:
                evidence.append({'case_id':case['case_id'],'passed':False,
                  'error_kind':exc.kind})
                result=None
            self.db.execute('BEGIN IMMEDIATE')
            with self.db:
                usage=(result or {}).get('usage') or {}
                outcome=('SUCCEEDED' if result is not None else UNKNOWN)
                if result is None or UNKNOWN in (provider['price_state'],model['price_state']):
                    actual_state=UNKNOWN;actual_cost=None
                elif 'KNOWN_PAID' in (provider['price_state'],model['price_state']):
                    actual_state='KNOWN';actual_cost=(usage.get('input_tokens',0)*
                      model['input_unit_cost']+usage.get('output_tokens',0)*
                      model['output_unit_cost'])
                else:actual_state='KNOWN_ZERO';actual_cost=0.0
                self._settle_reservation_locked(reservation['reservation_id'],
                                                'SETTLED',now,actual_state,actual_cost)
                self.db.execute('''INSERT INTO model_usage_attempts VALUES
                  (?,?,?,?,?,?,?,?,?,?,?)''',(self.tenant_id,request_id,1,
                  provider_id,model_id,usage.get('input_tokens'),
                  usage.get('output_tokens'),actual_state,actual_cost,outcome,now))
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
        if submitted_by!=self._principal():
            raise ValueError('AUTHENTICATED_EXECUTOR_REQUIRED')
        _sha(artifact_sha256,'artifact_sha256')
        _sha(checklist_sha256,'checklist_sha256')
        task=self.gateway.supervisor._task(task_id)
        if task['authority_state']!='VALID' or task['state'] not in ('STARTED','RUNNING'):
            raise ValueError('CURRENT_CANDIDATE_ATTEMPT_REQUIRED')
        in_flight=self.db.execute('''SELECT 1 FROM model_requests WHERE tenant_id=?
          AND task_id=? AND attempt_id=? AND state IN ('RUNNING',?) LIMIT 1''',(
          self.tenant_id,task_id,task['attempt_id'],UNKNOWN)).fetchone()
        if in_flight is not None:raise ValueError('MODEL_SIDE_EFFECT_RECONCILIATION_REQUIRED')
        checklist=self.db.execute('''SELECT * FROM acceptance_checklists WHERE
          tenant_id=? AND task_id=? AND attempt_id=? AND content_sha256=?''',(
          self.tenant_id,task_id,task['attempt_id'],checklist_sha256)).fetchone()
        if checklist is None:raise ValueError('EXECUTED_CHECKLIST_EVIDENCE_REQUIRED')
        if not checklist['all_required_passed'] or checklist['has_unexecuted']:
            raise ValueError('CHECKLIST_INCOMPLETE')
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
          None,'SUBMITTED',canonical([]),now,now))
        self._audit(submitted_by,'CANDIDATE_SUBMITTED',candidate_id,
          {'task_id':task_id,'attempt_id':task['attempt_id'],
           'artifact_sha256':artifact_sha256},now);self.db.commit()
        return {'candidate_id':candidate_id,'state':'SUBMITTED'}

    def review_candidate(self, candidate_id, reviewer, findings, passed,
                         now=None):
        now=self.clock() if now is None else now
        row=self.db.execute('''SELECT * FROM delivery_candidates WHERE
          tenant_id=? AND candidate_id=?''',(self.tenant_id,candidate_id)).fetchone()
        if row is None:raise KeyError(candidate_id)
        task=self.gateway.supervisor._task(row['task_id'])
        if (task['attempt_id']!=row['attempt_id'] or
                task['authority_state']!='VALID' or task['state'] not in ('STARTED','RUNNING')):
            raise ValueError('CURRENT_CANDIDATE_ATTEMPT_REQUIRED')
        if row['state']!='SUBMITTED':
            raise ValueError('SUBMITTED_CANDIDATE_REQUIRED')
        if reviewer!=self._principal():
            raise ValueError('AUTHENTICATED_REVIEWER_REQUIRED')
        if reviewer==row['submitted_by']:raise ValueError('SELF_REVIEW_FORBIDDEN')
        assignment=self.db.execute('''SELECT 1 FROM model_assignments a JOIN
          role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id
          AND r.version=a.role_version WHERE a.tenant_id=? AND a.task_id=? AND
          a.attempt_id=? AND a.principal_id=? AND r.phase='REVIEWER' ''',
          (self.tenant_id,row['task_id'],row['attempt_id'],reviewer)).fetchone()
        if assignment is None:raise ValueError('INDEPENDENT_REVIEW_ASSIGNMENT_REQUIRED')
        if not isinstance(findings,list):raise ValueError('FINDINGS_ARRAY_REQUIRED')
        state='REVIEW_PASSED' if passed and not findings else 'CHANGES_REQUESTED'
        review_body=canonical({'candidate_id':candidate_id,'reviewer':reviewer,
          'decision':state,'findings':findings,'observed_at':now})
        review_id=hashlib.sha256(review_body.encode()).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            changed=self.db.execute('''UPDATE delivery_candidates SET
              reviewed_by=?,state=?,findings_json=?,updated_at=? WHERE
              tenant_id=? AND candidate_id=? AND state='SUBMITTED' ''',
              (reviewer,state,canonical(findings),now,self.tenant_id,
               candidate_id)).rowcount
            if changed!=1:raise ValueError('SUBMITTED_CANDIDATE_REQUIRED')
            self.db.execute('''INSERT INTO candidate_reviews VALUES
              (?,?,?,?,?,?,?)''',(self.tenant_id,candidate_id,review_id,
              reviewer,state,canonical(findings),now))
            self._audit(reviewer,'CANDIDATE_REVIEWED',candidate_id,
              {'decision':state,'finding_count':len(findings)},now)
        return {'candidate_id':candidate_id,'state':state,
                'finding_count':len(findings)}

    def validate_accept_candidate(self, candidate_id, acceptor):
        row=self.db.execute('''SELECT rowid AS candidate_seq,* FROM delivery_candidates WHERE tenant_id=?
          AND candidate_id=?''',(self.tenant_id,candidate_id)).fetchone()
        if row is None:raise KeyError(candidate_id)
        task=self.gateway.supervisor._task(row['task_id'])
        current=((task['attempt_id']==row['attempt_id'] and
                  task['authority_state']=='VALID' and task['state'] in ('STARTED','RUNNING')) or
                 (task['attempt_id']==row['attempt_id'] and
                  task['authority_state']=='REVOKED' and task['state']=='SUCCESS'))
        if not current:
            raise ValueError('CURRENT_CANDIDATE_ATTEMPT_REQUIRED')
        if task['state']=='SUCCESS':
            self._require_terminal_artifact(row)
        if acceptor!=self._principal():
            raise ValueError('AUTHENTICATED_ACCEPTOR_REQUIRED')
        if row['state']!='REVIEW_PASSED':raise ValueError('REVIEW_PASS_REQUIRED')
        newer=self.db.execute('''SELECT 1 FROM delivery_candidates WHERE
          tenant_id=? AND task_id=? AND attempt_id=? AND rowid>?
          LIMIT 1''',(self.tenant_id,row['task_id'],row['attempt_id'],
          row['candidate_seq'])).fetchone()
        if newer is not None:raise ValueError('LATEST_CANDIDATE_REQUIRED')
        if acceptor in (row['submitted_by'],row['reviewed_by']):
            raise ValueError('INDEPENDENT_ACCEPTANCE_REQUIRED')
        assignment=self.db.execute('''SELECT 1 FROM model_assignments a JOIN
          role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id
          AND r.version=a.role_version WHERE a.tenant_id=? AND a.task_id=? AND
          a.attempt_id=? AND a.principal_id=? AND r.phase='ACCEPTOR' ''',
          (self.tenant_id,row['task_id'],row['attempt_id'],acceptor)).fetchone()
        if assignment is None:raise ValueError('ACCEPTOR_ASSIGNMENT_REQUIRED')
        return dict(row)

    def accept_candidate(self, candidate_id, acceptor, now=None):
        now=self.clock() if now is None else now
        row=self.db.execute('''SELECT * FROM delivery_candidates WHERE tenant_id=?
          AND candidate_id=?''',(self.tenant_id,candidate_id)).fetchone()
        if row is None:raise KeyError(candidate_id)
        task=self.gateway.supervisor._task(row['task_id'])
        if (task['attempt_id']!=row['attempt_id'] or task['state']!='SUCCESS'
                or task['authority_state']!='REVOKED'):
            raise ValueError('CANONICAL_TASK_SUCCESS_REQUIRED')
        self._require_terminal_artifact(row)
        if acceptor!=self._principal():
            raise ValueError('AUTHENTICATED_ACCEPTOR_REQUIRED')
        if row['state']!='REVIEW_PASSED':raise ValueError('REVIEW_PASS_REQUIRED')
        newer=self.db.execute('''SELECT 1 FROM delivery_candidates WHERE
          tenant_id=? AND task_id=? AND attempt_id=? AND rowid>(SELECT rowid
          FROM delivery_candidates WHERE tenant_id=? AND candidate_id=?) LIMIT 1''',(
          self.tenant_id,row['task_id'],row['attempt_id'],self.tenant_id,
          candidate_id)).fetchone()
        if newer is not None:raise ValueError('LATEST_CANDIDATE_REQUIRED')
        if acceptor in (row['submitted_by'],row['reviewed_by']):
            raise ValueError('INDEPENDENT_ACCEPTANCE_REQUIRED')
        assignment=self.db.execute('''SELECT 1 FROM model_assignments a JOIN
          role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id
          AND r.version=a.role_version WHERE a.tenant_id=? AND a.task_id=? AND
          a.attempt_id=? AND a.principal_id=? AND r.phase='ACCEPTOR' ''',
          (self.tenant_id,row['task_id'],row['attempt_id'],acceptor)).fetchone()
        if assignment is None:raise ValueError('ACCEPTOR_ASSIGNMENT_REQUIRED')
        changed=self.db.execute('''UPDATE delivery_candidates SET accepted_by=?,
          state='ACCEPTED',updated_at=? WHERE tenant_id=? AND candidate_id=?
          AND state='REVIEW_PASSED' ''',(acceptor,now,self.tenant_id,
          candidate_id)).rowcount;self.db.commit()
        if changed!=1:raise ValueError('REVIEW_PASS_REQUIRED')
        self._audit(acceptor,'CANDIDATE_ACCEPTED',candidate_id,
          {'task_id':row['task_id'],'attempt_id':row['attempt_id']},now)
        self.db.commit()
        return {'candidate_id':candidate_id,'state':'ACCEPTED'}

    def _require_terminal_artifact(self, candidate):
        rows=self.db.execute('''SELECT payload_json FROM outbox WHERE task_id=?
          AND attempt_id=?''',(candidate['task_id'],candidate['attempt_id']))
        for row in rows:
            try:payload=json.loads(row['payload_json'])
            except Exception:continue
            if (payload.get('state')=='SUCCESS' and
                    payload.get('artifact_sha256')==candidate['artifact_sha256']):
                return
        raise ValueError('CANONICAL_ARTIFACT_MISMATCH')

    def set_module(self,module_id,version,enabled,now=None):
        self._admin();now=self.clock() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''INSERT OR REPLACE INTO module_settings VALUES
              (?,?,?,?,?)''',(self.tenant_id,_text(module_id,'module_id'),
              int(bool(enabled)),_text(version,'version'),now))
            if not enabled and module_id=='xuanjun.scheduler.kernel':
                self.db.execute('''UPDATE model_requests SET state='CANCELLED',
                  error_kind='MODULE_DISABLED',updated_at=? WHERE tenant_id=?
                  AND state IN ('QUEUED','RETRY_WAIT')''',(now,self.tenant_id))
                self.db.execute('''UPDATE role_instances SET desired_state='STOPPED',
                  state=CASE WHEN current_request_id IS NULL THEN 'STOPPED'
                  ELSE 'DRAINING' END,updated_at=? WHERE tenant_id=?''',(
                  now,self.tenant_id))
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
        has_connections=self.db.execute('''SELECT 1 FROM sqlite_master WHERE
          type='table' AND name='service_connections' ''').fetchone() is not None
        return {'providers':self.list_providers(),
          'connections':([dict(x) for x in self.db.execute('''SELECT
          connection_id,provider_id,purpose,auth_type,destination_origin,issuer,
          scopes_json,supports_refresh,status,config_version,secret_mask,
          access_expires_at,updated_at FROM service_connections WHERE tenant_id=?
          ORDER BY connection_id''',(self.tenant_id,))] if has_connections else []),
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
          'usage_attempts':[dict(x) for x in self.db.execute('''SELECT
          request_id,attempt_number,provider_id,model_id,input_tokens,
          output_tokens,cost_state,cost_value,outcome,observed_at FROM
          model_usage_attempts WHERE tenant_id=? ORDER BY observed_at,
          request_id,attempt_number''',(self.tenant_id,))],
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
          'candidate_reviews':[dict(x) for x in self.db.execute('''SELECT
          candidate_id,review_id,reviewer,decision,findings_json,observed_at
          FROM candidate_reviews WHERE tenant_id=? ORDER BY observed_at,
          review_id''',(self.tenant_id,))],
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
        candidates=list(self.db.execute('''SELECT r.*,b.provider_config_version,
          b.connection_id,b.connection_config_version,b.expected_input_tokens,
          b.max_output_tokens,b.allow_paid,b.writer_fence,b.writer_epoch,
          b.writer_valid_until,b.skill_snapshot_sha256,b.work_spec_sha256,
          b.module_version,p.adapter_type,p.base_url,p.timeout_seconds,
          p.retry_limit,p.config_version,p.price_state AS provider_price,
          m.price_state AS model_price,m.input_unit_cost,m.output_unit_cost,
          a.principal_id AS instance_id
          FROM model_requests r JOIN
          model_request_bindings b ON b.tenant_id=r.tenant_id AND
          b.request_id=r.request_id JOIN model_providers p ON
          r.tenant_id=p.tenant_id AND r.provider_id=p.provider_id JOIN
          model_catalog m ON m.tenant_id=r.tenant_id AND
          m.provider_id=r.provider_id AND m.model_id=r.model_id JOIN
          model_assignments a ON a.tenant_id=r.tenant_id AND a.task_id=r.task_id
          AND a.attempt_id=r.attempt_id AND a.role_id=r.role_id WHERE
          r.tenant_id=? AND r.state IN ('QUEUED','RETRY_WAIT') AND
          r.next_attempt_at<=? ORDER BY r.created_at,r.request_id LIMIT 100''',
          (self.control.tenant_id,now)))
        if not candidates:return {'state':'IDLE'}
        row=None;reservation=None;last_limit=None
        for candidate in candidates:
            task=self.control.gateway.supervisor._task(candidate['task_id'])
            fatal=None
            if (candidate['cancel_requested'] or task['attempt_id']!=candidate['attempt_id'] or
                task['authority_state']!='VALID' or
                task['authority_valid_until'] is None or now>=task['authority_valid_until'] or
                task['fence']!=candidate['writer_fence'] or
                task['epoch']!=candidate['writer_epoch']):
                fatal='STALE_OR_UNAUTHORIZED'
            elif candidate['config_version']!=candidate['provider_config_version']:
                fatal='PROVIDER_CONFIG_CHANGED_REQUEUE_REQUIRED'
            else:
                module=self.db.execute('''SELECT enabled,version FROM module_settings
                  WHERE tenant_id=? AND module_id='xuanjun.scheduler.kernel' ''',(
                  candidate['tenant_id'],)).fetchone()
                if module is not None and (not module['enabled'] or
                        module['version']!=candidate['module_version']):
                    fatal='MODULE_DISABLED_OR_VERSION_CHANGED'
                spec=self.db.execute('''SELECT goal,deliverables_json,acceptance_json
                  FROM task_work_specs WHERE tenant_id=? AND task_id=?''',(
                  candidate['tenant_id'],candidate['task_id'])).fetchone()
                current_spec=(hashlib.sha256(canonical(dict(spec)).encode()).hexdigest()
                              if spec is not None else None)
                if current_spec!=candidate['work_spec_sha256']:
                    fatal='WORK_SPEC_CHANGED'
                assignment=self.db.execute('''SELECT role_version FROM
                  model_assignments WHERE tenant_id=? AND task_id=? AND
                  attempt_id=? AND role_id=?''',(candidate['tenant_id'],
                  candidate['task_id'],candidate['attempt_id'],
                  candidate['role_id'])).fetchone()
                if assignment is None:fatal='ASSIGNMENT_REVOKED'
                else:
                    skills=list(self.db.execute('''SELECT b.skill_id,b.skill_version,
                      s.content_sha256,s.state FROM role_skill_bindings b JOIN
                      approved_skills s ON s.tenant_id=b.tenant_id AND
                      s.skill_id=b.skill_id AND s.skill_version=b.skill_version
                      WHERE b.tenant_id=? AND b.role_id=? AND b.role_version=?
                      AND b.status='APPROVED' ORDER BY b.skill_id''',(
                      candidate['tenant_id'],candidate['role_id'],
                      assignment['role_version'])))
                    current_skill=(hashlib.sha256(canonical([dict(x) for x in skills]).encode()).hexdigest()
                                   if skills else None)
                    if current_skill!=candidate['skill_snapshot_sha256'] or any(
                            x['state']!='APPROVED' for x in skills):
                        fatal='SKILL_SNAPSHOT_REVOKED_OR_CHANGED'
                if candidate['connection_id']:
                    connection=self.db.execute('''SELECT status,config_version,
                      provider_id FROM service_connections WHERE tenant_id=? AND
                      connection_id=?''',(candidate['tenant_id'],
                      candidate['connection_id'])).fetchone()
                    if (connection is None or connection['status']!='ACTIVE' or
                            connection['config_version']!=candidate['connection_config_version'] or
                            connection['provider_id']!=candidate['provider_id']):
                        fatal='CONNECTION_REAUTH_OR_CONFIG_CHANGED'
            if fatal:
                last_limit=fatal
                self.db.execute('''UPDATE model_requests SET state='HOLD',error_kind=?,
                  updated_at=? WHERE tenant_id=? AND request_id=? AND state IN
                  ('QUEUED','RETRY_WAIT')''',(fatal,now,candidate['tenant_id'],
                  candidate['request_id']));self.db.commit();continue
            try:
                self.db.execute('BEGIN IMMEDIATE')
                fresh=self.db.execute('''SELECT state,cancel_requested FROM
                  model_requests WHERE tenant_id=? AND request_id=?''',(
                  candidate['tenant_id'],candidate['request_id'])).fetchone()
                if fresh is None or fresh['state'] not in ('QUEUED','RETRY_WAIT'):
                    raise ValueError('LOST_RACE')
                if fresh['cancel_requested']:raise ValueError('CANCELLED_BEFORE_CALL')
                reservation=self.control._reserve_call_locked(
                  candidate['provider_id'],candidate['model_id'],
                  candidate['request_id'],candidate['task_id'],
                  candidate['attempts']+1,candidate['expected_input_tokens'],
                  candidate['max_output_tokens'],bool(candidate['allow_paid']),
                  candidate['provider_config_version'],now)
                changed=self.db.execute('''UPDATE model_requests SET state='RUNNING',
                  attempts=attempts+1,lease_owner=?,lease_until=?,last_heartbeat=?,
                  updated_at=? WHERE tenant_id=? AND request_id=? AND state IN
                  ('QUEUED','RETRY_WAIT') AND cancel_requested=0''',(self.worker_id,
                  now+candidate['timeout_seconds']+5,now,now,candidate['tenant_id'],
                  candidate['request_id'])).rowcount
                if changed!=1:raise ValueError('LOST_RACE')
                self.db.execute('''INSERT INTO model_call_attempts VALUES
                  (?,?,?,?,?,?,?)''',(candidate['tenant_id'],candidate['request_id'],
                  candidate['attempts']+1,candidate['provider_id'],
                  candidate['model_id'],self.worker_id,now))
                self.db.execute('''UPDATE role_instances SET state='RUNNING',
                  current_request_id=?,last_checkpoint_json=?,updated_at=? WHERE
                  tenant_id=? AND instance_id=? AND desired_state='RUNNING' ''',(
                  candidate['request_id'],canonical({'state':'CALL_RESERVED',
                  'request_id':candidate['request_id'],'attempt_number':
                  candidate['attempts']+1}),now,candidate['tenant_id'],
                  candidate['instance_id']))
                self.db.commit();row=candidate;break
            except ValueError as exc:
                self.db.rollback();last_limit=str(exc)
                if str(exc) not in ('LOCAL_RPM_LIMIT','LOCAL_TPM_LIMIT',
                                    'LOCAL_CONCURRENCY_LIMIT','CIRCUIT_OPEN',
                                    'TENANT_BUDGET_EXHAUSTED','TASK_BUDGET_EXHAUSTED'):
                    self.db.execute('''UPDATE model_requests SET state='HOLD',
                      error_kind=?,updated_at=? WHERE tenant_id=? AND request_id=?
                      AND state IN ('QUEUED','RETRY_WAIT')''',(str(exc),now,
                      candidate['tenant_id'],candidate['request_id']));self.db.commit()
                continue
        if row is None:
            return {'state':last_limit if last_limit=='CIRCUIT_OPEN' else
                    ('HOLD' if last_limit not in (None,'LOCAL_RPM_LIMIT',
                    'LOCAL_TPM_LIMIT','LOCAL_CONCURRENCY_LIMIT',
                    'TENANT_BUDGET_EXHAUSTED','TASK_BUDGET_EXHAUSTED') else
                    'QUEUED_LIMIT'),'reason':last_limit}
        if row['connection_id']:
            secret,connection_version=ConnectionManager(self.control.gateway,
              self.control.context,self.control.master_key).credential(
              row['connection_id'],row['base_url'],now)
            if (row['connection_config_version'] is not None and
                    connection_version!=row['connection_config_version']):
                self._finish(row,UNKNOWN,'CONNECTION_CONFIG_CHANGED',None,now,
                             reservation['reservation_id'])
                return {'request_id':row['request_id'],'state':UNKNOWN,
                        'error':'CONNECTION_CONFIG_CHANGED'}
        else:secret=self.control.provider_secret(row['provider_id'])
        payload=json.loads(row['payload_json'])
        adapter=self.adapters[row['adapter_type']]
        try:
            result=adapter.invoke(row['base_url'],secret,row['model_id'],
                                  payload['messages'],row['timeout_seconds'],
                                  row['max_output_tokens'])
        except ProviderError as exc:
            attempts=row['attempts']+1
            if exc.kind in ('TIMEOUT_UNKNOWN','TRANSPORT_UNKNOWN'):
                stored=self._finish(row,UNKNOWN,exc.kind,None,now,
                                    reservation['reservation_id'])
                return {'request_id':row['request_id'],'state':UNKNOWN,
                        'error':exc.kind if stored else 'LATE_WORKER_RESULT_REJECTED'}
            if exc.kind=='RATE_LIMIT' and attempts<=row['retry_limit']:
                self.db.execute('BEGIN IMMEDIATE')
                cancelled=self.db.execute('''SELECT cancel_requested FROM model_requests
                  WHERE tenant_id=? AND request_id=?''',(row['tenant_id'],
                  row['request_id'])).fetchone()['cancel_requested']
                next_state='CANCELLED' if cancelled else 'RETRY_WAIT'
                changed=self.db.execute('''UPDATE model_requests SET state=?,
                  error_kind=?,next_attempt_at=?,lease_owner=NULL,
                  lease_until=NULL,updated_at=? WHERE tenant_id=?
                  AND request_id=? AND state='RUNNING' AND lease_owner=?
                  AND attempts=?''',
                  (next_state,'CANCELLED_AFTER_RATE_LIMIT' if cancelled else exc.kind,
                  now+min(60,2**attempts),now,
                  row['tenant_id'],row['request_id'],self.worker_id,
                  row['attempts']+1)).rowcount
                if changed==1:
                    self.control._settle_reservation_locked(
                      reservation['reservation_id'],'CANCELLED' if cancelled else
                      'SETTLED',now,UNKNOWN,None)
                    self.db.execute('''INSERT INTO model_usage_attempts VALUES
                      (?,?,?,?,?,?,?,?,?,?,?)''',(row['tenant_id'],row['request_id'],
                      row['attempts']+1,row['provider_id'],row['model_id'],None,
                      None,UNKNOWN,None,next_state,now))
                self.db.commit()
                if changed!=1:
                    return {'request_id':row['request_id'],'state':UNKNOWN,
                            'error':'LATE_WORKER_RESULT_REJECTED'}
                return {'request_id':row['request_id'],'state':next_state,'error':exc.kind}
            # Any 5xx is an already-sent POST with an unknown side effect.
            terminal=UNKNOWN if exc.kind=='HTTP' else 'FAILED'
            stored=self._finish(row,terminal,exc.kind,None,now,
                                reservation['reservation_id'])
            return {'request_id':row['request_id'],
                    'state':terminal if stored else UNKNOWN,
                    'error':exc.kind if stored else 'LATE_WORKER_RESULT_REJECTED'}
        stored=self._finish(row,'SUCCEEDED',None,result,now,
                            reservation['reservation_id'])
        return {'request_id':row['request_id'],
                'state':'SUCCEEDED' if stored else UNKNOWN,
                'error':None if stored else 'LATE_WORKER_RESULT_REJECTED'}

    def _finish(self,row,state,error,result,now,reservation_id=None):
        usage=(result or {}).get('usage',{})
        prices=(row['provider_price'],row['model_price'])
        if result is None or UNKNOWN in prices:
            cost_state=UNKNOWN;cost_value=None
        elif 'KNOWN_PAID' in prices:
            if row['input_unit_cost'] is None or row['output_unit_cost'] is None:
                cost_state=UNKNOWN;cost_value=None
            else:
                cost_state='KNOWN'
                cost_value=(usage.get('input_tokens',0) * row['input_unit_cost'] +
                            usage.get('output_tokens',0) * row['output_unit_cost'])
        else:
            cost_state='KNOWN_ZERO';cost_value=0
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            changed=self.db.execute('''UPDATE model_requests SET state=?,result_json=?,
              error_kind=?,lease_owner=NULL,lease_until=NULL,updated_at=?
              WHERE tenant_id=? AND request_id=? AND state='RUNNING' AND
              lease_owner=? AND attempts=?''',
              (state,canonical(result) if result else None,error,now,
               row['tenant_id'],row['request_id'],self.worker_id,
               row['attempts']+1)).rowcount
            if changed!=1:
                return False
            if reservation_id is None:
                raise ValueError('CALL_RESERVATION_REQUIRED')
            self.control._settle_reservation_locked(reservation_id,'SETTLED',now,
                                                    cost_state,cost_value)
            self.db.execute('''INSERT INTO model_usage_attempts VALUES
              (?,?,?,?,?,?,?,?,?,?,?)''',(row['tenant_id'],row['request_id'],
              row['attempts']+1,row['provider_id'],row['model_id'],
              usage.get('input_tokens') if result else None,
              usage.get('output_tokens') if result else None,cost_state,
              cost_value,state,now))
            self.db.execute('''INSERT OR REPLACE INTO model_usage_events VALUES
              (?,?,?,?,?,?,?,?,?,?)''',(row['tenant_id'],row['request_id'],
               row['provider_id'],row['model_id'],usage.get('input_tokens',0),
               usage.get('output_tokens',0),cost_state,cost_value,
               state,now))
            self.db.execute('''UPDATE role_instances SET state=CASE WHEN
              desired_state='STOPPED' THEN 'STOPPED' ELSE 'IDLE' END,
              current_request_id=NULL,last_checkpoint_json=?,updated_at=? WHERE
              tenant_id=? AND instance_id=? AND current_request_id=?''',(
              canonical({'state':state,'request_id':row['request_id'],
              'error_kind':error,'result_present':result is not None}),now,
              row['tenant_id'],row['instance_id'],row['request_id']))
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
        return True
