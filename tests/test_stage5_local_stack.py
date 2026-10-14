import unittest,threading,json
from http.server import HTTPServer
from http.client import HTTPConnection
from scripts.community_demo_api import DemoService,handler,server_database
class StackTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.db=server_database(":memory:")
  cls.server=HTTPServer(("127.0.0.1",0),handler(DemoService(cls.db)))
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.thread.join(3);cls.server.server_close();cls.db.close()
 def call(self,method,path,body=None,host=None):
  c=HTTPConnection("127.0.0.1",self.server.server_address[1],timeout=3)
  headers={"Content-Type":"application/json"}
  if host:headers["Host"]=host
  c.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
  r=c.getresponse();out=r.read();status=r.status;type_=r.getheader("Content-Type");c.close()
  return status,out,type_
 def test_same_origin_ui_is_served(self):
  status,raw,mime=self.call("GET","/demo/")
  self.assertEqual(status,200);self.assertIn(b"/demo/app.js",raw)
  self.assertIn("text/html",mime)
  status,raw,mime=self.call("GET","/demo/app.js")
  self.assertEqual(status,200);self.assertIn(b"simulated" if False else b"simulate",raw)
 def test_merchant_console_assets_same_origin(self):
  status,raw,mime=self.call("GET","/demo/merchant/")
  self.assertEqual(status,200)
  self.assertIn(b"/demo/merchant/app.js",raw)
  self.assertIn("text/html",mime)
  status,raw,mime=self.call("GET","/demo/merchant/app.js")
  self.assertEqual(status,200)
  self.assertIn(b"/demo/orders/state",raw)
  self.assertIn("text/javascript",mime)
 def test_api_full_simulated_sequence(self):
  scope={"tenant_id":"t1","merchant_id":"m1","store_id":"s1","reference":"ref_e2e","amount_minor":150}
  status,raw,_=self.call("POST","/demo/orders",scope)
  self.assertEqual(status,200)
  self.assertEqual(json.loads(raw)["state"],"PENDING")
  event={**scope,"event_id":"e2e1","transaction_id":"tx_e2e","target":"SUCCESS"}
  status,raw,_=self.call("POST","/demo/orders/simulate",event)
  self.assertEqual(status,200)
  self.assertFalse(json.loads(raw)["provider_settlement_verified"])
  status,raw,_=self.call("POST","/demo/orders/state",{k:v for k,v in scope.items() if k!="amount_minor"})
  self.assertEqual(status,200);self.assertEqual(json.loads(raw)["state"],"SUCCESS")
 def test_cross_host_is_denied(self):
  self.assertEqual(self.call("GET","/demo/",host="evil.example")[0],403)
 def test_no_arbitrary_static_files(self):
  self.assertEqual(self.call("GET","/scripts/community_order_store.py")[0],404)
if __name__=="__main__":unittest.main()
