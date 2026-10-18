"""Versioned Epoch7 Attempt5 native recovery coordinator. Python 3.6.
No implicit authority, phase SKIP, legacy successor reuse, or UK commands.
"""
import hashlib
import json
import re

class Hold(RuntimeError):
    pass

def check(ok, code):
    if not ok:
        raise Hold('EPOCH7_NATIVE5_' + code)

class NativeAttemptCoordinator(object):
    """Uses existing Ledger, but delegates all host effects to trusted native backend.

    Backend must independently authenticate the issuer and grant, acquire and
    verify cross-host fencing, persist native phase intent, verify actual effects,
    and return transaction readback. This module does NOT authenticate a backend.
    """
    def __init__(self, ledger, phase_order, backend=None):
        from attempt_ledger import Ledger
        check(isinstance(ledger, Ledger), 'LEDGER')
        check(type(phase_order) in (list, tuple) and len(phase_order) == 16
              and len(set(phase_order)) == 16, 'PHASE_ORDER')
        self.ledger = ledger
        self.phases = tuple(phase_order)
        self.backend = backend

    def _provider(self):
        b = self.backend
        check(b is not None and all(callable(getattr(b, method, None)) for method in
              ('authenticate_grant', 'acquire_fence', 'verify_fence',
               'read_transaction', 'reconcile_phase', 'transition_phase',
               'reconcile_terminal')), 'TRUST_PROVIDER_NOT_CONNECTED')
        check(b.authenticate_grant(self.ledger.grant) is True,
              'APPROVAL_UNVERIFIED')
        return b

    def _fence(self, attempt, step):
        b = self._provider()
        check(b.verify_fence(self.ledger.grant, attempt, step) is True,
              'WRITER_LEASE_FENCE_UNKNOWN')
        return b

    def _receipt(self, attempt):
        r = self.backend.read_transaction(self.ledger.grant, attempt)
        check(type(r) is dict and set(r) == {
              'grant_id','attempt_id','run_id','job_id','invoke_id',
              'backup_sha256','checkpoint_sha256','completed','status'},
              'RECEIPT_SCHEMA')
        check(r['grant_id'] == self.ledger.grant['grant_id'] and
              r['attempt_id'] == attempt, 'RECEIPT_BINDING')
        check(all(type(r[k]) is str and bool(r[k]) for k in
              ('run_id','job_id','invoke_id','backup_sha256','checkpoint_sha256')),
              'RECEIPT_MISSING')
        completed = r['completed']
        check(type(completed) is list and completed ==
              list(self.phases[:len(completed)]), 'NATIVE_PHASE_ORDER')
        check(type(r['status']) is str and r['status'] in ('NOT_DISPATCHED','RUNNING','RECONCILED','SUCCEEDED'),
              'UNKNOWN')
        return r

    def claim(self, command_sha):
        b = self._provider()
        check(b.acquire_fence(self.ledger.grant) is True, 'FENCE_UNKNOWN')
        # Ledger claim remains durable even if a later call is interrupted.
        attempt = self.ledger.claim()
        # Interruption after claim consumes capacity; never resets quota.
        self.ledger.intent(attempt, command_sha)
        return attempt

    def advance(self, attempt):
        # No execution until a trusted native host backend has been installed;
        # returned booleans are not sufficient as signatures or CAS evidence.
        self._fence(attempt, 'START')
        snapshot = self.ledger.snapshot()
        check(snapshot['attempts'] and snapshot['attempts'][-1]['id'] == attempt
              and snapshot['attempts'][-1]['state'] == 'INTENT_RECORDED',
              'INTENT_REQUIRED')
        completed = self._receipt(attempt)['completed']
        # Native recovery must be proven by a trusted host-side state machine.
        # The current provider contract does not expose an authenticated
        # generation/CAS proof. Therefore never execute host side effects yet.
        check(False, 'HOST_NATIVE_TRANSITION_NOT_CONNECTED')
        pins = {p['name']:p['sha256'] for p in snapshot['completed']}
        # Previously completed effects are verified by native readback.
        # They are never executed with a special SKIP command.
        for phase in completed:
            check(phase in pins, 'MISSING_CHECKPOINT')
            self._fence(attempt, 'RECOVER_'+phase)
            check(self.backend.reconcile_phase(self.ledger.grant, attempt,
                  phase, pins[phase], 'RECOVERY') is True, 'RECOVERY_UNVERIFIED')
        for phase in self.phases[len(completed):]:
            self._fence(attempt, 'BEFORE_'+phase)
            check(self._receipt(attempt)['completed'] == completed,
                  'CONCURRENT_DRIFT')
            outcome = self.backend.transition_phase(self.ledger.grant, attempt, phase)
            check(type(outcome) is dict and set(outcome) ==
                  {'status','checkpoint_sha256'} and outcome['status'] == 'COMMITTED'
                  and type(outcome['checkpoint_sha256']) is str
                  and re.match(r'^[0-9a-f]{64}
                  'TRANSITION_UNKNOWN')
            self._fence(attempt, 'AFTER_'+phase)
            check(self._receipt(attempt)['completed'] == completed+[phase],
                  'COMMIT_READBACK_UNKNOWN')
            check(self.backend.reconcile_phase(self.ledger.grant, attempt,
                  phase, outcome['checkpoint_sha256'], 'COMMIT') is True,
                  'EFFECT_UNVERIFIED')
            self.ledger.checkpoint(attempt, phase, outcome['checkpoint_sha256'])
            completed = completed+[phase]
        return tuple(completed)

    def finish(self, attempt, proof):
        self._fence(attempt, 'FINISH')
        r = self._receipt(attempt)
        check(r['status'] == 'SUCCEEDED' and r['completed'] == list(self.phases),
              'TERMINAL_UNKNOWN')
        return self.ledger.reconcile(attempt, proof, lambda value:
            self.backend.reconcile_terminal(self.ledger.grant, attempt, value) is True)
, outcome['checkpoint_sha256']) is not None,
                  'TRANSITION_UNKNOWN')
            self._fence(attempt, 'AFTER_'+phase)
            check(self._receipt(attempt)['completed'] == completed+[phase],
                  'COMMIT_READBACK_UNKNOWN')
            check(self.backend.reconcile_phase(self.ledger.grant, attempt,
                  phase, outcome['checkpoint_sha256'], 'COMMIT') is True,
                  'EFFECT_UNVERIFIED')
            self.ledger.checkpoint(attempt, phase, outcome['checkpoint_sha256'])
            completed = completed+[phase]
        return tuple(completed)

    def finish(self, attempt, proof):
        self._fence(attempt, 'FINISH')
        r = self._receipt(attempt)
        check(r['status'] == 'SUCCEEDED' and r['completed'] == list(self.phases),
              'TERMINAL_UNKNOWN')
        return self.ledger.reconcile(attempt, proof, lambda value:
            self.backend.reconcile_terminal(self.ledger.grant, attempt, value) is True)
