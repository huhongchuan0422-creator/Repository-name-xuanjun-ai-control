"""Assemble a private runtime candidate from preserved copies, never active paths."""
import ast,hashlib,json,os,re,stat,subprocess
from pathlib import Path
HOST='iZvt5t8tlrm8oiZ'
RELEASE=Path('/opt/xuanjun-migration-s07/releases/domestic-r2')
SOURCE=Path('/var/lib/xuanjun-pr99-s07-isolated-start-v4/rootfs')
VENV=Path('/opt/xuanjun-migration-s07/venv')
UNITS=('secure-secrets-portal.service','xuanjun-wecom-customer-contact.service','xuanjun-wecom-customer-service.service','provider-neutral-domestic-bridge.service','winctl.service','nginx.service')
def need(ok,code):
 if not ok:raise RuntimeError(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p,limit=67108864):
 p=Path(p)
 for q in p.parents:need(not q.is_symlink(),'SYMLINK_PARENT')
 a=p.lstat();need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_size<=limit,'FILE_SHAPE')
 fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW)
 try:
  z=os.fstat(fd);need((a.st_dev,a.st_ino)==(z.st_dev,z.st_ino),'REPLACED')
  with os.fdopen(os.dup(fd),'rb') as f:b=f.read(limit+1)
  z=os.fstat(fd);need((a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_size,z.st_mtime_ns,z.st_ctime_ns) and len(b)==a.st_size,'CHANGED')
  return b
 finally:os.close(fd)
def snap():
 out={}
 for u in UNITS:
  r=subprocess.run(['/usr/bin/systemctl','show',u,'--property=LoadState,ActiveState,SubState,MainPID,FragmentPath','--no-pager'],capture_output=True,timeout=10)
  need(r.returncode==0,'UNIT_QUERY');out[u]=r.stdout.decode()
 for name in ('/var/www/wenwenwenyiyiyi.work/current','/opt/trading-system'):
  p=Path(name)
  if p.is_symlink():out[name]={'link':os.readlink(p)}
  elif p.exists():
   s=p.stat();out[name]={'dev':s.st_dev,'ino':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid}
  else:out[name]=None
 return out
