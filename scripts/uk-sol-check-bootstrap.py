#!/usr/bin/python3 -I
"""Install only a hash-pinned, no-argument UK Sol diagnostic capability."""
import hashlib
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile

DIGEST = '3faf91ba5ea2ab64e65e987d6bacb5bb0884f33da9a695b21bc9e3a5d7d5e78a'
HELPER = '/usr/local/sbin/xuanjun-uk-sol-check'
POLICY = '/etc/sudoers.d/xuanjun-uk-sol-check'
RULE = b'githubrunner ALL=(root) NOPASSWD: /usr/local/sbin/xuanjun-uk-sol-check ""\n'


def check_destination(path):
    current = '/'
    for part in path.strip('/').split('/'):
        current = os.path.join(current, part)
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            if current != path:
                raise
            return
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('UNSAFE_ROOT_DESTINATION')


def write_atomic(path, data, mode):
    check_destination(path)
    fd, temporary = tempfile.mkstemp(prefix='.xuanjun-sol-', dir=os.path.dirname(path))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0 or socket.gethostname().split('.')[0] != 'iZd7oeikknn1z21sq6ji6zZ':
        raise SystemExit('STOP_FIXED_UK_ROOT_SCOPE')
    raw = Path(__file__).with_name('uk-sol-canary.py').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DIGEST:
        raise SystemExit('STOP_DIAGNOSTIC_HASH_MISMATCH')
    check_destination(HELPER)
    check_destination(POLICY)
    fd, temporary = tempfile.mkstemp(prefix='.xuanjun-sol-policy-', dir='/etc/sudoers.d')
    try:
        os.fchmod(fd, 0o440)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(RULE)
        subprocess.run(['/usr/sbin/visudo', '-cf', temporary], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        write_atomic(HELPER, raw, 0o755)
        write_atomic(POLICY, RULE, 0o440)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print('RUNNER_FIXED_SOL_DIAGNOSTIC=INSTALLED_NO_ARGUMENTS_ONLY', flush=True)
    subprocess.run([HELPER], check=True)


if __name__ == '__main__':
    main()
