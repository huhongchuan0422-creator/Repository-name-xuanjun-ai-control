"""Signed, non-privileged restricted-executor candidate.

Only an independently Ed25519-verified policy can reach the injected candidate
runner.  This module still has no sudo, SSH, systemd or root transport.
"""
from __future__ import print_function

import hashlib
import json
import os
import pwd
import re
import socket
import sqlite3
import stat
import time

from gate_common import GateError, bounded_call, canonical_bytes, require, sha256_value


ALLOWED_HOSTS = frozenset(("iZ6wee8q9z4t03hvqumwfhZ", "iZmj7a5kwr75qc1tul4kf9Z"))
ALLOWED_ACTIONS = frozenset(("READONLY_INSPECT", "RUNNER_RETIRE", "YIBI_RETIRE",
                             "WRITER_FENCE", "KOREA_DEPLOY", "KOREA_LOCK_WRITER"))
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX128 = re.compile(r"^[0-9a-f]{128}$")
_VERIFIED_SENTINEL = object()


def _hex64(value, code):
    require(isinstance(value, str) and HEX64.match(value) is not None, code)


def _identifier(value, code):
    require(isinstance(value, str) and value and len(value) <= 160 and
            all(character.isalnum() or character in "-_.:@" for character in value), code)


def _secure_file(path, expected_uid, code):
    require(isinstance(path, str) and os.path.isabs(path), code + "_ABSOLUTE_REQUIRED")
    absolute = os.path.abspath(path)
    require(os.path.realpath(absolute) == absolute, code + "_SYMLINK_COMPONENT_FORBIDDEN")
    value = os.lstat(absolute)
    require(stat.S_ISREG(value.st_mode), code + "_REGULAR_FILE_REQUIRED")
    require(value.st_uid == expected_uid, code + "_OWNER_INVALID")
    require(stat.S_IMODE(value.st_mode) & 0o022 == 0, code + "_GROUP_OTHER_WRITE_FORBIDDEN")
    return absolute


def _secure_allowlisted_path(path, expected_uid):
    require(isinstance(path, str) and os.path.isabs(path), "EXECUTOR_PATH_ABSOLUTE_REQUIRED")
    normalized = os.path.normpath(path)
    require(normalized == path and os.path.realpath(path) == path,
            "EXECUTOR_PATH_NOT_CANONICAL_OR_SYMLINKED")
    require(os.path.exists(path), "EXECUTOR_PATH_MUST_EXIST_FOR_OWNERSHIP_PROOF")
    target, parent = os.lstat(path), os.lstat(os.path.dirname(path))
    require(target.st_uid == expected_uid and parent.st_uid == expected_uid,
            "EXECUTOR_PATH_OWNER_INVALID")
    require(target.st_mode & 0o022 == 0 and parent.st_mode & 0o022 == 0,
            "EXECUTOR_PATH_GROUP_OTHER_WRITE_FORBIDDEN")
    return path


# Minimal RFC8032 verification primitives (verification only; no private-key API).
_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _xrecover(y):
    xx = (y * y - 1) * pow(_D * y * y + 1, _Q - 2, _Q) % _Q
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    require((x * x - xx) % _Q == 0, "EXECUTOR_ED25519_POINT_INVALID")
    return _Q - x if x & 1 else x


_BY = 4 * pow(5, _Q - 2, _Q) % _Q
_B = (_xrecover(_BY), _BY)


def _edwards(point, other):
    x1, y1 = point; x2, y2 = other
    return (((x1 * y2 + x2 * y1) * pow(1 + _D * x1 * x2 * y1 * y2, _Q - 2, _Q)) % _Q,
            ((y1 * y2 + x1 * x2) * pow(1 - _D * x1 * x2 * y1 * y2, _Q - 2, _Q)) % _Q)


def _scalarmult(point, scalar):
    result, addend = (0, 1), point
    while scalar:
        if scalar & 1:
            result = _edwards(result, addend)
        addend = _edwards(addend, addend)
        scalar >>= 1
    return result


