"""Task-scoped HTTP does not expose namespace aggregate conflicts."""
import copy
from pathlib import Path
from test_handoff_publication_conflicts import PublicationConflicts
from task_delivery_ledger.core import Store

class TaskScope(PublicationConflicts):
    def test_outside_task_conflict_does_not_change_response(self):
        self.setup_server()
        try:
            p=self.make('PROPOSE','p','NONE','alice')
            limited_auth=self.auth.authenticate_and_authorize
            def limited(session,action,binding):
                if binding.get('task_id')!='task-1':raise ValueError('OUTSIDE_TASK_SCOPE')
                return limited_auth(session,action,binding)
            self.auth.authenticate_and_authorize=limited
            status,first=self.post(p)
            self.assertEqual(status,200);self.assertEqual(first['ledger_publication'],'PUBLISHED')
            e=copy.deepcopy(p['ledger_event'])
            e.update(task_id='other-task',attempt_id='other-attempt',event_id='other-event',idempotency_key='other-event',type='register',validity='HISTORICAL',causation='NONE')
            e['data']={'kind':'role','id':'other-role','schema_version':1,'source':'source-ref','occurred_at':self.stamp,'observed_at':self.stamp,'validity':'HISTORICAL','task_id':'other-task','verified_session_ref':'UNKNOWN','entry_ref':'UNKNOWN','query_capability':'UNKNOWN','send_capability':'UNKNOWN','receipt_ref':'UNKNOWN'}
            store=Store(self.bridge.root,'writer');store.enqueue(e)
            dest=Path(self.bridge.root)/'events'/'tenant-ledger'/'other-event.json';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b'{}')
            status,repeated=self.post(p)
            self.assertEqual(status,200);self.assertEqual(repeated['state'],'ALREADY_RECORDED')
            # Except for the legitimate idempotent state, response is identical;
            # neither the existence nor count of other tasks' conflicts is sent.
            first['state']='ALREADY_RECORDED'
            self.assertEqual(repeated,first)
            self.assertNotIn('ledger_other_conflicts',repeated)
            self.assertEqual(dest.read_bytes(),b'{}')
            internal=self.bridge.flush('task-1','attempt-1',p['event_id'])
            self.assertEqual(internal['current'],'DUPLICATE');self.assertEqual(internal['flush']['conflict'],0)
            # Existing trusted namespace-wide flush still reports the other conflict.
            self.assertEqual(Store(self.bridge.root,'writer',authority=self.bridge).flush('tenant-ledger')['conflict'],1)
            self.assertEqual(dest.read_bytes(),b'{}')
        finally:self.stop_server()
