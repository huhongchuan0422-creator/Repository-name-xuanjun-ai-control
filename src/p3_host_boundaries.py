"""P3 host boundary candidate; inert unless explicit field admission is supplied.

This module contains no runner/provider implementation, service entry point, DB
bootstrap, scheduler, network client, credential loader, or retry loop.  It is an
additive boundary for the frozen P3 core and host-wiring successor.
"""
from __future__ import absolute_import

import abc
import hashlib
import json
import math
import re


HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
RUN_SUBJECT_KEYS = {
    "task_id", "spec_hash", "artifact", "run_id", "session_id", "fence",
    "epoch", "generation", "resume_generation"
}
RECEIPT_KEYS = {
    "schema", "provider", "receipt_id", "receipt_sha256", "kind", "subject",
    "payload", "observed_at", "verified"
}


def _packed(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _digest(value):
    return hashlib.sha256(_packed(value).encode("utf-8")).hexdigest()


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _exact(value, keys, error):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(error)
    return value


def _subject(value):
    _exact(value, RUN_SUBJECT_KEYS, "EXACT_RUN_SUBJECT_REQUIRED")
    if (not _text(value["task_id"]) or not HEX64.match(value["spec_hash"] or "")
            or not _text(value["artifact"]) or not _text(value["run_id"])
            or not _text(value["session_id"]) or type(value["fence"]) is not int
            or value["fence"] < 1 or type(value["epoch"]) is not int
            or value["epoch"] < 0 or type(value["generation"]) is not int
            or value["generation"] < 0
            or type(value["resume_generation"]) is not int
            or value["resume_generation"] < 0):
        raise ValueError("VALID_RUN_SUBJECT_REQUIRED")
    return value


def seal_receipt(provider, receipt_id, kind, subject, payload, observed_at):
    """Test/integration helper. Trust still comes from the injected provider."""
    value = {
        "schema": 1, "provider": provider, "receipt_id": receipt_id,
        "kind": kind, "subject": dict(subject), "payload": dict(payload),
        "observed_at": observed_at, "verified": True
    }
    value["receipt_sha256"] = _digest(value)
    return value


class TrustedReceiptProvider(object, metaclass=abc.ABCMeta):
    """Host-owned authenticated immutable receipt lookup.

    Implementations must retrieve already persisted evidence by opaque reference.
    They must not derive trust from request booleans or create evidence on read.
    """
    @abc.abstractmethod
    def read(self, evidence_ref):
        raise NotImplementedError


class RunnerAdapter(object, metaclass=abc.ABCMeta):
    """Approved native runner boundary. Each method returns an evidence ref."""
    @abc.abstractmethod
    def launch(self, admission):
        raise NotImplementedError

    @abc.abstractmethod
    def resume(self, admission):
        raise NotImplementedError

    @abc.abstractmethod
    def inspect(self, subject):
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self, subject, reason):
        raise NotImplementedError


class OutboxTransport(object, metaclass=abc.ABCMeta):
    """Existing approved transport; no provider or credentials are included."""
    @abc.abstractmethod
    def send(self, envelope):
        raise NotImplementedError

    @abc.abstractmethod
    def lookup(self, binding, opaque_notification_id, attempt_nonce):
        raise NotImplementedError

    @abc.abstractmethod
    def ack(self, delivery_receipt_id):
        raise NotImplementedError


