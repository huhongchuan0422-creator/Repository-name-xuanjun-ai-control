from __future__ import print_function

import json
import os
import shutil
import subprocess
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from reusable_task_gateway import (GatewayKernel, TestOnlyExecutor,
                                    TestTenantAuthority)
from task_supervisor import Supervisor, UNKNOWN
from task_writer_fence import Fence


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.path = os.path.join(self.root, 'ledger.sqlite')
        self.lock_root = os.path.join(self.root, 'locks')
        self.now = 1000.0
        self.supervisor = Supervisor(self.path, lambda: self.now)
        self.authority = TestTenantAuthority(b'k' * 32)
        self.gateway = GatewayKernel(
            self.supervisor, self.authority, lambda: self.now)
        self.fence = Fence(self.supervisor, self.lock_root)
        self.a = self.authority.issue('tenant-a', 'owner-a')
        self.b = self.authority.issue('tenant-b', 'owner-b')

    def tearDown(self):
        try:
            self.fence.close()
            self.supervisor.close()
        finally:
            shutil.rmtree(self.root)

    @staticmethod
    def task(task_id, output, dependencies=None, priority=10,
             preemptible=True, resources=None, evidence='evidence-v1',
             board='research-development'):
        return {
            'task_id': task_id, 'node_id': 'node-' + task_id,
            'stage': 'development', 'owner': 'developer', 'entry': 'WORK',
            'checkpoint_sha256': ('a' if task_id.endswith('a') else 'b') * 64,
            'spec_sha256': ('c' if task_id.endswith('a') else 'd') * 64,
            'input_version': 'input-v1', 'output_version': output,
            'priority': priority, 'preemptible': preemptible,
            'module_id': 'xuanjun.scheduler.kernel',
            'board_id': board,
            'resources': resources or ['fake:resource-' + task_id],
            'dependencies': dependencies or [],
            'completion_evidence': [{'evidence_ref': evidence}],
        }

    def graph(self, tenant='tenant-a', suffix='a', tasks=None):
        return {'graph_id': 'graph-' + suffix, 'tenant_id': tenant,
                'project_id': 'project-' + suffix, 'graph_version': 'v1',
                'tasks': tasks or [self.task('task-' + suffix, 'v1')]}

    def register_wait_graph(self):
        producer = self.task('task-b', 'b-v3', evidence='evid-b-v3')
        consumer = self.task('task-a', 'a-v1', dependencies=[{
            'task_id': 'task-b', 'version': 'b-v3',
            'evidence_ref': 'evid-b-v3'}], priority=100,
            resources=['fake:shared'])
        worker = self.task('task-c', 'c-v1', priority=10,
            preemptible=False,
            resources=['fake:shared'])
        self.gateway.register_graph(
            self.a, self.graph(tasks=[producer, consumer, worker]), now=1000)

    def executor(self, context=None):
        return TestOnlyExecutor(self.gateway, self.fence,
                                context or self.a, lambda: self.now)

    def start_complete_b(self):
        exe = self.executor()
        self.now = 1010
        exe.start('task-b', 'attempt-b1', ['fake:resource-task-b'], 2000)
        self.now = 1012
        exe.progress('task-b', 'attempt-b1', 'progress-b', 'test-b', self.now)
        self.now = 1013
        exe.complete_success('task-b', 'attempt-b1', 'f' * 64,
                             [{'evidence_ref': 'evid-b-v3'}], self.now)
        return self.supervisor.db.execute(
            "SELECT outbox_id,event_id FROM outbox WHERE task_id='task-b'"
        ).fetchone()

    def test_dynamic_graph_and_two_tenant_isolation(self):
        result = self.gateway.register_graph(self.a, self.graph(), now=1000)
        self.assertFalse(result['duplicate'])
        self.gateway.register_graph(self.b, self.graph(
            tenant='tenant-b', suffix='b'), now=1000)
        self.assertEqual(len(self.gateway.projection(self.a)['tasks']), 1)
        self.assertEqual(len(self.gateway.projection(self.b)['tasks']), 1)
        with self.assertRaisesRegex(ValueError, 'CROSS_TENANT'):
            self.gateway.assert_task_context(self.b, 'task-a')
        with self.assertRaisesRegex(ValueError, 'TRUSTED_TENANT'):
            self.gateway.projection({'tenant_id': 'tenant-a'})

    def test_cycle_and_duplicate_graph_conflict_rejected(self):
        t1 = self.task('task-a', 'v1', dependencies=[{
            'task_id': 'task-b', 'version': 'v1', 'evidence_ref': 'e'}])
        t2 = self.task('task-b', 'v1', dependencies=[{
            'task_id': 'task-a', 'version': 'v1', 'evidence_ref': 'e'}])
        with self.assertRaisesRegex(ValueError, 'CYCLIC'):
            self.gateway.register_graph(self.a, self.graph(tasks=[t1, t2]))
        graph = self.graph()
        self.gateway.register_graph(self.a, graph)
        self.assertTrue(self.gateway.register_graph(self.a, graph)['duplicate'])
        changed = dict(graph); changed['graph_version'] = 'v2'
        with self.assertRaisesRegex(ValueError, 'GRAPH_ID_CONFLICT'):
            self.gateway.register_graph(self.a, changed)

    def test_atomic_terminal_outbox_and_sent_ack_are_distinct(self):
        self.register_wait_graph()
        outbox = self.start_complete_b()
        task = self.supervisor._task('task-b')
        self.assertEqual(task['state'], 'SUCCESS')
        self.assertIsNone(self.supervisor.db.execute(
            'SELECT delivered_at FROM outbox WHERE outbox_id=?',
            (outbox['outbox_id'],)).fetchone()['delivered_at'])
        with self.assertRaisesRegex(ValueError, 'CROSS_TENANT'):
            self.gateway.mark_outbox_sent(
                self.b, outbox['outbox_id'], 'wrong-tenant', 1014)
        with self.assertRaisesRegex(ValueError, 'OUTBOX_NOT_SENT'):
            self.gateway.receive_outbox(self.a, outbox['outbox_id'])
        self.now = 1014
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'],
                                      'transport-receipt', self.now)
        self.assertEqual(self.gateway.receive_outbox(
            self.a, outbox['outbox_id'], self.now)['state'], 'RECEIVED')
        dep = self.supervisor.db.execute('''SELECT state FROM
          gateway_dependencies WHERE consumer_task_id='task-a' ''').fetchone()
        self.assertEqual(dep['state'], 'WAITING')
        ack = self.gateway.acknowledge_event(self.a, outbox['event_id'], 1015)
        self.assertEqual(ack['state'], 'CONSUMED_ACK')
        dep = self.supervisor.db.execute('''SELECT state FROM
          gateway_dependencies WHERE consumer_task_id='task-a' ''').fetchone()
        self.assertEqual(dep['state'], 'RECEIVED')

    def test_duplicate_delivery_and_out_of_order_old_version(self):
        self.register_wait_graph()
        outbox = self.start_complete_b()
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 1014)
        first = self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1014)
        second = self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1015)
        self.assertFalse(first['duplicate']); self.assertTrue(second['duplicate'])
        self.gateway.acknowledge_event(self.a, outbox['event_id'], 1016)
        duplicate = self.gateway.acknowledge_event(self.a, outbox['event_id'], 1017)
        self.assertTrue(duplicate['duplicate'])
        self.supervisor.db.execute("""UPDATE gateway_dependencies
          SET required_version='b-v4',state='WAITING',event_attempt_id=NULL,
          event_id=NULL
          WHERE consumer_task_id='task-a'""")
        self.supervisor.db.commit()
        # Replayed old event remains ACKed and cannot satisfy a new version.
        self.assertTrue(self.gateway.acknowledge_event(
            self.a, outbox['event_id'], 1018)['duplicate'])
        state = self.supervisor.db.execute('''SELECT state FROM
          gateway_dependencies WHERE consumer_task_id='task-a' ''').fetchone()[0]
        self.assertEqual(state, 'WAITING')

    def test_waiting_dependency_not_reported_timeout(self):
        self.register_wait_graph()
        self.now = 10000
        status = {x['task_id']: x for x in self.gateway.monitor(self.a)}
        self.assertEqual(status['task-a']['status'], 'WAITING_DEPENDENCY')
        self.assertEqual(status['task-a']['waiting_dependencies'], 1)

    def test_expired_or_revoked_writer_cannot_progress_or_checkpoint(self):
        self.gateway.register_graph(self.a,self.graph(),now=1000)
        self.executor().start('task-a','attempt-a1',['fake:resource-task-a'],1010)
        before_events=self.supervisor.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        before_points=self.supervisor.db.execute(
          'SELECT COUNT(*) FROM gateway_checkpoints').fetchone()[0]
        self.now=1011
        with self.assertRaisesRegex(ValueError,'CURRENT_WRITER_AUTHORITY_REQUIRED'):
            self.executor().progress('task-a','attempt-a1','late-progress','evidence')
        with self.assertRaisesRegex(ValueError,'CURRENT_WRITER_AUTHORITY_REQUIRED'):
            self.gateway.save_checkpoint(self.a,'task-a','attempt-a1','late-point',
              {'work':'late'},[],'RECONCILED',['fake:resource-task-a'],self.now)
        self.assertEqual(self.supervisor.db.execute(
          'SELECT COUNT(*) FROM events').fetchone()[0],before_events)
        self.assertEqual(self.supervisor.db.execute(
          'SELECT COUNT(*) FROM gateway_checkpoints').fetchone()[0],before_points)

    def test_resource_conflict_nonpreemptible_and_safe_release(self):
        self.register_wait_graph()
        exe = self.executor()
        self.now = 1001
        started = exe.start('task-c', 'attempt-c1', ['fake:shared'], 3000)
        decision = self.gateway.preemption_decision(
            self.a, 'task-c', 'task-a')
        self.assertEqual(decision['decision'], 'WAIT_NEXT_SAFE_POINT')
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_CONSUMED_ACK'):
            exe.start('task-a', 'attempt-a1', ['fake:shared'], 3000)
        self.gateway.save_checkpoint(self.a, 'task-c', 'attempt-c1',
            'checkpoint-c1', {'work': 'saved'}, ['external-write'], UNKNOWN,
            ['fake:shared'], 1002)
        with self.assertRaisesRegex(ValueError, 'SAFE_RESOURCE_RELEASE'):
            self.gateway.release_revoked_resources(
                self.a, 'task-c', 'attempt-c1', 'checkpoint-c1', 'release', 1003)
        self.assertFalse(self.supervisor.db.execute('''SELECT preemptible FROM
          gateway_task_metadata WHERE task_id='task-c' ''').fetchone()[0] is None)
        # Reconcile checkpoint, then use the existing fence revocation proof.
        self.supervisor.db.execute('''UPDATE gateway_checkpoints
          SET inflight_json='[]',effects_state='RECONCILED'
          WHERE task_id='task-c' ''')
        self.supervisor.db.commit()
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'gateway'}
        self.fence.begin_revocation('task-c', controller)
        self.fence.drain('task-c', controller, timeout=0.2)
        self.fence.invalidate_source_resources('task-c', 'release-c')
        self.supervisor.complete_revocation('task-c')
        released = self.gateway.release_revoked_resources(
            self.a, 'task-c', 'attempt-c1', 'checkpoint-c1', 'release-c', 1004)
        self.assertEqual(released['state'], 'RELEASED')
        self.assertEqual(started['state'], 'STARTED')

    def test_complete_resume_keeps_started_fact_and_records_failure(self):
        self.register_wait_graph()
        self.gateway.save_waiting_checkpoint(
            self.a, 'task-a', 'attempt-a0', 'checkpoint-a0', {},
            ['fake:shared'], 1001)
        outbox = self.start_complete_b()
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 1014)
        self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1014)
        self.gateway.acknowledge_event(self.a, outbox['event_id'], 1015)
        grant = self.gateway.issue_resume_grant(
            self.a, 'task-a', 'checkpoint-a0', 2000, 1016)
        self.gateway.consume_resume_grant(
            self.a, 'task-a', grant['grant_id'], 'checkpoint-a0', 1017)
        failed = self.gateway.complete_resume(
            self.a, 'task-a', grant['grant_id'], False, 'executor-failed', 1018)
        self.assertTrue(failed['started'])
        self.assertEqual(failed['result'], 'FAILED')
        phases = [row['phase'] for row in self.supervisor.db.execute(
            '''SELECT phase FROM gateway_delivery_receipts WHERE event_id=?''',
            (grant['grant_id'],))]
        self.assertEqual(phases, ['RESUME_FAILED'])

    def test_full_wait_do_c_b_event_safe_yield_resume_a(self):
        self.register_wait_graph()
        exe = self.executor()
        self.now = 1001
        exe.start('task-c', 'attempt-c1', ['fake:shared'], 3000)
        self.gateway.save_waiting_checkpoint(
            self.a, 'task-a', 'attempt-a0', 'checkpoint-a0',
            {'cursor': 7}, ['fake:shared'], 1002)
        outbox = self.start_complete_b()
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 1014)
        self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1014)
        self.gateway.acknowledge_event(self.a, outbox['event_id'], 1015)
        with self.assertRaisesRegex(ValueError, 'RESUME_RESOURCE_CONFLICT'):
            self.gateway.issue_resume_grant(
                self.a, 'task-a', 'checkpoint-a0', 2000, 1016)
        self.gateway.save_checkpoint(self.a, 'task-c', 'attempt-c1',
            'checkpoint-c1', {'cursor': 4}, [], 'RECONCILED',
            ['fake:shared'], 1016)
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'gateway'}
        self.fence.begin_revocation('task-c', controller)
        self.fence.drain('task-c', controller, timeout=0.2)
        self.fence.invalidate_source_resources('task-c', 'release-c')
        self.supervisor.complete_revocation('task-c')
        self.gateway.release_revoked_resources(
            self.a, 'task-c', 'attempt-c1', 'checkpoint-c1', 'release-c', 1017)
        grant = self.gateway.issue_resume_grant(
            self.a, 'task-a', 'checkpoint-a0', 2000, 1018)
        self.now = 1019
        resumed = exe.start('task-a', 'attempt-a1', ['fake:shared'], 2000,
                            checkpoint_id='checkpoint-a0',
                            resume_grant_id=grant['grant_id'])
        self.assertEqual(resumed['state'], 'STARTED')
        self.assertEqual(self.supervisor._task('task-a')['attempt_id'],
                         'attempt-a1')

    def test_checkpoint_match_grant_once_expiry_and_revoke(self):
        self.register_wait_graph()
        # Persist the original A checkpoint before the dependency unlock.
        self.gateway.save_waiting_checkpoint(
            self.a, 'task-a', 'attempt-a0', 'checkpoint-a0',
            {'resume': 'here'}, ['fake:shared'], 1001)
        outbox = self.start_complete_b()
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 1014)
        self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1014)
        self.gateway.acknowledge_event(self.a, outbox['event_id'], 1015)
        grant = self.gateway.issue_resume_grant(
            self.a, 'task-a', 'checkpoint-a0', 2000, 1016)
        with self.assertRaisesRegex(ValueError, 'CHECKPOINT_MISMATCH'):
            self.gateway.consume_resume_grant(
                self.a, 'task-a', grant['grant_id'], 'wrong', 1017)
        self.assertEqual(self.gateway.consume_resume_grant(
            self.a, 'task-a', grant['grant_id'], 'checkpoint-a0', 1017
        )['state'], 'STARTED')
        with self.assertRaisesRegex(ValueError, 'ALREADY_USED'):
            self.gateway.consume_resume_grant(
                self.a, 'task-a', grant['grant_id'], 'checkpoint-a0', 1018)
        self.gateway.revoke_dependency(self.a, 'task-b', 'qa-revoked', 1019)
        state = self.supervisor.db.execute('''SELECT state FROM
          gateway_resume_grants WHERE grant_id=?''',
          (grant['grant_id'],)).fetchone()[0]
        self.assertEqual(state, 'REVOKED')

    def test_expired_grant_and_restart_projection_consistency(self):
        self.register_wait_graph()
        self.gateway.save_waiting_checkpoint(
            self.a, 'task-a', 'attempt-a0', 'checkpoint-a0', {},
            ['fake:shared'], 1001)
        outbox = self.start_complete_b()
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 1014)
        self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1014)
        self.gateway.acknowledge_event(self.a, outbox['event_id'], 1015)
        grant = self.gateway.issue_resume_grant(
            self.a, 'task-a', 'checkpoint-a0', 1020, 1016)
        with self.assertRaisesRegex(ValueError, 'EXPIRED'):
            self.gateway.consume_resume_grant(
                self.a, 'task-a', grant['grant_id'], 'checkpoint-a0', 1021)
        before = self.gateway.projection(self.a)
        self.fence.close(); self.supervisor.close()
        self.supervisor = Supervisor(self.path, lambda: self.now)
        self.gateway = GatewayKernel(
            self.supervisor, self.authority, lambda: self.now)
        self.fence = Fence(self.supervisor, self.lock_root)
        after = self.gateway.projection(self.a)
        self.assertEqual(before, after)

    def test_only_scheduler_and_twin_module_contracts_exist(self):
        rows = list(self.supervisor.db.execute('''SELECT module_id,version,
          contract_json FROM gateway_module_contracts ORDER BY module_id'''))
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {x['module_id'] for x in rows},
            {'xuanjun.scheduler.kernel', 'xuanjun.digital-twin.projection'})
        self.assertTrue(all(json.loads(x['contract_json'])['lifecycle'] ==
                            'TEST_ONLY' for x in rows))

    def test_cross_tenant_progress_and_terminal_reject_before_any_write(self):
        self.gateway.register_graph(self.a, self.graph(), now=1000)
        self.now = 1001
        self.executor().start('task-a', 'attempt-a1',
                              ['fake:resource-task-a'], 2000)
        before = {name: self.supervisor.db.execute(
            'SELECT COUNT(*) FROM ' + name).fetchone()[0]
            for name in ('tasks', 'events', 'outbox', 'gateway_checkpoints')}
        wrong = self.executor(self.b)
        with self.assertRaisesRegex(ValueError, 'CROSS_TENANT'):
            wrong.progress('task-a', 'attempt-a1', 'wrong-progress', 'x', 1002)
        with self.assertRaisesRegex(ValueError, 'CROSS_TENANT'):
            wrong.complete_success('task-a', 'attempt-a1', 'f' * 64,
                                   [{'evidence_ref': 'evidence-v1'}], 1003)
        after = {name: self.supervisor.db.execute(
            'SELECT COUNT(*) FROM ' + name).fetchone()[0]
            for name in before}
        self.assertEqual(before, after)
        self.assertEqual(self.supervisor._task('task-a')['state'], 'STARTED')

    def test_start_requires_ack_matching_evidence_and_resume_grant(self):
        self.register_wait_graph()
        self.gateway.save_waiting_checkpoint(
            self.a, 'task-a', 'attempt-a0', 'checkpoint-a0', {},
            ['fake:shared'], 1001)
        outbox = self.start_complete_b()
        exe = self.executor()
        with self.assertRaisesRegex(ValueError, 'CONSUMED_ACK'):
            exe.start('task-a', 'attempt-a1', ['fake:shared'], 2000)
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 1014)
        self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1014)
        self.gateway.acknowledge_event(
            self.a, 'task-b', 'attempt-b1', outbox['event_id'], 1015)
        with self.assertRaisesRegex(ValueError, 'RESUME_GRANT'):
            exe.start('task-a', 'attempt-a1', ['fake:shared'], 2000,
                      checkpoint_id='checkpoint-a0')
        grant = self.gateway.issue_resume_grant(
            self.a, 'task-a', 'checkpoint-a0', 2000, 1016)
        self.gateway.revoke_dependency(self.a, 'task-b', 'qa-revoked', 1017)
        with self.assertRaisesRegex(ValueError, 'CONSUMED_ACK|ALREADY_USED'):
            exe.start('task-a', 'attempt-a1', ['fake:shared'], 2000,
                      checkpoint_id='checkpoint-a0',
                      resume_grant_id=grant['grant_id'])
        self.assertEqual(self.supervisor.db.execute(
            "SELECT COUNT(*) FROM resource_claims WHERE state='VALID'"
        ).fetchone()[0], 0)

    def test_wrong_dependency_evidence_never_unlocks_start(self):
        producer = self.task('task-b', 'b-v3', evidence='actual-evidence')
        consumer = self.task('task-a', 'a-v1', dependencies=[{
            'task_id': 'task-b', 'version': 'b-v3',
            'evidence_ref': 'required-other-evidence'}],
            resources=['fake:shared'])
        self.gateway.register_graph(
            self.a, self.graph(tasks=[producer, consumer]), now=1000)
        exe = self.executor()
        self.now = 1010
        exe.start('task-b', 'attempt-b1', ['fake:resource-task-b'], 2000)
        self.now = 1013
        exe.complete_success('task-b', 'attempt-b1', 'f' * 64,
                             [{'evidence_ref': 'actual-evidence'}], self.now)
        outbox = self.supervisor.db.execute(
            "SELECT outbox_id,event_id FROM outbox WHERE task_id='task-b'"
        ).fetchone()
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 1014)
        self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1014)
        ack = self.gateway.acknowledge_event(
            self.a, 'task-b', 'attempt-b1', outbox['event_id'], 1015)
        self.assertEqual(ack['matched_dependencies'], 0)
        with self.assertRaisesRegex(ValueError, 'CONSUMED_ACK'):
            self.executor().start('task-a', 'attempt-a1',
                                  ['fake:shared'], 2000)

    def test_claim_requires_exact_registered_resource_set(self):
        self.gateway.register_graph(self.a, self.graph(), now=1000)
        exe = self.executor()
        for resources in ([], ['fake:wrong'],
                          ['fake:resource-task-a', 'fake:extra']):
            with self.assertRaisesRegex(ValueError, 'REGISTERED_RESOURCE'):
                exe.start('task-a', 'attempt-a1', resources, 2000)
        self.assertEqual(self.supervisor.db.execute(
            'SELECT COUNT(*) FROM resource_claims').fetchone()[0], 0)
        self.assertEqual(self.supervisor._task('task-a')['state'], 'READY')

    def test_complete_event_identity_allows_same_attempt_event_per_task(self):
        one = self.task('task-a', 'v1', resources=['fake:a'])
        two = self.task('task-b', 'v1', resources=['fake:b'])
        self.gateway.register_graph(
            self.a, self.graph(tasks=[one, two]), now=1000)
        exe = self.executor()
        outboxes = []
        for task_id, resource in (('task-a', 'fake:a'), ('task-b', 'fake:b')):
            self.now += 1
            exe.start(task_id, 'same-attempt', [resource], 2000)
            self.now += 1
            exe.complete_success(task_id, 'same-attempt', 'f' * 64,
                [{'evidence_ref': 'evidence-v1'}], self.now)
            outboxes.append(self.supervisor.db.execute(
                'SELECT * FROM outbox WHERE task_id=?', (task_id,)).fetchone())
        for row in outboxes:
            self.now += 1
            self.gateway.mark_outbox_sent(
                self.a, row['outbox_id'], 'sent-' + row['task_id'], self.now)
            self.gateway.receive_outbox(self.a, row['outbox_id'], self.now)
            self.gateway.acknowledge_event(
                self.a, row['task_id'], 'same-attempt', row['event_id'],
                self.now)
        self.assertEqual(len(list(self.supervisor.db.execute(
            'SELECT * FROM gateway_inbox'))), 2)
        self.fence.close(); self.supervisor.close()
        self.supervisor = Supervisor(self.path, lambda: self.now)
        self.gateway = GatewayKernel(
            self.supervisor, self.authority, lambda: self.now)
        self.fence = Fence(self.supervisor, self.lock_root)
        for row in outboxes:
            self.assertTrue(self.gateway.receive_outbox(
                self.a, row['outbox_id'], self.now)['duplicate'])

    def test_resume_race_rolls_back_claim_and_does_not_consume_twice(self):
        self.register_wait_graph()
        self.gateway.save_waiting_checkpoint(
            self.a, 'task-a', 'attempt-a0', 'checkpoint-a0', {},
            ['fake:shared'], 1001)
        outbox = self.start_complete_b()
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 1014)
        self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1014)
        self.gateway.acknowledge_event(
            self.a, 'task-b', 'attempt-b1', outbox['event_id'], 1015)
        grant = self.gateway.issue_resume_grant(
            self.a, 'task-a', 'checkpoint-a0', 2000, 1016)
        original = self.gateway.consume_resume_grant
        def revoke_then_consume(*args, **kwargs):
            self.gateway.revoke_dependency(
                self.a, 'task-b', 'race-revoked', 1018)
            return original(*args, **kwargs)
        self.gateway.consume_resume_grant = revoke_then_consume
        self.now = 1018
        with self.assertRaisesRegex(ValueError, 'ALREADY_USED'):
            self.executor().start(
                'task-a', 'attempt-a1', ['fake:shared'], 2000,
                checkpoint_id='checkpoint-a0',
                resume_grant_id=grant['grant_id'])
        self.assertEqual(self.supervisor._task('task-a')['state'], 'READY')
        self.assertEqual(self.supervisor.db.execute(
            "SELECT COUNT(*) FROM resource_claims WHERE state='VALID'"
        ).fetchone()[0], 0)
        self.assertEqual(self.supervisor.db.execute('''SELECT state FROM
          gateway_resume_grants WHERE grant_id=?''',
          (grant['grant_id'],)).fetchone()[0], 'REVOKED')

    def test_gateway_scan_exempts_real_dependency_wait_from_ready_timeout(self):
        self.register_wait_graph()
        self.now = 10000
        actions = self.gateway.scan(self.a, now=self.now)
        self.assertNotIn('task-a', {row['task_id'] for row in actions})
        self.assertEqual(self.supervisor._task('task-a')['state'], 'READY')
        self.assertEqual({row['task_id']: row['status'] for row in
            self.gateway.monitor(self.a)}['task-a'], 'WAITING_DEPENDENCY')

    def test_restart_converges_claim_before_grant_consume_without_started(self):
        self.register_wait_graph()
        self.gateway.save_waiting_checkpoint(
            self.a, 'task-a', 'attempt-a0', 'checkpoint-a0', {},
            ['fake:shared'], 1001)
        outbox = self.start_complete_b()
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 1014)
        self.gateway.receive_outbox(self.a, outbox['outbox_id'], 1014)
        self.gateway.acknowledge_event(
            self.a, 'task-b', 'attempt-b1', outbox['event_id'], 1015)
        grant = self.gateway.issue_resume_grant(
            self.a, 'task-a', 'checkpoint-a0', 2000, 1016)
        self.fence.close(); self.supervisor.close()
        scripts = os.path.realpath(os.path.join(
            os.path.dirname(__file__), '..', 'scripts'))
        child = r'''
import os,sys
sys.path.insert(0,sys.argv[1])
from task_supervisor import Supervisor
from task_writer_fence import Fence
from reusable_task_gateway import GatewayKernel,TestOnlyExecutor,TestTenantAuthority
clock=lambda:1020.0
s=Supervisor(sys.argv[2],clock)
a=TestTenantAuthority(b'k'*32)
g=GatewayKernel(s,a,clock)
f=Fence(s,sys.argv[3])
e=TestOnlyExecutor(g,f,a.issue('tenant-a','owner-a'),clock,
                   start_claim_hook=lambda *_:os._exit(73))
e.start('task-a','attempt-a-crash',['fake:shared'],2000,
        'checkpoint-a0',sys.argv[4])
'''
        completed = subprocess.run(
            [sys.executable, '-c', child, scripts, self.path,
             self.lock_root, grant['grant_id']], check=False)
        self.assertEqual(completed.returncode, 73)
        self.now = 1030
        self.supervisor = Supervisor(self.path, lambda: self.now)
        self.gateway = GatewayKernel(
            self.supervisor, self.authority, lambda: self.now)
        self.fence = Fence(self.supervisor, self.lock_root)
        task = self.supervisor._task('task-a')
        self.assertEqual((task['state'], task['authority_state']),
                         ('RECEIVED', 'VALID'))
        self.assertEqual(self.supervisor.db.execute('''SELECT state FROM
          gateway_resume_grants WHERE grant_id=?''',
          (grant['grant_id'],)).fetchone()[0], 'ELIGIBLE')
        recovered = self.executor().recover_incomplete_starts(now=self.now)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]['interrupted_grants'], 1)
        task = self.supervisor._task('task-a')
        self.assertEqual((task['state'], task['authority_state'],
                          task['next_action']),
                         ('READY', 'NONE', 'REISSUE_RESUME_GRANT'))
        self.assertEqual(self.supervisor.db.execute(
            "SELECT COUNT(*) FROM resource_claims WHERE task_id='task-a'"
        ).fetchone()[0], 0)
        self.assertEqual(self.supervisor.db.execute('''SELECT COUNT(*) FROM
          events WHERE task_id='task-a' AND kind='STARTED' ''').fetchone()[0], 0)
        self.assertEqual(self.supervisor.db.execute('''SELECT state FROM
          gateway_resume_grants WHERE grant_id=?''',
          (grant['grant_id'],)).fetchone()[0], 'INTERRUPTED')
        self.assertEqual(self.executor().recover_incomplete_starts(now=1031), [])

    def test_long_dependency_wait_unlocks_fresh_dispatch_clock_and_starts(self):
        self.register_wait_graph()
        self.gateway.save_waiting_checkpoint(
            self.a, 'task-a', 'attempt-a0', 'checkpoint-a0', {},
            ['fake:shared'], 1001)
        self.now = 10000
        exe = self.executor()
        exe.start('task-b', 'attempt-b-long',
                  ['fake:resource-task-b'], 20000)
        exe.complete_success('task-b', 'attempt-b-long', 'f' * 64,
                             [{'evidence_ref': 'evid-b-v3'}], 10001)
        outbox = self.supervisor.db.execute('''SELECT outbox_id,event_id FROM
          outbox WHERE task_id='task-b' ''').fetchone()
        self.gateway.mark_outbox_sent(self.a, outbox['outbox_id'], 'sent', 10002)
        self.gateway.receive_outbox(self.a, outbox['outbox_id'], 10003)
        self.gateway.acknowledge_event(
            self.a, 'task-b', 'attempt-b-long', outbox['event_id'], 10004)
        actions = self.gateway.scan(self.a, now=10005)
        self.assertNotIn('task-a', {row['task_id'] for row in actions})
        task = self.supervisor._task('task-a')
        self.assertEqual(task['updated_at'], 10004)
        self.assertEqual(task['receipt_deadline'], 10304)
        grant = self.gateway.issue_resume_grant(
            self.a, 'task-a', 'checkpoint-a0', 11000, 10006)
        self.now = 10007
        started = self.executor().start(
            'task-a', 'attempt-a-long', ['fake:shared'], 11000,
            'checkpoint-a0', grant['grant_id'])
        self.assertEqual(started['state'], 'STARTED')

    def test_projection_reports_hold_failure_and_distinct_resolver(self):
        producer = self.task('task-b', 'b-v1', board='acceptance-delivery')
        producer['owner'] = 'acceptance-owner'
        consumer = self.task('task-a', 'a-v1', dependencies=[{
            'task_id': 'task-b', 'version': 'b-v1',
            'evidence_ref': 'acceptance-proof'}])
        consumer['owner'] = 'development-owner'
        held = self.task('task-h', 'h-v1', board='operations')
        failed = self.task('task-f', 'f-v1', board='customer')
        self.gateway.register_graph(self.a, self.graph(
            tasks=[producer, consumer, held, failed]), now=1000)
        self.now = 1001
        self.executor().start('task-f', 'attempt-f1',
                              ['fake:resource-task-f'], 3000)
        self.supervisor.record(
            'task-f', 'attempt-f1', 'failed-f1', 'TERMINAL', 1002,
            'TEST_RUN', 'failure-proof', {
                'state': 'FAILURE', 'artifact_sha256': UNKNOWN,
                'writer_stopped': UNKNOWN, 'effects_reconciled': UNKNOWN,
                'next_action': 'INSPECT_FAILURE',
                'completion_evidence': []})
        self.gateway.scan(self.a, now=2000)
        value = self.gateway.projection(self.a)
        anomalies = {row['task_id']: row for row in value['anomalies']}
        self.assertEqual(anomalies['task-a']['task_responsible_party'],
                         'development-owner')
        self.assertEqual(anomalies['task-a']['resolution_responsible_party'],
                         'acceptance-owner')
        self.assertEqual(anomalies['task-a']['impact'],
                         'DEPENDENT_TASK_NOT_STARTABLE')
        self.assertEqual(anomalies['task-f']['impact'],
                         'TASK_TERMINATED_FAILURE')
        self.assertEqual(anomalies['task-f']['resolution_responsible_party'],
                         UNKNOWN)
        self.assertEqual(anomalies['task-h']['impact'],
                         'TASK_EXECUTION_HELD')
        self.assertEqual(anomalies['task-h']['evidence_ref'][0],
                         'VISIBLE_HOLD_OR_CONTROLLED_REASSIGN')
        boards = {row['board_id']: row for row in value['boards']}
        self.assertEqual(boards['operations']['health'], 'BLOCKED')
        self.assertEqual(boards['customer']['health'], 'BLOCKED')

    def test_multi_project_cross_board_partial_flow_and_tenant_projection(self):
        ops = self.task('task-a', 'brief-v1', board='operations')
        dev = self.task('task-b', 'build-v1', dependencies=[{
            'task_id': 'task-a', 'version': 'brief-v1',
            'evidence_ref': 'evidence-v1'}], board='research-development')
        self.gateway.register_graph(
            self.a, self.graph(tasks=[ops, dev]), now=1000)
        finance_only = self.task('task-z', 'ledger-v1', board='finance')
        self.gateway.register_graph(self.a, self.graph(
            suffix='z', tasks=[finance_only]), now=1000)
        customer_only = self.task('task-y', 'request-v1', board='customer')
        self.gateway.register_graph(self.b, self.graph(
            tenant='tenant-b', suffix='y', tasks=[customer_only]), now=1000)
        pa = self.gateway.projection(self.a)
        pb = self.gateway.projection(self.b)
        self.assertEqual({task['project_id'] for task in pa['tasks']},
                         {'project-a', 'project-z'})
        self.assertEqual([task['task_id'] for task in pb['tasks']], ['task-y'])
        counts = {board['board_id']: board['task_count']
                  for board in pa['boards']}
        self.assertEqual(counts['operations'], 1)
        self.assertEqual(counts['research-development'], 1)
        self.assertEqual(counts['finance'], 1)
        self.assertEqual(counts['customer'], 0)
        self.assertEqual(pa['anomalies'][0]['task_id'], 'task-b')
        self.assertEqual(pa['anomalies'][0]['project_id'], 'project-a')


if __name__ == '__main__':
    unittest.main()
