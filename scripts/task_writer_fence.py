"""Source-only writer fencing enforcement for the canonical Supervisor.

All authority state and durable operation data live in task_supervisor.
This module supplies a fixed LOCAL_ONLY lock provider and pure-offline adapters.
It grants no production credential, network permission, or distributed fence.
"""
from __future__ import print_function

import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import time


LOCAL_ONLY = 'LOCAL_ONLY'
SOURCE_ONLY = 'SOURCE_ONLY'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _safe_atom(value):
    return (isinstance(value, str) and bool(value)
            and value == value.strip()
            and all(33 <= ord(ch) < 127 for ch in value)
            and re.fullmatch(r'[A-Za-z0-9._@+\-]+', value) is not None
            and value not in ('.', '..'))


def _safe_segmented(value, exact_parts=None):
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    parts = value.split('/')
    if exact_parts is not None and len(parts) != exact_parts:
        return False
    return bool(parts) and all(_safe_atom(part) for part in parts)


def _git_oid(value):
    return (isinstance(value, str)
            and re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', value)
            is not None)


class SourceResourceAdapter(object):
    """Trusted source-test normalization boundary; never a production adapter."""

    adapter_id = 'source-resource-adapter-v1'
    capability = LOCAL_ONLY

    def normalize(self, value):
        if not isinstance(value, str) or ':' not in value:
            raise ValueError('CANONICAL_RESOURCE_KEY_REQUIRED')
        kind, raw = value.split(':', 1)
        if kind not in ('fake', 'git') or not raw:
            raise ValueError('CANONICAL_RESOURCE_KEY_REQUIRED')
        parts = raw.split('/')
        if (any(not _safe_atom(part) for part in parts)
                or any(part in ('.', '..') for part in parts)):
            raise ValueError('CANONICAL_RESOURCE_KEY_REQUIRED')
        return kind + ':' + '/'.join(parts)

    def normalize_many(self, values):
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError('RESOURCE_SCOPE_REQUIRED')
        result = [self.normalize(value) for value in values]
        if len(result) != len(set(result)):
            raise ValueError('RESOURCE_ALIAS_COLLISION')
        return sorted(result)

    def recovery_inventory(self, supervisor, task_id, values, evidence_id,
                           provider_id):
        task = supervisor._task(task_id)
        keys = self.normalize_many(values)
        scope = supervisor._scope_digest(keys)
        return {
            'schema': 1,
            'source': 'TRUSTED_SOURCE_INVENTORY',
            'provider_id': provider_id,
            'evidence_id': evidence_id,
            'task_id': task_id,
            'old_attempt_id': task['attempt_id'],
            'resource_keys': keys,
            'resource_scope_digest': scope,
        }

    def invalidation_receipt(self, supervisor, task_id, resource_key,
                             provider_id, evidence_id):
        task = supervisor._task(task_id)
        key = self.normalize(resource_key)
        ticket = supervisor._authority_ticket(task)
        return {
            'schema': 1,
            'kind': 'RESOURCE_INVALIDATION',
            'capability': LOCAL_ONLY,
            'adapter_id': self.adapter_id,
            'provider_id': provider_id,
            'task_id': task_id,
            'old_attempt_id': task['attempt_id'],
            'old_lease_id': task['lease_id'],
            'old_fence': task['fence'],
            'old_epoch': task['epoch'],
            'ticket_sha256': supervisor._ticket_sha(ticket),
            'spec_sha256': task['spec_sha256'],
            'resource_scope_digest': task['resource_scope_digest'],
            'resource_key': key,
            'outcome': 'INVALIDATED',
            'evidence_id': evidence_id,
        }


class LocalActionLocks(object):
    """One pinned, private LOCAL_ONLY lock root shared by one trusted Fence."""

    capability = LOCAL_ONLY

    def __init__(self, root):
        self.root = os.path.realpath(root)
        if self.root != root:
            raise ValueError('CANONICAL_LOCK_ROOT_REQUIRED')
        if not os.path.exists(root):
            os.mkdir(root, 0o700)
        self.root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self.root_fd)
        current = os.lstat(root)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700
                or (current.st_dev, current.st_ino)
                   != (info.st_dev, info.st_ino)):
            os.close(self.root_fd)
            raise ValueError('UNSAFE_ACTION_LOCK_ROOT')
        self.root_identity = (info.st_dev, info.st_ino)
        self.provider_id = 'local-lock:%d:%d' % self.root_identity

    def close(self):
        if self.root_fd is not None:
            os.close(self.root_fd)
            self.root_fd = None

    def _validate_root(self):
        if self.root_fd is None:
            raise ValueError('LOCK_PROVIDER_CLOSED')
        info = os.fstat(self.root_fd)
        current = os.lstat(self.root)
        if ((current.st_dev, current.st_ino) != self.root_identity
                or (info.st_dev, info.st_ino) != self.root_identity
                or not stat.S_ISDIR(current.st_mode)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) != 0o700):
            raise ValueError('ACTION_LOCK_ROOT_CHANGED')

    @staticmethod
    def _lock_name(resource_key):
        return hashlib.sha256(resource_key.encode('utf-8')).hexdigest() + '.lock'

    def _open_lock(self, resource_key):
        self._validate_root()
        name = self._lock_name(resource_key)
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                     0o600, dir_fd=self.root_fd)
        info = os.fstat(fd)
        current = os.stat(name, dir_fd=self.root_fd, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or (current.st_dev, current.st_ino)
                   != (info.st_dev, info.st_ino)):
            os.close(fd)
            raise ValueError('UNSAFE_ACTION_LOCK')
        self._validate_root()
        return fd

    def acquire(self, resource_keys, exclusive=False, timeout=None):
        keys = tuple(sorted(resource_keys))
        if not keys:
            raise ValueError('RESOURCE_SCOPE_REQUIRED')
        held = []
        started = time.monotonic()
        flag = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            for key in keys:
                fd = self._open_lock(key)
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
            self._validate_root()
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


