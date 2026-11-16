import copy, unittest
from datetime import datetime, timezone
from task_delivery_ledger.core import canonical, digest
from task_delivery_ledger.handoffs import SNAPSHOT_FIELDS
from task_delivery_ledger.handoffs import project_handoffs

NOW=datetime(2026,11,16,12,0,tzinfo=timezone.utc)
def scenario():
    snap={k:'ref-'+k for k in SNAPSHOT_FIELDS}
    snap.update(commit='a'*40,tree='b'*40,artifact_sha256='c'*64,deploy_refs=['deploy-ref'],pending_operations=['none-ref'],expires_at='2099-01-01T00:00:00Z')
    included=list(SNAPSHOT_FIELDS); snapshot_digest=digest(canonical(snap)); timestamp='2026-11-16T10:00:00+08:00'
    def event(eid,kind,party,cause='NONE',**extra):
        data={'handoff_id':'h1','handoff_version':1,'snapshot_digest':snapshot_digest,'actor_ref':'actor-'+party,'role_id':'role-'+party,'session_ref':'session-'+party,'identity_evidence_ref':'identity-'+party,'permission_evidence_ref':'permission-'+party,'permission_expires_at':'2099-01-01T00:00:00Z'}
        if kind=='handoff_propose':data.update(snapshot_data=snap,scope_included=included,scope_excluded=[],scope_authorization_ref='UNKNOWN')
        else:data['proposal_event_id']='p1'
        data.update(extra)
        return {'event_id':eid,'task_id':'t1','attempt_id':'a1','type':kind,'occurred_at':timestamp,'observed_at':timestamp,'source':'source-ref','evidence':'evidence-ref','validity':'VERIFIED_NOW','causation':cause,'data':data}
    return [event('p1','handoff_propose','out'),event('n1','handoff_nominate','out','p1',target_ref='role-super'),event('s1','handoff_send_accepted','out','p1'),event('r1','handoff_received','in','p1'),event('a1','handoff_aligned','in','r1',received_event_id='r1',actual_checks=included,unknown_items=[]),event('b1','handoff_supervision_start','super','n1'),event('v1','handoff_verified','super','b1',alignment_event_id='a1',supervision_start_event_id='b1',actual_checks=included,unknown_items=[])]
def view(events): return project_handoffs(events,verifier=lambda e:True,now=NOW)['t1:h1']
class HandoffAttemptDelta(unittest.TestCase):
    def test_complete_chain_cannot_mix_attempts(self):
        events=scenario();self.assertEqual(view(events)['handoff_status'],'交接完成(范围)')
        for index in (1,3,4,5,6):
            wrong=copy.deepcopy(events);wrong[index]['attempt_id']='a2'
            self.assertNotEqual(view(wrong)['handoff_status'],'交接完成(范围)')
    def test_old_attempt_negative_does_not_poison_current(self):
        events=scenario();old=copy.deepcopy(events[-1]);old['event_id']='old-reject';old['attempt_id']='a2';old['type']='handoff_rejected'
        self.assertEqual(view(events+[old])['handoff_status'],'交接完成(范围)')
if __name__=='__main__':unittest.main()
