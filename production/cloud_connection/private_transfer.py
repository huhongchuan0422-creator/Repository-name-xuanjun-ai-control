"""Approved object transfer, not arbitrary file access or a new dispatcher.

The host supplies the approved catalog digest, protected roots, authenticated
recipient and the EXISTING connection Queue database. None comes from MCP
arguments. This module is deliberately not enrolled in the current OS-only MCP.
"""
import base64
import hashlib
import json
import os
import re
import stat
import time
import uuid

from .queue import Hold, SHA, TOKEN, canonical, unique

CHUNK = 65536
MAX_OBJECT = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
PART = re.compile(r'[A-Za-z0-9_@][A-Za-z0-9_.@+-]{0,127}\Z')


def check(value, reason):
    if not value:
        raise Hold(reason)


def strict(raw):
    check(type(raw) is bytes and len(raw) <= 131072, 'CATALOG_BOUND')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Hold('NONFINITE')))
    except (ValueError, UnicodeError):
        raise Hold('CATALOG_JSON') from None


class Catalog:
    def __init__(self, raw, approved_sha, project_policy):
        check(type(raw) is bytes and len(raw) <= 131072 and type(approved_sha) is str and SHA.fullmatch(approved_sha)
              and hashlib.sha256(raw).hexdigest() == approved_sha, 'CATALOG_APPROVAL_BINDING')
        v = strict(raw)
        check(type(v) is dict and set(v) == {'schema', 'project', 'approval_ref',
              'source_commit', 'executor_sha256', 'target', 'valid_from', 'valid_until',
              'recipients', 'objects'}, 'CATALOG_FIELDS')
        check(type(v['schema']) is int and v['schema'] == 1, 'CATALOG_SCHEMA')
        for key in ('project', 'approval_ref'):
            check(type(v[key]) is str and TOKEN.fullmatch(v[key]), 'CATALOG_ID')
        policy = project_policy
        check(type(policy) is dict and set(policy) == {'project', 'max_objects', 'max_object_bytes',
              'max_total_bytes', 'recipients', 'root_refs'} and v['project'] == policy['project'], 'ENROLLED_PROJECT_REQUIRED')
        for key, cap in [('max_objects', 64), ('max_object_bytes', MAX_OBJECT), ('max_total_bytes', MAX_TOTAL)]:
            check(type(policy[key]) is int and 0 < policy[key] <= cap, 'PROJECT_BUDGET')
        for key in ('recipients', 'root_refs'):
            check(type(policy[key]) is list and 1 <= len(policy[key]) <= 64 and
                  all(type(x) is str and TOKEN.fullmatch(x) for x in policy[key]), 'PROJECT_SCOPE')
        check(type(v['source_commit']) is str and re.fullmatch(r'[0-9a-f]{40}', v['source_commit']), 'SOURCE_COMMIT')
        check(type(v['executor_sha256']) is str and SHA.fullmatch(v['executor_sha256']), 'EXECUTOR_PIN')
        check(v['target'] in ('uk', 'korea', 'domestic'), 'CATALOG_TARGET')
        check(type(v['valid_from']) is int and type(v['valid_until']) is int
              and 0 < v['valid_until'] - v['valid_from'] <= 30 * 86400, 'CATALOG_WINDOW')
        r = v['recipients']
        check(type(r) is list and 1 <= len(r) <= 8 and all(type(x) is str and TOKEN.fullmatch(x) for x in r)
              and len(set(r)) == len(r), 'RECIPIENTS')
        check(set(r) <= set(policy['recipients']), 'PROJECT_RECIPIENT_SCOPE')
        objects = v['objects']
        check(type(objects) is list and 1 <= len(objects) <= policy['max_objects'], 'OBJECT_COUNT')
        self.objects = {}
        total = 0
        paths = set()
        for item in objects:
            check(type(item) is dict and set(item) == {'ref', 'root_ref', 'relative_path', 'bytes', 'sha256'}, 'OBJECT_FIELDS')
            for k in ('ref', 'root_ref'):
                check(type(item[k]) is str and TOKEN.fullmatch(item[k]), 'OBJECT_REF')
            check(item['root_ref'] in policy['root_refs'], 'PROJECT_ROOT_SCOPE')
            path = item['relative_path']
            check(type(path) is str and len(path) <= 2048 and 1 <= len(path.split('/')) <= 16
                  and all(PART.fullmatch(x) and x not in ('.', '..') for x in path.split('/')), 'OBJECT_PATH')
            check(type(item['bytes']) is int and 0 <= item['bytes'] <= policy['max_object_bytes'], 'OBJECT_SIZE')
            check(type(item['sha256']) is str and SHA.fullmatch(item['sha256']), 'OBJECT_SHA')
            key = (item['root_ref'], path)
            check(item['ref'] not in self.objects and key not in paths, 'OBJECT_ALIAS_OR_DUPLICATE')
            self.objects[item['ref']] = dict(item)
            paths.add(key)
            total += item['bytes']
        check(total <= policy['max_total_bytes'], 'CATALOG_TOTAL')
        self.value, self.sha = v, approved_sha

    def object(self, ref, authenticated_recipient, now):
        check(type(authenticated_recipient) is str and authenticated_recipient in self.value['recipients'], 'AUTHENTICATED_RECIPIENT_REQUIRED')
        check(type(now) is int and self.value['valid_from'] <= now < self.value['valid_until'], 'CATALOG_EXPIRED')
        check(type(ref) is str and ref in self.objects, 'OBJECT_NOT_APPROVED')
        return self.objects[ref]


def stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def directory(path, owner, private=False):
    check(type(path) is str and path.startswith('/') and os.path.normpath(path) == path, 'ROOT_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.split('/')[1:]:
            if not part:
                continue
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
            s = os.fstat(fd)
            check(s.st_uid in (0, owner) and not s.st_mode & 0o022, 'ROOT_PARENT')
        s = os.fstat(fd)
        check(s.st_uid == owner and (not private or stat.S_IMODE(s.st_mode) == 0o700), 'ROOT_METADATA')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_object(root, owner, item):
    """Descriptor walk, bounded regular file, full SHA, root/parents rechecked."""
    rootfd = directory(root, owner)
    fd = os.dup(rootfd)
    chain = []
    try:
        parts = item['relative_path'].split('/')
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            s = os.fstat(nxt)
            check(s.st_uid == owner and not s.st_mode & 0o022, 'SOURCE_PARENT')
            chain.append((part, s.st_dev, s.st_ino))
            os.close(fd)
            fd = nxt
        filefd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(filefd)
            check(stat.S_ISREG(before.st_mode) and before.st_uid == owner and before.st_nlink == 1
                  and not before.st_mode & 0o022 and before.st_size == item['bytes'], 'SOURCE_METADATA')
            data, deadline = bytearray(), time.monotonic() + 30
            while len(data) <= item['bytes']:
                check(time.monotonic() < deadline, 'SOURCE_TIMEOUT')
                block = os.read(filefd, min(CHUNK, item['bytes'] + 1 - len(data)))
                if not block:
                    break
                data.extend(block)
            check(stamp(before) == stamp(os.fstat(filefd))
                  and stamp(before) == stamp(os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)), 'SOURCE_CHANGED')
        finally:
            os.close(filefd)
        current = directory(root, owner)
        try:
            check((os.fstat(current).st_dev, os.fstat(current).st_ino) ==
                  (os.fstat(rootfd).st_dev, os.fstat(rootfd).st_ino), 'SOURCE_ROOT_MOVED')
            for part, dev, ino in chain:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                os.close(current)
                current = nxt
                check((os.fstat(current).st_dev, os.fstat(current).st_ino) == (dev, ino), 'SOURCE_PARENT_MOVED')
                check(os.fstat(current).st_uid == owner and not os.fstat(current).st_mode & 0o022, 'SOURCE_PARENT')
        finally:
            os.close(current)
        data = bytes(data)
        check(len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'], 'SOURCE_SHA')
        return data
    finally:
        os.close(fd)
        os.close(rootfd)


def bound_job(db, catalog, request_id, ref, recipient):
    check(type(request_id) is str and TOKEN.fullmatch(request_id), 'ORIGINAL_JOB_ID')
    row = db.execute('SELECT project,request_json,state,invoke_id,actor_id,receipt_json FROM connection_jobs WHERE request_id=?', (request_id,)).fetchone()
    check(row is not None and row[0] == catalog.value['project'] and row[2] == 'SUCCESS'
          and row[3] and row[4] == 332398908, 'ORIGINAL_JOB_NOT_SUCCESS')
    check(type(row[1]) is str and type(row[5]) is str, 'ORIGINAL_JOB_CORRUPT')
    r = strict(row[1].encode())
    check(type(r) is dict and r.get('request_id') == request_id and r.get('project') == row[0]
          and r.get('target') == catalog.value['target']
          and r.get('executor_sha256') == catalog.value['executor_sha256']
          and r.get('operation') == 'fetch_approved_object'
          and r.get('arguments') == {'manifest_sha256': catalog.sha, 'object_ref': ref, 'recipient_id': recipient}, 'ORIGINAL_JOB_SCOPE')
    receipt = strict(row[5].encode())
    item = catalog.objects[ref]
    expected = {'state': 'SUCCESS', 'invoke_id': row[3], 'target': catalog.value['target'],
                'manifest_sha256': catalog.sha, 'object_ref': ref, 'recipient_id': recipient,
                'bytes': item['bytes'], 'sha256': item['sha256']}
    check(type(receipt) is dict and all(receipt.get(k) == v for k, v in expected.items()), 'ORIGINAL_RECEIPT_BINDING')
    return row[3]


def export_chunk(db, catalog, roots, request_id, ref, authenticated_recipient, offset, now):
    item = catalog.object(ref, authenticated_recipient, now)
    invoke = bound_job(db, catalog, request_id, ref, authenticated_recipient)
    check(type(offset) is int and 0 <= offset <= item['bytes'] and offset % CHUNK == 0, 'CHUNK_OFFSET')
    check(item['root_ref'] in roots, 'ROOT_NOT_ENROLLED')
    root, owner = roots[item['root_ref']]
    raw = read_object(root, owner, item)
    block = raw[offset:offset + CHUNK]
    return {'manifest_sha256': catalog.sha, 'project': catalog.value['project'], 'request_id': request_id,
            'object_ref': ref, 'recipient_id': authenticated_recipient, 'invoke_id': invoke,
            'bytes': item['bytes'], 'sha256': item['sha256'], 'offset': offset,
            'chunk_sha256': hashlib.sha256(block).hexdigest(), 'data': base64.b64encode(block).decode('ascii')}


class Receiver:
    """Uses extension tables on the caller's original Queue connection, never a new DB.

    Write-before-COMMIT interruptions preserve the partial file. Reconcile may
    adopt only a complete, exact-SHA object; it never truncates uncertain bytes.
    """
    def __init__(self, db, destination_root, catalog, authenticated_recipient, owner=0):
        self.db, self.root, self.catalog, self.recipient, self.owner = db, destination_root, catalog, authenticated_recipient, owner
        self.fd = directory(destination_root, owner, private=True)
        entered = False
        try:
            self.begin()
            entered = True
            db.execute('SELECT request_id FROM connection_jobs LIMIT 1')
            db.execute('CREATE TABLE IF NOT EXISTS connection_file_delivery (id TEXT PRIMARY KEY, binding TEXT NOT NULL, offset INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN (\'PARTIAL\',\'SUCCESS\')))')
            db.execute('CREATE TABLE IF NOT EXISTS connection_file_events (delivery_id TEXT NOT NULL, offset INTEGER NOT NULL, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(delivery_id,offset))')
            db.execute('CREATE TABLE IF NOT EXISTS connection_file_failures (event_id TEXT PRIMARY KEY, delivery_id TEXT NOT NULL, observed INTEGER NOT NULL, code TEXT NOT NULL)')
            for table, identity in [('connection_file_delivery', 'id'), ('connection_file_events', 'delivery_id,offset')]:
                condition = ' AND '.join(k + '=NEW.' + k for k in identity.split(','))
                db.execute('CREATE TRIGGER IF NOT EXISTS '+table+'_no_replace BEFORE INSERT ON '+table+' WHEN EXISTS(SELECT 1 FROM '+table+' WHERE '+condition+") BEGIN SELECT RAISE(ABORT,'IMMUTABLE_DELIVERY'); END")
                db.execute('CREATE TRIGGER IF NOT EXISTS '+table+'_no_delete BEFORE DELETE ON '+table+" BEGIN SELECT RAISE(ABORT,'IMMUTABLE_DELIVERY'); END")
                columns = 'binding,id' if table.endswith('delivery') else 'delivery_id,offset,bytes,sha256'
                db.execute('CREATE TRIGGER IF NOT EXISTS '+table+'_no_rebind BEFORE UPDATE OF '+columns+' ON '+table+" BEGIN SELECT RAISE(ABORT,'IMMUTABLE_DELIVERY'); END")
            db.execute('CREATE TRIGGER IF NOT EXISTS connection_failure_no_replace BEFORE INSERT ON connection_file_failures '
                       'WHEN EXISTS(SELECT 1 FROM connection_file_failures WHERE event_id=NEW.event_id) '
                       "BEGIN SELECT RAISE(ABORT,'IMMUTABLE_DELIVERY'); END")
            for verb in ('UPDATE', 'DELETE'):
                db.execute('CREATE TRIGGER IF NOT EXISTS connection_failure_no_'+verb.lower()+' BEFORE '+verb+
                           " ON connection_file_failures BEGIN SELECT RAISE(ABORT,'IMMUTABLE_DELIVERY'); END")
            db.commit()
        except BaseException:
            try:
                if entered and db.in_transaction:
                    db.rollback()
            finally:
                os.close(self.fd)
            raise

    def close(self):
        os.close(self.fd)

    def begin(self):
        check(not self.db.in_transaction, 'CALLER_TRANSACTION_ACTIVE')
        self.db.execute('BEGIN IMMEDIATE')

    def check_root(self):
        current = directory(self.root, self.owner, private=True)
        try:
            check((os.fstat(current).st_dev, os.fstat(current).st_ino) ==
                  (os.fstat(self.fd).st_dev, os.fstat(self.fd).st_ino), 'RECEIVER_ROOT_MOVED')
        finally:
            os.close(current)

    def binding(self, request_id, ref, now):
        item = self.catalog.object(ref, self.recipient, now)
        invoke = bound_job(self.db, self.catalog, request_id, ref, self.recipient)
        v = {'manifest_sha256': self.catalog.sha, 'project': self.catalog.value['project'],
             'request_id': request_id, 'object_ref': ref, 'recipient_id': self.recipient,
             'invoke_id': invoke, 'bytes': item['bytes'], 'sha256': item['sha256']}
        body = canonical(v)
        return item, v, body, hashlib.sha256(body.encode()).hexdigest()

    def record_failure(self, ident, now, error):
        """Best effort on ORIGINAL DB only; unavailable audit never means PASS."""
        recorded = False
        try:
            self.begin()
            check(self.db.execute('SELECT COUNT(*) FROM connection_file_failures').fetchone()[0] < 4096, 'FAILURE_AUDIT_BOUND')
            code = str(error) if isinstance(error, Hold) else type(error).__name__
            if not re.fullmatch(r'[A-Za-z0-9_]{1,80}', code):
                code = 'TRANSFER_HOLD'
            self.db.execute('INSERT INTO connection_file_failures VALUES(?,?,?,?)',
                            (uuid.uuid4().hex, ident or 'UNBOUND', now, code))
            self.db.commit()
            recorded = True
        except BaseException:
            if self.db.in_transaction:
                try:
                    self.db.rollback()
                except BaseException:
                    pass
        error.failure_audit_recorded = recorded

    def rollback_or_unknown(self, error):
        if self.db.in_transaction:
            try:
                self.db.rollback()
            except BaseException:
                unknown = Hold('TRANSFER_ROLLBACK_FAILED_UNKNOWN')
                unknown.failure_audit_recorded = False
                raise unknown from error

    def open_file(self, name, create=False, paired=None):
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        fd = os.open(name, flags, 0o600, dir_fd=self.fd)
        try:
            s = os.fstat(fd)
            links_ok = s.st_nlink == 1
            if paired and s.st_nlink == 2:
                other = os.stat(paired, dir_fd=self.fd, follow_symlinks=False)
                links_ok = (s.st_dev, s.st_ino) == (other.st_dev, other.st_ino)
            check(stat.S_ISREG(s.st_mode) and s.st_uid == self.owner and links_ok
                  and stat.S_IMODE(s.st_mode) == 0o600, 'RECEIVER_METADATA')
        except BaseException:
            os.close(fd)
            raise
        return fd

    def check_quota(self, added):
        # Only this pre-enrolled private custody root is inspected, never a
        # project tree or filesystem search. Refuse foreign entries and stop.
        names = os.listdir(self.fd)
        check(len(names) <= 4096, 'RECEIVER_OBJECT_COUNT')
        total = 0
        for name in names:
            check(re.fullmatch(r'[0-9a-f]{64}\.(partial|bin)', name), 'RECEIVER_FOREIGN_ENTRY')
            s = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            check(stat.S_ISREG(s.st_mode) and s.st_uid == self.owner
                  and stat.S_IMODE(s.st_mode) == 0o600, 'RECEIVER_FOREIGN_ENTRY')
            total += s.st_size
        check(total + added <= 2 * MAX_TOTAL, 'RECEIVER_QUOTA')

    def accept(self, envelope, now):
        check(type(envelope) is dict and set(envelope) == {'manifest_sha256', 'project', 'request_id', 'object_ref',
              'recipient_id', 'invoke_id', 'bytes', 'sha256', 'offset', 'chunk_sha256', 'data'}, 'ENVELOPE_FIELDS')
        check(type(envelope['data']) is str and len(envelope['data']) <= 4 * ((CHUNK + 2) // 3), 'CHUNK_BOUND')
        try:
            block = base64.b64decode(envelope['data'].encode('ascii'), validate=True)
        except (ValueError, UnicodeError):
            raise Hold('CHUNK_ENCODING') from None
        check(type(envelope['offset']) is int and 0 <= envelope['offset'] <= MAX_OBJECT
              and envelope['offset'] % CHUNK == 0 and len(block) <= CHUNK
              and hashlib.sha256(block).hexdigest() == envelope['chunk_sha256'], 'CHUNK_SHA')
        self.begin()
        fd = None
        ident = None
        try:
            self.check_root()
            item, binding, body, ident = self.binding(envelope['request_id'], envelope['object_ref'], now)
            check(all(envelope[k] == v for k, v in binding.items()), 'ENVELOPE_BINDING')
            row = self.db.execute('SELECT binding,offset,state FROM connection_file_delivery WHERE id=?', (ident,)).fetchone()
            if row is None:
                check(envelope['offset'] == 0, 'FIRST_CHUNK')
                self.db.execute("INSERT INTO connection_file_delivery VALUES(?,?,0,'PARTIAL')", (ident, body))
                fd = self.open_file(ident + '.partial', create=True)
                os.fsync(self.fd)
                offset, state = 0, 'PARTIAL'
            else:
                check(row[0] == body, 'DELIVERY_REBOUND')
                offset, state = row[1:]
                fd = self.open_file(ident + ('.bin' if state == 'SUCCESS' else '.partial'))
            check(os.fstat(fd).st_size == offset, 'UNKNOWN_PARTIAL_WRITE_RECONCILE')
            pos = envelope['offset']
            if pos < offset or state == 'SUCCESS':
                old = self.db.execute('SELECT bytes,sha256 FROM connection_file_events WHERE delivery_id=? AND offset=?', (ident, pos)).fetchone()
                check(old == (len(block), envelope['chunk_sha256']) and os.pread(fd, len(block), pos) == block, 'REPLAY_MISMATCH')
            else:
                check(pos == offset and (len(block) > 0 or item['bytes'] == 0)
                      and pos + len(block) <= item['bytes'] and (len(block) == CHUNK or pos + len(block) == item['bytes']), 'CHUNK_ORDER')
                self.check_quota(len(block))
                written = 0
                while written < len(block):
                    n = os.pwrite(fd, block[written:], pos + written)
                    check(n > 0, 'SHORT_WRITE')
                    written += n
                os.fsync(fd)
                self.db.execute('INSERT INTO connection_file_events VALUES(?,?,?,?)', (ident, pos, len(block), envelope['chunk_sha256']))
                self.db.execute('UPDATE connection_file_delivery SET offset=? WHERE id=?', (pos + len(block), ident))
            self.check_root()
            self.db.commit()
        except BaseException as error:
            self.rollback_or_unknown(error)
            # Never erase partial bytes when the write/commit result is uncertain.
            self.record_failure(ident, now, error)
            raise
        finally:
            if fd is not None:
                os.close(fd)
        return self.reconcile(envelope['request_id'], envelope['object_ref'], now)

    def reconcile(self, request_id, ref, now):
        self.begin()
        ident = None
        try:
            self.check_root()
            item, binding, body, ident = self.binding(request_id, ref, now)
            row = self.db.execute('SELECT binding,offset,state FROM connection_file_delivery WHERE id=?', (ident,)).fetchone()
            check(row is not None and row[0] == body, 'DELIVERY_NOT_FOUND')
            partial, final = ident + '.partial', ident + '.bin'
            try:
                fd = self.open_file(final, paired=partial)
                published = True
            except FileNotFoundError:
                fd = self.open_file(partial)
                published = False
            try:
                before = os.fstat(fd)
                size = before.st_size
                if size < item['bytes']:
                    check(not published and size == row[1] and row[2] == 'PARTIAL', 'UNKNOWN_PARTIAL_WRITE_RECONCILE')
                    self.db.commit()
                    return dict(binding, state='PARTIAL', received_bytes=size)
                check(size == item['bytes'], 'RECEIVER_SIZE')
                digest, offset = hashlib.sha256(), 0
                while offset < size:
                    b = os.pread(fd, min(CHUNK, size - offset), offset)
                    check(b, 'RECEIVER_SHORT_READ')
                    digest.update(b)
                    offset += len(b)
                check(digest.hexdigest() == item['sha256'], 'RECEIVER_SHA')
                check(stamp(before) == stamp(os.fstat(fd)) and stamp(before) ==
                      stamp(os.stat(final if published else partial, dir_fd=self.fd, follow_symlinks=False)), 'RECEIVER_CHANGED')
            finally:
                os.close(fd)
            if not published:
                # Hard-link publication is exclusive; existing destinations are not overwritten.
                os.link(partial, final, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
                os.unlink(partial, dir_fd=self.fd)
                os.fsync(self.fd)
            elif before.st_nlink == 2:
                # Both exact names refer to the verified inode; finish only our
                # interrupted publication, never unlink an unrelated file.
                os.unlink(partial, dir_fd=self.fd)
                os.fsync(self.fd)
            self.check_root()
            proof = self.db.execute('SELECT bytes,sha256 FROM connection_file_events WHERE delivery_id=? AND offset=-1', (ident,)).fetchone()
            if proof is None:
                # Final whole-object proof, not a claim that lost chunk COMMITs
                # happened. Negative offset is reserved and cannot be received.
                self.db.execute('INSERT INTO connection_file_events VALUES(?,-1,?,?)', (ident, size, item['sha256']))
            else:
                check(proof == (size, item['sha256']), 'FINAL_PROOF_REBOUND')
            self.db.execute("UPDATE connection_file_delivery SET offset=?,state='SUCCESS' WHERE id=?", (size, ident))
            self.db.commit()
            return dict(binding, state='SUCCESS', received_bytes=size, private_ref=ident + '.bin')
        except BaseException as error:
            self.rollback_or_unknown(error)
            self.record_failure(ident, now, error)
            raise
