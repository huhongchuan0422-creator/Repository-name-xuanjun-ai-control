"""Narrow 477 backup assessment bridge; requires a trusted host resolver.

No built-in identity, registration or production host connection. Host owns
construction and current-cycle contract authorization. Never asserts COMPLETE.
"""
import time
import backup_component_hostcycle as component_module

class BackupAssessment:
 def __init__(self,component,tenant_id,required_context,clock=time.time):
  if type(component) is not component_module.BackupComponent:raise ValueError('component required')
  self.component=component;self.tenant_id=tenant_id;self.required_context=frozenset(required_context);self.clock=clock
 def __call__(self,binding):
  unknown={'state':'UNKNOWN','missing':[],'cycle_at':None}
  try:
   applicability=binding['applicability'];checks=applicability['required_checks']
   if not isinstance(checks,list) or checks!=sorted(set(checks)) or not checks or not set(checks)<=self.required_context:return unknown
   resolved,_=self.component.plan(binding)
   # HostContract.resolve must independently authenticate the reservation and
   # return the current authoritative artifact inventory; request text alone
   # does not constitute authorization or a policy/N-A waiver.
   if resolved['tenant_id']!=self.tenant_id:return unknown
   for k in component_module.BINDING:
    if k!='tenant_id' and resolved[k]!=binding.get(k):return unknown
   result=self.component.assess(binding,binding['backup_cycle_id'],binding['backup_manifest_sha256'],self.clock())
   if result is None:return {'state':'INCOMPLETE','missing':list(checks),'cycle_at':None}
   # Only source readback is positively mapped, conditional on the trusted
   # host's authoritative inventory/contract; all other requirements remain.
   missing=set(checks)
   if 'SOURCE' in result['artifact_categories']:missing.discard('SOURCE')
   if not missing:return unknown  # this bridge cannot establish COMPLETE
   return {'state':'INCOMPLETE','missing':sorted(missing),'cycle_at':result['cycle_at']}
  except Exception:return unknown
