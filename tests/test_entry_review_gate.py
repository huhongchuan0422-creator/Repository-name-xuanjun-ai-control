import copy
import hashlib
import hmac
import importlib.util
import pathlib
import unittest

spec=importlib.util.spec_from_file_location('gate',pathlib.Path(__file__).parents[1]/'scripts/entry_review_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
KEYS={'qa-key':b'Q'*32,'security-key':b'S'*32,'ledger-key':b'L'*32}


def signed(payload,key_id):
    record=dict(schema=1,key_id=key_id,record_id=gate.digest(gate.canonical(payload)),payload=payload)
    record['signature']=hmac.new(KEYS[key_id],gate.canonical(record),hashlib.sha256).hexdigest()
    return record


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.contract=dict(task_id='original',spec_sha256='a'*64,checkpoint_sha256='b'*64,
            target_repository='owner/repo',target_base_sha='c'*40,code_commit='d'*40,entry='CHATGPT',
            developer={'issuer':'native','subject':'developer'},allowed_files=['src/f.py'],
            trusted_reviewers=[{'issuer':'native','subject':'qa','key_id':'qa-key','role':'QA'},
                               {'issuer':'native','subject':'security','key_id':'security-key','role':'SECURITY'}])
        self.files={'src/f.py':b'answer=42\n'}
        self.binding=dict(task_id='same',attempt_id='attempt-1',run_id='run-1',session_id='session-1',fence=1,
                          checkpoint_sha256='a'*64,ledger_revision=2,receipt_sha256='b'*64,authority_key_id='ledger-key')

    def reviews(self):
        sha=gate.review_bundle(self.contract,self.files,[])['bundle_sha256']
        return [signed(dict(reviewer={k:p[k] for k in ('issuer','subject')},role=p['role'],bundle_sha256=sha,decision='PASS'),p['key_id']) for p in self.contract['trusted_reviewers']]

    def evidence(self,kind='CONTINUED',proof=None,at=1000):
        return signed(dict(binding=copy.deepcopy(self.binding),kind=kind,observed_at=at,
                           proof=proof or {'verified_execution':True}),'ledger-key')

    def test_three_entries_require_authenticated_independent_review(self):
        for entry in gate.ENTRIES:
            self.contract['entry']=entry
            self.assertEqual(gate.review_bundle(self.contract,self.files,[])['state'],'HOLD_INDEPENDENT_REVIEW_REQUIRED')
            result=gate.review_bundle(self.contract,self.files,self.reviews(),KEYS)
            self.assertEqual(result['state'],'ISOLATED_TEST_ELIGIBLE');self.assertFalse(result['release_approved'])

    def test_all_policy_fields_bound_to_digest(self):
        reviews=self.reviews()
        for field,value in [('developer',{'issuer':'native','subject':'other'}),('allowed_files',['src/f.py','src/new.py']),('trusted_reviewers',[dict(p,subject=p['subject']+'2') for p in self.contract['trusted_reviewers']])]:
            changed=copy.deepcopy(self.contract);changed[field]=value
            with self.assertRaises(ValueError):gate.review_bundle(changed,self.files,reviews,KEYS)

    def test_string_policy_and_duplicate_identity_rejected(self):
        for change in ('qa_security',[self.contract['trusted_reviewers'][0]]*2):
            changed=dict(self.contract,trusted_reviewers=change)
            with self.assertRaises(ValueError):gate.review_bundle(changed,self.files,[],KEYS)
        changed=dict(self.contract,developer='developer')
        with self.assertRaises(ValueError):gate.review_bundle(changed,self.files,[],KEYS)

    def test_tampered_forged_or_duplicate_reviews(self):
        for mutate in ('signature','payload','record','duplicate','nokey'):
            reviews=self.reviews();keys=KEYS
            if mutate=='signature':reviews[0]['signature']='0'*64
            if mutate=='payload':reviews[0]['payload']['reviewer']['subject']='security'
            if mutate=='record':reviews[0]['record_id']='0'*64
            if mutate=='duplicate':reviews[1]=reviews[0]
            if mutate=='nokey':keys={}
            with self.assertRaises(ValueError):gate.review_bundle(self.contract,self.files,reviews,keys)

    def test_changed_code_invalidates_reviews(self):
        reviews=self.reviews();self.files['src/f.py']+=b'changed=1\n'
        with self.assertRaises(ValueError):gate.review_bundle(self.contract,self.files,reviews,KEYS)

    def test_paths_encoding_and_limits(self):
        for files in ({'../f.py':b'x=1'},{'src/f.py':b'\xff'},{'src/f.py':b'x=1\r\n'},{'src/f.py':b'x'*131073}):
            with self.assertRaises((ValueError,UnicodeError)):gate.review_bundle(self.contract,files,[])

    def test_read_heartbeat_and_missing_progress_do_not_close(self):
        for age,state in [(299,'AWAIT_EXECUTION_EVIDENCE'),(300,'RECOVER_INTAKE'),(600,'INSPECT_AND_RESUME_SAME_ATTEMPT'),(900,'HOLD_CONTINUATION_MISSING')]:
            for kind in ('READ','HEARTBEAT','CONTINUED'):
                record=self.evidence(kind,{'verified_execution':False},age)
                self.assertEqual(gate.continuation_due(self.binding,0,age,record,KEYS)['state'],state)

    def test_each_canonical_binding_field_rejects_unrelated_evidence(self):
        for field in self.binding:
            changed=copy.deepcopy(self.binding)
            changed[field]=changed[field]+1 if type(changed[field]) is int else 'x'*64 if field.endswith('sha256') else changed[field]+'-other'
            with self.assertRaises(ValueError):gate.continuation_due(changed,0,1000,self.evidence(),KEYS)

    def test_stale_future_unsigned_evidence_rejected(self):
        for at in (-1,1001,float('inf')):
            if at==float('inf'):
                with self.assertRaises(ValueError):self.evidence(at=at)
            else:
                with self.assertRaises(ValueError):gate.continuation_due(self.binding,0,1000,self.evidence(at=at),KEYS)
        with self.assertRaises(ValueError):gate.continuation_due(self.binding,0,1000,{'kind':'CONTINUED','verified_execution':True},KEYS)

    def test_handoff_requires_full_same_attempt_proof(self):
        proof=dict(receiver_accepted=True,old_writer_stopped=True,old_fence_invalidated=True,effects_reconciled=True)
        self.assertEqual(gate.continuation_due(self.binding,0,1000,self.evidence('HANDOFF_ACKNOWLEDGED',proof),KEYS)['state'],'HANDOFF_ACKNOWLEDGED')
        for key in proof:
            changed=dict(proof);changed[key]=False
            self.assertEqual(gate.continuation_due(self.binding,0,1000,self.evidence('HANDOFF_ACKNOWLEDGED',changed),KEYS)['state'],'HOLD_CONTINUATION_MISSING')

    def test_real_progress_and_bound_hold(self):
        self.assertEqual(gate.continuation_due(self.binding,0,1000,self.evidence(),KEYS)['state'],'CONTINUED')
        proof=dict(blocker='api missing',checkpoint=self.binding['checkpoint_sha256'],next_action='bind api')
        self.assertEqual(gate.continuation_due(self.binding,0,1000,self.evidence('HOLD',proof),KEYS)['state'],'HOLD')

    def test_clock_drift(self):
        for now in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):gate.continuation_due(self.binding,0,now)

    def test_invalid_task_repository_and_policy_paths(self):
        for field,value in [('task_id',{}),('target_repository','owner/repo/../other'),('allowed_files',['../bad.py','src/f.py'])]:
            changed=dict(self.contract);changed[field]=value
            with self.assertRaises(ValueError):gate.review_bundle(changed,self.files,[])

    def test_same_key_cannot_claim_two_independent_reviewers(self):
        records=self.reviews();keys=dict(KEYS);keys['security-key']=keys['qa-key']
        record=records[1]
        record['signature']=hmac.new(keys['security-key'],gate.canonical({k:v for k,v in record.items() if k!='signature'}),hashlib.sha256).hexdigest()
        with self.assertRaises(ValueError):gate.review_bundle(self.contract,self.files,records,keys)

    def test_missing_or_extra_reviewed_file_is_rejected(self):
        for files in ({},{'src/f.py':b'x=1','src/extra.py':b'x=2'}):
            with self.assertRaises(ValueError):gate.review_bundle(self.contract,files,[])
        changed=dict(self.contract,allowed_files=['src/f.py','src/missing.py'])
        with self.assertRaises(ValueError):gate.review_bundle(changed,self.files,[])


if __name__=='__main__':unittest.main()
