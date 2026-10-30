from __future__ import absolute_import

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from p3_host_boundaries import (AdmissionGate, EvidenceReaders,
    OutboxController, OutboxTransport, ReceiptVerifier, RunnerAdapter,
    RunnerController, TrustedReceiptProvider, seal_receipt)


NOW = 1000.0
SPEC = "1" * 64
ARTIFACT_SHA = "2" * 64
COMMIT = "3" * 40
CHECKPOINT = "4" * 64
SUBJECT = {
    "task_id": "P3-T1", "spec_hash": SPEC, "artifact": "artifact-v1",
    "run_id": "run-1", "session_id": "session-1", "fence": 7,
    "epoch": 3, "generation": 9, "resume_generation": 1
}


def admission():
    value = dict(SUBJECT)
    value.update({"p2_accepted": True, "p3_release_accepted": True,
                  "unique_writer": True, "execution_authorized": True,
                  "notification_authorized": True, "valid_from": 900.0,
                  "valid_until": 1100.0, "verified": True})
    return value


class Provider(TrustedReceiptProvider):
    def __init__(self):
        self.values = {}

    def add(self, ref, kind, payload, subject=None):
        self.values[ref] = seal_receipt(
            "fixture-provider", ref, kind, subject or SUBJECT, payload, NOW)
        return ref

    def read(self, evidence_ref):
        return self.values[evidence_ref]


class TamperedAckRunner(RunnerAdapter):
    def __init__(self, provider):
        self.provider = provider
        self.calls = 0

    def launch(self, value):
        self.calls += 1
        ref = self.provider.add("ack-launch", "RUNNER_ACK", {
            "operation": "launch", "accepted": True, "started": False,
            "native_id": "native-1"
        })
        self.provider.values[ref]["payload"]["native_id"] = "tampered"
        return ref

    def resume(self, value):
        raise NotImplementedError

    def inspect(self, subject):
        raise NotImplementedError

    def stop(self, subject, reason):
        raise NotImplementedError


class TamperedSendTransport(OutboxTransport):
    def __init__(self, provider):
        self.provider = provider
        self.calls = 0

    def send(self, envelope):
        self.calls += 1
        ref = self.provider.add("send", "OUTBOX_SEND", {
            "binding": "binding-1", "opaque_notification_id": "notice-1",
            "attempt_nonce": "nonce-1", "state": "SENT",
            "delivery_receipt_id": "delivery-1"
        })
        self.provider.values[ref]["payload"]["delivery_receipt_id"] = "tampered"
        return ref

    def lookup(self, binding, opaque_notification_id, attempt_nonce):
        raise NotImplementedError

    def ack(self, delivery_receipt_id):
        raise NotImplementedError


class Supervisor(object):
    def __init__(self):
        self.calls = 0

    def accept_started(self, *args):
        self.calls += 1
        return "STARTED"