class FakeTransactionalSink(object):
    """Pure offline CAS sink with attributable before/after receipts."""

    adapter_id = 'fake-transactional-sink-v1'

    def __init__(self):
        self.values = {}
        self.effects = {}

    def apply(self, operation):
        key = operation['resource_key']
        expected = operation['expected_before']
        requested = operation['requested_after']
        current = self.values.get(key, expected)
        if current != expected:
            return self.receipt(operation, 'CONFLICT', current, current)
        marker = operation['operation_marker']
        if marker in self.effects:
            return self.effects[marker]
        self.values[key] = requested
        receipt = self.receipt(operation, 'CONFIRMED', expected, requested,
                               kind='FAKE_TXN')
        self.effects[marker] = receipt
        return receipt

    @staticmethod
    def receipt(operation, outcome, before, after, kind='READBACK'):
        return {
            'schema': 1,
            'outcome': outcome,
            'operation_id': operation['operation_id'],
            'resource_key': operation['resource_key'],
            'operation_marker': operation['operation_marker'],
            'attribution': {'kind': kind, 'before': before, 'after': after},
        }


class OfflineGitCAS(object):
    """Pure validator for attributable GitHub commit readback; no network."""

    @staticmethod
    def operation(operation_id, event_id, resource_key, repo, branch,
                  base_head, before_tree, before_blob, after_tree, after_blob,
                  marker):
        if (not _safe_segmented(repo, exact_parts=2)
                or not _safe_segmented(branch)
                or not all(_git_oid(x) for x in
                           (base_head, before_tree, before_blob,
                            after_tree, after_blob))
                or not _safe_atom(marker)):
            raise ValueError('CANONICAL_GIT_IDENTITY_REQUIRED')
        before = {'repo': repo, 'branch': branch, 'head': base_head,
                  'tree': before_tree, 'blob': before_blob}
        after = {'repo': repo, 'branch': branch, 'parent': base_head,
                 'tree': after_tree, 'blob': after_blob}
        return {
            'operation_id': operation_id,
            'event_id': event_id,
            'resource_key': resource_key,
            'operation_kind': 'GIT_CAS',
            'expected_before': before,
            'requested_after': after,
            'request_sha256': digest(after),
            'operation_marker': marker,
        }

    @staticmethod
    def validate(operation, readback):
        required = {'repo','branch','commit','parent','tree','blob','marker'}
        if not isinstance(readback, dict) or set(readback) != required:
            raise ValueError('EXACT_GIT_READBACK_REQUIRED')
        before = operation['expected_before']
        after = operation['requested_after']
        if (not _safe_segmented(readback['repo'], exact_parts=2)
                or not _safe_segmented(readback['branch'])
                or not _git_oid(readback['commit'])
                or not all(_git_oid(readback[x])
                           for x in ('parent','tree','blob'))
                or not _safe_atom(readback['marker'])):
            raise ValueError('CANONICAL_GIT_READBACK_REQUIRED')
        if (readback['repo'] != before['repo']
                or readback['branch'] != before['branch']):
            outcome = 'CONFLICT'
        elif readback['marker'] != operation['operation_marker']:
            outcome = 'CONFLICT'
        elif (readback['parent'] == before['head']
              and readback['tree'] == after['tree']
              and readback['blob'] == after['blob']):
            outcome = 'CONFIRMED'
        else:
            outcome = 'CONFLICT'
        receipt = FakeTransactionalSink.receipt(
            operation, outcome, before,
            after if outcome == 'CONFIRMED' else readback,
            kind='GIT_CAS' if outcome == 'CONFIRMED' else 'READBACK')
        receipt['observed_revision'] = readback['commit']
        return receipt


