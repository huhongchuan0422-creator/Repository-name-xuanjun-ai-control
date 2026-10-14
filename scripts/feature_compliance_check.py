"""Deterministic three-link feature governance validation. No network, no AI or secrets."""
import argparse
import json
import re
import sys
import fnmatch
from pathlib import Path

ID = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")
STATES = {"PLANNED", "IN_DEVELOPMENT", "CANDIDATE", "VERIFIED", "DEPLOYED"}
REQUIRED = ("feature_id", "design", "development", "acceptance", "reuse", "status")
CODE_ROOTS = ("scripts/", "tests/", "apps/", "src/", "services/")
CODE_SUFFIXES = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java")
BOOTSTRAP_EXEMPT = frozenset(("scripts/feature_compliance_check.py", "tests/test_feature_compliance_check.py"))
def validate(root, manifest):
    errors = []
    registry = json.loads((root / manifest).read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("schema_version") != 1 or not isinstance(registry.get("features"), list) or not registry["features"]:
        return ["INVALID_FEATURE_REGISTRY"]
    seen = set()
    coverage = []
    for number, feature in enumerate(registry["features"], 1):
        tag = "feature[" + str(number) + "]"
        if not isinstance(feature, dict):
            errors.append(tag + ": INVALID_ENTRY"); continue
        for field in REQUIRED:
            if field not in feature: errors.append(tag + ": MISSING_" + field.upper())
        fid = feature.get("feature_id")
        if not isinstance(fid, str) or not ID.fullmatch(fid):
            errors.append(tag + ": INVALID_FEATURE_ID"); continue
        if fid in seen: errors.append(fid + ": DUPLICATE_ID")
        seen.add(fid)
        if feature.get("status") not in STATES: errors.append(fid + ": INVALID_STATUS")
        design = feature.get("design")
        dev = feature.get("development")
        acceptance = feature.get("acceptance")
        if not isinstance(design, dict) or not isinstance(dev, dict) or not isinstance(acceptance, dict):
            errors.append(fid + ": INVALID_THREE_LINK_STRUCTURE"); continue
        doc = design.get("document")
        section = design.get("section")
        if not isinstance(doc, str) or not doc.startswith("docs/") or not isinstance(section, str) or not section.strip():
            errors.append(fid + ": INVALID_DESIGN"); continue
        docpath = (root / doc).resolve()
        if not docpath.is_relative_to(root.resolve()) or not docpath.is_file():
            errors.append(fid + ": DESIGN_DOCUMENT_NOT_FOUND")
        elif not re.search(r"^#{1,6}\s+" + re.escape(section) + r"(?:\s|$)", docpath.read_text(encoding="utf-8"), re.MULTILINE):
            errors.append(fid + ": DESIGN_SECTION_NOT_FOUND")
        orderdoc, ordersection = dev.get("document"), dev.get("section")
        if not isinstance(orderdoc, str) or not orderdoc.startswith("docs/") or not isinstance(ordersection, str):
            errors.append(fid + ": INVALID_DEVELOPMENT_MAPPING")
        else:
            path = (root / orderdoc).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                errors.append(fid + ": DEVELOPMENT_DOCUMENT_NOT_FOUND")
            elif not re.search(r"^#{1,6}\s+" + re.escape(ordersection) + r"(?:\s|$)", path.read_text(encoding="utf-8"), re.MULTILINE):
                errors.append(fid + ": DEVELOPMENT_SECTION_NOT_FOUND")
        phase = dev.get("phase")
        if type(phase) is not int or not 0 <= phase <= 8:
            errors.append(fid + ": INVALID_PHASE")
        criteria = acceptance.get("criteria")
        if not isinstance(criteria, list) or not criteria or any(not isinstance(x, str) or not x.strip() for x in criteria):
            errors.append(fid + ": MISSING_ACCEPTANCE_CRITERIA")
        tests = acceptance.get("tests")
        if not isinstance(tests, list) or not tests or any(not isinstance(x, str) or not x.startswith("tests/") for x in tests):
            errors.append(fid + ": MISSING_TEST_REFERENCES")
        elif any(not (root / p).is_file() for p in tests):
            errors.append(fid + ": ACCEPTANCE_TEST_NOT_FOUND")
        owned = feature.get("paths", [])
        if not isinstance(owned, list) or any(not isinstance(p, str) or not p or p.startswith("/") or ".." in p.split("/") for p in owned):
            errors.append(fid + ": INVALID_OWNED_PATHS")
        else:
            coverage.extend(owned)
        reuse = feature.get("reuse")
        if not isinstance(reuse, list) or not reuse or any(not isinstance(x, str) or not x.strip() for x in reuse):
            errors.append(fid + ": MISSING_REUSE_EVIDENCE")
        if feature.get("status") in ("VERIFIED", "DEPLOYED") and not acceptance.get("evidence"):
            errors.append(fid + ": VERIFIED_WITHOUT_EVIDENCE")
        if feature.get("status") == "DEPLOYED" and not feature.get("deployment_receipt"):
            errors.append(fid + ": DEPLOYED_WITHOUT_RECEIPT")
    return errors

def check_changed_paths(root, manifest, changed):
    """Fail closed for added code without an explicitly registered feature path.

    Existing modified legacy code is deliberately phased in separately; this
    gate protects NEW executable files, not code edits hidden in old files.
    """
    registry=json.loads((root / manifest).read_text(encoding="utf-8"))
    patterns=[p for f in registry.get("features",[]) if isinstance(f,dict) for p in f.get("paths",[]) if isinstance(p,str)]
    errors=[]
    for status,path in changed:
        if status != "A" or path in BOOTSTRAP_EXEMPT:
            continue
        if path.startswith(CODE_ROOTS) and path.endswith(CODE_SUFFIXES) and not any(fnmatch.fnmatchcase(path,pat) for pat in patterns):
            errors.append("UNREGISTERED_ADDED_CODE: " + path)
    return errors

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--manifest", default="governance/features.json")
    p.add_argument("--changed-file-list", help="tab-delimited git --name-status file generated by CI")
    args=p.parse_args()
    try:
        root=Path(args.root).resolve()
        errors=validate(root, args.manifest)
        if args.changed_file_list:
            changed=[]
            for record in Path(args.changed_file_list).read_text(encoding="utf-8").splitlines():
                parts=record.split("\t")
                if len(parts)!=2 or not parts[0] or not parts[1]:
                    raise ValueError("INVALID_CHANGED_FILE_RECORD")
                changed.append((parts[0],parts[1]))
            errors.extend(check_changed_paths(root,args.manifest,changed))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("COMPLIANCE_BLOCKED: INVALID_REGISTRY " + str(exc), file=sys.stderr)
        return 1
    if errors:
        for error in errors: print("COMPLIANCE_BLOCKED: " + error, file=sys.stderr)
        return 1
    print("COMPLIANCE_PASS: all registered feature design/development/acceptance links verified")
    return 0

if __name__=="__main__":
    sys.exit(main())
