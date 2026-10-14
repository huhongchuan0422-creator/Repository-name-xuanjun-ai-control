"""Concrete single-attempt host operations; invoked only by a verified kit loader.

The loader must authenticate all imported kit/runtime bytes before importing this
module. This file has no standalone CLI. Production admission remains unavailable
until the complete loader, tests, snapshot and independent review are delivered.
"""
import copy,hashlib,json,os,pathlib
from inspect_epoch5 import C,T,file_data
from epoch5_plan import compile_plan,canonical,sha,ROOT,TLS_CONFIG,MANIFEST
from epoch5_approval import expected,fetch
from epoch5_host_preflight import capture_host
from epoch5_attempt_journal import AttemptJournal
from epoch5_recovery_sequence import ContainmentIncomplete
from epoch3_install_lock import held
from epoch5_retained_runtime import RetainedEpoch5Runtime
from epoch3_service_containment import ServiceContainment
from epoch3_preserve import preserve_prior_receipts,exclusive_file
from epoch5_activation_rebind import rebind_prepared
from epoch5_native_binding import update as update_native
from prepare_epoch5_bindings import INSTALLER_SHA

POSTCHECK_SHA='e83b769b64547d75e130423b88684459d62f247ee1bd9b604d6740e3445bdb78'

def need(value,label):
 if not value:raise ValueError(label)

def load_functions(path,digest,name):
 raw,unused=file_data(path);need(sha(raw)==digest,'DRIVER_DEPENDENCY_HASH')
 ns={'__name__':name,'__file__':path};exec(compile(raw,path,'exec'),ns);return ns


