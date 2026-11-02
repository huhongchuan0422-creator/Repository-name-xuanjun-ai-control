"""Synthetic in-memory contract tests. NOT original Store/browser/server tests.
No persisted credentials, no network, no server, no real account inputs.
"""
import ast
import concurrent.futures
import pathlib
import secrets
import sys
import threading
import unittest
from urllib.parse import urlencode
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safe_input import (Candidate, ExistingHost, ExistingProtectedStore,
                        NAMES, PURPOSE, VERSION, Principal, Request, Outcome, Unbound, status_page, decode_form)

class Host(ExistingHost):
    def __init__(self):
        self.enabled = True
        self.owner = Principal('owner', 'original-session-binding')
        self.csrf_tokens = {}
    def ready(self): return self.enabled
    def authorize_owner(self, principal): return principal == self.owner
    def csrf_for(self, principal, request):
        key = (principal, request.question_id)
        if key not in self.csrf_tokens: self.csrf_tokens[key] = secrets.token_urlsafe(24)
        return self.csrf_tokens[key]
    def validate_post(self, principal, request, csrf, origin):
        return (principal == self.owner and csrf == self.csrf_for(principal, request)
                and origin == 'https://example.invalid')

class MemoryOracle(ExistingProtectedStore):
    """TEST ORACLE ONLY: lock/dict is not a production durable Store adapter.
    Deliberately fails restart durability; no filesystem/database is used.
    """
    def __init__(self):
        self.now = 1000
        self.requests = {}
        self.protected = {}
        self.lock = threading.Lock()
        self.writes = 0
        self.failure = None
        self.enabled = True
    def ready(self): return self.enabled
    def create_request(self, principal, purpose, version, ttl_seconds, names, allowed_hosts):
        assert names == NAMES and allowed_hosts == () and ttl_seconds == 600
        r = Request(secrets.token_urlsafe(24), principal.subject, principal.session_binding,
                    purpose, version, self.now + ttl_seconds, 'PENDING')
        self.requests[r.question_id] = r
        return r
    def metadata(self, question_id): return self.requests.get(question_id)
    def status(self, request, principal):
        r = self.requests[request.question_id]
        if (r.subject, r.session_binding) != (principal.subject, principal.session_binding):
            return Outcome('FORBIDDEN')
        if r.status == 'PENDING' and self.now >= r.expires_at: return Outcome('EXPIRED')
        return Outcome(r.status)
    def submit_once(self, request, principal, values, allowed_hosts):
        with self.lock:
            r = self.requests[request.question_id]
            if (r.subject, r.session_binding, r.purpose, r.version) != (
                    principal.subject, principal.session_binding, PURPOSE, VERSION):
                return Outcome('FORBIDDEN')
            if r.status == 'STORED': return Outcome('REPLAY_REJECTED')
            if r.status != 'PENDING': return Outcome(r.status)
            if self.now >= r.expires_at: return Outcome('EXPIRED')
            assert allowed_hosts == ()
            if self.failure == 'before':
                self.requests[r.question_id] = r._replace(status='UNKNOWN')
                raise RuntimeError(next(iter(values.values())))
            # A real adapter MUST atomically commit 3 writes + request receipt.
            for name, value in values.items():
                self.protected[name] = (value, 'synthetic-ref/' + name, ())
            self.writes += 1
            self.requests[r.question_id] = r._replace(status='STORED')
            if self.failure == 'after': raise RuntimeError(next(iter(values.values())))
            return Outcome('STORED')

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.host, self.store = Host(), MemoryOracle()
        self.c = Candidate(self.host, self.store)
        self.p = self.host.owner
        self.r = self.c.create(self.p)
        # Generated synthetic values are never printed/serialized or snapshot-tested.
        self.values = {name: secrets.token_urlsafe(24) for name in NAMES}
    def post(self, **kwargs):
        args = dict(principal=self.p, question_id=self.r.question_id, method='POST',
                    origin='https://example.invalid', csrf=self.host.csrf_for(self.p, self.r), values=self.values)
        args.update(kwargs)
        return self.c.submit(**args)
    def test_exact_names_ttl_and_binding(self):
        self.assertEqual(self.r.expires_at, 1600)
        self.assertEqual((self.r.purpose, self.r.version), (PURPOSE, VERSION))
    def test_unbound_host_cannot_issue(self):
        self.host.enabled = False
        with self.assertRaises(Unbound): self.c.create(self.p)
    def test_unbound_store_cannot_issue(self):
        self.store.enabled = False
        with self.assertRaises(Unbound): self.c.create(self.p)
    def test_abstract_ports_not_instantiable(self):
        with self.assertRaises(TypeError): ExistingProtectedStore()
    def test_owner_only(self):
        self.assertEqual(self.post(principal=Principal('other', 's')).status, 'FORBIDDEN')
        self.assertEqual(self.store.writes, 0)
    def test_session_rebinding_rejected(self):
        self.assertEqual(self.post(principal=Principal('owner', 'another')).status, 'FORBIDDEN')
    def test_id_not_auth(self):
        with self.assertRaises(Unbound): self.c.page(Principal('other', 's'), self.r.question_id)
    def test_get_not_consume(self):
        self.c.page(self.p, self.r.question_id)
        self.assertEqual(self.post(method='GET').status, 'FORBIDDEN')
        self.assertEqual(self.store.writes, 0)
    def test_csrf_reject_then_correct(self):
        self.assertEqual(self.post(csrf='incorrect').status, 'FORBIDDEN')
        self.assertEqual(self.post().status, 'STORED')
    def test_origin_reject(self):
        for origin in ('http://example.invalid', 'https://example.invalid.attacker.invalid', 'null', ''):
            self.assertEqual(self.post(origin=origin).status, 'FORBIDDEN')
    def test_extra_or_missing_fields(self):
        self.assertEqual(self.post(values={}).status, 'INVALID')
        self.assertEqual(self.post(values=dict(self.values, unexpected='test')).status, 'INVALID')
    def test_invalid_values(self):
        for invalid in ('', None, 42, ['test']):
            v = dict(self.values); v[NAMES[0]] = invalid
            self.assertEqual(self.post(values=v).status, 'INVALID')
    def test_preserve_whitespace(self):
        self.values[NAMES[1]] = ' ' + self.values[NAMES[1]] + ' '
        self.post()
        self.assertTrue(self.store.protected[NAMES[1]][0] == self.values[NAMES[1]])
    def test_expiry_exact_boundary(self):
        self.store.now = 1600
        self.assertEqual(self.post().status, 'EXPIRED')
        self.assertEqual(self.store.writes, 0)
    def test_before_expiry(self):
        self.store.now = 1599
        self.assertEqual(self.post().status, 'STORED')
    def test_replay_does_not_overwrite(self):
        self.post(); old = dict(self.store.protected)
        self.assertEqual(self.post(values={n: secrets.token_urlsafe(20) for n in NAMES}).status, 'REPLAY_REJECTED')
        self.assertTrue(old == self.store.protected)
    def test_concurrent_one_winner(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            statuses = list(pool.map(lambda _: self.post().status, range(64)))
        self.assertEqual(statuses.count('STORED'), 1)
        self.assertEqual(statuses.count('REPLAY_REJECTED'), 63)
        self.assertEqual(self.store.writes, 1)
    def test_expired_link_does_not_expire_refs(self):
        self.post(); self.store.now = 999999
        self.assertEqual(len(self.store.protected), 3)
        self.assertEqual(self.c.result(self.p, self.r.question_id).status, 'STORED')
    def test_zero_egress_hosts(self):
        self.post()
        self.assertTrue(all(item[2] == () for item in self.store.protected.values()))
    def test_purpose_version_tamper(self):
        for key in ('purpose', 'version'):
            self.store.requests[self.r.question_id] = self.r._replace(**{key:'wrong'})
            self.assertEqual(self.post().status, 'FORBIDDEN')
        self.assertEqual(self.store.writes, 0)
    def test_cancelled(self):
        self.store.requests[self.r.question_id] = self.r._replace(status='CANCELLED')
        self.assertEqual(self.post().status, 'CANCELLED')
    def test_unknown_before_write_no_automatic_retry(self):
        self.store.failure = 'before'
        self.assertEqual(self.post().status, 'UNKNOWN')
        self.store.failure = None
        self.assertEqual(self.post().status, 'UNKNOWN')
        self.assertEqual(self.store.writes, 0)
    def test_unknown_after_commit_query_not_resubmit(self):
        self.store.failure = 'after'
        self.assertEqual(self.post().status, 'UNKNOWN')
        self.assertEqual(self.c.result(self.p, self.r.question_id).status, 'STORED')
        self.assertEqual(self.post().status, 'REPLAY_REJECTED')
        self.assertEqual(self.store.writes, 1)
    def test_response_never_echoes(self):
        self.store.failure = 'after'
        response = repr(self.post())
        self.assertTrue(all(v not in response for v in self.values.values()))
    def test_page_masked_native_no_script_no_storage(self):
        headers, page = self.c.page(self.p, self.r.question_id)
        self.assertEqual(page.count('type="password"'), 3)
        self.assertNotIn('<script', page)
        self.assertNotIn('localStorage', page)
        self.assertTrue(all(v not in page for v in self.values.values()))
        self.assertIn('no-store', headers['Cache-Control'])
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
    def test_malicious_question_id_not_rendered(self):
        with self.assertRaises(Unbound): self.c.page(self.p, '"><script>test</script>')
    def test_completed_page_has_no_form(self):
        self.post()
        self.assertNotIn('<form', self.c.page(self.p, self.r.question_id)[1])
    def test_test_oracle_is_not_durable_negative(self):
        self.post()
        self.assertEqual(MemoryOracle().protected, {})
    def test_existing_route_prefix(self):
        candidate = Candidate(self.host, self.store, '/openclaw')
        page = candidate.page(self.p, self.r.question_id)[1]
        self.assertIn('action="/openclaw/ask/', page)
    def test_mount_rejects_url_and_escape(self):
        for mount in ('https://other.invalid', '//other', '/x/../y', '/x%2fy', '/x?y'):
            with self.assertRaises(Unbound): Candidate(self.host, self.store, mount)
    def test_adapter_exception_not_echoed_from_create_page(self):
        value = next(iter(self.values.values()))
        def fail(*args): raise RuntimeError(value)
        self.store.create_request = fail
        with self.assertRaises(Unbound) as caught: self.c.create(self.p)
        self.assertTrue(value not in str(caught.exception))
        self.host.csrf_for = fail
        with self.assertRaises(Unbound) as caught: self.c.page(self.p, self.r.question_id)
        self.assertTrue(value not in str(caught.exception))
    def test_no_request_metadata_values(self):
        self.post()
        self.assertTrue(all(v not in repr(self.store.metadata(self.r.question_id)) for v in self.values.values()))
    def test_wrong_metadata_record_rejected_all_paths(self):
        other = self.c.create(self.p)
        original = self.store.metadata
        self.store.metadata = lambda q: original(other.question_id)
        self.assertEqual(self.post().status, 'FORBIDDEN')
        self.assertEqual(self.c.result(self.p, self.r.question_id).status, 'FORBIDDEN')
        with self.assertRaises(Unbound): self.c.page(self.p, self.r.question_id)
        self.assertEqual(self.store.writes, 0)
    def test_csrf_bound_to_request(self):
        other = self.c.create(self.p)
        wrong = self.host.csrf_for(self.p, other)
        self.assertEqual(self.post(csrf=wrong).status, 'FORBIDDEN')
        self.assertEqual(self.post().status, 'STORED')
    def test_expired_page_visible_and_no_form(self):
        self.store.now = 1600
        headers, page = self.c.page(self.p, self.r.question_id)
        self.assertIn('链接已过期', page)
        self.assertNotIn('<form', page)
        self.assertIn('viewport', page)
    def test_status_unknown_never_echoes(self):
        value = next(iter(self.values.values()))
        headers, page = status_page(Outcome(value))
        self.assertTrue(value not in page)
        self.assertIn('不要重复提交', page)
        self.assertIn('no-store', headers['Cache-Control'])
    def test_status_pages_not_final_browser_claim(self):
        for status in ('STORED', 'REPLAY_REJECTED', 'CANCELLED', 'FORBIDDEN', 'INVALID', 'UNKNOWN'):
            headers, page = status_page(Outcome(status))
            self.assertNotIn('<form', page)
            self.assertIn('viewport', page)
            self.assertTrue(all(v not in page for v in self.values.values()))
        self.assertIn('单独验证', status_page(Outcome('STORED'))[1])
    def test_form_decode_preserves_and_redacts_repr(self):
        fields = dict(self.values, csrf=self.host.csrf_for(self.p, self.r))
        body = urlencode(fields).encode('utf-8')
        parsed = decode_form(body, 'application/x-www-form-urlencoded', len(body))
        self.assertTrue(parsed.values == self.values)
        self.assertTrue(all(v not in repr(parsed) + repr(parsed.values) for v in self.values.values()))
        self.assertEqual(self.post(csrf=parsed.csrf, values=parsed.values).status, 'STORED')
    def test_duplicate_form_fields_rejected(self):
        fields = list(dict(self.values, csrf='test').items())
        fields.append((NAMES[0], 'test'))
        body = urlencode(fields).encode('utf-8')
        with self.assertRaises(Unbound): decode_form(body, 'application/x-www-form-urlencoded', len(body))
    def test_form_limit_content_type_and_bad_encoding(self):
        body = urlencode(dict(self.values, csrf='test')).encode('utf-8')
        for content, limit, payload in (
            ('application/json', len(body), body),
            ('application/x-www-form-urlencoded', len(body)-1, body),
            ('application/x-www-form-urlencoded', 0, body),
            ('application/x-www-form-urlencoded', 9999, b'x=%ZZ'),
            ('application/x-www-form-urlencoded', 9999, b'x=%FF')):
            with self.assertRaises(Unbound): decode_form(payload, content, limit)
    def test_python36_source_grammar(self):
        source = pathlib.Path(__file__).resolve().parents[1] / 'safe_input.py'
        ast.parse(source.read_text(), feature_version=(3, 6))

if __name__ == '__main__': unittest.main(verbosity=2)
