"""Fixed Korea Runner capability. No arbitrary argv, source path or sudo shell.

The install action invokes the frozen stdlib handoff; it does not replace that
handoff's independent exact action permit and root private admission checks.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

HOST = 'iZmj7a5kwr75qc1tul4kf9Z'
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'}
INPUT = '/etc/xuanjun-pr99-release/phase-c-inputs'
HANDOFF_SHA = '12bec6d209b1e53bda515bc6d08dcce785338ebed0fa9aa88ba23504ac973c35'
ARCHIVE_SHA = '898263578775de2d0486f2d2c18986192305a8edbe213279c5c4d7b4e35cc520'
PROGRAM = '/usr/local/libexec/xuanjun-pr99-phase-c-channel.py'
WRAPPER = '/usr/local/sbin/xuanjun-pr99-phase-c'
WRAPPER_BYTES = ("#!/bin/sh\nexec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C "
                 "/usr/bin/python3.11 -I -B " + PROGRAM + ' "$@"\n').encode()
POLICY_BYTES = ('githubrunner ALL=(root) NOPASSWD:NOSETENV: ' + WRAPPER + ' inspect\n' +
                'githubrunner ALL=(root) NOPASSWD:NOSETENV: ' + WRAPPER + ' install\n').encode()


def require(value, code):
    if not value:
        raise ValueError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def trusted(path, directory=False):
    path = Path(path)
    require(path.is_absolute(), 'ABSOLUTE_PATH_REQUIRED')
    for parent in reversed(path.parents):
        s = parent.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
                'UNTRUSTED_PARENT')
    s = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    require(kind(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
            'UNTRUSTED_OBJECT')
    if not directory:
        require(s.st_nlink == 1, 'MULTIPLE_FILE_LINKS')
    return s


def read(path, limit, modes=(0o400, 0o600)):
    trusted(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_nlink == 1 and
                stat.S_IMODE(s.st_mode) in modes and s.st_size <= limit, 'INPUT_IDENTITY')
        data = bytearray()
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            require(len(data) <= limit, 'INPUT_SIZE')
        after = os.fstat(fd)
        current = os.lstat(path)
        identity = lambda v: (v.st_dev, v.st_ino, v.st_uid, v.st_mode, v.st_nlink,
                              v.st_size, v.st_mtime_ns, v.st_ctime_ns)
        require(identity(s) == identity(after) == identity(current), 'INPUT_CHANGED')
        return bytes(data)
    finally:
        os.close(fd)


class Context:
    def path(self, name):
        return Path(name)

    def identity(self):
        require(os.geteuid() == 0 and os.uname().nodename == HOST, 'ROOT_HOST_REQUIRED')
        allowed = dict(ENV)
        if os.environ.get('LC_CTYPE') == 'C.UTF-8':
            allowed['LC_CTYPE'] = 'C.UTF-8'
        require(dict(os.environ) == allowed, 'CLEAN_ENV_REQUIRED')
        require(sys.version_info[:2] == (3, 11), 'PYTHON311_REQUIRED')

    def execute(self, args):
        os.execve('/usr/bin/python3.11', args, ENV)


def inspect(ctx):
    rows = {}
    # No credential, private key, admission body, DB or business record reads.
    names = {'handoff': INPUT + '/root_handoff.py', 'archive': INPUT + '/review.tar.gz',
             'plan': INPUT + '/install-plan.json',
             'install_admission': '/etc/xuanjun-pr99-release/phase-c-offline-install-admission.json'}
    for name, raw in names.items():
        p = ctx.path(raw)
        try:
            s = trusted(p)
            rows[name] = {'present': True, 'mode': oct(stat.S_IMODE(s.st_mode)),
                          'root_owned': True, 'regular_single_link': True}
        except FileNotFoundError:
            rows[name] = {'present': False}
    for name in ('broker', 'source', 'authority'):
        p = ctx.path('/etc/xuanjun-pr99-release/phase-c-public-inputs/' + name + '.pem')
        try:
            data = read(p, 16384, modes=(0o400, 0o444, 0o600, 0o644))
            require(data.startswith(b'-----BEGIN PUBLIC KEY-----'), 'PUBLIC_KEY_REQUIRED')
            rows[name + '_public_key'] = {'present': True, 'sha256': digest(data)}
        except FileNotFoundError:
            rows[name + '_public_key'] = {'present': False}
    return {'status': 'CHANNEL_INSPECTION_COMPLETE', 'inputs': rows,
            'install_called': False, 'credentials_read': False, 'database_read': False}


def install(ctx):
    root = ctx.path(INPUT)
    s = trusted(root, directory=True)
    require(stat.S_IMODE(s.st_mode) == 0o700, 'INPUT_DIRECTORY_PRIVATE')
    helper = root / 'root_handoff.py'
    archive = root / 'review.tar.gz'
    plan = root / 'install-plan.json'
    require(digest(read(helper, 65536)) == HANDOFF_SHA, 'FROZEN_HANDOFF_HASH')
    require(digest(read(archive, 2097152)) == ARCHIVE_SHA, 'FROZEN_ARCHIVE_HASH')
    # Authenticate the private regular plan identity, never print its contents.
    read(plan, 65536)
    # Frozen handoff re-reads its own bytes, archive, plan, exact private pin and
    # current GitHub approval BEFORE importing candidate code or claiming a run.
    args = ['/usr/bin/python3.11', '-I', '-B', '-u', str(helper),
            '--archive', str(archive), '--plan', str(plan)]
    ctx.execute(args)
    raise RuntimeError('EXEC_RETURNED')


def main(argv=None, ctx=None):
    args = sys.argv[1:] if argv is None else argv
    require(args in (['inspect'], ['install']), 'FIXED_ACTION_ONLY')
    ctx = ctx or Context()
    ctx.identity()
    if args == ['inspect']:
        return inspect(ctx)
    return install(ctx)


if __name__ == '__main__':
    try:
        print(json.dumps(main(), sort_keys=True))
    except BaseException as error:
        print(json.dumps({'status': 'HOLD_CHANNEL', 'error_type': type(error).__name__,
                          'retry_allowed': False}), file=sys.stderr)
        sys.exit(2)
