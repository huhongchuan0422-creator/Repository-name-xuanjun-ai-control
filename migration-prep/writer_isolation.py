"""Hash-bound 95-path writer launch/import isolation candidate."""
from __future__ import print_function

import hashlib
import os

from gate_common import require


DISPOSITIONS = frozenset(("FENCE_REQUIRED", "QUARANTINE", "UNKNOWN"))
WRITE_ACTIONS = frozenset(("CREATE_ORDER", "CANCEL_ORDER", "MODIFY_ORDER", "PROTECTIVE_CREATE",
                           "PROTECTIVE_REPLACE", "PROTECTIVE_CANCEL", "CLOSE_POSITION",
                           "REDUCE_POSITION", "EMERGENCY_CLOSE"))
RISK_EXIT_ACTIONS = frozenset(("PROTECTIVE_CREATE", "PROTECTIVE_REPLACE", "PROTECTIVE_CANCEL",
                               "CLOSE_POSITION", "REDUCE_POSITION", "EMERGENCY_CLOSE"))


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_manifest(manifest):
    require(isinstance(manifest, dict) and manifest.get("schema_version") == 1,
            "WRITER_MANIFEST_SCHEMA_INVALID")
    records = manifest.get("records")
    require(isinstance(records, list) and len(records) == 95, "WRITER_MANIFEST_95_REQUIRED")
    ids = set()
    for record in records:
        required = ("path_id", "source_path_sha256", "source_sha256", "path_class", "static_role",
                    "disposition", "candidate_enforcement", "runtime_reachability", "scheduler_reachability",
                    "credential_reachability", "dynamic_import_policy", "manual_launch_policy",
                    "protection_policy")
        require(isinstance(record, dict) and set(record) == set(required),
                "WRITER_RECORD_FIELDS_INVALID")
        require(record["path_id"] not in ids, "WRITER_PATH_ID_DUPLICATE")
        ids.add(record["path_id"])
        require(record["disposition"] in DISPOSITIONS, "WRITER_DISPOSITION_INVALID")
        expected = ("DENY" if record["disposition"] in ("UNKNOWN", "QUARANTINE")
                    else "REQUIRE_EXTERNAL_EPOCH_FENCE")
        require(record["candidate_enforcement"] == expected,
                "WRITER_CANDIDATE_ENFORCEMENT_INVALID")
        require(record["dynamic_import_policy"] == "HASH_BOUND_DENY_UNLESS_FENCE_CONTEXT",
                "WRITER_DYNAMIC_IMPORT_NOT_COVERED")
        require(record["manual_launch_policy"] == "DENY_DIRECT_REQUIRE_RESTRICTED_LAUNCHER",
                "WRITER_MANUAL_LAUNCH_NOT_COVERED")
        if record["path_class"] == "PROTECTION":
            require(record["protection_policy"] == "RISK_EXIT_ONLY_STILL_FENCED",
                    "WRITER_PROTECTION_POLICY_INVALID")
        if "UNKNOWN" in (record["runtime_reachability"], record["scheduler_reachability"],
                         record["credential_reachability"]):
            require(record["disposition"] == "UNKNOWN", "WRITER_UNKNOWN_MUST_REMAIN_UNKNOWN")
    return True


def evaluate_launch(record, actual_path, actual_sha256, action, fence_context):
    require(record["source_path_sha256"] == hashlib.sha256(
        os.path.realpath(actual_path).encode("utf-8")).hexdigest(), "WRITER_PATH_IDENTITY_MISMATCH")
    require(record["source_sha256"] == actual_sha256, "WRITER_SOURCE_HASH_MISMATCH")
    require(action in WRITE_ACTIONS, "WRITER_ACTION_INVALID")
    if record["disposition"] in ("QUARANTINE", "UNKNOWN"):
        return {"decision": "DENY", "reason": record["disposition"], "production_authorized": False}
    require(isinstance(fence_context, dict), "WRITER_FENCE_CONTEXT_REQUIRED")
    require(fence_context.get("external_epoch_valid") is True and
            fence_context.get("credential_scope_valid") is True and
            fence_context.get("scheduler_gate_valid") is True,
            "WRITER_FENCE_CONTEXT_INCOMPLETE")
    if record["path_class"] == "PROTECTION" and action not in RISK_EXIT_ACTIONS:
        return {"decision": "DENY", "reason": "PROTECTION_OPEN_FORBIDDEN", "production_authorized": False}
    return {"decision": "CONTRACT_VALID_NOT_AUTHORIZED", "reason": "RELEASE_GATE_REQUIRED",
            "production_authorized": False}


def coverage_assessment(manifest):
    validate_manifest(manifest)
    unknown = [record["path_id"] for record in manifest["records"] if record["disposition"] == "UNKNOWN"]
    return {"checked": 95, "unknown": unknown, "status": "HOLD" if unknown else "CANDIDATE_COVERED",
            "production_authorized": False,
            "remaining_integrations": ["ALL_ENTRYPOINTS_USE_RESTRICTED_LAUNCHER",
                                        "CREDENTIAL_SCOPE_DEPLOYED", "GLOBAL_TRIGGER_INVENTORY_COMPLETE"]}
