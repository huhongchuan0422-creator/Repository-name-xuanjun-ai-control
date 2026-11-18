import copy, tempfile, unittest, json
from task_delivery_ledger.core import Store, LedgerError, canonical, digest
from task_delivery_ledger.handoffs import CONTINUATION_FIELDS, project_handoffs
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
            snap.update({k:'UNKNOWN' for k in CONTINUATION_FIELDS})
            snap['backup_ref']='source-backup-1889-coverage-20261118'
            snap['permission_request_ref']='openclaw-github-identity-status'
            events[0]['data']['scope_included'].extend(CONTINUATION_FIELDS)
            hashed=digest(canonical(snap))
            for e in events:e['data']['snapshot_digest']=hashed
            bad=copy.deepcopy(events[0]);bad['data']['snapshot_data']['credential_ref']='ref-changed'
            with self.assertRaises(LedgerError):store.enqueue(bad)
            for e in events:store.enqueue(e)
            store.flush('synthetic')
            view=reader.view();task=[x for x in view['tasks'] if x['task_id']=='t1'][0]
            context=task['handoffs'][0]['continuation']
            self.assertEqual(context['status'],'MISSING_REFERENCES')
            self.assertEqual(context['permission_request_ref'],'openclaw-github-identity-status')
            backup=context['backup_observation']
            self.assertEqual(backup['state'],'HISTORICAL_REPORTED_NOT_LIVE')
            self.assertEqual(backup['historical_deleted_files_commit'],'aedb23ddc9e76c68d6b3f0c7a6387aa046576ac1')
            self.assertEqual(backup['scheduler_identity'],'UNKNOWN')
            self.assertEqual(backup['data_config_permissions_recovery'],'NOT_PROVEN')
            self.assertIn('重新取得',context['instruction'])
            exported=reader.export('t1')['handoff']['handoffs']['t1:h1']['continuation']
            self.assertEqual(context,exported)
            self.assertNotEqual(task['handoffs'][0]['status'],'交接完成(范围)')

    def test_recomputed_digest_does_not_accept_or_export_inline_content(self):
        from task_delivery_ledger.core import CONTINUATION_REFERENCES
        for field in CONTINUATION_FIELDS:
            events=scenario(); e=events[0]
            e.update(schema_version=1,sanitization='MANUAL_REDACTED',namespace='synthetic',idempotency_key=e['event_id'],producer='writer',result='observed')
            snap=e['data']['snapshot_data'];snap.update({k:'UNKNOWN' for k in CONTINUATION_FIELDS})
            snap[field]='examplevalue123';e['data']['scope_included'].extend(CONTINUATION_FIELDS)
            e['data']['snapshot_digest']=digest(canonical(snap))
            with tempfile.TemporaryDirectory() as root:
                store=Store(root,'writer')
                with self.assertRaises(LedgerError):store.enqueue(e)
            projected=project_handoffs([e])['t1:h1']
            self.assertEqual(projected['continuation'][field],'UNKNOWN')
            self.assertNotIn('examplevalue123',json.dumps(projected))
        self.assertEqual(CONTINUATION_REFERENCES['credential_ref'],frozenset())

    def test_direct_projection_sanitizes_all_event_object_locations(self):
        for field in CONTINUATION_FIELDS:
            for location in ('event','data','nested_data','nested_snapshot'):
                e=scenario()[0]
                if location=='event':target=e
                elif location=='data':target=e['data']
                elif location=='nested_data':target=e['data'].setdefault('data',{})
                else:target=e['data']['snapshot_data'].setdefault('data',{})
                target[field]='examplevalue123'
                before=copy.deepcopy(e)
                projected=project_handoffs([e])['t1:h1']
                self.assertNotIn('examplevalue123',json.dumps(projected))
                self.assertEqual(e,before)
        e=scenario()[0];e['data']['permission_request_ref']='openclaw-github-identity-status'
        result=project_handoffs([e])['t1:h1']
        self.assertEqual(result['history'][0]['data']['permission_request_ref'],'openclaw-github-identity-status')

    def test_complete_registered_references_are_still_unverified(self):
        from unittest.mock import patch
        from task_delivery_ledger.core import CONTINUATION_REFERENCES
        selected={k:frozenset(('test-ref-'+str(i),)) for i,k in enumerate(CONTINUATION_FIELDS)}
        e=scenario()[0];snap=e['data']['snapshot_data']
        snap.update({k:next(iter(selected[k])) for k in CONTINUATION_FIELDS})
        e['data']['scope_included'].extend(CONTINUATION_FIELDS)
        e['data']['snapshot_digest']=digest(canonical(snap))
        e.update(schema_version=1,sanitization='MANUAL_REDACTED',namespace='synthetic',idempotency_key=e['event_id'],producer='writer',result='observed')
        with patch.dict(CONTINUATION_REFERENCES,selected):
            with tempfile.TemporaryDirectory() as root:
                store=Store(root,'writer');store.enqueue(e);store.flush('synthetic')
                context=MetadataReader(root,'synthetic','writer','tenant-ui').export('t1')['handoff']['handoffs']['t1:h1']['continuation']
                self.assertEqual(context['status'],'REFERENCES_UNVERIFIED')

    def test_protected_routes_reject_preexisting_unregistered_reference(self):
        import pathlib
        from test_delivery_ledger_route import RouteTests
        fixture=RouteTests();fixture.setUp()
        try:
            path=pathlib.Path(fixture.root)/'events/synthetic/e08.json'
            event=json.loads(path.read_text());data=event['data'];snap=data['snapshot_data']
            snap.update({k:'UNKNOWN' for k in CONTINUATION_FIELDS})
            snap['backup_ref']='source-backup-1889-coverage-20261118'
            data['scope_included'].extend(CONTINUATION_FIELDS)
            data['snapshot_digest']=digest(canonical(snap));path.write_bytes(canonical(event))
            for route in ('/api/admin/delivery-ledger','/api/admin/delivery-handoff?task_id=task1'):
                status,body,_=fixture.call(route);self.assertEqual(status,200)
                self.assertIn(b'source-backup-1889-coverage-20261118',body)
                self.assertEqual(fixture.call(route,admin=False)[0],403)
            snap['credential_ref']='examplevalue123'
            data['snapshot_digest']=digest(canonical(snap));path.write_bytes(canonical(event))
            for route in ('/api/admin/delivery-ledger','/api/admin/delivery-handoff?task_id=task1'):
                status,body,_=fixture.call(route);self.assertEqual(status,503)
                self.assertNotIn(b'examplevalue123',body)
        finally:fixture.tearDown()

if __name__=='__main__':unittest.main()
