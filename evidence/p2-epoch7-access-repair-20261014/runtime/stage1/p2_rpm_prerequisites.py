"""Fixed, signed RPM payload transaction; no scripts, triggers, downloads or service starts."""
import grp,json,os,pwd,re,stat,subprocess
from ledger_cutover_transaction import _atomic_receipt
from p2_bootstrap_files import private_read,hash_bytes
NAMES=frozenset(('alinux-logos-httpd','certbot','nginx','nginx-filesystem','python-josepy-doc','python3-acme','python3-certbot','python3-configargparse','python3-distro','python3-josepy','python3-parsedatetime','python3-pyrfc3339','python3-requests-toolbelt','python3-zope-component','python3-zope-event','python3-zope-interface'))
CACHE='/tmp/p2pkg-38369525772-1/tls-rpm-preparation'
OLD_UNITS=('xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service')
FORBIDDEN={'/etc/passwd','/etc/shadow','/etc/group','/etc/gshadow'}
def command(args,check=True):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
 if len(p.stdout)+len(p.stderr)>16777216 or (check and p.returncode):raise ValueError('RPM_COMMAND_FAILED')
 return p
def package_bytes(item):
 path=item['path']
 if os.path.dirname(path)!=CACHE or os.path.realpath(path)!=path or not path.endswith('.rpm'):raise ValueError('RPM_CACHE_SCOPE')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());raw=f.read(67108865);end=os.fstat(f.fileno())
  if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o400 or s.st_nlink!=1 or len(raw)>67108864 or hash_bytes(raw)!=item['sha256'] or (s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(end.st_size,end.st_mtime_ns,end.st_ctime_ns):raise ValueError('RPM_CACHE_HASH_IDENTITY')
def version(name):
 p=command(['/bin/rpm','-q','--qf','%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}',name],False)
 if p.returncode==1:return None
 if p.returncode!=0:raise ValueError('RPM_INSTALLED_QUERY')
 return p.stdout.decode().split()
class RpmPrerequisites:
 def __init__(self,directory):self.directory=directory;self.path=directory+'/rpm-prerequisites.json'
 def authority(self):
  s=os.lstat(self.directory)
  if os.geteuid()!=0 or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o700 or not stat.S_ISDIR(s.st_mode) or os.path.realpath(self.directory)!=self.directory:raise ValueError('RPM_ROOT_AUTHORITY')
 def prepare(self,ref,prerequisites):
  self.authority()
  if not isinstance(ref,dict) or set(ref)!={'path','sha256'} or not isinstance(ref['path'],str) or not ref['path'].startswith('/var/lib/xuanjun-p2-preparation/'):raise ValueError('RPM_EXACT_REFERENCE')
  raw=private_read(ref['path'])
  if hash_bytes(raw)!=ref['sha256']:raise ValueError('RPM_BASELINE_HASH')
  data=json.loads(raw.decode());rows=data.get('packages')
  if data.get('schema')!=1 or not isinstance(rows,list) or len(rows)!=16 or {r['name'] for r in rows}!=NAMES:raise ValueError('RPM_EXACT_PACKAGE_SET')
  nginx=prerequisites.get('users',{}).get('nginx')
  if not isinstance(nginx,dict) or (nginx.get('uid'),nginx.get('gid'),nginx.get('home'),nginx.get('groups'))!=(1008,1008,'/var/lib/xuanjun-development/nginx-home',[]):raise ValueError('RPM_DEDICATED_NGINX_IDENTITY')
  paths=[];seen=set();count=0
  for item in rows:
   if item['before'] is not None or item.get('state')!='NEW_PACKAGE' or item['path'] in seen:raise ValueError('RPM_NEW_ONLY')
   candidate=item['candidate']
   if not isinstance(candidate,list) or len(candidate)!=5 or candidate[0]!=item['name'] or any(not isinstance(x,str) or re.fullmatch(r'[A-Za-z0-9_.+:-]+',x) is None for x in candidate):raise ValueError('RPM_CANDIDATE_IDENTITY')
   seen.add(item['path']);package_bytes(item)
   sig=command(['/bin/rpm','--checksig',item['path']]);text=(sig.stdout+sig.stderr).decode()
   if 'OK' not in text or 'NOKEY' in text or 'NOT OK' in text:raise ValueError('RPM_SIGNATURE')
   meta=command(['/bin/rpm','-qp','--qf','%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}',item['path']])
   if meta.stdout.decode().split()!=candidate or version(item['name']) is not None:raise ValueError('HOLD_RPM_ALREADY_INSTALLED_OR_CHANGED')
   files=command(['/bin/rpm','-qp','--qf','[%{FILENAMES}\t%{FILEMODES:octal}\n]',item['path']])
   for line in files.stdout.decode().splitlines():
    path,mode=line.rsplit('\t',1);count+=1
    if count>50000 or not path.startswith('/') or '..' in path.split('/') or path in FORBIDDEN:raise ValueError('RPM_PAYLOAD_SCOPE')
    if not stat.S_ISDIR(int(mode,8)) and os.path.lexists(path):raise ValueError('HOLD_RPM_PAYLOAD_PRESENT')
   paths.append(item['path'])
  command(['/bin/rpm','-U','--test']+paths)
  return rows
 @staticmethod
 def require_quiesced():
  for unit in OLD_UNITS:
   p=command(['/usr/bin/systemctl','show',unit,'--property=ActiveState,SubState,MainPID,UnitFileState,ControlGroup'])
   value=dict(line.split('=',1) for line in p.stdout.decode().splitlines() if '=' in line)
   if value.get('ActiveState')!='inactive' or value.get('SubState')!='dead' or value.get('MainPID')!='0' or value.get('UnitFileState') not in ('masked','masked-runtime') or value.get('ControlGroup') not in ('','/system.slice/'+unit):raise ValueError('HOLD_RPM_OLD_EXECUTOR_NOT_QUIESCED')
   for group in ('/sys/fs/cgroup/systemd/system.slice/'+unit,):
    if os.path.isdir(group):
     for parent,dirs,files in os.walk(group):
      if 'cgroup.procs' in files:
       with open(parent+'/cgroup.procs') as f:
        if f.read(1048576).strip():raise ValueError('HOLD_RPM_OLD_CGROUP_NONEMPTY')
 def apply(self,ref,prerequisites):
  if os.path.lexists(self.path):raise ValueError('HOLD_RPM_EXISTING_TRANSACTION')
  rows=self.prepare(ref,prerequisites);self.require_quiesced()
  user=pwd.getpwnam('nginx');group=grp.getgrnam('nginx')
  if (user.pw_uid,user.pw_gid,user.pw_dir,user.pw_shell)!=(1008,1008,'/var/lib/xuanjun-development/nginx-home','/sbin/nologin') or group.gr_gid!=1008 or group.gr_mem or set(os.getgrouplist('nginx',1008))!={1008}:raise ValueError('HOLD_RPM_NGINX_IDENTITY_CHANGED')
  row={'schema':1,'reference':ref,'packages':rows,'state':'INSTALL_INTENT'};_atomic_receipt(self.path,row)
  command(['/bin/rpm','-U','--noscripts','--notriggers']+[r['path'] for r in rows])
  if any(version(r['name'])!=r['candidate'] for r in rows):raise ValueError('HOLD_RPM_INSTALL_ACK_MISMATCH')
  row['state']='INSTALLED';_atomic_receipt(self.path,row)
 def rollback_rows(self):
  if not os.path.lexists(self.path):return []
  self.authority();row=json.loads(private_read(self.path).decode());rows=row.get('packages')
  if row.get('schema')!=1 or row.get('state') not in ('INSTALL_INTENT','INSTALLED','ERASE_INTENT','RESTORED') or not isinstance(rows,list) or len(rows)!=16 or {r['name'] for r in rows}!=NAMES:raise ValueError('RPM_ROLLBACK_SCHEMA')
  source=private_read(row['reference']['path'])
  if hash_bytes(source)!=row['reference']['sha256'] or json.loads(source.decode()).get('packages')!=rows:raise ValueError('RPM_ROLLBACK_BASELINE_CHANGED')
  installed=[]
  for item in rows:
   current=version(item['name'])
   if current is None:
    if row['state']=='INSTALLED':raise ValueError('HOLD_RPM_INSTALLED_PACKAGE_MISSING')
    continue
   if row['state']=='RESTORED' or current!=item['candidate']:raise ValueError('HOLD_RPM_ROLLBACK_VERSION_CHANGED')
   # All installed payloads must validate before removing even one package.
   p=command(['/bin/rpm','-V',item['name']],False)
   if p.returncode or p.stdout.strip():raise ValueError('HOLD_RPM_ROLLBACK_PAYLOAD_CHANGED')
   installed.append(item['name'])
  if installed:command(['/bin/rpm','-e','--test','--noscripts','--notriggers']+installed)
  return installed
 def rollback(self):
  installed=self.rollback_rows()
  if not os.path.lexists(self.path):return
  row=json.loads(private_read(self.path).decode())
  if installed:
   for unit in ('nginx.service','certbot-renew.service','certbot-renew.timer'):
    p=command(['/usr/bin/systemctl','show',unit,'--property=ActiveState,MainPID'])
    value=dict(line.split('=',1) for line in p.stdout.decode().splitlines() if '=' in line)
    if value.get('ActiveState') not in ('inactive','failed') or value.get('MainPID')!='0':raise ValueError('HOLD_RPM_NEW_SERVICE_STILL_RUNNING')
   row['state']='ERASE_INTENT';_atomic_receipt(self.path,row)
   command(['/bin/rpm','-e','--noscripts','--notriggers']+installed)
  if any(version(r['name']) is not None for r in row['packages']):raise ValueError('HOLD_RPM_ERASE_ACK_MISMATCH')
  row['state']='RESTORED';_atomic_receipt(self.path,row)
