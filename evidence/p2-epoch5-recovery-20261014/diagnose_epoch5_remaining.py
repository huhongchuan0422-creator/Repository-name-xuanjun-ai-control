"""Read-only grouped diagnosis, never installation admission or a resume entry."""
import os,sys,socket,hashlib,json,stat,re,types,subprocess
C='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
KIT=C+'/epoch5-recovery-candidate-v2'
ENTRY_SHA='7f3b78bb3c75cdeab9323351c148a4c8a4815ad17f416b56dc1e50944ac68383'
KIT_SHA='a2c6ccf8cb2ca840e3a1981cf494678e5b388eb5a39c4c4f2e0309626d7700fb'
RELEASE='/opt/xuanjun-control-releases/integration-338e488c4203e23d'
def need(v,c):
 if not v:raise ValueError(c)
def sha(b):return hashlib.sha256(b).hexdigest()
def checked(path):
 need(os.path.realpath(path)==path,'DIAG_PATH_ALIAS')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());b=f.read(2097153);z=os.fstat(f.fileno())
 need(stat.S_ISREG(a.st_mode) and (a.st_uid,a.st_gid,a.st_nlink)==(0,0,1) and not a.st_mode&0o022 and len(b)<=2097152,'DIAG_AUTHORITY')
 ident=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 need(ident(a)==ident(z)==ident(os.lstat(path)),'DIAG_READ_RACE')
 return b,a
results={}
def probe(name,fn):
 try:
  v=fn();results[name]={'status':'OBSERVED','evidence':v}
 except Exception as e:
  msg=str(e);results[name]={'status':'BLOCKED','error_type':type(e).__name__,'error_code':msg if re.fullmatch('[A-Z0-9_]{1,160}',msg) else 'DETAIL_REDACTED','error_sha256':sha(msg.encode())}
 print('CHECK='+json.dumps({name:results[name]},sort_keys=True),flush=True)
 return results[name].get('evidence')
