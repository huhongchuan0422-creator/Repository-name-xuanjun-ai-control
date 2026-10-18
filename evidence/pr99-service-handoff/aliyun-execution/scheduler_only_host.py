import ast
import datetime
import hashlib
import json
import os
import re
import stat
import time
MARKERS = (b'/opt/trading-system', b'xuanjun', b'wecom', b'binance', b'finance')
SAFE = re.compile('[A-Za-z0-9_./-]{1,240}')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read_at(directory, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise RuntimeError('SOURCE_TYPE_OR_SIZE')
        raw = b''
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        after = os.fstat(fd)
        linked = os.stat(name, dir_fd=directory, follow_symlinks=False)
        fp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if fp(before) != fp(after) or fp(after) != fp(linked) or len(raw) != before.st_size:
            raise RuntimeError('SOURCE_DRIFT')
        return raw
    finally:
        os.close(fd)

def scheduler_inventory(deadline):
    rows = []
    scanned = 0
    matched = set()
    total = 0
    links = 0
    roots = ('/etc/systemd/system', '/usr/lib/systemd/system', '/etc/cron.d', '/var/spool/cron')
    for slot, root in enumerate(roots):
        try:
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            continue
        try:
            for name in sorted(os.listdir(fd)):
                if time.monotonic() > deadline:
                    raise RuntimeError('SCHEDULER_DEADLINE')
                if not re.fullmatch(r'[A-Za-z0-9_.:@\\-]{1,240}',name) or '/' in name:
                    raise RuntimeError('SCHEDULER_NAME_BOUND')
                s = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(s.st_mode):
                    links += 1
                    continue
                if not stat.S_ISREG(s.st_mode):
                    continue
                if slot < 2 and (not name.endswith(('.service', '.timer', '.path', '.socket'))):
                    continue
                raw = read_at(fd, name, 131072)
                scanned += 1
                total += len(raw)
                if scanned > 2048 or total > 8388608:
                    raise RuntimeError('SCHEDULER_TOTAL_BOUND')
                lower = raw.lower()
                if not any((m in lower or m in name.lower().encode() for m in MARKERS)):
                    continue
                if len(rows) >= 128:
                    raise RuntimeError('SCHEDULER_MATCH_BOUND')
                key = (slot, name)
                matched.add(key)
                rows.append({'root_slot': slot, 'name': name, 'sha256': sha(raw), 'bytes': len(raw), 'matching_lines': sum((any((m in line.lower() for m in MARKERS)) for line in raw.splitlines()))})
        finally:
            os.close(fd)
    fd = os.open('/etc', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        try:
            raw = read_at(fd, 'crontab', 131072)
        except FileNotFoundError:
            raw = None
        if raw is not None:
            scanned += 1
            if any((m in raw.lower() for m in MARKERS)):
                rows.append({'root_slot': 4, 'name': 'crontab', 'sha256': sha(raw), 'bytes': len(raw), 'matching_lines': sum((any((m in line.lower() for m in MARKERS)) for line in raw.splitlines()))})
    finally:
        os.close(fd)
    return {'regular_fragments_read': scanned, 'excluded_symlinks': links, 'candidates': rows}

def observe(expected,nonce):
    assert os.geteuid()==0 and os.uname().nodename==expected=='iZ6wee8q9z4t03hvqumwfhZ'
    return {'hostname':expected,'nonce':nonce,'observed_at':datetime.datetime.utcnow().isoformat()+'Z',
        'scope':'PR99_SCHEDULER_DEFINITIONS_ONLY_NOT_AUTHORITY',
        'schedulers':scheduler_inventory(time.monotonic()+25),
        'source_inventory':'PREVIOUS_FAILED_RESULT_NOT_RETURNED_NOT_REPLAYED',
        'business_source_imports':0,'database_opened':False,'service_actions':0,'business_requests':0,
        'canonical_data_assigned':False,'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN',
        'limitations':['IMMEDIATE_REGULAR_FRAGMENTS_ONLY_NOT_EFFECTIVE_UNIT_CONFIGURATION',
                       'EXCLUDED_LINKS_DROPINS_OTHER_NAMESPACES_NOT_COVERED','NO_DRAIN_OR_FENCE_PERFORMED']}

if __name__=='__main__':
    print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)
