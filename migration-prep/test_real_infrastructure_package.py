from __future__ import print_function

import json
import os
import unittest


ROOT = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(ROOT, name)) as stream:
        return json.load(stream)


class RealInfrastructurePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = load("production-operation-package.json")
        receipt_path = os.path.join(
            os.path.dirname(ROOT), "evidence", "migration",
            "real-infrastructure-prep-receipt.json"
        )
        with open(receipt_path) as stream:
            cls.receipt = json.load(stream)

    def test_global_execution_is_closed(self):
        self.assertFalse(self.package["execution_authorized"])
        self.assertEqual(self.package["privileged_executor_binding"], "NONE")
        self.assertEqual(self.package["production_migration_release"], "HOLD")
        self.assertFalse(self.package["blind_retry_allowed"])
        for gate in (
                "g1_runner_retirement", "g2_yibi_permanent_retirement",
                "g3_writer_fence", "g4_get_only_and_final_checkpoint",
                "g5_korea_isolated_deployment"):
            self.assertFalse(self.package[gate]["authorized"])

    def test_exact_candidate_binding(self):
        self.assertEqual(
            self.package["candidate"]["commit"],
            "f733cd4eca6be23e41be185f7d6421d0ff9cd522"
        )
        self.assertEqual(
            self.package["candidate"]["tree"],
            "31c262997b3850450cb7c1da2b4d9c472d9cf0ff"
        )

    def test_runner_targets_are_exact_and_cleanup_is_separate(self):
        runners = self.package["g1_runner_retirement"]["hosts"]
        self.assertEqual([item["runner_agent_id"] for item in runners], [4, 3])
        self.assertTrue(all(item["unit"].startswith("actions.runner.") for item in runners))
        cleanup = self.package["g1_runner_retirement"]["temporary_helper_cleanup"]
        self.assertFalse(cleanup["authorized"])
        self.assertTrue(cleanup["separate_owner_gate_required"])

    def test_yibi_targets_never_include_shared_services(self):
        gate = self.package["g2_yibi_permanent_retirement"]
        targets = set(gate["services"] + gate["timers"])
        protected = set(gate["protected_units"])
        self.assertFalse(targets & protected)
        self.assertEqual(gate["policy"], "ARCHIVE_ONLY_NEVER_REENABLE")
        self.assertIn("STOP_POSTGRESQL", gate["forbidden"])
        self.assertIn("STOP_REDIS", gate["forbidden"])

    def test_writer_inventory_cannot_pass_without_95_records(self):
        gate = self.package["g3_writer_fence"]
        self.assertEqual(gate["discovery_count"], 95)
        self.assertEqual(sum(gate["path_class_counts"].values()), 95)
        self.assertEqual(
            gate["current_blocker"],
            "ALL_95_PATHS_NOT_YET_RUNTIME_INTEGRATED_OR_QUARANTINED"
        )

    def test_g4_is_get_only_and_not_run(self):
        gate = self.package["g4_get_only_and_final_checkpoint"]
        self.assertEqual(gate["method_allowlist"], ["GET"])
        self.assertEqual(gate["symbols"], ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        self.assertFalse(gate["exchange_called_in_preparation"])
        self.assertIn("REAL_NO_LOCAL_MUTATION_ADAPTER_NOT_BOUND", gate["current_blockers"])

    def test_g5_forward_and_rollback_orders_are_fail_closed(self):
        gate = self.package["g5_korea_isolated_deployment"]
        self.assertLess(gate["forward_order"].index("TOKYO_FENCED"),
                        gate["forward_order"].index("KOREA_AUTHORITY_GRANTED"))
        self.assertEqual(gate["rollback_order"][:3], [
            "KOREA_WRITER_LOCKED", "KOREA_CREDENTIAL_REVOKED",
            "KOREA_IP_REMOVED"
        ])
        self.assertEqual(gate["rollback_order"][-1], "TOKYO_NEW_EPOCH_GRANTED")
        self.assertFalse(gate["runtime"]["reuse_yibi_venv"])

    def test_receipt_proves_no_production_action(self):
        self.assertFalse(self.receipt["production_mutation"])
        self.assertFalse(self.receipt["exchange_called"])
        self.assertFalse(self.receipt["backup_or_decrypt_repeated"])
        self.assertEqual(self.receipt["writer_discovery_count"], 95)
        self.assertEqual(self.receipt["production_migration_release"], "HOLD")


if __name__ == "__main__":
    unittest.main()
