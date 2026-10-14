from __future__ import print_function

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest

from c7_acceptance import (GATES, admission_matrix, load_private_writer_evidence,
                           load_verified_admission_policy,
                           trusted_evidence_adapter, validate_private_writer_map,
                           verify_result_verifier_evidence)
from gate_common import GateError, canonical_bytes, sha256_value
from restricted_executor import _B, _L, _encodepoint, _scalarmult


def public_key(seed):
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return _encodepoint(_scalarmult(_B, scalar))


def sign(seed, message):
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    key = public_key(seed)
    nonce = int.from_bytes(hashlib.sha512(digest[32:] + message).digest(), "little") % _L
    encoded_r = _encodepoint(_scalarmult(_B, nonce))
    challenge = int.from_bytes(hashlib.sha512(encoded_r + key + message).digest(),
                               "little") % _L
    scalar_s = (nonce + challenge * scalar) % _L
    return encoded_r + scalar_s.to_bytes(32, "little")


class WriterMapTests(unittest.TestCase):
    def values(self):
        private_records, public_records = [], []
        for index in range(1, 96):
            identifier = "WP{0:03d}".format(index)
            digest = "{0:064x}".format(index)
            private_records.append({"path_id": identifier, "source_path": "/private/{0}".format(index),
                                    "source_sha256": digest, "path_class": "FORMAL",
                                    "static_role": "DIRECT_WRITE_CAPABLE_SOURCE"})
            public_records.append({"path_id": identifier, "source_sha256": digest,
                                   "source_path_sha256": hashlib.sha256(
                                       "/private/{0}".format(index).encode()).hexdigest(),
                                   "path_class": "FORMAL",
                                   "static_role": "DIRECT_WRITE_CAPABLE_SOURCE",
                                   "candidate_enforcement": "DENY",
                                   "runtime_reachability": "UNKNOWN",
                                   "scheduler_reachability": "UNKNOWN",
                                   "dynamic_import_policy":
                                   "HASH_BOUND_DENY_UNLESS_FENCE_CONTEXT",
                                   "manual_launch_policy":
                                   "DENY_DIRECT_REQUIRE_RESTRICTED_LAUNCHER",
                                   "credential_reachability": "UNKNOWN",
                                   "disposition": "UNKNOWN"})
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

    def test_owner_controlled_private_byte_recompute_entry_is_redacted(self):
        raw, public = self.values()
        directory = tempfile.mkdtemp()
        try:
            private_path = os.path.join(directory, "private.json")
            public_path = os.path.join(directory, "public.json")
            with open(private_path, "wb") as stream:
                stream.write(raw)
            with open(public_path, "wb") as stream:
                stream.write(canonical_bytes(public))
            os.chmod(private_path, 0o600); os.chmod(public_path, 0o600)
            result = load_private_writer_evidence(private_path, public_path, os.getuid())
        finally:
            shutil.rmtree(directory)
        self.assertEqual(result["private_file_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(result["raw_paths_disclosed"])
        self.assertNotIn("/private/", repr(result))


class AdmissionTests(unittest.TestCase):
    SOURCES = {"WRITER_MAP": ("PRIVATE_RAW_BYTES", "INDEPENDENT"),
               "RUNNER_ADMIN": ("GITHUB_ADMIN_API", "ADMIN"),
               "ROOT_INVENTORY": ("ROOT_READONLY_HELPER", "ROOT"),
               "GLOBAL_TRIGGERS": ("OPENCLAW_ADMIN_API", "ADMIN"),
               "TRUST_ANCHOR": ("INDEPENDENT_AUTHORITY_RECORD", "INDEPENDENT"),
               "RESULT_VERIFIER": ("INDEPENDENT_VERIFIER_READBACK", "INDEPENDENT"),
               "KOREA_ISOLATION": ("KOREA_ROOT_READBACK", "ROOT")}
    NOW = 2000000000

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.root_seed = b"R" * 32
        self.seeds = {gate: hashlib.sha256(gate.encode("ascii")).digest()
                      for gate in GATES}
        self.anchor = {"schema_version": 1, "algorithm": "Ed25519",
                       "authority_id": "independent-policy-authority",
                       "public_key_hex": public_key(self.root_seed).hex()}
        authorities = {}
        for gate in GATES:
            source, authority = self.SOURCES[gate]
            authorities[gate] = {
                "authority_id": "authority-" + gate.lower(),
                "public_key_hex": public_key(self.seeds[gate]).hex(),
                "source_class": source, "authority_scope": authority,
                "adapter_id": "adapter-" + gate.lower(),
                "exact_subject_sha256": hashlib.sha256(("subject-" + gate).encode()).hexdigest(),
                "transaction_id": "tx-" + gate.lower(),
                "hosts": ["tokyo", "korea"],
                "coverage": ["complete-" + gate.lower()], "max_age_seconds": 300}
        self.policy = {"schema_version": 1, "policy_id": "c7-policy-1",
                       "candidate_sha256": "a" * 64,
                       "exact_commit": "c" * 40, "exact_tree": "d" * 40,
                       "epoch_id": "epoch-1", "expires_at_epoch": self.NOW + 600,
                       "trust_anchor_sha256": sha256_value(self.anchor),
                       "authorities": authorities}
        paths = [os.path.join(self.directory, name) for name in ("policy", "signature", "anchor")]
        with open(paths[0], "wb") as stream:
            stream.write(canonical_bytes(self.policy))
        with open(paths[1], "w") as stream:
            stream.write(sign(self.root_seed, canonical_bytes(self.policy)).hex())
        with open(paths[2], "wb") as stream:
            stream.write(canonical_bytes(self.anchor))
        for path in paths:
            os.chmod(path, 0o600)
        self.verified_policy = load_verified_admission_policy(
            paths[0], paths[1], paths[2], os.getuid())
        self.adapters = {}
        for gate in GATES:
            def verifier(receipt, raw, expected=gate):
                value = json.loads(raw.decode("utf-8"))
                return value == {"complete": True, "gate": expected}
            self.adapters[gate] = trusted_evidence_adapter(
                "adapter-" + gate.lower(), gate, verifier)

    def tearDown(self):
        shutil.rmtree(self.directory)

    def receipt(self, gate, raw=None, **changes):
        raw = raw if raw is not None else canonical_bytes({"complete": True, "gate": gate})
        source, authority = self.SOURCES[gate]
        value = {"schema_version": 2, "receipt_id": "r-" + gate.lower(), "gate": gate,
                 "source_class": source, "authority_id": "authority-" + gate.lower(),
                 "authority_scope": authority, "adapter_id": "adapter-" + gate.lower(),
                 "transaction_id": "tx-" + gate.lower(),
                 "observed_at_epoch": self.NOW - 10, "expires_at_epoch": self.NOW + 60,
                 "candidate_sha256": "a" * 64, "exact_commit": "c" * 40,
                 "exact_tree": "d" * 40,
                 "epoch_id": "epoch-1",
                 "exact_subject_sha256": self.policy["authorities"][gate]["exact_subject_sha256"],
                 "evidence_sha256": hashlib.sha256(raw).hexdigest(), "status": "PASS",
                 "production_mutation": False, "hosts": ["tokyo", "korea"],
                 "coverage": ["complete-" + gate.lower()], "limitations": []}
        value.update(changes)
        return value, raw

    def bundle(self, gate, raw=None, **changes):
        receipt, raw = self.receipt(gate, raw, **changes)
        return {"receipt": receipt, "raw_evidence": raw,
                "authority_signature_hex": sign(self.seeds[gate],
                                                 canonical_bytes(receipt)).hex()}

    def test_six_self_asserted_pass_receipts_remain_shape_only_hold(self):
        six_gates = tuple(gate for gate in GATES if gate != "RESULT_VERIFIER")
        self.assertEqual(len(six_gates), 6)
        receipts = [self.receipt(gate)[0] for gate in six_gates]
        result = admission_matrix(receipts)
        self.assertEqual(result["admission_class"], "FORMAL_RECEIPT_SHAPE_ONLY")
        self.assertFalse(result["production_acceptance_ready"])
        self.assertEqual(set(result["missing_gates"]), set(GATES))

    def test_authenticated_exact_original_evidence_can_reach_candidate_readiness_only(self):
        result = admission_matrix([self.bundle(gate) for gate in GATES],
                                  self.verified_policy, self.adapters, self.NOW)
        self.assertTrue(result["production_acceptance_ready"])
        self.assertFalse(result["production_execution_authorized"])
        self.assertEqual(result["invalid_receipt_count"], 0)

    def test_forged_partial_expired_wrong_version_host_epoch_and_evidence_hold(self):
        mutations = [
            ("authority_signature_hex", "00" * 64),
            ("status", "PARTIAL"),
            ("expires_at_epoch", self.NOW - 1),
            ("candidate_sha256", "c" * 64),
            ("exact_commit", "e" * 40),
            ("exact_tree", "f" * 40),
            ("transaction_id", "tx-wrong"),
            ("hosts", ["tokyo"]),
            ("epoch_id", "epoch-2"),
            ("coverage", ["partial"]),
        ]
        for field, value in mutations:
            bundles = [self.bundle(gate) for gate in GATES]
            if field == "authority_signature_hex":
                bundles[0][field] = value
            else:
                receipt = bundles[0]["receipt"]
                receipt[field] = value
                bundles[0]["authority_signature_hex"] = sign(
                    self.seeds[GATES[0]], canonical_bytes(receipt)).hex()
            result = admission_matrix(bundles, self.verified_policy,
                                      self.adapters, self.NOW)
            self.assertFalse(result["production_acceptance_ready"], field)
            self.assertEqual(result["gates"][GATES[0]], "HOLD", field)
        bundles = [self.bundle(gate) for gate in GATES]
        bundles[0]["raw_evidence"] = b'{"complete":false}'
        result = admission_matrix(bundles, self.verified_policy, self.adapters, self.NOW)
        self.assertFalse(result["production_acceptance_ready"])

    def test_contradictory_duplicate_receipts_hold(self):
        bundles = [self.bundle(gate) for gate in GATES]
        bundles.append(copy.deepcopy(bundles[0]))
        result = admission_matrix(bundles, self.verified_policy, self.adapters, self.NOW)
        self.assertFalse(result["production_acceptance_ready"])
        self.assertEqual(result["contradiction_count"], 1)
        self.assertEqual(result["gates"][GATES[0]], "HOLD")

    def test_receipt_id_reuse_across_gates_is_contradictory(self):
        bundles = [self.bundle(gate) for gate in GATES]
        bundles[1]["receipt"]["receipt_id"] = bundles[0]["receipt"]["receipt_id"]
        bundles[1]["authority_signature_hex"] = sign(
            self.seeds[GATES[1]], canonical_bytes(bundles[1]["receipt"])).hex()
        result = admission_matrix(bundles, self.verified_policy, self.adapters, self.NOW)
        self.assertFalse(result["production_acceptance_ready"])
        self.assertEqual(result["gates"][GATES[0]], "HOLD")
        self.assertEqual(result["gates"][GATES[1]], "HOLD")

    def test_adapter_rejects_signed_but_semantically_false_original_evidence(self):
        raw = canonical_bytes({"complete": False, "gate": GATES[0]})
        bundles = [self.bundle(gate) for gate in GATES]
        bundles[0] = self.bundle(GATES[0], raw=raw)
        result = admission_matrix(bundles, self.verified_policy, self.adapters, self.NOW)
        self.assertFalse(result["production_acceptance_ready"])
        self.assertGreater(result["invalid_receipt_count"], 0)

    def test_result_verifier_measurement_binds_loaded_file_and_post_state_authority(self):
        evidence = {"schema_version": 1, "action": "READONLY_INSPECT",
                    "host": "tokyo", "exact_commit": "c" * 40,
                    "exact_tree": "d" * 40, "epoch_id": "epoch-1",
                    "verifier_path_sha256": "1" * 64,
                    "verifier_file_sha256": "2" * 64, "verifier_owner_uid": 0,
                    "verifier_mode": 0o755, "verifier_parent_chain_sha256": "3" * 64,
                    "service_unit": "xuanjun-verifier.service", "service_main_pid": 123,
                    "service_execution_identity": "xuanjun_verify",
                    "loaded_command_sha256": "4" * 64,
                    "loaded_verifier_file_sha256": "2" * 64,
                    "post_state_source_kind": "ROOT_READONLY_STATE",
                    "post_state_source_sha256": "5" * 64,
                    "post_state_authority_id": "independent-root-reader",
                    "observed_at_epoch": self.NOW - 10, "complete": True,
                    "production_mutation": False}
        subject = {name: evidence[name] for name in (
            "action", "host", "service_unit", "service_execution_identity",
            "verifier_path_sha256", "post_state_source_kind", "post_state_authority_id")}
        receipt, unused = self.receipt(
            "RESULT_VERIFIER", exact_subject_sha256=sha256_value(subject))
        self.assertTrue(verify_result_verifier_evidence(receipt, canonical_bytes(evidence)))
        evidence["loaded_verifier_file_sha256"] = "9" * 64
        with self.assertRaises(GateError):
            verify_result_verifier_evidence(receipt, canonical_bytes(evidence))


if __name__ == "__main__":
    unittest.main()