class QACounterexamples(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.verifier = ReceiptVerifier(self.provider)
        self.gate = AdmissionGate(lambda: admission(), lambda: NOW,
                                  execution_enabled=True,
                                  notifications_enabled=True)

    def test_started_payload_fence_must_match_receipt_subject(self):
        runner = TamperedAckRunner(self.provider)
        controller = RunnerController(self.gate, self.verifier, runner)
        self.provider.add("started", "STARTED", {
            "native_state": "RUNNING", "lease_owner": "writer-1",
            "lease_until": 1050.0, "fence": 99, "checkpoint": {"step": 1},
            "start_receipt": {"task_id": "P3-T1"}
        })
        supervisor = Supervisor()
        with self.assertRaisesRegex(ValueError, "STARTED_FENCE_MISMATCH"):
            controller.accept_started(SUBJECT, "started", supervisor)
        self.assertEqual(0, supervisor.calls)

    def test_completion_rejects_mixed_acceptance_run_lineage(self):
        self.provider.add("terminal", "TERMINAL", {
            "terminal_receipt": "terminal-1", "effects": "KNOWN",
            "writer_stopped": True
        })
        actors = {"tests": "tester", "ci": "ci", "qa": "qa",
                  "security": "security", "business": "business"}
        for role, actor in actors.items():
            self.provider.add(role, role.upper(), {
                "status": "PASS", "commit": COMMIT,
                "artifact_sha256": ARTIFACT_SHA, "actor": actor
            })
        index = {"subject": SUBJECT, "checkpoint_sha256": CHECKPOINT,
                 "commit": COMMIT, "artifact_sha256": ARTIFACT_SHA,
                 "scope": "FIELD", "author": "author", "terminal": "terminal",
                 "tests": "tests", "ci": "ci", "qa": "qa",
                 "security": "security", "business": "business"}
        other = dict(SUBJECT, run_id="run-2", session_id="session-2", fence=8)
        self.provider.add("recovery-other", "RECOVERY_LINEAGE", {
            "current_fence": 8, "run_id": "run-2", "session_id": "session-2",
            "resume_generation": 1, "epoch": 3, "generation": 9
        }, subject=other)
        readers = EvidenceReaders(
            self.verifier, lambda ref: SUBJECT, lambda ref: SUBJECT,
            lambda task_id: index,
            completion_index=lambda task_id: {
                "subject": other, "evidence_ref": "recovery-other"})
        with self.assertRaisesRegex(
                ValueError, "COMPLETION_ACCEPTANCE_LINEAGE_MISMATCH"):
            readers.completion("P3-T1")

    def test_completion_payload_fence_must_match_receipt_subject(self):
        self.provider.add("terminal", "TERMINAL", {
            "terminal_receipt": "terminal-1", "effects": "KNOWN",
            "writer_stopped": True
        })
        actors = {"tests": "tester", "ci": "ci", "qa": "qa",
                  "security": "security", "business": "business"}
        for role, actor in actors.items():
            self.provider.add(role, role.upper(), {
                "status": "PASS", "commit": COMMIT,
                "artifact_sha256": ARTIFACT_SHA, "actor": actor
            })
        index = {"subject": SUBJECT, "checkpoint_sha256": CHECKPOINT,
                 "commit": COMMIT, "artifact_sha256": ARTIFACT_SHA,
                 "scope": "FIELD", "author": "author", "terminal": "terminal",
                 "tests": "tests", "ci": "ci", "qa": "qa",
                 "security": "security", "business": "business"}
        self.provider.add("recovery-wrong-current-fence", "RECOVERY_LINEAGE", {
            "current_fence": 999, "run_id": SUBJECT["run_id"],
            "session_id": SUBJECT["session_id"],
            "resume_generation": SUBJECT["resume_generation"],
            "epoch": SUBJECT["epoch"], "generation": SUBJECT["generation"]
        })
        readers = EvidenceReaders(
            self.verifier, lambda ref: SUBJECT, lambda ref: SUBJECT,
            lambda task_id: index,
            completion_index=lambda task_id: {
                "subject": SUBJECT,
                "evidence_ref": "recovery-wrong-current-fence"})
        with self.assertRaisesRegex(ValueError, "COMPLETION_LINEAGE_CHANGED"):
            readers.completion("P3-T1")

    def test_unverifiable_post_launch_ack_is_explicit_hold(self):
        runner = TamperedAckRunner(self.provider)
        controller = RunnerController(self.gate, self.verifier, runner)
        result = controller.launch(SUBJECT, {"opaque": "admission"})
        self.assertEqual("UNKNOWN_RUNNER_EFFECT_HOLD", result["state"])
        self.assertFalse(result["automatic_retry"])
        self.assertEqual(1, runner.calls)

    def test_unverifiable_post_send_receipt_is_no_redial_hold(self):
        transport = TamperedSendTransport(self.provider)
        controller = OutboxController(self.gate, self.verifier, transport)
        result = controller.send(SUBJECT, {"opaque": "payload"})
        self.assertEqual("UNKNOWN_NO_REDIAL", result["state"])
        self.assertFalse(result["automatic_retry"])
        self.assertEqual(1, transport.calls)


if __name__ == "__main__":
    unittest.main()
