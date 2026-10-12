"""Mechanical policy tests. No network, SDK, or inference."""
import datetime
import unittest

from uk_quota_policy import decide

NOW = datetime.datetime(2026, 10, 12, 6, 0, tzinfo=datetime.timezone.utc)

def evidence(**changes):
    base = dict(
        schema=1,
        model='openai/gpt-5.6-sol',
        fallbacks=[],
        observed_at=NOW.isoformat(),
        day='2026-10-12',
        quota_source='AUTHORITATIVE',
        evidence_ref='canonical:meter:20261012:00',
        daily_total_meter_verified=True,
        codex_period_used_pct=20.0,
        daily_total_used_pct=10.0,
        codex_status='AVAILABLE',
        chat_status='UNKNOWN',
        chat_non_codex_verified=False,
        chat_exhaustion_verified=False,
        chat_entrypoint='UNKNOWN',
        chat_evidence_ref='canonical:chat:20261012:00'
    )
    base.update(changes)
    return base

class QuotaPolicyTests(unittest.TestCase):
    def assert_route(self, expected, **kwargs):
        out = decide(evidence(**kwargs), now=NOW)
        self.assertEqual(expected, out['route'])
        self.assertEqual(out['may_infer'], expected != 'NONE')
        self.assertEqual(0, out['gate_inference_calls'])
        return out

    def test_under_30_uses_codex(self):
        self.assertEqual('CODEX_BELOW_30_PERCENT',
                         self.assert_route('CODEX_OAUTH', codex_period_used_pct=29.99)['reason'])

    def test_equal_30_switches_to_real_non_codex_chat(self):
        out = self.assert_route(
            'CHATGPT_NON_CODEX_CHAT', codex_period_used_pct=30,
            chat_status='AVAILABLE', chat_non_codex_verified=True,
            chat_entrypoint='CHATGPT_NON_CODEX_CHAT')
        self.assertEqual('SWITCH_AT_CODEX_30_PERCENT', out['reason'])

    def test_49_99_chat_still_permitted(self):
        self.assert_route('CHATGPT_NON_CODEX_CHAT', codex_period_used_pct=33,
                          daily_total_used_pct=49.99, chat_status='AVAILABLE',
                          chat_non_codex_verified=True, chat_entrypoint='CHATGPT_NON_CODEX_CHAT')

    def test_50_stops_even_non_codex_chat(self):
        out = self.assert_route('NONE', codex_period_used_pct=33,
                                daily_total_used_pct=50,
                                chat_status='AVAILABLE', chat_non_codex_verified=True,
                                chat_entrypoint='CHATGPT_NON_CODEX_CHAT')
        self.assertEqual('DAILY_50_PERCENT_LIMIT', out['reason'])
        self.assertEqual('2026-10-13T00:00:00+08:00', out['resume_not_before'])

    def test_chat_quota_verifiably_exhausted_can_return_to_codex(self):
        out = self.assert_route('CODEX_OAUTH', codex_period_used_pct=55,
                                daily_total_used_pct=48, chat_status='EXHAUSTED',
                                chat_exhaustion_verified=True)
        self.assertEqual('CHAT_EXHAUSTED_CODEX_UNDER_DAILY_CAP', out['reason'])

    def test_chat_error_not_exhaustion(self):
        self.assert_route('NONE', codex_period_used_pct=40, chat_status='ERROR')

    def test_unverified_chat_not_fallback(self):
        self.assert_route('NONE', codex_period_used_pct=30,
                          chat_status='AVAILABLE', chat_non_codex_verified=False,
                          chat_entrypoint='CHATGPT_NON_CODEX_CHAT')

    def test_codex_wrapper_does_not_count_as_non_codex_chat(self):
        self.assert_route('NONE', codex_period_used_pct=30,
                          chat_status='AVAILABLE', chat_non_codex_verified=True,
                          chat_entrypoint='CODEX_APP_SERVER')

    def test_exhaustion_without_evidence_does_not_restore_codex(self):
        self.assert_route('NONE', codex_period_used_pct=30,
                          chat_status='EXHAUSTED', chat_exhaustion_verified=False)

    def test_unknown_codex_below_switch_is_hold(self):
        self.assert_route('NONE', codex_status='UNKNOWN')

    def test_daily_comparison_unknown_holds(self):
        out=self.assert_route('NONE', daily_total_meter_verified=False)
        self.assertEqual('DAILY_TOTAL_NOT_COMPARABLE', out['reason'])

    def test_missing_daily_percent_holds(self):
        self.assert_route('NONE', daily_total_used_pct=None)

    def test_invalid_quota_negative_holds(self):
        self.assert_route('NONE', codex_period_used_pct=-1)

    def test_invalid_model_holds(self):
        self.assert_route('NONE', model='openai/gpt-6.1-sol')

    def test_nonempty_fallback_holds(self):
        self.assert_route('NONE', fallbacks=['astra'])

    def test_stale_evidence_holds(self):
        self.assert_route('NONE', observed_at='2026-10-12T05:49:59+00:00')

    def test_new_day_requires_new_evidence(self):
        self.assert_route('NONE', day='2026-10-11')

    def test_bogus_quota_source_holds(self):
        self.assert_route('NONE', quota_source='INFERRED')

    def test_invalid_timestamp_holds(self):
        self.assert_route('NONE', observed_at='yesterday')

    def test_daily_threshold_takes_precedence_over_switch(self):
        self.assertEqual('DAILY_50_PERCENT_LIMIT',
            self.assert_route('NONE', codex_period_used_pct=80,
                              daily_total_used_pct=51,
                              chat_status='EXHAUSTED', chat_exhaustion_verified=True)['reason'])

if __name__ == '__main__':
    unittest.main()
