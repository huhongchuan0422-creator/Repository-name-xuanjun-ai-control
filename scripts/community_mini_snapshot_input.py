"""Offline exact snapshot stage. No credentials, provider calls, workflow or authority."""
import hashlib,json,pathlib,re,os,tempfile,shutil,zipfile,stat

def sha(b):return hashlib.sha256(b).hexdigest()
def need(ok,why):
 if not ok:raise ValueError(why)
def prepare(archive,manifest_raw,expected_manifest_sha,expected_zip_sha,destination):
 # Pins are explicit caller inputs; never derive approval from archive contents.
 need(sha(manifest_raw)==expected_manifest_sha,'MANIFEST_PIN_MISMATCH')
 need(sha(archive)==expected_zip_sha,'ZIP_PIN_MISMATCH')
 m=json.loads(manifest_raw);need(m.get('format')==1 and m.get('file_count')==51,'EXACT_SNAPSHOT_FORMAT')
 files=m.get('files');need(type(files)is dict and len(files)==51,'COMPLETE_51_FILE_MANIFEST')
 for n,h in files.items():
  need(type(n)is str and re.fullmatch(r'[A-Za-z0-9_./-]+',n) and not n.startswith('/') and all(x not in ('','..','.') for x in n.split('/')),'UNSAFE_PATH')
  need(type(h)is str and re.fullmatch('[0-9a-f]{64}',h),'BAD_FILE_PIN')
 need('CONNECTED_PREVIEW_RECEIPT.json' not in files,'RECEIPT_NOT_SOURCE')
 import io
 with zipfile.ZipFile(io.BytesIO(archive)) as z:
  entries=z.infolist();need(len(entries)==51 and len({e.filename for e in entries})==51 and set(z.namelist())==set(files),'EXACT_ARCHIVE_SET')
  need(sum(e.file_size for e in entries)<=10000000,'SOURCE_BUDGET')
  data={}
  for e in entries:
   mode=e.external_attr>>16;need(not e.is_dir() and not stat.S_ISLNK(mode) and (not stat.S_IFMT(mode) or stat.S_ISREG(mode)),'REGULAR_FILES_ONLY')
   b=z.read(e);need(sha(b)==files[e.filename],'SOURCE_HASH_MISMATCH');data[e.filename]=b
 config=json.loads(data['project.config.json']);need(config.get('appid')=='wx1d5f8873eaea5392' and config.get('compileType')=='miniprogram' and config.get('miniprogramRoot')=='./','APPID_CONFIG_MISMATCH')
 need({'app.js','app.json','session.js'}<=set(files),'REQUIRED_SOURCE_MISSING')
 dest=pathlib.Path(destination);need(not dest.exists() and not dest.is_symlink(),'DESTINATION_EXISTS')
 # No app.js substitution, no filters: every snapshot byte is preserved.
 tmp=pathlib.Path(tempfile.mkdtemp(prefix='.snapshot-',dir=str(dest.parent)))
 try:
  mini=tmp/'clients/community-mini';mini.mkdir(parents=True)
  for n,b in data.items():
   p=mini/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
  actual={p.relative_to(mini).as_posix():sha(p.read_bytes()) for p in mini.rglob('*') if p.is_file()}
  need(actual==files,'STAGE_VERIFY_FAILED')
  receipt={'status':'SNAPSHOT_STAGED_NOT_UPLOAD_ADMITTED','manifest_sha256':expected_manifest_sha,'zip_sha256':expected_zip_sha,'source_files':files,'appid':config['appid'],'app_sha256':files['app.js'],'source_type':'HANGZHOU_FILE_SNAPSHOT_NOT_GIT_COMMIT','readiness_verified':False,'upload_allowed':False}
  (tmp/'snapshot-receipt.json').write_text(json.dumps(receipt,sort_keys=True)+'\n');os.rename(tmp,dest)
  return receipt
 finally:
  if tmp.exists():shutil.rmtree(tmp)

def identity(env):
 need((env.get('GITHUB_EVENT_NAME')=='workflow_dispatch' or (env.get('GITHUB_EVENT_NAME')=='push' and env.get('COMMUNITY_SNAPSHOT_PUSH')=='true')) and env.get('GITHUB_REPOSITORY')=='huhongchuan0422-creator/Repository-name-xuanjun-ai-control' and env.get('GITHUB_REF')=='refs/heads/feature/chatgpt-community-wechat-sp-offline-20261017','ORIGINAL_CONTROL_REQUIRED')
 head=env.get('GITHUB_SHA','');need(re.fullmatch('[a-f0-9]{40}',head) and env.get('PREVIEW_CONTROL_SHA')==head and env.get('PREVIEW_TARGET')=='uk-path-candidate' and env.get('PREVIEW_ENABLED')=='true' and env.get('IMAGE_BUILD_ENABLED')=='false','EXACT_CONTROL_BINDING')
 bp=pathlib.Path(env['COMMUNITY_SNAPSHOT_BINDING']);root=pathlib.Path(env['COMMUNITY_SNAPSHOT_ROOT']);need(not bp.is_symlink() and not root.is_symlink(),'BINDING_SYMLINK')
 raw=bp.read_bytes();need(sha(raw)==env['COMMUNITY_SNAPSHOT_BINDING_SHA256'],'BINDING_PIN');b=json.loads(raw)
 need(b['control_source_sha']==head and b['appid']=='wx1d5f8873eaea5392' and b['baseUrl']=='https://uk.wenwenwenyiyiyi.work/community-preview' and b['scene'] is None and b['payments'] is False and b['commerce'] is True,'PRODUCT_BINDING')
 for name in ('manifest_sha256','archive_sha256','compatibility_evidence_sha256'):need(re.fullmatch('[a-f0-9]{64}',b[name]),'PAIR_PIN')
 need(re.fullmatch('[a-f0-9]{40}',b['backend_source_sha']),'BACKEND_PIN')
 receipt=json.loads((root/'snapshot-receipt.json').read_bytes());need(receipt['manifest_sha256']==b['manifest_sha256'] and receipt['zip_sha256']==b['archive_sha256'] and receipt['source_files']==b['source_files'],'STAGED_PAIR_MISMATCH')
 actual={};mini=root/'clients/community-mini'
 for p in mini.rglob('*'):
  need(not p.is_symlink(),'SOURCE_SYMLINK')
  if p.is_file():actual[p.relative_to(mini).as_posix()]=sha(p.read_bytes())
 need(actual==b['source_files'] and len(actual)==51,'STAGED_DRIFT')
 return dict(product_source_sha=b['manifest_sha256'],control_source_sha=head,fixed_product=True,backend_source_sha=b['backend_source_sha'],compatibility='EXACT_REVIEWED_SNAPSHOT_BACKEND_PAIR',snapshot_binding=b)

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['stage','identity']);args=parser.parse_args()
 if args.operation=='identity':print(json.dumps(identity(os.environ),sort_keys=True))
 else:
  inp=pathlib.Path(os.environ['COMMUNITY_SNAPSHOT_INPUT']);bp=inp/'binding.json';raw=bp.read_bytes();need(sha(raw)==os.environ['COMMUNITY_SNAPSHOT_BINDING_SHA256'],'BINDING_PIN');b=json.loads(raw)
  prepare((inp/'snapshot.zip').read_bytes(),(inp/'manifest.json').read_bytes(),b['manifest_sha256'],b['archive_sha256'],os.environ['COMMUNITY_SNAPSHOT_ROOT'])
  identity(os.environ)
  print('SNAPSHOT_STAGE_VERIFIED_NOT_UPLOADED')
