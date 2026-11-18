"""List visibility must follow existing trusted host task/attempt mapping."""
import json
from test_handoff_alert_original_delivery import OriginalAlertDelivery
from task_supervisor import canonical

class ScopeHost:
    def __init__(self,bindings):self.bindings=set(bindings)
    def resolve_destination(self,packet):
        if (packet['tenant_id'],packet['task_id'],packet['attempt_id']) not in self.bindings:return None
        return 'synthetic-destination'

class AlertListScope(OriginalAlertDelivery):
    def setUp(self):
        super().setUp()
        payload=json.loads(self.s.db.execute('SELECT payload_json FROM outbox WHERE outbox_id=?',(self.oid,)).fetchone()[0])
        payload.update(task_id='demo-c',attempt_id='attempt-c')
        self.s.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('demo-c','attempt-c','other-alert','SUPERVISION_ACTION',1000,'PHASE_EXECUTION','HANDOFF_CONTEXT_INCOMPLETE',canonical(payload)))
        self.s._enqueue('demo-c','attempt-c','other-alert',payload,1000);self.s.db.commit()
        self.oid_c=self.s.db.execute("SELECT outbox_id FROM outbox WHERE event_id='other-alert'").fetchone()[0]
    def test_authorized_exact_task_attempts_and_missing_host(self):
        b=ScopeHost({('tenant-1','demo-b','attempt-1')})
        both=ScopeHost({('tenant-1','demo-b','attempt-1'),('tenant-1','demo-c','attempt-c')})
        wrong_attempt=ScopeHost({('tenant-1','demo-b','other-attempt')})
        rows=self.g.due_handoff_alerts(self.context,now=1000,host_adapter=b)
        self.assertEqual([r['task_id'] for r in rows],['demo-b'])
        self.assertEqual({r['task_id'] for r in self.g.due_handoff_alerts(self.context,now=1000,host_adapter=both)},{'demo-b','demo-c'})
        self.assertEqual(self.g.due_handoff_alerts(self.context,now=1000,host_adapter=wrong_attempt),[])
        self.assertEqual(self.g.due_handoff_alerts(self.context,now=1000),[])
        self.assertEqual(self.g.due_handoff_alerts(self.authority.issue('other','seed'),now=1000,host_adapter=both),[])
        class Unknown:
            def resolve_destination(self,packet):raise ValueError('unknown authority')
        self.assertEqual(self.g.due_handoff_alerts(self.context,now=1000,host_adapter=Unknown()),[])
        # Limit applies after authorization, so an unpermitted early row cannot
        # consume a permitted host's only result slot.
        self.assertEqual([r['task_id'] for r in self.g.due_handoff_alerts(self.context,now=1000,limit=1,host_adapter=b)],['demo-b'])
        c=ScopeHost({('tenant-1','demo-c','attempt-c')})
        self.assertEqual([r['task_id'] for r in self.g.due_handoff_alerts(self.context,now=1000,limit=1,host_adapter=c)],['demo-c'])
