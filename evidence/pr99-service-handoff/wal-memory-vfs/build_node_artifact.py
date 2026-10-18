"""Reproducible source-only node package; no generated databases or credentials."""
import ctypes
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

FILES = ('README.md', 'build_node_artifact.py', 'lost_invoke_reconciliation.py',
         'sqlite_wal_vfs.py', 'test_lost_invoke_reconciliation.py', 'test_sqlite_wal_vfs.py')


def build(root, output, commit, tree):
    assert re.fullmatch('[0-9a-f]{40}', commit) and re.fullmatch('[0-9a-f]{40}', tree)
    root, output = Path(root), Path(output)
    files = {name: (root/name).read_bytes() for name in FILES}
    manifest = {'schema': 1, 'source_commit': commit, 'source_tree': tree,
        'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        'production_entry': False, 'M99_dynamic_acceptance': 'NOT_RUN'}
    files['MANIFEST.json'] = (json.dumps(manifest, sort_keys=True, indent=2)+'\n').encode()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0)); info.external_attr = 0o100600 << 16
            info.compress_type = zipfile.ZIP_DEFLATED; z.writestr(info, raw)
    lib = ctypes.CDLL('libsqlite3.so.0'); lib.sqlite3_libversion.restype = ctypes.c_char_p
    receipt = {'schema': 1, 'source_commit': commit, 'source_tree': tree,
        'artifact_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'artifact_bytes': output.stat().st_size, 'members': len(files),
        'sqlite_version': lib.sqlite3_libversion().decode(), 'production_installed': False}
    output.with_suffix('.receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    commit = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    tree = subprocess.check_output(['git','rev-parse','HEAD^{tree}'], text=True).strip()
    print(json.dumps(build(Path(__file__).parent, 'pr99-wal-reconciliation-node.zip', commit, tree), sort_keys=True))
