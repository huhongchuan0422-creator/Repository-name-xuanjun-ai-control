"""Local enforcement primitives for canonical task writer fencing.

This module deliberately does not own schema or authority allocation.  The
Supervisor is the only canonical store.  Local locks model same-host exclusion
only; production distributed enforcement still requires an admitted unique
gateway or resource-native fencing.
"""
from __future__ import print_function

import errno
import fcntl
import hashlib
import json
import os
import time


UNKNOWN = 'UNKNOWN'
LOCAL_ONLY = 'LOCAL_ONLY'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _lock_name(resource_key):
    return hashlib.sha256(resource_key.encode('utf-8')).hexdigest() + '.lock'


class LocalActionLocks(object):
    """Sorted per-resource flock set.  Capability is explicitly LOCAL_ONLY."""

    capability = LOCAL_ONLY

    def __init__(self, root):
        self.root = root

    def _open(self, resource_key):
        if not os.path.isdir(self.root):
            os.makedirs(self.root, 0o700)
        if os.path.islink(self.root):
            raise ValueError('UNSAFE_ACTION_LOCK_ROOT')
        path = os.path.join(self.root, _lock_name(resource_key))
        return os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)

    def acquire(self, resource_keys, exclusive, timeout=None):
        keys = tuple(sorted(set(resource_keys)))
        if not keys:
            raise ValueError('RESOURCE_SCOPE_REQUIRED')
        held = []
        started = time.monotonic()
        flag = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            for key in keys:
                fd = self._open(key)
                try:
                    if timeout is None:
                        fcntl.flock(fd, flag)
                    else:
                        while True:
                            try:
                                fcntl.flock(fd, flag | fcntl.LOCK_NB)
                                break
                            except OSError as error:
                                if error.errno not in (errno.EACCES,
                                                      errno.EAGAIN):
                                    raise
                                if time.monotonic() - started >= timeout:
                                    raise ValueError(
                                        'REVOCATION_NOT_COMPLETED')
                                time.sleep(0.01)
                    held.append(fd)
                except Exception:
                    os.close(fd)
                    raise
            return held
        except Exception:
            self.release(held)
            raise

    @staticmethod
    def release(held):
        while held:
            fd = held.pop()
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


class CommitLease(object):
    """Hold shared resource locks from final authority check through outcome."""

    def __init__(self, supervisor, ticket, caller, operation_id, lock_root,
                 now=None):
        self.supervisor = supervisor
        self.ticket = ticket
        self.caller = caller
        self.operation_id = operation_id
        self.now = now
        self.locks = LocalActionLocks(lock_root)
        self.held = []
        self.finished = False

    def __enter__(self):
        resource_keys = self.supervisor.ticket_resource_keys(self.ticket)
        self.held = self.locks.acquire(resource_keys, exclusive=False)
        try:
            # The authoritative re-read and PREPARED->DISPATCHING CAS happen
            # while the shared action locks are already held.
            self.supervisor.begin_dispatch(
                self.ticket, self.caller, self.operation_id, now=self.now)
            return self
        except Exception:
            self.locks.release(self.held)
            raise

    def confirmed(self, receipt, now=None):
        if self.finished:
            raise ValueError('COMMIT_LEASE_ALREADY_FINISHED')
        self.supervisor.confirm_operation(
            self.ticket, self.caller, self.operation_id, receipt, now=now)
        self.finished = True

    def unknown(self, evidence, now=None):
        if self.finished:
            raise ValueError('COMMIT_LEASE_ALREADY_FINISHED')
        self.supervisor.mark_operation_unknown(
            self.ticket, self.caller, self.operation_id, evidence, now=now)
        self.finished = True

    def __exit__(self, exc_type, exc, tb):
        try:
            if not self.finished:
                # A process that survives an exception records UNKNOWN.  A
                # hard kill cannot do this, so DISPATCHING is itself treated
                # as unresolved by revocation/recovery.
                try:
                    self.supervisor.mark_operation_unknown(
                        self.ticket, self.caller, self.operation_id,
                        {'kind': 'LEASE_EXIT_WITHOUT_FINAL_RESULT'})
                except Exception:
                    pass
        finally:
            self.locks.release(self.held)
        return False


def reconcile_unknown(supervisor, operation_id, context, outcome, evidence,
                      receipt=None, now=None):
    """Trusted readback path; it never redispatches the original effect."""
    return supervisor.reconcile_operation(
        operation_id, context, outcome, evidence, receipt=receipt, now=now)


def revoke_with_local_drain(supervisor, task_id, caller, lock_root,
                            timeout, now=None):
    """Begin revocation, then exclusively drain local in-flight actions.

    This is intentionally LOCAL_ONLY.  A successful local drain does not
    establish production-wide fencing when direct credentials or distributed
    writers exist.
    """
    resource_keys = supervisor.begin_revocation(task_id, caller, now=now)
    locks = LocalActionLocks(lock_root)
    held = locks.acquire(resource_keys, exclusive=True, timeout=timeout)
    try:
        unresolved = supervisor.unresolved_operations(task_id)
        if unresolved:
            raise ValueError('REVOCATION_NOT_COMPLETED')
        return {'state': 'LOCAL_DRAINED_RESOURCE_RECONCILIATION_REQUIRED',
                'lock_capability': locks.capability,
                'resource_keys': list(resource_keys)}
    finally:
        locks.release(held)


def production_fencing_verdict(inventory_complete, raw_write_capable,
                               lock_capability=LOCAL_ONLY):
    """Fail closed: source-level/local locking is never production proof."""
    reasons = []
    if not inventory_complete:
        reasons.append('PRODUCTION_INVENTORY_INCOMPLETE')
    if raw_write_capable:
        reasons.append('UNFENCED_PATH_PRESENT')
    if lock_capability == LOCAL_ONLY:
        reasons.append('LOCAL_LOCK_NOT_GLOBAL_FENCE')
    return {
        'framework_inventory_complete': bool(inventory_complete),
        'production_fencing': 'HOLD' if reasons else 'ELIGIBLE_FOR_REVIEW',
        'reasons': reasons,
    }
