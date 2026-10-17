"""Scoped read-only reporting over the original advertisement event store."""
import unittest
from scripts import community_ad_store as ads
from scripts.community_ad_contract import AMOUNT
import test_community_stage_roles as roles


class AdReport(unittest.TestCase):
    def setUp(self):
        self.db=ads.open_offline()
        self.scope=dict(tenant_id='t',merchant_id='m',store_id='s')
        self.other=dict(self.scope,store_id='other')
        for scope in (self.scope,self.other):
            for cid in ('a','b','c'):
                ads.create_campaign(self.db,scope,dict(id=cid,slot=AMOUNT,starts_at=0,
                    ends_at=1000,title='Fixture',target_url='https://example.org/a',priority=1),
                    dict(authenticated=True,role='PLATFORM_ADMIN',actor_id='reviewer'),0)
    def tearDown(self):self.db.close()
    def report(self,**kwargs):
        return ads.metric_report(self.db,self.scope,100,200,**kwargs)
    def test_half_open_window_duplicates_scope_and_zero_impressions(self):
        for event,kind,at in [('before','CLICK',99),('start','IMPRESSION',100),
                              ('inside','CLICK',150),('end','CLICK',200)]:
            ads.record_metric(self.db,self.scope,AMOUNT,kind,event,'a',at)
        ads.record_metric(self.db,self.scope,AMOUNT,'CLICK','inside','a',151)
        ads.record_metric(self.db,self.other,AMOUNT,'CLICK','other','a',150)
        ads.record_metric(self.db,self.scope,AMOUNT,'CLICK','onlyclick','b',150)
        result=self.report();a,b,c=result['campaigns']
        self.assertEqual((a['impressions'],a['clicks'],a['click_rate']),(1,1,1.0))
        self.assertEqual((b['impressions'],b['clicks'],b['click_rate']),(0,1,None))
        self.assertEqual((c['impressions'],c['clicks']),(0,0))
        self.assertFalse(result['payment_affected'])
        self.assertFalse(result['provider_settlement_verified'])
    def test_pagination_and_read_only(self):
        before=self.db.total_changes
        first=self.report(limit=2)
        self.assertEqual([x['id'] for x in first['campaigns']],['a','b'])
        self.assertEqual(first['next_cursor'],'b')
        last=self.report(limit=2,after_id=first['next_cursor'])
        self.assertEqual([x['id'] for x in last['campaigns']],['c'])
        self.assertFalse(last['has_more']);self.assertIsNone(last['next_cursor'])
        self.assertEqual(before,self.db.total_changes)
    def test_invalid_windows_and_pages(self):
        for start,end in [(True,200),(200,200),(201,200),(-1,200),(0,367*86400)]:
            with self.assertRaises(ValueError):ads.metric_report(self.db,self.scope,start,end)
        for kw in [dict(limit=True),dict(limit=201),dict(after_id="' OR 1=1")]:
            with self.assertRaises(ValueError):self.report(**kw)


class ReportRoles(unittest.TestCase):
    def setUp(self):self.fx=roles.ScopedCommunityRoles();self.fx.setUp()
    def tearDown(self):self.fx.tearDown()
    def test_registered_roles_and_strict_fields(self):
        params=dict(starts_at=0,ends_at=86400,limit=50,after_id='')
        for p in (self.fx.fx.merchant,self.fx.reviewer):
            self.assertIn('campaigns',self.fx.call(p,'ad_report',params))
        for p in (self.fx.staff,self.fx.finance,self.fx.fx.customer):
            with self.assertRaises(PermissionError):self.fx.call(p,'ad_report',params)
        with self.assertRaises(ValueError):self.fx.call(self.fx.fx.merchant,'ad_report',dict(params,store_id='other'))

if __name__=='__main__':unittest.main()