class AdmissionGate(object):
    """Rechecks P2/P3/Writer authority before every possible side effect."""
    KEYS = {
        "p2_accepted", "p3_release_accepted", "unique_writer", "task_id",
        "spec_hash", "artifact", "run_id", "session_id", "fence", "epoch",
        "generation", "resume_generation", "execution_authorized",
        "notification_authorized", "valid_from", "valid_until", "verified"
    }

    def __init__(self, reader, clock, execution_enabled=False,
                 notifications_enabled=False):
        if type(execution_enabled) is not bool or type(notifications_enabled) is not bool:
            raise ValueError("BOOLEAN_ENABLE_REQUIRED")
        if notifications_enabled and not execution_enabled:
            raise ValueError("EXECUTION_ADMISSION_REQUIRED")
        self.reader = reader
        self.clock = clock
        self.execution_enabled = execution_enabled
        self.notifications_enabled = notifications_enabled

    def check(self, subject, notifications=False):
        _subject(subject)
        if not self.execution_enabled:
            raise PermissionError("P3_DEFAULT_OFF")
        if notifications and not self.notifications_enabled:
            raise PermissionError("P3_NOTIFICATIONS_DEFAULT_OFF")
        if not callable(self.reader):
            raise PermissionError("FIELD_ADMISSION_READER_UNAVAILABLE")
        try:
            proof = self.reader()
        except Exception:
            raise PermissionError("FIELD_ADMISSION_UNKNOWN")
        _exact(proof, self.KEYS, "EXACT_FIELD_ADMISSION_REQUIRED")
        now = self.clock()
        if (proof["verified"] is not True
                or any(proof[k] is not True for k in
                       ("p2_accepted", "p3_release_accepted", "unique_writer",
                        "execution_authorized"))
                or (notifications and proof["notification_authorized"] is not True)
                or type(proof["notification_authorized"]) is not bool
                or any(proof[k] != subject[k] for k in RUN_SUBJECT_KEYS)
                or not _finite(proof["valid_from"])
                or not _finite(proof["valid_until"])
                or not proof["valid_from"] <= now < proof["valid_until"]):
            raise PermissionError("FIELD_ADMISSION_NOT_ESTABLISHED")
        return proof


class ReceiptVerifier(object):
    def __init__(self, provider):
        if not isinstance(provider, TrustedReceiptProvider):
            raise TypeError("TRUSTED_RECEIPT_PROVIDER_REQUIRED")
        self.provider = provider

    def read(self, evidence_ref, kind, subject):
        if not _text(evidence_ref):
            raise ValueError("OPAQUE_EVIDENCE_REF_REQUIRED")
        _subject(subject)
        value = self.provider.read(evidence_ref)
        _exact(value, RECEIPT_KEYS, "EXACT_RECEIPT_ENVELOPE_REQUIRED")
        unsigned = dict(value)
        claimed = unsigned.pop("receipt_sha256")
        if (value["schema"] != 1 or value["verified"] is not True
                or not _text(value["provider"]) or not _text(value["receipt_id"])
                or value["kind"] != kind or value["subject"] != subject
                or not _finite(value["observed_at"])
                or not isinstance(value["payload"], dict)
                or not HEX64.match(claimed or "") or _digest(unsigned) != claimed):
            raise ValueError("RECEIPT_NOT_VERIFIED_OR_BOUND")
        return value


