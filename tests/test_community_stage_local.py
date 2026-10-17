import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from scripts.community_stage_local import LocalStage
from scripts.community_saas_phase2 import Principal
from scripts.community_merchant_store import upsert_profile
from scripts.community_demo_bootstrap import DEMO_SCOPE

class PersistentHost(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.customer=Principal('tenant1','CUSTOMER')
        self.owner=Principal('tenant1','PLATFORM_OWNER')
        self.bindings={self.customer:DEMO_SCOPE,self.owner:DEMO_SCOPE}
    def tearDown(self):self.tmp.cleanup()
    def host(self):return LocalStage(self.tmp.name,self.bindings,DEMO_SCOPE)
    def test_one_writer_and_reopen_all_component_stores(self):
        with self.host() as app:
            upsert_profile(app.demo.merchant_db,DEMO_SCOPE,
                {'authenticated':True,'role':'MERCHANT_ADMIN','actor_id':'fixture',**DEMO_SCOPE},
                {'name':'Durable','description':'Offline','contact':'none','status':'ACTIVE'})
            from scripts.community_order_store import create_order
            create_order(app.demo.db,DEMO_SCOPE,'order1',101)
            app.runtime.simulate_from_operator(self.owner,'order1','event1','SUCCESS','tx1')
            with self.assertRaises(BlockingIOError): self.host()
        with self.host() as app:
            result=app.runtime.dispatch(self.customer,'community.receipt',{'reference':'order1'},0)
            self.assertEqual(result['order']['amount_minor'],101)
            self.assertFalse(result['provider_settlement_verified'])
            self.assertEqual(app.runtime.dispatch(self.customer,'catalog',{},0)['production'],False)
    def test_real_http_uses_same_principal_and_original_order_store(self):
        with self.host() as app:
            server=app.listen({'c'*32:self.customer,'p'*32:self.owner})
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                raw=json.dumps({'operation':'catalog','params':{},'at':0}).encode()
                request=urllib.request.Request('http://127.0.0.1:%s/offline/saas'%server.server_port,
                    raw,headers={'Content-Type':'application/json','X-Offline-Token':'c'*32})
                with urllib.request.urlopen(request) as response:
                    self.assertTrue(json.load(response)['result']['framework_free'])
                request=urllib.request.Request(request.full_url,
                    json.dumps({'operation':'community.orders','params':{},'at':0}).encode(),
                    headers={'Content-Type':'application/json','X-Offline-Token':'c'*32})
                with self.assertRaises(urllib.error.HTTPError) as caught: urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code,400)
            finally:server.shutdown();thread.join(3)
    def test_symlink_database_and_public_directory_rejected(self):
        target=Path(self.tmp.name)/'target';target.write_text('unchanged')
        (Path(self.tmp.name)/'orders.sqlite').symlink_to(target)
        with self.assertRaisesRegex(ValueError,'SYMLINK_DATABASE'):self.host()
        self.assertEqual(target.read_text(),'unchanged')
    def test_no_seed_on_reopen_or_automatic_business_writes(self):
        for attempt in range(2):
            with self.host() as app:
                self.assertEqual(app.demo.db.execute('SELECT count(*) FROM orders').fetchone()[0],0)
                self.assertEqual(app.demo.merchant_db.execute('SELECT count(*) FROM merchant_profiles').fetchone()[0],0)
                self.assertEqual(app.runtime.saas.orders.execute('SELECT count(*) FROM saas_order_preparations').fetchone()[0],0)

if __name__=='__main__':unittest.main()
