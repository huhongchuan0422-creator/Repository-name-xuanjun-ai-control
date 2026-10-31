import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from pr17_gateway_bridge import (consume_inbox, intake_event, publish_result)


TASK = 'XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1'


def event(comment_id=901):
    value = {
        'schema': 1, 'entry': 'CHATGPT', 'execution_path': 'CHATGPT_NATIVE',
        'task_id': TASK, 'spec_sha256': 'a' * 64,
        'checkpoint_sha256': 'b' * 64,
        'target_repository': 'owner/repo', 'target_base_sha': 'c' * 40,
        'code_commit': 'd' * 40, 'event': 'RECEIVED',
        'attempt_id': 'attempt-1', 'lease_id': 'lease-1', 'fence': 7,
        'epoch': 3, 'caller_id': 'caller', 'run_id': 'run',
        'session_id': 'session', 'gateway_id': 'gateway',
        'lock_provider_id': 'lock',
    }
    return {'repository': {'full_name': 'owner/repo'}, 'issue': {
        'number': 17, 'pull_request': {}}, 'sender': {'login': 'owner'},
        'comment': {'id': comment_id, 'user': {'login': 'owner'},
                    'body': '<!-- XJ_DEV_ENTRY %s -->' % json.dumps(value)},
        'action': 'created'}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.inbox = os.path.join(self.root.name, 'inbox')
        self.outbox = os.path.join(self.root.name, 'outbox')
        self.sent = os.path.join(self.root.name, 'sent')
        for path in (self.inbox, self.outbox, self.sent):
            os.mkdir(path, 0o700)

    def tearDown(self):
        self.root.cleanup()

    def test_intake_duplicate_is_one_content_addressed_record(self):
        first = intake_event(event(), 'owner/repo', 'owner', self.inbox)
        second = intake_event(event(), 'owner/repo', 'owner', self.inbox)
        self.assertFalse(first['duplicate'])
        self.assertTrue(second['duplicate'])
        self.assertEqual(first['envelope_id'], second['envelope_id'])
        self.assertEqual(1, len(os.listdir(self.inbox)))

    def test_consume_binds_existing_gateway_and_deduplicates_outbox(self):
        receipt = intake_event(event(), 'owner/repo', 'owner', self.inbox)
        seen = []
        def binder(value):
            seen.append(value['task_id'])
            return {'state': 'CANONICAL_MATCH_NOT_ADMITTED',
                    'authority_effect': 'NONE'}
        first = consume_inbox(receipt['path'], self.outbox, binder)
        second = consume_inbox(receipt['path'], self.outbox, binder)
        self.assertFalse(first['duplicate'])
        self.assertTrue(second['duplicate'])
        self.assertEqual([TASK, TASK], seen)
        self.assertEqual(1, len(os.listdir(self.outbox)))

    def test_publish_recovers_existing_comment_without_duplicate_post(self):
        receipt = intake_event(event(), 'owner/repo', 'owner', self.inbox)
        output = consume_inbox(receipt['path'], self.outbox,
                               lambda _: {'state': 'CANONICAL_MATCH_NOT_ADMITTED',
                                          'authority_effect': 'NONE'})
        calls = []
        def poster(token, repository, marker, body):
            calls.append((token, repository, marker, body))
            return {'comment_id': 77, 'duplicate': len(calls) > 1}
        first = publish_result(output['path'], self.sent, 'token', poster)
        second = publish_result(output['path'], self.sent, 'token', poster)
        self.assertEqual(77, first['comment_id'])
        self.assertEqual(first['sent_id'], second['sent_id'])
        self.assertTrue(second['duplicate'])
        self.assertEqual(1, len(os.listdir(self.sent)))

    def test_rejects_unprotected_directory(self):
        os.chmod(self.inbox, 0o777)
        with self.assertRaisesRegex(ValueError, 'PROTECTED_DIRECTORY_CUSTODY'):
            intake_event(event(), 'owner/repo', 'owner', self.inbox)


if __name__ == '__main__':
    unittest.main()
