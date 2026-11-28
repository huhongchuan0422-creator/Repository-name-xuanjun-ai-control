import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import development_entry_intake as intake
from development_entry_intake import validate_event, main, TASK, ENTRIES

REPO = 'owner/control'
BOUND_TASK = 'tc-real-development-20261123-4d99c26f2b07'
BOUND_DESTINATION = {'task_id': BOUND_TASK, 'pull_request_number': 17}
WRITER_FIELDS = ('attempt_id', 'lease_id', 'fence', 'epoch', 'caller_id',
                 'run_id', 'session_id', 'gateway_id', 'lock_provider_id')

def fixture(entry='WORK', task_id=TASK):
    value = dict(schema=1, entry=entry, execution_path=ENTRIES[entry], task_id=task_id,
                 spec_sha256='a'*64, checkpoint_sha256='b'*64,
                 target_repository='owner/business', target_base_sha='c'*40,
                 code_commit='d'*40, event='CODE_READY', attempt_id='a1',
                 lease_id='lease1', fence=1, epoch=1, caller_id='writer',
                 run_id='run1', session_id='session1', gateway_id='gateway1',
                 lock_provider_id='provider1')
    event = dict(action='created', repository={'full_name':REPO}, sender={'login':'owner'},
                 issue={'number':17,'pull_request':{}},
                 comment={'id':123,'user':{'login':'owner'},
                          'body':'<!-- XJ_DEV_ENTRY '+json.dumps(value)+' -->'})
    return value, event

def rebody(event, value):
    event['comment']['body'] = '<!-- XJ_DEV_ENTRY '+json.dumps(value)+' -->'
    return event

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


class HostDestinationTests(unittest.TestCase):
    def test_original_pr17_destination_receives_bound_task_with_all_fields(self):
        value, event = fixture('WORK', BOUND_TASK)
        result = validate_event(event, REPO, 'owner', dict(BOUND_DESTINATION))
        for key, item in value.items():
            self.assertEqual(result[key], item)
        self.assertEqual(result['task_id'], BOUND_TASK)
        self.assertEqual(result['status'], 'RECEIPT_VALIDATED_NOT_ADMITTED')
        self.assertEqual(result['authority_effect'], 'NONE')

    def test_comment_body_cannot_select_the_destination(self):
        value, event = fixture('WORK', BOUND_TASK)
        with self.assertRaises(ValueError):
            validate_event(event, REPO, 'owner')

    def test_bound_destination_rejects_wrong_task_pr_or_actor(self):
        for mutation in ('task', 'pr', 'actor'):
            value, event = fixture('DOTS', BOUND_TASK)
            destination = dict(BOUND_DESTINATION)
            if mutation == 'task': destination['task_id'] = 'another-task'
            if mutation == 'pr': event['issue']['number'] = 18
            if mutation == 'actor': event['sender']['login'] = 'intruder'
            with self.assertRaises(ValueError):
                validate_event(event, REPO, 'owner', destination)

    def test_incomplete_or_invalid_writer_binding_is_rejected(self):
        for drop in ('attempt_id', 'lease_id', 'caller_id', 'lock_provider_id'):
            value, event = fixture('WORK', BOUND_TASK)
            del value[drop]
            with self.assertRaises(ValueError):
                validate_event(rebody(event, value), REPO, 'owner',
                               dict(BOUND_DESTINATION))
        for key in ('fence', 'epoch'):
            value, event = fixture('WORK', BOUND_TASK)
            value[key] = 0
            with self.assertRaises(ValueError):
                validate_event(rebody(event, value), REPO, 'owner',
                               dict(BOUND_DESTINATION))

    def test_only_exact_host_scopes_are_accepted(self):
        for destination in ({}, {'task_id': BOUND_TASK},
                {'task_id': BOUND_TASK, 'pull_request_number': True},
                {'task_id': BOUND_TASK, 'pull_request_number': 0},
                {'task_id': BOUND_TASK, 'pull_request_number': 17, 'allow_any': True},
                {'task_id': '', 'pull_request_number': 17}):
            with self.assertRaises(ValueError): intake._destination(destination)


class WorkflowReceiptRuntimeTests(unittest.TestCase):
    def post_receipt(self, comment_task, bound_env):
        value, event = fixture('WORK', comment_task)
        handle, event_path = tempfile.mkstemp(); os.close(handle)
        with open(event_path, 'w', encoding='utf-8') as stream:
            json.dump(event, stream)
        captured = {}
        class Response(object):
            status = 201
            def __enter__(self): return self
            def __exit__(self, *args): return False
        def fake_open(request, timeout=15):
            captured['url'] = request.full_url
            captured['body'] = json.loads(request.data.decode('utf-8'))['body']
            return Response()
        env = {'GITHUB_EVENT_PATH': event_path, 'GITHUB_REPOSITORY': REPO,
               'GITHUB_TOKEN': 'fixture-token'}
        if bound_env: env['XJ_ENTRY_TASK_ID'] = BOUND_TASK
        try:
            with mock.patch.dict(os.environ, env):
                if not bound_env:
                    os.environ.pop('XJ_ENTRY_TASK_ID', None)
                with mock.patch.object(
                        intake, 'syntax_receipt', return_value=None), mock.patch.object(
                        intake.urllib.request, 'urlopen', side_effect=fake_open):
                    main(intake._host_destination())
        finally:
            os.unlink(event_path)
        raw = captured['body'].split('\n', 1)[0]
        self.assertTrue(raw.endswith(' -->'))
        return captured, json.loads(
            raw[len('<!-- XJ_DEV_ENTRY_RECEIPT '):-len(' -->')])

    def test_workflow_binding_posts_valid_pr17_receipt_quoting_writer_binding(self):
        with mock.patch.dict(os.environ, {'XJ_ENTRY_TASK_ID': BOUND_TASK}):
            self.assertEqual(intake._host_destination(), dict(BOUND_DESTINATION))
        captured, payload = self.post_receipt(BOUND_TASK, True)
        self.assertEqual(captured['url'],
            'https://api.github.com/repos/owner/control/issues/17/comments')
        self.assertEqual(payload['status'], 'RECEIPT_VALIDATED_NOT_ADMITTED')
        self.assertEqual(payload['task_id'], BOUND_TASK)
        for key in WRITER_FIELDS + ('code_commit', 'target_base_sha',
                                    'spec_sha256', 'checkpoint_sha256'):
            self.assertIn(key, payload)
        self.assertEqual(payload['authority_effect'], 'NONE')
        self.assertIn('::SKIP_COMPLETION::', captured['body'])

    def test_legacy_unbound_invocation_still_receipts_the_original_task(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('XJ_ENTRY_TASK_ID', None)
            self.assertIsNone(intake._host_destination())
        captured, payload = self.post_receipt(TASK, False)
        self.assertEqual(payload['status'], 'RECEIPT_VALIDATED_NOT_ADMITTED')
        self.assertEqual(payload['task_id'], TASK)
        self.assertEqual(captured['url'],
            'https://api.github.com/repos/owner/control/issues/17/comments')

    def test_bound_env_fails_closed_for_other_task_body(self):
        captured, payload = self.post_receipt(TASK, True)
        self.assertEqual(payload['status'], 'REJECTED_INVALID_ENTRY_ENVELOPE')
        self.assertEqual(payload['authority_effect'], 'NONE')
        self.assertEqual(payload['source_comment_id'], 123)

if __name__ == '__main__':
    unittest.main()
