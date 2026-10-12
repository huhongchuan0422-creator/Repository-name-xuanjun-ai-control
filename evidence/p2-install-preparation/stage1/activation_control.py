"""Crash-reconcilable authority for one active dispatcher generation.

The append-only epoch journal is outside every database generation. A journal
record is fsynced before the descriptor is atomically replaced. A crash can
disable dispatch, but cannot silently reactivate an old epoch: ``reconcile``
deterministically republishes the last durable record.
"""
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from contextlib import contextmanager


SHA256 = re.compile(r'^[0-9a-f]{64}$')
STATES = ('PREPARED', 'QUIESCED', 'ACTIVE')
ZERO_HASH = '0' * 64


class ActivationError(RuntimeError):
    pass


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256((_dump(value) + '\n').encode('utf-8')).hexdigest()


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_all(fd, value):
    position = 0
    while position < len(value):
        written = os.write(fd, value[position:])
        if written <= 0:
            raise OSError('short activation write')
        position += written


class ActivationStore(object):
    """Durable descriptor contract shared by dispatcher, broker and callback."""

    REQUIRED = frozenset(['schema', 'state', 'release_sha256', 'config_sha256',
                          'binary_sha256', 'ledger_uuid', 'generation', 'epoch',
                          'instance', 'db_path', 'ledger_socket'])
    JOURNAL_KEYS = frozenset(['schema', 'seq', 'epoch', 'state', 'previous_sha256',
                              'descriptor_sha256', 'descriptor', 'proof'])

    def __init__(self, descriptor, epoch_journal, lock_path, owner_uid=0):
        paths = (descriptor, epoch_journal, lock_path)
        if any(not isinstance(path, str) or not os.path.isabs(path) or
               os.path.realpath(path) != path for path in paths):
            raise ValueError('activation paths must be canonical absolute paths')
        self.descriptor, self.epoch_journal, self.lock_path = paths
        self.owner_uid = owner_uid
        parents = {os.path.dirname(path) for path in paths}
        if len(parents) != 1:
            raise ValueError('activation files must share one protected parent')
        self.parent = parents.pop()

    def _check_parent(self):
        info = os.stat(self.parent, follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != self.owner_uid
                or info.st_mode & 0o022):
            raise ActivationError('activation parent is not protected')

    def _locked(self):
        self._check_parent()
        authority = os.geteuid() == self.owner_uid
        flags = (os.O_RDWR | os.O_CREAT) if authority else os.O_RDONLY
        # Local Linux flock permits an exclusive lock on a read-only fd. Readers
        # synchronize with the root writer without gaining file-write authority.
        fd = os.open(self.lock_path, flags | getattr(os, 'O_NOFOLLOW', 0), 0o644)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.owner_uid
                or info.st_mode & 0o022):
            os.close(fd)
            raise ActivationError('unsafe activation lock')
        if authority:
            os.fchmod(fd, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    @classmethod
    def validate(cls, value):
        if not isinstance(value, dict) or set(value) != cls.REQUIRED:
            raise ActivationError('activation descriptor keys mismatch')
        if value['schema'] != 1 or value['state'] not in STATES:
            raise ActivationError('invalid activation schema/state')
        for key in ('release_sha256', 'config_sha256', 'binary_sha256'):
            if not isinstance(value[key], str) or not SHA256.fullmatch(value[key]):
                raise ActivationError('invalid ' + key)
        for key in ('ledger_uuid', 'instance'):
            try:
                canonical = str(uuid.UUID(value[key]))
            except (ValueError, TypeError, AttributeError):
                raise ActivationError('invalid ' + key)
            if not isinstance(value[key], str) or canonical != value[key]:
                raise ActivationError('invalid ' + key)
        if type(value['generation']) is not int or value['generation'] < 1:
            raise ActivationError('invalid generation')
        if type(value['epoch']) is not int or value['epoch'] < 1:
            raise ActivationError('invalid epoch')
        for key in ('db_path', 'ledger_socket'):
            path = value[key]
            if (not isinstance(path, str) or not os.path.isabs(path)
                    or os.path.realpath(path) != path):
                raise ActivationError(key + ' is not canonical')
        if value['db_path'] == value['ledger_socket']:
            raise ActivationError('database and ledger socket must differ')
        return dict(value)

    def _read_descriptor_unlocked(self):
        fd = os.open(self.descriptor, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.owner_uid
                or info.st_mode & 0o022 or info.st_size > 65536):
            os.close(fd)
            raise ActivationError('unsafe activation descriptor')
        with os.fdopen(fd) as handle:
            return self.validate(json.load(handle))

    def _journal(self):
        try:
            fd = os.open(self.epoch_journal, os.O_RDONLY |
                         getattr(os, 'O_NOFOLLOW', 0))
        except FileNotFoundError:
            return []
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.owner_uid
                or info.st_mode & 0o022 or info.st_size > 16 * 1024 * 1024):
            os.close(fd)
            raise ActivationError('unsafe epoch journal')
        records, previous_hash, previous = [], ZERO_HASH, None
        with os.fdopen(fd) as handle:
            for raw in handle:
                try:
                    record = json.loads(raw)
                except ValueError:
                    raise ActivationError('corrupt epoch journal')
                if not isinstance(record, dict) or set(record) != self.JOURNAL_KEYS:
                    raise ActivationError('corrupt epoch journal keys')
                descriptor = self.validate(record['descriptor'])
                if (record['schema'] != 1 or type(record['seq']) is not int
                        or record['seq'] != len(records) + 1
                        or record['epoch'] != descriptor['epoch']
                        or record['state'] != descriptor['state']
                        or record['previous_sha256'] != previous_hash
                        or record['descriptor_sha256'] != _digest(descriptor)
                        or not isinstance(record['proof'], dict)):
                    raise ActivationError('corrupt epoch journal record')
                if previous is None:
                    if descriptor['epoch'] != 1 or descriptor['state'] != 'PREPARED':
                        raise ActivationError('epoch journal must begin PREPARED at epoch 1')
                elif descriptor['epoch'] == previous['epoch']:
                    expected = {'PREPARED': 'QUIESCED', 'QUIESCED': 'ACTIVE'}.get(previous['state'])
                    if descriptor['state'] != expected:
                        raise ActivationError('invalid durable activation transition')
                    immutable = self.REQUIRED - {'state'}
                    if any(descriptor[key] != previous[key] for key in immutable):
                        raise ActivationError('activation identity changed within epoch')
                elif (descriptor['epoch'] != previous['epoch'] + 1
                      or descriptor['state'] != 'PREPARED'):
                    raise ActivationError('non-monotonic activation epoch')
                previous_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
                previous = descriptor
                records.append((record, previous_hash))
        return records

    def _write_descriptor(self, value):
        packed = (_dump(self.validate(value)) + '\n').encode('utf-8')
        fd, temporary = tempfile.mkstemp(prefix='.activation-', dir=self.parent)
        try:
            # The dispatcher/callback may be unprivileged readers. Integrity is
            # provided by root ownership and no group/other write permission.
            os.fchmod(fd, 0o644)
            _write_all(fd, packed)
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.replace(temporary, self.descriptor)
            _fsync_dir(self.parent)
        finally:
            if fd >= 0:
                os.close(fd)
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _append(self, value, records, proof):
        value = self.validate(value)
        record = {'schema': 1, 'seq': len(records) + 1, 'epoch': value['epoch'],
                  'state': value['state'],
                  'previous_sha256': records[-1][1] if records else ZERO_HASH,
                  'descriptor_sha256': _digest(value), 'descriptor': value,
                  'proof': proof}
        packed = (_dump(record) + '\n').encode('utf-8')
        fd = os.open(self.epoch_journal, os.O_WRONLY | os.O_APPEND | os.O_CREAT |
                     getattr(os, 'O_NOFOLLOW', 0), 0o644)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.owner_uid
                    or info.st_mode & 0o022):
                raise ActivationError('unsafe epoch journal')
            os.fchmod(fd, 0o644)
            _write_all(fd, packed)
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(self.parent)

    def read(self, require_active=False):
        self._check_parent()
        records = self._journal()
        if not records:
            raise ActivationError('activation journal is empty')
        value = self._read_descriptor_unlocked()
        if value != records[-1][0]['descriptor']:
            raise ActivationError('activation requires journal reconciliation')
        if require_active and value['state'] != 'ACTIVE':
            raise ActivationError('dispatcher activation is not ACTIVE')
        return value

    @staticmethod
    def head(value):
        """Return the canonical SHA256 identity used for activation CAS."""
        return _digest(ActivationStore.validate(value))

    @contextmanager
    def guard_head(self, expected_head, require_active=True):
        """Hold the activation lock while a bound write commits."""
        if not SHA256.fullmatch(expected_head or ''):
            raise ActivationError('invalid activation expected head')
        lock = self._locked()
        try:
            records = self._journal()
            if not records:
                raise ActivationError('activation journal is empty')
            value = self._read_descriptor_unlocked()
            if (value != records[-1][0]['descriptor']
                    or _digest(value) != expected_head
                    or (require_active and value['state'] != 'ACTIVE')):
                raise ActivationError('STALE_ACTIVATION_HEAD_HOLD_REREAD')
            yield value
        finally:
            os.close(lock)

    def reconcile(self):
        """Publish the last durable journal state; never invent a transition."""
        lock = self._locked()
        try:
            records = self._journal()
            if not records:
                raise ActivationError('activation journal is empty')
            value = records[-1][0]['descriptor']
            try:
                if self._read_descriptor_unlocked() == value:
                    return value
            except (FileNotFoundError, ValueError, ActivationError):
                pass
            self._write_descriptor(value)
            return value
        finally:
            os.close(lock)

    def prepare(self, release_sha256, config_sha256, binary_sha256, ledger_uuid,
                generation, instance, db_path, ledger_socket, expected_epoch=None):
        lock = self._locked()
        try:
            records = self._journal()
            current = records[-1][0]['descriptor'] if records else None
            if current is not None:
                try:
                    published = self._read_descriptor_unlocked()
                except FileNotFoundError:
                    published = None
                if published != current:
                    raise ActivationError('activation requires journal reconciliation')
                if current['state'] != 'ACTIVE':
                    raise ActivationError('previous activation is not ACTIVE')
            old_epoch = current['epoch'] if current else 0
            if expected_epoch is not None and expected_epoch != old_epoch:
                raise ActivationError('activation epoch CAS failed')
            if current is not None and generation <= current['generation']:
                raise ActivationError('activation generation must advance')
            value = {'schema': 1, 'state': 'PREPARED',
                     'release_sha256': release_sha256, 'config_sha256': config_sha256,
                     'binary_sha256': binary_sha256, 'ledger_uuid': ledger_uuid,
                     'generation': generation, 'epoch': old_epoch + 1,
                     'instance': instance, 'db_path': os.path.realpath(db_path),
                     'ledger_socket': os.path.realpath(ledger_socket)}
            self._append(value, records, {})
            self._write_descriptor(value)
            return value
        finally:
            os.close(lock)

    def transition(self, expected_state, new_state, epoch, instance, proof=None):
        if (expected_state, new_state) not in (('PREPARED', 'QUIESCED'),
                                               ('QUIESCED', 'ACTIVE')):
            raise ActivationError('invalid activation transition')
        lock = self._locked()
        try:
            records = self._journal()
            if not records:
                raise ActivationError('activation journal is empty')
            current = records[-1][0]['descriptor']
            if (self._read_descriptor_unlocked() != current
                    or current['state'] != expected_state or current['epoch'] != epoch
                    or current['instance'] != instance):
                raise ActivationError('activation transition CAS failed')
            if new_state == 'QUIESCED':
                required = ('identity_verified', 'coordinator_inactive',
                            'parent_unit_inactive', 'cgroups_empty', 'restart_inhibited')
                if (not isinstance(proof, dict) or set(proof) != set(required)
                        or any(proof[key] is not True for key in required)):
                    raise ActivationError('legacy exclusion proof incomplete')
            elif (not isinstance(proof, dict) or set(proof) != {'database_reopened'}
                  or proof['database_reopened'] is not True):
                raise ActivationError('database reopen proof required')
            updated = dict(current, state=new_state)
            self._append(updated, records, proof)
            self._write_descriptor(updated)
            return updated
        finally:
            os.close(lock)