class HostDriver:
 def __init__(self,scanner,kit_manifest_sha,snapshot_sha,review_body_sha,postchecker_path):
  self.scanner=scanner;self.kit_sha=kit_manifest_sha;self.snapshot_sha=snapshot_sha
  self.review_body_sha=review_body_sha;self.postchecker_path=postchecker_path
  self.journal=AttemptJournal(T);self.runtime=RetainedEpoch5Runtime(T)
  self.containment=ServiceContainment(scanner);self.context=None;self.authorization=None
  self.plan=None;self.lock_held=False;self.current=None;self.attempt_binding=None
  self.installer=load_functions(ROOT+'/scripts/uk-integration-install.py',INSTALLER_SHA,'epoch3_staging')
  self.postchecker=load_functions(postchecker_path,POSTCHECK_SHA,'epoch3_postchecks')
 def verify_approval(self,plan,review_id):
  # Recompile all private bindings from the exact original plan and runtime files.
  original,unused=file_data(C+'/protected-core-install-plan.json')
  compiled=compile_plan(original,C+'/xuanjun-p2-package',ROOT)
  need(canonical(compiled)==canonical(plan),'DRIVER_EXACT_COMPILED_PLAN')
  artifact=plan['artifact']
  self.installer['verify'](ROOT,artifact['manifest'],artifact['source_commit'],MANIFEST,artifact['source_tree'])
  wanted=expected(sha(canonical(plan)),self.kit_sha,MANIFEST,self.snapshot_sha)
  authorization=fetch(review_id,wanted)
  need(authorization['body_sha256']==self.review_body_sha,'DRIVER_APPROVAL_BODY_CHANGED')
  if self.authorization is not None:need(authorization==self.authorization,'DRIVER_APPROVAL_CHANGED')
  self.authorization=authorization;self.plan=copy.deepcopy(plan)
 def install_lock(self):
  from contextlib import contextmanager
  @contextmanager
  def guarded():
   with held():
    self.lock_held=True
    try:yield
    finally:self.lock_held=False
  return guarded()
 def preflight(self,plan):
  need(self.lock_held,'DRIVER_INSTALL_LOCK_REQUIRED')
  evidence,self.context=capture_host(MANIFEST,self.scanner)
  evidence['runtime_reference_checks']=self.runtime.preflight_retained(plan)
  need(not os.path.lexists(TLS_CONFIG),'DRIVER_TLS_REFERENCE_ALREADY_EXISTS')
  # Repeat live exclusion after read-only CLI inventory and reference checks.
  self.scanner.no_runner_or_old_worker();self.containment.verify_all()
  self.current=self.context['active']
  return evidence
 def verify_snapshot_binding(self,snapshot,approval):
  need(sha(canonical(snapshot))==self.snapshot_sha,'DRIVER_FRESH_SNAPSHOT_CHANGED')
 def create_attempt(self,state,plan,approval,snapshot):
  need(self.lock_held and self.authorization is not None,'DRIVER_NOT_ADMITTED')
  self.attempt_binding={'authorization':self.authorization,'plan_sha256':sha(canonical(plan)),
                        'snapshot_sha256':sha(canonical(snapshot)),'kit_manifest_sha256':self.kit_sha}
  self.journal.create(dict(state,**self.attempt_binding))
 def save_attempt(self,state):
  need(self.lock_held and self.attempt_binding is not None,'DRIVER_ATTEMPT_NOT_OWNED')
  self.journal.save(dict(state,**self.attempt_binding))
 def stage_exact_release(self,plan):
  a=plan['artifact']
  target=self.installer['install'](ROOT,a['manifest'],a['source_commit'],MANIFEST,a['releases'],
                                   enforce_root=True,expected_tree=a['source_tree'])
  need(target==a['releases']+'/'+plan['runtime']['release_directory'],'DRIVER_RELEASE_RESULT')
  return {'release':target,'manifest_sha256':MANIFEST,'files':102}
 def preserve_prior_receipts(self,plan):
  from inspect_epoch5 import PINS
  for path,wanted in PINS.items():need(sha(file_data(path)[0])==wanted,'DRIVER_PRIOR_RECEIPT_DRIFT')
  return {'prior_receipts_retained':True,'original_preservation_not_replayed':True}
 def rebind_prepared_epoch(self,plan):
  store=self.context['activation'];proposed=plan['activation_proposal']
  proof={'approval_body_sha256':self.authorization['body_sha256'],'snapshot_sha256':self.snapshot_sha,
         'recovery_plan_sha256':sha(canonical(plan)),'old_descriptor_sha256':store.head(self.current),
         'new_descriptor_sha256':store.head(proposed),'all_writers_excluded':True,
         'install_lock_held':self.lock_held,'retained_resources_verified':True}
  self.containment.verify_all();self.scanner.no_runner_or_old_worker()
  self.current=rebind_prepared(store,self.current,proposed,proof)
  retained=self.context['retained']
  native=update_native(retained['native_binding_before'],retained['native_binding_after'],MANIFEST)
  exclusive_file(TLS_CONFIG,plan['tls_config_bytes'].encode())
  return {'descriptor_sha256':store.head(self.current),'epoch':6,'native_binding':native,
          'tls_reference_sha256':sha(plan['tls_config_bytes'].encode())}
 def quiesce_exact_epoch(self,plan):
  observed=self.context['adapter'].measure_quiescence(plan['cutover']['legacy_bindings'])
  need(observed['proof']==self.context['observation']['proof'],'DRIVER_QUIESCENCE_CHANGED')
  self.current=self.context['activation'].transition('PREPARED','QUIESCED',6,self.current['instance'],observed['proof'])
  return {'state':self.current['state'],'epoch':self.current['epoch']}
 def provision_from_retained_resources(self,plan):
  release=plan['artifact']['releases']+'/'+plan['runtime']['release_directory']
  result=self.runtime.provision(release,plan['runtime'])
  need(result['failure_policy']=='FENCE_STOP_RETAIN_NO_REPLAY' and result['retained_resources_replayed'] is False,
       'DRIVER_PROVISION_POLICY')
  return result
 def reopen_existing_database(self,plan):
  result=self.runtime.reopen_database(self.current)
  need(result=={'database_reopened':True},'DRIVER_DATABASE_REOPEN')
  return result
 def activate_exact_epoch(self,plan):
  self.current=self.context['activation'].transition('QUIESCED','ACTIVE',6,self.current['instance'],{'database_reopened':True})
  return {'epoch':6,'state':'ACTIVE','descriptor_sha256':self.context['activation'].head(self.current)}
 def activate_new_services(self,plan):
  result=self.context['adapter'].restore_legacy_files(gateway_only=True)
  need(result=={'unit_files_restored':True,'services_restarted':False},'DRIVER_GATEWAY_REBIND')
  result=self.runtime.activate(plan['runtime'],self.current)
  need(result=={'services_active':True},'DRIVER_ACTIVATION_RESULT')
  return result
 def post_install_checks(self,plan):
  adapted=copy.deepcopy(plan)
  adapted['activation']=dict(plan['activation_proposal'],expected_epoch=5)
  return self.postchecker['post_install_checks'](adapted,ROOT,{'epoch':6})
 def fence_uncertain_activation(self,plan):
  store=self.context['activation'];actual=store.read()
  need(actual['instance']==self.current['instance'] and actual['epoch'] in (5,6),'DRIVER_FENCE_IDENTITY')
  fenced=store.fence(actual['epoch'],actual['instance'])
  self.current=fenced
  return {'epoch':fenced['epoch'],'state':fenced['state'],'descriptor_sha256':store.head(fenced)}
 def stop_exact_new_services(self,plan):return self.containment.stop_all()
 def verify_stopped_and_preserve_legacy_masks(self,plan):
  evidence={'operations':{},'verified_stopped':False,'legacy_masks_preserved':False}
  failures=[]
  def attempt(name,operation):
   try:
    result=operation()
    need(isinstance(result,dict) and bool(result),'DRIVER_CLEANUP_EVIDENCE_REQUIRED')
    # Validate serializability before recording; never let one result suppress
    # the remaining bounded cleanup or final observations.
    canonical(result)
    evidence['operations'][name]={'status':'OBSERVED','evidence':result}
   except BaseException as error:
    failures.append(name)
    evidence['operations'][name]={'status':'UNKNOWN','error_type':type(error).__name__}
  def restore_boot():
   self.runtime._restore_boot()
   return {'previous_boot_state_restored':True}
  def measure_legacy():
   observed=self.context['adapter'].measure_quiescence(plan['cutover']['legacy_bindings'])
   need(all(observed['proof'].get(k) is True for k in
       ('identity_verified','coordinator_inactive','parent_unit_inactive','cgroups_empty','restart_inhibited')),
       'DRIVER_FAILURE_LEGACY_ISOLATION')
   return {'legacy_proof':observed['proof']}
  # An uncertain first observation must NEVER skip any restart-inhibition work.
  attempt('stopped_before',self.containment.verify_all)
  attempt('boot',restore_boot)
  attempt('owner_masks',lambda:self.runtime.restore_retained_owner_masks(plan))
  attempt('legacy_masks',lambda:self.context['adapter'].restore_legacy_files(preserve_mask=True))
  # Re-observe both boundaries independently, even after any cleanup failure.
  attempt('stopped_after',self.containment.verify_all)
  attempt('legacy_after',measure_legacy)
  if failures:
   evidence['failed_operations']=failures
   raise ContainmentIncomplete(evidence)
  evidence.update(verified_stopped=True,previous_boot_state_restored=True,
                  original_owner_masks_restored=True,legacy_masks_preserved=True)
  return evidence
