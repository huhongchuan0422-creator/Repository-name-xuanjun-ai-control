"""Stage verified code in a new domestic release; no data copy or service activation."""
import ast,hashlib,json,os,stat,subprocess,re
from pathlib import Path
HOST='iZvt5t8tlrm8oiZ'
BASE=Path('/opt/xuanjun-migration-s07')
SOURCE=BASE/'releases/domestic-r1/app'
TARGET=BASE/'releases/domestic-r2'
UNITS=('secure-secrets-portal.service','xuanjun-wecom-customer-contact.service','xuanjun-wecom-customer-service.service','provider-neutral-domestic-bridge.service','winctl.service','nginx.service')

def need(ok,code):
 if not ok:raise RuntimeError(code)
def read(p):
 p=Path(p)
 for q in p.parents:need(not q.is_symlink(),'SYMLINK_PARENT')
 s=p.lstat();need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=1048576,'FILE_SHAPE')
 fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW)
 try:
  a=os.fstat(fd);need((a.st_dev,a.st_ino)==(s.st_dev,s.st_ino),'FILE_REPLACED')
  with os.fdopen(os.dup(fd),'rb') as f:b=f.read(1048577)
  z=os.fstat(fd);need((a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_size,z.st_mtime_ns,z.st_ctime_ns) and len(b)==z.st_size,'FILE_CHANGED')
  return b
 finally:os.close(fd)
def sha(b):return hashlib.sha256(b).hexdigest()
def snapshot():
 rows={}
 for u in UNITS:
  r=subprocess.run(['/usr/bin/systemctl','show',u,'--property=LoadState,ActiveState,SubState,MainPID,FragmentPath','--no-pager'],capture_output=True,timeout=10)
  need(r.returncode==0,'SYSTEMD_QUERY')
  rows[u]=r.stdout.decode()
 for p in ('/var/www/wenwenwenyiyiyi.work/current','/opt/trading-system'):
  q=Path(p)
  if q.is_symlink():rows[p]={'link':os.readlink(q)}
  elif q.exists():
   s=q.lstat();rows[p]={'dev':s.st_dev,'ino':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid}
  else:rows[p]={'absent':True}
 return rows

PINS={
 'ai_service/telegram_customer_service_canary.py':'83904b6994db02b2702563eaaace50399caaf968864bd7f0ea355b4350462150',
 'ai_service/wecom_customer_service.py':'aa50fff75f53646bac75a30adbeccb98104e25d58bf099929bfea93e5810a402'}
def patch_port(raw,pin):
 need(sha(raw)==pin,'PATCH_SOURCE_HASH')
 tree=ast.parse(raw);calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='ProviderNeutralBridgeClient' and len(n.args)>=2 and isinstance(n.args[0],ast.Constant) and n.args[0].value=='127.0.0.1' and isinstance(n.args[1],ast.Constant) and n.args[1].value==19443]
 need(len(calls)==1,'PATCH_EXACT_CALL')
 node=calls[0].args[1];need(node.lineno==node.end_lineno,'PATCH_SINGLE_LINE')
 lines=raw.splitlines(keepends=True);line=lines[node.lineno-1]
 need(line[node.col_offset:node.end_col_offset]==b'19443','PATCH_EXACT_BYTES')
 lines[node.lineno-1]=line[:node.col_offset]+b'18443'+line[node.end_col_offset:]
 result=b''.join(lines);compile(result,'domestic-bridge-port-adapted.py','exec')
 new=ast.parse(result);calls[0].args[1].value=18443
 need(ast.dump(tree,include_attributes=False)==ast.dump(new,include_attributes=False),'PATCH_AST_DIFF')
 return result

def main():
 need(os.geteuid()==0 and os.uname().nodename==HOST,'HOST_ROOT')
 receipt=json.loads(read(SOURCE.parent/'receipt.json'))
 need(receipt['status']=='DOMESTIC_CODE_RELEASE_STAGED_NOT_ACTIVE' and len(receipt['source_hashes'])==124,'R1_RECEIPT')
 sources={name:read(SOURCE/name) for name in receipt['source_hashes']}
 need(all(sha(data)==receipt['source_hashes'][name] for name,data in sources.items()),'R1_SOURCE_CHANGED')
 patches=[]
 for name,pin in PINS.items():
  original=sources[name];updated=patch_port(original,pin)
  sources[name]=updated
  patches.append({'source':name,'before_sha256':sha(original),'after_sha256':sha(updated),'from_port':19443,'to_port':18443,'changed_calls':1})
 before=snapshot()
 for u in UNITS[:3]:need('LoadState=not-found' in before[u],'DOMESTIC_UNIT_EXISTS')
 parent=TARGET.parent
 need(BASE.is_dir() and not BASE.is_symlink(),'BASE_SHAPE')
 if not parent.exists():parent.mkdir(mode=0o755);parent.chmod(0o755)
 need(not parent.is_symlink() and parent.stat().st_uid==0,'RELEASE_PARENT')
 TARGET.mkdir(mode=0o700)
 # No existing version is removed, overwritten, activated or used as current.
 try:
  app=TARGET/'app';app.mkdir(mode=0o755);app.chmod(0o755)
  for name,b in sorted(sources.items()):
   p=app/name;p.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
   for q in [p.parent]+list(p.parent.parents):
    if q==TARGET:break
    if q.is_relative_to(app):q.chmod(0o755)
   with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
   p.chmod(0o444);need(sha(read(p))==sha(b),'DESTINATION_HASH')
  after=snapshot();need(before==after,'PROTECTED_STATE_CHANGED')
  manifest={'status':'DOMESTIC_R2_CODE_BRIDGE_PORT_ADAPTED_NOT_ACTIVE','hostname':HOST,'uid':os.geteuid(),'attempt_nonce':ATTEMPT_NONCE,'source_files':124,'source_provenance':'R1_EXACT_124_WITH_TWO_EXPLICIT_DOMESTIC_BRIDGE_PORT_ADAPTATIONS_NOT_FRESH_TOKYO','source_hashes':{k:sha(v) for k,v in sorted(sources.items())},'patches':patches,'protected_state_unchanged':True,'services_installed':False,'service_actions':0,'runtime_materials_copied':False,'database_opened':False,'business_api_requests':0,'production_cutover':False,'retry_allowed':False,'effective_live_bridge_auth_verified':False}
  with (TARGET/'receipt.json').open('x') as f:json.dump(manifest,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
  (TARGET/'receipt.json').chmod(0o400)
  print(json.dumps({k:v for k,v in manifest.items() if k!='source_hashes'}),flush=True)
 except Exception:
  with (TARGET/'failure.json').open('x') as f:json.dump({'status':'HOLD_PRESERVE_NO_RETRY'},f)
  raise
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'status':'HOLD_PRESERVE_NO_RETRY','exception':type(e).__name__,'code':str(e) if re.fullmatch(r'[A-Z0-9_]{1,100}',str(e)) else 'PRIVATE_DETAIL_WITHHELD'}),flush=True);raise SystemExit(2)
