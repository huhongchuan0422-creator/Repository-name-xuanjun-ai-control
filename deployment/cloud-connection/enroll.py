"""Pinned connection-only enrollment. Default is a non-mutating plan.

Run --apply only after confirmation of this exact new persistent delegation.
Not a P2 installer. Does not change credentials, SSH, other services or DNS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import urllib.request

SOURCE_COMMIT = 'f3bfc3fe531c7dcbaa4d94bb8ef52b83e3f02565'
BASE = '/opt/xuanjun-cloud-connection'
STATE = '/var/lib/xuanjun-cloud-connection'
CONFIG = '/etc/xuanjun-cloud-executor/connection.json'
UNIT = '/etc/systemd/system/xuanjun-cloud-connection.service'
REPO = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
# Filled at packaging, derived from the exact checked-back repository objects.
FILES = {'production/cloud_connection/queue.py': 'a61583dba2890dd7906de5516bcfd60a5bf41e5e79c3ec81adc44c1a05caf8c1', 'production/cloud_connection/worker.py': '7be21f5dfa610382410cf73474869656caf830703e91a656748056110053b2e4', 'production/cloud_connection/runtime.py': 'bc3c2a9bc0825a7a2bdc1da41b36c7864f92d413f09c48989e97bf647be1dd44', 'deployment/cloud-connection/xuanjun-cloud-connection.service': 'f3866aa91eb30bb82e6482e876a69d19650662d4ae36f0bd5ab84784db2af6b6'}


def checked_dir(path, mode=None):
    p = Path(path)
    for current in reversed((p,) + tuple(p.parents)):
        s = current.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            raise RuntimeError('UNPROTECTED_DIRECTORY')
    if mode is not None and stat.S_IMODE(p.stat().st_mode) != mode:
        raise RuntimeError('DIRECTORY_MODE')


def exclusive(path, raw, mode):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0 or os.uname().nodename != 'iZd7oeikknn1z21sq6ji6zZ':
        raise RuntimeError('EXACT_UK_ROOT_EXECUTOR_ONLY')
    if sys.version_info < (3, 6):
        raise RuntimeError('PYTHON_VERSION')
    os.umask(0o077)
    for parent in ('/opt', '/var/lib', '/etc/systemd/system', '/etc/xuanjun-cloud-executor'):
        checked_dir(parent)
    for new in (BASE, STATE, CONFIG, UNIT):
        if os.path.lexists(new):
            raise RuntimeError('EXISTING_ENROLLMENT_HOLD_NO_OVERWRITE')
    for path, owner in (('/etc/xuanjun-cloud-executor/credentials.json', 0),
                        ('/etc/xuanjun-development/github-intake-token', 1003)):
        checked_dir(str(Path(path).parent))
        s = os.lstat(path)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != owner or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1:
            raise RuntimeError('EXISTING_CREDENTIAL_METADATA')
    raw_files = {}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for path, digest in FILES.items():
        url = 'https://raw.githubusercontent.com/' + REPO + '/' + SOURCE_COMMIT + '/' + path
        with opener.open(url, timeout=20) as response:
            if response.geturl() != url:
                raise RuntimeError('SOURCE_REDIRECT')
            raw = response.read(131073)
        if len(raw) > 131072 or hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError('SOURCE_SHA')
        raw_files[path] = raw
    if len(raw_files) != 4:
        raise RuntimeError('SOURCE_CLOSURE')
    code_records = [[name, FILES['production/cloud_connection/' + name]]
                    for name in ('queue.py', 'worker.py', 'runtime.py')]
    code_pin = hashlib.sha256(json.dumps(code_records, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    print(json.dumps({'state': 'PLAN_VERIFIED', 'source_commit': SOURCE_COMMIT,
                      'executor_sha256': code_pin, 'operations': ['probe', 'fetch_os_release'],
                      'oss': 'NOT_USED', 'private_delivery': 'NOT_CONNECTED'}))
    if not args.apply:
        return
    # All writes are new objects. Any interrupted/partial enrollment stops and is
    # preserved; --apply never overwrites or restarts an existing enrollment.
    release = BASE + '/releases/' + SOURCE_COMMIT
    os.mkdir(BASE, 0o755)
    os.mkdir(BASE + '/releases', 0o755)
    os.mkdir(release, 0o755)
    os.mkdir(release + '/production', 0o755)
    os.mkdir(release + '/production/cloud_connection', 0o755)
    for name in ('queue.py', 'worker.py', 'runtime.py'):
        exclusive(release + '/production/cloud_connection/' + name,
                  raw_files['production/cloud_connection/' + name], 0o644)
    os.mkdir(STATE, 0o700)
    os.mkdir(STATE + '/private-results', 0o700)
    config = {'executor_sha256': code_pin, 'allowed_actor_ids': [332398908],
              'github_token_ref': '/etc/xuanjun-development/github-intake-token', 'github_token_owner': 1003,
              'credentials_ref': '/etc/xuanjun-cloud-executor/credentials.json',
              'state_root': STATE, 'poll_seconds': 30}
    exclusive(CONFIG, json.dumps(config, sort_keys=True).encode(), 0o600)
    exclusive(UNIT, raw_files['deployment/cloud-connection/xuanjun-cloud-connection.service'], 0o644)
    os.symlink(release, BASE + '/current')
    subprocess.check_call(['systemctl', 'daemon-reload'])
    subprocess.check_call(['systemctl', 'enable', '--now', 'xuanjun-cloud-connection.service'])
    subprocess.check_call(['systemctl', 'is-active', '--quiet', 'xuanjun-cloud-connection.service'])
    print('ENROLLED_SERVICE_ACTIVE_BUSINESS_DEPLOYMENT_NOT_EXECUTED')


if __name__ == '__main__':
    main()
