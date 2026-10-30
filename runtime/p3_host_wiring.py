"""Composition entry for the ONE original admitted host; no executable daemon.
Trusted dependency injection is host code, never HTTP/request configuration.
"""
import os
import json
import math
from activation_control import ActivationStore
import threading
_COMPOSITION_LOCK=threading.Lock()
_COMPOSED_PATHS=set()
from p3_lifecycle import P3Ledger
from p3_owner_reminders import OwnerReminders,ReminderIntegratedLoop


def validate_config(value):
    if not isinstance(value,dict) or set(value)!={'execution_enabled','notifications_enabled','task_to_blocker','ratio_bands','worker_prefix'}:
        raise ValueError('EXACT_HOST_CONFIG_REQUIRED')
    if type(value['execution_enabled']) is not bool or type(value['notifications_enabled']) is not bool:raise ValueError('BOOLEAN_ENABLE_REQUIRED')
    if value['notifications_enabled'] and not value['execution_enabled']:raise ValueError('EXECUTION_ADMISSION_REQUIRED')
    if not isinstance(value['worker_prefix'],str) or not value['worker_prefix'].strip():raise ValueError('WORKER_PREFIX_REQUIRED')
    if not isinstance(value['task_to_blocker'],dict) or not value['task_to_blocker']:raise ValueError('MAPPING_REQUIRED')
    OwnerReminders.validate_bands(value['ratio_bands'])
    return dict(value,task_to_blocker=dict(value['task_to_blocker']),ratio_bands=tuple(tuple(b) for b in value['ratio_bands']))


def _activation_identity(ledger):
    store=ledger.activation_store
    keys={'ledger_uuid','generation','epoch','instance','db_path'}
    if type(store) is not ActivationStore or not isinstance(ledger.activation_binding,dict) or set(ledger.activation_binding)!=keys:
        raise PermissionError('REAL_ACTIVE_HOST_BINDING_REQUIRED')
    active=store.read(require_active=True)
    ledger._assert_activation()
    supervisor=ledger.p3_supervisor
    if (supervisor is None or supervisor.activation_store is not store
        or supervisor.activation_binding!=ledger.activation_binding
        or supervisor.p3_pins!=ledger.p3_pins
        or os.path.realpath(supervisor.db_path)!=os.path.realpath(ledger.db_path)):
        raise PermissionError('SAME_ACTIVE_SUPERVISOR_REQUIRED')
    identity=os.stat(ledger.db_path,follow_symlinks=False)
    value={'db_identity':[identity.st_dev,identity.st_ino],'db_path':os.path.realpath(ledger.db_path),'binding':ledger.activation_binding,
        'pins':ledger.p3_pins,'activation_head':store.head(active),
        'store_paths':[store.descriptor,store.epoch_journal,store.lock_path,store.owner_uid]}
    return json.dumps(value,sort_keys=True,separators=(',',':')),store


def _admitted(ledger,reader,notifications,snapshot):
    if _activation_identity(ledger)!=snapshot:raise PermissionError('COMPOSED_HOST_IDENTITY_CHANGED')
    if not callable(reader):raise PermissionError('ORIGINAL_HOST_ADMISSION_READER_UNAVAILABLE')
    try:proof=reader()
    except Exception:raise PermissionError('ORIGINAL_HOST_ADMISSION_UNKNOWN')
    keys={'p2_accepted','p3_release_accepted','unique_writer','db_path','activation_binding','task_spec_pins','notification_authorized','verified','valid_from','valid_until'}
    if (not isinstance(proof,dict) or set(proof)!=keys or proof['verified'] is not True
        or any(proof[k] is not True for k in ('p2_accepted','p3_release_accepted','unique_writer'))
        or not isinstance(proof['db_path'],str) or proof['db_path']!=os.path.realpath(ledger.db_path)
        or proof['activation_binding']!=ledger.activation_binding or proof['task_spec_pins']!=ledger.p3_pins
        or type(proof['notification_authorized']) is not bool
        or (notifications and proof['notification_authorized'] is not True)
        or any(type(proof[k]) not in (int,float) or not math.isfinite(proof[k]) for k in ('valid_from','valid_until'))
        or not proof['valid_from']<=ledger._now()<proof['valid_until']
        or ledger.p3_admitted is not True):raise PermissionError('ORIGINAL_HOST_ADMISSION_NOT_ESTABLISHED')


class GuardedProvider:
    def __init__(self,ledger,reader,adapter,snapshot):
        self.ledger=ledger;self.reader=reader;self.adapter=adapter;self.snapshot=snapshot;self.not_invoked=None
    def route(self):
        _admitted(self.ledger,self.reader,True,self.snapshot)
        return self.adapter.route()
    def send(self,*args):
        try:_admitted(self.ledger,self.reader,True,self.snapshot)
        except Exception:
            self.not_invoked={'notification_id':args[0],'attempt_nonce':args[3]}
            raise
        return self.adapter.send(*args)


