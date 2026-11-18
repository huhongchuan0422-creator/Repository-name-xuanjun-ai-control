"""Opt-in host event publication must not scan other events."""
from pathlib import Path
from test_handoff_publication_conflicts import PublicationConflicts
from task_delivery_ledger.core import canonical

class ScopedFlush(PublicationConflicts):
    def test_malformed_other_outbox_does_not_block_current_event(self):
        self.setup_server()
        try:
            value=self.make('PROPOSE','p','NONE','alice')
            path=Path(self.bridge.root)/'outbox'/'tenant-ledger'/'a-other-event.json'
            path.parent.mkdir(parents=True);path.write_bytes(b'not-json')
            status,body=self.post(value)
            self.assertEqual(status,200);self.assertEqual(body['state'],'RECORDED')
            self.assertEqual(body['ledger_publication'],'PUBLISHED')
            published=Path(self.bridge.root)/'events'/'tenant-ledger'/(value['event_id']+'.json')
            self.assertEqual(published.read_bytes(),canonical(value['ledger_event']))
            status,retry=self.post(value)
            self.assertEqual(status,200);self.assertEqual(retry['state'],'ALREADY_RECORDED');self.assertEqual(retry['ledger_publication'],'PUBLISHED')
            self.assertEqual(path.read_bytes(),b'not-json')
        finally:self.stop_server()
