"""Build a deterministic review manifest for this candidate file set."""
from __future__ import print_function

import hashlib
import json
import os
import sys

from gate_common import canonical_bytes


FILES = (
    "readonly_reconciliation_adapter.py", "restricted_executor.py",
    "restricted-executor-allowlist.json", "writer_isolation.py",
    "writer-coverage-public.json", "build_writer_coverage.py",
    "test_implementation_batch.py", "IMPLEMENTATION_BATCH.md",
    "HUMAN_ACTIONS_REQUIRED.md", "C7_EVIDENCE_GAPS.md", "korea/get_only_policy.py",
    "korea/xuanjun-binance-shadow.service.in", "korea/requirements.lock",
    "korea/deployment-manifest.json", "korea/DEPLOYMENT.md",
    "c7_acceptance.py", "c7_private_writer_verify.py", "test_c7_acceptance.py",
    "c7-real-machine-execution-package.json", "c7-owner-scope-execution-package.json",
    "C7_PRODUCTION_ACCEPTANCE_PREP.md",
    "c7_root_inventory.py", "test_c7_root_inventory.py",
    "c7-current-evidence.json", "C7_CURRENT_EVIDENCE.md",
    "canonical-migration-policy.json", "production_dependency_inventory.py",
    "production-dependency-inventory-public.json",
    "test_production_dependency_inventory.py",
    "collect_dracut_symlink_supplement.py",
    "production-runtime-closure.json",
    "FINAL_CLOSEOUT_PACKAGE.md", "SHARED_DATABASE_CUTOVER_PLAN.md",
    "OWNER_ONE_TIME_COMPLETION.md", "PHASE_AUTHORIZATION_AND_OUTCOME_MATRIX.md",
    "test_closeout_package.py", "test_r1_r6_closeout.py",
    "test_korea_install_shell_behavior.py",
    "korea/__init__.py", "korea/build_minimal_runtime_manifest.py",
    "korea/build_runtime_candidate.py", "korea/validate_runtime_candidate.py",
    "korea/migration_shadow_entry.py", "korea/shadow-config.template.json",
    "korea/snapshot_handoff.py",
    "korea/shadow_acceptance.py", "korea/shadow-acceptance.template.json",
    "korea/install-candidate.sh", "korea/check-candidate.sh",
    "korea/uninstall-candidate.sh", "korea/minimal-runtime-manifest.json"
)


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def build(root):
    files = []
    for relative in FILES:
        path = os.path.join(root, relative)
        files.append({"path": "migration-prep/" + relative, "size": os.path.getsize(path),
                      "sha256": digest(path)})
    value = {"schema_version": 12,
             "task_id": "TOKYO_KOREA_COMPLETE_MIGRATION_REVIEW_PACKAGE_6171881293",
             "audit_comment": "6206991380",
             "host_outcome_comment": "6207782855",
             "host_security_acceptance": "HOLD_UNSUPPORTED_SECURITY_CAPABILITIES",
             "base_commit": "632bbe6f204a2c9ef778d3c91e425593c079abb1",
             "base_tree": "59a48168764e8465e62fd17a55504c29812365b3",
             "files": files, "production_authorized": False,
             "binance_called": False, "production_deployed": False,
             "self_asserted_receipts_can_pass": False,
             "root_inventory_incomplete_can_pass": False,
             "trusted_adapter_installed": False,
             "canonical_migration_policy_enforced": True,
             "legacy_package_execution_accepted": False,
             "persistent_production_launcher_proven": False,
             "shared_database_post_cutover_route_proven": False,
             "production_dependency_inventory_complete": False}
    value["candidate_content_sha256"] = hashlib.sha256(canonical_bytes(value)).hexdigest()
    return value


if __name__ == "__main__":
    root = os.path.dirname(__file__)
    output = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "candidate-manifest.json")
    with open(output, "w") as stream:
        json.dump(build(root), stream, sort_keys=True, indent=2)
        stream.write("\n")
