"""Fixed-host read-only HOLD inventory. No production admission or ACME calls.

Only a temporary parser config is written, outside all production directories.
Private files are reported by hashes/metadata only, never contents.
"""
import os,stat,socket,hashlib,json,subprocess,tempfile
HOST='iZd7oeikknn1z21sq6ji6zZ'
B='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
C=B+'/complete-install-candidate-38503014520'
T=B+'/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5'
TLS='/var/lib/xuanjun-development/tls-acme'
ACTIVE='/var/lib/xuanjun-development/activation/active.json'
DOMAIN='uk.wenwenwenyiyiyi.work'
PINS={T+'/epoch3-recovery-execution.json':'8550b672ced35e5f5812321094bd1a6087c2985f03be7b8101f829a0217a7ebe',ACTIVE:'d936af6b07d8d47583b7c49e2736b8387f0ed35b19971130372e76d6a34a37bc',T+'/tls-lifecycle.json':'8bdd9e5a40a21980f342ca0c2c98e2c5efffd7543e981855ad4481f63e5b7c14',C+'/protected-core-install-plan.json':'ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a',T+'/runtime-provisioning.json':'b106258604fc7423786e18d46d249ef9826f8cd8c0eb29ed580c968bdbe8e3f0'}
def need(value,label):
 if not value:raise ValueError(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def identity(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_gid,s.st_nlink)
def read(path,limit=2097152):
 need(os.path.realpath(path)==path,'PATH_ALIAS')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 first=os.fstat(fd)
 if not stat.S_ISREG(first.st_mode):
  os.close(fd);raise ValueError('REGULAR_REQUIRED')
 with os.fdopen(fd,'rb') as f:
  raw=f.read(limit+1);last=os.fstat(f.fileno())
 need(len(raw)<=limit and identity(first)==identity(last) and identity(os.lstat(path))==identity(last),'FILE_BOUND_OR_RACE')
 return raw,first

def meta(path):
 try:s=os.lstat(path)
 except FileNotFoundError:return {'state':'ABSENT'}
 value={'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'dev':s.st_dev,'ino':s.st_ino,'nlink':s.st_nlink}
 if stat.S_ISLNK(s.st_mode):value.update(state='SYMLINK',target=os.readlink(path))
 elif stat.S_ISDIR(s.st_mode):value.update(state='DIRECTORY')
 else:
  raw,s=read(path,16777216);value.update(state='FILE',sha256=sha(raw),size=len(raw))
 return value

def tree(root):
 rows=[];total=0
 def failed(error):raise error
 for parent,dirs,files in os.walk(root,followlinks=False,onerror=failed):
  for name in sorted(dirs+files):
   path=parent+'/'+name;value=meta(path);value['path']=os.path.relpath(path,root)
   need(value['uid']==0 and (value['state']=='SYMLINK' or not value['mode']&0o022),'TLS_TREE_AUTHORITY')
   if value['state']=='SYMLINK':need(os.path.realpath(path).startswith(root+'/') and os.path.isfile(path),'TLS_LINK_ESCAPE')
   total+=value.get('size',0);rows.append(value)
   need(len(rows)<=4096 and total<=67108864,'TLS_TREE_BOUND')
 return sorted(rows,key=lambda v:v['path'])

def capture():
 values={}
 for path,wanted in PINS.items():
  raw,s=read(path);need(sha(raw)==wanted and s.st_uid==0 and not s.st_mode&0o022,'PIN_OR_AUTHORITY_CHANGED')
  values[path]=json.loads(raw.decode())
 active=values[ACTIVE];attempt=values[T+'/epoch3-recovery-execution.json'];tls=values[T+'/tls-lifecycle.json']
 need(active['epoch']==5 and active['state']=='PREPARED','EPOCH5_PREPARED_REQUIRED')
 need(attempt['stage']=='HOLD' and attempt['automatic_retry'] is False,'TERMINAL_HOLD_REQUIRED')
 need(tls['state']=='HOLD' and tls['certificate_sha256']=='f7caaaed2c24582a22df2f4708e8140a8f27007d64f1dd9436ce972e145fc6f6','RETAINED_CERTIFICATE_REQUIRED')
 original=values[T+'/runtime-provisioning.json']['targets']
 need(len(original)==24 and len({r['target'] for r in original})==24,'TARGET_COUNT')
 targets=[]
 for row in original:
  path=row['target'];need(path.startswith('/etc/') and '..' not in path.split('/'),'TARGET_PATH')
  value=meta(path);previous=row['previous']
  match=(value['state']=='ABSENT') if previous is None else (previous.get('masked') is True and value['state']=='SYMLINK' and value['target']=='/dev/null')
  targets.append({'target':path,'matches_original_absent_or_masked':match,'observed':value})
 paths=[T+'/'+name for name in ('epoch4-runtime-provisioning.json','epoch4-tls-renewal-candidate.json','runtime-boot.json','sandbox-profile.json','ledger-access.json','epoch3-prior-receipts/native-binding-original.json')]
 paths+=['/etc/xuanjun-development/p2-native-binding.json',os.path.dirname(ACTIVE)+'/epochs.jsonl',TLS+'/client.ini']
 records={path:meta(path) for path in paths}
 old_config=json.loads(read(T+'/epoch4-tls-renewal-candidate.json')[0].decode())
 need(old_config==tls['config'],'RETAINED_TLS_CONFIG_BINDING')
 new_release='/opt/xuanjun-control-releases/integration-338e488c4203e23d'
 records[new_release]=meta(new_release)
 records[new_release+'/INTEGRATION_MANIFEST.json']=meta(new_release+'/INTEGRATION_MANIFEST.json')
 tls_root=meta(TLS);need(tls_root['state']=='DIRECTORY' and tls_root['uid']==0 and tls_root['mode']==0o700,'TLS_ROOT_AUTHORITY')
 return {'pins':PINS,'active':{'epoch':active['epoch'],'state':active['state']},'completed':attempt['completed'],'targets':targets,'records':records,'tls_root':tls_root,'tls_inventory':tree(TLS)}

def parse_only():
 with tempfile.TemporaryDirectory(prefix='xuanjun-epoch5-parser-') as root:
  cfg=root+'/client.ini'
  with open(cfg,'xb'):pass
  os.chmod(cfg,0o600)
  code="import sys; from certbot._internal import cli; from certbot._internal.plugins import disco; args=['--non-interactive','-c',sys.argv[1],'--config-dir',sys.argv[2]+'/config','--work-dir',sys.argv[2]+'/work','--logs-dir',sys.argv[2]+'/logs','renew','--cert-name','uk.wenwenwenyiyiyi.work','--no-directory-hooks','--no-random-sleep-on-renew']; plugins=disco.PluginsRegistry.find_all(); a=cli.prepare_and_parse_args(plugins,args); b=cli.prepare_and_parse_args(plugins,args+['--dry-run']); assert a.random_sleep_on_renew is False and b.random_sleep_on_renew is False and b.dry_run is True; print('BOTH_RENEWAL_MODES_PARSE_ONLY_PASS')"
  p=subprocess.run(['/usr/bin/python3','-B','-c',code,cfg,root],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
  return {'returncode':p.returncode,'pass':p.returncode==0 and p.stdout.strip()==b'BOTH_RENEWAL_MODES_PARSE_ONLY_PASS','stderr_sha256':sha(p.stderr),'acme_called':False}

def main():
 need(os.geteuid()==0 and socket.gethostname().split('.')[0]==HOST,'FIXED_ROOT_HOST')
 first=capture();parsed=parse_only();last=capture()
 need(first==last,'OBSERVATION_CHANGED')
 result={'schema':1,'observation':first,'certbot_parse_only':parsed,'production_mutations':0,'install_admission':'NOT_GRANTED'}
 raw=json.dumps(result,sort_keys=True,separators=(',',':')).encode()
 print('EPOCH5_READ_ONLY_OBSERVATION='+raw.decode());print('EPOCH5_OBSERVATION_SHA256='+sha(raw))
 print('OBSERVATION_ONLY_NO_RESUME_NO_ISSUANCE')
if __name__=='__main__':main()