class EvidenceReaders(object):
    """Readers with the exact shapes consumed by the frozen P3 core."""
    ACCEPTANCE_INDEX_KEYS = {
        "subject", "checkpoint_sha256", "commit", "artifact_sha256", "scope",
        "author", "terminal", "tests", "ci", "qa", "security", "business"
    }

    def __init__(self, verifier, progress_subject, stop_subject,
                 acceptance_index, completion_index=None):
        self.verifier = verifier
        self.progress_subject = progress_subject
        self.stop_subject = stop_subject
        self.acceptance_index = acceptance_index
        self.completion_index = completion_index

    def progress(self, evidence_ref):
        subject = self.progress_subject(evidence_ref)
        receipt = self.verifier.read(evidence_ref, "PROGRESS", subject)
        payload = _exact(receipt["payload"], {"kind", "sha256"},
                         "EXACT_PROGRESS_PAYLOAD_REQUIRED")
        if payload["kind"] not in ("SOURCE_COMMIT", "TEST_RUN", "ARTIFACT") \
                or not HEX64.match(payload["sha256"] or ""):
            raise ValueError("REAL_PROGRESS_NOT_VERIFIED")
        return {"task_id": subject["task_id"], "spec_hash": subject["spec_hash"],
                "fence": subject["fence"], "kind": payload["kind"],
                "sha256": payload["sha256"], "verified": True}

    def stop(self, evidence_ref):
        subject = self.stop_subject(evidence_ref)
        receipt = self.verifier.read(evidence_ref, "STOP", subject)
        payload = _exact(receipt["payload"], {
            "writer_stopped", "descendants_stopped", "effects",
            "checkpoint_sha256", "authority_verified"
        }, "EXACT_STOP_PAYLOAD_REQUIRED")
        if (payload["writer_stopped"] is not True
                or payload["descendants_stopped"] is not True
                or payload["effects"] not in ("NONE", "KNOWN")
                or not HEX64.match(payload["checkpoint_sha256"] or "")
                or payload["authority_verified"] is not True):
            raise ValueError("STOP_EFFECTS_NOT_RECONCILED")
        result = dict(payload)
        result.update({"task_id": subject["task_id"],
                       "spec_hash": subject["spec_hash"],
                       "fence": subject["fence"], "epoch": subject["epoch"],
                       "run_id": subject["run_id"],
                       "session_id": subject["session_id"],
                       "resume_generation": subject["resume_generation"],
                       "receipt_sha256": receipt["receipt_sha256"]})
        return result

    def _acceptance(self, task_id):
        if not callable(self.acceptance_index):
            raise ValueError("ACCEPTANCE_INDEX_UNAVAILABLE")
        index = self.acceptance_index(task_id)
        _exact(index, self.ACCEPTANCE_INDEX_KEYS,
               "EXACT_ACCEPTANCE_INDEX_REQUIRED")
        subject = _subject(index["subject"])
        if subject["task_id"] != task_id:
            raise ValueError("ACCEPTANCE_TASK_MISMATCH")
        if (not HEX64.match(index["checkpoint_sha256"] or "")
                or not HEX40.match(index["commit"] or "")
                or not HEX64.match(index["artifact_sha256"] or "")
                or index["scope"] not in ("LOCAL_INTEGRATION", "FIELD")
                or not _text(index["author"])):
            raise ValueError("ACCEPTANCE_IDENTITY_INVALID")
        terminal = self.verifier.read(index["terminal"], "TERMINAL", subject)
        terminal_payload = _exact(terminal["payload"], {
            "terminal_receipt", "effects", "writer_stopped"
        }, "EXACT_TERMINAL_PAYLOAD_REQUIRED")
        if (not _text(terminal_payload["terminal_receipt"])
                or terminal_payload["effects"] not in ("NONE", "KNOWN")
                or terminal_payload["writer_stopped"] is not True):
            raise ValueError("TERMINAL_RECEIPT_INVALID")
        proof = {
            "task_id": task_id, "spec_hash": subject["spec_hash"],
            "fence": subject["fence"],
            "checkpoint_sha256": index["checkpoint_sha256"],
            "commit": index["commit"],
            "artifact_sha256": index["artifact_sha256"],
            "terminal_receipt": terminal_payload["terminal_receipt"],
            "effects": terminal_payload["effects"], "writer_stopped": True,
            "scope": index["scope"], "authority_verified": True,
            "author": index["author"]
        }
        for role in ("tests", "ci", "qa", "security", "business"):
            receipt = self.verifier.read(index[role], role.upper(), subject)
            payload = _exact(receipt["payload"], {
                "status", "commit", "artifact_sha256", "actor"
            }, "EXACT_%s_PAYLOAD_REQUIRED" % role.upper())
            if (payload["status"] != "PASS" or payload["commit"] != index["commit"]
                    or payload["artifact_sha256"] != index["artifact_sha256"]
                    or not _text(payload["actor"])):
                raise ValueError("SAME_ARTIFACT_%s_REQUIRED" % role.upper())
            proof[role] = {"status": "PASS", "commit": payload["commit"],
                           "artifact_sha256": payload["artifact_sha256"],
                           "receipt_sha256": receipt["receipt_sha256"],
                           "actor": payload["actor"]}
        if len({proof["author"], proof["qa"]["actor"],
                proof["security"]["actor"]}) != 3:
            raise ValueError("INDEPENDENT_REVIEW_REQUIRED")
        return proof, subject

    def acceptance(self, task_id):
        proof, _ = self._acceptance(task_id)
        return proof

    def completion(self, task_id):
        """Full frozen reconcile_completed input, including current lineage."""
        proof, acceptance_subject = self._acceptance(task_id)
        if not callable(self.completion_index):
            raise ValueError("COMPLETION_RECOVERY_INDEX_UNAVAILABLE")
        value = self.completion_index(task_id)
        _exact(value, {"subject", "evidence_ref"},
               "EXACT_COMPLETION_INDEX_REQUIRED")
        subject = _subject(value["subject"])
        if subject["task_id"] != task_id:
            raise ValueError("COMPLETION_TASK_MISMATCH")
        if any(subject[key] != acceptance_subject[key]
               for key in RUN_SUBJECT_KEYS):
            raise ValueError("COMPLETION_ACCEPTANCE_LINEAGE_MISMATCH")
        receipt = self.verifier.read(value["evidence_ref"],
                                     "RECOVERY_LINEAGE", subject)
        payload = _exact(receipt["payload"], {
            "current_fence", "run_id", "session_id", "resume_generation",
            "epoch", "generation"
        }, "EXACT_COMPLETION_LINEAGE_REQUIRED")
        if (type(payload["current_fence"]) is not int
                or payload["run_id"] != subject["run_id"]
                or payload["session_id"] != subject["session_id"]
                or payload["resume_generation"] != subject["resume_generation"]
                or payload["epoch"] != subject["epoch"]
                or payload["generation"] != subject["generation"]):
            raise ValueError("COMPLETION_LINEAGE_CHANGED")
        proof["recovery"] = dict(payload)
        return proof


