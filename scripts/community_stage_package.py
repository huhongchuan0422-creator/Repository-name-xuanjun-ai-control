"""Deterministic allowlisted offline review package; never an installer."""
import hashlib
import io
import json
import zipfile
from pathlib import Path


def build(root):
    root = Path(root)
    patterns = ('scripts/community_*.py', 'scripts/community_*.cjs', 'tests/test_community_*.py',
                'tests/test_stage5_*.py', 'demos/community-local-e2e/*',
                'demos/community-stage/*', 'demos/community-payment/*',
                'demos/community-admin/*', 'clients/community-mini/*.js',
                'clients/community-mini/*.json', 'clients/community-mini/*.cjs',
                'clients/community-mini/pages/checkout/*',
                'docs/development/COMMUNITY_STAGE_INTEGRATION_20261017.md',
                'scripts/pr122_customer_core.py',
                'docs/development/COMMUNITY_PINNED_DEPENDENCIES_20261017.json')
    paths = sorted({p for pattern in patterns for p in root.glob(pattern) if p.is_file()})
    files = {}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('PACKAGE_SYMLINK_DENIED')
        files[path.relative_to(root).as_posix()] = path.read_bytes()
    required = {'scripts/community_stage_local.py', 'scripts/community_stage_runtime.py',
                'scripts/community_stage_package.py', 'clients/community-mini/app.json'}
    if not required.issubset(files):
        raise ValueError('REQUIRED_SOURCE_MISSING')
    manifest = {'format': 1, 'purpose':'OFFLINE_SOURCE_CANDIDATE_NOT_INSTALLABLE',
                'production_payment':'HOLD', 'production_deployment':'HOLD',
                'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    files['MANIFEST.json'] = json.dumps(manifest, sort_keys=True, separators=(',',':')).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name,data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026,1,1,0,0,0))
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info,data)
    data = buffer.getvalue()
    return data, hashlib.sha256(data).hexdigest()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    data,digest=build(Path(__file__).resolve().parents[1])
    # Never replace an existing review artifact silently.
    with open(args.output,'xb') as out:out.write(data)
    print('OFFLINE_PACKAGE_SHA256='+digest)