def _decodepoint(value):
    require(isinstance(value, bytes) and len(value) == 32, "EXECUTOR_ED25519_POINT_LENGTH")
    y = int.from_bytes(value, "little") & ((1 << 255) - 1)
    require(y < _Q, "EXECUTOR_ED25519_POINT_RANGE")
    x = _xrecover(y)
    if (x & 1) != (value[31] >> 7):
        x = _Q - x
    return x, y


def _encodepoint(point):
    x, y = point
    value = y | ((x & 1) << 255)
    return value.to_bytes(32, "little")


def verify_ed25519(public_key, message, signature):
    require(isinstance(public_key, bytes) and len(public_key) == 32,
            "EXECUTOR_ED25519_PUBLIC_KEY_INVALID")
    require(isinstance(signature, bytes) and len(signature) == 64,
            "EXECUTOR_ED25519_SIGNATURE_INVALID")
    encoded_r, scalar_s = signature[:32], int.from_bytes(signature[32:], "little")
    require(scalar_s < _L, "EXECUTOR_ED25519_SCALAR_INVALID")
    public_point, r_point = _decodepoint(public_key), _decodepoint(encoded_r)
    challenge = int.from_bytes(hashlib.sha512(encoded_r + public_key + message).digest(),
                               "little") % _L
    require(_encodepoint(_scalarmult(_B, scalar_s)) ==
            _encodepoint(_edwards(r_point, _scalarmult(public_point, challenge))),
            "EXECUTOR_ED25519_SIGNATURE_MISMATCH")
    return True


class VerifiedPolicy(object):
    def __init__(self, policy, anchor, expected_path_owner_uid, sentinel):
        require(sentinel is _VERIFIED_SENTINEL, "EXECUTOR_VERIFIED_POLICY_CONSTRUCTION_FORBIDDEN")
        self.policy, self.anchor = policy, anchor
        self.expected_path_owner_uid = expected_path_owner_uid


def validate_policy(policy, expected_path_owner_uid):
    required = ("schema_version", "policy_id", "candidate_sha256", "expires_at_epoch",
                "hosts", "one_time_authority_id", "authorized_request_sha256",
                "execution_identity", "trust_anchor_sha256",
                "independent_verifier_sha256")
    require(isinstance(policy, dict) and set(policy) == set(required),
            "EXECUTOR_POLICY_FIELDS_INVALID")
    require(type(policy["schema_version"]) is int and policy["schema_version"] == 3,
            "EXECUTOR_POLICY_SCHEMA_INVALID")
    _identifier(policy["policy_id"], "EXECUTOR_POLICY_ID_INVALID")
    _hex64(policy["candidate_sha256"], "EXECUTOR_VERSION_HASH_INVALID")
    _hex64(policy["authorized_request_sha256"], "EXECUTOR_AUTHORIZED_REQUEST_HASH_INVALID")
    _hex64(policy["trust_anchor_sha256"], "EXECUTOR_TRUST_ANCHOR_HASH_INVALID")
    _hex64(policy["independent_verifier_sha256"],
           "EXECUTOR_INDEPENDENT_VERIFIER_HASH_INVALID")
    require(type(policy["expires_at_epoch"]) is int, "EXECUTOR_EXPIRY_INVALID")
    _identifier(policy["one_time_authority_id"], "EXECUTOR_AUTHORITY_ID_REQUIRED")
    _identifier(policy["execution_identity"], "EXECUTOR_EXECUTION_IDENTITY_INVALID")
    require(isinstance(policy["hosts"], dict) and policy["hosts"] and
            set(policy["hosts"]).issubset(ALLOWED_HOSTS), "EXECUTOR_HOSTS_INVALID")
    for unused_host, value in policy["hosts"].items():
        require(isinstance(value, dict) and set(value) == set(("paths", "units", "actions")),
                "EXECUTOR_HOST_POLICY_INVALID")
        require(isinstance(value["paths"], list) and len(value["paths"]) == len(set(value["paths"])),
                "EXECUTOR_PATH_LIST_INVALID")
        for path in value["paths"]:
            _secure_allowlisted_path(path, expected_path_owner_uid)
        require(isinstance(value["units"], list) and len(value["units"]) == len(set(value["units"])) and
                all(isinstance(unit, str) and unit.endswith((".service", ".timer"))
                    for unit in value["units"]), "EXECUTOR_UNIT_INVALID")
        require(isinstance(value["actions"], list) and
                set(value["actions"]).issubset(ALLOWED_ACTIONS), "EXECUTOR_ACTION_INVALID")
    return True


