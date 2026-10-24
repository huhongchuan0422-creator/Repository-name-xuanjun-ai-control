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
    frozen={'loader.py':'393b9c3f3e5720a1a9164aaafba0f2198fd5e461c49c4e58859c497ef5100f19',
        'scripts/community_preview_release_plan.py':'e0870cfaf7f1bb16b8664e644ec616e150b0ada93146a8d955e64c5f3f7ec4b9',
        'scripts/community_preview_update_checkpoint.py':'a73c1fe8ebb71abaefeb56ca880057e23876b5c005d315e4fb1268d3087064fd',
        'scripts/community_preview_update_composition.py':'f3007cdd26d53e7348164d404186602335ee5f237963f5d6f627e5376cfdc4f1',
        'scripts/community_preview_upgrade.py':'2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee',
        'scripts/community_preview_version_inspect.py':'98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3',
        'deploy/community-preview/f131-image-receipt.json':'cba144af0ca2f753413f7bdcec92625c370c479c4708b1d4a1db0b35907c8b45'}
    if set(files)!=set(frozen) or any(hashlib.sha256(b).hexdigest()!=frozen[p] for p,b in files.items()):
        raise ValueError('FROZEN_V1_SOURCE_ONLY_USE_BC_BUILD')
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
