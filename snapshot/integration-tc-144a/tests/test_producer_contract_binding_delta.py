import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from producer_http_contract import REFERENCE_SHA256,REPOSITORY,ALLOWED_FILE
from task_supervisor import Supervisor,canonical

class ProducerContractBinding(unittest.TestCase):
    def contract(self):
        return {'task_id':'synthetic','spec_sha256':'b'*64,'checkpoint_sha256':'a'*64,
                'target_repository':REPOSITORY,'target_base_sha':'1'*40,'entry':'CHATGPT',
                'developer':{'issuer':'fixture','subject':'developer'},'allowed_files':[ALLOWED_FILE],
                'trusted_reviewers':[{'role':'QA'},{'role':'SECURITY'}]}
    def test_reference_matches_frozen_spec(self):
        reference=ROOT/'producer-test-assets'/'test-reference.json'
        self.assertEqual(list(ROOT.rglob('test-reference.json')),[reference])
        spec=json.loads(reference.read_text())
        self.assertEqual(hashlib.sha256(canonical(spec).encode()).hexdigest(),REFERENCE_SHA256)
    def test_optional_identity_exact_and_legacy_unchanged(self):
        c=self.contract();self.assertEqual(Supervisor._development_contract_shape(c),c)
        with self.assertRaisesRegex(ValueError,'EXACT_DEVELOPMENT_CONTRACT_REQUIRED'):
            Supervisor._development_contract_shape(dict(c,fixed_test={'function':'f','cases':[]}))
        c['producer_http_test_sha256']=REFERENCE_SHA256
        self.assertEqual(Supervisor._development_contract_shape(c),c)
        for change in ({'producer_http_test_sha256':'0'*64},{'target_repository':'other/repo'},
                       {'allowed_files':['scripts/other.py']},{'fixed_test':{}}):
            wrong=dict(c,**change)
            with self.assertRaises(ValueError):Supervisor._development_contract_shape(wrong)
    def test_reference_does_not_relax_execution_hold(self):
        with self.assertRaisesRegex(ValueError,'HOLD_SANDBOX_UNAVAILABLE'):
            Supervisor._require_development_execution_ready(None,{'source_kind':'LOCAL_ONLY_CONFIRMED_OPERATION'})
    def test_generic_event_ingest_rejects_execution_evidence_kind(self):
        with self.assertRaisesRegex(ValueError,'UNKNOWN_EVENT_KIND'):
            Supervisor.record(None,'synthetic','attempt','event','DEVELOPMENT_EXECUTION',0)
