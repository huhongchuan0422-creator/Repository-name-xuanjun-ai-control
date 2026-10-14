import copy,json,os,pathlib,unittest
import epoch5_retained_state as subject
class RetainedStateTests(unittest.TestCase):
 def setUp(self):
  if os.environ.get('P2_OBSERVATION_PATH'):
   self.value=json.loads(pathlib.Path(os.environ['P2_OBSERVATION_PATH']).read_text());return
  self.value={'epoch':5,'production_mutations':0,'install_admission':'NOT_GRANTED',
   'pins':dict(subject.collector.PINS),
   'provision_targets':[{'target':'fixture-'+str(n),'original_state_matches':True} for n in range(24)],
   'bootstrap':[{'target':'fixture-'+str(n),'published_identity_matches':True,'journal_state':'PUBLISHED','temporary':'ABSENT'} for n in range(7)],
   'rpm_journal_sha256':subject.RPM_JOURNAL_SHA,'rpm_journal_state':'INSTALLED',
   'rpm_versions':[{'name':'fixture-'+str(n),'matches_candidate':True,'query_rc':0} for n in range(16)],
   'publisher':[{'target':'fixture-'+str(n),'root_identity_matches':True,'journal_state':'PUBLISHED','stage_state':'ABSENT'} for n in range(2)],
   'tls':{n:{'entries':[],'metadata':{'state':'DIRECTORY','uid':0,'gid':0,'mode':0o700}} for n in ('config','work','logs')},
   'regular_config_parse_only':{'pass':True,'acme_called':False,'modes':[{'mode':'renew','pass':True},{'mode':'dry-run','pass':True}]}}

 def reject(self):
  with self.assertRaises(ValueError):subject.validate_observation(self.value)
 def test_valid_observation_accepted(self):self.assertIs(subject.validate_observation(self.value),self.value)
 def test_epoch_changed(self):self.value['epoch']=4;self.reject()
 def test_target_effect(self):self.value['provision_targets'][0]['original_state_matches']=False;self.reject()
 def test_bootstrap_drift(self):self.value['bootstrap'][0]['published_identity_matches']=False;self.reject()
 def test_duplicate_targets(self):self.value['provision_targets'][1]=copy.deepcopy(self.value['provision_targets'][0]);self.reject()
 def test_rpm_drift(self):self.value['rpm_versions'][0]['matches_candidate']=False;self.reject()
 def test_rpm_journal_drift(self):self.value['rpm_journal_sha256']='0'*64;self.reject()
 def test_publisher_stage_present(self):self.value['publisher'][0]['stage_state']='DIRECTORY';self.reject()
 def test_tls_directory_missing(self):del self.value['tls']['config'];self.reject()
 def test_parser_did_call_acme(self):self.value['regular_config_parse_only']['acme_called']=True;self.reject()
 def test_parser_failure(self):self.value['regular_config_parse_only']['pass']=False;self.reject()
 def test_approval_cannot_be_inferred(self):self.value['install_admission']='GRANTED';self.reject()
 def test_receipt_drift(self):self.value['pins']={};self.reject()
if __name__=='__main__':unittest.main()
