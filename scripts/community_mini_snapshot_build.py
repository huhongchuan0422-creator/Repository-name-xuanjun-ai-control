"""Original workflow test-job artifact builder; no network, secrets or deployment."""
import hashlib,json,pathlib,os,re,shutil
MANIFEST='c87e9374135797329d35303dfa8a527e3b4fc680f49db126e4f667fecbff613f'
ARCHIVE='4f88d86abfb28e95481039e227ee09023309b040d185fd186a78ab12abf07b74'
# Must be frozen from real reviewed backend evidence after P3 stabilizes.
BACKEND_PAIR_SHA256='03bb501ea98a578da17629b7e9d3fb7ed7bf50569082215c42acd78a2b879c6f'
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
REF='refs/heads/feature/chatgpt-community-wechat-sp-offline-20261017'
def sha(b):return hashlib.sha256(b).hexdigest()
def need(v,msg):
 if not v:raise ValueError(msg)
def build(root,env,pair_pin=BACKEND_PAIR_SHA256):
 need(env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')==REF and env.get('COMMUNITY_SNAPSHOT_PUSH')=='true','EXACT_ORIGINAL_PUSH_REQUIRED')
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
