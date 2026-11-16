import base64, contextlib, io, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import test_delivery_ledger_route as fixtures
import task_center_app as app
from task_delivery_observation import ObservationUnavailable

SOURCE=str(Path(__file__).resolve().parent.parent/'evidence/development-handoff/main-relayed-20261117.json')
COLLECTOR='main-development-handoff-20261117'

class CliObservationDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.RouteTests();self.f.setUp()
        self.base=['--db',self.f.db,'--test-authority-key','synthetic-key-0123456789abcdef0123456789','--tenant','tenant-ui','--model-master-key-file','test-key-file','--admin-token-file','test-token-file','--delivery-ledger-root',self.f.root,'--delivery-ledger-namespace','synthetic','--delivery-ledger-writer','writer']
    def tearDown(self):self.f.tearDown()
    def run_handler(self,observation):
        calls=[]
        class FakeServer:
            def __init__(self,address,handler):self.server_address=address;self.server_port=address[1];self.handler=handler
            def serve_forever(self):
                for authorized,path in [(False,'/api/admin/delivery-ledger'),(True,'/api/admin/delivery-ledger'),(True,'/api/admin/delivery-handoff?scope=ledger-self-observation'),(True,'/api/admin/delivery-handoff?scope=ledger-self-observation&file=other')]:
                    h=self.handler.__new__(self.handler);h.path=path;h.command='GET';h.headers={'Host':'localhost:8765'};h.server=self
                    if authorized:h.headers['X-Test-Admin-Token']=fixtures.ADMIN
                    h._send=lambda status,body,kind,extra_headers=None:calls.append((status,json.loads(body)))
                    h.do_GET()
                raise KeyboardInterrupt()
            def server_close(self):pass
        with patch.object(app,'TaskCenterHTTPServer',FakeServer),patch.object(app,'load_master_key',return_value=base64.urlsafe_b64encode(b'0'*32)),patch.object(app,'_read_owned_secret_file',return_value=fixtures.ADMIN),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(self.base+observation),0)
        return calls
    def test_cli_real_relay_observation_through_handler(self):
        calls=self.run_handler(['--delivery-observation-file',SOURCE,'--delivery-observation-collector',COLLECTOR])
        self.assertEqual([x[0] for x in calls],[403,200,200,503]);v=calls[1][1];self.assertEqual(v['source_trust'],'UNAVAILABLE');self.assertEqual(v['writer_verification'],'UNKNOWN')
        obs=v['observations'];self.assertEqual(obs['permission_verification'],'UNKNOWN');self.assertEqual(obs['handoff_completed'],'UNKNOWN');self.assertEqual(obs['source_observation_verified'],'MAIN_RELAYED_SNAPSHOT_BYTES_MATCH')
        d=obs['development_handoff'];self.assertEqual(d['records'][0]['timestamp_ms'],1794846300397);self.assertEqual(d['records'][1]['message_ref'],'UNKNOWN');self.assertNotEqual(d['records'][1]['commit'],d['records'][3]['commit']);self.assertEqual(d['online_permission'],'UNKNOWN');self.assertEqual(calls[2][1],obs)
    def test_unconfigured_missing_bad_hash_and_oversize(self):
        for options in ([],['--delivery-observation-file','/nonexistent-observation','--delivery-observation-collector',COLLECTOR]):
            calls=self.run_handler(options);self.assertEqual(calls[1][0],200);self.assertEqual(calls[1][1]['observations']['state'],'UNAVAILABLE');self.assertEqual(calls[2][0],503)
        for raw in (b'{}',b'x'*65537):
            with tempfile.NamedTemporaryFile() as f:
                f.write(raw);f.flush();calls=self.run_handler(['--delivery-observation-file',f.name,'--delivery-observation-collector',COLLECTOR]);self.assertEqual(calls[1][1]['observations']['state'],'UNAVAILABLE');self.assertEqual(calls[2][0],503)
    def test_partial_and_unapproved_source_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for args in (['--delivery-observation-file',SOURCE],['--delivery-observation-collector',COLLECTOR]):
                with self.assertRaises(SystemExit):app.main(self.base+args)
            with self.assertRaises(SystemExit):app.main(self.base[:8]+['--delivery-observation-file',SOURCE,'--delivery-observation-collector',COLLECTOR])
        with self.assertRaises(ObservationUnavailable):app.main(self.base+['--delivery-observation-file',SOURCE,'--delivery-observation-collector','unapproved'])
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):app.main(self.base+['--delivery-observation-file',SOURCE,'--delivery-observation-collector',COLLECTOR],delivery_ledger_reader=self.f.reader)

if __name__=='__main__':unittest.main()
