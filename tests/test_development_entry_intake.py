import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from development_entry_intake import validate_event, bind_validated_receipt, TASK, ENTRIES
from task_supervisor import Supervisor

REPO = 'owner/control'

def fixture(entry='WORK'):
    value = dict(schema=1, entry=entry, execution_path=ENTRIES[entry], task_id=TASK,
                 spec_sha256='a'*64, checkpoint_sha256='b'*64,
                 target_repository='owner/business', target_base_sha='c'*40,
                 code_commit='d'*40, event='CODE_READY', attempt_id='a1',
                 lease_id='lease1', fence=1, epoch=1)
    event = dict(action='created', repository={'full_name':REPO}, sender={'login':'owner'},
                 issue={'number':17,'pull_request':{}},
                 comment={'id':123,'user':{'login':'owner'},
                          'body':'<!-- XJ_DEV_ENTRY '+json.dumps(value)+' -->'})
    return value, event

class Tests(unittest.TestCase):
    def test_all_native_entries_preserve_business_target_without_granting_authority(self):
        for entry in ENTRIES:
            value, event = fixture(entry)
            result = validate_event(event, REPO, 'owner')
            self.assertEqual(result['target_repository'], 'owner/business')
            self.assertEqual(result['authority_effect'], 'NONE')
            self.assertEqual(result['quota_attribution'], 'UNKNOWN')
            self.assertEqual(result['status'], 'RECEIPT_VALIDATED_NOT_ADMITTED')

    def test_sender_or_comment_author_cannot_impersonate_owner(self):
        for key in ('sender','comment'):
            value, event = fixture()
            if key == 'sender': event[key]['login']='intruder'
            else: event[key]['user']['login']='intruder'
            with self.assertRaises(ValueError): validate_event(event, REPO, 'owner')

    def test_invalid_fields_hashes_target_and_hidden_codex_rejected(self):
        mutations=[('execution_path','CODEX'),('spec_sha256','a'),
                   ('target_repository','owner/business/../control'),('schema',True),
                   ('task_id','another-task'),('event','EXECUTE_ROOT')]
        for key, replacement in mutations:
            value, event=fixture('DOTS'); value[key]=replacement
            event['comment']['body']='<!-- XJ_DEV_ENTRY '+json.dumps(value)+' -->'
            with self.assertRaises(ValueError): validate_event(event, REPO, 'owner')

    def test_duplicate_json_keys_and_multiple_markers_rejected(self):
        value,event=fixture()
        event['comment']['body']=event['comment']['body'].replace('{','{"schema":1,',1)
        with self.assertRaises(ValueError): validate_event(event,REPO,'owner')
        value,event=fixture();event['comment']['body']*=2
        with self.assertRaises(ValueError): validate_event(event,REPO,'owner')

    def test_stop_and_handoff_receipts_do_not_confirm_writer_stopped(self):
        for state in ('STOPPED','HANDOFF'):
            value,event=fixture('CHATGPT');value['event']=state
            event['comment']['body']='<!-- XJ_DEV_ENTRY '+json.dumps(value)+' -->'
            result=validate_event(event,REPO,'owner')
            self.assertEqual(result['authority_effect'],'NONE')
            self.assertIn('LEASE_FENCE',result['required_gate'])


class CanonicalBindingTests(unittest.TestCase):
    def setUp(self):
        handle,self.path=tempfile.mkstemp();os.close(handle)
        self.now=1000.0
        self.s=Supervisor(self.path,lambda:self.now)
        self.s.register(dict(
            task_id=TASK,parent_task_id='parent',stage='dev',
            owner='developer',entry='WORK',checkpoint_sha256='b'*64,
            spec_sha256='a'*64,next_action='implement',dependencies=[],
            completion_conditions=['reviewed-development'],
            progress_deadline=1900,receipt_deadline=1100,
            started_deadline=1200,terminal_deadline=3000,
            handoff_deadline=1800),now=self.now)
        self.contract=dict(
            task_id=TASK,spec_sha256='a'*64,checkpoint_sha256='b'*64,
            target_repository='owner/business',target_base_sha='c'*40,
            entry='WORK',developer={'issuer':'native','subject':'developer'},
            allowed_files=['src/f.py','src/data.json'],
            trusted_reviewers=[
                {'issuer':'native','subject':'qa','key_id':'qa-key','role':'QA'},
                {'issuer':'native','subject':'security','key_id':'security-key',
                 'role':'SECURITY'}])
        self.s.register_development_contract(TASK,self.contract,now=self.now)
        self.caller={'caller_id':'writer','run_id':'run1',
                     'session_id':'session1','gateway_id':'gateway1'}
        self.s.claim_writer(TASK,'a1','developer','WORK',self.caller,
                            'lease1','provider1',['fake:development/source'],
                            1700)

    def tearDown(self):
        self.s.close()
        if os.path.exists(self.path):os.unlink(self.path)

    def receipt(self):
        value,event=fixture('WORK')
        return validate_event(event,REPO,'owner')

    def files(self):
        return {'src/f.py':b'answer=42\n','src/data.json':b'{}\n'}

    def test_code_ready_binds_current_attempt_and_exact_files(self):
        result=bind_validated_receipt(self.s,self.receipt(),self.files())
        self.assertFalse(result['duplicate'])
        candidate=result['candidate']
        self.assertEqual(
            (candidate['attempt_id'],candidate['lease_id'],
             candidate['fence'],candidate['epoch']),
            ('a1','lease1',1,1))
        self.assertEqual(set(candidate['files']),set(self.contract['allowed_files']))

    def test_wrong_task_contract_or_writer_generation_is_rejected(self):
        for field,value in (
                ('spec_sha256','9'*64),('checkpoint_sha256','8'*64),
                ('target_repository','owner/other'),('target_base_sha','7'*40),
                ('attempt_id','old'),('lease_id','old'),('fence',2),('epoch',2)):
            receipt=self.receipt();receipt[field]=value
            with self.assertRaises(ValueError):
                bind_validated_receipt(self.s,receipt,self.files())

    def test_same_candidate_event_is_idempotent_and_changed_files_conflict(self):
        receipt=self.receipt()
        first=bind_validated_receipt(self.s,receipt,self.files())
        second=bind_validated_receipt(self.s,receipt,self.files())
        self.assertFalse(first['duplicate']);self.assertTrue(second['duplicate'])
        changed=self.files();changed['src/f.py']=b'answer=43\n'
        with self.assertRaisesRegex(ValueError,'DEVELOPMENT_CANDIDATE_CONFLICT'):
            bind_validated_receipt(self.s,receipt,changed)

    def test_non_code_ready_never_creates_candidate(self):
        value,event=fixture('WORK');value['event']='RECEIVED'
        event['comment']['body']='<!-- XJ_DEV_ENTRY '+json.dumps(value)+' -->'
        receipt=validate_event(event,REPO,'owner')
        result=bind_validated_receipt(self.s,receipt)
        self.assertEqual(result['state'],'CANONICAL_MATCH_NOT_ADMITTED')
        self.assertEqual(self.s.db.execute(
            "SELECT count(*) FROM events WHERE kind='DEVELOPMENT_CANDIDATE'"
        ).fetchone()[0],0)


if __name__=='__main__':unittest.main()
