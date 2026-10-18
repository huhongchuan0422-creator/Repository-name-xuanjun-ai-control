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
        assert raw == git('show', BASE + ':' + name), 'REVIEWED_CORE_CHANGED:' + name
        files[name] = hashlib.sha256(raw).hexdigest()
    added = ['production/p2_attempt5/assembly.py', 'production/p2_attempt5/entry.py',
             'production/p2_attempt5/verify.py', 'production/p2_attempt5/README.md',
             'production/p2_attempt5/registry.py', 'production/p2_attempt5/registry_cli.py',
             'tests/p2_production_assembly/test_registry.py',
             'tests/p2_production_assembly/test_assembly.py',
             '.github/workflows/p2-production-assembly.yml']
    for name in added:
        files[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    groups = []
    cases = [(str(ROOT / 'tests/p2_production_assembly'), 'test_registry.py', 50)]
    for index, (directory, pattern, count) in enumerate(cases):
        script = ('import sys,unittest;sys.path.insert(0,%r);'
                  'suite=unittest.defaultTestLoader.discover(%r,pattern=%r);'
                  'assert suite.countTestCases()==%d;'
                  'r=unittest.TextTestRunner(verbosity=2).run(suite);'
                  'assert r.wasSuccessful() and not r.skipped' %
                  (directory, directory, pattern, count))
        result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', script],
                                cwd=str(ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=240)
        log = output / ('tests-%d.log' % index)
        log.write_bytes(result.stdout)
        print(result.stdout.decode('utf-8'), flush=True)
        assert result.returncode == 0, 'AFFECTED_ACCEPTANCE_FAILED:' + pattern
        groups.append({'group': pattern, 'tests': count,
                       'log_sha256': hashlib.sha256(result.stdout).hexdigest()})
    manifest = {'schema': 1, 'source_commit': head, 'source_tree': tree,
                'reviewed_core_commit': BASE,
                'reviewed_core_tree': '2c2e3c09cbda31df30e0d269b580348c55e6de87',
                'inherited_kit_sha256': 'da3c42f6dd6d030c337ffb358be0cbe77c64eb0912016ebf30a353f65451d83f',
                'inherited_manifest_sha256': '41771b95c95b960cc643f06b1b3c622a880ed64a385d2f122322605b8abf106c',
                'files': files, 'groups': groups, 'tests': sum(g['tests'] for g in groups),
                'python': sys.version, 'production_binding': 'UNKNOWN',
                'trusted_config_entry': 'production/p2_attempt5/registry_cli.py',
                'registry_default_root': '/etc/xuanjun-p2/registry',
                'registry_deployment': 'NOT_EXECUTED',
                'inherited_assembly_ci_run': 39122271093,
                'inherited_assembly_tests_per_python': 83,
                'registry_review_fix': 'PR58_6250074905_R1_R2',
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
        hashlib.sha256(bundle.read_bytes()).hexdigest() + '  production-assembly.tar.gz\n')
    print('ARTIFACT_BINDING=' + json.dumps({
        'source_commit': head, 'source_tree': tree, 'files': files,
        'manifest_sha256': hashlib.sha256(raw).hexdigest(),
        'bundle_sha256': hashlib.sha256(bundle.read_bytes()).hexdigest(),
        'tests': manifest['tests'], 'groups': groups}, sort_keys=True), flush=True)
    print('AFFECTED_ACCEPTANCE=PASS TESTS=' + str(manifest['tests']), flush=True)


if __name__ == '__main__':
    main()
