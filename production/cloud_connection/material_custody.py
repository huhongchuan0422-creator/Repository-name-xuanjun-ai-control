"""Default-off local custody bridge; original Queue and Receiver, no transport.

Only an already enrolled policy and real successful object jobs may enter.
No source approval, root creation, cloud dispatch, credential or SDK execution.
"""
import base64
import hashlib
import json
import os
import sqlite3
import stat
import time
from .queue import Hold, canonical, decode
from .private_transfer import (CHUNK, Receiver, bound_job, check, directory,
                               read_object, stamp)


def delivery_binding(db, catalog, request_id, ref, recipient, now):
    item = catalog.object(ref, recipient, now)
    invoke = bound_job(db, catalog, request_id, ref, recipient)
    binding = {'manifest_sha256': catalog.sha, 'project': catalog.value['project'],
               'request_id': request_id, 'object_ref': ref, 'recipient_id': recipient,
               'invoke_id': invoke, 'bytes': item['bytes'], 'sha256': item['sha256']}
    body = canonical(binding)
    return item, binding, body, hashlib.sha256(body.encode()).hexdigest()


def ingest_approved_batch(db, policy, destination_root, destination_owner, now,
                          enabled=False, clock=time.time):
    check(enabled is True, 'MATERIAL_CUSTODY_DISABLED')
    check(type(now) is int, 'MATERIAL_CUSTODY_CLOCK')
    requests = {}
    # Check the whole approved set before creating Receiver audit tables or
    # reading any source. Never create/upgrade a job to SUCCESS here.
    for ref, request_id in policy.binding['requests'].items():
        bound_job(db, policy.catalog, request_id, ref, policy.binding['recipient_id'])
        row = db.execute('SELECT request_json,receipt_json FROM connection_jobs WHERE request_id=?', (request_id,)).fetchone()
        request = decode(row[0])
        receipt = decode(row[1])
        check(type(receipt) is dict and receipt.get('action_binding_sha256') == policy.sha, 'CUSTODY_POLICY_RECEIPT_BINDING')
        policy.validate(request, 332398908, now)
        requests[ref] = request
    completed = []
    receiver = Receiver(db, destination_root, policy.catalog, policy.binding['recipient_id'], destination_owner)
    try:
        pending = {}
        # Resolve all pre-existing deliveries before source I/O; an uncertain
        # partial is not permission to re-read or overwrite the object.
        for ref in sorted(requests):
            current = int(clock())
            check(current >= now, 'MATERIAL_CUSTODY_CLOCK')
            request = requests[ref]
            policy.validate(request, 332398908, current)
            item, binding, body, ident = delivery_binding(db, policy.catalog, request['request_id'], ref, policy.binding['recipient_id'], current)
            existing = db.execute('SELECT state FROM connection_file_delivery WHERE id=?', (ident,)).fetchone()
            if existing is not None:
                prior = receiver.reconcile(request['request_id'], ref, current)
                if prior['state'] == 'SUCCESS':
                    completed.append(prior)
                    continue
                raise Hold('CUSTODY_PARTIAL_REQUIRES_REVIEW')
            pending[ref] = item
        cache = {}
        for ref in sorted(pending):
            current = int(clock())
            check(current >= now, 'MATERIAL_CUSTODY_CLOCK')
            request, item = requests[ref], pending[ref]
            policy.validate(request, 332398908, current)
            if item['root_ref'] in policy.binding.get('archives', {}):
                if ref not in cache:
                    group = [x for x in pending.values() if x['root_ref'] == item['root_ref']]
                    for x in group: policy.validate(requests[x['ref']], 332398908, current)
                    loaded = policy.read_archive_group(group)
                    after = int(clock())
                    check(after >= current, 'MATERIAL_CUSTODY_CLOCK')
                    for x in group: policy.validate(requests[x['ref']], 332398908, after)
                    cache.update(loaded)
                raw = cache.pop(ref)
            else:
                raw = policy.read_source(item)
            current = int(clock())
            check(current >= now, 'MATERIAL_CUSTODY_CLOCK')
            policy.validate(request, 332398908, current)
            item, binding, body, ident = delivery_binding(db, policy.catalog, request['request_id'], ref, policy.binding['recipient_id'], current)
            check(len(raw) <= CHUNK, 'MATERIAL_CUSTODY_SINGLE_CHUNK')
            envelope = dict(binding, offset=0, chunk_sha256=hashlib.sha256(raw).hexdigest(),
                            data=base64.b64encode(raw).decode('ascii'))
            completed.append(receiver.accept(envelope, current))
        return {'state': 'MATERIAL_CUSTODY_COMPLETE', 'objects': len(completed),
                'bytes': sum(x['received_bytes'] for x in completed), 'catalog_sha256': policy.catalog.sha,
                'analyst_receipt': 'NOT_VERIFIED', 'source_execution': False}
    finally:
        receiver.close()


