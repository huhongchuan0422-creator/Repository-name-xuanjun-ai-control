"""Fixed-domain ACME lifecycle; exclusive installer lock and protected journal.

No production action is executed by preparation. Online issuance/dry-run is a
reviewed install step, before ACTIVE; failure retains evidence on rollback.
"""
import fcntl,hashlib,json,os,signal,socket,stat,subprocess,time
from ledger_cutover_transaction import _atomic_receipt
from p2_bootstrap_files import private_read
DOMAIN='uk.wenwenwenyiyiyi.work'
ROOT='/var/lib/xuanjun-development/tls-acme'
CONFIG='/etc/xuanjun-development/tls-renewal.json'
TIMER='xuanjun-p2-tls-renew.timer'
SERVICE='xuanjun-p2-tls-renew.service'
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
TX='c529c379-9341-4510-8384-fc6be1e412e5'

def require(v,c):
 if not v:raise ValueError(c)
def command_failure(out,err,returncode,reason,timeout,cleanup=None):
 failure={'schema':1,'reason':reason,'timeout_seconds':timeout,'returncode':returncode,'stdout_sha256':hashlib.sha256(out).hexdigest(),'stderr_sha256':hashlib.sha256(err).hexdigest(),'stdout':out[:1048576].decode('utf-8','replace'),'stderr':err[:1048576].decode('utf-8','replace'),'truncated':len(out)>1048576 or len(err)>1048576}
 if cleanup is not None:failure['cleanup']=cleanup
 # Private diagnostics are never copied into a public receipt.
 logdir=ROOT+'/logs';info=os.lstat(logdir)
 require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700 and os.path.realpath(logdir)==logdir,'TLS_DIAGNOSTIC_AUTHORITY')
 _atomic_receipt(logdir+'/command-failure.json',failure)
# A deadline on the first communicate does not bound inherited pipe holders.
# Cleanup has its own shared drain/reap budget; an escaped descendant is UNKNOWN.
COMMAND_CLEANUP_SECONDS=2.0
DIAGNOSTIC_STREAM_LIMIT=1048576

def command_partial_output(p,name,fallback):
 # CPython3.6 POSIX TimeoutExpired does not expose partial stdout/stderr.
 # Its completed nonblocking reads remain in this buffer. Copy at most limit+1
 # bytes, without reading the pipe or waiting; other runtimes use exception data.
 buffers=getattr(p,'_fileobj2output',None)
 chunks=buffers.get(getattr(p,name,None)) if isinstance(buffers,dict) else None
 if not isinstance(chunks,list):return fallback
 result=bytearray()
 for chunk in chunks:
  if not isinstance(chunk,bytes):return fallback
  room=DIAGNOSTIC_STREAM_LIMIT+1-len(result)
  if room<=0:break
  result.extend(chunk[:room])
 return bytes(result)

def bounded_command_cleanup(p,initial):
 deadline=time.monotonic()+COMMAND_CLEANUP_SECONDS
 out=getattr(initial,'output',None) or b'';err=getattr(initial,'stderr',None) or b''
 evidence={'budget_seconds':COMMAND_CLEANUP_SECONDS,'group_signal':'UNKNOWN',
           'direct_process':'UNKNOWN','output':'INCOMPLETE','descendants':'UNKNOWN'}
 try:
  try:os.killpg(p.pid,signal.SIGKILL);evidence['group_signal']='SENT'
  except ProcessLookupError:evidence['group_signal']='NOT_FOUND'
  except OSError as error:evidence['group_signal']='FAILED';evidence['signal_error_type']=type(error).__name__
  remaining=deadline-time.monotonic()
  if remaining>0:
   try:
    out,err=p.communicate(timeout=remaining);evidence['output']='COMPLETE'
   except subprocess.TimeoutExpired as error:
    # TimeoutExpired output is the cumulative capture; never concatenate twice.
    if error.output is not None:out=error.output
    if error.stderr is not None:err=error.stderr
   except BaseException as error:evidence['drain_error_type']=type(error).__name__
 finally:
  # Linux pipe readers have no background communicate threads. Closing them
  # abandons unbounded EOF waiting even when descendants escaped the killed PG.
  for name in ('stdout','stderr'):
   stream=getattr(p,name,None)
   if stream is not None:
    try:stream.close()
    except BaseException as error:evidence[name+'_close_error_type']=type(error).__name__
  remaining=deadline-time.monotonic()
  try:
   if p.poll() is None and remaining>0:p.wait(timeout=remaining)
   if p.returncode is not None:evidence['direct_process']='EXITED'
  except BaseException as error:evidence['reap_error_type']=type(error).__name__
 if evidence['output']!='COMPLETE':
  out=command_partial_output(p,'stdout',out);err=command_partial_output(p,'stderr',err)
 evidence['captured_output_truncated']=len(out)>DIAGNOSTIC_STREAM_LIMIT or len(err)>DIAGNOSTIC_STREAM_LIMIT
 # Hashes below describe retained prefixes when output was truncated/incomplete.
 return out[:DIAGNOSTIC_STREAM_LIMIT],err[:DIAGNOSTIC_STREAM_LIMIT],evidence

