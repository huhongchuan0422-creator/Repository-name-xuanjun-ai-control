"""Offline B5 source inventory and external binder. Never executes a release.

The runtime manifest covers every release_path in SOURCE_MANIFEST, excluding
tests and itself. The external binder is generated only after a real commit
and is deliberately outside the covered source set.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
ORDER = ('queue.py', 'worker.py', 'runtime.py', 'private_transfer.py',
         'credential_lifecycle.py', 'fixed_actions.py',
         'pr122_baseline_collector.py', 'archive_reader.py',
         'material_custody.py')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory():
    source = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_bytes())
    rows = []
    paths = set()
    for entry in source['files']:
        name = entry['bundle_path']
        raw = (ROOT / name).read_bytes()
        if len(raw) != entry['bytes'] or digest(raw) != entry['sha256']:
            raise ValueError('SOURCE_MANIFEST_BYTES_CHANGED:' + name)
        release = entry['release_path']
        if release is not None:
            if release in paths:
                raise ValueError('DUPLICATE_RELEASE_PATH')
            paths.add(release)
            rows.append({'path': release, 'bytes': len(raw),
                         'sha256': digest(raw)})
    rows.sort(key=lambda row: row['path'])
    pinned = {row['path']: row['sha256'] for row in rows}
    prefix = 'production/cloud_connection/'
    code_pin = digest(canonical([[name, pinned[prefix + name]]
                                 for name in ORDER]))
    return {'schema': 'B5_RUNTIME_SOURCE_V1', 'files': rows,
            'code_pin_sha256': code_pin,
            'source_manifest_sha256': digest((ROOT / 'SOURCE_MANIFEST.json').read_bytes())}


def git_bytes(*args):
    # Git blob contents are exact bytes, including the terminal LF.
    return subprocess.check_output(('git',) + args, cwd=str(ROOT),
                                   stderr=subprocess.DEVNULL)


def git(*args):
    # Only Git's textual identifiers/status receive line-ending normalization.
    return git_bytes(*args).decode().strip()


def binder(commit):
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('REAL_COMMIT_REQUIRED')
    if git('status', '--porcelain'):
        raise ValueError('WORKTREE_NOT_CLEAN')
    if git('rev-parse', 'HEAD') != commit:
        raise ValueError('COMMIT_NOT_CURRENT_HEAD')
    manifest = canonical(inventory()) + b'\n'
    path = 'plans/p2_b5_new19_offline_candidate/RUNTIME_SOURCE_MANIFEST.json'
    if git_bytes('show', commit + ':' + path) != manifest:
        raise ValueError('COMMITTED_RUNTIME_MANIFEST_CHANGED')
    return {'schema': 'B5_EXTERNAL_RELEASE_BINDER_V1',
            'release_commit': commit, 'release_tree': git('rev-parse', commit+'^{tree}'),
            'runtime_manifest_sha256': digest(manifest),
            'source_manifest_sha256': inventory()['source_manifest_sha256'],
            'code_pin_sha256': inventory()['code_pin_sha256'],
            'status': 'SOURCE_IDENTITY_ONLY_NOT_INSTALL_ADMISSION'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', help='Emit external binder for exact clean HEAD')
    args = parser.parse_args()
    print((canonical(binder(args.commit) if args.commit else inventory()) + b'\n').decode(),
          end='')


if __name__ == '__main__':
    main()
