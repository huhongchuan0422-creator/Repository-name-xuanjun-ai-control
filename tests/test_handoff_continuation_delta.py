import copy, tempfile, unittest
from task_delivery_ledger.core import Store, LedgerError, canonical, digest
from task_delivery_ledger.handoffs import CONTINUATION_FIELDS
from task_delivery_observer import MetadataReader
from test_handoff_attempt_delta import scenario

class ContinuationDelta(unittest.TestCase):
    def test_old_and_extended_snapshot_readback_and_digest(self):
        events=scenario()
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,'writer')
            for e in events:
                e.update(schema_version=1,sanitization='MANUAL_REDACTED',namespace='synthetic',idempotency_key=e['event_id'],producer='writer',result='observed')
            old=copy.deepcopy(events[0]); old.update(event_id='old',idempotency_key='old',task_id='old-task')
            store.enqueue(old);store.flush('synthetic')
            reader=MetadataReader(root,'synthetic','writer','tenant-ui')
            old_view=reader.export('old-task')['handoff']['handoffs']['old-task:h1']['continuation']
            self.assertEqual(old_view['status'],'MISSING_REFERENCES')
            snap=events[0]['data']['snapshot_data']
            snap.update({k:'ref-'+str(i) for i,k in enumerate(CONTINUATION_FIELDS)})
            snap['backup_ref']='source-backup-1889-coverage-20261118'
            events[0]['data']['scope_included'].extend(CONTINUATION_FIELDS)
            hashed=digest(canonical(snap))
            for e in events:e['data']['snapshot_digest']=hashed
            bad=copy.deepcopy(events[0]);bad['data']['snapshot_data']['credential_ref']='ref-changed'
            with self.assertRaises(LedgerError):store.enqueue(bad)
            for e in events:store.enqueue(e)
            store.flush('synthetic')
            view=reader.view();task=[x for x in view['tasks'] if x['task_id']=='t1'][0]
            context=task['handoffs'][0]['continuation']
            self.assertEqual(context['status'],'REFERENCES_UNVERIFIED')
            self.assertEqual(context['permission_request_ref'],'ref-1')
            backup=context['backup_observation']
            self.assertEqual(backup['state'],'HISTORICAL_REPORTED_NOT_LIVE')
            self.assertEqual(backup['historical_deleted_files_commit'],'aedb23ddc9e76c68d6b3f0c7a6387aa046576ac1')
            self.assertEqual(backup['scheduler_identity'],'UNKNOWN')
            self.assertEqual(backup['data_config_permissions_recovery'],'NOT_PROVEN')
            self.assertIn('重新取得',context['instruction'])
            exported=reader.export('t1')['handoff']['handoffs']['t1:h1']['continuation']
            self.assertEqual(context,exported)
            self.assertNotEqual(task['handoffs'][0]['status'],'交接完成(范围)')

if __name__=='__main__':unittest.main()
