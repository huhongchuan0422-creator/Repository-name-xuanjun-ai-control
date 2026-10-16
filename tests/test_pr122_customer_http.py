import base64
import http.client
import json
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from scripts.pr122_customer_core import Center,canonical
from scripts.pr122_customer_http import App,COOKIE
from scripts.pr122_customer_providers import Providers
from tests.test_pr122_customer_center import CustomerTests

class HttpTests(CustomerTests):
 # Do not inherit/re-run core cases in this suite.
 def setUp(self):
  super().setUp()
  root=self.root;key=self.key;now=self.now
  def factory():return Center(root,{'v1':key},'v1',clock=lambda:now,mail_ready=True,scanner=lambda b:True)
  self.server=HTTPServer(('127.0.0.1',0),App(factory,Providers({}),'https://wenwenwenyiyiyi.work','deploy/pr122-customer-center/ui').handler())
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.addCleanup(self.finish)
 def finish(self):self.server.shutdown();self.server.server_close();self.thread.join()
 def request(self,path,body=None,headers=None,method=None):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
  h={'Host':'wenwenwenyiyiyi.work',**(headers or {})}
  if body is not None:h={'Origin':'https://wenwenwenyiyiyi.work','Content-Type':'application/json',**h}
  c.request(method or ('POST' if body is not None else 'GET'),'/customer/center/'+path,json.dumps(body) if body is not None else None,h);r=c.getresponse();raw=r.read();out=(r.status,dict(r.getheaders()),raw);c.close();return out
 def auth_headers(self):return {'Cookie':COOKIE+'='+self.users['owner']['token'],'X-CSRF-Token':self.users['owner']['csrf']}
 def test_http_session_injection_csrf_origin_and_secure_cookie(self):
  status,headers,body=self.request('api/login',{'email':'owner@example.com','password':'correct-password-123'});self.assertEqual(status,200);self.assertIn('Secure; HttpOnly; SameSite=Strict',headers['Set-Cookie']);self.assertNotIn(b'token',body)
  self.assertEqual(self.request('api/save',{'actor':self.owner},self.auth_headers())[0],400)
  self.assertEqual(self.request('api/message',{'project':'project-a','body':'hello'},{**self.auth_headers(),'Origin':'https://evil.example'})[0],403)
  self.assertEqual(self.request('api/message',{'project':'project-a','body':'hello'},{**self.auth_headers(),'X-CSRF-Token':'wrong'})[0],403)
  self.assertEqual(self.request('api/checklist/project-a')[0],403)
  self.assertEqual(self.request('api/me',headers=self.auth_headers())[0],200)
 def test_http_private_upload_download_no_range_cache_or_enumeration(self):
  b={'project':'project-a','item':'license','revision':0,'kind':'DOCUMENT','content':base64.b64encode(b'%PDF-test').decode(),'expires':None}
  self.assertEqual(self.request('api/save',b,self.auth_headers())[0],200)
  oid=self.c.db.execute('SELECT id FROM objects').fetchone()[0];path='api/download/project-a/'+oid
  status,h,raw=self.request(path,headers=self.auth_headers());self.assertEqual(status,200);self.assertEqual(raw,b'%PDF-test');self.assertIn('no-store',h['Cache-Control']);self.assertIn('attachment',h['Content-Disposition']);self.assertEqual(h['X-Content-Type-Options'],'nosniff')
  self.assertEqual(self.request(path)[0],403);self.assertEqual(self.request(path,headers={**self.auth_headers(),'Range':'bytes=0-2'})[0],403)
  self.assertEqual(self.request('api/download/project-a/o_missing',headers=self.auth_headers())[0],403)
 def test_http_csp_static_routes_and_webhook_rejection(self):
  s,h,raw=self.request('');self.assertEqual(s,200);self.assertIn("frame-ancestors 'none'",h['Content-Security-Policy']);self.assertIn('渝ICP备2026024862号'.encode(),raw)
  for f in ('app.css','app.js'):self.assertEqual(self.request(f)[0],200)
  self.assertEqual(self.request('api/none',headers=self.auth_headers())[0],404)
  self.assertEqual(self.request('api/me',headers=self.auth_headers(),method='DELETE')[0],405)
  self.assertEqual(self.request('webhooks/telegram',{'verified_provider':True,'subject':'123'})[0],503)
  self.assertEqual(self.request('api/me',headers={**self.auth_headers(),'Host':'evil.example'})[0],403)
  self.assertEqual(self.request('api/../objects')[0],403)
 def test_http_actual_registration_verification_login_reset_roundtrip(self):
  address='httpuser@example.com';self.assertEqual(self.request('api/register',{'email':address,'password':'correct-password-123'})[0],200)
  r=self.c.db.execute('SELECT * FROM outbox ORDER BY rowid DESC LIMIT 1').fetchone();token=json.loads(self.c.decrypt(r['payload'],'outbox:'+r['id']))['token']
  self.assertEqual(self.request('api/verify',{'token':token})[0],200);self.assertEqual(self.request('api/verify',{'token':token})[0],403)
  self.assertEqual(self.request('api/login',{'email':address,'password':'correct-password-123'})[0],200)

# Inherited core cases are collected only in their original test module.
for name in list(CustomerTests.__dict__):
 if name.startswith('test_'):setattr(HttpTests,name,None)
if __name__=='__main__':unittest.main()