def main():
 need(os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ','DIAG_HOST_ROOT')
 need(sys.flags.isolated and sys.dont_write_bytecode and sys.version_info[:2]==(3,6),'DIAG_PYTHON36_ISOLATED')
 raw,_=checked(KIT+'/epoch5_recovery_entry.py');need(sha(raw)==ENTRY_SHA,'DIAG_ENTRY_HASH')
 ns={'__name__':'verified_loader_definitions','__file__':KIT+'/epoch5_recovery_entry.py'}
 exec(compile(raw,ns['__file__'],'exec'),ns)
 root=ns['verify_kit'](KIT_SHA)
 sys.path[:0]=[KIT+'/helpers',root+'/stage1']
 from epoch5_host_preflight import load_reviewed_scanner
 from epoch3_install_lock import held
 from epoch5_plan import compile_plan,canonical,MANIFEST
 from inspect_epoch5 import T,PINS,file_data
 from epoch5_retained_state import capture_retained
 from epoch5_retained_runtime import RetainedEpoch5Runtime
 from epoch3_service_containment import ServiceContainment
 from activation_control import ActivationStore
 from ledger_backup import database_manifest
 from legacy_host_adapter import LegacyHostAdapter
 import p2_auxiliary_isolation as auxiliary
 scanner=load_reviewed_scanner(KIT+'/helpers/recover_exact_hold.py')
 original,_=file_data(C+'/protected-core-install-plan.json');need(sha(original)==PINS[C+'/protected-core-install-plan.json'],'DIAG_PLAN_HASH')
 old=json.loads(original.decode());plan=compile_plan(original,C+'/xuanjun-p2-package',root)
 def inventory():
  manifest_raw,_=checked(RELEASE+'/INTEGRATION_MANIFEST.json')
  need(sha(manifest_raw)=='338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09','DIAG_RETAINED_MANIFEST')
  document=json.loads(manifest_raw.decode());manifest=document['files'];rows=[];seen=set();dirs=[]
  verified=scanner.validate_release(C+'/epoch3-recovery-candidate/xuanjun-p2-package',RELEASE,document,sha(manifest_raw))
  def failed(e):raise e
  for parent,names,files in os.walk(RELEASE,followlinks=False,onerror=failed):
   meta=os.lstat(parent);need(stat.S_ISDIR(meta.st_mode) and os.path.realpath(parent)==parent,'DIAG_DIRECTORY_ALIAS')
   dirs.append({'path':os.path.relpath(parent,RELEASE),'mode':stat.S_IMODE(meta.st_mode),'uid':meta.st_uid,'gid':meta.st_gid})
   need(len(dirs)<=128,'DIAG_DIRECTORY_BOUND')
   for name in names:need(not os.path.islink(parent+'/'+name),'DIAG_CHILD_ALIAS')
   for name in sorted(files):
    p=parent+'/'+name;rel=os.path.relpath(p,RELEASE);data,s=checked(p);seen.add(rel)
    need(len(seen)<=256,'DIAG_FILE_BOUND')
    row={'path':rel,'sha256':sha(data),'size':len(data),'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid,'mtime_ns':s.st_mtime_ns,'ino':s.st_ino,'dev':s.st_dev}
    if rel in manifest:need(data==verified[p][1],'DIAG_RETAINED_SOURCE_HASH')
    elif rel!='INTEGRATION_MANIFEST.json':
     if re.fullmatch(r'stage1/__pycache__/[a-zA-Z0-9_]+\.cpython-36\.pyc',rel):
      source_rel='stage1/'+name[:-len('.cpython-36.pyc')]+'.py'
      try:
       source,source_info=checked(RELEASE+'/'+source_rel)
       need(source==verified[RELEASE+'/'+source_rel][1],'DIAG_CACHE_SOURCE')
       row['staging']=scanner.verify_cache_bytes(data,source,source_rel,source_info)
       row['source_sha256']=sha(source);row['compiled_source_match']=True
      except Exception as error:
       row['compiled_source_match']=False;row['validation_error_type']=type(error).__name__
       row['validation_error_code']=str(error) if re.fullmatch('[A-Z0-9_]{1,160}',str(error)) else 'DETAIL_REDACTED'
     rows.append(row)
  need(set(manifest).issubset(seen),'DIAG_SOURCE_MISSING')
  return {'source_files':len(manifest),'extra_files':rows,'directories':dirs}
 def activation():
  path='/var/lib/xuanjun-development/activation/active.json';store=ActivationStore(path,os.path.dirname(path)+'/epochs.jsonl',os.path.dirname(path)+'/activation.lock')
  active=store.read();records=store._journal()
  need(active['epoch']==5 and active['state']=='PREPARED' and records[-1][0]['descriptor']==active,'DIAG_ACTIVATION')
  return {'epoch':5,'state':'PREPARED','journal_sha256':sha(scanner.read(store.epoch_journal)[0])}
 def later_effects():
  paths=[T+'/'+n for n in ('epoch5-recovery-execution.json','epoch6-runtime-provisioning.json','epoch6-tls-renewal-candidate.json','epoch5-prior-tls-lifecycle.json','epoch5-prior-native-binding.json','runtime-boot.json','sandbox-profile.json','ledger-access.json')]
  paths+=['/opt/xuanjun-control-releases/integration-'+MANIFEST[:16]]
  present=[p for p in paths if os.path.lexists(p)];need(not present,'DIAG_LATER_EFFECT_PRESENT');return {'absent_paths':len(paths)}
 def legacy():
  auxiliary.verify(old['runtime']['auxiliary_isolation'])
  v=LegacyHostAdapter(T).measure_quiescence(old['cutover']['legacy_bindings'])
  need(all(v['proof'].get(k) is True for k in ('identity_verified','coordinator_inactive','parent_unit_inactive','cgroups_empty','restart_inhibited')),'DIAG_LEGACY_BUSY')
  return v['proof']
 def databases():
  raw,_=scanner.read(T+'/ledger-cutover.json',private=True);cut=json.loads(raw.decode())
  need(cut['stage']=='STAGED' and cut.get('source_replaced') is False and cut.get('activation_executed') is False and cut.get('task_replay') is False,'DIAG_CUTOVER_EFFECTS')
  paths=[old['cutover'][k] for k in ('source','rollback_snapshot','staged_generation')];sets={};payloads={}
  for i,p in enumerate(paths):sets[p],payloads[p]=scanner.database_file_set(p,1002 if i==0 else 0,retained_source=i==0)
  need(scanner.manifest_from_copy(payloads[paths[1]],database_manifest)==cut['migration']['rollback'] and scanner.manifest_from_copy(payloads[paths[2]],database_manifest)==cut['migration']['generation'],'DIAG_DB_MANIFEST')
  scanner.fd_exclusion(tuple(p+s for p in paths for s in ('','-wal','-shm','-journal')))
  for i,p in enumerate(paths):need(scanner.database_file_set(p,1002 if i==0 else 0,retained_source=i==0)[0]==sets[p],'DIAG_DB_RACE')
  return sets
 def runner():
  scanner.no_runner_or_old_worker()
  p=subprocess.run(['/usr/bin/systemctl','show',scanner.RUNNER,'--property=MainPID,ActiveState,ConditionResult'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
  state=dict(line.split('=',1) for line in p.stdout.decode().splitlines() if '=' in line)
  need(p.returncode==0 and state.get('MainPID')=='0' and state.get('ActiveState')=='inactive' and state.get('ConditionResult')=='no' and os.path.isfile('/run/xuanjun-p2-runner-isolation.guard'),'DIAG_RUNNER')
  return state
 def pins():
  for p,w in PINS.items():need(sha(file_data(p)[0])==w,'DIAG_FINAL_PIN_CHANGED')
  return {'count':len(PINS)}
 with held():
  probe('retained_release_inventory',inventory)
  probe('activation',activation)
  probe('later_effects',later_effects)
  probe('legacy_isolation',legacy)
  probe('new_service_exclusion',lambda:ServiceContainment(scanner).verify_all())
  probe('database_sets',databases)
  probe('runner_exclusion',runner)
  probe('scheduler_exclusion',scanner.scheduler_exclusion)
  probe('runtime_references_and_plugin',lambda:RetainedEpoch5Runtime(T).preflight_retained(plan))
  probe('final_pins',pins)
  probe('inventory_repeat',inventory)
  if results['retained_release_inventory']!=results['inventory_repeat']:results['inventory_stability']={'status':'BLOCKED'}
 print('DIAGNOSTIC_SUMMARY='+json.dumps({'checks':{k:v['status'] for k,v in results.items()},'report_sha256':sha(json.dumps(results,sort_keys=True,separators=(',',':')).encode()),'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'},sort_keys=True))
 print('READ_ONLY_GROUPED_DIAGNOSIS_COMPLETE_NO_RESUME_NO_CACHE_DELETE')
if __name__=='__main__':main()
