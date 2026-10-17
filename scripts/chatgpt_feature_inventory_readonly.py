"""Deterministic read-only feature inventory for the existing governance registry.

No progress claims based on path presence alone. No new task queue or writer.
CI and independent-review evidence must be supplied by the canonical sources.
"""
import hashlib
import json
from pathlib import Path

class RegistryHold(ValueError):
    pass

def inventory(root):
    root=Path(root)
    raw=(root/"governance/features.json").read_bytes()
    doc=json.loads(raw.decode("utf-8"))
    items=doc.get("features")
    if not isinstance(items,list):
        raise RegistryHold("FEATURES_MISSING")
    seen=set();rows=[]
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get("feature_id"),str):
            raise RegistryHold("INVALID_FEATURE")
        fid=item["feature_id"]
        if fid in seen:
            raise RegistryHold("DUPLICATE_FEATURE")
        seen.add(fid)
        paths=item.get("paths",[])
        if not isinstance(paths,list) or not all(isinstance(x,str) for x in paths):
            raise RegistryHold("INVALID_PATHS")
        invalid=[p for p in paths if p.startswith("/") or ".." in p.split("/") or "\\" in p or not p]
        if invalid:
            raise RegistryHold("UNSAFE_PATH")
        # A source path being present proves nothing about build, review or release.
        concrete=[p for p in paths if "*" not in p]
        missing=[p for p in concrete if not (root/p).is_file()]
        tests=item.get("acceptance",{}).get("tests",[])
        if not isinstance(tests,list):
            raise RegistryHold("INVALID_TESTS")
        rows.append({
            "feature_id":fid,
            "registered_status":item.get("status","UNKNOWN"),
            "tracked_paths":len(paths),
            "missing_tracked_paths":sorted(missing),
            "test_paths":len(tests),
            "ci_status":"UNKNOWN",
            "independent_review":"UNKNOWN",
            "production_acceptance":"UNKNOWN",
            "next_action":"CHECK_CANONICAL_OWNER_AND_EVIDENCE"
        })
    rows.sort(key=lambda r:r["feature_id"])
    return {"schema":1,"registry_sha256":hashlib.sha256(raw).hexdigest(),
            "feature_count":len(rows),"features":rows,
            "note":"Read-only inventory; not a canonical ledger or completion receipt."}
