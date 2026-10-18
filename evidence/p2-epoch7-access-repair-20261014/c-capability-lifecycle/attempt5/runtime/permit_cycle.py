"""One approved immutable grant; autonomous bounded native continuation.

The host service supplies independent diagnostic/configuration receipts. UNKNOWN
never means retry. This controller never launches an installer command, edits
source, issues a grant, or supplies SKIP to the inherited phase dispatcher.
"""
import fcntl
import os
import stat
from receipt_provider import need, digest, Hold, canonical

POLICY={'schema':1,'mode':'ONE_PERMIT_MAX_5_ATTEMPTS','max_attempts':5,
        'new_approval_per_retry':False,'diagnosis':'TRUSTED_TRANSACTION_READBACK',
        'recovery':'NATIVE_CAS_ONLY','source_change':'STOP_NEW_PERMIT',
        'configuration_actions':[]}

def policy(value=None):
    import copy
    result=copy.deepcopy(POLICY if value is None else value)
    need(type(result) is dict and set(result)==set(POLICY),'CYCLE_POLICY_SCHEMA')
    need(all(result[k]==v for k,v in POLICY.items() if k!='configuration_actions'),'CYCLE_POLICY_BOUNDARY')
    actions=result['configuration_actions']
    need(type(actions) is list and len(actions)<=16,'CONFIG_SCOPE_BOUND')
    ids=[]
    for action in actions:
        need(type(action) is dict and set(action)=={'id','target','before_sha256','after_sha256','payload_sha256','checkpoint_sha256'},'CONFIG_SCOPE')
        need(type(action['id']) is str and 0<len(action['id'])<=64,'CONFIG_ID')
        for key in ('before_sha256','after_sha256','payload_sha256','checkpoint_sha256'):
            import re
            need(type(action[key]) is str and re.fullmatch('[0-9a-f]{64}',action[key]),'CONFIG_HASH')
        need(type(action['target']) is str and os.path.isabs(action['target']) and
             os.path.normpath(action['target'])==action['target'] and action['target'].endswith('.json'),'CONFIG_EXACT_TARGET')
        ids.append(action['id'])
    need(len(set(ids))==len(ids),'DUPLICATE_CONFIG_SCOPE')
    return result

