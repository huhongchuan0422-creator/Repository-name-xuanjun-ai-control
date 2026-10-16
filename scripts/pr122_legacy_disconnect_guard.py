"""R4 containment candidate: disable the legacy HTTP disconnect operation.

This is NOT an authenticated disconnect implementation or a production installer.
Only the exact deployed legacy source is accepted; all other bytes are preserved.
"""
import hashlib

SOURCE_SHA256 = "d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0"
OLD_BRANCH = '''        if parsed.path == TIKTOK_DISCONNECT_PATH:
            payload = TikTokTokenLifecycleStore(DEFAULT_STATE_ROOT / "tiktok-token-state").disconnect()
            self.server.portal_service.operations_store.record_audit({
                "operation": "TIKTOK_DISCONNECT",
                "provider": "tiktok",
                "result": "PASS",
                "secret_value_exposed": False,
            })
            self._send(HTTPStatus.OK, json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\\n", content_type="application/json; charset=utf-8")
            return
'''
NEW_BRANCH = '''        if parsed.path == TIKTOK_DISCONNECT_PATH:
            sys.stderr.write("security_event=TIKTOK_DISCONNECT_HTTP_DENIED\\n")
            self._send(HTTPStatus.FORBIDDEN, json.dumps({
                "status": "REJECTED",
                "sanitized_error_code": "DISCONNECT_DISABLED_AUTH_NOT_INTEGRATED",
                "operation_performed": False,
            }, ensure_ascii=True, sort_keys=True) + "\\n", content_type="application/json; charset=utf-8")
            return
'''


def build_candidate(source):
    if not isinstance(source, bytes):
        raise TypeError("SOURCE_BYTES_REQUIRED")
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("SOURCE_SHA256_MISMATCH")
    old, new = OLD_BRANCH.encode(), NEW_BRANCH.encode()
    if source.count(old) != 1:
        raise ValueError("UNIQUE_DISCONNECT_BRANCH_REQUIRED")
    return source.replace(old, new, 1)
