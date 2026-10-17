"""Issue #19 isolated observer regressions; no canonical ledger mutation."""
import copy
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "observer", str(ROOT / "scripts/chatgpt_native_handoff_observer.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def sample():
    return {"task_id": "task-19", "spec_sha256": "a"*64,
            "checkpoint_sha256": "b"*64,
            "target_repository": "owner/control-repo", "target_base_sha": "c"*40,
            "entry": "CHATGPT", "attempt_id": "a1", "state": "STOPPED",
            "writer_stopped": True, "lease_expired": True,
            "effects_reconciled": True, "next_owner_ack": True,
            "last_real_progress_at": 100, "progress_deadline_at": 120,
            "receipt_id": "receipt-1"}

class ObserverTests(unittest.TestCase):
    def test_green_never_grants_writer(self):
        row=mod.project(sample(),110)
        self.assertTrue(row["candidate_handoff_ready"])
        self.assertEqual(row["writer_permission"],"NOT_GRANTED")
        self.assertEqual(row["side_effects"],0)
    def test_old_writer_and_fence_block(self):
        for field in ("writer_stopped","lease_expired","effects_reconciled","next_owner_ack"):
            row=sample();row[field]=None
            self.assertFalse(mod.project(row,110)["candidate_handoff_ready"])
    def test_overdue_not_heartbeat(self):
        row=mod.project(sample(),121)
        self.assertIn("PROGRESS_OVERDUE",row["blockers"])
    def test_unknown_never_passes(self):
        for state in ("HOLD","UNKNOWN"):
            row=sample();row["state"]=state
            self.assertFalse(mod.project(row,110)["candidate_handoff_ready"])
    def test_malformed_hash_rejected(self):
        row=sample();row["checkpoint_sha256"]="wrong"
        with self.assertRaises(mod.HandoffHold):mod.project(row,110)
    def test_duplicate_attempt_rejected(self):
        with self.assertRaises(mod.HandoffHold):
            mod.observe_many([sample(),copy.deepcopy(sample())],110)
    def test_stable_sort_and_hash(self):
        a=sample();b=sample();b["task_id"]="task-20"
        result=mod.observe_many([b,a],110)
        self.assertEqual([x["task_id"] for x in result],["task-19","task-20"])
        self.assertEqual(result,mod.observe_many([b,a],110))
    def test_no_progress_source_fails_closed(self):
        row=sample();row["last_real_progress_at"]=None
        self.assertIn("PROGRESS_DEADLINE_UNKNOWN",mod.project(row,110)["blockers"])

if __name__ == "__main__":
    unittest.main()
