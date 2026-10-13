"""Exercise the exact frozen RPM module in a disposable RPM root, with explicit fixture-only gates."""
import os,sys,stat,socket,json,hashlib,shutil,tempfile,subprocess,types,importlib.util
from unittest.mock import patch
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
PACKAGE=BASE+'/plan-p2pkg-38417154795-1/xuanjun-p2-package'
SOURCE='305a4f35fa1018d6dba3007d59aa03c3a6258ead'
TREE='a388ad2d28e0125c4790e409db146ec77410c081'
MANIFEST='5b8439e1434eb5b9ccbc76b1d24b043f9c31fb3442cc5746ec52d04d69c9b58e'
MODULE='b7e2ce848b2b7a15f738e50b4a3e245e1be661615448ec09adad6c022aa72086'
REF={'path':BASE+'/rpm-tls-baseline-38410346819/protected-rpm-tls-baseline.json','sha256':'f784c4809b77df7f75ded97209efc32ff8c69944be33028e59e9422dcae100ec'}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def run(args):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
 assert p.returncode==0,'RPM_COMPONENT_FIXTURE_COMMAND_FAILED'
 return p.stdout
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ' and len(sys.argv)==2 and sys.argv[1].isdigit()
spec=importlib.util.spec_from_file_location('frozen_verify',PACKAGE+'/scripts/uk-integration-install.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
v.verify(PACKAGE,PACKAGE+'/deploy/integration-manifest.json',SOURCE,MANIFEST,expected_tree=TREE)
with open(PACKAGE+'/stage1/p2_rpm_prerequisites.py','rb') as f:assert sha(f.read())==MODULE
sys.path.insert(0,PACKAGE+'/stage1');import p2_rpm_prerequisites as m
raw=m.private_read(REF['path']);assert sha(raw)==REF['sha256'];baseline=json.loads(raw);rows=baseline['packages']
for row in rows:
 assert m.version(row['name']) is None
 m.package_bytes(row)
wrapper=tempfile.mkdtemp(prefix='xj-p2-rpm-module-');os.chmod(wrapper,0o711)
root=wrapper+'/rootfs';os.mkdir(root,0o711);tx=wrapper+'/transaction';os.mkdir(tx,0o700)
public={'schema':1,'state':'HOLD_FROZEN_RPM_COMPONENT_FIXTURE','artifact_id':11824656512,'source_commit':SOURCE,'module_sha256':MODULE,'scope':'ISOLATED_PAYLOAD_AND_JOURNAL_ONLY','production_quiescence_gate_mocked':True,'nginx_nss_metadata_mocked':True,'host_nss_changed':False,'production_install':False,'host_services_changed':False,'canonical_ledger_changed':False,'model_calls':0,'writer_admission':False}
try:
 os.makedirs(root+'/etc');os.makedirs(root+'/var/lib/rpm');os.makedirs(root+'/usr/lib64')
 with open(root+'/etc/passwd','w') as f:f.write('root:x:0:0:root:/root:/bin/sh\nnginx:x:1008:1008:fixture:/var/lib/xuanjun-development/nginx-home:/sbin/nologin\n')
 with open(root+'/etc/group','w') as f:f.write('root:x:0:\nnginx:x:1008:\n')
 with open(root+'/etc/nsswitch.conf','w') as f:f.write('passwd: files\ngroup: files\n')
 if not os.path.lexists(root+'/lib64'):os.symlink('usr/lib64',root+'/lib64')
 nss='/usr/lib64/libnss_files.so.2'
 if os.path.exists(nss):
  real=os.path.realpath(nss);s=os.stat(real);assert s.st_uid==0 and not s.st_mode&0o022
  shutil.copy2(real,root+'/usr/lib64/libnss_files.so.2')
 rpm=['/bin/rpm','--root',root,'--dbpath','/var/lib/rpm'];run(rpm+['--initdb'])
 real_command=m.command;real_lexists=os.path.lexists
 def fixture_command(args,check=True):
  if args[0]=='/usr/bin/systemctl':
   return types.SimpleNamespace(returncode=0,stdout=b'ActiveState=inactive\nMainPID=0\n',stderr=b'')
  if args[0]=='/bin/rpm' and any(x in args for x in ('-q','-U','-e','-V')):
   args=rpm+args[1:]
   if '-U' in args or '-e' in args:args=args+['--nodeps'] # Fixture-only: no host dependency database.
  return real_command(args,check)
 def fixture_lexists(path):
  # Payload targets are queried only during prepare; journals and cached RPMs remain real.
  if isinstance(path,str) and not path.startswith((wrapper,BASE,m.CACHE)) and path.startswith('/'):
   return real_lexists(root+path)
  return real_lexists(path)
 prereq={'users':{'nginx':{'uid':1008,'gid':1008,'home':'/var/lib/xuanjun-development/nginx-home','groups':[]}}}
 component=m.RpmPrerequisites(tx)
 with patch.object(m,'command',side_effect=fixture_command),patch.object(m.os.path,'lexists',side_effect=fixture_lexists),patch.object(m.RpmPrerequisites,'require_quiesced',return_value=None),patch.object(m.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=1008,pw_gid=1008,pw_dir='/var/lib/xuanjun-development/nginx-home',pw_shell='/sbin/nologin')),patch.object(m.grp,'getgrnam',return_value=types.SimpleNamespace(gr_gid=1008,gr_mem=[])),patch.object(m.os,'getgrouplist',return_value=[1008]):
  component.apply(REF,prereq)
  assert all(m.version(r['name'])==r['candidate'] for r in rows)
  public['exact_component_install_ack']=True
  candidates=[]
  for parent,dirs,files in os.walk(root+'/var/lib/nginx'):
   info=os.stat(parent)
   if info.st_uid==1008 and info.st_mode&0o200 and not info.st_mode&0o002:candidates.append(parent)
  assert candidates,'NUMERIC_NGINX_PAYLOAD_IDENTITY_UNPROVEN'
  parent=sorted(candidates,key=len)[0];probe=parent+'/.p2-numeric-write'
  results=[]
  for uid in (1008,1002,1005):
   code="import os,sys\ntry:\n fd=os.open(sys.argv[1],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd);os.unlink(sys.argv[1]);print('ALLOWED')\nexcept PermissionError:print('DENIED')\n"
   p=subprocess.run(['/usr/bin/setpriv','--reuid='+str(uid),'--regid='+str(uid),'--clear-groups','/usr/bin/python3','-I','-B','-c',code,probe],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
   assert p.returncode==0;value=p.stdout.decode().strip()
   assert value==('ALLOWED' if uid==1008 else 'DENIED');results.append({'numeric_uid':uid,'nginx_payload_write':value})
  public['numeric_payload_access']=results
  component.rollback();component.rollback()
  assert not run(rpm+['-qa']).strip();public['exact_component_erase_and_replay_ack']=True
 for row in rows:assert m.version(row['name']) is None
 public['host_packages_absent_before_after']=True;public['state']='FROZEN_RPM_COMPONENT_REAL_PAYLOAD_JOURNAL_AND_ERASE_PASS'
finally:
 shutil.rmtree(wrapper);public['fixture_removed']=not os.path.lexists(wrapper)
out=BASE+'/rpm-component-'+sys.argv[1];os.mkdir(out,0o700);path=out+'/protected-rpm-component-receipt.json';raw=(json.dumps(public,sort_keys=True,separators=(',',':'))+'\n').encode()
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps(public,sort_keys=True));print('RPM_COMPONENT_RECEIPT_PATH='+path);print('RPM_COMPONENT_RECEIPT_SHA256='+sha(raw))