class RunnerController(object):
    """No automatic retry: unknown launch/resume/stop effects become HOLD."""
    ACK_PAYLOAD_KEYS = {"operation", "accepted", "started", "native_id"}

    def __init__(self, gate, verifier, adapter):
        if not isinstance(gate, AdmissionGate):
            raise TypeError("ADMISSION_GATE_REQUIRED")
        if not isinstance(verifier, ReceiptVerifier):
            raise TypeError("RECEIPT_VERIFIER_REQUIRED")
        if not isinstance(adapter, RunnerAdapter):
            raise TypeError("RUNNER_ADAPTER_REQUIRED")
        self.gate, self.verifier, self.adapter = gate, verifier, adapter

    def _invoke(self, operation, subject, admission):
        self.gate.check(subject)
        try:
            evidence_ref = getattr(self.adapter, operation)(admission)
        except Exception:
            return {"state": "UNKNOWN_RUNNER_EFFECT_HOLD", "operation": operation,
                    "automatic_retry": False, "started": False}
        try:
            receipt = self.verifier.read(evidence_ref, "RUNNER_ACK", subject)
            payload = _exact(receipt["payload"], self.ACK_PAYLOAD_KEYS,
                             "EXACT_RUNNER_ACK_REQUIRED")
            if (payload["operation"] != operation
                    or payload["accepted"] is not True
                    or payload["started"] is not False
                    or not _text(payload["native_id"])):
                raise ValueError("ACK_IS_NOT_STARTED")
        except Exception:
            return {"state": "UNKNOWN_RUNNER_EFFECT_HOLD", "operation": operation,
                    "automatic_retry": False, "started": False}
        return {"state": "ACKNOWLEDGED_AWAITING_STARTED",
                "operation": operation, "started": False,
                "receipt_sha256": receipt["receipt_sha256"],
                "automatic_retry": False}

    def launch(self, subject, admission):
        return self._invoke("launch", subject, admission)

    def resume(self, subject, admission, validate_launch):
        self.gate.check(subject)
        if not callable(validate_launch) or validate_launch(admission) is not True:
            raise ValueError("CURRENT_RESUME_ADMISSION_REQUIRED")
        return self._invoke("resume", subject, admission)

    def accept_started(self, subject, evidence_ref, supervisor):
        self.gate.check(subject)
        receipt = self.verifier.read(evidence_ref, "STARTED", subject)
        payload = _exact(receipt["payload"], {
            "native_state", "lease_owner", "lease_until", "fence",
            "checkpoint", "start_receipt"
        }, "EXACT_STARTED_PAYLOAD_REQUIRED")
        if payload["fence"] != subject["fence"]:
            raise ValueError("STARTED_FENCE_MISMATCH")
        if not callable(getattr(supervisor, "accept_started", None)):
            raise TypeError("ORIGINAL_SUPERVISOR_REQUIRED")
        return supervisor.accept_started(
            subject["task_id"], payload["native_state"], payload["lease_owner"],
            payload["lease_until"], payload["fence"], payload["checkpoint"],
            payload["start_receipt"])

    def inspect(self, subject):
        self.gate.check(subject)
        try:
            ref = self.adapter.inspect(dict(subject))
        except Exception:
            return {"state": "UNKNOWN", "automatic_action": "NONE"}
        receipt = self.verifier.read(ref, "RUNNER_INSPECT", subject)
        payload = _exact(receipt["payload"], {
            "native_state", "terminal_receipt", "effects", "writer_stopped",
            "descendants_stopped"
        }, "EXACT_RUNNER_INSPECT_REQUIRED")
        if payload["effects"] not in ("NONE", "KNOWN", "UNKNOWN"):
            raise ValueError("INVALID_EFFECT_STATE")
        return dict(payload, receipt_sha256=receipt["receipt_sha256"])

    def stop(self, subject, reason):
        self.gate.check(subject)
        if not _text(reason):
            raise ValueError("STOP_REASON_REQUIRED")
        try:
            ref = self.adapter.stop(dict(subject), reason)
        except Exception:
            return {"state": "UNKNOWN_STOP_EFFECT_HOLD", "automatic_retry": False}
        receipt = self.verifier.read(ref, "RUNNER_STOP", subject)
        payload = _exact(receipt["payload"], {
            "writer_stopped", "descendants_stopped", "effects"
        }, "EXACT_RUNNER_STOP_REQUIRED")
        if (payload["writer_stopped"] is not True
                or payload["descendants_stopped"] is not True
                or payload["effects"] not in ("NONE", "KNOWN")):
            raise ValueError("STOP_NOT_RECONCILED")
        return dict(payload, state="STOPPED_RECONCILIATION_REQUIRED",
                    receipt_sha256=receipt["receipt_sha256"],
                    automatic_retry=False)


