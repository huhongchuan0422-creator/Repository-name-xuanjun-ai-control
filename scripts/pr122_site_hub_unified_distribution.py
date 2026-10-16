"""Freeze the unified Owner-only release wrapper; never installs or grants approval."""
import argparse,gzip,hashlib,io,json,tarfile
from pathlib import Path
from scripts import pr122_site_hub_unified_release as r
ROOT=Path(__file__).resolve().parents[1]
def build(candidate,output):
    pins=json.loads(r.PINS.read_bytes());raw=candidate.read_bytes();r.entries(raw,pins)
    old=(ROOT/'evidence/pr122-site-hub-experience/PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes()
    assert r.digest(old)=='b66eba8c958b10925064053f41dc575a6eb301616bc414d139cdddd98a2e7cb3'
    with tarfile.open(fileobj=io.BytesIO(old),mode='r:gz') as a:baseline=a.extractfile('pr122-site-hub/candidate-manifest.json').read()
    assert r.digest(baseline)==pins['previous_manifest_sha256']
    names=('scripts/pr122_site_hub_unified_release.py','scripts/pr122_site_hub_combined.py','scripts/pr122_site_hub_host_preflight.py','deploy/pr122-site-hub-unified/HOST_PINS.json')
    files={p:(ROOT/p).read_bytes() for p in names};files['inputs/PR122_SITE_HUB_REVIEW_ONLY.tar.gz']=raw;files['inputs/R2_CANDIDATE_MANIFEST.json']=baseline
    manifest={'schema':1,'state':'REVIEW_ONLY_NOT_APPROVED','transaction_id':pins['transaction_id'],'content_commit':pins['source_head'],'source_archive_sha256':pins['source_archive_sha256'],'source_archive_included':False,'files':[{'path':p,'size':len(b),'sha256':r.digest(b)} for p,b in sorted(files.items())]}
    files['DISTRIBUTION_MANIFEST.json']=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    output.mkdir(parents=True,exist_ok=False);buf=io.BytesIO()
    with gzip.GzipFile(filename='',fileobj=buf,mode='wb',mtime=0) as z,tarfile.open(fileobj=z,mode='w') as a:
        for name,b in sorted(files.items()):
            m=tarfile.TarInfo('pr122-unified-release/'+name);m.size=len(b);m.mode=0o644;a.addfile(m,io.BytesIO(b))
    raw=buf.getvalue();(output/'PR122_UNIFIED_RELEASE_REVIEW_ONLY.tar.gz').write_bytes(raw)
    receipt={'state':'REVIEW_ONLY_NOT_APPROVED','transaction_id':pins['transaction_id'],'tar_sha256':r.digest(raw),'distribution_manifest_sha256':r.digest(files['DISTRIBUTION_MANIFEST.json']),'wrapper_sha256':r.digest(files[names[0]]),'host_pins_sha256':r.digest(files[names[3]]),'member_count':7,'production_changes':0}
    (output/'UNIFIED_DISTRIBUTION_RECEIPT.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n');print(json.dumps(receipt));return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.candidate,a.output)
