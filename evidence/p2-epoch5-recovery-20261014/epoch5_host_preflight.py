"""Concrete read-only epoch3 host gates; not a production resume entrypoint.

Reuse reviewed cc46 process/cgroup/scheduler/database observation functions.
Neither the old snapshot nor the consumed old resume function is called.
"""
import hashlib,json,os,socket,stat,subprocess,types
from inspect_epoch5 import C,T,PINS,file_data
from epoch5_retained_state import capture_retained
from epoch3_service_containment import ServiceContainment

SCANNER_SHA='45affbb3b9298999d7e71bfb93b3ef5cb824464000ac78a927fd7c388614d74e'
HOST='iZd7oeikknn1z21sq6ji6zZ'
RETAINED_MANIFEST='338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09'
ACTIVATION='/var/lib/xuanjun-development/activation/active.json'


def require(value,label):
 if not value:raise ValueError(label)
def sha(data):return hashlib.sha256(data).hexdigest()

def load_reviewed_scanner(path):
 raw,info=file_data(path)
 require(sha(raw)==SCANNER_SHA,'EPOCH5_REVIEWED_SCANNER_CHANGED')
 module=types.ModuleType('epoch3_reviewed_readonly_scanner');module.__file__=path
 exec(compile(raw,path,'exec'),module.__dict__)
 return module


