import contextlib, io, json, unittest
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
