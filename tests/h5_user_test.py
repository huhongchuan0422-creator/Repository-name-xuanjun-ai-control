"""Local user acceptance launcher. Never installs, publishes, or uses live WeChat.
Uses the exact frozen H5 build and existing synthetic Center/OCR fixtures.
"""
import argparse,http.server,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_community_h5_ocr import H5Ocr
from scripts.community_h5 import make_handler
from scripts.community_commerce import Commerce

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=0);args=parser.parse_args()
 if not (args.port==0 or 1024<=args.port<=65535):parser.error('Use 0 or a nonprivileged local port')
 os.chdir(ROOT)
 H5Ocr.setUpClass();fx=H5Ocr();fx.setUp();center=fx.fx.fx.fx.center;center.scanner=lambda raw:True
 fx.h5.gateway.commerce=Commerce(fx.fx.fx.operations,fx.fx.fx.fx.identity)
 handler=make_handler(fx.h5,ROOT/'clients/community-h5/dist')
 class LocalOnly(handler):
  def do_GET(self):
   if self.path=='/':
    raw='''<!doctype html><meta charset="utf-8"><title>H5 本地合成测试入口</title><h1>仅供用户测试，尚未安装</h1><p>使用合成账户、合成OCR、临时数据。不会提交真实微信申请，不证明真实支付开通。不要上传真实证照、银行卡或客户资料。</p><p>测试账号 one@example.org 或 two@example.org；密码 FixturePassword123!</p><p><a href="/h5/#/pages/merchant-join/index?scene=shop1">进入同版H5资料准备测试</a></p><p>停止本进程会清除临时测试账户与文件。正式安装必须另获用户测试确认。</p>'''.encode()
    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
   else:super().do_GET()
 server=http.server.HTTPServer(('127.0.0.1',args.port),LocalOnly)
 print('LOCAL_SYNTHETIC_TEST_ONLY http://localhost:'+str(server.server_port)+'/',flush=True)
 print('Loopback only: this URL is not a public or mobile-accessible link. No deployment. Ctrl-C stops and removes temporary fixtures.',flush=True)
 try:server.serve_forever(.05)
 except KeyboardInterrupt:pass
 finally:server.server_close();fx.tearDown();H5Ocr.tearDownClass()
if __name__=='__main__':main()
