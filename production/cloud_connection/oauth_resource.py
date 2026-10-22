"""OAuth resource boundary. No issuer, credentials, listener or live enrollment.

RFC 7662 introspection is performed for every call. Only a host-installed
issuer/client and subject registry can supply a project recipient. Tool input
and tunnel metadata are never accepted as identity. Compatible with core 3.6.
"""
import base64
import json
import re
import urllib.parse
import urllib.request

from .queue import Hold, unique
from .worker import ExistingProjectFiles

SCOPES = frozenset(('connection.status', 'project.files.read'))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Hold('OAUTH_REDIRECT_FORBIDDEN')


class Introspection:
    def __init__(self, issuer, endpoint, client_id, secret_provider, audience,
                 subjects, open_url=None):
        for value in (issuer, endpoint, audience):
            u = urllib.parse.urlsplit(value)
            if (u.scheme != 'https' or not u.hostname or u.username or u.password
                    or u.query or u.fragment):
                raise Hold('OAUTH_FIXED_HTTPS_REQUIRED')
        if urllib.parse.urlsplit(issuer).netloc != urllib.parse.urlsplit(endpoint).netloc:
            raise Hold('OAUTH_ISSUER_ENDPOINT')
        if not client_id or ':' in client_id or not callable(secret_provider):
            raise Hold('OAUTH_CLIENT_CONFIGURATION')
        if not subjects or any(type(k) is not str or not k or type(v) is not dict
                               or set(v) != {'recipient', 'projects'}
                               or type(v['recipient']) is not str or not v['recipient']
                               or type(v['projects']) is not list or not v['projects']
                               or any(type(p) is not str or not p for p in v['projects'])
                               for k, v in subjects.items()):
            raise Hold('OAUTH_HOST_SUBJECT_MAPPING')
        self.issuer, self.endpoint, self.client_id = issuer, endpoint, client_id
        self.secret_provider, self.audience = secret_provider, audience
        # Copy to prevent a caller mutating policy between verification/use.
        self.subjects = json.loads(json.dumps(subjects))
        self.open_url = open_url or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()).open

    def authenticate(self, authorization, required_scope, project, now):
        if (required_scope not in SCOPES or type(now) is not int
                or type(authorization) is not str
                or not re.fullmatch(r'Bearer [A-Za-z0-9._~+/=-]{16,4096}', authorization)):
            raise Hold('OAUTH_BEARER_REQUIRED')
        token = authorization[7:]
        try:
            secret = self.secret_provider()
        except Exception:
            raise Hold('OAUTH_CLIENT_SECRET_UNAVAILABLE') from None
        if type(secret) is not str or not secret or '\n' in secret or '\r' in secret:
            raise Hold('OAUTH_CLIENT_SECRET')
        basic = base64.b64encode((urllib.parse.quote(self.client_id, safe='') + ':' +
                                 urllib.parse.quote(secret, safe='')).encode()).decode()
        request = urllib.request.Request(self.endpoint,
            data=urllib.parse.urlencode({'token': token,
                                        'token_type_hint': 'access_token'}).encode(),
            headers={'Authorization': 'Basic ' + basic,
                     'Content-Type': 'application/x-www-form-urlencoded',
                     'Accept': 'application/json'}, method='POST')
        try:
            with self.open_url(request, timeout=5) as response:
                if response.getcode() != 200:
                    raise ValueError()
                raw = response.read(16385)
                if len(raw) > 16384:
                    raise ValueError()
            claims = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        except Exception:
            # Never propagate endpoint responses, bearer or client secret.
            raise Hold('OAUTH_INTROSPECTION_UNAVAILABLE') from None
        if (type(claims) is not dict or claims.get('active') is not True
                or claims.get('iss') != self.issuer
                or type(claims.get('token_type')) is not str
                or claims['token_type'].lower() != 'bearer'
                or type(claims.get('exp')) is not int or claims['exp'] <= now
                or type(claims.get('iat')) is not int or claims['iat'] > now
                or claims['exp'] <= claims['iat']
                or ('nbf' in claims and (type(claims['nbf']) is not int or claims['nbf'] > now))):
            raise Hold('OAUTH_INACTIVE_OR_INVALID')
        audience = claims.get('aud')
        if audience != self.audience and audience != [self.audience]:
            raise Hold('OAUTH_RESOURCE_AUDIENCE')
        scope = claims.get('scope')
        if type(scope) is not str or required_scope not in scope.split():
            raise Hold('OAUTH_SCOPE')
        subject = claims.get('sub')
        mapping = self.subjects.get(subject) if type(subject) is str else None
        if mapping is None or project not in mapping['projects']:
            raise Hold('OAUTH_SUBJECT_PROJECT')
        return mapping['recipient']


class OAuthProjectResource:
    """Request-local recipient bridge; no shared mutable current-user state.

    The HTTP host must pass the actual Authorization header. This class is not
    registered by the installed stdio launcher and remains disabled by default.
    """
    def __init__(self, db, catalogs, authenticator, enabled=False):
        self.db, self.catalogs = db, dict(catalogs)
        self.authenticator, self.enabled = authenticator, enabled

    def read(self, authorization, arguments, now):
        if not self.enabled:
            raise Hold('OAUTH_RESOURCE_DISABLED')
        if type(arguments) is not dict or set(arguments) != {
                'manifest_sha256', 'request_id', 'object_ref', 'offset'}:
            raise Hold('PROJECT_TRANSFER_ARGUMENTS')
        digest = arguments['manifest_sha256']
        entry = self.catalogs.get(digest) if type(digest) is str else None
        if entry is None:
            raise Hold('PROJECT_CATALOG_REQUIRED')
        catalog, roots = entry
        recipient = self.authenticator.authenticate(
            authorization, 'project.files.read', catalog.value['project'], now)
        return ExistingProjectFiles(self.db, {digest: (catalog, roots)},
                                    lambda: recipient, True).read(arguments, now)
