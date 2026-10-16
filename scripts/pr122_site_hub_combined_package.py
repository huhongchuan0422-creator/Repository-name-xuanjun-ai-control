"""Deterministic REVIEW-ONLY outer distribution; never emits release approval."""
import argparse
import gzip
import io
import json
from pathlib import Path
import tarfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.pr122_site_hub_combined import sha,canonical,verified_entries

def build(root,output,source=None):
    if output.exists():raise ValueError('OUTPUT_EXISTS')
    pins=json.loads((root/'deploy/pr122-site-hub-combined/HOST_PINS.json').read_text())
    frozen=root/'evidence/pr122-site-hub/PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
    if not frozen.exists():frozen=root/'review-package-preview-final/PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
    verified_entries(frozen.read_bytes(),pins)
    paths=['scripts/pr122_site_hub_combined.py','scripts/pr122_site_hub_host_preflight.py','deploy/pr122-site-hub-combined/HOST_PINS.json','deploy/pr122-site-hub-combined/README.md']
    entries={p:(root/p).read_bytes() for p in paths}
    entries['inputs/PR122_SITE_HUB_REVIEW_ONLY.tar.gz']=frozen.read_bytes()
    if source is not None:
        raw=source.read_bytes()
        if sha(raw)!=pins['source_archive_sha256']:raise ValueError('SOURCE_ARCHIVE_HASH')
        entries['inputs/PR122_TOKYO_WEBROOT_MIGRATION_SOURCE_0363531ee2f8.tar.gz']=raw
    entries['RELEASE_STATUS.json']=canonical({'decision':'HOLD','production_approved':False,'source_head':pins['source_head'],'external_original_source_required':source is None,
        'wrapper_sha256':sha(entries[paths[0]]),'host_pins_sha256':sha(entries[paths[2]]),'independent_wrapper_review':'PENDING','production_deployed':False})
    entries['DISTRIBUTION_MANIFEST.json']=canonical({'scope':'REVIEW_ONLY_NO_RELEASE_APPROVAL','files':[{'path':p,'size':len(raw),'sha256':sha(raw)} for p,raw in sorted(entries.items())]})
    output.mkdir(parents=True)
    archive_path=output/'PR122_SITE_HUB_COMBINED_REVIEW_ONLY.tar.gz'
    with archive_path.open('wb') as stream,gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as archive:
        for name,raw in sorted(entries.items()):
            member=tarfile.TarInfo('pr122-site-hub-combined/'+name);member.size=len(raw);member.mode=0o644;archive.addfile(member,io.BytesIO(raw))
    receipt={'state':'REVIEW_ONLY_HOLD','archive_sha256':sha(archive_path.read_bytes()),'distribution_manifest_sha256':sha(entries['DISTRIBUTION_MANIFEST.json']),
             'wrapper_sha256':sha(entries[paths[0]]),'pins_sha256':sha(entries[paths[2]]),'member_count':len(entries),'includes_original_source':source is not None,'production_deployed':False}
    (output/'PACKAGE_RECEIPT.json').write_bytes(canonical(receipt));print(json.dumps(receipt,sort_keys=True));return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--source-archive',type=Path);a=p.parse_args()
    build(Path(__file__).resolve().parents[1],a.output,a.source_archive)
