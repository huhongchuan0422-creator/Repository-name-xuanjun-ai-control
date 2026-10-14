"""Finite recovery-only PREPARED release rebinding using the existing epoch journal.

Not a CLI, approval verifier, service exclusion check, or writer grant. The exact
recovery caller must hold the installation lock and obtain fresh independently
approved evidence before invoking this operation. No database or queue is created.
"""
import os
import re

SHA = re.compile(r'^[0-9a-f]{64}$')
IDENTITY_KEYS = ('schema', 'instance', 'generation', 'ledger_uuid', 'db_path',
                 'ledger_socket', 'binary_sha256')
PROOF_KEYS = frozenset(('approval_body_sha256', 'snapshot_sha256',
                        'recovery_plan_sha256', 'old_descriptor_sha256',
                        'new_descriptor_sha256', 'all_writers_excluded',
                        'install_lock_held', 'retained_resources_verified'))


def rebind_prepared(store, expected, proposed, proof):
    """Append epoch4 PREPARED then publish; crash leaves an explicit journal HOLD.

    The scope is deliberately epoch3 -> epoch4 only. Proof fields are a bound
    caller contract, not independently verified claims inside this primitive.
    Production wiring and exact review are required separately.
    """
    if os.geteuid() != store.owner_uid:
        raise ValueError('REBIND_OWNER_REQUIRED')
    expected = store.validate(expected)
    proposed = store.validate(proposed)
    if (expected['state'] != 'PREPARED' or expected['epoch'] != 3 or
            proposed['state'] != 'PREPARED' or proposed['epoch'] != 4):
        raise ValueError('REBIND_EXACT_PREPARED_EPOCHS')
    if any(expected[key] != proposed[key] for key in IDENTITY_KEYS):
        raise ValueError('REBIND_CANONICAL_IDENTITY_CHANGED')
    if expected['release_sha256'] == proposed['release_sha256']:
        raise ValueError('REBIND_NEW_RELEASE_REQUIRED')
    if not isinstance(proof, dict) or set(proof) != PROOF_KEYS:
        raise ValueError('REBIND_PROOF_KEYS')
    for key in ('all_writers_excluded', 'install_lock_held', 'retained_resources_verified'):
        if proof[key] is not True:
            raise ValueError('REBIND_LIVE_GATES_REQUIRED')
    for key in PROOF_KEYS - {'all_writers_excluded', 'install_lock_held', 'retained_resources_verified'}:
        if not isinstance(proof[key], str) or not SHA.fullmatch(proof[key]):
            raise ValueError('REBIND_PROOF_HASH')
    if (proof['old_descriptor_sha256'] != store.head(expected) or
            proof['new_descriptor_sha256'] != store.head(proposed)):
        raise ValueError('REBIND_DESCRIPTOR_BINDING')
    lock = store._locked()
    try:
        records = store._journal()
        if (not records or records[-1][0]['descriptor'] != expected or
                store._read_descriptor_unlocked() != expected):
            raise ValueError('REBIND_STALE_OR_UNRECONCILED_HEAD')
        record_proof = dict(proof, recovery='EXACT_EPOCH3_RELEASE_REBIND',
                            writer_admission=False, previous_epoch=3)
        store._append(proposed, records, record_proof)
        store._write_descriptor(proposed)
        return store.validate(proposed)
    finally:
        os.close(lock)