def load_verified_policy(policy_path, signature_path, trust_anchor_path, expected_owner_uid):
    """Load root/owner-controlled raw files and independently verify Ed25519."""
    require(type(expected_owner_uid) is int and expected_owner_uid >= 0,
            "EXECUTOR_EXPECTED_OWNER_UID_INVALID")
    policy_path = _secure_file(policy_path, expected_owner_uid, "EXECUTOR_POLICY_FILE")
    signature_path = _secure_file(signature_path, expected_owner_uid, "EXECUTOR_SIGNATURE_FILE")
    trust_anchor_path = _secure_file(trust_anchor_path, expected_owner_uid, "EXECUTOR_ANCHOR_FILE")
    with open(policy_path, "rb") as stream:
        policy_bytes = stream.read()
    with open(signature_path, "r") as stream:
        signature_hex = stream.read().strip()
    with open(trust_anchor_path, "r") as stream:
        anchor = json.load(stream)
    require(isinstance(anchor, dict) and set(anchor) ==
            set(("schema_version", "algorithm", "authority_id", "public_key_hex")),
            "EXECUTOR_TRUST_ANCHOR_FIELDS_INVALID")
    require(anchor["schema_version"] == 1 and anchor["algorithm"] == "Ed25519",
            "EXECUTOR_TRUST_ANCHOR_SCHEMA_INVALID")
    _identifier(anchor["authority_id"], "EXECUTOR_TRUST_ANCHOR_AUTHORITY_INVALID")
    require(isinstance(anchor["public_key_hex"], str) and HEX64.match(
        anchor["public_key_hex"]) is not None, "EXECUTOR_TRUST_ANCHOR_KEY_INVALID")
    require(HEX128.match(signature_hex) is not None, "EXECUTOR_SIGNATURE_HEX_INVALID")
    try:
        policy = json.loads(policy_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GateError("EXECUTOR_POLICY_JSON_INVALID")
    require(policy_bytes == canonical_bytes(policy), "EXECUTOR_POLICY_NOT_CANONICAL")
    validate_policy(policy, expected_owner_uid)
    require(policy["one_time_authority_id"] == anchor["authority_id"],
            "EXECUTOR_POLICY_ANCHOR_AUTHORITY_MISMATCH")
    require(policy["trust_anchor_sha256"] == sha256_value(anchor),
            "EXECUTOR_TRUST_ANCHOR_NOT_HASH_BOUND")
    verify_ed25519(bytes.fromhex(anchor["public_key_hex"]), policy_bytes,
                   bytes.fromhex(signature_hex))
    return VerifiedPolicy(policy, anchor, expected_owner_uid, _VERIFIED_SENTINEL)


class TransactionLedger(object):
    def __init__(self, path):
        self.path = path
        self.connection = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS transactions ("
                                "tx_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, "
                                "nonce_sha256 TEXT NOT NULL UNIQUE, state TEXT NOT NULL, "
                                "intent_json TEXT NOT NULL, result_json TEXT, updated_at INTEGER NOT NULL)")

    def close(self):
        self.connection.close()

    def intent(self, tx_id, request):
        digest, payload = sha256_value(request), canonical_bytes(request).decode("ascii")
        self.connection.execute("BEGIN IMMEDIATE")
        row = self.connection.execute("SELECT request_sha256,state FROM transactions WHERE tx_id=?",
                                      (tx_id,)).fetchone()
        if row:
            self.connection.rollback()
            require(row[0] == digest, "EXECUTOR_TRANSACTION_CONFLICT")
            raise GateError("EXECUTOR_NO_BLIND_RETRY_EXISTING_STATE:" + row[1])
        try:
            self.connection.execute("INSERT INTO transactions VALUES(?,?,?,?,?,?,?)",
                                    (tx_id, digest, request["one_time_nonce_sha256"],
                                     "INTENT", payload, None, int(time.time())))
        except sqlite3.IntegrityError:
            self.connection.rollback()
            raise GateError("EXECUTOR_ONE_TIME_NONCE_REPLAY")
        self.connection.commit()

    def finish(self, tx_id, state, result):
        require(state in ("SUCCEEDED", "FAILED", "UNKNOWN"), "EXECUTOR_RESULT_STATE_INVALID")
        self.connection.execute("BEGIN IMMEDIATE")
        row = self.connection.execute("SELECT state FROM transactions WHERE tx_id=?", (tx_id,)).fetchone()
        require(row and row[0] == "INTENT", "EXECUTOR_INTENT_STATE_REQUIRED")
        self.connection.execute("UPDATE transactions SET state=?,result_json=?,updated_at=? WHERE tx_id=?",
                                (state, canonical_bytes(result).decode("ascii"), int(time.time()), tx_id))
        self.connection.commit()

    def read(self, tx_id):
        row = self.connection.execute(
            "SELECT request_sha256,state,intent_json,result_json FROM transactions WHERE tx_id=?",
            (tx_id,)).fetchone()
        return None if not row else {"request_sha256": row[0], "state": row[1],
                                     "intent": json.loads(row[2]),
                                     "result": json.loads(row[3]) if row[3] else None}


def runtime_identity():
    return {"host": socket.gethostname(), "os_identity": pwd.getpwuid(os.geteuid()).pw_name}


def _strict_runner_result(value, action):
    required = ("schema_version", "action", "outcome", "side_effects_attempted",
                "side_effects", "effect_verification", "postcondition_verified",
                "completed_at_epoch", "evidence_sha256")
    require(isinstance(value, dict) and set(value) == set(required),
            "EXECUTOR_RESULT_FIELDS_INVALID")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1,
            "EXECUTOR_RESULT_SCHEMA_INVALID")
    require(value["action"] == action, "EXECUTOR_RESULT_ACTION_MISMATCH")
    require(value["outcome"] in ("SUCCEEDED", "FAILED", "UNKNOWN"),
            "EXECUTOR_RESULT_OUTCOME_INVALID")
    require(type(value["side_effects_attempted"]) is bool, "EXECUTOR_RESULT_EFFECT_FLAG_INVALID")
    require(isinstance(value["side_effects"], list) and
            all(isinstance(item, dict) and
                set(item) == set(("effect_id", "kind", "target_sha256", "claimed_state")) and
                isinstance(item["effect_id"], str) and item["effect_id"] and
                isinstance(item["kind"], str) and item["kind"] and
                HEX64.match(item["target_sha256"]) is not None and
                isinstance(item["claimed_state"], str) and item["claimed_state"]
                for item in value["side_effects"]),
            "EXECUTOR_RESULT_EFFECTS_INVALID")
    require(isinstance(value["effect_verification"], list) and
            all(isinstance(item, dict) and set(item) == set(("effect_id", "verified", "evidence_sha256")) and
                isinstance(item["effect_id"], str) and item["effect_id"] and
                type(item["verified"]) is bool and HEX64.match(item["evidence_sha256"]) is not None
                for item in value["effect_verification"]), "EXECUTOR_RESULT_VERIFICATION_INVALID")
    require(type(value["postcondition_verified"]) is bool,
            "EXECUTOR_RESULT_POSTCONDITION_TYPE_INVALID")
    require(type(value["completed_at_epoch"]) is int, "EXECUTOR_RESULT_TIME_INVALID")
    _hex64(value["evidence_sha256"], "EXECUTOR_RESULT_EVIDENCE_HASH_INVALID")
    effect_ids = [item["effect_id"] for item in value["side_effects"]]
    verification_ids = [item["effect_id"] for item in value["effect_verification"]]
    require(len(effect_ids) == len(set(effect_ids)) and
            len(verification_ids) == len(set(verification_ids)) and
            set(effect_ids) == set(verification_ids),
            "EXECUTOR_RESULT_EFFECT_VERIFICATION_COVERAGE_INVALID")
    require(value["side_effects_attempted"] is bool(effect_ids),
            "EXECUTOR_RESULT_EFFECT_ATTEMPT_MISMATCH")
    if value["outcome"] == "SUCCEEDED":
        require(value["postcondition_verified"] is True and
                all(item["verified"] is True for item in value["effect_verification"]),
                "EXECUTOR_SUCCESS_EFFECTS_NOT_VERIFIED")
    return value


