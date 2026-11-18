"""Original host/ledger bridge. Default-off; no identity or authority provider.

The database is the durable outbox; file publication is retryable and checked
against exact committed bytes on enqueue, flush and read. No network in txn.
"""
import json
from task_delivery_ledger.core import validate, canonical, ident, parse_time, Store

PHASES={'PROPOSE':'handoff_propose','NOMINATE':'handoff_nominate',
        'RECEIVE':'handoff_received','ALIGNED':'handoff_aligned',
        'SUPERVISION_START':'handoff_supervision_start','VERIFIED':'handoff_verified'}

def validate_host_event(host, binding, payload, event, now):
    validate(event)
    data=event['data']; action=payload['action']
    if (action not in PHASES or event['type']!=PHASES[action] or event['namespace']=='synthetic'
        or event['validity']!='VERIFIED_NOW'
        or any(event[k]!=payload[k] for k in ('task_id','attempt_id','event_id','causation'))
        or any(data[k]!=payload[k] for k in ('handoff_id','handoff_version','snapshot_digest','role_id'))
        or data['actor_ref']!=payload['principal_id'] or data['session_ref']!=payload['session_id']
        or parse_time(data['permission_expires_at']).timestamp()!=payload['expires_at']
        or parse_time(event['occurred_at']).timestamp()>now or parse_time(event['observed_at']).timestamp()>now
        or parse_time(event['occurred_at'])>parse_time(event['observed_at'])):
        raise ValueError('HANDOFF_LEDGER_BINDING_INVALID')
    if action=='NOMINATE' and data.get('target_ref')!=payload['target_ref']:raise ValueError('HANDOFF_LEDGER_BINDING_INVALID')
    if action=='ALIGNED' and data.get('received_event_id')!=payload['causation']:raise ValueError('HANDOFF_LEDGER_BINDING_INVALID')
    if action=='VERIFIED' and (data.get('alignment_event_id')!=payload['alignment_ref'] or data.get('supervision_start_event_id')!=payload['causation']):raise ValueError('HANDOFF_LEDGER_BINDING_INVALID')
    # Identity, scope, event source, original timestamps, snapshot and every
    # actual check are independently attested by the existing trusted adapter.
    original=canonical(event); host_bytes=canonical(payload)
    if (host.adapter.assess_ledger_event(dict(binding, **{'host_record':payload}),event) is not True
        or canonical(event)!=original or canonical(payload)!=host_bytes):
        raise ValueError('HANDOFF_LEDGER_FACTS_UNVERIFIED')

class HandoffLedgerBridge:
    """Host-created binding; never construct from HTTP input."""
    def __init__(self, host, root, namespace, writer):
        from task_center_handoff_host import HandoffHost
        if type(host) is not HandoffHost:raise ValueError('HANDOFF_HOST_REQUIRED')
        self.host=host;self.root=root;self.namespace=ident(namespace);self.writer=ident(writer)
        if namespace=='synthetic':raise ValueError('NON_SYNTHETIC_NAMESPACE_REQUIRED')

    def verify_event(self, event, writer, namespace=None):
        if writer!=self.writer or event.get('producer')!=writer or event.get('namespace')!=self.namespace or (namespace is not None and namespace!=self.namespace):return False
        try:
            row=self.host.db.execute("SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=? AND kind='HANDOFF_LEDGER_BOUND'",(event['task_id'],event['attempt_id'],'handoff-ledger:'+event['event_id'])).fetchone()
            hostrow=self.host.db.execute("SELECT kind,payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?",(event['task_id'],event['attempt_id'],'handoff-host:'+event['event_id'])).fetchone()
            if row is None or hostrow is None or row['payload_json']!=canonical(event).decode('utf-8'):return False
            payload=json.loads(hostrow['payload_json'])
            return (payload.get('tenant_id')==self.host.tenant_id and payload.get('issuer')==self.host.issuer
                    and payload.get('event_id')==event['event_id'] and PHASES.get(payload.get('action'))==event['type']
                    and hostrow['kind']=='AUTHENTICATED_HANDOFF_'+payload['action'])
        except (KeyError,TypeError,ValueError):return False

    def verify_current(self,event):
        if not self.verify_event(event,self.writer,self.namespace):return False
        row=self.host.db.execute("SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?",(event['task_id'],event['attempt_id'],'handoff-host:'+event['event_id'])).fetchone()
        try:return self.host.adapter.verify_ledger_event_current(event,json.loads(row['payload_json'])) is True
        except Exception:return False

    def flush(self, task_id, attempt_id, event_id):
        """Recover one committed DB event; immutable file conflict is surfaced."""
        for value in (task_id,attempt_id,event_id):ident(value)
        row=self.host.db.execute("SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=? AND kind='HANDOFF_LEDGER_BOUND'",(task_id,attempt_id,'handoff-ledger:'+event_id)).fetchone()
        if row is None:raise ValueError('HANDOFF_LEDGER_EVENT_UNAVAILABLE')
        event=json.loads(row['payload_json'])
        store=Store(self.root,self.writer,authority=self)
        enqueued=store.enqueue(event)
        return {'enqueue':enqueued,'flush':store.flush(self.namespace)}
