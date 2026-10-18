#!/usr/bin/env python3
"""Fixed historical-file observations only. No execution, enrollment or writes.

No paths, commands, credentials or requests are accepted from callers. Missing
historical candidates are ordinary ABSENT observations, never retry permission.
"""
import errno
import hashlib
import json
import os
import signal
import stat
import sys
import time

HOST = 'iZvt5t8tlrm8oiZ'
ROOT_UID = 0
RUNNER_UID = 1002
RUNNER_HOME = '/home/githubrunner'
ROOTS = (
    '/root/pr122-unified-release-4ryrkhl9',
    '/home/githubrunner/pr122-unified-release-6218264390',
)
# Exact original archive member names; extraction and current presence UNKNOWN.
# No stripped-prefix alternate paths or unknown Tokyo input path are probed.
FILES = (
    ('ROOT_DISTRIBUTION_MANIFEST', 0, 'pr122-unified-release/DISTRIBUTION_MANIFEST.json', 65536),
    ('ROOT_HOST_PINS', 0, 'pr122-unified-release/deploy/pr122-site-hub-unified/HOST_PINS.json', 65536),
    ('ROOT_STATIC_ARCHIVE', 0, 'pr122-unified-release/inputs/PR122_SITE_HUB_REVIEW_ONLY.tar.gz', 400000),
    ('ROOT_PREVIOUS_MANIFEST', 0, 'pr122-unified-release/inputs/R2_CANDIDATE_MANIFEST.json', 300000),
    ('ROOT_COMBINED_SOURCE', 0, 'pr122-unified-release/scripts/pr122_site_hub_combined.py', 40000),
    ('ROOT_PREFLIGHT_SOURCE', 0, 'pr122-unified-release/scripts/pr122_site_hub_host_preflight.py', 20000),
    ('ROOT_UNIFIED_SOURCE', 0, 'pr122-unified-release/scripts/pr122_site_hub_unified_release.py', 30000),
    ('RUNNER_APPROVED_ARCHIVE', 1, 'approved-release.tar.gz', 406102),
)
MAX_TOTAL_BYTES = 1500000
MAX_OUTPUT_BYTES = 4096
DEADLINE_SECONDS = 20
CHUNK_BYTES = 65536


class Hold(Exception):
    pass


def _need(ok, code):
    if not ok:
        raise Hold(code)


def _clock(deadline):
    _need(time.monotonic() < deadline, 'DEADLINE')


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _owner(path, root):
    runner = root == ROOTS[1] and (path == RUNNER_HOME or path.startswith(RUNNER_HOME + '/'))
    return RUNNER_UID if runner else ROOT_UID


def _protected(info, uid):
    _need(info.st_uid == uid and not stat.S_IMODE(info.st_mode) & 0o022, 'OWNER_OR_MODE')


def _stable(chain, deadline):
    for parent, name, fd, expected in chain:
        _clock(deadline)
        _need(_stamp(os.fstat(fd)) == expected, 'DIRECTORY_CHANGED')
        if parent is not None:
            try:
                current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except OSError:
                raise Hold('DIRECTORY_REPLACED') from None
            _need(_stamp(current) == expected, 'DIRECTORY_REPLACED')