def command(args,timeout=180):
 p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
 try:out,err=p.communicate(timeout=timeout)
 except BaseException as error:
  out,err,cleanup=bounded_command_cleanup(p,error)
  timed_out=isinstance(error,subprocess.TimeoutExpired)
  command_failure(out,err,p.returncode,'TIMEOUT_BOUNDED_CLEANUP' if timed_out else 'INTERRUPTED_BOUNDED_CLEANUP',timeout,cleanup)
  if timed_out:raise ValueError('TLS_COMMAND_TIMEOUT_HOLD') from error
  raise
 if p.returncode!=0 or len(out)+len(err)>2097152:
  command_failure(out,err,p.returncode,'EXIT_OR_OUTPUT_BOUND',timeout)
  raise ValueError('TLS_EXTERNAL_COMMAND_FAILED_RC_'+str(p.returncode))
 return out
def validate(v):
 require(isinstance(v,dict) and set(v)=={'schema','domain','root','transaction_directory','transaction_id','instance','generation','ledger_uuid','release_sha256','accept_acme_terms'},'TLS_EXACT_CONFIG')
 require(v['schema']==1 and v['domain']==DOMAIN and v['root']==ROOT and v['transaction_id']==TX and v['transaction_directory']==BASE+'/legacy-isolation-'+TX and v['accept_acme_terms'] is True,'TLS_FIXED_SCOPE_AND_TERMS')
 require(type(v['generation']) is int and v['generation']>0 and all(isinstance(v[k],str) and len(v[k])==36 for k in ('instance','ledger_uuid')),'TLS_ACTIVATION_IDENTITY')
 require(isinstance(v['release_sha256'],str) and len(v['release_sha256'])==64 and all(c in '0123456789abcdef' for c in v['release_sha256']),'TLS_RELEASE_DIGEST')
 return v
def scan_error(error):
 raise error
def fingerprint(root):
 require(os.path.realpath(root)==root,'TLS_ROOT_ALIAS')
 i=os.lstat(root);require(stat.S_ISDIR(i.st_mode) and i.st_uid==0 and stat.S_IMODE(i.st_mode)==0o700,'TLS_ROOT_AUTHORITY')
 rows=[];total=0
 for parent,dirs,files in os.walk(root,followlinks=False,onerror=scan_error):
  for name in sorted(dirs+files):
   p=parent+'/'+name;s=os.lstat(p);rel=os.path.relpath(p,root)
   require(s.st_uid==0 and (stat.S_ISLNK(s.st_mode) or not s.st_mode&0o022),'TLS_TREE_AUTHORITY')
   if stat.S_ISLNK(s.st_mode):
    target=os.path.realpath(p);require(target.startswith(root+'/') and os.path.isfile(target),'TLS_SYMLINK_ESCAPE')
    rows.append([rel,'LINK',os.readlink(p)])
   elif stat.S_ISDIR(s.st_mode):rows.append([rel,'DIR',stat.S_IMODE(s.st_mode)])
   else:
    require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=16777216,'TLS_FILE_BOUND')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);h=hashlib.sha256()
    with os.fdopen(fd,'rb') as f:
     for b in iter(lambda:f.read(65536),b''):total+=len(b);require(total<=67108864,'TLS_TREE_BOUND');h.update(b)
    rows.append([rel,'FILE',stat.S_IMODE(s.st_mode),h.hexdigest()])
   require(len(rows)<=4096,'TLS_ENTRY_BOUND')
 return hashlib.sha256(json.dumps(sorted(rows),separators=(',',':')).encode()).hexdigest()
