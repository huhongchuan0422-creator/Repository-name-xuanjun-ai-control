"""C7 evidence admission and redacted Writer-map validation.

This module never discovers secrets, executes a Writer, changes a service, or
turns partial evidence into production authority.  It accepts only explicit
receipts from the authoritative control plane for each gate.
"""
from __future__ import print_function

import hashlib
import json
import re

from gate_common import GateError, canonical_bytes, require, sha256_value


HEX64 = re.compile(r"^[0-9a-f]{64}$")
PATH_IDS = tuple("WP{0:03d}".format(index) for index in range(1, 96))
GATES = ("WRITER_MAP", "RUNNER_ADMIN", "ROOT_INVENTORY", "GLOBAL_TRIGGERS",
         "TRUST_ANCHOR", "KOREA_ISOLATION")
SOURCE_CLASSES = frozenset((
    "PRIVATE_RAW_BYTES", "GITHUB_ADMIN_API", "ROOT_READONLY_HELPER",
    "OPENCLAW_ADMIN_API", "INDEPENDENT_AUTHORITY_RECORD",
    "KOREA_ROOT_READBACK"))
STATUSES = frozenset(("PASS", "PARTIAL", "BLOCKED_PERMISSION", "HOLD"))


def _hex64(value, code):
    require(isinstance(value, str) and HEX64.match(value) is not None, code)


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
                public.get("path_class") == item.get("path_class"),
                "C7_PRIVATE_PUBLIC_RECORD_MISMATCH")
        require(public.get("candidate_enforcement") == "DENY",
                "C7_PUBLIC_WRITER_MUST_DEFAULT_DENY")
    return {"status": "PASS_PRIVATE_MAP_BYTES_AND_PUBLIC_IDS",
            "record_count": 95,
            "private_file_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "private_mapping_sha256": supplied,
            "raw_paths_disclosed": False, "production_mutation": False,
            "runtime_coverage_proven": False}


def validate_receipt(receipt):
    required = ("schema_version", "receipt_id", "gate", "source_class", "scope",
                "observed_at_utc", "exact_subject_sha256", "evidence_sha256",
                "status", "production_mutation", "authority_scope", "limitations")
    require(isinstance(receipt, dict) and set(receipt) == set(required),
            "C7_RECEIPT_FIELDS_INVALID")
    require(type(receipt["schema_version"]) is int and receipt["schema_version"] == 1,
            "C7_RECEIPT_SCHEMA_INVALID")
    require(receipt["gate"] in GATES and receipt["source_class"] in SOURCE_CLASSES and
            receipt["status"] in STATUSES, "C7_RECEIPT_ENUM_INVALID")
    require(receipt["authority_scope"] in ("CALLER", "ADMIN", "ROOT", "INDEPENDENT"),
            "C7_RECEIPT_AUTHORITY_SCOPE_INVALID")
    require(type(receipt["production_mutation"]) is bool and
            receipt["production_mutation"] is False,
            "C7_READONLY_RECEIPT_MUTATION_FORBIDDEN")
    require(isinstance(receipt["receipt_id"], str) and receipt["receipt_id"] and
            isinstance(receipt["scope"], str) and receipt["scope"] and
            isinstance(receipt["observed_at_utc"], str) and receipt["observed_at_utc"] and
            isinstance(receipt["limitations"], list) and
            all(isinstance(item, str) and item for item in receipt["limitations"]),
            "C7_RECEIPT_TEXT_INVALID")
    _hex64(receipt["exact_subject_sha256"], "C7_RECEIPT_SUBJECT_HASH_INVALID")
    _hex64(receipt["evidence_sha256"], "C7_RECEIPT_EVIDENCE_HASH_INVALID")
    return receipt


def admission_matrix(receipts):
    require(isinstance(receipts, list), "C7_RECEIPTS_LIST_REQUIRED")
    grouped = {gate: [] for gate in GATES}
    for receipt in receipts:
        receipt = validate_receipt(receipt)
        grouped[receipt["gate"]].append(receipt)
    required_authority = {
        "WRITER_MAP": ("PRIVATE_RAW_BYTES", "INDEPENDENT"),
        "RUNNER_ADMIN": ("GITHUB_ADMIN_API", "ADMIN"),
        "ROOT_INVENTORY": ("ROOT_READONLY_HELPER", "ROOT"),
        "GLOBAL_TRIGGERS": ("OPENCLAW_ADMIN_API", "ADMIN"),
        "TRUST_ANCHOR": ("INDEPENDENT_AUTHORITY_RECORD", "INDEPENDENT"),
        "KOREA_ISOLATION": ("KOREA_ROOT_READBACK", "ROOT")}
    matrix = {}
    for gate in GATES:
        source, authority = required_authority[gate]
        accepted = [item for item in grouped[gate]
                    if item["status"] == "PASS" and item["source_class"] == source and
                    item["authority_scope"] == authority and not item["limitations"]]
        matrix[gate] = "PASS" if accepted else "HOLD"
    production_ready = all(value == "PASS" for value in matrix.values())
    return {"schema_version": 1, "gates": matrix,
            "production_acceptance_ready": production_ready,
            "production_execution_authorized": False,
            "missing_gates": sorted(key for key, value in matrix.items() if value != "PASS")}
