"""Freeze one self-contained P2 candidate from the already reconstructed source tree.

Hosted packaging only. No model calls and no host mutation. Python 3.6 compatible.
"""
from __future__ import print_function

import hashlib
import json
import os
import pathlib
import shutil
import stat
import sys

ROOT = pathlib.Path(__file__).resolve().parent
OLD_FROZEN_SHA256 = '456ae23aa52e300021c9fb889df84d8eba34965769ce868e5ee6e43c29911a13'


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    if len(argv) != 3:
        raise SystemExit('usage: freeze_candidate.py SOURCE_ROOT DEST_ROOT')
    source = pathlib.Path(argv[1]).resolve()
    dest_root = pathlib.Path(argv[2]).resolve()
    if source.name != 'xuanjun-p2-package' or not source.is_dir():
        raise ValueError('reconstructed package root required')
    if dest_root.exists():
        raise ValueError('destination must not exist')
    dest_root.mkdir(mode=0o700, parents=True)
    dest = dest_root / 'xuanjun-p2-package'
    shutil.copytree(str(source), str(dest))

    files = []
    total = 0
    for item in sorted(dest.rglob('*'), key=lambda x: str(x.relative_to(dest))):
        rel = item.relative_to(dest).as_posix()
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('symlink forbidden: ' + rel)
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError('special file forbidden: ' + rel)
        total += info.st_size
        if total > 96 * 1024 * 1024:
            raise ValueError('candidate size limit')
        files.append({'path': rel, 'sha256': sha256_file(item), 'size': info.st_size})

    provenance = {
        'schema': 1,
        'state': 'FROZEN_CANDIDATE_NOT_RELEASED',
        'source_commit': os.environ.get('GITHUB_SHA', 'UNKNOWN'),
        'source_repository': os.environ.get('GITHUB_REPOSITORY', 'UNKNOWN'),
        'old_frozen_archive_sha256': OLD_FROZEN_SHA256,
        'native_patch_sha256': sha256_file(ROOT / 'native-wiring.patch'),
        'followup_overlay_sha256': sha256_file(ROOT / 'followup_overlay.py'),
        'controller_source_commit': os.environ.get('GITHUB_SHA', 'UNKNOWN'),
        'model_calls': 0,
        'uk_runtime': 'NOT_RUN_BY_PACKAGER',
        'release_gate': 'NOT_GRANTED',
        'file_count_before_metadata': len(files),
        'bytes_before_metadata': total,
    }
    prov_path = dest / 'P2_CANDIDATE_PROVENANCE.json'
    prov_path.write_text(json.dumps(provenance, sort_keys=True, separators=(',', ':')) + '\n',
                         encoding='utf-8')

    sums = []
    for item in sorted(dest.rglob('*'), key=lambda x: str(x.relative_to(dest))):
        if item.is_file() and item.name != 'SHA256SUMS':
            sums.append('%s  %s' % (sha256_file(item), item.relative_to(dest).as_posix()))
    (dest / 'SHA256SUMS').write_text('\n'.join(sums) + '\n', encoding='utf-8')
    print(json.dumps({
        'state': 'P2_CANDIDATE_TREE_FROZEN',
        'source_commit': provenance['source_commit'],
        'file_count': len(sums),
        'model_calls': 0,
        'release_gate': 'NOT_GRANTED'
    }, sort_keys=True))


if __name__ == '__main__':
    main(sys.argv)
