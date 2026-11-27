"""Host-owned isolated executor bridge; no shell, model call, queue or authority.

The original host injects an executor with execute(request, files) and
lookup(execution_id). Only that executor runs its preconfigured isolated test
plan. Unknown sends are reconciled, never blindly rerun. MCP cannot supply
commands, test plans, executor objects, paths or execution receipts.
"""
import copy
import hashlib
import json
import re
from task_supervisor import canonical


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def execution_event(candidate):
    return 'development-execution:'+digest(candidate)


def _execution_request(candidate,plan):
    cid=digest(candidate)
    return {'schema':1,'execution_id':cid,'candidate_sha256':cid,
        'task_id':candidate['task_id'],'attempt_id':candidate['attempt_id'],
        'lease_id':candidate['lease_id'],'fence':candidate['fence'],'epoch':candidate['epoch'],
        'target_repository':candidate['target_repository'],'code_commit':candidate['code_commit'],
        'files':candidate['files'],'test_plan_sha256':plan}


def _matching_intent(supervisor,candidate,request):
    row=supervisor.db.execute('''SELECT kind,evidence_ref,payload_json FROM events
        WHERE task_id=? AND attempt_id=? AND event_id=?''',
        (candidate['task_id'],candidate['attempt_id'],execution_event(candidate)+':intent')).fetchone()
    if row is None:return False
    if (row['kind']!='DEVELOPMENT_EXECUTION_INTENT' or row['evidence_ref']!=digest(request)
            or row['payload_json']!=canonical(request)):
        raise ValueError('NATIVE_EXECUTION_REQUEST_CONFLICT')
    return True


def require_execution(supervisor,candidate,native_test_plan_sha256=None):
    row=supervisor.db.execute('SELECT * FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',
        (candidate['task_id'],candidate['attempt_id'],execution_event(candidate))).fetchone()
    if row is None or row['kind']!='DEVELOPMENT_EXECUTION':
        raise ValueError('HOLD_TRUSTED_NATIVE_EXECUTION_REQUIRED')
    value=json.loads(row['payload_json'])
    cid=digest(candidate)
    if (not isinstance(value,dict) or set(value)!={'candidate_sha256','receipt'}
            or row['evidence_ref']!=digest(value) or value['candidate_sha256']!=cid):
        raise ValueError('NATIVE_EXECUTION_EVIDENCE_MISMATCH')
    receipt=value['receipt']
    expected={'schema','execution_id','candidate_sha256','code_commit','test_plan_sha256',
        'state','isolation','tests_executed','result_sha256'}
    if (not isinstance(receipt,dict) or set(receipt)!=expected
            or type(receipt['schema']) is not int or receipt['schema']!=1
            or receipt['execution_id']!=cid or receipt['candidate_sha256']!=cid
            or receipt['code_commit']!=candidate['code_commit']
            or receipt['isolation']!='ISOLATED'
            or type(receipt['tests_executed']) is not int or receipt['tests_executed']<1
            or any(not isinstance(receipt[k],str) or re.fullmatch('[0-9a-f]{64}',receipt[k]) is None
                   for k in ('test_plan_sha256','result_sha256'))):
        raise ValueError('NATIVE_EXECUTION_EVIDENCE_MISMATCH')
    if receipt['state']!='PASSED':
        raise ValueError('HOLD_NATIVE_TESTS_FAILED')
    if native_test_plan_sha256 is not None and receipt['test_plan_sha256']!=native_test_plan_sha256:
        raise ValueError('NATIVE_EXECUTION_APPROVED_PLAN_MISMATCH')
    if not _matching_intent(supervisor,candidate,_execution_request(candidate,receipt['test_plan_sha256'])):
        raise ValueError('HOLD_TRUSTED_NATIVE_EXECUTION_INTENT_REQUIRED')
    return value