def _strict_expected_postconditions(value, action):
    require(isinstance(value, list) and value,
            "EXECUTOR_EXPECTED_POSTCONDITIONS_REQUIRED")
    identifiers = []
    for item in value:
        require(isinstance(item, dict) and set(item) == set((
            "postcondition_id", "kind", "target_sha256", "required_state", "is_effect")),
            "EXECUTOR_EXPECTED_POSTCONDITION_FIELDS_INVALID")
        _identifier(item["postcondition_id"],
                    "EXECUTOR_EXPECTED_POSTCONDITION_ID_INVALID")
        _identifier(item["kind"], "EXECUTOR_EXPECTED_POSTCONDITION_KIND_INVALID")
        _hex64(item["target_sha256"],
               "EXECUTOR_EXPECTED_POSTCONDITION_TARGET_INVALID")
        _identifier(item["required_state"],
                    "EXECUTOR_EXPECTED_POSTCONDITION_STATE_INVALID")
        require(type(item["is_effect"]) is bool,
                "EXECUTOR_EXPECTED_POSTCONDITION_EFFECT_TYPE_INVALID")
        identifiers.append(item["postcondition_id"])
    require(len(identifiers) == len(set(identifiers)),
            "EXECUTOR_EXPECTED_POSTCONDITION_DUPLICATE")
    if action == "READONLY_INSPECT":
        require(not any(item["is_effect"] for item in value),
                "EXECUTOR_READONLY_EFFECT_FORBIDDEN")
    else:
        require(all(item["is_effect"] for item in value),
                "EXECUTOR_MUTATION_EFFECT_POSTCONDITION_REQUIRED")
    return value