def capture_host(new_manifest_sha,scanner):
 require(os.geteuid()==0 and socket.gethostname().split('.')[0]==HOST,'EPOCH5_HOST_ROOT')
 from activation_control import ActivationStore
 from ledger_backup import database_manifest
 from legacy_host_adapter import LegacyHostAdapter
 from p2_prerequisites import Prerequisites
 import p2_auxiliary_isolation as auxiliary
 plan_raw,unused=file_data(C+'/protected-core-install-plan.json')
 require(sha(plan_raw)==PINS[C+'/protected-core-install-plan.json'],'EPOCH5_ORIGINAL_PLAN')
 plan=json.loads(plan_raw.decode())
 retained=capture_retained(new_manifest_sha)
 prerequisites_sha=scanner.verify_prerequisites(Prerequisites(T),plan['runtime']['prerequisites'])
 old_root=plan['artifact']['root']
 require(old_root==C+'/xuanjun-p2-package','EPOCH5_ORIGINAL_ROOT')
 old_manifest_raw,unused=scanner.read(plan['artifact']['manifest'])
 require(sha(old_manifest_raw)==scanner.MANIFEST_SHA,'EPOCH5_ORIGINAL_MANIFEST')
 old_manifest=json.loads(old_manifest_raw.decode())
 old_release='/opt/xuanjun-control-releases/'+plan['runtime']['release_directory']
 scanner.validate_directories(old_root)
 scanner.validate_directories(old_release,retained_cache=True)
 scanner.validate_file_inventory(old_root,set(old_manifest['files'])|
                                 {'P2_PACKAGE_PROVENANCE.json','tools/p2-package-freeze.py','deploy/integration-manifest.json'})
 scanner.validate_file_inventory(old_release,set(old_manifest['files'])|
                                 set(scanner.RETAINED_CACHE_HASHES)|{'INTEGRATION_MANIFEST.json'})
 scanner.validate_release_metadata(old_release)
 require(sha(scanner.read(old_release+'/INTEGRATION_MANIFEST.json')[0])==scanner.MANIFEST_SHA,
         'EPOCH5_INSTALLED_MANIFEST')
 old_payloads=scanner.validate_release(old_root,old_release,old_manifest,scanner.MANIFEST_SHA)
 cache_evidence=scanner.validate_retained_caches(old_release,old_payloads)
 # The failed epoch3 release is retained, verified and never overwritten.
 retained_root=C+'/epoch3-recovery-candidate/xuanjun-p2-package'
 retained_release='/opt/xuanjun-control-releases/integration-338e488c4203e23d'
 retained_manifest_sha=RETAINED_MANIFEST
 retained_raw,unused=scanner.read(retained_root+'/deploy/integration-manifest.json')
 require(sha(retained_raw)==retained_manifest_sha,'EPOCH5_RETAINED_RELEASE_MANIFEST')
 retained_manifest=json.loads(retained_raw.decode())
 scanner.validate_directories(retained_root)
 scanner.validate_directories(retained_release)
 scanner.validate_file_inventory(retained_root,set(retained_manifest['files'])|{'P2_PACKAGE_PROVENANCE.json','tools/p2-package-freeze.py','deploy/integration-manifest.json'})
 scanner.validate_file_inventory(retained_release,set(retained_manifest['files'])|{'INTEGRATION_MANIFEST.json'})
 scanner.validate_release_metadata(retained_release)
 require(sha(scanner.read(retained_release+'/INTEGRATION_MANIFEST.json')[0])==retained_manifest_sha,'EPOCH5_RETAINED_INSTALLED_MANIFEST')
 scanner.validate_release(retained_root,retained_release,retained_manifest,retained_manifest_sha)
 # These paths must never have been reached by the failed TLS-first execution.
 for name in ('epoch5-recovery-execution.json','epoch6-runtime-provisioning.json',
              'runtime-boot.json','sandbox-profile.json','ledger-access.json'):
  require(not os.path.lexists(T+'/'+name),'EPOCH5_UNCLASSIFIED_LATER_EFFECT')
 require(os.path.isdir(T+'/epoch3-prior-receipts') and os.path.realpath(T+'/epoch3-prior-receipts')==T+'/epoch3-prior-receipts','EPOCH5_PRIOR_PRESERVATION_REQUIRED')
 require(not os.path.lexists(T+'/epoch5-prior-tls-lifecycle.json') and not os.path.lexists(T+'/epoch5-prior-native-binding.json'),'EPOCH5_RECONCILIATION_ALREADY_ATTEMPTED')
 new_release='/opt/xuanjun-control-releases/integration-'+new_manifest_sha[:16]
 require(not os.path.lexists(new_release),'EPOCH5_NEW_RELEASE_ALREADY_PRESENT')
 store=ActivationStore(ACTIVATION,os.path.dirname(ACTIVATION)+'/epochs.jsonl',
                       os.path.dirname(ACTIVATION)+'/activation.lock')
 unused,lock_info=scanner.read(store.lock_path)
 require(lock_info.st_gid==0 and stat.S_IMODE(lock_info.st_mode)==0o644,'EPOCH5_ACTIVATION_LOCK')
 active=store.read()
 require(active['state']=='PREPARED' and active['epoch']==5,'EPOCH5_ACTIVATION_STATE')
 journal,unused=scanner.read(store.epoch_journal)
 records=store._journal()
 require(records and records[-1][0]['descriptor']==active,'EPOCH5_ACTIVATION_JOURNAL_HEAD')
 auxiliary.verify(plan['runtime']['auxiliary_isolation'])
 adapter=LegacyHostAdapter(T)
 ref=plan['cutover']['legacy_isolation']
 for path,wanted in ((T+'/legacy-units.json',ref['legacy_state_sha256']),
                     (T+'/owner-isolation-receipt.json',ref['receipt_sha256']),
                     (ref['original_plan_path'],ref['original_plan_sha256'])):
  require(sha(scanner.read(path,private=True)[0])==wanted,'EPOCH5_LEGACY_REFERENCE')
 for unit in ('xj-uk-owner-notify.timer','xj-uk-owner-notify.service'):
  path='/etc/systemd/system/'+unit
  require(os.path.islink(path) and os.readlink(path)=='/dev/null','EPOCH5_NOTIFIER_MASK')
  scanner.notifier_cgroup_empty(unit)
 observation=adapter.measure_quiescence(plan['cutover']['legacy_bindings'])
 require(all(observation['proof'].get(k) is True for k in
             ('identity_verified','coordinator_inactive','parent_unit_inactive',
              'cgroups_empty','restart_inhibited')),'EPOCH5_LEGACY_QUIESCENCE')
 services=ServiceContainment(scanner).verify_all()
 cutover_raw,unused=scanner.read(T+'/ledger-cutover.json',private=True)
 cutover=json.loads(cutover_raw.decode())
 require(cutover.get('stage')=='STAGED' and cutover.get('source_replaced') is False and
         cutover.get('activation_executed') is False and cutover.get('task_replay') is False,
         'EPOCH5_CUTOVER_EFFECTS')
 paths=[plan['cutover'][k] for k in ('source','rollback_snapshot','staged_generation')]
 sets={};payloads={}
 for index,path in enumerate(paths):
  sets[path],payloads[path]=scanner.database_file_set(path,1002 if index==0 else 0,retained_source=index==0)
 require(scanner.manifest_from_copy(payloads[paths[1]],database_manifest)==cutover['migration']['rollback'] and
         scanner.manifest_from_copy(payloads[paths[2]],database_manifest)==cutover['migration']['generation'],
         'EPOCH5_DATABASE_MANIFEST')
 protected=tuple(p+s for p in paths for s in ('','-wal','-shm','-journal'))
 scanner.fd_exclusion(protected);scanner.no_runner_or_old_worker()
 scheduler=scanner.scheduler_exclusion()
 result=subprocess.run(['/usr/bin/systemctl','show',scanner.RUNNER,
                        '--property=MainPID,ActiveState,ConditionResult'],stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,timeout=15,check=False)
 state=dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)
 require(result.returncode==0 and state.get('MainPID')=='0' and state.get('ActiveState')=='inactive' and
         state.get('ConditionResult')=='no' and os.path.isfile('/run/xuanjun-p2-runner-isolation.guard'),
         'EPOCH5_RUNNER_ISOLATION')
 for index,path in enumerate(paths):
  require(scanner.database_file_set(path,1002 if index==0 else 0,retained_source=index==0)[0]==sets[path],
          'EPOCH5_DATABASE_RACE')
 scanner.fd_exclusion(protected)
 for path,wanted in PINS.items():require(sha(file_data(path)[0])==wanted,'EPOCH5_FINAL_PIN_RACE')
 require(scanner.read(store.epoch_journal)[0]==journal,'EPOCH5_JOURNAL_RACE')
 evidence={'schema':1,'epoch':5,'retained':retained['evidence'],
           'prerequisites_sha256':prerequisites_sha,'retained_cache_evidence':cache_evidence,
           'epoch_journal_sha256':sha(journal),'database_file_sets':sets,
           'cutover_sha256':sha(cutover_raw),'legacy_proof':observation['proof'],
           'new_service_exclusion':services,'scheduler_sha256':scheduler,
           'runner_isolated':True,'effects':0,'install_admission':'NOT_GRANTED'}
 return evidence,{'activation':store,'active':active,'adapter':adapter,'observation':observation,
                  'original_plan':plan,'retained':retained}
