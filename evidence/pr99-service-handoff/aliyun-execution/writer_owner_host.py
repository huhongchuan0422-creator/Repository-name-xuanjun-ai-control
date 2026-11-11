"""Resolve only two already observed domestic handle owners; no filesystem writes."""
import datetime
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

PINS = {90354: 91354061, 188767: 178248493}
UNITS = ('provider-neutral-domestic-bridge.service', 'windows-interaction-http.service')
ROOT = '/home/openclaw_ops/v8-domestic-operations'


def read(path, limit=16384):
    with Path(path).open('rb') as f:
        raw = f.read(limit + 1)
    if len(raw) > limit:
        raise RuntimeError('METADATA_BOUND')
    return raw


def start(p):
    raw = read(p / 'stat', 4096)
    return int(raw[raw.rfind(b')') + 2:].split()[19])


def category(name):
    if name.endswith('-wal'): return 'SQLITE_WAL'
    if name.endswith('-shm'): return 'SQLITE_SHM'
    if name.endswith(('.db', '.sqlite', '.sqlite3')): return 'DATABASE'
    if name.endswith('.jsonl'): return 'JSONL'
    if name.endswith('.log'): return 'LOG'
    if name.endswith('.json'): return 'JSON'
    return 'OTHER'


def observe(expected, nonce):
    assert os.geteuid() == 0 and os.uname().nodename == expected == 'iZvt5t8tlrm8oiZ'
    root = Path(ROOT).stat()
    assert (root.st_dev, root.st_ino) == (64771, 835411)
    control = {}
    units = []
    for name in UNITS:
        r = subprocess.run(['/usr/bin/systemctl', 'show', name,
            '--property=ControlGroup,MainPID,ActiveState', '--no-pager'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3,
            universal_newlines=True, env={'LANG': 'C', 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})
        values = dict(line.split('=', 1) for line in r.stdout.splitlines() if '=' in line)
        assert r.returncode == 0 and values.get('MainPID', '').isdigit()
        control[name] = values.get('ControlGroup', '')
        active = values.get('ActiveState')
        assert active in ('active', 'inactive', 'failed', 'activating', 'deactivating')
        units.append({'unit': name, 'pid': int(values['MainPID']), 'active': active})
    rows = []
    for pid, ticks in PINS.items():
        p = Path('/proc') / str(pid)
        assert start(p) == ticks
        cg = read(p / 'cgroup').decode()
        paths = [line.split(':', 2)[2] for line in cg.splitlines()]
        groups = [name for name, group in control.items() if group and group in paths]
        handles = []
        fds = list((p / 'fd').iterdir())
        assert len(fds) <= 4096
        for fd in fds:
            try:
                target = os.readlink(fd)
                if not target.startswith(ROOT + '/'):
                    continue
                fs = fd.stat()
                info = read(p / 'fdinfo' / fd.name, 4096)
                flags = [line.partition(b':')[2].strip() for line in info.splitlines() if line.startswith(b'flags:')]
                assert len(flags) == 1
                handles.append({'fd': int(fd.name), 'category': category(target),
                    'device': fs.st_dev, 'inode': fs.st_ino,
                    'writable': (int(flags[0], 8) & os.O_ACCMODE) in (os.O_WRONLY, os.O_RDWR)})
            except FileNotFoundError:
                raise RuntimeError('HANDLE_CHANGED_PRESERVE') from None
        assert start(p) == ticks and len(handles) <= 256
        rows.append({'pid': pid, 'start_ticks': ticks, 'matched_units': groups,
                     'handles': sorted(handles, key=lambda x: x['fd'])})
    after = Path(ROOT).stat()
    assert (after.st_dev, after.st_ino) == (root.st_dev, root.st_ino)
    return {'hostname': expected, 'nonce': nonce, 'observed_at': datetime.datetime.utcnow().isoformat() + 'Z',
            'scope': 'EXACT_EXISTING_DOMESTIC_HANDLE_OWNER_METADATA', 'units': units, 'processes': rows,
            'service_actions': 0, 'database_opened': False, 'business_requests': 0,
            'fence_enforced': False, 'inflight_drained': False}


if __name__ == '__main__':
    print(json.dumps(observe(EXPECTED, NONCE), sort_keys=True), flush=True)
