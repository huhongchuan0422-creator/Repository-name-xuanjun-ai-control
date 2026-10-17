"""Offline test cases for single-contract freeze. Python 3.6+."""
import copy
import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts/single_contract_freeze.py"
spec = importlib.util.spec_from_file_location("single_contract_freeze", str(PATH))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def sample():
    return {
        "project_id": "prj1", "verified_customer_id": "cust1",
        "contract_id": "contract1", "requirements_version": "r1",
        "quote_version": "q1", "pricebook_hash": "a" * 64,
        "selection_manifest_hash": "b" * 64,
        "authorization_manifest_hash": "c" * 64,
        "materials_manifest_hash": "d" * 64,
        "acceptance_version": "v1",
        "disclosure_confirmed": True, "customer_selection_confirmed": True,
        "signer_authority_verified": True, "legal_review_approved": True,
        "quote_valid": True, "development_fee_cny": "6000.00",
        "features": [{"feature_id":"feature-1", "description":"页面", "acceptance":"具体验收标准"}],
        "resources": [{"item_id":"server1", "mode":"AGENT_PURCHASE", "owner":"customer",
            "third_party_first_cny":"1000.00", "procurement_fee_cny":"50.00",
            "deployment_fee_cny":"100.00", "tax_cny":"0",
            "display_CNY":"1000 CNY", "display_USD":"quoted USD"}]
    }

class FreezeTests(unittest.TestCase):
    def test_payment_first_and_second(self):
        x=mod.freeze(sample())
        p=x["frozen"]["payment_cny"]
        self.assertEqual(p["first_total"], "4150.00")
        self.assertEqual(p["development_final_after_acceptance_50pct"], "3000.00")
        self.assertEqual(x["contract_sign"], "HOLD")
        self.assertEqual(x["payment"], "HOLD")
        self.assertEqual(x["procurement"], "HOLD")

    def test_deterministic_freeze(self):
        x=sample()
        self.assertEqual(mod.freeze(x), mod.freeze(copy.deepcopy(x)))
        self.assertTrue(mod.assert_unchanged(mod.freeze(x), x))
        x["quote_version"]="q2"
        with self.assertRaises(mod.ContractHold):
            mod.assert_unchanged(mod.freeze(sample()), x)

    def test_missing_disclosure_and_authority(self):
        for key in ("disclosure_confirmed", "signer_authority_verified",
                    "legal_review_approved", "quote_valid"):
            x=sample();x[key]=False
            with self.assertRaises(mod.ContractHold):
                mod.freeze(x)

    def test_unknown_cost_and_double_charging(self):
        x=sample();x["resources"][0].pop("third_party_first_cny")
        with self.assertRaises(mod.ContractHold):
            mod.freeze(x)
        x=sample();x["resources"][0]["mode"]="SELF_PURCHASE"
        with self.assertRaises(mod.ContractHold):
            mod.freeze(x)

    def test_duplicate_and_invalid_amount(self):
        x=sample();x["resources"].append(copy.deepcopy(x["resources"][0]))
        with self.assertRaises(mod.ContractHold):mod.freeze(x)
        for value in ("NaN","Infinity","-1","1.001"):
            x=sample();x["development_fee_cny"]=value
            with self.assertRaises(mod.ContractHold):mod.freeze(x)

    def test_missing_feature_and_fx(self):
        x=sample();x["features"]=[]
        with self.assertRaises(mod.ContractHold):mod.freeze(x)
        x=sample();x["resources"][0].pop("display_USD")
        with self.assertRaises(mod.ContractHold):mod.freeze(x)

    def test_never_signed_or_paid(self):
        x=mod.freeze(sample())
        self.assertEqual(x["status"], "UNSIGNED_CANDIDATE_ONLY")
        self.assertEqual(x["development_start"], "HOLD")
        self.assertNotIn("signature", x)

if __name__=="__main__":
    unittest.main()
