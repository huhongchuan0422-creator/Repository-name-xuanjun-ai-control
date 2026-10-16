"""Prepare a deterministic review-only delta for the controlled PR122 publisher."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.pr122_site_hub_stage import build, SOURCE_HASH
from scripts.pr122_site_hub_release_delta import publisher_source, BASE_SHA256

def canonical(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()

def package(root,source,output):
    if output.exists():raise ValueError('PACKAGE_OUTPUT_EXISTS')
    if sha(source.read_bytes())!=SOURCE_HASH:raise ValueError('SOURCE_HASH_MISMATCH')
    with tempfile.TemporaryDirectory() as td:
        stage=Path(td)/'stage';build(root,source,stage)
        with tarfile.open(source) as archive:
            raw=archive.extractfile('package/MANIFEST.json').read()
            if sha(raw)!='d9157976ae67e89aba90a8de0d2c606ec62268c6b649d9ebe578f6c2619e0d6a':raise ValueError('SOURCE_MANIFEST_DRIFT')
            original={r['path']:r for r in json.loads(raw)['files']}
        public=stage/'public'
        final={p.relative_to(public).as_posix():p.read_bytes() for p in sorted(public.rglob('*')) if p.is_file()}
        changed={p:raw for p,raw in final.items() if p not in original or sha(raw)!=original[p]['sha256']}
        baselines={p:original[p]['sha256'] if p in original else None for p in changed}
        pin={'schema_version':2,'source_archive_sha256':SOURCE_HASH,'source_archive_size':source.stat().st_size,'overlay_baselines':baselines}
        manifest={'schema_version':2,'file_count':len(final),'files':[{'path':p,'size':len(raw),'sha256':sha(raw),'mode':'0644','uid':0,'gid':0} for p,raw in final.items()]}
        new_code=publisher_source(root)
        entries={'source-pin.json':canonical(pin),'candidate-manifest.json':canonical(manifest),'bin/pr122_website_release.py':new_code,
                 'PRODUCTION_EXECUTION.lock':b'REVIEW_ONLY. Independent approval and protected execution channel required.\n',
                 'PUBLISHER_PROVENANCE.json':canonical({'base_source_sha256':BASE_SHA256,'candidate_source_sha256':sha(new_code),'change':'Explicit absent-baseline new files; collision rejection; exclusive create; final manifest verification; original installed publisher unchanged'}),
                 'RELEASE_GATE.json':canonical({'state':'HOLD','production_approved':False,'expected_live_baseline_digest':'a05cf7c23e8ad3a8f63f7af07b68e0219fc79cc4c0c417ded86e2a947054fe09','unresolved':['Independent approval of exact bundle, publisher delta and isolated preview runtime','Protected combined host execution path admission','Target-host runtime and Nginx validation','Production browser HTTPS and rollback acceptance'],'simulation_service_included':True,'simulation_service_production_approved':False})}
        entries.update({'overlay/public/'+p:raw for p,raw in changed.items()})
        runtime=sorted((root/'scripts').glob('community_*.py'))+[root/'scripts/pr122_site_hub_preview.py']
        entries.update({'runtime/scripts/'+p.name:p.read_bytes() for p in runtime})
        entries.update({'runtime-config/'+p.name:p.read_bytes() for p in sorted((root/'deploy/pr122-site-hub-preview').glob('*')) if p.is_file()})
        entries['RUNTIME_MANIFEST.json']=canonical({'scope':'In-memory synthetic preview only','files':[{'path':p,'size':len(raw),'sha256':sha(raw)} for p,raw in sorted(entries.items()) if p.startswith(('runtime/','runtime-config/'))]})
        package_manifest={'schema_version':2,'files':[{'path':p,'size':len(raw),'sha256':sha(raw)} for p,raw in sorted(entries.items())]}
        entries['PACKAGE_MANIFEST.json']=canonical(package_manifest)
        output.mkdir(parents=True)
        bundle=output/'bundle'
        for p,raw in entries.items():
            target=bundle/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        archive_path=output/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz'
        with archive_path.open('wb') as stream,gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as archive:
            for name,raw in sorted(entries.items()):
                member=tarfile.TarInfo('pr122-site-hub/'+name);member.size=len(raw);member.mode=0o644;member.mtime=0;archive.addfile(member,io.BytesIO(raw))
        receipt={'state':'REVIEW_ONLY_NOT_APPROVED','source_archive_sha256':SOURCE_HASH,'public_file_count':len(final),'overlay_file_count':len(changed),'new_file_count':sum(v is None for v in baselines.values()),'tar_sha256':sha(archive_path.read_bytes()),'package_manifest_sha256':sha(entries['PACKAGE_MANIFEST.json']),'candidate_manifest_sha256':sha(entries['candidate-manifest.json']),'publisher_source_sha256':sha(new_code),'production_deployed':False}
        (output/'PACKAGE_RECEIPT.json').write_bytes(canonical(receipt));print(json.dumps(receipt,sort_keys=True));return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    package(Path(__file__).resolve().parents[1],a.source_archive,a.output)
