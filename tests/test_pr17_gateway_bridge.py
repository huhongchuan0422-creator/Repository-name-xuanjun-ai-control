import json
import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from pr17_gateway_bridge import (consume_inbox, intake_event, publish_result,
                                 pull_pr17_comments)
from github_runtime_ci import ALLOWED_FILES, WORKFLOW_BLOB


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
        self.received = os.path.join(self.root.name, 'received')
        self.consumed = os.path.join(self.root.name, 'consumed')
        self.published = os.path.join(self.root.name, 'published')
        for path in (self.inbox, self.outbox, self.sent, self.received,
                     self.consumed, self.published):
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

    def test_successful_consume_archives_inbox_and_clears_watch_directory(self):
        receipt = intake_event(event(), 'owner/repo', 'owner', self.inbox)
        value = consume_inbox(
            receipt['path'], self.outbox,
            lambda _: {'state': 'CANONICAL_MATCH_NOT_ADMITTED',
                       'authority_effect': 'NONE'}, self.consumed)
        self.assertEqual([], os.listdir(self.inbox))
        self.assertEqual(1, len(os.listdir(self.consumed)))
        self.assertTrue(os.path.isfile(value['consumed_path']))

    def test_successful_publish_archives_outbox_and_clears_watch_directory(self):
        receipt = intake_event(event(), 'owner/repo', 'owner', self.inbox)
        output = consume_inbox(
            receipt['path'], self.outbox,
            lambda _: {'state': 'CANONICAL_MATCH_NOT_ADMITTED',
                       'authority_effect': 'NONE'})
        value = publish_result(
            output['path'], self.sent, 'token',
            lambda *args: {'comment_id': 88, 'duplicate': False},
            self.published)
        self.assertEqual([], os.listdir(self.outbox))
        self.assertEqual(1, len(os.listdir(self.published)))
        self.assertTrue(os.path.isfile(value['published_path']))

    def test_public_intake_is_durable_and_does_not_requeue_received_comment(self):
        source = event()
        comment = dict(source['comment'])
        comment['user'] = {'login': 'owner'}
        rows = [{'id': comment['id'], 'user': {'login': 'owner'},
                 'body': comment['body']}]
        calls = []
        def fetcher(repository, page):
            calls.append((repository, page))
            return rows
        first = pull_pr17_comments(
            'owner/repo', 'owner', self.inbox, self.received, fetcher)
        self.assertEqual(1, first['new_entries'])
        self.assertEqual(1, len(os.listdir(self.inbox)))
        consume_inbox(
            os.path.join(self.inbox, os.listdir(self.inbox)[0]), self.outbox,
            lambda _: {'state': 'CANONICAL_MATCH_NOT_ADMITTED',
                       'authority_effect': 'NONE'}, self.consumed)
        second = pull_pr17_comments(
            'owner/repo', 'owner', self.inbox, self.received, fetcher)
        self.assertEqual(0, second['new_entries'])
        self.assertEqual([], os.listdir(self.inbox))
        self.assertEqual([('owner/repo', 1), ('owner/repo', 1)], calls)

    def test_public_intake_ignores_non_owner_and_unmarked_comments(self):
        rows = [
            {'id': 1, 'user': {'login': 'other'},
             'body': event()['comment']['body']},
            {'id': 2, 'user': {'login': 'owner'}, 'body': 'ordinary'},
        ]
        value = pull_pr17_comments(
            'owner/repo', 'owner', self.inbox, self.received,
            lambda repository, page: rows)
        self.assertEqual(0, value['accepted_entries'])
        self.assertEqual([], os.listdir(self.inbox))

    def test_public_intake_rejects_malformed_owner_marker(self):
        rows = [{'id': 1, 'user': {'login': 'owner'},
                 'body': '<!-- XJ_DEV_ENTRY {} -->'}]
        with self.assertRaises(ValueError):
            pull_pr17_comments(
                'owner/repo', 'owner', self.inbox, self.received,
                lambda repository, page: rows)

    def test_rejects_unprotected_directory(self):
        os.chmod(self.inbox, 0o777)
        with self.assertRaisesRegex(ValueError, 'PROTECTED_DIRECTORY_CUSTODY'):
            intake_event(event(), 'owner/repo', 'owner', self.inbox)

    def test_runtime_ci_pin_and_scope_cover_pr17_successor(self):
        root = os.path.join(os.path.dirname(__file__), '..')
        workflow_path = '.github/workflows/mcp-current-successor-gates.yml'
        with open(os.path.join(root, workflow_path), 'rb') as handle:
            raw = handle.read()
        blob = hashlib.sha1(
            ('blob %d\0' % len(raw)).encode('ascii') + raw).hexdigest()
        self.assertEqual(WORKFLOW_BLOB, blob)
        required = {
            workflow_path, 'scripts/pr17_gateway_bridge.py',
            'tests/test_pr17_gateway_bridge.py',
            'deploy/xuanjun-pr17-gateway-intake.service.in',
            'deploy/xuanjun-pr17-gateway-intake.timer.in',
            'deploy/xuanjun-pr17-gateway-consumer.path.in',
            'deploy/xuanjun-pr17-gateway-consumer.service.in',
            'deploy/xuanjun-pr17-gateway-consumer.timer.in',
            'deploy/xuanjun-pr17-gateway-publisher.path.in',
            'deploy/xuanjun-pr17-gateway-publisher.service.in',
            'deploy/xuanjun-pr17-gateway-publisher.timer.in',
        }
        self.assertTrue(required <= ALLOWED_FILES)

    def test_units_clear_watched_directories_and_allow_exact_writes(self):
        root = os.path.join(os.path.dirname(__file__), '..', 'deploy')
        def read(name):
            with open(os.path.join(root, name), encoding='utf-8') as handle:
                return handle.read()
        consumer = read('xuanjun-pr17-gateway-consumer.service.in')
        publisher = read('xuanjun-pr17-gateway-publisher.service.in')
        intake = read('xuanjun-pr17-gateway-intake.service.in')
        self.assertIn('XJ_PR17_CONSUMED=@CONSUMED@', consumer)
        self.assertIn('@CANONICAL_LEDGER@', consumer.split('ReadWritePaths=', 1)[1])
        self.assertIn('@CANONICAL_LEDGER_DIR@', consumer.split('ReadWritePaths=', 1)[1])
        self.assertIn('XJ_PR17_PUBLISHED=@PUBLISHED@', publisher)
        self.assertIn('ReadWritePaths=@OUTBOX@ @SENT@ @PUBLISHED@', publisher)
        self.assertIn('pr17_gateway_bridge.py pull', intake)
        self.assertIn('ReadWritePaths=@INBOX@ @RECEIVED@', intake)


if __name__ == '__main__':
    unittest.main()