class OutboxController(object):
    """Separates send, lookup and provider ACK; it never mutates the ledger."""
    def __init__(self, gate, verifier, transport):
        if not isinstance(transport, OutboxTransport):
            raise TypeError("OUTBOX_TRANSPORT_REQUIRED")
        self.gate, self.verifier, self.transport = gate, verifier, transport

    def send(self, subject, envelope):
        self.gate.check(subject, notifications=True)
        try:
            ref = self.transport.send(dict(envelope))
        except Exception:
            return {"state": "UNKNOWN_NO_REDIAL", "automatic_retry": False}
        try:
            receipt = self.verifier.read(ref, "OUTBOX_SEND", subject)
            payload = _exact(receipt["payload"], {
                "binding", "opaque_notification_id", "attempt_nonce", "state",
                "delivery_receipt_id"
            }, "EXACT_OUTBOX_SEND_REQUIRED")
            if payload["state"] not in ("SENT", "UNKNOWN"):
                raise ValueError("INVALID_SEND_RESULT")
        except Exception:
            return {"state": "UNKNOWN_NO_REDIAL", "automatic_retry": False}
        return dict(payload, receipt_sha256=receipt["receipt_sha256"],
                    automatic_retry=False)

    def lookup(self, subject, binding, opaque_notification_id, attempt_nonce):
        self.gate.check(subject, notifications=True)
        try:
            ref = self.transport.lookup(binding, opaque_notification_id, attempt_nonce)
        except Exception:
            return {"state": "UNKNOWN_NO_REDIAL", "automatic_retry": False}
        receipt = self.verifier.read(ref, "OUTBOX_LOOKUP", subject)
        payload = _exact(receipt["payload"], {
            "binding", "opaque_notification_id", "attempt_nonce", "state",
            "delivery_receipt_id", "absence_proof_id"
        }, "EXACT_OUTBOX_LOOKUP_REQUIRED")
        if (payload["binding"] != binding
                or payload["opaque_notification_id"] != opaque_notification_id
                or payload["attempt_nonce"] != attempt_nonce
                or payload["state"] not in ("SENT", "NOT_SENT", "UNKNOWN")):
            raise ValueError("LOOKUP_NOT_BOUND_TO_ORIGINAL_ATTEMPT")
        if payload["state"] == "SENT" and not _text(payload["delivery_receipt_id"]):
            raise ValueError("SENT_RECEIPT_REQUIRED")
        if payload["state"] == "NOT_SENT" and not _text(payload["absence_proof_id"]):
            raise ValueError("NOT_SENT_PROOF_REQUIRED")
        return dict(payload, receipt_sha256=receipt["receipt_sha256"],
                    automatic_retry=False)

    def ack(self, subject, delivery_receipt_id):
        self.gate.check(subject, notifications=True)
        if not _text(delivery_receipt_id):
            raise ValueError("DELIVERY_RECEIPT_ID_REQUIRED")
        try:
            ref = self.transport.ack(delivery_receipt_id)
        except Exception:
            return {"state": "ACK_UNKNOWN_HOLD", "automatic_retry": False}
        receipt = self.verifier.read(ref, "OUTBOX_ACK", subject)
        payload = _exact(receipt["payload"], {"delivery_receipt_id", "acked"},
                         "EXACT_OUTBOX_ACK_REQUIRED")
        if payload["delivery_receipt_id"] != delivery_receipt_id \
                or payload["acked"] is not True:
            raise ValueError("OUTBOX_ACK_NOT_BOUND")
        return {"state": "ACK_VERIFIED", "receipt_sha256": receipt["receipt_sha256"],
                "automatic_retry": False}


