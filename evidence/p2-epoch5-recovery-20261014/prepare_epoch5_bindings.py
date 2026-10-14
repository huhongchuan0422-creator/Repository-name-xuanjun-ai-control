"""Offline binding proposal ONLY. Cannot be passed to the install entrypoint.

Reuse exact original target inventory and the existing identity renderer. No host
paths are read or written. Private plan replacement values remain in local memory;
the public report includes target paths and hashes, never chat IDs or credentials.
"""
import copy,hashlib,json,pathlib,re
from build_epoch5_runtime import OLD_MANIFEST,SOURCE_COMMIT,SOURCE_TREE,REPAIRS
PLAN_SHA='ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a'
INSTALLER_SHA='943f4d04861d8b580008af457d90187622a9de2d1c8cd66c93a721b8ac2be0f3'
TOKEN=re.compile(br'@@[A-Z0-9_]+@@')
def sha(data):return hashlib.sha256(data).hexdigest()
def need(value,message):
 if not value:raise ValueError(message)
def renderer(root,manifest):
 raw=(root/'scripts/uk-integration-install.py').read_bytes()
 need(sha(raw)==INSTALLER_SHA,'RENDERER_CHANGED')
 ns={'__name__':'epoch5_offline_identity_renderer','__file__':str(root/'scripts/uk-integration-install.py')}
 exec(compile(raw,ns['__file__'],'exec'),ns)
 return lambda name,data,digest:ns['render_identity_bytes'](name,data,digest,manifest)
def render_target(data,replacements):
 for token in sorted(replacements):data=data.replace(token.encode('ascii'),replacements[token].encode('utf-8'))
 need(not TOKEN.search(data),'UNRESOLVED_TARGET_TOKEN')
 return data

