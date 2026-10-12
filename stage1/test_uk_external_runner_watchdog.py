"""Pure tests for event-started Runner receipt monitor; no network/model calls."""
import datetime
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "watchdog", str(ROOT / "scripts" / "uk-external-runner-watchdog.py"))
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
T = datetime.datetime(2026, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)


def e(sec, state, attempt="attempt-0001"):
    return T + datetime.timedelta(seconds=sec), {"attempt": attempt, "state": state}


class WatchdogTest(unittest.TestCase):
    def test_receive_start_progress_and_terminal_thresholds(self):
        self.assertEqual(MOD.detect([e(0, "SUBMITTED")], set(), T + datetime.timedelta(seconds=120)),
                         [("attempt-0001", "RECEIVE_TIMEOUT_2M")])
        data = [e(0, "SUBMITTED"), e(50, "RECEIVED")]
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(seconds=300)),
                         [("attempt-0001", "START_TIMEOUT_5M")])
        data.append(e(60, "STARTED"))
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(seconds=660)),
                         [("attempt-0001", "PROGRESS_TIMEOUT_10M")])
        self.assertIn(("attempt-0001", "TERMINAL_TIMEOUT_60M"),
                      MOD.detect(data, set(), T + datetime.timedelta(seconds=3600)))

    def test_terminal_and_dedup(self):
        data = [e(0, "SUBMITTED"), e(10, "COMPLETE")]
        self.assertTrue(MOD.is_terminal(data, "attempt-0001"))
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(hours=2)), [])
        self.assertEqual(MOD.detect([e(0, "SUBMITTED")],
                                    {("attempt-0001", "RECEIVE_TIMEOUT_2M")},
                                    T + datetime.timedelta(seconds=130)), [])

    def test_owner_submitted_event_only(self):
        marker = {"task_id": MOD.TASK, "state": "SUBMITTED",
                  "source": "AUTHORIZED_EXECUTION_RECEIPT", "attempt": "attempt-0001"}
        body = "<!-- XJ_GH_TASK_EVENT " + __import__("json").dumps(marker) + " -->"
        event = {"action": "created", "issue": {"number": 17},
                 "sender": {"login": MOD.OWNER},
                 "comment": {"user": {"login": MOD.OWNER}, "body": body}}
        self.assertEqual(MOD.submitted_attempt(event), "attempt-0001")
        event["sender"]["login"] = "untrusted"
        self.assertIsNone(MOD.submitted_attempt(event))

    def test_parse_ignores_untrusted_receipt(self):
        marker = {"task_id": MOD.TASK, "state": "COMPLETE",
                  "source": "AUTHORIZED_EXECUTION_RECEIPT", "attempt": "attempt-0001"}
        comment = {"created_at": "2026-10-12T00:00:00Z",
                   "user": {"login": "untrusted"},
                   "body": "<!-- XJ_GH_TASK_EVENT " + __import__("json").dumps(marker) + " -->"}
        self.assertEqual(MOD.parse([comment]), ([], set()))


if __name__ == "__main__":
    unittest.main()
