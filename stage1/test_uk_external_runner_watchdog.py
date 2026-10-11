"""Pure mechanical tests for external Runner watchdog, no GitHub/network/model calls."""
import datetime
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uk_external_runner_watchdog", str(ROOT / "scripts" / "uk-external-runner-watchdog.py"))
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
T = datetime.datetime(2026, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)


def e(sec, state, attempt="attempt-0001"):
    return T + datetime.timedelta(seconds=sec), {"attempt": attempt, "state": state}


class WatchdogTest(unittest.TestCase):
    def test_receive_threshold(self):
        data = [e(0, "SUBMITTED")]
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(seconds=119)), [])
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(seconds=120)),
                         [("attempt-0001", "RECEIVE_TIMEOUT")])

    def test_start_threshold(self):
        data = [e(0, "SUBMITTED"), e(50, "RECEIVED")]
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(seconds=299)), [])
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(seconds=300)),
                         [("attempt-0001", "START_TIMEOUT")])

    def test_stall_and_terminal(self):
        data = [e(0, "SUBMITTED"), e(30, "RECEIVED"), e(60, "STARTED")]
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(seconds=659)), [])
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(seconds=660)),
                         [("attempt-0001", "STALL_10M")])
        self.assertEqual(MOD.detect(data + [e(661, "HOLD")], set(),
                                    T + datetime.timedelta(seconds=900)), [])

    def test_alert_dedup(self):
        data = [e(0, "SUBMITTED")]
        self.assertEqual(MOD.detect(data, {("attempt-0001", "RECEIVE_TIMEOUT")},
                                    T + datetime.timedelta(seconds=130)), [])

    def test_no_anchor_never_invents_incident(self):
        self.assertEqual(MOD.detect([], set(), T), [])
        self.assertEqual(MOD.detect([e(0, "PROGRESS")], set(),
                                    T + datetime.timedelta(hours=5)), [])

    def test_attempt_isolation(self):
        data = [e(0, "SUBMITTED"), e(120, "COMPLETE"),
                e(125, "SUBMITTED", "attempt-0002")]
        self.assertEqual(MOD.detect(data, set(), T + datetime.timedelta(seconds=245)),
                         [("attempt-0002", "RECEIVE_TIMEOUT")])


if __name__ == "__main__":
    unittest.main()
