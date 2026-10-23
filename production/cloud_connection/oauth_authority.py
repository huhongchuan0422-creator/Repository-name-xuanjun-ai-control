"""Authlib authorization service factory; no automatic service registration.

Runs in a separately pinned Python3.12 environment, not the legacy worker.
Only opaque Authlib tokens; hashes of credentials/codes/tokens are persisted.
"""
import hashlib
import hmac
import json
import math
import re
import secrets
import sqlite3
import time
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit

from flask import Flask, abort, g, jsonify, redirect, request, session
from authlib.integrations.flask_client import OAuth
from authlib.integrations.flask_oauth2 import AuthorizationServer
from authlib.oauth2.rfc6749 import ClientMixin, AuthorizationCodeMixin, TokenMixin
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant, RefreshTokenGrant
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc7662 import IntrospectionEndpoint
from authlib.oauth2.rfc7009 import RevocationEndpoint
from .queue import Hold
from .github_network import GithubApp, GithubNetwork

SCOPES = {'connection.status', 'project.files.read'}
SCHEMA = '''
CREATE TABLE oauth_codes(digest TEXT PRIMARY KEY, client TEXT NOT NULL,
 sub TEXT NOT NULL, redirect TEXT NOT NULL, scope TEXT NOT NULL,
 challenge TEXT NOT NULL, method TEXT NOT NULL, expires INTEGER NOT NULL,
 used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE oauth_tokens(access_hash TEXT PRIMARY KEY, refresh_hash TEXT UNIQUE NOT NULL,
 client TEXT NOT NULL, sub TEXT NOT NULL, scope TEXT NOT NULL,
 issued INTEGER NOT NULL, expires INTEGER NOT NULL, refresh_expires INTEGER NOT NULL,
 family TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE INDEX oauth_token_family ON oauth_tokens(family);
CREATE TABLE oauth_flows(sid_hash TEXT PRIMARY KEY, params TEXT NOT NULL,
 csrf_hash TEXT NOT NULL, sub TEXT, expires INTEGER NOT NULL,
 used INTEGER NOT NULL DEFAULT 0);
'''


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def consent_form_source(uri):
    """Serialize one bounded HTTPS CSP source, never arbitrary header syntax.

    Deliberately supports only query-free ASCII host/path callback URLs. Exact
    OAuth redirect URI matching remains mandatory: CSP redirect checks may
    ignore the source path and are not an authorization boundary.
    """
    if type(uri) is not str or not 1 <= len(uri) <= 2048:
        raise Hold('OAUTH_CONSENT_CSP_SOURCE')
    match = re.fullmatch(r'https://([A-Za-z0-9.-]+)(?::([0-9]{1,5}))?(/(?:[A-Za-z0-9._~/-]|%[0-9A-Fa-f]{2})*)', uri)
    if match is None:
        raise Hold('OAUTH_CONSENT_CSP_SOURCE')
    host, port, path = match.groups()
    if len(host) > 253 or any(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) is None for label in host.split('.')):
        raise Hold('OAUTH_CONSENT_CSP_SOURCE')
    if port is not None and not 1 <= int(port) <= 65535:
        raise Hold('OAUTH_CONSENT_CSP_SOURCE')
    return 'https://' + host.lower() + (':' + str(int(port)) if port is not None else '') + path


def initialize_new_database(db):
    """Explicit offline/bootstrap operation. Never called by create_app."""
    if db.in_transaction:
        raise Hold('OAUTH_NESTED_TRANSACTION')
    try:
        db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
    except BaseException:
        db.rollback()
        raise


class Client(ClientMixin):
    def __init__(self, client_id, settings):
        self.client_id, self.settings = client_id, settings

    def get_client_id(self): return self.client_id
    def get_default_redirect_uri(self): return None  # explicit exact URI mandatory
    def get_allowed_scope(self, scope):
        return ' '.join(sorted(set((scope or '').split()) & SCOPES))
    def check_redirect_uri(self, uri): return uri in self.settings['redirect_uris']
    def check_client_secret(self, secret):
        return type(secret) is str and hmac.compare_digest(digest(secret), self.settings['secret_hash'])
    def check_endpoint_auth_method(self, method, endpoint):
        if endpoint == 'introspection':
            return self.settings['resource_client'] is True and method == 'client_secret_basic'
        if self.settings['resource_client']:
            return False
        return method == self.settings['auth_method']
    def check_response_type(self, response_type):
        return not self.settings['resource_client'] and response_type == 'code'
    def check_grant_type(self, grant_type):
        return not self.settings['resource_client'] and grant_type in ('authorization_code', 'refresh_token')