class WatchdogClassifier(object):
    """Pure classification only; the original ledger performs all transitions."""
    KEYS = {
        "task_state", "run_status", "native_state", "lease_live",
        "start_deadline", "progress_deadline", "result_deadline", "now",
        "last_progress", "effects", "terminal_receipt", "writer_stopped",
        "completion_proof_available"
    }

    @classmethod
    def classify(cls, snapshot):
        _exact(snapshot, cls.KEYS, "EXACT_WATCHDOG_SNAPSHOT_REQUIRED")
        if any(not _finite(snapshot[k]) for k in
               ("start_deadline", "progress_deadline", "result_deadline", "now")):
            raise ValueError("FINITE_WATCHDOG_DEADLINES_REQUIRED")
        if snapshot["effects"] not in ("NONE", "KNOWN", "UNKNOWN"):
            raise ValueError("INVALID_EFFECT_STATE")
        if snapshot["effects"] == "UNKNOWN":
            return {"state": "HOLD_UNKNOWN_SIDE_EFFECT", "next": "RECONCILE_EFFECT",
                    "automatic_retry": False}
        if snapshot["run_status"] == "COMPLETED" or snapshot["terminal_receipt"]:
            if snapshot["completion_proof_available"] is True and snapshot["writer_stopped"] is True:
                return {"state": "COMPLETED_RECOVERY_READY", "next": "RECONCILE_COMPLETED",
                        "automatic_retry": False}
            return {"state": "COMPLETED_RECOVERY_HOLD", "next": "READ_ACCEPTANCE_AND_STOP",
                    "automatic_retry": False}
        if snapshot["native_state"] in ("EXITED", "FAILED", "STOPPED"):
            return {"state": "RESULT_MISSING", "next": "INSPECT_ORIGINAL_RUN",
                    "automatic_retry": False}
        now = snapshot["now"]
        if snapshot["run_status"] == "DISPATCHED" and now >= snapshot["start_deadline"]:
            return {"state": "START_ACK_TIMEOUT", "next": "INSPECT_THEN_STOP_OR_HOLD",
                    "automatic_retry": False}
        if snapshot["task_state"] == "RUNNING" and snapshot["lease_live"] is not True:
            return {"state": "LEASE_STALLED", "next": "INSPECT_WRITER",
                    "automatic_retry": False}
        if snapshot["task_state"] == "RUNNING" and now >= snapshot["result_deadline"]:
            return {"state": "RESULT_TIMEOUT", "next": "INSPECT_WRITER",
                    "automatic_retry": False}
        if snapshot["task_state"] == "RUNNING" and now >= snapshot["progress_deadline"]:
            return {"state": "PROGRESS_STALLED", "next": "INSPECT_PROGRESS_AND_WRITER",
                    "automatic_retry": False}
        return {"state": "HEALTHY", "next": "NONE", "automatic_retry": False}
