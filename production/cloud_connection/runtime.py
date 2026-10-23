"""Outbound connection loop and host-private custody; no public file fallback.

Enrollment is host-configured. This module does not grant installation rights.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import sqlite3
import stat
import time
import uuid

from .queue import Hold, Queue, TOKEN, canonical, decode
from .worker import Cloud, Github, Network, execute_ready, protected_read, query_existing, receive


class PrivateStore:
    """Fixed root, opaque per-request objects, no path from a remote request."""
    def __init__(self, root, owner=0, max_total=16 * 1024 * 1024):
        self.root = str(root)
        self.owner = owner
        self.max_total = max_total
        # Walk with directory descriptors: a symlink in any component is refused.
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in Path(root).parts[1:]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                s = os.fstat(fd)
                if s.st_uid != owner or s.st_mode & 0o022:
                    raise Hold('PRIVATE_PARENT')
            s = os.fstat(fd)
            if stat.S_IMODE(s.st_mode) != 0o700:
                raise Hold('PRIVATE_ROOT_MODE')
            self.fd = fd
        except BaseException:
            os.close(fd)
            raise

    def close(self):
        os.close(self.fd)

    def read(self, name):
        if type(name) is not str or not re.fullmatch(r'[0-9a-f]{64}\.bin', name):
            raise Hold('PRIVATE_OBJECT_NAME')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        with os.fdopen(fd, 'rb') as f:
            s = os.fstat(f.fileno())
            if (not stat.S_ISREG(s.st_mode) or s.st_uid != self.owner or s.st_nlink != 1
                    or stat.S_IMODE(s.st_mode) != 0o600 or s.st_size > 65536):
                raise Hold('PRIVATE_OBJECT_METADATA')
            before = (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            raw = f.read(65537)
            s = os.fstat(f.fileno())
            after = (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if len(raw) > 65536 or before != after:
                raise Hold('PRIVATE_OBJECT_CHANGED')
            return raw

    def put(self, request_id, data, digest):
        if (type(request_id) is not str or not TOKEN.fullmatch(request_id)
                or type(data) is not bytes or len(data) > 65536
                or hashlib.sha256(data).hexdigest() != digest):
            raise Hold('PRIVATE_OBJECT_INPUT')
        name = hashlib.sha256(request_id.encode()).hexdigest() + '.bin'
        try:
            old = self.read(name)
        except FileNotFoundError:
            old = None
        if old is not None:
            if old != data:
                raise Hold('PRIVATE_OBJECT_REBOUND')
            return 'server-private:' + name
        # Only worker-created regular files count; unexpected entries stop custody.
        total = 0
        for item in os.listdir(self.fd):
            s = os.stat(item, dir_fd=self.fd, follow_symlinks=False)
            if not stat.S_ISREG(s.st_mode) or s.st_uid != self.owner:
                raise Hold('PRIVATE_STORE_FOREIGN_ENTRY')
            total += s.st_size
        if total + len(data) > self.max_total:
            raise Hold('PRIVATE_STORE_QUOTA')
        tmp = '.pending-' + uuid.uuid4().hex
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(tmp, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
            except FileExistsError:
                if self.read(name) != data:
                    raise Hold('PRIVATE_OBJECT_REBOUND')
            os.unlink(tmp, dir_fd=self.fd)
            os.fsync(self.fd)
        except BaseException:
            # Preserve already-published objects; remove only our temporary name.
            try:
                os.unlink(tmp, dir_fd=self.fd)
            except FileNotFoundError:
                pass
            raise
        if self.read(name) != data:
            raise Hold('PRIVATE_OBJECT_VERIFY')
        return 'server-private:' + name


class Loop:
    def __init__(self, queue, github, cloud, store, expiry_watch=None):
        self.q, self.gh, self.cloud, self.store = queue, github, cloud, store
        # Host-only source contact point; main() does not enroll this candidate.
        self.expiry_watch = expiry_watch
        queue.db.executescript('''
          CREATE TABLE IF NOT EXISTS connection_cursor (id INTEGER PRIMARY KEY CHECK(id=1), since TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS connection_outbox (
            request_id TEXT PRIMARY KEY,
            body TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('READY','POSTING','SENT','UNKNOWN')),
            comment_id INTEGER);
        ''')

    def ingest(self, now):
        cursor = self.q.db.execute('SELECT since FROM connection_cursor WHERE id=1').fetchone()
        # Advance to the beginning of the fetch, with overlap; dedup is in SQLite.
        since = cursor[0] if cursor else datetime.datetime.fromtimestamp(now - 86400, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        next_since = datetime.datetime.fromtimestamp(now - 60, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        outcomes = receive(self.gh, self.q, since, now)
        self.q.db.execute('BEGIN IMMEDIATE')
        try:
            changed = self.q.db.execute('UPDATE connection_cursor SET since=? WHERE id=1', (next_since,))
            if not changed.rowcount:
                self.q.db.execute('INSERT INTO connection_cursor VALUES(1,?)', (next_since,))
            self.q.db.execute('COMMIT')
        except BaseException:
            if self.q.db.in_transaction:
                self.q.db.execute('ROLLBACK')
            raise
        return outcomes

    def tick(self, now):
        if self.expiry_watch is not None:
            from .credential_lifecycle import record_on_existing_queue
            raw, approved_sha = self.expiry_watch
            result = record_on_existing_queue(self.q.db, raw, approved_sha, now)
            if result['state'] == 'STOP_EXPIRED_OR_CONSERVATIVE_BOUND':
                self.flush()
                raise Hold('CREDENTIAL_EXPIRY_STOP')
        self.ingest(now)
        rows = self.q.db.execute('SELECT request_id,state,invoke_id FROM connection_jobs ORDER BY rowid').fetchall()
        for rid, state, invoke in rows:
            try:
                if state == 'READY':
                    execute_ready(self.q, self.cloud, rid, now)
                elif state == 'DISPATCHING' and not invoke:
                    # Crash after durable intent: never infer that dispatch did not happen.
                    self.q.unknown(rid)
                status = self.q.inspect(rid)
                if status['state'] in ('DISPATCHING', 'UNKNOWN') and status['invoke_id']:
                    query_existing(self.q, self.cloud, rid, self.store.put)
            except (Hold, OSError, sqlite3.Error, KeyError, TypeError, ValueError):
                # Only query an existing invoke on the next tick; do not redispatch.
                self.q.unknown(rid)
            status = self.q.inspect(rid)
            if status['state'] != 'READY':
                # Metadata only; never publish private file bytes or arbitrary cloud output.
                public = {'schema': 1, 'request_id': rid, 'state': status['state'],
                          'invoke_id': status['invoke_id'], 'private_file_delivery': 'NOT_DELIVERED'}
                body = 'XJ_CLOUD_RESULT_V1\n' + canonical(public)
                # One initial acknowledgement, plus a separate terminal result key.
                key = rid + ('.terminal' if status['state'] in ('SUCCESS', 'FAILED') else '.observed')
                self.q.db.execute('INSERT OR IGNORE INTO connection_outbox VALUES(?,?,?,NULL)', (key, body, 'READY'))
        self.flush()

    def flush(self):
        for key, body in self.q.db.execute("SELECT request_id,body FROM connection_outbox WHERE state='READY'").fetchall():
            self.q.db.execute("UPDATE connection_outbox SET state='POSTING' WHERE request_id=? AND state='READY'", (key,))
            try:
                result = self.gh.call('/issues/17/comments', {'body': body})
                if type(result.get('id')) is not int:
                    raise Hold('COMMENT_WRITE_RESULT')
                self.q.db.execute("UPDATE connection_outbox SET state='SENT',comment_id=? WHERE request_id=?", (result['id'], key))
            except (Hold, OSError, ValueError, KeyError, TypeError):
                self.q.db.execute("UPDATE connection_outbox SET state='UNKNOWN' WHERE request_id=?", (key,))
                # No blind duplicate POST when GitHub may have accepted the write.


def code_pin(directory):
    records = []
    for name in ('queue.py', 'worker.py', 'runtime.py', 'private_transfer.py', 'credential_lifecycle.py', 'fixed_actions.py', 'pr122_baseline_collector.py'):
        raw = (Path(directory) / name).read_bytes()
        records.append([name, hashlib.sha256(raw).hexdigest()])
    return hashlib.sha256(canonical(records).encode()).hexdigest()


def optional_hooks(config, source_directory):
    """Only root host config selects candidates; no request can enable them."""
    expiry, actions = None, None
    for key, filename in (('expiry_watch', 'tunnel-expiry.json'),
                          ('website_baseline', 'website-baseline-binding.json')):
        if key not in config:
            continue
        entry = config[key]
        if (type(entry) is not dict or set(entry) != {'metadata_ref', 'metadata_sha256'}
                or entry['metadata_ref'] != '/etc/xuanjun-cloud-executor/' + filename):
            raise Hold('OPTIONAL_HOST_CONFIG_SCOPE')
        raw = protected_read(entry['metadata_ref'], 16384)
        if (type(entry['metadata_sha256']) is not str or
                hashlib.sha256(raw).hexdigest() != entry['metadata_sha256']):
            raise Hold('OPTIONAL_HOST_CONFIG_SHA')
        if key == 'expiry_watch':
            expiry = (raw, entry['metadata_sha256'])
        else:
            from .fixed_actions import WebsiteBaselinePolicy
            source = (Path(source_directory) / 'pr122_baseline_collector.py').read_bytes()
            actions = WebsiteBaselinePolicy(source, raw, entry['metadata_sha256'])
    return expiry, actions


def approved_object_hook(config):
    """Absent by default. Only protected host config enrolls this operation."""
    if 'approved_objects' not in config:
        return None
    entry = config['approved_objects']
    if (type(entry) is not dict or set(entry) != {'metadata_ref', 'metadata_sha256'}
            or entry['metadata_ref'] != '/etc/xuanjun-cloud-executor/approved-objects-binding.json'):
        raise Hold('APPROVED_OBJECT_HOST_SCOPE')
    from .fixed_actions import ApprovedObjectsPolicy
    raw = protected_read(entry['metadata_ref'], 16384)
    return ApprovedObjectsPolicy(raw, entry['metadata_sha256'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    config = decode(protected_read(args.config, 16384).decode())
    if os.geteuid() != 0:
        raise Hold('ENROLLED_ROOT_SERVICE_ONLY')
    fields = {'executor_sha256', 'allowed_actor_ids', 'github_token_ref', 'github_token_owner',
              'credentials_ref', 'state_root', 'poll_seconds'}
    if (not fields <= set(config) or set(config) - fields - {'expiry_watch', 'website_baseline', 'approved_objects'}
            or code_pin(Path(__file__).parent) != config['executor_sha256']):
        raise Hold('HOST_CONFIG_OR_CODE_PIN')
    if (config['allowed_actor_ids'] != [332398908] or config['github_token_owner'] != 1003
            or config['github_token_ref'] != '/etc/xuanjun-development/github-intake-token'
            or config['credentials_ref'] != '/etc/xuanjun-cloud-executor/credentials.json'
            or config['state_root'] != '/var/lib/xuanjun-cloud-connection'
            or type(config['poll_seconds']) is not int or not 15 <= config['poll_seconds'] <= 300):
        raise Hold('HOST_ENROLLMENT_SCOPE')
    expiry_watch, project_actions = optional_hooks(config, Path(__file__).parent)
    approved_objects = approved_object_hook(config)
    root = config['state_root']
    store = PrivateStore(root + '/private-results')
    lockfd = os.open(root + '/worker.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    ls = os.fstat(lockfd)
    if not stat.S_ISREG(ls.st_mode) or ls.st_uid != 0 or ls.st_nlink != 1 or stat.S_IMODE(ls.st_mode) != 0o600:
        raise Hold('LOCK_METADATA')
    fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    q = Queue(root + '/queue.sqlite', config['executor_sha256'], config['allowed_actor_ids'], project_actions=project_actions, approved_objects=approved_objects)
    network = Network()
    loop = Loop(q, Github(config['github_token_ref'], network, config['github_token_owner']),
                Cloud(config['credentials_ref'], network), store, expiry_watch=expiry_watch)
    # Interrupted POST is uncertain; never replay it after restart.
    q.db.execute("UPDATE connection_outbox SET state='UNKNOWN' WHERE state='POSTING'")
    stopping = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda signum, frame: stopping.append(signum))
    try:
        while not stopping:
            try:
                loop.tick(int(time.time()))
            except (Hold, OSError, sqlite3.Error, ValueError):
                print('CONNECTION_TICK_HOLD', flush=True)
            if args.once:
                break
            for _ in range(config['poll_seconds']):
                if stopping:
                    break
                time.sleep(1)
    finally:
        q.close()
        store.close()
        os.close(lockfd)


if __name__ == '__main__':
    main()
