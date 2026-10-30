from __future__ import absolute_import

import hashlib
import os
import shutil
import tempfile
import types
import unittest

from src import p3_host_callsite as callsite
from src.p3_host_boundaries import TrustedReceiptProvider


class Provider(TrustedReceiptProvider):
    def read(self, evidence_ref):
        raise AssertionError("receipt read is not part of composition")


class Wiring(object):
    def __init__(self):
        self.calls = 0

    def compose_existing_host(self, *args, **kwargs):
        self.calls += 1
        return "ORIGINAL_LOOP"


class CallsiteTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="p3-callsite-")
        self.old_expected = dict(callsite.EXPECTED_MODULE_SHA256)
        self.modules = {}
        for name in sorted(callsite.EXPECTED_MODULE_SHA256):
            path = os.path.join(self.root, name + ".py")
            with open(path, "wb") as output:
                output.write((name + "\n").encode("ascii"))
            digest = hashlib.sha256((name + "\n").encode("ascii")).hexdigest()
            callsite.EXPECTED_MODULE_SHA256[name] = digest
            self.modules[name] = types.SimpleNamespace(__file__=path)
        self.wiring = Wiring()
        self.modules["p3_host_wiring"] = self.wiring
        # Preserve the fake source path expected by verify_loaded_sources.
        self.wiring.__file__ = os.path.join(self.root, "p3_host_wiring.py")
        self.subject = {
            "task_id": "p3-task", "spec_hash": "1" * 64,
            "artifact": "p3-carrier", "run_id": "run-1",
            "session_id": "session-1", "fence": 3, "epoch": 8,
            "generation": 2, "resume_generation": 1,
        }

    def tearDown(self):
        callsite.EXPECTED_MODULE_SHA256.clear()
        callsite.EXPECTED_MODULE_SHA256.update(self.old_expected)
        shutil.rmtree(self.root)

    def config(self, execution=False, notifications=False):
        return {
            "execution_enabled": execution,
            "notifications_enabled": notifications,
            "task_to_blocker": {"p3-task": "blocker-1"},
            "ratio_bands": ((0, 100, 10),),
            "worker_prefix": "p3-worker",
        }

    def proof(self, p2=True, release=True):
        value = dict(self.subject)
        value.update({
            "p2_accepted": p2, "p3_release_accepted": release,
            "unique_writer": True, "execution_authorized": True,
            "notification_authorized": False, "valid_from": 1,
            "valid_until": 20, "verified": True,
        })
        return value

    def test_default_off_verifies_sources_without_composing_or_reading_gate(self):
        result = callsite.compose_existing_p3_host(
            object(), None, self.config(),
            lambda: (_ for _ in ()).throw(AssertionError("gate read")),
            lambda: 10, modules=self.modules)
        self.assertEqual("PREPARED_DEFAULT_OFF", result["state"])
        self.assertIsNone(result["loop"])
        self.assertEqual(0, self.wiring.calls)

    def test_p2_and_release_are_both_hard_gates_before_composition(self):
        for p2, release in ((False, True), (True, False)):
            with self.assertRaisesRegex(PermissionError,
                                        "FIELD_ADMISSION_NOT_ESTABLISHED"):
                callsite.compose_existing_p3_host(
                    object(), None, self.config(execution=True),
                    lambda p2=p2, release=release: self.proof(p2, release),
                    lambda: 10, subject=self.subject, modules=self.modules)
        self.assertEqual(0, self.wiring.calls)

    def test_admitted_callsite_reuses_existing_host_and_stays_notifications_off(self):
        result = callsite.compose_existing_p3_host(
            object(), object(), self.config(execution=True),
            lambda: self.proof(), lambda: 10,
            progress_subject=lambda ref: self.subject,
            stop_subject=lambda ref: self.subject,
            acceptance_index=lambda task: {}, receipt_provider=Provider(),
            executor=object(), subject=self.subject, modules=self.modules)
        self.assertEqual("COMPOSED_ADMISSION_RECHECKED", result["state"])
        self.assertEqual("ORIGINAL_LOOP", result["loop"])
        self.assertFalse(result["notifications_enabled"])
        self.assertEqual(1, self.wiring.calls)

    def test_loaded_source_hash_mismatch_fails_closed(self):
        with open(self.modules["p3_lifecycle"].__file__, "ab") as output:
            output.write(b"changed")
        with self.assertRaisesRegex(ValueError,
                                    "LOADED_MODULE_SHA256_MISMATCH:p3_lifecycle"):
            callsite.compose_existing_p3_host(
                object(), None, self.config(), lambda: self.proof(),
                lambda: 10, modules=self.modules)


if __name__ == "__main__":
    unittest.main()