def _strict_independent_verification(value, request, runner_result):
    required = ("schema_version", "tx_id", "host", "action", "candidate_sha256",
                "verifier_sha256", "runner_result_sha256", "observed_at_epoch",
                "observations", "all_postconditions_verified", "evidence_sha256")
    require(isinstance(value, dict) and set(value) == set(required),
            "EXECUTOR_INDEPENDENT_VERIFICATION_FIELDS_INVALID")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1,
            "EXECUTOR_INDEPENDENT_VERIFICATION_SCHEMA_INVALID")
    require(value["tx_id"] == request["tx_id"] and value["host"] == request["host"] and
            value["action"] == request["action"] and
            value["candidate_sha256"] == request["candidate_sha256"],
            "EXECUTOR_INDEPENDENT_VERIFICATION_REQUEST_MISMATCH")
    require(value["verifier_sha256"] == request["independent_verifier_sha256"],
            "EXECUTOR_INDEPENDENT_VERIFIER_NOT_REQUEST_BOUND")
    require(value["runner_result_sha256"] == sha256_value(runner_result),
            "EXECUTOR_INDEPENDENT_VERIFICATION_RUNNER_RESULT_MISMATCH")
    require(type(value["observed_at_epoch"]) is int,
            "EXECUTOR_INDEPENDENT_VERIFICATION_TIME_INVALID")
    require(type(value["all_postconditions_verified"]) is bool and
            value["all_postconditions_verified"] is True,
            "EXECUTOR_INDEPENDENT_POSTCONDITIONS_NOT_VERIFIED")
    expected = {item["postcondition_id"]: item
                for item in request["expected_postconditions"]}
    require(isinstance(value["observations"], list) and
            len(value["observations"]) == len(expected),
            "EXECUTOR_INDEPENDENT_OBSERVATION_COUNT_INVALID")
    observed = {}
    allowed_sources = frozenset((
        "FILESYSTEM_DESCRIPTOR", "SYSTEMD_READBACK", "PROCESS_READBACK",
        "GITHUB_ADMIN_API", "OPENCLAW_ADMIN_API", "NETWORK_POLICY_READBACK",
        "DATABASE_READONLY", "EXCHANGE_GET_RECEIPT"))
    for item in value["observations"]:
        require(isinstance(item, dict) and set(item) == set((
            "postcondition_id", "kind", "target_sha256", "observed_state",
            "source_class", "verified", "evidence_sha256")),
            "EXECUTOR_INDEPENDENT_OBSERVATION_FIELDS_INVALID")
        identifier = item["postcondition_id"]
        require(identifier in expected and identifier not in observed,
                "EXECUTOR_INDEPENDENT_OBSERVATION_ID_INVALID")
        wanted = expected[identifier]
        require(item["kind"] == wanted["kind"] and
                item["target_sha256"] == wanted["target_sha256"] and
                item["observed_state"] == wanted["required_state"] and
                item["source_class"] in allowed_sources and
                type(item["verified"]) is bool and item["verified"] is True,
                "EXECUTOR_INDEPENDENT_OBSERVATION_MISMATCH")
        _hex64(item["evidence_sha256"],
               "EXECUTOR_INDEPENDENT_OBSERVATION_EVIDENCE_INVALID")
        observed[identifier] = item
    unsigned = dict(value)
    supplied_digest = unsigned.pop("evidence_sha256")
    _hex64(supplied_digest, "EXECUTOR_INDEPENDENT_EVIDENCE_HASH_INVALID")
    require(supplied_digest == sha256_value(unsigned),
            "EXECUTOR_INDEPENDENT_EVIDENCE_HASH_MISMATCH")
    return value


