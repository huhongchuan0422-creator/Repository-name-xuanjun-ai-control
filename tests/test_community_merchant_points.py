import contextlib
import sqlite3
import hashlib
import json
import unittest
from scripts.community_merchant_points import MerchantPoints
from scripts.community_admin_route_inventory import BUSINESS_CAPABILITIES


class Center:
    def __init__(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE links(channel TEXT,subject_idx TEXT,user_id TEXT,project TEXT,payload BLOB,active INTEGER,PRIMARY KEY(channel,subject_idx,project))')
        self.now_value=1000000;self.audits=[]
    def encrypt(self,value,purpose):return value
    def decrypt(self,value,purpose):return value
    def now(self):return self.now_value
    @contextlib.contextmanager
    def tx(self):
        with self.db:yield
    def audit(self,*args):self.audits.append(args)


class MerchantPointsTests(unittest.TestCase):
    def setUp(self):
        self.c=Center();self.p=MerchantPoints(self.c)
        self.g=dict(scope=dict(tenant_id='tenant',merchant_id='merchant',store_id='store'),project='project',user_id='owner')
    def test_points_do_not_change_initialized_admin_capability_manifest(self):
        self.assertFalse(any('#community.points_' in capability for capability in BUSINESS_CAPABILITIES))
    def test_verified_split_awards_once_and_setting_is_bounded(self):
        saved=dict(reference='order1',provider_reference='provider1')
        result=dict(status='FINISHED',receivers=[dict(result='SUCCESS',amount_minor=123),dict(result='CLOSED',amount_minor=50)])
        with self.c.tx():self.p.record_split(self.g,'split1',saved,result)
        with self.c.tx():self.p.record_split(self.g,'split1',saved,result)
        summary=self.p.dispatch(self.g,'community.points_summary',{})
        self.assertEqual((summary['available_points'],summary['cash_value_minor'],summary['total_earned_points']),(12,120,12))
        updated=self.p.dispatch(self.g,'community.points_setting_save',dict(redemption_percent=30,expected_revision=1))
        self.assertEqual((updated['redemption_percent'],updated['revision']),(30,2))
    def test_points_records_are_real_persisted_events_not_synthetic_totals(self):
        with self.c.tx():self.p.record_split(self.g,'split1',dict(reference='order1',provider_reference='provider1'),dict(status='FINISHED',receivers=[dict(result='SUCCESS',amount_minor=1000)]))
        self.p.dispatch(self.g,'community.points_setting_save',dict(redemption_percent=20,expected_revision=1))
        self.c.now_value+=1
        self.p.dispatch(self.g,'community.points_redeem',dict(request_id='redeem1',purpose='CHARITY_MALL',order_amount_minor=1000,points=10))
        records=self.p.dispatch(self.g,'community.points_records',{})['records']
        self.assertEqual([(r['id'],r['type'],r['reference']) for r in records],[('redeem1','REDEEM','redeem1'),('split1','EARN','order1')])
    def test_pending_split_no_points_and_redeem_limit(self):
        with self.c.tx():self.p.record_split(self.g,'split0',dict(reference='order0',provider_reference='provider0'),dict(status='PROCESSING',receivers=[]))
        self.assertEqual(self.p.dispatch(self.g,'community.points_summary',{})['available_points'],0)
        with self.c.tx():self.p.record_split(self.g,'split1',dict(reference='order1',provider_reference='provider1'),dict(status='FINISHED',receivers=[dict(result='SUCCESS',amount_minor=1000)]))
        self.p.dispatch(self.g,'community.points_setting_save',dict(redemption_percent=20,expected_revision=1))
        redeemed=self.p.dispatch(self.g,'community.points_redeem',dict(request_id='redeem1',purpose='CHARITY_MALL',order_amount_minor=1000,points=20))
        self.assertEqual(redeemed['cash_offset_minor'],200)
        self.assertEqual(self.p.dispatch(self.g,'community.points_summary',{})['available_points'],80)
        with self.assertRaises(ValueError):self.p.dispatch(self.g,'community.points_redeem',dict(request_id='redeem2',purpose='ALLIANCE_MERCHANT',order_amount_minor=1000,points=21))
    def test_approved_application_percent_is_immutable_and_snapshotted_on_order(self):
        key=hashlib.sha256(json.dumps(self.g['scope'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        opening=json.dumps(dict(workspace='merchant',scope=self.g['scope'],project=self.g['project'],revision=7,state='OPENED',preserve_profile=False),ensure_ascii=False,sort_keys=True,separators=(',',':'))
        meta=json.dumps(dict(approved_redemption_percent=25),ensure_ascii=False,sort_keys=True,separators=(',',':'))
        self.c.db.execute("INSERT INTO links VALUES('COMMUNITY_MERCHANT_OPENING',?,?,?,?,1)",(key,'owner','application1',opening))
        self.c.db.execute("INSERT INTO links VALUES('COMMUNITY_ONBOARDING','application1','owner','application1',?,1)",(meta,))
        with self.c.tx():self.p.record_split(self.g,'split1',dict(reference='order1',provider_reference='provider1'),dict(status='FINISHED',receivers=[dict(result='SUCCESS',amount_minor=1000)]))
        summary=self.p.dispatch(self.g,'community.points_summary',{})
        self.assertEqual((summary['redemption_percent'],summary['redemption_percent_locked']),(25,True))
        with self.assertRaisesRegex(PermissionError,'APPROVED_REDEMPTION_PERCENT_IMMUTABLE'):
            self.p.dispatch(self.g,'community.points_setting_save',dict(redemption_percent=30,expected_revision=summary['revision']))
        redeemed=self.p.dispatch(self.g,'community.points_redeem',dict(request_id='approved1',purpose='CHARITY_MALL',order_amount_minor=1000,points=25))
        self.assertEqual((redeemed['redemption_percent'],redeemed['cash_offset_minor']),(25,250))
    def test_successful_return_reverses_original_points(self):
        with self.c.tx():self.p.record_split(self.g,'split1',dict(reference='order1',provider_reference='provider1'),dict(status='FINISHED',receivers=[dict(result='SUCCESS',amount_minor=1000)]))
        with self.c.tx():self.p.record_return(self.g,'split1','return1',300)
        with self.c.tx():self.p.record_return(self.g,'split1','return1',300)
        summary=self.p.dispatch(self.g,'community.points_summary',{})
        self.assertEqual((summary['available_points'],summary['total_earned_points']),(70,100))
    def test_small_returns_accumulate_before_point_reversal(self):
        with self.c.tx():self.p.record_split(self.g,'split1',dict(reference='order1',provider_reference='provider1'),dict(status='FINISHED',receivers=[dict(result='SUCCESS',amount_minor=100)]))
        with self.c.tx():self.p.record_return(self.g,'split1','return1',6)
        self.assertEqual(self.p.dispatch(self.g,'community.points_summary',{})['available_points'],10)
        with self.c.tx():self.p.record_return(self.g,'split1','return2',4)
        self.assertEqual(self.p.dispatch(self.g,'community.points_summary',{})['available_points'],9)

    def test_return_without_awarded_points_is_a_safe_noop(self):
        with self.c.tx():self.p.record_split(self.g,'split1',dict(reference='order1',provider_reference='provider1'),dict(status='FINISHED',receivers=[dict(result='SUCCESS',amount_minor=9)]))
        with self.c.tx():self.p.record_return(self.g,'split1','return1',9)
        self.assertEqual(self.p.dispatch(self.g,'community.points_summary',{})['available_points'],0)
        self.assertEqual(self.c.audits,[])

    def test_redemption_reverse_is_idempotent_audited_and_bounded(self):
        with self.c.tx():self.p.record_split(self.g,'split1',dict(reference='order1',provider_reference='provider1'),dict(status='FINISHED',receivers=[dict(result='SUCCESS',amount_minor=1000)]))
        redeemed=self.p.dispatch(self.g,'community.points_redeem',dict(request_id='redeem1',purpose='CHARITY_MALL',order_amount_minor=1000,points=10))
        first=self.p.dispatch(self.g,'community.points_redeem_reverse',dict(request_id='reverse1',redemption_id='redeem1',points=7))
        again=self.p.dispatch(self.g,'community.points_redeem_reverse',dict(request_id='reverse1',redemption_id='redeem1',points=7))
        self.assertEqual(first,again)
        summary=self.p.dispatch(self.g,'community.points_summary',{})
        self.assertEqual((summary['available_points'],summary['total_redeemed_points'],summary['total_redemption_reversed_points']),(97,10,7))
        self.assertEqual([event[2] for event in self.c.audits].count('MERCHANT_POINTS_REDEMPTION_REVERSED'),1)
        with self.assertRaisesRegex(ValueError,'POINTS_REDEMPTION_RETURN_ID_COLLISION'):
            self.p.dispatch(self.g,'community.points_redeem_reverse',dict(request_id='reverse1',redemption_id='redeem1',points=8))
        with self.assertRaisesRegex(ValueError,'POINTS_REDEMPTION_RETURN_EXCEEDS_ORIGINAL'):
            self.p.dispatch(self.g,'community.points_redeem_reverse',dict(request_id='reverse2',redemption_id='redeem1',points=4))

    def test_scope_isolation_and_stable_error_codes(self):
        other=dict(self.g,scope=dict(tenant_id='tenant',merchant_id='other',store_id='store'))
        with self.c.tx():self.p.record_split(self.g,'split1',dict(reference='order1',provider_reference='provider1'),dict(status='FINISHED',receivers=[dict(result='SUCCESS',amount_minor=100)]))
        self.assertEqual(self.p.dispatch(other,'community.points_summary',{})['available_points'],0)
        with self.assertRaisesRegex(ValueError,'POINTS_ORIGINAL_REDEMPTION_REQUIRED'):
            self.p.dispatch(other,'community.points_redeem_reverse',dict(request_id='reverse1',redemption_id='redeem1',points=1))
        with self.assertRaisesRegex(ValueError,'INVALID_POINTS_SPLIT_RETURN'):
            with self.c.tx():self.p.record_return(self.g,'split1','bad return',1)


if __name__=='__main__':unittest.main()
