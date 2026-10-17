"""Mini community membership and explicit campaign redemption on original Center."""
import unittest
import test_community_reports as fixtures

class ConsumerCommunityJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CommunityReportJourney.setUpClass()
    def setUp(self):self.fx=fixtures.CommunityReportJourney();self.fx.setUp()
    def tearDown(self):self.fx.tearDown()
    def consumer(self,op,p):return self.fx.commerce.consumer(self.fx.token,'shop1',op,p)
    def promotion(self):return self.fx.call('promotion_create',dict(community_id=self.fx.cid,scene='shop1',title='Fixture campaign',expires_at=self.fx.c.now()+3600))
    def test_list_is_public_fields_and_mini_membership_matches_web_relation(self):
        listing=self.consumer('communities',dict(after_id=''))
        self.assertEqual([r['id'] for r in listing['records']],[self.fx.cid]);self.assertNotIn('contact',listing['records'][0])
        self.consumer('community_join',dict(community_id=self.fx.cid))
        self.assertEqual(self.consumer('community_mine',{})['community_id'],self.fx.cid)
        members=self.fx.call('members',dict(community_id=self.fx.cid,after_id=''))['records']
        self.assertEqual([r['user_id'] for r in members],[self.fx.fx.uid1])
        self.consumer('community_leave',dict(community_id=self.fx.cid));self.assertFalse(self.consumer('community_mine',{})['active'])
    def test_campaign_redemptions_are_explicit_deduplicated_and_pause_enforced(self):
        campaign=self.promotion();self.assertIn('promotion='+campaign['id'],campaign['mini_page'])
        self.assertFalse(self.consumer('community_mine',{})['active'])
        for _ in range(2):self.consumer('promotion_redeem',dict(code=campaign['id']))
        record=self.fx.call('promotions',dict(community_id=self.fx.cid,after_id=''))['records'][0]
        self.assertEqual((record['authenticated_redemptions'],record['new_members']),(1,1))
        self.fx.call('promotion_state',dict(community_id=self.fx.cid,code=campaign['id'],expected_version=1,status='PAUSED'))
        with self.assertRaises(PermissionError):self.consumer('promotion_redeem',dict(code=campaign['id']))
        with self.assertRaises(ValueError):self.fx.call('promotion_state',dict(community_id=self.fx.cid,code=campaign['id'],expected_version=1,status='ACTIVE'))
    def test_existing_member_not_counted_as_new_and_unowned_campaign_denied(self):
        self.consumer('community_join',dict(community_id=self.fx.cid));campaign=self.promotion()
        self.consumer('promotion_redeem',dict(code=campaign['id']))
        record=self.fx.call('promotions',dict(community_id=self.fx.cid,after_id=''))['records'][0]
        self.assertEqual(record['new_members'],0)
        with self.assertRaises(PermissionError):self.fx.call('promotions',dict(community_id=self.fx.cid,after_id=''),workspace='other',web=self.fx.reviewer)
        with self.assertRaises(PermissionError):self.fx.call('promotion_create',dict(community_id=self.fx.cid,scene='foreign',title='denied',expires_at=self.fx.c.now()+100))
    def test_paused_community_cannot_be_joined_but_can_be_left(self):
        self.consumer('community_join',dict(community_id=self.fx.cid))
        self.fx.call('review',dict(community_id=self.fx.cid,expected_version=3,decision='PAUSED',opinion='fixture paused'),workspace='reviewer',web=self.fx.reviewer)
        with self.assertRaises(PermissionError):self.consumer('community_join',dict(community_id=self.fx.cid))
        self.consumer('community_leave',dict(community_id=self.fx.cid))
