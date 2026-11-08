import unittest,http.server,json,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from test_community_h5_recovery import H5Recovery
from scripts.community_h5 import with_existing_handler
from scripts.community_mini_http import make_handler
class Parallel(unittest.TestCase):
 def test_h5_mount_keeps_original_mini_identity_boundary(self):
  f=H5Recovery();f.setUp();original=make_handler(f.f.fx.gateway,onboarding=f.f.onboarding,operations=f.f.operations)
  server=http.server.HTTPServer(('127.0.0.1',0),with_existing_handler(original,f.h,Path('clients/community-h5/dist')));server.timeout=3
  def send(path,body):
   req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=json.dumps(body).encode(),headers={**dict(f.headers.items()),'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.load(r)
   except urllib.error.HTTPError as e:return e.code,json.load(e)
  try:
   with ThreadPoolExecutor(1) as pool:
    future=pool.submit(send,'/h5/platform',{});server.handle_request();self.assertEqual(future.result()[0],200)
    future=pool.submit(send,'/mini/api',{'scene':'shop1','operation':'community.storefront','params':{}});server.handle_request();self.assertEqual(future.result()[0],403)
    future=pool.submit(send,'/h5/session/check',{});server.handle_request();self.assertEqual(future.result()[0],200)
  finally:server.server_close();f.tearDown()
