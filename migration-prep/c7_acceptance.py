"""C7 authenticated evidence admission and redacted Writer-map validation.

Receipt dictionaries are never authority. A gate can become ready only when
an independently signed admission policy names the gate authority and adapter,
the authority signs the canonical receipt, and the adapter verifies the exact
raw evidence bytes. This candidate still never authorizes production.
"""
from __future__ import print_function

import hashlib
import json
import os
import re
import stat

from gate_common import GateError, canonical_bytes, require, sha256_value
from restricted_executor import _secure_file, verify_ed25519


HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX128 = re.compile(r"^[0-9a-f]{128}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:@-]{1,160}$")
PATH_IDS = tuple("WP{0:03d}".format(index) for index in range(1, 96))
GATES = ("WRITER_MAP", "RUNNER_ADMIN", "ROOT_INVENTORY", "GLOBAL_TRIGGERS",
         "TRUST_ANCHOR", "RESULT_VERIFIER", "KOREA_ISOLATION")
SOURCE_CLASSES = frozenset((
    "PRIVATE_RAW_BYTES", "GITHUB_ADMIN_API", "ROOT_READONLY_HELPER",
    "OPENCLAW_ADMIN_API", "INDEPENDENT_AUTHORITY_RECORD",
    "INDEPENDENT_VERIFIER_READBACK", "KOREA_ROOT_READBACK"))
STATUSES = frozenset(("PASS", "PARTIAL", "BLOCKED_PERMISSION", "HOLD"))
_VERIFIED_POLICY_SENTINEL = object()
_TRUSTED_ADAPTER_SENTINEL = object()


def _hex64(value, code):
    require(isinstance(value, str) and HEX64.match(value) is not None, code)


def _identifier(value, code):
    require(isinstance(value, str) and IDENTIFIER.match(value) is not None, code)


def validate_private_writer_map(raw_bytes, public_manifest):
    """Validate raw private evidence while returning no source paths."""
    require(isinstance(raw_bytes, bytes), "C7_PRIVATE_MAP_BYTES_REQUIRED")
    try:
        private = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GateError("C7_PRIVATE_MAP_JSON_INVALID")
    records = private.get("records") if isinstance(private, dict) else None
    require(isinstance(records, list) and len(records) == 95,
            "C7_PRIVATE_MAP_RECORD_COUNT_INVALID")
    identifiers = [item.get("path_id") for item in records if isinstance(item, dict)]
    require(tuple(identifiers) == PATH_IDS, "C7_PRIVATE_MAP_IDS_INVALID")
    supplied = private.get("mapping_sha256")
    unsigned = dict(private); unsigned.pop("mapping_sha256", None)
    _hex64(supplied, "C7_PRIVATE_MAP_MAPPING_DIGEST_INVALID")
    require(supplied == sha256_value(unsigned), "C7_PRIVATE_MAP_MAPPING_DIGEST_MISMATCH")
    require(isinstance(public_manifest, dict) and
            public_manifest.get("source_discovery_count") == 95,
            "C7_PUBLIC_MANIFEST_RECORD_COUNT_INVALID")
    public_records = public_manifest.get("records")
    require(isinstance(public_records, list) and
            tuple(item.get("path_id") for item in public_records) == PATH_IDS,
            "C7_PUBLIC_MANIFEST_IDS_INVALID")
    public_by_id = {item["path_id"]: item for item in public_records}
    for item in records:
        public = public_by_id[item["path_id"]]
        require(public.get("source_sha256") == item.get("source_sha256") and
                public.get("path_class") == item.get("path_class") and
                public.get("source_path_sha256") == hashlib.sha256(
                    item.get("source_path", "").encode("utf-8")).hexdigest() and
                public.get("static_role") == item.get("static_role"),
                "C7_PRIVATE_PUBLIC_RECORD_MISMATCH")
        require(public.get("candidate_enforcement") == "DENY" and
                public.get("runtime_reachability") == "UNKNOWN" and
                public.get("scheduler_reachability") == "UNKNOWN" and
                public.get("dynamic_import_policy") ==
                "HASH_BOUND_DENY_UNLESS_FENCE_CONTEXT" and
                public.get("manual_launch_policy") ==
                "DENY_DIRECT_REQUIRE_RESTRICTED_LAUNCHER" and
                public.get("credential_reachability") == "UNKNOWN" and
                public.get("disposition") == "UNKNOWN",
                "C7_PUBLIC_WRITER_FOUR_SURFACES_MUST_FAIL_CLOSED")
    return {"status": "PASS_PRIVATE_MAP_BYTES_AND_PUBLIC_IDS",
            "record_count": 95,
            "private_file_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "private_mapping_sha256": supplied,
            "raw_paths_disclosed": False, "production_mutation": False,
            "runtime_coverage_proven": False,
            "scheduler_coverage": "UNKNOWN",
            "dynamic_import_policy": "DENY_UNLESS_HASH_BOUND_FENCE_CONTEXT",
            "manual_execution_policy": "DENY_DIRECT_REQUIRE_RESTRICTED_LAUNCHER",
            "credential_coverage": "UNKNOWN"}


