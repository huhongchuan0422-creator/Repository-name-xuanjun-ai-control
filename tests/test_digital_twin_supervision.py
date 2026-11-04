from __future__ import print_function

import os
import sys
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from digital_twin_supervision import evaluate_supervision


class DigitalTwinSupervisionTests(unittest.TestCase):
    def snapshot(self):
        return {
            'task': {
                'task_id': 'task-1', 'attempt_id': 'attempt-1',
                'state': 'STARTED', 'run_id': 'run-1',
                'session_id': 'session-1', 'epoch': 7,
                'authority_state': 'VALID', 'effects_reconciled': 'TRUE',
                'last_real_progress_at': 900, 'received_at': 800,
                'started_at': 850, 'terminal_deadline': 3000,
                'next_action': 'work',
            },
            'events': [
                {'event_id': 'ack-1', 'kind': 'EXECUTOR_ACK',
                 'observed_at': 820},
                {'event_id': 'start-1', 'kind': 'PROCESS_STARTED',
                 'observed_at': 850},
                {'event_id': 'heartbeat-1', 'kind': 'HEARTBEAT_OBSERVED',
                 'observed_at': 999},
                {'event_id': 'progress-1', 'kind': 'PROGRESS_EVIDENCED',
                 'observed_at': 900, 'evidence_ref': 'test://run-1'},
            ],
            'execution': {
                'run_id': 'run-1', 'session_id': 'session-1',
                'process_id': 'pid:42', 'writer_epoch': 7,
                'process_state': 'PROVEN_RUNNING', 'observed_at': 1000,
                'evidence_ref': 'proc://42',
                'source': 'Task Supervisor process observer',
            },
            'supervisor': {
                'instance_id': 'supervisor-1',
                'process_state': 'PROVEN_RUNNING',
                'last_heartbeat_at': 990, 'evidence_ref': 'supervisor://1',
            },
            'checkpoints': [],
            'unknown_effects': [],
        }

    def test_heartbeat_is_separate_and_cannot_hide_stale_progress(self):
        value = evaluate_supervision(self.snapshot(), 1601)
        self.assertEqual(value['decision'], 'STALLED_NO_PROGRESS')
        self.assertEqual(value['progress']['last_heartbeat_at'], 999)
        self.assertFalse(value['progress']['heartbeat_counts_as_progress'])

    def test_ack_without_start_is_not_started(self):
        value = self.snapshot()
        value['task']['state'] = 'RECEIVED'
        value['task']['last_real_progress_at'] = None
        value['events'] = value['events'][:1]
        value['execution']['process_state'] = 'UNKNOWN'
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'ACCEPTED_NOT_STARTED')
        self.assertEqual(result['reason'], 'ACK_IS_NOT_START')

    def test_process_exit_is_result_missing_not_failure(self):
        value = self.snapshot()
        value['execution']['process_state'] = 'PROVEN_EXITED'
        value['task']['effects_reconciled'] = 'UNKNOWN'
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertNotEqual(result['decision'], 'TERMINAL')
        self.assertFalse(result['recovery']['allowed'])

    def test_safe_recovery_preserves_task_attempt_executor(self):
        value = self.snapshot()
        value['execution']['process_state'] = 'PROVEN_EXITED'
        value['checkpoints'] = [{
            'attempt_id': 'attempt-1', 'checkpoint_id': 'checkpoint-1',
            'created_at': 950, 'effects_state': 'RECONCILED'}]
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'RECOVERABLE_SAME_ATTEMPT')
        self.assertTrue(result['recovery']['allowed'])
        self.assertEqual(result['recovery']['same_attempt_id'], 'attempt-1')
        self.assertTrue(result['recovery']['same_executor_required'])
        self.assertFalse(result['recovery']['new_writer_authority_granted'])

    def test_unknown_effect_holds_and_is_never_redispatched(self):
        value = self.snapshot()
        value['unknown_effects'] = [{
            'task_id': 'task-1', 'attempt_id': 'attempt-1',
            'operation_id': 'operation-1', 'resource_key': 'git:repo:branch',
            'state': 'UNKNOWN'}]
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertEqual(result['unknown_effects']['unresolved_operation_ids'],
                         ['operation-1'])
        self.assertFalse(result['unknown_effects']['redispatch_allowed'])

    def test_unknown_effect_without_original_key_holds(self):
        value = self.snapshot()
        value['unknown_effects'] = [{
            'task_id': 'task-1', 'attempt_id': 'attempt-1',
            'operation_id': 'operation-1', 'state': 'UNKNOWN'}]
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertEqual(result['reason'],
                         'UNKNOWN_EFFECT_ORIGINAL_KEY_MISSING_OR_MISMATCHED')

    def test_old_epoch_is_rejected_before_late_result(self):
        value = self.snapshot()
        value['execution']['writer_epoch'] = 6
        value['task']['state'] = 'SUCCESS'
        value['events'].append({'event_id': 'terminal-1',
                                'kind': 'TERMINAL_RECEIPT',
                                'observed_at': 1000})
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'STALE_EXECUTOR_REJECTED')
        self.assertEqual(result['reason'],
                         'EXECUTION_IDENTITY_OR_EPOCH_MISMATCH')

    def test_known_process_requires_complete_current_identity(self):
        value = self.snapshot()
        value['execution']['run_id'] = 'UNKNOWN'
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertEqual(result['reason'],
                         'EXECUTION_OBSERVATION_NOT_BOUND_TO_CURRENT_IDENTITY')

    def test_unknown_canonical_run_or_session_cannot_bind_known_process(self):
        for field in ('run_id', 'session_id'):
            value = self.snapshot()
            value['task'][field] = 'UNKNOWN'
            result = evaluate_supervision(value, 1000)
            self.assertEqual(result['decision'], 'HOLD', field)
            self.assertNotIn(result['decision'], ('EXECUTING',
                                                   'RECOVERABLE_SAME_ATTEMPT'))

    def test_unknown_canonical_identity_cannot_make_exit_recoverable(self):
        value = self.snapshot()
        value['task']['run_id'] = 'UNKNOWN'
        value['execution']['process_state'] = 'PROVEN_EXITED'
        value['checkpoints'] = [{
            'attempt_id': 'attempt-1', 'checkpoint_id': 'checkpoint-1',
            'created_at': 950, 'effects_state': 'RECONCILED'}]
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertFalse(result['recovery']['allowed'])

    def test_untrusted_same_attempt_exit_event_cannot_allow_recovery(self):
        value = self.snapshot()
        value['execution']['process_state'] = 'UNKNOWN'
        value['events'].append({
            'task_id': 'task-1', 'attempt_id': 'attempt-1',
            'event_id': 'exit-forged', 'kind': 'PROCESS_EXITED',
            'observed_at': 950})
        value['checkpoints'] = [{
            'attempt_id': 'attempt-1', 'checkpoint_id': 'checkpoint-1',
            'created_at': 940, 'effects_state': 'RECONCILED'}]
        result = evaluate_supervision(value, 1000)
        self.assertNotEqual(result['decision'], 'RECOVERABLE_SAME_ATTEMPT')
        self.assertFalse(result['recovery']['allowed'])

    def test_untrusted_process_exit_observation_cannot_allow_recovery(self):
        value = self.snapshot()
        value['execution']['process_state'] = 'PROVEN_EXITED'
        value['execution']['source'] = 'caller-asserted'
        value['checkpoints'] = [{
            'attempt_id': 'attempt-1', 'checkpoint_id': 'checkpoint-1',
            'created_at': 940, 'effects_state': 'RECONCILED'}]
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertEqual(result['reason'], 'UNTRUSTED_EXECUTION_OBSERVATION')
        self.assertFalse(result['recovery']['allowed'])

    def test_old_or_untrusted_exit_identity_cannot_allow_recovery(self):
        for changed in ('run_id', 'session_id', 'writer_epoch', 'producer'):
            value = self.snapshot()
            value['execution']['process_state'] = 'UNKNOWN'
            event = {
                'task_id': 'task-1', 'attempt_id': 'attempt-1',
                'event_id': 'exit-' + changed, 'kind': 'PROCESS_EXITED',
                'observed_at': 950, 'run_id': 'run-1',
                'session_id': 'session-1', 'writer_epoch': 7,
                'producer': 'Task Supervisor process observer',
                'evidence_ref': 'proc://exit'}
            event[changed] = ('untrusted' if changed == 'producer'
                              else (6 if changed == 'writer_epoch' else 'old'))
            value['events'].append(event)
            value['checkpoints'] = [{
                'attempt_id': 'attempt-1', 'checkpoint_id': 'checkpoint-1',
                'created_at': 940, 'effects_state': 'RECONCILED'}]
            result = evaluate_supervision(value, 1000)
            self.assertNotEqual(result['decision'],
                                'RECOVERABLE_SAME_ATTEMPT', changed)
            self.assertFalse(result['recovery']['allowed'], changed)

    def test_trusted_exact_exit_event_can_make_same_attempt_recoverable(self):
        value = self.snapshot()
        value['execution']['process_state'] = 'UNKNOWN'
        value['events'].append({
            'task_id': 'task-1', 'attempt_id': 'attempt-1',
            'event_id': 'exit-trusted', 'kind': 'PROCESS_EXITED',
            'observed_at': 950, 'run_id': 'run-1',
            'session_id': 'session-1', 'writer_epoch': 7,
            'producer': 'Task Supervisor process observer',
            'evidence_ref': 'proc://exit'})
        value['checkpoints'] = [{
            'attempt_id': 'attempt-1', 'checkpoint_id': 'checkpoint-1',
            'created_at': 940, 'effects_state': 'RECONCILED'}]
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'RECOVERABLE_SAME_ATTEMPT')
        self.assertTrue(result['recovery']['allowed'])

    def test_success_requires_bound_terminal_receipt(self):
        value = self.snapshot()
        value['task']['state'] = 'SUCCESS'
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'RESULT_MISSING')
        value['events'].append({'event_id': 'terminal-1', 'kind': 'TERMINAL',
                                'observed_at': 1000})
        self.assertEqual(evaluate_supervision(value, 1000)['decision'],
                         'COMPLETE')

    def test_old_attempt_terminal_receipt_cannot_complete_current_attempt(self):
        value = self.snapshot()
        value['task']['state'] = 'SUCCESS'
        value['events'].append({
            'task_id': 'task-1', 'attempt_id': 'attempt-old',
            'event_id': 'terminal-old', 'kind': 'TERMINAL',
            'observed_at': 1000})
        result = evaluate_supervision(value, 1000)
        self.assertEqual(result['decision'], 'RESULT_MISSING')

    def test_next_action_is_idempotent_and_supervisor_stall_is_separate(self):
        value = self.snapshot()
        value['supervisor']['last_heartbeat_at'] = 100
        first = evaluate_supervision(value, 1000)
        second = evaluate_supervision(value, 1100)
        self.assertEqual(first['next_action_id'], second['next_action_id'])
        self.assertEqual(first['supervisor']['status'],
                         'STALLED_OR_UNKNOWN')
        self.assertNotEqual(first['decision'], 'COMPLETE')


if __name__ == '__main__':
    unittest.main()
