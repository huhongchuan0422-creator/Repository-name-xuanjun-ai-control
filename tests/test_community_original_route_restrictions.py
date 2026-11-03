"""Real original Center + directory dispatch; no role mocks or server access."""
import ast
import secrets
import tempfile
import unittest
from pathlib import Path
from scripts.pr122_customer_core import Center, canonical, Denied
from scripts.community_admin_authority import CommunityAdminAuthority, CHANNEL
from scripts.community_admin_route_gate import community_project, ROUTE_FAMILIES
from scripts.community_center_communities import CenterCommunities

ROUTE='/community/directory'
CAPS=(ROUTE+'#list', ROUTE+'#review', '/community/operations#community.orders', '/community/merchant-bills#bill_rows')
SCOPES=(ROUTE+'#rootspace', ROUTE+'#childspace', '/community/operations#adminops', '/community/merchant-bills#bills', '/community/merchant-bills#finance')

class OriginalRouteRestrictions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=Center(Path(self.tmp.name)/'center',{'k':b'x'*32},'k',clock=lambda:1000)
        c=self.c
        realm=dict(kind='COMMUNITY_PLATFORM_REALM',title='SYNTHETIC',requirements=[],source='OWNER_APPROVED_FIRST_INSTALL',authority_ref='fixture')
        with c.tx():
            c.db.execute('INSERT INTO projects VALUES(?,?,?,?,?,1,?,?,1)',('p','t','c','system_community_platform','fixture',9999,c.encrypt(canonical(realm),'project:p')))
            for uid in ('root','child','ordinary'):
                salt=secrets.token_bytes(16)
                c.db.execute('INSERT INTO accounts(id,email_idx,email_enc,salt,password,verified) VALUES(?,?,?,?,?,1)',(uid,c.idx(uid+'@test.invalid'),c.encrypt((uid+'@test.invalid').encode(),uid),salt,c.password('synthetic-password',salt)))
        self.api=CommunityAdminAuthority(c,'p','t',CAPS,SCOPES)
        self.c.community_admin_authority=self.api
        with c.tx():
            self.api._write(dict(uid='root',project='p',tenant='t',kind='ROOT',revision=1,parent=None,parent_revision=None,capabilities=list(CAPS),workspace_scopes=list(SCOPES),manifest_sha=self.api.manifest_sha,scope_binding_sha=self.api.scope_binding_sha,request_id='fixture'),True)
        self.logins={u:c.login(u+'@test.invalid','synthetic-password') for u in ('root','child','ordinary')}
        self.directory=CenterCommunities(c,{u+'space':dict(user_id=u,project='p',tenant='t',role='PLATFORM_OWNER') for u in ('root','child','ordinary')})
    def tearDown(self):
        self.c.db.close();self.tmp.cleanup()
    def call(self,uid='root',operation='list',workspace=None,params=None):
        login=self.logins[uid]
        return self.directory.dispatch(login['token'],login['csrf'],dict(workspace=workspace or uid+'space',operation=operation,params=params or dict(after_id='',status='ALL')))
    def delegate(self,scopes=None):
        r=self.logins['root'];return self.api.delegate(r['token'],r['csrf'],'child',[CAPS[0]],'delegation',0,workspace_scopes=[SCOPES[1]] if scopes is None else scopes)
    def test_root_real_directory_without_fabricated_membership(self):
        self.assertEqual(self.call()['records'],[])
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM members').fetchone()[0],0)
    def test_real_child_restricted_capability_and_workspace(self):
        self.delegate();self.assertEqual(self.call('child')['records'],[])
        with self.assertRaises(Denied):self.call('child','review')
        with self.assertRaises(Denied):self.call('child',workspace='rootspace')
    def test_default_child_scope_is_not_all(self):
        self.delegate([])
        with self.assertRaises(Denied):self.call('child')
    def test_revoked_child_never_falls_back(self):
        self.delegate();r=self.logins['root'];self.api.revoke(r['token'],r['csrf'],'child',1)
        with self.assertRaises(Denied):self.call('child')
    def test_missing_protected_composition_denies(self):
        del self.c.community_admin_authority
        with self.assertRaises(Denied):self.call()
    def test_context_cleared_after_success_and_error(self):
        self.call()
        with self.assertRaises(Denied):community_project(self.c,'root','p',('OWNER',))
        with self.assertRaises(ValueError):self.call(params=dict(after_id='',status='INVALID'))
        with self.assertRaises(Denied):community_project(self.c,'root','p',('OWNER',))
    def test_original_ordinary_membership_denial_unchanged(self):
        with self.assertRaises(Denied):self.call('ordinary')
    def test_wrong_project_or_tenant_grant_rejected(self):
        self.directory.grants['rootspace']['project']='other'
        with self.assertRaises(Denied):self.call()
        self.directory.grants['rootspace']['project']='p';self.directory.grants['rootspace']['tenant']='other'
        with self.assertRaises(PermissionError):self.call()
    def test_native_business_validation_not_bypassed(self):
        with self.assertRaises(ValueError):self.call(params=dict(after_id='',status='INVALID'))
    def test_child_template_uses_real_actor_without_static_user_grant(self):
        self.c.community_admin_workspace_bindings={SCOPES[0]:dict(project='p',tenant='t',role='PLATFORM_OWNER')}
        self.delegate([SCOPES[0]])
        self.assertEqual(self.call('child',workspace='rootspace')['records'],[])
        self.assertEqual(self.directory.grants['rootspace']['user_id'],'root')
        self.assertEqual(self.c.db.execute('SELECT actor FROM audit ORDER BY seq DESC LIMIT 1').fetchone()[0],'child')
    def test_template_cannot_escape_realm(self):
        self.c.community_admin_workspace_bindings={SCOPES[0]:dict(project='other',tenant='t',role='PLATFORM_OWNER')}
        with self.assertRaises(Denied):self.call()
    def configure_operations(self):
        from scripts.community_admin_route_gate import configure_admin_routes, binding_digest
        from scripts.community_saas_phase2 import Principal
        from scripts.community_stage_runtime import StageRuntime
        from scripts.community_demo_api import DemoService
        from scripts.community_order_store import connect
        from scripts.community_center_operations import CenterOperations
        db=connect();self.addCleanup(db.close)
        p=Principal('t','PLATFORM_OWNER')
        runtime=StageRuntime(DemoService(db),None,{p:dict(tenant_id='t',merchant_id='m',store_id='s')},clock=lambda:1000)
        config=dict(project='p',tenant='t',capabilities=list(CAPS),workspace_scopes=list(SCOPES),manifest_sha=self.api.manifest_sha,
            workspace_bindings={SCOPES[2]:dict(project='p',project_roles=['OWNER'],principal='owner',onboarding_required=False)})
        self.api=CommunityAdminAuthority(self.c,'p','t',CAPS,SCOPES,binding_digest(config['workspace_bindings'],runtime,{'owner':p}))
        config['manifest_sha']=self.api.manifest_sha
        with self.c.tx():
            self.api._write(dict(uid='root',project='p',tenant='t',kind='ROOT',revision=1,parent=None,parent_revision=None,capabilities=list(CAPS),workspace_scopes=list(SCOPES),manifest_sha=self.api.manifest_sha,scope_binding_sha=self.api.scope_binding_sha,request_id='fixture'),True)
        configure_admin_routes(self.c,runtime,{'owner':p},config)
        api=CenterOperations(self.c,runtime,{'legacy':dict(user_id='ordinary',project='p',project_roles=['OWNER'],principal=p)})
        return api,runtime,p,config
    def test_real_runtime_registered_principal_child_reads_without_static_grant(self):
        operations,runtime,p,config=self.configure_operations()
        root=self.logins['root'];child=self.logins['child']
        self.api.delegate(root['token'],root['csrf'],'child',[CAPS[2]],'runtime-child',0,workspace_scopes=[SCOPES[2]])
        body=dict(workspace='adminops',operation='community.orders',params={})
        self.assertEqual(operations.dispatch(child['token'],child['csrf'],body)['orders'],[])
        self.assertNotIn('adminops',operations.grants)
        self.assertIs(self.c.community_admin_workspace_bindings[SCOPES[2]]['principal'],p)
        self.assertEqual(self.c.db.execute('SELECT actor FROM audit ORDER BY seq DESC LIMIT 1').fetchone()[0],'child')
        runtime.bindings[p]['store_id']='changed'
        with self.assertRaises(PermissionError):operations.dispatch(child['token'],child['csrf'],body)
    def test_protected_composition_rejects_user_impersonation(self):
        from scripts.community_admin_route_gate import configure_admin_routes
        api,runtime,p,config=self.configure_operations()
        config['workspace_bindings'][SCOPES[2]]['user_id']='root'
        with self.assertRaises(Denied):configure_admin_routes(self.c,runtime,{'owner':p},config)
    def test_protected_composition_rejects_manifest_change(self):
        from scripts.community_admin_route_gate import configure_admin_routes
        api,runtime,p,config=self.configure_operations();config['manifest_sha']='0'*64
        with self.assertRaises(Denied):configure_admin_routes(self.c,runtime,{'owner':p},config)
    def test_same_principal_name_retarget_requires_new_manifest(self):
        from scripts.community_admin_route_gate import configure_admin_routes
        api,runtime,p,config=self.configure_operations()
        runtime.bindings[p]['store_id']='another'
        with self.assertRaises(Denied):configure_admin_routes(self.c,runtime,{'owner':p},config)
    def test_bill_nested_finance_template_requires_both_scopes_no_provider_power(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        from scripts.community_wechat_sp_actions import ProviderActions
        from scripts.community_merchant_bills import MerchantBills, PERMISSION
        from scripts.community_admin_route_gate import configure_admin_routes, binding_digest
        operations,runtime,p,config=self.configure_operations()
        private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        reader=PartnerOrderReader('123456','AB',private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()),'PUB_KEY_ID_TEST',private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo),lambda:1000)
        policy=dict(sp_appid='wx'+'1'*16,sub_mchid='654321',sub_appid=None,refund_notify_url='https://example.invalid/refund',profit_sharing=False,max_total_bps=0,receivers={},enabled_operations=[])
        actions=ProviderActions(operations,reader,{('t','m','s'):policy})
        bills=MerchantBills(actions)
        config['workspace_bindings'][SCOPES[3]]=dict(finance_workspace='finance',project='p',tenant_id='t',merchant_id='m',sp_mchid='123456',sub_mchid='654321',revision=1,permission=PERMISSION)
        config['workspace_bindings'][SCOPES[4]]=dict(config['workspace_bindings'][SCOPES[2]])
        self.api=CommunityAdminAuthority(self.c,'p','t',CAPS,SCOPES,binding_digest(config['workspace_bindings'],runtime,{'owner':p}))
        config['manifest_sha']=self.api.manifest_sha
        with self.c.tx():self.api._write(dict(uid='root',project='p',tenant='t',kind='ROOT',revision=1,parent=None,parent_revision=None,capabilities=list(CAPS),workspace_scopes=list(SCOPES),manifest_sha=self.api.manifest_sha,scope_binding_sha=self.api.scope_binding_sha,request_id='fixture'),True)
        configure_admin_routes(self.c,runtime,{'owner':p},config)
        root=self.logins['root'];child=self.logins['child']
        self.api.delegate(root['token'],root['csrf'],'child',[CAPS[3]],'bill-child',0,workspace_scopes=[SCOPES[3]])
        body=dict(workspace='bills',operation='bill_rows',params=dict(kind='TRADE',bill_date='1969-12-31',offset=0))
        with self.assertRaisesRegex(Denied,'COMMUNITY_ADMIN_WORKSPACE_DENIED'):bills.dispatch(child['token'],child['csrf'],body)
        self.api.delegate(root['token'],root['csrf'],'child',[CAPS[3]],'bill-child-2',1,workspace_scopes=[SCOPES[3],SCOPES[4]])
        # Real nested authorizers pass; native verified-bill requirement remains.
        with self.assertRaisesRegex(ValueError,'VERIFIED_MERCHANT_BILL_NOT_FOUND'):bills.dispatch(child['token'],child['csrf'],body)
        with self.assertRaisesRegex(Denied,'COMMUNITY_ADMIN_OPERATION_DENIED'):
            actions.dispatch(child['token'],child['csrf'],dict(workspace='finance',operation='receivers',params={}))
    def test_template_only_operations_does_not_enable_ordinary_users(self):
        from scripts.community_center_operations import CenterOperations
        _,runtime,principal,config=self.configure_operations()
        operations=CenterOperations(self.c,runtime,{},consumer_only=True)
        body=dict(workspace='adminops',operation='community.orders',params={})
        login=self.logins['root']
        self.assertEqual(operations.dispatch(login['token'],login['csrf'],body)['orders'],[])
        login=self.logins['ordinary']
        with self.assertRaisesRegex(PermissionError,'OPERATOR_WORKSPACES_DISABLED'):
            operations.dispatch(login['token'],login['csrf'],body)
    def test_template_only_directory_needs_no_legacy_user_binding(self):
        self.c.community_admin_workspace_bindings={SCOPES[0]:dict(project='p',tenant='t',role='PLATFORM_OWNER')}
        self.directory=CenterCommunities(self.c,{})
        self.assertEqual(self.call()['records'],[])
    def test_inventory_nine_routes_and_expected_current_operation_count(self):
        from scripts.community_admin_route_inventory import ROUTE_OPERATIONS, BUSINESS_CAPABILITIES
        self.assertCountEqual(ROUTE_OPERATIONS,ROUTE_FAMILIES)
        self.assertEqual(len(BUSINESS_CAPABILITIES),153)
        self.assertEqual(len(set(BUSINESS_CAPABILITIES)),153)
    def test_nine_real_dispatch_entries_decorated(self):
        root=Path(__file__).resolve().parents[1]/'scripts';found=[]
        for p in root.glob('*.py'):
            tree=ast.parse(p.read_text())
            for n in ast.walk(tree):
                if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    for d in n.decorator_list:
                        if isinstance(d,ast.Call) and isinstance(d.func,ast.Name) and d.func.id=='community_route':found.append(ast.literal_eval(d.args[0]))
        self.assertCountEqual(found,ROUTE_FAMILIES)

if __name__=='__main__':unittest.main()