def _stable_file_bytes(path):
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), "C7_EVIDENCE_FILE_NOT_REGULAR")
        chunks = []
        while True:
            value = os.read(descriptor, 1024 * 1024)
            if not value:
                break
            chunks.append(value)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    path_after = os.lstat(path)
    identity_fields = lambda value: (
        value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode),
        stat.S_IMODE(value.st_mode), value.st_uid, value.st_gid, value.st_size,
        getattr(value, "st_mtime_ns", int(value.st_mtime * 1000000000)))
    require(identity_fields(before) == identity_fields(after) and
            before.st_dev == path_after.st_dev and before.st_ino == path_after.st_ino and
            stat.S_ISREG(path_after.st_mode), "C7_EVIDENCE_FILE_CHANGED_DURING_READ")
    return b"".join(chunks), sha256_value(identity_fields(after))


def load_private_writer_evidence(private_path, public_path, expected_owner_uid):
    """Read owner-controlled original bytes and return only the redacted receipt."""
    private_path = _secure_file(private_path, expected_owner_uid,
                                "C7_PRIVATE_WRITER_FILE")
    public_path = _secure_file(public_path, expected_owner_uid,
                               "C7_PUBLIC_WRITER_FILE")
    raw, private_identity = _stable_file_bytes(private_path)
    public_raw, unused_public_identity = _stable_file_bytes(public_path)
    try:
        public = json.loads(public_raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GateError("C7_PUBLIC_WRITER_JSON_INVALID")
    result = validate_private_writer_map(raw, public)
    result.update({"private_file_identity_sha256": private_identity,
        "public_file_sha256": hashlib.sha256(public_raw).hexdigest()})
    return result


class VerifiedAdmissionPolicy(object):
    def __init__(self, policy, anchor, sentinel):
        require(sentinel is _VERIFIED_POLICY_SENTINEL,
                "C7_VERIFIED_POLICY_CONSTRUCTION_FORBIDDEN")
        self.policy = policy
        self.anchor = anchor


class TrustedEvidenceAdapter(object):
    def __init__(self, adapter_id, gate, verifier, sentinel):
        require(sentinel is _TRUSTED_ADAPTER_SENTINEL,
                "C7_TRUSTED_ADAPTER_CONSTRUCTION_FORBIDDEN")
        self.adapter_id = adapter_id
        self.gate = gate
        self.verifier = verifier

    def verify(self, receipt, raw_evidence):
        return self.verifier(receipt, raw_evidence)


def trusted_evidence_adapter(adapter_id, gate, verifier):
    """Bind a code-owned verifier to the exact adapter identity in policy."""
    _identifier(adapter_id, "C7_ADAPTER_ID_INVALID")
    require(gate in GATES and callable(verifier), "C7_ADAPTER_INVALID")
    return TrustedEvidenceAdapter(adapter_id, gate, verifier,
                                  _TRUSTED_ADAPTER_SENTINEL)


def verify_result_verifier_evidence(receipt, raw_evidence):
    """Validate redacted measurement of the actual loaded result verifier."""
    require(isinstance(raw_evidence, bytes), "C7_VERIFIER_EVIDENCE_BYTES_REQUIRED")
    try:
        value = json.loads(raw_evidence.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GateError("C7_VERIFIER_EVIDENCE_JSON_INVALID")
    require(raw_evidence == canonical_bytes(value),
            "C7_VERIFIER_EVIDENCE_NOT_CANONICAL")
    fields = set(("schema_version", "action", "host", "exact_commit", "exact_tree",
                  "epoch_id", "verifier_path_sha256", "verifier_file_sha256",
                  "verifier_owner_uid", "verifier_mode", "verifier_parent_chain_sha256",
                  "service_unit", "service_main_pid", "service_execution_identity",
                  "loaded_command_sha256", "loaded_verifier_file_sha256",
                  "post_state_source_kind", "post_state_source_sha256",
                  "post_state_authority_id", "observed_at_epoch", "complete",
                  "production_mutation"))
    require(isinstance(value, dict) and set(value) == fields,
            "C7_VERIFIER_EVIDENCE_FIELDS_INVALID")
    require(value["schema_version"] == 1 and value["complete"] is True and
            value["production_mutation"] is False,
            "C7_VERIFIER_EVIDENCE_NOT_COMPLETE")
    require(value["host"] in receipt["hosts"] and
            value["exact_commit"] == receipt["exact_commit"] and
            value["exact_tree"] == receipt["exact_tree"] and
            value["epoch_id"] == receipt["epoch_id"] and
            value["observed_at_epoch"] == receipt["observed_at_epoch"],
            "C7_VERIFIER_EVIDENCE_RECEIPT_MISMATCH")
    for name in ("verifier_path_sha256", "verifier_file_sha256",
                 "verifier_parent_chain_sha256", "loaded_command_sha256",
                 "loaded_verifier_file_sha256", "post_state_source_sha256"):
        _hex64(value[name], "C7_VERIFIER_EVIDENCE_HASH_INVALID")
    require(value["loaded_verifier_file_sha256"] == value["verifier_file_sha256"],
            "C7_VERIFIER_LOADED_FILE_HASH_MISMATCH")
    require(type(value["verifier_owner_uid"]) is int and
            value["verifier_owner_uid"] == 0 and
            type(value["verifier_mode"]) is int and
            value["verifier_mode"] & 0o022 == 0,
            "C7_VERIFIER_FILE_AUTHORITY_INVALID")
    require(type(value["service_main_pid"]) is int and value["service_main_pid"] > 0 and
            all(isinstance(value[name], str) and value[name] for name in (
                "action", "service_unit", "service_execution_identity",
                "post_state_source_kind", "post_state_authority_id")),
            "C7_VERIFIER_LIVE_BINDING_INVALID")
    subject = {name: value[name] for name in (
        "action", "host", "service_unit", "service_execution_identity",
        "verifier_path_sha256", "post_state_source_kind", "post_state_authority_id")}
    require(sha256_value(subject) == receipt["exact_subject_sha256"],
            "C7_VERIFIER_SUBJECT_MISMATCH")
    return True


def validate_admission_policy(policy):
    required = ("schema_version", "policy_id", "candidate_sha256",
                "exact_commit", "exact_tree", "epoch_id", "expires_at_epoch",
                "trust_anchor_sha256", "authorities")
    require(isinstance(policy, dict) and set(policy) == set(required),
            "C7_POLICY_FIELDS_INVALID")
    require(type(policy["schema_version"]) is int and policy["schema_version"] == 1,
            "C7_POLICY_SCHEMA_INVALID")
    _identifier(policy["policy_id"], "C7_POLICY_ID_INVALID")
    _identifier(policy["epoch_id"], "C7_POLICY_EPOCH_INVALID")
    _hex64(policy["candidate_sha256"], "C7_POLICY_CANDIDATE_INVALID")
    require(isinstance(policy["exact_commit"], str) and
            HEX40.match(policy["exact_commit"]) is not None and
            isinstance(policy["exact_tree"], str) and
            HEX40.match(policy["exact_tree"]) is not None,
            "C7_POLICY_GIT_VERSION_INVALID")
    _hex64(policy["trust_anchor_sha256"], "C7_POLICY_ANCHOR_HASH_INVALID")
    require(type(policy["expires_at_epoch"]) is int,
            "C7_POLICY_EXPIRY_INVALID")
    authorities = policy["authorities"]
    require(isinstance(authorities, dict) and set(authorities) == set(GATES),
            "C7_POLICY_GATE_SET_INVALID")
    authority_fields = set(("authority_id", "public_key_hex", "source_class",
                            "authority_scope", "adapter_id",
                            "exact_subject_sha256", "transaction_id", "hosts", "coverage",
                            "max_age_seconds"))
    for gate in GATES:
        value = authorities[gate]
        require(isinstance(value, dict) and set(value) == authority_fields,
                "C7_POLICY_AUTHORITY_FIELDS_INVALID")
        _identifier(value["authority_id"], "C7_POLICY_AUTHORITY_ID_INVALID")
        _identifier(value["adapter_id"], "C7_POLICY_ADAPTER_ID_INVALID")
        _identifier(value["transaction_id"], "C7_POLICY_TRANSACTION_ID_INVALID")
        _hex64(value["public_key_hex"], "C7_POLICY_AUTHORITY_KEY_INVALID")
        _hex64(value["exact_subject_sha256"], "C7_POLICY_SUBJECT_INVALID")
        require(value["source_class"] in SOURCE_CLASSES and
                value["authority_scope"] in ("ADMIN", "ROOT", "INDEPENDENT"),
                "C7_POLICY_AUTHORITY_ENUM_INVALID")
        require(isinstance(value["hosts"], list) and value["hosts"] and
                len(value["hosts"]) == len(set(value["hosts"])) and
                all(isinstance(item, str) and item for item in value["hosts"]),
                "C7_POLICY_HOSTS_INVALID")
        require(isinstance(value["coverage"], list) and value["coverage"] and
                len(value["coverage"]) == len(set(value["coverage"])) and
                all(isinstance(item, str) and item for item in value["coverage"]),
                "C7_POLICY_COVERAGE_INVALID")
        require(type(value["max_age_seconds"]) is int and
                0 < value["max_age_seconds"] <= 86400,
                "C7_POLICY_MAX_AGE_INVALID")
    return True


def load_verified_admission_policy(policy_path, signature_path, trust_anchor_path,
                                   expected_owner_uid):
    """Load canonical root/owner-controlled policy and verify Ed25519 authority."""
    require(type(expected_owner_uid) is int and expected_owner_uid >= 0,
            "C7_POLICY_OWNER_UID_INVALID")
    policy_path = _secure_file(policy_path, expected_owner_uid, "C7_POLICY_FILE")
    signature_path = _secure_file(signature_path, expected_owner_uid, "C7_POLICY_SIGNATURE")
    trust_anchor_path = _secure_file(trust_anchor_path, expected_owner_uid,
                                     "C7_POLICY_TRUST_ANCHOR")
    policy_bytes, unused_policy_identity = _stable_file_bytes(policy_path)
    signature_bytes, unused_signature_identity = _stable_file_bytes(signature_path)
    anchor_bytes, unused_anchor_identity = _stable_file_bytes(trust_anchor_path)
    try:
        signature_hex = signature_bytes.decode("ascii").strip()
        anchor = json.loads(anchor_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GateError("C7_POLICY_AUTHORITY_FILES_INVALID")
    require(isinstance(anchor, dict) and set(anchor) == set((
        "schema_version", "algorithm", "authority_id", "public_key_hex")),
        "C7_POLICY_ANCHOR_FIELDS_INVALID")
    require(anchor["schema_version"] == 1 and anchor["algorithm"] == "Ed25519",
            "C7_POLICY_ANCHOR_SCHEMA_INVALID")
    _identifier(anchor["authority_id"], "C7_POLICY_ANCHOR_AUTHORITY_INVALID")
    _hex64(anchor["public_key_hex"], "C7_POLICY_ANCHOR_KEY_INVALID")
    require(anchor_bytes == canonical_bytes(anchor), "C7_POLICY_ANCHOR_NOT_CANONICAL")
    require(isinstance(signature_hex, str) and HEX128.match(signature_hex) is not None,
            "C7_POLICY_SIGNATURE_INVALID")
    try:
        policy = json.loads(policy_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GateError("C7_POLICY_JSON_INVALID")
    require(policy_bytes == canonical_bytes(policy), "C7_POLICY_NOT_CANONICAL")
    validate_admission_policy(policy)
    require(policy["trust_anchor_sha256"] == sha256_value(anchor),
            "C7_POLICY_ANCHOR_NOT_HASH_BOUND")
    verify_ed25519(bytes.fromhex(anchor["public_key_hex"]), policy_bytes,
                   bytes.fromhex(signature_hex))
    return VerifiedAdmissionPolicy(policy, anchor, _VERIFIED_POLICY_SENTINEL)


def validate_receipt(receipt):
    required = ("schema_version", "receipt_id", "gate", "source_class",
                "authority_id", "authority_scope", "adapter_id",
                "transaction_id", "observed_at_epoch", "expires_at_epoch", "candidate_sha256",
                "exact_commit", "exact_tree", "epoch_id", "exact_subject_sha256",
                "evidence_sha256", "status", "production_mutation", "hosts",
                "coverage", "limitations")
    require(isinstance(receipt, dict) and set(receipt) == set(required),
            "C7_RECEIPT_FIELDS_INVALID")
    require(type(receipt["schema_version"]) is int and receipt["schema_version"] == 2,
            "C7_RECEIPT_SCHEMA_INVALID")
    require(receipt["gate"] in GATES and receipt["source_class"] in SOURCE_CLASSES and
            receipt["status"] in STATUSES, "C7_RECEIPT_ENUM_INVALID")
    require(receipt["authority_scope"] in ("CALLER", "ADMIN", "ROOT", "INDEPENDENT"),
            "C7_RECEIPT_AUTHORITY_SCOPE_INVALID")
    require(type(receipt["production_mutation"]) is bool and
            receipt["production_mutation"] is False,
            "C7_READONLY_RECEIPT_MUTATION_FORBIDDEN")
    for name in ("receipt_id", "authority_id", "adapter_id", "transaction_id", "epoch_id"):
        _identifier(receipt[name], "C7_RECEIPT_IDENTIFIER_INVALID")
    require(type(receipt["observed_at_epoch"]) is int and
            type(receipt["expires_at_epoch"]) is int,
            "C7_RECEIPT_TIME_INVALID")
    for name in ("candidate_sha256", "exact_subject_sha256", "evidence_sha256"):
        _hex64(receipt[name], "C7_RECEIPT_HASH_INVALID")
    require(isinstance(receipt["exact_commit"], str) and
            HEX40.match(receipt["exact_commit"]) is not None and
            isinstance(receipt["exact_tree"], str) and
            HEX40.match(receipt["exact_tree"]) is not None,
            "C7_RECEIPT_GIT_VERSION_INVALID")
    for name in ("hosts", "coverage", "limitations"):
        require(isinstance(receipt[name], list) and
                len(receipt[name]) == len(set(receipt[name])) and
                all(isinstance(item, str) and item for item in receipt[name]),
                "C7_RECEIPT_LIST_INVALID")
    require(receipt["hosts"] and receipt["coverage"],
            "C7_RECEIPT_COVERAGE_REQUIRED")
    return receipt


def _verify_bundle(bundle, verified_policy, adapters, now_epoch):
    require(isinstance(bundle, dict) and set(bundle) == set((
        "receipt", "raw_evidence", "authority_signature_hex")),
        "C7_RECEIPT_BUNDLE_FIELDS_INVALID")
    receipt = validate_receipt(bundle["receipt"])
    raw_evidence = bundle["raw_evidence"]
    signature_hex = bundle["authority_signature_hex"]
    require(isinstance(raw_evidence, bytes), "C7_RAW_EVIDENCE_BYTES_REQUIRED")
    require(isinstance(signature_hex, str) and HEX128.match(signature_hex) is not None,
            "C7_RECEIPT_SIGNATURE_INVALID")
    policy = verified_policy.policy
    authority = policy["authorities"][receipt["gate"]]
    require(policy["expires_at_epoch"] >= now_epoch, "C7_POLICY_EXPIRED")
    require(receipt["candidate_sha256"] == policy["candidate_sha256"] and
            receipt["exact_commit"] == policy["exact_commit"] and
            receipt["exact_tree"] == policy["exact_tree"],
            "C7_RECEIPT_CANDIDATE_VERSION_MISMATCH")
    require(receipt["epoch_id"] == policy["epoch_id"],
            "C7_RECEIPT_EPOCH_MISMATCH")
    require(receipt["authority_id"] == authority["authority_id"] and
            receipt["source_class"] == authority["source_class"] and
            receipt["authority_scope"] == authority["authority_scope"] and
            receipt["adapter_id"] == authority["adapter_id"] and
            receipt["transaction_id"] == authority["transaction_id"],
            "C7_RECEIPT_AUTHORITY_MISMATCH")
    require(receipt["exact_subject_sha256"] == authority["exact_subject_sha256"],
            "C7_RECEIPT_SUBJECT_MISMATCH")
    require(receipt["hosts"] == authority["hosts"] and
            receipt["coverage"] == authority["coverage"],
            "C7_RECEIPT_COVERAGE_MISMATCH")
    require(receipt["observed_at_epoch"] <= now_epoch <= receipt["expires_at_epoch"] and
            now_epoch - receipt["observed_at_epoch"] <= authority["max_age_seconds"],
            "C7_RECEIPT_NOT_FRESH")
    evidence_digest = hashlib.sha256(raw_evidence).hexdigest()
    require(receipt["evidence_sha256"] == evidence_digest,
            "C7_RECEIPT_ORIGINAL_EVIDENCE_HASH_MISMATCH")
    verify_ed25519(bytes.fromhex(authority["public_key_hex"]),
                   canonical_bytes(receipt), bytes.fromhex(signature_hex))
    adapter = adapters.get(receipt["gate"])
    require(isinstance(adapter, TrustedEvidenceAdapter) and
            adapter.gate == receipt["gate"] and
            adapter.adapter_id == authority["adapter_id"],
            "C7_TRUSTED_ADAPTER_MISSING_OR_MISMATCH")
    require(adapter.verify(receipt, raw_evidence) is True,
            "C7_ORIGINAL_EVIDENCE_ADAPTER_REJECTED")
    return receipt


def admission_matrix(receipt_bundles, verified_policy=None, adapters=None,
                     now_epoch=None):
    """Return HOLD for shapes; only authenticated exact evidence may be ready."""
    require(isinstance(receipt_bundles, list), "C7_RECEIPTS_LIST_REQUIRED")
    if not isinstance(verified_policy, VerifiedAdmissionPolicy):
        for value in receipt_bundles:
            receipt = value.get("receipt", value) if isinstance(value, dict) else value
            validate_receipt(receipt)
        return {"schema_version": 2, "admission_class": "FORMAL_RECEIPT_SHAPE_ONLY",
                "gates": {gate: "HOLD" for gate in GATES},
                "production_acceptance_ready": False,
                "production_execution_authorized": False,
                "invalid_receipt_count": 0, "contradiction_count": 0,
                "missing_gates": list(GATES)}
    require(type(now_epoch) is int and isinstance(adapters, dict),
            "C7_AUTHENTICATED_ADMISSION_CONTEXT_REQUIRED")
    grouped = {gate: [] for gate in GATES}
    invalid = {gate: 0 for gate in GATES}
    receipt_id_gates = {}
    for bundle in receipt_bundles:
        gate = None
        if isinstance(bundle, dict) and isinstance(bundle.get("receipt"), dict):
            gate = bundle["receipt"].get("gate")
        if gate not in GATES:
            raise GateError("C7_RECEIPT_GATE_INVALID")
        try:
            verified = _verify_bundle(bundle, verified_policy, adapters, now_epoch)
            grouped[gate].append(verified)
            receipt_id_gates.setdefault(verified["receipt_id"], []).append(gate)
        except (GateError, ValueError, TypeError):
            invalid[gate] += 1
    matrix = {}
    contradictions = 0
    duplicate_id_gates = set()
    for gates in receipt_id_gates.values():
        if len(set(gates)) > 1:
            duplicate_id_gates.update(gates)
            contradictions += 1
    for gate in GATES:
        receipts = grouped[gate]
        if len(receipts) != 1 or invalid[gate] or gate in duplicate_id_gates:
            if len(receipts) + invalid[gate] > 1:
                contradictions += 1
            matrix[gate] = "HOLD"
            continue
        receipt = receipts[0]
        matrix[gate] = ("PASS" if receipt["status"] == "PASS" and
                        not receipt["limitations"] else "HOLD")
    production_ready = all(value == "PASS" for value in matrix.values())
    return {"schema_version": 2,
            "admission_class": "AUTHENTICATED_ORIGINAL_EVIDENCE_CANDIDATE",
            "gates": matrix, "production_acceptance_ready": production_ready,
            "production_execution_authorized": False,
            "invalid_receipt_count": sum(invalid.values()),
            "contradiction_count": contradictions,
            "missing_gates": sorted(key for key, value in matrix.items()
                                    if value != "PASS")}
