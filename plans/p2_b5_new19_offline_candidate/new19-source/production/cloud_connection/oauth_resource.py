"""OAuth resource boundary. No issuer, credentials, listener or live enrollment.

RFC 7662 introspection is performed for every call. Only a host-installed
issuer/client and subject registry can supply a project recipient. Tool input
and tunnel metadata are never accepted as identity. Compatible with core 3.6.
"""
import base64
import json
import math
import multiprocessing
import time
import re
import urllib.parse
import urllib.request

from .queue import Hold, unique
from .worker import ExistingProjectFiles

SCOPES = frozenset(('connection.status', 'project.files.read'))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Hold('OAUTH_REDIRECT_FORBIDDEN')


def _http_child(channel, url, data, headers, budget):
    """No secrets on argv, disk or exception output; parent owns total limit."""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        with opener.open(req, timeout=budget) as response:
            if response.getcode() != 200:
                raise ValueError()
            raw = response.read(16385)
            if len(raw) > 16384:
                raise ValueError()
        channel.send_bytes(b'1' + raw)
    except BaseException:
        channel.send_bytes(b'0')
    finally:
        channel.close()


def bounded_http(request, budget, context=None):
    # A socket timeout resets after every successful read and does not bound
    # DNS/TLS/drip-feed duration. Isolate the whole request and cancel it.
    if not math.isfinite(budget) or not 0 < budget <= 5:
        raise Hold('OAUTH_DEADLINE')
    deadline = time.monotonic() + budget
    ctx = context or multiprocessing.get_context('spawn')
    receiving, sending = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_http_child, args=(sending, request.full_url,
        request.data, dict(request.header_items()), budget))
    try:
        process.start()
        sending.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not receiving.poll(remaining):
            raise Hold('OAUTH_DEADLINE')
        result = receiving.recv_bytes(16386)
        if time.monotonic() >= deadline or result[:1] != b'1':
            raise Hold('OAUTH_DEADLINE_OR_NETWORK')
        return result[1:]
    finally:
        receiving.close()
        sending.close()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=0.1)
            if process.is_alive():
                import signal, os
                os.kill(process.pid, signal.SIGKILL)
                process.join(timeout=0.1)


class Introspection:
    def __init__(self, issuer, endpoint, client_id, secret_provider, audience,
                 subjects, open_url=None, wall_clock=None, monotonic=None):
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
        self.open_url = open_url
        self.wall_clock = wall_clock or time.time
        self.monotonic = monotonic or time.monotonic

    def authenticate(self, authorization, required_scope, project, now):
        return self.authenticate_projection(authorization, required_scope,
                                            project, now)['recipient']

    def authenticate_projection(self, authorization, required_scope, project, now):
        """Return only validated, request-local nonsecret claims.

        This projection is not a durable grant. A separate live family query
        must prove that the original authorization remains unrevoked.
        """
        if (required_scope is not None and required_scope not in SCOPES or type(now) is not int
                or type(authorization) is not str
                or not re.fullmatch(r'Bearer [A-Za-z0-9._~+/=-]{16,4096}', authorization)):
            raise Hold('OAUTH_BEARER_REQUIRED')
        start = self.monotonic()
        if not math.isfinite(start):
            raise Hold('OAUTH_CLOCK')
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
            if self.open_url is None:
                raw = bounded_http(request, 5 - (self.monotonic() - start))
            else:
                # Explicit offline transport seam; the production path always
                # uses a cancellable process, not a socket inactivity timeout.
                with self.open_url(request, timeout=5) as response:
                    if response.getcode() != 200:
                        raise ValueError()
                    raw = response.read(16385)
                    if len(raw) > 16384:
                        raise ValueError()
            claims = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
            elapsed = self.monotonic() - start
            current = self.wall_clock()
            if not math.isfinite(elapsed) or elapsed < 0 or elapsed >= 5:
                raise ValueError()
            if not math.isfinite(current) or current < now:
                raise ValueError()
            now = current
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
        if (type(scope) is not str or not set(scope.split()) & SCOPES
                or (required_scope is not None and required_scope not in scope.split())):
            raise Hold('OAUTH_SCOPE')
        subject = claims.get('sub')
        mapping = self.subjects.get(subject) if type(subject) is str else None
        if mapping is None or (project is not None and project not in mapping['projects']):
            raise Hold('OAUTH_SUBJECT_PROJECT')
        final_time = self.wall_clock()
        elapsed = self.monotonic() - start
        if (not math.isfinite(final_time) or final_time < now or claims['exp'] <= final_time
                or not math.isfinite(elapsed) or not 0 <= elapsed < 5):
            raise Hold('OAUTH_EXPIRED_OR_DEADLINE')
        family = claims.get('family_ref')
        # The original authority may omit this until its reviewed next release
        # is active. Missing reference can never be inferred from a token hash.
        if family is not None and (type(family) is not str or
                                   re.fullmatch(r'[0-9a-f]{48}',family) is None):
            raise Hold('OAUTH_FAMILY_REFERENCE')
        return {'recipient':mapping['recipient'],'subject':subject,
                'scopes':sorted(set(scope.split()) & SCOPES),
                'issuer':self.issuer,'audience':self.audience,
                'client_id':claims.get('client_id'),
                'expires':claims['exp'],'checked_at':int(final_time),
                'family_ref':family}


class OAuthProjectResource:
    """Request-local recipient bridge; no shared mutable current-user state.

    The HTTP host must pass the actual Authorization header. This class is not
    registered by the installed stdio launcher and remains disabled by default.
    """
    def __init__(self, db, catalogs, authenticator, enabled=False, clock=time.time, custodies=None):
        self.custodies = custodies
        self.db, self.catalogs = db, dict(catalogs)
        self.authenticator, self.enabled = authenticator, enabled
        self.clock = clock

    def read(self, authorization, arguments, now):
        if self.enabled is not True:
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
        current = self.clock()
        if not math.isfinite(current) or current < now:
            raise Hold('OAUTH_CLOCK')
        if self.custodies is not None:
            from .material_custody import read_received_chunk
            if type(self.custodies) is not dict or set(self.custodies) != set(self.catalogs):
                raise Hold('CUSTODY_CATALOG_BINDING')
            root, owner = self.custodies[digest]
            return read_received_chunk(self.db, catalog, root, owner, arguments['request_id'],
                                       arguments['object_ref'], recipient, arguments['offset'], int(current), True)
        return ExistingProjectFiles(self.db, {digest: (catalog, roots)},
                                    lambda: recipient, True).read(arguments, int(current))
