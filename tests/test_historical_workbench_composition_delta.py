import contextlib, hashlib, io, json, os, sqlite3, subprocess, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import task_center_app as app
from task_center_session_auth import SessionStore
from task_supervisor import Supervisor
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from reusable_scheduler_cli import demo_graph

ROOT=Path(__file__).resolve().parent.parent
HISTORY=ROOT.parent/'owner-354-reported-20261116-121107'
OBS=ROOT/'evidence/development-handoff/main-relayed-20261117.json'
KEY=b'0123456789abcdef0123456789abcdef'

def fingerprint(root):
    return {str(p.relative_to(root)): (p.stat().st_mtime_ns, p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None) for p in [root]+sorted(root.rglob('*'))}

class HistoricalComposition(unittest.TestCase):
    def test_main_reader_handler_preview_workbench(self):
        before=fingerprint(HISTORY); obs_before=(OBS.stat().st_mtime_ns,hashlib.sha256(OBS.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            db=os.path.join(tmp,'test.sqlite'); sup=Supervisor(db); auth=TestTenantAuthority(KEY)
            gateway=GatewayKernel(sup,auth); gateway.register_graph(auth.issue('tenant-test-only','seed'),demo_graph('tenant-test-only'))
            from cryptography.fernet import Fernet
            app.ModelControl(gateway,auth.issue('tenant-test-only','admin:viewer'),Fernet.generate_key()); sup.close()
            captured={}
            class Captured(Exception): pass
            def intercept(*args,**kwargs): captured.update(kwargs); raise Captured()
            args=['--db',db,'--test-authority-key','synthetic-test-key','--tenant','tenant-test-only','--delivery-ledger-root',str(HISTORY),'--delivery-ledger-namespace','pilot354','--delivery-ledger-writer','ledger-writer','--delivery-observation-file',str(OBS),'--delivery-observation-collector','main-development-handoff-20261117']
            with patch.object(app,'make_server',side_effect=intercept):
                with self.assertRaises(Captured): app.main(args)
            reader=captured['delivery_ledger_reader']; store=reader._store()
            self.assertEqual(len(store.events('pilot354')),4)
            def connect():
                c=sqlite3.connect(db);c.row_factory=sqlite3.Row;return c
            sessions=SessionStore(connect,'tenant-test-only',ttl_seconds=600)
            admin=sessions.create({'tenant_id':'tenant-test-only','principal_id':'admin-test','roles':['TASK_CENTER_ADMIN']})[0]
            viewer=sessions.create({'tenant_id':'tenant-test-only','principal_id':'viewer-test','roles':['TASK_CENTER_VIEWER']})[0]
            cls=app.build_handler(db,KEY,'tenant-test-only','viewer',session_store=sessions,delivery_ledger_reader=reader)
            def call(path,token=None):
                h=cls.__new__(cls);h.path=path;h.command='GET';h.headers={'Host':'localhost:8765'};h.server=SimpleNamespace(server_port=8765)
                if token:h.headers['Cookie']=sessions.COOKIE+'='+token
                out=[];h._send=lambda status,body,kind,extra_headers=None:out.append((status,body))
                h.do_GET();return out[0]
            self.assertEqual(call('/api/admin/delivery-ledger')[0],403)
            self.assertEqual(call('/api/admin/delivery-ledger',viewer)[0],403)
            status,body=call('/api/admin/delivery-ledger',admin);self.assertEqual(status,200)
            ledger=json.loads(body); self.assertEqual(ledger['ledger_state'],'AVAILABLE_METADATA_ONLY'); self.assertEqual(len(ledger['tasks']),1)
            self.assertEqual(ledger['tasks'][0]['validity'],'HISTORICAL');self.assertEqual(ledger['tasks'][0]['state'],'UNKNOWN')
            self.assertEqual(ledger['observations']['permission_verification'],'UNKNOWN');self.assertEqual(ledger['observations'],reader.export_observations())
            with self.assertRaises(ValueError): app.build_handler(db,KEY,'wrong-tenant','viewer',delivery_ledger_reader=reader)
            pstatus,projection=call('/api/projection',admin); tstatus,twin=call('/api/admin/digital-twin',admin)
            self.assertEqual((pstatus,tstatus),(200,200))
            # Exact handler bytes go to JS over stdin, never persisted or printed.
            payload=b'{"projection":'+projection+b',"twinStatus":'+str(tstatus).encode()+b',"twin":'+twin+b',"ledger":'+body+b'}'
            result=subprocess.run(['node','tests/historical_workbench_composition_delta.test.cjs'],input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertEqual(result.returncode,0, result.stderr.decode()[-1000:])
        self.assertEqual(before,fingerprint(HISTORY));self.assertEqual(obs_before,(OBS.stat().st_mtime_ns,hashlib.sha256(OBS.read_bytes()).hexdigest()))
