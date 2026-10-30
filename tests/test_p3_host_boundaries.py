from __future__ import absolute_import

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from p3_host_boundaries import (AdmissionGate, EvidenceReaders, OutboxController,
    OutboxTransport, ReceiptVerifier, RunnerAdapter, RunnerController,
    TrustedReceiptProvider, WatchdogClassifier, seal_receipt)


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


def admission(**changes):
    value = dict(SUBJECT)
    value.update({"p2_accepted": True, "p3_release_accepted": True,
                  "unique_writer": True, "execution_authorized": True,
                  "notification_authorized": True, "valid_from": 900.0,
                  "valid_until": 1100.0, "verified": True})
    value.update(changes)
    return value


class Provider(TrustedReceiptProvider):
    def __init__(self):
        self.values = {}

    def add(self, ref, kind, payload, subject=None):
        self.values[ref] = seal_receipt("fixture-provider", ref, kind,
                                        subject or SUBJECT, payload, NOW)
        return ref

    def read(self, evidence_ref):
        return self.values[evidence_ref]


class Runner(RunnerAdapter):
    def __init__(self, provider):
        self.provider = provider
        self.calls = []
        self.fail = False

    def _ack(self, operation):
        self.calls.append(operation)
        if self.fail:
            raise RuntimeError("effect unknown")
        return self.provider.add("ack-" + operation, "RUNNER_ACK", {
            "operation": operation, "accepted": True, "started": False,
            "native_id": "native-1"
        })

    def launch(self, value):
        return self._ack("launch")

    def resume(self, value):
        return self._ack("resume")

    def inspect(self, value):
        self.calls.append("inspect")
        return self.provider.add("inspect", "RUNNER_INSPECT", {
            "native_state": "RUNNING", "terminal_receipt": None,
            "effects": "NONE", "writer_stopped": False,
            "descendants_stopped": False
        })

    def stop(self, value, reason):
        self.calls.append("stop")
        return self.provider.add("stop-runner", "RUNNER_STOP", {
            "writer_stopped": True, "descendants_stopped": True,
            "effects": "KNOWN"
        })


class Transport(OutboxTransport):
    def __init__(self, provider):
        self.provider = provider
        self.fail_send = False

    def send(self, envelope):
        if self.fail_send:
            raise RuntimeError("timeout")
        return self.provider.add("send", "OUTBOX_SEND", {
            "binding": "binding-1", "opaque_notification_id": "notice-1",
            "attempt_nonce": "nonce-1", "state": "SENT",
            "delivery_receipt_id": "delivery-1"
        })

    def lookup(self, binding, opaque_notification_id, attempt_nonce):
        return self.provider.add("lookup", "OUTBOX_LOOKUP", {
            "binding": binding, "opaque_notification_id": opaque_notification_id,
            "attempt_nonce": attempt_nonce, "state": "SENT",
            "delivery_receipt_id": "delivery-1", "absence_proof_id": None
        })

    def ack(self, delivery_receipt_id):
        return self.provider.add("ack-delivery", "OUTBOX_ACK", {
            "delivery_receipt_id": delivery_receipt_id, "acked": True
        })


