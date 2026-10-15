"""Real loopback HTTP integration: offline SaaS only."""
import http.client
import json
import threading
import unittest
from scripts.community_saas_phase2 import Principal,OfflineSaas
from scripts.community_saas_phase2_http import serve
from scripts.community_saas_modules import connect
from scripts.community_saas_offer_catalog import install as offer_install
from scripts.community_saas_order_preparation import install as order_install,install_lifecycle
from scripts.community_saas_offline_handoff import install_reviews
import sqlite3
KEY="stage5-offline-integration-token-1234567890"
class LoopbackSaasTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
    cls.q=connect();offer_install(cls.q)
    cls.o=sqlite3.connect(":memory:",check_same_thread=False)
    order_install(cls.o);install_lifecycle(cls.o);install_reviews(cls.o)
    cls.server=serve(OfflineSaas(cls.q,cls.o,cls.q),{KEY:Principal("tenantA","CUSTOMER")})
    cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
    cls.thread.start()
 @classmethod
 def tearDownClass(cls):
    cls.server.shutdown();cls.thread.join(4);cls.server.server_close()
    cls.q.close();cls.o.close()
 def request(self,data,token=KEY,host=None,origin=None):
    connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=4)
    headers={"Content-Type":"application/json","X-Offline-Token":token}
    if host:headers["Host"]=host
    if origin:headers["Origin"]=origin
    connection.request("POST","/offline/saas",body=data,headers=headers)
    resp=connection.getresponse()
    result=(resp.status,json.loads(resp.read()))
    connection.close()
    return result
 def payload(self,op="catalog",params=None,at=20):
    return json.dumps({"operation":op,"params":params if params is not None else {},"at":at})
 def test_01_authorized_catalog(self):
    code,obj=self.request(self.payload())
    self.assertEqual(code,200);self.assertTrue(obj["offline_only"])
 def test_02_no_token_no_access(self):
    self.assertEqual(self.request(self.payload(),token="")[0],403)
 def test_03_invalid_host_forbidden(self):
    self.assertEqual(self.request(self.payload(),host="evil.example")[0],403)
 def test_04_origin_not_accepted(self):
    self.assertEqual(self.request(self.payload(),origin="https://evil.example")[0],403)
 def test_05_no_payment_operation(self):
    self.assertEqual(self.request(self.payload("payment_settle"))[0],400)
 def test_06_client_tenant_injection(self):
    self.assertEqual(self.request(self.payload(params={"tenant_id":"tenantB"}))[0],400)
 def test_07_admin_read_not_customer(self):
    self.assertEqual(self.request(self.payload("admin_snapshot"))[0],400)
 def test_08_duplicate_json_key(self):
    self.assertEqual(self.request('{"operation":"catalog","operation":"admin_snapshot","params":{},"at":20}')[0],400)
 def test_09_nonfinite_json(self):
    self.assertEqual(self.request('{"operation":"catalog","params":{},"at":NaN}')[0],400)
 def test_10_extra_field(self):
    self.assertEqual(self.request('{"operation":"catalog","params":{},"at":20,"payment_confirmed":true}')[0],400)
if __name__=="__main__":unittest.main()
