"""Run only root-installed immutable source under isolated Python."""
import os
import hashlib
import json
from pathlib import Path
import stat
import sys

location=Path(__file__).resolve()
root=location.parents[3]
for item in (location,)+tuple(location.parents):
    s=item.lstat()
    if s.st_uid!=0 or s.st_mode & 0o022:
        raise SystemExit('HOLD_OAUTH_SOURCE_OWNERSHIP')
manifest=root/'deployment/cloud-connection/oauth/SOURCE_MANIFEST.json'
metadata=manifest.lstat()
if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=0
        or metadata.st_mode & 0o022 or metadata.st_nlink!=1 or metadata.st_size>262144):
    raise SystemExit('HOLD_OAUTH_SOURCE_MANIFEST_METADATA')
raw=manifest.read_bytes()
if hashlib.sha256(raw).hexdigest()!=os.environ.get('OAUTH_SOURCE_MANIFEST_SHA256'):
    raise SystemExit('HOLD_OAUTH_SOURCE_MANIFEST')
for entry in json.loads(raw)['files']:
    path=entry['path']
    if path.startswith('/') or any(p in ('','.','..') for p in path.split('/')):
        raise SystemExit('HOLD_OAUTH_SOURCE_PATH')
    target=root/path
    for item in (target,)+tuple(target.parents):
        s=item.lstat()
        if s.st_uid!=0 or s.st_mode & 0o022 or stat.S_ISLNK(s.st_mode):
            raise SystemExit('HOLD_OAUTH_SOURCE_OWNERSHIP')
    if target.stat().st_size!=entry['bytes'] or hashlib.sha256(target.read_bytes()).hexdigest()!=entry['sha256']:
        raise SystemExit('HOLD_OAUTH_SOURCE_HASH')
sys.path.insert(0,str(root))
from production.cloud_connection.oauth_entrypoint import main
if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('HOLD_OAUTH_STARTUP') from None
