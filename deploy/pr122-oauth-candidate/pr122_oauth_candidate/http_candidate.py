"""Loopback-only HTTP adapter candidate. Provider calls are disabled by default.

No production CLI or installer: custody, old route successors and independent
review must be complete before release. Never pass a trading runtime root.
"""
import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import core, oauth

ORIGIN = 'https://wenwenwenyiyiyi.work'
HOST = 'wenwenwenyiyiyi.work'
_server_lock = threading.RLock()
_active_server = None


class CandidateServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # No traceback may disclose a secret, form body or OAuth query.
        pass

    def server_close(self):
        global _active_server
        super().server_close()
        with _server_lock:
            if _active_server is self:
                _active_server = None


class Handler(BaseHTTPRequestHandler):
    server_version = 'PR122OAuthCandidate'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass

    def reply(self, status, body, headers=None, content_type='application/json'):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=True, sort_keys=True)
        data = body.encode('utf-8')
        self.send_response(status)
        for key, value in core.secure_headers().items():
            self.send_header(key, value)
        for key, value in (headers or {}).items():
            if key.lower() not in {k.lower() for k in core.secure_headers()}:
                self.send_header(key, value)
        self.send_header('Content-Type', content_type+'; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def deny(self, status=503, reason='ROUTE_SUCCESSOR_NOT_ACCEPTED'):
        self.reply(status, {'status':'UNKNOWN', 'reason':reason})

    def boundary(self):
        if (self.headers.get_all('Host') != [HOST]
                or self.headers.get_all('X-Forwarded-Proto') != ['https']):
            self.deny(400,'HOST_OR_TLS_ORIGIN_INVALID')
            return False
        return True

    def do_GET(self):
        if not self.boundary():
            return
        try:
            with self.server.state_lock:
                self.get_route()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception:
            self.deny(503,'BOUNDED_HANDLER_FAILURE_PRESERVE_STATE')

    def get_route(self):
        parsed = urllib.parse.urlsplit(self.path)
        service = self.server.portal_service
        if parsed.path == '/healthz':
            self.reply(200,{'status':'OFFLINE_HTTP_CANDIDATE',
                            'production_accepted':False, 'trading_enabled':False})
            return
        for filename, body in oauth.TIKTOK_URL_PROPERTY_VERIFICATION_FILES.items():
            if parsed.path in {'/'+filename,'/p/'+filename,'/integrations/'+filename}:
                self.reply(200,body,content_type='text/plain')
                return
        if parsed.path == '/integrations/tiktok/status':
            self.reply(200,oauth.tiktok_connection_status())
            return
        match = re.fullmatch(r'/p/([A-Za-z0-9_-]{1,160})',parsed.path)
        if match:
            session = service.sessions.get(match.group(1))
            forms = tuple(session.required_credential_types) if session else ()
            if len(forms) != 1 or forms[0] not in {'douyin','tiktok'}:
                self.deny(404,'OAUTH_SESSION_NOT_FOUND')
                return
            result = getattr(oauth,'render_'+forms[0]+'_page')(service,match.group(1))
            status, headers, body = result if len(result)==3 else (result[0],{},result[1])
            self.reply(status,body,headers,content_type='text/html')
            return
        callbacks = {oauth.DOUYIN_REDIRECT_PATH:oauth.handle_douyin_oauth_callback,
                     oauth.TIKTOK_REDIRECT_PATH:oauth.handle_tiktok_oauth_callback}
        if parsed.path in callbacks or parsed.path == oauth.TIKTOK_OAUTH_START_PATH:
            if not self.server.provider_calls_enabled:
                self.deny(503,'PROVIDER_CALLS_NOT_RELEASED')
                return
            if parsed.path == oauth.TIKTOK_OAUTH_START_PATH:
                url, failure = oauth.handle_tiktok_oauth_start(service,ORIGIN)
                if url:
                    self.reply(302,'',{'Location':url})
                else:
                    self.reply(400,failure)
            else:
                query = urllib.parse.parse_qs(parsed.query,keep_blank_values=True,max_num_fields=16)
                result = callbacks[parsed.path](service,ORIGIN,query)
                self.reply(200 if result.get('status')=='PASS' else 400,result)
            return
        self.deny()

    def do_POST(self):
        if not self.boundary():
            return
        path = urllib.parse.urlsplit(self.path).path
        if path not in {'/submit/douyin','/submit/tiktok'}:
            self.deny()
            return
        if self.headers.get_all('Origin') != [ORIGIN]:
            self.deny(403,'ORIGIN_INVALID')
            return
        lengths = self.headers.get_all('Content-Length') or []
        if len(lengths)!=1 or not re.fullmatch(r'[0-9]{1,5}',lengths[0]) or 'Transfer-Encoding' in self.headers:
            self.deny(400,'INVALID_BODY_FRAMING')
            return
        length = int(lengths[0])
        if length > 8192:
            self.deny(413,'REQUEST_TOO_LARGE')
            return
        if self.headers.get_content_type() != 'application/x-www-form-urlencoded':
            self.deny(415,'FORM_CONTENT_TYPE_REQUIRED')
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                self.deny(400,'INCOMPLETE_BODY')
                return
            form = urllib.parse.parse_qs(raw.decode('utf-8'),keep_blank_values=True,max_num_fields=24)
            if any(len(values)!=1 for values in form.values()):
                self.deny(400,'DUPLICATE_FORM_FIELD')
                return
            payload = {key:values[0] for key,values in form.items()}
            with self.server.state_lock:
                result = getattr(self.server.portal_service,'submit_'+path.rsplit('/',1)[1])(
                    payload.get('session_id',''),payload.get('csrf_token',''),ORIGIN,payload)
            if result.get('status') == 'CONFIGURED':
                self.reply(200,{'status':'CONFIGURED','returns_secret':False})
            else:
                self.reply(400,{'status':'REJECTED','reason':result.get('sanitized_error_code') or result.get('reason') or 'FORM_REJECTED'})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except (UnicodeError, ValueError):
            self.deny(400,'INVALID_FORM')
        except Exception:
            self.deny(503,'BOUNDED_HANDLER_FAILURE_PRESERVE_STATE')


def make_server(state_root, operations_root, *, port=0, provider_calls_enabled=False):
    """One instance per process: original OAuth helpers use a global state root.

    Enabling provider calls is an unapproved candidate capability, not a release
    gate. Tests use fake transports only. No launch or root install is supplied.
    """
    global _active_server
    with _server_lock:
        if _active_server is not None:
            raise RuntimeError('ONE_STATE_ROOT_PER_PROCESS')
        service = core.SecureSecretsPortalService(state_root,operations_root)
        oauth.configure_state_root(state_root)
        server = CandidateServer(('127.0.0.1',port),Handler)
        server.portal_service = service
        server.state_lock = threading.Lock()
        server.provider_calls_enabled = provider_calls_enabled
        _active_server = server
        return server