def proposal(plan_bytes,old_root,new_root):
 need(sha(plan_bytes)==PLAN_SHA,'ORIGINAL_PLAN_CHANGED')
 old_root,new_root=pathlib.Path(old_root),pathlib.Path(new_root)
 plan=json.loads(plan_bytes.decode());before=copy.deepcopy(plan)
 old_bytes=(old_root/'deploy/integration-manifest.json').read_bytes()
 new_bytes=(new_root/'deploy/integration-manifest.json').read_bytes()
 need(sha(old_bytes)==OLD_MANIFEST,'ORIGINAL_MANIFEST_CHANGED')
 old,new=json.loads(old_bytes.decode()),json.loads(new_bytes.decode())
 need(set(old['files'])==set(new['files']) and len(new['files'])==102,'FILE_SCOPE_CHANGED')
 expected_new=copy.deepcopy(old);expected_new['files'].update(REPAIRS)
 need(new==expected_new,'UNREVIEWED_MANIFEST_DELTA')
 for root,manifest in ((old_root,old),(new_root,new)):
  for name,expected in manifest['files'].items():
   need(not name.startswith('/') and '..' not in name.split('/'),'SOURCE_PATH')
   path=root/name
   need(path.resolve()==path.absolute(),'SOURCE_ALIAS')
   need(sha(path.read_bytes())==expected,'SOURCE_FILE_CHANGED')
 oldrender,newrender=renderer(old_root,old),renderer(new_root,new)
 digest=sha(new_bytes);old_release='integration-'+OLD_MANIFEST[:16];new_release='integration-'+digest[:16]
 old_base='/opt/xuanjun-control-releases/'+old_release;new_base='/opt/xuanjun-control-releases/'+new_release
 updates={'@@ARTIFACT_SHA256@@':digest,'@@PACKAGE_SHA256@@':digest,
          '@@RELEASE_DIRECTORY@@':new_release,'@@RELEASE@@':new_base,
          '@@LEDGER_BRIDGE_PATH@@':new_base+'/stage1/native_ledger_bridge.py',
          '@@SOURCE_COMMIT@@':SOURCE_COMMIT}
 rows=plan['runtime']['provisioning'];need(len(rows)==24 and len({r['target'] for r in rows})==24,'TARGET_SCOPE')
 report=[];rendered={}
 for row in rows:
  name=row['source'];raw=(old_root/name).read_bytes();old_source=oldrender(name,raw,OLD_MANIFEST)
  old_source_kind='RENDERED'
  if sha(old_source)!=row['source_sha256']:
   need(name in old['rendering']['identity_files'] and sha(raw)==row['source_sha256'],
        'ORIGINAL_RENDERED_SOURCE_MISMATCH')
   old_source_kind='ORIGINAL_RAW_HASH_KNOWN_INSTALL_BUG'
  old_target=render_target(old_source,row['replacements'])
  need(sha(old_target)==row['rendered_sha256'],'ORIGINAL_TARGET_HASH_MISMATCH')
  for token in set(updates)&set(row['replacements']):row['replacements'][token]=updates[token]
  new_source=newrender(name,(new_root/name).read_bytes(),digest)
  new_target=render_target(new_source,row['replacements'])
  need(old_base.encode() not in new_target and OLD_MANIFEST.encode() not in new_target,'STALE_RELEASE_BINDING')
  row['source_sha256']=sha(new_source);row['rendered_sha256']=sha(new_target)
  rendered[row['target']]=new_target
  report.append({'source':name,'target':row['target'],'source_sha256':sha(new_source),
                 'original_source_hash_kind':old_source_kind,
                 'old_target_sha256':sha(old_target),'new_target_sha256':sha(new_target),
                 'changed':old_target!=new_target})
 need(plan['activation']==before['activation'] and plan['cutover']==before['cutover'],'ORIGINAL_AUTHORITY_MUTATED')
 activation=copy.deepcopy(plan['activation']);activation.pop('expected_epoch')
 activation.update(schema=1,state='PREPARED',epoch=6,release_sha256=digest,
                   config_sha256=sha(rendered['/etc/xuanjun-development/dispatcher.json']))
 need(activation['binary_sha256']==new['files']['stage1/native_gateway_controller.py'],'BINARY_BINDING')
 tls=rendered['/etc/xuanjun-development/tls-renewal.json']
 need(json.loads(tls.decode())['release_sha256']==digest,'TLS_BINDING')
 public={'schema':1,'kind':'OFFLINE_BINDING_PROPOSAL_NOT_INSTALL_PLAN',
         'old_manifest_sha256':OLD_MANIFEST,'new_manifest_sha256':digest,
         'new_release_directory':new_release,'source_commit':SOURCE_COMMIT,'source_tree':SOURCE_TREE,
         'target_bindings':report,'proposed_prepared_epoch':6,
         'dispatcher_config_sha256':activation['config_sha256'],'tls_config_sha256':sha(tls),
         'requires_separate_approved_activation_transition':True,
         'native_bootstrap_binding_rebind':'PENDING_EXACT_OLD_BYTES',
         'runtime_resume_and_failure_path':'NOT_IMPLEMENTED','install_admission':'NOT_GRANTED'}
 return public, {'provisioning':rows,'activation_proposal':activation,
                 'tls_config_bytes':tls.decode(),'rendered_targets':rendered}

NATIVE_BINDING_SHA='94598c41b7b3342ee7be5206577d127a3c3e90f06972a2160ffdd35e6949da98'
def native_binding_delta(raw,new_manifest_sha):
 """Pure exact-old-bytes transformation; caller handles storage/approval separately."""
 need(sha(raw)==NATIVE_BINDING_SHA,'OLD_NATIVE_BINDING_CHANGED')
 need(isinstance(new_manifest_sha,str) and re.fullmatch(r'[0-9a-f]{64}',new_manifest_sha),
      'NEW_MANIFEST_HASH')
 value=json.loads(raw.decode());need(set(value)=={'ledger','gatewayIdentity'},'NATIVE_BINDING_SCHEMA')
 ledger=value['ledger'];need(set(ledger)=={'python','pythonSha256','bridge','config','files'},'NATIVE_LEDGER_SCHEMA')
 old_bridge='/opt/xuanjun-control-releases/integration-'+OLD_MANIFEST[:16]+'/stage1/native_ledger_bridge.py'
 config='/etc/xuanjun-development/p2-native-ledger-client.json'
 need(ledger['bridge']==old_bridge and ledger['config']==config and
      set(ledger['files'])=={old_bridge,config},'NATIVE_BINDING_PATHS')
 new_bridge='/opt/xuanjun-control-releases/integration-'+new_manifest_sha[:16]+'/stage1/native_ledger_bridge.py'
 ledger['bridge']=new_bridge;ledger['files'][new_bridge]=ledger['files'].pop(old_bridge)
 result=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(OLD_MANIFEST[:16].encode() not in result,'STALE_NATIVE_RELEASE')
 return result
