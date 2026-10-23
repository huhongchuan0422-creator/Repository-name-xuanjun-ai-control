"""Original host orchestration with protected synthetic secrets and identities."""
import base64
import contextlib
import copy
import json
import os
import signal
import socket
import subprocess
import sys
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import test_community_mini_center_identity as fixture
from scripts.community_platform_host import PlatformHost, _configuration, _require_nonroot, main
from scripts.community_persistent_runtime import PersistentRuntime
from scripts.community_mini_host_config import stores

class FormalHost(unittest.TestCase):
    def setUp(self):
        original = tempfile.TemporaryDirectory
        with patch.object(tempfile,'TemporaryDirectory',side_effect=lambda *a,**kw:original(dir=Path.home())):
            self.fx = fixture.ExistingCenterComposition();self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.tmp=original(dir=Path.home());self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.runtime_root=self.root/'runtime'
        self.now=int(time.time())
        # Synthetic project fixture only; not production first-account provisioning.
        self.fx.center.db.execute("UPDATE projects SET expires=?",(self.now+10000,))
        from scripts.pr122_customer_core import canonical
        realm=dict(kind='COMMUNITY_PLATFORM_REALM',title='Synthetic community platform',requirements=[],
            source='OWNER_APPROVED_FIRST_INSTALL',authority_ref='test_platform_realm')
        self.fx.center.db.execute("UPDATE projects SET authority_ref='test_platform_realm',payload=? WHERE id='project1'",
            (self.fx.center.encrypt(canonical(realm),'project:project1'),))
        with PersistentRuntime.initialize(str(self.runtime_root),self.fx.stage.api.bindings,clock=lambda:self.now) as owner:
            config=dict(version=1,appid=self.fx.identity.appid,https_origin='https://uk.wenwenwenyiyiyi.work',
                scenes={'shop1':dict(project='project1',principal='customer')},
                stores={name:db.execute('PRAGMA database_list').fetchone()[2]
                        for name,db in stores(self.fx.center,owner.runtime).items()})
        self.config_path=self.write('application.json',config)
        self.plan=dict(version=1,center_root=self.fx.tmp.name,runtime_directory=str(self.runtime_root),
            application_config=str(self.config_path),
            principals={'customer':dict(tenant_id='tenant1',role='CUSTOMER'),
                        'merchant':dict(tenant_id='tenant1',role='MERCHANT_ADMIN')},
            bindings={'customer':dict(self.fx.stage.api.bindings[self.fx.stage.customer]),
                      'merchant':dict(self.fx.stage.api.bindings[self.fx.stage.merchant])},
            operations={'merchant':dict(user_id=self.fx.uid1,project='project1',
                project_roles=['OWNER'],principal='merchant')},reviewers={self.fx.uid2:'project1'},
            socket_path=str(self.root/'community.sock'),https_origin=config['https_origin'],
            nginx_uid=max(1,os.geteuid()),nginx_gid=os.getegid())
        # Synthetic RSA fixture uses the actual PartnerOrderReader validation path.
        private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        private_pem=private.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode('ascii')
        public_pem=private.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
        self.reader_path=self.write('reader.json',dict(sp_mchid='1900000000',
            merchant_serial='ABCD1234',private_key_pem=private_pem,
            public_key_id='PUB_KEY_ID_TEST',public_key_pem=public_pem))
        self.reader_valid_private=private_pem
        self.reader_valid_public=public_pem
        self.plan['provider_reader_config']=str(self.reader_path)
        self.key_material=dict(active_key='testkey',keys={'testkey':base64.b64encode(b'k'*32).decode()})
        self.wechat=dict(appid=self.fx.identity.appid,app_secret='a'*32)
        self.plan_path=self.write('host.json',self.plan)
        self.keys_path=self.write('keys.json',self.key_material)
        self.wechat_path=self.write('wechat.json',self.wechat)
        self.fx.center.db.close()  # Only the new host owns this synthetic Center now.
    def write(self,name,value):
        path=self.root/name;path.write_text(json.dumps(value));path.chmod(0o600);return path
    def open(self):
        # Local CI may run as root. Mock ONLY the isolated root rejection there;
        # all filesystem ownership checks continue using the actual process UID.
        ctx=patch('scripts.community_platform_host._require_nonroot') if os.geteuid()==0 else contextlib.nullcontext()
        with ctx:
            return PlatformHost.open(str(self.plan_path),str(self.keys_path),str(self.wechat_path))
    def test_original_identity_real_stores_commerce_and_no_payment_or_demo_secrets(self):
        with self.open() as host:
            app=host.application
            self.assertIs(app.center,host.center)
            self.assertIs(app.identity.runtime,host.persistence.runtime)
            self.assertIs(app.gateway.commerce,app.commerce)
            self.assertIs(app.operations.onboarding,app.onboarding)
            from scripts.community_wechat_sp_readonly import PartnerOrderReader
            self.assertIsInstance(app.onboarding.wechat_applyment.reader,PartnerOrderReader)
            self.assertFalse(app.onboarding.wechat_applyment.enabled)
            self.assertIs(app.onboarding.wechat_applyment.onboarding,app.onboarding)

            self.assertIsNone(getattr(app.gateway,'payments',None))
            self.assertIsNone(host.persistence.runtime.demo.qr_key)
            web=host.center.login('one@example.org','FixturePassword123!')
            app.gateway.provider.exchange=Mock(return_value=dict(appid=self.wechat['appid'],openid='new_openid'))
            self.assertEqual(app.gateway.bind(web['token'],web['csrf'],{'code':'bind_native'}),{'bound':True})
            token=app.gateway.login({'code':'login_native'})['session_token']
            self.assertEqual(host.center.session(token),self.fx.uid1)
            with self.assertRaises(PermissionError):
                app.gateway.dispatch(token,dict(scene='wrong',operation='community.storefront',params={}))
            host.center.db.execute("UPDATE projects SET active=0 WHERE id='project1'")
            with self.assertRaises(PermissionError):
                app.gateway.dispatch(token,dict(scene='shop1',operation='community.storefront',params={}))
        self.assertIsNone(host.center);self.assertIsNone(host.persistence)
    def test_real_reader_same_application_save_read_and_reviewer_readback(self):
        """Use the formal host and actual Reader type; no provider request."""
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        with self.open() as host:
            app=host.application
            onboarding=app.onboarding
            self.assertIs(app.operations.onboarding,onboarding)
            self.assertIsInstance(onboarding.wechat_applyment.reader,PartnerOrderReader)
            self.assertFalse(onboarding.wechat_applyment.enabled)
            host.center.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?",(self.fx.uid2,))
            with patch.object(onboarding.wechat_applyment.reader,'_fetch',side_effect=AssertionError('PROVIDER_IO_FORBIDDEN')) as provider:
                applicant=host.center.login('one@example.org','FixturePassword123!')
                reviewer=host.center.login('two@example.org','FixturePassword123!')
                def call(web,op,params):
                    return onboarding.dispatch(web['token'],web['csrf'],dict(operation=op,params=params))
                fields=dict(legal_name='Fixture Legal Name',store_name='Fixture Store',
                            address='Fixture Address',contact='Fixture Contact')
                saved=call(applicant,'save',dict(application=None,revision=0,fields=fields,
                        entity_type='ENTERPRISE',category='GENERAL',delegated=False))
                application=saved['application'];revision=saved['revision']
                self.assertEqual(saved['fields']['legal_name'],fields['legal_name'])
                self.assertEqual(call(applicant,'read',dict(application=application))['application'],application)
                reviewed=call(reviewer,'review_read',dict(application=application))
                self.assertEqual(reviewed['application'],application)
                self.assertEqual(reviewed['revision'],revision)
                self.assertEqual(reviewed['fields']['store_name'],fields['store_name'])
                self.assertEqual(reviewed['wechat_submerchant_state'],'NOT_VERIFIED')
                self.assertFalse(reviewed['payment_enabled'])
                with self.assertRaises(PermissionError):
                    call(reviewer,'save',dict(application=application,revision=revision,fields=fields,
                         entity_type='ENTERPRISE',category='GENERAL',delegated=False))
                with self.assertRaises(PermissionError):
                    call(applicant,'review_read',dict(application=application))
                self.assertEqual(host.center.db.execute(
                    "SELECT count(*) FROM onboarding WHERE application=?",(application,)).fetchone()[0],1)
                provider.assert_not_called()

    def test_real_reader_wechat_draft_projects_into_same_platform_application(self):
        """Original Center + real PartnerOrderReader, never provider IO."""
        from scripts.community_wechat_sp_readonly import PartnerOrderReader
        with self.open() as host:
            onboarding=host.application.onboarding
            applyment=onboarding.wechat_applyment
            self.assertIsInstance(applyment.reader,PartnerOrderReader)
            self.assertFalse(applyment.enabled)
            host.center.db.execute("UPDATE members SET role='REVIEWER' WHERE user_id=?",(self.fx.uid2,))
            applicant=host.center.login('one@example.org','FixturePassword123!')
            reviewer=host.center.login('two@example.org','FixturePassword123!')
            def call(account,operation,params):
                return onboarding.dispatch(account['token'],account['csrf'],
                    dict(operation=operation,params=params))
            with patch.object(applyment.reader,'_fetch',side_effect=AssertionError('REAL_PROVIDER_IO_FORBIDDEN')) as provider:
                saved=call(applicant,'save',dict(application=None,revision=0,
                    fields=dict(legal_name='Initial Applicant',store_name='Original Store',
                        address='Original Address',contact='Initial Contact'),
                    entity_type='ENTERPRISE',category='GENERAL',delegated=False))
                application=saved['application']
                profile={'subject_info':{'business_license_info':{
                            'merchant_name':'Wechat Shared Legal'}},
                         'contact_info':{'mobile_phone':'13800138000'}}
                draft=call(applicant,'wechat_save',dict(
                    application=application,expected_version=0,profile=profile))
                self.assertEqual(draft['version'],1)
                self.assertEqual(draft['state'],'DRAFT')
                self.assertEqual(draft['provider_state'],'NOT_SUBMITTED')
                self.assertEqual(call(applicant,'wechat_read',
                    dict(application=application))['profile'],profile)
                platform=call(applicant,'read',dict(application=application))
                reviewed=call(reviewer,'review_read',dict(application=application))
                self.assertEqual(platform['application'],application)
                self.assertEqual(reviewed['application'],application)
                for view in (platform,reviewed):
                    self.assertEqual(view['fields']['legal_name'],'Wechat Shared Legal')
                    self.assertEqual(view['fields']['contact'],'13800138000')
                    self.assertEqual(view['fields']['store_name'],'Original Store')
                    self.assertFalse(view['payment_enabled'])
                    self.assertEqual(view['wechat_submerchant_state'],'NOT_SUBMITTED')
                with self.assertRaises(PermissionError):
                    call(applicant,'wechat_review_read',dict(application=application))
                with self.assertRaises(PermissionError):
                    call(reviewer,'wechat_save',dict(
                        application=application,expected_version=1,profile=profile))
                with self.assertRaises(PermissionError):
                    call(applicant,'wechat_execute',dict(
                        application=application,expected_version=1))
                provider.assert_not_called()

    def test_protected_community_grants_use_same_center_and_commerce(self):
        self.plan['community_grants']={'community':dict(user_id=self.fx.uid1,project='project1',tenant='tenant1',role='COMMUNITY_ADMIN')}
        self.write('host.json',self.plan)
        with self.open() as host:
            app=host.application
            self.assertIs(app.communities.center,host.center)
            self.assertIs(app.communities.commerce,app.commerce)
            web=host.center.login('one@example.org','FixturePassword123!')
            self.assertEqual(app.communities.authorize(web['token'],web['csrf'],'community')['role'],'COMMUNITY_ADMIN')
            host.center.db.execute("UPDATE projects SET active=0 WHERE id='project1'")
            with self.assertRaises(PermissionError):app.communities.authorize(web['token'],web['csrf'],'community')
            host.center.db.execute("UPDATE projects SET active=1 WHERE id='project1'")
        self.plan['community_grants']['community']['role']='SUPERADMIN'
        self.write('host.json',self.plan)
        with self.assertRaises(ValueError):self.open()

    def test_unknown_provider_subject_does_not_create_an_account(self):
        with self.open() as host:
            before=host.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
            host.application.gateway.provider.exchange=Mock(return_value=dict(appid=self.wechat['appid'],openid='unbound'))
            from scripts.community_mini_login import LoginUnavailable
            with self.assertRaises(LoginUnavailable):host.application.gateway.login({'code':'unknown_native'})
            self.assertEqual(host.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
    def test_provider_reader_fail_closed_and_does_not_use_mock_or_enable_submission(self):
        # Omitted or invalid protected Reader references cannot start the
        # privileged onboarding composition, even if the operator has grants.
        for issue in ('missing_ref','relative_ref','extra_key','world_readable','bad_rsa'):
            with self.subTest(issue=issue):
                plan=copy.deepcopy(self.plan)
                reader=json.loads(self.reader_path.read_text())
                original_mode=self.reader_path.stat().st_mode
                if issue=='missing_ref':plan.pop('provider_reader_config')
                elif issue=='relative_ref':plan['provider_reader_config']='reader.json'
                elif issue=='extra_key':reader['test_only']='forbidden'
                elif issue=='world_readable':self.reader_path.chmod(0o644)
                else:reader['private_key_pem']='not a real RSA private key'
                self.write('host.json',plan)
                if issue in ('extra_key','bad_rsa'):self.write('reader.json',reader)
                try:
                    with self.assertRaises((ValueError,PermissionError)):
                        self.open()
                finally:
                    self.write('host.json',self.plan)
                    self.reader_path.chmod(0o600)
                    if issue in ('extra_key','bad_rsa'):
                        self.write('reader.json',dict(sp_mchid='1900000000',
                            merchant_serial='ABCD1234',
                            private_key_pem=self.reader_valid_private,
                            public_key_id='PUB_KEY_ID_TEST',
                            public_key_pem=self.reader_valid_public))

    def test_bad_appid_private_input_or_missing_center_fail_before_store_open(self):
        for kind in ('appid','permission','missing_center'):
            with self.subTest(kind=kind):
                if kind=='appid':self.write('wechat.json',dict(self.wechat,appid='wx0000000000000000'))
                if kind=='permission':self.keys_path.chmod(0o644)
                center=Path(self.plan['center_root'])/'center.sqlite'
                backup=center.with_suffix('.saved')
                if kind=='missing_center':center.rename(backup)
                try:
                    with patch('scripts.community_platform_host.PersistentRuntime.open',side_effect=AssertionError('NO_OPEN')):
                        with self.assertRaises((ValueError,PermissionError,FileNotFoundError)):self.open()
                finally:
                    self.write('wechat.json',self.wechat);self.keys_path.chmod(0o600)
                    if backup.exists():backup.rename(center)
    def test_exact_config_rejects_extra_roles_or_plain_secret_fields(self):
        for kind in ('extra','role','principal','key','booluid'):
            plan=copy.deepcopy(self.plan);keys=copy.deepcopy(self.key_material)
            if kind=='extra':plan['app_secret']='not_allowed'
            elif kind=='role':plan['principals']['customer']['role']='SUPERADMIN'
            elif kind=='principal':plan['operations']['merchant']['principal']='unknown'
            elif kind=='key':keys['keys']['testkey']='not_base64!'
            else:plan['nginx_uid']=True
            with self.subTest(kind=kind),self.assertRaises((ValueError,PermissionError)):
                _configuration(plan,keys,self.wechat)
    def test_host_lock_cleanup_on_failed_composition_allows_explicit_reopen(self):
        config=json.loads(self.config_path.read_text());config['scenes']['shop1']['project']='missing'
        self.write('application.json',config)
        with self.assertRaises(PermissionError):self.open()
        config['scenes']['shop1']['project']='project1';self.write('application.json',config)
        with self.open() as host:
            with self.assertRaises(BlockingIOError):self.open()
            self.assertEqual(host.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],2)
        with self.open():pass
    def test_serve_uses_exact_proxy_arguments_and_always_closes(self):
        host=self.open();server=Mock();server.serve_forever.side_effect=KeyboardInterrupt()
        with patch.object(host.application,'listen_proxy',return_value=server) as listen:
            with self.assertRaises(KeyboardInterrupt):host.serve()
            listen.assert_called_once_with(self.plan['socket_path'],self.plan['https_origin'],self.plan['nginx_uid'],self.plan['nginx_gid'])
        self.assertIsNone(host.application);self.assertIsNone(host.center_lock)
        with self.open():pass
    def test_cli_redacts_failures_and_restores_signal_handler(self):
        from io import StringIO
        before=signal.getsignal(signal.SIGTERM);out=StringIO()
        with patch('scripts.community_platform_host.PlatformHost.open',side_effect=ValueError('credential value must never be logged')),contextlib.redirect_stdout(out):
            self.assertEqual(main(['--plan','/x','--center-keys','/y','--wechat-secret','/z']),2)
        self.assertEqual(out.getvalue(),'BACKEND_NOT_READY\n')
        self.assertEqual(signal.getsignal(signal.SIGTERM),before)
    @unittest.skipIf(os.geteuid()==0,'Actual nonroot CLI/Unix socket runs on Hosted')
    def test_actual_nonroot_cli_unix_health_sigterm_and_restart(self):
        args=[sys.executable,'-B','-m','scripts.community_platform_host','--plan',str(self.plan_path),
              '--center-keys',str(self.keys_path),'--wechat-secret',str(self.wechat_path)]
        for attempt in range(2):
            process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                deadline=time.monotonic()+8
                while not Path(self.plan['socket_path']).exists():
                    if process.poll() is not None or time.monotonic()>deadline:
                        out,err=process.communicate(timeout=2)
                        self.fail('Synthetic CLI did not open socket: '+out+err)
                    time.sleep(.025)
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                    connection.settimeout(3);connection.connect(self.plan['socket_path'])
                    connection.sendall(b'GET /community/health HTTP/1.0\r\nHost: uk.wenwenwenyiyiyi.work\r\nX-Xuanjun-Client-IP: 127.0.0.1\r\n\r\n')
                    raw=b''
                    while True:
                        chunk=connection.recv(4096)
                        if not chunk:break
                        raw+=chunk
                    self.assertIn(b'200 OK',raw)
                    self.assertEqual(json.loads(raw.split(b'\r\n\r\n',1)[1])['status'],'READY')
                for path in ('/merchant/workbench','/merchant/review','/community/portal','/community/entrypoints'):
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                        connection.settimeout(3);connection.connect(self.plan['socket_path'])
                        connection.sendall(('GET '+path+' HTTP/1.0\r\nHost: uk.wenwenwenyiyiyi.work\r\nX-Xuanjun-Client-IP: 127.0.0.1\r\n\r\n').encode())
                        raw=b''
                        while True:
                            chunk=connection.recv(65536)
                            if not chunk:break
                            raw+=chunk
                        self.assertIn(b'200 OK',raw.split(b'\r\n',1)[0])
                        body=raw.split(b'\r\n\r\n',1)[1]
                        if path.endswith('entrypoints'):
                            self.assertFalse(json.loads(body)['production_acceptance'])
                        else:self.assertIn(b'/community-preview/',body)
                process.send_signal(signal.SIGTERM)
                out,err=process.communicate(timeout=5)
                self.assertEqual(process.returncode,0,err)
                self.assertEqual(out,'')
                self.assertFalse(Path(self.plan['socket_path']).exists())
            finally:
                if process.poll() is None:
                    process.kill();process.communicate(timeout=3)

    def test_native_registration_requires_protected_host_optin_and_never_grants_staff(self):
        self.plan['registration_scenes']=['shop1'];self.write('host.json',self.plan)
        with self.open() as host:
            gateway=host.application.gateway
            gateway.provider.exchange=Mock(return_value=dict(appid=self.wechat['appid'],openid='first_native_customer'))
            token=gateway.login({'code':'first_native'})['session_token']
            uid=host.center.session(token)
            result=gateway.dispatch(token,dict(scene='shop1',operation='commerce.profile_read',params={}))
            self.assertEqual(result['user_id'],uid)
            self.assertEqual(host.center.db.execute('SELECT count(*) FROM members WHERE user_id=?',(uid,)).fetchone()[0],0)
            with self.assertRaises(PermissionError):
                gateway.dispatch(token,dict(scene='shop1',operation='commerce.project_summary',params={}))
            with self.assertRaises(PermissionError):
                gateway.dispatch(token,dict(scene='shop1',operation='community.profile',params={}))
        with self.open() as host:
            gateway=host.application.gateway
            gateway.provider.exchange=Mock(return_value=dict(appid=self.wechat['appid'],openid='first_native_customer'))
            again=gateway.login({'code':'next_native'})['session_token']
            self.assertEqual(host.center.session(again),uid)

    def test_root_guard_is_not_configurable(self):
        with patch('scripts.community_platform_host.os.geteuid',return_value=0):
            with self.assertRaisesRegex(PermissionError,'NONROOT_PLATFORM_HOST_REQUIRED'):_require_nonroot()

if __name__=='__main__':unittest.main()
