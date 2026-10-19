"""P2 authority recovery admission, never an installer or authority initializer.

Source identities are fixed. Live isolation facts must come from independently
pinned management signers. A signed assertion is evidence, not a revocation
operation. This program does not discover databases or issue production grants.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
SOURCE = '6041c7458dce7c83c49c5a9eafa0e20cef52d1c0'
TREE = '8e27d077d22af392108568ac06d284df4dd4b35e'
ROLES = {'owner', 'isolation', 'reconciliation'}
CHANNELS = {'ssh', 'ram_swas', 'github_runners', 'systemd', 'schedulers',
            'issuer_api', 'storage_clones', 'other_hosts'}
HEX = re.compile(r'^[0-9a-f]{64}$')
IDENT = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
MAX = 262144


class Hold(RuntimeError):
    pass


def need(ok, reason):
    if not ok:
        raise Hold(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    need(len(raw) <= MAX, 'JSON_BOUND')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_KEY')
            result[key] = value
        return result
    def invalid(unused):
        raise Hold('NONFINITE_JSON')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=invalid)


def fields(value, names):
    need(type(value) is dict and set(value) == set(names.split()), 'FIELDS')


def pin(value):
    need(type(value) is str and HEX.fullmatch(value) is not None, 'SHA256')
    return value


def ident(value):
    need(type(value) is str and IDENT.fullmatch(value) is not None and
         value.upper() not in ('UNKNOWN', 'NONE', 'UNVERIFIED'), 'IDENTITY')
    return value


def path(value):
    need(type(value) is str and value.startswith('/') and value != '/' and
         not value.startswith('//') and os.path.normpath(value) == value and
         not any(ord(c) < 32 or ord(c) == 127 for c in value) and
         '\\' not in value, 'ABSOLUTE_PATH')
    return value


def directory(name):
    path(name)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in name.strip('/').split('/'):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            need(info.st_uid == 0 and not info.st_mode & 0o022,
                 'DIRECTORY_PROTECTION')
            for key in ('system.posix_acl_access', 'system.posix_acl_default'):
                try:
                    os.getxattr(fd, key)
                except OSError as exc:
                    if exc.errno not in (61, 95):
                        raise
                else:
                    raise Hold('DIRECTORY_ACL')
        return fd
    except BaseException:
        os.close(fd)
        raise


def opened(name):
    path(name)
    parent = directory(os.path.dirname(name))
    try:
        fd = os.open(os.path.basename(name), os.O_RDONLY | os.O_NOFOLLOW |
                     os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and
             info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
             'FILE_PROTECTION')
        return fd
    except BaseException:
        os.close(fd)
        raise


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read(name, expected=None, bound=MAX):
    fd = opened(name)
    try:
        before = os.fstat(fd)
        need(before.st_size <= bound, 'FILE_BOUND')
        raw = b''
        while len(raw) <= bound:
            block = os.read(fd, min(65536, bound + 1 - len(raw)))
            if not block:
                break
            raw += block
        need(stamp(before) == stamp(os.fstat(fd)) and len(raw) == before.st_size,
             'READ_RACE')
        if expected is not None:
            need(sha(raw) == pin(expected), 'FILE_SHA')
        return raw
    finally:
        os.close(fd)


def reference(value):
    fields(value, 'path sha256')
    path(value['path'])
    pin(value['sha256'])
    return value


def openssl(args, raw=None):
    return subprocess.check_output(['/usr/bin/openssl'] + args, input=raw,
        stderr=subprocess.DEVNULL, timeout=5,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})


def load_trust(name, expected):
    trust = decode(read(name, expected))
    fields(trust, 'schema host keys')
    need(type(trust['schema']) is int and trust['schema'] == 1 and
         trust['host'] == HOST and type(trust['keys']) is dict and
         set(trust['keys']) == ROLES, 'TRUST_SCOPE')
    public = {}
    for role, ref in trust['keys'].items():
        fields(ref, 'path sha256 der_sha256')
        raw = read(path(ref['path']), pin(ref['sha256']), 16384)
        need(raw.startswith(b'-----BEGIN PUBLIC KEY-----\n') and
             b'PRIVATE KEY' not in raw, 'PUBLIC_KEY_ONLY')
        der = openssl(['pkey', '-pubin', '-outform', 'DER'], raw)
        need(sha(der) == pin(ref['der_sha256']), 'TRUST_DER_PIN')
        detail = openssl(['rsa', '-pubin', '-text', '-noout'], raw).decode('ascii')
        modulus = openssl(['rsa', '-pubin', '-modulus', '-noout'], raw).decode('ascii')
        need(re.search(r'Exponent: 65537 \(0x10001\)', detail) is not None and
             2048 <= int(modulus.strip().split('=')[1], 16).bit_length() <= 4096,
             'RSA_PARAMETERS')
        public[role] = raw
    need(len({trust['keys'][r]['der_sha256'] for r in ROLES}) == 3,
         'INDEPENDENT_TRUST_ROLES')
    return public


def signature(body, encoded, key):
    need(type(encoded) is str and len(encoded) <= 2048, 'SIGNATURE_BOUND')
    try:
        signed = base64.b64decode(encoded.encode('ascii'), validate=True)
    except (ValueError, UnicodeError):
        raise Hold('SIGNATURE_ENCODING')
    # Temporary files contain PUBLIC material only. Root protected ancestry;
    # no private signer or production files are opened or generated.
    with tempfile.TemporaryDirectory(prefix='p2-recovery-verify-', dir='/root') as root:
        for name, raw in [('key.pem', key), ('signature', signed)]:
            fd = os.open(root + '/' + name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
        try:
            openssl(['dgst', '-sha256', '-verify', root + '/key.pem',
                     '-signature', root + '/signature'], canonical(body))
        except subprocess.CalledProcessError:
            raise Hold('SIGNATURE_INVALID')


def verified_packet(packet, keys, request, now):
    fields(packet, 'body signatures')
    body = packet['body']
    fields(body, 'schema request_sha256 issued_utc expires_utc inventory isolation history sources restoration')
    need(type(body['schema']) is int and body['schema'] == 1 and
         body['request_sha256'] == sha(canonical(request)), 'PACKET_BINDING')
    need(type(body['issued_utc']) is int and type(body['expires_utc']) is int and
         body['issued_utc'] <= now < body['expires_utc'] <= body['issued_utc'] + 300,
         'EVIDENCE_EXPIRED')
    need(type(packet['signatures']) is dict and set(packet['signatures']) == ROLES,
         'SIGNATURE_ROLES')
    for role in sorted(ROLES):
        signature(body, packet['signatures'][role], keys[role])
    inventory = body['inventory']
    fields(inventory, 'complete channels unknown_writers')
    need(inventory['complete'] is True and inventory['unknown_writers'] == [] and
         type(inventory['channels']) is dict and
         set(inventory['channels']) == CHANNELS, 'WRITER_INVENTORY_INCOMPLETE')
    for channel in inventory['channels'].values():
        fields(channel, 'status source_id receipt_sha256')
        need(channel['status'] in ('ISOLATED', 'NOT_PRESENT_PROVEN'),
             'CHANNEL_NOT_ISOLATED')
        ident(channel['source_id'])
        pin(channel['receipt_sha256'])
    isolation = body['isolation']
    fields(isolation, 'old_authority_id old_epoch revoked_grants_sha256 all_old_tokens_rejected enforcement_sha256')
    need(isolation['old_authority_id'] == request['old_authority_id'] and
         isolation['old_epoch'] == request['old_epoch'] and
         isolation['all_old_tokens_rejected'] is True, 'OLD_AUTHORITY_NOT_FENCED')
    pin(isolation['revoked_grants_sha256'])
    pin(isolation['enforcement_sha256'])
    history = body['history']
    fields(history, 'status pending_transactions unknown_effects disposition_sha256 old_grants_not_reissued preservation')
    need(history['status'] == 'RECONCILED' and history['pending_transactions'] == [] and
         history['unknown_effects'] == [] and history['old_grants_not_reissued'] is True,
         'HISTORY_UNRECONCILED')
    pin(history['disposition_sha256'])
    need(type(history['preservation']) is list and bool(history['preservation']),
         'PRESERVATION_MISSING')
    for item in history['preservation']:
        fields(item, 'source_id sha256 category')
        ident(item['source_id'])
        pin(item['sha256'])
        need(item['category'] in ('DATABASE_AND_SIDECARS', 'BACKUP', 'EXECUTION_RECEIPTS'),
             'PRESERVATION_CATEGORY')
    need({x['category'] for x in history['preservation']} ==
         {'DATABASE_AND_SIDECARS', 'BACKUP', 'EXECUTION_RECEIPTS'}, 'PRESERVATION_INCOMPLETE')
    need(type(body['sources']) is list and bool(body['sources']), 'SOURCE_RECORDS')
    for ref in body['sources']:
        reference(ref)
        read(ref['path'], ref['sha256'])
    return body


def validate_request(request):
    fields(request, 'schema host source_commit source_tree recovery_id old_authority_id new_authority_id old_epoch new_epoch writer_id new_grant_id route target_database nonce')
    need(type(request['schema']) is int and request['schema'] == 1 and
         request['host'] == HOST and request['source_commit'] == SOURCE and
         request['source_tree'] == TREE, 'REQUEST_SOURCE_HOST')
    for name in ('recovery_id', 'old_authority_id', 'new_authority_id', 'writer_id', 'new_grant_id'):
        ident(request[name])
    need(request['old_authority_id'] != request['new_authority_id'], 'AUTHORITY_REUSE')
    need(type(request['old_epoch']) is int and request['old_epoch'] >= 0 and
         type(request['new_epoch']) is int and request['new_epoch'] > request['old_epoch'],
         'EPOCH_NOT_ADVANCED')
    need(request['route'] in ('RESTORE_EXISTING', 'NEW_AUTHORITY'), 'ROUTE')
    path(request['target_database'])
    pin(request['nonce'])


def inspect_snapshot(ref):
    """Inspect an ALREADY consistent, manager-created SQLite backup, never live DB.

    immutable is used only on a private in-memory copy of the exact SHA-pinned
    consistent backup, NOT on an unknown live database. No sidecars are omitted
    from a live snapshot operation: this module never creates that snapshot.
    """
    reference(ref)
    raw = read(ref['path'], ref['sha256'], 16777216)
    need(raw.startswith(b'SQLite format 3\x00'), 'SNAPSHOT_FORMAT')
    with tempfile.TemporaryDirectory(prefix='p2-recovery-snapshot-', dir='/root') as root:
        target = root + '/snapshot.sqlite3'
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
        db = sqlite3.connect('file:' + quote(target, safe='/') + '?mode=ro&immutable=1',
                             uri=True, timeout=1)
        steps = [0]
        def progress():
            steps[0] += 1
            return int(steps[0] > 10000)
        db.set_progress_handler(progress, 100)
        try:
            db.execute('PRAGMA query_only=ON')
            need(db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'SNAPSHOT_CORRUPT')
            expected = {'grants': {'id','binding','body','approval','consumed','terminal','writer','epoch','fence','expiry'},
                        'attempts': {'id','grant_id','ordinal','operation','state','proof'},
                        'audit': {'id','grant_id','event','at','body'}}
            tables = dict(db.execute("SELECT name,type FROM sqlite_master WHERE name IN ('grants','attempts','audit')"))
            for table, cols in expected.items():
                need(tables.get(table) == 'table' and
                     {r[1] for r in db.execute('PRAGMA table_info(' + table + ')')} == cols,
                     'SNAPSHOT_SCHEMA')
            rows = db.execute('SELECT grant_id,ordinal,state FROM attempts LIMIT 10001').fetchall()
            grants = db.execute('SELECT id,consumed,terminal FROM grants LIMIT 10001').fetchall()
            need(len(rows) <= 10000 and len(grants) <= 10000, 'SNAPSHOT_ROW_BOUND')
            gid = {g[0]: g for g in grants}
            grouped = {}
            for grant, ordinal, state in rows:
                need(grant in gid and type(ordinal) is int and 1 <= ordinal <= 5 and
                     state in ('NO_WRITE','SAFE_CHECKPOINT','SUCCESS'), 'SNAPSHOT_PENDING_OR_UNKNOWN')
                grouped.setdefault(grant, []).append(ordinal)
            for grant, consumed, terminal in grants:
                need(type(consumed) is int and 0 <= consumed <= 5 and terminal in (0,1) and
                     sorted(grouped.get(grant, [])) == list(range(1, consumed + 1)),
                     'SNAPSHOT_QUOTA_HISTORY')
            return {'grants': len(grants), 'attempts': len(rows),
                    'audit_rows': db.execute('SELECT count(*) FROM audit').fetchone()[0],
                    'snapshot_sha256': ref['sha256'], 'production_database_opened': False}
        finally:
            db.close()


def decide(request, packet, keys, now=None):
    validate_request(request)
    now = int(time.time()) if now is None else now
    body = verified_packet(packet, keys, request, now)
    decision = {'schema': 1, 'state': 'RECOVERY_EVIDENCE_VALIDATED_NOT_ACTIVATED',
                'request_sha256': sha(canonical(request)),
                'evidence_sha256': sha(canonical(packet)), 'route': request['route'],
                'authority_id': request['new_authority_id'], 'epoch': request['new_epoch'],
                'expires_utc': body['expires_utc'], 'authority_initialized': False,
                'grant_registered': False, 'writer_started': False,
                'activation_permission': 'NOT_INFERRED'}
    restoration = body['restoration']
    fields(restoration, 'status snapshot')
    if request['route'] == 'RESTORE_EXISTING':
        need(restoration['status'] == 'CONSISTENT_BACKUP_VERIFIED', 'RESTORE_SNAPSHOT_REQUIRED')
        decision['snapshot'] = inspect_snapshot(restoration['snapshot'])
    else:
        need(restoration['status'] == 'UNRECOVERABLE_WITH_DISPOSITION' and
             restoration['snapshot'] is None, 'NEW_AUTHORITY_DISPOSITION_REQUIRED')
    return decision


def checkpoint(root, request, decision):
    """Two-phase durable decision only. Uncommitted output is retained and rejected."""
    need(decision['state'] == 'RECOVERY_EVIDENCE_VALIDATED_NOT_ACTIVATED' and
         decision['request_sha256'] == sha(canonical(request)), 'DECISION_BINDING')
    fd = directory(root)
    lock = None
    try:
        need(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700, 'CHECKPOINT_DIRECTORY')
        lock = os.open('.recovery.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        info = os.fstat(lock)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 0 and
             stat.S_IMODE(info.st_mode) == 0o600, 'CHECKPOINT_LOCK')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        name = ident(request['recovery_id'])
        data = canonical({'request': request, 'decision': decision}) + b'\n'
        index_path = root + '/.recovery-commits.sqlite3'
        created = False
        try:
            idx = os.open('.recovery-commits.sqlite3', os.O_RDWR | os.O_CREAT |
                          os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            os.fsync(idx)
            os.close(idx)
            os.fsync(fd)
            created = True
        except FileExistsError:
            pass
        idx = opened(index_path)
        identity = stamp(os.fstat(idx))[:2]
        os.close(idx)
        for suffix in ('-journal', '-wal', '-shm'):
            need(not os.path.lexists(index_path + suffix), 'CHECKPOINT_INDEX_RECOVERY_REQUIRED')
        db = sqlite3.connect(index_path, isolation_level=None, timeout=1)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA journal_mode=DELETE')
            if created:
                db.execute('CREATE TABLE commits(id TEXT PRIMARY KEY,sha TEXT NOT NULL,device INTEGER NOT NULL,inode INTEGER NOT NULL)')
            need(db.execute('PRAGMA table_info(commits)').fetchall() and
                 stamp(os.lstat(index_path))[:2] == identity, 'CHECKPOINT_INDEX_IDENTITY')
            row = db.execute('SELECT sha,device,inode FROM commits WHERE id=?', (name,)).fetchone()
            try:
                existing = read(root + '/' + name + '.json')
            except FileNotFoundError:
                existing = None
            if existing is not None:
                need(existing == data, 'CHECKPOINT_CONFLICT')
                info = os.lstat(root + '/' + name + '.json')
                need(row == (sha(data), info.st_dev, info.st_ino), 'CHECKPOINT_NOT_COMMITTED')
                return 'ALREADY_COMMITTED'
            need(row is None, 'CHECKPOINT_ORPHAN_COMMIT')
            out = os.open(name + '.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                          os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                view = memoryview(data)
                while view:
                    count = os.write(out, view)
                    need(count > 0, 'CHECKPOINT_SHORT_WRITE')
                    view = view[count:]
                os.fsync(out)
                info = os.fstat(out)
            finally:
                os.close(out)
            os.fsync(fd)
            # SQLite FULL commit is the final publication. No success marker
            # can be accepted after failed data/directory fsync or partial write.
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO commits VALUES(?,?,?,?)',
                       (name, sha(data), info.st_dev, info.st_ino))
            db.execute('COMMIT')
            return 'COMMITTED_DECISION_NOT_ACTIVATION'
        finally:
            db.close()
    finally:
        if lock is not None:
            os.close(lock)
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('assess', 'checkpoint'))
    for option in ('request', 'request-sha256', 'evidence', 'evidence-sha256',
                   'trust', 'trust-sha256'):
        parser.add_argument('--' + option, required=True)
    parser.add_argument('--checkpoint-root')
    args = parser.parse_args()
    need(os.getuid() == 0 and os.geteuid() == 0 and
         os.uname().nodename.split('.')[0] == HOST and sys.flags.isolated and
         sys.flags.no_site and sys.dont_write_bytecode, 'ISOLATED_UK_ROOT_REQUIRED')
    request = decode(read(args.request, args.request_sha256))
    packet = decode(read(args.evidence, args.evidence_sha256))
    keys = load_trust(args.trust, args.trust_sha256)
    result = decide(request, packet, keys)
    if args.operation == 'checkpoint':
        need(args.checkpoint_root is not None, 'CHECKPOINT_ROOT_REQUIRED')
        result['checkpoint'] = checkpoint(args.checkpoint_root, request, result)
    else:
        need(args.checkpoint_root is None, 'ASSESS_HAS_NO_CHECKPOINT_WRITE')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    signal.signal(signal.SIGALRM, lambda unused_a, unused_b: sys.exit('RECOVERY_TIMEOUT_HOLD'))
    signal.alarm(30)
    try:
        main()
    except (Hold, OSError, ValueError, KeyError, sqlite3.Error,
            subprocess.SubprocessError) as exc:
        print(json.dumps({'state': 'HOLD', 'reason': str(exc) if type(exc) is Hold
                          else type(exc).__name__, 'authority_initialized': False,
                          'grant_registered': False, 'writer_started': False}))
        sys.exit(2)
