"""Fixed whole-website coordinator, invoked only through original release authority.

No CLI, credentials, enrollment, arbitrary commands, extra transaction or budget.
Stage adapters are trusted implementation dependencies, never request JSON. Missing
actual target bindings fail closed; offline tests are not those target bindings.
"""
import copy
import os
import re
import time
from pathlib import Path
from scripts.pr122_customer_core import Denied, canonical, digest, secure_write
from scripts.pr122_customer_attempts import protected_directory, read_private

POLICY = 'CONTROLLED_WHOLE_WEBSITE_V3'
STAGES = ('PROBE', 'ACCOUNT', 'RUNTIME', 'POLICY_RESTORE', 'CHANNEL_REBIND', 'CUSTOMER_APPLY')
RECOVERY = {
    'PROBE': frozenset({'REVALIDATE_READONLY'}),
    'ACCOUNT': frozenset({'RECONCILE_ACCOUNT'}),
    'RUNTIME': frozenset({'RECONCILE_RUNTIME'}),
    'POLICY_RESTORE': frozenset({'RECONCILE_POLICY'}),
    'CHANNEL_REBIND': frozenset({'RECONCILE_CHANNEL'}),
    'CUSTOMER_APPLY': frozenset({'RECONCILE_CUSTOMER', 'REPAIR_INCOMPLETE_OWNED_FILE', 'RETRY_TRANSIENT_READONLY_CHECK'}),
}


def need(ok, code):
    if not ok: raise Denied('HOLD:' + code)


