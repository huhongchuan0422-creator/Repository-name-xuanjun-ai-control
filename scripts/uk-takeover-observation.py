#!/usr/bin/env python3
"""Read-only takeover evidence. Never claims a production writer lock."""
import datetime
import hashlib
import json
import os
import socket
import stat
import subprocess

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
PATHS = [
    '/home/xuanjun_dev/uk-stage1-minimal/coordinator.py',
    '/home/xuanjun_dev/uk-stage1-minimal/owner-callback/serve_uk_callback.py',
    '/opt/xuanjun-uk-control/release/owner_dashboard.py',
    '/etc/systemd/system/xuanjun-uk-owner-dashboard.service',
    '/usr/local/sbin/xuanjun-uk-owner-audit',
]


def observe_file(path):
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            return {'path': path, 'status': 'UNSAFE_FILE_TYPE'}
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            raw = stream.read(1000001)
            ended = os.fstat(stream.fileno())
        if (opened.st_ino != info.st_ino or opened.st_dev != info.st_dev
                or ended.st_mtime_ns != opened.st_mtime_ns
                or ended.st_size != opened.st_size or len(raw) > 1000000):
            return {'path': path, 'status': 'CHANGED_OR_OVERSIZE'}
        return {'path': path, 'status': 'READ',
                'sha256': hashlib.sha256(raw).hexdigest(),
                'modified_at': opened.st_mtime, 'owner_uid': opened.st_uid}
    except OSError:
        return {'path': path, 'status': 'NOT_READABLE_OR_ABSENT'}


def main():
    if socket.gethostname().split('.')[0] != HOST:
        raise SystemExit('STOP_WRONG_HOST')
    result = {'observed_at': datetime.datetime.utcnow().isoformat() + 'Z',
              'production_mutation': False, 'exclusive_writer': 'NOT_VERIFIED',
              'files': [observe_file(p) for p in PATHS], 'candidate_processes': []}
    # comm contains an executable name only: never inspect command lines/env.
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open('/proc/' + pid + '/comm') as stream:
                name = stream.read(64).strip()
            if name in ('codex', 'openclaw', 'git', 'Runner.Worker', 'nginx'):
                result['candidate_processes'].append({'pid': int(pid), 'name': name})
        except OSError:
            pass
    result['candidate_processes'] = result['candidate_processes'][:100]
    print(json.dumps(result, sort_keys=True))
    if os.path.isfile('/usr/local/sbin/xuanjun-uk-owner-audit'):
        subprocess.run(['sudo', '-n', '/usr/local/sbin/xuanjun-uk-owner-audit'],
                       timeout=90, check=True, stderr=subprocess.DEVNULL)
    else:
        print('CAPABILITY_AUDIT=WAITING_HUMAN')


if __name__ == '__main__':
    main()
