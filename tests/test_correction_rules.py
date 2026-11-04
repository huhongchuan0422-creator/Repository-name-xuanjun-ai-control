import json
import os
import tempfile
import unittest
from task_supervisor import Supervisor

class CorrectionRulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1000.
        self.s=Supervisor(os.path.join(self.tmp.name,'ledger'),clock=lambda:self.now)
        self.s.register(dict(task_id='task',parent_task_id='parent',stage='development',owner='developer',entry='WORK',checkpoint_sha256='a'*64,spec_sha256='b'*64,next_action='implement',dependencies=[],completion_conditions=['original-tests'],progress_deadline=2000,receipt_deadline=1500,started_deadline=1800,terminal_deadline=4000,handoff_deadline=3000),now=self.now)
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def test_missing_optional_sources_unknown_no_fake_anomaly(self):
        value=self.s.correction_rules(now=self.now)['observations'][0]
        self.assertIsNone(value['dependency_ack_evidence']);self.assertEqual([],value['findings'])
        self.assertEqual([],self.s.due_outbox(now=self.now))
    def test_default_five_minutes_restart_durable_three_minute_choice(self):
        self.s.correction_rules(now=self.now)
        self.assertEqual('NOT_DUE',self.s.correction_rules(now=1179,interval=180)['state'])
        self.assertNotEqual('NOT_DUE',self.s.correction_rules(now=1180,interval=180)['state'])
        self.assertEqual('NOT_DUE',self.s.correction_rules(now=1479)['state'])
        self.assertNotEqual('NOT_DUE',self.s.correction_rules(now=1480)['state'])
    def test_interval_does_not_accept_bool_or_other_values(self):
        for value in (True,60,0,301):
            with self.assertRaises(ValueError):self.s.correction_rules(interval=value)
    def test_no_commit_does_not_mean_no_work(self):
        self.s.claim('task','attempt','developer','WORK','run','session','lease',1,1,now=self.now)
        self.s.record('task','attempt','received','RECEIVED',self.now)
        self.s.record('task','attempt','started','STARTED',self.now)
        self.s.record('task','attempt','ci','PROGRESS',self.now,evidence_kind='TEST_RUN',evidence_ref='ci:existing/42')
        value=self.s.correction_rules()['observations'][0]
        self.assertEqual('ci',value['progress_evidence']['event_id']);self.assertEqual([],value['findings'])
    def test_unresolved_operations_deduplicate_without_changing_task(self):
        # Ordinary persisted unresolved-state fixture, not an executor call.
        self.s.db.execute('INSERT INTO writer_operations VALUES (?,?,?,?,?,?,?,?,?,?,?)',('op','task','UNKNOWN','op-event','fake:x','a'*64,'b'*64,'{}','UNKNOWN',1000,1000));self.s.db.commit()
        before=self.s._task('task')
        one=self.s.correction_rules()['observations'][0]['findings'][0]
        self.now+=300
        two=self.s.correction_rules()['observations'][0]['findings'][0]
        self.assertEqual(one['event_id'],two['event_id']);self.assertTrue(two['duplicate'])
        self.assertEqual([],self.s.due_outbox(now=self.now))
        self.assertEqual(1,self.s.db.execute('SELECT count(*) FROM outbox').fetchone()[0]);self.assertEqual(before,self.s._task('task'))
        self.assertEqual('RECONCILE_EXISTING_OPERATIONS_NO_REPLAY',one['action'])
    def test_display_projection_does_not_mutate_registered_stage(self):
        before=self.s._task('task')
        self.s.correction_rules()
        self.assertEqual(before,self.s._task('task'))

if __name__=='__main__':unittest.main()

