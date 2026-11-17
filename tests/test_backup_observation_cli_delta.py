import base64, contextlib, io, json, os, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import test_delivery_ledger_route as fixtures
import task_center_app as app

SOURCE='/home/xuanjun_dev/.openclaw/workspace/deliveries/followup-watch-20261114/backup-center-observation.json'
HANDOFF=str(Path(__file__).resolve().parent.parent/'evidence/development-handoff/main-relayed-20261117.json')
class BackupObservationCli(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.RouteTests();self.f.setUp()
        self.base=['--db',self.f.db,'--test-authority-key','synthetic-key-0123456789abcdef0123456789','--tenant','tenant-ui','--model-master-key-file','test-key-file','--admin-token-file','test-token-file','--delivery-ledger-root',self.f.root,'--delivery-ledger-namespace','synthetic','--delivery-ledger-writer','writer']
    def tearDown(self):self.f.tearDown()
    def call(self,args):
        calls=[]
        class FakeServer:
            def __init__(self,address,handler):self.server_address=address;self.server_port=address[1];self.handler=handler
            def serve_forever(self):
                h=self.handler.__new__(self.handler);h.path='/api/admin/delivery-ledger';h.command='GET';h.headers={'Host':'localhost:8765'};h.server=self
                h._send=lambda status,body,kind,extra_headers=None:calls.append((status,json.loads(body)))
                h.do_GET();h.headers['X-Test-Admin-Token']=fixtures.ADMIN;h.do_GET();raise KeyboardInterrupt()
            def server_close(self):pass
        with patch.object(app,'TaskCenterHTTPServer',FakeServer),patch.object(app,'load_master_key',return_value=base64.urlsafe_b64encode(b'0'*32)),patch.object(app,'_read_owned_secret_file',return_value=fixtures.ADMIN),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(app.main(self.base+args),0)
        return calls
    @unittest.skipUnless(os.path.isfile(SOURCE),'main-relayed protected source not mounted')
    def test_real_snapshot_cli_handler_and_board(self):
        args=['--delivery-backup-observation-file',SOURCE,'--delivery-observation-file',HANDOFF,'--delivery-observation-collector','main-development-handoff-20261117']
        calls=self.call(args);self.assertEqual(calls[0][0],403);self.assertEqual(calls[1][0],200);v=calls[1][1];b=v['backup'];o=b['backup_observation']
        self.assertEqual(b['provider_verification'],'UNKNOWN');self.assertEqual(b['freshness'],'snapshot-not-live');self.assertEqual(o['observed_at'],'2026-11-16T18:23:23.889Z');self.assertEqual((o['interval_ms'],o['files'],o['excluded_count']),(300000,401,34));self.assertFalse(o['changed']);self.assertTrue(o['remote_verified_reported']);self.assertEqual(o['latest_run_status'],'succeeded');self.assertEqual(v['observations']['permission_verification'],'UNKNOWN');self.assertIn('development_handoff',v['observations'])
        self.assertNotIn('manifestSha256',json.dumps(b));self.assertNotIn('bc52965b',json.dumps(b));self.assertNotIn('b2c818a2',json.dumps(b))
        self.base[self.base.index('--delivery-ledger-root')+1]=str(Path(self.f.tmp.name)/'missing-root')
        missing=self.call(['--delivery-backup-observation-file',SOURCE]);self.assertEqual(missing[1][0],200);self.assertEqual(missing[1][1]['ledger_state'],'UNAVAILABLE');self.assertEqual(missing[1][1]['backup']['backup_observation']['files'],401);self.assertEqual(missing[1][1]['observations']['state'],'UNAVAILABLE')
        js="""const assert=require('assert'),ui=require('./demos/task-center-digital-twin/app.js');let s='';process.stdin.on('data',x=>s+=x).on('end',()=>{const v=JSON.parse(s),h=ui.render({mode:'TEST_ONLY',tasks:[]},ui.parseRoute('#board/research-development'),null,v);for(const x of ['源码备份','每5分钟','交接资料','任务与三方交接资料','delivery-ledger','delivery-handoff'])assert(!h.includes(x),x);assert(h.includes('研发工作台'));console.log('BOARD_RENDER_OK');});"""
        p=subprocess.run(['node','-e',js],input=json.dumps(v).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE);self.assertEqual(p.returncode,0,p.stderr.decode());self.assertIn(b'BOARD_RENDER_OK',p.stdout)
    def test_unconfigured_and_unapproved_file(self):
        self.assertEqual(self.call([])[1][1]['backup']['state'],'UNAVAILABLE')
        self.assertEqual(self.call(['--delivery-backup-observation-file','/missing-backup-observation'])[1][1]['backup']['state'],'UNAVAILABLE')
        for raw in (b'{}',b'x'*65537):
            with tempfile.NamedTemporaryFile() as f:
                f.write(raw);f.flush();self.assertEqual(self.call(['--delivery-backup-observation-file',f.name])[1][1]['backup']['state'],'UNAVAILABLE')
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):app.main(['--db',self.f.db,'--test-authority-key','key','--tenant','tenant-ui','--delivery-backup-observation-file','x'])
            with self.assertRaises(SystemExit):app.main(self.base+['--delivery-observation-file','x','--delivery-observation-collector','main-backup-observation-20261117'])
if __name__=='__main__':unittest.main()
