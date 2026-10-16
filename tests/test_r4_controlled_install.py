"""Temporary filesystem + synthetic source/service only; no production access."""
import base64
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("r4install", ROOT / "deploy/pr122-r4-controlled-install/controlled_install.py")
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


def fresh_engine():
    data = (ROOT / "deploy/pr122-portal-log-capability/portal_log_capability.py").read_bytes()
    if hashlib.sha256(data).hexdigest() != INSTALL.HELPER_SHA256:
        raise AssertionError("REUSED_ENGINE_CHANGED")
    engine = types.ModuleType("synthetic_root_engine")
    exec(compile(data, "<reused-root-engine>", "exec"), engine.__dict__)
    guard_data = base64.b64decode(INSTALL.GUARD_B64, validate=True)
    if hashlib.sha256(guard_data).hexdigest() != INSTALL.GUARD_SHA256:
        raise AssertionError("APPROVED_BUILDER_CHANGED")
    guard = types.ModuleType("synthetic_guard_namespace")
    exec(compile(guard_data, "<approved-builder>", "exec"), guard.__dict__)
    return engine, guard


class InstallTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() != 0:
            self.skipTest("Requires isolated root filesystem; not production root")
        self.tmp = tempfile.TemporaryDirectory(prefix="r4-control-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / "app/scripts/portal.py"
        self.source.parent.mkdir(parents=True)
        self.engine, self.guard = fresh_engine()
        self.assertEqual(self.guard.SOURCE_SHA256, INSTALL.SOURCE_SHA256)
        self.original = ("class PortalHandler:\n    def do_POST(self):\n        parsed = object()\n" + self.guard.OLD_BRANCH).encode()
        # Only test module namespaces receive synthetic pins; shipped constants
        # and installed files are never changed or sourced from an env override.
        self.guard.SOURCE_SHA256 = hashlib.sha256(self.original).hexdigest()
        self.engine.SOURCE_SHA256 = self.guard.SOURCE_SHA256
        self.engine.build_candidate = self.guard.build_candidate
        self.candidate = self.guard.build_candidate(self.original)
        self.engine.CANDIDATE_SHA256 = hashlib.sha256(self.candidate).hexdigest()
        self.source.write_bytes(self.original)
        try:
            os.chown(self.source, 1000, 1000)
        except OSError:
            self.engine.SOURCE_UID = os.getuid()  # local user namespace only
        self.source.chmod(0o755)
        self.root = self.base / "state"
        self.summary = self.base / "public.json"
        self.calls = []
        self.pid = "100"
        self.active = "active"
        def inspect():
            return {"MainPID": self.pid, "ActiveState": self.active,
                "SubState": "running" if self.active == "active" else "dead",
                "User": "admin", "WorkingDirectory": "/opt/trading-system"}
        def restart():
            self.calls.append("restart")
            self.pid = "200"
        def health():
            self.calls.append("health")
            return [{"method": "GET", "status": 200}, {"method": "HEAD", "status": 501}]
        def negative():
            self.calls.append("negative")
            return [{"method": "POST", "status": 403, "synthetic_empty_request": True}]
        def stop():
            self.calls.append("stop")
            self.pid, self.active = "0", "inactive"
        self.op = INSTALL.Operation(self.engine, self.root, self.source, self.summary,
            inspect=inspect, restart=restart, health=health, negative=negative, stop=stop)

    def test_install_exact_backup_source_fresh_pid_and_fixed_denial(self):
        receipt = self.op.install()
        self.assertEqual(receipt["status"], "LIVE_R4_CONTAINMENT_PASS")
        self.assertEqual(self.source.read_bytes(), self.candidate)
        self.assertEqual((self.root / "source.before.py").read_bytes(), self.original)
        self.assertEqual(self.calls, ["restart", "health", "negative"])
        self.assertEqual(receipt["service_after"]["MainPID"], "200")

    def test_installer_never_blind_retries(self):
        self.op.install()
        with self.assertRaisesRegex(ValueError, "NO_BLIND_INSTALL_RETRY"):
            self.op.install()
        self.assertEqual(self.calls.count("restart"), 1)

    def test_source_drift_refuses_before_creating_state(self):
        self.engine.atomic_write(self.source, b"foreign", self.engine.SOURCE_UID, self.engine.SOURCE_UID, 0o755)
        with self.assertRaisesRegex(ValueError, "LIVE_SOURCE_HASH_CHANGED"):
            self.op.install()
        self.assertFalse(self.root.exists())
        self.assertEqual(self.calls, [])

    def test_stopped_backend_is_not_started(self):
        self.active, self.pid = "inactive", "0"
        with self.assertRaisesRegex(ValueError, "EXPECTED_RUNNING_PORTAL_REQUIRED"):
            self.op.install()
        self.assertFalse(self.root.exists())
        self.assertEqual(self.calls, [])

    def test_unchanged_pid_prevents_negative_http_probe(self):
        self.op.cap.restart = lambda: self.calls.append("restart")
        with self.assertRaisesRegex(ValueError, "NEW_RUNNING_PORTAL_PID_REQUIRED"):
            self.op.install()
        self.assertNotIn("negative", self.calls)
        self.assertEqual(json.loads(self.summary.read_text())["status"], "UNKNOWN_PRESERVE_EVIDENCE")

    def test_negative_probe_failure_preserves_new_source_and_no_auto_rollback(self):
        def fail():
            raise TimeoutError("SYNTHETIC_NETWORK_UNKNOWN")
        self.op.negative = fail
        with self.assertRaises(TimeoutError):
            self.op.install()
        self.assertEqual(self.source.read_bytes(), self.candidate)
        self.assertEqual(self.calls.count("restart"), 1)
        self.assertNotIn("stop", self.calls)
        self.assertEqual(json.loads(self.summary.read_text())["status"], "UNKNOWN_PRESERVE_EVIDENCE")

    def test_offline_rollback_restores_only_after_stop_and_never_restarts(self):
        self.op.install()
        receipt = self.op.rollback_offline()
        self.assertEqual(receipt["status"], "ROLLED_BACK_BACKEND_STOPPED")
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.pid, "0")
        self.assertEqual(self.calls.count("restart"), 1)
        self.assertEqual(self.calls[-1], "stop")
        self.assertEqual(receipt["tiktok_http_disconnect"], "NOT_ESTABLISHED")

    def test_stop_failure_never_restores_vulnerable_source(self):
        self.op.install()
        self.op.stop = lambda: self.calls.append("unconfirmed_stop")
        with self.assertRaisesRegex(ValueError, "PORTAL_STOP_NOT_CONFIRMED"):
            self.op.rollback_offline()
        self.assertEqual(self.source.read_bytes(), self.candidate)
        self.assertEqual(self.pid, "200")

    def test_tampered_backup_blocks_rollback_before_stop(self):
        self.op.install()
        self.engine.atomic_write(self.root / "source.before.py", b"tampered", mode=0o400)
        with self.assertRaisesRegex(ValueError, "ROLLBACK_BACKUP_HASH"):
            self.op.rollback_offline()
        self.assertNotIn("stop", self.calls)

    def test_private_and_public_receipt_modes_and_allowlist(self):
        self.op.install()
        expected = {self.root: 0o700, self.root / "grant.json": 0o600,
            self.root / "receipt.json": 0o600, self.root / "source.before.py": 0o400,
            self.summary: 0o644}
        for path, mode in expected.items():
            self.assertEqual(path.stat().st_mode & 0o777, mode)
        public = json.loads(self.summary.read_text())
        self.assertNotIn("scope", public)
        self.assertNotIn("backup", public)
        self.assertNotIn("grant", public)
        self.assertFalse(public["dns_change"])

    def test_existing_public_receipt_is_not_overwritten_by_install(self):
        self.summary.write_bytes(b"foreign")
        with self.assertRaisesRegex(ValueError, "NO_BLIND_INSTALL_RETRY"):
            self.op.install()
        self.assertEqual(self.summary.read_bytes(), b"foreign")
        self.assertFalse(self.root.exists())

    def test_execution_lock_is_nonblocking_and_exclusive(self):
        path = self.base / "lock"
        fd = INSTALL.lock_file(path, create=True)
        try:
            with self.assertRaises(BlockingIOError):
                INSTALL.lock_file(path, create=False)
        finally:
            os.close(fd)

    def test_loader_checks_exact_reused_engine_and_embedded_builder(self):
        path = self.base / "helper"
        path.write_bytes((ROOT / "deploy/pr122-portal-log-capability/portal_log_capability.py").read_bytes())
        path.chmod(0o755)
        with mock.patch.object(INSTALL, "HELPER", path), mock.patch.object(INSTALL, "root_chain"):
            loaded = INSTALL.load_engine()
        self.assertEqual(loaded.SOURCE_SHA256, INSTALL.SOURCE_SHA256)
        self.assertEqual(loaded.CANDIDATE_SHA256, INSTALL.CANDIDATE_SHA256)
        self.assertEqual(loaded.build_candidate.__globals__["SOURCE_SHA256"], INSTALL.SOURCE_SHA256)

    def test_loader_refuses_modified_engine_before_executing_it(self):
        path = self.base / "helper"
        path.write_bytes(b"raise AssertionError('MUST_NOT_EXECUTE')\n")
        path.chmod(0o755)
        with mock.patch.object(INSTALL, "HELPER", path), mock.patch.object(INSTALL, "root_chain"):
            with self.assertRaisesRegex(ValueError, "REUSED_HELPER_SHA256"):
                INSTALL.load_engine()

    def test_world_writable_ancestor_refused(self):
        # The temporary tree is beneath /tmp, whose writable ancestor is
        # intentionally forbidden for production root engine/state locations.
        with self.assertRaisesRegex(ValueError, "ROOT_PATH_IDENTITY"):
            INSTALL.root_chain(self.base)

    def fake_http(self, *, status=403, body=None, cookie=None):
        requests, connections = [], []
        if body is None:
            body = {"status": "REJECTED", "sanitized_error_code": "DISCONNECT_DISABLED_AUTH_NOT_INTEGRATED", "operation_performed": False}
        class Response:
            def __init__(self):
                self.status = status
            def getheader(self, name):
                return cookie if name == "Set-Cookie" else None
            def read(self, limit):
                return json.dumps(body).encode()
        class Connection:
            def __init__(self, *args, **kwargs):
                connections.append(self)
                self.closed = False
            def request(self, method, path, body, headers):
                requests.append((method, path, body, headers))
            def getresponse(self):
                return Response()
            def close(self):
                self.closed = True
        return Connection, requests, connections

    def test_negative_http_probes_are_empty_synthetic_and_verified_denials(self):
        self.op.install()
        connection, requests, connections = self.fake_http()
        with mock.patch.object(INSTALL.socket, "create_connection"), mock.patch.object(INSTALL.ssl, "create_default_context"), mock.patch.object(INSTALL.http.client, "HTTPConnection", connection):
            checks = self.op.verify_disabled_http()
        self.assertEqual(len(checks), 4)
        self.assertTrue(all(c["status"] == 403 for c in checks))
        for method, path, body, headers in requests:
            self.assertEqual((method, path, body), ("POST", "/integrations/tiktok/disconnect", b""))
            self.assertNotIn("Cookie", headers)
            self.assertNotIn("Authorization", headers)
            self.assertEqual(headers["Content-Length"], "0")
        self.assertTrue(all(c.closed for c in connections))

    def test_negative_http_rejects_success_wrong_body_and_cookie(self):
        self.op.install()
        for kwargs in ({"status": 200}, {"body": {"operation_performed": True}}, {"cookie": "unexpected"}):
            with self.subTest(case=kwargs):
                connection, _, connections = self.fake_http(**kwargs)
                with mock.patch.object(INSTALL.socket, "create_connection"), mock.patch.object(INSTALL.ssl, "create_default_context"), mock.patch.object(INSTALL.http.client, "HTTPConnection", connection):
                    with self.assertRaisesRegex(ValueError, "LIVE_CONTAINMENT_"):
                        self.op.verify_disabled_http()
                self.assertTrue(all(c.closed for c in connections))

    def test_negative_http_source_drift_prevents_network_request(self):
        with mock.patch.object(INSTALL.socket, "create_connection") as network:
            with self.assertRaisesRegex(ValueError, "LIVE_SOURCE_HASH_CHANGED"):
                self.op.verify_disabled_http()
        network.assert_not_called()

    def test_cli_refuses_unregistered_arguments_before_host_or_source_access(self):
        p = subprocess.run([sys.executable, "-I", str(ROOT / "deploy/pr122-r4-controlled-install/controlled_install.py"), "--install", "extra"], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("ONE_FIXED_ACTION_REQUIRED", p.stderr)


if __name__ == "__main__":
    unittest.main()
