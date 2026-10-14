"""Real localhost signed-QR issuance/verification tests, simulation only."""
import json
import unittest
from scripts.community_demo_api import serve_local

class DemoQRTests(unittest.TestCase):
 def setUp(self):
  self.srv=serve_local(port=0)
  self.service=self.srv.RequestHandlerClass
  from http.client import HTTPConnection
  self.conn=HTTPConnection("127.0.0.1",self.srv.server_address[1],timeout=3)
  import threading
  self.thread=threading.Thread(target=self.srv.serve_forever,daemon=True)
  self.thread.start()
 def tearDown(self):
  self.conn.close()
  self.srv.shutdown();self.thread.join(3);self.srv.server_close()
 def send(self,path,data):
  self.conn.request("POST",path,body=json.dumps(data),headers={"Content-Type":"application/json"})
  res=self.conn.getresponse()
  return res.status,json.loads(res.read())
 def test_signed_qr_scope_and_tamper(self):
  identity={"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1","context":"scan_demo"}
  code,created=self.send("/demo/qr/create",identity)
  self.assertEqual(code,200)
  self.assertFalse(created["provider_payment_started"])
  self.assertNotIn("key",created)
  payload={**identity,"token":created["token"]}
  code,checked=self.send("/demo/qr/verify",payload)
  self.assertEqual(code,200);self.assertTrue(checked["valid"])
  self.assertFalse(self.send("/demo/qr/verify",{**payload,"merchant_id":"merchant2"})[1]["valid"])
  tampered=json.loads(json.dumps(created["token"]))
  tampered["payload"]["expires"]+=500
  self.assertFalse(self.send("/demo/qr/verify",{**payload,"token":tampered})[1]["valid"])
 def test_bad_qr_shape_rejected(self):
  identity={"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1","context":"demo"}
  self.assertEqual(self.send("/demo/qr/create",{**identity,"unsafe":"extra"})[0],400)
  self.assertEqual(self.send("/demo/qr/verify",{**identity,"token":{},"extra":"x"})[0],400)
if __name__=="__main__":unittest.main()
