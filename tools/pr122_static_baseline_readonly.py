"""Fixed domestic static-baseline observation candidate, not execution permission.

No arguments, configurable roots, network, subprocess, flock, writes or services.
Unknown inputs/source roots are never guessed or searched. File reads can update
atime; observations are individually stable, not a global atomic snapshot.
"""
import hashlib
import json
import os
import re
import signal
import stat
import sys
import time

HOST = 'iZvt5t8tlrm8oiZ'
SITE = '/var/www/wenwenwenyiyiyi.work'
CONTROL = '/var/lib/xuanjun-pr122-site-hub'
RUNTIME = '/var/lib/xuanjun-site-hub-preview'
R2 = SITE + '/releases/pr122-hub-experience-ca7ab933-r2'
NGINX = (
    '/etc/nginx/conf.d/pr122-00-logformat.conf',
    '/etc/nginx/conf.d/pr122-apex-http.conf',
    '/etc/nginx/conf.d/pr122-apex-https.conf',
    '/etc/nginx/conf.d/pr122-site-hub-limit.conf',
    '/etc/nginx/conf.d/winctl.windows-interaction-ip.conf',
    '/etc/nginx/conf.d/winctl.windows-interaction.conf',
    '/etc/nginx/mime.types', '/etc/nginx/nginx.conf',
    '/etc/nginx/pr122-minimal-cutover/apex.locations.conf',
    '/etc/nginx/pr122-minimal-cutover/static-security.conf',
    '/etc/nginx/pr122-minimal-cutover/tokyo-proxy-settings.conf',
    '/etc/nginx/pr122-site-hub/locations.conf',
    R2 + '/release-metadata/inline-csp.conf')
RECEIPT = CONTROL + '/transactions/pr122-hub-experience-20261016-r2/receipt.json'
FILES = (('R2_RECEIPT', RECEIPT),
         ('INSTALLED_PUBLISHER', '/usr/local/libexec/pr122_website_release.py'),
         ('RUNTIME_UNIT', '/etc/systemd/system/xuanjun-site-hub-preview.service')) + tuple(
             ('NGINX_' + str(i + 1).zfill(2), path) for i, path in enumerate(NGINX))
METADATA = (('STATIC_LOCK', CONTROL + '/transaction.lock'),
            ('CANDIDATE_LEDGER', CONTROL + '/transactions/pr122-public-mobile-20261016.attempts.json'))
LINKS = (('CURRENT', SITE + '/current', SITE + '/releases/'),
         ('RUNTIME_CURRENT', RUNTIME + '/current', RUNTIME + '/'))
FILE_LIMIT = 2 * 1024 * 1024
TOTAL_LIMIT = 16 * 1024 * 1024
OUTPUT_LIMIT = 32768
PATH_LIMIT = 256
DEADLINE_SECONDS = 20
STATES = frozenset(('INIT', 'PREPARED', 'HOLD_PARTIAL', 'ROLLED_BACK', 'SUCCESS',
    'HTTPS_SMOKE_PASS_AWAIT_BROWSER', 'STATIC_READONLY_HTTP_COMPLETE_AWAIT_BROWSER',
    'BACKUP_VERIFIED', 'SEALED_BUNDLE', 'STATIC_PREPARED', 'NGINX_STAGED',
    'NGINX_VALIDATED', 'ACTIVATION_DRIFT_CHECK', 'STATIC_ACTIVATED',
    'NGINX_RELOADED', 'HTTPS_SMOKE', 'STATIC_CHECK'))


class Hold(Exception):
    pass


def need(ok, code):
    if not ok:
        raise Hold(code)


def stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def metadata(s):
    return {'uid': s.st_uid, 'gid': s.st_gid, 'mode': stat.S_IMODE(s.st_mode),
            'size': s.st_size, 'device': s.st_dev, 'inode': s.st_ino,
            'mtime_ns': s.st_mtime_ns}


