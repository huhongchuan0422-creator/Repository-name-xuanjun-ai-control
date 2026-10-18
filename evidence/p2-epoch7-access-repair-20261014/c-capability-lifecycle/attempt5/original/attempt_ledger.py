"""Offline five-attempt accounting for a *new*, separately approved P2 grant.

This module does not authorize installation, create an epoch7 successor, or run
host commands. A separately reviewed executor and independent reconciliation
provider must be wired before any production use. Python 3.6 compatible.
"""
from __future__ import print_function
import fcntl
import hashlib
import json
import os
import re
import stat
import time
import uuid

MAX_ATTEMPTS = 5
HEX64 = re.compile(r'^[0-9a-f]{64}$')
STATE = ('CLAIMED', 'INTENT_RECORDED', 'UNKNOWN', 'PARTIAL_WRITE',
         'SAFE_RECONCILED', 'FAILED_NO_WRITE', 'SUCCEEDED', 'CONFLICT')


def _require(ok, code):
    if not ok:
        raise ValueError('P2_ATTEMPT5_' + code)


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _valid_grant(grant):
    keys = {'grant_id', 'source_commit', 'source_tree', 'kit_sha256',
            'manifest_sha256', 'target_host', 'actor_id', 'expires_utc',
            'recovery_entry', 'approval_body_sha256', 'max_attempts'}
    _require(type(grant) is dict and set(grant) == keys, 'GRANT_FIELDS')
    _require(type(grant['grant_id']) is str and re.match(r'^[A-Za-z0-9_-]{12,80}$', grant['grant_id']), 'GRANT_ID')
    for name in ('kit_sha256', 'manifest_sha256', 'approval_body_sha256'):
        _require(type(grant[name]) is str and HEX64.match(grant[name]), 'GRANT_DIGEST')
    for name in ('source_commit', 'source_tree'):
        _require(type(grant[name]) is str and re.match(r'^[0-9a-f]{40}$', grant[name]), 'GRANT_SOURCE')
    for name in ('target_host', 'actor_id', 'recovery_entry'):
        _require(type(grant[name]) is str and 0 < len(grant[name]) <= 256, 'GRANT_SCOPE')
    _require(type(grant['expires_utc']) is int and grant['expires_utc'] > 0, 'GRANT_TIME')
    _require(type(grant['max_attempts']) is int and grant['max_attempts'] == MAX_ATTEMPTS, 'GRANT_COUNT')
    return _digest(grant)


