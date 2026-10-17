"""Real original Center sessions/project ACL and original community stores."""
import concurrent.futures
import json
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import test_community_mini_center_identity as center_fixture
from scripts.community_center_operations import CenterOperations
from scripts.community_saas_phase2 import Principal
from scripts.community_mini_http import serve


class ExistingCenterOperations(unittest.TestCase):
    def setUp(self):
        self.fx=center_fixture.ExistingCenterComposition();self.fx.setUp()
        self.web=self.fx.center.login('one@example.org','FixturePassword123!')
        self.other=self.fx.center.login('two@example.org','FixturePassword123!')
        self.staff=Principal('tenant1','STORE_STAFF')
        self.fx.stage.api.bindings[self.staff]=dict(self.fx.stage.api.bindings[self.fx.stage.customer])
        self.grants={'merchant':self.grant(self.fx.stage.merchant),'staff':self.grant(self.staff)}
        self.operations=CenterOperations(self.fx.center,self.fx.stage.api,self.grants)
    def tearDown(self):self.fx.tearDown()
    def grant(self,principal):
        return {'user_id':self.fx.uid1,'project':'project1','project_roles':['OWNER'],'principal':principal}
    def body(self,workspace='staff',operation='community.orders',params=None):
        return {'workspace':workspace,'operation':operation,'params':params or {}}
    def call(self,body=None,web=None,csrf=None):
        web=self.web if web is None else web
        return self.operations.dispatch(web['token'],web['csrf'] if csrf is None else csrf,body or self.body())
    def test_existing_session_reads_registered_store_without_new_identity_tables(self):
        before=self.fx.center.db.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall()
        self.assertEqual(self.call()['orders'],[])
        self.assertEqual(before,self.fx.center.db.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall())
    def test_project_member_without_exact_user_grant_cannot_inherit_roles(self):
        with self.assertRaises(PermissionError):self.call(web=self.other)
    def test_missing_wrong_csrf_and_revoked_session_deny(self):
        for csrf in ('','wrong'):
            with self.assertRaises(PermissionError):self.call(csrf=csrf)
        self.fx.center.logout(self.web['token'])
        with self.assertRaises(PermissionError):self.call()
    def test_membership_revocation_and_project_expiry_take_effect_each_request(self):
        self.call()
        self.fx.center.db.execute("UPDATE members SET active=0 WHERE user_id=?",(self.fx.uid1,))
        with self.assertRaises(PermissionError):self.call()
        self.fx.center.db.execute("UPDATE members SET active=1 WHERE user_id=?",(self.fx.uid1,))
        self.fx.center.db.execute("UPDATE projects SET expires=?",(self.fx.stage.now,))
        with self.assertRaises(PermissionError):self.call()
    def test_original_account_epoch_and_verification_revocation_deny(self):
        self.fx.center.db.execute('UPDATE accounts SET epoch=epoch+1 WHERE id=?',(self.fx.uid1,))
        with self.assertRaises(PermissionError):self.call()
    def test_staff_cannot_edit_or_enter_original_saas_administration(self):
        with self.assertRaises(PermissionError):self.call(self.body(operation='community.ads'))
        with self.assertRaises(PermissionError):self.call(self.body(operation='owner_approve_offer'))
    def test_client_role_scope_and_user_fields_rejected(self):
        for field in ('role','tenant_id','user_id','principal'):
            with self.assertRaises(ValueError):self.call(dict(self.body(),**{field:'PLATFORM_OWNER'}))
    def test_changed_server_principal_or_scope_fails_closed(self):
        self.staff.role='PLATFORM_OWNER'
        with self.assertRaises(PermissionError):self.call()
        self.staff.role='STORE_STAFF';self.fx.stage.api.bindings[self.staff]['store_id']='other_store'
        with self.assertRaises(PermissionError):self.call()
    def test_protected_grant_input_is_copied_and_customer_is_not_operator(self):
        self.grants['staff']['project_roles'].clear()
        self.grants['staff']['user_id']=self.fx.uid2
        self.call()
        with self.assertRaises(PermissionError):
            CenterOperations(self.fx.center,self.fx.stage.api,{'bad':self.grant(self.fx.stage.customer)})
    def test_limit_reuses_original_persistent_center_counter(self):
        for _ in range(60):self.call()
        with self.assertRaises(PermissionError):self.call()
        again=CenterOperations(self.fx.center,self.fx.stage.api,self.grants)
        with self.assertRaises(PermissionError):again.dispatch(self.web['token'],self.web['csrf'],self.body())
    def test_http_requires_center_session_csrf_and_route_is_disabled_by_default(self):
        for enabled in (False,True):
            server=serve(self.fx.gateway,operations=self.operations if enabled else None)
            try:
                def request():
                    req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/community/operations',
                        data=json.dumps(self.body()).encode(),headers={'Content-Type':'application/json',
                            'X-Center-Session':self.web['token'],'X-Center-CSRF':self.web['csrf']})
                    try:
                        with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
                    except urllib.error.HTTPError as error:return error.code,json.load(error)
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(request);server.handle_request();code,result=future.result()
                self.assertEqual(code,200 if enabled else 404)
                if enabled:self.assertFalse(result['payment_enabled'])
            finally:server.server_close()
    def test_audit_failure_after_dispatch_is_unknown_and_not_retried(self):
        original=self.fx.center.audit
        def audit(project,user,kind,reference):
            if kind=='COMMUNITY_OPERATION_COMPLETED':raise RuntimeError('fixture audit failure')
            return original(project,user,kind,reference)
        with patch.object(self.fx.stage.api,'dispatch',wraps=self.fx.stage.api.dispatch) as dispatch:
            with patch.object(self.fx.center,'audit',side_effect=audit):
                with self.assertRaises(RuntimeError):self.call()
            dispatch.assert_called_once()

if __name__=='__main__':unittest.main()
