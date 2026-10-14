#!/usr/bin/env python3
"""Reviewer sandbox only: materialize pinned inputs, run audited pure compiler.
NOT data-only: executes four pinned helper modules' definitions and the pinned
identity renderer. Never invokes main, host driver, installer, service or network.
Inspect before running. Output contains counts/hashes, no plan or rendered values.
"""
import argparse,base64,gzip,hashlib,io,json,pathlib,sys,tarfile,tempfile,types
OLD_ARCHIVE='c2d593d662fbce4a0c2fa454cc4a18dbec327c0bd0bf3d6d72849d9a5a79970d'
NEW_ARCHIVE='9c186c8d9788ff12307bc95362d00a9315ba8f18d899c8e41fa4e45a51a5e4c0'
OLD_MANIFEST='9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3'
NEW_MANIFEST='3332a6e63b11b75420f1bd0f1a264c89528a92a771f6bc1399f2a38009f324ef'
KIT='48d4b86f48aaa3440ac8744a9e0fe99dacf4cddc1050777a7911c9a71fd89180'
ORIGINAL_PLAN='ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a'
COMPILED_PLAN='949dee6ed4d1a1c271f584bd995f61da238aa92171974ec05bc23bfa930465e2'
REPAIRS={'stage1/p2_fixed_host_runtime.py','stage1/p2_tls_lifecycle.py'}
def need(ok,label):
 if not ok:raise ValueError(label)
def sha(b):return hashlib.sha256(b).hexdigest()
def pairs(items):
 result={}
 for k,v in items:need(k not in result,'DUPLICATE_JSON');result[k]=v
 return result
def parse(b):return json.loads(b.decode('utf-8'),object_pairs_hook=pairs)
def read(path,limit=2097152):
 with open(path,'rb') as f:b=f.read(limit+1)
 need(len(b)<=limit,'INPUT_BOUND');return b
def archive(path,wanted,size,prefix):
 raw=read(path)
 if sha(raw)!=wanted:raw=base64.b64decode(b''.join(raw.split()),validate=True)
 need(len(raw)==size and sha(raw)==wanted,'ARCHIVE_PIN')
 with gzip.GzipFile(fileobj=io.BytesIO(raw)) as z:tar=z.read(8388609)
 need(len(tar)<=8388608,'EXPANDED_BOUND');files={};seen=set()
 with tarfile.open(fileobj=io.BytesIO(tar),mode='r:') as t:
  for m in t:
   parts=m.name.split('/')
   need(parts[0]==prefix and all(p not in ('','.','..') for p in parts) and '\\' not in m.name,'PATH')
   need(m.name not in seen and len(seen)<256,'DUPLICATE_OR_COUNT');seen.add(m.name)
   need(m.uid==m.gid==0 and (m.isfile() or m.isdir()),'OWNER_OR_TYPE')
   if m.isdir():continue
   need(0<=m.size<=2097152,'MEMBER_BOUND');b=t.extractfile(m).read(2097153)
   need(len(b)==m.size,'MEMBER_SIZE');files['/'.join(parts[1:])]=b
 return files
def runtime(files,prefix,expected):
 data=files[prefix+'deploy/integration-manifest.json'];need(sha(data)==expected,'MANIFEST_PIN');m=parse(data)
 need(len(m['files'])==102,'RUNTIME_COUNT')
 result={'deploy/integration-manifest.json':data}
 for name,h in m['files'].items():
  need(not name.startswith('/') and all(p not in ('','.','..') for p in name.split('/')),'RUNTIME_PATH')
  b=files[prefix+name];need(sha(b)==h,'RUNTIME_PIN');result[name]=b
 return result,m
def materialize(root,files):
 for name,b in files.items():
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(b)
  p.chmod(0o600)
