"""Exact S08 remaining metadata; no app, DB, HTTP, credential values or mutation."""
import ast,datetime,hashlib,ipaddress,json,os,re,shlex,stat,subprocess
from pathlib import Path
from urllib.parse import urlsplit
HOSTS={'iZmj7a5kwr75qc1tul4kf9Z':'korea','iZvt5t8tlrm8oiZ':'domestic','iZ6wee8q9z4t03hvqumwfhZ':'tokyo'}

def read(p):
 p=Path(p)
 for parent in p.parents:
  if parent.is_symlink():raise RuntimeError('SYMLINK_PARENT')
 s=p.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>262144:raise RuntimeError('FILE_SHAPE')
 fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW)
 try:
  before=os.fstat(fd)
  if (s.st_dev,s.st_ino)!=(before.st_dev,before.st_ino):raise RuntimeError('FILE_REPLACED')
  with os.fdopen(os.dup(fd),'rb') as f:b=f.read(262145)
  after=os.fstat(fd)
  if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns) or len(b)!=after.st_size:raise RuntimeError('FILE_CHANGED')
  return b
 finally:os.close(fd)

def run(a):
 try:
  r=subprocess.run(a,capture_output=True,text=True,timeout=12);return r.returncode,r.stdout[:262144]
 except Exception:return -1,''

