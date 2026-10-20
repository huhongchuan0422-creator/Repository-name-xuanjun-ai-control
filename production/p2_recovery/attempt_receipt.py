"""P2 operator-side attempt receipt recorder (Python 3.6). No installation or cloud calls.

Records verified evidence for each of up to five real installation attempts.
A receipt is NOT authorization, a production Grant, or evidence of global fencing.
Existing files are never overwritten; missing/unknown execution outcomes are HOLD.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
STATES = ('FAILED_RECONCILED', 'SUCCEEDED_VERIFIED', 'UNKNOWN_HOLD')
HEX64 = re.compile(r'^[a-f0-9]{64}$')
ID = re.compile(r'^[A-Za-z0-9_-]{6,100}$')


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, help='Existing root-owned 0700 receipts directory')
    p.add_argument('--slot', type=int, required=True)
    p.add_argument('--attempt-id', required=True)
    p.add_argument('--status', choices=STATES, required=True)
    p.add_argument('--command-sha256', required=True)
    p.add_argument('--evidence-sha256', required=True,
                   help='SHA of original immutable execution receipt; never synthetic')
    p.add_argument('--invoke-id', default=None)
    a = p.parse_args()
    require(os.geteuid() == 0 and os.getuid() == 0 and
            os.uname().nodename.split('.')[0] == HOST and
            sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
            'UK_ISOLATED_ROOT_REQUIRED')
    require(1 <= a.slot <= 5 and ID.fullmatch(a.attempt_id), 'INVALID_ATTEMPT')
    require(HEX64.fullmatch(a.command_sha256) and
            HEX64.fullmatch(a.evidence_sha256), 'INVALID_DIGEST')
    if a.invoke_id is not None:
        require(ID.fullmatch(a.invoke_id), 'INVALID_INVOKE_ID')
    require(a.root.startswith('/') and a.root != '/' and '..' not in a.root.split('/'),
            'INVALID_ROOT')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in a.root.strip('/').split('/'):
            require(bool(part), 'INVALID_ROOT')
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
            st = os.fstat(fd)
            require(st.st_uid == 0 and not st.st_mode & 0o022, 'INSECURE_PARENT')
        st = os.fstat(fd)
        require(stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o700,
                'RECEIPT_DIR_NOT_PROTECTED')
        # Fail closed on skipped slots, earlier success, or unresolved failure.
        # This is operator bookkeeping, not a production execution grant.
        for number in range(1, a.slot):
            prior_name = 'attempt-%d.json' % number
            prior_fd = os.open(prior_name, os.O_RDONLY | os.O_NOFOLLOW |
                               os.O_NONBLOCK, dir_fd=fd)
            try:
                prior_st = os.fstat(prior_fd)
                require(stat.S_ISREG(prior_st.st_mode) and prior_st.st_uid == 0 and
                        prior_st.st_nlink == 1 and
                        stat.S_IMODE(prior_st.st_mode) == 0o600 and
                        prior_st.st_size <= 4096, 'PRIOR_RECEIPT_UNSAFE')
                data = os.read(prior_fd, 4097)
                require(len(data) <= 4096, 'PRIOR_RECEIPT_BOUND')
                prior = json.loads(data.decode('ascii'))
                require(prior.get('schema') == 1 and prior.get('host') == HOST and
                        prior.get('slot') == number and
                        prior.get('authorizes_execution') is False and
                        prior.get('status') == 'FAILED_RECONCILED' and
                        HEX64.fullmatch(prior.get('evidence_sha256', '')) is not None,
                        'PRIOR_ATTEMPT_NOT_RECONCILED')
            finally:
                os.close(prior_fd)
        # Exactly one immutable file per numbered slot.
        name = 'attempt-%d.json' % a.slot
        payload = {'schema': 1, 'host': HOST, 'slot': a.slot,
                   'attempt_id': a.attempt_id, 'status': a.status,
                   'command_sha256': a.command_sha256,
                   'evidence_sha256': a.evidence_sha256,
                   'invoke_id': a.invoke_id,
                   'recorded_utc': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                   'authorizes_execution': False}
        raw = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        try:
            with os.fdopen(out, 'wb', closefd=False) as stream:
                stream.write(raw)
                stream.flush()
            os.fsync(out)
        finally:
            os.close(out)
        os.fsync(fd)
        print(json.dumps({'status': 'RECORDED_NOT_ACTIVATED', 'slot': a.slot,
                          'sha256': hashlib.sha256(raw).hexdigest()}, sort_keys=True))
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'status': 'HOLD_RETAIN_OUTPUT',
                          'error_type': type(exc).__name__}, sort_keys=True))
        sys.exit(2)
