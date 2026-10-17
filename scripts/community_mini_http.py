"""Local transport for real-provider MiniGateway testing; no production listener.

A deployment must terminate trusted HTTPS separately and supply admitted Identity.
No direct callback, payment submission or root/host operation exists here.
"""
import json
import math
import socket
import time
from http.server import BaseHTTPRequestHandler,HTTPServer
from scripts.community_demo_api import _HeaderDeadlineReader
from scripts.community_mini_login import LoginUnavailable


def make_handler(gateway):
    class Handler(BaseHTTPRequestHandler):
        server_version='CommunityMiniCandidate'
        sys_version=''
        def log_message(self,*args):pass
        def setup(self):
            super().setup();self.rfile.close();self.rfile=_HeaderDeadlineReader(self.connection)
        def answer(self,status,value):
            raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status)
            for k,v in [('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(raw))),
                        ('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),
                        ('Content-Security-Policy',"default-src 'none'")]:self.send_header(k,v)
            self.end_headers();self.wfile.write(raw);self.close_connection=True
        def do_POST(self):
            host='127.0.0.1:'+str(self.server.server_port)
            if (self.headers.get_all('Host') != [host] or
                    self.headers.get('Origin') not in (None,'http://'+host)):
                return self.answer(403,{'error':'ORIGIN_DENIED'})
            if self.path not in ('/mini/login','/mini/api','/mini/logout','/mini/bind'):
                return self.answer(404,{'error':'NOT_FOUND'})
            if (self.headers.get('Transfer-Encoding') is not None or
                    len(self.headers.get_all('Content-Length',[])) != 1 or
                    any(len(self.headers.get_all(h,[])) > 1 for h in
                        ('X-Community-Session','X-Center-Session','X-Center-CSRF'))):
                return self.answer(400,{'error':'AMBIGUOUS_HEADERS'})
            if self.headers.get('Content-Type','').split(';')[0].lower() != 'application/json':
                return self.answer(415,{'error':'JSON_REQUIRED'})
            try:
                length=int(self.headers.get('Content-Length','-1'))
                if not 0 < length <= 16384:raise ValueError('INVALID_LENGTH')
                remaining=length;chunks=[];deadline=time.monotonic()+1
                while remaining:
                    budget=deadline-time.monotonic()
                    if budget<=0:raise socket.timeout()
                    self.connection.settimeout(budget)
                    part=self.rfile.read1(remaining)
                    if not part:raise ValueError('TRUNCATED_BODY')
                    chunks.append(part);remaining-=len(part)
                def pairs(items):
                    result={}
                    for k,v in items:
                        if k in result:raise ValueError('DUPLICATE_JSON')
                        result[k]=v
                    return result
                def finite(token):
                    value=float(token)
                    if not math.isfinite(value):raise ValueError('NONFINITE')
                    return value
                body=json.loads(b''.join(chunks),object_pairs_hook=pairs,parse_float=finite,
                                parse_constant=lambda _:(_ for _ in ()).throw(ValueError('NONFINITE')))
                token=self.headers.get('X-Community-Session','')
                if self.path=='/mini/bind':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=gateway.bind(self.headers.get('X-Center-Session',''),
                                        self.headers.get('X-Center-CSRF',''),body)
                elif self.path=='/mini/login':result=gateway.login(body)
                elif self.path=='/mini/logout':
                    if body!={} or type(body) is not dict:raise ValueError('INVALID_BODY')
                    result=gateway.logout(token)
                else:result=gateway.dispatch(token,body)
                return self.answer(200,{'result':result,'payment_enabled':False})
            except LoginUnavailable:return self.answer(503,{'error':'LOGIN_UNKNOWN_OR_REJECTED'})
            except PermissionError:return self.answer(403,{'error':'ACCESS_DENIED'})
            except (ValueError,TypeError,KeyError):return self.answer(400,{'error':'INVALID_REQUEST'})
            except (socket.timeout,TimeoutError):return self.answer(408,{'error':'REQUEST_TIMEOUT'})
            except Exception:return self.answer(503,{'error':'SERVICE_UNAVAILABLE'})
    return Handler


def serve(gateway,port=0):
    if type(port) is not int or not (port==0 or 1024 <= port <= 65535):raise ValueError('INVALID_PORT')
    return HTTPServer(('127.0.0.1',port),make_handler(gateway))
