"""Read-only epoch3 partial-provision reconciliation, not installation admission.

No package imports, credentials printed, cert issuance, services changed or DB
connections. Private bootstrap files are read only to compare their digests.
"""
import hashlib,json,os,stat,socket,subprocess,sys,tempfile
B='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
C=B+'/complete-install-candidate-38503014520'
T=B+'/legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5'
TLS='/var/lib/xuanjun-development/tls-acme'
PINS={
 C+'/install-receipt.json':'49cb3537b6d23419a670e2f5c0a73c34cf7cfea98f449b5bec6ef25179e1449b',
 T+'/recovery-execution.json':'76de78cdd58e899bcb40b79162c8c44c4785cc13a88b541f5d850fe97181a766',
 '/var/lib/xuanjun-development/activation/active.json':'4f8f6f218a7f62b203a2961dffdeaec6d1bcf6d9f24f78fae7fccc2581b834cd',
 T+'/tls-lifecycle.json':'dd9de0ad6a64c25da4a60f48912a931de1f3b5d26c1c9445aa73cce70fb67340',
 T+'/runtime-provisioning.json':'b106258604fc7423786e18d46d249ef9826f8cd8c0eb29ed580c968bdbe8e3f0',
 T+'/bootstrap-files.json':'ab9386e0068796a7290847647c77242b7c83b88117e3036ca20998661c250cda',
 T+'/publisher-bootstrap.json':'dde7083c8141d254eb254d90b4d442d8da31678995ce7aa21188e279cb4e5da8',
 C+'/protected-core-install-plan.json':'ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a'}
def sha(b):return hashlib.sha256(b).hexdigest()
def need(v,label):
 if not v:raise ValueError(label)
