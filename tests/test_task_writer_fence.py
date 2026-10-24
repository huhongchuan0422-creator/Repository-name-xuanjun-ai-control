from __future__ import print_function

import inspect
import json
import os
import sqlite3
import tempfile
import threading
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from task_supervisor import Supervisor, UNKNOWN
from task_writer_fence import (
    Fence, FakeTransactionalSink, LocalActionLocks, OfflineGitCAS,
    SourceResourceAdapter, production_fencing_verdict, reconcile_unknown,
)


class WriterFenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, 'ledger.sqlite')
        self.lock_root = os.path.join(self.directory.name, 'locks')
        self.now = 1000.0
        self.s = Supervisor(self.path, lambda: self.now)
        self.fence = Fence(self.s, self.lock_root)
        self.register('t1')

    def tearDown(self):
        try:
            self.fence.close()
        except Exception:
            pass
        try:
            self.s.close()
        except Exception:
            pass
        self.directory.cleanup()

    def register(self, task):
        self.s.register(dict(
            task_id=task, parent_task_id='parent', stage='dev',
            owner='developer', entry='WORK',
            checkpoint_sha256='a' * 64, spec_sha256='b' * 64,
            next_action='implement', dependencies=[],
            completion_conditions=['tests'],
            progress_deadline=1900, receipt_deadline=1100,
            started_deadline=1200, terminal_deadline=3000,
            handoff_deadline=1800), now=self.now)

    def caller(self, caller_id='writer-a', run='run1', session='session1',
               gateway='gateway1'):
        return {'caller_id': caller_id, 'run_id': run,
                'session_id': session, 'gateway_id': gateway}

    def claim(self, task='t1', attempt='a1', resources=None, caller=None):
        return self.fence.claim(
            task, attempt, 'developer', 'WORK', caller or self.caller(),
            'lease-' + attempt, resources or ['fake:account/a'],
            valid_until=1700)

    def op(self, opid='op1', event='event1', resource='fake:account/a'):
        return {
            'operation_id': opid,
            'event_id': event,
            'resource_key': resource,
            'operation_kind': 'FAKE_TXN',
            'expected_before': {'value': 'old'},
            'requested_after': {'value': 'new'},
            'request_sha256': 'c' * 64,
            'operation_marker': 'xuanjun-op:' + opid,
        }

    def final_receipt(self, operation, outcome='CONFIRMED',
                      before=None, after=None, kind=None):
        before = operation['expected_before'] if before is None else before
        if after is None:
            after = (operation['requested_after'] if outcome == 'CONFIRMED'
                     else operation['expected_before'])
        if kind is None:
            kind = 'FAKE_TXN' if outcome == 'CONFIRMED' else 'READBACK'
        return FakeTransactionalSink.receipt(
            operation, outcome, before, after, kind=kind)

    def revoke_to_reconciled(self):
        controller = {'role': 'REVOCATION_CONTROLLER', 'caller_id': 'owner'}
        self.fence.begin_revocation('t1', controller)
        self.fence.drain('t1', controller, timeout=0.2)
        self.fence.invalidate_source_resources('t1', 'invalidate')
        return self.s.complete_revocation('t1')

    def ack(self, result, **overrides):
        value = {
            'schema': 1,
            'task_id': 't1',
            'old_attempt_id': 'a1',
            'new_attempt_id': 'a2',
            'new_owner': 'developer',
            'new_entry': 'WORK',
            'new_caller_id': 'writer-b',
            'new_run_id': 'run2',
            'new_session_id': 'session2',
            'new_lease_id': 'lease-a2',
            'new_gateway_id': 'gateway2',
            'resource_scope_digest': result['resource_scope_digest'],
            'coverage_digest': result['coverage_digest'],
            'spec_sha256': 'b' * 64,
            'checkpoint_sha256': 'a' * 64,
        }
        value.update(overrides)
        return value

    def test_store_allocates_exact_max_plus_one_and_binds_caller(self):
        ticket = self.claim()
        self.assertEqual((ticket['fence'], ticket['epoch']), (1, 1))
        self.assertEqual(ticket['assigned_caller_id'], 'writer-a')
        self.assertEqual(self.s._task('t1')['authority_state'], 'VALID')

    def test_two_connections_claim_single_winner(self):
        self.fence.close(); self.s.close()
        barrier = threading.Barrier(2)
        results = []
        def worker(name):
            db = Supervisor(self.path, lambda: 1000.0)
            root = os.path.join(self.directory.name, 'locks-' + name)
            fence = Fence(db, root)
            try:
                barrier.wait()
                try:
                    fence.claim('t1', 'a-' + name, 'developer', 'WORK',
                                self.caller(caller_id=name),
                                'lease-' + name, ['fake:account/a'], 1700)
                    results.append('won')
                except ValueError:
                    results.append('lost')
            finally:
                fence.close(); db.close()
        one=threading.Thread(target=worker,args=('one',))
        two=threading.Thread(target=worker,args=('two',))
        one.start();two.start();one.join(3);two.join(3)
        self.assertEqual(sorted(results), ['lost','won'])
        self.s=Supervisor(self.path,lambda:self.now)
        self.fence=Fence(self.s,self.lock_root)

    def test_cross_task_same_resource_conflicts(self):
        self.claim()
        self.register('t2')
        with self.assertRaisesRegex(ValueError, 'RESOURCE_SCOPE_CONFLICT'):
            self.claim('t2', 'b1')

    def test_multi_resource_claim_rolls_back_atomically(self):
        self.claim(resources=['fake:account/a'])
        self.register('t2')
        with self.assertRaisesRegex(ValueError, 'RESOURCE_SCOPE_CONFLICT'):
            self.claim('t2', 'b1',
                       resources=['fake:account/b','fake:account/a'])
        self.assertIsNone(self.s.db.execute(
            "SELECT 1 FROM resource_claims WHERE resource_key='fake:account/b'"
        ).fetchone())

    def test_resource_alias_whitespace_control_and_dot_paths_rejected(self):
        adapter = SourceResourceAdapter()
        for bad in ('fake: account/a','fake:account/../a',
                    'fake:account//a','fake:account/./a','fake:account/\x00a'):
            with self.assertRaises(ValueError):
                adapter.normalize(bad)

    def test_commit_api_has_no_per_call_lock_root_or_time_override(self):
        params = inspect.signature(self.fence.commit_lease).parameters
        self.assertNotIn('lock_root', params)
        ticket = self.claim()
        with self.assertRaises(TypeError):
            self.s.prepare_operation(ticket, self.caller(), self.op(),
                                     now=999)

    def test_lock_root_mode_symlink_and_path_swap_fail_closed(self):
        self.assertEqual(os.stat(self.lock_root).st_mode & 0o777, 0o700)
        original = self.lock_root + '.old'
        os.rename(self.lock_root, original)
        os.mkdir(self.lock_root, 0o700)
        with self.assertRaisesRegex(ValueError, 'ACTION_LOCK_ROOT_CHANGED'):
            self.fence.locks.acquire(['fake:account/a'])
        self.fence.close()
        os.rmdir(self.lock_root)
        os.rename(original, self.lock_root)
        link = os.path.join(self.directory.name, 'link-root')
        os.symlink(self.lock_root, link)
        with self.assertRaises(ValueError):
            LocalActionLocks(link)
        self.fence = Fence(self.s, self.lock_root)

    def test_stolen_ticket_caller_only_change_is_rejected(self):
        ticket = self.claim()
        stolen = self.caller(caller_id='thief')
        with self.assertRaisesRegex(ValueError, 'CALLER_CONTEXT_MISMATCH'):
            self.fence.prepare(ticket, stolen, self.op())

    def test_clock_rollback_and_expiry_use_supervisor_clock_only(self):
        ticket = self.claim()
        self.now = 1001.0
        self.fence.prepare(ticket, self.caller(), self.op())
        self.now = 999.0
        with self.assertRaisesRegex(ValueError, 'CLOCK_ROLLBACK_HOLD'):
            self.fence.prepare(ticket, self.caller(),
                               self.op('op2','event2'))
        self.now = 1700.0
        with self.assertRaisesRegex(ValueError, 'WRITER_TICKET_EXPIRED'):
            self.fence.prepare(ticket, self.caller(),
                               self.op('op3','event3'))

    def test_operation_same_bytes_idempotent_different_bytes_conflict(self):
        ticket = self.claim()
        first = self.fence.prepare(ticket, self.caller(), self.op())
        second = self.fence.prepare(ticket, self.caller(), self.op())
        self.assertFalse(first['duplicate']); self.assertTrue(second['duplicate'])
        changed = self.op()
        changed['request_sha256'] = 'd' * 64
        with self.assertRaisesRegex(ValueError, 'OPERATION_IDENTITY_CONFLICT'):
            self.fence.prepare(ticket, self.caller(), changed)

    def test_duplicate_operation_concurrent_has_one_row(self):
        ticket = self.claim()
        self.fence.close(); self.s.close()
        barrier=threading.Barrier(2); results=[]
        def worker():
            db=Supervisor(self.path,lambda:1000.0)
            fence=Fence(db,os.path.join(self.directory.name,'shared-locks'))
            try:
                barrier.wait()
                try:
                    result=fence.prepare(ticket,self.caller(),self.op())
                    results.append('dup' if result['duplicate'] else 'new')
                except Exception as exc:
                    results.append(type(exc).__name__)
            finally:
                fence.close();db.close()
        one=threading.Thread(target=worker);two=threading.Thread(target=worker)
        one.start();two.start();one.join(3);two.join(3)
        self.assertEqual(sorted(results),['dup','new'])
        self.s=Supervisor(self.path,lambda:self.now)
        self.fence=Fence(self.s,self.lock_root)
        self.assertEqual(self.s.db.execute(
            "SELECT count(*) FROM writer_operations").fetchone()[0],1)

    def test_fake_transaction_sink_produces_attributable_receipt(self):
        ticket = self.claim()
        operation = self.op()
        self.fence.prepare(ticket, self.caller(), operation)
        sink = FakeTransactionalSink()
        with self.fence.commit_lease(ticket,self.caller(),'op1') as lease:
            receipt=sink.apply(operation)
            lease.confirmed(receipt)
        self.assertEqual(self.s.db.execute(
            "SELECT state FROM writer_operations WHERE operation_id='op1'"
        ).fetchone()[0],'CONFIRMED')

    def test_confirm_rejects_missing_fields_wrong_marker_and_content_match(self):
        ticket=self.claim(); operation=self.op()
        self.fence.prepare(ticket,self.caller(),operation)
        self.s.begin_dispatch(ticket,self.caller(),'op1')
        for bad in (
            {'outcome':'CONFIRMED'},
            self.final_receipt(operation,after={'value':'same'},
                               kind='FAKE_TXN'),
            dict(self.final_receipt(operation),operation_marker='other'),
        ):
            with self.assertRaises(ValueError):
                self.s.confirm_operation(ticket,self.caller(),'op1',bad)
        self.assertIsNone(self.s.db.execute(
            "SELECT 1 FROM writer_receipts WHERE operation_id='op1'"
        ).fetchone())

    def test_offline_git_cas_binds_branch_head_tree_blob_and_marker(self):
        operation=OfflineGitCAS.operation(
            'git-op','git-event','git:repo/feature-x','repo','feature-x',
            'head0','tree0','blob0','tree1','blob1','marker-1')
        good={'repo':'repo','branch':'feature-x','commit':'commit1',
              'parent':'head0','tree':'tree1','blob':'blob1','marker':'marker-1'}
        self.assertEqual(
            OfflineGitCAS.validate(operation,good)['outcome'],'CONFIRMED')
        for field,value in (('parent','other'),('tree','other'),
                            ('blob','other'),('marker','other'),
                            ('branch','other')):
            bad=dict(good);bad[field]=value
            self.assertEqual(
                OfflineGitCAS.validate(operation,bad)['outcome'],'CONFLICT')

    def test_reconcile_unknown_without_redispatch_and_one_final_receipt(self):
        ticket=self.claim();operation=self.op()
        self.fence.prepare(ticket,self.caller(),operation)
        with self.fence.commit_lease(ticket,self.caller(),'op1') as lease:
            lease.unknown({'transport':'lost'})
        ctx={'role':'RECONCILER','evidence_id':'readback-1',
             'caller_id':'reader'}
        receipt=self.final_receipt(operation,'NOT_APPLIED')
        result=reconcile_unknown(
            self.s,'op1',ctx,'NOT_APPLIED',{'readback':'old'},receipt)
        self.assertEqual(result['state'],'NOT_APPLIED')
        self.assertEqual(self.s.db.execute(
            "SELECT count(*) FROM writer_receipts WHERE operation_id='op1'"
        ).fetchone()[0],1)
        with self.assertRaises(ValueError):
            self.s.begin_dispatch(ticket,self.caller(),'op1')

    def test_unknown_observations_append_without_consuming_receipt(self):
        ticket=self.claim();operation=self.op()
        self.fence.prepare(ticket,self.caller(),operation)
        self.s.begin_dispatch(ticket,self.caller(),'op1')
        for index in (1,2):
            ctx={'role':'RECONCILER','evidence_id':'unknown-%d'%index,
                 'caller_id':'reader'}
            self.s.reconcile_operation(
                'op1',ctx,'UNKNOWN',{'probe':index})
        self.assertIsNone(self.s.db.execute(
            "SELECT 1 FROM writer_receipts WHERE operation_id='op1'"
        ).fetchone())
        self.assertEqual(self.s.db.execute(
            "SELECT count(*) FROM writer_reconcile_evidence WHERE operation_id='op1'"
        ).fetchone()[0],2)

    def test_prepared_can_only_reconcile_not_applied(self):
        ticket=self.claim();operation=self.op()
        self.fence.prepare(ticket,self.caller(),operation)
        self.fence.begin_revocation(
            't1',{'role':'REVOCATION_CONTROLLER','caller_id':'owner'})
        ctx={'role':'RECONCILER','evidence_id':'prepared','caller_id':'reader'}
        with self.assertRaisesRegex(
                ValueError,'UNDISPATCHED_OPERATION_ONLY_NOT_APPLIED'):
            self.s.reconcile_operation(
                'op1',ctx,'CONFIRMED',{'probe':'no'},
                self.final_receipt(operation))
        self.s.reconcile_operation(
            'op1',ctx,'NOT_APPLIED',{'probe':'never-dispatched'},
            self.final_receipt(operation,'NOT_APPLIED'))
        self.assertEqual(self.s.unresolved_operations('t1'),[])

    def test_revoke_waits_shared_lease_times_out_then_resumes_same_generation(self):
        ticket=self.claim();operation=self.op()
        self.fence.prepare(ticket,self.caller(),operation)
        entered=threading.Event();release=threading.Event();errors=[]
        def old_writer():
            db=Supervisor(self.path,lambda:self.now)
            fence=Fence(db,self.lock_root)
            try:
                with fence.commit_lease(ticket,self.caller(),'op1') as lease:
                    entered.set();release.wait(2)
                    lease.unknown({'transport':'uncertain'})
            except Exception as exc:
                errors.append(str(exc))
            finally:
                fence.close();db.close()
        thread=threading.Thread(target=old_writer);thread.start()
        self.assertTrue(entered.wait(1))
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'owner'}
        with self.assertRaisesRegex(ValueError,'REVOCATION_NOT_COMPLETED'):
            self.fence.drain('t1',controller,timeout=0.05)
        self.assertEqual(self.s._task('t1')['authority_state'],'REVOKING')
        release.set();thread.join(2);self.assertEqual(errors,[])
        drain=self.fence.drain('t1',controller,timeout=0.2)
        self.assertEqual(drain['outcome'],'DRAINED')
        self.assertEqual(self.s.db.execute(
            "SELECT count(*) FROM revocation_drains WHERE task_id='t1'"
        ).fetchone()[0],1)
        self.assertEqual(self.s._task('t1')['max_epoch'],1)

    def test_complete_revocation_cannot_bypass_drain_or_unknown(self):
        ticket=self.claim();operation=self.op()
        self.fence.prepare(ticket,self.caller(),operation)
        self.s.begin_dispatch(ticket,self.caller(),'op1')
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'owner'}
        self.fence.begin_revocation('t1',controller)
        with self.assertRaisesRegex(ValueError,'REVOCATION_NOT_COMPLETED'):
            self.s.complete_revocation('t1')
        self.s.reconcile_operation(
            'op1',{'role':'RECONCILER','evidence_id':'rb','caller_id':'reader'},
            'NOT_APPLIED',{'readback':'old'},
            self.final_receipt(operation,'NOT_APPLIED'))
        with self.assertRaisesRegex(ValueError,'LOCAL_DRAIN_REQUIRED'):
            self.s.complete_revocation('t1')
        self.fence.drain('t1',controller,0.2)
        self.fence.invalidate_source_resources('t1','inv')
        self.assertEqual(self.s.complete_revocation('t1')['state'],'REVOKED')

    def test_invalidation_receipt_must_bind_old_identity_spec_scope_ticket(self):
        self.claim()
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'owner'}
        self.fence.begin_revocation('t1',controller)
        self.fence.drain('t1',controller,0.2)
        receipt=self.fence.adapter.invalidation_receipt(
            self.s,'t1','fake:account/a',self.fence.locks.provider_id,'e1')
        for field in ('old_attempt_id','old_lease_id','old_fence','old_epoch',
                      'ticket_sha256','spec_sha256','resource_scope_digest',
                      'resource_key'):
            bad=dict(receipt)
            bad[field]='bad' if field not in ('old_fence','old_epoch') else 999
            with self.assertRaises(ValueError):
                self.s.record_resource_invalidation('t1',bad)
        self.assertFalse(
            self.s.record_resource_invalidation('t1',receipt)['duplicate'])
        self.assertTrue(
            self.s.record_resource_invalidation('t1',receipt)['duplicate'])

    def test_ack_binds_scope_and_coverage_and_is_append_once(self):
        self.claim();result=self.revoke_to_reconciled()
        ack=self.ack(result)
        first=self.s.record_receiver_ack('t1',ack)
        second=self.s.record_receiver_ack('t1',ack)
        self.assertFalse(first['duplicate']);self.assertTrue(second['duplicate'])
        bad=dict(ack);bad['new_caller_id']='other'
        with self.assertRaisesRegex(ValueError,'RECEIVER_ACK_CONFLICT'):
            self.s.record_receiver_ack('t1',bad)

    def test_gapless_takeover_rejects_old_ticket(self):
        old=self.claim();result=self.revoke_to_reconciled()
        ack=self.ack(result)
        self.s.record_receiver_ack('t1',ack)
        new=self.s.takeover_claim('t1',ack,1800)
        self.assertEqual((new['fence'],new['epoch']),(2,2))
        self.assertEqual(new['assigned_caller_id'],'writer-b')
        with self.assertRaises(ValueError):
            self.fence.prepare(old,self.caller(),self.op('old','old-event'))

    def test_revoking_rejects_new_intent_and_effect(self):
        ticket=self.claim()
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'owner'}
        self.fence.begin_revocation('t1',controller)
        with self.assertRaisesRegex(ValueError,'WRITER_AUTHORITY_NOT_VALID'):
            self.fence.prepare(ticket,self.caller(),self.op())
        self.assertEqual(self.s.db.execute(
            "SELECT count(*) FROM writer_operations").fetchone()[0],0)

    def test_unknown_full_source_recovery_persists_inventory_then_takeover(self):
        ticket=self.claim()
        self.s.db.execute("DELETE FROM resource_claims WHERE task_id='t1'")
        self.s.db.execute("""UPDATE tasks SET authority_state=?,state='HOLD',
          resource_scope_json='[]',resource_scope_digest=? WHERE task_id='t1'""",
          (UNKNOWN,UNKNOWN))
        self.s.db.commit()
        inventory_controller={
            'role':'SOURCE_INVENTORY_CONTROLLER','caller_id':'inventory'}
        recovered=self.fence.recover_unknown(
            't1',inventory_controller,['fake:account/a'],'inventory-1')
        self.assertEqual(recovered['state'],'REVOKING')
        self.assertEqual(self.s.db.execute(
            "SELECT count(*) FROM authority_recovery_evidence WHERE task_id='t1'"
        ).fetchone()[0],1)
        controller={'role':'REVOCATION_CONTROLLER','caller_id':'owner'}
        self.fence.drain('t1',controller,0.2)
        self.fence.invalidate_source_resources('t1','recover-inv')
        result=self.s.complete_revocation('t1')
        ack=self.ack(result)
        self.s.record_receiver_ack('t1',ack)
        new=self.s.takeover_claim('t1',ack,1800)
        self.assertEqual(new['epoch'],2)
        self.assertNotEqual(ticket['resource_scope_digest'],UNKNOWN)

    def test_unknown_recovery_insufficient_or_conflicting_inventory_holds(self):
        self.claim()
        self.s.db.execute("DELETE FROM resource_claims WHERE task_id='t1'")
        self.s.db.execute("""UPDATE tasks SET authority_state=?,state='HOLD',
          resource_scope_json='[]',resource_scope_digest=? WHERE task_id='t1'""",
          (UNKNOWN,UNKNOWN));self.s.db.commit()
        controller={'role':'SOURCE_INVENTORY_CONTROLLER','caller_id':'inventory'}
        with self.assertRaises(ValueError):
            self.fence.recover_unknown('t1',controller,[],'missing')
        self.assertEqual(self.s._task('t1')['authority_state'],UNKNOWN)

    def test_local_only_production_verdict_is_fixed_hold_and_unknown_is_hold(self):
        result=production_fencing_verdict()
        self.assertEqual(result['production_fencing'],'HOLD')
        self.assertEqual(result['production_inventory'],'INCOMPLETE')
        unknown=production_fencing_verdict('UNKNOWN')
        self.assertEqual(unknown['production_fencing'],'HOLD')
        self.assertIn('UNKNOWN_OR_UNADMITTED_CAPABILITY',unknown['reasons'])


if __name__ == '__main__':
    unittest.main()
