"""PR99 exact-byte, stopped-unit installation and conflict-safe rollback.
No start/enable/restart, route edit, data restore, user creation or cloud call.
Host execution requires a separate root-held, independently issued admission.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path

HOST = 'iZvt5t8tlrm8oiZ'
RELEASE = '/opt/xuanjun-migration-s07/releases/domestic-r1'
STATE = '/var/lib/xuanjun-pr99-s09-stopped-install-v1'
ADMISSION = '/etc/xuanjun-pr99/s09-stopped-install.admission.json'
NAMES = tuple('xuanjun-pr99-domestic-' + r + '.service' for r in ('portal', 'contact', 'customer-service'))
ORIGINAL = ('secure-secrets-portal.service', 'xuanjun-wecom-customer-contact.service', 'xuanjun-wecom-customer-service.service')
PROTECTED = ORIGINAL + ('provider-neutral-domestic-bridge.service', 'winctl.service', 'nginx.service')


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def read_regular(path, limit=100000, private=False):
    path = Path(path)
    for parent in reversed(path.parents):
        require(not parent.is_symlink(), 'SYMLINK_PARENT')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1, 'FILE_IDENTITY')
        require(not before.st_mode & 0o022, 'WRITABLE_INPUT')
        if private:
            require(not before.st_mode & 0o077, 'PRIVATE_INPUT_MODE')
        data = os.read(fd, limit + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(data) <= limit and identity(before) == identity(after), 'INPUT_CHANGED_OR_OVERSIZE')
        return data
    finally:
        os.close(fd)


def write_exclusive(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def unit_bytes():
    commands = (
        'scripts/secure_secrets_portal_server.py serve --host 127.0.0.1 --port 18080',
        '-m ai_service.wecom_customer_contact_service',
        '-m ai_service.wecom_customer_service',
    )
    result = {}
    for name, command in zip(NAMES, commands):
        # Quarantine is mandatory. These units cannot reach the real bridge.
        result[name] = ('''[Unit]
Description=PR99 quarantined domestic candidate
ConditionPathExists={release}/restart-acceptance-v1/receipt.json

[Service]
Type=simple
User=65534
Group=65534
RootDirectory={release}/rootfs
WorkingDirectory=/opt/trading-system
ExecStart=/venv/bin/python {command}
Environment=PYTHONPATH=/opt/trading-system PYTHONDONTWRITEBYTECODE=1
Environment=WECOM_CONTACT_HOST=127.0.0.1 WECOM_CONTACT_PORT=18781
Environment=WECOM_KF_HOST=127.0.0.1 WECOM_KF_PORT=18780
BindReadOnlyPaths=/usr /lib /lib64
PrivateDevices=yes
PrivateNetwork=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/trading-system/runtime /home /tmp
NoNewPrivileges=yes
CapabilityBoundingSet=
RestrictSUIDSGID=yes
UMask=0077
Restart=no
TimeoutStopSec=15
KillMode=control-group
StandardOutput=null
StandardError=null
'''.format(release=RELEASE, command=command)).encode()
    return result


def manifest():
    return {'schema': 1, 'action': 'INSTALL_STOPPED_QUARANTINE_ONLY', 'host': HOST,
            'release': RELEASE, 'unit_hashes': {n: digest(b) for n, b in unit_bytes().items()},
            'activation_supported': False, 'production_cutover': False}


def systemctl(*args):
    result = subprocess.run(['/usr/bin/systemctl', *args], capture_output=True, timeout=20)
    require(result.returncode == 0, 'SYSTEMCTL_FAILED_PRESERVE')
    return result.stdout.decode()


def snapshot():
    result = {u: systemctl('show', u, '--property=LoadState,ActiveState,SubState,MainPID,FragmentPath', '--no-pager') for u in PROTECTED}
    for name in ('/var/www/wenwenwenyiyiyi.work/current', '/opt/trading-system'):
        p = Path(name)
        if p.is_symlink():
            result[name] = {'link': os.readlink(p)}
        elif p.exists():
            s = p.stat()
            result[name] = {'dev': s.st_dev, 'ino': s.st_ino, 'mode': s.st_mode, 'uid': s.st_uid, 'gid': s.st_gid}
        else:
            result[name] = None
    return result


def stopped(name):
    value = systemctl('show', name, '--property=ActiveState,MainPID', '--no-pager')
    fields = dict(line.split('=', 1) for line in value.splitlines() if '=' in line)
    return fields.get('MainPID') == '0' and fields.get('ActiveState') in ('inactive', 'failed')


def admission(action, source):
    raw = read_regular(ADMISSION, private=True)
    permit = json.loads(raw)
    require(permit['schema'] == 1 and permit['host'] == HOST, 'ADMISSION_HOST')
    require(permit['action'] == action and permit['source_sha256'] == digest(source), 'ADMISSION_ACTION_SOURCE')
    require(permit['manifest_sha256'] == digest(encode(manifest())), 'ADMISSION_MANIFEST')
    now = int(time.time())
    require(type(permit['issued_at']) is int and type(permit['expires_at']) is int, 'ADMISSION_TIME_TYPE')
    require(permit['issued_at'] <= now < permit['expires_at'] <= permit['issued_at'] + 7200, 'ADMISSION_EXPIRED')
    require(re.fullmatch(r'[a-zA-Z0-9_-]{16,80}', permit['nonce']) is not None, 'ADMISSION_NONCE')
    require(type(permit['independent_review_comment_id']) is int and permit['independent_review_comment_id'] > 0, 'INDEPENDENT_REVIEW_REFERENCE')
    # A local file is not itself independent review evidence. Its provisioning
    # through the original reviewed authority is a separate mandatory host gate.
    return permit, digest(raw)


def install(units_dir, state, permit, permit_hash):
    units = unit_bytes()
    before = snapshot()
    for original in ORIGINAL:
        require('LoadState=not-found' in before[original], 'ORIGINAL_UNIT_PRESENT')
    for name in NAMES:
        require(not os.path.lexists(units_dir / name), 'TARGET_UNIT_PRESENT')
        require(stopped(name), 'TARGET_NOT_STOPPED')
    receipt = json.loads(read_regular(Path(RELEASE) / 'restart-acceptance-v1/receipt.json', private=True))
    require(receipt['status'] == 'COPIED_RELEASE_RESTART_CLEANUP_PASS_NOT_PRODUCTION' and receipt['application_processes_stopped'] is True, 'COPY_ACCEPTANCE_MISSING')
    write_exclusive(state / 'before.json', encode(before))
    write_exclusive(state / 'intent.json', encode({'permit_sha256': permit_hash, 'nonce': permit['nonce'], 'manifest': manifest()}))
    created = []
    try:
        for name, data in units.items():
            write_exclusive(units_dir / name, data, 0o644)
            created.append(name)
            write_exclusive(state / (name + '.created'), encode({'sha256': digest(data)}))
        systemctl('daemon-reload')
        require(all(stopped(n) for n in NAMES), 'UNIT_NOT_STOPPED')
        require(snapshot() == before, 'PROTECTED_CHANGED')
        write_exclusive(state / 'receipt.json', encode({'status': 'QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION', 'manifest': manifest(), 'protected_state_unchanged': True, 'starts': 0, 'enables': 0}))
    except BaseException:
        # Never delete an unrecognised or running unit, even after partial failure.
        write_exclusive(state / 'failure.json', encode({'status': 'HOLD_PRESERVE', 'created': created}))
        raise


def rollback(units_dir, state, permit, permit_hash):
    intent = json.loads(read_regular(state / 'intent.json', private=True))
    require(intent['manifest'] == manifest(), 'ROLLBACK_MANIFEST')
    require(not (state / 'rollback.intent.json').exists(), 'ROLLBACK_ALREADY_CONSUMED')
    before = snapshot()
    targets = []
    for name, data in unit_bytes().items():
        p = units_dir / name
        if os.path.lexists(p):
            require(read_regular(p) == data and stopped(name), 'ROLLBACK_CONFLICT_OR_RUNNING')
            # Only units whose transaction intent predates creation may be removed.
            marker = json.loads(read_regular(state / (name + '.created'), private=True))
            require(marker['sha256'] == digest(data), 'ROLLBACK_OWNERSHIP')
            targets.append(name)
    write_exclusive(state / 'rollback.intent.json', encode({'nonce': permit['nonce'], 'permit_sha256': permit_hash, 'targets': targets}))
    for name in targets:
        require(read_regular(units_dir / name) == unit_bytes()[name] and stopped(name), 'ROLLBACK_CHANGED')
        (units_dir / name).unlink()
    systemctl('daemon-reload')
    require(snapshot() == before, 'PROTECTED_CHANGED')
    write_exclusive(state / 'rollback.receipt.json', encode({'status': 'OWNED_STOPPED_UNITS_REMOVED', 'removed': targets, 'production_cutover': False}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('manifest', 'install-stopped', 'rollback-stopped'))
    args = parser.parse_args()
    if args.action == 'manifest':
        print(encode(manifest()).decode(), end='')
        return
    require(os.geteuid() == 0 and os.uname().nodename == HOST, 'HOST_ROOT')
    os.umask(0o077)
    source = read_regular(Path(__file__), 100000)
    permit, permit_hash = admission(args.action, source)
    state = Path(STATE)
    if args.action == 'install-stopped':
        state.mkdir(mode=0o700)  # one attempt; never replay or merge state
    require(stat.S_IMODE(state.lstat().st_mode) == 0o700 and state.lstat().st_uid == 0 and not state.is_symlink(), 'STATE_IDENTITY')
    lock = os.open(state / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'install-stopped':
            install(Path('/etc/systemd/system'), state, permit, permit_hash)
        else:
            rollback(Path('/etc/systemd/system'), state, permit, permit_hash)
    finally:
        os.close(lock)


if __name__ == '__main__':
    main()
