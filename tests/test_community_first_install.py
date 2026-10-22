"""Fresh platform with zero accounts/staff/merchants, synthetic provider only."""
import json
import os
import base64
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from scripts.community_first_install import FirstInstallation, SYSTEM_OWNER
from scripts.community_saas_phase2 import Principal
from scripts.community_mini_application import MiniApplication
from scripts.community_mini_host_config import stores

class FreshPlatform(unittest.TestCase):
    def setUp(self):
        if os.geteuid()==0:
            guard=patch('scripts.community_first_install._require_nonroot');guard.start();self.addCleanup(guard.stop)
        self.tmp=tempfile.TemporaryDirectory(dir=Path.home());self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'platform'
        self.customer=Principal('customer_platform','CUSTOMER')
        self.bindings={self.customer:dict(tenant_id='customer_platform',merchant_id='first_shop',store_id='first_store')}
        self.realm=dict(project='community',tenant='customer_platform',customer='platform_customer',
            title='Customer community',expires=20000,authority_ref='owner_first_install')
        self.clock=lambda:10000
    def initialize(self):
        return FirstInstallation.initialize(str(self.root),{'testkey':b'k'*32},'testkey',self.realm,self.bindings,clock=self.clock)
    def test_zero_seed_first_wechat_registration_profile_and_no_operator_access(self):
        with self.initialize() as owner:
            c=owner.center;runtime=owner.persistence.runtime
            for table in ('accounts','members','sessions','links'):
                self.assertEqual(c.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
            self.assertEqual(runtime.demo.merchant_db.execute('SELECT count(*) FROM merchant_profiles').fetchone()[0],0)
            row=c.db.execute('SELECT * FROM projects').fetchone()
            self.assertEqual(row['owner'],SYSTEM_OWNER)
            payload=json.loads(c.decrypt(row['payload'],'project:community'))
            self.assertEqual(payload['kind'],'COMMUNITY_PLATFORM_REALM')
            self.assertNotIn('verified_entity',payload);self.assertNotIn('order_ref',payload)
            config=dict(version=1,appid='wx1d5f8873eaea5392',https_origin='https://uk.wenwenwenyiyiyi.work',
                scenes={'shop1':dict(project='community',principal='consumer')},
                stores={name:db.execute('PRAGMA database_list').fetchone()[2] for name,db in stores(c,runtime).items()})
            app=MiniApplication.from_existing_runtime(c,runtime,{'consumer':self.customer},config,'a'*32)
            try:
                app.configure_operations({},consumer_only=True);app.configure_commerce()
                app.identity.configure_registration(['shop1'])
                app.gateway.provider.exchange=Mock(return_value=dict(appid=config['appid'],openid='first_real_format_subject'))
                token=app.gateway.login({'code':'first_code'})['session_token']
                profile=app.gateway.dispatch(token,dict(scene='shop1',operation='commerce.profile_read',params={}))
                self.assertEqual(profile['user_id'],c.session(token))
                self.assertEqual(c.db.execute('SELECT count(*) FROM accounts').fetchone()[0],1)
                self.assertEqual(c.db.execute('SELECT count(*) FROM members').fetchone()[0],0)
                self.assertEqual(app.gateway.dispatch(token,dict(scene='shop1',operation='commerce.products',params={}))['products'],[])
                with self.assertRaises(PermissionError):app.operations.dispatch(token,'x',dict(workspace='admin',operation='community.summary',params={}))
                with self.assertRaises(PermissionError):app.gateway.dispatch(token,dict(scene='shop1',operation='commerce.project_summary',params={}))
                self.assertIsNone(getattr(app.gateway,'payments',None))
            finally:app.close()
    def test_existing_installation_refused_and_partial_failure_kept(self):
        with self.initialize():pass
        before=(self.root/'identity'/'center.sqlite').read_bytes()
        with self.assertRaises(FileExistsError):self.initialize()
        self.assertEqual((self.root/'identity'/'center.sqlite').read_bytes(),before)
        other=Path(self.tmp.name)/'failed'
        with patch('scripts.community_first_install.PersistentRuntime.initialize',side_effect=OSError('synthetic fault')):
            with self.assertRaises(OSError):
                FirstInstallation.initialize(str(other),{'testkey':b'k'*32},'testkey',self.realm,self.bindings,clock=self.clock)
        self.assertTrue((other/'identity'/'center.sqlite').exists())
        with self.assertRaises(FileExistsError):
            FirstInstallation.initialize(str(other),{'testkey':b'k'*32},'testkey',self.realm,self.bindings,clock=self.clock)
    def test_invalid_realm_key_expiry_or_cross_tenant_writes_nothing(self):
        for kind in ('expires','keys','tenant','extra'):
            realm=dict(self.realm);keys={'testkey':b'k'*32}
            if kind=='expires':realm['expires']=9999
            elif kind=='keys':keys['testkey']=b'bad'
            elif kind=='tenant':realm['tenant']='other_platform'
            else:realm['verified_entity']=True
            with self.subTest(kind=kind),self.assertRaises((ValueError,PermissionError)):
                FirstInstallation.initialize(str(self.root),keys,'testkey',realm,self.bindings,clock=self.clock)
            self.assertFalse(self.root.exists())
    def test_fresh_protected_host_consumes_native_registration_without_privileged_seed(self):
        from scripts.community_platform_host import PlatformHost
        self.clock=lambda:int(time.time());self.realm['expires']=self.clock()+10000
        with self.initialize() as initial:
            config=dict(version=1,appid='wx1d5f8873eaea5392',https_origin='https://uk.wenwenwenyiyiyi.work',
                scenes={'shop1':dict(project='community',principal='consumer')},
                stores={name:db.execute('PRAGMA database_list').fetchone()[2]
                    for name,db in stores(initial.center,initial.persistence.runtime).items()})
        def write(name,value):
            path=Path(self.tmp.name)/name;path.write_text(json.dumps(value));path.chmod(0o600);return str(path)
        application=write('application.json',config)
        plan=dict(version=1,center_root=str(self.root/'identity'),runtime_directory=str(self.root/'runtime'),
            application_config=application,principals={'consumer':dict(tenant_id=self.customer.tenant_id,role='CUSTOMER')},
            bindings={'consumer':self.bindings[self.customer]},operations={},reviewers={},registration_scenes=['shop1'],
            socket_path=str(self.root/'community.sock'),https_origin=config['https_origin'],
            nginx_uid=max(1,os.geteuid()),nginx_gid=os.getegid())
        plan_path=write('host.json',plan)
        keys=write('keys.json',dict(active_key='testkey',keys={'testkey':base64.b64encode(b'k'*32).decode()}))
        wechat=write('wechat.json',dict(appid=config['appid'],app_secret='a'*32))
        guard=patch('scripts.community_platform_host._require_nonroot') if os.geteuid()==0 else __import__('contextlib').nullcontext()
        with guard,PlatformHost.open(plan_path,keys,wechat) as host:
            self.assertEqual(host.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],0)
            self.assertTrue(host.application.operations.consumer_only)
            self.assertIsNone(host.application.onboarding)
            host.application.gateway.provider.exchange=Mock(return_value=dict(appid=config['appid'],openid='first_fresh_customer'))
            token=host.application.gateway.login({'code':'fresh_platform'})['session_token']
            profile=host.application.gateway.dispatch(token,dict(scene='shop1',operation='commerce.profile_read',params={}))
            self.assertEqual(profile['user_id'],host.center.session(token))
            self.assertEqual(host.center.db.execute('SELECT count(*) FROM members').fetchone()[0],0)

    def test_wrong_core_pin_and_root_guard_fail_before_creating_files(self):
        with patch('scripts.community_first_install.hashlib.sha256') as digest:
            digest.return_value.hexdigest.return_value='0'*64
            with self.assertRaisesRegex(PermissionError,'PINNED_CENTER_SOURCE_REQUIRED'):self.initialize()
        self.assertFalse(self.root.exists())
        with patch('scripts.community_first_install._require_nonroot',side_effect=PermissionError('NONROOT_PLATFORM_INITIALIZATION_REQUIRED')):
            with self.assertRaises(PermissionError):self.initialize()
        self.assertFalse(self.root.exists())

    def test_consumer_only_is_explicit_and_cannot_contain_operator_grants(self):
        from scripts.community_center_operations import CenterOperations
        with self.initialize() as owner:
            with self.assertRaises(ValueError):CenterOperations(owner.center,owner.persistence.runtime,{})
            with self.assertRaises(ValueError):CenterOperations(owner.center,owner.persistence.runtime,{'admin':{}},consumer_only=True)
            with self.assertRaises(ValueError):CenterOperations(owner.center,owner.persistence.runtime,{},consumer_only=1)

if __name__=='__main__':unittest.main()
