"""Offline-only deterministic delta package preparation. NEVER installs or resumes.

Inputs: the original verified 102-file package and the two exact source repairs.
Outputs: a new directory/archive and a delta receipt. Host plans and activation
are deliberately not rewritten; a new independently reviewed recovery is needed.
"""
import argparse
import hashlib
import json
import os
import pathlib
import runpy

OLD_MANIFEST = '9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3'
FREEZER_SHA = 'f1fe5dc3e199fe891a89969c07612304803ee453ee79e165815eab776eb6bb8e'
SOURCE_COMMIT = 'bb6ed0d40eabbb535623b0a5341cddedc9b9e38a'
SOURCE_TREE = '5c18914a59172d9a005dafaae3d4c86701240210'
REPAIRS = {
    'stage1/p2_fixed_host_runtime.py': '83ca91a597c3220c40a4de37c8af211463dba13eb36eac55a8802c12d5a36ac2',
    'stage1/p2_tls_lifecycle.py': 'd890732f39b4dd9e0134fa7c26aa2f0a79deacef3e2e0f2d30e5280c903070db',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, label):
    if not value:
        raise ValueError(label)


def build(original, fixes, output):
    original, fixes, output = map(pathlib.Path, (original, fixes, output))
    manifest_path = 'deploy/integration-manifest.json'
    verifier_path = 'tools/p2-package-freeze.py'
    original_bytes = (original / manifest_path).read_bytes()
    require(sha(original_bytes) == OLD_MANIFEST, 'ORIGINAL_MANIFEST_CHANGED')
    verifier = (original / verifier_path).read_bytes()
    require(sha(verifier) == FREEZER_SHA, 'FREEZER_CHANGED')
    namespace = {'__name__': 'p2_offline_freezer', '__file__': str(original / verifier_path)}
    exec(compile(verifier, str(original / verifier_path), 'exec'), namespace)
    unused, manifest, payload, unused_verifier = namespace['checked_inputs'](
        str(original), manifest_path, verifier_path)
    require(len(payload) == 102 and set(REPAIRS).issubset(payload), 'ORIGINAL_102_REQUIRED')
    delta = []
    for relative, expected in sorted(REPAIRS.items()):
        data = namespace['read_regular'](str(fixes), pathlib.Path(relative).name)
        require(sha(data) == expected, 'REPAIR_SOURCE_CHANGED')
        compile(data, relative, 'exec')
        delta.append({'path': relative, 'old_sha256': manifest['files'][relative],
                      'new_sha256': expected})
        payload[relative] = data
        manifest['files'][relative] = expected
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    require(not output.exists() and not os.path.lexists(str(output)), 'OUTPUT_ALREADY_EXISTS')
    output.mkdir(mode=0o700)
    root = output / 'xuanjun-p2-package'
    for relative, data in sorted(list(payload.items()) + [(manifest_path, manifest_bytes),
                                                          (verifier_path, verifier)]):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        target.chmod(0o555 if relative == verifier_path else 0o444)
    archive = output / 'epoch5-runtime-candidate.tar.gz'
    result = namespace['build'](str(root), manifest_path, verifier_path, str(archive),
                                SOURCE_COMMIT, SOURCE_TREE)
    namespace['verify'](str(archive), result['archive_sha256'], SOURCE_COMMIT, SOURCE_TREE)
    receipt = {'schema': 1, 'kind': 'OFFLINE_RUNTIME_DELTA_NOT_INSTALL_ADMISSION',
               'base_manifest_sha256': OLD_MANIFEST, 'manifest_sha256': sha(manifest_bytes),
               'archive_sha256': result['archive_sha256'], 'runtime_files': 102,
               'unchanged_runtime_files': 100, 'changed_runtime_files': delta,
               'source_commit': SOURCE_COMMIT, 'source_tree': SOURCE_TREE,
               'production_execution': 'NOT_RUN', 'independent_review': 'PENDING',
               'epoch5_recovery_entrypoint': 'NOT_IMPLEMENTED',
               'old_install_or_resume_entrypoint_permitted': False}
    (output / 'delta-receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', required=True)
    parser.add_argument('--fixes', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.original, args.fixes, args.output), sort_keys=True))
