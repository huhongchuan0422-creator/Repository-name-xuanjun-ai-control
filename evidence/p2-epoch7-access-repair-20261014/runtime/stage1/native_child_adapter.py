"""Fenced OpenClaw native-child adapter through an injectable native API."""
import hashlib
import json
import math
import os
import re
import subprocess
import time
import uuid


class NativeContractError(ValueError):
    pass


class OpenClawGatewayNativeProvider(object):
    """Concrete native provider using only installed, supported Gateway RPCs.

    The provider deliberately maps to ``agent``, ``agent.wait``,
    ``sessions.list`` and ``sessions.get``. It does not assume proposed or
    nonexistent execution methods are available.
    """
    ACTIVE = frozenset(['queued', 'running'])
    TERMINAL = frozenset(['done', 'failed', 'interrupted', 'killed', 'timeout'])

    def __init__(self, task_message, executable=None, runner=None,
                 model='openai/gpt-5.6-sol', timeout_seconds=30, controller=None):
        if not isinstance(task_message, str) or not task_message.strip():
            raise NativeContractError('nonempty native task message required')
        if model != 'openai/gpt-5.6-sol':
            raise NativeContractError('fixed OAuth model required')
        self.controller = controller
        self.task_message = task_message
        self.executable = executable or '/home/xuanjun_dev/.openclaw/bin/openclaw'
        if not os.path.isabs(self.executable):
            raise NativeContractError('absolute OpenClaw executable required')
        self.runner = runner or self._run_subprocess
        self.model = model
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _dump(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False)

    @staticmethod
    def _session_key(binding_hash, executor_id):
        safe_executor = re.sub(r'[^a-zA-Z0-9_-]', '-', executor_id)[:64]
        return 'agent:%s:p2-%s' % (safe_executor, binding_hash[:32])

    def _run_subprocess(self, argv):
        environment = {
            'HOME': os.environ.get('HOME', '/home/xuanjun_dev'),
            'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'),
            'LANG': os.environ.get('LANG', 'C.UTF-8'),
        }
        process = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=environment)
        try:
            output, error = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError('OpenClaw Gateway call timed out')
        if process.returncode:
            raise RuntimeError('OpenClaw Gateway call failed: ' +
                               error.decode('utf-8', 'replace')[:500])
        return json.loads(output.decode('utf-8'))

    def _call(self, method, params):
        return self.runner([self.executable, 'gateway', 'call', method,
                            '--params', self._dump(params), '--json'])

    def _session(self, session_key=None, run_id=None, session_id=None):
        response = self._call('sessions.list', {'limit': 200})
        rows = response.get('sessions', []) if isinstance(response, dict) else []
        matches = [row for row in rows if isinstance(row, dict)
                   and (session_key is None or row.get('key') == session_key)
                   and (session_id is None or row.get('sessionId') == session_id)
                   and (run_id is None or row.get('lastRunId') == run_id
                        or row.get('runId') == run_id)]
        if len(matches) > 1:
            raise NativeContractError('ambiguous native session identity')
        return matches[0] if matches else None

    def _instruction(self, binding):
        identity = {key: binding[key] for key in (
            'task_id', 'spec_hash', 'executor_id', 'workdir',
            'artifact_commit', 'artifact_tree', 'artifact_hash', 'lease',
            'fence', 'epoch')}
        return (self.task_message.rstrip() + '\n\nNATIVE_EXECUTION_BINDING=' +
                self._dump(binding) + '\nReturn the terminal result as one JSON '
                'object containing these exact identity fields plus outcome: ' +
                self._dump(identity))

    def spawn(self, binding, idempotency_key):
        raise NativeContractError('delegated model dispatch prohibited by owner policy')
        if self.controller is None:
            raise NativeContractError('trusted native controller unavailable; dispatch denied')
        self.controller.authorize(binding, idempotency_key)
        session_key = self._session_key(idempotency_key, binding['executor_id'])
        response = self._call('agent', {
            'message': self._instruction(binding),
            'agentId': binding['executor_id'],
            'provider': 'openai',
            'model': self.model.split('/', 1)[1],
            'sessionKey': session_key,
            'thinking': 'low',
            'deliver': False,
            'cwd': binding['workdir'],
            'timeout': max(1, int(binding['result_deadline'] - time.time())),
            'idempotencyKey': idempotency_key,
            'label': 'P2 ' + binding['task_id'][:80],
        })
        if (not isinstance(response, dict) or response.get('status') != 'accepted'
                or not response.get('runId')
                or response.get('sessionKey') != session_key
                or response.get('agentId') != binding['executor_id']):
            return {'accepted': False, 'provider_response': response}
        return self._receipt(binding, idempotency_key, response['runId'],
                             response.get('acceptedAt'))

    def reconcile_spawn(self, idempotency_key, binding):
        session_key = self._session_key(idempotency_key, binding['executor_id'])
        row = self._session(session_key=session_key)
        if not row or not row.get('lastRunId'):
            return None
        return self._receipt(binding, idempotency_key, row['lastRunId'],
                             row.get('createdAt'))

    def _receipt(self, binding, idempotency_key, run_id, started_at):
        session_key = self._session_key(idempotency_key, binding['executor_id'])
        row = self._session(session_key=session_key, run_id=run_id)
        if not row or not row.get('sessionId'):
            return {'accepted': False, 'run_id': run_id,
                    'reason': 'accepted run session identity unavailable'}
        if self.controller is None:
            return {'accepted': False, 'run_id': run_id,
                    'reason': 'trusted execution observation unavailable'}
        return self.controller.receipt(run_id, row['sessionId'], idempotency_key)

    def status(self, run_id, session_id):
        unknown = {'run_id': run_id, 'session_id': session_id,
                   'state': 'unknown', 'process_alive': None,
                   'unit_active': None, 'effects': 'unknown'}
        if self.controller is None:
            return unknown
        try:
            observed = self.controller.status(run_id, session_id)
        except Exception:
            return unknown
        return observed if isinstance(observed, dict) else unknown

    def recover_report(self, run_id, session_id):
        # Conversation text is not an authoritative durable execution report.
        if self.controller is None:
            return None
        return self.controller.recover_report(run_id, session_id)


