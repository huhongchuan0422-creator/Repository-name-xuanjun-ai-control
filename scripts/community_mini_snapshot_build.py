"""Original workflow test-job artifact builder; no network, secrets or deployment."""
import hashlib,json,pathlib,os,re,shutil
MANIFEST='1877e83c8e78fe7cc15fe25ac8d9be8193fc3ff41c9d3e85bb6c586b4af93f92'
ARCHIVE='69b8c4c9647a51912be10ff3e68eb32aae78fc89dcee49c21746f32222f85b33'
# Must be frozen from real reviewed backend evidence after P3 stabilizes.
BACKEND_PAIR_SHA256='15845a54f213f5b77eda7650259be41a796563be44b8663efae0cfb5bf5f66ea'
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
REF='refs/heads/feature/chatgpt-community-wechat-sp-offline-20261017'
def sha(b):return hashlib.sha256(b).hexdigest()
def need(v,msg):
 if not v:raise ValueError(msg)
def build(root,env,pair_pin=BACKEND_PAIR_SHA256):
 push=env.get('GITHUB_EVENT_NAME')=='push' and env.get('COMMUNITY_SNAPSHOT_PUSH')=='true'
 manual=env.get('GITHUB_EVENT_NAME')=='workflow_dispatch' and env.get('COMMUNITY_SNAPSHOT_FROM_SOURCE')=='true' and env.get('PREVIEW_ENABLED')=='true' and env.get('PREVIEW_TARGET')=='uk-path-candidate' and env.get('PREVIEW_CONTROL_SHA')==env.get('GITHUB_SHA')
 need((push or manual) and env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')==REF,'EXACT_ORIGINAL_PUSH_REQUIRED')
 head=env.get('GITHUB_SHA','');need(re.fullmatch('[a-f0-9]{40}',head),'CONTROL_COMMIT_REQUIRED')
 need(type(pair_pin)is str and re.fullmatch('[a-f0-9]{64}',pair_pin),'REAL_BACKEND_PAIR_NOT_FROZEN')
 root=pathlib.Path(root);source=root/'deploy/community-preview/hangzhou-snapshot';need(not source.is_symlink(),'SOURCE_SYMLINK')
 archive=(source/'snapshot.zip').read_bytes();manifest=(source/'manifest.json').read_bytes();need(sha(archive)==ARCHIVE and sha(manifest)==MANIFEST,'EXACT_HANGZHOU_INPUT_DRIFT')
 pair_raw=(source/'backend-pair.json').read_bytes();need(sha(pair_raw)==pair_pin,'PAIR_PIN_CHANGED');pair=json.loads(pair_raw)
 need(pair['manifest_sha256']==MANIFEST and pair['archive_sha256']==ARCHIVE and re.fullmatch('[a-f0-9]{40}',pair['backend_source_sha']) and pair['backend_version_source']=='IMAGE_BUILD_STAMP','PAIR_SOURCE_BINDING')
 need(pair['appid']=='wx1d5f8873eaea5392' and pair['baseUrl']=='https://uk.wenwenwenyiyiyi.work/community-preview' and pair['scene'] is None and pair['payments'] is False and pair['commerce'] is True,'PAIR_CONFIG_BINDING')
 # Evidence content is independently reviewed and pinned, never generated from runtime health.
 need(pair.get('compatibility')=='EXACT_REVIEWED_SNAPSHOT_BACKEND_PAIR','COMPATIBILITY_REQUIRED')
 files=json.loads(manifest)['files'];binding={k:pair[k] for k in ('backend_source_sha','appid','baseUrl','scene','payments','commerce')};binding.update(control_source_sha=head,manifest_sha256=MANIFEST,archive_sha256=ARCHIVE,compatibility_evidence_sha256=pair_pin,source_files=files)
 raw=(json.dumps(binding,sort_keys=True,separators=(',',':'))+'\n').encode();out=root/'hangzhou-snapshot-input';need(not out.exists() and not out.is_symlink(),'OUTPUT_EXISTS');out.mkdir()
 for n,b in [('snapshot.zip',archive),('manifest.json',manifest),('binding.json',raw)]:
  with (out/n).open('xb') as f:f.write(b)
 return sha(raw)
if __name__=='__main__':
 digest=build(pathlib.Path(__file__).resolve().parents[1],os.environ)
 with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('binding_sha256='+digest+'\n')
 print('EXACT_HANGZHOU_CURRENT_RUN_INPUT_BUILT_NOT_UPLOADED')
