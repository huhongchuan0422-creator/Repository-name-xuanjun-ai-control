"""Read-only diagnosis of rejected notifier preflight; no retry or effects."""
import hashlib,json,os,socket,stat,subprocess
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
B='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
D=B+'/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5'
paths=[B+'/legacy-isolation.lock',D,D+'/owner-isolation-receipt.json',D+'/legacy-units.json',D+'/xuanjun-uk-stage1-minimal.service.backup',D+'/xuanjun-uk-openclaw.service.backup',D+'/auxiliary-owner',D+'/auxiliary-owner/auxiliary-isolation-receipt.json',D+'/auxiliary-owner/xuanjun-uk-owner-callback.service.backup',D+'/auxiliary-owner/xuanjun-uk-owner-dashboard.service.backup',D+'/notifier',D+'/notifier/notifier-isolation-receipt.json','/home/xuanjun_dev/uk-stage1-minimal/state.sqlite','/home/xuanjun_dev/uk-owner-notify/owner_notify.py']
out={'schema':1,'effects':0,'inputs':{},'units':{}}
for p in paths:
 row={'exists':os.path.lexists(p)}
 if row['exists']:
  i=os.lstat(p);row.update(uid=i.st_uid,gid=i.st_gid,mode=stat.S_IMODE(i.st_mode),regular=stat.S_ISREG(i.st_mode),directory=stat.S_ISDIR(i.st_mode),size=i.st_size)
  if stat.S_ISREG(i.st_mode) and i.st_size<=1048576 and os.path.realpath(p)==p:
   fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
   with os.fdopen(fd,'rb') as f:b=f.read(1048577)
   row['sha256']=hashlib.sha256(b).hexdigest()
   if p==D+'/legacy-units.json':
    j=json.loads(b.decode());row['canonical_backup_paths']={u:v.get('backup') for u,v in j.get('units',{}).items()}
 out['inputs'][p]=row
out['original_transaction_filenames']=sorted(os.listdir(D))
for unit in ['xj-uk-owner-notify.timer','xj-uk-owner-notify.service','xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service','xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service']:
 r=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=Id,LoadState,FragmentPath,ActiveState,SubState,MainPID,ControlGroup,UnitFileState'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10)
 assert r.returncode==0
 out['units'][unit]=dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
out['cgroup_paths']={}
for unit in out['units']:
 p='/sys/fs/cgroup/systemd/system.slice/'+unit
 try:i=os.lstat(p);row={'exists':True,'directory':stat.S_ISDIR(i.st_mode),'symlink':stat.S_ISLNK(i.st_mode)}
 except FileNotFoundError:row={'exists':False}
 out['cgroup_paths'][unit]=row
print('NOTIFIER_PREFLIGHT_READONLY_DIAG='+json.dumps(out,sort_keys=True))
