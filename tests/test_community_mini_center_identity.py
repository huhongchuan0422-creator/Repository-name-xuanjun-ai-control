"""Real existing Center SQLite/session/project composition, with synthetic accounts.

The WeChat exchange and signed CRM authority are fixtures, not live credentials.
"""
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import test_community_stage_runtime as stage_fixture
from scripts.pr122_customer_core import Center,canonical
from scripts.community_mini_center_identity import CenterIdentity
from scripts.community_mini_login import MiniGateway,WechatCodeClient,LoginUnavailable
from scripts.community_order_store import create_order
from scripts.community_demo_bootstrap import DEMO_SCOPE

PINNED_CORE_SHA256='cfd3c9d634ddd41d4b59dd4a3ca374d1f1bbcec009c22878e9560d21ae9365b0'
class ExistingCenterComposition(unittest.TestCase):
    def setUp(self):
        self.stage=stage_fixture.RuntimeJourney();self.stage.setUp();self.tmp=tempfile.TemporaryDirectory()
        self.center=Center(self.tmp.name,{'testkey':b'k'*32},'testkey',clock=lambda:self.stage.now,mail_ready=True)
        self.uid1,self.web1=self.account('one@example.org');self.uid2,self.web2=self.account('two@example.org')
        payload={'revision':1,'expires':self.stage.now+10000,'projects':[{'id':'project1','tenant':'tenant1',
            'customer':'customer1','owner_email':'one@example.org','contract_ref':'fixture_contract',
            'order_ref':'fixture_order','verified_entity':True,'title':'Synthetic community project',
            'requirements':[],'reviewer_emails':[]}]}
        key=b'a'*32;signature=hmac.new(key,canonical(payload),hashlib.sha256).hexdigest()
        self.center.import_authority({'payload':payload,'signature':signature},key)
        self.center.db.execute("INSERT INTO members VALUES('project1',?,'EDITOR',1)",(self.uid2,))
        self.scenes={'shop1':{'project':'project1','principal':self.stage.customer}}
        self.identity=CenterIdentity(self.center,self.stage.api,'wx1d5f8873eaea5392',self.scenes)
        self.identity.bind_existing_account(self.web1,self.identity.appid,'openid1')
        self.identity.bind_existing_account(self.web2,self.identity.appid,'openid2')
        self.provider=WechatCodeClient(self.identity.appid,'a'*32)
        self.provider.exchange=Mock(return_value={'appid':self.identity.appid,'openid':'openid1'})
        self.gateway=MiniGateway(self.stage.api,self.identity,self.provider)
    def account(self,address):
        self.center.register(address,'FixturePassword123!')
        row=self.center.db.execute("SELECT id,payload FROM outbox WHERE kind='VERIFY' ORDER BY rowid DESC LIMIT 1").fetchone()
        payload=json.loads(self.center.decrypt(row['payload'],'outbox:'+row['id']))
        self.center.verify(payload['token'],'FixturePassword123!')
        session=self.center.login(address,'FixturePassword123!')
        return session['user_id'],session['token']
    def tearDown(self):self.center.db.close();self.tmp.cleanup();self.stage.tearDown()
    def token(self,code='oncecode',openid='openid1'):
        self.provider.exchange.return_value={'appid':self.identity.appid,'openid':openid}
        return self.gateway.login({'code':code})['session_token']
    def call(self,token,operation,params=None):
        return self.gateway.dispatch(token,{'scene':'shop1','operation':operation,'params':params or {}})
    def reopen(self):
        self.center.db.close();self.center=Center(self.tmp.name,{'testkey':b'k'*32},'testkey',clock=lambda:self.stage.now,mail_ready=True)
        self.identity=CenterIdentity(self.center,self.stage.api,self.identity.appid,self.scenes)
        self.gateway=MiniGateway(self.stage.api,self.identity,self.provider)
    def checkout(self,token,reference='order1'):
        qr=self.call(token,'community.qr',{'context':'mini'})['token']
        return self.call(token,'community.checkout',{'context':'mini','token':qr,'reference':reference,'amount_minor':101})
    def test_core_bytes_are_identical_to_explicit_website_pin(self):
        path=Path(__file__).resolve().parents[1]/'scripts/pr122_customer_core.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),PINNED_CORE_SHA256)
    def test_real_account_session_and_scene_use_original_schema(self):
        before=self.center.db.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall()
        token=self.token();self.assertEqual(self.center.session(token),self.uid1)
        self.assertEqual(self.call(token,'community.storefront')['merchant']['name'],'Demo Merchant A')
        self.assertEqual(before,self.center.db.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall())
        self.assertEqual(self.center.check_integrity()['integrity'],'PASS')
    def test_code_consumption_and_sessions_survive_real_database_reopen(self):
        token=self.token();self.reopen()
        self.assertEqual(self.call(token,'community.storefront')['merchant']['name'],'Demo Merchant A')
        self.provider.exchange.reset_mock()
        with self.assertRaises(Exception):self.token()
        self.provider.exchange.assert_not_called()
    def test_unknown_exchange_stays_consumed_after_restart(self):
        self.provider.exchange.side_effect=TimeoutError()
        with self.assertRaises(LoginUnavailable):self.token()
        self.reopen();self.provider.exchange.side_effect=None;self.provider.exchange.reset_mock()
        with self.assertRaises(Exception):self.token()
        self.provider.exchange.assert_not_called()
    def test_second_verified_customer_cannot_read_same_store_order(self):
        first=self.token();self.checkout(first)
        second=self.token('code2','openid2')
        with self.assertRaises(PermissionError):self.call(second,'community.receipt',{'reference':'order1'})
        self.assertEqual(self.call(first,'community.receipt',{'reference':'order1'})['order']['amount_minor'],101)
    def test_revoked_order_binding_denies_read_and_cannot_be_reclaimed_after_restart(self):
        token=self.token();self.checkout(token)
        self.center.db.execute("UPDATE links SET active=0 WHERE channel='COMMUNITY_ORDER'")
        with self.assertRaises(PermissionError):
            self.call(token,'community.receipt',{'reference':'order1'})
        self.reopen()
        with self.assertRaises(PermissionError):
            self.call(token,'community.receipt',{'reference':'order1'})
        second=self.token('second_code','openid2')
        with self.assertRaises(PermissionError):self.checkout(second)
        self.assertEqual(self.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0],1)
    def test_real_membership_revocation_takes_effect_immediately(self):
        token=self.token();self.center.db.execute("UPDATE members SET active=0 WHERE user_id=?",(self.uid1,))
        with self.assertRaises(PermissionError):self.call(token,'community.storefront')
    def test_provider_unlink_revokes_mini_access_even_if_session_exists(self):
        token=self.token();self.center.db.execute("UPDATE links SET active=0 WHERE channel='WECHAT_MINI' AND user_id=?",(self.uid1,))
        self.assertEqual(self.center.session(token),self.uid1)
        with self.assertRaises(PermissionError):self.call(token,'community.storefront')
    def test_original_center_logout_revokes_mini_session(self):
        token=self.token();self.center.logout(token)
        with self.assertRaises(PermissionError):self.call(token,'community.storefront')
    def test_legacy_order_without_customer_binding_cannot_be_claimed(self):
        create_order(self.stage.o,DEMO_SCOPE,'legacy1',101)
        with self.assertRaises(PermissionError):self.checkout(self.token(),'legacy1')
    def test_reservation_survives_failed_order_creation_no_blind_retry(self):
        token=self.token();self.identity.reserve_order(token,'shop1','unknown1',101,self.stage.now)
        self.reopen();token2=self.token('code2')
        with self.assertRaises(PermissionError):self.identity.reserve_order(token2,'shop1','unknown1',101,self.stage.now)
        self.assertEqual(self.stage.o.execute('SELECT count(*) FROM orders').fetchone()[0],0)
    def test_signed_ownership_amount_mismatch_rejected(self):
        token=self.token();self.checkout(token)
        self.stage.o.execute("UPDATE orders SET amount_minor=102 WHERE reference='order1'")
        with self.assertRaises(PermissionError):self.call(token,'community.receipt',{'reference':'order1'})
    def test_cannot_rebind_wechat_subject_to_another_existing_account(self):
        with self.assertRaises(PermissionError):self.identity.bind_existing_account(self.web2,self.identity.appid,'openid1')

if __name__=='__main__':unittest.main()
