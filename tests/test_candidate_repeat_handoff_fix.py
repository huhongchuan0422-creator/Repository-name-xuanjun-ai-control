"""Two independent original handoffs: select by original evidence, not recency."""
import json
import test_candidate_lifecycle_readback_delta as fixture

class RepeatedHandoff(fixture.CandidateLifecycleReadback):
    def two(self):
        cid=self.make_candidate();self.handoff(cid);first=self.adapter.event
        self.handoff(cid);second=self.adapter.event
        self.assertNotEqual(first,second)
        return cid,first,second
    def test_two_valid_cycles_accept_once_and_duplicate(self):
        cid,first,second=self.two()
        # The trusted backup authority recognizes only the second cycle;
        # lexical order is irrelevant and the other may be examined first.
        db=self.h.control.db
        row=db.execute("SELECT payload_json FROM events WHERE event_id=?",('handoff-host:'+second,)).fetchone()
        current=json.loads(row[0])['backup_cycle_id']
        original=self.adapter.assess_backup
        def backup(binding):
            result=original(binding)
            if binding['backup_cycle_id']!=current:return {'state':'UNKNOWN','missing':[],'cycle_at':None}
            return result
        self.adapter.assess_backup=backup
        self.assertEqual(self.call(cid)['state'],'ACCEPTED')
        self.assertTrue(self.call(cid)['duplicate'])
        anchor=db.execute("SELECT detail_json FROM model_audit WHERE action='CANDIDATE_EVIDENCE_BOUND' AND target_id=?",(cid,)).fetchone()
        self.assertEqual(json.loads(anchor[0])['handoff_event_id'],second)
    def test_two_current_valid_cycles_are_both_sufficient(self):
        cid,first,second=self.two()
        self.assertEqual(self.call(cid)['state'],'ACCEPTED')
        self.assertTrue(self.call(cid)['duplicate'])
    def test_unknown_backup_for_both_cycles_holds(self):
        cid,first,second=self.two()
        self.adapter.assess_backup=lambda binding: {'state':'UNKNOWN','missing':[],'cycle_at':None}
        with self.assertRaisesRegex(ValueError,'CANDIDATE_BACKUP_COMPLETE_REQUIRED'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
    def test_tampered_cycles_cannot_supply_evidence(self):
        cid,first,second=self.two()
        db=self.h.control.db
        for event in (first,second):
            db.execute("DELETE FROM events WHERE event_id=?",('handoff-contract:'+event,))
        db.commit()
        with self.assertRaisesRegex(ValueError,'CANDIDATE_HANDOFF_RECEIPTS_REQUIRED'):self.call(cid)
        self.assertEqual(self.h.supervisor._task('demo-b')['state'],'STARTED')
