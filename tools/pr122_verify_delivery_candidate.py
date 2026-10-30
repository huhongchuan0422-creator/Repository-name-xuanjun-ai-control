from pathlib import Path
import tempfile,shutil,importlib.util,argparse,contextlib,io,json,hashlib,tarfile,zipfile
from scripts import pr122_site_hub_unified_release as release
from scripts.pr122_delivery_host import FROZEN
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--brand',type=Path,required=True);args=parser.parse_args()
folder=args.candidate/'bundle';receipt=json.loads(folder.parent.joinpath('PACKAGE_RECEIPT.json').read_text())
pins={'static_artifact_sha256':receipt['tar_sha256'],'package_manifest_sha256':receipt['package_manifest_sha256'],'candidate_manifest_sha256':receipt['candidate_manifest_sha256'],'package_schema':receipt['package_schema'],'source_archive_sha256':receipt['source_archive_sha256'],'publisher_sha256':receipt['publisher_source_sha256'],'full_stage_manifest_sha256':hashlib.sha256((folder/'FULL_SOURCE_STAGE_MANIFEST.json').read_bytes()).hexdigest(),'build_provenance_sha256':hashlib.sha256((folder/'BUILD_PROVENANCE.json').read_bytes()).hexdigest()}
raw=(folder.parent/'PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes();files=release.entries(raw,pins)
print('EXACT_WRAPPER_ENTRIES_PASS',len(files))
with tempfile.TemporaryDirectory() as td:
 work=Path(td);source=work/'source.tar.gz';shutil.copyfile(args.source,source)
 bundle=work/'bundle';shutil.copytree(folder,bundle)
 spec=importlib.util.spec_from_file_location('nativepub',bundle/'bin/pr122_website_release.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 a=argparse.Namespace(webroot_base=work/'webroot',bundle=bundle,source_archive=source,transaction_id='delivery-local',release_id='delivery-local',approved_package_manifest_sha256=receipt['package_manifest_sha256'],lock_wait_seconds=5,deadline_seconds=120,allow_non_root_test=True)
 with contextlib.redirect_stdout(io.StringIO()):m.prepare(a);m.activate(a);m.check(a)
 public=work/'webroot/releases/delivery-local/public'
 assert len([p for p in public.rglob('*') if p.is_file()])==1303
 for name,h in FROZEN.items():assert hashlib.sha256((public/'delivery/community-next'/name).read_bytes()).hexdigest()==h
 # Reconstruct the received exact brand package, not a rebuilt approximation.
 old={}
 with tarfile.open(source) as t:
  for x in t:
   if x.isfile() and x.name.startswith('package/public/'):old[x.name[len('package/public/'):]]=t.extractfile(x).read()
 with zipfile.ZipFile(args.brand) as z:
  with tarfile.open(fileobj=io.BytesIO(z.read('PR122_SITE_HUB_REVIEW_ONLY.tar.gz')),mode='r:gz') as t:
   for x in t:
    prefix='pr122-site-hub/overlay/public/'
    if x.name.startswith(prefix):old[x.name[len(prefix):]]=t.extractfile(x).read()
 assert len(old)==1288
 unexpected=[];changed=0
 for name,before in old.items():
  after=(public/name).read_bytes()
  if after==before:continue
  changed+=1
  for addition in ['<a href="/delivery/">开发中项目</a><a href="/delivery/cases.html">已完成案例</a>','<a href="/delivery/">Developing projects · Chinese review</a><a href="/delivery/cases.html">Completed cases</a>']:
   after=after.replace(addition.encode(),b'')
  after=after.replace('href="/delivery/">查看开发中的作品'.encode(),'href="/visual/community-payment/">查看开发中的作品'.encode())
  if after!=before:unexpected.append(name)
 assert not unexpected,unexpected
 print('ORIGINAL_BRAND_1288_RETAINED_ONLY_NAV_DIFF',changed)
 with contextlib.redirect_stdout(io.StringIO()):m.rollback(a)
 print('ORIGINAL_PUBLISHER_PREPARE_ACTIVATE_CHECK_ROLLBACK_ISOLATED_PASS')
(args.candidate/'VALIDATION_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
