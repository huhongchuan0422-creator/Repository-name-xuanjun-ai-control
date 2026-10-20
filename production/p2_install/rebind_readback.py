"""Read-only R03 evidence mirror inspection; never grants resume/write authority.

Only an explicitly pinned ISOLATED_TEST_ONLY mirror is accepted. The frozen
ActivationStore validates the existing journal/descriptor format. No guard,
reconcile, append, replacement or native installation method is called.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

PHASE = 'rebind_prepared_epoch'
TX = 'c529c379-9341-4510-8384-fc6be1e412e5'
TRANSACTION = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/legacy-isolation-' + TX
ACTIVATION = '/var/lib/xuanjun-development/activation/'
RESOURCES = {'descriptor': ACTIVATION + 'active.json', 'journal': ACTIVATION + 'epochs.jsonl',
    'lock': ACTIVATION + 'activation.lock', 'native': '/etc/xuanjun-development/p2-native-binding.json',
    'backup': TRANSACTION + '/epoch7-prior-native-binding.json',
    'tls': TRANSACTION + '/epoch8-tls-renewal-candidate.json',
    'outer': TRANSACTION + '/epoch7-recovery-sequence.json',
    'inner': TRANSACTION + '/epoch7-recovery-execution.json'}
PREFIX = ['stage_exact_release', 'preserve_prior_receipts']
ACTIVATION_SOURCE_SHA256 = '169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4'
SOURCE = 'evidence/p2-epoch7-access-repair-20261014/runtime/stage1/activation_control.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def need(ok, code):
    if not ok:
        raise ValueError(code)


def decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'DUPLICATE_FIELD')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read(root, resource):
    """Fixed resource names only; all ancestors opened relative/no-follow."""
    fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = RESOURCES[resource].lstrip('/').split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            info = os.fstat(child)
            need(info.st_uid == os.geteuid() and not info.st_mode & 0o022, 'UNSAFE_PARENT')
            os.close(fd)
            fd = child
        try:
            item = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            return None
        with os.fdopen(item, 'rb') as stream:
            before = os.fstat(stream.fileno())
            need(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                 and not before.st_mode & 0o022 and before.st_nlink == 1
                 and before.st_size <= 16 * 1024 * 1024, 'UNSAFE_RESOURCE')
            raw = stream.read(16 * 1024 * 1024 + 1)
            after = os.fstat(stream.fileno())
            need(stamp(before) == stamp(after) and len(raw) == before.st_size, 'READ_RACE')
            return raw, stamp(after)
    finally:
        os.close(fd)


def inspect(spec, expected_spec_sha256):
    result = {'schema': 1, 'scope': 'ISOLATED_TEST_ONLY', 'phase': PHASE,
              'status': 'UNKNOWN', 'decision': 'HOLD', 'write_authority': False,
              'spec_sha256': sha(encode(spec)), 'observed': {}}
    lock = None
    try:
        need(result['spec_sha256'] == expected_spec_sha256, 'INPUT_IDENTITY_MISMATCH')
        need(set(spec) == {'schema', 'scope', 'root', 'phase', 'transaction_id', 'context_sha256',
             'binding', 'before', 'after', 'proof', 'source_refs'}, 'INPUT_FIELDS')
        need(spec['schema'] == 1 and spec['scope'] == result['scope'] and spec['phase'] == PHASE
             and spec['transaction_id'] == TX, 'INPUT_SCOPE')
        root = Path(spec['root'])
        need(root.is_absolute() and root.name.startswith('p2-b3-readback-')
             and str(root.resolve()) == str(root), 'ISOLATED_MIRROR_REQUIRED')
        info = os.lstat(str(root))
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
             and stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_MIRROR_REQUIRED')
        need(isinstance(spec['source_refs'], dict) and set(spec['source_refs']) ==
             {'context', 'snapshot', 'candidate', 'plan', 'outer', 'inner'}, 'SOURCE_REFS_REQUIRED')
        for ref in spec['source_refs'].values():
            need(isinstance(ref, dict) and set(ref) == {'ref', 'sha256'} and isinstance(ref['ref'], str)
                 and bool(ref['ref']) and isinstance(ref['sha256'], str)
                 and len(ref['sha256']) == 64 and all(c in '0123456789abcdef' for c in ref['sha256']), 'SOURCE_REF_IDENTITY')
        need(spec['source_refs']['context']['sha256'] == spec['context_sha256'], 'CONTEXT_REFERENCE')
        for side, keys in (('before', {'activation', 'journal_sha256', 'native_sha256'}),
                           ('after', {'activation', 'native_sha256', 'tls_sha256'})):
            need(set(spec[side]) == keys, 'EXPECTED_STATE_FIELDS')
        module_path = Path(__file__).resolve().parents[2] / SOURCE
        module_raw = module_path.read_bytes()
        need(sha(module_raw) == ACTIVATION_SOURCE_SHA256, 'FROZEN_VALIDATOR_CHANGED')
        module = importlib.util.module_from_spec(importlib.util.spec_from_file_location('r03_activation', str(module_path)))
        exec(compile(module_raw, str(module_path), 'exec'), module.__dict__)
        Store = module.ActivationStore
        before, after = (Store.validate(spec[k]['activation']) for k in ('before', 'after'))
        need(before['epoch'] == 7 and after['epoch'] == 8 and
             before['state'] == after['state'] == 'PREPARED', 'EXACT_EPOCHS')
        need(all(before[k] == after[k] for k in ('ledger_uuid', 'generation', 'instance', 'db_path', 'ledger_socket')),
             'CANONICAL_IDENTITY')
        need(spec['before']['native_sha256'] != spec['after']['native_sha256'], 'DISTINCT_NATIVE_STATES')
        proof = spec['proof']
        need(set(proof) == {'controller_transition_sha256', 'approval_body_sha256', 'snapshot_sha256',
             'recovery_plan_sha256', 'old_descriptor_sha256', 'new_descriptor_sha256',
             'all_writers_excluded', 'install_lock_held', 'retained_resources_verified'}, 'PROOF_FIELDS')
        need(all(proof[k] is True for k in ('all_writers_excluded', 'install_lock_held',
             'retained_resources_verified')), 'ORIGINAL_PROOF_FLAGS')
        need(proof['old_descriptor_sha256'] == Store.head(before) and
             proof['new_descriptor_sha256'] == Store.head(after) and
             proof['snapshot_sha256'] == spec['source_refs']['snapshot']['sha256'] and
             proof['recovery_plan_sha256'] == spec['source_refs']['plan']['sha256'], 'PROOF_IDENTITY')
        need(proof['approval_body_sha256'] == spec['binding']['approval_body_sha256']
             and proof['snapshot_sha256'] == spec['binding']['snapshot_sha256'], 'BINDING_PROOF_MISMATCH')
        lock_before = read(root, 'lock')
        need(lock_before is not None, 'EXISTING_LOCK_REQUIRED')
        # Unlike authority _locked(), this cannot create/chmod the original lock.
        lock = os.open(str(root) + RESOURCES['lock'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        need(stamp(os.fstat(lock)) == lock_before[1], 'LOCK_RACE')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        captured = {key: read(root, key) for key in RESOURCES}
        need(captured['lock'] == lock_before, 'LOCK_CHANGED')
        result['observed'] = {k: {'origin': RESOURCES[k], 'mirror': str(root) + RESOURCES[k],
            'exists': v is not None, 'sha256': sha(v[0]) if v else None,
            'metadata': list(v[1]) if v else None} for k, v in captured.items()}
        for key in ('journal', 'descriptor', 'native', 'outer', 'inner'):
            need(captured[key] is not None, 'REQUIRED_EVIDENCE_MISSING:' + key)
        # Reject noncanonical/duplicate fields before reusing the frozen reader.
        for raw in captured['journal'][0].splitlines(keepends=True):
            need(encode(decode(raw)) + b'\n' == raw, 'NONCANONICAL_ACTIVATION_JOURNAL')
        for key in ('outer', 'inner'):
            raw = captured[key][0]
            value = decode(raw)
            need(encode(value) + b'\n' == raw and stat.S_IMODE(captured[key][1][2]) == 0o600,
                 'PROTECTED_RECORD_FORMAT')
            need(value['schema'] == 1 and value['transaction_id'] == TX and
                 value['binding'] == spec['binding'], 'RECORD_BINDING')
            need(sha(raw) == spec['source_refs'][key]['sha256'], 'RECORD_REFERENCE')
            if key == 'outer':
                need(set(value) == {'schema', 'name', 'transaction_id', 'context_sha256', 'binding', 'state'}
                     and value['name'] == 'epoch7-recovery-sequence.json'
                     and value['context_sha256'] == spec['context_sha256'], 'OUTER_IDENTITY')
                state = value['state']
                need(state['admission'] == 'ADMITTED' and state['containment_status'] == 'NOT_ATTEMPTED'
                     and state['containment'] == [] and state['automatic_retry'] is False, 'OUTER_HOLD_OR_CONTAINMENT')
                need((state['stage'] == PHASE + '_INTENT' and state['completed'] == PREFIX) or
                     (state['stage'] == PHASE + '_COMPLETE' and state['completed'] == PREFIX + [PHASE]), 'PHASE_PREFIX')
            else:
                need(set(value) == {'schema', 'name', 'transaction_id', 'binding', 'state'}
                     and value['name'] == 'epoch7-recovery-execution.json'
                     and value['state']['stage'] == 'ADMITTED', 'INNER_IDENTITY')
        store = Store(str(root) + RESOURCES['descriptor'], str(root) + RESOURCES['journal'],
                      str(root) + RESOURCES['lock'], owner_uid=os.geteuid())
        rows = store._journal()  # existing validator, read only; never _locked/reconcile
        descriptor = store._read_descriptor_unlocked()
        need(rows, 'EMPTY_HISTORY_IS_NOT_PROOF')
        need(Store.validate(decode(captured['descriptor'][0])) == descriptor, 'DESCRIPTOR_READ_RACE')
        need({k: read(root, k) for k in RESOURCES} == captured, 'EVIDENCE_CHANGED')
        journal_new = rows[-1][0]['descriptor'] == after
        journal_old = rows[-1][0]['descriptor'] == before and sha(captured['journal'][0]) == spec['before']['journal_sha256']
        if journal_new:
            expected_proof = dict(proof, recovery='EXACT_EPOCH7_RELEASE_REBIND', writer_admission=False, previous_epoch=7)
            need(rows[-1][0]['proof'] == expected_proof and len(rows) >= 2 and
                 rows[-2][0]['descriptor'] == before, 'APPEND_PROOF_MISMATCH')
            prefix_raw = b''.join(captured['journal'][0].splitlines(keepends=True)[:-1])
            need(sha(prefix_raw) == spec['before']['journal_sha256'], 'PRIOR_HISTORY_MISMATCH')
        for key in ('native', 'backup', 'tls'):
            if captured[key] is not None:
                need(stat.S_IMODE(captured[key][1][2]) == (0o644 if key == 'native' else 0o600), 'RESOURCE_MODE:' + key)
        native_old = sha(captured['native'][0]) == spec['before']['native_sha256']
        native_new = sha(captured['native'][0]) == spec['after']['native_sha256']
        backup = captured['backup']
        backup_ok = backup is not None and sha(backup[0]) == spec['before']['native_sha256']
        tls = captured['tls']
        tls_ok = tls is not None and sha(tls[0]) == spec['after']['tls_sha256']
        result['effects'] = {'activation_append': 'ALREADY_APPLIED' if journal_new else
            'PROVEN_NOT_APPLIED' if journal_old else 'UNKNOWN',
            'descriptor': 'ALREADY_APPLIED' if descriptor == after else 'PROVEN_NOT_APPLIED' if descriptor == before else 'UNKNOWN',
            'native': 'ALREADY_APPLIED' if native_new and backup_ok else 'PROVEN_NOT_APPLIED' if native_old else 'UNKNOWN',
            'tls_candidate': 'ALREADY_APPLIED' if tls_ok else 'PROVEN_NOT_APPLIED' if tls is None else 'UNKNOWN'}
        if journal_new and descriptor == before and native_old and backup is None and tls is None:
            result['interruption'] = 'ACTIVATION_APPEND_BEFORE_DESCRIPTOR'
        elif journal_new and descriptor == after and native_new and backup_ok and tls is None:
            result['interruption'] = 'NATIVE_REPLACED_BEFORE_TLS_CANDIDATE'
        if journal_new and descriptor == after and native_new and backup_ok and tls_ok:
            result['status'] = 'ALREADY_APPLIED'
        elif journal_old and descriptor == before and native_old and backup is None and tls is None and state['stage'] == PHASE + '_INTENT':
            result['status'] = 'PROVEN_NOT_APPLIED'
        # A classification never bypasses original guard or authorizes a retry.
        need({k: read(root, k) for k in RESOURCES} == captured, 'FINAL_EVIDENCE_CHANGED')
    except Exception as exc:
        result['status'] = 'UNKNOWN'
        result['error'] = {'type': type(exc).__name__, 'code': str(exc) if isinstance(exc, ValueError) else type(exc).__name__}
    finally:
        if lock is not None:
            os.close(lock)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec-sha256', required=True)
    args = parser.parse_args()
    spec = decode(sys.stdin.buffer.read(1048577))
    result = inspect(spec, args.spec_sha256)
    print(json.dumps(result, sort_keys=True))
    return 2 if result['status'] == 'UNKNOWN' else 0


if __name__ == '__main__':
    sys.exit(main())
