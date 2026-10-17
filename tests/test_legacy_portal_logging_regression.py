"""Regression against pinned server source; fake HTTP server uses loopback only."""
import ast
import contextlib
import hashlib
import http.client
import http.server
import io
import os
from pathlib import Path
import sys
import threading
import types
import unittest
import urllib.parse

from scripts.pr122_legacy_portal_log_fix import (
    SOURCE_SHA256, build_candidate,
)


def logging_method(source):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "PortalHandler")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                  and n.name == "log_message")
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"urllib": urllib, "sys": sys}
    exec(compile(module, "<isolated-portal-log-method>", "exec"), namespace)
    return namespace["log_message"]


class LegacyPortalLoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = os.environ.get("PR122_PORTAL_SOURCE")
        if not source_path:
            raise RuntimeError("PR122_PORTAL_SOURCE_REQUIRED_NO_FAKE_SOURCE_FALLBACK")
        cls.source = Path(source_path).read_bytes()
        cls.candidate = build_candidate(cls.source)
        cls.old_log = staticmethod(logging_method(cls.source))
        cls.fixed_log = staticmethod(logging_method(cls.candidate))

    def capture(self, fmt, *args, path="/healthz?token=QUERY_SECRET"):
        fake = types.SimpleNamespace(
            path=path, client_address=("127.0.0.1", 1),
            log_date_time_string=lambda: "fixed",
        )
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            self.fixed_log(fake, fmt, *args)
        return out.getvalue()

    def test_actual_source_hash(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), SOURCE_SHA256)

    def test_original_mixed_numeric_error_is_reproduced(self):
        fake = types.SimpleNamespace(path="/healthz", client_address=("127.0.0.1", 1),
                                     log_date_time_string=lambda: "fixed")
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(TypeError):
                self.old_log(fake, "code %d, message %s", 501, "SECRET")

    def test_numeric_error_keeps_status_and_redacts_message(self):
        log = self.capture("code %d, message %s", 501, "SECRET")
        self.assertIn("code 501, message [REDACTED]", log)
        self.assertNotIn("SECRET", log)

    def test_request_line_redacted_and_query_excluded(self):
        log = self.capture('"%s" %s %s', "GET /secret HTTP/1.1", 200, "-")
        self.assertIn('"[REDACTED]" 200 [REDACTED]', log)
        self.assertNotIn("/secret", log)
        self.assertNotIn("QUERY_SECRET", log)

    def test_non_string_objects_never_call_repr_or_str(self):
        class Private:
            def __str__(self):
                raise AssertionError("PRIVATE_OBJECT_STRINGIFIED")
            __repr__ = __str__
        self.assertIn("[REDACTED]", self.capture("%s %r", Private(), Private()))

    def test_numeric_subclass_is_redacted(self):
        class PrivateInt(int):
            def __str__(self):
                raise AssertionError("PRIVATE_NUMERIC_OBJECT_STRINGIFIED")
        self.assertIn("[REDACTED]", self.capture("%s", PrivateInt(42)))

    def test_malformed_internal_format_falls_back(self):
        for fmt, args in (("%d", ("SECRET",)), ("%s %s", ("SECRET",)),
                          ("%q", (123,))):
            with self.subTest(fmt=fmt):
                log = self.capture(fmt, *args)
                self.assertIn("[REDACTED]", log)
                self.assertNotIn("SECRET", log)

    def test_invalid_url_does_not_break_error_response_logging(self):
        self.assertIn("path=[INVALID_PATH]", self.capture("code %d", 400, path="http://["))

    def test_bytes_redacted(self):
        self.assertNotIn("PRIVATE_BYTES", self.capture("%s", b"PRIVATE_BYTES"))

    def test_no_argument_log_format(self):
        self.assertIn("fixed message", self.capture("fixed message"))

    def test_foreign_source_rejected(self):
        for source in (self.source + b"\n", self.candidate, b"", b"print('untrusted')"):
            with self.subTest(size=len(source)):
                with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH"):
                    build_candidate(source)

    def test_non_bytes_rejected(self):
        with self.assertRaisesRegex(TypeError, "SOURCE_BYTES_REQUIRED"):
            build_candidate(self.source.decode())

    def test_only_logging_method_ast_changes(self):
        def normalized(source):
            tree = ast.parse(source)
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                       and n.name == "PortalHandler")
            cls.body = [n for n in cls.body if not (
                isinstance(n, ast.FunctionDef) and n.name == "log_message")]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(normalized(self.source), normalized(self.candidate))

    def test_only_logging_method_bytes_change(self):
        from scripts.pr122_legacy_portal_log_fix import OLD_METHOD, NEW_METHOD
        self.assertEqual(self.candidate.replace(NEW_METHOD.encode(), OLD_METHOD.encode(), 1),
                         self.source)

    @contextlib.contextmanager
    def server(self, method):
        class Handler(http.server.BaseHTTPRequestHandler):
            log_message = method
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "3")
                self.end_headers()
                self.wfile.write(b"OK\n")
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        server.timeout = 1
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()
            self.assertFalse(thread.is_alive())

    def request(self, address, method):
        conn = http.client.HTTPConnection(*address, timeout=3)
        try:
            conn.request(method, "/healthz?token=QUERY_SECRET")
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_original_head_disconnects_in_isolated_http_server(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.server(self.old_log) as address:
                with self.assertRaises(http.client.RemoteDisconnected):
                    self.request(address, "HEAD")

    def test_fixed_unsupported_methods_return_501_without_disconnect(self):
        logs = io.StringIO()
        with contextlib.redirect_stderr(logs):
            with self.server(self.fixed_log) as address:
                for method in ("HEAD", "OPTIONS", "DELETE", "PATCH", "TRACE", "CONNECT"):
                    with self.subTest(method=method):
                        status, body = self.request(address, method)
                        self.assertEqual(status, 501)
                        if method == "HEAD":
                            self.assertEqual(body, b"")
                self.assertEqual(self.request(address, "GET"), (200, b"OK\n"))
        self.assertNotIn("QUERY_SECRET", logs.getvalue())
        self.assertNotIn("Traceback", logs.getvalue())


if __name__ == "__main__":
    unittest.main()
