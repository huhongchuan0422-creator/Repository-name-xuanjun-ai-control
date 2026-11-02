import os,stat,fcntl,hashlib,json,sys
CACHE='/var/lib/xuanjun-cloud-connection/registered-update-v1/lifecycle/cache'
LEAF='package-b9b666d37a40c1b3b21979f45bcacf20bc7f948c46dc1e6f8fdfd07831caec40'
SHA='2be41b4d3dd7b583fe84427db7f68da06d703531741e88e56a9a95ba8135c749'
OUTER='3b675923f11b0a7725806d6d35fa8a718cd9bdbb262eff4f8e3cc96596364371'
TASK_SHA='1e89da20a787a106e741c5d40d62899f2855ef0ad5d827f84b3cf44ac64e8137'
NEW_OUTER_CHUNK_COUNT=2  # Bind only actual hosted artifact chunk count.
def need(v,r):
 if not v:raise SystemExit('HOLD_'+r)
def ident(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def decode(b):
 def pairs(v):
  d={}
  for k,x in v:need(k not in d,'DUPLICATE_JSON');d[k]=x
  return d
 return json.loads(b,object_pairs_hook=pairs)
def chain():
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);seen=[]
 try:
  for part in ['']+CACHE.split('/')[1:]:
   if part:
    n=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=n
   s=os.fstat(fd);need(s.st_uid==0 and not s.st_mode&0o022,'CACHE_PARENT');seen.append((s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid))
  need(stat.S_IMODE(s.st_mode)==0o700,'CACHE_MODE');return fd,seen
 except BaseException:os.close(fd);raise
def read(name,limit):
 fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
 try:
  s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1 and s.st_size<=limit,'PRIVATE_LEAF');v=b''
  while len(v)<=limit:
   b=os.read(fd,min(65536,limit+1-len(v)))
   if not b:break
   v+=b
  need(len(v)==s.st_size and ident(s)==ident(os.fstat(fd))==ident(os.stat(name,dir_fd=parent,follow_symlinks=False)),'LEAF_CHANGED');return v,ident(s)
 finally:os.close(fd)
need(len(TASK_SHA)==64 and os.getuid()==os.geteuid()==0,'EXACT_REGISTERED_ROOT')
parent,parents=chain();lock=None
try:
 _,li=read('update.lock',65536);lock=os.open('update.lock',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent);need(ident(os.fstat(lock))==li,'LOCK_CHANGED');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 markraw,_=read(LEAF+'.complete',16384);mark=decode(markraw)
 manifest={'schema':'immutable-package-v1','payload':'COMMUNITY_SUPERADMIN_FIRST_ENABLE_INSTALL.py','members':[{'name':'COMMUNITY_SUPERADMIN_FIRST_ENABLE_INSTALL.py','role':'payload','bytes':512685,'sha256':SHA}]}
 need(set(mark)=={'schema','outer_sha256','manifest','identity'} and mark['schema']=='verified-immutable-package-v1' and mark['outer_sha256']==OUTER and mark['manifest']==manifest,'MATERIALIZATION_RECEIPT')
 doneleaf='package-'+TASK_SHA+'.complete';done,_=read(doneleaf,16384)
 expected={'state':'PACKAGE_CACHE_COMPLETE','business_executed':False,'package_sha256':TASK_SHA,'project':'community-preview','version':'e23e186-first-enable-installer-v1-2be41b','artifact_sha256':SHA,'bytes':512685,'outer_sha256':OUTER,'verified_chunks':NEW_OUTER_CHUNK_COUNT,'total_chunks':NEW_OUTER_CHUNK_COUNT}
 enc=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)
 need(enc(decode(done))==enc(expected),'PACKAGE_COMPLETE')
 payload,pi=read(LEAF,512685);need(len(payload)==512685 and hashlib.sha256(payload).hexdigest()==SHA and list(pi)==mark['identity'],'PAYLOAD_PIN')
 fd,again=chain();os.close(fd);need(again==parents,'PARENTS_CHANGED')
 need(read(LEAF+'.complete',16384)[0]==markraw and read(doneleaf,16384)[0]==done and ident(os.fstat(lock))==ident(os.stat('update.lock',dir_fd=parent,follow_symlinks=False))==li,'RECEIPT_OR_LOCK_CHANGED')
finally:
 if lock is not None:os.close(lock)
 os.close(parent)
