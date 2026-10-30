"""P3-only continuation over the original ExecutionLedger and DevelopmentLoop.

No DB bootstrap, alternate queue, transport, model invocation or install entry.
Host supplies admitted task/spec pins and independently verified evidence readers.
"""
import hashlib
import json
import math
import os
import re
import threading

from execution_ledger import ExecutionLedger, LeaseLost, InvalidDAG
from development_loop import DevelopmentLoop
from execution_supervision import ExecutionSupervisor


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256


def sha(value, length=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


class P3Supervisor(ExecutionSupervisor):
    """Original resume transaction with a P3-only atomic capacity admission.

    No new DB/lock table. Original BEGIN IMMEDIATE serializes this check with
    P3Ledger.claim. A thread-local flag scopes checks to resume_dispatch only;
    readback/notification operations are never treated as a launch.
    """
    def __init__(self, *args, task_spec_pins=None, max_heavy=2, p3_admitted=False, **kwargs):
        if (not isinstance(task_spec_pins,dict) or not task_spec_pins
                or any(not text(k) or not sha(v) for k,v in task_spec_pins.items())
                or type(max_heavy) is not int or max_heavy not in (1,2)):
            raise ValueError('EXACT_P3_SCOPE_AND_CAPACITY_REQUIRED')
        self.p3_pins=dict(task_spec_pins)
        self.max_heavy=max_heavy
        self.p3_admitted=p3_admitted is True
        self._p3_call=threading.local()
        super().__init__(*args,**kwargs)

    def dispatch(self, task_id, *args, **kwargs):
        if not self.p3_admitted or task_id not in self.p3_pins:
            raise PermissionError('P3_INITIAL_DISPATCH_ADMISSION_REQUIRED')
        self._p3_call.initial_task=task_id
        try:
            return super().dispatch(task_id,*args,**kwargs)
        finally:
            self._p3_call.initial_task=None

    def _commit(self, db):
        task_id=getattr(self._p3_call,'initial_task',None)
        if task_id is not None:
            task=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
            run=db.execute('SELECT * FROM supervised_runs WHERE task_id=?',(task_id,)).fetchone()
            spec=db.execute('SELECT hash FROM execution_specs WHERE task_id=?',(task_id,)).fetchone()
            if (task is None or run is None or spec is None or task['state']!='RUNNING'
                    or not task['lease_owner'] or task['lease_until'] is None or task['lease_until']<=self.clock()
                    or run['resume_generation']!=0 or run['status']!='DISPATCHED'
                    or spec['hash']!=self.p3_pins[task_id] or run['spec_hash']!=spec['hash']
                    or digest(json.loads(task['checkpoint']))!=run['checkpoint_hash']):
                raise ValueError('P3_INITIAL_DISPATCH_BINDING_REQUIRED')
            # Original first dispatch has no fence in its DISPATCHED event.
            # Bind its actual canonical lease in the SAME original transaction.
            db.execute('UPDATE supervised_runs SET resume_base_fence=? WHERE task_id=?',
                       (task['fence'],task_id))
            active=self.activation_binding or {}
            self._event(db,task_id,'P3_INITIAL_DISPATCH_ADMITTED',{
                'run_id':run['run_id'],'session_id':run['session_id'],'resume_generation':0,
                'fence':task['fence'],'lease_owner':task['lease_owner'],'lease_until':task['lease_until'],
                'epoch':active.get('epoch',0),'generation':active.get('generation',0),
                'started_claimed':False})
        return super()._commit(db)

    def _tx(self):
        db=super()._tx()
        task_id=getattr(self._p3_call,'resume_task',None)
        checkpoint_call=getattr(self._p3_call,'checkpoint_call',None)
        reconcile_call=getattr(self._p3_call,'reconcile_call',None)
        if task_id is None and checkpoint_call is None and reconcile_call is None:return db
        try:
            if reconcile_call is not None:
                cid,expected=reconcile_call
                row=db.execute('SELECT * FROM tasks WHERE id=?',(cid,)).fetchone()
                run=db.execute('SELECT * FROM supervised_runs WHERE task_id=?',(cid,)).fetchone()
                spec=db.execute('SELECT hash FROM execution_specs WHERE task_id=?',(cid,)).fetchone()
                if (row is None or run is None or row['state']!='PENDING'
                        or row['lease_owner'] is not None or row['lease_until'] is not None
                        or row['fence']!=expected['fence']
                        or digest(json.loads(row['checkpoint']))!=expected['checkpoint_hash']
                        or spec is None or spec['hash']!=self.p3_pins[cid]
                        or any(run[k]!=expected[k] for k in ('writer_fence','resume_generation','checkpoint_hash','run_id','session_id'))):
                    raise LeaseLost('P3 resume reconciliation lineage changed')
                return db
            if checkpoint_call is not None:
                cid,worker,fence=checkpoint_call
                row=db.execute('SELECT * FROM tasks WHERE id=?',(cid,)).fetchone()
                spec=db.execute('SELECT hash FROM execution_specs WHERE task_id=?',(cid,)).fetchone()
                if (row is None or row['state']!='RUNNING' or row['lease_owner']!=worker
                        or row['fence']!=fence or row['lease_until'] is None
                        or row['lease_until']<=self.clock() or spec is None
                        or spec['hash']!=self.p3_pins[cid]):
                    raise LeaseLost('P3 checkpoint writer no longer live')
                return db
            stored=db.execute('SELECT hash FROM execution_specs WHERE task_id=?',(task_id,)).fetchone()
            if stored is None or stored['hash']!=self.p3_pins[task_id]:
                raise ValueError('P3_SPEC_PIN_CHANGED')
            occupied=0
            for row in db.execute('SELECT id,state FROM tasks').fetchall():
                last=db.execute("SELECT event FROM events WHERE task_id=? AND event IN ('P3_UNRESOLVED_WRITER','P3_STOP_RECONCILED') ORDER BY id DESC LIMIT 1",(row['id'],)).fetchone()
                unresolved=last is not None and last['event']=='P3_UNRESOLVED_WRITER'
                if row['id']==task_id and unresolved:
                    raise ValueError('P3_RESUME_STOP_NOT_RECONCILED')
                occupied+=row['state']=='RUNNING' or unresolved
            if occupied>=self.max_heavy:
                raise ValueError('P3_RESUME_CAPACITY_WAIT')
            return db
        except BaseException:
            db.rollback();db.close();raise

    def reconcile_verified(self, task_id, expected):
        if not self.p3_admitted or task_id not in self.p3_pins:
            raise PermissionError('P3_RECONCILE_ADMISSION_REQUIRED')
        self._p3_call.reconcile_call=(task_id,dict(expected))
        try:
            return super().reconcile(task_id,True,True)
        finally:
            self._p3_call.reconcile_call=None

    def advance_live_checkpoint(self, task_id, worker_id, fence, value, version, previous_hash):
        if not self.p3_admitted or task_id not in self.p3_pins:
            raise PermissionError('P3_CHECKPOINT_ADMISSION_REQUIRED')
        self._p3_call.checkpoint_call=(task_id,worker_id,fence)
        try:
            return super().advance_checkpoint(task_id,value,version,previous_hash,fence,
                                               (self.activation_binding or {}).get('epoch',0))
        finally:
            self._p3_call.checkpoint_call=None

    def resume_dispatch(self, task_id, *args, **kwargs):
        if not self.p3_admitted or task_id not in self.p3_pins:
            raise PermissionError('P3_RESUME_ADMISSION_REQUIRED')
        self._p3_call.resume_task=task_id
        try:
            return super().resume_dispatch(task_id,*args,**kwargs)
        finally:
            self._p3_call.resume_task=None


class P3Ledger(ExecutionLedger):
    """Restricted original-ledger view; P2 rows are read for capacity, never written.

    Evidence readers are trusted host dependencies, NOT event/body callbacks.
    An absent reader or missing admission cannot turn into an automatic approval.
    """
    def __init__(self, *args, task_spec_pins=None, progress_reader=None,
                 acceptance_reader=None, stop_reader=None, supervisor=None, p3_admitted=False, **kwargs):
        if (not isinstance(task_spec_pins, dict) or not task_spec_pins
                or any(not text(k) or not sha(v) for k,v in task_spec_pins.items())):
            raise ValueError('EXACT_P3_TASK_SPEC_PINS_REQUIRED')
        self.p3_pins = dict(task_spec_pins)
        self.progress_reader = progress_reader
        self.acceptance_reader = acceptance_reader
        self.stop_reader = stop_reader
        self.p3_admitted = p3_admitted is True
        super().__init__(*args, **kwargs)
        self.p3_supervisor=supervisor
        if supervisor is not None and (not isinstance(supervisor,P3Supervisor)
                or supervisor.p3_pins!=self.p3_pins or supervisor.max_heavy!=self.max_heavy
                or os.path.realpath(supervisor.db_path)!=os.path.realpath(self.db_path)
                or supervisor.activation_binding!=self.activation_binding):
            raise ValueError('SAME_CANONICAL_SUPERVISOR_REQUIRED')

    def _scope(self, task_id):
        if not self.p3_admitted:
            raise PermissionError('P3_FIELD_ADMISSION_REQUIRED')
        if task_id not in self.p3_pins:
            raise PermissionError('NOT_ADMITTED_P3_TASK')

    def _task(self, db, task_id):
        self._scope(task_id)
        return super()._task(db, task_id)

    def _bound(self, db, task_id):
        self._scope(task_id)
        row = self._task(db, task_id)
        spec = db.execute('SELECT * FROM execution_specs WHERE task_id=?', (task_id,)).fetchone()
        if spec is None or spec['hash'] != self.p3_pins[task_id]:
            raise ValueError('P3_SPEC_PIN_CHANGED')
        packed = self._validate_spec(json.loads(spec['spec']))
        if hashlib.sha256(packed.encode()).hexdigest() != spec['hash']:
            raise ValueError('P3_SPEC_INTEGRITY')
        return row, spec

    def _recover(self, db, now):
        # Same original recovery semantics, but never recover a P2 row.
        recovered = []
        for task_id in self.p3_pins:
            try:
                row, spec = self._bound(db, task_id)
            except ValueError:
                row=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
                if row is not None:
                    self._quarantine(db,row,'P3_SPEC_UNAVAILABLE',now)
                    if row['state']=='RUNNING':
                        self._event(db,task_id,'P3_UNRESOLVED_WRITER',now,{'fence':row['fence']})
                continue
            if row['state'] != 'RUNNING' or (row['lease_until'] is not None and row['lease_until'] > now):
                continue
            if self._safe_ci_wait(db, row):
                db.execute("UPDATE tasks SET state='PENDING',lease_owner=NULL,lease_until=NULL,"
                           'fence=fence+1,updated=? WHERE id=?', (now,task_id))
                self._event(db,task_id,'CI_WAIT_RECOVERED',now,
                            {'previous_fence':row['fence'],'automatic_retry':True,'model_turn_replayed':False})
            else:
                self._quarantine(db,row,'P3_UNCERTAIN_EXIT_HOLD',now)
                self._event(db,task_id,'P3_UNRESOLVED_WRITER',now,{'fence':row['fence']})
            recovered.append(task_id)
        return recovered

    def _unresolved(self, db, task_id):
        row = db.execute("SELECT event FROM events WHERE task_id=? AND event IN "
                         "('P3_UNRESOLVED_WRITER','P3_STOP_RECONCILED') ORDER BY id DESC LIMIT 1",
                         (task_id,)).fetchone()
        return row is not None and row['event'] == 'P3_UNRESOLVED_WRITER'

    def claim(self, worker_id, ttl=60):
        if not self.p3_admitted:
            raise PermissionError('P3_FIELD_ADMISSION_REQUIRED')
        self._ttl(ttl)
        if not text(worker_id):
            raise ValueError('worker identity required')
        with self._transaction() as db:
            now=self._now(); self._recover(db,now)
            rows=db.execute('SELECT * FROM tasks ORDER BY updated,id').fetchall()
            # Conservative: all active tasks and uncertain stopped writers occupy
            # heavy slots. Never allow a HOLD to conceal a still-running process.
            occupied=sum(r['state']=='RUNNING' or self._unresolved(db,r['id']) for r in rows)
            if occupied >= self.max_heavy:
                return None
            for row in rows:
                task_id=row['id']
                if task_id not in self.p3_pins or row['state']!='PENDING' or self._unresolved(db,task_id):
                    continue
                row,stored=self._bound(db,task_id)
                if self.p3_supervisor is not None and db.execute(
                        'SELECT 1 FROM supervised_runs WHERE task_id=?',(task_id,)).fetchone():
                    # Existing native attempts require original reconcile/resume_dispatch.
                    # Never treat a recovered PENDING row as a fresh launch.
                    continue
                try:
                    all_rows,graph=self._dag(db,focus=task_id,quarantine=False)
                except InvalidDAG:
                    self._quarantine(db,row,'P3_INVALID_DAG',now)
                    continue
                states={r['id']:r['state'] for r in all_rows}
                if any(states[d]!='DONE' for d in graph[task_id]):
                    continue
                cp=json.loads(row['checkpoint'])
                if not isinstance(cp,dict):
                    self._quarantine(db,row,'P3_INVALID_CHECKPOINT',now);continue
                fence=row['fence']+1
                db.execute("UPDATE tasks SET state='RUNNING',lease_owner=?,lease_until=?,fence=?,updated=? WHERE id=?",
                           (worker_id,now+ttl,fence,now,task_id))
                db.execute('INSERT OR REPLACE INTO worker_heartbeats VALUES(?,?,?,?,?)',
                           (worker_id,task_id,fence,now,'EXECUTING'))
                self._event(db,task_id,'EXECUTION_CLAIMED',now,
                            {'worker_id':worker_id,'fence':fence,'spec_hash':stored['hash']})
                result={'task_id':task_id,'worker_id':worker_id,'fence':fence,
                        'lease_until':now+ttl,'spec':json.loads(stored['spec']),
                        'revision':stored['revision'],'spec_hash':stored['hash'],'checkpoint':cp}
                if self.activation_binding:result.update(self.activation_binding)
                return result
        return None

    def _live(self, db, task_id, worker_id, fence, now):
        try:self._bound(db,task_id)
        except ValueError:raise LeaseLost('P3 spec authority changed')
        return super()._live(db,task_id,worker_id,fence,now)

    def checkpoint(self, task_id, worker_id, fence, value):
        """Public original pipeline API, synchronized through original CAS after STARTED."""
        self._scope(task_id)
        if not isinstance(value,dict):raise ValueError('checkpoint must be an object')
        run=None
        if self.p3_supervisor is not None:run,unused=self.p3_supervisor.snapshot(task_id)
        if run is None or run['status']!='STARTED':
            return super().checkpoint(task_id,worker_id,fence,value)
        previous=json.loads(run['checkpoint'])
        value=dict(value)
        if ('native_execution' in value and self._dump(value['native_execution'])!=self._dump(previous.get('native_execution'))):
            raise ValueError('controller checkpoint requires native CAS')
        if 'native_execution' in previous:value['native_execution']=previous['native_execution']
        if digest(value)==run['checkpoint_hash']:
            self.assert_live(task_id,worker_id,fence)
            return None
        self.p3_supervisor.advance_live_checkpoint(task_id,worker_id,fence,value,
                                                  run['checkpoint_version'],run['checkpoint_hash'])
        return None

    def progress(self, task_id, worker_id, fence, evidence_ref):
        self._scope(task_id)
        if not text(evidence_ref) or not callable(self.progress_reader):
            raise ValueError('VERIFIED_PROGRESS_READER_REQUIRED')
        # Read evidence before locking; rebind all identities inside the transaction.
        proof=self.progress_reader(evidence_ref)
        with self._transaction() as db:
            now=self._now();row=self._live(db,task_id,worker_id,fence,now)
            if (not isinstance(proof,dict) or proof.get('task_id')!=task_id
                    or proof.get('spec_hash')!=self.p3_pins[task_id] or type(proof.get('fence')) is not int
                    or proof['fence']!=fence or proof.get('kind') not in ('SOURCE_COMMIT','TEST_RUN','ARTIFACT')
                    or not sha(proof.get('sha256')) or proof.get('verified') is not True):
                raise ValueError('REAL_PROGRESS_NOT_VERIFIED')
            details={'fence':fence,'evidence_sha256':proof['sha256'],'kind':proof['kind']}
            for old in db.execute("SELECT details FROM events WHERE task_id=? AND event='P3_REAL_PROGRESS'",(task_id,)):
                if json.loads(old['details'])==details:return False
            self._event(db,task_id,'P3_REAL_PROGRESS',now,details)
            return True

    def _acceptance(self, task_id, row, proof):
        cp=json.loads(row['checkpoint'])
        required={'task_id','spec_hash','fence','checkpoint_sha256','commit','artifact_sha256',
                  'terminal_receipt','effects','writer_stopped','scope','authority_verified','author',
                  'tests','ci','qa','security','business'}
        if (not isinstance(proof,dict) or set(proof)!=required or proof.get('task_id')!=task_id
                or proof.get('spec_hash')!=self.p3_pins[task_id]
                or type(proof.get('fence')) is not int or proof['fence']!=row['fence']
                or proof.get('checkpoint_sha256')!=digest(cp)
                or not sha(proof.get('commit'),40) or not sha(proof.get('artifact_sha256'))
                or not text(proof.get('terminal_receipt')) or proof.get('effects') not in ('NONE','KNOWN')
                or proof.get('writer_stopped') is not True
                or proof.get('scope') not in ('LOCAL_INTEGRATION','FIELD')
                or proof.get('authority_verified') is not True or not text(proof.get('author'))):
            raise ValueError('P3_TERMINAL_EVIDENCE_UNVERIFIED')
        identities=[]
        for role in ('tests','ci','qa','security','business'):
            evidence=proof.get(role)
            if (not isinstance(evidence,dict) or set(evidence)!={'status','commit','artifact_sha256','receipt_sha256','actor'} or evidence.get('status')!='PASS'
                    or evidence.get('commit')!=proof['commit']
                    or evidence.get('artifact_sha256')!=proof['artifact_sha256']
                    or not sha(evidence.get('receipt_sha256')) or not text(evidence.get('actor'))):
                raise ValueError('P3_EXACT_VERSION_ACCEPTANCE_REQUIRED')
            if role in ('qa','security'):
                identities.append(evidence['actor'])
        if len(set(identities+[proof['author']]))!=3:
            raise ValueError('P3_INDEPENDENT_REVIEW_REQUIRED')
        return proof

    def finish(self, task_id, worker_id, fence, state, effects='unknown'):
        self._scope(task_id)
        if state!='DONE':
            if state not in ('FAILED','WAITING_HUMAN','PAUSED_RESOURCE') or effects not in ('none','known','unknown'):
                raise ValueError('invalid terminal state/effects')
            if state=='PAUSED_RESOURCE' and effects!='none':state='WAITING_HUMAN'
            with self._transaction() as db:
                now=self._now();self._live(db,task_id,worker_id,fence,now)
                uncertain=effects=='unknown'
                db.execute('UPDATE tasks SET state=?,lease_owner=NULL,lease_until=NULL,fence=fence+?,updated=? WHERE id=?',
                           (state,int(uncertain),now,task_id))
                if state=='WAITING_HUMAN':self._pending_approval(db,task_id,now)
                self._event(db,task_id,'EXECUTION_FINISHED',now,{'fence':fence,'state':state,'effects':effects})
                if uncertain:self._event(db,task_id,'P3_UNRESOLVED_WRITER',now,{'fence':fence})
            return state
        if not callable(self.acceptance_reader):raise ValueError('ACCEPTANCE_READER_UNAVAILABLE')
        proof=self.acceptance_reader(task_id)
        with self._transaction() as db:
            now=self._now();row=self._live(db,task_id,worker_id,fence,now)
            proof=self._acceptance(task_id,row,proof)
            # Same transaction: immutable acceptance evidence before dependency DONE.
            if self.p3_supervisor is None:
                raise ValueError('CANONICAL_RESULT_OUTBOX_REQUIRED')
            self.p3_supervisor._assert_activation()
            run=db.execute('SELECT * FROM supervised_runs WHERE task_id=?',(task_id,)).fetchone()
            if (run is None or run['spec_hash']!=self.p3_pins[task_id]
                    or run['writer_fence']!=fence or run['status'] not in ('STARTED','COMPLETED')
                    or run['start_receipt'] is None
                    or (run['status']=='COMPLETED' and (run['terminal_receipt']!=proof['terminal_receipt']
                                                       or run['effects']!=proof['effects']))):
                raise ValueError('BOUND_STARTED_RECEIPT_REQUIRED')
            self._event(db,task_id,'P3_ACCEPTED_RESULT',now,proof)
            db.execute("UPDATE supervised_runs SET status='COMPLETED',terminal_receipt=?,effects=? WHERE task_id=?",
                       (proof['terminal_receipt'],proof['effects'],task_id))
            self.p3_supervisor._event(db,task_id,'P3_ACCEPTED_RESULT',
                {'fence':fence,'proof_sha256':digest(proof),'scope':proof['scope']},canonical=True)
            db.execute("UPDATE tasks SET state='DONE',lease_owner=NULL,lease_until=NULL,updated=? WHERE id=?",(now,task_id))
            self._event(db,task_id,'EXECUTION_FINISHED',now,
                        {'fence':fence,'state':'DONE','effects':proof['effects'].lower()})
        return 'DONE'

    def reconcile_completed(self, task_id):
        """Accept a durable terminal after its writer exited before finish().

        No execution/replay/approval synthesis: a trusted reader must re-verify
        FULL acceptance plus the current fenced recovery lineage. Metadata-only
        COMPLETED never grants DONE. All effects below share the original DB tx.
        """
        self._scope(task_id)
        if self.p3_supervisor is None or not callable(self.acceptance_reader):
            raise ValueError('CANONICAL_ACCEPTANCE_READER_REQUIRED')
        try:supplied=self.acceptance_reader(task_id)
        except Exception:raise ValueError('ACCEPTANCE_READER_UNAVAILABLE')
        if not isinstance(supplied,dict):raise ValueError('RECOVERY_LINEAGE_REQUIRED')
        proof=dict(supplied);recovery=proof.pop('recovery',None)
        required={'current_fence','run_id','session_id','resume_generation','epoch','generation'}
        if not isinstance(recovery,dict) or set(recovery)!=required:
            raise ValueError('RECOVERY_LINEAGE_REQUIRED')
        with self._transaction() as db:
            row,unused=self._bound(db,task_id)
            run=db.execute('SELECT * FROM supervised_runs WHERE task_id=?',(task_id,)).fetchone()
            active=self.activation_binding or {}
            if (run is None or run['status']!='COMPLETED' or run['start_receipt'] is None
                    or type(run['writer_fence']) is not int
                    or row['state'] not in ('WAITING_HUMAN','PENDING','DONE')
                    or row['lease_owner'] is not None or row['lease_until'] is not None
                    or row['fence']!=run['writer_fence']+1
                    or type(recovery['current_fence']) is not int or recovery['current_fence']!=row['fence']
                    or any(recovery[k]!=run[k] for k in ('run_id','session_id','resume_generation'))
                    or type(recovery['resume_generation']) is not int
                    or type(recovery['epoch']) is not int or type(recovery['generation']) is not int
                    or recovery['epoch']!=active.get('epoch',0) or recovery['generation']!=active.get('generation',0)
                    or run['writer_epoch']!=recovery['epoch'] or run['spec_hash']!=self.p3_pins[task_id]
                    or run['checkpoint_hash']!=digest(json.loads(row['checkpoint']))
                    or proof.get('terminal_receipt')!=run['terminal_receipt']
                    or proof.get('effects')!=run['effects']):
                raise ValueError('COMPLETED_RECOVERY_LINEAGE_CHANGED')
            started=json.loads(run['start_receipt'])
            if any(started.get(k)!=run[k] for k in ('run_id','session_id','resume_generation','spec_hash')):
                raise ValueError('COMPLETED_START_IDENTITY_CHANGED')
            validation=dict(row);validation['fence']=run['writer_fence']
            proof=self._acceptance(task_id,validation,proof)
            prior=db.execute("SELECT details FROM events WHERE task_id=? AND event='P3_ACCEPTED_RESULT' ORDER BY id DESC LIMIT 1",(task_id,)).fetchone()
            if row['state']=='DONE':
                if prior is None or json.loads(prior['details'])!=proof:
                    raise ValueError('COMPLETED_ACCEPTANCE_REPLAY_CONFLICT')
                return {'state':'DONE','duplicate':True,'execution_replayed':False}
            if prior is not None:raise ValueError('COMPLETED_ACCEPTANCE_STATE_DIVERGED')
            now=self._now()
            self._event(db,task_id,'P3_ACCEPTED_RESULT',now,proof)
            self.p3_supervisor._event(db,task_id,'P3_ACCEPTED_RESULT',{
                'fence':row['fence'],'writer_fence':run['writer_fence'],
                'proof_sha256':digest(proof),'scope':proof['scope'],'reconciled_after_exit':True},canonical=True)
            self._event(db,task_id,'P3_STOP_RECONCILED',now,{
                'fence':run['writer_fence'],'receipt_sha256':digest(proof),
                'terminal_receipt':run['terminal_receipt'],'completed_result':True})
            db.execute("UPDATE tasks SET state='DONE',updated=? WHERE id=?",(now,task_id))
            self._event(db,task_id,'EXECUTION_FINISHED',now,{
                'fence':row['fence'],'state':'DONE','effects':proof['effects'].lower(),
                'reconciled_after_exit':True,'execution_replayed':False})
            return {'state':'DONE','duplicate':False,'execution_replayed':False}

    def recover_completions(self):
        """Bounded per-task reconciliation during the original loop's next tick."""
        if self.p3_supervisor is None:return []
        with self._transaction() as db:
            self._scope(sorted(self.p3_pins)[0])
            pending=[r['id'] for r in db.execute("SELECT t.id FROM tasks t JOIN supervised_runs s ON s.task_id=t.id WHERE t.state IN ('WAITING_HUMAN','PENDING') AND s.status='COMPLETED'")
                     if r['id'] in self.p3_pins]
        results=[]
        for task_id in pending:
            try:
                outcome=self.reconcile_completed(task_id)
            except ValueError:
                # Missing/bad authority evidence blocks only this chain. Never
                # treat a metadata-complete result as accepted to make progress.
                outcome={'state':'HOLD_ACCEPTANCE_EVIDENCE_REQUIRED'}
            results.append({'task_id':task_id,'result':outcome})
        return results

    def watchdog(self, seconds=600):
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0:
            raise ValueError('bounded progress deadline required')
        held=[]
        with self._transaction() as db:
            now=self._now();self._recover(db,now)
            for task_id in self.p3_pins:
                row=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
                if row is None or row['state']!='RUNNING':continue
                self._bound(db,task_id)
                latest=None
                start_timeout=False
                for event in db.execute("SELECT event,created,details FROM events WHERE task_id=? "
                                        "AND event IN ('EXECUTION_CLAIMED','P3_REAL_PROGRESS') ORDER BY id",(task_id,)):
                    if json.loads(event['details']).get('fence')==row['fence']:
                        latest=event['created'] if latest is None else max(latest,event['created'])
                if self.p3_supervisor is not None:
                    run=db.execute('SELECT * FROM supervised_runs WHERE task_id=?',(task_id,)).fetchone()
                    if run is not None and run['status'] in ('STALLED','RESULT_MISSING','HOLD','PAUSED_RESOURCE'):
                        start_timeout=True
                    if run is not None and run['status']=='DISPATCHED':
                        event=db.execute("SELECT details FROM supervision_events WHERE task_id=? AND kind IN ('RESUMED_DISPATCH','P3_INITIAL_DISPATCH_ADMITTED') ORDER BY sequence DESC LIMIT 1",(task_id,)).fetchone()
                        admission=json.loads(event['details']) if event else {}
                        active=self.activation_binding or {}
                        bound=(run['spec_hash']==self.p3_pins[task_id]
                            and run['resume_base_fence']==row['fence']
                            and admission.get('fence')==row['fence']
                            and admission.get('run_id')==run['run_id']
                            and admission.get('session_id')==run['session_id']
                            and admission.get('resume_generation')==run['resume_generation']
                            and admission.get('lease_owner')==row['lease_owner']
                            and admission.get('epoch')==active.get('epoch',0)
                            and admission.get('generation')==active.get('generation',0)
                            and run['checkpoint_hash']==digest(json.loads(row['checkpoint'])))
                        if bound:
                            deadline=run['start_deadline']
                            if type(deadline) in (int,float) and math.isfinite(deadline) and now<deadline:
                                # Persisted admission is NOT real progress. Only
                                # a bounded ACK/STARTED wait for this generation.
                                continue
                            start_timeout=True
                    if (run is not None and run['status']=='STARTED'
                            and run['writer_fence']==row['fence']
                            and run['writer_epoch']==(self.activation_binding or {}).get('epoch',0)
                            and run['spec_hash']==self.p3_pins[task_id]
                            and run['start_receipt'] is not None):
                        receipt=json.loads(run['start_receipt'])
                        started=run['started_at']
                        if (receipt.get('task_id')==task_id and receipt.get('fence')==row['fence']
                                and receipt.get('run_id')==run['run_id']
                                and receipt.get('session_id')==run['session_id']
                                and receipt.get('resume_generation')==run['resume_generation']
                                and type(started) in (int,float) and math.isfinite(started)
                                and started<=now):
                            # Original resume_dispatch emits RESUMED_DISPATCH in
                            # supervision_events, not EXECUTION_CLAIMED in events.
                            # STARTED supplies one grace origin, never rolling progress.
                            latest=started if latest is None else max(latest,started)
                if start_timeout or latest is None or now-latest>=seconds:
                    self._quarantine(db,row,'P3_START_ACK_TIMEOUT' if start_timeout else 'P3_NO_REAL_PROGRESS',now)
                    self._event(db,task_id,'P3_UNRESOLVED_WRITER',now,{'fence':row['fence']})
                    held.append(task_id)
        return held

    def reconcile_stopped(self, task_id, evidence_ref):
        """Release capacity only. Does NOT approve/resume WAITING_HUMAN tasks."""
        self._scope(task_id)
        if not text(evidence_ref) or not callable(self.stop_reader):raise ValueError('STOP_READER_UNAVAILABLE')
        proof=self.stop_reader(evidence_ref)
        with self._transaction() as db:
            row,unused=self._bound(db,task_id)
            old=db.execute("SELECT details FROM events WHERE task_id=? AND event='P3_UNRESOLVED_WRITER' ORDER BY id DESC LIMIT 1",(task_id,)).fetchone()
            if (old is None or not isinstance(proof,dict) or proof.get('task_id')!=task_id
                    or proof.get('spec_hash')!=self.p3_pins[task_id]
                    or type(proof.get('fence')) is not int or proof['fence']!=json.loads(old['details'])['fence']
                    or row['fence']<=proof['fence'] or row['state']=='RUNNING'
                    or proof.get('writer_stopped') is not True or proof.get('descendants_stopped') is not True
                    or proof.get('effects') not in ('NONE','KNOWN')
                    or proof.get('checkpoint_sha256')!=digest(json.loads(row['checkpoint']))
                    or proof.get('epoch')!=(self.activation_binding or {}).get('epoch',0)
                    or type(proof.get('epoch')) is not int or not sha(proof.get('receipt_sha256'))
                    or proof.get('authority_verified') is not True):
                raise ValueError('STOP_EFFECTS_NOT_RECONCILED')
            if not self._unresolved(db,task_id):return False
            if self.p3_supervisor is not None:
                run=db.execute('SELECT * FROM supervised_runs WHERE task_id=?',(task_id,)).fetchone()
                if run is not None:
                    if run['status']=='COMPLETED' or run['terminal_receipt'] is not None:
                        raise ValueError('COMPLETED_RESULT_RECONCILIATION_REQUIRED')
                    if (run['writer_fence'] is None and run['start_receipt'] is None and run['started_at'] is None
                            and run['status'] in ('DISPATCHED','STALLED','RESULT_MISSING','HOLD','PAUSED_RESOURCE')):
                        event=db.execute("SELECT details FROM supervision_events WHERE task_id=? AND kind IN ('RESUMED_DISPATCH','P3_INITIAL_DISPATCH_ADMITTED') ORDER BY sequence DESC LIMIT 1",(task_id,)).fetchone()
                        admission=json.loads(event['details']) if event else {}
                        active=self.activation_binding or {}
                        if (run['resume_base_fence']!=proof['fence']
                                or admission.get('fence')!=proof['fence']
                                or admission.get('epoch')!=proof['epoch']
                                or admission.get('generation')!=active.get('generation',0)
                                or any(proof.get(k)!=run[k] or admission.get(k)!=run[k]
                                       for k in ('run_id','session_id','resume_generation'))
                                or type(proof.get('resume_generation')) is not int
                                or run['spec_hash']!=proof['spec_hash']
                                or run['checkpoint_hash']!=proof['checkpoint_sha256']):
                            raise ValueError('STOP_UNSTARTED_ADMISSION_LINEAGE_DIVERGED')
                        # Recover known lease identity from the exact persisted
                        # admission ONLY after trusted stopped proof. This is NOT
                        # STARTED: timestamps/start_receipt stay NULL, native state
                        # records STOPPED, and the evidence kind is explicit.
                        db.execute("UPDATE supervised_runs SET writer_fence=?,writer_epoch=?,native_state='STOPPED' WHERE task_id=?",
                                   (proof['fence'],proof['epoch'],task_id))
                        self.p3_supervisor._event(db,task_id,'UNSTARTED_STOP_RECONCILED',
                            {'fence':proof['fence'],'resume_generation':proof['resume_generation'],
                             'receipt_sha256':proof['receipt_sha256'],'started_claimed':False})
                    elif (run['writer_fence']!=proof['fence'] or run['writer_epoch']!=proof['epoch']
                            or run['spec_hash']!=proof['spec_hash']
                            or run['checkpoint_hash']!=proof['checkpoint_sha256']):
                        raise ValueError('STOP_SUPERVISION_LINEAGE_DIVERGED')
                    # Consume the trusted same-generation reconciliation in the
                    # same transaction as its receipt. Never clear UNKNOWN by
                    # passing caller booleans to original reconcile().
                    db.execute('UPDATE supervised_runs SET effects=? WHERE task_id=?',
                               (proof['effects'],task_id))
            self._event(db,task_id,'P3_STOP_RECONCILED',self._now(),proof)
            return True

    def resume_human(self, task_id, actor):
        """Reconcile the SAME task after original owner_decision(APPROVE).

        The original API already moves WAITING_HUMAN -> PENDING without changing
        the fenced generation. Never synthesize another approval/state transition.
        """
        self._scope(task_id)
        if not text(actor):raise ValueError('review actor required')
        with self._transaction() as db:
            row,unused=self._bound(db,task_id)
            approval=db.execute('SELECT decision FROM approvals WHERE task_id=?',(task_id,)).fetchone()
            approved=db.execute("SELECT details FROM events WHERE task_id=? AND event='OWNER_APPROVE' ORDER BY id DESC LIMIT 1",(task_id,)).fetchone()
            decision=json.loads(approved['details']) if approved else {}
            if (row['state']!='PENDING' or approval is None or approval['decision']!='APPROVE'
                    or decision.get('fence')!=row['fence'] or row['lease_owner'] is not None
                    or row['lease_until'] is not None):
                raise PermissionError('ORIGINAL_EXPLICIT_APPROVAL_REQUIRED')
            stopped=db.execute("SELECT details FROM events WHERE task_id=? AND event='P3_STOP_RECONCILED' ORDER BY id DESC LIMIT 1",(task_id,)).fetchone()
            proof=json.loads(stopped['details']) if stopped else {}
            if (self._unresolved(db,task_id) or not proof
                    or proof.get('fence')!=row['fence']-1
                    or proof.get('checkpoint_sha256')!=digest(json.loads(row['checkpoint']))
                    or proof.get('spec_hash')!=self.p3_pins[task_id]
                    or proof.get('epoch')!=(self.activation_binding or {}).get('epoch',0)):
                raise ValueError('VERIFIED_RESUME_LINEAGE_REQUIRED')
            details={'actor':actor,'fence':row['fence'],'checkpoint_sha256':proof['checkpoint_sha256'],
                     'preserved_budget':True,'native_launch_performed':False}
            previous=db.execute("SELECT details FROM events WHERE task_id=? AND event='HUMAN_REVIEW_RESUMED' ORDER BY id DESC LIMIT 1",(task_id,)).fetchone()
            if previous is None or json.loads(previous['details']).get('fence')!=row['fence']:
                self._event(db,task_id,'HUMAN_REVIEW_RESUMED',self._now(),details)
            expected=None
            if self.p3_supervisor is not None:
                run=db.execute('SELECT * FROM supervised_runs WHERE task_id=?',(task_id,)).fetchone()
                if run is not None:
                    expected={k:run[k] for k in ('writer_fence','resume_generation','checkpoint_hash','run_id','session_id')}
                    expected['fence']=row['fence']
        if expected is not None:
            return self.p3_supervisor.reconcile_verified(task_id,expected)
        return 'PENDING_SAME_TASK_NO_NATIVE_LAUNCH'

    def pulse(self, phase):
        if phase not in ('START','COMPLETE'):raise ValueError('invalid pulse')
        anchor=sorted(self.p3_pins)[0]
        with self._transaction() as db:
            self._task(db,anchor)
            self._event(db,anchor,'P3_SUPERVISOR_'+phase,self._now(),{})

    def health(self, max_age=30):
        if type(max_age) not in (int,float) or not math.isfinite(max_age) or max_age<=0:
            raise ValueError('invalid health deadline')
        with self._transaction() as db:
            anchor=sorted(self.p3_pins)[0];self._task(db,anchor)
            event=db.execute("SELECT created FROM events WHERE task_id=? AND event='P3_SUPERVISOR_COMPLETE' ORDER BY id DESC LIMIT 1",(anchor,)).fetchone()
            completed=event['created'] if event else None
            return {'state':'HEALTHY' if completed is not None and 0<=self._now()-completed<max_age else 'SUPERVISOR_STALLED',
                    'last_completed_pass':completed,'recovery':'EXISTING_HOST_SERVICE_RESTART_ONLY',
                    'automatic_window_wake':False}


class P3ContinuousLoop(DevelopmentLoop):
    """Use the original bounded pool and original dependency claim semantics.

    ACK/report/heartbeat never satisfies progress. One failing chain doesn't
    stop the next tick; authority/schema errors still fail closed globally.
    """
    def __init__(self, ledger, *args, progress_timeout=600, **kwargs):
        if not isinstance(ledger,P3Ledger):raise TypeError('P3Ledger required')
        if type(progress_timeout) not in (int,float) or not math.isfinite(progress_timeout) or progress_timeout<=0:
            raise ValueError('invalid progress timeout')
        self.progress_timeout=progress_timeout
        super().__init__(ledger,*args,**kwargs)

    def tick(self):
        if self.stop_event.is_set():return super().tick()
        self.ledger.pulse('START')
        held=self.ledger.watchdog(self.progress_timeout)
        completions=self.ledger.recover_completions()
        result=super().tick()
        self.ledger.pulse('COMPLETE')
        result['completion_reconciliation']=completions
        result['held_no_real_progress']=held
        result['field_acceptance']='NOT_ESTABLISHED_BY_TICK'
        return result
