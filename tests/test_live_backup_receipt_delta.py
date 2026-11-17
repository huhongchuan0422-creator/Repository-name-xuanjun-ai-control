import base64,contextlib,io,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_delivery_ledger_route as fixtures
import task_center_app as app
from task_delivery_backup_receipt import LocalBackupReceiptReader
from task_delivery_observation import ObservationUnavailable

SOURCE='/home/xuanjun_dev/.openclaw/workspace-platform-engineer/deliveries/source-backup-1889/latest.json'
SNAPSHOT='/home/xuanjun_dev/.openclaw/workspace/deliveries/followup-watch-20261114/backup-center-observation.json'
class LocalReceiptDelta(unittest.TestCase):
    def setUp(self):self.f=fixtures.RouteTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    @unittest.skipUnless(os.path.isfile(SOURCE) and os.path.isfile(SNAPSHOT),'protected sources not mounted')
    def test_live_two_reads_via_original_handler_and_board(self):
        with open(SOURCE,'rb') as f:raw=f.read(65537)
        original=LocalBackupReceiptReader(SOURCE).read()['backup_observation']
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'latest.json';path.write_bytes(raw);calls=[]
            class FakeServer:
                def __init__(self,address,handler):self.server_address=address;self.server_port=address[1];self.handler=handler
                def serve_forever(self):
                    def get(auth,extra=''):
                        h=self.handler.__new__(self.handler);h.path='/api/admin/delivery-ledger'+extra;h.command='GET';h.headers={'Host':'localhost:8765'};h.server=self
                        if auth:h.headers['X-Test-Admin-Token']=fixtures.ADMIN
                        h._send=lambda status,body,kind,extra_headers=None:calls.append((status,json.loads(body)))
                        h.do_GET()
                    get(False);get(True);get(True,'?file=/not-the-bound-file')
                    path.write_text(json.dumps({'time_utc':'2026-11-16T18:31:59+00:00','status':'failed','error':'PRIVATE-ERROR-NOT-DISPLAYED'}))
                    get(True);raise KeyboardInterrupt()
                def server_close(self):pass
            argv=['--db',self.f.db,'--test-authority-key','synthetic-key-0123456789abcdef0123456789','--tenant','tenant-ui','--model-master-key-file','test-key-file','--admin-token-file','test-token-file','--delivery-ledger-root',self.f.root,'--delivery-ledger-namespace','synthetic','--delivery-ledger-writer','writer','--delivery-backup-observation-file',SNAPSHOT,'--delivery-backup-receipt-file',str(path)]
            with patch.object(app,'TaskCenterHTTPServer',FakeServer),patch.object(app,'load_master_key',return_value=base64.urlsafe_b64encode(b'0'*32)),patch.object(app,'_read_owned_secret_file',return_value=fixtures.ADMIN),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(app.main(argv),0)
        self.assertEqual([v[0] for v in calls],[403,200,200,200]);a,b=calls[1][1],calls[3][1];first=a['backup']['backup_observation'];second=b['backup']['backup_observation'];self.assertEqual(calls[2][1]['backup']['backup_observation']['backup_at'],first['backup_at'])
        self.assertEqual(first['backup_at'],original['backup_at']);self.assertEqual(first['files'],original['files']);self.assertEqual(second['backup_status'],'failed');self.assertEqual(second['backup_at'],'2026-11-16T18:31:59+00:00');self.assertEqual(second['files'],'UNKNOWN');self.assertEqual(b['backup']['provider_verification'],'UNKNOWN');self.assertEqual(b['backup']['static_snapshot']['freshness'],'snapshot-not-live');self.assertNotIn('PRIVATE-ERROR',json.dumps(b));self.assertNotIn(str(path),json.dumps(b))
        js="""const assert=require('assert'),ui=require('./demos/task-center-digital-twin/app.js');let s='';process.stdin.on('data',x=>s+=x).on('end',()=>{const v=JSON.parse(s),h=ui.render({mode:'TEST_ONLY',tasks:[]},ui.parseRoute('#board/research-development'),null,v);for(const x of ['源码备份','每5分钟','交接资料','任务与三方交接资料','delivery-ledger','delivery-handoff'])assert(!h.includes(x),x);assert(h.includes('研发工作台'));console.log('BOARD_RENDER_OK');});"""
        p=subprocess.run(['node','-e',js],input=json.dumps([[a,'记录成功'],[b,'记录失败']]).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(p.returncode,0,p.stderr.decode())
    def test_fail_closed_for_missing_invalid_types_and_oversize(self):
        with self.assertRaises(ObservationUnavailable):LocalBackupReceiptReader('/missing-local-receipt').read()
        for data in (b'{',b'x'*65537,json.dumps({'time_utc':'bad','status':'ok','files':1,'excluded_count':0}).encode(),json.dumps({'time_utc':'2026-11-16T18:31:59+00:00','status':'ok','files':True,'excluded_count':0}).encode()):
            with tempfile.NamedTemporaryFile() as f:
                f.write(data);f.flush()
                with self.assertRaises(ObservationUnavailable):LocalBackupReceiptReader(f.name).read()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):app.main(['--db',self.f.db,'--test-authority-key','key','--tenant','tenant-ui','--delivery-backup-receipt-file','x'])
if __name__=='__main__':unittest.main()
