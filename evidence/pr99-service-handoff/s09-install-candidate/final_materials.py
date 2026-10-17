"""Offline final-material verification and exact-file route CAS mechanics.

Caller-supplied fence proof must be independently verified before snapshot creation.
This module never obtains that proof, opens a production database, stops a writer,
reloads nginx, or chooses a route. It only handles explicitly supplied local files.
Runtime bytes/receipt details are private; do not upload generated snapshots.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

from migration_transaction import Hold, require, encode, exclusive, sync_directory


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path, limit=67108864):
    path = Path(path)
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink(), 'INPUT_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit,
                'INPUT_TYPE_SIZE')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(limit + 1)
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and len(data) == before.st_size, 'INPUT_DRIFT')
        return data
    finally:
        os.close(fd)


def safe_relative(name):
    require(type(name) is str and name and not name.startswith('/') and
            all(p not in ('', '.', '..') for p in name.split('/')), 'RELATIVE_PATH')
    return name


def write_bytes(path, raw, mode=0o400):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    sync_directory(Path(path).parent)


def snapshot_fenced_files(source, destination, names, verify_fence):
    """Copy exact already-fenced files; no live SQLite/WAL consistency claim.

    verify_fence is called before/after and returns the same approved proof digest.
    It must cover ALL writers, shared data, SQLite main/WAL/SHM and open handles.
    This function cannot replace a host-enforced fence or schema reconciliation.
    Destination is one-use and every partial artifact is retained on failure.
    """
    require(type(names) is list and 0 < len(names) <= 12000 and
            len(names) == len(set(names)), 'EXACT_FILE_LIST')
    for name in names:
        safe_relative(name)
        require(name != 'final-checkpoint.receipt.json', 'RESERVED_RECEIPT_PATH')
    proof = verify_fence()
    require(type(proof) is str and len(proof) == 64 and all(c in '0123456789abcdef' for c in proof),
            'FENCE_PROOF_REQUIRED')
    source, destination = Path(source), Path(destination)
    require(source.is_absolute() and destination.is_absolute() and
            '..' not in source.parts and '..' not in destination.parts, 'ABSOLUTE_CANONICAL_PATH')
    for ancestor in (destination.parent, *destination.parent.parents):
        require(not ancestor.is_symlink(), 'DESTINATION_SYMLINK')
    require(not (destination == source or source in destination.parents or destination in source.parents),
            'SOURCE_DESTINATION_OVERLAP')
    destination.mkdir(mode=0o700)
    sync_directory(destination.parent)
    manifest = {}
    total = 0
    for name in sorted(names):
        raw = read_regular(source / name)
        total += len(raw)
        require(total <= 536870912, 'SNAPSHOT_BYTE_BOUND')
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_bytes(target, raw)
        manifest[name] = {'sha256': sha(raw), 'bytes': len(raw)}
    require(verify_fence() == proof, 'FENCE_CHANGED_PRESERVE')
    require(all(sha(read_regular(source / name)) == item['sha256'] for name, item in manifest.items()),
            'SOURCE_CHANGED_PRESERVE')
    receipt = {'class': 'FINAL_FENCED_FILES_CANDIDATE', 'fence_proof_sha256': proof,
               'files': manifest, 'bytes': total}
    exclusive(destination / 'final-checkpoint.receipt.json', receipt)
    return receipt


def verify_received(root, receipt, expected_receipt_sha256):
    require(sha(encode(receipt)) == expected_receipt_sha256 and
            receipt.get('class') == 'FINAL_FENCED_FILES_CANDIDATE', 'CHECKPOINT_BINDING')
    require(type(receipt.get('files')) is dict and 0 < len(receipt['files']) <= 12000, 'MANIFEST')
    root = Path(root)
    actual = set()
    for current, dirs, files in os.walk(root, followlinks=False):
        require(all(not (Path(current) / d).is_symlink() for d in dirs), 'RECEIVER_DIRECTORY_LINK')
        for name in files:
            rel = (Path(current) / name).relative_to(root).as_posix()
            if rel != 'final-checkpoint.receipt.json':
                actual.add(rel)
    require(actual == set(receipt['files']), 'RECEIVED_EXACT_SET')
    total = 0
    for name, item in receipt['files'].items():
        safe_relative(name)
        raw = read_regular(root / name)
        total += len(raw)
        require(total <= 536870912 and item == {'sha256': sha(raw), 'bytes': len(raw)}, 'RECEIVED_HASH_SIZE')
    require(total == receipt['bytes'], 'RECEIVED_TOTAL')
    require(read_regular(root / 'final-checkpoint.receipt.json') == encode(receipt), 'RECEIPT_FILE_DRIFT')
    return True


def replace_owned_route(route, expected_old, new_bytes, state):
    """Exact regular-file CAS under caller-held exclusive route ownership.

    No reload or HTTPS acceptance occurs here. Symlink/current deployments and
    other writers' files are rejected. Caller must journal intent BEFORE invoking.
    A crash following replace is UNKNOWN; inspect exact bytes, never blindly retry.
    """
    route, state = Path(route), Path(state)
    old = read_regular(route, 1048576)
    require(sha(old) == expected_old and len(new_bytes) <= 1048576, 'ROUTE_CAS_CONFLICT')
    st = route.stat()
    require(st.st_uid == os.geteuid() and not st.st_mode & 0o022, 'ROUTE_OWNER_MODE')
    state.mkdir(mode=0o700)
    sync_directory(state.parent)
    write_bytes(state / 'before', old)
    write_bytes(state / 'after', new_bytes)
    exclusive(state / 'binding.json', {'route': str(route), 'before': sha(old), 'after': sha(new_bytes),
                                       'mode': stat.S_IMODE(st.st_mode)})
    temporary = route.with_name(route.name + '.pr99-candidate')
    write_bytes(temporary, new_bytes, stat.S_IMODE(st.st_mode))
    require(read_regular(route) == old, 'ROUTE_CHANGED_PRESERVE')
    os.replace(temporary, route)
    sync_directory(route.parent)
    require(read_regular(route) == new_bytes, 'ROUTE_POSTCHECK_UNKNOWN')
    return {'status': 'FILE_REPLACED_RELOAD_AND_HTTPS_PENDING', 'route_sha256': sha(new_bytes)}


def restore_owned_route(route, state):
    route, state = Path(route), Path(state)
    binding = json.loads(read_regular(state / 'binding.json'))
    require(binding['route'] == str(route), 'ROLLBACK_ROUTE_BINDING')
    old, new = read_regular(state / 'before'), read_regular(state / 'after')
    require(sha(old) == binding['before'] and sha(new) == binding['after'], 'ROLLBACK_SNAPSHOT_DRIFT')
    require(read_regular(route) == new, 'ROLLBACK_FOREIGN_ROUTE')
    temporary = route.with_name(route.name + '.pr99-rollback')
    write_bytes(temporary, old, binding['mode'])
    require(read_regular(route) == new, 'ROLLBACK_ROUTE_CHANGED')
    os.replace(temporary, route)
    sync_directory(route.parent)
    require(read_regular(route) == old, 'ROLLBACK_POSTCHECK_UNKNOWN')
    return {'status': 'FILE_RESTORED_RELOAD_AND_HTTPS_PENDING', 'source_writer_resumed': False}


def snapshot_sqlite_fenced(source, destination, verify_fence, expected_schema_sha256,
                           clock=None):
    """WAL-aware backup of a *copied*, externally fenced SQLite file set.

    Reuses the S07 stage_runtime_materials SQLite backup/integrity mechanism, but
    never connects SQLite to the original source. Only captured copies are opened.
    This cannot establish the source fence or choose the authoritative database.
    Private copies, partial database and failures are retained without replay.
    """
    import sqlite3
    import time
    clock = clock or time.monotonic
    source, destination = Path(source), Path(destination)
    require(source.is_absolute() and destination.is_absolute() and '..' not in source.parts and
            '..' not in destination.parts, 'ABSOLUTE_CANONICAL_PATH')
    require(source != destination and destination not in source.parents and source not in destination.parents,
            'SOURCE_DESTINATION_OVERLAP')
    proof = verify_fence()
    require(type(proof) is str and len(proof) == 64 and all(c in '0123456789abcdef' for c in proof),
            'FENCE_PROOF_REQUIRED')
    require(type(expected_schema_sha256) is str and len(expected_schema_sha256) == 64 and
            all(c in '0123456789abcdef' for c in expected_schema_sha256), 'SCHEMA_BINDING_REQUIRED')
    wal = source.with_name(source.name + '-wal')
    source_files = [source] + ([wal] if os.path.lexists(wal) else [])
    copied = {p.name: read_regular(p) for p in source_files}
    require(sum(map(len, copied.values())) <= 536870912, 'SQLITE_SET_BOUND')
    for p in (destination.parent, *destination.parent.parents):
        require(not p.is_symlink(), 'DESTINATION_SYMLINK')
    destination.mkdir(mode=0o700); sync_directory(destination.parent)
    capture = destination / 'captured'; capture.mkdir(mode=0o700)
    for p in source_files:
        suffix = '-wal' if p == wal else ''
        write_bytes(capture / ('source.db' + suffix), copied[p.name], 0o600)
    target = destination / 'final.db'
    # Exclusive creation consumes the output before SQLite opens it.
    write_bytes(target, b'', 0o600)
    started = clock()
    src = sqlite3.connect((capture / 'source.db').as_uri() + '?mode=ro', uri=True, timeout=5)
    dst = sqlite3.connect(str(target), timeout=5)
    def progress(status, remaining, total):
        require(clock() - started < 90, 'SQLITE_BACKUP_TIMEOUT')
    try:
        src.backup(dst, pages=128, progress=progress, sleep=0.05)
        require(dst.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'SQLITE_INTEGRITY')
        schema = dst.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        require(sha(encode(schema)) == expected_schema_sha256, 'SQLITE_SCHEMA_MISMATCH')
    finally:
        dst.close(); src.close()
    require(verify_fence() == proof, 'FENCE_CHANGED_PRESERVE')
    after_files = [source] + ([wal] if os.path.lexists(wal) else [])
    require(after_files == source_files and
            all(read_regular(p) == copied[p.name] for p in source_files), 'SOURCE_CHANGED_PRESERVE')
    raw = read_regular(target)
    target.chmod(0o400)
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)
    sync_directory(destination)
    receipt = {'class': 'FINAL_FENCED_SQLITE_CANDIDATE', 'fence_proof_sha256': proof,
               'sha256': sha(raw), 'bytes': len(raw), 'schema_sha256': expected_schema_sha256,
               'integrity': 'PASS', 'source_wal_captured': wal in source_files,
               'source_database_opened': False}
    exclusive(destination / 'sqlite-checkpoint.receipt.json', receipt)
    return receipt