class _Reader:
    """Root FD and UID are private fixture seams; collect() fixes / and UID zero."""
    def __init__(self, root_fd, uid=0):
        self.root_fd = os.dup(root_fd)
        self.uid = uid
        self.deadline = time.monotonic() + DEADLINE_SECONDS
        self.remaining = TOTAL_LIMIT
        self.calls = 0
        self.chain = [(None, None, self.root_fd, stamp(os.fstat(self.root_fd)))]
        self.records = []
        self.absent = []
        try:
            self.protected(os.fstat(self.root_fd), directory=True)
        except BaseException:
            os.close(self.root_fd)
            raise

    def tick(self):
        need(time.monotonic() < self.deadline, 'DEADLINE')

    def protected(self, s, directory=False):
        need(s.st_uid == self.uid and not s.st_mode & 0o022, 'OWNER_MODE')
        if directory:
            need(stat.S_ISDIR(s.st_mode), 'DIRECTORY_TYPE')

    def stable(self):
        for parent, name, fd, expected in self.chain:
            self.tick()
            need(stamp(os.fstat(fd)) == expected, 'DIRECTORY_CHANGED')
            if parent is not None:
                need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                     'DIRECTORY_REPLACED')
        for fd, name, expected in self.records:
            self.tick()
            need(stamp(os.stat(name, dir_fd=fd, follow_symlinks=False)) == expected,
                 'OBJECT_REPLACED')
        for fd, name in self.absent:
            self.tick()
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise Hold('PATH_APPEARED')

    def parent(self, path):
        self.tick()
        self.calls += 1
        need(self.calls <= PATH_LIMIT, 'PATH_BUDGET')
        need(type(path) is str and path.startswith('/') and '\\' not in path
             and all(p not in ('', '.', '..') for p in path.split('/')[1:]), 'PATH_SCOPE')
        fd = self.root_fd
        for part in path.split('/')[1:-1]:
            self.tick()
            before = os.stat(part, dir_fd=fd, follow_symlinks=False)
            self.protected(before, directory=True)
            opened = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                             os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
            self.chain.append((fd, part, opened, stamp(before)))
            need(len(self.chain) <= PATH_LIMIT, 'DESCRIPTOR_BUDGET')
            need(stamp(os.fstat(opened)) == stamp(before), 'DIRECTORY_REPLACED')
            fd = opened
        return fd, path.rsplit('/', 1)[1]

    def missing(self, fd, name):
        self.stable()
        try:
            os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            self.absent.append((fd, name))
            return {'state': 'ABSENT'}
        raise Hold('PATH_APPEARED')

    def file(self, path, *, digest=True):
        allowed = {p for _, p in (FILES if digest else METADATA)}
        need(path in allowed, 'PATH_SCOPE')
        try:
            parent, name = self.parent(path)
        except FileNotFoundError:
            # Missing ancestry cannot be rechecked by name: do not label ABSENT.
            self.stable()
            return {'state': 'UNKNOWN', 'reason': 'ANCESTOR_ABSENT'}, None
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return self.missing(parent, name), None
        self.protected(before)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'FILE_TYPE_LINKS')
        need(0 <= before.st_size <= FILE_LIMIT, 'FILE_BUDGET')
        self.records.append((parent, name, stamp(before)))
        if not digest:
            self.stable()
            return {'state': 'METADATA_ONLY', **metadata(before)}, None
        need(before.st_size <= self.remaining, 'TOTAL_BUDGET')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     dir_fd=parent)
        try:
            need(stamp(os.fstat(fd)) == stamp(before), 'FILE_REPLACED')
            raw = bytearray()
            while True:
                self.tick()
                block = os.read(fd, min(65536, FILE_LIMIT - len(raw) + 1, self.remaining + 1))
                if not block:
                    break
                self.remaining -= len(block)
                need(self.remaining >= 0 and len(raw) + len(block) <= FILE_LIMIT, 'READ_BUDGET')
                raw.extend(block)
            need(len(raw) == before.st_size and stamp(os.fstat(fd)) == stamp(before), 'FILE_CHANGED')
            self.stable()
            return {'state': 'OBSERVED', **metadata(before),
                    'sha256': hashlib.sha256(raw).hexdigest()}, bytes(raw)
        finally:
            os.close(fd)

    def link(self, path, prefix):
        need((path, prefix) in {(p, q) for _, p, q in LINKS}, 'LINK_SCOPE')
        try:
            parent, name = self.parent(path)
        except FileNotFoundError:
            self.stable()
            return {'state': 'UNKNOWN', 'reason': 'ANCESTOR_ABSENT'}
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return self.missing(parent, name)
        need(stat.S_ISLNK(before.st_mode) and before.st_uid == self.uid
             and before.st_nlink == 1 and before.st_size <= 256, 'LINK_POLICY')
        self.records.append((parent, name, stamp(before)))
        target = os.readlink(name, dir_fd=parent)
        if not target.startswith('/'):
            target = path.rsplit('/', 1)[0] + '/' + target
        need(target.startswith(prefix) and re.fullmatch(r'pr122-[a-z0-9-]{1,90}',
             target[len(prefix):]) is not None, 'LINK_ESCAPE')
        # Verify exact target directory through NOFOLLOW ancestry; no enumeration.
        directory, leaf = self.parent(target + '/_not_opened')
        need(leaf == '_not_opened', 'LINK_SCOPE')
        self.stable()
        return {'state': 'OBSERVED_LINK', 'target': target,
                'target_directory': metadata(os.fstat(directory))}

    def close(self):
        for _, _, fd, _ in reversed(self.chain):
            os.close(fd)


