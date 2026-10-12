"""Fixed UK runtime provisioning for the unified P2 install transaction.

This module never discovers credentials, copies OAuth, installs packages, or
starts a legacy writer.  Every source/target/hash/uid/gid/mode is supplied by
the reviewed plan and checked before the first target mutation.
"""
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import tempfile

from ledger_cutover_transaction import _atomic_receipt


HOST = 'iZd7oeikknn1z21sq6ji6zZ'
SHA256 = re.compile(r'^[0-9a-f]{64}$')
TOKEN = re.compile(br'@@[A-Z0-9_]+@@')
ALLOWED_SERVICES = (
    'xj-root-broker.socket',
    'xuanjun-ledger.socket',
    'xuanjun-uk-owner-callback.service',
    'xuanjun-uk-owner-dashboard.service',
    'xuanjun-development-dispatcher.service',
    'xuanjun-github-intake.timer',
)
ALLOWED_TARGET_PREFIXES = (
    '/etc/xuanjun-development/',
    '/etc/systemd/system/',
    '/etc/nginx/conf.d/',
)


def _digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _read_regular(path, limit=1024 * 1024):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('UNSAFE_REGULAR_FILE_REFERENCE')
        data = b''
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk: break
            data += chunk
        if len(data) > limit: raise ValueError('REFERENCE_TOO_LARGE')
        return data, info
    finally:
        os.close(fd)


