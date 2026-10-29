"""Synthetic original Center sessions; no live accounts or provider requests."""
import unittest
from email.message import Message
import test_community_mini_center_identity as fixture
from scripts.community_web_session import WebSession,token,COOKIE
from scripts.community_center_communities import CenterCommunities

class OriginalWebSession(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ExistingCenterComposition();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.service=WebSession(self.fx.center)
    def login(self):
        result,cookie=self.service.dispatch('/community/session/login',Message(),{'email':'one@example.org','password':'FixturePassword123!'},'127.0.0.1')
        headers=Message();headers['Cookie']=cookie.split(';')[0];headers['X-CSRF-Token']=result['csrf']
        return result,cookie,headers
    def test_existing_login_cookie_csrf_check_and_logout(self):
        before=self.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        result,cookie,headers=self.login()
        for flag in ['Path=/','Secure','HttpOnly','SameSite=Strict']:self.assertIn(flag,cookie)
        self.assertNotIn('token',result)
        value,_=self.service.dispatch('/community/session/check',headers,{},'127.0.0.1')
        self.assertEqual(value,{'user_id':self.fx.uid1,'workspaces':[],'reviewer':False})
        self.assertEqual(self.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
        _,clear=self.service.dispatch('/community/session/logout',headers,{},'127.0.0.1')
        self.assertIn('Max-Age=0',clear)
        with self.assertRaises(PermissionError):self.service.dispatch('/community/session/check',headers,{},'127.0.0.1')
    def test_csrf_duplicate_cookie_bearer_and_epoch_revocation(self):
        _,cookie,headers=self.login()
        headers.replace_header('X-CSRF-Token','wrong')
        with self.assertRaises(PermissionError):self.service.dispatch('/community/session/check',headers,{},'127.0.0.1')
        for extra in [('Cookie',cookie.split(';')[0]),('X-Center-Session','anything'),('Authorization','Bearer anything')]:
            h=Message();h['Cookie']=cookie.split(';')[0];h[extra[0]]=extra[1]
            with self.assertRaises(PermissionError):token(h)
        _,_,headers=self.login();self.fx.center.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.fx.uid1,))
        with self.assertRaises(PermissionError):self.service.dispatch('/community/session/check',headers,{},'127.0.0.1')
    def test_no_registration_client_grants_or_unknown_action(self):
        for body in [{'email':'unknown@example.org','password':'FixturePassword123!'}, {'email':'one@example.org','password':'FixturePassword123!','role':'OWNER'}]:
            with self.assertRaises((PermissionError,ValueError)):self.service.dispatch('/community/session/login',Message(),body,'127.0.0.1')
        _,_,headers=self.login()
        with self.assertRaises(ValueError):self.service.dispatch('/community/session/grant',headers,{},'127.0.0.1')

    def setup_community(self):
        grants={name:dict(user_id=self.fx.uid1,project='project1',tenant='tenant1',role=role) for name,role in [('community','COMMUNITY_ADMIN'),('platform','PLATFORM_OWNER'),('review','PLATFORM_REVIEWER'),('customer','CUSTOMER'),('merchant','MERCHANT_ADMIN')]}
        grants['foreign']=dict(user_id=self.fx.uid2,project='project1',tenant='tenant1',role='PLATFORM_OWNER')
        communities=CenterCommunities(self.fx.center,grants)
        self.service=WebSession(self.fx.center,communities=communities)
        return communities
    def test_check_projects_exact_server_roles_and_preserves_original_fields(self):
        self.setup_community();_,_,headers=self.login()
        result,_=self.service.dispatch('/community/session/check',headers,{},'127.0.0.1')
        self.assertEqual(set(result),{'user_id','workspaces','reviewer'})
        self.assertFalse(result['reviewer'])
        self.assertEqual(result['workspaces'],[dict(kind='COMMUNITY',workspace=n,role=r) for n,r in [('community','COMMUNITY_ADMIN'),('platform','PLATFORM_OWNER'),('review','PLATFORM_REVIEWER'),('customer','CUSTOMER'),('merchant','MERCHANT_ADMIN')]])
    def test_role_is_rechecked_and_unknown_does_not_become_platform(self):
        communities=self.setup_community();_,_,headers=self.login()
        communities.grants['platform']['role']='INVALID'
        communities.grants['review']['tenant']='foreign'
        result,_=self.service.dispatch('/community/session/check',headers,{},'127.0.0.1')
        self.assertNotIn('platform',[w['workspace'] for w in result['workspaces']])
        self.assertNotIn('review',[w['workspace'] for w in result['workspaces']])
        with self.assertRaises(ValueError):self.service.dispatch('/community/session/check',headers,{'role':'PLATFORM_OWNER'},'127.0.0.1')

if __name__=='__main__':unittest.main()
