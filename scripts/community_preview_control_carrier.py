"""Offline exact root carrier archive, never an installer or image loader."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
from scripts import community_preview_root_loader as loader

ROOT=Path(__file__).resolve().parents[1]

def build():
    files={path:(ROOT/('scripts/community_preview_root_loader.py' if path=='loader.py' else path)).read_bytes() for path in sorted(loader.PATHS)}
    manifest=dict(format=1,install_root=loader.INSTALL_ROOT,updates_enabled=False,
        files={p:dict(sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),uid=0,mode='0600') for p,b in files.items()})
    raw=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for path,body in sorted(dict(files,**{'manifest.json':raw}).items()):
            info=zipfile.ZipInfo(path,(2026,10,24,0,0,0));info.create_system=3;info.external_attr=0o100600<<16
            z.writestr(info,body)
    return buffer.getvalue(),raw


if __name__=='__main__':
    archive,manifest=build();target=ROOT/'deploy/community-preview'
    (target/'control-oci2330-v1.zip').write_bytes(archive)
    (target/'control-oci2330-v1-manifest.json').write_bytes(manifest)
