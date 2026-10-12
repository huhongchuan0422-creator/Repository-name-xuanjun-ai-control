"""Consistent SQLite backup/verification and restore staging.

Never replaces the live database.  A reviewed operator must stop the dispatcher,
hold its exclusive lock and atomically activate a verified staged copy.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile

from execution_ledger import ExecutionLedger


def database_manifest(path):
    with sqlite3.connect('file:' + path + '?mode=ro', uri=True) as db:
        check = db.execute('PRAGMA quick_check').fetchone()[0]
        if check != 'ok':
            raise ValueError('SQLite quick_check failed')
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        counts = {name: db.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                  for name in tables}
        pragmas = {name: db.execute('PRAGMA ' + name).fetchone()[0]
                   for name in ('user_version', 'application_id', 'page_size')}
        schema = [row[0] for row in db.execute(
            "SELECT coalesce(sql,'') FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        schema_sha = hashlib.sha256(json.dumps(schema, separators=(',', ':'),
                                               ensure_ascii=False).encode('utf-8')).hexdigest()
        table_hashes = {}
        for name in tables:
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [row[1] for row in db.execute('PRAGMA table_info(' + quoted + ')')]
            order = ','.join('"' + column.replace('"', '""') + '"' for column in columns)
            rows = db.execute('SELECT * FROM ' + quoted + (' ORDER BY ' + order if order else ''))
            table_digest = hashlib.sha256()
            for row in rows:
                values = [{'blob': value.hex()} if isinstance(value, bytes) else value
                          for value in row]
                table_digest.update((json.dumps(values, sort_keys=True, separators=(',', ':'),
                                                ensure_ascii=False) + '\n').encode('utf-8'))
            table_hashes[name] = table_digest.hexdigest()
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'sha256': digest.hexdigest(), 'size': os.path.getsize(path), 'counts': counts,
            'pragmas': pragmas, 'schema_sha256': schema_sha,
            'table_sha256': table_hashes, 'quick_check': 'ok'}


def backup(source, target):
    if os.path.exists(target):
        raise ValueError('backup target already exists')
    directory = os.path.dirname(target) or '.'
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.ledger-backup-', dir=directory)
    os.close(fd)
    try:
        # Python 3.6 deployments may not expose Connection.backup().  Hold a
        # consistent read transaction and replay SQLite's quoted logical dump
        # into a new file; this also avoids copying a live WAL database file.
        with sqlite3.connect('file:' + source + '?mode=ro', uri=True) as src:
            src.execute('BEGIN')
            user_version=src.execute('PRAGMA user_version').fetchone()[0]
            application_id=src.execute('PRAGMA application_id').fetchone()[0]
            page_size=src.execute('PRAGMA page_size').fetchone()[0]
            statements = list(src.iterdump())
            with sqlite3.connect(temporary) as dst:
                dst.execute('PRAGMA page_size=%d' % page_size)
                dst.executescript('\n'.join(statements))
                dst.execute('PRAGMA user_version=%d' % user_version)
                dst.execute('PRAGMA application_id=%d' % application_id)
            src.commit()
        manifest = database_manifest(temporary)
        os.chmod(temporary, 0o600)
        with open(temporary,'rb') as durable:
            os.fsync(durable.fileno())
        os.replace(temporary, target)
        directory_fd=os.open(directory,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
        return manifest
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify(path, expected_sha=None, expected_manifest=None):
    manifest = database_manifest(path)
    if expected_sha is not None and manifest['sha256'] != expected_sha:
        raise ValueError('backup digest mismatch')
    if expected_manifest is not None and manifest != expected_manifest:
        raise ValueError('backup manifest mismatch')
    # Validate read-only: verification must not create tables or alter WAL state.
    with sqlite3.connect('file:' + path + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        ExecutionLedger._validate_schema(db)
        ExecutionLedger._validate_side_schema(db)
    return manifest


def stage_restore(source, target, expected_sha, expected_manifest=None):
    source_manifest = verify(source, expected_sha, expected_manifest)
    parent = os.path.dirname(target) or '.'
    for candidate in (target, target + '-wal', target + '-shm'):
        if os.path.lexists(candidate):
            raise ValueError('restore target or SQLite sidecar already exists')
    os.makedirs(parent, mode=0o700, exist_ok=True)
    result = backup(source, target)
    # Logical recreation changes file bytes, but schema, PRAGMAs, counts and
    # every table (including requests/approvals/events) must be identical.
    for key in ('counts', 'pragmas', 'schema_sha256', 'table_sha256'):
        if result[key] != source_manifest[key]:
            raise ValueError('restored database state mismatch: ' + key)
    verify(target, result['sha256'], result)
    if os.path.exists(target + '-wal') or os.path.exists(target + '-shm'):
        raise ValueError('restored generation was contaminated by sidecars')
    return result


class RestoreActivator(object):
    """Restore to a fresh generation and advance activation under a new epoch."""
    def __init__(self, activation_store, generations_root, stop_all, reopen):
        self.activation_store = activation_store
        self.generations_root = os.path.realpath(generations_root)
        self.stop_all, self.reopen = stop_all, reopen
        if not os.path.isabs(generations_root) or self.generations_root != generations_root:
            raise ValueError('generations root must be canonical absolute')

    def restore(self, source, expected_manifest, release_sha256, config_sha256,
                binary_sha256, ledger_uuid, generation, instance, ledger_socket):
        if not isinstance(expected_manifest, dict) or not expected_manifest.get('sha256'):
            raise ValueError('complete expected backup manifest required')
        current = self.activation_store.read(require_active=True)
        directory = os.path.join(self.generations_root, 'generation-%020d' % generation)
        target = os.path.join(directory, 'ledger.sqlite')
        if os.path.lexists(directory):
            raise ValueError('restore generation already exists')
        # Authenticate the immutable backup before entering maintenance. Once
        # PREPARED is durable, all ledger users fail closed until reconciliation.
        verify(source, expected_manifest['sha256'], expected_manifest)
        prepared = self.activation_store.prepare(
            release_sha256, config_sha256, binary_sha256, ledger_uuid, generation,
            instance, target, ledger_socket, expected_epoch=current['epoch'])
        proof = self.stop_all(current, prepared)
        quiesced = self.activation_store.transition(
            'PREPARED', 'QUIESCED', prepared['epoch'], instance, proof=proof)
        manifest = stage_restore(source, target, expected_manifest['sha256'],
                                 expected_manifest)
        # verify() opens the new generation after restore; the caller then
        # performs its own authoritative schema/service reopen before ACTIVE.
        verify(target, manifest['sha256'], manifest)
        if self.reopen(quiesced, manifest) is not True:
            raise RuntimeError('restored database reopen failed')
        active = self.activation_store.transition(
            'QUIESCED', 'ACTIVE', prepared['epoch'], instance,
            proof={'database_reopened': True})
        return {'activation': active, 'manifest': manifest}


def main(argv=None):
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--backup', nargs=2, metavar=('SOURCE', 'TARGET'))
    actions.add_argument('--verify', metavar='DATABASE')
    actions.add_argument('--stage-restore', nargs=2, metavar=('BACKUP', 'STAGED_TARGET'))
    parser.add_argument('--expected-sha256')
    args = parser.parse_args(argv)
    if args.backup:
        result = backup(*args.backup)
    elif args.verify:
        result = verify(args.verify, args.expected_sha256)
    else:
        if not args.expected_sha256:
            parser.error('--stage-restore requires --expected-sha256')
        result = stage_restore(args.stage_restore[0], args.stage_restore[1], args.expected_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
