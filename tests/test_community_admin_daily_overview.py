import tempfile
import unittest
import sqlite3
import json
from types import SimpleNamespace
from unittest.mock import patch

from scripts.community_admin_management import _daily_overview
from scripts.community_ad_store import open_offline
from scripts.community_order_store import connect
from scripts.pr122_customer_core import Center, canonical


class DailyOverviewTests(unittest.TestCase):
    def test_project_scoped_daily_terminal_records(self):
        with tempfile.TemporaryDirectory() as directory:
            original_connect = sqlite3.connect
            with patch('scripts.pr122_customer_core.sqlite3.connect',
                       side_effect=lambda path, *args, **kwargs: original_connect(str(path), *args, **kwargs)):
                center = Center(directory + '/identity', {'k': b'x' * 32}, 'k', clock=lambda: 1000)
            order_db = connect()
            ad_db = open_offline()
            try:
                split = dict(kind='SPLIT', at=1000, result=dict(status='FINISHED', receivers=[
                    dict(result='SUCCESS', amount_minor=120), dict(result='CLOSED', amount_minor=30)]))
                refund = dict(kind='REFUND', at=1000, result=dict(status='SUCCESS', amount_minor=45))
                pending = dict(kind='SPLIT', at=1000, result=dict(status='PROCESSING', receivers=[
                    dict(result='SUCCESS', amount_minor=999)]))
                center.db.execute("CREATE TABLE onboarding (tenant TEXT NOT NULL, application TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, reviewer_note TEXT, PRIMARY KEY(tenant,application))")
                center.db.execute("INSERT INTO onboarding VALUES('t','a1',1,'SUBMITTED','{}',NULL)")
                with center.tx():
                    for key, value in [('s1', split), ('r1', refund), ('s2', pending)]:
                        center.db.execute("INSERT INTO links VALUES('COMMUNITY_PROVIDER_ACTION',?,'root','p',?,1)",
                                          (key, center.encrypt(canonical(value), 'provider-action:' + key)))
                order_db.execute("INSERT INTO orders VALUES('t','m','s','o1',1234,'CNY','SUCCESS','123')")
                evidence = json.dumps(dict(source='WECHAT_SIGNED_PAYMENT_NOTIFICATION', body_sha256='a'*64,
                                           transaction_id='123', provider_state='SUCCESS', observed_at=1000))
                paid_time = json.dumps(dict(source='WECHAT_SIGNED_PAYMENT_TIME', paid_at=1000,
                                            transaction_id='123', body_sha256='a'*64))
                order_db.execute("INSERT INTO order_events VALUES('e1','t','m','s','o1','PENDING','SUCCESS',?)", (evidence,))
                order_db.execute("INSERT INTO order_events VALUES('e2','t','m','s','o1','SUCCESS','SUCCESS',?)", (paid_time,))
                ad_db.execute("INSERT INTO campaigns VALUES('t','m','s','ad1','AD_SLOT_PAYMENT_AMOUNT','ACTIVE','APPROVED',10,900,1100,'Ad','https://example.com/ad',1)")
                ad_db.execute("INSERT INTO metric_events VALUES('t','m','s','AD_SLOT_PAYMENT_AMOUNT','IMPRESSION','view1','ad1',1000)")
                ad_db.execute("INSERT INTO metric_events VALUES('t','m','s','AD_SLOT_PAYMENT_AMOUNT','CLICK','click1','ad1',1000)")
                scope = dict(tenant_id='t', merchant_id='m', store_id='s')
                operations = SimpleNamespace(center=center, grants={'w': dict(project='p', tenant='t', scope=scope)},
                                             runtime=SimpleNamespace(demo=SimpleNamespace(db=order_db, ad_db=ad_db)))
                result = _daily_overview(center, 'p', 't', operations)
                self.assertEqual({key: result[key] for key in (
                    'day_start', 'timezone', 'pending_merchant_count', 'transaction_count',
                    'transaction_amount_minor', 'ad_impression_count', 'ad_click_count',
                    'active_ad_count', 'completed_split_minor', 'completed_split_count',
                    'confirmed_refund_minor', 'confirmed_refund_count', 'currency', 'finance_status')}, dict(
                    day_start=-28800, timezone='Asia/Shanghai', pending_merchant_count=1,
                    transaction_count=1, transaction_amount_minor=1234,
                    ad_impression_count=1, ad_click_count=1, active_ad_count=1,
                    completed_split_minor=120, completed_split_count=1, confirmed_refund_minor=45,
                    confirmed_refund_count=1, currency='CNY', finance_status='UNCONFIRMED'))
                self.assertEqual(len(result['daily_series']), 7)
                self.assertEqual(result['daily_series'][-1], dict(
                    day_start=-28800, transaction_count=1, transaction_amount_minor=1234,
                    completed_split_minor=120, confirmed_refund_minor=45,
                    ad_impression_count=1, ad_click_count=1))
                other = _daily_overview(center, 'other', 'other', operations)
                self.assertIsNone(other['transaction_count'])
                self.assertTrue(all(item['transaction_count'] is None for item in other['daily_series']))
            finally:
                ad_db.close()
                order_db.close()
                center.db.close()

    def test_core_only_host_reports_unread_metrics_as_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            original_connect = sqlite3.connect
            with patch('scripts.pr122_customer_core.sqlite3.connect',
                       side_effect=lambda path, *args, **kwargs: original_connect(str(path), *args, **kwargs)):
                center = Center(directory + '/identity', {'k': b'x' * 32}, 'k', clock=lambda: 1000)
            order_db = connect()
            ad_db = open_offline()
            try:
                operations = SimpleNamespace(center=center, grants={},
                    runtime=SimpleNamespace(demo=SimpleNamespace(db=order_db, ad_db=ad_db)))
                result = _daily_overview(center, 'p', 't', operations)
                for key in ('pending_merchant_count','transaction_count','transaction_amount_minor',
                            'ad_impression_count','ad_click_count','active_ad_count'):
                    self.assertIsNone(result[key])
                self.assertTrue(all(item['transaction_count'] is None and
                                    item['ad_impression_count'] is None
                                    for item in result['daily_series']))
            finally:
                ad_db.close()
                order_db.close()
                center.db.close()


if __name__ == '__main__':
    unittest.main()
