"""Local transport for real-provider MiniGateway testing; no production listener.

A deployment must terminate trusted HTTPS separately and supply admitted Identity.
No direct callback, payment submission or root/host operation exists here.
"""
import json
import os
import re
from pathlib import Path
import math
import socket
import time
from http.server import BaseHTTPRequestHandler,HTTPServer
from scripts.community_demo_api import _HeaderDeadlineReader
from scripts.community_mini_login import LoginUnavailable

def runtime_version():
    """Image-build stamp, never a request header or the preview caller's SHA.

    Old/bare runtimes remain health-checkable but cannot claim version binding.
    The deployment owner still verifies the image digest/OCI revision separately.
    """
    try:
        stamp = Path(__file__).resolve().parents[1] / 'COMMUNITY_SOURCE_SHA'
        if stamp.is_symlink() or not stamp.is_file():return None
        value = stamp.read_text().strip()
        if not re.fullmatch('[0-9a-f]{40}', value):return None
        if os.environ.get('COMMUNITY_SOURCE_SHA') != value:return None
        return value
    except (OSError, UnicodeError):return None


def make_handler(gateway,*,proxy_origin=None,trusted_proxy=None,operations=None,onboarding=None,saas=None,fulfillment=None,provider_actions=None,merchant_bills=None,communities=None,commerce=None,notifications=None):
    source_sha = runtime_version()  # immutable for this running composition
    # Remember admitted dependencies so a lost SaaS backend cannot silently
    # turn a previously full composition into a healthy community-only one.
    saas_required=(getattr(getattr(gateway,'runtime',None),'saas',None) is not None
                   or saas is not None or fulfillment is not None)
    if notifications is not None:
        from scripts.community_payment_notifications import PaymentNotifications
        if type(notifications) is not PaymentNotifications or notifications.payments is not getattr(gateway,'payments',None):
            raise ValueError('SAME_ORIGINAL_PAYMENT_NOTIFICATIONS_REQUIRED')
    if commerce is not None:
        from scripts.community_commerce import Commerce
        if type(commerce) is not Commerce or commerce.identity is not gateway.identity:
            raise ValueError('SAME_ORIGINAL_COMMERCE_REQUIRED')
    if communities is not None:
        from scripts.community_center_communities import CenterCommunities
        if type(communities) is not CenterCommunities or communities.center is not getattr(gateway.identity,'center',None):
            raise ValueError('SAME_CENTER_COMMUNITIES_REQUIRED')
    if merchant_bills is not None:
        from scripts.community_merchant_bills import MerchantBills
        if type(merchant_bills) is not MerchantBills or merchant_bills.actions is not provider_actions:
            raise ValueError('SAME_ORIGINAL_MERCHANT_BILLS_REQUIRED')
    if provider_actions is not None:
        from scripts.community_wechat_sp_actions import ProviderActions
        if type(provider_actions) is not ProviderActions or provider_actions.runtime is not gateway.runtime or provider_actions.center is not getattr(gateway.identity,'center',None):
            raise ValueError('SAME_REGISTERED_PROVIDER_ACTIONS_REQUIRED')
    if fulfillment is not None:
        from scripts.community_saas_fulfillment import SaasFulfillment
        if type(fulfillment) is not SaasFulfillment or fulfillment.runtime is not gateway.runtime or fulfillment.center is not getattr(gateway.identity,'center',None):
            raise ValueError('SAME_REGISTERED_FULFILLMENT_REQUIRED')
    if saas is not None:
        from scripts.community_center_saas import CenterSaas
        if type(saas) is not CenterSaas or saas.runtime is not gateway.runtime or saas.center is not getattr(gateway.identity,'center',None):
            raise ValueError('SAME_REGISTERED_CUSTOMER_SAAS_REQUIRED')
    if onboarding is not None:
        from scripts.community_merchant_onboarding import MerchantOnboarding
        if type(onboarding) is not MerchantOnboarding or onboarding.center is not getattr(gateway.identity,'center',None):
            raise ValueError('SAME_EXISTING_CENTER_ONBOARDING_REQUIRED')
    if operations is not None:
        from scripts.community_center_operations import CenterOperations
        if (type(operations) is not CenterOperations or operations.runtime is not gateway.runtime
                or operations.center is not getattr(gateway.identity,'center',None)):
            raise ValueError('SAME_REGISTERED_OPERATIONS_RUNTIME_REQUIRED')
    if proxy_origin is not None:
        import hashlib
        import re
        from pathlib import Path
        from scripts import pr122_customer_source
        if (type(proxy_origin) is not str or not re.fullmatch(r'https://[A-Za-z0-9.-]+',proxy_origin)
                or type(trusted_proxy) is not pr122_customer_source.TrustedNginxSource
                or hashlib.sha256(Path(pr122_customer_source.__file__).read_bytes()).hexdigest()!=
                '3e8d531ede69577b72b6ee9089fdc8f481b2f91578f19e0e44d1841c168f3471'):
            raise ValueError('PINNED_HTTPS_PROXY_REQUIRED')
    elif trusted_proxy is not None:
        raise ValueError('PROXY_ORIGIN_REQUIRED')
    class Handler(BaseHTTPRequestHandler):
        server_version='CommunityMiniCandidate'
        sys_version=''
        def log_message(self,*args):pass
        def setup(self):
            super().setup();self.rfile.close();self.rfile=_HeaderDeadlineReader(self.connection)
        def answer(self,status,value,*,cookie=None):
            raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status)
            for k,v in [('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(raw))),
                        ('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),
                        ('Content-Security-Policy',"default-src 'none'")]:self.send_header(k,v)
            if cookie is not None:self.send_header('Set-Cookie',cookie)
            self.end_headers();self.wfile.write(raw);self.close_connection=True
        def do_GET(self):
            if self.path!='/community/health' and onboarding is None and operations is None and saas is None and communities is None and commerce is None:return self.answer(404,{'error':'NOT_FOUND'})
            host=proxy_origin[len('https://'):] if proxy_origin else '127.0.0.1:'+str(self.server.server_port)
            if self.headers.get_all('Host')!=[host]:return self.answer(403,{'error':'ORIGIN_DENIED'})
            if trusted_proxy is not None:
                try:trusted_proxy(self.connection,self.headers)
                except Exception:return self.answer(403,{'error':'PROXY_DENIED'})
            if self.path=='/community/health':
                center=getattr(getattr(gateway,'identity',None),'center',None)
                if center is None:return self.answer(503,{'status':'UNAVAILABLE'})
                try:
                    maintenance=center.db.execute("SELECT v FROM settings WHERE k='maintenance'").fetchone()[0]!='0'
                    runtime=gateway.runtime
                    databases=[runtime.demo.db,runtime.demo.merchant_db,
                               runtime.demo.ad_db,runtime.demo.refund_db]
                    backend=getattr(runtime,'saas',None)
                    if saas_required or backend is not None:
                        databases.extend((backend.quotes,backend.orders,backend.modules))
                    # Quotes and modules normally share one original store;
                    # independently composed stores must both be checked too.
                    for db in {id(db):db for db in databases}.values():
                        db.execute('SELECT 1').fetchone()
                except Exception:return self.answer(503,{'status':'UNAVAILABLE'})
                health={'status':'MAINTENANCE' if maintenance else 'READY','scope':'PROCESS_AND_DATABASE_CONNECTIVITY','production_acceptance':False}
                if source_sha is not None:
                    health.update(runtime_source_sha=source_sha,version_source='IMAGE_BUILD_STAMP',
                                  observed_at=int(time.time()))
                return self.answer(503 if maintenance else 200,health)
            if proxy_origin=='https://uk.wenwenwenyiyiyi.work':
                from scripts.community_web_entries import asset,entries
                if self.path=='/community/entrypoints':return self.answer(200,entries(value['project'] for value in gateway.identity.scenes.values()))
                selected=asset(self.path)
                if selected is not None:
                    raw,mime=selected
                    self.send_response(200)
                    for key,value in [('Content-Type',mime),('Content-Length',str(len(raw))),('Cache-Control','no-store'),
                        ('X-Content-Type-Options','nosniff'),('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]:
                        self.send_header(key,value)
                    self.end_headers();self.wfile.write(raw);self.close_connection=True
                    return
            assets={'/merchant/join':('onboarding.html','text/html; charset=utf-8'),
                    '/merchant/review':('onboarding.html','text/html; charset=utf-8'),
                    '/merchant/onboarding.js':('onboarding.js','application/javascript; charset=utf-8'),
                    '/merchant/onboarding.css':('onboarding.css','text/css; charset=utf-8')}
            if onboarding is None:assets={}
            if operations is not None:
                assets.update({'/merchant/workbench':('workbench.html','text/html; charset=utf-8'),
                    '/merchant/workbench.js':('workbench.js','application/javascript; charset=utf-8'),
                    '/merchant/workbench.css':('workbench.css','text/css; charset=utf-8')})
            if saas is not None:
                assets.update({'/customer/saas':('saas.html','text/html; charset=utf-8'),
                    '/customer/saas.js':('saas.js','application/javascript; charset=utf-8'),
                    '/customer/saas.css':('workbench.css','text/css; charset=utf-8')})
            if communities is not None:
                assets.update({'/community/portal':('communities.html','text/html; charset=utf-8'),
                    '/community/portal.js':('communities.js','application/javascript; charset=utf-8'),
                    '/community/portal.css':('workbench.css','text/css; charset=utf-8')})
            if commerce is not None:
                assets.update({'/community/project-review':('project-review.html','text/html; charset=utf-8'),
                    '/community/project-review.js':('project-review.js','application/javascript; charset=utf-8'),
                    '/community/project-review.css':('workbench.css','text/css; charset=utf-8')})
            if self.path not in assets:return self.answer(404,{'error':'NOT_FOUND'})
            from pathlib import Path
            name,mime=assets[self.path]
            raw=(Path(__file__).resolve().parents[1]/'demos'/'community-stage'/name).read_bytes()
            self.send_response(200)
            for key,value in [('Content-Type',mime),('Content-Length',str(len(raw))),('Cache-Control','no-store'),
                    ('X-Content-Type-Options','nosniff'),('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]:
                self.send_header(key,value)
            self.end_headers();self.wfile.write(raw);self.close_connection=True
        def do_POST(self):
            host=proxy_origin[len('https://'):] if proxy_origin else '127.0.0.1:'+str(self.server.server_port)
            if (self.headers.get_all('Host') != [host] or
                    self.headers.get_all('Origin',[]) not in ([],[proxy_origin or 'http://'+host])):
                return self.answer(403,{'error':'ORIGIN_DENIED'})
            if trusted_proxy is not None:
                try:proxy_source=trusted_proxy(self.connection,self.headers)
                except PermissionError:return self.answer(403,{'error':'PROXY_DENIED'})
                except Exception:return self.answer(503,{'error':'PROXY_UNAVAILABLE'})
            web_session=(proxy_origin=='https://uk.wenwenwenyiyiyi.work' and self.path in ('/community/session/login','/community/session/check','/community/session/logout'))
            if web_session and (self.headers.get_all('Origin',[]) != [proxy_origin] or self.headers.get_all('Sec-Fetch-Site',[]) not in ([],['same-origin'])):
                return self.answer(403,{'error':'ORIGIN_DENIED'})
            if not web_session and self.path not in ('/mini/login','/mini/api','/mini/logout','/mini/bind') and not (
                    self.path=='/community/operations' and operations is not None) and not (
                    self.path=='/mini/merchant' and onboarding is not None) and not (
                    self.path=='/mini/payment' and getattr(gateway,'payments',None) is not None) and not (
                    self.path=='/merchant/onboarding' and onboarding is not None) and not (
                    self.path=='/customer/saas-api' and saas is not None) and not (
                    self.path=='/community/fulfillment' and fulfillment is not None) and not (
                    self.path=='/community/provider-actions' and provider_actions is not None) and not (
                    self.path=='/community/merchant-bills' and merchant_bills is not None) and not (
                    self.path=='/community/directory' and communities is not None) and not (
                    self.path=='/community/commerce' and commerce is not None) and not (
                    self.path in ('/mini/project-materials','/community/project-materials') and commerce is not None) and not (
                    notifications is not None and self.path==notifications.path):
                return self.answer(404,{'error':'NOT_FOUND'})
            if (self.headers.get('Transfer-Encoding') is not None or
                    len(self.headers.get_all('Content-Length',[])) != 1 or
                    any(len(self.headers.get_all(h,[])) > 1 for h in
                        ('X-Community-Session','X-Community-Scene','X-Center-Session','X-Center-CSRF','Cookie','X-CSRF-Token'))):
                return self.answer(400,{'error':'AMBIGUOUS_HEADERS'})
            if self.headers.get('Content-Type','').split(';')[0].lower() != 'application/json':
                return self.answer(415,{'error':'JSON_REQUIRED'})
            try:
                length=int(self.headers.get('Content-Length','-1'))
                limit=7_000_000 if self.path=='/merchant/onboarding' else 1048576 if notifications is not None and self.path==notifications.path else 16384
                session=self.headers.get('X-Center-Session','')
                csrf=self.headers.get('X-Center-CSRF','')
                if self.path=='/mini/merchant':
                    from scripts.community_mini_merchant import MiniMerchant
                    if session or csrf or self.headers.get('Cookie') or self.headers.get('X-CSRF-Token') or self.headers.get_all('Authorization',[]):
                        raise PermissionError('MINI_BEARER_SESSION_REQUIRED')
                    mini_merchant=MiniMerchant(gateway.identity,onboarding,operations,getattr(gateway,'collection_codes',None))
                    mini_merchant.context(self.headers.get('X-Community-Session',''),self.headers.get('X-Community-Scene',''))
                    limit=7_000_000
                if self.path=='/mini/project-materials':
                    from scripts.community_project_materials import MAX_UPLOAD_BODY
                    limit=MAX_UPLOAD_BODY
                if not 0 < length <= limit:raise ValueError('INVALID_LENGTH')
                if self.path=='/mini/project-materials':
                    if session or csrf or self.headers.get('Cookie') or self.headers.get('X-CSRF-Token'):
                        raise PermissionError('MINI_BEARER_SESSION_REQUIRED')
                    # Authentication and current project authorization precede
                    # reading any private file bytes, including small uploads.
                    commerce.project_document_authorize(self.headers.get('X-Community-Session',''),
                                                        self.headers.get('X-Community-Scene',''))
                if self.path in ('/merchant/onboarding','/community/operations','/customer/saas-api','/community/fulfillment','/community/provider-actions','/community/merchant-bills','/community/directory','/community/commerce','/community/project-materials'):
                    cookies=[part.strip().partition('=')[2] for part in self.headers.get('Cookie','').split(';')
                             if part.strip().partition('=')[0]=='__Host-xj_customer']
                    if len(cookies)>1 or cookies and session or csrf and self.headers.get('X-CSRF-Token'):
                        raise PermissionError('AMBIGUOUS_CENTER_CREDENTIALS')
                    session=cookies[0] if cookies else session
                    csrf=csrf or self.headers.get('X-CSRF-Token','')
                    # Authenticate before accepting a large private upload body.
                    if session:
                        if not csrf:raise PermissionError('CENTER_CSRF_REQUIRED')
                        {'/merchant/onboarding':onboarding,'/community/operations':operations,'/customer/saas-api':saas,'/community/fulfillment':fulfillment,'/community/provider-actions':provider_actions,'/community/merchant-bills':merchant_bills,'/community/directory':communities,'/community/commerce':commerce,'/community/project-materials':commerce}[self.path].center.session(session,csrf)
                    elif length>16384:raise PermissionError('CENTER_SESSION_REQUIRED')
                remaining=length;chunks=[];deadline=time.monotonic()+1
                while remaining:
                    budget=deadline-time.monotonic()
                    if budget<=0:raise socket.timeout()
                    self.connection.settimeout(budget)
                    part=self.rfile.read1(remaining)
                    if not part:raise ValueError('TRUNCATED_BODY')
                    chunks.append(part);remaining-=len(part)
                if notifications is not None and self.path==notifications.path:
                    if self.headers.get_all('Origin',[]) or self.headers.get('Cookie') or self.headers.get('X-Community-Session') or session or csrf:
                        raise PermissionError('PROVIDER_NOTIFICATION_ONLY')
                    if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':raise ValueError('JSON_NOTIFICATION_REQUIRED')
                    headers={}
                    for name,value in self.headers.items():
                        if name.lower() in headers:raise ValueError('DUPLICATE_PROVIDER_HEADER')
                        headers[name.lower()]=value
                    notifications.receive(headers,b''.join(chunks))
                    return self.answer(200,{'code':'SUCCESS','message':'成功'})
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
                if web_session:
                    from scripts.community_web_session import WebSession
                    result,cookie=WebSession(gateway.identity.center,operations,communities,onboarding).dispatch(self.path,self.headers,body,proxy_source)
                    return self.answer(200,{'result':result,'payment_enabled':False},cookie=cookie)
                token=self.headers.get('X-Community-Session','')
                if self.path=='/mini/merchant':
                    result=mini_merchant.dispatch(token,self.headers.get('X-Community-Scene',''),body)
                    return self.answer(200,{'result':result,'payment_enabled':False})
                if self.path=='/mini/project-materials':
                    result=commerce.project_document_upload(token,self.headers.get('X-Community-Scene',''),body)
                    return self.answer(200,{'result':result,'payment_enabled':False})
                if self.path=='/community/project-materials':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=commerce.project_material_review(session,csrf,body)
                    return self.answer(200,{'result':result,'payment_enabled':False})
                if self.path=='/mini/payment':
                    if session or csrf or self.headers.get('Cookie') or self.headers.get('X-CSRF-Token'):raise PermissionError('MINI_BEARER_SESSION_REQUIRED')
                    result=gateway.payments.dispatch(token,body)
                    return self.answer(200,{'result':result,'payment_enabled':True})
                if self.path=='/merchant/onboarding':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=onboarding.dispatch(session,csrf,body)
                elif self.path=='/community/commerce':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=commerce.dispatch(session,csrf,body)
                elif self.path=='/community/directory':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=communities.dispatch(session,csrf,body)
                elif self.path=='/community/merchant-bills':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=merchant_bills.dispatch(session,csrf,body)
                    return self.answer(200,{'result':result,'payment_enabled':False})
                elif self.path=='/community/provider-actions':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=provider_actions.dispatch(session,csrf,body)
                    return self.answer(200,{'result':result,'provider_actions_enabled':True})
                elif self.path=='/community/fulfillment':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=fulfillment.dispatch(session,csrf,body)
                elif self.path=='/customer/saas-api':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=saas.dispatch(session,csrf,body)
                elif self.path=='/community/operations':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=operations.dispatch(session,csrf,body)
                elif self.path=='/mini/bind':
                    if token:raise PermissionError('CENTER_SESSION_REQUIRED')
                    result=gateway.bind(self.headers.get('X-Center-Session',''),
                                        self.headers.get('X-Center-CSRF',''),body)
                elif self.path=='/mini/login':
                    result=gateway.login(body,source=proxy_source) if trusted_proxy is not None else gateway.login(body)
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


def serve(gateway,port=0,*,operations=None,onboarding=None,saas=None,fulfillment=None,provider_actions=None,merchant_bills=None,communities=None,commerce=None,notifications=None):
    if type(port) is not int or not (port==0 or 1024 <= port <= 65535):raise ValueError('INVALID_PORT')
    return HTTPServer(('127.0.0.1',port),make_handler(gateway,operations=operations,onboarding=onboarding,saas=saas,fulfillment=fulfillment,provider_actions=provider_actions,merchant_bills=merchant_bills,communities=communities,commerce=commerce,notifications=notifications))