class NativeChildAdapter(object):
    TERMINAL = frozenset(['completed', 'failed', 'cancelled', 'lost'])
    KEYS = frozenset(['task_id', 'spec_hash', 'executor_id', 'workdir',
        'artifact_commit', 'artifact_tree', 'artifact_hash', 'lease', 'fence',
        'epoch', 'budget', 'progress_deadline', 'result_deadline', 'checkpoint'])

    def __init__(self, ledger, native, notifier, clock=None, max_delivery_attempts=2):
        self.ledger, self.native, self.notifier = ledger, native, notifier
        self.clock = clock or time.time
        self.max_delivery_attempts = max_delivery_attempts
        self.instance_id = 'adapter-' + uuid.uuid4().hex[:12]

    @staticmethod
    def _dump(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False)

    @staticmethod
    def _token(claim):
        return (claim['task_id'], claim['worker_id'], claim['fence'])

    def _validate(self, claim, binding):
        if not isinstance(binding, dict) or set(binding) != self.KEYS:
            raise NativeContractError('complete native execution binding required')
        if (binding['task_id'] != claim['task_id']
                or binding['spec_hash'] != claim['spec_hash']
                or binding['fence'] != claim['fence']
                or binding['lease'] != claim['worker_id']):
            raise NativeContractError('task/spec/lease/fence mismatch')
        for key in ('artifact_commit', 'artifact_tree', 'artifact_hash'):
            if not isinstance(binding[key], str) or re.fullmatch(r'[0-9a-f]{40,64}', binding[key]) is None:
                raise NativeContractError('immutable artifact identities required')
        for key in ('task_id', 'executor_id', 'workdir', 'epoch', 'checkpoint'):
            if not isinstance(binding[key], str) or not binding[key].strip():
                raise NativeContractError('nonempty binding field required: ' + key)
        for key in ('progress_deadline', 'result_deadline'):
            value = binding[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise NativeContractError('finite deadlines required')
        if binding['result_deadline'] < binding['progress_deadline'] or not isinstance(binding['budget'], dict):
            raise NativeContractError('invalid deadline or budget')
        return hashlib.sha256(self._dump(binding).encode('utf-8')).hexdigest()

    def start(self, claim, binding):
        digest = self._validate(claim, binding)
        observed = self.ledger.observation(claim['task_id'])['checkpoint']
        if observed.get('native_binding_hash') == digest:
            return observed
        won, cp = self._acquire_dispatch(claim, binding, digest)
        if not won:
            return cp
        try:
            receipt = self.native.spawn(binding, idempotency_key=digest)
        except Exception as exc:
            return self._reconcile_dispatch(
                claim, cp, 'spawn raised after possible external effect: ' + str(exc))
        return self._accept_dispatch_receipt(claim, cp, binding, receipt)

    def _accept_dispatch_receipt(self, claim, cp, binding, receipt):
        if not isinstance(receipt, dict) or receipt.get('accepted') is not True:
            return self._dispatch_hold(claim, cp,
                                       'unverifiable native acceptance receipt')
        echoed, unit = receipt.get('binding'), receipt.get('execution_unit')
        identity = receipt.get('execution_identity')
        expected_identity = {
            'executor_id': binding['executor_id'],
            'session_id': receipt.get('session_id'),
            'epoch': binding['epoch'],
            'git_commit': binding['artifact_commit'],
            'git_tree': binding['artifact_tree'],
        }
        if (not receipt.get('run_id') or not receipt.get('session_id')
                or echoed != binding or not isinstance(unit, dict)
                or unit.get('run_id') != receipt.get('run_id')
                or unit.get('session_id') != receipt.get('session_id')
                or unit.get('active') is not True
                or not isinstance(unit.get('id'), str) or not unit.get('id')
                or identity != expected_identity):
            cp.update({'phase': 'UNKNOWN_SIDE_EFFECT_HOLD', 'effects': 'unknown',
                       'receipt': receipt})
            self.ledger.checkpoint(*self._token(claim), value=cp)
            self.ledger.finish(*self._token(claim), state='WAITING_HUMAN', effects='unknown')
            return cp
        cp.update({'phase': 'STARTED', 'run_id': receipt['run_id'],
                   'session_id': receipt['session_id'],
                   'execution_unit_id': unit['id'],
                   'started_at': receipt.get('started_at', self.clock())})
        self.ledger.checkpoint(*self._token(claim), value=cp)
        return cp

    def _reconcile_dispatch(self, claim, cp, reason):
        query = getattr(self.native, 'reconcile_spawn', None)
        if query is None:
            return self._dispatch_hold(claim, cp, reason + '; provider query unavailable')
        try:
            receipt = query(cp['native_binding_hash'], cp['native_binding'])
        except Exception as exc:
            return self._dispatch_hold(claim, cp, reason + '; query failed: ' + str(exc))
        if receipt is None:
            return self._dispatch_hold(claim, cp, reason + '; query result unknown')
        return self._accept_dispatch_receipt(
            claim, cp, cp['native_binding'], receipt)

    def _dispatch_hold(self, claim, cp, reason):
        cp.update({'phase': 'UNKNOWN_SIDE_EFFECT_HOLD', 'effects': 'unknown',
                   'reason': reason,
                   'next_action': 'reconcile native spawn by idempotency key',
                   'dispatch_key': cp['native_binding_hash']})
        self.ledger.checkpoint(*self._token(claim), value=cp)
        self.ledger.finish(*self._token(claim), state='WAITING_HUMAN', effects='unknown')
        return cp

    def _acquire_dispatch(self, claim, binding, digest):
        """Atomically establish the sole native-spawn owner in the ledger.

        A persisted DISPATCHING record is deliberately never stolen: after a
        crash its external effect is unknown, so replay must reconcile instead
        of creating a second execution unit.
        """
        owner = 'dispatch-' + uuid.uuid4().hex[:12]
        with self.ledger._transaction() as conn:
            now = self.ledger._now()
            row = self.ledger._live(conn, claim['task_id'], claim['worker_id'],
                                    claim['fence'], now)
            current = json.loads(row['checkpoint'] or '{}')
            current_hash = current.get('native_binding_hash')
            if current_hash:
                if current_hash != digest:
                    raise NativeContractError('different writer already bound')
                return False, current
            cp = {'phase': 'DISPATCHING', 'native_binding': binding,
                  'native_binding_hash': digest, 'dispatch_owner': owner,
                  'delivery_attempts': 0, 'notification_delivered': False}
            packed = self.ledger._dump(cp)
            changed = conn.execute(
                'UPDATE tasks SET checkpoint=?,updated=? '
                'WHERE id=? AND checkpoint=?',
                (packed, now, claim['task_id'], row['checkpoint'])).rowcount
            if changed != 1:
                raise RuntimeError('atomic dispatch ownership lost')
            self.ledger._event(conn, claim['task_id'], 'EXECUTION_CHECKPOINTED',
                               now, {'fence': claim['fence'],
                                     'phase': 'DISPATCHING'})
            return True, cp

    def supervise(self, claim):
        cp = self.ledger.observation(claim['task_id'])['checkpoint']
        if cp.get('notification_delivered'):
            return cp
        if cp.get('phase') in ('UNKNOWN_SIDE_EFFECT_HOLD',
                               'DELIVERY_UNKNOWN_SIDE_EFFECT_HOLD'):
            return cp
        if cp.get('phase') == 'DISPATCHING':
            return self._reconcile_dispatch(claim, cp,
                                            'dispatch owner has no accepted receipt')
        if cp.get('phase') in ('DELIVERY_PENDING', 'DELIVERY_FAILED', 'RESULT_READY'):
            return self._deliver(claim, cp)
        status = self.native.status(cp['run_id'], cp['session_id'])
        if (not isinstance(status, dict) or status.get('run_id') != cp['run_id']
                or status.get('session_id') != cp['session_id']):
            return self._hold(claim, cp, 'NATIVE_STATE_UNCONFIRMED', 'unknown')
        if status.get('state') == 'unknown':
            return self._hold(claim, cp, 'NATIVE_STATE_UNCONFIRMED', 'unknown')
        report = status.get('report')
        if status.get('state') == 'completed' and not report:
            report = self.native.recover_report(cp['run_id'], cp['session_id'])
        if report:
            if (status.get('state') not in self.TERMINAL
                    or status.get('process_alive') is not False
                    or status.get('unit_active') is not False):
                return self._hold(claim, cp, 'RESULT_STOP_UNCONFIRMED', 'unknown')
            identity = self._result_identity(cp)
            if not isinstance(report, dict) or any(report.get(k) != v for k, v in identity.items()):
                return self._hold(claim, cp, 'ARTIFACT_REPORT_MISMATCH', 'unknown')
            cp.update({'phase': 'RESULT_READY', 'result': report})
            self.ledger.checkpoint(*self._token(claim), value=cp)
            return self._deliver(claim, cp)
        if (status.get('state') in self.TERMINAL
                and status.get('process_alive') is False
                and status.get('unit_active') is False):
            return self._hold(claim, cp, 'RESULT_MISSING', 'unknown')
        if self.clock() > cp['native_binding']['result_deadline']:
            return self._hold(claim, cp, 'RESULT_DEADLINE_EXCEEDED', 'unknown')
        deadline = cp['native_binding']['progress_deadline']
        progress = status.get('last_progress_at')
        if self.clock() > deadline and (not isinstance(progress, (int, float)) or progress < deadline):
            return self._hold(claim, cp, 'STALLED', 'unknown')
        return cp

    def _deliver(self, claim, cp):
        key = hashlib.sha256(('result:' + cp['native_binding_hash']).encode('utf-8')).hexdigest()
        if cp.get('phase') in ('DELIVERY_PENDING', 'DELIVERY_FAILED'):
            recovered = self._reconcile_delivery(key)
            if self._is_delivery_receipt(key, recovered):
                if cp.get('delivery_owner', '').startswith(self.instance_id + '.'):
                    return self._complete_delivery(claim, cp, key, recovered)
                won, cp = self._acquire_delivery_recovery(claim, cp, key)
                if not won:
                    return cp
                return self._complete_delivery(claim, cp, key, recovered, recovery=True)
            if cp.get('phase') == 'DELIVERY_PENDING':
                won, cp = self._acquire_delivery_recovery(claim, cp, key)
                if not won:
                    return cp
                recovered = self._reconcile_delivery(key)
                if self._is_delivery_receipt(key, recovered):
                    return self._complete_delivery(claim, cp, key, recovered, recovery=True)
                return self._delivery_hold(
                    claim, cp, 'dead delivery owner effect cannot be proven', recovery=True)
        if cp.get('delivery_attempts', 0) >= self.max_delivery_attempts:
            cp['phase'] = 'DELIVERY_FAILED'
            self.ledger.checkpoint(*self._token(claim), value=cp)
            self.ledger.finish(*self._token(claim), state='WAITING_HUMAN', effects='unknown')
            return cp
        won, cp = self._acquire_delivery(claim, key)
        if not won:
            return cp
        try:
            receipt = self.notifier.send(cp['result'], idempotency_key=key)
        except Exception as exc:
            recovered = self._reconcile_delivery(key)
            if self._is_delivery_receipt(key, recovered):
                return self._complete_delivery(claim, cp, key, recovered)
            # Keep the ownership record intact while this execution and lease
            # are live.  A different supervisor may only recover after it can
            # prove that lease dead; until then this is observation-only.
            cp['delivery_error'] = 'send raised; reconciliation unproven: ' + str(exc)
            return cp
        return self._complete_delivery(claim, cp, key, receipt)

    def _acquire_delivery(self, claim, key):
        owner = self.instance_id + '.delivery-' + uuid.uuid4().hex[:12]
        with self.ledger._transaction() as conn:
            now = self.ledger._now()
            row = self.ledger._live(conn, claim['task_id'], claim['worker_id'],
                                    claim['fence'], now)
            current = json.loads(row['checkpoint'] or '{}')
            if current.get('notification_delivered'):
                return False, current
            if current.get('delivery_owner'):
                if current.get('notification_key') != key:
                    raise NativeContractError('different delivery already bound')
                return False, current
            if current.get('phase') != 'RESULT_READY':
                return False, current
            current.update({'phase': 'DELIVERY_PENDING',
                            'notification_key': key,
                            'delivery_owner': owner,
                            'delivery_attempts': current.get('delivery_attempts', 0) + 1})
            packed = self.ledger._dump(current)
            changed = conn.execute(
                'UPDATE tasks SET checkpoint=?,updated=? WHERE id=? AND checkpoint=?',
                (packed, now, claim['task_id'], row['checkpoint'])).rowcount
            if changed != 1:
                raise RuntimeError('atomic delivery ownership lost')
            self.ledger._event(conn, claim['task_id'], 'EXECUTION_CHECKPOINTED',
                               now, {'fence': claim['fence'],
                                     'phase': 'DELIVERY_PENDING'})
            return True, current

    def _acquire_delivery_recovery(self, claim, cp, key):
        """Fence recovery behind proven lease death and a single ledger CAS."""
        owner = self.instance_id + '.recovery-' + uuid.uuid4().hex[:12]
        token = uuid.uuid4().hex
        with self.ledger._transaction() as conn:
            now = self.ledger._now()
            row = self.ledger._task(conn, claim['task_id'])
            current = json.loads(row['checkpoint'] or '{}')
            if current.get('notification_delivered'):
                return False, current
            if (current.get('phase') != 'DELIVERY_PENDING'
                    or current.get('notification_key') != key):
                return False, current
            if (row['state'] == 'RUNNING' and row['lease_owner'] is not None
                    and row['lease_until'] is not None and row['lease_until'] > now):
                return False, current
            if current.get('delivery_recovery_owner'):
                return False, current
            current.update({'delivery_recovery_owner': owner,
                            'delivery_recovery_token': token,
                            'delivery_recovery_fence': row['fence']})
            changed = conn.execute(
                'UPDATE tasks SET checkpoint=?,updated=? WHERE id=? AND checkpoint=?',
                (self.ledger._dump(current), now, claim['task_id'], row['checkpoint'])).rowcount
            if changed != 1:
                raise RuntimeError('atomic delivery recovery ownership lost')
            self.ledger._event(conn, claim['task_id'], 'EXECUTION_CHECKPOINTED',
                               now, {'fence': row['fence'], 'phase': 'DELIVERY_RECOVERY'})
            return True, current

    def _reconcile_delivery(self, key):
        try:
            return self.notifier.reconcile(key)
        except Exception:
            return None

    @staticmethod
    def _is_delivery_receipt(key, receipt):
        return (isinstance(receipt, dict)
                and receipt.get('idempotency_key') == key
                and isinstance(receipt.get('message_id'), str)
                and bool(receipt.get('message_id')))

    def _delivery_hold(self, claim, cp, reason, recovery=False):
        final = dict(cp)
        final.update({'phase': 'DELIVERY_UNKNOWN_SIDE_EFFECT_HOLD',
                      'effects': 'unknown', 'reason': reason,
                      'next_action': 'query notifier by notification_key; do not resend'})
        if recovery:
            committed, current = self._finish_delivery_recovery(
                claim, cp, final, 'WAITING_HUMAN', 'unknown')
            return final if committed else current
        else:
            self.ledger.checkpoint(*self._token(claim), value=final)
            self.ledger.finish(*self._token(claim), state='WAITING_HUMAN', effects='unknown')
        return final

    def _complete_delivery(self, claim, cp, key, receipt, recovery=False):
        if not self._is_delivery_receipt(key, receipt):
            return self._delivery_hold(claim, cp,
                                       'notifier returned unverifiable receipt')
        final = dict(cp)
        final.update({'phase': 'COMPLETED', 'notification_delivered': True,
                      'notification_key': key, 'delivery_receipt': receipt})
        if recovery:
            committed, current = self._finish_delivery_recovery(
                claim, cp, final, 'DONE', 'known')
            return final if committed else current
        else:
            self.ledger.checkpoint(*self._token(claim), value=final)
            self.ledger.finish(*self._token(claim), state='DONE', effects='known')
        return final

    def _finish_delivery_recovery(self, claim, acquired, final, state, effects):
        """Atomically commit only the still-current fenced recovery owner."""
        with self.ledger._transaction() as conn:
            now = self.ledger._now()
            row = self.ledger._task(conn, claim['task_id'])
            current = json.loads(row['checkpoint'] or '{}')
            recovery_fence = acquired.get('delivery_recovery_fence')
            if (row['fence'] != recovery_fence
                    or current != acquired
                    or current.get('delivery_recovery_owner')
                       != acquired.get('delivery_recovery_owner')
                    or current.get('delivery_recovery_token')
                       != acquired.get('delivery_recovery_token')
                    or current.get('delivery_recovery_fence') != recovery_fence
                    or current.get('notification_key') != acquired.get('notification_key')
                    or current.get('native_binding_hash')
                       != acquired.get('native_binding_hash')
                    or current.get('delivery_owner') != acquired.get('delivery_owner')
                    or (row['state'] == 'RUNNING' and row['lease_owner'] is not None
                        and row['lease_until'] is not None and row['lease_until'] > now)):
                return False, current
            changed = conn.execute(
                'UPDATE tasks SET checkpoint=?,state=?,lease_owner=NULL,'
                'lease_until=NULL,updated=? WHERE id=? AND fence=? AND checkpoint=?',
                (self.ledger._dump(final), state, now, claim['task_id'],
                 recovery_fence, row['checkpoint'])).rowcount
            if changed != 1:
                return False, current
            if state == 'WAITING_HUMAN':
                self.ledger._pending_approval(conn, claim['task_id'], now)
            self.ledger._event(conn, claim['task_id'], 'EXECUTION_FINISHED', now,
                               {'fence': recovery_fence, 'state': state,
                                'effects': effects, 'recovery': True})
            return True, final

    @staticmethod
    def _result_identity(cp):
        binding = cp['native_binding']
        keys = ('task_id', 'spec_hash', 'executor_id', 'workdir', 'artifact_commit',
                'artifact_tree', 'artifact_hash', 'lease', 'fence', 'epoch')
        result = {key: binding[key] for key in keys}
        result.update({'run_id': cp['run_id'], 'session_id': cp['session_id'],
                       'execution_unit_id': cp['execution_unit_id']})
        return result

    def _hold(self, claim, cp, reason, effects):
        cp.update({'phase': reason, 'effects': effects})
        self.ledger.checkpoint(*self._token(claim), value=cp)
        self.ledger.finish(*self._token(claim), state='WAITING_HUMAN', effects=effects)
        return cp