def _observe(root, relative, limit, deadline, budget):
    parts = (root + '/' + relative).split('/')[1:]
    _need(root.startswith('/') and all(p not in ('', '.', '..') for p in parts)
          and '\\' not in root + relative, 'FIXED_PATH')
    chain = []
    file_fd = None
    file_seen = False
    missing = None
    absolute = ''
    try:
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        chain.append((None, None, fd, _stamp(os.fstat(fd))))
        _protected(os.fstat(fd), ROOT_UID)
        for component in parts[:-1]:
            _clock(deadline)
            absolute += '/' + component
            missing = (fd, component)
            before = os.stat(component, dir_fd=fd, follow_symlinks=False)
            missing = None
            _need(stat.S_ISDIR(before.st_mode), 'UNSAFE_DIRECTORY')
            _protected(before, _owner(absolute, root))
            opened = os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                             os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            chain.append((fd, component, opened, _stamp(before)))
            _need(_stamp(os.fstat(opened)) == _stamp(before), 'DIRECTORY_REPLACED')
            fd = opened
        _stable(chain, deadline)
        name = parts[-1]
        missing = (fd, name)
        before = os.stat(name, dir_fd=fd, follow_symlinks=False)
        missing = None
        file_seen = True
        _protected(before, _owner(absolute + '/' + name, root))
        _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'UNSAFE_FILE')
        _need(0 <= before.st_size <= limit, 'FILE_SIZE_LIMIT')
        _need(before.st_size <= budget[0], 'TOTAL_SIZE_LIMIT')
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        _need(_stamp(os.fstat(file_fd)) == _stamp(before), 'FILE_REPLACED')
        total = 0
        hashed = hashlib.sha256()
        while True:
            _clock(deadline)
            raw = os.read(file_fd, min(CHUNK_BYTES, limit - total + 1))
            if not raw:
                break
            total += len(raw)
            budget[0] -= len(raw)
            _need(total <= limit and budget[0] >= 0, 'READ_SIZE_LIMIT')
            hashed.update(raw)
        _need(total == before.st_size and _stamp(os.fstat(file_fd)) == _stamp(before),
              'FILE_CHANGED')
        after = os.stat(name, dir_fd=fd, follow_symlinks=False)
        _need(_stamp(after) == _stamp(before), 'FILE_REPLACED')
        _stable(chain, deadline)
        return {'state': 'OBSERVED', 'size': total, 'sha256': hashed.hexdigest()}
    except FileNotFoundError:
        _need(not file_seen and missing is not None, 'PATH_DISAPPEARED')
        _stable(chain, deadline)
        try:
            os.stat(missing[1], dir_fd=missing[0], follow_symlinks=False)
        except FileNotFoundError:
            return {'state': 'ABSENT'}
        except OSError:
            raise Hold('FILE_ACCESS') from None
        raise Hold('PATH_APPEARED')
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise Hold('UNSAFE_PATH') from None
        raise Hold('FILE_ACCESS') from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for _, _, fd, _ in reversed(chain):
            os.close(fd)


def _collect():
    _need(os.geteuid() == 0 and os.uname().nodename == HOST, 'FIXED_HOST_ROOT_REQUIRED')
    deadline = time.monotonic() + DEADLINE_SECONDS
    budget = [MAX_TOTAL_BYTES]
    rows = []
    held = False
    for label, root_index, relative, limit in FILES:
        if held:
            rows.append({'label': label, 'state': 'NOT_READ'})
            continue
        try:
            _clock(deadline)
            row = _observe(ROOTS[root_index], relative, limit, deadline, budget)
        except Hold as error:
            row = {'state': 'HOLD', 'reason': str(error)}
            held = True
        rows.append(dict(label=label, **row))
    return {'schema': 1, 'scope': 'DOMESTIC_STAGING_READONLY',
            'state': 'HOLD' if held else 'OBSERVATION_COMPLETE', 'files': rows,
            'production_changes': 0, 'deployment_performed': False}


def collect():
    def expired(_signal, _frame):
        raise Hold('DEADLINE')
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(DEADLINE_SECONDS)
    try:
        return _collect()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def main():
    try:
        _need(len(sys.argv) == 1, 'NO_ARGUMENTS_ALLOWED')
        result = collect()
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'))
        _need(len(encoded.encode('utf-8')) <= MAX_OUTPUT_BYTES, 'OUTPUT_LIMIT')
    except Hold as error:
        result = {'scope': 'DOMESTIC_STAGING_READONLY', 'state': 'HOLD', 'reason': str(error)}
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'))
    except Exception:
        result = {'scope': 'DOMESTIC_STAGING_READONLY', 'state': 'HOLD', 'reason': 'READ_UNAVAILABLE'}
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'))
    print(encoded)
    return 2 if result['state'] == 'HOLD' else 0


if __name__ == '__main__':
    sys.exit(main())