class Code(AuthorizationCodeMixin):
    def __init__(self, row):
        self.row = row
        self.code_challenge, self.code_challenge_method = row['challenge'], row['method']
    def get_redirect_uri(self): return self.row['redirect']
    def get_scope(self): return self.row['scope']


class Token(TokenMixin):
    def __init__(self, row, clock): self.row, self.clock = row, clock
    def get_scope(self): return self.row['scope']
    def check_client(self, client): return self.row['client'] == client.client_id
    def is_expired(self): return self.row['expires'] <= self.clock()
    def is_revoked(self): return self.row['revoked'] != 0


def create_app(config, connect, session_secret, github_secret, enabled=False, clock=time.time,
               github_network=None):
    """connect returns a fresh connection to a pre-approved existing auth DB.

    No alternate identity fixture is accepted here. Offline GitHub doubles run
    behind the real Authlib HTTP client, outside the production factory.
    """
    if enabled is not True:
        raise Hold('OAUTH_AUTHORITY_DISABLED')
    if type(session_secret) is not bytes or len(session_secret) < 32:
        raise Hold('OAUTH_SESSION_SECRET')
    required = {'issuer', 'audience', 'github_client_id', 'clients', 'subjects'}
    if type(config) is not dict or set(config) != required:
        raise Hold('OAUTH_CONFIG_FIELDS')
    config = json.loads(json.dumps(config))
    issuer, audience = config['issuer'], config['audience']
    for uri in (issuer, audience):
        u = urlsplit(uri)
        if u.scheme != 'https' or not u.hostname or u.username or u.query or u.fragment:
            raise Hold('OAUTH_HTTPS_CONFIG')
    if issuer.endswith('/') or urlsplit(issuer).path:
        raise Hold('OAUTH_ISSUER_ORIGIN')
    for cid, client in config['clients'].items():
        if (type(cid) is not str or not cid or type(client) is not dict
                or set(client) != {'redirect_uris', 'auth_method', 'secret_hash', 'resource_client'}
                or type(client['resource_client']) is not bool
                or client['auth_method'] not in ('none', 'client_secret_basic')
                or type(client['secret_hash']) is not str or len(client['secret_hash']) != 64
                or type(client['redirect_uris']) is not list):
            raise Hold('OAUTH_CLIENT_CONFIG')
        for uri in client['redirect_uris']:
            u = urlsplit(uri)
            if u.scheme != 'https' or not u.hostname or u.username or u.fragment:
                raise Hold('OAUTH_REDIRECT_CONFIG')
    if not config['subjects'] or any(
            s not in ('github:332398908', 'github:95597695') for s in config['subjects']):
        raise Hold('OAUTH_SUBJECT_ALLOWLIST')
    app = Flask(__name__)
    app.config.update(SECRET_KEY=session_secret, MAX_CONTENT_LENGTH=16384,
        SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_NAME='__Host-xuanjun-oauth',
        TRUSTED_HOSTS=[urlsplit(issuer).netloc],
        OAUTH2_SCOPES_SUPPORTED=sorted(SCOPES), OAUTH2_REFRESH_TOKEN_GENERATOR=True,
        OAUTH2_TOKEN_EXPIRES_IN={'authorization_code':900, 'refresh_token':900})

    def now():
        value = clock()
        if not math.isfinite(value) or value < 0: raise Hold('OAUTH_CLOCK')
        return int(value)

    def db():
        if 'oauth_db' not in g:
            connection = connect()
            if connection.in_transaction: raise Hold('OAUTH_NESTED_TRANSACTION')
            g.oauth_db = connection
            g.oauth_db.row_factory = sqlite3.Row
            # Require pre-existing schema; do not create an empty history.
            g.oauth_db.execute('SELECT access_hash FROM oauth_tokens LIMIT 0')
        return g.oauth_db

    @app.teardown_appcontext
    def close_db(error):
        connection = g.pop('oauth_db', None)
        if connection is not None:
            if connection.in_transaction: connection.rollback()
            connection.close()

    def subject(sub):
        return SimpleNamespace(id=sub) if sub in config['subjects'] else None

    def query_client(cid):
        settings = config['clients'].get(cid)
        return Client(cid, settings) if settings else None

    def token_lookup(raw, hint):
        if type(raw) is not str or len(raw) > 4096: return None
        row = db().execute('SELECT * FROM oauth_tokens WHERE access_hash=? OR refresh_hash=?',
                           (digest(raw), digest(raw))).fetchone()
        return Token(row, now) if row else None

    def save_token(token, oauth_request):
        previous = getattr(oauth_request, 'refresh_token', None)
        issued = now()
        # Absolute 7-day refresh family lifetime cannot extend by rotation.
        family = previous.row['family'] if previous else secrets.token_hex(24)
        expires = previous.row['refresh_expires'] if previous else issued + 7*86400
        db().execute('INSERT INTO oauth_tokens VALUES(?,?,?,?,?,?,?,?,?,0)',
            (digest(token['access_token']), digest(token['refresh_token']),
             oauth_request.client.client_id, oauth_request.user.id,
             token['scope'], issued, issued+token['expires_in'], expires, family))

    server = AuthorizationServer(app, query_client=query_client, save_token=save_token)

    class Grant(AuthorizationCodeGrant):
        TOKEN_ENDPOINT_AUTH_METHODS = ['none', 'client_secret_basic']
        def save_authorization_code(self, code, req):
            db().execute('INSERT INTO oauth_codes VALUES(?,?,?,?,?,?,?,?,0)',
                (digest(code), req.client.client_id, req.user.id, req.payload.redirect_uri,
                 req.scope, req.payload.data['code_challenge'], 'S256', now()+120))
        def query_authorization_code(self, code, client):
            row = db().execute('SELECT * FROM oauth_codes WHERE digest=? AND client=? AND used=0 AND expires>?',
                               (digest(code), client.client_id, now())).fetchone()
            return Code(row) if row else None
        def delete_authorization_code(self, code):
            cursor = db().execute('UPDATE oauth_codes SET used=1 WHERE digest=? AND used=0', (code.row['digest'],))
            if cursor.rowcount != 1: raise Hold('OAUTH_CODE_RACE')
        def authenticate_user(self, code): return subject(code.row['sub'])

    class S256(CodeChallenge):
        SUPPORTED_CODE_CHALLENGE_METHOD = ['S256']

    class Refresh(RefreshTokenGrant):
        TOKEN_ENDPOINT_AUTH_METHODS = ['none', 'client_secret_basic']
        INCLUDE_NEW_REFRESH_TOKEN = True
        def authenticate_refresh_token(self, raw):
            token = token_lookup(raw, 'refresh_token')
            if not token or token.row['refresh_hash'] != digest(raw): return None
            if token.is_revoked():
                # Refresh replay invalidates all successors, preserved history.
                db().execute('UPDATE oauth_tokens SET revoked=1 WHERE family=?', (token.row['family'],))
                return None
            return token if token.row['refresh_expires'] > now() else None
        def authenticate_user(self, token): return subject(token.row['sub'])
        def revoke_old_credential(self, token):
            cursor = db().execute('UPDATE oauth_tokens SET revoked=1 WHERE access_hash=? AND revoked=0',
                                  (token.row['access_hash'],))
            if cursor.rowcount != 1: raise Hold('OAUTH_REFRESH_RACE')

    class Inspect(IntrospectionEndpoint):
        def query_token(self, raw, hint):
            token = token_lookup(raw, hint)
            return token if token and token.row['access_hash'] == digest(raw) else None
        def check_permission(self, token, client, req):
            return client.settings['resource_client'] is True and subject(token.row['sub']) is not None
        def introspect_token(self, token):
            r = token.row
            return dict(active=True, iss=issuer, aud=audience, sub=r['sub'],
                        scope=r['scope'], iat=r['issued'], exp=r['expires'],
                        token_type='Bearer', client_id=r['client'])

    class Revoke(RevocationEndpoint):
        CLIENT_AUTH_METHODS = ['none', 'client_secret_basic']
        def query_token(self, raw, hint): return token_lookup(raw, hint)
        def revoke_token(self, token, req):
            db().execute('UPDATE oauth_tokens SET revoked=1 WHERE family=?', (token.row['family'],))

    server.register_grant(Grant, [S256(required=True)])
    server.register_grant(Refresh)
    server.register_endpoint(Inspect)
    server.register_endpoint(Revoke)
    oauth = OAuth(app)
    github = oauth.register('github', client_id=config['github_client_id'],
        client_cls=GithubApp,
        client_secret=github_secret, access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize', api_base_url='https://api.github.com/',
        client_kwargs={'scope':'', 'code_challenge_method':'S256'})
    network=github_network if github_network is not None else GithubNetwork()
    # The actual service has four HTTP threads. At most two may wait for
    # callback wire work, reserving capacity for introspection and revocation.
    callback_slots=threading.BoundedSemaphore(2)

    @app.before_request
    def secure_boundary():
        if request.scheme != 'https' or request.host != urlsplit(issuer).netloc:
            abort(400)
        # Reverse proxy headers are deliberately not trusted by this factory.
        if request.content_length and request.content_length > 16384: abort(413)
        for values in (request.args, request.form):
            if any(len(values.getlist(k)) != 1 for k in values): abort(400)
        if request.path in ('/token', '/introspect', '/revoke'):
            if request.args or request.mimetype != 'application/x-www-form-urlencoded': abort(400)
            if 'resource' in request.form and request.form['resource'] != audience: abort(400)

    @app.after_request
    def no_secrets_cached(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Referrer-Policy'] = 'no-referrer'
        form_action = "'self'"
        if (request.method == 'GET' and request.path == '/consent'
                and response.status_code == 200 and response.mimetype == 'text/html'
                and 'consent_form_source' in g):
            form_action += ' ' + g.consent_form_source
        response.headers['Content-Security-Policy'] = "default-src 'none'; form-action " + form_action + "; frame-ancestors 'none'"
        # Fixed phase labels only, never exception text or authentication data.
        if (request.method == 'GET' and request.path == '/github/callback'
                and response.status_code == 401
                and g.get('oauth_callback_stage') in (
                    'FLOW_VALID', 'TOKEN_EXCHANGE', 'USER_HTTP', 'USER_SHAPE',
                    'SUBJECT_ALLOWED', 'DEADLINE', 'FLOW_BIND')):
            response.headers['X-Xuanjun-OAuth-Stage'] = g.oauth_callback_stage
            if response.mimetype == 'text/html':
                response.set_data(response.get_data() +
                    ('<p>OAuth stage: ' + g.oauth_callback_stage + '</p>\n').encode('ascii'))
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.errorhandler(Hold)
    @app.errorhandler(sqlite3.Error)
    def hold(error): return jsonify(error='temporarily_unavailable'), 503

    def transaction(callback):
        connection = db()
        if connection.in_transaction: raise Hold('OAUTH_NESTED_TRANSACTION')
        connection.execute('BEGIN IMMEDIATE')
        try:
            response = callback()
            connection.commit()
            return response
        except BaseException:
            connection.rollback()
            raise

    @app.get('/.well-known/oauth-authorization-server')
    def metadata():
        return jsonify(issuer=issuer, authorization_endpoint=issuer+'/authorize',
            token_endpoint=issuer+'/token', revocation_endpoint=issuer+'/revoke',
            introspection_endpoint=issuer+'/introspect', response_types_supported=['code'],
            grant_types_supported=['authorization_code','refresh_token'],
            token_endpoint_auth_methods_supported=['none','client_secret_basic'],
            code_challenge_methods_supported=['S256'], scopes_supported=sorted(SCOPES))

    def flow():
        sid = session.get('flow')
        if type(sid) is not str: abort(401)
        row = db().execute('SELECT * FROM oauth_flows WHERE sid_hash=? AND used=0 AND expires>?',
                            (digest(sid), now())).fetchone()
        if row is None: abort(401)
        return row

    @app.get('/authorize')
    def authorize():
        if (set(request.args) - {'client_id','redirect_uri','response_type','scope','state',
                                 'code_challenge','code_challenge_method','resource','ui_locales'}
                or request.args.get('resource') != audience
                or request.args.get('code_challenge_method') != 'S256'
                or not request.args.get('code_challenge')
                or not request.args.get('state') or len(request.query_string) > 8192): abort(400)
        # Optional display hint only: bounded ASCII language-tag-shaped tokens.
        # This is not language negotiation or an authentication/authorization input.
        locales = request.args.get('ui_locales')
        if locales is not None and (not 1 <= len(locales) <= 128
                or len(locales.split(' ')) > 8
                or re.fullmatch(r'[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*(?: [A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)*', locales) is None):
            abort(400)
        # Authlib validates the exact callback, client, scopes and S256 shape.
        try: server.get_consent_grant(end_user=None)
        except Exception: abort(400)
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        params = request.args.to_dict()
        params.pop('ui_locales', None)  # Ignored; never persist or forward this display hint.
        def save_flow():
            if db().execute('SELECT count(*) FROM oauth_flows WHERE used=0 AND expires>?', (now(),)).fetchone()[0] >= 128:
                raise Hold('OAUTH_FLOW_CAPACITY')
            if db().execute('SELECT count(*) FROM oauth_flows').fetchone()[0] >= 100000:
                raise Hold('OAUTH_HISTORY_CAPACITY')
            db().execute('INSERT INTO oauth_flows VALUES(?,?,?,NULL,?,0)',
                (digest(sid), json.dumps(params), digest(csrf), now()+600))
            return redirect('/login')
        response = transaction(save_flow)
        session.clear()
        session.update(flow=sid, csrf=csrf)
        return response

    @app.get('/login')
    def login():
        flow()
        return github.authorize_redirect(issuer+'/github/callback')

    @app.get('/github/callback')
    def callback():
        g.oauth_callback_stage = 'FLOW_VALID'
        original = flow()
        if not callback_slots.acquire(blocking=False):
            return jsonify(error='temporarily_unavailable'),503
        g.github_deadline=time.monotonic()+5
        g.github_network=network
        try:
            g.oauth_callback_stage = 'TOKEN_EXCHANGE'
            token = github.authorize_access_token()
            g.oauth_callback_stage = 'USER_HTTP'
            response = github.get('user', token=token, allow_redirects=False)
            if response.status_code != 200: abort(401)
            g.oauth_callback_stage = 'USER_SHAPE'
            user = response.json()
            if type(user) is not dict or type(user.get('id')) is not int: abort(401)
            sub = 'github:' + str(user['id'])
            g.oauth_callback_stage = 'SUBJECT_ALLOWED'
            if subject(sub) is None: abort(403)
            g.oauth_callback_stage = 'DEADLINE'
            if time.monotonic()>=g.github_deadline:raise Hold('GITHUB_TOTAL_DEADLINE')
        except Exception:
            abort(401)
        finally:
            g.pop('github_deadline',None);g.pop('github_network',None)
            callback_slots.release()
        g.oauth_callback_stage = 'FLOW_BIND'
        def bind():
            cursor = db().execute('UPDATE oauth_flows SET sub=? WHERE sid_hash=? AND used=0 AND sub IS NULL AND expires>?',
                                  (sub, original['sid_hash'], now()))
            if cursor.rowcount != 1: abort(401)
            return redirect('/consent')
        return transaction(bind)

    @app.route('/consent', methods=['GET','POST'])
    def consent():
        row = flow()
        user = subject(row['sub'])
        if user is None: abort(401)
        if request.method == 'GET':
            params = json.loads(row['params'])
            settings = config['clients'].get(params.get('client_id'))
            redirect_uri = params.get('redirect_uri')
            if (settings is None or settings['resource_client']
                    or redirect_uri not in settings['redirect_uris']): abort(403)
            g.consent_form_source = consent_form_source(redirect_uri)
            from markupsafe import escape
            return ('<form method="post"><p>Allow read-only project connection access?</p>'
                    '<input type="hidden" name="csrf" value="'+str(escape(session['csrf']))+'">'
                    '<button name="approve" value="yes">Allow</button></form>')
        if (set(request.form) != {'csrf','approve'} or request.form['approve'] != 'yes'
                or not hmac.compare_digest(digest(request.form['csrf']), row['csrf_hash'])): abort(403)
        params = json.loads(row['params'])
        # Reconstruct the previously validated authorization request, never a
        # URL or user identity supplied by the consent POST.
        from urllib.parse import urlencode
        def issue():
            current = flow()
            if current['sub'] != user.id: abort(401)
            import io
            environment = request.environ.copy()
            environment.update(REQUEST_METHOD='GET', PATH_INFO='/authorize',
                               QUERY_STRING=urlencode(params), CONTENT_LENGTH='0',
                               **{'wsgi.input':io.BytesIO()})
            with app.request_context(environment):
                response = server.create_authorization_response(grant_user=user)
            if response.status_code != 302: raise Hold('OAUTH_AUTHORIZATION_RESPONSE')
            db().execute('UPDATE oauth_flows SET used=1 WHERE sid_hash=? AND used=0', (row['sid_hash'],))
            return response
        response = transaction(issue)
        session.clear()
        return response

    @app.post('/token')
    def exchange(): return transaction(server.create_token_response)

    @app.post('/introspect')
    def introspect(): return server.create_endpoint_response('introspection')

    @app.post('/revoke')
    def revoke(): return transaction(lambda:server.create_endpoint_response('revocation'))

    return app
