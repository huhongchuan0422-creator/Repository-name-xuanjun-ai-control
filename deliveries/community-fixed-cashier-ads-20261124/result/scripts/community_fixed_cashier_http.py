"""Narrow extension of the original HTTP handler; no second listener/runtime.

Compose with make_handler(..., fixed_cashier=the_same_host, proxy_origin=...,
trusted_proxy=the_original_source). All unrelated routes remain original.
"""
import json
import re
import socket
import time
from pathlib import Path

API = '/community/fixed-cashier'
ASSETS = {'/community/fixed-ad-preview.js': ('fixed-ad-preview.js', 'application/javascript; charset=utf-8'),'/community/fixed-workbench.js': ('fixed-workbench.js', 'application/javascript; charset=utf-8'),
          '/merchant/workbench': ('workbench.html', 'text/html; charset=utf-8'),
          '/community/fixed-cashier.js': ('fixed-cashier.js', 'application/javascript; charset=utf-8'),
          '/community/fixed-cashier.css': ('fixed-cashier.css', 'text/css; charset=utf-8'),
          '/merchant/fixed-code': ('fixed-code.html', 'text/html; charset=utf-8')}
GO = re.compile(r'/community-preview/go/(fx[0-9a-f]{24})')


def make_handler(gateway, *, fixed_cashier, **kwargs):
    from scripts.community_mini_http import make_handler as original
    from scripts.community_fixed_cashier_host import FixedCashierHost
    if (type(fixed_cashier) is not FixedCashierHost
            or fixed_cashier.identity is not gateway.identity
            or fixed_cashier.operations is not kwargs.get('operations')
            or fixed_cashier.commerce is not kwargs.get('commerce')
            or fixed_cashier.payments is not getattr(gateway, 'payments', None)
            or fixed_cashier.https_origin != kwargs.get('proxy_origin')
            or kwargs.get('trusted_proxy') is None):
        raise ValueError('SAME_ORIGINAL_HTTPS_CASHIER_REQUIRED')
    base = original(gateway, **kwargs)  # original pinned proxy admission still runs
    return _extend(base, fixed_cashier, kwargs['proxy_origin'], kwargs['trusted_proxy'])


def _extend(base, host, origin, trusted_proxy):
    class Handler(base):
        def _fixed_guard(self, post=False):
            if self.headers.get_all('Host') != [origin[8:]]:
                raise PermissionError('ORIGIN_DENIED')
            trusted_proxy(self.connection, self.headers)
            if post and (self.headers.get_all('Origin') != [origin]
                         or self.headers.get_all('Sec-Fetch-Site', []) not in ([], ['same-origin'])):
                raise PermissionError('ORIGIN_DENIED')

        def _fixed_asset(self, name, mime):
            raw = (Path(__file__).resolve().parents[1] / 'demos' / 'community-stage' / name).read_bytes()
            if name == 'workbench.html' and origin == 'https://uk.wenwenwenyiyiyi.work':
                from scripts.community_web_entries import asset
                raw, mime = asset('/merchant/workbench')
            self.send_response(200)
            for key, value in [('Content-Type', mime), ('Content-Length', str(len(raw))),
                ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                ('Referrer-Policy', 'no-referrer'),
                ('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; base-uri 'none'; frame-ancestors 'self'; form-action 'self'")]:
                self.send_header(key, value)
            self.end_headers()
            if self.command != 'HEAD': self.wfile.write(raw)
            self.close_connection = True

        def do_GET(self):
            path = self.path.partition('?')[0]
            match = GO.fullmatch(path)
            if not match and path not in ASSETS: return super().do_GET()
            try:
                self._fixed_guard()
                if match:
                    host.entry_scope(match.group(1))
                    return self._fixed_asset('fixed-cashier.html', 'text/html; charset=utf-8')
                return self._fixed_asset(*ASSETS[path])
            except PermissionError: return self.answer(403, {'error': 'CASHIER_ACCESS_DENIED'})
            except Exception: return self.answer(503, {'error': 'CASHIER_UNAVAILABLE'})

        def do_POST(self):
            if self.path != API: return super().do_POST()
            try:
                self._fixed_guard(post=True)
                if self.headers.get('Transfer-Encoding') is not None or any(
                    len(self.headers.get_all(h, [])) > 1 for h in
                    ('Content-Length', 'Content-Type', 'Cookie', 'X-Center-Session', 'X-Center-CSRF', 'X-CSRF-Token')):
                    raise ValueError('AMBIGUOUS_HEADERS')
                if self.headers.get('Content-Type', '').split(';')[0].lower() != 'application/json':
                    return self.answer(415, {'error': 'JSON_REQUIRED'})
                length = int(self.headers.get('Content-Length', '-1'))
                if not 0 < length <= 16384: raise ValueError('INVALID_LENGTH')
                chunks = []; remaining = length; deadline = time.monotonic() + 1
                while remaining:
                    budget = deadline - time.monotonic()
                    if budget <= 0: raise socket.timeout()
                    self.connection.settimeout(budget)
                    part = self.rfile.read1(remaining)
                    if not part: raise ValueError('TRUNCATED_BODY')
                    chunks.append(part); remaining -= len(part)
                def unique(items):
                    result = {}
                    for key, value in items:
                        if key in result: raise ValueError('DUPLICATE_FIELD')
                        result[key] = value
                    return result
                body = json.loads(b''.join(chunks).decode(), object_pairs_hook=unique)
                if type(body) is not dict: raise ValueError('INVALID_BODY')
                op = body.get('op')
                fields = {'amount': {'op', 'locator'}, 'reserve': {'op', 'locator', 'reference', 'yuan'},
                          'prepare': {'op', 'locator', 'reference'}, 'result': {'op', 'locator', 'reference'},
                          'ad_preview': {'op', 'workspace'}, 'qr_view': {'op', 'workspace'}, 'qr_download': {'op', 'workspace'}}
                if type(op) is not str or op not in fields or set(body) != fields[op]:
                    raise ValueError('INVALID_OPERATION')
                if op == 'amount': return self.answer(200, host.amount(body['locator']))
                cookies = [p.strip().partition('=')[2] for p in self.headers.get('Cookie', '').split(';')
                           if p.strip().partition('=')[0] == '__Host-xj_customer']
                session = self.headers.get('X-Center-Session', '')
                csrf = self.headers.get('X-Center-CSRF', '')
                if len(cookies) > 1 or cookies and session or csrf and self.headers.get('X-CSRF-Token'):
                    raise PermissionError('AMBIGUOUS_CENTER_CREDENTIALS')
                session = cookies[0] if cookies else session
                csrf = csrf or self.headers.get('X-CSRF-Token', '')
                host.center.session(session, csrf)
                if op in ('qr_view', 'qr_download', 'ad_preview'):
                    value = getattr(host, op)(session, csrf, body['workspace'])
                elif op == 'reserve':
                    value = host.reserve(session, csrf, body['locator'], body['reference'], body['yuan'])
                else:
                    value = getattr(host, op)(session, csrf, body['locator'], body['reference'])
                return self.answer(200, value)
            except PermissionError: return self.answer(403, {'error': 'CASHIER_ACCESS_DENIED'})
            except (ValueError, KeyError, TypeError): return self.answer(400, {'error': 'INVALID_CASHIER_REQUEST'})
            except Exception: return self.answer(503, {'error': 'CASHIER_UNCONFIRMED_QUERY_ONLY'})
    return Handler
