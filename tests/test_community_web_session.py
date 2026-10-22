"""Synthetic original Center sessions; no live accounts or provider requests."""
import unittest
from email.message import Message
import test_community_mini_center_identity as fixture
from scripts.community_web_session import WebSession,token,COOKIE

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

if __name__=='__main__':unittest.main()
