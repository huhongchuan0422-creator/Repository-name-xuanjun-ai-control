"""Prepare a new generation from the existing registry; never activate it.

The privileged installer must measure the legacy stop/cgroup/restart proof.
This module preserves an unmodified rollback snapshot and adds only the two
ExecutionLedger side tables in a separate fresh generation.
"""
import os
import sqlite3
import stat

from execution_ledger import ExecutionLedger
from ledger_backup import backup, database_manifest, verify

PROOF_KEYS = frozenset(('identity_verified', 'coordinator_inactive',
                        'parent_unit_inactive', 'cgroups_empty', 'restart_inhibited'))


def _fresh(path):
    if not os.path.isabs(path) or os.path.realpath(path) != path:
        raise ValueError('NON_CANONICAL_STAGING_PATH')
    if any(os.path.lexists(p) for p in (path, path + '-wal', path + '-shm')):
        raise ValueError('STAGING_TARGET_OR_SIDECAR_EXISTS')


def _core_snapshot(path):
    with sqlite3.connect('file:' + path + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        ExecutionLedger._validate_schema(db)
        if db.execute('SELECT count(*) FROM tasks WHERE lease_owner IS NOT NULL '
                      "OR state='RUNNING'").fetchone()[0]:
            raise ValueError('HOLD_UNRECONCILED_LEASE_OR_RUNNING_TASK')
    return database_manifest(path)


def stage_existing_registry(source, rollback_snapshot, staged_generation,
                            repository, quiescence_proof):
    if (not isinstance(quiescence_proof, dict) or set(quiescence_proof) != PROOF_KEYS
            or any(quiescence_proof[k] is not True for k in PROOF_KEYS)):
        raise ValueError('HOLD_LEGACY_QUIESCENCE_NOT_PROVED')
    if not isinstance(repository, str) or repository.count('/') != 1:
        raise ValueError('EXPLICIT_REPOSITORY_REQUIRED')
    if (not os.path.isabs(source) or os.path.realpath(source) != source
            or not stat.S_ISREG(os.lstat(source).st_mode)):
        raise ValueError('UNSAFE_CANONICAL_SOURCE')
    if len({source, rollback_snapshot, staged_generation}) != 3:
        raise ValueError('SOURCE_BACKUP_GENERATION_MUST_DIFFER')
    _fresh(rollback_snapshot)
    _fresh(staged_generation)
    # All existing-task decisions are taken from the consistent logical backup,
    # not from a raw copy of an active main SQLite file.
    backup(source, rollback_snapshot)
    before = _core_snapshot(rollback_snapshot)
    backup(rollback_snapshot, staged_generation)
    ExecutionLedger(staged_generation, [repository])
    # Existing callback tables stay byte-logically unchanged; add the missing
    # replay side table only on the isolated generation, before activation.
    from uk_owner_callback_core import install_schema, validate_schema
    install_schema(staged_generation)
    validate_schema(staged_generation)
    after = verify(staged_generation)
    for table in before['counts']:
        if (after['counts'].get(table) != before['counts'][table]
                or after['table_sha256'].get(table) != before['table_sha256'][table]):
            raise ValueError('HOLD_ORIGINAL_TABLE_STATE_CHANGED')
    for key in ('user_version', 'application_id', 'page_size'):
        if before['pragmas'][key] != after['pragmas'][key]:
            raise ValueError('HOLD_DATABASE_PRAGMA_CHANGED')
    retained = database_manifest(rollback_snapshot)
    if retained != before:
        raise ValueError('HOLD_ROLLBACK_SNAPSHOT_CHANGED')
    if any(os.path.exists(staged_generation + suffix) for suffix in ('-wal', '-shm')):
        raise ValueError('HOLD_STAGED_GENERATION_HAS_SIDECARS')
    return {'status': 'STAGED_NOT_ACTIVE', 'rollback': before, 'generation': after,
            'new_tables': sorted(set(after['counts']) - set(before['counts'])),
            'source_replaced': False, 'task_replay': False}
