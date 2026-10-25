"""Persistent TEST_ONLY Codex SDK/App Server execution adapter.

This module owns no task truth and no second queue. It stores send intent and
transport receipts in the canonical task-center SQLite database, and validates
the current task/attempt/writer snapshot before each state transition.
"""
from __future__ import print_function

import hashlib
import json
import select
import subprocess
import time

from task_supervisor import UNKNOWN,canonical
from reusable_task_gateway import _sha
from execution_policy_gateway import ExecutionPolicyGateway


STATES=frozenset(('PENDING','SENDING','ACKED','RUNNING','WAITING_APPROVAL',
  'SUCCEEDED','FAILED','CANCEL_REQUESTED','CANCELLED',UNKNOWN))


class CodexTransportUnavailable(Exception):pass
class CodexSendUnknown(Exception):pass


class CodexSDKTransport(object):
    """Adapter boundary for the official Codex SDK.

    The callable is injected in isolation tests. A real deployment must supply
    the installed official SDK; this repository does not install it.
    """
    kind='CODEX_SDK'
    def __init__(self,runner=None):self.runner=runner
    def send(self,intent):
        if self.runner is None:raise CodexTransportUnavailable('CODEX_SDK_NOT_INSTALLED')
        return self.runner(intent)


class CodexAppServerTransport(object):
    """Concrete stdio JSON-RPC adapter for a fixed app-server command."""
    kind='CODEX_APP_SERVER'
    def __init__(self,exchange=None,command=None,timeout=5):
        self.exchange=exchange;self.command=command;self.timeout=timeout
        self.processes={}
    def _rpc(self,proc,request):
        proc.stdin.write((canonical(request)+'\n').encode('utf-8'));proc.stdin.flush()
        ready,_,_=select.select([proc.stdout],[],[],self.timeout)
        if not ready:raise CodexSendUnknown('APP_SERVER_TIMEOUT')
        line=proc.stdout.readline()
        if not line:raise CodexSendUnknown('APP_SERVER_EOF')
        value=json.loads(line.decode('utf-8'))
        if value.get('id')!=request.get('id') or 'error' in value:
            raise CodexSendUnknown('APP_SERVER_RPC_ERROR')
        return value.get('result') or {}
    def send(self,intent):
        if self.exchange is not None:return self.exchange(intent)
        if not self.command:
            raise CodexTransportUnavailable('CODEX_APP_SERVER_NOT_CONFIGURED')
        if (not isinstance(self.command,(list,tuple)) or not self.command or
                any(not isinstance(x,str) or not x for x in self.command)):
            raise CodexTransportUnavailable('FIXED_APP_SERVER_COMMAND_REQUIRED')
        proc=subprocess.Popen(list(self.command),stdin=subprocess.PIPE,
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
        try:
            self._rpc(proc,{'jsonrpc':'2.0','id':1,'method':'initialize',
              'params':{'clientInfo':{'name':'xuanjun-task-center','version':'r6'}}})
            proc.stdin.write((canonical({'jsonrpc':'2.0','method':'initialized',
              'params':{}})+'\n').encode('utf-8'));proc.stdin.flush()
            context=json.loads(intent['context_json'])
            if intent.get('thread_id'):
                self._rpc(proc,{'jsonrpc':'2.0','id':2,'method':'thread/resume',
                  'params':{'threadId':intent['thread_id']}})
                thread_id=intent['thread_id']
            else:
                thread=self._rpc(proc,{'jsonrpc':'2.0','id':2,
                  'method':'thread/start','params':{'metadata':{'task_id':
                  intent['task_id'],'attempt_id':intent['attempt_id']}}})
                thread_id=thread.get('threadId') or thread.get('id')
            if not thread_id:raise CodexSendUnknown('APP_SERVER_THREAD_ID_REQUIRED')
            turn=self._rpc(proc,{'jsonrpc':'2.0','id':3,'method':'turn/start',
              'params':{'threadId':thread_id,'input':[{'type':'text','text':
              canonical(context)}]}})
            turn_id=turn.get('turnId') or turn.get('id')
            if not turn_id:raise CodexSendUnknown('APP_SERVER_TURN_ID_REQUIRED')
            self.processes[thread_id]=proc
            return {'state':'RUNNING','execution_id':turn_id,
              'session_id':thread_id,'thread_id':thread_id,'turn_id':turn_id}
        except Exception:
            if proc.poll() is None:proc.terminate()
            raise
    def cancel(self,intent):
        proc=self.processes.get(intent.get('thread_id'))
        if proc is None or proc.poll() is not None:
            raise CodexSendUnknown('CANCEL_TRANSPORT_STATE_UNKNOWN')
        self._rpc(proc,{'jsonrpc':'2.0','id':4,'method':'turn/interrupt',
          'params':{'threadId':intent['thread_id'],'turnId':intent['turn_id']}})
        return {'state':'CANCELLED','thread_id':intent['thread_id'],
          'turn_id':intent['turn_id']}
    def reconcile(self,intent):
        if self.exchange is not None:
            return self.exchange(dict(intent,reconcile_only=True))
        if not self.command or not intent.get('thread_id'):
            raise CodexTransportUnavailable('APP_SERVER_RECONCILE_NOT_CONFIGURED')
        proc=subprocess.Popen(list(self.command),stdin=subprocess.PIPE,
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
        try:
            self._rpc(proc,{'jsonrpc':'2.0','id':1,'method':'initialize',
              'params':{'clientInfo':{'name':'xuanjun-task-center','version':'r6'}}})
            proc.stdin.write((canonical({'jsonrpc':'2.0','method':'initialized',
              'params':{}})+'\n').encode('utf-8'));proc.stdin.flush()
            self._rpc(proc,{'jsonrpc':'2.0','id':2,'method':'thread/resume',
              'params':{'threadId':intent['thread_id']}})
            self.processes[intent['thread_id']]=proc
            return {'state':'ACKED','execution_id':intent.get('execution_id'),
              'session_id':intent.get('session_id'),'thread_id':intent['thread_id'],
              'turn_id':intent.get('turn_id')}
        except Exception:
            if proc.poll() is None:proc.terminate()
            raise


class CodexExecutionControl(object):
    def __init__(self,gateway,context,clock=None):
        self.gateway=gateway;self.db=gateway.db;self.context=context
        self.tenant_id=gateway.tenants.verify(context);self.clock=clock or time.time
        self._schema()

    def _schema(self):
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS codex_execution_intents(
              tenant_id TEXT NOT NULL,intent_id TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,task_id TEXT NOT NULL,
              attempt_id TEXT NOT NULL,transport_kind TEXT NOT NULL,
              requesting_principal TEXT,
              writer_principal TEXT NOT NULL,writer_fence INTEGER NOT NULL,
              writer_epoch INTEGER NOT NULL,writer_valid_until REAL NOT NULL,
              state TEXT NOT NULL,context_json TEXT NOT NULL,
              execution_id TEXT,session_id TEXT,thread_id TEXT,turn_id TEXT,
              artifact_sha256 TEXT,error_kind TEXT,cancel_requested INTEGER NOT NULL,
              lease_owner TEXT,lease_until REAL,created_at REAL NOT NULL,
              updated_at REAL NOT NULL,PRIMARY KEY(tenant_id,intent_id),
              UNIQUE(tenant_id,idempotency_key))''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS codex_execution_events(
              tenant_id TEXT NOT NULL,intent_id TEXT NOT NULL,event_id TEXT NOT NULL,
              event_kind TEXT NOT NULL,payload_json TEXT NOT NULL,
              accepted INTEGER NOT NULL,observed_at REAL NOT NULL,
              PRIMARY KEY(tenant_id,intent_id,event_id))''')
            columns={row['name'] for row in self.db.execute(
              'PRAGMA table_info(codex_execution_intents)')}
            if 'requesting_principal' not in columns:
                self.db.execute('''ALTER TABLE codex_execution_intents ADD COLUMN
                  requesting_principal TEXT''')
            for name,kind in (('connection_id','TEXT'),
                              ('connection_config_version','INTEGER'),
                              ('provider_id','TEXT'),('quota_verified_at','REAL')):
                if name not in columns:self.db.execute(
                  'ALTER TABLE codex_execution_intents ADD COLUMN %s %s'%(name,kind))

    def _actor_allowed(self,task_id,attempt_id,principal,writer_principal):
        unit=self.db.execute('''SELECT responsible_party FROM execution_units
          WHERE tenant_id=? AND task_id=?''',(self.tenant_id,task_id)).fetchone()
        if principal==writer_principal or (unit is not None and
                principal==unit['responsible_party']):
            return True
        if self.db.execute('''SELECT 1 FROM sqlite_master WHERE type='table' AND
          name='model_assignments' ''').fetchone() is None:
            return False
        return self.db.execute('''SELECT 1 FROM model_assignments a JOIN
          role_templates r ON r.tenant_id=a.tenant_id AND r.role_id=a.role_id
          AND r.version=a.role_version WHERE a.tenant_id=? AND a.task_id=? AND
          a.attempt_id=? AND a.principal_id=? AND a.state='ASSIGNED' AND
          r.phase='EXECUTOR' AND r.writer_allowed=1 AND r.enabled=1''',(
          self.tenant_id,task_id,attempt_id,principal)).fetchone() is not None

    @staticmethod
    def _quota_allows_zero_new_spend(row,now):
        if row is None:return False
        source=row['quota_source']
        attributable=(source in ('EXISTING_SUBSCRIPTION_INCLUDED',
          'VERIFIED_FREE_TIER') or (isinstance(source,str) and
          source.startswith('TEST_ONLY_INCLUDED_')))
        return (row['quota_state']=='AVAILABLE' and attributable and
          row['verified_at'] is not None and now-row['verified_at']<=3600)

    def create_intent(self,task_id,transport_kind,idempotency_key,context,now=None):
        now=self.clock() if now is None else now
        self.gateway.assert_task_context(self.context,task_id)
        if transport_kind not in ('CODEX_SDK','CODEX_APP_SERVER'):
            raise ValueError('CODEX_TRANSPORT_REQUIRED')
        if not isinstance(context,dict) or set(context)!={'goal','scope',
              'acceptance','asset_version','reuse_evidence','connection_id',
              'provider_id'}:
            raise ValueError('EXACT_CODEX_CONTEXT_REQUIRED')
        ready=ExecutionPolicyGateway(self.gateway,
          self.context).require_dispatch_ready(task_id)
        task=self.gateway.supervisor._task(task_id)
        if (task['attempt_id'] in (None,UNKNOWN) or task['authority_state']!='VALID'
                or task['authority_valid_until'] is None or
                now>=task['authority_valid_until']):
            raise ValueError('CURRENT_WRITER_AUTHORITY_REQUIRED')
        unit=self.db.execute('''SELECT * FROM execution_units WHERE tenant_id=?
          AND task_id=?''',(self.tenant_id,task_id)).fetchone()
        spec=self.db.execute('''SELECT goal,acceptance_json FROM task_work_specs
          WHERE tenant_id=? AND task_id=?''',(self.tenant_id,task_id)).fetchone()
        preflight=self.db.execute('''SELECT query_ids_json FROM dispatch_preflights
          WHERE tenant_id=? AND task_id=? AND preflight_id=?''',(
          self.tenant_id,task_id,ready['preflight_id'])).fetchone()
        principal=self.context['principal_id']
        if not self._actor_allowed(task_id,task['attempt_id'],principal,
                                   task['authority_caller_id']):
            raise ValueError('CURRENT_ASSIGNED_CODEX_ACTOR_REQUIRED')
        expected_reuse=sorted(json.loads(preflight['query_ids_json']))
        supplied_reuse=(sorted(context['reuse_evidence']) if isinstance(
          context['reuse_evidence'],list) else None)
        if (context['goal']!=unit['goal'] or context['goal']!=spec['goal'] or
                canonical(context['scope'])!=unit['scope_json'] or
                canonical(context['acceptance'])!=unit['acceptance_json'] or
                canonical(context['acceptance'])!=spec['acceptance_json'] or
                context['asset_version']!=unit['asset_version'] or
                context['asset_version']!=ready['asset_version'] or
                supplied_reuse!=expected_reuse):
            raise ValueError('CODEX_CONTEXT_NOT_CANONICAL')
        if expected_reuse:
            placeholders=','.join(['?']*len(expected_reuse))
            found=self.db.execute('''SELECT COUNT(*) FROM asset_query_receipts
              WHERE tenant_id=? AND task_id=? AND query_id IN (%s)'''%
              placeholders,(self.tenant_id,task_id)+tuple(
              expected_reuse)).fetchone()[0]
            if found!=len(set(expected_reuse)):
                raise ValueError('CODEX_REUSE_EVIDENCE_REQUIRED')
        connection=self.db.execute('''SELECT provider_id,purpose,status,
          config_version FROM service_connections WHERE tenant_id=? AND
          connection_id=?''',(self.tenant_id,context['connection_id'])).fetchone()
        quota=self.db.execute('''SELECT quota_state,quota_source,verified_at FROM
          model_quota_status WHERE tenant_id=? AND provider_id=?''',(
          self.tenant_id,context['provider_id'])).fetchone()
        if (connection is None or connection['provider_id']!=context['provider_id'] or
                connection['purpose']!='CODEX_EXECUTION' or connection['status']!='ACTIVE'):
            raise ValueError('ACTIVE_CODEX_CONNECTION_REQUIRED')
        if not self._quota_allows_zero_new_spend(quota,now):
            raise ValueError('CODEX_QUOTA_UNKNOWN_OR_UNAVAILABLE')
        seed=canonical({'tenant':self.tenant_id,'task':task_id,
          'attempt':task['attempt_id'],'idempotency':idempotency_key})
        intent_id=hashlib.sha256(seed.encode()).hexdigest()
        existing=self.db.execute('''SELECT * FROM codex_execution_intents WHERE
          tenant_id=? AND idempotency_key=?''',(self.tenant_id,
          idempotency_key)).fetchone()
        if existing:
            if existing['intent_id']!=intent_id or existing['context_json']!=canonical(context):
                raise ValueError('CODEX_IDEMPOTENCY_CONFLICT')
            return {'intent_id':intent_id,'state':existing['state'],'duplicate':True}
        self.db.execute('''INSERT INTO codex_execution_intents(
          tenant_id,intent_id,idempotency_key,task_id,attempt_id,transport_kind,
          requesting_principal,writer_principal,writer_fence,writer_epoch,
          writer_valid_until,state,context_json,execution_id,session_id,thread_id,
          turn_id,artifact_sha256,error_kind,cancel_requested,lease_owner,
          lease_until,created_at,updated_at,connection_id,
          connection_config_version,provider_id,quota_verified_at) VALUES
          (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
          self.tenant_id,intent_id,idempotency_key,task_id,task['attempt_id'],
          transport_kind,principal,task['authority_caller_id'],task['fence'],task['epoch'],
          task['authority_valid_until'],'PENDING',canonical(context),None,None,
          None,None,None,None,0,None,None,now,now,context['connection_id'],
          connection['config_version'],context['provider_id'],quota['verified_at']));self.db.commit()
        return {'intent_id':intent_id,'state':'PENDING','duplicate':False}

    def cancel(self,intent_id,now=None):
        now=self.clock() if now is None else now
        row=self.db.execute('''SELECT state,writer_principal FROM codex_execution_intents WHERE
          tenant_id=? AND intent_id=?''',(self.tenant_id,intent_id)).fetchone()
        if row is None:raise KeyError(intent_id)
        principal=self.context['principal_id']
        responsible=self.db.execute('''SELECT 1 FROM execution_units WHERE
          tenant_id=? AND task_id=(SELECT task_id FROM codex_execution_intents
          WHERE tenant_id=? AND intent_id=?) AND responsible_party=?''',(
          self.tenant_id,self.tenant_id,intent_id,principal)).fetchone()
        if row['writer_principal']!=principal and responsible is None:
            raise ValueError('CURRENT_CODEX_WRITER_REQUIRED')
        if row['state']=='PENDING':
            state='CANCELLED'
        elif row['state'] in ('SENDING','ACKED','RUNNING','WAITING_APPROVAL'):
            state='CANCEL_REQUESTED'
        else:raise ValueError('CODEX_INTENT_TERMINAL')
        self.db.execute('''UPDATE codex_execution_intents SET state=?,
          cancel_requested=1,updated_at=? WHERE tenant_id=? AND intent_id=?''',(
          state,now,self.tenant_id,intent_id));self.db.commit()
        return {'intent_id':intent_id,'state':state}

    def reconcile_restart(self,now=None):
        now=self.clock() if now is None else now
        changed=self.db.execute('''UPDATE codex_execution_intents SET state=?,
          error_kind='EXECUTION_RECONCILIATION_REQUIRED_AFTER_RESTART',lease_owner=NULL,
          lease_until=NULL,updated_at=? WHERE tenant_id=? AND state IN
          ('SENDING','ACKED','RUNNING','WAITING_APPROVAL') ''',(
          UNKNOWN,now,self.tenant_id)).rowcount;self.db.commit()
        return {'unknown_intents':changed}

    def reconcile_transport_once(self,transports,now=None):
        now=self.clock() if now is None else now
        row=self.db.execute('''SELECT * FROM codex_execution_intents WHERE
          tenant_id=? AND state=? AND thread_id IS NOT NULL AND
          cancel_requested=0 ORDER BY updated_at,intent_id LIMIT 1''',(
          self.tenant_id,UNKNOWN)).fetchone()
        if row is None:return {'state':'IDLE'}
        transport=transports.get(row['transport_kind'])
        if transport is None or not hasattr(transport,'reconcile'):
            return {'intent_id':row['intent_id'],'state':UNKNOWN,
                    'error':'TRANSPORT_RECONCILIATION_UNSUPPORTED'}
        try:receipt=transport.reconcile(dict(row))
        except Exception as exc:return {'intent_id':row['intent_id'],'state':UNKNOWN,
          'error':'RECONCILIATION_UNKNOWN:'+type(exc).__name__}
        if not isinstance(receipt,dict) or receipt.get('state') not in (
                'ACKED','RUNNING','WAITING_APPROVAL','SUCCEEDED','FAILED'):
            raise ValueError('VALID_CODEX_RECONCILIATION_RECEIPT_REQUIRED')
        return self.record_result(row['intent_id'],'reconciled-'+row['intent_id'],
          receipt['state'],receipt,now)

    def dispatch_once(self,transports,worker_id='codex-adapter',now=None):
        now=self.clock() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('''SELECT * FROM codex_execution_intents WHERE
              tenant_id=? AND state='PENDING' AND cancel_requested=0 ORDER BY
              created_at,intent_id LIMIT 1''',(self.tenant_id,)).fetchone()
            if row is None:self.db.commit();return {'state':'IDLE'}
            task=self.gateway.supervisor._task(row['task_id'])
            if (task['attempt_id']!=row['attempt_id'] or
                    task['authority_state']!='VALID' or
                    task['authority_caller_id']!=row['writer_principal'] or
                    task['fence']!=row['writer_fence'] or
                    task['epoch']!=row['writer_epoch'] or
                    task['authority_valid_until'] is None or
                    now>=task['authority_valid_until']):
                self.db.execute('''UPDATE codex_execution_intents SET state='FAILED',
                  error_kind='STALE_OR_UNAUTHORIZED',updated_at=? WHERE tenant_id=?
                  AND intent_id=?''',(now,self.tenant_id,row['intent_id']))
                self.db.commit();return {'intent_id':row['intent_id'],'state':'FAILED'}
            if not self._actor_allowed(row['task_id'],row['attempt_id'],
                    row['requesting_principal'],row['writer_principal']):
                self.db.execute('''UPDATE codex_execution_intents SET state='FAILED',
                  error_kind='REQUESTING_ACTOR_REVOKED',updated_at=? WHERE
                  tenant_id=? AND intent_id=?''',(now,self.tenant_id,
                  row['intent_id']))
                self.db.commit();return {'intent_id':row['intent_id'],
                  'state':'FAILED'}
            connection=self.db.execute('''SELECT status,config_version,provider_id,
              purpose FROM service_connections WHERE tenant_id=? AND connection_id=?''',(
              self.tenant_id,row['connection_id'])).fetchone()
            quota=self.db.execute('''SELECT quota_state,quota_source,verified_at FROM
              model_quota_status WHERE tenant_id=? AND provider_id=?''',(
              self.tenant_id,row['provider_id'])).fetchone()
            if (connection is None or connection['status']!='ACTIVE' or
                    connection['purpose']!='CODEX_EXECUTION' or
                    connection['provider_id']!=row['provider_id'] or
                    connection['config_version']!=row['connection_config_version'] or
                    not self._quota_allows_zero_new_spend(quota,now)):
                self.db.execute('''UPDATE codex_execution_intents SET state='FAILED',
                  error_kind='CODEX_CONNECTION_OR_QUOTA_HOLD',updated_at=? WHERE
                  tenant_id=? AND intent_id=?''',(now,self.tenant_id,row['intent_id']))
                self.db.commit();return {'intent_id':row['intent_id'],'state':'FAILED'}
            changed=self.db.execute('''UPDATE codex_execution_intents SET
              state='SENDING',lease_owner=?,lease_until=?,updated_at=? WHERE
              tenant_id=? AND intent_id=? AND state='PENDING' AND
              cancel_requested=0''',(worker_id,now+60,now,self.tenant_id,
              row['intent_id'])).rowcount
            if changed!=1:raise ValueError('CODEX_DISPATCH_RACE')
            self.db.execute('''INSERT INTO codex_execution_events VALUES
              (?,?,?,?,?,?,?)''',(self.tenant_id,row['intent_id'],
              'sent-'+row['intent_id'],'SENT_INTENT',canonical({
              'transport_kind':row['transport_kind']}),1,now));self.db.commit()
        except Exception:self.db.rollback();raise
        transport=transports.get(row['transport_kind'])
        if transport is None:
            self.db.execute('''UPDATE codex_execution_intents SET state='FAILED',
              error_kind=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE
              tenant_id=? AND intent_id=? AND state='SENDING' ''',(
              row['transport_kind']+'_UNAVAILABLE',now,self.tenant_id,
              row['intent_id']));self.db.commit()
            return {'intent_id':row['intent_id'],'state':'FAILED'}
        try:
            receipt=transport.send(dict(row))
            if not isinstance(receipt,dict) or receipt.get('state') not in (
                    'ACKED','RUNNING','WAITING_APPROVAL'):
                raise ValueError('VALID_CODEX_RECEIPT_REQUIRED')
        except CodexTransportUnavailable as exc:
            # An adapter that proves it was unavailable before sending is a
            # definitive local failure.  Every exception after a transport
            # accepted the call is conservatively UNKNOWN below.
            self.db.execute('''UPDATE codex_execution_intents SET state='FAILED',
              error_kind=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE
              tenant_id=? AND intent_id=? AND state='SENDING' ''',(
              str(exc),now,self.tenant_id,row['intent_id']));self.db.commit()
            return {'intent_id':row['intent_id'],'state':'FAILED'}
        except Exception as exc:
            self.db.execute('''UPDATE codex_execution_intents SET state=?,
              error_kind=?,lease_owner=NULL,lease_until=NULL,
              updated_at=? WHERE tenant_id=? AND intent_id=? AND state='SENDING' ''',
              (UNKNOWN,'SEND_RESULT_UNKNOWN:'+type(exc).__name__,now,
               self.tenant_id,row['intent_id']));self.db.commit()
            return {'intent_id':row['intent_id'],'state':UNKNOWN}
        fresh=self.db.execute('''SELECT cancel_requested,state FROM codex_execution_intents
          WHERE tenant_id=? AND intent_id=?''',(self.tenant_id,
          row['intent_id'])).fetchone()
        state='CANCEL_REQUESTED' if fresh['cancel_requested'] else receipt['state']
        self.db.execute('''UPDATE codex_execution_intents SET state=?,
          execution_id=?,session_id=?,thread_id=?,turn_id=?,lease_owner=NULL,
          lease_until=NULL,updated_at=? WHERE tenant_id=? AND intent_id=? AND
          state IN ('SENDING','CANCEL_REQUESTED') ''',(state,receipt.get('execution_id'),
          receipt.get('session_id'),receipt.get('thread_id'),
          receipt.get('turn_id'),now,self.tenant_id,row['intent_id']))
        self.db.commit();return {'intent_id':row['intent_id'],'state':state}

    def dispatch_cancel_once(self,transports,now=None):
        now=self.clock() if now is None else now
        row=self.db.execute('''SELECT * FROM codex_execution_intents WHERE
          tenant_id=? AND state='CANCEL_REQUESTED' ORDER BY updated_at,intent_id
          LIMIT 1''',(self.tenant_id,)).fetchone()
        if row is None:return {'state':'IDLE'}
        transport=transports.get(row['transport_kind'])
        if transport is None or not hasattr(transport,'cancel'):
            return {'intent_id':row['intent_id'],'state':UNKNOWN,
                    'error':'CANCEL_CAPABILITY_UNVERIFIED'}
        try:receipt=transport.cancel(dict(row))
        except Exception as exc:
            self.db.execute('''UPDATE codex_execution_intents SET error_kind=?,
              updated_at=? WHERE tenant_id=? AND intent_id=? AND
              state='CANCEL_REQUESTED' ''',('CANCEL_RESULT_UNKNOWN:'+type(exc).__name__,
              now,self.tenant_id,row['intent_id']));self.db.commit()
            return {'intent_id':row['intent_id'],'state':UNKNOWN}
        if not isinstance(receipt,dict) or receipt.get('state')!='CANCELLED':
            raise ValueError('VALID_CODEX_CANCEL_RECEIPT_REQUIRED')
        return self.record_result(row['intent_id'],'cancelled-'+row['intent_id'],
          'CANCELLED',receipt,now)

    def record_result(self,intent_id,event_id,state,payload,now=None):
        now=self.clock() if now is None else now
        if state not in ('ACKED','RUNNING','WAITING_APPROVAL','SUCCEEDED','FAILED',
                         'CANCELLED'):
            raise ValueError('CODEX_RESULT_STATE_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('''SELECT * FROM codex_execution_intents WHERE
              tenant_id=? AND intent_id=?''',(self.tenant_id,intent_id)).fetchone()
            if row is None:raise KeyError(intent_id)
            existing=self.db.execute('''SELECT payload_json,event_kind FROM
              codex_execution_events WHERE tenant_id=? AND intent_id=? AND
              event_id=?''',(self.tenant_id,intent_id,event_id)).fetchone()
            body=canonical(payload)
            if existing:
                if existing['payload_json']!=body or existing['event_kind']!=state:
                    raise ValueError('CODEX_EVENT_ID_CONFLICT')
                self.db.commit();return {'duplicate':True,'state':row['state']}
            task=self.gateway.supervisor._task(row['task_id'])
            current=(task['attempt_id']==row['attempt_id'] and
              task['authority_caller_id']==row['writer_principal'] and
              task['fence']==row['writer_fence'] and task['epoch']==row['writer_epoch']
              and task['authority_state']=='VALID' and
              task['authority_valid_until'] is not None and
              now<task['authority_valid_until'])
            if row['state'] in ('SUCCEEDED','FAILED','CANCELLED'):
                current=False
            cancellation=(row['cancel_requested'] and state=='CANCELLED')
            accepted=int((current and not row['cancel_requested']) or cancellation)
            self.db.execute('''INSERT INTO codex_execution_events VALUES
              (?,?,?,?,?,?,?)''',(self.tenant_id,intent_id,event_id,state,body,
              accepted,now))
            if accepted:
                artifact=payload.get('artifact_sha256') if state=='SUCCEEDED' else None
                if state=='SUCCEEDED':_sha(artifact,'artifact_sha256')
                self.db.execute('''UPDATE codex_execution_intents SET state=?,
                  artifact_sha256=COALESCE(?,artifact_sha256),
                  execution_id=COALESCE(?,execution_id),
                  session_id=COALESCE(?,session_id),thread_id=COALESCE(?,thread_id),
                  turn_id=COALESCE(?,turn_id),updated_at=? WHERE
                  tenant_id=? AND intent_id=?''',(state,artifact,
                  payload.get('execution_id'),payload.get('session_id'),
                  payload.get('thread_id'),payload.get('turn_id'),now,
                  self.tenant_id,intent_id))
            self.db.commit();return {'duplicate':False,'accepted':bool(accepted),
              'state':state if accepted else row['state']}
        except Exception:self.db.rollback();raise

    def projection(self):
        return [dict(x) for x in self.db.execute('''SELECT intent_id,task_id,
          attempt_id,transport_kind,requesting_principal,state,execution_id,
          session_id,thread_id,
          turn_id,artifact_sha256,error_kind,cancel_requested,updated_at FROM
          codex_execution_intents WHERE tenant_id=? ORDER BY created_at,
          intent_id''',(self.tenant_id,))]