def main():
 need(os.geteuid()==0 and os.uname().nodename==HOST,'HOST_ROOT')
 code_receipt=json.loads(read(RELEASE/'receipt.json',1000000))
 need(code_receipt['status']=='DOMESTIC_R2_CODE_BRIDGE_PORT_ADAPTED_NOT_ACTIVE' and len(code_receipt['source_hashes'])==124,'CODE_RECEIPT')
 v4=json.loads(read(SOURCE.parent/'receipt.json',1000000));need(v4['application_processes_stopped'] is True and v4['protected_state_unchanged'] is True,'V4_STATE')
 before=snap()
 for u in UNITS[:3]:need('LoadState=not-found' in before[u],'UNIT_ALREADY_PRESENT')
 need(not (RELEASE/'rootfs').exists() and not (RELEASE/'runtime-stage.started.json').exists(),'ATTEMPT_ALREADY_CONSUMED')
 with (RELEASE/'runtime-stage.started.json').open('x') as f:json.dump({'status':'STARTED','nonce':ATTEMPT_NONCE},f)
 root=RELEASE/'rootfs';root.mkdir(mode=0o700)
 hashes={};total=0;count=0;links=0
 try:
  r1=json.loads(read(RELEASE.parent/'domestic-r1/receipt.json',1000000))
  patches={p['source']:p for p in code_receipt['patches']};need(len(patches)==2,'TWO_PATCHES')
  for origin,dest in ((SOURCE/'opt',root/'opt'),(SOURCE/'home',root/'home'),(VENV,root/'venv')):
   need(origin.is_dir() and not origin.is_symlink(),'SOURCE_ROOT')
   for current,dirs,files in os.walk(origin,followlinks=False):
    rel=Path(current).relative_to(origin);target=dest/rel;target.mkdir(mode=0o700,parents=True,exist_ok=True)
    for name in list(dirs):
     p=Path(current)/name
     if p.is_symlink():
      need(dest==root/'venv' and p.relative_to(origin).as_posix()=='lib64' and os.readlink(p)=='lib','DIRECTORY_LINK')
      (target/name).symlink_to('lib');dirs.remove(name);links+=1
    for name in sorted(files):
     p=Path(current)/name;q=target/name
     if p.is_symlink():
      link=os.readlink(p);relative=p.relative_to(origin).as_posix()
      need(dest==root/'venv' and relative in ('bin/python','bin/python3','bin/python3.11') and link in ('python3','/usr/bin/python3'),'VENV_LINK')
      q.symlink_to(link);links+=1;continue
     b=read(p)
     key=q.relative_to(root).as_posix()
     if key.startswith('opt/trading-system/'):
      source_name=key[len('opt/trading-system/'):]
      if source_name in code_receipt['source_hashes']:
       need(sha(b)==r1['source_hashes'][source_name],'ORIGINAL_COPY_SOURCE_HASH')
       replacement=read(RELEASE/'app'/source_name)
       need(sha(replacement)==code_receipt['source_hashes'][source_name],'R2_ADAPTED_SOURCE_HASH')
       if source_name not in patches:need(replacement==b,'UNPLANNED_SOURCE_CHANGE')
       else:need(sha(b)==patches[source_name]['before_sha256'] and sha(replacement)==patches[source_name]['after_sha256'],'PATCH_PROVENANCE')
       b=replacement
     total+=len(b);count+=1;need(count<=12000 and total<=536870912,'COPY_BOUND')
     with q.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
     q.chmod(0o500 if p.stat().st_mode&0o111 else 0o400)
     need(sha(read(q))==sha(b),'COPY_HASH');hashes[q.relative_to(root).as_posix()]=sha(b)
  for name,h in code_receipt['source_hashes'].items():need(hashes.get('opt/trading-system/'+name)==h,'CODE_BINDING')
  # Resolve only literal environment variable names and path existence; never import apps.
  contract=[]
  for entry in ('scripts/secure_secrets_portal_server.py','ai_service/wecom_customer_contact_service.py','ai_service/wecom_customer_service.py','ai_service/telegram_customer_service_canary.py'):
   tree=ast.parse(read(root/'opt/trading-system'/entry));envkeys=set();paths=set()
   for n in ast.walk(tree):
    if isinstance(n,ast.Constant) and isinstance(n.value,str):
     v=n.value
     if re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',v):envkeys.add(v)
     if v.startswith('/opt/trading-system/runtime/') and re.fullmatch(r'/[A-Za-z0-9_./-]{1,400}',v):paths.add(v)
   contract.append({'entry':entry,'environment_key_names':sorted(envkeys),'literal_paths':[{'path':p,'exists':(root/p.lstrip('/')).exists()} for p in sorted(paths)]})
  after=snap();need(before==after,'PROTECTED_CHANGED')
  private={'status':'R2_RUNTIME_CANDIDATE_COPIED_NOT_ACTIVE','files':count,'bytes':total,'links':links,'file_hashes':hashes,'contract':contract,'final_snapshot':False,'effective_production_env_verified':False}
  with (RELEASE/'runtime-candidate.private.json').open('x') as f:json.dump(private,f,sort_keys=True);f.flush();os.fsync(f.fileno())
  (RELEASE/'runtime-candidate.private.json').chmod(0o400)
  print(json.dumps({'status':private['status'],'hostname':HOST,'uid':0,'attempt_nonce':ATTEMPT_NONCE,'files':count,'bytes':total,'links':links,'source_files':124,'copy_hashes':'PASS','protected_state_unchanged':True,'services_installed':False,'service_actions':0,'production_cutover':False,'final_cutover_snapshot':False,'database_opened':False,'business_api_requests':0,'effective_production_env_verified':False,'retry_allowed':False}),flush=True)
 except Exception:
  with (RELEASE/'runtime-stage.failure.json').open('x') as f:json.dump({'status':'HOLD_PRESERVE_NO_RETRY'},f)
  raise
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'status':'HOLD_PRESERVE_NO_RETRY','exception':type(e).__name__,'code':str(e) if re.fullmatch(r'[A-Z0-9_]{1,100}',str(e)) else 'PRIVATE_DETAIL_WITHHELD'}),flush=True);raise SystemExit(2)
