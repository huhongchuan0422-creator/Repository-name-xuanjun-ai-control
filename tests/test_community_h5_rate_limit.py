"""Exact original rate limit stays enforced; rate exhaustion is not logout."""
import json,http.server,urllib.request,urllib.error,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from test_community_h5_recovery import H5Recovery
from scripts.community_h5 import make_handler
from scripts.community_wechat_applyment import WechatApplyment
from scripts.community_wechat_sp_readonly import PartnerOrderReader
class RateLimit(unittest.TestCase):
 def test_original_twenty_per_minute_limit_returns_429_and_session_still_checks(self):
  f=H5Recovery();f.setUp();f.f.onboarding.wechat_applyment=WechatApplyment(f.f.onboarding,PartnerOrderReader.__new__(PartnerOrderReader))
  app=f.f.draft()['application'];server=http.server.HTTPServer(('127.0.0.1',0),make_handler(f.h,Path('clients/community-h5/dist')));server.timeout=3
  def send(path,body):
   req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=json.dumps(body).encode(),headers={**dict(f.headers.items()),'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.load(r)
   except urllib.error.HTTPError as e:return e.code,json.load(e)
  try:
   with ThreadPoolExecutor(1) as pool:
    statuses=[]
    for _ in range(21):
     future=pool.submit(send,'/h5/merchant',{'scene':'shop1','operation':'onboarding','params':{'operation':'wechat_read','params':{'application':app}}});server.handle_request();status,body=future.result();statuses.append(status)
    self.assertEqual(statuses,[200]*20+[429]);self.assertEqual(body,{'error':'RATE_LIMIT'})
    future=pool.submit(send,'/h5/session/check',{});server.handle_request();status,body=future.result();self.assertEqual(status,200);self.assertEqual(body['result']['user_id'],f.f.fx.uid1)
  finally:server.server_close();f.tearDown()