class ResumeTests(unittest.TestCase):
    setUp=CorrectionRulesTests.setUp
    tearDown=CorrectionRulesTests.tearDown
    def prepare(self):
        self.s.claim_writer('task','attempt','developer','WORK',{'caller_id':'writer','run_id':'run','session_id':'session','gateway_id':'gateway'},'lease','fixed-provider',['fake:source'],3000)
        self.s.record('task','attempt','received','RECEIVED',self.now)
        self.s.record('task','attempt','started','STARTED',self.now)
        self.now=1601
        action=self.s.scan(now=self.now)[0]
        return self.s.db.execute('SELECT outbox_id FROM outbox WHERE event_id=?',(action['outbox_event_id'],)).fetchone()[0]
    def adapter(self,state='SENT'):
        import hashlib
        from task_supervisor import canonical
        class LocalFixtureAdapter:
            calls=0
            def admit(this,packet):return {'approved':True,'packet_sha256':hashlib.sha256(canonical(packet).encode()).hexdigest(),'source_ref':'fixture:host-existing-admission'}
            def request_resume(this,packet):
                this.calls+=1
                return {'state':state,'outbox_id':packet['outbox_id'],'source_ref':'fixture:original-owner-channel'}
        return LocalFixtureAdapter()
    def test_unconfigured_provider_does_not_consume_attempt(self):
        oid=self.prepare()
        self.assertFalse(self.s.resume_existing_owner(oid)['dispatch_performed'])
        self.assertEqual(0,self.s.correction_delivery_status(oid)['attempts'])
    def test_sent_is_not_ack_then_real_progress_ack_no_duplicate(self):
        oid=self.prepare();adapter=self.adapter()
        first=self.s.resume_existing_owner(oid,adapter)
        self.assertEqual('SENT_ACK_PENDING',first['state'])
        self.assertFalse(self.s.resume_existing_owner(oid,adapter)['dispatch_performed']);self.assertEqual(1,adapter.calls)
        self.now+=1
        self.s.record('task','attempt','resumed','PROGRESS',self.now,'TEST_RUN','fixture:ci-run',{'resumed_outbox_id':oid})
        self.assertEqual('ACK_OBSERVED',self.s.correction_delivery_status(oid)['state'])
        self.assertNotEqual('SUCCESS',self.s._task('task')['state'])
    def test_unknown_delivery_is_not_replayed_by_any_due_poll(self):
        oid=self.prepare();adapter=self.adapter('UNKNOWN')
        self.assertEqual('HOLD_DELIVERY_UNKNOWN_NO_RETRY',self.s.resume_existing_owner(oid,adapter)['state'])
        self.assertFalse(self.s.resume_existing_owner(oid,adapter)['dispatch_performed'])
        self.assertEqual(1,adapter.calls);self.assertEqual([],self.s.due_outbox(now=2000))
    def test_revoked_writer_cannot_resume(self):
        oid=self.prepare();adapter=self.adapter()
        self.s.db.execute("UPDATE tasks SET authority_state='REVOKING' WHERE task_id='task'");self.s.db.commit()
        with self.assertRaisesRegex(ValueError,'HOLD_CURRENT_SAME_WRITER'):self.s.resume_existing_owner(oid,adapter)
        self.assertEqual(0,adapter.calls)
    def test_wrong_host_admission_cannot_resume(self):
        oid=self.prepare();adapter=self.adapter();adapter.admit=lambda packet:{'approved':False}
        with self.assertRaisesRegex(ValueError,'HOLD_HOST_PROVIDER'):self.s.resume_existing_owner(oid,adapter)
        self.assertEqual(0,adapter.calls)

    def test_unresolved_effects_prevent_resume(self):
        oid=self.prepare();adapter=self.adapter()
        self.s.db.execute('INSERT INTO writer_operations VALUES (?,?,?,?,?,?,?,?,?,?,?)',('op','task','attempt','operation','fake:source','a'*64,'b'*64,'{}','UNKNOWN',1000,1000));self.s.db.commit()
        with self.assertRaisesRegex(ValueError,'HOLD_UNRESOLVED'):self.s.resume_existing_owner(oid,adapter)
        self.assertEqual(0,adapter.calls)
    def test_old_generation_cannot_resume_after_real_progress(self):
        oid=self.prepare();adapter=self.adapter()
        self.s.record('task','attempt','ci-progress','PROGRESS',self.now,'TEST_RUN','fixture:ci-existing')
        with self.assertRaisesRegex(ValueError,'HOLD_CURRENT_SAME_WRITER'):self.s.resume_existing_owner(oid,adapter)
        self.assertEqual(0,adapter.calls)
    def test_missing_original_claims_cannot_resume(self):
        oid=self.prepare();adapter=self.adapter()
        self.s.db.execute("DELETE FROM resource_claims WHERE task_id='task'");self.s.db.commit()
        with self.assertRaisesRegex(ValueError,'HOLD_ORIGINAL_WRITER_CLAIMS'):self.s.resume_existing_owner(oid,adapter)
        self.assertEqual(0,adapter.calls)

    def test_generic_result_cannot_erase_unknown_or_mark_it_sent(self):
        oid=self.prepare();adapter=self.adapter('UNKNOWN')
        self.s.resume_existing_owner(oid,adapter)
        for delivered in (False,True):
            with self.assertRaisesRegex(ValueError,'CORRECTION_OUTBOX_REQUIRES'):self.s.outbox_result(oid,delivered,error='offline')
        self.assertEqual([],self.s.due_outbox(now=2000))
        self.assertEqual('HOLD_DELIVERY_UNKNOWN_NO_RETRY',self.s.correction_delivery_status(oid)['state'])
    def test_generic_result_cannot_deliver_rule_proposal(self):
        self.s.db.execute('INSERT INTO writer_operations VALUES (?,?,?,?,?,?,?,?,?,?,?)',('op','task','UNKNOWN','op-event','fake:x','a'*64,'b'*64,'{}','UNKNOWN',1000,1000));self.s.db.commit()
        self.s.correction_rules()
        oid=self.s.db.execute('SELECT outbox_id FROM outbox').fetchone()[0]
        with self.assertRaisesRegex(ValueError,'CORRECTION_OUTBOX_REQUIRES'):self.s.outbox_result(oid,True)
    def test_normal_admission_time_elapsed_requires_current_authority(self):
        oid=self.prepare();adapter=self.adapter();original=adapter.admit
        def admit(packet):
            value=original(packet);self.now=3000.;return value
        adapter.admit=admit
        with self.assertRaisesRegex(ValueError,'WRITER_TICKET_EXPIRED'):self.s.resume_existing_owner(oid,adapter)
        self.assertEqual(0,adapter.calls);self.assertEqual(0,self.s.correction_delivery_status(oid)['attempts'])
    def test_recorded_trusted_time_rejects_clock_rollback(self):
        oid=self.prepare();adapter=self.adapter()
        self.s.db.execute("UPDATE tasks SET last_trusted_time=1700 WHERE task_id='task'");self.s.db.commit()
        with self.assertRaisesRegex(ValueError,'CLOCK_ROLLBACK_HOLD'):self.s.resume_existing_owner(oid,adapter)
        self.assertEqual(0,adapter.calls);self.assertEqual(0,self.s.correction_delivery_status(oid)['attempts'])
    def test_progress_during_request_before_sent_return_is_real_ack(self):
        oid=self.prepare();adapter=self.adapter();original=adapter.request_resume
        def request(packet):
            self.now+=1
            self.s.record('task','attempt','during-request','PROGRESS',self.now,'TEST_RUN','fixture:ci-run',{'resumed_outbox_id':oid})
            self.now+=1
            return original(packet)
        adapter.request_resume=request
        result=self.s.resume_existing_owner(oid,adapter)
        self.assertEqual('ACK_OBSERVED',result['state']);self.assertEqual('during-request',result['ack']['event_id'])
