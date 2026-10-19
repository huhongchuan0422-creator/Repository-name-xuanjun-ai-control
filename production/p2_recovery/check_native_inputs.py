"""Batch the retained lifecycle inputs through the exact native compiler.

Read-only input/contract compatibility; no Driver, Observer, Grant, DB or phase.
Outputs never authorize execution and are not production isolation evidence.
Python 3.6 standard library only.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

PARENT = ('/var/lib/xuanjun-p2-preparation/'
          'artifact-11796280855-p2pkg-38372304180-1/'
          'complete-install-candidate-38503014520')
PAIRS = (
    ('lifecycle-2ac961e8',
     '2ac961e8765e82e6b6fca18f2c3be0f299a71898ad5a8f95109c44420c4a1f15',
     '57f46aa89f4af77b6e66167ae84875b5c54ee3bdf48c4b28c702a1f7855f94b5'),
    ('lifecycle-5b3a3422',
     '5b3a34222dc634d95b4e070105de9afb3dc24b5c53f7b6497bc61d392887fb01',
     'd7eabd4c0716bd23c35a210c0ace8493b8a9f23237d1df1eeef231fdda8d16f0'),
    ('lifecycle-8adf9461',
     '8adf9461da734f4c10a4c9a4c5e70167f5bccd117e8ae06e7774973afff7f349',
     'be033bc4e8e4703220494e15d0d7524b040388f9700f052714c027132b75898c'),
)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, str(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reason(exc):
    value = str(exc)
    return value if re.fullmatch('[A-Z][A-Z0-9_]{0,160}', value) else type(exc).__name__


def check_pair(adapter, kit, factory, name, plan_pin, seed_pin):
    row = {'pair': name, 'plan_sha256': plan_pin, 'seed_sha256': seed_pin,
           'status': 'FAILED', 'stage': 'READ_PRIVATE_INPUTS'}
    try:
        def ref(prefix, pin):
            return {'path': PARENT + '/' + prefix + pin[:16] + '.private.json',
                    'sha256': pin}
        plan_ref = ref('epoch7-lifecycle-approved-plan-', plan_pin)
        seed_ref = ref('epoch7-lifecycle-resume-inputs-', seed_pin)
        unused_raw, plan, private = adapter.private_resume_inputs(kit, plan_ref, seed_ref)
        row['stage'] = 'HYDRATE_FROZEN_SEED'
        seed = kit._hydrate_seed(private, factory)
        row['stage'] = 'COMPILE_HOST_INPUTS'
        prepared = factory.prepare_host_inputs(seed)
        if (prepared.get('state') != 'COMPILED_NOT_ADMITTED' or
                prepared.get('install_admission') is not False or
                prepared.get('unresolved') != []):
            row['reason'] = 'HOST_INPUTS_UNRESOLVED'
            row['unresolved_count'] = (len(prepared['unresolved'])
                if isinstance(prepared.get('unresolved'), list) else None)
            return row
        row['stage'] = 'COMPARE_RETAINED_PLAN'
        contract = factory.compile_host_contract(prepared['inputs'])
        different = sorted(key for key, value in contract.items()
                           if adapter.canonical(plan.get(key)) != adapter.canonical(value))
        if different:
            row['reason'] = 'APPROVED_CONTRACT_CHANGED'
            row['different_fields'] = different
            return row
        row['stage'] = 'RECHECK_PRIVATE_INPUTS'
        adapter.private_resume_inputs(kit, plan_ref, seed_ref)
        row['status'] = 'INPUT_CONTRACT_COMPATIBLE_NOT_INSTALLED'
    except Exception as exc:
        row['reason'] = reason(exc)
    return row


def inherited_bytes(filename, bound):
    """Root-owned, non-writable Kit files may legitimately be mode 0444."""
    parts = filename.strip('/').split('/')
    if not filename.startswith('/') or any(x in ('', '.', '..') for x in parts):
        raise RuntimeError('INHERITED_PATH')
    import stat
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise RuntimeError('INHERITED_PARENT_PROTECTION')
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)
    try:
        before = os.fstat(child)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or
                before.st_nlink != 1 or before.st_mode & 0o022 or before.st_size > bound):
            raise RuntimeError('INHERITED_FILE_PROTECTION')
        chunks = []
        count = 0
        while count <= bound:
            raw = os.read(child, min(65536, bound + 1 - count))
            if not raw:
                break
            chunks.append(raw)
            count += len(raw)
        after = os.fstat(child)
        stamp = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if count != before.st_size or count > bound or stamp(before) != stamp(after):
            raise RuntimeError('INHERITED_READ_RACE_OR_BOUND')
        return b''.join(chunks)
    finally:
        os.close(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit-root', required=True)
    args = parser.parse_args()
    if not (os.geteuid() == 0 and os.getuid() == 0 and
            os.uname().nodename.split('.')[0] == 'iZd7oeikknn1z21sq6ji6zZ' and
            sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise RuntimeError('ISOLATED_UK_ROOT_REQUIRED')
    root = Path(__file__).resolve().parents[2]
    adapter = load('p2_retained_input_adapter',
                   root / 'production/p2_attempt5/native_adapter.py')
    kitroot = Path(args.kit_root)
    loader_raw = inherited_bytes(str(kitroot / 'attempt5/runtime/versioned_entry.py'),
                             bound=1048576)
    # The descriptor bytes and inherited manifest are authenticated against the
    # independently reviewed, unchanged runtime pins before executing imports.
    from types import ModuleType
    loader = ModuleType('p2_retained_input_loader')
    loader.__file__ = str(kitroot / 'attempt5/runtime/versioned_entry.py')
    manifest_raw = inherited_bytes(str(kitroot / 'attempt5-manifest.json'), bound=1048576)
    manifest_pin = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_pin != '243bc01b1e9c7d2cb302f800556002abcebcfa9f96c298e4275e15d8b1346e1e':
        raise RuntimeError('INHERITED_RUNTIME_MANIFEST_CHANGED')
    manifest = adapter.decode(manifest_raw)
    if hashlib.sha256(loader_raw).hexdigest() != manifest['files']['attempt5/runtime/versioned_entry.py']:
        raise RuntimeError('INHERITED_LOADER_SHA')
    exec(compile(loader_raw, loader.__file__, 'exec'), loader.__dict__)
    results = []
    with loader.imports(str(kitroot), manifest_pin):
        import epoch7_host_factory as factory
        legacy_raw = inherited_bytes(str(kitroot / 'legacy/epoch7_recovery_entry.py'),
                                  bound=1048576)
        if hashlib.sha256(legacy_raw).hexdigest() != '21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890':
            raise RuntimeError('INHERITED_LEGACY_ENTRY_SHA')
        legacy = ModuleType('p2_retained_legacy_entry')
        legacy.__file__ = str(kitroot / 'legacy/epoch7_recovery_entry.py')
        exec(compile(legacy_raw, legacy.__file__, 'exec'), legacy.__dict__)
        legacy_pin = hashlib.sha256(inherited_bytes(
            str(kitroot / 'legacy/recovery-kit-manifest.json'), bound=1048576)).hexdigest()
        kit = legacy.verify_kit(str(kitroot / 'legacy'), legacy_pin)
        for name, plan_pin, seed_pin in PAIRS:
            results.append(check_pair(adapter, kit, factory, name, plan_pin, seed_pin))
    compatible = [row['pair'] for row in results
                  if row['status'] == 'INPUT_CONTRACT_COMPATIBLE_NOT_INSTALLED']
    print(json.dumps({'scope': 'ISOLATED_READ_COMPILE_ONLY',
        'production_permission': False, 'installation_executed': False,
        'pairs': results, 'compatible_pairs': compatible}, sort_keys=True, indent=2))
    return 0 if compatible else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({'scope': 'ISOLATED_READ_COMPILE_ONLY',
            'installation_executed': False, 'production_permission': False,
            'reason': reason(exc)}, sort_keys=True))
        sys.exit(2)
