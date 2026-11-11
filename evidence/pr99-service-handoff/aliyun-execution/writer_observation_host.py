"""Fixed PR99 process/descriptor observation. Metadata only, never a fence.

Only imported by the exact embedded read-only entry; no standalone dispatch.
All /proc reads are bounded. Runtime file contents and environment are not read.
"""
import datetime
import hashlib
import json
import os
import stat
import subprocess
import time
from pathlib import Path

ROOTS = (
    ('portal', '/opt/trading-system/runtime/secure-secrets-portal'),
    ('operations', '/opt/trading-system/runtime/v8-domestic-operations'),
    ('database', '/opt/trading-system/database/data'),
    ('workspace', '/home/admin/.openclaw/workspace/xuanjun-agent-coordination'),
    ('external_operations', '/home/openclaw_ops/v8-domestic-operations'),
)
TAGS = (
    'scripts/secure_secrets_portal_server.py',
    'ai_service.wecom_customer_contact_service',
    'ai_service.wecom_customer_service',
    'ai_service.internal_provider_neutral_bridge',
    'production_start.py', 'production_transport.py',
)
UNITS = ('secure-secrets-portal.service',
         'xuanjun-wecom-customer-contact.service',
         'xuanjun-wecom-customer-service.service',
         'xuanjun-pr99-domestic-portal.service',
         'xuanjun-pr99-domestic-contact.service',
         'xuanjun-pr99-domestic-customer-service.service')


def bounded(path, limit):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise RuntimeError('PROC_BOUND')
    return raw


def identity(path):
    # The comm field can contain spaces or ')'; all following fields are numeric.
    raw = bounded(path / 'stat', 4096)
    values = raw[raw.rfind(b')') + 2:].split()
    return int(values[1]), int(values[19])  # ppid, starttime, not pid alone


def classify(target, roots):
    deleted = target.endswith(' (deleted)')
    target = target[:-10] if deleted else target
    labels = sorted({label for label, name in roots
                     if target == name or target.startswith(name + '/')})
    return labels, deleted


def writable_flags(raw):
    flags = [line.partition(b':')[2].strip() for line in raw.splitlines()
             if line.startswith(b'flags:')]
    if len(flags) != 1:
        raise RuntimeError('FD_FLAGS_UNKNOWN')
    return int(flags[0], 8) & os.O_ACCMODE in (os.O_WRONLY, os.O_RDWR)


def scan(roots, deadline, proc=Path('/proc')):
    counts = {'processes': 0, 'fds': 0, 'vanished': 0, 'unreadable': 0,
              'pid_identity_changed': 0}
    matches = []
    pids = sorted((p for p in proc.iterdir() if p.name.isdigit()), key=lambda p: int(p.name))
    if len(pids) > 4096:
        raise RuntimeError('PROCESS_BOUND')
    for p in pids:
        if int(p.name) == os.getpid():
            continue
        if time.monotonic() > deadline:
            raise RuntimeError('OBSERVATION_DEADLINE')
        counts['processes'] += 1
        try:
            before = identity(p)
            tags = [i for i, tag in enumerate(TAGS) if tag.encode() in bounded(p / 'cmdline', 65536)]
            handles = []
            fds = sorted((p / 'fd').iterdir(), key=lambda f: int(f.name))
            if len(fds) > 4096:
                raise RuntimeError('FD_BOUND')
            for fd in fds:
                counts['fds'] += 1
                if counts['fds'] > 65536:
                    raise RuntimeError('TOTAL_FD_BOUND')
                try:
                    labels, deleted = classify(os.readlink(fd), roots)
                    if not labels:
                        continue
                    fs = fd.stat()
                    # Never open the descriptor target (which could be a database).
                    flags = writable_flags(bounded(p / 'fdinfo' / fd.name, 4096))
                    handles.append({'fd': int(fd.name), 'roots': labels, 'writable': flags,
                                    'deleted': deleted, 'device': fs.st_dev, 'inode': fs.st_ino})
                except FileNotFoundError:
                    counts['vanished'] += 1
                except PermissionError:
                    counts['unreadable'] += 1
            mapped = []
            # Shared writable mappings can persist after the file descriptor closes.
            for line in bounded(p / 'maps', 2097152).decode('utf-8', 'replace').splitlines():
                fields = line.split(None, 5)
                if len(fields) != 6 or len(fields[1]) != 4 or fields[1][1] != 'w' or fields[1][3] != 's':
                    continue
                labels, deleted = classify(fields[5], roots)
                if labels:
                    mapped.append({'roots': labels, 'deleted': deleted})
            if len(handles) > 256 or len(mapped) > 256:
                raise RuntimeError('MATCH_BOUND')
            if before != identity(p):
                counts['pid_identity_changed'] += 1
                continue
            if tags or handles or mapped:
                group = bounded(p / 'cgroup', 16384)
                matches.append({'pid': int(p.name), 'ppid': before[0], 'start_ticks': before[1],
                                'uid': p.stat().st_uid, 'tags': tags,
                                'cgroup_sha256': hashlib.sha256(group).hexdigest(),
                                'handles': handles, 'shared_writable_mappings': mapped})
            if len(matches) > 128:
                raise RuntimeError('MATCH_PROCESS_BOUND')
        except (FileNotFoundError, ProcessLookupError):
            counts['vanished'] += 1
        except PermissionError:
            counts['unreadable'] += 1
    return {'counts': counts, 'processes': matches}


