import json, os, unittest
from types import SimpleNamespace
from task_center_app import build_handler
from task_delivery_observer import MetadataReader
from task_delivery_observation import ApprovedObservationReader, ObservationUnavailable

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE=os.path.join(ROOT,'evidence/development-handoff/main-relayed-20261117.json')

class DevelopmentHandoffReadback(unittest.TestCase):
    def test_main_relay_through_protected_original_handler(self):
        source=ApprovedObservationReader(SOURCE,'main-development-handoff-20261117')
        reader=MetadataReader('/nonexistent-read-only-ledger','pilot354','ledger-writer','tenant-check',source)
        cls=build_handler('/nonexistent',b'0'*32,'tenant-check','viewer',admin_token='local-probe-token',delivery_ledger_reader=reader)
        def get(authorized):
            h=cls.__new__(cls);h.path='/api/admin/delivery-ledger';h.command='GET';h.headers={'Host':'localhost:8765'};h.server=SimpleNamespace(server_port=8765)
            if authorized:h.headers['X-Test-Admin-Token']='local-probe-token'
            out=[];h._send=lambda status,body,kind,extra_headers=None:out.append((status,json.loads(body)));h.do_GET();return out[0]
        self.assertEqual(get(False)[0],403)
        status,result=get(True);self.assertEqual(status,200);self.assertEqual(result['ledger_state'],'UNAVAILABLE')
        obs=result['observations'];self.assertEqual(obs['permission_verification'],'UNKNOWN');self.assertEqual(obs['handoff_completed'],'UNKNOWN')
        d=obs['development_handoff'];self.assertEqual(d['records'][0]['commit'],d['records'][1]['commit']);self.assertNotEqual(d['records'][1]['commit'],d['records'][3]['commit'])
        self.assertEqual(d['records'][1]['message_ref'],'UNKNOWN');self.assertEqual(d['runtime_version'],'UNKNOWN')
        self.assertEqual(d['branch'],'candidate/tc-workbench-resources-20261115');self.assertIn('/api/admin/delivery-ledger',d['entry'])
    def test_missing_source_fails_closed(self):
        with self.assertRaises(ObservationUnavailable):ApprovedObservationReader('/missing','main-development-handoff-20261117').read()

if __name__=='__main__':unittest.main()