class PermitCycle(object):
    def __init__(self, native_factory, approved_policy=None):
        need(callable(native_factory),'NATIVE_FACTORY')
        self.factory=native_factory;self.policy=policy(approved_policy)
        self.native=native_factory()
        from native_recovery import NativeRecovery
        need(isinstance(self.native,NativeRecovery),'NATIVE_RECOVERY_REQUIRED')
        self.grant=dict(self.native.ledger.grant)
        self.binding=digest(self.grant)
        need(getattr(self.native,'cycle_policy',None)==self.policy,'APPROVED_CYCLE_POLICY_REQUIRED')
        self.review=getattr(self.native,'approval_review_id',None)

    def fresh(self):
        native=self.factory()
        from native_recovery import NativeRecovery
        need(isinstance(native,NativeRecovery),'NATIVE_RECOVERY_REQUIRED')
        need(digest(native.ledger.grant)==self.binding and native.cycle_policy==self.policy and
             native.approval_review_id==self.review,'PERMIT_CHANGED')
        self.native=native
        return native

    def report(self,status):
        snapshot=self.native.ledger.snapshot()
        # Durable ledger already retains every intent, proof, checkpoint and
        # independent log hash. Return the full aggregate, including on HOLD.
        report={'status':status,'grant_id':self.grant['grant_id'],
                'review_id':self.review,'approval_body_sha256':self.grant['approval_body_sha256'],
                'used':len(snapshot['attempts']),'max_attempts':5,'ledger':snapshot}
        raw=canonical(report);name=os.path.join(self.native.ledger.directory,'cycle-report-'+digest(report)+'.json')
        try:
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW)
            try:
                info=os.fstat(fd)
                need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o600,'REPORT_AUTHORITY')
                need(os.read(fd,len(raw)+1)==raw,'REPORT_CONFLICT')
            finally:os.close(fd)
        else:
            try:
                view=memoryview(raw)
                while view:
                    count=os.write(fd,view);need(count>0,'REPORT_WRITE');view=view[count:]
                os.fsync(fd)
            finally:os.close(fd)
            directory=os.open(self.native.ledger.directory,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
            try:os.fsync(directory)
            finally:os.close(directory)
        return report

    def checked(self,attempt,operation,payload):
        self.native.fence(attempt,'CYCLE_'+operation)
        binding=dict(payload,policy_sha256=digest(self.policy),review_id=self.review,
                     approval_body_sha256=self.grant['approval_body_sha256'])
        result=self.native.proof(attempt,operation,binding)
        need(result.get('binding')==binding,'CYCLE_RECEIPT_BINDING')
        return result

    def recover(self,attempt,command_sha):
        native=self.native
        native.confirm_admission(attempt,command_sha)
        if native.converge_committed(attempt):return True
        row=native.ledger.snapshot()['attempts'][-1]
        if not any(e['kind']=='execution_intent' for e in row['events']):
            need(row['state']=='INTENT_RECORDED' and
                 not native.driver.journal_io.journal_exists(native.s.OUTER_NAME) and
                 not native.driver.retained_io.journal_exists(native.driver.inner.name),'UNSTARTED_ATTEMPT_NATIVE_CONFLICT')
            native.run(attempt)
            return True
        if native.driver.journal_io.journal_exists(native.s.OUTER_NAME):
            record=native.driver.journal_io.read_journal(native.s.OUTER_NAME)
            state=native.s.retained.BoundJournal._validate_record(record)['state']
            if state.get('completed')==list(native.s.PHASES) and state.get('stage')==native.s.PHASES[-1]+'_COMPLETE':
                native.reconcile(attempt)
                return True
        result=self.checked(attempt,'diagnose_attempt',{'ledger_sha256':digest(native.ledger.snapshot())})
        need(result.get('source_identity')=={k:self.grant[k] for k in ('source_commit','source_tree','kit_sha256','manifest_sha256')},'SOURCE_CHANGE_NEW_PERMIT')
        need(result.get('status')=='DIAGNOSED' and result.get('transaction_consistent') is True and
             result.get('recovery') in ('NO_WRITE','NATIVE_CAS'),'DIAGNOSIS_HOLD')
        # Native recovery independently verifies the complete host transaction,
        # backup/checkpoint and actual effects again; diagnosis is not a waiver.
        # At the fifth failure only reconcile/retain evidence. There is no
        # next attempt to prepare, so do not apply retry configuration changes.
        actions=(result.get('configuration_actions',[]) if len(native.ledger.snapshot()['attempts'])<5 else [])
        need(type(actions) is list and len(actions)==len(set(actions)),'CONFIG_PLAN')
        approved={a['id']:a for a in self.policy['configuration_actions']}
        for action_id in actions:
            need(action_id in approved,'UNAPPROVED_CONFIG')
            response=self.checked(attempt,'apply_approved_configuration',{'action':approved[action_id]})
            need(response.get('status')=='COMMITTED' and response.get('action')==approved[action_id] and
                 response.get('backup_sha256')==approved[action_id]['before_sha256'] and
                 response.get('after_sha256')==approved[action_id]['after_sha256'], 'CONFIG_UNKNOWN_HOLD')
        if result['recovery']=='NO_WRITE':native.reconcile_unadmitted(attempt)
        else:native.reconcile(attempt)
        return True

    def run(self,command_sha):
        ledger=self.native.ledger
        # Same private durable ledger directory. Never unlink this lock file.
        path=os.path.join(ledger.directory,'permit-cycle.lock')
        fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            info=os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.geteuid() and
                 stat.S_IMODE(info.st_mode)==0o600,'CYCLE_LOCK_AUTHORITY')
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise Hold('CONCURRENT_CYCLE')
            try:
                self.native.bind_command(command_sha)
                while True:
                    rows=self.native.ledger.snapshot()['attempts']
                    if rows and rows[-1]['state']=='SUCCEEDED':return self.report('SUCCEEDED')
                    if rows and rows[-1]['state'] not in ('FAILED_NO_WRITE','SAFE_RECONCILED'):
                        self.recover(rows[-1]['id'],command_sha)
                        self.fresh()
                        continue
                    if len(rows)>=5:return self.report('EXHAUSTED')
                    # Trusted service verifies unchanged code/Kit/Manifest and
                    # transaction state before each new native admission.
                    ready=self.checked('CANDIDATE','verify_cycle_binding',{})
                    need(ready.get('status')=='UNCHANGED','SOURCE_CHANGE_NEW_PERMIT')
                    attempt=self.native.begin(command_sha)
                    try:self.native.run(attempt)
                    except Exception:
                        # No blind replay: independent reconciliation must
                        # succeed before the next persistent quota consumption.
                        self.fresh();self.recover(attempt,command_sha);self.fresh()
            except Exception:
                return self.report('HOLD')
        finally:os.close(fd)
