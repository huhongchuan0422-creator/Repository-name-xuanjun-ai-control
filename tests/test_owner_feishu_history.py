import copy
import json
import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from owner_feishu_history import OwnerFeishuHistory


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.content = json.dumps({'text': '玄钧 P2 通知\n状态：COMPLETED\n事件：T1:COMPLETED:1\n包摘要：' + 'a'*64}, ensure_ascii=False)
        self.item = {'message_id': 'om_fixture', 'chat_id': 'oc_fixture',
                     'msg_type': 'text', 'sender': {'sender_type': 'app', 'id': 'cli_fixture'},
                     'body': {'content': self.content}}
        self.responses = [self.page([], True, 'next'), self.page([self.item]),
                          {'code': 0, 'data': {'items': [self.item]}}]
        self.calls = []

    def page(self, items, more=False, token=None):
        return {'code': 0, 'data': {'items': items, 'has_more': more, 'page_token': token}}

    def get(self, path):
        self.calls.append(path)
        return self.responses.pop(0)

    def lookup(self, pages=30):
        return OwnerFeishuHistory(self.get, 'oc_fixture', 'cli_fixture', pages)(
            'oc_fixture', 'T1:COMPLETED:1', self.content)

    def test_complete_pagination_and_receipt_readback(self):
        self.assertEqual(self.lookup()['message_id'], 'om_fixture')
        self.assertIn('page_token=next', self.calls[1])
        self.assertEqual(self.calls[-1], 'im/v1/messages/om_fixture')

    def test_complete_absence_unknown_never_not_sent(self):
        self.responses = [self.page([])]
        self.assertEqual(self.lookup(), 'UNKNOWN')

    def test_page_limit_even_with_match_unknown(self):
        self.responses = [self.page([self.item], True, 'next')]
        self.assertEqual(self.lookup(1), 'UNKNOWN')

    def test_token_cycle_unknown(self):
        self.responses = [self.page([], True, 'next'), self.page([], True, 'next')]
        self.assertEqual(self.lookup(), 'UNKNOWN')

    def test_invalid_pagination_unknown(self):
        for field, value in [('has_more', 1), ('page_token', None)]:
            self.responses = [self.page([], True, 'next')]
            self.responses[0]['data'][field] = value
            self.assertEqual(self.lookup(), 'UNKNOWN')

    def test_error_and_missing_envelope_unknown(self):
        for result in ({'code': True, 'data': {}}, {'code': 999}, {}, None):
            self.responses = [result]
            self.assertEqual(self.lookup(), 'UNKNOWN')

    def test_wrong_chat_sender_type_or_content_unknown(self):
        for field, value in [('chat_id', 'oc_other'), ('msg_type', 'image'),
                             ('deleted', True), ('sender', {'sender_type': 'user', 'id': 'cli_fixture'}),
                             ('sender', {'sender_type': 'app', 'id': 'cli_other'}),
                             ('body', {'content': '{"text":"wrong"}'})]:
            item = copy.deepcopy(self.item); item[field] = value
            self.responses = [self.page([item])]
            self.assertEqual(self.lookup(), 'UNKNOWN')

    def test_missing_type_unknown(self):
        item = copy.deepcopy(self.item); del item['msg_type']
        self.responses = [self.page([item])]
        self.assertEqual(self.lookup(), 'UNKNOWN')

    def test_duplicate_matching_receipts_unknown(self):
        other = copy.deepcopy(self.item); other['message_id'] = 'om_second'
        self.responses = [self.page([self.item, other])]
        self.assertEqual(self.lookup(), 'UNKNOWN')

    def test_readback_changed_or_unavailable_unknown(self):
        for result in ({'code': 0, 'data': {'items': []}}, {'code': 999}):
            self.responses = [self.page([self.item]), result]
            self.assertEqual(self.lookup(), 'UNKNOWN')

    def test_identity_and_chat_binding_before_query(self):
        provider = OwnerFeishuHistory(self.get, 'oc_fixture', 'cli_fixture')
        self.assertEqual(provider('oc_other', 'T1:COMPLETED:1', self.content), 'UNKNOWN')
        self.assertEqual(provider('oc_fixture', 'other', self.content), 'UNKNOWN')
        self.assertEqual(self.calls, [])

    def test_exception_sanitized(self):
        def fail(path): raise RuntimeError('SECRET_MUST_NOT_ESCAPE')
        provider = OwnerFeishuHistory(fail, 'oc_fixture', 'cli_fixture')
        self.assertEqual(provider('oc_fixture', 'T1:COMPLETED:1', self.content), 'UNKNOWN')


@unittest.skipUnless('P2_SOURCE_ROOT' in os.environ, 'Exact frozen producer absent: integration NOT_RUN')
class PersistentAckTests(unittest.TestCase):
    def test_history_reconciliation_persisted_and_restart_deduped(self):
        from test_owner_feishu_transport import Tests
        fixture = Tests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.mode = 'lost'; fixture.send(); fixture.now = 200
        content = fixture.transport._body(fixture.key, 'COMPLETED')
        item = {'message_id': 'om_found', 'chat_id': 'oc_fixture', 'msg_type': 'text',
                'sender': {'sender_type': 'app', 'id': 'cli_fixture'}, 'body': {'content': content}}
        replies = [{'code': 0, 'data': {'items': [item], 'has_more': False}},
                   {'code': 0, 'data': {'items': [item]}}]
        provider = OwnerFeishuHistory(lambda path: replies.pop(0), 'oc_fixture', 'cli_fixture')
        def lookup(destination, identity):
            # Supervisor's own fenced reconciliation CAS owns persistence.
            answer = provider('oc_fixture', identity, content)
            return answer['message_id'] if isinstance(answer, dict) else 'UNKNOWN'
        self.assertEqual(fixture.supervisor.reconcile_delivery(fixture.key, 'OWNER', 'fixture-reconciler', lookup), 'om_found')
        self.assertEqual(fixture.state(), ('ACKED', 'om_found', 1))
        from execution_supervision import ExecutionSupervisor
        fixture.supervisor = ExecutionSupervisor(fixture.path, lambda: fixture.now)
        self.assertIsNone(fixture.send())
        self.assertEqual(len(fixture.calls), 1)
