import copy,hashlib,json,unittest
from unittest import mock
import epoch3_plan as s
class Tests(unittest.TestCase):
 def setUp(self):
  self.original={'transaction_id':'existing','runtime':{'plugin':{'binding_file':'a','ledger_client_config':'b','gateway_relay_config':'c'},
    'legacy_cutover':{'original':True},'bootstrap':{'path':'retained'}},'cutover':{'original':True},'auth':{'references':[]},'tls':{'references':[]}}
  self.raw=json.dumps(self.original).encode();self.rows=[{'target':v,'rendered_sha256':v*64} for v in 'abc']
  self.pub={'new_manifest_sha256':s.MANIFEST,'new_release_directory':'integration-'+s.MANIFEST[:16]}
  self.bind={'provisioning':self.rows,'tls_config_bytes':'{"fixture":true}',
             'activation_proposal':{'state':'PREPARED','epoch':4}}
  self.patch=mock.patch.object(s,'proposal',return_value=(self.pub,self.bind));self.patch.start()
 def tearDown(self):self.patch.stop()
 def run_plan(self):return s.compile_plan(self.raw,'old','new')
 def test_plugin_hashes_rebound(self):
  p=self.run_plan()['runtime']['plugin']
  self.assertEqual([p[k] for k in ('binding_sha256','ledger_client_sha256','gateway_relay_sha256')],[v*64 for v in 'abc'])
 def test_tls_reference_exact(self):
  p=self.run_plan();self.assertEqual(p['runtime']['tls_renewal'],{'path':s.TLS_CONFIG,'sha256':hashlib.sha256(p['tls_config_bytes'].encode()).hexdigest()})
 def test_retained_bootstrap_unchanged(self):self.assertEqual(self.run_plan()['runtime']['bootstrap'],self.original['runtime']['bootstrap'])
 def test_cutover_identity_unchanged(self):self.assertEqual(self.run_plan()['cutover'],self.original['cutover'])
 def test_wrong_manifest_rejected(self):
  self.pub['new_manifest_sha256']='0'*64
  with self.assertRaises(ValueError):self.run_plan()
 def test_missing_plugin_target_rejected(self):
  self.rows.pop()
  with self.assertRaises(KeyError):self.run_plan()
 def test_explicit_failure_policy(self):
  p=self.run_plan();self.assertFalse(p['automatic_retry']);self.assertFalse(p['legacy_writer_restart'])
  self.assertEqual(p['failure_policy'],'FENCE_STOP_RETAIN_NO_REPLAY')
if __name__=='__main__':unittest.main()