def hex64(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_contract(plan, approval):
    contract = plan.get('workflow_contract')
    need(type(contract) is dict and set(contract) == {'schema', 'stages'} and contract['schema'] == 1,
         'WORKFLOW_CONTRACT')
    need(type(contract['stages']) is list and len(contract['stages']) == len(STAGES), 'WORKFLOW_FIXED_STAGES')
    for name, row in zip(STAGES, contract['stages']):
        need(type(row) is dict and set(row) == {'stage', 'input_sha256', 'implementation_sha256',
             'adopt_receipt_sha256', 'recovery_actions'} and row['stage'] == name, 'WORKFLOW_STAGE_SCHEMA')
        need(hex64(row['input_sha256']) and hex64(row['implementation_sha256']), 'WORKFLOW_EXACT_INPUTS')
        need(row['adopt_receipt_sha256'] is None or hex64(row['adopt_receipt_sha256']), 'WORKFLOW_ADOPTION_PIN')
        actions = row['recovery_actions']
        need(type(actions) is list and all(type(x) is str for x in actions)
             and len(set(actions)) == len(actions) and set(actions) <= RECOVERY[name], 'WORKFLOW_RECOVERY_SCOPE')
    need(approval.get('attempt_policy') == POLICY and approval.get('workflow_contract_sha256') == digest(canonical(contract))
         and type(approval.get('max_executions')) is int and 1 <= approval['max_executions'] <= 5,
         'WORKFLOW_EXPLICIT_NEW_PERMISSION')
    return contract


class WorkflowStopped(Denied):
    def __init__(self, summary):
        super().__init__('HOLD:' + summary['state']); self.summary = summary


from dataclasses import dataclass

@dataclass(frozen=True)
class StageLease:
    """An immutable capability for one fence AND one still-pending stage."""
    _coordinator: object
    _row: object
    _intent_sha256: str
    _stage: str
    _readonly: bool = False

    def assert_fence(self):
        c=self._coordinator;c.assert_fence()
        need(c.data['attempts'][-1] is self._row and c.data['intent'] is not None
             and digest(canonical(c.data['intent']))==self._intent_sha256,
             'WORKFLOW_STALE_CHILD_LEASE')

    def assert_active(self):
        self.assert_fence()
        need(not self._readonly,'WORKFLOW_RECONCILIATION_READONLY')
        self._coordinator.assert_active()

    def authority(self):
        self.assert_fence();self._coordinator.authority();self.assert_fence()
        if not self._readonly:self.assert_active()

    def assert_locked(self):
        self.assert_active()

    @property
    def active(self):return copy.deepcopy(self._row)
    @property
    def approval(self):return copy.deepcopy(self._coordinator.approval)
    @property
    def plan(self):return copy.deepcopy(self._coordinator.plan)
    @property
    def data(self):return copy.deepcopy(self._coordinator.data)
    @property
    def ops(self):return self._coordinator.ops

    def verify_inputs(self,stage):
        self.assert_fence();need(stage==self._stage,'WORKFLOW_CHILD_STAGE')
        self._coordinator.verify_inputs(stage)

    def stage_contract(self,stage):
        self.assert_fence();need(stage==self._stage,'WORKFLOW_CHILD_STAGE')
        return copy.deepcopy(self._coordinator.stage_contract(stage))

    def record_stage(self,stage,phase,metadata):
        self.assert_active();need(stage==self._stage,'WORKFLOW_CHILD_STAGE')
        self._coordinator.record_stage(stage,phase,metadata)



class Coordinator:
    """One total lease covers all remaining stages, never one lease per child.

    operations methods are fixed: input(stage), implementation(stage),
    inherited(stage), verify(stage, checkpoint), execute(stage, lease), and
    reconcile(stage, intent, checkpoint, lease). No command strings are accepted.
    execute must call existing stage writers, preserving their own locks/receipts.
    reconcile must provide real evidence, not interpret HOLD as permission.
    """
    def __init__(self, release, folder, comment, plan, approval, operations, lock_fd):
        self.r, self.folder, self.comment = release, folder, comment
        self.plan, self.approval, self.ops = copy.deepcopy(plan), copy.deepcopy(approval), operations
        self.contract = validate_contract(self.plan, self.approval)
        self.lock_fd = lock_fd
        self.path = release.STATE / (release.TXN + '.attempts.json')
        self.binding = {'transaction':release.TXN, 'approval_comment':comment,
                        'approval_sha256':digest(canonical(approval)), 'plan_sha256':digest(canonical(plan)),
                        'host':os.uname().nodename, 'executor_uid':os.geteuid()}
        self.data = None
        self.active = None
        self.snapshot = None
        if hasattr(operations,'attach'):operations.attach(self)

    def assert_lock(self):
        opened, named = os.fstat(self.lock_fd), os.lstat(self.r.LOCK)
        need((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino), 'WORKFLOW_LOCK_REPLACED')

    def authority(self):
        self.assert_lock()
        need(self.approval['issued_unix'] <= time.time() < self.approval['expires_unix'], 'WORKFLOW_LEASE_EXPIRED')
        need(self.r.gate(self.comment,self.plan) == self.approval, 'WORKFLOW_PERMISSION_DRIFT')
        manifest, raw, _ = self.r.source(self.folder)
        need(digest(raw) == self.plan['manifest_sha256'] and manifest['source_commit'] == self.plan['source_commit'],
             'WORKFLOW_SOURCE_DRIFT')
        need(time.time()<self.approval['expires_unix'],'WORKFLOW_LEASE_EXPIRED')
        self.assert_lock()

    def assert_fence(self):
        self.assert_lock()
        if self.snapshot is not None:
            need(canonical(read_private(self.path)) == self.snapshot, 'WORKFLOW_FENCE_LOST')

    def assert_active(self):
        self.assert_fence()
        need(self.active is not None and self.data['attempts'][-1] is self.active
             and self.active['state'] == 'STARTED_UNKNOWN', 'WORKFLOW_NO_ACTIVE_ATTEMPT')
        need(self.active['lease'] == {'fence':self.active['number'], 'expires_unix':self.approval['expires_unix'],
             'binding_sha256':digest(canonical(self.binding))}, 'WORKFLOW_LEASE_BINDING')
        need(time.time() < self.approval['expires_unix'], 'WORKFLOW_LEASE_EXPIRED')

    def save(self, initial=False):
        self.assert_fence()
        raw = canonical(self.data)
        need(len(raw) <= 65536, 'WORKFLOW_LEDGER_BOUND')
        if initial:
            secure_write(self.path, raw)
            fd=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try: os.fsync(fd)
            finally: os.close(fd)
        else:self.r.atomic_json(self.path, self.data)
        self.snapshot = raw

    def load(self):
        self.authority()
        if os.path.lexists(self.path):
            data=read_private(self.path)
            need(type(data) is dict and set(data)=={'schema','policy','binding','state','attempts','checkpoints','intent','failures','recoveries','stage_records'}
                 and data['schema']==3 and data['policy']==POLICY and data['binding']==self.binding, 'WORKFLOW_LEGACY_OR_CHANGED_SCOPE_SEALED')
            need(type(data['attempts']) is list and 1 <= len(data['attempts']) <= self.approval['max_executions'], 'WORKFLOW_HISTORY')
            previous=None
            for number,row in enumerate(data['attempts'],1):
                need(type(row) is dict and type(row.get('number')) is int and row['number']==number
                     and row.get('previous_sha256')==previous and row.get('state') in
                     ('STARTED_UNKNOWN','FAILED_HOLD','FAILED_RECONCILED','SUCCESS')
                     and type(row.get('started_unix')) is int
                     and row.get('lease')=={'fence':number,'expires_unix':self.approval['expires_unix'],
                          'binding_sha256':digest(canonical(self.binding))}, 'WORKFLOW_ATTEMPT_CHAIN')
                previous=digest(canonical(row))
            need(set(data['checkpoints']) <= set(STAGES), 'WORKFLOW_CHECKPOINT_SCOPE')
            self.data=data; self.snapshot=canonical(data)
            need(data['state'] != 'SUCCESS', 'WORKFLOW_FINISHED')
        else:
            # Never create a second budget around a consumed original transaction.
            need(not os.path.lexists(self.r.STATE/self.r.TXN),'WORKFLOW_LEGACY_TRANSACTION_SEALED')
            if self.r.STATE.exists():protected_directory(self.r.STATE)
            else:
                protected_directory(self.r.STATE.parent);self.r.STATE.mkdir(mode=0o700)
                fd=os.open(self.r.STATE.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:os.fsync(fd)
                finally:os.close(fd)
            self.data={'schema':3,'policy':POLICY,'binding':self.binding,'state':'READY',
                       'attempts':[],'checkpoints':{},'intent':None,'failures':[],'recoveries':[],'stage_records':[]}

    def stage_contract(self, stage):
        return self.contract['stages'][STAGES.index(stage)]

    def verify_inputs(self, stage):
        row=self.stage_contract(stage)
        need(digest(canonical(self.ops.input(stage)))==row['input_sha256']
             and digest(self.ops.implementation(stage))==row['implementation_sha256'], 'WORKFLOW_STAGE_INPUT_DRIFT')

    def verified_checkpoint(self,stage,value):
        need(type(value) is dict and set(value)=={'state','receipt_sha256','effect_sha256','source_commit'}
             and value['state']=='COMPLETE' and hex64(value['receipt_sha256']) and hex64(value['effect_sha256'])
             and type(value['source_commit']) is str and len(value['source_commit'])==40
             and all(c in '0123456789abcdef' for c in value['source_commit']), 'WORKFLOW_CHECKPOINT_SHAPE')
        pinned=self.stage_contract(stage)['adopt_receipt_sha256']
        need(value['source_commit']==self.plan['source_commit'] or value['receipt_sha256']==pinned,
             'WORKFLOW_CHECKPOINT_SOURCE')
        need(self.ops.verify(stage,copy.deepcopy(value)) is True,'WORKFLOW_CHECKPOINT_UNPROVEN')
        return copy.deepcopy(value)

    def inherit_or_verify(self):
        # No writer/attempt is needed to adopt an explicitly pinned successful
        # probe or child receipt; fresh live proof is still required.
        for stage in STAGES:
            self.verify_inputs(stage)
            old=self.data['checkpoints'].get(stage)
            if old is not None:self.verified_checkpoint(stage,old);continue
            pin=self.stage_contract(stage)['adopt_receipt_sha256']
            if pin is not None:
                value=self.verified_checkpoint(stage,self.ops.inherited(stage))
                need(value['receipt_sha256']==pin,'WORKFLOW_INHERITED_RECEIPT_DRIFT')
                self.data['checkpoints'][stage]=value

    def recover(self):
        intent=self.data['intent']
        if intent is None:return True
        need(type(intent) is dict and set(intent)=={'stage','attempt','input_sha256'}
             and intent.get('stage') in STAGES and type(intent.get('attempt')) is int
             and intent['attempt']==self.data['attempts'][-1]['number']
             and intent['input_sha256']==self.stage_contract(intent['stage'])['input_sha256'], 'WORKFLOW_INTENT_SCOPE')
        stage=intent['stage'];self.verify_inputs(stage)
        # This proof runs under the original shared lock and valid authority.
        # It cannot issue arbitrary repair commands or spend a new attempt yet.
        self.authority();self.assert_fence()
        proof=self.ops.reconcile(stage,copy.deepcopy(intent),copy.deepcopy(self.data['checkpoints'].get(stage)),
                                 StageLease(self,self.data['attempts'][-1],digest(canonical(intent)),stage,True))
        self.authority();self.assert_fence()
        need(type(proof) is dict and set(proof)=={'status','action','evidence_sha256','checkpoint'}
             and proof['status'] in ('SAFE_TO_RETRY','COMPLETE','UNKNOWN') and hex64(proof['evidence_sha256']), 'WORKFLOW_RECONCILE_PROOF')
        if proof['status']=='UNKNOWN':return False
        need(proof['action'] in self.stage_contract(stage)['recovery_actions'], 'WORKFLOW_RECOVERY_NOT_APPROVED')
        if proof['status']=='COMPLETE':self.data['checkpoints'][stage]=self.verified_checkpoint(stage,proof['checkpoint'])
        else:need(proof['checkpoint'] is None,'WORKFLOW_RETRY_CHECKPOINT')
        self.data['recoveries'].append({'attempt':intent['attempt'],'stage':stage,**proof})
        self.data['intent']=None
        last=self.data['attempts'][-1]
        if last['state']=='STARTED_UNKNOWN':
            last.update(state='FAILED_RECONCILED',ended_unix=int(time.time()))
            self.data['failures'].append({'attempt':last['number'],'stage':stage,'cause':'PROCESS_INTERRUPTED',
                                          'intent_sha256':digest(canonical(intent))})
        self.data['state']='READY';self.save();return True

    def record_stage(self, stage, phase, metadata):
        """Durable child evidence inside the same total-budget ledger."""
        self.assert_active()
        need(stage in STAGES and self.data['intent'] is not None
             and self.data['intent']['stage']==stage, 'WORKFLOW_CHILD_STAGE')
        allowed={'ACCOUNT':{'ACCOUNT_CREATE_INTENT','ACCOUNT_VERIFIED','ACCOUNT_UNKNOWN_PRESERVE'},
                 'RUNTIME':{'RUNTIME_CREATE_INTENT','RUNTIME_VERIFIED','RUNTIME_UNKNOWN_PRESERVE'},
                 'POLICY_RESTORE':{'POLICY_RESTORE_INTENT','POLICY_RESTORE_VERIFIED','POLICY_RESTORE_UNKNOWN'}}
        need(phase in allowed.get(stage,set()) and type(metadata) is dict
             and len(canonical(metadata))<=8192,'WORKFLOW_CHILD_EVENT_SCOPE')
        self.data['stage_records'].append({'attempt':self.active['number'],'stage':stage,
                                          'phase':phase,'metadata':copy.deepcopy(metadata)})
        self.save()

    def summary(self):
        return {'state':self.data['state'],'attempts_used':len(self.data['attempts']),
                'max_attempts':self.approval['max_executions'],'completed_stages':list(self.data['checkpoints']),
                'failures':copy.deepcopy(self.data['failures']),'recoveries':copy.deepcopy(self.data['recoveries']),
                'target_acceptance':'NOT_VERIFIED'}

    def settle_readonly(self):
        """Budget exhaustion blocks effects, not authenticated completion proof.

        Only original reconciliation capabilities and the original ledger are
        used. No attempt or stage execution is admitted by this method.
        """
        self.authority();self.assert_fence()
        try:
            known=self.recover()
            if known and self.data['intent'] is None and set(self.data['checkpoints'])==set(STAGES):
                self.authority();self.assert_fence();self.inherit_or_verify()
                self.data['attempts'][-1].update(state='SUCCESS',ended_unix=int(time.time()),completion_reconciled=True)
                state='SUCCESS'
            elif not known:state='HOLD'
            else:state='EXHAUSTED' if len(self.data['attempts'])>=self.approval['max_executions'] else 'READY'
        except Exception:
            # Never overwrite a newer fence or write under expired authority.
            self.authority();self.assert_fence()
            self.data['state']='HOLD';self.save()
            raise
        self.authority();self.assert_fence()
        self.data['state']=state;self.save()
        return state

    def run(self):
        self.load();self.inherit_or_verify()
        if self.data['attempts']:
            state=self.settle_readonly()
            if state=='SUCCESS':return self.summary()
            if state in ('HOLD','EXHAUSTED'):raise WorkflowStopped(self.summary())
            # A crash without an effect intent happened between complete stages.
            last=self.data['attempts'][-1]
            if last['state']=='STARTED_UNKNOWN':
                last.update(state='FAILED_RECONCILED',ended_unix=int(time.time()))
                self.data['failures'].append({'attempt':last['number'],'stage':None,'cause':'INTERRUPTED_BETWEEN_CHECKPOINTS'})
                self.save()
        while True:
            self.authority();self.assert_fence()
            rows=self.data['attempts'];need(len(rows)<self.approval['max_executions'],'WORKFLOW_EXHAUSTED')
            number=len(rows)+1
            row={'number':number,'previous_sha256':digest(canonical(rows[-1])) if rows else None,
                 'state':'STARTED_UNKNOWN','started_unix':int(time.time()),
                 'lease':{'fence':number,'expires_unix':self.approval['expires_unix'],'binding_sha256':digest(canonical(self.binding))}}
            rows.append(row);self.active=row;self.data['state']='RUNNING';self.save(initial=self.snapshot is None)
            stage=None
            try:
                for stage in STAGES:
                    self.assert_active();self.verify_inputs(stage)
                    if stage in self.data['checkpoints']:
                        self.verified_checkpoint(stage,self.data['checkpoints'][stage]);continue
                    self.authority();self.assert_active()
                    self.data['intent']={'stage':stage,'attempt':number,'input_sha256':self.stage_contract(stage)['input_sha256']};self.save()
                    lease=StageLease(self,row,digest(canonical(self.data['intent'])),stage)
                    value=self.ops.execute(stage,lease)
                    self.assert_active()
                    self.data['checkpoints'][stage]=self.verified_checkpoint(stage,value)
                    self.data['intent']=None;self.save()
                self.authority();self.assert_active()
                row.update(state='SUCCESS',ended_unix=int(time.time()));self.data['state']='SUCCESS';self.save()
                return self.summary()
            except BaseException as error:
                self.assert_fence()
                failure={'attempt':number,'stage':stage,'cause':type(error).__name__}
                # Persist only fixed diagnostic labels, never command output,
                # account details, credentials or arbitrary exception text.
                label=str(error)
                if re.fullmatch(r'HOLD:[A-Z][A-Z0-9_]{0,119}',label):
                    failure['cause_code']=label[5:]
                self.data['failures'].append(failure)
                row.update(state='FAILED_HOLD',ended_unix=int(time.time()))
                self.data['state']='HOLD'
                self.save();self.active=None
                if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
                state=self.settle_readonly()
                if state=='SUCCESS':return self.summary()
                if state in ('HOLD','EXHAUSTED'):raise WorkflowStopped(self.summary()) from None
                self.inherit_or_verify()
