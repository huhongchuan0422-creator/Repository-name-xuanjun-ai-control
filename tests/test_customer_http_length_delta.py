"""Full original HTTP handler, in-memory HTTP transport and explicit domain doubles.
No production identity, database, provider, or network assertions are implied.
Run with HTTP_SOURCE to compare the unchanged original against this candidate.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('HTTP_SOURCE', str(ROOT / 'scripts/pr122_customer_http.py')))

class Denied(Exception): pass
class Conflict(Exception): pass
class Unavailable(Exception): pass

def canonical(value):
    return json.dumps(value, ensure_ascii=False).encode()

def load_handler():
    exports = {
        'core': dict(Center=object, Denied=Denied, Conflict=Conflict, Unavailable=Unavailable, canonical=canonical),
        'source': dict(reject_untrusted=lambda *a: None, TrustedNginxSource=object),
        'providers': dict(Providers=object, enqueue=lambda *a: None, ai_reply=lambda *a: None),
        'changes': dict(Changes=object),
        'publication_worker': dict(enqueue=lambda *a: None, status=lambda *a: None),
        'edit_jobs': dict(enqueue=lambda *a: None),
        'profile': dict(FULL='FULL', LOGIN_ONLY='LOGIN_ONLY', profile=lambda x: x['deployment_profile']),
        'privacy': dict(acknowledge=lambda *a: None, submit_request=lambda *a: None),
    }
    modules = {'scripts': types.ModuleType('scripts')}
    modules['scripts'].__path__ = []
    for suffix, attrs in exports.items():
        name = 'scripts.pr122_customer_' + suffix
        modules[name] = types.ModuleType(name)
        modules[name].__dict__.update(attrs)
    spec = importlib.util.spec_from_file_location('http_delta_under_test', SOURCE)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module, modules

HTTP, MODULES = load_handler()

class Transport:
    def __init__(self, data):
        self.input = io.BytesIO(data)
        self.output = io.BytesIO()
    def makefile(self, *args, **kwargs): return self.input
    def sendall(self, data): self.output.write(data)
    def settimeout(self, value): pass

class CenterDouble:
    def __init__(self):
        self.db = types.SimpleNamespace(close=lambda: None)
        self.saved = None
    def register(self): pass
    def verify(self): pass
    def login(self): pass
    def request_reset(self): pass
    def reset(self): pass
    def session(self, token, csrf):
        if token != 'synthetic-session' or csrf != 'synthetic-csrf': raise Denied()
        return 'synthetic-user'
    def save(self, uid, project, item, revision, kind, content, expires):
        if project != 'allowed': raise Denied()
        self.saved = content
        return {'saved': True, 'characters': len(content)}

class LengthDelta(unittest.TestCase):
    def request(self, body=b'{}', headers=None, path='api/save', profile='FULL', length=None):
        self.center = CenterDouble()
        defaults = [
            ('Host', 'wenwenwenyiyiyi.work'), ('Origin', 'https://wenwenwenyiyiyi.work'),
            ('Content-Type', 'application/json'), ('Cookie', '__Host-xj_customer=synthetic-session'),
            ('X-CSRF-Token', 'synthetic-csrf'),
        ]
        if headers:
            keys = {k.lower() for k, v in headers}
            defaults = [(k, v) for k, v in defaults if k.lower() not in keys]
            defaults += [(k, v) for k, v in headers if v is not None]
        if length is None: length = [str(len(body))]
        defaults += [('Content-Length', n) for n in length]
        wire = ('POST /customer/center/' + path + ' HTTP/1.1\r\n' + ''.join(k + ': ' + v + '\r\n' for k, v in defaults) + '\r\n').encode() + body
        transport = Transport(wire)
        app = HTTP.App(lambda: self.center, object(), 'https://wenwenwenyiyiyi.work', '.', deployment_profile=profile)
        with patch.dict(sys.modules, MODULES):
            app.handler()(transport, ('127.0.0.1', 12345), object())
        head, result = transport.output.getvalue().split(b'\r\n\r\n', 1)
        return int(head.split()[1]), json.loads(result)

    def save_body(self, n=8, project='allowed'):
        return json.dumps(dict(project=project, item='synthetic-item', revision=0, kind='TEXT', content='x'*n, expires=None)).encode()

    def test_large_legal_json_reaches_original_save(self):
        body = self.save_body(7_000_001)
        self.assertGreater(len(body), 7_000_000)
        self.assertEqual(self.request(body)[0], 200)
        self.assertEqual(self.center.saved, 'x'*7_000_001)

    def test_small_legal_json_unchanged(self):
        self.assertEqual(self.request(self.save_body())[0], 200)

    def test_legal_leading_zero_length_has_no_digit_count_cap(self):
        body = self.save_body()
        self.assertEqual(self.request(body, length=[str(len(body)).zfill(10)])[0], 200)

    def test_malformed_length_rejected(self):
        for length in ['0', '-1', '+2', '1.5', 'abc', '２', '']:
            with self.subTest(length=length):
                self.assertEqual(self.request(length=[length])[0], 400)

    def test_missing_duplicate_and_transfer_encoding_rejected(self):
        for length, extra in [([], []), (['2', '2'], []), (['2'], [('Transfer-Encoding', 'chunked')])]:
            with self.subTest(length=length, extra=extra):
                self.assertEqual(self.request(length=length, headers=extra)[0], 400)

    def test_truncated_body_rejected_including_nine_digit_length(self):
        for length in ['3', '100000000']:
            with self.subTest(length=length):
                self.assertEqual(self.request(length=[length])[0], 400)

    def test_invalid_json_and_content_type_rejected(self):
        for body, extra in [(b'{', []), (b'[]', []), (b'{"x":1,"x":2}', []), (b'{}', [('Content-Type','text/plain')])]:
            with self.subTest(body=body, extra=extra):
                self.assertEqual(self.request(body, headers=extra)[0], 400)

    def test_origin_host_fetch_and_session_boundaries_unchanged(self):
        for headers in [[('Origin','https://invalid.example')], [('Host','invalid.example')], [('Sec-Fetch-Site','cross-site')], [('Cookie',None)], [('X-CSRF-Token',None)]]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request(self.save_body(), headers=headers)[0], 403)
                self.assertIsNone(self.center.saved)

    def test_large_body_still_requires_session_and_project_permission(self):
        body = self.save_body(7_000_001)
        self.assertEqual(self.request(body, headers=[('Cookie',None)])[0], 403)
        self.assertIsNone(self.center.saved)
        self.assertEqual(self.request(self.save_body(7_000_001, project='other'))[0], 403)
        self.assertIsNone(self.center.saved)

    def test_login_only_scope_unchanged(self):
        self.assertEqual(self.request(self.save_body(), profile='LOGIN_ONLY')[0], 403)

    def test_service_specific_limit_unchanged(self):
        self.assertEqual(self.request(b' '*8193, path='api/authorization/consume')[0], 413)
        self.assertEqual(self.request(path='api/authorization/consume')[0], 403)

    def test_webhook_specific_limit_unchanged(self):
        self.assertEqual(self.request(b' '*65537, path='webhooks/telegram')[0], 413)

if __name__ == '__main__': unittest.main(verbosity=2)