def execute_candidate(request, verified_policy, ledger_path, runner,
                      postcondition_verifier=None, now_epoch=None):
    """Execute an injected runner only after independent signed-policy proof."""
    require(isinstance(verified_policy, VerifiedPolicy), "EXECUTOR_VERIFIED_POLICY_REQUIRED")
    policy = verified_policy.policy
    require(callable(runner), "EXECUTOR_INJECTED_RUNNER_REQUIRED")
    require(callable(postcondition_verifier),
            "EXECUTOR_INDEPENDENT_POSTCONDITION_VERIFIER_REQUIRED")
    required = ("tx_id", "host", "action", "paths", "units", "candidate_sha256",
                "authority_id", "one_time_nonce_sha256", "timeout_seconds",
                "independent_verifier_sha256", "expected_postconditions")
    require(isinstance(request, dict) and set(request) == set(required),
            "EXECUTOR_REQUEST_FIELDS_INVALID")
    identity = runtime_identity()
    require(identity == {"host": request["host"], "os_identity": policy["execution_identity"]},
            "EXECUTOR_FIXED_RUNTIME_IDENTITY_MISMATCH")
    current = int(time.time()) if now_epoch is None else now_epoch
    require(type(current) is int and current < policy["expires_at_epoch"],
            "EXECUTOR_AUTHORIZATION_EXPIRED")
    require(request["candidate_sha256"] == policy["candidate_sha256"],
            "EXECUTOR_VERSION_MISMATCH")
    require(request["independent_verifier_sha256"] ==
            policy["independent_verifier_sha256"],
            "EXECUTOR_INDEPENDENT_VERIFIER_VERSION_MISMATCH")
    require(request["authority_id"] == policy["one_time_authority_id"],
            "EXECUTOR_AUTHORITY_MISMATCH")
    _hex64(request["one_time_nonce_sha256"], "EXECUTOR_NONCE_INVALID")
    require(sha256_value(request) == policy["authorized_request_sha256"],
            "EXECUTOR_REQUEST_NOT_BOUND_TO_AUTHORIZATION")
    host = request["host"]
    require(host in policy["hosts"], "EXECUTOR_HOST_NOT_ALLOWLISTED")
    allowed = policy["hosts"][host]
    require(request["action"] in allowed["actions"], "EXECUTOR_ACTION_NOT_ALLOWLISTED")
    expected_postconditions = _strict_expected_postconditions(
        request["expected_postconditions"], request["action"])
    require(isinstance(request["paths"], list) and len(request["paths"]) == len(set(request["paths"])) and
            set(request["paths"]).issubset(set(allowed["paths"])),
            "EXECUTOR_PATH_NOT_ALLOWLISTED")
    for path in request["paths"]:
        _secure_allowlisted_path(path, verified_policy.expected_path_owner_uid)
    require(isinstance(request["units"], list) and len(request["units"]) == len(set(request["units"])) and
            set(request["units"]).issubset(set(allowed["units"])),
            "EXECUTOR_UNIT_NOT_ALLOWLISTED")
    require(type(request["timeout_seconds"]) is int and 0 < request["timeout_seconds"] <= 300,
            "EXECUTOR_TIMEOUT_INVALID")
    ledger = TransactionLedger(ledger_path)
    try:
        ledger.intent(request["tx_id"], request)
        try:
            raw = bounded_call(lambda: runner(request), request["timeout_seconds"])
            value = _strict_runner_result(raw, request["action"])
            if value["outcome"] != "SUCCEEDED":
                result = {"status": "UNKNOWN", "reason": "RUNNER_DID_NOT_PROVE_SUCCESS",
                          "runner_result": value, "blind_retry_allowed": False,
                          "inspection_required": True, "production_authorized": False,
                          "containment": "POSIX_PROCESS_GROUP_BEST_EFFORT_NO_CGROUP_PROOF"}
                ledger.finish(request["tx_id"], "UNKNOWN", result)
                return result
            effect_ids = set(item["effect_id"] for item in value["side_effects"])
            expected_effects = set(item["postcondition_id"]
                                   for item in expected_postconditions if item["is_effect"])
            require(effect_ids == expected_effects,
                    "EXECUTOR_RUNNER_EFFECTS_NOT_REQUEST_BOUND")
            independent = bounded_call(
                lambda: postcondition_verifier(request, value),
                request["timeout_seconds"])
            independent = _strict_independent_verification(independent, request, value)
            result = {"status": "SUCCEEDED", "result": value,
                      "independent_verification": independent,
                      "production_authorized": False,
                      "containment": "POSIX_PROCESS_GROUP_ONLY_CGROUP_NOT_INVOKED"}
            ledger.finish(request["tx_id"], "SUCCEEDED", result)
            return result
        except BaseException as error:
            result = {"status": "UNKNOWN", "reason": repr(error),
                      "blind_retry_allowed": False, "inspection_required": True,
                      "production_authorized": False,
                      "containment": "POSIX_PROCESS_GROUP_BEST_EFFORT_NO_CGROUP_PROOF"}
            ledger.finish(request["tx_id"], "UNKNOWN", result)
            return result
    finally:
        ledger.close()


def cgroup_candidate_spec(tx_id):
    """Return a future systemd-run spec; it does not prove cgroup isolation."""
    _identifier(tx_id, "EXECUTOR_TRANSACTION_ID_INVALID")
    return {"unit": "xuanjun-migration-{0}.service".format(tx_id), "properties": [
        "Type=oneshot", "DynamicUser=yes", "PrivateTmp=yes", "NoNewPrivileges=yes",
        "ProtectSystem=strict", "ProtectHome=yes", "PrivateDevices=yes",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", "KillMode=control-group",
        "TimeoutStartSec=300s"], "invoked": False, "root_capability": False,
        "containment_level": "CANDIDATE_DATA_ONLY_NOT_INVOKED",
        "actual_cgroup_boundary_proven": False}