def file_data(path):
 need(os.path.realpath(path)==path,'PATH_ALIAS')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  before=os.fstat(f.fileno());need(stat.S_ISREG(before.st_mode),'REGULAR_REQUIRED')
  data=f.read(2097153);after=os.fstat(f.fileno())
 need(len(data)<=2097152,'FILE_BOUND')
 need((before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'FILE_RACE')
 return data,before
def metadata(path):
 try:i=os.lstat(path)
 except FileNotFoundError:return {'state':'ABSENT'}
 if stat.S_ISLNK(i.st_mode):return {'state':'SYMLINK','target':os.readlink(path)}
 if stat.S_ISDIR(i.st_mode):return {'state':'DIRECTORY','uid':i.st_uid,'gid':i.st_gid,'mode':stat.S_IMODE(i.st_mode),'dev':i.st_dev,'ino':i.st_ino}
 data,i=file_data(path)
 return {'state':'FILE','sha256':sha(data),'uid':i.st_uid,'gid':i.st_gid,'mode':stat.S_IMODE(i.st_mode),'dev':i.st_dev,'ino':i.st_ino,'nlink':i.st_nlink,'size':len(data)}
def main():
 need(os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ','FIXED_ROOT_HOST')
 values={}
 for path,wanted in PINS.items():
  data,i=file_data(path);need(sha(data)==wanted,'PIN_CHANGED:'+os.path.basename(path));values[path]=json.loads(data.decode())
 provision=values[T+'/runtime-provisioning.json'];rows=provision['targets'];need(len(rows)==24,'TARGET_COUNT')
 observed=[]
 for row in rows:
  path=row['target'];v=metadata(path);previous=row['previous']
  if previous is None:match=v['state']=='ABSENT'
  elif previous.get('masked') is True:match=v=={'state':'SYMLINK','target':'/dev/null'}
  else:match=v['state']=='FILE' and tuple(v[k] for k in ('sha256','mode','uid','gid'))==tuple(previous[k] for k in ('sha256','mode','uid','gid'))
  observed.append({'target':path,'original_state_matches':match,'observed':v})
 bootstrap=[]
 for row in values[T+'/bootstrap-files.json']['files']:
  v=metadata(row['target']);temp=metadata(row['temp'])
  match=v['state']=='FILE' and all(v[k]==row[k] for k in ('sha256','dev','ino','mode')) and v['uid']==row['owner_uid'] and v['gid']==row['group_gid'] and temp['state']=='ABSENT'
  bootstrap.append({'target':row['target'],'journal_state':row['state'],'published_identity_matches':match,'observed':v,'temporary':temp['state']})
 pub=[]
 for row in values[T+'/publisher-bootstrap.json']['directories']:
  v=metadata(row['target']);stage=metadata(row['stage'])
  pub.append({'target':row['target'],'journal_state':row['state'],'observed':v,'stage_state':stage['state'],'journal_fingerprint':row['fingerprint'],'root_identity_matches':v.get('dev')==row['dev'] and v.get('ino')==row['ino']})
 rpm_path=T+'/rpm-prerequisites.json';data,i=file_data(rpm_path);rpm=json.loads(data.decode());versions=[]
 for row in rpm['packages']:
  name=row['name'];need(name and all(c.isalnum() or c in '-_.' for c in name),'RPM_NAME')
  p=subprocess.run(['/bin/rpm','-q','--qf','%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}',name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
  actual=p.stdout.decode().split();versions.append({'name':name,'query_rc':p.returncode,'matches_candidate':p.returncode==0 and actual==row['candidate'],'version':actual})
 tls={}
 for name in ('config','work','logs'):
  path=TLS+'/'+name;v=metadata(path);need(v['state']=='DIRECTORY','TLS_DIRECTORY')
  tls[name]={'metadata':v,'entries':sorted(os.listdir(path))}
 with tempfile.TemporaryDirectory(prefix='xuanjun-certbot-parse-') as scratch:
  cfg=scratch+'/client.ini'
  with open(cfg,'xb') as stream:pass
  os.chmod(cfg,0o600)
  code="from certbot._internal import cli; from certbot._internal.plugins import disco; import sys; v=cli.prepare_and_parse_args(disco.PluginsRegistry.find_all(), ['--non-interactive','-c',sys.argv[1],'--config-dir',sys.argv[2]+'/config','--work-dir',sys.argv[2]+'/work','--logs-dir',sys.argv[2]+'/logs','certonly','--server','https://acme-v02.api.letsencrypt.org/directory','--standalone','--preferred-challenges','http','--cert-name','uk.wenwenwenyiyiyi.work','-d','uk.wenwenwenyiyiyi.work','--agree-tos','--register-unsafely-without-email','--no-eff-email']); print('REGULAR_CONFIG_PARSE_ONLY_PASS')"
  parsed=subprocess.run(['/usr/bin/python3','-B','-c',code,cfg,scratch],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
  parse_proof={'returncode':parsed.returncode,'stdout':parsed.stdout.decode('utf-8','replace')[:8192],'stderr':parsed.stderr.decode('utf-8','replace')[:8192],'issuance_executed':False}
 result={'schema':1,'regular_config_parse_only':parse_proof,'epoch':values['/var/lib/xuanjun-development/activation/active.json']['epoch'],'pins':PINS,'provision_targets':observed,'bootstrap':bootstrap,'publisher':pub,'publisher_content_verification':'NOT_PERFORMED_BY_THIS_COLLECTOR','rpm_journal_sha256':sha(data),'rpm_journal_state':rpm.get('state'),'rpm_versions':versions,'tls':tls,'production_mutations':0,'install_admission':'NOT_GRANTED'}
 for path,wanted in PINS.items():need(sha(file_data(path)[0])==wanted,'RECEIPT_CHANGED_DURING_READ')
 packed=json.dumps(result,sort_keys=True,separators=(',',':'))
 print('EPOCH3_PARTIAL_EFFECTS='+packed);print('EPOCH3_PARTIAL_EFFECTS_SHA256='+sha(packed.encode()))
 print('OBSERVATION_ONLY_NOT_RESUME_ADMISSION')
if __name__=='__main__':main()
