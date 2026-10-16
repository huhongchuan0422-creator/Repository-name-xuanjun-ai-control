"""Same-origin bounded HTTP adapter. Bind loopback; TLS terminated by approved Nginx.
No login/credential/URL/body logging; no public path for private objects.
"""
import base64
import binascii
import json
import re
import socketserver
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from scripts.pr122_customer_core import Center,Denied,Conflict,Unavailable,canonical
from scripts.pr122_customer_source import reject_untrusted,TrustedNginxSource
from scripts.pr122_customer_providers import Providers,enqueue,ai_reply
from scripts.pr122_customer_changes import Changes

PREFIX='/customer/center/'
CSP="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
COOKIE='__Host-xj_customer'

def strict_json(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('DUPLICATE_KEY')
            d[k]=v
        return d
    def reject(_):raise ValueError('NONFINITE_JSON')
    d=json.loads(raw,object_pairs_hook=pairs,parse_constant=reject)
    if type(d) is not dict:raise ValueError('OBJECT_REQUIRED')
    return d

class CustomerUnixServer(socketserver.UnixStreamServer):
    # Bounded queue for bursts; serial request/state semantics stay unchanged.
    request_queue_size=128

class App:
    def __init__(self,factory,providers,origin,assets,*,source_identity=reject_untrusted):
        if origin!='https://wenwenwenyiyiyi.work':raise ValueError('PINNED_ORIGIN_REQUIRED')
        self.factory=factory;self.providers=providers;self.origin=origin;self.assets=Path(assets);self.source_identity=source_identity
    def handler(self):
        app=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def reply(self,status,value,ctype='application/json; charset=utf-8',cookie=None,csp=CSP):
                raw=value if type(value) is bytes else canonical(value)
                self.send_response(status)
                for k,v in [('Content-Type',ctype),('Content-Length',str(len(raw))),('Cache-Control','no-store, private'),('Pragma','no-cache'),('Content-Security-Policy',csp),('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),('X-Frame-Options','DENY'),('Connection','close')]:self.send_header(k,v)
                if cookie:self.send_header('Set-Cookie',cookie)
                if ctype in ('application/pdf','image/png','image/jpeg'):self.send_header('Content-Disposition','attachment; filename="project-material"')
                self.end_headers()
                if self.command!='HEAD':self.wfile.write(raw)
                self.close_connection=True
            def token(self):
                try:
                    c=SimpleCookie();c.load(self.headers.get('Cookie',''));return c[COOKIE].value if COOKIE in c else ''
                except Exception:return ''
            def execute(self):
                center=None
                try:
                    self.connection.settimeout(30)
                    u=urlsplit(self.path)
                    if u.query or u.fragment or '%' in u.path or '//' in u.path or '..' in u.path or self.headers.get('Host')!='wenwenwenyiyiyi.work':raise Denied('INVALID_REQUEST_TARGET')
                    path=u.path
                    if self.command not in ('GET','HEAD','POST'):return self.reply(405,{'error':'METHOD_NOT_ALLOWED'})
                    if self.command in ('GET','HEAD') and path in (PREFIX,PREFIX+'app.css',PREFIX+'app.js',PREFIX+'feedback.js',PREFIX+'feedback.css'):
                        name={'': 'index.html','app.css':'app.css','app.js':'app.js','feedback.js':'feedback.js','feedback.css':'feedback.css'}[path[len(PREFIX):]]
                        raw=(app.assets/name).read_bytes();ctype={'index.html':'text/html; charset=utf-8','app.css':'text/css; charset=utf-8','app.js':'application/javascript; charset=utf-8','feedback.js':'application/javascript; charset=utf-8','feedback.css':'text/css; charset=utf-8'}[name]
                        return self.reply(200,raw,ctype)
                    if not path.startswith((PREFIX+'api/',PREFIX+'preview/')) and path not in (PREFIX+'webhooks/telegram',PREFIX+'webhooks/feishu'):return self.reply(404,{'error':'NOT_FOUND'})
                    body={};raw=b''
                    if self.command=='POST':
                        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:raise ValueError('CONTENT_LENGTH_REQUIRED')
                        length=self.headers.get('Content-Length','')
                        if not re.fullmatch(r'[0-9]{1,8}',length) or not 1<=int(length)<=7_000_000:return self.reply(413,{'error':'REQUEST_TOO_LARGE'})
                        if self.headers.get_content_type()!='application/json':raise ValueError('JSON_REQUIRED')
                        raw=self.rfile.read(int(length))
                        if len(raw)!=int(length):raise ValueError('INCOMPLETE_BODY')
                        if '/webhooks/' not in path:
                            if self.headers.get('Origin')!=app.origin or self.headers.get('Sec-Fetch-Site') not in (None,'same-origin'):raise Denied('ORIGIN_REQUIRED')
                            body=strict_json(raw)
                    center=app.factory()
                    if '/webhooks/' in path:
                        if self.command!='POST':return self.reply(405,{'error':'POST_REQUIRED'})
                        if len(raw)>65536:return self.reply(413,{'error':'EVENT_TOO_LARGE'})
                        if path.endswith('/telegram'):
                            event,subject,text=app.providers.telegram(self.headers,raw);result=center.channel_event('TELEGRAM',event,subject,text)
                        else:
                            value=app.providers.feishu(self.headers,raw)
                            if type(value) is dict:return self.reply(200,value)
                            event,subject,text=value;result=center.channel_event('FEISHU',event,subject,text)
                        return self.reply(200,{'ok':True}) # Never return identity or stored confirmation tokens to provider.
                    operation=path[len(PREFIX+'api/'):]
                    public={'register':({'email','password'},center.register),'verify':({'token','password'},center.verify),'login':({'email','password'},center.login),'request_reset':({'email'},center.request_reset),'reset':({'token','password'},center.reset)}
                    if operation in public:
                        if self.command!='POST':return self.reply(405,{'error':'POST_REQUIRED'})
                        fields,func=public[operation]
                        if set(body)!=fields:raise ValueError('INVALID_FIELDS')
                        origin=app.source_identity(self.connection,self.headers)
                        # Per-source and per-source/account quotas are atomic and
                        # committed before password parsing/authentication failures.
                        account=body.get('email','challenge-operation')
                        if type(account) is not str:raise ValueError('INVALID_ACCOUNT')
                        with center.tx():
                            center.limit('auth-source:'+origin,40,300)
                            center.limit('auth-source-account:'+origin+':'+account.casefold(),12,300)
                        result=func(**body) if operation not in ('register','login','request_reset') else func(*[body[k] for k in ('email','password') if k in body])
                        if operation=='login':
                            cookie=COOKIE+'='+result.pop('token')+'; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=3600'
                            return self.reply(200,result,cookie=cookie)
                        return self.reply(200,result)
                    # Clearing an expired/revoked browser cookie must remain possible.
                    # This operation grants no access; same-origin JSON POST is
                    # mandatory even when the old session can no longer authenticate.
                    if operation=='logout' and self.command=='POST':
                        if body:raise ValueError('INVALID_FIELDS')
                        center.logout(self.token())
                        return self.reply(200,{'logged_out':True},cookie=COOKIE+'=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0')
                    uid=center.session(self.token(),self.headers.get('X-CSRF-Token','') if self.command=='POST' else None)
                    if path.startswith(PREFIX+'preview/'):
                        from scripts.pr122_customer_preview import render,served
                        if self.command not in ('GET','HEAD'):return self.reply(405,{'error':'READ_ONLY_PREVIEW'})
                        parts=path[len(PREFIX+'preview/'):].split('/')
                        if len(parts)!=3:return self.reply(404,{'error':'PREVIEW_NOT_FOUND'})
                        project,page_key,version=parts
                        if self.headers.get('Range') or self.headers.get('If-None-Match') or self.headers.get('If-Modified-Since'):raise Denied('UNCONDITIONAL_PREVIEW_ONLY')
                        rendered,mime,policy=render(center,uid,project,page_key,version)
                        self.reply(200,rendered,mime,csp=policy)
                        if self.command=='GET' and mime.startswith('text/html'):served(center,uid,project,page_key,version,rendered)
                        return
                    if self.command in ('GET','HEAD'):
                        if operation.startswith('previews/'):
                            from scripts.pr122_customer_preview import listing
                            return self.reply(200,listing(center,uid,operation[len('previews/'):]))
                        if operation=='me':return self.reply(200,{'user_id':uid,'projects':center.projects(uid),'channels':app.providers.status()})
                        parts=operation.split('/')
                        if len(parts)==2 and parts[0]=='checklist':return self.reply(200,center.checklist(uid,parts[1]))
                        if len(parts)==2 and parts[0]=='messages':return self.reply(200,{'messages':center.messages(uid,parts[1])})
                        if len(parts)==2 and parts[0]=='changes':return self.reply(200,Changes(center).list(uid,parts[1]))
                        if len(parts)==2 and parts[0]=='pending_links':return self.reply(200,{'links':center.pending_links(uid,parts[1])})
                        if len(parts)==3 and parts[0]=='download':
                            if self.headers.get('Range') or self.headers.get('If-None-Match') or self.headers.get('If-Modified-Since'):raise Denied('UNCONDITIONAL_AUTHORIZED_DOWNLOAD_ONLY')
                            data,mime=center.download(uid,parts[1],parts[2]);return self.reply(200,data,mime)
                        return self.reply(404,{'error':'NOT_FOUND'})
                    operations={
                        'change_updates':({'project','page','version'},lambda:Changes(center).page_updates(uid,body['project'],body['page'],body['version'])),
                        'change_retest':({'project','case','revision','page','version','delivery_sha256','action','reason'},lambda:Changes(center).retest(uid,body['project'],body['case'],body['revision'],body['page'],body['version'],body['delivery_sha256'],body['action'],body['reason'])),
                        'change_context':({'project','page','version'},lambda:Changes(center)._preview(uid,body['project'],body['page'],body['version'])),
                        'change_submit':({'project','page','version','text','intent'},lambda:Changes(center).submit(uid,body['project'],body['page'],body['version'],body['text'],body['intent'])),
                        'change_baseline':({'project','page','version','document_id'},lambda:Changes(center).baseline(uid,body['project'],body['page'],body['version'],body['document_id'])),
                        'change_confirm_new_scope':({'project','case','revision','document_id'},lambda:Changes(center).confirm_new_scope(uid,body['project'],body['case'],body['revision'],body['document_id'])),
                        'change_assess':({'project','case','revision','category','minutes','lines','evidence','explanation'},lambda:Changes(center).assess(uid,body['project'],body['case'],body['revision'],body['category'],body['minutes'],body['lines'],body['evidence'],body['explanation'])),
                        'change_respond':({'project','case','revision','action','reason'},lambda:Changes(center).respond(uid,body['project'],body['case'],body['revision'],body['action'],body['reason'])),
                        'logout':(set(),lambda:center.logout(self.token()) or {'logged_out':True}),
                        'invite':({'project','email','role'},lambda:center.invite(uid,body['project'],body['email'],body['role'])),
                        'accept_invite':({'invitation'},lambda:center.accept_invite(uid,body['invitation'])),
                        'revoke':({'project','user_id'},lambda:center.revoke(uid,body['project'],body['user_id'])),
                        'save':({'project','item','revision','kind','content','expires'},lambda:center.save(uid,body['project'],body['item'],body['revision'],body['kind'],base64.b64decode(body['content'],validate=True) if body['kind']=='DOCUMENT' else body['content'],body['expires'])),
                        'transition':({'project','item','revision','action','reason'},lambda:center.transition(uid,body['project'],body['item'],body['revision'],body['action'],body['reason'])),
                        'message':({'project','body'},lambda:self.webmessage(center,uid,body)),
                        'send':({'project','channel','body'},lambda:enqueue(center,uid,body['project'],body['channel'],body['body'])),
                        'bind':({'project','channel','subject'},lambda:center.binding_challenge(uid,body['project'],body['channel'],body['subject'])),
                        'confirm_link':({'project','challenge_id'},lambda:center.confirm_link(uid,body['project'],body['challenge_id'])),
                        'unlink':({'project','channel'},lambda:center.unlink(uid,body['project'],body['channel']))}
                    if operation not in operations:return self.reply(404,{'error':'NOT_FOUND'})
                    fields,func=operations[operation]
                    if set(body)!=fields:raise ValueError('INVALID_FIELDS')
                    result=func();cookie=COOKIE+'=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0' if operation=='logout' else None
                    return self.reply(200,result,cookie=cookie)
                except Denied:return self.reply(403,{'error':'权限不足、凭据失效或请求不符合要求'})
                except Conflict:return self.reply(409,{'error':'版本或状态已变化，请刷新后重试'})
                except Unavailable:return self.reply(503,{'error':'服务尚未接通或处于维护状态'})
                except (ValueError,KeyError,TypeError,binascii.Error,json.JSONDecodeError,UnicodeError):return self.reply(400,{'error':'请求格式不正确'})
                except Exception:return self.reply(503,{'error':'处理结果未确认，请保留记录并联系支持'})
                finally:
                    if center:center.db.close()
            def webmessage(self,center,uid,body):
                with center.tx():result=center.message(uid,body['project'],body['body'])
                result['ai_response']=ai_reply(center,uid,body['project'],result['id'],app.providers)
                return result
            def do_GET(self):self.execute()
            def do_HEAD(self):self.execute()
            def do_POST(self):self.execute()
            def do_PUT(self):self.execute()
            def do_DELETE(self):self.execute()
            def do_OPTIONS(self):self.execute()
            def do_PATCH(self):self.execute()
        return Handler

def serve(factory,providers,assets):
    # Single-process bounded service serializes permission revocation and outbound
    # work; each request gets a fresh SQLite connection. application limits authenticated writes and credential attempts.
    import grp,os,socketserver
    path=Path('/run/xuanjun-customer-api/http.sock')
    # Private service-owned directory plus pinned Nginx group prevents another
    # local application impersonating a crashed loopback backend.
    if path.exists() or path.is_symlink():raise RuntimeError('SOCKET_EXISTS_INSPECT_FIRST')
    server=CustomerUnixServer(str(path),App(factory,providers,'https://wenwenwenyiyiyi.work',assets,source_identity=TrustedNginxSource(__import__('pwd').getpwnam('nginx').pw_uid)).handler())
    os.chown(path,-1,grp.getgrnam('nginx').gr_gid);os.chmod(path,0o660)
    try:server.serve_forever()
    finally:server.server_close();path.unlink(missing_ok=True)