def safe_path(s):return isinstance(s,str) and bool(re.fullmatch(r'/[A-Za-z0-9_./-]{1,240}',s))
def safe_host(s):return bool(re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',s))

def ssh_projection(command):
 t=shlex.split(command);out={'destination':None,'user':None,'port':22,'forwards':[]}
 if not t or t[0]!='/usr/bin/ssh':return {'status':'NOT_SSH'}
 takes={'-i','-F','-S','-J','-W','-b','-c','-E','-e','-l','-m','-o','-p','-L','-R','-D','-w'}
 i=1
 while i<len(t):
  token=t[i];flag=token[:2];value=None
  if token in takes:
   if i+1==len(t):return {'status':'PARSE_HOLD'}
   value=t[i+1];i+=2;flag=token
  elif flag in takes and len(token)>2:value=token[2:];i+=1
  elif token.startswith('-'):i+=1;continue
  else:
   if re.fullmatch(r'(?:[A-Za-z_][A-Za-z0-9_-]{0,39}@)?[A-Za-z0-9_.:-]{1,100}',token):out['destination']=token
   else:out['destination']='WITHHELD'
   break
  if flag=='-p' and value.isdigit():out['port']=int(value)
  elif flag=='-l' and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,39}',value):out['user']=value
  elif flag in ('-L','-R','-D'):out['forwards'].append({'flag':flag,'binding':value if re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{1,180}',value) else 'WITHHELD'})
  elif flag=='-o':
   k,sep,v=value.partition('=')
   if sep and k.lower() in ('hostname','user','port') and safe_host(v):out[k.lower()]=v
 return out

def main():
 host=os.uname().nodename;assert os.geteuid()==0 and host in HOSTS
 role=HOSTS[host];result={'status':'S08_EXACT_ENDPOINT_METADATA','hostname':host,'uid':0,'attempt_nonce':globals().get('ATTEMPT_NONCE'),'collected_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ssh':[],'sources':[],'cron_spool':[],'nginx_includes':[],'container_metadata':[],'service_actions':0,'business_api_requests':0,'database_opened':False}
 if role=='tokyo':
  for unit in ('provider-neutral-tokyo-tunnel.service','domestic-model-rpc-tunnel.service','korea-novel-model-rpc-tunnel.service'):
   path='/etc/systemd/system/'+unit
   try:
    b=read(path);text=b.decode().replace('\\\n',' ')
    commands=[ssh_projection(l.partition('=')[2]) for l in text.splitlines() if l.startswith('ExecStart=')]
    result['ssh'].append({'unit':unit,'sha256':hashlib.sha256(b).hexdigest(),'commands':commands})
   except Exception as e:result['ssh'].append({'unit':unit,'error':type(e).__name__})
  for rel in ('ai_service/telegram_customer_service_canary.py','ai_service/wecom_customer_service.py','ai_service/wecom_customer_contact_service.py','scripts/secure_secrets_portal_server.py'):
   try:
    b=read('/opt/trading-system/'+rel);tree=ast.parse(b);refs=[]
    for n in ast.walk(tree):
     if not isinstance(n,ast.Constant) or not isinstance(n.value,str):continue
     v=n.value
     if v.startswith(('http://','https://')):
      try:
       u=urlsplit(v)
       if not u.username and not u.password and u.hostname and safe_host(u.hostname):refs.append({'line':n.lineno,'scheme':u.scheme,'host':u.hostname,'port':u.port or (443 if u.scheme=='https' else 80)})
      except ValueError:pass
     elif v.startswith(('/opt/trading-system/runtime/','/home/admin/.openclaw/workspace/','/home/openclaw_ops/v8-domestic-operations/')) and safe_path(v):refs.append({'line':n.lineno,'path':v})
    result['sources'].append({'path':rel,'sha256':hashlib.sha256(b).hexdigest(),'refs':refs[:70]})
   except Exception as e:result['sources'].append({'path':rel,'error':type(e).__name__})
 for root in ('/var/spool/cron','/var/spool/cron/crontabs'):
  for user in ('root','admin'):
   p=Path(root)/user
   try:
    b=read(p);result['cron_spool'].append({'path':str(p),'status':'REGULAR','bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'noncomment_lines':len([l for l in b.splitlines() if l.strip() and not l.lstrip().startswith(b'#')])})
   except FileNotFoundError:result['cron_spool'].append({'path':str(p),'status':'ABSENT'})
   except Exception as e:result['cron_spool'].append({'path':str(p),'status':'UNKNOWN','error':type(e).__name__})
 for path in ('/etc/nginx/pr122-site-hub/locations.conf','/etc/nginx/pr122-minimal-cutover/apex.locations.conf'):
  if role!='domestic':continue
  try:
   b=read(path);routes=[]
   for line in b.decode().splitlines():
    m=re.match(r'^\s*(location|proxy_pass)\s+([^;{]+)',line)
    if not m:continue
    k,v=m.groups();v=v.strip()
    if k=='location' and re.fullmatch(r'[A-Za-z0-9_./~*^= -]{1,180}',v):routes.append({'location':v})
    elif k=='proxy_pass':
     try:
      u=urlsplit(v)
      if u.scheme in ('http','https') and not u.username and not u.password and u.hostname and safe_host(u.hostname):routes.append({'upstream_host':u.hostname,'upstream_port':u.port or (443 if u.scheme=='https' else 80)})
     except ValueError:pass
   result['nginx_includes'].append({'path':path,'sha256':hashlib.sha256(b).hexdigest(),'routes':routes[:60]})
  except Exception as e:result['nginx_includes'].append({'path':path,'error':type(e).__name__})
 if role=='tokyo':
  for name in ('xj-tokyo-personal-exit','objective_turing','relaxed_jemison','sharp_bell'):
   rc,out=run(['/usr/bin/docker','inspect','--format','{{json .HostConfig.NetworkMode}}|{{json .Mounts}}',name])
   row={'name':name,'inspect_returncode':rc}
   try:
    mode,mounts=out.strip().split('|',1);mode=json.loads(mode);mounts=json.loads(mounts)
    row['network_mode']=mode if re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',mode) else 'WITHHELD'
    row['mounts']=[{'type':m.get('Type'),'destination':m.get('Destination') if safe_path(m.get('Destination')) else 'WITHHELD','read_write':m.get('RW')} for m in mounts[:16]]
   except Exception:row['metadata']='UNKNOWN'
   result['container_metadata'].append(row)
 print(json.dumps(result,sort_keys=True),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'status':'HOLD','exception':type(e).__name__}),flush=True);raise SystemExit(2)
