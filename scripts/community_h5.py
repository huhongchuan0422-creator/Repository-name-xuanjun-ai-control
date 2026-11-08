"""Isolated H5 composition. Host must explicitly compose it; no installation.

Original Center cookies, original applicant and consumer services. No admin
review endpoints, registration, provider payments or synthetic production data.
"""
import json
from scripts.community_web_session import WebSession, token as cookie_token
from scripts.community_h5_context import authorized
from scripts.community_mini_merchant import MiniMerchant
from scripts.community_license_region import RegionValidationError
from scripts.pr122_customer_core import Denied

def credentials(center, headers):
    token = cookie_token(headers)
    values = headers.get_all('X-CSRF-Token', [])
    if len(values) != 1 or ',' in values[0] or not values[0]:
        raise PermissionError('CSRF_REQUIRED')
    center.session(token, values[0])
    return token, values[0]

class H5:
    def __init__(self, gateway, onboarding, merchant):
        if type(merchant) is not MiniMerchant or merchant.identity is not gateway.identity or merchant.onboarding is not onboarding:
            raise PermissionError('SAME_ORIGINAL_SERVICES_REQUIRED')
        self.gateway, self.onboarding, self.merchant = gateway, onboarding, merchant
        self.center = gateway.identity.center
        self.session = WebSession(self.center, operations=merchant.operations, onboarding=onboarding)

    def dispatch(self, path, headers, body, source='h5-original-http'):
        if path in ('/h5/session/login','/h5/session/check','/h5/session/logout'):
            result,cookie = self.session.dispatch(path.replace('/h5/','/community/'),headers,body,source)
            # Navigation is consumer/applicant-only; no staff authority projected.
            if path.endswith('/check'):result={'user_id':result['user_id']}
            return result,cookie
        session,csrf=credentials(self.center,headers)
        if path=='/h5/platform':
            if type(body) is not dict or body:raise ValueError('EMPTY_PLATFORM_BODY_REQUIRED')
            return {'appid':self.gateway.identity.appid,'source':'ORIGINAL_CENTER_CONFIGURATION'},None
        with authorized(self.gateway.identity,session,csrf):
            if path=='/h5/api':
                if type(body) is not dict or set(body)!={'scene','operation','params'}:raise ValueError('EXACT_H5_BODY_REQUIRED')
                # Reuse consumer dispatcher and live original ownership checks.
                return self.gateway.dispatch(session,body),None
            if path=='/h5/merchant':
                if type(body) is not dict or set(body)!={'scene','operation','params'}:raise ValueError('EXACT_H5_BODY_REQUIRED')
                return self.merchant.dispatch(session,body['scene'],{k:body[k] for k in ('operation','params')}),None
            if path=='/h5/project-materials':
                if type(body) is not dict or set(body)!={'scene','params'}:raise ValueError('EXACT_H5_BODY_REQUIRED')
                return self.gateway.commerce.project_document_upload(session,body['scene'],body['params']),None
        raise PermissionError('H5_ROUTE_DENIED')

def make_handler(h5, dist):
    """Serial original owner-thread-compatible HTTP handler for isolated testing.
    Production TLS/origin and existing installation admission remain required.
    """
    import http.server
    from pathlib import Path
    from urllib.parse import urlsplit
    root=Path(dist).resolve()
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def answer(self,status,value,cookie=None):
            raw=json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)))
            if cookie:self.send_header('Set-Cookie',cookie)
            self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            path=urlsplit(self.path).path
            if not path.startswith('/h5/'):return self.answer(404,{'error':'NOT_FOUND'})
            rel=path[len('/h5/'):] or 'index.html'
            target=(root/rel).resolve()
            if root not in target.parents or not target.is_file():return self.answer(404,{'error':'NOT_FOUND'})
            raw=target.read_bytes();self.send_response(200)
            import mimetypes
            self.send_header('Content-Type',mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            try:
                origin=self.headers.get('Origin')
                if origin and urlsplit(origin).netloc != self.headers.get('Host'):raise PermissionError('SAME_ORIGIN_REQUIRED')
                if self.headers.get('Sec-Fetch-Site')=='cross-site':raise PermissionError('SAME_ORIGIN_REQUIRED')
                lengths=self.headers.get_all('Content-Length',[])
                if len(lengths)!=1 or not lengths[0].isdigit() or self.headers.get('Transfer-Encoding'):raise ValueError('EXACT_LENGTH_REQUIRED')
                if self.headers.get_content_type()!='application/json':raise ValueError('JSON_REQUIRED')
                def pairs(items):
                    d={}
                    for k,v in items:
                        if k in d:raise ValueError('DUPLICATE_KEY')
                        d[k]=v
                    return d
                remaining=int(lengths[0]);chunks=[]
                while remaining:
                    part=self.rfile.read1(remaining)
                    if not part:raise ValueError('TRUNCATED_BODY')
                    chunks.append(part);remaining-=len(part)
                body=json.loads(b''.join(chunks),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('FINITE_JSON_REQUIRED')))
                result,cookie=h5.dispatch(self.path,self.headers,body,self.client_address[0])
                self.answer(200,{'result':result,'payment_enabled':False},cookie)
            except (BrokenPipeError,ConnectionResetError):return
            except PermissionError as error:
                # Preserve the exact original rate limit, but do not misreport it
                # as account revocation. No threshold/window or authority changes.
                if type(error) is Denied and str(error)=='RATE_LIMIT':return self.answer(429,{'error':'RATE_LIMIT'})
                from scripts.community_ocr_host import OcrPublicError
                from scripts.community_wechat_applyment import WechatMediaUnavailable
                self.answer(403,error.public_payload() if type(error) is OcrPublicError else {'error':'WECHAT_MEDIA_UNAVAILABLE' if type(error) is WechatMediaUnavailable else 'ACCESS_DENIED'})
            except RegionValidationError as error:self.answer(400,{'error':'MINI_LICENSE_REGION_INVALID','reason':error.reason,'message':str(error),'correction_step':error.correctionStep})
            except (ValueError,TypeError,KeyError):self.answer(400,{'error':'INVALID_REQUEST'})
            except Exception:self.answer(503,{'error':'SERVICE_UNAVAILABLE'})
    return Handler

def with_existing_handler(original_handler, h5, dist):
    """Mount H5 alongside the ORIGINAL server, without replacing mini/admin routes.

    Caller supplies the already-composed original services and handler. This
    function starts no server, changes no configuration or permissions, and
    preserves the original handler's response method on all non-H5 requests.
    """
    import types
    h5_handler=make_handler(h5,dist)
    class Combined(original_handler):
        def _h5(self,method):
            previous=self.answer
            self.answer=types.MethodType(h5_handler.answer,self)
            try:return method(self)
            finally:self.answer=previous
        def do_GET(self):
            if self.path.startswith('/h5/'):
                return self._h5(h5_handler.do_GET)
            return super().do_GET()
        def do_POST(self):
            if self.path.startswith('/h5/'):
                return self._h5(h5_handler.do_POST)
            return super().do_POST()
    return Combined
