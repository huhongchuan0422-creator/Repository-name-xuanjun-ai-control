import importlib.util,json,os,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch
ROOT=pathlib.Path(os.environ['P2_SOURCE_ROOT']);sys.path.insert(0,str(ROOT/'stage1'))
import p2_install_entrypoint as entry
import p2_fixed_host_runtime as runtime
spec=importlib.util.spec_from_file_location('base_install_highs',str(pathlib.Path(__file__).parent/'test_c2_install_highs.py'));base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
class Order(unittest.TestCase):
 def exercise(self,failed_proof=False,failed_provision=False):
  events=[];plan=base.PlanTlsBindingTests()._plan();u=plan['transaction_id']
  class Activation:
   def prepare(self,*a,**k):events.append('activation-prepare');return {'epoch':1,'instance':u}
   def transition(self,before,after,*a):events.append(after);return {'state':after,'epoch':1,'instance':u}
   def fence(self,*a):events.append('fence');return {'epoch':2}
  class Adapter:
   def restore_legacy_files(self,gateway_only=False):events.append(('restore-legacy',gateway_only));return {'unit_files_restored':True,'services_restarted':False}
  class Cutover:
   adapter=Adapter()
   def execute(self,p):
    events.append('cutover-quiesced-staged');proof=dict.fromkeys(entry.PROOF_KEYS,True)
    if failed_proof:proof['cgroups_empty']=False
    return {'stage':'STAGED','quiescence':{'proof':proof}}
  class Runtime:
   def preflight(self,*a):events.append('preflight');return True
   def prepare_prerequisites(self,*a):events.append('identity-dir-bin-only');return True
   def restore_prerequisites(self,*a):events.append('restore-prerequisites');return True
   def provision(self,*a):
    events.append('runtime-rpm-profile-plugin-offline')
    if failed_provision:raise ValueError('synthetic provision')
    return {'schema':1,'receipt_sha256':'a'*64,'rollback_complete':True}
   def reopen_database(self,*a):events.append('reopen');return {'database_reopened':True}
   def activate(self,*a):events.append('start-admitted-runtime');return {'services_active':True}
   def restore(self,*a):events.append('restore-runtime');return True
   def stop_new(self,*a):events.append('stop-new');return True
  with tempfile.TemporaryDirectory() as d:
   installer=entry.P2InstallEntrypoint(d+'/receipt.json',lambda p:'/opt/xuanjun-control-releases/'+plan['runtime']['release_directory'],Cutover(),Activation(),Runtime())
   try:
    with patch.object(entry,'validate_plan',return_value=True):installer.execute(plan)
   except ValueError:
    if not (failed_proof or failed_provision):raise
  return events
 def test_quiescence_before_runtime_effects(self):
  e=self.exercise();self.assertLess(e.index('cutover-quiesced-staged'),e.index('runtime-rpm-profile-plugin-offline'));self.assertLess(e.index('QUIESCED'),e.index('runtime-rpm-profile-plugin-offline'));self.assertLess(e.index('ACTIVE'),e.index('start-admitted-runtime'))
 def test_bad_quiescence_has_no_runtime_effects(self):
  e=self.exercise(failed_proof=True);self.assertNotIn('runtime-rpm-profile-plugin-offline',e);self.assertNotIn('start-admitted-runtime',e);self.assertIn('fence',e)
 def test_provision_failure_never_starts_and_restores_prerequisites(self):
  e=self.exercise(failed_provision=True);self.assertNotIn('start-admitted-runtime',e);self.assertIn('restore-prerequisites',e)
 def test_offline_plugin_has_no_gateway_start_or_runtime_inspect(self):
  r=runtime.FixedHostRuntime.__new__(runtime.FixedHostRuntime);r.directory='/synthetic';r._plugin_present=lambda x:False;r._stop_gateway=lambda:None;r._start_gateway=lambda:(_ for _ in ()).throw(AssertionError('early start'))
  calls=[];r._openclaw=lambda rt,args,**kw:calls.append(args)
  rt={'plugin':{'source':'plugins/p2-native-controller','binding_file':'/synthetic/binding','binding_sha256':'a'*64},'sandbox_policy':{}}
  with patch.object(runtime.os.path,'realpath',side_effect=lambda p:p),patch.object(runtime.os.path,'isdir',return_value=True),patch.object(runtime.SandboxProfile,'apply',return_value=None):r._install_plugin('/synthetic/release',rt)
  self.assertFalse(any('inspect' in c for c in calls));self.assertTrue(any(c[:2]==['plugins','install'] for c in calls))
if __name__=='__main__':unittest.main()
