import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from development_entry_intake import validate_event, TASK, ENTRIES

REPO = 'owner/control'

def fixture(entry='WORK'):
    value = dict(schema=1, entry=entry, execution_path=ENTRIES[entry], task_id=TASK,
                 spec_sha256='a'*64, checkpoint_sha256='b'*64,
                 target_repository='owner/business', target_base_sha='c'*40,
                 code_commit='d'*40, event='CODE_READY')
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

if __name__=='__main__':unittest.main()
