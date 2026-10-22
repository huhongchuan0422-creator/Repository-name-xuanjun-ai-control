"""Native consumer registration: real original stores, synthetic WeChat only."""
import hashlib
import json
import unittest
from unittest.mock import Mock
import test_community_mini_center_identity as fixture
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_mini_login import MiniGateway, LoginUnavailable
from scripts.community_customer_profile import CustomerProfile
from scripts.community_wechat_registration import ACCOUNT, CONSUMER

class NativeConsumer(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ExistingCenterComposition();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.c=self.fx.center;self.i=self.fx.identity;self.g=self.fx.gateway
        from scripts.pr122_customer_core import canonical
        self.realm=dict(kind='COMMUNITY_PLATFORM_REALM',title='Synthetic platform',requirements=[],
            source='OWNER_APPROVED_FIRST_INSTALL',authority_ref='test_realm')
        self.c.db.execute("UPDATE projects SET authority_ref='test_realm',payload=? WHERE id='project1'",
            (self.c.encrypt(canonical(self.realm),'project:project1'),))
        self.i.configure_registration(['shop1'])
        self.fx.provider.exchange.return_value=dict(appid=self.i.appid,openid='new_customer_openid')
    def login(self,code='new_code'):
        return self.g.login({'code':code})['session_token']
    def uid(self,token):return self.c.session(token)
    def test_first_login_registers_once_without_email_or_project_membership(self):
        before=self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        token=self.login();uid=self.uid(token)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before+1)
        self.assertEqual(self.i.resolve(token,'shop1',self.c.now()).role,'CUSTOMER')
        account=self.c.db.execute('SELECT * FROM accounts WHERE id=?',(uid,)).fetchone()
        self.assertEqual(self.c.decrypt(account['email_enc'],uid),b'')
        marker=self.c.db.execute('SELECT payload FROM links WHERE channel=? AND user_id=?',(ACCOUNT,uid)).fetchone()[0]
        metadata=json.loads(self.c.decrypt(marker,'community-wechat-account'))
        self.assertIs(metadata['email_verified'],False)
        self.assertIs(metadata['identity_verified'],True)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM members WHERE user_id=?',(uid,)).fetchone()[0],0)
        self.assertEqual(self.uid(self.login('second_code')),uid)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before+1)
        with self.assertRaises(PermissionError):self.c.project(uid,'project1',('OWNER','EDITOR','REVIEWER'))
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM audit WHERE actor=? AND event='COMMUNITY_CONSUMER_REGISTERED'",(uid,)).fetchone()[0],1)
    def test_unknown_network_result_has_no_account_and_code_is_not_replayed(self):
        before=self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        self.fx.provider.exchange.side_effect=TimeoutError()
        with self.assertRaises(LoginUnavailable):self.login()
        self.fx.reopen();self.c=self.fx.center;self.i=self.fx.identity;self.g=self.fx.gateway
        self.i.configure_registration(['shop1'])
        self.fx.provider.exchange.side_effect=None;self.fx.provider.exchange.reset_mock()
        with self.assertRaises(PermissionError):self.login()
        self.fx.provider.exchange.assert_not_called()
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
    def test_client_cannot_choose_role_tenant_or_provider_identity(self):
        for extra in ({'role':'PLATFORM_OWNER'},{'tenant':'tenant2'},{'openid':'victim'},{'verified':True}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):self.g.login(dict(code='injected',**extra))
        self.fx.provider.exchange.assert_not_called()
    def test_revocation_never_recreates_or_reactivates_account_or_grant(self):
        token=self.login();uid=self.uid(token)
        self.c.db.execute('UPDATE links SET active=0 WHERE channel=? AND user_id=?',(CONSUMER,uid))
        with self.assertRaises(PermissionError):self.i.resolve(token,'shop1',self.c.now())
        with self.assertRaises(LoginUnavailable):self.login('after_revoke')
        self.assertEqual(self.c.db.execute('SELECT active FROM links WHERE channel=? AND user_id=?',(CONSUMER,uid)).fetchone()[0],0)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM links WHERE channel=? AND user_id=?',(ACCOUNT,uid)).fetchone()[0],1)
        self.c.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI' AND user_id=?",(uid,))
        with self.assertRaises(LoginUnavailable):self.login('after_unlink')
    def test_mapping_change_project_expiry_and_wrong_scene_refused(self):
        token=self.login()
        with self.assertRaises(PermissionError):self.i.resolve(token,'other_shop',self.c.now())
        from scripts.community_saas_phase2 import Principal
        another=Principal('tenant1','CUSTOMER')
        self.i.runtime.bindings[another]=dict(self.i.runtime.bindings[self.fx.stage.customer],store_id='another_store')
        scenes=dict(self.fx.scenes,shop2=dict(project='project1',principal=another))
        other_identity=CenterIdentity(self.c,self.i.runtime,self.i.appid,scenes)
        other_identity.configure_registration(['shop1'])
        with self.assertRaises(PermissionError):other_identity.resolve(token,'shop2',self.c.now())
        scope=self.i.runtime.bindings[self.fx.stage.customer]
        old=dict(scope);scope['store_id']='other_store'
        try:
            with self.assertRaises(PermissionError):self.i.resolve(token,'shop1',self.c.now())
            with self.assertRaises(LoginUnavailable):self.login('mapping_changed')
        finally:scope.clear();scope.update(old)
        self.c.db.execute("UPDATE projects SET customer='changed_customer' WHERE id='project1'")
        with self.assertRaises(PermissionError):self.i.resolve(token,'shop1',self.c.now())
        self.c.db.execute("UPDATE projects SET customer='customer1' WHERE id='project1'")
        self.c.db.execute("UPDATE projects SET active=0 WHERE id='project1'")
        with self.assertRaises(PermissionError):self.i.resolve(token,'shop1',self.c.now())
        with self.assertRaises(LoginUnavailable):self.login('project_revoked')
    def test_profile_and_referral_use_consumer_scope_without_editor_privileges(self):
        token=self.login();uid=self.uid(token);profile=CustomerProfile(identity=self.i)
        result=profile.consumer(token,'shop1','profile_read',{})
        self.assertEqual(result['user_id'],uid)
        updated=profile.consumer(token,'shop1','profile_update',dict(nickname='Consumer',contact='',expected_version=0))
        self.assertEqual(updated['version'],1)
        code=profile.consumer(token,'shop1','referral_code',{})['code']
        self.fx.provider.exchange.return_value=dict(appid=self.i.appid,openid='another_consumer')
        other=self.login('other_consumer_code')
        result=profile.consumer(other,'shop1','referral_bind',{'code':code})
        self.assertEqual(result['referrer_user_id'],uid)
        self.c.db.execute('UPDATE links SET active=0 WHERE channel=? AND user_id=?',(CONSUMER,uid))
        self.fx.provider.exchange.return_value=dict(appid=self.i.appid,openid='third_consumer')
        third=self.login('third_consumer_code')
        with self.assertRaises(PermissionError):profile.consumer(third,'shop1','referral_bind',{'code':code})
    def test_restart_same_id_and_disabling_registration_refuses_native_access(self):
        token=self.login();uid=self.uid(token)
        self.fx.reopen();self.c=self.fx.center;self.i=self.fx.identity;self.g=self.fx.gateway
        self.fx.provider.exchange.return_value=dict(appid=self.i.appid,openid='new_customer_openid')
        with self.assertRaises(LoginUnavailable):self.login('disabled')
        self.i.configure_registration(['shop1'])
        self.assertEqual(self.uid(self.login('after_restart')),uid)
        self.assertIs(self.i.resolve(token,'shop1',self.c.now()),self.fx.stage.customer)
    def test_invalid_provider_result_and_cross_tenant_policy_do_not_register(self):
        before=self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        for idx,result in enumerate((dict(appid='wx0000000000000000',openid='new'),dict(appid=self.i.appid,openid='invalid unicode 空'),dict(appid=self.i.appid,openid='new',role='CUSTOMER'))):
            self.fx.provider.exchange.return_value=result
            with self.assertRaises(LoginUnavailable):self.login('invalid_'+str(idx))
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
        with self.assertRaises(ValueError):
            CenterIdentity(self.c,self.i.runtime,self.i.appid,self.fx.scenes).configure_registration(['unknown'])
        # Actual different-tenant source project, never an inferred client tenant.
        self.c.db.execute("INSERT INTO projects SELECT 'project2','tenant2',customer,owner,authority_ref,revision,expires,payload,active FROM projects WHERE id='project1'")
        from scripts.pr122_customer_core import canonical
        self.c.db.execute("UPDATE projects SET payload=? WHERE id='project2'",(self.c.encrypt(canonical(self.realm),'project:project2'),))
        scenes=dict(self.fx.scenes,shop2=dict(project='project2',principal=self.fx.stage.other))
        i=CenterIdentity(self.c,self.i.runtime,self.i.appid,scenes)
        with self.assertRaises(PermissionError):i.configure_registration(['shop1','shop2'])
    def test_new_consumer_uses_original_basket_order_ownership_without_staff_access(self):
        from scripts.community_center_operations import CenterOperations
        from scripts.community_commerce import Commerce
        ops=CenterOperations(self.c,self.i.runtime,{'merchant':dict(user_id=self.fx.uid1,
            project='project1',project_roles=['OWNER'],principal=self.fx.stage.merchant)})
        commerce=Commerce(ops,self.i);self.g.commerce=commerce
        web=self.c.login('one@example.org','FixturePassword123!')
        commerce.dispatch(web['token'],web['csrf'],dict(workspace='merchant',operation='price_set',
            params=dict(item_id='sample_item',expected_revision=0,unit_minor=101,stock=3,enabled=True)))
        token=self.login();uid=self.uid(token)
        result=self.g.dispatch(token,dict(scene='shop1',operation='commerce.purchase',
            params=dict(reference='native_basket',lines=[dict(item_id='sample_item',quantity=1,revision=1)])))
        self.assertEqual(result['user_id'],uid)
        self.assertEqual(result['order']['amount_minor'],101)
        self.assertEqual(result['order']['state'],'PENDING')
        self.assertIsNone(result['order']['provider_transaction_id'])
        self.fx.provider.exchange.return_value=dict(appid=self.i.appid,openid='another_buyer')
        other=self.login('another_buyer')
        with self.assertRaises(PermissionError):
            self.g.dispatch(other,dict(scene='shop1',operation='commerce.purchase_read',params=dict(reference='native_basket')))
        with self.assertRaises(PermissionError):
            self.g.dispatch(token,dict(scene='shop1',operation='commerce.project_summary',params={}))
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM members WHERE user_id=?',(uid,)).fetchone()[0],0)

    def test_registration_audit_failure_rolls_back_account_grants_and_session(self):
        before=self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        audit=self.c.audit
        def fail(project,actor,event,obj):
            if event=='COMMUNITY_CONSUMER_REGISTERED':raise OSError('synthetic audit failure')
            return audit(project,actor,event,obj)
        from unittest.mock import patch
        with patch.object(self.c,'audit',side_effect=fail):
            with self.assertRaises(LoginUnavailable):self.login('audit_failure')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM links WHERE channel IN (?,?)',(ACCOUNT,CONSUMER)).fetchone()[0],0)
        self.fx.provider.exchange.reset_mock()
        with self.assertRaises(PermissionError):self.login('audit_failure')
        self.fx.provider.exchange.assert_not_called()

    def test_saas_contract_project_cannot_be_used_as_native_registration_realm(self):
        from scripts.pr122_customer_core import canonical
        wrong=dict(self.realm,kind='SAAS_CUSTOMER_PROJECT',verified_entity=True,order_ref='not_a_community_realm')
        self.c.db.execute("UPDATE projects SET payload=? WHERE id='project1'",(self.c.encrypt(canonical(wrong),'project:project1'),))
        before=self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        with self.assertRaises(LoginUnavailable):self.login('wrong_platform_kind')
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)

    def test_existing_legacy_binding_keeps_original_account_and_default_is_closed(self):
        before=self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        self.fx.provider.exchange.return_value=dict(appid=self.i.appid,openid='openid1')
        self.assertEqual(self.uid(self.login()),self.fx.uid1)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
        i=CenterIdentity(self.c,self.i.runtime,self.i.appid,self.fx.scenes)
        gateway=MiniGateway(self.i.runtime,i,self.fx.provider)
        self.fx.provider.exchange.return_value=dict(appid=i.appid,openid='unconfigured_new')
        with self.assertRaises(LoginUnavailable):gateway.login({'code':'no_registration_policy'})
        self.assertEqual(hashlib.sha256(__import__('pathlib').Path('scripts/pr122_customer_core.py').read_bytes()).hexdigest(),'cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0')

if __name__=='__main__':unittest.main()