class Supervisor(object):
    def __init__(self):
        self.args = None

    def accept_started(self, *args):
        self.args = args
        return "STARTED"


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.verifier = ReceiptVerifier(self.provider)
        self.runner = Runner(self.provider)

    def gate(self, enabled=True, notifications=False, proof=None):
        value = proof or admission()
        return AdmissionGate(lambda: value, lambda: NOW,
                             execution_enabled=enabled,
                             notifications_enabled=notifications)

    def controller(self, enabled=True):
        return RunnerController(self.gate(enabled), self.verifier, self.runner)

    def test_default_off_never_invokes_runner(self):
        with self.assertRaises(PermissionError):
            self.controller(False).launch(SUBJECT, {"opaque": "admission"})
        self.assertEqual([], self.runner.calls)

    def test_missing_p2_admission_fails_before_runner(self):
        gate = self.gate(proof=admission(p2_accepted=False))
        with self.assertRaises(PermissionError):
            RunnerController(gate, self.verifier, self.runner).launch(SUBJECT, {})
        self.assertEqual([], self.runner.calls)

    def test_runner_ack_is_not_started(self):
        result = self.controller().launch(SUBJECT, {"opaque": "admission"})
        self.assertEqual("ACKNOWLEDGED_AWAITING_STARTED", result["state"])
        self.assertFalse(result["started"])

    def test_unknown_launch_effect_holds_without_retry(self):
        self.runner.fail = True
        result = self.controller().launch(SUBJECT, {})
        self.assertEqual("UNKNOWN_RUNNER_EFFECT_HOLD", result["state"])
        self.assertFalse(result["automatic_retry"])

    def test_resume_revalidates_original_admission(self):
        called = []
        result = self.controller().resume(
            SUBJECT, {"resume": 1}, lambda value: called.append(value) or True)
        self.assertEqual("ACKNOWLEDGED_AWAITING_STARTED", result["state"])
        self.assertEqual([{"resume": 1}], called)

    def test_resume_rejects_stale_admission_before_runner(self):
        with self.assertRaises(ValueError):
            self.controller().resume(SUBJECT, {}, lambda value: False)
        self.assertEqual([], self.runner.calls)

    def test_started_receipt_is_forwarded_to_original_supervisor(self):
        start_receipt = {"task_id": "P3-T1"}
        self.provider.add("started", "STARTED", {
            "native_state": "RUNNING", "lease_owner": "writer-1",
            "lease_until": 1050.0, "fence": 7, "checkpoint": {"step": 1},
            "start_receipt": start_receipt
        })
        supervisor = Supervisor()
        result = self.controller().accept_started(SUBJECT, "started", supervisor)
        self.assertEqual("STARTED", result)
        self.assertEqual("P3-T1", supervisor.args[0])
        self.assertEqual(start_receipt, supervisor.args[-1])

    def test_progress_reader_emits_frozen_core_shape(self):
        self.provider.add("progress", "PROGRESS", {
            "kind": "SOURCE_COMMIT", "sha256": "5" * 64
        })
        readers = EvidenceReaders(self.verifier, lambda ref: SUBJECT,
                                  lambda ref: SUBJECT, None)
        self.assertEqual({"task_id": "P3-T1", "spec_hash": SPEC, "fence": 7,
                          "kind": "SOURCE_COMMIT", "sha256": "5" * 64,
                          "verified": True}, readers.progress("progress"))

    def test_tampered_receipt_is_rejected(self):
        self.provider.add("progress", "PROGRESS", {
            "kind": "SOURCE_COMMIT", "sha256": "5" * 64
        })
        self.provider.values["progress"]["payload"]["sha256"] = "6" * 64
        readers = EvidenceReaders(self.verifier, lambda ref: SUBJECT,
                                  lambda ref: SUBJECT, None)
        with self.assertRaises(ValueError):
            readers.progress("progress")

    def test_stop_reader_binds_lineage_and_known_effects(self):
        self.provider.add("stop", "STOP", {
            "writer_stopped": True, "descendants_stopped": True,
            "effects": "KNOWN", "checkpoint_sha256": CHECKPOINT,
            "authority_verified": True
        })
        readers = EvidenceReaders(self.verifier, lambda ref: SUBJECT,
                                  lambda ref: SUBJECT, None)
        result = readers.stop("stop")
        self.assertEqual("run-1", result["run_id"])
        self.assertEqual(1, result["resume_generation"])
        self.assertEqual("KNOWN", result["effects"])

    def _acceptance_readers(self, mismatch=False, completion=False):
        self.provider.add("terminal", "TERMINAL", {
            "terminal_receipt": "terminal-1", "effects": "KNOWN",
            "writer_stopped": True
        })
        actors = {"tests": "tester", "ci": "ci", "qa": "qa",
                  "security": "security", "business": "business"}
        for role, actor in actors.items():
            self.provider.add(role, role.upper(), {
                "status": "PASS", "commit": ("6" * 40 if mismatch and role == "ci" else COMMIT),
                "artifact_sha256": ARTIFACT_SHA, "actor": actor
            })
        index = {"subject": SUBJECT, "checkpoint_sha256": CHECKPOINT,
                 "commit": COMMIT, "artifact_sha256": ARTIFACT_SHA,
                 "scope": "FIELD", "author": "author", "terminal": "terminal",
                 "tests": "tests", "ci": "ci", "qa": "qa",
                 "security": "security", "business": "business"}
        completion_index = None
        if completion:
            self.provider.add("recovery", "RECOVERY_LINEAGE", {
                "current_fence": 8, "run_id": "run-1", "session_id": "session-1",
                "resume_generation": 1, "epoch": 3, "generation": 9
            })
            completion_index = lambda task_id: {
                "subject": SUBJECT, "evidence_ref": "recovery"}
        return EvidenceReaders(self.verifier, lambda ref: SUBJECT,
                               lambda ref: SUBJECT, lambda task_id: index,
                               completion_index=completion_index)

    def test_acceptance_reads_same_artifact_independent_roles(self):
        result = self._acceptance_readers().acceptance("P3-T1")
        self.assertEqual(COMMIT, result["qa"]["commit"])
        self.assertEqual("author", result["author"])
        self.assertEqual("security", result["security"]["actor"])

    def test_acceptance_rejects_cross_commit_ci(self):
        with self.assertRaises(ValueError):
            self._acceptance_readers(mismatch=True).acceptance("P3-T1")

    def test_completion_reader_adds_exact_current_recovery_lineage(self):
        result = self._acceptance_readers(completion=True).completion("P3-T1")
        self.assertEqual({"current_fence": 8, "run_id": "run-1",
                          "session_id": "session-1", "resume_generation": 1,
                          "epoch": 3, "generation": 9}, result["recovery"])

    def test_inspect_and_stop_return_evidence_not_resume_authority(self):
        controller = self.controller()
        self.assertEqual("RUNNING", controller.inspect(SUBJECT)["native_state"])
        stopped = controller.stop(SUBJECT, "progress deadline")
        self.assertEqual("STOPPED_RECONCILIATION_REQUIRED", stopped["state"])
        self.assertFalse(stopped["automatic_retry"])

    def test_outbox_send_timeout_holds_without_redial(self):
        transport = Transport(self.provider)
        transport.fail_send = True
        outbox = OutboxController(self.gate(notifications=True), self.verifier, transport)
        result = outbox.send(SUBJECT, {"opaque": "payload"})
        self.assertEqual("UNKNOWN_NO_REDIAL", result["state"])
        self.assertFalse(result["automatic_retry"])

    def test_notifications_default_off_never_invoke_transport(self):
        transport = Transport(self.provider)
        outbox = OutboxController(self.gate(), self.verifier, transport)
        with self.assertRaises(PermissionError):
            outbox.send(SUBJECT, {"opaque": "payload"})

    def test_outbox_lookup_and_ack_are_bound(self):
        transport = Transport(self.provider)
        outbox = OutboxController(self.gate(notifications=True), self.verifier, transport)
        lookup = outbox.lookup(SUBJECT, "binding-1", "notice-1", "nonce-1")
        self.assertEqual("SENT", lookup["state"])
        ack = outbox.ack(SUBJECT, lookup["delivery_receipt_id"])
        self.assertEqual("ACK_VERIFIED", ack["state"])

    def snapshot(self, **changes):
        value = {"task_state": "RUNNING", "run_status": "STARTED",
                 "native_state": "RUNNING", "lease_live": True,
                 "start_deadline": 950.0, "progress_deadline": 1050.0,
                 "result_deadline": 1100.0, "now": NOW,
                 "last_progress": 990.0, "effects": "NONE",
                 "terminal_receipt": None, "writer_stopped": False,
                 "completion_proof_available": False}
        value.update(changes)
        return value

    def test_watchdog_unknown_effect_precedes_retry(self):
        result = WatchdogClassifier.classify(self.snapshot(effects="UNKNOWN"))
        self.assertEqual("HOLD_UNKNOWN_SIDE_EFFECT", result["state"])
        self.assertFalse(result["automatic_retry"])

    def test_watchdog_completed_requires_full_recovery_chain(self):
        held = WatchdogClassifier.classify(self.snapshot(
            run_status="COMPLETED", native_state="EXITED", writer_stopped=True))
        ready = WatchdogClassifier.classify(self.snapshot(
            run_status="COMPLETED", native_state="EXITED", writer_stopped=True,
            completion_proof_available=True))
        self.assertEqual("COMPLETED_RECOVERY_HOLD", held["state"])
        self.assertEqual("COMPLETED_RECOVERY_READY", ready["state"])
        self.assertEqual("RECONCILE_COMPLETED", ready["next"])

    def test_watchdog_result_missing_and_progress_stalled_are_distinct(self):
        missing = WatchdogClassifier.classify(self.snapshot(native_state="EXITED"))
        stalled = WatchdogClassifier.classify(self.snapshot(progress_deadline=999.0))
        self.assertEqual("RESULT_MISSING", missing["state"])
        self.assertEqual("PROGRESS_STALLED", stalled["state"])

    def test_watchdog_healthy_is_no_action(self):
        result = WatchdogClassifier.classify(self.snapshot())
        self.assertEqual({"state": "HEALTHY", "next": "NONE",
                          "automatic_retry": False}, result)


if __name__ == "__main__":
    unittest.main()
