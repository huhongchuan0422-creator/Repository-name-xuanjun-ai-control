"""G3 candidate: durable external writer-epoch authorization contract.

The exchange credential/IP allowlist is the hard outer fence.  This module is
defence in depth and deliberately rejects a local-only epoch or SQLite lock.
"""
from __future__ import print_function

import datetime
import hashlib
import os
import re

from archive_binding import verify as verify_detached_signature
from gate_common import IdempotentLedger, require, require_exact_keys


WRITE_ACTIONS = frozenset((
    "CREATE_ORDER", "CANCEL_ORDER", "CANCEL_ALL", "MODIFY_ORDER",
    "PROTECTIVE_CREATE", "PROTECTIVE_REPLACE", "PROTECTIVE_CANCEL",
    "CLOSE_POSITION", "REDUCE_POSITION", "EMERGENCY_CLOSE"
))

PATH_CLASSES = frozenset(("FORMAL", "LEGACY", "PROTECTION", "MANUAL_SCRIPT"))

WRITE_MARKERS = (
    re.compile(r"\b(?:create|place|new|submit)_order\b", re.I),
    re.compile(r"\b(?:cancel|modify|replace)_order\b", re.I),
    re.compile(r"\b(?:cancel_all|close_position|emergency_close)\b", re.I),
    re.compile(r"/fapi/v\d+/(?:order|allOpenOrders|batchOrders|algoOrder)", re.I),
    re.compile(r"\b(?:STOP_MARKET|TAKE_PROFIT_MARKET)\b")
)


def parse_utc(value):
    require(isinstance(value, str) and value.endswith("Z"), "UTC_TIMESTAMP_REQUIRED")
    return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def _sha256_fingerprint(value, code):
    require(isinstance(value, str) and len(value) == 64 and
            all(character in "0123456789abcdef" for character in value), code)


def validate_lease(lease, host, epoch, action, now, binding, trust_policy):
    """Validate a signed external-authority lease contract.

    This verifier has no production authority adapter.  A successful result is
    only eligible for later integration and never grants an exchange write.
    """
    required = (
        "schema_version", "lease_id", "epoch", "external_current_epoch", "writer_host",
        "issued_at", "expires_at", "authority_id", "authoritative_store",
        "credential_fingerprint", "credential_state_verified",
        "ip_allowlist_fingerprint", "ip_allowlist_verified", "previous_epoch_revoked",
        "old_host_credential_revoked", "old_host_ip_removed", "production_release_gate_id"
    )
    require_exact_keys(lease, required)
    require(lease["schema_version"] == 2, "G3_SCHEMA_INVALID")
    require(action in WRITE_ACTIONS, "G3_ACTION_NOT_ALLOWLISTED")
    require(isinstance(trust_policy, dict) and lease["authority_id"] in trust_policy,
            "G3_AUTHORITY_NOT_ALLOWLISTED")
    trusted = trust_policy[lease["authority_id"]]
    require(isinstance(trusted, dict), "G3_TRUST_POLICY_INVALID")
    require(set(trusted) == set(("authoritative_store", "public_key_path",
                                "pinned_public_key_sha256")), "G3_TRUST_POLICY_FIELDS_INVALID")
    require(isinstance(trusted["public_key_path"], str) and
            os.path.isfile(trusted["public_key_path"]), "G3_TRUST_PUBLIC_KEY_REQUIRED")
    _sha256_fingerprint(trusted["pinned_public_key_sha256"],
                        "G3_TRUST_FINGERPRINT_INVALID")
    require(lease["authoritative_store"] == trusted.get("authoritative_store") and
            lease["authoritative_store"] not in ("", "LOCAL_FILE", "LOCAL_SQLITE", "IN_MEMORY"),
            "G3_AUTHORITY_STORE_MISMATCH")
    require(isinstance(binding, dict) and binding.get("key_id") == lease["authority_id"],
            "G3_AUTHORITY_KEY_ID_MISMATCH")
    verify_detached_signature(lease, binding, trusted.get("public_key_path"),
                              trusted.get("pinned_public_key_sha256"))
    for field, code in (
        ("credential_state_verified", "G3_CREDENTIAL_STATE_UNVERIFIED"),
        ("ip_allowlist_verified", "G3_IP_ALLOWLIST_UNVERIFIED"),
        ("previous_epoch_revoked", "G3_PREVIOUS_EPOCH_ACTIVE"),
        ("old_host_credential_revoked", "G3_OLD_HOST_CREDENTIAL_ACTIVE"),
        ("old_host_ip_removed", "G3_OLD_HOST_IP_ALLOWED")
    ):
        require(type(lease[field]) is bool and lease[field] is True, code)
    _sha256_fingerprint(lease["credential_fingerprint"], "G3_CREDENTIAL_FINGERPRINT_INVALID")
    _sha256_fingerprint(lease["ip_allowlist_fingerprint"], "G3_IP_FINGERPRINT_INVALID")
    require(isinstance(lease["production_release_gate_id"], str) and
            lease["production_release_gate_id"], "G3_RELEASE_GATE_REQUIRED")
    require(isinstance(lease["lease_id"], str) and lease["lease_id"], "G3_LEASE_ID_REQUIRED")
    require(isinstance(lease["writer_host"], str) and lease["writer_host"], "G3_WRITER_HOST_REQUIRED")
    require(host == lease["writer_host"], "G3_WRITER_HOST_MISMATCH")
    require(type(epoch) is int and epoch > 0 and type(lease["epoch"]) is int and
            type(lease["external_current_epoch"]) is int and
            epoch == lease["epoch"] == lease["external_current_epoch"], "G3_STALE_EPOCH")
    current = now if now.tzinfo is not None else now.replace(tzinfo=datetime.timezone.utc)
    require(parse_utc(lease["issued_at"]) <= current < parse_utc(lease["expires_at"]), "G3_LEASE_EXPIRED_OR_NOT_YET_VALID")
    return True