def cert_paths():return ROOT+'/config/live/'+DOMAIN+'/fullchain.pem',ROOT+'/config/live/'+DOMAIN+'/privkey.pem'
def certificate_check():
 cert,key=cert_paths()
 require(os.path.realpath(cert).startswith(ROOT+'/config/archive/'+DOMAIN+'/') and os.path.realpath(key).startswith(ROOT+'/config/archive/'+DOMAIN+'/'),'TLS_LINEAGE_PATH')
 host=command(['/usr/bin/openssl','x509','-in',cert,'-noout','-checkhost',DOMAIN]);require(b'does match certificate' in host,'TLS_CERT_DOMAIN')
 command(['/usr/bin/openssl','x509','-in',cert,'-noout','-checkend','86400'])
 require(command(['/usr/bin/openssl','x509','-in',cert,'-pubkey','-noout'])==command(['/usr/bin/openssl','pkey','-in',key,'-pubout']),'TLS_KEY_PAIR')
 return hashlib.sha256(command(['/usr/bin/openssl','x509','-in',cert,'-outform','DER'])).hexdigest()
def client_config(create=False):
 path=ROOT+'/client.ini'
 info=os.lstat(ROOT)
 require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700 and os.path.realpath(ROOT)==ROOT,'TLS_CLIENT_CONFIG_ROOT')
 if create:
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  try:os.fsync(fd)
  finally:os.close(fd)
  parent=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:os.fsync(parent)
  finally:os.close(parent)
 data=private_read(path)
 require(data==b'','TLS_CLIENT_CONFIG_NOT_EMPTY')
 return path
def base_args():return ['/usr/bin/certbot','--non-interactive','-c',client_config(),'--config-dir',ROOT+'/config','--work-dir',ROOT+'/work','--logs-dir',ROOT+'/logs']
def renewal_args(dry_run=False):
 # This caller already owns the scheduling/timeout policy. Certbot's internal
 # random sleep can exceed the entire bounded subprocess deadline.
 args=['renew','--cert-name',DOMAIN,'--no-directory-hooks','--no-random-sleep-on-renew']
 if dry_run:args.append('--dry-run')
 return args
def available_port():
 require({r[4][0] for r in socket.getaddrinfo(DOMAIN,80,socket.AF_INET)}=={'8.208.119.115'},'TLS_DNS_CHANGED')
 # A bounded bind check; no listener or ACME request during preparation.
 s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
 try:s.bind(('0.0.0.0',80))
 finally:s.close()

