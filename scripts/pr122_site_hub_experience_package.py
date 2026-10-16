#!/usr/bin/env python3
"""Package a review-only UI update; never access or activate production."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
from scripts import pr122_site_hub_experience_release as release

ROOT=Path(__file__).resolve().parents[1]

def build(output):
    pins=json.loads(release.PINS.read_text());folder=ROOT/'evidence/pr122-site-hub-experience'
    raw=(folder/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes();release.entries(raw,pins)
    old=(ROOT/'evidence/pr122-site-hub/PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes()
    release.need(release.digest(old)=='dcf96b124cea6170453bdec52e60fc94d157864f342e2d1706801d54568abafb','OLD_PACKAGE_HASH')
    with tarfile.open(fileobj=io.BytesIO(old),mode='r:gz') as archive:
        baseline=archive.extractfile('pr122-site-hub/candidate-manifest.json').read()
    release.need(release.digest(baseline)==pins['previous_manifest_sha256'],'BASELINE_MANIFEST_HASH')
    files={name:(ROOT/name).read_bytes() for name in (
        'scripts/pr122_site_hub_experience_release.py','scripts/pr122_site_hub_combined.py',
        'scripts/pr122_site_hub_host_preflight.py','deploy/pr122-site-hub-experience/HOST_PINS.json')}
    files['inputs/PR122_SITE_HUB_REVIEW_ONLY.tar.gz']=raw
    files['inputs/R2_CANDIDATE_MANIFEST.json']=baseline
    manifest={'schema':1,'state':'REVIEW_ONLY_NOT_APPROVED','content_commit':pins['source_head'],
              'transaction_id':pins['transaction_id'],'source_archive_included':False,
              'source_archive_sha256':pins['source_archive_sha256'],
              'files':[{'path':name,'size':len(data),'sha256':release.digest(data)} for name,data in sorted(files.items())]}
    files['DISTRIBUTION_MANIFEST.json']=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    output.mkdir(parents=True,exist_ok=True);stream=io.BytesIO()
    with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as archive:
        for name,data in sorted(files.items()):
            member=tarfile.TarInfo('pr122-ui-release/'+name);member.size=len(data);member.mode=0o644
            archive.addfile(member,io.BytesIO(data))
    package=stream.getvalue();(output/'PR122_EXPERIENCE_RELEASE_REVIEW_ONLY.tar.gz').write_bytes(package)
    receipt={'state':'REVIEW_ONLY_NOT_APPROVED','transaction_id':pins['transaction_id'],'tar_sha256':release.digest(package),
             'distribution_manifest_sha256':release.digest(files['DISTRIBUTION_MANIFEST.json']),
             'wrapper_sha256':release.digest(files['scripts/pr122_site_hub_experience_release.py']),
             'host_pins_sha256':release.digest(files['deploy/pr122-site-hub-experience/HOST_PINS.json']),
             'member_count':len(files),'production_changes':0}
    (output/'EXPERIENCE_RELEASE_RECEIPT.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print(json.dumps(receipt,sort_keys=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    build(parser.parse_args().output)
