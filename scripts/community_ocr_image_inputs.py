"""Reuse one original PR139 offline artifact; no model resolution or downloads."""
import argparse
import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath

BUNDLE_SHA='5d4ac9dad0badefaab20853cc4ceff0be9caf4c4501cebb4e318599007d662f6'
BUNDLE_BYTES=245599357
BASE_SHA='8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199'
BASE_PACKAGES={'cryptography','cffi','pycparser'}

def prepare(bundle,destination,verification_destination=None):
    bundle=Path(bundle);destination=Path(destination)
    if bundle.is_symlink() or not bundle.is_file() or bundle.stat().st_size!=BUNDLE_BYTES:raise ValueError('ORIGINAL_OCR_BUNDLE_REQUIRED')
    h=hashlib.sha256()
    with bundle.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    if h.hexdigest()!=BUNDLE_SHA:raise ValueError('ORIGINAL_OCR_BUNDLE_SHA_MISMATCH')
    if destination.exists() or destination.is_symlink():raise ValueError('EMPTY_OCR_BUILD_DIRECTORY_REQUIRED')
    verification=Path(verification_destination) if verification_destination is not None else None
    if verification is not None and (verification.exists() or verification.is_symlink()):raise ValueError('EMPTY_VERIFY_DIRECTORY_REQUIRED')
    with tarfile.open(bundle,'r:gz') as t:
        members=t.getmembers()
        if len(members)!=104 or len({m.name for m in members})!=104:raise ValueError('OCR_BUNDLE_MEMBERS_CHANGED')
        for m in members:
            p=PurePosixPath(m.name)
            if not m.isfile() or p.is_absolute() or str(p)!=m.name or '..' in p.parts or m.size>150_000_000:raise ValueError('OCR_BUNDLE_MEMBER_UNSAFE')
        manifest=json.load(t.extractfile('offline-bundle-manifest.json'))
        if manifest['base_image_manifest_sha256']!=BASE_SHA or manifest['target_platform']!='linux-x86_64-cp311':raise ValueError('OCR_BASE_ABI_MISMATCH')
        required={**manifest['source_files']}
        required.update({'models/'+i['filename']:i['sha256'] for i in manifest['models']})
        required.update({'wheelhouse/'+i['filename']:i['sha256'] for i in manifest['wheels']})
        debs=json.load(t.extractfile('system-deb-lock.json'))
        required.update({'system-debs/'+i['filename']:i['sha256'] for i in debs['packages']})
        for name,digest in required.items():
            if hashlib.sha256(t.extractfile(name).read()).hexdigest()!=digest:raise ValueError('OCR_INNER_SHA_MISMATCH')
        lock=json.loads(Path(__file__).with_name('community_ocr_dependency.json').read_text())
        for name,digest in lock.get('upstream_files',lock['files']).items():
            if required['services/ocr_engine/'+name]!=digest:raise ValueError('OCR_COMMUNITY_PIN_MISMATCH')
        destination.mkdir(mode=0o700)
        selected=('services/','models/','wheelhouse/','system-debs/')
        for m in members:
            if not m.name.startswith(selected) and m.name not in ('LICENSE-2.0.txt','NOTICE.md','offline-bundle-manifest.json','requirements-lock.json','system-deb-lock.json'):continue
            out=destination/m.name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(t.extractfile(m).read());out.chmod(0o644)
        # Verification-only originals, before successor substitution. These are
        # copied only to the verify stage, never the release image filesystem.
        if verification is not None:
            verification.mkdir(mode=0o700)
            for name,digest in lock.get('upstream_files',lock['files']).items():
                raw=t.extractfile('services/ocr_engine/'+name).read()
                if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('OCR_VERIFY_UPSTREAM_SHA_MISMATCH')
                out=verification/name;out.write_bytes(raw);out.chmod(0o644)
        successor=lock.get('local_successor',{})
        root=Path(__file__).resolve().parents[1]
        if successor:
            if hashlib.sha256((root/successor['patch_path']).read_bytes()).hexdigest()!=successor['patch_sha256']:
                raise ValueError('OCR_SUCCESSOR_PATCH_HASH_MISMATCH')
            for name,relative in successor['source_files'].items():
                raw=(root/relative).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=lock['files'][name]:raise ValueError('OCR_SUCCESSOR_SOURCE_HASH_MISMATCH')
                (destination/'services/ocr_engine'/name).write_bytes(raw)
        # Keep original community crypto/cffi/pycparser byte pins. The original
        # crypto METADATA accepts cffi>=2.0.0; no resolver or package downgrade.
        lines=[]
        for item in manifest['wheels']:
            name,version=item['filename'].split('-',2)[:2]
            if name not in BASE_PACKAGES:lines.append(name.replace('_','-')+'=='+version+' --hash=sha256:'+item['sha256'])
        (destination/'requirements-community-ocr.lock').write_text('\n'.join(lines)+'\n')
        return {'original_bundle_sha256':BUNDLE_SHA,'models':manifest['models'],'installed_ocr_wheels':len(lines),'preserved_base_packages':sorted(BASE_PACKAGES),'network_runtime':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bundle');p.add_argument('destination');p.add_argument('--verification-upstream');a=p.parse_args();print(json.dumps(prepare(a.bundle,a.destination,a.verification_upstream),sort_keys=True))
