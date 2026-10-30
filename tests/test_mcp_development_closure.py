from __future__ import print_function

import copy
import os
import sys
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from mcp_development_closure import (HOLD, PROVEN, UNKNOWN,
                                     admission_for_real_task,
                                     evaluate_closure)


class MCPDevelopmentClosureTests(unittest.TestCase):
    def snapshot(self):
        return {
          'tenant_id': 'tenant-a', 'idempotency_key': 'real-task-1',
          'task': {'tenant_id': 'tenant-a', 'task_id': 'task-1',
            'attempt_id': 'attempt-1', 'authority_caller_id': 'writer-1',
            'run_id': 'run-1', 'session_id': 'session-1',
            'fence': 7, 'epoch': 9, 'state': 'SUCCESS',
            'authority_state': 'REVOKED',
            'authority_valid_until': 200},
          'assignment': {'tenant_id': 'tenant-a', 'task_id': 'task-1',
            'attempt_id': 'attempt-1', 'role_id': 'developer',
            'principal_id': 'ai-1', 'state': 'ASSIGNED'},
          'role_instance': {'instance_id': 'ai-1',
                            'current_request_id': 'request-1'},
          'model_request': {'tenant_id': 'tenant-a', 'request_id': 'request-1',
            'task_id': 'task-1', 'attempt_id': 'attempt-1',
            'role_id': 'developer', 'state': 'SUCCEEDED'},
          'model_request_binding': {'request_id': 'request-1',
            'writer_principal': 'writer-1', 'writer_fence': 7,
            'writer_epoch': 9},
          'execution_intent': {'tenant_id': 'tenant-a', 'intent_id': 'intent-1',
            'task_id': 'task-1', 'attempt_id': 'attempt-1',
            'writer_principal': 'writer-1', 'writer_fence': 7,
            'writer_epoch': 9, 'state': 'SUCCEEDED', 'execution_id': 'exec-1',
            'session_id': 'session-1', 'thread_id': 'thread-1',
            'turn_id': 'turn-1'},
          'execution_events': [
            {'tenant_id': 'tenant-a', 'intent_id': 'intent-1',
             'event_id': 'sent-1', 'event_kind': 'SENT_INTENT', 'accepted': 1},
            {'tenant_id': 'tenant-a', 'intent_id': 'intent-1',
             'event_id': 'ack-1', 'event_kind': 'RUNNING', 'accepted': 1}],
          'process_receipt': {'tenant_id': 'tenant-a', 'task_id': 'task-1',
            'attempt_id': 'attempt-1', 'run_id': 'run-1',
            'session_id': 'session-1', 'process_id': 'pid-123',
            'writer_epoch': 9, 'state': 'STARTED',
            'source_kind': 'TRUSTED_PROCESS_OBSERVER', 'observed_at': 110},
          'ai_call_receipt': {'tenant_id': 'tenant-a', 'task_id': 'task-1',
            'attempt_id': 'attempt-1', 'request_id': 'request-1',
            'role_id': 'developer', 'writer_epoch': 9,
            'source_kind': 'LIVE_PROVIDER_RECEIPT',
            'provider_request_id': 'provider-1', 'response_sha256': 'a'*64},
          'checklist': {'tenant_id': 'tenant-a', 'task_id': 'task-1',
            'attempt_id': 'attempt-1', 'content_sha256': 'b'*64,
            'all_required_passed': 1, 'has_unexecuted': 0},
          'candidate': {'tenant_id': 'tenant-a', 'candidate_id': 'candidate-1',
            'task_id': 'task-1', 'attempt_id': 'attempt-1',
            'artifact_sha256': 'c'*64, 'checklist_sha256': 'b'*64,
            'submitted_by': 'ai-1', 'accepted_by': 'acceptor-1',
            'state': 'ACCEPTED'},
          'reviews': [
            {'tenant_id': 'tenant-a', 'candidate_id': 'candidate-1',
             'review_id': 'qa-1', 'review_kind': 'QA', 'reviewer': 'qa-1',
             'decision': 'QA_PASSED'},
            {'tenant_id': 'tenant-a', 'candidate_id': 'candidate-1',
             'review_id': 'security-1', 'review_kind': 'SECURITY',
             'reviewer': 'security-1', 'decision': 'SECURITY_PASSED'}],
          'terminal_receipt': {'tenant_id': 'tenant-a', 'task_id': 'task-1',
            'attempt_id': 'attempt-1', 'state': 'SUCCESS',
            'artifact_sha256': 'c'*64, 'authority_state': 'REVOKED'},
          'connection': {'purpose': 'CODEX_EXECUTION', 'status': 'ACTIVE'},
          'quota': {'quota_state': 'AVAILABLE',
                    'quota_source': 'EXISTING_SUBSCRIPTION_INCLUDED'},
        }

    def test_complete_chain_requires_same_identity_and_every_stage(self):
        value = evaluate_closure(self.snapshot(), observed_at=100)
        self.assertEqual(value['verdict'], PROVEN)
        self.assertTrue(all(item['status'] == PROVEN
                            for item in value['stages'].values()))
        self.assertEqual(len(value['receipt_sha256']), 64)

    def test_sent_ack_and_model_success_do_not_fake_process_or_live_call(self):
        value = self.snapshot()
        value.pop('process_receipt'); value.pop('ai_call_receipt')
        result = evaluate_closure(value, observed_at=100)
        self.assertEqual(result['stages']['SENT']['status'], PROVEN)
        self.assertEqual(result['stages']['ACK']['status'], PROVEN)
        self.assertEqual(result['stages']['PROCESS_STARTED']['status'], UNKNOWN)
        self.assertEqual(result['stages']['REAL_AI_CALL']['status'], UNKNOWN)
        self.assertEqual(result['verdict'], UNKNOWN)

    def test_process_receipt_cannot_self_assert_another_run(self):
        value = self.snapshot(); value['process_receipt']['run_id'] = 'other-run'
        result = evaluate_closure(value, observed_at=100)
        self.assertEqual(result['stages']['PROCESS_STARTED']['status'], UNKNOWN)

    def test_unknown_canonical_run_holds_instead_of_trusting_receipt(self):
        value = self.snapshot(); value['task']['run_id'] = UNKNOWN
        result = evaluate_closure(value, observed_at=100)
        self.assertEqual(result['verdict'], HOLD)
        self.assertIn('MISSING_RUN_ID', result['integrity_holds'])

    def test_intent_session_mismatch_holds_process_chain(self):
        value = self.snapshot(); value['execution_intent']['session_id'] = 'other-session'
        result = evaluate_closure(value, observed_at=100)
        self.assertEqual(result['verdict'], HOLD)
        self.assertIn('INTENT_SESSION_MISMATCH', result['integrity_holds'])

    def test_fixture_call_never_counts_as_real_provider_evidence(self):
        value = self.snapshot()
        value['ai_call_receipt']['source_kind'] = 'TEST_FIXTURE'
        result = evaluate_closure(value, observed_at=100)
        self.assertEqual(result['stages']['REAL_AI_CALL']['status'], UNKNOWN)

    def test_writer_epoch_or_attempt_mismatch_holds_whole_chain(self):
        for mutation in ('epoch', 'attempt'):
            value = self.snapshot()
            if mutation == 'epoch':
                value['execution_intent']['writer_epoch'] = 8
            else:
                value['assignment']['attempt_id'] = 'old-attempt'
            result = evaluate_closure(value, observed_at=100)
            self.assertEqual(result['verdict'], HOLD)
            self.assertTrue(all(item['status'] == HOLD
                                for item in result['stages'].values()))

    def test_request_and_role_instance_cannot_be_spliced(self):
        value = self.snapshot(); value['model_request']['request_id'] = 'other'
        self.assertEqual(evaluate_closure(value, observed_at=100)['verdict'], HOLD)
        value = self.snapshot(); value['role_instance']['instance_id'] = 'other-ai'
        self.assertEqual(evaluate_closure(value, observed_at=100)['verdict'], HOLD)
        value = self.snapshot(); value['role_instance']['current_request_id'] = 'other'
        self.assertEqual(evaluate_closure(value, observed_at=100)['verdict'], HOLD)

    def test_old_or_expired_writer_is_hold(self):
        value = self.snapshot(); value['task']['state'] = 'RUNNING'
        value.pop('terminal_receipt')
        self.assertEqual(evaluate_closure(value, observed_at=100)['verdict'], HOLD)
        value = self.snapshot(); value['task']['state'] = 'RUNNING'
        value['task']['authority_state'] = 'VALID'; value.pop('terminal_receipt')
        self.assertEqual(evaluate_closure(value, observed_at=200)['verdict'], HOLD)

    def test_reviewers_and_acceptor_must_be_independent(self):
        value = self.snapshot(); value['reviews'][0]['reviewer'] = 'ai-1'
        result = evaluate_closure(value, observed_at=100)
        self.assertEqual(result['stages']['INDEPENDENT_REVIEW']['status'], UNKNOWN)
        self.assertEqual(result['stages']['ACCEPTED']['status'], UNKNOWN)
        value = self.snapshot(); value['candidate']['accepted_by'] = 'qa-1'
        self.assertEqual(evaluate_closure(value, observed_at=100)[
          'stages']['ACCEPTED']['status'], UNKNOWN)

    def test_acceptance_requires_canonical_terminal_artifact(self):
        value = self.snapshot(); value['terminal_receipt']['artifact_sha256'] = 'd'*64
        result = evaluate_closure(value, observed_at=100)
        self.assertEqual(result['stages']['INDEPENDENT_REVIEW']['status'], PROVEN)
        self.assertEqual(result['stages']['ACCEPTED']['status'], UNKNOWN)

    def test_real_task_admission_does_not_claim_execution(self):
        value = self.snapshot(); value['task']['state'] = 'RUNNING'
        value['task']['authority_state'] = 'VALID'
        result = admission_for_real_task(value, observed_at=100)
        self.assertEqual(result['status'], PROVEN)
        self.assertIn('REAL_AI_CALL', result['does_not_prove'])
        value['quota']['quota_state'] = UNKNOWN
        held = admission_for_real_task(value, observed_at=100)
        self.assertEqual(held['status'], HOLD)
        self.assertIn('ATTRIBUTABLE_QUOTA_AVAILABLE_REQUIRED', held['holds'])

    def test_late_event_from_other_intent_is_not_ack(self):
        value = self.snapshot()
        value['execution_events'][1]['intent_id'] = 'old-intent'
        result = evaluate_closure(value, observed_at=100)
        self.assertEqual(result['stages']['ACK']['status'], UNKNOWN)


if __name__ == '__main__':
    unittest.main()
