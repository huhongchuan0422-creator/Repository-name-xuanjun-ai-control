import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.community_admin_ui_release_guard import DEFAULT_CONTRACT, Hold, verify


ROOT = Path(__file__).resolve().parents[1]


class CommunityAdminUiReleaseGuardTest(unittest.TestCase):
    def contract_sha(self):
        return hashlib.sha256(DEFAULT_CONTRACT.read_bytes()).hexdigest()

    def test_current_owner_required_baseline_passes(self):
        result = verify(self.contract_sha())
        self.assertEqual(result["state"], "PASS_OWNER_UI_BASELINE_MATCH")
        self.assertEqual(result["verified_asset_count"], 11)

    def test_wrong_external_owner_hash_is_blocked(self):
        with self.assertRaisesRegex(Hold, "OWNER_CONTRACT_SHA256_MISMATCH"):
            verify("0" * 64)

    def test_owner_three_acceptance_policies_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            contract_path = Path(directory) / "contract.json"
            contract = json.loads(DEFAULT_CONTRACT.read_text())
            contract["reviewer_navigation"]["navigation_mode"] = "CROSS_DOCUMENT_LINK"
            contract_path.write_text(json.dumps(contract, ensure_ascii=False))
            contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(Hold, "OWNER_THREE_ACCEPTANCE_POLICY_MISMATCH"):
                verify(contract_sha, contract_path=contract_path)

    def test_page_drift_is_blocked_even_if_candidate_tests_change(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)
            contract = json.loads(DEFAULT_CONTRACT.read_text())
            for relative in contract["assets"]:
                target = candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            changed = candidate / "demos/community-stage/onboarding.js"
            changed.write_bytes(changed.read_bytes() + b"\n// unapproved navigation change\n")
            with self.assertRaisesRegex(Hold, "UI_ASSET_DRIFT:demos/community-stage/onboarding.js"):
                verify(self.contract_sha(), root=candidate)

    def test_existing_image_build_requires_external_owner_contract_hash(self):
        dockerfile = (ROOT / "deploy/community-preview/Dockerfile.ui-successor").read_text()
        self.assertIn("ARG OWNER_UI_CONTRACT_SHA256", dockerfile)
        self.assertIn("--expected-owner-contract-sha256 \"$OWNER_UI_CONTRACT_SHA256\"", dockerfile)
        self.assertIn("scripts/community_admin_ui_release_guard.py", dockerfile)


if __name__ == "__main__":
    unittest.main()
