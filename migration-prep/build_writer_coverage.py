"""Build the public, path-redacted 95-item enforcement manifest.

Input is the private host-source map retained outside the repository.  No source
path, process command, credential name, secret, token, or customer data is copied.
"""
from __future__ import print_function

import argparse
import hashlib
import json

from gate_common import canonical_bytes


def build(private):
    records = []
    for source in private["records"]:
        unknown = any(("UNKNOWN" in str(source.get(key, "")) or
                       "NOT_OBSERVED" in str(source.get(key, "")))
                      for key in ("current_runtime_reachability",
                                  "gateway_global_openclaw_inventory",
                                  "root_yibi_githubrunner_cron_inventory",
                                  "runtime_credential_access"))
        disposition = "UNKNOWN" if unknown else (
            "FENCE_REQUIRED" if source["static_role"] in
            ("DIRECT_WRITE_CAPABLE_SOURCE", "WRITE_ORCHESTRATION_OR_HELPER") else "QUARANTINE")
        records.append({
            "path_id": source["path_id"],
            "source_path_sha256": hashlib.sha256(source["source_path"].encode("utf-8")).hexdigest(),
            "source_sha256": source["source_sha256"],
            "path_class": source["path_class"],
            "static_role": source["static_role"],
            "disposition": disposition,
            "candidate_enforcement": ("DENY" if disposition in ("UNKNOWN", "QUARANTINE")
                                      else "REQUIRE_EXTERNAL_EPOCH_FENCE"),
            "runtime_reachability": "UNKNOWN" if unknown else "BOUNDED_EVIDENCE_NO_DIRECT_ENTRY",
            "scheduler_reachability": "UNKNOWN" if unknown else "NO_DIRECT_ENTRY_OBSERVED",
            "credential_reachability": "UNKNOWN" if unknown else "NOT_OBSERVED",
            "dynamic_import_policy": "HASH_BOUND_DENY_UNLESS_FENCE_CONTEXT",
            "manual_launch_policy": "DENY_DIRECT_REQUIRE_RESTRICTED_LAUNCHER",
            "protection_policy": ("RISK_EXIT_ONLY_STILL_FENCED" if
                                  source["path_class"] == "PROTECTION" else "NOT_APPLICABLE")
        })
    value = {"schema_version": 1, "source_discovery_count": private["frozen_discovery_count"],
             "source_discovery_sha256": private["frozen_discovery_sha256"],
             "private_mapping_sha256": private["mapping_sha256"], "records": records,
             "production_authorized": False, "default_unknown_enforcement": "DENY",
             "source_paths_redacted": True}
    unsigned = dict(value)
    value["manifest_sha256"] = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("private_map")
    parser.add_argument("output")
    args = parser.parse_args()
    with open(args.private_map, "r") as stream:
        value = build(json.load(stream))
    with open(args.output, "w") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