def verify(old_path,new_path,plan_path):
 oldfiles=archive(old_path,OLD_ARCHIVE,192286,'xuanjun-p2-package')
 newfiles=archive(new_path,NEW_ARCHIVE,264661,'epoch5-recovery-candidate-v3')
 old,om=runtime(oldfiles,'',OLD_MANIFEST);new,nm=runtime(newfiles,'xuanjun-p2-package/',NEW_MANIFEST)
 need(set(om['files'])==set(nm['files']),'SCOPE')
 need({n for n in om['files'] if om['files'][n]!=nm['files'][n]}==REPAIRS,'DELTA')
 kitraw=newfiles['recovery-kit-manifest.json'];need(sha(kitraw)==KIT,'KIT_PIN');kit=parse(kitraw)
 raw=read(plan_path);need(len(raw)==22468 and sha(raw)==ORIGINAL_PLAN,'ORIGINAL_PLAN_PIN')
 original=parse(raw);saved={};names=['build_epoch5_runtime','inspect_epoch3','prepare_epoch5_bindings','epoch5_plan']
 with tempfile.TemporaryDirectory(prefix='p2-review-offline-') as td:
  root=pathlib.Path(td);a=root/'old';b=root/'new';materialize(a,old);materialize(b,new)
  try:
   for name in names:
    data=newfiles['helpers/'+name+'.py'];need(sha(data)==kit['helper_files'][name+'.py'],'HELPER_PIN')
    saved[name]=sys.modules.get(name);module=types.ModuleType(name);module.__file__=str(root/(name+'.py'));sys.modules[name]=module
    exec(compile(data,module.__file__,'exec'),module.__dict__)
   binding=sys.modules['prepare_epoch5_bindings'];compiler=sys.modules['epoch5_plan']
   public,private=binding.proposal(raw,a,b);plan=compiler.compile_plan(raw,a,b)
   need(len(public['target_bindings'])==24,'TARGET_COUNT')
   render=binding.renderer(b,nm);rendered={}
   for row in plan['runtime']['provisioning']:
    source=render(row['source'],(b/row['source']).read_bytes(),NEW_MANIFEST)
    need(sha(source)==row['source_sha256'],'SOURCE_BINDING')
    output=binding.render_target(source,row['replacements'])
    need(output==private['rendered_targets'][row['target']] and sha(output)==row['rendered_sha256'],'TARGET_BINDING')
    rendered[row['target']]=output
   plugin=plan['runtime']['plugin']
   for k,h in [('binding_file','binding_sha256'),('ledger_client_config','ledger_client_sha256'),('gateway_relay_config','gateway_relay_sha256')]:
    need(sha(rendered[plugin[k]])==plugin[h],'PLUGIN_BINDING')
   activation=plan['activation_proposal']
   for k in ['db_path','generation','instance','ledger_uuid','ledger_socket','binary_sha256']:
    need(activation[k]==original['activation'][k],'CANONICAL_IDENTITY')
   need(activation['epoch']==6 and activation['state']=='PREPARED','PROPOSED_ACTIVATION')
   need(activation['config_sha256']==sha(rendered['/etc/xuanjun-development/dispatcher.json']),'DISPATCHER_BINDING')
   tls=rendered['/etc/xuanjun-development/tls-renewal.json'];need(tls==plan['tls_config_bytes'].encode(),'TLS_BYTES')
   need(plan['runtime']['tls_renewal']['sha256']==sha(tls) and parse(tls)['release_sha256']==NEW_MANIFEST,'TLS_BINDING')
   digest=sha(compiler.canonical(plan));need(digest==COMPILED_PLAN,'COMPILED_PLAN_PIN')
   return {'old_runtime_files_verified':102,'new_runtime_files_verified':102,'unchanged_files':100,'changed_files':2,'old_target_hashes_verified':24,'new_target_bindings_verified':24,'plugin_bindings_verified':3,'activation_dispatcher_tls':'PASS','compiled_plan_sha256':digest,'production_effects':'NOT_RUN','release_approval':'NOT_GRANTED'}
  finally:
   for name,value in saved.items():
    if value is None:sys.modules.pop(name,None)
    else:sys.modules[name]=value
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--old-archive',required=True);p.add_argument('--new-archive',required=True);p.add_argument('--original-plan',required=True);args=p.parse_args()
 print(json.dumps(verify(args.old_archive,args.new_archive,args.original_plan),sort_keys=True,indent=2))
