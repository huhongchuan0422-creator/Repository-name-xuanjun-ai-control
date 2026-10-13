"""Extract vendor RPM effects from a previously hash-verified private baseline; no install."""
import os,sys,stat,socket,json,hashlib,subprocess
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
PATH=BASE+'/rpm-tls-baseline-38410346819/protected-rpm-tls-baseline.json'
DIGEST='f784c4809b77df7f75ded97209efc32ff8c69944be33028e59e9422dcae100ec'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path,mode,maximum=67108864):
 assert os.path.realpath(path)==path
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());raw=f.read(maximum+1)
  assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==mode and s.st_nlink==1 and len(raw)<=maximum
 return raw
def query(path,flag):
 p=subprocess.run(['/bin/rpm','-qp',flag,path],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 assert p.returncode==0 and len(p.stdout)<=16777216
 return p.stdout
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ' and len(sys.argv)==2 and sys.argv[1].isdigit()
raw=read(PATH,0o600);assert sha(raw)==DIGEST;baseline=json.loads(raw.decode());rows=[]
for item in baseline['packages']:
 assert item['before'] is None and sha(read(item['path'],0o400))==item['sha256']
 scripts=query(item['path'],'--scripts');triggers=query(item['path'],'--triggers');files=query(item['path'],'--list').decode().splitlines()
 assert len(files)<=50000 and all(p.startswith('/') and '/..' not in p for p in files)
 lifecycle=[p for p in files if '/systemd/' in p or '/cron' in p or '/init.d/' in p or '/logrotate.d/' in p]
 rows.append({'name':item['name'],'candidate':item['candidate'],'path':item['path'],'sha256':item['sha256'],'scripts':scripts.decode(),'triggers':triggers.decode(),'files':files,'lifecycle_files':lifecycle,'files_sha256':sha(('\n'.join(files)+'\n').encode())})
out=BASE+'/rpm-effects-'+sys.argv[1];os.mkdir(out,0o700)
value={'schema':1,'baseline_path':PATH,'baseline_sha256':DIGEST,'packages':rows,'install_admission':False}
raw=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode();path=out+'/protected-rpm-effects.json'
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
public={'state':'VENDOR_RPM_EFFECTS_READONLY_PREPARED','packages':[{'name':r['name'],'lifecycle_files':r['lifecycle_files'],'scripts_sha256':sha(r['scripts'].encode()),'triggers_sha256':sha(r['triggers'].encode()),'vendor_scripts':r['scripts'],'vendor_triggers':r['triggers']} for r in rows],'install':False,'services_changed':False,'model_calls':0,'writer_admission':False}
print(json.dumps(public,sort_keys=True));print('RPM_EFFECTS_PATH='+path);print('RPM_EFFECTS_SHA256='+sha(raw))
