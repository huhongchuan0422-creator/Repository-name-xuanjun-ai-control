"""Anonymous, per-session synthetic preview gateway. Never a payment service.

Binds loopback only; production requests require the fixed HTTPS host and
unchanged same-origin Origin. Stores are fresh in-memory demo fixtures.
"""
import argparse
import http.cookies
import json
import math
import secrets
import sqlite3
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.community_demo_api import DemoService, server_database, _HeaderDeadlineReader
from scripts.community_demo_bootstrap import fixture_stores, DEMO_SCOPE
from scripts.community_local_admin import LocalAdminPolicy, dispatch_local_admin
from scripts.community_refund_preview_store import open_refund_store

HOST='wenwenwenyiyiyi.work'
PREFIX='/_preview/community-api'
COOKIE='xj_community_preview'
TTL=900
MAX_SESSIONS=64
ROUTES={'/orders','/orders/state','/orders/simulate','/storefront','/orders/list','/ads/list','/orders/summary','/refunds/preview','/refunds/record-preview','/qr/create','/qr/verify','/qr/checkout','/splits/preview','/reconciliation/preview','/admin/profile','/admin/item','/admin/campaign/create','/admin/campaign/state','/admin/campaign/review'}

class Session:
    def __init__(self):
        self.opened=[]
        try:
            db=server_database(':memory:');self.opened.append(db)
            merchant,ads,now=fixture_stores();self.opened.extend((merchant,ads))
            source=open_refund_store()
            try:
                refund=sqlite3.connect(':memory:',check_same_thread=False);self.opened.append(refund);source.backup(refund)
            finally:source.close()
            self.merchant=secrets.token_urlsafe(32);self.platform=secrets.token_urlsafe(32)
            self.service=DemoService(db,merchant,ads,now,refund,secrets.token_bytes(32),LocalAdminPolicy(self.merchant,self.platform,DEMO_SCOPE))
            self.expires=time.monotonic()+TTL
        except BaseException:
            self.close();raise
    def close(self):
        for connection in reversed(self.opened):
            try:connection.close()
            except sqlite3.Error:pass
        self.opened=[]

class PreviewServer(HTTPServer):
    def __init__(self,port=18793,test_mode=False):
        self.sessions={};self.test_mode=test_mode
        super().__init__(('127.0.0.1',port),Handler)
    def clean(self):
        for key in list(self.sessions):
            if self.sessions[key].expires<=time.monotonic():self.sessions.pop(key).close()
    def server_close(self):
        for session in self.sessions.values():session.close()
        self.sessions.clear();super().server_close()

class Handler(BaseHTTPRequestHandler):
    server_version='XuanjunSyntheticPreview';sys_version=''
    def setup(self):
        super().setup();self.rfile.close();self.rfile=_HeaderDeadlineReader(self.connection)
    def log_message(self,*args):pass
    def origin(self):
        return 'http://127.0.0.1:'+str(self.server.server_port) if self.server.test_mode else 'https://'+HOST
    def allowed(self,post=False):
        expected=self.origin().split('://',1)[1]
        if self.headers.get('Host')!=expected:return False
        if not self.server.test_mode and self.headers.get('X-Forwarded-Proto')!='https':return False
        if post and self.headers.get('Origin')!=self.origin():return False
        return self.headers.get('Sec-Fetch-Site') not in ('cross-site',)
    def session(self,create=False):
        self.server.clean();raw=self.headers.get('Cookie','')
        if raw.count(COOKIE+'=')>1:raise PermissionError('DUPLICATE_SESSION_COOKIE')
        cookie=http.cookies.SimpleCookie()
        try:cookie.load(raw)
        except http.cookies.CookieError:raise PermissionError('INVALID_SESSION_COOKIE')
        token=cookie[COOKIE].value if COOKIE in cookie else ''
        if token in self.server.sessions:return token,self.server.sessions[token],False
        if not create:raise PermissionError('PREVIEW_SESSION_REQUIRED')
        if len(self.server.sessions)>=MAX_SESSIONS:raise OverflowError('PREVIEW_CAPACITY_REACHED')
        token=secrets.token_urlsafe(32);session=Session();self.server.sessions[token]=session
        return token,session,True
    def do_GET(self):
        if not self.allowed():return self.answer(403,{'error':'ORIGIN_DENIED'})
        if self.path!=PREFIX+'/session':return self.answer(404,{'error':'NOT_FOUND'})
        try:
            token,session,new=self.session(True)
            # These are capabilities for this visitor's synthetic fixture only.
            return self.answer(200,{'simulation_only':True,'provider_connected':False,'merchant_demo_capability':session.merchant,'platform_demo_capability':session.platform},token if new else None)
        except PermissionError as e:return self.answer(403,{'error':str(e)})
        except OverflowError as e:return self.answer(503,{'error':str(e)})
    def do_POST(self):
        if not self.allowed(True):return self.answer(403,{'error':'ORIGIN_DENIED'})
        if not self.path.startswith(PREFIX+'/') or self.path.removeprefix(PREFIX) not in ROUTES:return self.answer(404,{'error':'NOT_FOUND'})
        try:
            _,session,_=self.session()
            if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':return self.answer(415,{'error':'JSON_REQUIRED'})
            length=int(self.headers.get('Content-Length','-1'))
            if not 0<length<=2048:raise ValueError('INVALID_BODY_SIZE')
            deadline=time.monotonic()+1.0;raw=bytearray()
            while len(raw)<length:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('BODY_TIMEOUT')
                self.connection.settimeout(remaining);chunk=self.rfile.read1(length-len(raw))
                if not chunk:raise ValueError('INCOMPLETE_BODY')
                raw.extend(chunk)
            def pairs(items):
                result={}
                for key,value in items:
                    if key in result:raise ValueError('DUPLICATE_JSON_KEY')
                    result[key]=value
                return result
            def number(token):
                value=float(token)
                if not math.isfinite(value):raise ValueError('NONFINITE_JSON')
                return value
            data=json.loads(raw,object_pairs_hook=pairs,parse_float=number,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
            route='/demo'+self.path.removeprefix(PREFIX)
            if route.startswith('/demo/admin/'):
                result=dispatch_local_admin(session.service,route,data,self.headers.get('X-Local-Admin-Capability'))
            else:result=session.service.dispatch('POST',route,data)
            return self.answer(200,result)
        except PermissionError as e:return self.answer(403,{'error':str(e)})
        except (ValueError,TypeError,KeyError,OverflowError,sqlite3.Error):return self.answer(400,{'error':'PREVIEW_REQUEST_REJECTED'})
        except TimeoutError:return self.answer(408,{'error':'REQUEST_TIMEOUT'})
    def answer(self,status,value,new_token=None):
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode();self.send_response(status)
        for k,v in [('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(raw))),('Cache-Control','no-store'),('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'"),('X-Content-Type-Options','nosniff')]:self.send_header(k,v)
        if new_token:
            self.send_header('Set-Cookie',COOKIE+'='+new_token+'; Path=/_preview/; HttpOnly; SameSite=Strict; Max-Age=900'+('' if self.server.test_mode else '; Secure'))
        self.end_headers();self.wfile.write(raw)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=18793);a=p.parse_args()
    if not 1024<=a.port<=65535:p.error('Unprivileged loopback port required')
    server=PreviewServer(a.port)
    try:server.serve_forever()
    finally:server.server_close()
