"""Concrete provisioning continuation that never replays retained prerequisites.

Requires the full admitted recovery driver: fresh retained-state gate, exact new
plan/release, preserved TLS transaction and native binding update. This module
is not a stand-alone install command and deliberately has no rollback fallback.
"""
import hashlib,json,os,stat
from p2_fixed_host_runtime import FixedHostRuntime,_read_regular,_digest_bytes,ALLOWED_SERVICES,P2_PLUGIN_ID,GATEWAY_SERVICE
from p2_bootstrap_files import private_read
from p2_tls_lifecycle import TlsLifecycle,TIMER as TLS_TIMER,SERVICE as TLS_SERVICE
from ledger_cutover_transaction import _atomic_receipt
import p2_auxiliary_isolation as Auxiliary
from inspect_epoch3 import PINS,T


def need(value,label):
 if not value:raise ValueError(label)

class RetainedEpoch3Runtime(FixedHostRuntime):
 def __init__(self,directory,**kwargs):
  need(directory==T,'EPOCH3_RUNTIME_EXACT_TRANSACTION')
  super(RetainedEpoch3Runtime,self).__init__(directory,**kwargs)
  self.receipt_path=directory+'/epoch4-runtime-provisioning.json'
 def preflight_retained(self,plan):
  self._authority()
  runtime=plan['runtime']
  need(tuple(runtime['services'])==ALLOWED_SERVICES,'EPOCH3_SERVICE_ORDER')
  need(not os.path.lexists(self.receipt_path),'EPOCH3_PROVISION_ALREADY_ATTEMPTED')
  Auxiliary.verify(runtime['auxiliary_isolation'])
  from p2_sandbox_profile import SandboxProfile
  from p2_tls_lifecycle import validate,available_port
  SandboxProfile(self.directory).prepare(runtime['sandbox_policy'])
  config=validate(json.loads(plan['tls_config_bytes']))
  need(config['release_sha256']==plan['artifact']['manifest_sha256'],'EPOCH3_TLS_RELEASE')
  available_port()
  for ref in plan['auth']['references']+plan['tls']['references']:self._reference(ref)
  release=plan['artifact']['releases']+'/'+runtime['release_directory']
  seen=set()
  for row in runtime['provisioning']:
   source,target=self._binding(row,release,runtime['auxiliary_isolation'])
   need(target not in seen,'EPOCH3_DUPLICATE_TARGET');seen.add(target)
  need(len(seen)==24,'EPOCH3_TARGET_COUNT')
  need(not self._plugin_present(runtime),'EPOCH3_PLUGIN_ALREADY_PRESENT')
  # CLI inventory must not change any existing private reference.
  for ref in plan['auth']['references']+plan['tls']['references']:self._reference(ref)
  return {'references_verified':True,'plugin_absent':True,'tls_port_available':True}
 def provision(self,release,runtime):
  self._authority()
  need(not os.path.lexists(self.receipt_path),'EPOCH3_PROVISION_ALREADY_ATTEMPTED')
  need(release=='/opt/xuanjun-control-releases/'+runtime['release_directory'],'EPOCH3_RELEASE_PATH')
  Auxiliary.verify(runtime['auxiliary_isolation'])
  old_raw=private_read(self.directory+'/epoch3-prior-receipts/runtime-provisioning.json')
  need(hashlib.sha256(old_raw).hexdigest()==PINS[T+'/runtime-provisioning.json'],'EPOCH3_PRIOR_PROVISION_CHANGED')
  old=json.loads(old_raw.decode());previous={r['target']:r for r in old['targets']}
  bindings=runtime['provisioning']
  need(len(bindings)==24 and len(previous)==24 and len({r['target'] for r in bindings})==24
       and {r['target'] for r in bindings}==set(previous),'EPOCH3_TARGET_SET')
  prepared=[]
  for binding in bindings:
   source,target=self._binding(binding,release,runtime['auxiliary_isolation'])
   raw,unused=_read_regular(source)
   need(_digest_bytes(raw)==binding['source_sha256'],'EPOCH3_INSTALLED_SOURCE_HASH')
   data=self._render(raw,binding);prior=previous[target]['previous']
   if prior is None:need(not os.path.lexists(target),'EPOCH3_UNEXPECTED_TARGET')
   else:
    need(prior.get('masked') is True and Auxiliary.is_mask(target),'EPOCH3_ORIGINAL_MASK_REQUIRED')
   prepared.append({'target':target,'previous':prior,'rendered_sha256':binding['rendered_sha256'],
                    'mode':binding['mode'],'uid':binding['owner_uid'],'gid':binding['group_gid'],'data':data})
  tls=TlsLifecycle(self.directory);tls_config=tls.prepare(runtime['tls_renewal'])
  configs=[item for item in prepared if item['target']=='/etc/xuanjun-development/tls-renewal.json']
  need(len(configs)==1 and json.loads(configs[0]['data'].decode())==tls_config,'EPOCH3_TLS_CONFIG_BINDING')
  required={'/etc/systemd/system/'+TLS_TIMER,'/etc/systemd/system/'+TLS_SERVICE,
            '/etc/systemd/system/nginx.service','/etc/xuanjun-development/nginx-main.conf'}
  need(required.issubset(previous),'EPOCH3_TLS_TARGETS')
  need(self._dropin_parent_state() is True,'EPOCH3_DROPIN_MUST_BE_ABSENT')
  receipt={'schema':1,'targets':[dict(item,data=None) for item in prepared],
           'services':list(ALLOWED_SERVICES),'rollback_complete':False,
           'failure_policy':'FENCE_STOP_RETAIN_NO_REPLAY',
           'prerequisites':runtime['prerequisites'],'auxiliary_isolation':runtime['auxiliary_isolation'],
           'tls_renewal':runtime['tls_renewal'],
           'plugin':{'id':P2_PLUGIN_ID,'previous':'ABSENT','gateway_service':GATEWAY_SERVICE,
                     'dropin_parent_created':True}}
  packed=(json.dumps(receipt,sort_keys=True,separators=(',',':'))+'\n').encode()
  _atomic_receipt(self.receipt_path,receipt)
  # RPM, NSS, bootstrap and publisher publication are intentionally NOT called.
  # Failure propagates to the single-attempt driver's fence/stop/retain handler.
  tls.apply(runtime['tls_renewal'])
  self._create_dropin_parent()
  for item in prepared:self._atomic_target(item['target'],item['data'],item['mode'],item['uid'],item['gid'])
  self._command(['/usr/bin/systemctl','daemon-reload'])
  self._command(['/usr/sbin/nginx','-t','-c','/etc/xuanjun-development/nginx-main.conf'])
  self._install_plugin(release,runtime)
  return {'schema':1,'receipt_sha256':_digest_bytes(packed),'rollback_complete':False,
          'failure_policy':'FENCE_STOP_RETAIN_NO_REPLAY','retained_resources_replayed':False}
 def restore_retained_owner_masks(self,plan):
  self._authority()
  raw=private_read(self.directory+'/runtime-provisioning.json')
  need(hashlib.sha256(raw).hexdigest()==PINS[T+'/runtime-provisioning.json'],'EPOCH3_PRIOR_PROVISION_CHANGED')
  old=json.loads(raw.decode())['targets']
  masked=[row['target'] for row in old if isinstance(row.get('previous'),dict) and row['previous'].get('masked') is True]
  need(set(masked)=={Auxiliary.UNIT_ROOT+'/'+name for name in Auxiliary.UNITS},'EPOCH3_OLD_OWNER_MASK_SCOPE')
  new={row['target']:row for row in plan['runtime']['provisioning']}
  # Validate all current bytes before replacing either known owner unit.
  for target in masked:
   if Auxiliary.is_mask(target):continue
   data,info=_read_regular(target);row=new[target]
   need((_digest_bytes(data),info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==
        (row['rendered_sha256'],row['owner_uid'],row['group_gid'],row['mode']),
        'EPOCH3_OWNER_UNIT_UNEXPECTED_DRIFT')
  for target in masked:Auxiliary.restore_mask(target)
  self._command(['/usr/bin/systemctl','daemon-reload'])
  Auxiliary.verify(plan['runtime']['auxiliary_isolation'])
  return {'original_owner_masks_restored':True}
 def restore(self,*args,**kwargs):
  raise ValueError('EPOCH3_GENERIC_RESTORE_FORBIDDEN_USE_ADMITTED_CONTAINMENT')
 def prepare_prerequisites(self,*args,**kwargs):
  raise ValueError('EPOCH3_PREREQUISITE_REPLAY_FORBIDDEN')
 def restore_prerequisites(self,*args,**kwargs):
  raise ValueError('EPOCH3_PREREQUISITE_REMOVAL_FORBIDDEN')