def observe(expected, nonce):
    assert os.geteuid() == 0 and os.uname().nodename == expected
    deadline = time.monotonic() + 35
    roots = []
    metadata = []
    for label, name in ROOTS:
        try:
            resolved = str(Path(name).resolve(strict=True))
            s = Path(name).stat()
            roots += [(label, name), (label, resolved)]
            metadata.append({'root': label, 'present': True, 'device': s.st_dev, 'inode': s.st_ino})
        except FileNotFoundError:
            metadata.append({'root': label, 'present': False})
    samples = [scan(roots, deadline)]
    units = []
    for name in UNITS:
        r = subprocess.run(['/usr/bin/systemctl', 'show', name,
            '--property=LoadState,ActiveState,MainPID,ControlGroup', '--no-pager'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3,
            universal_newlines=True, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'})
        fields = dict(line.split('=', 1) for line in r.stdout.splitlines() if '=' in line)
        states = ('loaded', 'not-found', 'masked', 'error', 'bad-setting', 'active',
                  'inactive', 'failed', 'activating', 'deactivating', 'reloading')
        units.append({'unit': name, 'returncode': r.returncode,
                      'load': fields.get('LoadState') if fields.get('LoadState') in states else 'UNKNOWN',
                      'active': fields.get('ActiveState') if fields.get('ActiveState') in states else 'UNKNOWN',
                      'pid': int(fields.get('MainPID', '0')),
                      'cgroup_sha256': hashlib.sha256(fields.get('ControlGroup', '').encode()).hexdigest()})
    # Metadata of scheduler entrypoints; their contents/commands are not read.
    schedulers = []
    for name in ('/etc/crontab', '/etc/cron.d', '/var/spool/cron', '/var/spool/cron/crontabs'):
        try:
            s = Path(name).lstat()
            schedulers.append({'slot': len(schedulers), 'present': True, 'mode': stat.S_IMODE(s.st_mode),
                               'uid': s.st_uid, 'size': s.st_size, 'symlink': stat.S_ISLNK(s.st_mode)})
        except FileNotFoundError:
            schedulers.append({'slot': len(schedulers), 'present': False})
    samples.append(scan(roots, deadline))
    return {'hostname': expected, 'uid': 0, 'nonce': nonce,
            'observed_at': datetime.datetime.utcnow().isoformat() + 'Z',
            'scope': 'PR99_OPEN_HANDLE_OBSERVATION_NOT_AUTHORITY_OR_FENCE',
            'roots': metadata, 'samples': samples, 'units': units, 'scheduler_metadata': schedulers,
            'authoritative_writer': 'UNKNOWN', 'enforced_fence': 'UNKNOWN', 'inflight_drained': False,
            'database_opened': False, 'service_actions': 0, 'business_requests': 0,
            'limitations': ['IDLE_WRITERS_NOT_EXCLUDED', 'SCHEDULER_CONTENTS_NOT_READ',
                            'OTHER_MOUNT_NAMESPACES_NOT_PROVEN', 'NO_STOP_OR_DRAIN_PERFORMED']}


if __name__ == '__main__':
    # EXPECTED/NONCE are supplied only by the exact fixed-host transport bootstrap.
    print(json.dumps(observe(EXPECTED, NONCE), sort_keys=True), flush=True)
