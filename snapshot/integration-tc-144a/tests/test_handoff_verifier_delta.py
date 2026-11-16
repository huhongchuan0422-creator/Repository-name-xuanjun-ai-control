import copy, json, tempfile, unittest
import test_delivery_ledger_route as route_fixture
from task_delivery_ledger.core import Store, LedgerError
from task_delivery_observer import MetadataReader
from test_handoff_attempt_delta import scenario

class HandoffVerifierDelta(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name,'writer')
        self.events=scenario()
        for e in self.events:
            e.update(schema_version=1,sanitization='MANUAL_REDACTED',namespace='synthetic',idempotency_key=e['event_id'],producer='writer',result='observed')
            self.store.enqueue(e)
        self.store.flush('synthetic')
    def tearDown(self):self.temp.cleanup()
    def test_optional_verifier_reaches_projection_reader_and_export(self):
        def status(v):return v['handoffs']['t1:h1']['handoff_status']
        default=status(self.store.project('synthetic'))
        self.assertNotEqual(default,'交接完成(范围)')
        calls=[]
        def verifier(event):calls.append(event['event_id']);return True
        self.assertEqual(status(self.store.project('synthetic',verifier=verifier)),'交接完成(范围)')
        self.assertEqual(len(calls),6)
        self.assertNotEqual(status(self.store.project('synthetic',verifier=lambda e:False)),'交接完成(范围)')
        reader=MetadataReader(self.temp.name,'synthetic','writer','tenant-ui',handoff_verifier=verifier)
        view=reader.view(); self.assertEqual(view['source_trust'],'UNAVAILABLE');self.assertEqual(view['writer_verification'],'UNKNOWN')
        self.assertEqual(view['tasks'][0]['handoffs'][0]['status'],'交接完成(范围)')
        self.assertEqual(reader.export('t1')['handoff']['handoffs']['t1:h1']['handoff_status'],'交接完成(范围)')
        default_reader=MetadataReader(self.temp.name,'synthetic','writer','tenant-ui')
        self.assertNotEqual(default_reader.export('t1')['handoff']['handoffs']['t1:h1']['handoff_status'],'交接完成(范围)')
    def test_actual_admin_read_and_export_use_same_verifier(self):
        fixture=route_fixture.RouteTests();fixture.setUp()
        try:
            fixture.reader=MetadataReader(self.temp.name,'synthetic','writer','tenant-ui',handoff_verifier=lambda e:True)
            status,body,_=fixture.call('/api/admin/delivery-ledger');self.assertEqual(status,200)
            view=json.loads(body.decode());self.assertEqual(view['mode'],'TEST_ONLY');self.assertEqual(view['source_trust'],'UNAVAILABLE')
            self.assertEqual(view['tasks'][0]['handoffs'][0]['status'],'交接完成(范围)')
            status,body,_=fixture.call('/api/admin/delivery-handoff?task_id=t1');self.assertEqual(status,200)
            export=json.loads(body.decode());self.assertEqual(export['handoff']['handoffs']['t1:h1']['handoff_status'],'交接完成(范围)')
            self.assertEqual(fixture.call('/api/admin/delivery-ledger',admin=False)[0],403)
        finally:fixture.tearDown()
    def test_injection_does_not_bypass_non_synthetic_policy(self):
        event=copy.deepcopy(self.events[0]);event['namespace']='real-scope'
        with self.assertRaises(LedgerError):self.store.enqueue(event)
        reader=MetadataReader(self.temp.name,'synthetic','writer','tenant-ui',handoff_verifier=lambda e:True)
        self.assertEqual(reader.view()['source_trust'],'UNAVAILABLE')
if __name__=='__main__':unittest.main()
