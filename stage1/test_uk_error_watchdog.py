"""Boundary and fail-closed tests; no network or inference."""
import datetime
import unittest

from uk_error_watchdog import evaluate

NOW = datetime.datetime(2026, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)


def evidence(elapsed, **changes):
    first = NOW - datetime.timedelta(seconds=elapsed)
    base = {
        'schema': 1,
        'ledger_verified': True,
        'task_id': 'XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1',
        'spec_sha256': '1' * 64,
        'failure_sha256': '2' * 64,
        'first_seen_at': first.isoformat(),
        'last_seen_at': NOW.isoformat(),
        'attempt_count': 3,
        'resolved': False,
        'alert30_delivered': False,
        'alert60_delivered': False,
    }
    base.update(changes)
    return base


class WatchdogTests(unittest.TestCase):
    def status(self, elapsed, expected, **changes):
        result = evaluate(evidence(elapsed, **changes), now=NOW)
        self.assertEqual(expected, result['status'])
        self.assertEqual(0, result['model_inference_calls'])
        return result

    def test_29_59_observes(self):
        self.status(1799, 'OBSERVE')

    def test_30_00_alerts_once(self):
        result = self.status(1800, 'ALERT_30M')
        self.assertEqual(1, len(result['notify_owner_keys']))
        self.assertTrue(result['must_assess_alternative'])

    def test_30_alert_delivery_deduplicates(self):
        result = self.status(1800, 'ALERT_30M', alert30_delivered=True)
        self.assertEqual([], result['notify_owner_keys'])

    def test_59_59_still_alert_state(self):
        self.status(3599, 'ALERT_30M')

    def test_60_00_hard_stops_method(self):
        result = self.status(3600, 'HOLD_METHOD_CHANGE_REQUIRED')
        self.assertFalse(result['may_retry_same_method'])
        self.assertEqual(2, len(result['notify_owner_keys']))

    def test_60_delivery_deduplicates_both_milestones(self):
        result = self.status(3600, 'HOLD_METHOD_CHANGE_REQUIRED',
                             alert30_delivered=True, alert60_delivered=True)
        self.assertEqual([], result['notify_owner_keys'])

    def test_keys_are_stable_across_attempt_count_changes(self):
        first = self.status(1800, 'ALERT_30M', attempt_count=2)
        second = self.status(1800, 'ALERT_30M', attempt_count=99)
        self.assertEqual(first['notify_owner_keys'], second['notify_owner_keys'])

    def test_unverified_ledger_fails_closed(self):
        self.status(10, 'HOLD_ERROR_EVIDENCE_INVALID', ledger_verified=False)

    def test_bad_hash_fails_closed(self):
        self.status(10, 'HOLD_ERROR_EVIDENCE_INVALID', failure_sha256='short')

    def test_resolution_requires_evidence(self):
        self.status(4000, 'HOLD_ERROR_EVIDENCE_INVALID', resolved=True)

    def test_evidenced_resolution_closes(self):
        self.status(4000, 'RESOLVED', resolved=True,
                    resolution_evidence_sha256='a' * 64)


if __name__ == '__main__':
    unittest.main()
