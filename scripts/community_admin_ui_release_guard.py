"""Fail-closed release guard for the Owner-required community admin UI baseline."""

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "deploy/community-preview/community-admin-ui-contract.json"
SHA256 = re.compile(r"[0-9a-f]{64}")


class Hold(Exception):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_contract(path, expected_contract_sha256):
    if SHA256.fullmatch(expected_contract_sha256) is None:
        raise Hold("EXPECTED_OWNER_CONTRACT_SHA256_REQUIRED")
    raw = path.read_bytes()
    observed = digest(raw)
    if observed != expected_contract_sha256:
        raise Hold("OWNER_CONTRACT_SHA256_MISMATCH")
    value = json.loads(raw)
    if value.get("schema_version") != 2 or value.get("project") != "社区分账管理后台":
        raise Hold("UI_CONTRACT_IDENTITY_MISMATCH")
    policy = value.get("change_policy")
    if policy != {
        "presentation_only_may_change_inventory": False,
        "developer_may_amend_contract": False,
        "developer_may_replace_owner_approval_hash": False,
        "owner_amendment_required_for_asset_change": True,
        "release_without_expected_contract_sha256": "HOLD",
    }:
        raise Hold("UI_CONTRACT_POLICY_MISMATCH")
    assets = value.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise Hold("UI_CONTRACT_ASSETS_REQUIRED")
    reviewer = value.get("reviewer_navigation")
    if not isinstance(reviewer, dict) or {
        "navigation_mode": reviewer.get("navigation_mode"),
        "route_switch_method": reviewer.get("route_switch_method"),
        "default_form_policy": reviewer.get("default_form_policy"),
        "entry_data_policy": reviewer.get("entry_data_policy"),
    } != {
        "navigation_mode": "SAME_DOCUMENT_PANEL",
        "route_switch_method": "HISTORY_REPLACE_STATE_NO_DOCUMENT_NAVIGATION",
        "default_form_policy": "HIDDEN_UNTIL_EXPLICIT_ACTION",
        "entry_data_policy": "SELECTED_ENTRY_ONLY",
    }:
        raise Hold("OWNER_THREE_ACCEPTANCE_POLICY_MISMATCH")
    if reviewer.get("required_entry_count") != 17:
        raise Hold("OWNER_NAVIGATION_ENTRY_COUNT_MISMATCH")
    return value, observed


def verify_assets(contract, root=ROOT):
    observed = {}
    for relative, expected in contract["assets"].items():
        if not isinstance(relative, str) or relative.startswith("/") or ".." in Path(relative).parts:
            raise Hold("UI_ASSET_PATH_REJECTED")
        if not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
            raise Hold("UI_ASSET_SHA256_REJECTED")
        path = root / relative
        if not path.is_file():
            raise Hold("UI_ASSET_MISSING:" + relative)
        actual = digest(path.read_bytes())
        if actual != expected:
            raise Hold("UI_ASSET_DRIFT:" + relative)
        observed[relative] = actual
    return observed


def verify(expected_contract_sha256, contract_path=DEFAULT_CONTRACT, root=ROOT):
    contract, contract_sha256 = load_contract(contract_path, expected_contract_sha256)
    assets = verify_assets(contract, root)
    return {
        "state": "PASS_OWNER_UI_BASELINE_MATCH",
        "contract_sha256": contract_sha256,
        "baseline_source_commit": contract["baseline_source_commit"],
        "baseline_source_tree": contract["baseline_source_tree"],
        "verified_asset_count": len(assets),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-owner-contract-sha256", required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)
    try:
        result = verify(args.expected_owner_contract_sha256, args.contract)
    except (Hold, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"state": "HOLD_UI_BASELINE", "reason": str(error)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
