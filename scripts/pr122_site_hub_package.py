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

def package(root,source,output,derive_navigation=False, delivery_review=False):
    if output.exists():raise ValueError('PACKAGE_OUTPUT_EXISTS')
    if sha(source.read_bytes())!=SOURCE_HASH:raise ValueError('SOURCE_HASH_MISMATCH')
    with tempfile.TemporaryDirectory() as td:
        stage=Path(td)/'stage'
        if delivery_review and not derive_navigation:raise ValueError('DELIVERY_REQUIRES_FULL_NAVIGATION_BUILD')
        if derive_navigation:build(root,source,stage,derive_navigation=True,delivery_review=delivery_review)
        else:build(root,source,stage)
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
        stage_binding=None
        if derive_navigation:
            stage_binding=json.loads((stage/'MANIFEST.json').read_bytes())
            if stage_binding.get('status')!='ISOLATED_INTEGRATION_CANDIDATE' or stage_binding.get('source_archive_sha256')!=SOURCE_HASH or stage_binding.get('production_approved') is not False:
                raise ValueError('FULL_SOURCE_STAGE_REQUIRED')
            if stage_binding.get('files')!={p:sha(raw) for p,raw in final.items()}:
                raise ValueError('FINAL_STAGE_MANIFEST_MISMATCH')
            if not stage_binding.get('navigation_derivation'):
                raise ValueError('NAVIGATION_PROVENANCE_REQUIRED')
        new_code=publisher_source(root)
        entries={'source-pin.json':canonical(pin),'candidate-manifest.json':canonical(manifest),'bin/pr122_website_release.py':new_code,
                 'PRODUCTION_EXECUTION.lock':b'REVIEW_ONLY. Independent approval and protected execution channel required.\n',
                 'PUBLISHER_PROVENANCE.json':canonical({'base_source_sha256':BASE_SHA256,'candidate_source_sha256':sha(new_code),'change':'Explicit absent-baseline new files; collision rejection; exclusive create; final manifest verification; original installed publisher unchanged'}),
                 'RELEASE_GATE.json':canonical({'state':'HOLD','production_approved':False,'expected_live_baseline_digest':'a05cf7c23e8ad3a8f63f7af07b68e0219fc79cc4c0c417ded86e2a947054fe09','unresolved':['Independent approval of exact bundle, publisher delta and isolated preview runtime','Protected combined host execution path admission','Target-host runtime and Nginx validation','Production browser HTTPS and rollback acceptance'],'simulation_service_included':True,'simulation_service_production_approved':False})}
        if derive_navigation:
            entries['FULL_SOURCE_STAGE_MANIFEST.json']=canonical(stage_binding)
            entries['BUILD_PROVENANCE.json']=canonical({'scope':'FULL_PINNED_SOURCE_REVIEW_CANDIDATE','production_approved':False,'source_archive_sha256':SOURCE_HASH,'stage_manifest_sha256':sha(entries['FULL_SOURCE_STAGE_MANIFEST.json']),'mechanisms':[{'path':name,'sha256':sha((root/name).read_bytes())} for name in ('scripts/pr122_site_hub_package.py','scripts/pr122_site_hub_stage.py','scripts/pr122_community_experience_package.py','scripts/pr122_site_hub_unified_package.py','demos/work-community-experience/role.js')]})
        entries.update({'overlay/public/'+p:raw for p,raw in changed.items()})
        runtime=sorted((root/'scripts').glob('community_*.py'))+[root/'scripts/pr122_site_hub_preview.py']
        entries.update({'runtime/scripts/'+p.name:p.read_bytes() for p in runtime})
        entries.update({'runtime-config/'+p.name:p.read_bytes() for p in sorted((root/'deploy/pr122-site-hub-preview').glob('*')) if p.is_file()})
        entries['RUNTIME_MANIFEST.json']=canonical({'scope':'In-memory synthetic preview only','files':[{'path':p,'size':len(raw),'sha256':sha(raw)} for p,raw in sorted(entries.items()) if p.startswith(('runtime/','runtime-config/'))]})
        package_schema='FULL_STATIC_REVIEW_V1' if derive_navigation else None
        if derive_navigation and 'brand_projection' in stage_binding and not delivery_review:
            brand_contract={'schema':'FULL_STATIC_BRAND_REVIEW_V1','brand':'玄钧AI新','archive_members':1241,'overlay_files':1197,'new_files':101,'public_files':1288}
            if (stage_binding['brand_projection'].get('brand')!=brand_contract['brand'] or len(entries)+1!=1241 or len(changed)!=1197 or len(final)!=1288 or sum(v is None for v in baselines.values())!=101):
                raise ValueError('BRAND_PACKAGE_CONTRACT')
            provenance=json.loads(entries['BUILD_PROVENANCE.json'])
            provenance['brand_contract']=brand_contract
            entries['BUILD_PROVENANCE.json']=canonical(provenance)
            package_schema=brand_contract['schema']
        if delivery_review:
            provenance=json.loads(entries['BUILD_PROVENANCE.json'])
            provenance['delivery_review']=stage_binding['delivery_review']
            provenance['mechanisms'].append({'path':'scripts/pr122_delivery_host.py','sha256':sha((root/'scripts/pr122_delivery_host.py').read_bytes())})
            provenance['brand_contract']={'schema':'FULL_STATIC_DELIVERY_REVIEW_V1','brand':'玄钧AI新','archive_members':1256,'overlay_files':1212,'new_files':116,'public_files':1303}
            if len(entries)+1!=1256 or len(changed)!=1212 or len(final)!=1303 or sum(v is None for v in baselines.values())!=116:raise ValueError('DELIVERY_PACKAGE_CONTRACT')
            provenance['parent_brand_contract']={'schema':'FULL_STATIC_BRAND_REVIEW_V1','archive_members':1241,'public_files':1288}
            entries['BUILD_PROVENANCE.json']=canonical(provenance)
            package_schema='FULL_STATIC_DELIVERY_REVIEW_V1'
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
        receipt={'state':'REVIEW_ONLY_NOT_APPROVED','package_schema':package_schema,'source_archive_sha256':SOURCE_HASH,'public_file_count':len(final),'overlay_file_count':len(changed),'new_file_count':sum(v is None for v in baselines.values()),'tar_sha256':sha(archive_path.read_bytes()),'package_manifest_sha256':sha(entries['PACKAGE_MANIFEST.json']),'candidate_manifest_sha256':sha(entries['candidate-manifest.json']),'publisher_source_sha256':sha(new_code),'production_deployed':False}
        (output/'PACKAGE_RECEIPT.json').write_bytes(canonical(receipt));print(json.dumps(receipt,sort_keys=True));return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--derive-navigation',action='store_true');p.add_argument('--delivery-review',action='store_true');a=p.parse_args()
    package(Path(__file__).resolve().parents[1],a.source_archive,a.output,a.derive_navigation,a.delivery_review)
