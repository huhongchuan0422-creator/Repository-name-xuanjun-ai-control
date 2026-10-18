"""Affected acceptance only, retaining exact reviewed core and artifact pins."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
BASE = 'f4f74fdd0b6aa49e046debabf81e438b17ff20b5'
PREFIX = 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/attempt5'


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    def git(*args):
        return subprocess.check_output(['git', '-c', 'safe.directory=*'] + list(args), cwd=str(ROOT))
    head = git('rev-parse', 'HEAD').decode().strip()
    assert head == os.environ.get('GITHUB_SHA', head), 'EXACT_CI_HEAD'
    tree = git('rev-parse', 'HEAD^{tree}').decode().strip()
    paths = git('ls-tree', '-r', '--name-only', BASE, '--', PREFIX).decode().splitlines()
    files = {}
    for name in paths:
        raw = (ROOT / name).read_bytes()
        previous = git('show', BASE + ':' + name)
        if name == PREFIX + '/runtime/authorization.py':
            assert hashlib.sha256(previous).hexdigest() == '3623a18e0286fa61de3ac2fc24d909dcdd4e9df764acb978a5854bf193c051fd', 'HISTORICAL_AUTHORITY_PIN'
            assert raw != previous, 'OWNER_AUTHORITY_DELTA_REQUIRED'
        else:
            assert raw == previous, 'REVIEWED_CORE_CHANGED:' + name
        files[name] = hashlib.sha256(raw).hexdigest()
    added = ['production/p2_attempt5/assembly.py', 'production/p2_attempt5/entry.py',
             'production/p2_attempt5/verify.py', 'production/p2_attempt5/README.md',
             'production/p2_attempt5/registry.py', 'production/p2_attempt5/registry_cli.py',
             'tests/p2_production_assembly/test_registry.py',
             'tests/p2_production_assembly/test_assembly.py',
             'production/p2_attempt5/native_adapter.py',
             'tests/p2_production_assembly/test_native_adapter.py',
             'production/p2_attempt5/observer_server.py',
             'tests/p2_production_assembly/test_observer_server.py',
             'tests/p2_production_assembly/test_observer_recovery.py',
             'tests/p2_production_assembly/test_owner_authorization.py',
             '.github/workflows/p2-production-assembly.yml']
    for name in added:
        files[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    groups = []
    cases = [(str(ROOT / 'tests/p2_production_assembly'), 'test_owner_authorization.py', 25),
             (str(ROOT / PREFIX), 'test_authorization.py', 9),(str(ROOT / 'tests/p2_production_assembly'), 'test_observer_recovery.py', 20),(str(ROOT / 'tests/p2_production_assembly'), 'test_observer_server.py', 23),
             (str(ROOT / 'tests/p2_production_assembly'), 'test_assembly.py', 27),
             (str(ROOT / 'tests/p2_production_assembly'), 'test_native_adapter.py', 21),
             (str(ROOT / 'tests/p2_production_assembly'), 'test_registry.py', 50)]
    for index, (directory, pattern, count) in enumerate(cases):
        script = ('import sys,unittest;sys.path[:0]=[%r,%r];'
                  'suite=unittest.defaultTestLoader.discover(%r,pattern=%r);'
                  'print("DISCOVERED_TESTS=",suite.countTestCases(),flush=True);'
                  'r=unittest.TextTestRunner(verbosity=2).run(suite);'
                  'assert r.wasSuccessful() and not r.skipped and r.testsRun==%d' %
                  (directory, str(ROOT/'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/helpers'),
                   directory, pattern, count))
        if pattern == 'test_observer_recovery.py':
            script = 'import runpy;runpy.run_path(%r,run_name="__main__")' % str(Path(directory)/pattern)
        result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', script],
                                cwd=str(ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=240)
        log = output / ('tests-%d.log' % index)
        log.write_bytes(result.stdout)
        print(result.stdout.decode('utf-8'), flush=True)
        assert result.returncode == 0, 'AFFECTED_ACCEPTANCE_FAILED:' + pattern
        if pattern == 'test_observer_recovery.py':
            import re
            summary = re.findall(r'Ran (\d+) tests? in ', result.stdout.decode('utf-8'))
            assert summary == [str(count)] and b'\\nskipped=' not in result.stdout, 'RECOVERY_TEST_COUNT'
        groups.append({'group': pattern, 'tests': count,
                       'log_sha256': hashlib.sha256(result.stdout).hexdigest()})
    # Separate versioned runtime Kit: only authorization.py changes; legacy
    # payload stays exactly inherited. Never overwrite the historical Kit.
    import importlib.util
    spec = importlib.util.spec_from_file_location('build_owner_runtime_kit',str(ROOT/PREFIX/'build_kit.py'))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    kit_raw, kit_manifest = builder.build(head,tree)
    kit_manifest_raw = builder.canonical(kit_manifest)
    (output/'attempt5-kit.tar.gz').write_bytes(kit_raw)
    (output/'attempt5-manifest.json').write_bytes(kit_manifest_raw)
    runtime_kit_sha = hashlib.sha256(kit_raw).hexdigest()
    runtime_manifest_sha = hashlib.sha256(kit_manifest_raw).hexdigest()
    assert len(kit_manifest['inherited_files'])==257
    manifest = {'schema': 1, 'source_commit': head, 'source_tree': tree,
                'reviewed_core_commit': BASE,
                'reviewed_core_tree': '2c2e3c09cbda31df30e0d269b580348c55e6de87',
                'inherited_kit_sha256': 'da3c42f6dd6d030c337ffb358be0cbe77c64eb0912016ebf30a353f65451d83f',
                'historical_attempt5_manifest_sha256': '41771b95c95b960cc643f06b1b3c622a880ed64a385d2f122322605b8abf106c',
                'inherited_manifest_sha256': runtime_manifest_sha,
                'runtime_source_commit': head, 'runtime_source_tree': tree,
                'runtime_kit_sha256': runtime_kit_sha,
                'runtime_manifest_sha256': runtime_manifest_sha,
                'authorization_modes': ['PR58_INDEPENDENT_V1','PR17_OWNER_V1'],
                'reviewed_core_delta': [PREFIX+'/runtime/authorization.py'],
                'files': files, 'groups': groups, 'tests': sum(g['tests'] for g in groups),
                'python': sys.version, 'production_binding': 'UNKNOWN',
                'trusted_config_entry': 'production/p2_attempt5/registry_cli.py',
                'registry_default_root': '/etc/xuanjun-p2/registry',
                'registry_deployment': 'NOT_EXECUTED',
                'inherited_assembly_ci_run': 39122271093,
                'inherited_assembly_tests_per_python': 83,
                'registry_review_fix': 'CLOSED_PR58_6250317194',
                'adapter_scope': 'PUBLIC_KEY_NATIVE_FACTORY_CLIENT_AND_FENCED_OBSERVER_SERVER',
                'observer_server': 'SOURCE_IMPLEMENTED_NOT_DEPLOYED',
                'observer_fact_source': 'INHERITED_NATIVE_OBSERVER_UK_NOT_VERIFIED',
                'native_run_positive': 'NOT_VERIFIED_NO_PERMIT_OR_PRIVATE_INPUTS',
                'host_effects': 'SYNTHETIC_TEST_ONLY', 'installation': 'NOT_EXECUTED',
                'permit': 'NOT_ISSUED', 'release': 'HOLD'}
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    (output / 'MANIFEST.json').write_bytes(raw)
    bundle = output / 'production-assembly.tar.gz'
    with tarfile.open(str(bundle), 'w:gz') as archive:
        for name in sorted(files):
            archive.add(str(ROOT / name), arcname=name, recursive=False)
        archive.add(str(output / 'MANIFEST.json'), arcname='MANIFEST.json')
        for log in sorted(output.glob('tests-*.log')):
            archive.add(str(log), arcname=log.name)
    (output / 'SHA256SUMS').write_text(
        hashlib.sha256(raw).hexdigest() + '  MANIFEST.json\n' +
        hashlib.sha256(bundle.read_bytes()).hexdigest() + '  production-assembly.tar.gz\n' +
        runtime_kit_sha + '  attempt5-kit.tar.gz\n' +
        runtime_manifest_sha + '  attempt5-manifest.json\n')
    print('ARTIFACT_BINDING=' + json.dumps({
        'source_commit': head, 'source_tree': tree, 'files': files,
        'manifest_sha256': hashlib.sha256(raw).hexdigest(),
        'bundle_sha256': hashlib.sha256(bundle.read_bytes()).hexdigest(),
        'runtime_kit_sha256': runtime_kit_sha,'runtime_manifest_sha256':runtime_manifest_sha,
        'tests': manifest['tests'], 'groups': groups}, sort_keys=True), flush=True)
    print('AFFECTED_ACCEPTANCE=PASS TESTS=' + str(manifest['tests']), flush=True)


if __name__ == '__main__':
    main()