def _receipt_summary(raw):
    def unique(items):
        out = {}
        for key, value in items:
            need(key not in out, 'RECEIPT_JSON')
            out[key] = value
        return out
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(Hold('RECEIPT_JSON')))
    need(type(value) is dict, 'RECEIPT_JSON')
    state = value.get('state')
    return {'state': state if type(state) is str and state in STATES else 'UNKNOWN',
            'intent': 'NONE' if 'intent' in value and value['intent'] is None else 'UNKNOWN_OR_PRESENT'}


def _observe(reader):
    rows = []
    held = False
    for label, path, kind, prefix in (
        [(l, p, 'link', q) for l, p, q in LINKS] +
        [(l, p, 'file', None) for l, p in FILES] +
        [(l, p, 'metadata', None) for l, p in METADATA]):
        if held:
            rows.append({'label': label, 'state': 'NOT_READ'})
            continue
        try:
            if kind == 'link':
                row = reader.link(path, prefix)
            else:
                row, raw = reader.file(path, digest=kind == 'file')
                if label == 'R2_RECEIPT' and raw is not None:
                    row['receipt_fields'] = _receipt_summary(raw)
            rows.append({'label': label, **row})
        except BaseException:
            rows.append({'label': label, 'state': 'HOLD', 'reason': 'UNSAFE_OR_UNSTABLE_OR_BUDGET'})
            held = True
    try:
        reader.stable()
    except BaseException:
        held = True
        # Invalidate earlier observations if any retained pathname changed.
        rows = [{'label': row['label'], 'state': 'HOLD', 'reason': 'FINAL_STABILITY'} for row in rows]
    return {'scope': 'STATIC_BASELINE_FIXED_READONLY_CANDIDATE',
            'state': 'HOLD' if held else 'OBSERVATION_ONLY', 'observations': rows,
            'inputs_root': 'UNKNOWN_NOT_READ', 'source_root': 'UNKNOWN_NOT_READ',
            'previous_manifest_and_count': 'UNKNOWN_NOT_READ',
            'writer_fence_lock_availability': 'UNKNOWN',
            'service_active_loaded_nginx_runtime_sandbox': 'UNKNOWN_NOT_QUERIED',
            'production_changes': 0, 'deployment_performed': False,
            'retry_allowed': False}


def collect():
    need(os.geteuid() == 0 and os.uname().nodename == HOST, 'FIXED_HOST_ROOT_REQUIRED')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    reader = None
    try:
        reader = _Reader(fd)
        return _observe(reader)
    finally:
        if reader is not None:
            reader.close()
        os.close(fd)


def main():
    previous = None
    armed = False
    try:
        need(len(sys.argv) == 1, 'NO_ARGUMENTS')
        need(os.geteuid() == 0 and os.uname().nodename == HOST, 'FIXED_HOST_ROOT_REQUIRED')
        def timeout(*_):
            raise Hold('DEADLINE')
        previous = signal.signal(signal.SIGALRM, timeout)
        armed = True
        signal.alarm(DEADLINE_SECONDS)
        result = collect()
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'))
        need(len(encoded.encode()) <= OUTPUT_LIMIT, 'OUTPUT_BUDGET')
    except BaseException:
        result = {'scope': 'STATIC_BASELINE_FIXED_READONLY_CANDIDATE',
                  'state': 'HOLD', 'reason': 'READ_UNAVAILABLE', 'retry_allowed': False}
        encoded = json.dumps(result, sort_keys=True)
    finally:
        if armed:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
    print(encoded)
    return 2 if result['state'] == 'HOLD' else 0


if __name__ == '__main__':
    sys.exit(main())
