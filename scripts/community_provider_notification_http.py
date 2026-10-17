"""Bounded raw WeChat notification intake into the original pending review store.

Official JSAPI partner callback: https://pay.wechatpay.cn/doc/v3/partner/4012085146
204 acknowledges durable evidence intake only, never settlement. No public
listener, funding request, refund, split or automatic entitlement is created.
"""
import hashlib
import socket
import time
from scripts.community_mini_http import make_handler as mini_handler
from scripts.community_saas_provider_evidence import SaasProviderEvidence
from scripts.community_saas_offline_handoff import canonical
from scripts.community_saas_phase2 import Principal


def notification_path(inbox,tenant_id,order_id):
    if type(inbox) is not SaasProviderEvidence:raise ValueError('EXISTING_EVIDENCE_INTAKE_REQUIRED')
    binding=inbox.orders.get((tenant_id,order_id))
    if binding is None:raise PermissionError('INVOICE_BINDING_REQUIRED')
    key=hashlib.sha256(canonical([inbox.merchant,tenant_id,order_id,binding])).hexdigest()
    return '/wechat/notify/'+key


def make_handler(inbox,principal,*,https_origin,trusted_proxy):
    if type(inbox) is not SaasProviderEvidence:raise ValueError('EXISTING_EVIDENCE_INTAKE_REQUIRED')
    if type(principal) is not Principal or principal not in inbox.runtime.bindings or principal.role!='PLATFORM_OWNER':
        raise PermissionError('REGISTERED_OWNER_REQUIRED')
    # Reuse the exact pinned HTTPS-origin/proxy constructor checks.
    base=mini_handler(None,proxy_origin=https_origin,trusted_proxy=trusted_proxy)
    routes={notification_path(inbox,t,o):o for t,o in inbox.orders if t==principal.tenant_id}
    if not routes:raise ValueError('SERVER_INVOICE_ROUTES_REQUIRED')
    class Handler(base):
        def reply_notification(self,status):
            body=b'' if status==204 else b'{"code":"FAIL","message":"notification not accepted"}'
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('Connection','close')
            self.end_headers()
            if body:self.wfile.write(body)
            self.close_connection=True
        def do_POST(self):
            try:
                if self.path not in routes:return self.reply_notification(404)
                if self.headers.get_all('Host')!=[https_origin[len('https://'):]] or self.headers.get_all('Origin',[]):
                    return self.reply_notification(403)
                trusted_proxy(self.connection,self.headers)
                headers={};seen=set()
                for name,value in self.headers.items():
                    if name.lower() in seen:raise ValueError('DUPLICATE_HEADER')
                    seen.add(name.lower());headers[name]=value
                if self.headers.get('Transfer-Encoding') is not None or self.headers.get('Content-Type','').split(';')[0].lower()!='application/json':
                    raise ValueError('BOUNDED_JSON_REQUIRED')
                length=self.headers.get('Content-Length','')
                if not length.isascii() or not length.isdigit() or not 0<int(length)<=1048576:
                    raise ValueError('BOUNDED_LENGTH_REQUIRED')
                remaining=int(length);chunks=[];deadline=time.monotonic()+1
                while remaining:
                    budget=deadline-time.monotonic()
                    if budget<=0:raise TimeoutError()
                    self.connection.settimeout(budget)
                    part=self.rfile.read1(remaining)
                    if not part:raise ValueError('TRUNCATED_BODY')
                    chunks.append(part);remaining-=len(part)
                db=inbox.runtime.saas.orders
                old_timeout=db.execute('PRAGMA busy_timeout').fetchone()[0]
                db.execute('PRAGMA busy_timeout=1000')
                try:inbox.receive(principal,routes[self.path],headers,b''.join(chunks))
                finally:db.execute('PRAGMA busy_timeout='+str(old_timeout))
                return self.reply_notification(204)
            except PermissionError:return self.reply_notification(403)
            except (ValueError,TypeError,KeyError):return self.reply_notification(400)
            except (TimeoutError,socket.timeout):return self.reply_notification(408)
            except Exception:return self.reply_notification(503)
    return Handler