def read_received_chunk(db, catalog, destination_root, destination_owner,
                        request_id, ref, recipient, offset, now, enabled=False):
    check(enabled is True, 'MATERIAL_CUSTODY_READ_DISABLED')
    item, binding, body, ident = delivery_binding(db, catalog, request_id, ref, recipient, now)
    check(type(offset) is int and 0 <= offset <= item['bytes'] and offset % CHUNK == 0, 'CHUNK_OFFSET')
    row = db.execute('SELECT binding,offset,state FROM connection_file_delivery WHERE id=?', (ident,)).fetchone()
    check(row == (body, item['bytes'], 'SUCCESS'), 'CUSTODY_NOT_COMPLETE')
    proof = db.execute('SELECT bytes,sha256 FROM connection_file_events WHERE delivery_id=? AND offset=-1', (ident,)).fetchone()
    check(proof == (item['bytes'], item['sha256']), 'CUSTODY_FINAL_PROOF')
    rootfd = directory(destination_root, destination_owner, private=True)
    try:
        before = stamp(os.fstat(rootfd))
        filemeta = os.stat(ident + '.bin', dir_fd=rootfd, follow_symlinks=False)
        check(stat.S_ISREG(filemeta.st_mode) and stat.S_IMODE(filemeta.st_mode) == 0o600
              and filemeta.st_uid == destination_owner and filemeta.st_nlink == 1, 'CUSTODY_FILE_METADATA')
        stored = dict(item, relative_path=ident + '.bin')
        raw = read_object(destination_root, destination_owner, stored)
        check(stamp(filemeta) == stamp(os.stat(ident + '.bin', dir_fd=rootfd, follow_symlinks=False)), 'CUSTODY_FILE_CHANGED')
        current = directory(destination_root, destination_owner, private=True)
        try:
            check(stamp(os.fstat(current)) == before, 'CUSTODY_ROOT_CHANGED')
        finally: os.close(current)
    finally: os.close(rootfd)
    block = raw[offset:offset + CHUNK]
    return dict(binding, offset=offset, chunk_sha256=hashlib.sha256(block).hexdigest(),
                data=base64.b64encode(block).decode('ascii'))


def main():
    """One-shot host tool. No root/DB/config creation and no stdout bodies."""
    import argparse
    from .runtime import approved_object_hook, code_pin
    from pathlib import Path
    from .worker import protected_read, HOSTS
    parser = argparse.ArgumentParser()
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    db, fd, guard = None, None, None
    try:
        check(os.geteuid() == 0 and os.uname().nodename == HOSTS['uk'], 'CUSTODY_HOST')
        raw = protected_read('/etc/xuanjun-cloud-executor/material-custody.json', 16384)
        check(hashlib.sha256(raw).hexdigest() == args.sha256, 'CUSTODY_CONFIG_SHA')
        config = decode(raw.decode())
        check(type(config) is dict and set(config) == {'schema', 'enabled', 'approved_objects', 'destination_root', 'destination_owner'}
              and type(config['schema']) is int and config['schema'] == 1 and config['enabled'] is True
              and config['destination_owner'] == 0 and type(config['destination_owner']) is int, 'CUSTODY_CONFIG')
        root = config['destination_root']
        state = '/var/lib/xuanjun-cloud-connection'
        check(type(root) is str and root.startswith(state + '/') and os.path.normpath(root) == root and root != state + '/', 'CUSTODY_ROOT_SCOPE')
        policy = approved_object_hook(config)
        check(policy is not None, 'CUSTODY_POLICY_REQUIRED')
        check(code_pin(Path(__file__).parent) == policy.catalog.value['executor_sha256'], 'CUSTODY_SOURCE_PIN')
        guard = directory(state, 0, private=True)
        fd = os.open('queue.sqlite', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=guard)
        before = os.fstat(fd)
        check(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
              and stat.S_IMODE(before.st_mode) == 0o600, 'CUSTODY_DATABASE')
        db = sqlite3.connect('file:' + state + '/queue.sqlite?mode=rw', uri=True, timeout=0, isolation_level=None)
        after = os.stat('queue.sqlite', dir_fd=guard, follow_symlinks=False)
        check((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino), 'CUSTODY_DATABASE_REPLACED')
        result = ingest_approved_batch(db, policy, root, 0, int(time.time()), True)
        print(json.dumps(result, sort_keys=True))
    except BaseException:
        print('{"state":"HOLD_KEEP_ALL_STATE_NO_REPLAY","reason":"MATERIAL_CUSTODY_FAILED"}')
        raise SystemExit(2)
    finally:
        if db is not None: db.close()
        if fd is not None: os.close(fd)
        if guard is not None: os.close(guard)


if __name__ == '__main__':
    main()