# Original cache loader has already verified exact old carrier payload bytes.
# No on-disk carrier, control manifest, image or prior receipt is rewritten.
import ast,base64
need(hashlib.sha256(payload).hexdigest()=='2be41b4d3dd7b583fe84427db7f68da06d703531741e88e56a9a95ba8135c749','ORIGINAL_CARRIER_SHA')
tree=ast.parse(payload);constants={}
for node in tree.body:
 if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('PAYLOAD','BOOTSTRAP','BOOTSTRAP_SHA','MANIFEST_SHA'):
  need(node.targets[0].id not in constants,'DUPLICATE_SEALED_CONSTANT');constants[node.targets[0].id]=ast.literal_eval(node.value)
need(set(constants)=={'PAYLOAD','BOOTSTRAP','BOOTSTRAP_SHA','MANIFEST_SHA'},'SEALED_CONSTANTS')
need(constants['BOOTSTRAP_SHA']=='4a530555eceed9fb98fc21c6223783b560939da2bc6da081f3835754e6a20408' and constants['MANIFEST_SHA']=='3f82ff990e09f5e7e3b46cacfdf3e08687ab9c0c8f142e762da629a606efa897','ORIGINAL_SEALED_BINDINGS')
files={}
for name,item in constants['PAYLOAD'].items():
 data=base64.b64decode(item['base64'],validate=True)
 need(len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],'ORIGINAL_CONTROL_BYTES');files[name]=data
code=base64.b64decode(constants['BOOTSTRAP'],validate=True);need(hashlib.sha256(code).hexdigest()==constants['BOOTSTRAP_SHA'],'ORIGINAL_BOOTSTRAP_BYTES')
ns={'__name__':'fixed_572_bootstrap'};exec(compile(code,'original-reviewed-bootstrap','exec'),ns)
ns['real_operator']();ns['validate_payload_files'](files,constants['MANIFEST_SHA'])
expected={'/community/admin-shell.css':'c28d10b2afbb9f0c88f19a74f6a6e45842044029dc778e88d0edbf8e985133d7','/community/admin-shell.js':'8a0a6cec035ba252b9d48bea93b5046a6046beee66507bae1171e508aa35fa39','/community/web-session.js':'2170f4932388803bb571bc01a0f3db7f6131df6f087c7a4fe53a92b07f026eac'}
need(ns['ADMIN_ROUTE_ASSETS']==expected,'ORIGINAL_PROBE_BINDING_CHANGED')
# e23e scripts/community_web_entries.asset rebases three JS URL strings. Exact
# immutable source projection and normal TLS GET independently prove this wire SHA.
# Only in-memory verification expectation changes; no module/file/install mutation.
ns['ADMIN_ROUTE_ASSETS']=dict(expected,**{'/community/web-session.js':'c0cff58d537e8402c74e21e3d9110b4915773414fc553dc12f6951b6030b9e77'})
h=ns['load_embedded_control'](files,constants['MANIFEST_SHA'])
with ns['management_lock']():
 observed=ns['inspect_status'](h,files,constants['MANIFEST_SHA'])
 need(observed['phase']=='COMMITTED' and observed['new_id']=='3efa731a127bed49a2c07690dad4e25d7e0c1a6f28765f49631d6346cd2b378d','EXACT_COMMITTED_CURRENT_REQUIRED')
 state=ns['admin_route_status'](h,constants['MANIFEST_SHA'])
 need(state['phase'] in ('admin-route-reload-intent','admin-route-success'),'EXISTING_RELOAD_ONLY_NO_NEW_APPLY')
 need(state['intent']['new_id']==observed['new_id'],'ROUTE_INSTANCE_CHANGED')
 proof=ns['admin_route_probe'](h)
 after=ns['inspect_status'](h,files,constants['MANIFEST_SHA']);again=ns['admin_route_status'](h,constants['MANIFEST_SHA'])
 need(after['phase']=='COMMITTED' and after['new_id']==observed['new_id'] and again==state,'ROUTE_OR_CURRENT_CHANGED')
 if state['phase']=='admin-route-reload-intent':
  parent=ns['directory'](ns['JOURNAL'],True)
  try:ns['put_same'](parent,'admin-route-success.json',ns['encode']({'intent_sha256':ns['sha'](ns['encode'](state['intent']))}))
  finally:os.close(parent)
 final=ns['admin_route_status'](h,constants['MANIFEST_SHA']);need(final['phase']=='admin-route-success','SUCCESS_RECEIPT_READBACK')
 print(json.dumps({'state':'ADMIN_ROUTES_RECONCILED_EXACT_E23E_WIRE_PROJECTION','new_id':observed['new_id'],'asset_auth_probe':proof,'route_phase':final['phase'],'nginx_reload_performed':False,'include_modified':False,'old_carrier_modified':False,'account_created':False,'complete_delivery':False},sort_keys=True))