class HostReminders(OwnerReminders):
    def __init__(self,*args,**kwargs):
        self.send_lock=threading.Lock()
        super().__init__(*args,**kwargs)
    def send_one(self,*args,**kwargs):
        with self.send_lock:
            if isinstance(self.adapter,GuardedProvider):self.adapter.not_invoked=None
            result=super().send_one(*args,**kwargs)
            denied=getattr(self.adapter,'not_invoked',None)
            if denied is not None:
                # No external invocation occurred. Preserve the old outbox's
                # conservative uncertainty (no retry), but report facts exactly.
                recorded=False
                try:
                    with self.ledger._transaction() as db:
                        self.ledger._event(db,self.anchor,'P3_HOST_PROVIDER_NOT_INVOKED',self.ledger._now(),denied)
                    recorded=True
                except Exception:pass # Revoked activation must not be bypassed for audit.
                return {'state':'NOT_SENT_ADMISSION_REVOKED_HOLD','dial_attempted':False,
                    'external_delivery_attempted':False,'approval_performed':False,
                    'outbox_state':'SENDING_UNCERTAIN','not_invoked_evidence_persisted':recorded}
            return result


class AdmittedHostLoop(ReminderIntegratedLoop):
    def __init__(self,ledger,pipeline_factory,config,admission_reader,executor,event_reader,eligibility_reader,adapter,snapshot):
        self.snapshot=snapshot
        self.host_admission_reader=admission_reader;self.notifications=config['notifications_enabled']
        if self.notifications:adapter=GuardedProvider(ledger,admission_reader,adapter,snapshot)
        reminders=HostReminders(ledger,config['task_to_blocker'],event_reader=event_reader,
            eligibility_reader=eligibility_reader,adapter=adapter,enabled=self.notifications,ratio_bands=config['ratio_bands'])
        super().__init__(ledger,pipeline_factory,config['worker_prefix'],reminders=reminders,executor=executor)

    def tick(self):
        # Original host must stop/reconcile already-running work on revocation;
        # this hook never launches or notifies after its gate becomes unknown.
        _admitted(self.ledger,self.host_admission_reader,self.notifications,self.snapshot)
        return super().tick()

    def serve(self):
        # Original serve performs recover_expired before its first tick.
        _admitted(self.ledger,self.host_admission_reader,self.notifications,self.snapshot)
        return super().serve()

    def confirmation_event(self,evidence_ref):
        _admitted(self.ledger,self.host_admission_reader,self.notifications,self.snapshot)
        return self.reminders.ingest(evidence_ref)

    def verified_progress(self,task_id,worker_id,fence,evidence_ref):
        _admitted(self.ledger,self.host_admission_reader,self.notifications,self.snapshot)
        return self.ledger.progress(task_id,worker_id,fence,evidence_ref)

    def reconcile_notification(self,event_key,lookup):
        _admitted(self.ledger,self.host_admission_reader,self.notifications,self.snapshot)
        return self.reminders.reconcile_unknown(event_key,lookup)


def compose_existing_host(ledger,pipeline_factory,config,admission_reader=None,
                          executor=None,event_reader=None,eligibility_reader=None,adapter=None):
    """Replace construction of the original loop; NEVER run beside it.

    Returns None while disabled. Caller owns original executor and host lifecycle.
    Does not open/create a DB, spawn a process, run a tick, route or send a notice.
    """
    config=validate_config(config)
    if not isinstance(ledger,P3Ledger):raise TypeError('ORIGINAL_P3_LEDGER_REQUIRED_NOT_MCP_SUPERVISOR')
    if not config['execution_enabled']:return None
    snapshot=_activation_identity(ledger)
    _admitted(ledger,admission_reader,config['notifications_enabled'],snapshot)
    if not callable(pipeline_factory):raise ValueError('ORIGINAL_PIPELINE_REQUIRED')
    if executor is None or not callable(getattr(executor,'submit',None)):raise ValueError('ORIGINAL_HOST_EXECUTOR_REQUIRED')
    if any(not callable(getattr(ledger,k,None)) for k in ('progress_reader','acceptance_reader','stop_reader')):raise ValueError('ORIGINAL_EXECUTION_EVIDENCE_READERS_REQUIRED')
    if config['notifications_enabled']:
        if not callable(event_reader):raise ValueError('CONFIRMATION_INPUT_NOT_CONNECTED')
        if adapter is None or any(not callable(getattr(adapter,k,None)) for k in ('route','send')):raise ValueError('AUTHORIZED_PROVIDER_ADAPTER_UNAVAILABLE')
    with _COMPOSITION_LOCK:
        path=os.path.realpath(ledger.db_path)
        if path in _COMPOSED_PATHS:raise ValueError('HOST_LOOP_ALREADY_COMPOSED')
        loop=AdmittedHostLoop(ledger,pipeline_factory,config,admission_reader,executor,event_reader,eligibility_reader,adapter,snapshot)
        _COMPOSED_PATHS.add(path)
        return loop
