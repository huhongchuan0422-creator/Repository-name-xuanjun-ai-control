"""Read-only epoch5 partial-provision reconciliation, not installation admission.

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
 '/var/lib/xuanjun-development/activation/active.json':'d936af6b07d8d47583b7c49e2736b8387f0ed35b19971130372e76d6a34a37bc',
 T+'/tls-lifecycle.json':'8bdd9e5a40a21980f342ca0c2c98e2c5efffd7543e981855ad4481f63e5b7c14',
 T+'/runtime-provisioning.json':'b106258604fc7423786e18d46d249ef9826f8cd8c0eb29ed580c968bdbe8e3f0',
 T+'/bootstrap-files.json':'ab9386e0068796a7290847647c77242b7c83b88117e3036ca20998661c250cda',
 T+'/publisher-bootstrap.json':'dde7083c8141d254eb254d90b4d442d8da31678995ce7aa21188e279cb4e5da8',
 C+'/protected-core-install-plan.json':'ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a'}
PINS.update({T+'/epoch3-recovery-execution.json':'8550b672ced35e5f5812321094bd1a6087c2985f03be7b8101f829a0217a7ebe',T+'/epoch4-runtime-provisioning.json':'b9b6ad864fab37b877471242f2338b1d0724b72f5ab09c12b8e4fd12f1679793',T+'/epoch4-tls-renewal-candidate.json':'a079c2d38b2c033b0a32c5b34d5995e1fb9588600ac7d2b44c6f8f9f091f515c','/etc/xuanjun-development/p2-native-binding.json':'91c65c9fbc5c2cf68648672b4c096d7df376ecfbc605bc4cc838300bd302f629','/var/lib/xuanjun-development/activation/epochs.jsonl':'0e1c7aeadeaaad43386948edd01abf7572e3a666fa46325765626c720b80f092'})
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
NATIVE='/etc/xuanjun-development/p2-native-binding.json'
NATIVE_BEFORE_SHA='94598c41b7b3342ee7be5206577d127a3c3e90f06972a2160ffdd35e6949da98'
NATIVE_AFTER={'state':'FILE','sha256':'91c65c9fbc5c2cf68648672b4c096d7df376ecfbc605bc4cc838300bd302f629','uid':0,'gid':0,'mode':0o644,'dev':64771,'ino':1838476,'nlink':1,'size':831}
def recognized_native_rebind(row,value,temporary):
 return (row['target']==NATIVE and row['sha256']==NATIVE_BEFORE_SHA and
         row['state']=='PUBLISHED' and (row['owner_uid'],row['group_gid'],row['mode'])==(0,0,0o644) and
         temporary['state']=='ABSENT' and value==NATIVE_AFTER)

def main():
 need(os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ','FIXED_ROOT_HOST')
 values={}
 for path,wanted in PINS.items():
  data,i=file_data(path);need(sha(data)==wanted,'PIN_CHANGED:'+os.path.basename(path));values[path]=None if path.endswith('/epochs.jsonl') else json.loads(data.decode())
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
  bootstrap.append({'target':row['target'],'journal_state':row['state'],'published_identity_matches':match,'recognized_epoch4_native_rebind':recognized_native_rebind(row,v,temp),'observed':v,'temporary':temp['state']})
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
 from observe_epoch5 import parse_only
 parse_proof=parse_only()
 result={'schema':1,'regular_config_parse_only':parse_proof,'epoch':values['/var/lib/xuanjun-development/activation/active.json']['epoch'],'pins':PINS,'provision_targets':observed,'bootstrap':bootstrap,'publisher':pub,'publisher_content_verification':'NOT_PERFORMED_BY_THIS_COLLECTOR','rpm_journal_sha256':sha(data),'rpm_journal_state':rpm.get('state'),'rpm_versions':versions,'tls':tls,'production_mutations':0,'install_admission':'NOT_GRANTED'}
 for path,wanted in PINS.items():need(sha(file_data(path)[0])==wanted,'RECEIPT_CHANGED_DURING_READ')
 packed=json.dumps(result,sort_keys=True,separators=(',',':'))
 print('EPOCH5_PARTIAL_EFFECTS='+packed);print('EPOCH5_PARTIAL_EFFECTS_SHA256='+sha(packed.encode()))
 print('OBSERVATION_ONLY_NOT_RESUME_ADMISSION')
if __name__=='__main__':main()
