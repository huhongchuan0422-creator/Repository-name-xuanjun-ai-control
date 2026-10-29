"""Reproduce one approved carrier, never execute its payload or rebuild its image."""
import base64
import hashlib
import json
import sys
import zipfile
from pathlib import Path

IMAGE_BYTES = 532397655
IMAGE_SHA = '6b441ee1af9bdc3283eec7dd05d4961058c261379ae6254e97e10728d1a56e11'
OUTPUT_BYTES = 532542883
OUTPUT_SHA = '392cda2ca9866f55d3479887a0379b224a2c4186fda5663169af55c0e365c738'
NAME = 'COMMUNITY_STAGE_A_06053_TO_C19DB7_81a7c88af819.zip'

def assemble(image, destination):
    raw = Path(image).read_bytes()
    if len(raw) != IMAGE_BYTES or hashlib.sha256(raw).hexdigest() != IMAGE_SHA:
        raise ValueError('FIXED_IMAGE_ARTIFACT_MISMATCH')
    records = json.loads(Path(__file__).with_name('members.json').read_text())
    expected = {'community_preview_site_prepare.py', 'control-06053-to-c19db7-v1.zip',
                'manifest.json', 'prepare-site.sh', 'stage-a-entry.py'}
    if set(records) != expected:
        raise ValueError('FIXED_MEMBER_SET_MISMATCH')
    blobs = {'artifact12832817699.zip': raw}
    for name, record in records.items():
        data = base64.b64decode(record['base64'], validate=True)
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('FIXED_MEMBER_MISMATCH')
        blobs[name] = data
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / NAME
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(blobs.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 28, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, data)
    digest = hashlib.file_digest(output.open('rb'), 'sha256').hexdigest()
    if output.stat().st_size != OUTPUT_BYTES or digest != OUTPUT_SHA:
        output.unlink()
        raise ValueError('COMPLETE_CARRIER_MISMATCH')
    receipt = {'status': 'BYTE_IDENTICAL_CARRIER_ONLY', 'file': NAME,
               'bytes': OUTPUT_BYTES, 'sha256': digest, 'source_artifact_id': 12832817699,
               'site_downloaded': False, 'site_executed': False}
    (destination / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))

if __name__ == '__main__':
    assemble(sys.argv[1], sys.argv[2])
