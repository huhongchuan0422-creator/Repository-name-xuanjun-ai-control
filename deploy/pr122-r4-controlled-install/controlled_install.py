#!/usr/bin/python3 -I
"""Fixed R4 root action, preparation candidate only; no privilege registration.

Reuses the exact installed root-owned log-fix transaction engine in memory.
Never reads OAuth state, credentials or a business database.
"""
import ast
import base64
import fcntl
import errno
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import subprocess
import sys
import types

HOST = "iZ6wee8q9z4t03hvqumwfhZ"
HELPER = Path("/usr/local/sbin/xuanjun-pr122-portal-logfix-v1")
HELPER_SHA256 = "0e61a4cab72a18e94ed8b97c81e035ee023dfe0969c871c50651cf75792cbcbe"
STATE = Path("/var/lib/xuanjun-pr122-r4-containment")
SUMMARY = Path("/var/lib/xuanjun-pr122-r4-containment-receipt.json")
TARGET = Path("/opt/trading-system/scripts/secure_secrets_portal_server.py")
SOURCE_SHA256 = "d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0"
CANDIDATE_SHA256 = "57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1"
GUARD_SHA256 = "1afc01c6b19cb8bfc82c16eab257a06dd95b0420118dc6a0dc4726f25a0d6d93"
GUARD_B64 = "IiIiUjQgY29udGFpbm1lbnQgY2FuZGlkYXRlOiBkaXNhYmxlIHRoZSBsZWdhY3kgSFRUUCBkaXNjb25uZWN0IG9wZXJhdGlvbi4KClRoaXMgaXMgTk9UIGFuIGF1dGhlbnRpY2F0ZWQgZGlzY29ubmVjdCBpbXBsZW1lbnRhdGlvbiBvciBhIHByb2R1Y3Rpb24gaW5zdGFsbGVyLgpPbmx5IHRoZSBleGFjdCBkZXBsb3llZCBsZWdhY3kgc291cmNlIGlzIGFjY2VwdGVkOyBhbGwgb3RoZXIgYnl0ZXMgYXJlIHByZXNlcnZlZC4KIiIiCmltcG9ydCBoYXNobGliCgpTT1VSQ0VfU0hBMjU2ID0gImQ1YWI1OTJhNmEyM2RkNWViZmE4Njg5Yzk1YWFhNDUzZTM3MTEyN2FhYjlhMzliYzJmZTdlYmEwZmViYmJkZjAiCk9MRF9CUkFOQ0ggPSAnJycgICAgICAgIGlmIHBhcnNlZC5wYXRoID09IFRJS1RPS19ESVNDT05ORUNUX1BBVEg6CiAgICAgICAgICAgIHBheWxvYWQgPSBUaWtUb2tUb2tlbkxpZmVjeWNsZVN0b3JlKERFRkFVTFRfU1RBVEVfUk9PVCAvICJ0aWt0b2stdG9rZW4tc3RhdGUiKS5kaXNjb25uZWN0KCkKICAgICAgICAgICAgc2VsZi5zZXJ2ZXIucG9ydGFsX3NlcnZpY2Uub3BlcmF0aW9uc19zdG9yZS5yZWNvcmRfYXVkaXQoewogICAgICAgICAgICAgICAgIm9wZXJhdGlvbiI6ICJUSUtUT0tfRElTQ09OTkVDVCIsCiAgICAgICAgICAgICAgICAicHJvdmlkZXIiOiAidGlrdG9rIiwKICAgICAgICAgICAgICAgICJyZXN1bHQiOiAiUEFTUyIsCiAgICAgICAgICAgICAgICAic2VjcmV0X3ZhbHVlX2V4cG9zZWQiOiBGYWxzZSwKICAgICAgICAgICAgfSkKICAgICAgICAgICAgc2VsZi5fc2VuZChIVFRQU3RhdHVzLk9LLCBqc29uLmR1bXBzKHBheWxvYWQsIGVuc3VyZV9hc2NpaT1UcnVlLCBzb3J0X2tleXM9VHJ1ZSkgKyAiXFxuIiwgY29udGVudF90eXBlPSJhcHBsaWNhdGlvbi9qc29uOyBjaGFyc2V0PXV0Zi04IikKICAgICAgICAgICAgcmV0dXJuCicnJwpORVdfQlJBTkNIID0gJycnICAgICAgICBpZiBwYXJzZWQucGF0aCA9PSBUSUtUT0tfRElTQ09OTkVDVF9QQVRIOgogICAgICAgICAgICBzeXMuc3RkZXJyLndyaXRlKCJzZWN1cml0eV9ldmVudD1USUtUT0tfRElTQ09OTkVDVF9IVFRQX0RFTklFRFxcbiIpCiAgICAgICAgICAgIHNlbGYuX3NlbmQoSFRUUFN0YXR1cy5GT1JCSURERU4sIGpzb24uZHVtcHMoewogICAgICAgICAgICAgICAgInN0YXR1cyI6ICJSRUpFQ1RFRCIsCiAgICAgICAgICAgICAgICAic2FuaXRpemVkX2Vycm9yX2NvZGUiOiAiRElTQ09OTkVDVF9ESVNBQkxFRF9BVVRIX05PVF9JTlRFR1JBVEVEIiwKICAgICAgICAgICAgICAgICJvcGVyYXRpb25fcGVyZm9ybWVkIjogRmFsc2UsCiAgICAgICAgICAgIH0sIGVuc3VyZV9hc2NpaT1UcnVlLCBzb3J0X2tleXM9VHJ1ZSkgKyAiXFxuIiwgY29udGVudF90eXBlPSJhcHBsaWNhdGlvbi9qc29uOyBjaGFyc2V0PXV0Zi04IikKICAgICAgICAgICAgcmV0dXJuCicnJwoKCmRlZiBidWlsZF9jYW5kaWRhdGUoc291cmNlKToKICAgIGlmIG5vdCBpc2luc3RhbmNlKHNvdXJjZSwgYnl0ZXMpOgogICAgICAgIHJhaXNlIFR5cGVFcnJvcigiU09VUkNFX0JZVEVTX1JFUVVJUkVEIikKICAgIGlmIGhhc2hsaWIuc2hhMjU2KHNvdXJjZSkuaGV4ZGlnZXN0KCkgIT0gU09VUkNFX1NIQTI1NjoKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJTT1VSQ0VfU0hBMjU2X01JU01BVENIIikKICAgIG9sZCwgbmV3ID0gT0xEX0JSQU5DSC5lbmNvZGUoKSwgTkVXX0JSQU5DSC5lbmNvZGUoKQogICAgaWYgc291cmNlLmNvdW50KG9sZCkgIT0gMToKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJVTklRVUVfRElTQ09OTkVDVF9CUkFOQ0hfUkVRVUlSRUQiKQogICAgcmV0dXJuIHNvdXJjZS5yZXBsYWNlKG9sZCwgbmV3LCAxKQo="
UNIT = "secure-secrets-portal.service"


