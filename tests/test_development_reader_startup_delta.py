import base64, contextlib, hashlib, io, json, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import test_delivery_ledger_route as fixtures
import task_center_app as app

class ReaderStartupDelta(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.RouteTests(); self.f.setUp()
    def tearDown(self):
        self.f.tearDown()
    def test_main_passes_explicit_reader_to_make_server(self):
        server=SimpleNamespace(server_address=('127.0.0.1',8765),mcp_worker=None,codex_worker=None,
            serve_forever=lambda: (_ for _ in ()).throw(KeyboardInterrupt()),server_close=lambda:None)
        with patch.object(app,'make_server',return_value=server) as make, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(['--db',self.f.db,'--test-authority-key','synthetic-key','--tenant','tenant-ui'],delivery_ledger_reader=self.f.reader),0)
        self.assertIs(make.call_args[1]['delivery_ledger_reader'],self.f.reader)
    def test_cli_assembles_reader_through_main_and_handler_read_only(self):
        calls=[]
        class FakeServer:
            def __init__(self,address,handler):self.server_address=address;self.server_port=address[1];self.handler=handler
            def serve_forever(self):
                h=self.handler.__new__(self.handler);h.path='/api/admin/delivery-ledger';h.command='GET';h.headers={'Host':'localhost:8765'};h.server=self
                h._send=lambda status,body,kind,extra_headers=None:calls.append((status,json.loads(body)))
                h.do_GET();h.headers['X-Test-Admin-Token']=fixtures.ADMIN;h.do_GET();raise KeyboardInterrupt()
            def server_close(self):pass
        def snapshot():return {str(p.relative_to(self.f.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(self.f.root).rglob('*') if p.is_file()}
        before=snapshot()
        argv=['--db',self.f.db,'--test-authority-key','synthetic-key-0123456789abcdef0123456789','--tenant','tenant-ui','--model-master-key-file','test-key-file','--admin-token-file','test-token-file','--delivery-ledger-root',self.f.root,'--delivery-ledger-namespace','synthetic','--delivery-ledger-writer','writer']
        with patch.object(app,'TaskCenterHTTPServer',FakeServer),patch.object(app,'load_master_key',return_value=base64.urlsafe_b64encode(b'0'*32)),patch.object(app,'_read_owned_secret_file',return_value=fixtures.ADMIN),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(app.main(argv),0)
        self.assertEqual(calls[0][0],403);self.assertEqual(calls[1][0],200);self.assertEqual(calls[1][1]['tasks'][0]['task_id'],'task1');self.assertEqual(calls[1][1]['source_trust'],'UNAVAILABLE');self.assertEqual(calls[1][1]['writer_verification'],'UNKNOWN');self.assertEqual(snapshot(),before)
        with self.assertRaises(ValueError):app.build_handler(self.f.db,fixtures.KEY,'other-tenant','viewer',delivery_ledger_reader=self.f.reader)
    def test_cli_default_partial_and_conflicting_config(self):
        server=SimpleNamespace(server_address=('127.0.0.1',8765),mcp_worker=None,codex_worker=None,serve_forever=lambda:(_ for _ in ()).throw(KeyboardInterrupt()),server_close=lambda:None)
        base=['--db',self.f.db,'--test-authority-key','synthetic-key','--tenant','tenant-ui']
        missing=str(Path(self.f.tmp.name)/'missing-ledger')
        with patch.object(app,'make_server',return_value=server) as make,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(base),0);self.assertIsNone(make.call_args[1]['delivery_ledger_reader'])
            self.assertEqual(app.main(base+['--delivery-ledger-root',missing,'--delivery-ledger-namespace','synthetic','--delivery-ledger-writer','writer']),0)
            self.assertFalse(Path(missing).exists())
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):app.main(base+['--delivery-ledger-root',self.f.root])
            with self.assertRaises(SystemExit):app.main(base+['--delivery-ledger-root',self.f.root,'--delivery-ledger-namespace','synthetic','--delivery-ledger-writer','writer'],delivery_ledger_reader=self.f.reader)
    def test_canonical_reader_exposes_tasks_not_fabricated_handoffs(self):
        result=app.read_only_projection(self.f.db,fixtures.KEY,'tenant-ui','viewer',consistent_snapshot=True)
        self.assertEqual(result['tenant_id'],'tenant-ui');self.assertTrue(result['tasks'])
        for task in result['tasks']:
            self.assertTrue({'task_id','board_id','state','received_at','started_at','last_real_progress_at','process_state','session_state'}.issubset(task))
            self.assertNotIn('handoffs',task);self.assertEqual(task['process_state'],'UNKNOWN');self.assertEqual(task['session_state'],'UNKNOWN')
        other=app.read_only_projection(self.f.db,fixtures.KEY,'tenant-other','viewer',consistent_snapshot=True)
        self.assertEqual(other['tasks'],[])
    def test_actual_make_server_assembles_bound_reader_and_route(self):
        class FakeServer:
            def __init__(self,address,handler): self.handler=handler;self.server_port=address[1]
        with patch.object(app,'TaskCenterHTTPServer',FakeServer):
            server=app.make_server(self.f.db,fixtures.KEY,'tenant-ui','viewer',admin_token=fixtures.ADMIN,delivery_ledger_reader=self.f.reader)
        h=server.handler.__new__(server.handler);h.path='/api/admin/delivery-ledger';h.command='GET';h.headers={'Host':'localhost:8765','X-Test-Admin-Token':fixtures.ADMIN};h.server=server
        out=[];h._send=lambda status,body,kind,extra_headers=None:out.append((status,json.loads(body)))
        h.do_GET();self.assertEqual(out[0][0],200);self.assertEqual(out[0][1]['source_trust'],'UNAVAILABLE');self.assertEqual(out[0][1]['writer_verification'],'UNKNOWN')
        h.headers={'Host':'localhost:8765'};out.clear();h.do_GET();self.assertEqual(out[0][0],403)

if __name__=='__main__':unittest.main()