class FixedHostRuntime(object):
    def __init__(self, transaction_directory, run=subprocess.run):
        if (not os.path.isabs(transaction_directory)
                or os.path.realpath(transaction_directory) != transaction_directory):
            raise ValueError('CANONICAL_RUNTIME_TRANSACTION_DIRECTORY_REQUIRED')
        self.directory = transaction_directory
        self.run = run
        self.receipt_path = os.path.join(transaction_directory, 'runtime-provisioning.json')

    def _authority(self):
        if os.geteuid() != 0 or socket.gethostname().split('.')[0] != HOST:
            raise ValueError('FIXED_UK_ROOT_RUNTIME_REQUIRED')
        info = os.lstat(self.directory)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError('PROTECTED_RUNTIME_TRANSACTION_DIRECTORY_REQUIRED')

    def _command(self, command):
        result = self.run(command, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=45, check=False)
        if result.returncode:
            raise RuntimeError('RUNTIME_COMMAND_FAILED')

    @staticmethod
    def _reference(value):
        data, info = _read_regular(value['path'])
        if (info.st_uid != value['owner_uid']
                or stat.S_IMODE(info.st_mode) != value['mode']
                or _digest_bytes(data) != value['sha256']):
            raise ValueError('REFERENCE_IDENTITY_MISMATCH')

    @staticmethod
    def _binding(binding, release):
        required = {'source', 'target', 'source_sha256', 'rendered_sha256',
                    'mode', 'owner_uid', 'group_gid', 'replacements'}
        if not isinstance(binding, dict) or set(binding) != required:
            raise ValueError('EXACT_PROVISIONING_BINDING_REQUIRED')
        source = os.path.realpath(os.path.join(release, binding['source']))
        target = binding['target']
        if (not isinstance(binding['source'], str) or binding['source'].startswith('/')
                or '..' in binding['source'].split('/')
                or not source.startswith(release + '/')
                or not isinstance(target, str) or os.path.realpath(target) != target
                or not any(target.startswith(prefix) for prefix in ALLOWED_TARGET_PREFIXES)
                or not SHA256.fullmatch(binding.get('source_sha256', ''))
                or not SHA256.fullmatch(binding.get('rendered_sha256', ''))
                or type(binding.get('mode')) is not int or binding['mode'] & 0o022
                or type(binding.get('owner_uid')) is not int
                or type(binding.get('group_gid')) is not int
                or not isinstance(binding.get('replacements'), dict)):
            raise ValueError('INVALID_PROVISIONING_BINDING')
        for token, replacement in binding['replacements'].items():
            if (not isinstance(token, str) or not re.fullmatch(r'@@[A-Z0-9_]+@@', token)
                    or not isinstance(replacement, str) or '\x00' in replacement):
                raise ValueError('INVALID_RUNTIME_REPLACEMENT')
        return source, target

    def preflight(self, runtime, auth, tls):
        self._authority()
        if tuple(runtime['services']) != ALLOWED_SERVICES:
            raise ValueError('EXACT_RUNTIME_SERVICE_ORDER_REQUIRED')
        if os.path.lexists(self.receipt_path):
            raise ValueError('HOLD_EXISTING_RUNTIME_RECEIPT')
        for reference in auth['references'] + tls['references']:
            self._reference(reference)
        release = '/opt/xuanjun-control-releases/' + runtime['release_directory']
        if os.path.realpath(release) != release:
            raise ValueError('NON_CANONICAL_RELEASE_DIRECTORY')
        seen = set()
        for binding in runtime['provisioning']:
            source, target = self._binding(binding, release)
            if target in seen: raise ValueError('DUPLICATE_RUNTIME_TARGET')
            seen.add(target)
            # The immutable release does not exist on a first installation.
            # Its installer verifies every source hash before staging; verify
            # the installed bytes again in provision before target effects.
        return True

    @staticmethod
    def _render(source, binding):
        value = source
        for token in sorted(binding['replacements']):
            value = value.replace(token.encode('ascii'),
                                  binding['replacements'][token].encode('utf-8'))
        if TOKEN.search(value): raise ValueError('UNRESOLVED_RUNTIME_PLACEHOLDER')
        if _digest_bytes(value) != binding['rendered_sha256']:
            raise ValueError('RUNTIME_RENDERED_HASH_MISMATCH')
        return value

    @staticmethod
    def _atomic_target(path, data, mode, uid, gid):
        parent = os.path.dirname(path)
        info = os.lstat(parent)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
            raise ValueError('UNSAFE_RUNTIME_TARGET_PARENT')
        fd, temporary = tempfile.mkstemp(prefix='.p2-runtime-', dir=parent)
        try:
            os.fchmod(fd, mode); os.fchown(fd, uid, gid)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def provision(self, release, runtime):
        self._authority()
        expected = '/opt/xuanjun-control-releases/' + runtime['release_directory']
        if release != expected: raise ValueError('RUNTIME_RELEASE_MISMATCH')
        prepared = []
        for number, binding in enumerate(runtime['provisioning']):
            source, target = self._binding(binding, release)
            data, unused = _read_regular(source)
            if _digest_bytes(data) != binding['source_sha256']:
                raise ValueError('RUNTIME_SOURCE_HASH_MISMATCH')
            rendered = self._render(data, binding)
            previous = None
            if os.path.lexists(target):
                old, info = _read_regular(target)
                backup = os.path.join(self.directory, 'target-%03d.backup' % number)
                fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             getattr(os, 'O_NOFOLLOW', 0), 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(old); stream.flush(); os.fsync(stream.fileno())
                previous = {'backup': backup, 'sha256': _digest_bytes(old),
                            'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid,
                            'gid': info.st_gid}
            prepared.append({'target': target, 'previous': previous,
                             'rendered_sha256': binding['rendered_sha256'],
                             'mode': binding['mode'], 'uid': binding['owner_uid'],
                             'gid': binding['group_gid'], 'data': rendered})
        receipt = {'schema': 1, 'targets': [dict(item, data=None) for item in prepared],
                   'services': list(ALLOWED_SERVICES), 'rollback_complete': True}
        packed = json.dumps(receipt, sort_keys=True,
                            separators=(',', ':')).encode('utf-8')
        reference = {'schema': 1, 'receipt_sha256': _digest_bytes(packed),
                     'rollback_complete': True}
        _atomic_receipt(self.receipt_path, receipt)
        try:
            for item in prepared:
                self._atomic_target(item['target'], item['data'], item['mode'],
                                    item['uid'], item['gid'])
            self._command(['/usr/bin/systemctl', 'daemon-reload'])
            if any(item['target'].startswith('/etc/nginx/') for item in prepared):
                self._command(['/usr/sbin/nginx', '-t'])
            return reference
        except Exception:
            # The receipt was durable before the first target effect. Restore
            # the exact previous bytes immediately; the outer transaction will
            # still enter HOLD/ROLLED_BACK and never restart a legacy writer.
            self.restore(reference)
            raise

    def activate(self, runtime, descriptor):
        self._authority()
        for service in ALLOWED_SERVICES:
            self._command(['/usr/bin/systemctl', 'start', service])
            self._command(['/usr/bin/systemctl', 'is-active', '--quiet', service])
        if any(binding['target'].startswith('/etc/nginx/')
               for binding in runtime['provisioning']):
            self._command(['/usr/sbin/nginx', '-t'])
            self._command(['/usr/bin/systemctl', 'reload', 'nginx.service'])
            self._command(['/usr/bin/systemctl', 'is-active', '--quiet',
                           'nginx.service'])
        self._command(['/usr/bin/python3', '-c',
                       'import sqlite3,sys;d=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True);assert d.execute("PRAGMA quick_check").fetchone()[0]=="ok"',
                       descriptor['db_path']])
        return {'database_reopened': True, 'services_active': True}

    def stop_new(self, runtime):
        self._authority()
        for service in reversed(ALLOWED_SERVICES):
            self._command(['/usr/bin/systemctl', 'stop', service])
        return True

    def restore(self, provision):
        self._authority()
        data, unused = _read_regular(self.receipt_path)
        receipt = json.loads(data.decode('utf-8'))
        packed = json.dumps(receipt, sort_keys=True,
                            separators=(',', ':')).encode('utf-8')
        if _digest_bytes(packed) != provision['receipt_sha256']:
            raise ValueError('RUNTIME_ROLLBACK_RECEIPT_MISMATCH')
        # Validate every backup and current target before any rollback effect.
        # A failed provision may leave either old or installed bytes in place.
        prepared = []
        seen = set()
        for item in reversed(receipt['targets']):
            target = item['target']
            if (not isinstance(target, str) or not os.path.isabs(target)
                    or os.path.realpath(target) != target or target in seen
                    or not any(target.startswith(p) for p in ALLOWED_TARGET_PREFIXES)):
                raise ValueError('UNSAFE_RUNTIME_ROLLBACK_TARGET')
            seen.add(target)
            parent = os.lstat(os.path.dirname(target))
            if (not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o022):
                raise ValueError('UNSAFE_RUNTIME_TARGET_PARENT')
            previous = item['previous']
            old = None
            if previous is not None:
                backup = previous['backup']
                if (os.path.dirname(backup) != self.directory
                        or os.path.realpath(backup) != backup):
                    raise ValueError('UNSAFE_RUNTIME_ROLLBACK_BACKUP')
                old, info = _read_regular(backup)
                if _digest_bytes(old) != previous['sha256']:
                    raise ValueError('RUNTIME_ROLLBACK_BACKUP_CHANGED')
            if os.path.lexists(target):
                current, info = _read_regular(target)
                observed = (_digest_bytes(current), stat.S_IMODE(info.st_mode),
                            info.st_uid, info.st_gid)
                allowed = [(item['rendered_sha256'], item['mode'], item['uid'], item['gid'])]
                if previous is not None:
                    allowed.append((previous['sha256'], previous['mode'],
                                    previous['uid'], previous['gid']))
                if observed not in allowed:
                    raise ValueError('RUNTIME_ROLLBACK_TARGET_CHANGED')
            elif previous is not None:
                raise ValueError('RUNTIME_ROLLBACK_TARGET_MISSING')
            prepared.append((item, old))
        for item, old in prepared:
            previous = item['previous']
            if previous is None:
                if os.path.lexists(item['target']):
                    os.unlink(item['target'])
                    directory = os.open(os.path.dirname(item['target']),
                                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    try: os.fsync(directory)
                    finally: os.close(directory)
            else:
                self._atomic_target(item['target'], old, previous['mode'],
                                    previous['uid'], previous['gid'])
        self._command(['/usr/bin/systemctl', 'daemon-reload'])
        if any(item['target'].startswith('/etc/nginx/')
               for item in receipt['targets']):
            self._command(['/usr/sbin/nginx', '-t'])
            self._command(['/usr/bin/systemctl', 'reload', 'nginx.service'])
        return {'restored': True, 'services_restarted': False}