def root_chain(path):
    for item in reversed((path,) + tuple(path.parents)):
        info = item.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("ROOT_PATH_IDENTITY")


def load_engine():
    root_chain(HELPER.parent)
    fd = os.open(HELPER, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o755):
            raise ValueError("REUSED_HELPER_IDENTITY")
        data = handle.read(1000001)
    if hashlib.sha256(data).hexdigest() != HELPER_SHA256:
        raise ValueError("REUSED_HELPER_SHA256")
    engine = types.ModuleType("r4_reused_transaction_engine")
    exec(compile(data, str(HELPER), "exec"), engine.__dict__)
    guard_data = base64.b64decode(GUARD_B64, validate=True)
    if hashlib.sha256(guard_data).hexdigest() != GUARD_SHA256:
        raise ValueError("APPROVED_GUARD_SHA256")
    guard = types.ModuleType("r4_exact_approved_builder")
    exec(compile(guard_data, "<approved-r4-builder>", "exec"), guard.__dict__)
    engine.SOURCE_SHA256 = SOURCE_SHA256
    engine.CANDIDATE_SHA256 = CANDIDATE_SHA256
    engine.build_candidate = guard.build_candidate
    return engine


def service_state():
    result = subprocess.run(["/usr/bin/systemctl", "show", UNIT, "-p", "MainPID",
        "-p", "User", "-p", "ActiveState", "-p", "SubState", "-p", "WorkingDirectory"],
        check=True, capture_output=True, text=True, timeout=10,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"})
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def stop_backend():
    subprocess.run(["/usr/bin/systemctl", "stop", UNIT], check=True, timeout=40,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"})


def backend_closed():
    with socket.socket() as connection:
        connection.settimeout(2)
        try:
            return connection.connect_ex(("127.0.0.1", 18080)) == errno.ECONNREFUSED
        except OSError:
            return False


def running(state):
    return (state.get("ActiveState") == "active" and state.get("SubState") == "running"
        and state.get("User") == "admin" and state.get("WorkingDirectory") == "/opt/trading-system"
        and state.get("MainPID", "0").isdigit() and int(state["MainPID"]) > 0)


class Operation:
    def __init__(self, engine, root=STATE, source=TARGET, summary=SUMMARY,
                 inspect=service_state, restart=None, health=None, negative=None,
                 stop=stop_backend, offline_confirm=backend_closed):
        self.engine, self.root, self.source, self.summary = engine, Path(root), Path(source), Path(summary)
        self.inspect, self.stop = inspect, stop
        self.offline_confirm = offline_confirm
        self.health = health or (lambda: engine.verify_live(501))
        self.negative = negative or self.verify_disabled_http
        self.cap = engine.Capability(root=self.root, source=self.source,
            restart=restart or engine.restart_portal, verify=self.verify_after,
            preflight=self.preflight)

    def current(self, expected):
        data, info = self.cap.source_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("LIVE_SOURCE_HASH_CHANGED")
        return data, info

    def preflight(self):
        self.before = self.inspect()
        if not running(self.before):
            raise ValueError("EXPECTED_RUNNING_PORTAL_REQUIRED")

    def verify_after(self, ignored):
        self.current(self.engine.CANDIDATE_SHA256)
        after = self.inspect()
        if not running(after) or after["MainPID"] == self.before["MainPID"]:
            raise ValueError("NEW_RUNNING_PORTAL_PID_REQUIRED")
        checks = self.health()
        self.current(self.engine.CANDIDATE_SHA256)
        checks.extend(self.negative())
        self.cap.record["service_before"] = self.before
        self.cap.record["service_after"] = after
        return checks

    def verify_disabled_http(self):
        """Proposed safe negative POST only after exact new bytes + fresh PID.

        This action still requires installation-plan approval. No real session,
        account ID, Cookie, bearer token or business data is sent.
        """
        checks = []
        domain = "wenwenwenyiyiyi.work"
        for address in ("47.245.53.152", "47.101.152.210"):
            for variant in ("empty", "synthetic_untrusted_headers"):
                self.current(self.engine.CANDIDATE_SHA256)
                raw = socket.create_connection((address, 443), timeout=8)
                tls = ssl.create_default_context().wrap_socket(raw, server_hostname=domain)
                conn = http.client.HTTPConnection(domain, timeout=8)
                conn.sock = tls
                try:
                    headers = {"Host": domain, "Connection": "close", "Content-Length": "0"}
                    if variant != "empty":
                        headers.update({"Origin": "https://invalid.example", "X-Authenticated-User": "SYNTHETIC_OWNER", "X-CSRF-Token": "SYNTHETIC_INVALID"})
                    conn.request("POST", "/integrations/tiktok/disconnect", body=b"", headers=headers)
                    response = conn.getresponse()
                    data = response.read(4096)
                    if response.status != 403 or response.getheader("Set-Cookie"):
                        raise ValueError("LIVE_CONTAINMENT_STATUS")
                    if json.loads(data) != {"status": "REJECTED", "sanitized_error_code": "DISCONNECT_DISABLED_AUTH_NOT_INTEGRATED", "operation_performed": False}:
                        raise ValueError("LIVE_CONTAINMENT_BODY")
                    checks.append({"address": address, "variant": variant, "method": "POST", "status": 403, "tls_verified": True, "synthetic_empty_request": True})
                finally:
                    conn.close()
        return checks

    def publish(self):
        self.cap.load()
        record = self.cap.record
        # Only fixed operational metadata; never copy private source or grant.
        public = {"schema_version": 1, "action": "PR122_R4_CONTAINMENT_V1",
            "host": HOST, "status": record["status"], "source_sha256": self.engine.SOURCE_SHA256,
            "candidate_sha256": self.engine.CANDIDATE_SHA256,
            "apply_started": record.get("apply_started", False),
            "offline_rollback_started": record.get("offline_rollback_started", False),
            "checks": record.get("checks", []), "service_before": record.get("service_before"),
            "service_after": record.get("service_after"), "error": record.get("error"),
            "dns_change": False, "website_files_changed": False,
            "tiktok_http_disconnect": "TEMPORARILY_DISABLED" if record["status"] == "LIVE_R4_CONTAINMENT_PASS" else "NOT_ESTABLISHED",
            "authenticated_disconnect": "NOT_IMPLEMENTED"}
        if os.path.lexists(self.summary):
            data, _ = self.engine.checked_read(self.summary, 0, 0o644)
            if json.loads(data).get("action") != public["action"]:
                raise ValueError("PUBLIC_RECEIPT_IDENTITY")
        self.engine.atomic_write(self.summary, (json.dumps(public, sort_keys=True) + "\n").encode(), mode=0o644)
        return public

    def install(self):
        if os.path.lexists(self.root) or os.path.lexists(self.summary):
            raise ValueError("NO_BLIND_INSTALL_RETRY")
        data, _ = self.current(self.engine.SOURCE_SHA256)
        candidate = self.engine.build_candidate(data)
        if hashlib.sha256(candidate).hexdigest() != self.engine.CANDIDATE_SHA256:
            raise ValueError("CANDIDATE_HASH_MISMATCH")
        ast.parse(candidate)
        self.preflight()
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.engine.atomic_write(self.root / "grant.json", json.dumps({
            "scope": "OWNER_LONG_TERM_DOMESTIC_TOKYO_MIGRATION_R4_FIXED_ACTION",
            "source_scope_approval": "PR122#6205371670",
            "install_plan_approval": "REQUIRED_BEFORE_OWNER_EXECUTION",
            "full_authenticated_disconnect": "NOT_IMPLEMENTED"}).encode())
        try:
            self.cap.run("apply")
            self.cap.record["status"] = "LIVE_R4_CONTAINMENT_PASS"
            self.cap.save()
            return self.publish()
        except BaseException as error:
            # Inherited engine preserves its bounded failure receipt and backup.
            self.cap.load()
            self.cap.record.update(status="UNKNOWN_PRESERVE_EVIDENCE", error=type(error).__name__)
            self.cap.save()
            self.publish()
            raise

    def rollback_offline(self):
        """Emergency-only proposed rollback: old vulnerable code stays OFFLINE.

        Never automatic. Stops only Portal (not Nginx/VM), verifies MainPID=0,
        restores exact backup, and DOES NOT restart. Requires independent plan
        acceptance and deliberate Owner root invocation; dynamic routes outage.
        """
        self.cap.load()
        if not self.cap.record.get("apply_started") or self.cap.record.get("offline_rollback_started"):
            raise ValueError("OFFLINE_ROLLBACK_NOT_ALLOWED")
        _, info = self.current(self.engine.CANDIDATE_SHA256)
        backup, _ = self.engine.checked_read(self.root / "source.before.py", 0, 0o400)
        if hashlib.sha256(backup).hexdigest() != self.engine.SOURCE_SHA256:
            raise ValueError("ROLLBACK_BACKUP_HASH")
        self.cap.record.update(offline_rollback_started=True, status="OFFLINE_ROLLBACK_STARTED")
        self.cap.save()
        try:
            self.stop()
            stopped = self.inspect()
            if (stopped.get("MainPID") != "0"
                    or stopped.get("ActiveState") not in ("inactive", "failed")
                    or not self.offline_confirm()):
                raise ValueError("PORTAL_STOP_NOT_CONFIRMED")
            self.current(self.engine.CANDIDATE_SHA256)
            self.engine.atomic_write(self.source, backup, info.st_uid, info.st_gid, 0o755)
            self.cap.record.update(status="ROLLED_BACK_BACKEND_STOPPED", checks=[], service_after=stopped)
            self.cap.save()
            return self.publish()
        except BaseException as error:
            self.cap.record.update(status="UNKNOWN_PRESERVE_EVIDENCE", error=type(error).__name__)
            self.cap.save()
            self.publish()
            raise


def lock_file(path, *, create):
    flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0)
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600):
        os.close(fd)
        raise ValueError("EXECUTION_LOCK_IDENTITY")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("--install", "--status", "--rollback-offline"):
        raise SystemExit("ONE_FIXED_ACTION_REQUIRED")
    if os.geteuid() != 0 or os.uname().nodename != HOST:
        raise SystemExit("ROOT_ON_APPROVED_TOKYO_REQUIRED")
    os.umask(0o077)
    engine = load_engine()
    root_chain(STATE.parent)
    root_chain(Path("/var/lib/xuanjun-pr122-portal-logfix-capability"))
    # Coordinate with the already installed engine; do not change its state.
    locks = []
    try:
        locks.append(lock_file(Path("/var/lib/xuanjun-pr122-portal-logfix-capability/execution.lock"), create=False))
        locks.append(lock_file(Path("/run/xuanjun-pr122-r4-install.lock"), create=True))
        operation = Operation(engine)
        if sys.argv[1] == "--install":
            result = operation.install()
        elif sys.argv[1] == "--rollback-offline":
            result = operation.rollback_offline()
        else:
            result = operation.cap.run("status")
        print(json.dumps(result, sort_keys=True))
    except BaseException as error:
        print(json.dumps({"status": "HOLD_PRESERVE_EVIDENCE", "reason": type(error).__name__, "private_state": str(STATE)}, sort_keys=True))
        raise SystemExit(1)
    finally:
        for fd in reversed(locks):
            os.close(fd)


if __name__ == "__main__":
    main()
