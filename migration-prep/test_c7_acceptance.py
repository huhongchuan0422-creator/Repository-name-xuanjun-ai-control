from __future__ import print_function

import copy
import json
import unittest

from c7_acceptance import GATES, admission_matrix, validate_private_writer_map
from gate_common import GateError, canonical_bytes, sha256_value


class WriterMapTests(unittest.TestCase):
    def values(self):
        private_records, public_records = [], []
        for index in range(1, 96):
            identifier = "WP{0:03d}".format(index)
            digest = "{0:064x}".format(index)
            private_records.append({"path_id": identifier, "source_path": "/private/{0}".format(index),
                                    "source_sha256": digest, "path_class": "FORMAL"})
            public_records.append({"path_id": identifier, "source_sha256": digest,
                                   "path_class": "FORMAL", "candidate_enforcement": "DENY"})
        private = {"records": private_records}
        private["mapping_sha256"] = sha256_value(private)
        public = {"source_discovery_count": 95, "records": public_records}
        return canonical_bytes(private), public

    def test_private_raw_bytes_match_public_ids_without_path_disclosure(self):
        raw, public = self.values()
        result = validate_private_writer_map(raw, public)
        self.assertEqual(result["record_count"], 95)
        self.assertFalse(result["raw_paths_disclosed"])
        self.assertFalse(result["runtime_coverage_proven"])

    def test_digest_id_and_default_deny_mismatch_fail(self):
        raw, public = self.values()
        for mutation in ("digest", "id", "allow"):
            changed_raw, changed_public = raw, copy.deepcopy(public)
            if mutation == "digest":
                value = json.loads(raw.decode("utf-8")); value["mapping_sha256"] = "0" * 64
                changed_raw = canonical_bytes(value)
            elif mutation == "id":
                changed_public["records"][0]["path_id"] = "WP999"
            else:
                changed_public["records"][0]["candidate_enforcement"] = "ALLOW"
            with self.assertRaises(GateError):
                validate_private_writer_map(changed_raw, changed_public)


class AdmissionTests(unittest.TestCase):
    SOURCES = {"WRITER_MAP": ("PRIVATE_RAW_BYTES", "INDEPENDENT"),
               "RUNNER_ADMIN": ("GITHUB_ADMIN_API", "ADMIN"),
               "ROOT_INVENTORY": ("ROOT_READONLY_HELPER", "ROOT"),
               "GLOBAL_TRIGGERS": ("OPENCLAW_ADMIN_API", "ADMIN"),
               "TRUST_ANCHOR": ("INDEPENDENT_AUTHORITY_RECORD", "INDEPENDENT"),
               "KOREA_ISOLATION": ("KOREA_ROOT_READBACK", "ROOT")}

    def receipt(self, gate, status="PASS", limitations=None):
        source, authority = self.SOURCES[gate]
        return {"schema_version": 1, "receipt_id": "r-" + gate.lower(), "gate": gate,
                "source_class": source, "scope": "exact", "observed_at_utc": "2026-10-14T14:00:00Z",
                "exact_subject_sha256": "a" * 64, "evidence_sha256": "b" * 64,
                "status": status, "production_mutation": False,
                "authority_scope": authority, "limitations": list(limitations or [])}

    def test_complete_authoritative_receipts_pass_but_do_not_authorize_execution(self):
        result = admission_matrix([self.receipt(gate) for gate in GATES])
        self.assertTrue(result["production_acceptance_ready"])
        self.assertFalse(result["production_execution_authorized"])

    def test_caller_scope_partial_or_limited_receipt_cannot_pass(self):
        receipts = [self.receipt(gate) for gate in GATES]
        receipts[1]["authority_scope"] = "CALLER"
        receipts[3]["limitations"] = ["restricted inventory"]
        result = admission_matrix(receipts)
        self.assertFalse(result["production_acceptance_ready"])
        self.assertEqual(result["gates"]["RUNNER_ADMIN"], "HOLD")
        self.assertEqual(result["gates"]["GLOBAL_TRIGGERS"], "HOLD")


if __name__ == "__main__":
    unittest.main()
