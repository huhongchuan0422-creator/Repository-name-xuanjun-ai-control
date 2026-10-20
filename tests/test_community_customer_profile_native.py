"""Native personal-center calls reuse original verified account/project identity."""
import unittest
import test_community_mini_center_identity as fixtures
from scripts.community_customer_profile import CustomerProfile,notify
from scripts.community_center_communities import CenterCommunities

class NativeProfileJourney(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.ExistingCenterComposition();self.fx.setUp()
        self.first=self.fx.token();self.second=self.fx.token('second','openid2')
        self.profile=CustomerProfile(identity=self.fx.identity)
    def tearDown(self):self.fx.tearDown()
    def call(self,op,p=None,token=None):return self.profile.consumer(token or self.first,'shop1',op,p or {})
    def test_original_id_crm_and_scoped_profile_revision(self):
        initial=self.call('profile_read');self.assertEqual(initial['user_id'],self.fx.uid1);self.assertEqual(initial['project_customer_id'],'customer1')
        updated=self.call('profile_update',dict(nickname='first',contact='private',expected_version=0))
        self.assertEqual(updated['version'],1)
        self.assertEqual(self.call('profile_read',token=self.second)['nickname'],'')
        with self.assertRaises(ValueError):self.call('profile_update',dict(nickname='stale',contact='',expected_version=0))
    def test_explicit_immutable_referral_and_cycle_denial(self):
        code=self.call('referral_code',token=self.second)['code']
        linked=self.call('referral_bind',dict(code=code));self.assertEqual(linked['referrer_user_id'],self.fx.uid2)
        self.assertEqual(self.call('referral_bind',dict(code=code)),linked)
        own=self.call('referral_code')['code']
        with self.assertRaises(PermissionError):self.call('referral_bind',dict(code=own),token=self.second)
        with self.assertRaises(PermissionError):self.call('referral_bind',dict(code=own))
    def test_notice_is_private_and_mark_read_cannot_cross_accounts(self):
        with self.fx.center.tx():notify(self.fx.center,'project1',self.fx.uid1,'ORDER','order1','private notice')
        record=self.call('notices',dict(after_id=''))['records'][0]
        self.assertEqual(self.call('notices',dict(after_id=''),self.second)['records'],[])
        with self.assertRaises(PermissionError):self.call('notice_read',dict(notice_id=record['id']),self.second)
        self.assertTrue(self.call('notice_read',dict(notice_id=record['id']))['read'])

    def _logout_before_profile_tx(self, profile, token):
        original=profile._run
        def race(g,op,p,reauthorize):
            self.fx.center.logout(token)
            return original(g,op,p,reauthorize)
        profile._run=race

    def _notice(self):
        with self.fx.center.tx():
            notify(self.fx.center,'project1',self.fx.uid1,'ORDER','revocation-race','private notice')
        row=self.fx.center.db.execute(
            "SELECT subject_idx,payload FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND user_id=? AND project='project1'",
            (self.fx.uid1,)).fetchone()
        return row[0],row[1]

    def test_mini_notice_read_rechecks_real_logout_inside_transaction(self):
        key,payload=self._notice()
        before_audit=self.fx.center.db.execute('SELECT count(*) FROM audit').fetchone()[0]
        before_limits=self.fx.center.db.execute('SELECT count(*) FROM rate_limits').fetchone()[0]
        self._logout_before_profile_tx(self.profile,self.first)
        with self.assertRaises(PermissionError):
            self.call('notices',dict(after_id=''))
        self.assertEqual(self.fx.center.db.execute(
            "SELECT payload FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND subject_idx=?",(key,)).fetchone()[0],payload)
        self.assertEqual(self.fx.center.db.execute('SELECT count(*) FROM audit').fetchone()[0],before_audit)
        self.assertEqual(self.fx.center.db.execute('SELECT count(*) FROM rate_limits').fetchone()[0],before_limits)

    def test_mini_notice_mark_read_rechecks_real_logout_without_persisting(self):
        key,payload=self._notice()
        self._logout_before_profile_tx(self.profile,self.first)
        with self.assertRaises(PermissionError):
            self.call('notice_read',dict(notice_id=key))
        self.assertEqual(self.fx.center.db.execute(
            "SELECT payload FROM links WHERE channel='COMMUNITY_NOTICE_V1' AND subject_idx=?",(key,)).fetchone()[0],payload)
        decoded=self.fx.center.decrypt(payload,'community-notice:'+key)
        self.assertFalse(__import__('json').loads(decoded)['read'])

    def test_mini_profile_update_rechecks_real_logout_without_persisting(self):
        self._logout_before_profile_tx(self.profile,self.first)
        with self.assertRaises(PermissionError):
            self.call('profile_update',dict(nickname='revoked',contact='secret',expected_version=0))
        key=self.fx.center.idx('community-profile:project1:'+self.fx.uid1)
        self.assertIsNone(self.fx.center.db.execute(
            "SELECT payload FROM links WHERE channel='COMMUNITY_CUSTOMER_PROFILE' AND subject_idx=? AND project='project1'",
            (key,)).fetchone())

    def test_web_notice_read_rechecks_real_logout_inside_transaction(self):
        self._notice()
        web=self.fx.center.login('one@example.org','FixturePassword123!')
        communities=CenterCommunities(self.fx.center,{'customer':{
            'user_id':self.fx.uid1,'project':'project1','tenant':'tenant1','role':'CUSTOMER'}})
        profile=CustomerProfile(communities)
        self._logout_before_profile_tx(profile,web['token'])
        with self.assertRaises(PermissionError):
            profile.dispatch(web['token'],web['csrf'],'customer','notices',{'after_id':''})

    def test_revoked_membership_and_client_identity_fields_deny(self):
        with self.assertRaises(ValueError):self.call('profile_read',dict(user_id=self.fx.uid2))
        self.fx.center.db.execute('UPDATE members SET active=0 WHERE user_id=?',(self.fx.uid1,))
        with self.assertRaises(PermissionError):self.call('profile_read')
