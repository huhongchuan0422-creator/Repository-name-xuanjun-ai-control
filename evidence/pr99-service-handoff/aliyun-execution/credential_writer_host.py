"""Observe handles to one newly identified source-default database candidate.
No database open, data content read, process control, drain, fence or authority.
"""
import os, stat, re, json, datetime
from pathlib import Path

PIN = (64771, 1601016)


def writable_flags(raw):
    values = [line.partition(b':')[2].strip() for line in raw.splitlines() if line.startswith(b'flags:')]
    if len(values) != 1:
        raise ValueError('FD_FLAGS_SCHEMA')
    return (int(values[0], 8) & os.O_ACCMODE) in (os.O_WRONLY, os.O_RDWR)


def shared_writable_mapping(line, identities):
    parts = line.split(None, 5)
    if len(parts) < 5:
        return False
    permissions, device, inode = parts[1], parts[3], parts[4]
    if len(permissions) != 4 or permissions[1] != 'w' or permissions[3] != 's':
        return False
    major, minor = device.split(':')
    return (int(major, 16), int(minor, 16), int(inode)) in identities


def read_meta(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        raw = b''
        while len(raw) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw += part
        if len(raw) > limit:
            raise ValueError('PROC_METADATA_BOUND')
        return raw
    finally:
        os.close(fd)


def ticks(process):
    raw = read_meta(process / 'stat', 8192)
    return int(raw[raw.rfind(b')')+2:].split()[19])


def observe(expected, nonce):
    assert os.geteuid() == 0 and os.uname().nodename == expected == 'iZ6wee8q9z4t03hvqumwfhZ'
    root = os.open('/opt/trading-system/database', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        raw = read_at(root, 'connection.py', 1048576)
    finally:
        os.close(root)
    assert hashlib.sha256(raw).hexdigest() == '58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece'
    model = Defaults(raw, '/opt/trading-system/database/connection.py', '/opt/trading-system')
    status, location = locate(model.globals.get('DATABASE_URL'), 'URL', '/opt/trading-system')
    assert status == 'FILE_CANDIDATE'
    main = os.lstat(location)
    assert stat.S_ISREG(main.st_mode) and (main.st_dev, main.st_ino) == PIN and main.st_nlink == 1
    parts, targets = [], {}
    for role, suffix in (('MAIN',''), ('WAL','-wal'), ('SHM','-shm'), ('JOURNAL','-journal')):
        try:
            item = os.lstat(location + suffix)
        except FileNotFoundError:
            parts.append({'part': role, 'state': 'MISSING'})
            continue
        assert stat.S_ISREG(item.st_mode) and item.st_nlink == 1
        targets[(item.st_dev, item.st_ino)] = role
        parts.append({'part': role, 'state': 'REGULAR', 'device': item.st_dev, 'inode': item.st_ino, 'uid': item.st_uid, 'gid': item.st_gid, 'bytes': item.st_size})
    mapping_ids = {(os.major(dev), os.minor(dev), ino) for dev, ino in targets}
    processes = sorted((p for p in Path('/proc').iterdir() if p.name.isdigit()), key=lambda p:int(p.name))
    assert len(processes) <= 4096
    counts = {'processes_seen':len(processes), 'processes_scanned':0, 'races':0, 'unreadable_or_bounded':0, 'fds_inspected':0}
    owners = []
    for process in processes:
        try:
            before = ticks(process)
            fds = list((process / 'fd').iterdir())
            if len(fds) > 4096 or counts['fds_inspected'] + len(fds) > 200000:
                counts['unreadable_or_bounded'] += 1
                continue
            handles = []
            for fd in fds:
                counts['fds_inspected'] += 1
                try:
                    fs = fd.stat()
                    part = targets.get((fs.st_dev,fs.st_ino))
                    if part:
                        writable = writable_flags(read_meta(process/'fdinfo'/fd.name, 8192))
                        after_fd = fd.stat()
                        if (after_fd.st_dev,after_fd.st_ino) != (fs.st_dev,fs.st_ino):
                            raise ProcessLookupError()
                        handles.append({'fd':int(fd.name),'part':part,'writable':writable})
                except FileNotFoundError:
                    counts['races'] += 1
            maps = read_meta(process/'maps', 1048576).decode('utf-8','replace')
            mappings = sum(shared_writable_mapping(line,mapping_ids) for line in maps.splitlines())
            candidate = None
            if handles or mappings:
                cg = read_meta(process/'cgroup',32768).decode('utf-8','replace')
                units = sorted({segment for line in cg.splitlines() for segment in line.split('/') if re.fullmatch(r'[A-Za-z0-9_.@-]{1,180}\.service',segment)})
                assert len(handles) <= 256 and len(units) <= 16
                candidate = {'pid':int(process.name),'start_ticks':before,'units':units,'handles':handles,'shared_writable_mappings':mappings}
            if ticks(process) != before:
                raise ProcessLookupError()
            if candidate:
                owners.append(candidate)
            counts['processes_scanned'] += 1
        except (FileNotFoundError,ProcessLookupError):
            counts['races'] += 1
        except (OSError,ValueError):
            counts['unreadable_or_bounded'] += 1
    after = os.lstat(location)
    assert (after.st_dev,after.st_ino) == PIN and len(owners) <= 64
    return {'scope':'PR99_EXACT_CREDENTIAL_DB_CANDIDATE_HANDLE_SAMPLE_NOT_FENCE', 'hostname':expected,'nonce':nonce,
        'observed_at':datetime.datetime.utcnow().isoformat()+'Z','parts':parts,'counts':counts,'owners':owners,
        'source_default_candidate_only':True,'database_opened':False,'business_requests':0,'service_actions':0,
        'fence_enforced':False,'all_writers_proven':False,'inflight_drained':False,
        'limitations':['INSTANT_VISIBLE_PROC_SAMPLE_NOT_IDLE_OR_FUTURE_WRITER_PROOF','SOURCE_DEFAULT_NOT_EFFECTIVE_RUNTIME_CONFIGURATION','NO_DATABASE_CONTENT_OR_FORMAT_INSPECTION','NO_FENCE_DRAIN_STOP_OR_CHECKPOINT']}
