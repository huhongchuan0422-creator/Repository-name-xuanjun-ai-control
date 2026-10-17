"""Owner-only, exact-byte read-only plan launcher. Stdlib, no install actions.

The launcher's own SHA must be enrolled by the independent plan permission.
Never substitute an internally consistent newer ZIP for the frozen audited ZIP.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

HOST = 'iZvt5t8tlrm8oiZ'
ROOT = Path('/root/pr122-customer-channel-upgrade-inputs')
INPUT = ROOT / 'REVIEW_ARTIFACT.zip'
HELPER = ROOT / 'approved-upgrade.py'
BASE = Path('/var/lib/xuanjun-customer-channel')
ZIP_SHA = 'd03a09d3110cf372d5c6209da4514fffd77f8487c6a36532744e80557ac353d8'
HELPER_SHA = '9edc15851d653cdbc9366ebc7dcdd8215b2df3814248065fe96d704acbf1111c'
SOURCE = 'bc9404216f2eb69dabf7754950a966238e758596'
CHANNEL_SHA = 'f864d40da21544de51cdfcc51998116390dc56afe01dcd17112019a72fbc319a'


def need(ok, reason):
    if not ok:
        raise RuntimeError('HOLD:' + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def checked(path, expected, limit):
    for item in (path, *path.parents):
        info = item.lstat()
        need(info.st_uid == 0 and not stat.S_ISLNK(info.st_mode) and not info.st_mode & 0o022, 'ROOT_PATH_IDENTITY')
        if item != path:
            need(stat.S_ISDIR(info.st_mode), 'PARENT_DIRECTORY')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == 0 and not before.st_mode & 0o022 and before.st_size <= limit, 'REGULAR_INPUT_IDENTITY')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    need((before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns) and len(raw) <= limit, 'INPUT_DRIFT')
    need(sha(raw) == expected, 'EXACT_INPUT_SHA256')
    return raw


def plan():
    need(os.geteuid() == 0 and os.uname().nodename == HOST and os.environ.get('SUDO_UID') != '1002', 'OWNER_ROOT_HOST_REQUIRED')
    need(sys.flags.isolated and sys.dont_write_bytecode, 'ISOLATED_NO_BYTECODE_REQUIRED')
    package = checked(INPUT, ZIP_SHA, 12000000)
    helper = checked(HELPER, HELPER_SHA, 100000)
    # Execute only verified stdlib function definitions. __main__ is never run;
    # CLI apply/rollback and candidate imports have no path through this guard.
    namespace = {'__name__': 'pr122_exact_readonly_plan', '__file__': str(HELPER)}
    exec(compile(helper, str(HELPER), 'exec'), namespace)
    need(namespace['INPUT'] == INPUT and namespace['BASE'] == BASE, 'FIXED_PROTECTED_PATHS')
    original_read = namespace['read']
    namespace['read'] = lambda path: package if Path(path) == INPUT else original_read(path)
    first = namespace['plan']()
    second = namespace['plan']()
    need(canonical(first) == canonical(second), 'PLAN_BASELINE_CHANGED')
    need(first['new']['zip_sha256'] == ZIP_SHA and first['new']['binding']['source_commit'] == SOURCE and first['new']['binding']['channel_sha256'] == CHANNEL_SHA, 'FROZEN_PLAN_IDENTITY')
    checked(INPUT, ZIP_SHA, 12000000)
    checked(HELPER, HELPER_SHA, 100000)
    return {'state': 'READONLY_PLAN_COMPLETE', 'plan': first, 'plan_sha256': sha(canonical(first)), 'outer_zip_sha256': ZIP_SHA, 'upgrade_sha256': HELPER_SHA, 'production_mutations': 0, 'apply_called': False, 'rollback_called': False}


def main():
    need(sys.argv[1:] == ['plan'], 'ONLY_PLAN_ALLOWED')
    print(canonical(plan()).decode())


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('{"state":"HOLD","execution_not_authorized_by_code":true}')
        raise SystemExit(2) from None
