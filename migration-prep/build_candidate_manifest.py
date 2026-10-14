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
    "korea/deployment-manifest.json", "korea/DEPLOYMENT.md"
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
    value = {"schema_version": 2,
             "task_id": "TOKYO_KOREA_C1_C6_REMEDIATION_6169446383",
             "audit_comment": "6169446383",
             "base_commit": "1929506900e5cc9e0e1eb3d56510c4638a3d57d1",
             "base_tree": "306d609af5a414c9447c8e2494258ed817a896d9",
             "files": files, "production_authorized": False,
             "binance_called": False, "production_deployed": False}
    value["candidate_content_sha256"] = hashlib.sha256(canonical_bytes(value)).hexdigest()
    return value


if __name__ == "__main__":
    root = os.path.dirname(__file__)
    output = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "candidate-manifest.json")
    with open(output, "w") as stream:
        json.dump(build(root), stream, sort_keys=True, indent=2)
        stream.write("\n")
