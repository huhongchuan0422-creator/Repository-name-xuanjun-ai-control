from __future__ import print_function

import os
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from task_supervisor import Supervisor, UNKNOWN


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp()
        os.close(handle)
        self.now = 1000.0
        self.s = Supervisor(self.path, lambda: self.now)

    def tearDown(self):
        self.s.close()
        os.unlink(self.path)

    def registration(self, task='t1', deps=None):
        self.s.register(dict(task_id=task, parent_task_id='parent', stage='dev',
            writer_scope=task + ':dev', owner='developer', entry='WORK', checkpoint_sha256='a'*64,
            spec_sha256='b'*64, next_action='implement',
            dependencies=deps or [], completion_conditions=['tests'],
            progress_deadline=1900, receipt_deadline=1100,
            started_deadline=1200, terminal_deadline=3000,
            handoff_deadline=1800), now=self.now)

    def claim(self, task='t1', attempt='a1'):
        self.s.claim(task, attempt, 'developer', 'WORK', 'run1', 'session1',
                     'lease1', 1, 1, now=self.now)

    def test_ready_fair_scan_and_dependencies(self):
        self.registration('b')
        self.registration('a', ['b'])
        self.assertEqual([x['task_id'] for x in self.s.ready()], ['b'])

    def test_single_writer_cas_and_duplicate_event(self):
        self.registration(); self.claim()
        with self.assertRaises(ValueError): self.claim(attempt='a2')
        one = self.s.record('t1','a1','e1','STARTED',1001)
        two = self.s.record('t1','a1','e1','STARTED',1001)
        self.assertFalse(one['duplicate']); self.assertTrue(two['duplicate'])

    def test_heartbeat_does_not_refresh_progress(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.s.record('t1','a1','hb','HEARTBEAT',1200)
        self.assertIsNone(self.s._task('t1')['last_real_progress_at'])

    def test_real_progress_requires_bound_evidence(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        with self.assertRaises(ValueError):
            self.s.record('t1','a1','p0','PROGRESS',1002,'HEARTBEAT','x')
        self.s.record('t1','a1','p1','PROGRESS',1003,'TEST_RUN','run/42')
        self.assertEqual(self.s._task('t1')['last_real_progress_at'],1003)

    def test_5_10_15_recovery_is_bounded_and_no_takeover(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.assertEqual(self.s.scan(1302)[0]['action'],'CHECK_RECEIPT_AND_PROGRESS')
        self.assertEqual(self.s.scan(1602)[0]['action'],'RECONCILE_AND_RESUME_SAME_ATTEMPT')
        action=self.s.scan(1902)[0]
        self.assertEqual(action['action'],'VISIBLE_HOLD_OR_CONTROLLED_REASSIGN')
        self.assertFalse(action['takeover_allowed'])

    def test_terminal_outbox_survives_restart_and_deduplicates(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        payload=dict(state='SUCCESS',artifact_sha256='c'*64,
            writer_stopped=True,effects_reconciled=True,next_action='handoff',
            completion_evidence=['tests'])
        self.s.record('t1','a1','done','TERMINAL',1002,payload=payload)
        self.s.close(); self.s=Supervisor(self.path,lambda:self.now)
        due=self.s.due_outbox(1002)
        self.assertEqual(len(due),1)
        self.assertTrue(self.s.record('t1','a1','done','TERMINAL',1002,
                                      payload=payload)['duplicate'])

    def test_lost_completion_notification_retries_bounded(self):
        self.registration(); self.claim()
        payload=dict(state='FAILURE',artifact_sha256=UNKNOWN,
            writer_stopped=UNKNOWN,effects_reconciled=UNKNOWN,next_action='inspect',
            completion_evidence=[])
        self.s.record('t1','a1','done','TERMINAL',1002,payload=payload)
        item=self.s.due_outbox(1002)[0]
        expected=[1032,1092,1212,1452]
        now=1002
        for index,next_at in enumerate(expected,1):
            result=self.s.outbox_result(item['outbox_id'],False,now,'offline')
            self.assertEqual(result['attempts'],index)
            self.assertEqual(result['next_attempt_at'],next_at)
            now=next_at
        last=self.s.outbox_result(item['outbox_id'],False,now,'offline')
        self.assertTrue(last['dead_lettered'])
        self.assertEqual(self.s._task('t1')['state'],'HOLD')
        self.assertEqual(self.s.due_outbox(now + 999999),[])

    def test_receiver_without_ack_cannot_release_responsibility(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.s.record('t1','a1','h','HANDOFF_REQUESTED',1002)
        bad=dict(receiver_accepted=True,old_writer_stopped=False,
            old_fence_invalidated=True,effects_reconciled=True,
            new_owner='qa',new_entry='WORK',
            lease_id='lease1',fence=1,epoch=1)
        with self.assertRaises(ValueError):
            self.s.record('t1','a1','ackbad','HANDOFF_ACKNOWLEDGED',1003,'PHASE_EXECUTION','proof:'+('a'*64),bad)
        self.assertEqual(self.s._task('t1')['state'],'HANDOFF_PENDING')

    def test_exact_handoff_allows_new_claim_only_after_reconciliation(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.s.record('t1','a1','h','HANDOFF_REQUESTED',1002)
        good=dict(receiver_accepted=True,old_writer_stopped=True,
            old_fence_invalidated=True,effects_reconciled=True,
            new_owner='qa',new_entry='WORK',
            lease_id='lease1',fence=1,epoch=1)
        self.s.record('t1','a1','ack','HANDOFF_ACKNOWLEDGED',1003,'PHASE_EXECUTION','proof:'+('a'*64),good)
        self.s.claim('t1','a2','qa','WORK','run2','session2','lease2',2,2,1004)
        self.assertEqual(self.s._task('t1')['attempt_id'],'a2')

    def test_unknown_side_effects_preserved_in_visible_hold(self):
        self.registration(); self.claim()
        payload=dict(state='CAPABILITY_UNAVAILABLE',artifact_sha256=UNKNOWN,
            writer_stopped=UNKNOWN,effects_reconciled=UNKNOWN,
            next_action='owner-visible hold',completion_evidence=[])
        self.s.record('t1','a1','u','TERMINAL',1002,payload=payload)
        row=self.s._task('t1')
        self.assertEqual(row['state'],'CAPABILITY_UNAVAILABLE')
        self.assertEqual(row['effects_reconciled'],UNKNOWN)

    def test_normal_exit_without_receipt_becomes_visible_hold_action(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        action=self.s.scan(1902)[0]
        self.assertEqual(action['action'],'VISIBLE_HOLD_OR_CONTROLLED_REASSIGN')
        self.assertTrue(action['requires_effect_reconciliation'])
        self.assertEqual(self.s._task('t1')['state'],'HOLD')

    def test_old_writer_cannot_resume_after_ack_and_new_attempt(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.s.record('t1','a1','h','HANDOFF_REQUESTED',1002)
        good=dict(receiver_accepted=True,old_writer_stopped=True,
            old_fence_invalidated=True,effects_reconciled=True,
            new_owner='qa',new_entry='WORK',
            lease_id='lease1',fence=1,epoch=1)
        self.s.record('t1','a1','ack','HANDOFF_ACKNOWLEDGED',1003,'PHASE_EXECUTION','proof:'+('a'*64),good)
        self.s.claim('t1','a2','qa','WORK','run2','session2','lease2',2,2,1004)
        with self.assertRaises(ValueError):
            self.s.record('t1','a1','zombie','PROGRESS',1005,
                          'SOURCE_COMMIT','deadbeef')

    def test_heartbeat_cannot_delay_ten_or_fifteen_minute_actions(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.s.record('t1','a1','hb','HEARTBEAT',1290)
        self.assertEqual(self.s.scan(1602)[0]['action'],
                         'RECONCILE_AND_RESUME_SAME_ATTEMPT')
        self.s.record('t1','a1','hb2','HEARTBEAT',1295)
        self.assertEqual(self.s.scan(1902)[0]['action'],
                         'VISIBLE_HOLD_OR_CONTROLLED_REASSIGN')

    def test_ready_scan_does_not_starve_later_eligible_task(self):
        for index in range(101):
            self.registration('blocked-%03d' % index, ['missing'])
        self.registration('eligible')
        self.assertEqual([row['task_id'] for row in self.s.ready(1)],
                         ['eligible'])

    def test_fence_and_epoch_must_increase_after_handoff(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.s.record('t1','a1','h','HANDOFF_REQUESTED',1002)
        good=dict(receiver_accepted=True,old_writer_stopped=True,
            old_fence_invalidated=True,effects_reconciled=True,
            new_owner='qa',new_entry='WORK',lease_id='lease1',fence=1,epoch=1)
        self.s.record('t1','a1','ack','HANDOFF_ACKNOWLEDGED',1003,
                      'PHASE_EXECUTION','proof:'+('a'*64),good)
        with self.assertRaises(ValueError):
            self.s.claim('t1','a2','qa','WORK','run2','session2',
                         'lease2',1,1,1004)

    def test_unclaimed_or_unsafe_success_cannot_unlock_dependency(self):
        self.registration('parent')
        unsafe=dict(state='SUCCESS',artifact_sha256='c'*64,
            writer_stopped=False,effects_reconciled=False,next_action='handoff',
            completion_evidence=['tests'])
        with self.assertRaises(ValueError):
            self.s.record('parent',UNKNOWN,'fake','TERMINAL',1001,payload=unsafe)
        self.claim('parent')
        with self.assertRaises(ValueError):
            self.s.record('parent','a1','unsafe','TERMINAL',1002,payload=unsafe)

    def test_future_or_reordered_event_is_rejected(self):
        self.registration(); self.claim()
        with self.assertRaises(ValueError):
            self.s.record('t1','a1','future','STARTED',2000)
        self.s.record('t1','a1','start','STARTED',1001)
        with self.assertRaises(ValueError):
            self.s.record('t1','a1','old','HEARTBEAT',1000)

    def test_supervisor_liveness_never_claims_process_verified(self):
        with self.assertRaises(ValueError):
            self.s.supervisor_heartbeat('uk-supervisor','pid:42','d'*64,2000)
        self.s.supervisor_heartbeat('uk-supervisor','pid:42','d'*64,1000)
        self.assertEqual(self.s.supervisor_health(1001)[0]['state'],
                         'FRESH_RECORD_NOT_PROCESS_VERIFIED')

    def test_event_id_reuse_with_different_bytes_is_rejected(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        with self.assertRaises(ValueError):
            self.s.record('t1','a1','start','HEARTBEAT',1001)

    def test_assigned_responsibility_is_bound_to_claim(self):
        self.registration()
        with self.assertRaises(ValueError):
            self.s.claim('t1','a1','other','WORK','run1','session1',
                         'lease1',1,1,now=self.now)

    def test_deadlines_trigger_even_before_generic_age(self):
        self.registration()
        action = self.s.scan(1100)[0]
        self.assertEqual(action['action'],'CHECK_RECEIPT_AND_PROGRESS')
        self.assertEqual(action['attempt_id'],UNKNOWN)

    def test_supervision_action_and_hold_survive_restart(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.s.scan(1302); self.s.scan(1602); self.s.scan(1902)
        self.s.close(); self.s=Supervisor(self.path,lambda:self.now)
        self.assertEqual(self.s._task('t1')['state'],'HOLD')
        events=[r['event_id'] for r in self.s.db.execute(
            "SELECT event_id FROM events WHERE kind='SUPERVISION_ACTION'")]
        self.assertEqual(len(events),3)
        self.assertEqual(len(self.s.due_outbox(1902)),3)

    def test_supervisor_liveness_survives_restart(self):
        self.s.supervisor_heartbeat('uk-supervisor','pid:42','d'*64,1000)
        self.s.close(); self.s=Supervisor(self.path,lambda:self.now)
        self.assertEqual(self.s.supervisor_health(1200)[0]['state'],
                         'FRESH_RECORD_NOT_PROCESS_VERIFIED')
        self.assertEqual(self.s.supervisor_health(1400)[0]['state'],
                         'SUPERVISOR_UNAVAILABLE')

    def test_real_progress_resets_recovery_budget(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.s.scan(1302)
        self.assertEqual(self.s._task('t1')['recovery_level'],1)
        self.s.record('t1','a1','p','PROGRESS',1303,
                      'SOURCE_COMMIT','commit:abc',
                      {'next_progress_deadline':2000})
        self.assertEqual(self.s._task('t1')['recovery_level'],0)
        self.assertEqual(self.s._task('t1')['progress_deadline'],2000)

    def test_late_handoff_requires_fresh_attempt_deadlines(self):
        self.registration(); self.claim()
        self.s.record('t1','a1','start','STARTED',1001)
        self.s.record('t1','a1','h','HANDOFF_REQUESTED',1002)
        good=dict(receiver_accepted=True,old_writer_stopped=True,
            old_fence_invalidated=True,effects_reconciled=True,
            new_owner='qa',new_entry='WORK',
            lease_id='lease1',fence=1,epoch=1)
        self.s.record('t1','a1','ack','HANDOFF_ACKNOWLEDGED',1003,'PHASE_EXECUTION','proof:'+('a'*64),good)
        with self.assertRaises(ValueError):
            self.s.claim('t1','a2','qa','WORK','run2','session2',
                         'lease2',2,2,now=4000)
        deadlines=dict(progress_deadline=5000,receipt_deadline=4100,
            started_deadline=4200,terminal_deadline=6000,handoff_deadline=5500)
        self.s.claim('t1','a2','qa','WORK','run2','session2',
                     'lease2',2,2,now=4000,deadlines=deadlines)
        task=self.s._task('t1')
        self.assertEqual(task['recovery_level'],0)
        self.assertEqual(task['writer_stopped'],UNKNOWN)

    def test_terminal_artifact_hash_is_strict(self):
        self.registration(); self.claim()
        bad=dict(state='SUCCESS',artifact_sha256='not-a-hash',
            writer_stopped=True,effects_reconciled=True,next_action='handoff',
            completion_evidence=['tests'])
        with self.assertRaises(ValueError):
            self.s.record('t1','a1','bad','TERMINAL',1002,payload=bad)

    def test_quota_unavailable_is_terminal_durable_and_not_fake_running(self):
        self.registration(); self.claim()
        payload=dict(state='CAPABILITY_UNAVAILABLE',artifact_sha256=UNKNOWN,
            writer_stopped=True,effects_reconciled=True,
            next_action='OWNER_VISIBLE_QUOTA_HOLD',completion_evidence=[])
        self.s.record('t1','a1','quota','TERMINAL',1002,payload=payload)
        self.assertEqual(self.s._task('t1')['state'],'CAPABILITY_UNAVAILABLE')
        self.assertEqual(len(self.s.due_outbox(1002)),1)


if __name__ == '__main__':
    unittest.main()