class Ledger(object):
    """Trusted local ledger. Caller verifies external effects independently.

    A process-global lock (flock on a persistent sidecar) prevents simultaneous
    grant mutations. Each update is fsync+atomic rename; intent is persisted
    before any executor action. Unexpected crash leaves the attempt unresolved.
    """

    def __init__(self, directory, grant, clock=None):
        self.grant = dict(grant)
        self.binding = _valid_grant(grant)
        self.clock = clock or time.time
        self.directory = os.path.abspath(directory)
        _require(self.directory == directory and os.path.isdir(directory), 'DIRECTORY')
        info = os.lstat(directory)
        _require(stat.S_ISDIR(info.st_mode) and not (stat.S_IMODE(info.st_mode) & 0o077), 'DIRECTORY_MODE')
        self.data = os.path.join(directory, 'attempts.json')
        self.lock_file = os.path.join(directory, 'attempts.lock')

    def _guard(self, fn):
        # Existing lock with absent state implies erased or missing history.
        # Never mint a fresh quota in that condition.
        existed = os.path.lexists(self.lock_file)
        fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            _require(not (existed and not os.path.lexists(self.data)), 'HISTORY_MISSING')
            state = self._read()
            value, modified = fn(state)
            if modified or not os.path.lexists(self.data):
                self._save(state)
            return value
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self):
        if not os.path.exists(self.data):
            return {'schema': 1, 'grant_binding': self.binding, 'attempts': [], 'completed': []}
        fd = os.open(self.data, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 1048576, 'LEDGER_FILE')
            raw = os.read(fd, 1048577)
            _require(len(raw) == info.st_size, 'LEDGER_BYTES')
        finally:
            os.close(fd)
        def unique(pairs):
            out = {}
            for key, val in pairs:
                _require(key not in out, 'DUPLICATE_KEY')
                out[key] = val
            return out
        state = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        _require(type(state) is dict and set(state) == {'schema', 'grant_binding', 'attempts', 'completed'} and
                 state['schema'] == 1 and state['grant_binding'] == self.binding, 'LEDGER_BINDING')
        _require(type(state['attempts']) is list and len(state['attempts']) <= 5, 'LEDGER_COUNT')
        seen_ids = set()
        for index, item in enumerate(state['attempts']):
            _require(type(item) is dict and item.get('ordinal') == index + 1 and
                     item.get('state') in STATE and type(item.get('id')) is str and
                     type(item.get('events')) is list and item['id'] not in seen_ids, 'LEDGER_HISTORY')
            seen_ids.add(item['id'])
        _require(type(state['completed']) is list, 'CHECKPOINT_SET')
        return state

    def _save(self, state):
        raw = _canonical(state)
        _require(len(raw) <= 1048576, 'LEDGER_BOUND')
        temp = os.path.join(self.directory, '.attempts-' + uuid.uuid4().hex)
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            length = 0
            while length < len(raw):
                written = os.write(fd, raw[length:])
                _require(written > 0, 'WRITE')
                length += written
            os.fsync(fd)
        finally:
            os.close(fd)
        os.rename(temp, self.data)
        parent = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)

    def _fresh(self):
        _require(self.clock() < self.grant['expires_utc'], 'EXPIRED')

    def snapshot(self):
        return self._guard(lambda state: (json.loads(json.dumps(state)), False))

    def claim(self):
        self._fresh()
        def operation(state):
            attempts = state['attempts']
            _require(len(attempts) < MAX_ATTEMPTS, 'EXHAUSTED')
            if attempts:
                last = attempts[-1]
                _require(last['state'] in ('SAFE_RECONCILED', 'FAILED_NO_WRITE'), 'UNRESOLVED')
                _require(last['events'] and last['events'][-1]['kind'] == 'independently_reconciled',
                         'RECONCILIATION_REQUIRED')
            ordinal = len(attempts) + 1
            attempt_id = self.grant['grant_id'] + '-' + str(ordinal) + '-' + uuid.uuid4().hex
            attempts.append({'id': attempt_id, 'ordinal': ordinal, 'state': 'CLAIMED',
                             'events': [{'kind': 'claim', 'at': int(self.clock())}]})
            return attempt_id, True
        return self._guard(operation)

    def intent(self, attempt_id, operation_sha):
        self._fresh()
        _require(type(operation_sha) is str and HEX64.match(operation_sha), 'OPERATION_HASH')
        def action(state):
            _require(state['attempts'] and state['attempts'][-1]['id'] == attempt_id, 'ATTEMPT_ID')
            last = state['attempts'][-1]
            _require(last['state'] == 'CLAIMED', 'INTENT_ALREADY_RECORDED')
            last['state'] = 'INTENT_RECORDED'
            last['events'].append({'kind': 'intent', 'sha256': operation_sha, 'at': int(self.clock())})
            return None, True
        self._guard(action)

    def uncertain(self, attempt_id, partial=False):
        def action(state):
            _require(state['attempts'] and state['attempts'][-1]['id'] == attempt_id, 'ATTEMPT_ID')
            last = state['attempts'][-1]
            _require(last['state'] == 'INTENT_RECORDED', 'UNCERTAIN_STATE')
            last['state'] = 'PARTIAL_WRITE' if partial else 'UNKNOWN'
            last['events'].append({'kind': 'unresolved', 'at': int(self.clock())})
            return None, True
        self._guard(action)

    def reconcile(self, attempt_id, proof, independent_verifier):
        """Verifier must authenticate terminal side effects, checkpoint and logs.

        Unlike a caller-supplied flag, the proof is only accepted after a
        separate independently trusted verifier returns True. No default.
        """
        self._fresh()
        _require(callable(independent_verifier) and type(proof) is dict and
                 set(proof) == {'outcome', 'evidence_sha256', 'checkpoint_sha256', 'log_sha256'} and
                 proof['outcome'] in ('NO_WRITE', 'SAFE_CHECKPOINT', 'SUCCESS'), 'PROOF_FIELDS')
        for key in ('evidence_sha256', 'checkpoint_sha256', 'log_sha256'):
            _require(type(proof[key]) is str and HEX64.match(proof[key]), 'PROOF_HASH')
        _require(independent_verifier(dict(proof)) is True, 'PROOF_UNVERIFIED')
        def action(state):
            _require(state['attempts'] and state['attempts'][-1]['id'] == attempt_id, 'ATTEMPT_ID')
            last = state['attempts'][-1]
            _require(last['state'] in ('INTENT_RECORDED', 'PARTIAL_WRITE', 'UNKNOWN'), 'RECONCILE_STATE')
            last['state'] = {'NO_WRITE': 'FAILED_NO_WRITE', 'SAFE_CHECKPOINT': 'SAFE_RECONCILED',
                             'SUCCESS': 'SUCCEEDED'}[proof['outcome']]
            last['events'].append({'kind': 'independently_reconciled', 'proof_sha256': _digest(proof),
                                   'at': int(self.clock())})
            return last['state'], True
        return self._guard(action)

    def checkpoint(self, attempt_id, name, fingerprint):
        _require(type(name) is str and re.match(r'^[a-z][a-z0-9_]{1,63}$', name) and
                 type(fingerprint) is str and HEX64.match(fingerprint), 'CHECKPOINT')
        def action(state):
            _require(state['attempts'] and state['attempts'][-1]['id'] == attempt_id, 'ATTEMPT_ID')
            last = state['attempts'][-1]
            _require(last['state'] == 'INTENT_RECORDED', 'CHECKPOINT_STATE')
            existing = [x for x in state['completed'] if x['name'] == name]
            _require(not existing or existing[0]['sha256'] == fingerprint, 'CHECKPOINT_CONFLICT')
            if not existing:
                state['completed'].append({'name': name, 'sha256': fingerprint})
            return bool(existing), True
        return self._guard(action)
