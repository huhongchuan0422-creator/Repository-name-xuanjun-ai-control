from __future__ import print_function

import copy
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from project_delivery_contract import (ProjectDeliveryContract,
                                       build_project_delivery_projection)
from reusable_scheduler_cli import demo_graph
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from task_supervisor import Supervisor


KEY = b'0123456789abcdef0123456789abcdef'


class ProjectDeliveryContractTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.supervisor = Supervisor(os.path.join(self.root, 'state.sqlite3'))
        self.authority = TestTenantAuthority(KEY)
        self.gateway = GatewayKernel(self.supervisor, self.authority)
        self.context = self.authority.issue('tenant-a', 'adapter-a')
        self.other = self.authority.issue('tenant-b', 'adapter-b')
        self.gateway.register_graph(self.context, demo_graph('tenant-a'))
        self.contract = ProjectDeliveryContract(self.gateway, self.context)

    def tearDown(self):
        self.supervisor.close()
        shutil.rmtree(self.root)

    def event(self, event_type, event_id, **updates):
        value = {
            'source': 'CUSTOMER_PROJECT_CENTER',
            'tenant_id': 'tenant-a', 'project_id': 'demo-project',
            'page_id': 'page-home', 'ui_version': 'input-v1',
            'task_id': 'demo-b', 'attempt_id': 'UNKNOWN',
            'event_id': event_id, 'event_type': event_type,
            'occurred_at': 1, 'actor_kind': 'developer',
            'actor_id': 'developer-1',
            'permission_scope': 'TEST_ONLY_READ_CONTRACT',
            'authorization_ref': 'UNKNOWN', 'evidence_ref': 'evidence-1',
            'change_id': 'UNKNOWN', 'delivery_id': 'UNKNOWN',
            'acceptance_id': 'UNKNOWN', 'content_ref': 'UNKNOWN',
            'showcase_allowed': False,
        }
        value.update(updates)
        return value

    def projection(self, events):
        return build_project_delivery_projection(
            self.gateway.projection(self.context), events,
            showcase_allowlist=['case://approved'])

    def test_tenant_project_and_ui_version_are_bound_without_writes(self):
        before = self.supervisor.db.total_changes
        for field, bad, error in (
                ('tenant_id', 'tenant-b', 'CROSS_TENANT'),
                ('project_id', 'other-project', 'PROJECT_BINDING'),
                ('ui_version', 'old-ui', 'UI_VERSION')):
            value = self.event('CUSTOMER_COMMENT_RECORDED', 'event-' + field)
            value[field] = bad
            with self.assertRaisesRegex(ValueError, error):
                self.contract.normalize(value)
        self.assertEqual(before, self.supervisor.db.total_changes)

    def test_ai_or_executor_cannot_confirm_or_accept(self):
        value = self.event('PAGE_ACCEPTED', 'accept-1',
                           acceptance_id='acceptance-1')
        with self.assertRaisesRegex(ValueError, 'CANNOT_CONFIRM'):
            self.contract.normalize(value)
        value.update(actor_kind='customer', actor_id='customer-1',
                     authorization_ref='auth://customer/1')
        normalized = self.contract.normalize(value)
        self.assertEqual(normalized['canonical_event_type'], 'PAGE_ACCEPTED')
        self.assertEqual(normalized['production_adapter'], 'NOT_CONNECTED')

    def test_current_attempt_binding_is_not_inferred(self):
        value = self.event('CUSTOMER_COMMENT_RECORDED', 'comment-attempt',
                           attempt_id='invented-attempt')
        with self.assertRaisesRegex(ValueError, 'ATTEMPT_BINDING'):
            self.contract.normalize(value)

    def test_page_version_lifecycle_and_delivery_preserve_audit(self):
        raw = [
            self.event('PAGE_UI_CONFIRMED', 'event-1', occurred_at=1,
                       actor_kind='requester', actor_id='requester-1',
                       authorization_ref='auth://requester/1'),
            self.event('CUSTOMER_COMMENT_RECORDED', 'event-2', occurred_at=2,
                       actor_kind='customer', actor_id='customer-1',
                       change_id='change-1'),
            self.event('PAGE_RECTIFICATION_SUBMITTED', 'event-3',
                       occurred_at=3, change_id='change-1'),
            self.event('PAGE_RECHECK_RECORDED', 'event-4', occurred_at=4,
                       actor_kind='reviewer', actor_id='reviewer-1'),
            self.event('PAGE_ACCEPTED', 'event-5', occurred_at=5,
                       actor_kind='customer', actor_id='customer-1',
                       authorization_ref='auth://customer/1',
                       acceptance_id='acceptance-1'),
            self.event('PROJECT_DELIVERED', 'event-6', occurred_at=6,
                       page_id='PROJECT', actor_kind='owner',
                       actor_id='owner-1', authorization_ref='auth://owner/1',
                       delivery_id='delivery-1'),
        ]
        value = self.projection([self.contract.normalize(x) for x in raw])
        page = value['records']['page_versions'][0]
        project = value['records']['projects'][0]
        self.assertEqual(page['state'], 'ACCEPTED')
        self.assertEqual(page['acceptance_id'], 'acceptance-1')
        self.assertFalse(project['active_development'])
        self.assertEqual(project['delivery_state'], 'FORMALLY_DELIVERED')
        self.assertEqual(len(value['records']['events']), 6)

    def test_delivery_does_not_bypass_missing_page_acceptance(self):
        raw = [
            self.event('CUSTOMER_COMMENT_RECORDED', 'comment-1',
                       change_id='change-1'),
            self.event('PROJECT_DELIVERED', 'delivery-1', page_id='PROJECT',
                       occurred_at=2, actor_kind='owner', actor_id='owner-1',
                       authorization_ref='auth://owner/1',
                       delivery_id='delivery-1'),
        ]
        value = self.projection([self.contract.normalize(x) for x in raw])
        project = value['records']['projects'][0]
        self.assertTrue(project['active_development'])
        self.assertEqual(project['delivery_state'],
                         'BLOCKED_INCOMPLETE_PAGE_ACCEPTANCE')

    def test_direct_accept_without_confirmed_baseline_fails_closed(self):
        raw = [
            self.event('PAGE_ACCEPTED', 'accept-no-baseline',
                       actor_kind='customer', actor_id='customer-1',
                       authorization_ref='auth://customer/1',
                       acceptance_id='acceptance-unbound'),
            self.event('PROJECT_DELIVERED', 'delivery-no-baseline',
                       occurred_at=2, page_id='PROJECT', actor_kind='owner',
                       actor_id='owner-1', authorization_ref='auth://owner/1',
                       delivery_id='delivery-unbound'),
        ]
        value = self.projection([self.contract.normalize(x) for x in raw])
        page = value['records']['page_versions'][0]
        project = value['records']['projects'][0]
        self.assertEqual(page['baseline_state'], 'UNKNOWN')
        self.assertEqual(page['state'], 'BLOCKED_BASELINE_UNCONFIRMED')
        self.assertEqual(page['acceptance_blocker'],
                         'UI_BASELINE_NOT_CONFIRMED')
        self.assertEqual(page['acceptance_id'], 'UNKNOWN')
        self.assertTrue(project['active_development'])
        self.assertEqual(project['delivery_state'],
                         'BLOCKED_INCOMPLETE_PAGE_ACCEPTANCE')

    def test_confirmed_baseline_from_other_ui_version_cannot_accept(self):
        baseline = self.contract.normalize(self.event(
            'PAGE_UI_CONFIRMED', 'baseline-v1', ui_version='input-v1',
            actor_kind='requester', actor_id='requester-1',
            authorization_ref='auth://requester/1'))
        self.gateway.db.execute('''UPDATE gateway_task_metadata
          SET input_version='input-v2' WHERE task_id='demo-b' ''')
        acceptance = self.contract.normalize(self.event(
            'PAGE_ACCEPTED', 'accept-v2', ui_version='input-v2',
            actor_kind='customer', actor_id='customer-1',
            authorization_ref='auth://customer/1',
            acceptance_id='acceptance-v2'))
        delivery = self.contract.normalize(self.event(
            'PROJECT_DELIVERED', 'delivery-v2', ui_version='input-v2',
            page_id='PROJECT', occurred_at=2, actor_kind='owner',
            actor_id='owner-1', authorization_ref='auth://owner/1',
            delivery_id='delivery-v2'))
        value = self.projection([baseline, acceptance, delivery])
        pages = {item['ui_version']: item
                 for item in value['records']['page_versions']}
        self.assertEqual(pages['input-v1']['baseline_state'], 'CONFIRMED')
        self.assertEqual(pages['input-v2']['state'],
                         'BLOCKED_BASELINE_UNCONFIRMED')
        project = value['records']['projects'][0]
        self.assertTrue(project['active_development'])
        self.assertEqual(project['delivery_state'],
                         'BLOCKED_INCOMPLETE_PAGE_ACCEPTANCE')

    def test_showcase_emits_only_double_allowlisted_opaque_reference(self):
        allowed = self.event(
            'SHOWCASE_REFERENCE_ALLOWED', 'showcase-1',
            actor_kind='customer', actor_id='customer-1',
            authorization_ref='auth://customer/1',
            content_ref='case://approved', showcase_allowed=True)
        absent = copy.deepcopy(allowed)
        absent.update(event_id='showcase-2', content_ref='case://not-listed')
        value = self.projection([self.contract.normalize(allowed),
                                 self.contract.normalize(absent)])
        refs = value['records']['showcase_references']
        self.assertEqual([x['content_ref'] for x in refs],
                         ['case://approved'])

    def test_exact_duplicate_event_is_idempotent_and_conflict_rejects(self):
        event = self.contract.normalize(self.event(
            'CUSTOMER_COMMENT_RECORDED', 'same-event'))
        value = self.projection([event, copy.deepcopy(event)])
        self.assertEqual(len(value['records']['events']), 1)
        conflict = copy.deepcopy(event)
        conflict['evidence_ref'] = 'different-evidence'
        with self.assertRaisesRegex(ValueError, 'CONFLICTING'):
            self.projection([event, conflict])

    def test_missing_website_adapter_stays_not_connected_unknown(self):
        value = self.projection([])
        self.assertEqual(value['source']['status'], 'NOT_CONNECTED')
        self.assertEqual(value['production_status'], 'NOT_IMPLEMENTED')
        self.assertIn('PAGE_VERSION_ACCEPTANCE_FACTS_UNKNOWN', value['gaps'])


if __name__ == '__main__':
    unittest.main()