class TlsLifecycle:
 def __init__(self,directory):self.directory=directory;self.journal=directory+'/tls-lifecycle.json'
 def authority(self):
  require(os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ','TLS_FIXED_ROOT_HOST')
  require(self.directory==BASE+'/legacy-isolation-'+TX and os.path.realpath(self.directory)==self.directory,'TLS_EXACT_TRANSACTION')
  s=os.lstat(self.directory);require(s.st_uid==0 and stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==0o700,'TLS_TRANSACTION_AUTHORITY')
 def prepare(self,ref):
  self.authority();require(isinstance(ref,dict) and set(ref)=={'path','sha256'},'TLS_REFERENCE')
  data=private_read(ref['path']);require(hashlib.sha256(data).hexdigest()==ref['sha256'],'TLS_CONFIG_DRIFT');v=validate(json.loads(data.decode()))
  require(v['transaction_directory']==self.directory and not os.path.lexists(ROOT) and not os.path.lexists(self.journal),'TLS_EXISTING_TRANSACTION_HOLD')
  available_port();return v
 def apply(self,ref):
  v=self.prepare(ref);record={'schema':1,'config':v,'state':'REQUESTED','fingerprint':None}
  _atomic_receipt(self.journal,record);os.mkdir(ROOT,0o700)
  try:
   for name in ('config','work','logs'):os.mkdir(ROOT+'/'+name,0o700)
   client_config(create=True)
   command(base_args()+['certonly','--server','https://acme-v02.api.letsencrypt.org/directory','--standalone','--preferred-challenges','http','--cert-name',DOMAIN,'-d',DOMAIN,'--agree-tos','--register-unsafely-without-email','--no-eff-email'])
   record['certificate_sha256']=certificate_check()
   renewal=ROOT+'/config/renewal/'+DOMAIN+'.conf';require(os.path.realpath(renewal)==renewal and os.path.isfile(renewal),'TLS_RENEWAL_CONFIG_REQUIRED')
   # Actual staging-CA renewal rehearsal is part of admitted installation.
   command(base_args()+renewal_args(dry_run=True),timeout=240)
   record['state']='READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED'
  except Exception:
   record['state']='HOLD';raise
  finally:
   record['fingerprint']=fingerprint(ROOT);_atomic_receipt(self.journal,record)
  return record
 def rollback_check(self):
  self.authority()
  if not os.path.lexists(self.journal):require(not os.path.lexists(ROOT),'TLS_UNJOURNALED_ROOT');return None
  v=json.loads(private_read(self.journal).decode());validate(v['config'])
  if v['state']=='RETAINED_OFFLINE':
   require(not os.path.lexists(ROOT),'TLS_RETAINED_ROOT_REAPPEARED')
   if v['fingerprint'] is not None:require(v['fingerprint']==fingerprint(self.directory+'/retained-tls-acme'),'TLS_RETAINED_EVIDENCE_CHANGED')
   return v
  if not os.path.lexists(ROOT):require(v['fingerprint'] is None and v['state']=='REQUESTED','TLS_ROOT_MISSING');return v
  require(v['fingerprint']==fingerprint(ROOT),'TLS_UNKNOWN_FILE_CHANGE_HOLD');return v
 def rollback(self):
  v=self.rollback_check()
  if v is None or v['state']=='RETAINED_OFFLINE':return
  if os.path.lexists(ROOT):
   target=self.directory+'/retained-tls-acme';require(not os.path.lexists(target),'TLS_RETAIN_TARGET_EXISTS')
   os.rename(ROOT,target)
   source_parent=os.open(os.path.dirname(ROOT),os.O_RDONLY|os.O_DIRECTORY)
   try:os.fsync(source_parent)
   finally:os.close(source_parent)
   fd=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY)
   try:os.fsync(fd)
   finally:os.close(fd)
  v['state']='RETAINED_OFFLINE';_atomic_receipt(self.journal,v)

def renew():
 require(os.geteuid()==0,'TLS_RENEW_ROOT_REQUIRED')
 fd=os.open('/run/xuanjun-p2-install.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 try:
  s=os.fstat(fd);require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'TLS_INSTALL_LOCK_AUTHORITY')
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  config=validate(json.loads(private_read(CONFIG).decode()));manager=TlsLifecycle(config['transaction_directory']);record=manager.rollback_check()
  require(record is not None and record['config']==config and record['state']=='READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED','TLS_RENEW_JOURNAL_BINDING')
  from activation_control import ActivationStore
  store=ActivationStore('/var/lib/xuanjun-development/activation/active.json','/var/lib/xuanjun-development/activation/epochs.jsonl','/var/lib/xuanjun-development/activation/activation.lock')
  before=store.read(require_active=True)
  require(all(before[k]==config[k] for k in ('instance','generation','ledger_uuid','release_sha256')),'TLS_RENEW_ACTIVE_BINDING')
  available_port()
  try:
   command(base_args()+renewal_args());leaf=certificate_check()
   after=store.read(require_active=True);require(after==before,'TLS_RENEW_ACTIVATION_CHANGED')
   command(['/usr/sbin/nginx','-t','-c','/etc/xuanjun-development/nginx-main.conf']);command(['/usr/bin/systemctl','reload','nginx.service'])
   record['certificate_sha256']=leaf
  finally:
   record['fingerprint']=fingerprint(ROOT);_atomic_receipt(manager.journal,record)
 finally:os.close(fd)
