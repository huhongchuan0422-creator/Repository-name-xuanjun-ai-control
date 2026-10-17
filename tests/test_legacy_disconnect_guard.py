"""Real legacy do_POST AST, synthetic dependencies only; never imports the app."""
import ast
import concurrent.futures
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import threading
import types
import unittest
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import http.client
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("guard", ROOT / "scripts/pr122_legacy_disconnect_guard.py")
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


def extracted_post(source, events, *, forbidden_store=False):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PortalHandler")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "do_POST")
    class FakeStore:
        def __init__(self, path):
            events.append("store_constructor")
            if forbidden_store:
                raise AssertionError("REAL_STORE_MUST_NOT_BE_REACHED")
        def disconnect(self):
            events.append("disconnect")
            return {"status": "PASS"}
    class FakeAudit:
        def record_audit(self, payload):
            events.append("business_audit")
    stderr = io.StringIO()
    namespace = {"urllib": types.SimpleNamespace(parse=urllib.parse),
        "TikTokTokenLifecycleStore": FakeStore,
        "TIKTOK_DISCONNECT_PATH": "/integrations/tiktok/disconnect",
        "DEFAULT_STATE_ROOT": Path("/SYNTHETIC_NOT_OPENED"),
        "sys": types.SimpleNamespace(stderr=stderr), "json": json, "HTTPStatus": HTTPStatus}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "<legacy-do_POST-only>", "exec"), namespace)
    return namespace["do_POST"], types.SimpleNamespace(
        portal_service=types.SimpleNamespace(operations_store=FakeAudit())), stderr


class GuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Path(os.environ["PR122_R4_SOURCE"]).read_bytes()
        if hashlib.sha256(cls.original).hexdigest() != GUARD.SOURCE_SHA256:
            raise AssertionError("ACTUAL_DEPLOYED_SOURCE_REQUIRED")
        cls.candidate = GUARD.build_candidate(cls.original)

    def request(self, *, original=False, headers=None, query="", path=None):
        events = []
        fn, server, stderr = extracted_post(
            self.original if original else self.candidate, events,
            forbidden_store=not original)
        class Handler:
            def _send(self, status, body, **kwargs):
                self.response = (int(status), json.loads(body))
        handler = Handler()
        handler.path = path or "/integrations/tiktok/disconnect" + query
        handler.headers = headers or {}
        handler.server = server
        handler.rfile = mock.Mock()
        handler.rfile.read.side_effect = AssertionError("BODY_MUST_NOT_BE_READ")
        fn(handler)
        return handler, events, stderr.getvalue()

    def deny(self, **kwargs):
        handler, events, log = self.request(**kwargs)
        self.assertEqual(handler.response[0], 403)
        self.assertEqual(handler.response[1], {"status": "REJECTED",
            "sanitized_error_code": "DISCONNECT_DISABLED_AUTH_NOT_INTEGRATED",
            "operation_performed": False})
        self.assertEqual(events, [])
        handler.rfile.read.assert_not_called()
        self.assertEqual(log, "security_event=TIKTOK_DISCONNECT_HTTP_DENIED\n")

    def test_old_unauthenticated_branch_reproduced_with_fake_store(self):
        handler, events, _ = self.request(original=True)
        self.assertEqual(handler.response[0], 200)
        self.assertEqual(events, ["store_constructor", "disconnect", "business_audit"])

    def test_no_login_no_store_or_business_audit(self):
        self.deny()

    def test_supplied_login_remains_disabled_not_fake_authentication(self):
        self.deny(headers={"Authorization": "Bearer SYNTHETIC_LOGIN", "Cookie": "session=SYNTHETIC"})

    def test_wrong_account_rejected(self):
        self.deny(headers={"X-Account-ID": "SYNTHETIC_OTHER"}, query="?account_id=SYNTHETIC_OTHER")

    def test_missing_csrf_rejected(self):
        self.deny(headers={"Origin": "https://wenwenwenyiyiyi.work"})

    def test_bad_csrf_rejected(self):
        self.deny(headers={"Origin": "https://wenwenwenyiyiyi.work", "X-CSRF-Token": "SYNTHETIC_BAD"})

    def test_forged_origin_rejected(self):
        self.deny(headers={"Origin": "https://invalid.example"})

    def test_spoofed_proxy_headers_cannot_enable_operation(self):
        self.deny(headers={"X-Real-IP": "127.0.0.1", "X-Forwarded-For": "127.0.0.1", "X-Forwarded-Proto": "https", "X-Authenticated-User": "owner"})

    def test_sensitive_headers_never_echoed_to_response_or_security_log(self):
        h, events, log = self.request(headers={"Authorization": "SYNTHETIC_DO_NOT_ECHO", "X-CSRF-Token": "SYNTHETIC_DO_NOT_ECHO"})
        self.assertNotIn("SYNTHETIC_DO_NOT_ECHO", json.dumps(h.response) + log)
        self.assertEqual(events, [])

    def test_duplicate_submissions_always_deny_without_state_change(self):
        for _ in range(10):
            self.deny(headers={"Idempotency-Key": "SYNTHETIC_REPEAT"})

    def test_concurrent_denials_never_construct_store(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: self.deny(), range(32)))

    def test_disconnect_failure_seam_is_unreachable(self):
        self.deny(headers={"Content-Length": "999999", "Transfer-Encoding": "chunked"})

    def test_body_and_query_credentials_not_read_or_logged(self):
        handler, events, log = self.request(query="?token=SYNTHETIC_QUERY")
        self.assertEqual(handler.response[0], 403)
        self.assertEqual(events, [])
        self.assertNotIn("SYNTHETIC_QUERY", log)
        handler.rfile.read.assert_not_called()

    def test_only_exact_branch_changes_all_other_bytes_preserved(self):
        self.assertEqual(self.candidate.replace(GUARD.NEW_BRANCH.encode(), GUARD.OLD_BRANCH.encode(), 1), self.original)
        self.assertEqual(self.candidate.count(GUARD.NEW_BRANCH.encode()), 1)

    def test_other_handler_methods_unchanged(self):
        before, after = ast.parse(self.original), ast.parse(self.candidate)
        classes = [next(n for n in t.body if isinstance(n, ast.ClassDef) and n.name == "PortalHandler") for t in (before, after)]
        for c in classes:
            c.body = [n for n in c.body if not (isinstance(n, ast.FunctionDef) and n.name == "do_POST")]
        self.assertEqual(ast.dump(classes[0], include_attributes=False), ast.dump(classes[1], include_attributes=False))

    def test_source_hash_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH"):
            GUARD.build_candidate(self.original + b"\n")

    def test_nonbytes_rejected(self):
        with self.assertRaises(TypeError):
            GUARD.build_candidate(self.original.decode())

    def test_real_isolated_http_post_returns403_no_store_and_no_cookie(self):
        events = []
        fn, fake_server, _ = extracted_post(self.candidate, events, forbidden_store=True)
        class Handler(BaseHTTPRequestHandler):
            do_POST = fn
            def log_message(self, *args):
                pass
            def _send(self, status, body, **kwargs):
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        server = HTTPServer(("127.0.0.1", 0), Handler)
        server.portal_service = fake_server.portal_service
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection(*server.server_address, timeout=3)
            try:
                conn.request("POST", "/integrations/tiktok/disconnect", body="")
                response = conn.getresponse()
                self.assertEqual(response.status, 403)
                self.assertIsNone(response.getheader("Set-Cookie"))
                self.assertFalse(json.loads(response.read())["operation_performed"])
            finally:
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
