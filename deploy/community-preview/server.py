"""Isolated community preview candidate.

This composition is strictly synthetic:
- WeChat exchange is a fixture Mock; it is NOT real wx.login/code2session.
- Center accounts/projects are synthetic fixtures.
- business databases are temporary fixture databases.
- payments remain disabled and Finance remains UNCONFIRMED.
"""
import json, os, sys, urllib.parse, socketserver
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import test_community_reports as fixtures
from scripts.community_mini_http import make_handler
from scripts.pr122_customer_source import TrustedNginxSource
ORIGIN=os.environ['COMMUNITY_PREVIEW_ORIGIN']
if ORIGIN!='https://community-preview.wenwenwenyiyiyi.work':raise SystemExit('ISOLATED_PREVIEW_ORIGIN_REQUIRED')
SOCKET=Path(os.environ.get('COMMUNITY_PREVIEW_SOCKET','/run/xuanjun-community-preview/preview.sock'))
NGINX_UID=int(os.environ['COMMUNITY_PREVIEW_NGINX_UID'])
COOKIE='__Host-xj_community_preview'
fixtures.CommunityReportJourney.setUpClass()
fx=fixtures.CommunityReportJourney();fx.setUp()
fx.fx.gateway.commerce=fx.commerce
fx.basket()
trusted=TrustedNginxSource(NGINX_UID)
Base=make_handler(fx.fx.gateway,proxy_origin=ORIGIN,trusted_proxy=trusted,operations=fx.ops,communities=fx.communities,commerce=fx.commerce)
ROLE_ROUTES={'/merchant':('/merchant/workbench','merchant'),'/community':('/community/portal','community'),'/platform':('/community/portal','platform')}
class Handler(Base):
    def _trusted(self):
        try:return trusted(self.connection,self.headers)
        except Exception:
            self.answer(403,{'error':'PROXY_DENIED'});return None
    def _preview_html(self):
        raw=b"""<!doctype html><meta charset="utf-8"><title>Community Preview</title><h1>Community Preview</h1><p>Synthetic identities/data. Mock WeChat exchange. Payment disabled. Finance UNCONFIRMED.</p><ul><li><a href="/merchant">Merchant Workbench</a></li><li><a href="/community">Community Portal</a></li><li><a href="/platform">Platform Portal</a></li></ul>"""
        self.send_response(200)
        for k,v in [('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(raw))),('Cache-Control','no-store'),('Referrer-Policy','no-referrer'),('X-Content-Type-Options','nosniff')]:self.send_header(k,v)
        self.end_headers();self.wfile.write(raw);self.close_connection=True
    def do_GET(self):
        if self.path in ('/','/index.html'):
            if self._trusted() is None:return
            return self._preview_html()
        if self.path in ROLE_ROUTES:
            if self._trusted() is None:return
            target,workspace=ROLE_ROUTES[self.path]
            context=urllib.parse.quote(json.dumps({'csrf':fx.web['csrf'],'workspace':workspace},separators=(',',':')))
            self.send_response(302)
            self.send_header('Set-Cookie',COOKIE+'='+fx.web['token']+'; Path=/; Secure; HttpOnly; SameSite=Strict')
            self.send_header('Location',target+'#preview='+context)
            self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
            self.end_headers();self.close_connection=True;return
        return super().do_GET()
    def do_POST(self):
        cookie=self.headers.get('Cookie','');token='';kept=[]
        for part in cookie.split(';'):
            name,sep,value=part.strip().partition('=')
            if name==COOKIE:
                if token or not sep:return self.answer(400,{'error':'AMBIGUOUS_HEADERS'})
                token=value
            elif name!='__Host-xj_customer' and part.strip():kept.append(part.strip())
        if '__Host-xj_customer=' in cookie:return self.answer(403,{'error':'PRODUCTION_COOKIE_DENIED'})
        if token:
            if self.headers.get('X-Center-Session'):return self.answer(400,{'error':'AMBIGUOUS_HEADERS'})
            self.headers['X-Center-Session']=token
            if self.headers.get('Cookie'):self.headers.replace_header('Cookie','; '.join(kept))
        return super().do_POST()
class Server(socketserver.UnixStreamServer):
    request_queue_size=64;allow_reuse_address=False
if SOCKET.exists():SOCKET.unlink()
server=Server(str(SOCKET),Handler);os.chmod(SOCKET,0o660)
try:server.serve_forever(poll_interval=.1)
finally:
    server.server_close()
    try:SOCKET.unlink()
    except FileNotFoundError:pass
    fx.tearDown()