class NativeDevelopmentExecutor:
    """Explicit bootstrap injection, like the existing Codex SDK transport.

    runner is an existing trusted ISOLATED executor, not an arbitrary callable
    loaded from config. test_plan_sha256 pins its host-owned test plan. A real
    runner must attest actual isolated tests and retain lookup receipts under
    the deterministic execution_id. Missing runner never runs code locally.
    """
    @staticmethod
    def valid_plan(value):
        return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None

    def __init__(self,runner,test_plan_sha256):
        if (runner is None or not callable(getattr(runner,'execute',None))
                or not callable(getattr(runner,'lookup',None))
                or not self.valid_plan(test_plan_sha256)):
            raise ValueError('TRUSTED_ISOLATED_EXECUTOR_AND_PINNED_PLAN_REQUIRED')
        self.runner=runner;self.plan=test_plan_sha256

    def run(self,s,candidate,files,admission_check):
        request=_execution_request(candidate,self.plan)
        cid=request['execution_id'];eid=execution_event(candidate)
        if ({p:hashlib.sha256(raw).hexdigest() for p,raw in files.items()}!=candidate['files']):
            raise ValueError('SAME_COMMIT_EXECUTION_BYTES_REQUIRED')
        def current_generation():
            task=s._task(candidate['task_id'])
            if any(task[k]!=candidate[k] for k in ('attempt_id','lease_id','fence','epoch')):
                raise ValueError('CURRENT_EXECUTION_GENERATION_REQUIRED')
            return task
        def current():
            task=current_generation()
            caller={k:task['authority_'+k] for k in ('caller_id','run_id','session_id','gateway_id')}
            s._validate_writer_locked(s._authority_ticket(task),caller,task['authority_lock_provider_id'])
            admission_check()
        # Canonical intent is a receipt, not a queue/worker or a second ledger.
        s.db.execute('BEGIN IMMEDIATE')
        with s.db:
            current()
            done=s.db.execute('SELECT 1 FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',
                (candidate['task_id'],candidate['attempt_id'],eid)).fetchone()
            if done:return require_execution(s,candidate,self.plan)
            prior=_matching_intent(s,candidate,request)
            if not prior:
                s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                    (candidate['task_id'],candidate['attempt_id'],eid+':intent','DEVELOPMENT_EXECUTION_INTENT',
                     s.clock(),'EXECUTION_REQUEST',digest(request),canonical(request)))
        # Recheck after committing the intent and immediately before invoking the runner.
        task=current_generation()
        if (task['authority_state']!='VALID' or task['authority_valid_until'] is None
                or s.clock()>=task['authority_valid_until']):
            raise ValueError('WRITER_AUTHORITY_NOT_VALID')
        admission_check()
        # A prior send may have happened: lookup ONLY. None is unknown, not permission to repeat.
        receipt=(self.runner.lookup(cid) if prior else
                 self.runner.execute(copy.deepcopy(request),dict(files)))
        if receipt is None:raise ValueError('HOLD_NATIVE_EXECUTION_EFFECT_UNKNOWN')
        expected={'schema','execution_id','candidate_sha256','code_commit','test_plan_sha256',
            'state','isolation','tests_executed','result_sha256'}
        if (not isinstance(receipt,dict) or set(receipt)!=expected
                or type(receipt['schema']) is not int or receipt['schema']!=1
                or any(receipt[k]!=request[k] for k in ('execution_id','candidate_sha256','code_commit','test_plan_sha256'))
                or receipt['state'] not in ('PASSED','FAILED') or receipt['isolation']!='ISOLATED'
                or type(receipt['tests_executed']) is not int or receipt['tests_executed']<1
                or not isinstance(receipt['result_sha256'],str)
                or re.fullmatch('[0-9a-f]{64}',receipt['result_sha256']) is None):
            raise ValueError('EXACT_TRUSTED_NATIVE_EXECUTION_RECEIPT_REQUIRED')
        value={'candidate_sha256':cid,'receipt':copy.deepcopy(receipt)}
        s.db.execute('BEGIN IMMEDIATE')
        with s.db:
            current()
            old=s.db.execute('SELECT payload_json FROM events WHERE task_id=? AND attempt_id=? AND event_id=?',
                (candidate['task_id'],candidate['attempt_id'],eid)).fetchone()
            if old is not None:
                if old[0]!=canonical(value):raise ValueError('NATIVE_EXECUTION_RECEIPT_CONFLICT')
            else:
                s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',
                    (candidate['task_id'],candidate['attempt_id'],eid,'DEVELOPMENT_EXECUTION',s.clock(),
                     'TRUSTED_EXECUTION',digest(value),canonical(value)))
        return require_execution(s,candidate,self.plan)