def authorize_write(lease, host, epoch, action, request_id, path_class, ledger_path, now,
                    binding, trust_policy):
    """Evaluate and durably deduplicate the contract; never authorize production."""
    require(path_class in PATH_CLASSES, "G3_PATH_CLASS_INVALID")
    require(isinstance(request_id, str) and request_id, "G3_REQUEST_ID_REQUIRED")
    validate_lease(lease, host, epoch, action, now, binding, trust_policy)
    payload = {
        "lease_id": lease["lease_id"], "epoch": epoch, "host": host,
        "action": action, "path_class": path_class, "request_id": request_id,
        "credential_fingerprint": lease["credential_fingerprint"],
        "ip_allowlist_fingerprint": lease["ip_allowlist_fingerprint"]
    }
    replay = IdempotentLedger(ledger_path).record(request_id, payload)
    return {
        "contract_accepted": not replay["replayed"],
        "replayed": replay["replayed"],
        "payload_digest": replay["digest"],
        "execution_authorized": False,
        "scope": "CONTRACT_SIMULATOR_ONLY_NOT_PRODUCTION_AUTHORITY"
    }


def evaluate_path_coverage(records):
    """Every reachable writer must be fenced or made unreachable."""
    require(isinstance(records, list) and records, "G3_PATH_INVENTORY_REQUIRED")
    failures = []
    identities = set()
    for record in records:
        for key in ("path_id", "path_class", "source_path", "reachable", "fence_call", "credential_access", "scheduler_access"):
            require(key in record, "G3_PATH_FIELD_MISSING:" + key)
        require(record["path_id"] not in identities, "G3_DUPLICATE_PATH_ID")
        identities.add(record["path_id"])
        require(record["path_class"] in PATH_CLASSES, "G3_PATH_CLASS_INVALID")
        if record["reachable"]:
            if not record["fence_call"] or not record["credential_access"]:
                failures.append(record["path_id"] + ":REACHABLE_UNFENCED")
        else:
            if record["credential_access"] or record["scheduler_access"]:
                failures.append(record["path_id"] + ":QUARANTINE_INCOMPLETE")
    return {"status": "PASS" if not failures else "HOLD", "failures": failures, "checked": len(records)}


def reboot_verdict(lease, rebooted_host, presented_epoch, now, binding, trust_policy):
    try:
        validate_lease(lease, rebooted_host, presented_epoch, "CREATE_ORDER", now,
                       binding, trust_policy)
    except Exception:
        return "DENY"
    return "CONTRACT_VALID_NOT_AUTHORIZED"


def _path_class(path):
    name = os.path.basename(path).lower()
    if name.startswith("manual_"):
        return "MANUAL_SCRIPT"
    if any(token in name for token in ("guard", "protect", "sentinel", "stop")):
        return "PROTECTION"
    if "/opt/trading-system/" in path:
        return "FORMAL"
    return "LEGACY"


def discover_writer_paths(roots):
    """Read source only; return every file containing a conservative write marker."""
    findings = []
    for root in roots:
        require(os.path.isdir(root), "G3_SCAN_ROOT_MISSING")
        for directory, names, files in os.walk(root):
            names[:] = sorted(name for name in names if name not in (".git", "venv", "__pycache__", "backup", "backups", "logs", "archives"))
            for name in sorted(files):
                if not name.endswith(".py") or name.startswith("test_"):
                    continue
                path = os.path.join(directory, name)
                try:
                    with open(path, "rb") as stream:
                        raw = stream.read()
                    text = raw.decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    findings.append({"source_path": path, "path_class": _path_class(path),
                                     "sha256": None, "markers": ["UNREADABLE_FAIL_CLOSED"]})
                    continue
                markers = sorted(set(pattern.pattern for pattern in WRITE_MARKERS if pattern.search(text)))
                if markers:
                    findings.append({"source_path": path, "path_class": _path_class(path),
                                     "sha256": hashlib.sha256(raw).hexdigest(), "markers": markers})
    return findings


def bind_discovery_to_coverage(findings, coverage):
    discovered = {record["source_path"]: record["sha256"] for record in findings}
    declared = {record["source_path"]: record.get("source_sha256") for record in coverage}
    missing = sorted(set(discovered) - set(declared))
    stale = sorted(path for path in set(discovered) & set(declared) if discovered[path] != declared[path])
    extra = sorted(set(declared) - set(discovered))
    result = evaluate_path_coverage(coverage) if coverage else {"status": "HOLD", "failures": ["EMPTY_COVERAGE"], "checked": 0}
    if missing or stale or extra:
        result = dict(result)
        result["status"] = "HOLD"
    result.update({"missing": missing, "stale": stale, "extra": extra,
                   "discovery_count": len(findings)})
    return result
