"""Offline exact static-controller source closure. No permit or target writes.
The resulting review-only source archive is separate from the approved public
content archive; neither is execution permission. Never package private pins,
trust stores, receipts, credentials or configuration.
"""
import argparse,gzip,hashlib,io,json,os,re,tarfile
from pathlib import Path
MODULES=('community_merchant_contract','pr122_customer_attempts','pr122_customer_change_authority','pr122_customer_changes','pr122_customer_core','pr122_customer_delivery_source','pr122_customer_edit_jobs','pr122_customer_http','pr122_customer_preview','pr122_customer_profile','pr122_customer_providers','pr122_customer_publication_worker','pr122_customer_release','pr122_customer_review','pr122_customer_small_edit','pr122_customer_source','pr122_customer_workflow','pr122_site_hub_combined','pr122_site_hub_host_preflight','pr122_site_hub_unified_release','pr122_static_github_approval','pr122_static_operations','pr122_static_workflow')
def build(root,commit):
 if type(commit) is not str or re.fullmatch('[0-9a-f]{40}',commit) is None:raise ValueError('EXACT_SOURCE_COMMIT_REQUIRED')
 root=Path(root);files={}
 for module in MODULES:
  name='scripts/'+module+'.py';p=root/name
  if any(q.is_symlink() for q in (p,*p.parents)) or not p.is_file():raise ValueError('UNTRUSTED_SOURCE_PATH:'+name)
  files[name]=p.read_bytes()
 rows=[dict(path=n,size=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in sorted(files.items())]
 manifest=(json.dumps(dict(schema=1,source_commit=commit,files=rows),sort_keys=True,indent=2)+'\n').encode()
 files['STATIC_SOURCE_MANIFEST.json']=manifest
 stream=io.BytesIO()
 with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0,filename='') as zipped:
  with tarfile.open(fileobj=zipped,mode='w') as archive:
   for name,data in sorted(files.items()):
    info=tarfile.TarInfo('pr122-static-controlled/'+name);info.size=len(data);info.mode=0o644;info.mtime=0;archive.addfile(info,io.BytesIO(data))
 raw=stream.getvalue()
 return raw,dict(scope='STATIC_CONTROLLER_SOURCE_REVIEW_ONLY',source_commit=commit,source_members=len(files),source_bindings=len(rows),archive_sha256=hashlib.sha256(raw).hexdigest(),manifest_sha256=hashlib.sha256(manifest).hexdigest(),installation_permission='NOT_ISSUED',public_content_included=False)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-commit',default=os.environ.get('GITHUB_SHA'));a=p.parse_args()
 raw,report=build(Path(__file__).resolve().parents[1],a.source_commit)
 a.output.mkdir(parents=True,exist_ok=False)
 (a.output/'PR122_STATIC_CONTROLLED_SOURCE_REVIEW_ONLY.tar.gz').write_bytes(raw)
 (a.output/'STATIC_SOURCE_BINDING.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
