"""Offline integration checks; never perform real payment or network operations."""
import unittest
from scripts.community_ad_store import open_offline,create_campaign,list_campaigns,choose,record_metric,change_campaign_state,review_creative
from scripts.community_ad_contract import AMOUNT,SUCCESS

class OfflineAdStoreTests(unittest.TestCase):
    def setUp(self):
        self.db=open_offline()
        self.scope={"tenant_id":"tenant1","merchant_id":"merchant1","store_id":"store1"}
        self.actor={"authenticated":True,"role":"MERCHANT_ADMIN","actor_id":"alice",
                    "tenant_id":"tenant1","merchant_id":"merchant1"}
        self.record={"id":"campaign1","slot":AMOUNT,"starts_at":100,"ends_at":200,
                     "title":"Safe ad","target_url":"https://example.org/ad","priority":10}
    def tearDown(self): self.db.close()
    def create(self): return create_campaign(self.db,self.scope,self.record,self.actor,100)
    def test_create_draft_and_audit_atomic(self):
        result=self.create()
        self.assertEqual(result["status"],"DRAFT")
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit_events").fetchone()[0],1)
    def test_cross_tenant_actor_rejected(self):
        with self.assertRaises(ValueError):
            create_campaign(self.db,self.scope,self.record,dict(self.actor,tenant_id="other"),100)
        self.assertEqual(self.db.execute("SELECT count(*) FROM campaigns").fetchone()[0],0)
    def test_no_ad_before_approval(self):
        self.create()
        self.assertIsNone(choose(self.db,self.scope,AMOUNT,120))
    def test_requires_approved_moderation_and_active(self):
        self.create()
        self.db.execute("UPDATE campaigns SET status='ACTIVE' WHERE campaign_id='campaign1'")
        self.assertIsNone(choose(self.db,self.scope,AMOUNT,120))
        self.db.execute("UPDATE campaigns SET moderation='APPROVED' WHERE campaign_id='campaign1'")
        self.assertEqual(choose(self.db,self.scope,AMOUNT,120)["id"],"campaign1")
        self.assertIsNone(choose(self.db,self.scope,AMOUNT,200))
    def test_tenant_scope_for_query_and_selection(self):
        self.create()
        other=dict(self.scope,tenant_id="other")
        self.assertEqual(list_campaigns(self.db,other)["campaigns"],[])
        self.assertIsNone(choose(self.db,other,AMOUNT,120))
    def test_campaign_duplicate_does_not_append_audit(self):
        self.create()
        with self.assertRaises(Exception): self.create()
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit_events").fetchone()[0],1)
    def test_metrics_atomic_duplicate(self):
        self.create()
        x=record_metric(self.db,self.scope,AMOUNT,"CLICK","ev1","campaign1",130)
        y=record_metric(self.db,self.scope,AMOUNT,"CLICK","ev1","campaign1",130)
        self.assertTrue(x["recorded"]);self.assertFalse(y["recorded"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM metric_events").fetchone()[0],1)
    def test_metrics_slot_kind_separation(self):
        self.create()
        record_metric(self.db,self.scope,AMOUNT,"CLICK","ev1","campaign1",130)
        record_metric(self.db,self.scope,AMOUNT,"IMPRESSION","ev1","campaign1",130)
        self.assertEqual(self.db.execute("SELECT count(*) FROM metric_events").fetchone()[0],2)
    def test_unknown_campaign_metric_denied(self):
        with self.assertRaises(ValueError):
            record_metric(self.db,self.scope,AMOUNT,"CLICK","ev1","missing",130)
    def test_refuses_unsafe_url(self):
        with self.assertRaises(ValueError):
            create_campaign(self.db,self.scope,dict(self.record,target_url="javascript:alert(1)"),self.actor,100)
    def test_rejects_illegal_slot_and_invalid_time(self):
        with self.assertRaises(ValueError):
            create_campaign(self.db,self.scope,dict(self.record,slot="unknown"),self.actor,100)
        with self.assertRaises(ValueError):
            create_campaign(self.db,self.scope,dict(self.record,ends_at=100),self.actor,100)
    def test_keyset_pagination(self):
        self.create()
        create_campaign(self.db,self.scope,dict(self.record,id="campaign2"),self.actor,100)
        p=list_campaigns(self.db,self.scope,limit=1)
        self.assertTrue(p["has_more"])
        q=list_campaigns(self.db,self.scope,after_id=p["next_cursor"],limit=1)
        self.assertFalse(q["has_more"])
        self.assertEqual(q["campaigns"][0]["id"],"campaign2")

    def test_status_and_moderator_complete_lifecycle(self):
        self.create()
        review=change_campaign_state(self.db,self.scope,"campaign1","REVIEW",self.actor,110,1)
        self.assertEqual(review["version"],2)
        with self.assertRaises(ValueError):
            change_campaign_state(self.db,self.scope,"campaign1","ACTIVE",self.actor,120,2)
        moderator={"authenticated":True,"role":"PLATFORM_ADMIN","actor_id":"moderator"}
        approved=review_creative(self.db,self.scope,"campaign1",True,moderator,120,2)
        self.assertEqual(approved["version"],3)
        change_campaign_state(self.db,self.scope,"campaign1","APPROVED",self.actor,125,3)
        change_campaign_state(self.db,self.scope,"campaign1","ACTIVE",self.actor,130,4)
        self.assertEqual(choose(self.db,self.scope,AMOUNT,140)["id"],"campaign1")
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit_events").fetchone()[0],5)

    def test_creative_approval_is_platform_moderator_only(self):
        self.create()
        change_campaign_state(self.db,self.scope,"campaign1","REVIEW",self.actor,110,1)
        with self.assertRaises(ValueError):
            review_creative(self.db,self.scope,"campaign1",True,self.actor,120,2)

    def test_stale_version_rejected_before_update(self):
        self.create()
        with self.assertRaises(ValueError):
            change_campaign_state(self.db,self.scope,"campaign1","REVIEW",self.actor,110,2)
        self.assertEqual(self.db.execute("SELECT version FROM campaigns").fetchone()[0],1)

    def test_cannot_edit_or_delete_audit_history(self):
        self.create()
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM audit_events")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE audit_events SET action='FAKE'")
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit_events").fetchone()[0],1)

    def test_cross_tenant_state_transition_denied(self):
        self.create()
        with self.assertRaises(ValueError):
            change_campaign_state(self.db,self.scope,"campaign1","REVIEW",
                                  dict(self.actor,tenant_id="other"),110,1)

if __name__=="__main__": unittest.main()
