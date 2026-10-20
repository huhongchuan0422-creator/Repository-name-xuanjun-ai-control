"""Isolated customer-facing community preview service.

Development preview only. Uses the existing Center/Stage/Commerce/Community code
with synthetic fixture data. No real customer data, provider payment, Finance
settlement, production database, or public release authority is present.
"""
import json, os, sys, urllib.parse, socketserver
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]

import test_community_reports as fixtures
from scripts.community_mini_http import make_handler
from scripts.pr122_customer_source import TrustedNginxSource

ORIGIN=os.environ.get('COMMUNITY_PREVIEW_ORIGIN','https://wenwenwenyiyiyi.work')
SOCKET=Path(os.environ.get('COMMUNITY_PREVIEW_SOCKET','/run/xuanjun-community-preview/preview.sock'))
NGINX_UID=int(os.environ['COMMUNITY_PREVIEW_NGINX_UID'])

fixtures.CommunityReportJourney.setUpClass()
fx=fixtures.CommunityReportJourney();fx.setUp()
fx.fx.gateway.commerce=fx.commerce
# Seed one authentic synthetic Center order through the existing consumer path.
fx.basket()

trusted=TrustedNginxSource(NGINX_UID)
Base=make_handler(fx.fx.gateway,proxy_origin=ORIGIN,trusted_proxy=trusted,
                  operations=fx.ops,communities=fx.communities,commerce=fx.commerce)

class Handler(Base):
    def _preview_html(self):
        raw=b"""<!doctype html><meta charset="utf-8"><title>Community Preview</title>
<h1>Community Preview</h1><p>Isolated synthetic data. Payment disabled. Finance unconfirmed.</p>
<ul><li><a href="/preview/merchant">Merchant Workbench</a></li>
<li><a href="/preview/community">Community Portal</a></li>
<li><a href="/preview/platform">Platform Portal</a></li></ul>"""
        self.send_response(200)
        for k,v in [('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(raw))),
                    ('Cache-Control','no-store'),('Referrer-Policy','no-referrer'),
                    ('X-Content-Type-Options','nosniff')]:self.send_header(k,v)
        self.end_headers();self.wfile.write(raw);self.close_connection=True

    def do_GET(self):
        if self.path in ('/preview','/preview/'):
            try: trusted(self.connection,self.headers)
            except Exception: return self.answer(403,{'error':'PROXY_DENIED'})
            return self._preview_html()
        routes={'/preview/merchant':('/merchant/workbench','merchant'),
                '/preview/community':('/community/portal','community'),
                '/preview/platform':('/community/portal','platform')}
        if self.path in routes:
            try: trusted(self.connection,self.headers)
            except Exception: return self.answer(403,{'error':'PROXY_DENIED'})
            target,workspace=routes[self.path]
            context=urllib.parse.quote(json.dumps({'csrf':fx.web['csrf'],'workspace':workspace},
                                    separators=(',',':')))
            self.send_response(302)
            self.send_header('Set-Cookie','__Host-xj_customer='+fx.web['token']+
                             '; Path=/; Secure; HttpOnly; SameSite=Strict')
            self.send_header('Location',target+'#preview='+context)
            self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','no-referrer')
            self.end_headers();self.close_connection=True
            return
        return super().do_GET()

class Server(socketserver.UnixStreamServer):
    request_queue_size=64
    allow_reuse_address=False

if SOCKET.exists(): SOCKET.unlink()
server=Server(str(SOCKET),Handler)
os.chmod(SOCKET,0o660)
try:
    server.serve_forever(poll_interval=.1)
finally:
    server.server_close()
    try: SOCKET.unlink()
    except FileNotFoundError: pass
    fx.tearDown()
