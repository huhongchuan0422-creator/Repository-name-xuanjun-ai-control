"""Rehearse exact vendor RPM payload install/erase in an isolated root; never host installation."""
import os,sys,socket,stat,json,hashlib,subprocess,tempfile,shutil
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
BASELINE=BASE+'/rpm-tls-baseline-38410346819/protected-rpm-tls-baseline.json'
BASELINE_SHA='f784c4809b77df7f75ded97209efc32ff8c69944be33028e59e9422dcae100ec'
EFFECTS=BASE+'/rpm-effects-38411108032/protected-rpm-effects.json'
EFFECTS_SHA='aef9dc5502d2da938959bfa71a29f9848d233d129cc3d6e49436ac2cbfd10736'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path,mode,limit=67108864):
 assert os.path.realpath(path)==path
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());raw=f.read(limit+1)
  assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==mode and s.st_nlink==1 and len(raw)<=limit
 return raw
def command(args,check=True):
 p=subprocess.run(args,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
 assert len(p.stdout)+len(p.stderr)<=16777216
 if check and p.returncode:raise ValueError('ISOLATED_RPM_COMMAND_FAILED')
 return p
def host_absent(names):
 for name in names:assert command(['/bin/rpm','-q',name],False).returncode==1
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ' and len(sys.argv)==2 and sys.argv[1].isdigit()
raw=read(BASELINE,0o600);assert sha(raw)==BASELINE_SHA;baseline=json.loads(raw)
raw=read(EFFECTS,0o600);assert sha(raw)==EFFECTS_SHA;effects=json.loads(raw)
assert len(baseline['packages'])==16 and len(effects['packages'])==16
rows=baseline['packages'];names=[r['name'] for r in rows];paths=[]
for row in rows:
 assert row['before'] is None and sha(read(row['path'],0o400))==row['sha256'];paths.append(row['path'])
host_absent(names)
root=tempfile.mkdtemp(prefix='xj-p2-rpm-rehearsal-');os.chmod(root,0o700)
public={'schema':1,'state':'HOLD_ISOLATED_RPM_REHEARSAL','packages':16,'package_scripts_executed':False,'host_nss_changed':False,'production_install':False,'production_services_changed':False,'canonical_ledger_changed':False,'model_calls':0,'writer_admission':False}
try:
 os.makedirs(root+'/etc');os.makedirs(root+'/var/lib/rpm')
 # Synthetic account metadata exists only inside this disposable rpm root.
 with open(root+'/etc/passwd','w') as f:f.write('root:x:0:0:root:/root:/bin/sh\nnginx:x:1008:1008:synthetic:/var/lib/nginx:/sbin/nologin\n')
 with open(root+'/etc/group','w') as f:f.write('root:x:0:\nnginx:x:1008:\n')
 rpm=['/bin/rpm','--root',root,'--dbpath','/var/lib/rpm']
 command(rpm+['--initdb'])
 # Real host dependency resolution was validated separately by rpm-U--test.
 # nodeps here is restricted to disposable payload mechanics, not installation admission.
 command(rpm+['-U','--nodeps','--noscripts','--notriggers']+paths)
 for row in rows:
  fmt='%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}\n'
  p=command(rpm+['-q','--qf',fmt,row['name']]);assert p.stdout.decode().strip().split()==row['candidate']
 assert os.path.isfile(root+'/usr/sbin/nginx') and os.path.isfile(root+'/usr/bin/certbot')
 public['isolated_payload_install']=True
 command(rpm+['-e','--nodeps','--noscripts','--notriggers']+names)
 assert not command(rpm+['-qa']).stdout.strip()
 assert not os.path.lexists(root+'/usr/sbin/nginx') and not os.path.lexists(root+'/usr/bin/certbot')
 public['isolated_packages_removed']=True
 host_absent(names);public['host_packages_absent_before_after']=True
 public['state']='EXACT_RPM_ISOLATED_PAYLOAD_INSTALL_AND_ERASE_PASS'
finally:
 shutil.rmtree(root);public['fixture_removed']=not os.path.lexists(root)
out=BASE+'/rpm-rehearsal-'+sys.argv[1];os.mkdir(out,0o700)
value={'schema':1,'baseline_path':BASELINE,'baseline_sha256':BASELINE_SHA,'effects_path':EFFECTS,'effects_sha256':EFFECTS_SHA,'public_receipt':public,'production_install_admission':False}
raw=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode();path=out+'/protected-rpm-rehearsal.json'
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps(public,sort_keys=True));print('RPM_REHEARSAL_PATH='+path);print('RPM_REHEARSAL_SHA256='+sha(raw))
