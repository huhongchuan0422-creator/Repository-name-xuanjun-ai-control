"""Synthetic API-body negatives; never a production approval or live fetch."""
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'runtime'),str(HERE.parent/'kit-overlay/helpers'),str(HERE)]
import authorization as a
from receipt_provider import Hold,canonical
from test_authority_store import grant
class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.g=grant();self.p=types.SimpleNamespace(modulus=(1<<2047)+1,exponent=65537,issuer='TEST_ONLY')
        self.wanted=a.expected(self.g,self.p)
        self.body=a.MARKER+canonical(self.wanted).decode()
        self.g['approval_body_sha256']=hashlib.sha256(self.body.encode()).hexdigest()
        self.value={'id':9000000001,'user':{'id':95597695,'login':'18598789888'},
                    'issue_url':'https://api.github.com/repos/'+a.REPO+'/issues/58','body':self.body}
    def validate(self):return a.validate(json.dumps(self.value).encode(),9000000001,self.g,self.p)
    def test_exact_new_body_binds_key_grant(self):
        self.assertEqual(self.validate()['approval_body_sha256'],self.g['approval_body_sha256'])
        self.assertEqual(self.wanted['retry_policy'],'INDEPENDENT_NO_WRITE_OR_NATIVE_CAS_SAFE_CHECKPOINT_ONLY_NO_REPLAY_V1')
        self.assertEqual(self.wanted['effect_scope'],'INHERITED_107_PAYLOADS_16_PHASES_NO_TLS_ISSUANCE')
    def test_developer_cannot_issue_permit(self):
        self.value['user']={'id':332398908,'login':'huhongchuan0422-creator'}
        with self.assertRaises(Hold):self.validate()
    def test_wrong_pr(self):
        self.value['issue_url']='https://api.github.com/repos/'+a.REPO+'/issues/17'
        with self.assertRaises(Hold):self.validate()
    def test_unapproved_key_cannot_authenticate_itself(self):
        self.p.modulus+=2
        with self.assertRaises(Hold):self.validate()
    def test_changed_grant_scope(self):
        self.g['target_host']='OTHER'
        with self.assertRaises(Hold):self.validate()
    def test_old_single_use_marker_refused(self):
        self.value['body']='CHATGPT_NATIVE_TASK5_EXACT_EPOCH7_RECOVERY_ACCEPTANCE\n'+canonical(self.wanted).decode()
        self.g['approval_body_sha256']=hashlib.sha256(self.value['body'].encode()).hexdigest()
        with self.assertRaises(Hold):self.validate()
    def test_missing_approval_never_fetches(self):
        with self.assertRaises(Hold):a.authenticate(None,self.g,self.p)
    def test_single_approval_explicitly_binds_whole_autonomous_cycle(self):
        self.assertEqual(self.wanted['permit_cycle']['mode'],'ONE_PERMIT_MAX_5_ATTEMPTS')
        self.assertFalse(self.wanted['permit_cycle']['new_approval_per_retry'])
        self.assertEqual(self.validate()['cycle_policy_sha256'],a.digest(self.wanted['permit_cycle']))
    def test_unapproved_configuration_scope_cannot_be_added_after_review(self):
        value=dict(self.wanted['permit_cycle'])
        value['configuration_actions']=[{'id':'repair','target':'/var/lib/xuanjun-attempt5/config/repair.json','before_sha256':'a'*64,'after_sha256':'b'*64,'payload_sha256':'b'*64,'checkpoint_sha256':'c'*64}]
        with self.assertRaises(Hold):a.validate(json.dumps(self.value).encode(),9000000001,self.g,self.p,value)
if __name__=='__main__':unittest.main()
