import http.client
import json
import threading
import time
import unittest
from unittest import mock
from scripts import pr122_site_hub_preview as preview

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.server=preview.PreviewServer(0,True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.scope={'tenant_id':'tenant1','merchant_id':'merchant1','store_id':'store1','reference':'same_reference'}
    def tearDown(self):self.server.shutdown();self.thread.join();self.server.server_close()
    def call(self,route,body=None,cookie='',headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        values={'Cookie':cookie,'Content-Type':'application/json','Origin':self.origin};values.update(headers or {})
        raw=body if isinstance(body,str) else json.dumps(body) if body is not None else None
        c.request('GET' if body is None else 'POST',preview.PREFIX+route,raw,values)
        r=c.getresponse();status=r.status;response_headers=dict(r.getheaders());data=json.loads(r.read());c.close();return status,response_headers,data
    def session(self):
        status,headers,data=self.call('/session');self.assertEqual(status,200)
        self.assertTrue(data['simulation_only']);self.assertFalse(data['provider_connected'])
        return headers['Set-Cookie'].split(';',1)[0],data
    def test_two_visitors_never_share_orders_or_admin_capabilities(self):
        a,aa=self.session();b,bb=self.session();self.assertNotEqual(a,b)
        self.assertNotEqual(aa['merchant_demo_capability'],bb['merchant_demo_capability'])
        self.assertEqual(self.call('/orders',{**self.scope,'amount_minor':123},a)[0],200)
        self.assertEqual(self.call('/orders/state',self.scope,a)[0],200)
        self.assertEqual(self.call('/orders/state',self.scope,b)[0],400)
        operation={'identity':{k:self.scope[k] for k in ('tenant_id','merchant_id','store_id')},'operation':{'item':{'id':'sample_new','name':'synthetic','status':'ACTIVE','sort':1}}}
        self.assertEqual(self.call('/admin/item',operation,b,{'X-Local-Admin-Capability':aa['merchant_demo_capability']})[0],403)
    def test_csrf_host_cookie_and_missing_session_fail_closed(self):
        cookie,_=self.session()
        self.assertEqual(self.call('/orders',{**self.scope,'amount_minor':1})[0],403)
        self.assertEqual(self.call('/orders',{**self.scope,'amount_minor':1},cookie,{'Origin':'https://external.example'})[0],403)
        self.assertEqual(self.call('/session',headers={'Host':'external.example'})[0],403)
        self.assertEqual(self.call('/session',headers={'Sec-Fetch-Site':'cross-site'})[0],403)
        self.assertEqual(self.call('/session',cookie=cookie+'; '+cookie)[0],403)
    def test_expiry_and_bounded_capacity(self):
        cookie,_=self.session()
        with mock.patch.object(preview,'MAX_SESSIONS',1):self.assertEqual(self.call('/session')[0],503)
        self.server.sessions[cookie.split('=',1)[1]].expires=time.monotonic()-1
        self.assertEqual(self.call('/orders',{**self.scope,'amount_minor':1},cookie)[0],403)
        self.assertEqual(len(self.server.sessions),0)
    def test_json_overflow_duplicate_keys_and_unknown_routes_rejected(self):
        cookie,_=self.session()
        self.assertEqual(self.call('/orders','{"amount_minor":1e9999}',cookie)[0],400)
        self.assertEqual(self.call('/orders','{"x":1,"x":2}',cookie)[0],400)
        self.assertEqual(self.call('/unknown',{},cookie)[0],404)
        self.assertEqual(self.call('/orders?x=1',{},cookie)[0],404)
    def test_production_requires_fixed_https_proxy_and_secure_cookie(self):
        self.server.test_mode=False
        self.assertEqual(self.call('/session')[0],403)
        headers={'Host':preview.HOST,'X-Forwarded-Proto':'https','Origin':'https://'+preview.HOST}
        status,values,_=self.call('/session',headers=headers);self.assertEqual(status,200)
        for expected in ('Secure','HttpOnly','SameSite=Strict','Path=/_preview/'):
            self.assertIn(expected,values['Set-Cookie'])
        cookie=values['Set-Cookie'].split(';',1)[0]
        self.assertEqual(self.call('/orders',{**self.scope,'amount_minor':1},cookie,{**headers,'Origin':'https://external.example'})[0],403)

if __name__=='__main__':unittest.main()
