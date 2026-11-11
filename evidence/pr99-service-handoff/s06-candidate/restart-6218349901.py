"""Owner-root handoff authorized by PR99#6218349901; original capture is unchanged."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys

SCRIPT = Path('/root/pr99-s06-approved.66ER1spv/run.py')
SCRIPT_SHA = '9ca936d3935732c0b4161f7599286ed63a022a142cb1e6cac69601f64bfb9eca'
SOURCE_COMMIT = '4c9460a215b793259228f9d2e0fbfe5ea50267a1'
NEW_ID = 6218349901
NEW_BODY_SHA = '37c365385bada2ecfd8c0d2bc6f5eec8591b2c59ec5d09dde8917f9bd31b54bf'
OLD_ID = 6217834919
OLD_BODY_SHA = '52100208da889d70920942d137420a79037f7aa44bd70bc7778198bb11b7bb6c'
FAILURE_SHA = '9f48d4a2e1940af1c426d09cf044cc294b6ebb5e295420075b26d20317dbd362'
OLD = Path('/root/pr99-s06-runtime-received-v1')
SAVED = Path('/root/pr99-s06-runtime-received-v1.auth-failed-6217834919')
ROOT = Path('/root')


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def load_reviewed_script():
    for p in (SCRIPT, *SCRIPT.parents):
        s = p.lstat()
        require(s.st_uid == 0 and not stat.S_ISLNK(s.st_mode) and not s.st_mode & 0o022,
                'REVIEWED_SCRIPT_PATH_IDENTITY')
    s = SCRIPT.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and
            stat.S_IMODE(s.st_mode) in (0o400, 0o600), 'REVIEWED_SCRIPT_FILE_IDENTITY')
    fd = os.open(SCRIPT, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        before = os.fstat(f.fileno())
        raw = f.read(262145)
        after = os.fstat(f.fileno())
    current = SCRIPT.lstat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    require(len(raw) <= 262144 and all(getattr(before, k) == getattr(after, k)
            == getattr(current, k) for k in fields), 'REVIEWED_SCRIPT_CHANGED')
    require(hashlib.sha256(raw).hexdigest() == SCRIPT_SHA, 'REVIEWED_SCRIPT_HASH')
    ns = {'__name__': 's06_reviewed_original', '__file__': str(SCRIPT)}
    exec(compile(raw, str(SCRIPT), 'exec'), ns)
    return ns


def original_failure(ns):
    ns['private_directory'](OLD)
    require(not os.path.lexists(SAVED), 'PRESERVED_DESTINATION_ALREADY_EXISTS')
    require({p.name for p in OLD.iterdir()} == {'approval.json', 'failure.json', 'known_hosts'},
            'OLD_STAGE_HAS_PROGRESS_OR_UNKNOWN_ENTRY')
    for name in ('approval.json', 'failure.json', 'known_hosts'):
        s = (OLD / name).lstat()
        require(stat.S_IMODE(s.st_mode) == 0o600, 'OLD_FILE_MODE')
    failed = ns['stable_file'](OLD / 'failure.json', private=True)
    require(ns['sha'](failed) == FAILURE_SHA, 'OLD_FAILURE_CHANGED')
    value = json.loads(failed)
    require(value.get('status') == 'HOLD_PRESERVE_EVIDENCE'
            and value.get('reason') == 'CalledProcessError'
            and value.get('retry_allowed') is False, 'OLD_FAILURE_STATE')
    previous = json.loads(ns['stable_file'](OLD / 'approval.json', private=True))
    require(previous.get('id') == OLD_ID and ns['sha'](previous['body'].encode()) == OLD_BODY_SHA,
            'OLD_APPROVAL_CHANGED')
    require(ns['stable_file'](OLD / 'known_hosts', private=True) == ns['PUBLIC_KEY'].encode(),
            'OLD_HOSTKEY_CHANGED')
    s = OLD.lstat()
    return s.st_dev, s.st_ino


def no_old_coordinator():
    # Read only the Python invocation prefix up to its script pathname. Never
    # inspect arguments after that pathname, inline -c code, or /proc/environ.
    def token(f):
        value = bytearray()
        for _ in range(512):
            b = f.read(1)
            if b in (b'', b'\0'):
                return bytes(value)
            value.extend(b)
        raise RuntimeError('PROCESS_PREFIX_UNBOUNDED')
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != 0:
                continue
            with (entry / 'comm').open('rb') as f:
                comm = f.read(32)
            # All reported old invocations used the fixed /usr/bin/python3.11.
            if comm.rstrip(b'\n') != b'python3.11':
                continue
            with (entry / 'cmdline').open('rb') as f:
                exe = token(f)
                if not Path(os.fsdecode(exe)).name.startswith('python'):
                    continue
                for _ in range(8):
                    arg = token(f)
                    if not arg or arg in (b'-c', b'-m'):
                        break
                    if re.fullmatch(br'-[IBu]+', arg):
                        continue
                    if arg.startswith(b'-'):
                        raise RuntimeError('PYTHON_PREFIX_UNKNOWN_' + entry.name)
                    path = os.fsdecode(arg)
                    require(not re.fullmatch(r'/root/pr99-s06-approved\.[A-Za-z0-9]+/run\.py', path),
                            'OLD_COORDINATOR_ACTIVE_' + entry.name)
                    break
                else:
                    raise RuntimeError('PYTHON_PREFIX_UNKNOWN_' + entry.name)
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise RuntimeError('PROCESS_SCAN_PERMISSION_UNKNOWN') from None


def exclusive_preserve(identity):
    root = ROOT
    require(OLD.parent == root == SAVED.parent, 'PRESERVE_PARENT_MISMATCH')
    s = root.lstat()
    require(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
            'ROOT_PARENT_IDENTITY')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        bound = os.fstat(fd)
        current = root.lstat()
        require((bound.st_dev, bound.st_ino) == (current.st_dev, current.st_ino), 'ROOT_PARENT_DRIFT')
        old = os.stat(OLD.name, dir_fd=fd, follow_symlinks=False)
        require(stat.S_ISDIR(old.st_mode) and old.st_uid == 0
                and stat.S_IMODE(old.st_mode) == 0o700
                and (old.st_dev, old.st_ino) == identity, 'OLD_DIRECTORY_IDENTITY_DRIFT')
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, 'renameat2', None)
        require(rename is not None, 'EXCLUSIVE_RENAME_UNAVAILABLE')
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(fd, os.fsencode(OLD.name), fd, os.fsencode(SAVED.name), 1)
        if result:
            raise OSError(ctypes.get_errno(), 'EXCLUSIVE_PRESERVE_FAILED')
        os.fsync(fd)
        saved = SAVED.lstat()
        require((saved.st_dev, saved.st_ino) == identity and not os.path.lexists(OLD),
                'PRESERVE_RESULT_UNKNOWN')
    finally:
        os.close(fd)


def main():
    require(os.geteuid() == 0 and os.uname().nodename == 'iZmj7a5kwr75qc1tul4kf9Z', 'KOREA_ROOT_REQUIRED')
    os.umask(0o077)
    ns = load_reviewed_script()
    args = argparse.Namespace(approval_id=NEW_ID, approval_sha256=NEW_BODY_SHA,
        source_commit=SOURCE_COMMIT, script_sha256=SCRIPT_SHA, confirm_independent_auditor=True)
    ns['approval'](args)  # Full authentic-comment/hash/author/action/host/version/time admission.
    identity = original_failure(ns)
    no_old_coordinator()
    remote_code = (
        "import os,stat;from pathlib import Path;"
        "assert os.geteuid()==0 and os.uname().nodename=='iZ6wee8q9z4t03hvqumwfhZ';"
        "s=Path('/root').lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022;"
        "p=Path('/root/pr99-s06-runtime-contract-v1');\n"
        "try: p.lstat()\n"
        "except FileNotFoundError: print('TOKYO_ROOT_PREFLIGHT=PASS SOURCE_STAGE=ABSENT')\n"
        "else: raise RuntimeError('SOURCE_STAGE_EXISTS_NO_RESTART')\n")
    ssh = ['/usr/bin/ssh', '-n', '-T', '-S', 'none', '-o', 'UserKnownHostsFile=' + str(OLD / 'known_hosts'),
        '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'HostKeyAlgorithms=ecdsa-sha2-nistp256', '-o', 'UpdateHostKeys=no',
        '-o', 'ClearAllForwardings=yes', '-o', 'ForwardAgent=no', '-o', 'ForwardX11=no',
        '-o', 'ConnectTimeout=10', '-o', 'ConnectionAttempts=1', '-o', 'BatchMode=no',
        '-o', 'NumberOfPasswordPrompts=3', 'root@47.245.53.152',
        '/usr/bin/python3.11 -I -B -c ' + shlex.quote(remote_code)]
    print('第1轮：只读登录预检。看到password提示后输入东京root密码并回车。', flush=True)
    subprocess.run(ssh, check=True, timeout=120)
    ns['approval'](args)  # Recheck revocation, expiry and exact independent body before rename.
    require(original_failure(ns) == identity, 'OLD_STAGE_CHANGED_AFTER_PREFLIGHT')
    no_old_coordinator()
    exclusive_preserve(identity)
    print('OLD_FAILURE_ATOMICALLY_PRESERVED; 第2轮：运行获批原脚本一次，再次提示时输入东京root密码。', flush=True)
    sys.argv = [str(SCRIPT), '--approval-id', str(NEW_ID), '--approval-sha256', NEW_BODY_SHA,
        '--source-commit', SOURCE_COMMIT, '--script-sha256', SCRIPT_SHA, '--confirm-independent-auditor']
    ns['main']()


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        print('HOLD_PRESERVE_EVIDENCE NO_RETRY: ' + type(e).__name__ + '; ' + str(e), flush=True)
        raise SystemExit(2)
