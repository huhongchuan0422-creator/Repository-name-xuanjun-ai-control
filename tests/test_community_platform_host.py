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
    def test_unknown_provider_subject_does_not_create_an_account(self):
        with self.open() as host:
            before=host.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
            host.application.gateway.provider.exchange=Mock(return_value=dict(appid=self.wechat['appid'],openid='unbound'))
            from scripts.community_mini_login import LoginUnavailable
            with self.assertRaises(LoginUnavailable):host.application.gateway.login({'code':'unknown_native'})
            self.assertEqual(host.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
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