class CommitLease(object):
    def __init__(self, fence, ticket, caller, operation_id):
        self.fence = fence
        self.ticket = ticket
        self.caller = caller
        self.operation_id = operation_id
        self.held = []
        self.finished = False

    def __enter__(self):
        keys = self.fence.supervisor.ticket_resource_keys(self.ticket)
        self.held = self.fence.locks.acquire(keys, exclusive=False)
        try:
            self.fence.supervisor.begin_dispatch(
                self.ticket, self.caller, self.operation_id,
                self.fence.locks.provider_id)
            return self
        except Exception:
            self.fence.locks.release(self.held)
            raise

    def confirmed(self, receipt):
        if self.finished:
            raise ValueError('COMMIT_LEASE_ALREADY_FINISHED')
        self.fence.supervisor.confirm_operation(
            self.ticket, self.caller, self.operation_id, receipt,
            self.fence.locks.provider_id)
        self.finished = True

    def unknown(self, evidence):
        if self.finished:
            raise ValueError('COMMIT_LEASE_ALREADY_FINISHED')
        self.fence.supervisor.mark_operation_unknown(
            self.ticket, self.caller, self.operation_id, evidence,
            self.fence.locks.provider_id)
        self.finished = True

    def __exit__(self, exc_type, exc, tb):
        try:
            if not self.finished:
                try:
                    self.fence.supervisor.mark_operation_unknown(
                        self.ticket, self.caller, self.operation_id,
                        {'kind': 'LEASE_EXIT_WITHOUT_FINAL_RESULT'},
                        self.fence.locks.provider_id)
                except Exception:
                    pass
        finally:
            self.fence.locks.release(self.held)
        return False


class Fence(object):
    """Fixed source-only Fence instance; callers cannot choose lock roots."""

    def __init__(self, supervisor, lock_root, adapter=None):
        self.supervisor = supervisor
        self.adapter = adapter or SourceResourceAdapter()
        self.locks = LocalActionLocks(lock_root)

    def close(self):
        self.locks.close()

    def claim(self, task_id, attempt_id, owner, entry, caller, lease_id,
              resources, valid_until):
        keys = self.adapter.normalize_many(resources)
        return self.supervisor.claim_writer(
            task_id, attempt_id, owner, entry, caller, lease_id,
            self.locks.provider_id, keys, valid_until)

    def prepare(self, ticket, caller, operation):
        operation = dict(operation)
        operation['resource_key'] = self.adapter.normalize(
            operation['resource_key'])
        return self.supervisor.prepare_operation(
            ticket, caller, operation, self.locks.provider_id)

    def commit_lease(self, ticket, caller, operation_id):
        return CommitLease(self, ticket, caller, operation_id)

    def begin_revocation(self, task_id, controller):
        return self.supervisor.begin_revocation(task_id, controller)

    def drain(self, task_id, controller, timeout):
        keys = self.supervisor.begin_revocation(task_id, controller)
        held = self.locks.acquire(keys, exclusive=True, timeout=timeout)
        try:
            task = self.supervisor._task(task_id)
            ticket = self.supervisor._authority_ticket(task)
            receipt = {
                'schema': 1, 'kind': 'LOCAL_DRAIN',
                'capability': LOCAL_ONLY, 'task_id': task_id,
                'old_attempt_id': task['attempt_id'],
                'old_lease_id': task['lease_id'],
                'old_fence': task['fence'],
                'old_epoch': task['epoch'],
                'ticket_sha256': self.supervisor._ticket_sha(ticket),
                'spec_sha256': task['spec_sha256'],
                'provider_id': self.locks.provider_id,
                'resource_scope_digest': task['resource_scope_digest'],
                'outcome': 'DRAINED',
            }
            self.supervisor.record_revocation_drain(
                task_id, self.locks.provider_id, receipt)
            return receipt
        finally:
            self.locks.release(held)

    def invalidate_source_resources(self, task_id, evidence_prefix):
        task = self.supervisor._task(task_id)
        results = []
        for index, key in enumerate(json.loads(task['resource_scope_json'])):
            receipt = self.adapter.invalidation_receipt(
                self.supervisor, task_id, key, self.locks.provider_id,
                '%s-%d' % (evidence_prefix, index))
            results.append(
                self.supervisor.record_resource_invalidation(task_id, receipt))
        return results

    def recover_unknown(self, task_id, controller, resources, evidence_id):
        inventory = self.adapter.recovery_inventory(
            self.supervisor, task_id, resources, evidence_id,
            self.locks.provider_id)
        return self.supervisor.recover_unknown_from_inventory(
            task_id, controller, inventory)


def reconcile_unknown(supervisor, operation_id, context, outcome, evidence,
                      receipt=None):
    return supervisor.reconcile_operation(
        operation_id, context, outcome, evidence, receipt=receipt)


def production_fencing_verdict(capability=LOCAL_ONLY):
    """Production verdict is fixed HOLD for this source-only implementation."""
    if capability != LOCAL_ONLY:
        return {'production_fencing': 'HOLD',
                'reasons': ['UNKNOWN_OR_UNADMITTED_CAPABILITY']}
    return {
        'framework_inventory': 'SOURCE_ONLY',
        'production_inventory': 'INCOMPLETE',
        'production_fencing': 'HOLD',
        'reasons': [
            'PRODUCTION_INVENTORY_INCOMPLETE',
            'LOCAL_LOCK_NOT_GLOBAL_FENCE',
            'REAL_ADAPTER_NOT_EXECUTED',
        ],
    }
