"""Unix HTTP transport with pinned proxy boundary; provider/source success fixtures."""
import concurrent.futures
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock,patch
import test_community_mini_center_identity as center_fixture
from scripts.community_mini_application import MiniApplication
from scripts.community_mini_http import make_handler
from scripts.pr122_customer_source import TrustedNginxSource

class UnixMiniProxy(unittest.TestCase):
    def setUp(self):
        self.fx=center_fixture.ExistingCenterComposition('test_core_bytes_are_identical_to_explicit_website_pin');self.fx.setUp()
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.root.chmod(0o750)
        self.app=MiniApplication(self.fx.center,self.root/'state',self.fx.stage.api.bindings,
             self.fx.stage.api.bindings[self.fx.stage.customer],self.fx.scenes,self.fx.identity.appid,'a'*32)
        self.app.gateway.provider.exchange=Mock(return_value={'appid':self.fx.identity.appid,'openid':'openid1'})
        self.path=self.root/'mini.sock'
        self.server=self.app.listen_proxy(self.path,'https://example.test',65534,os.getegid())
    def tearDown(self):self.app.close();self.tmp.cleanup();self.fx.tearDown()
    def request(self,host='example.test',origins=(),source='192.0.2.1',code='proxy_code'):
        def client():
            conn=http.client.HTTPConnection('unused',timeout=3)
            sock=socket.socket(socket.AF_UNIX);sock.settimeout(3);sock.connect(str(self.path));conn.sock=sock
            try:
                raw=json.dumps({'code':code}).encode()
                conn.putrequest('POST','/mini/login',skip_host=True)
                conn.putheader('Host',host);conn.putheader('Content-Type','application/json')
                conn.putheader('Content-Length',str(len(raw)));conn.putheader('X-Xuanjun-Client-IP',source)
                for origin in origins:conn.putheader('Origin',origin)
                conn.endheaders(raw);response=conn.getresponse();return response.status,json.loads(response.read())
            finally:conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(client);self.server.handle_request();return future.result()
    def test_real_unix_peer_cannot_spoof_pinned_nginx_uid_by_header(self):
        # CI account/root are deliberately different from the pinned nobody UID.
        self.assertNotEqual(os.geteuid(),65534)
        self.assertEqual(self.request()[0],403)
        self.app.gateway.provider.exchange.assert_not_called()
    def test_https_origin_and_unix_source_fixture_reach_existing_account(self):
        with patch.object(TrustedNginxSource,'__call__',return_value='192.0.2.1') as source:
            status,body=self.request(origins=('https://example.test',))
        self.assertEqual(status,200);self.assertFalse(body['payment_enabled'])
        self.assertEqual(self.fx.center.session(body['result']['session_token']),self.fx.uid1)
        self.assertEqual(source.call_count,1)
    def test_real_matching_unix_peer_and_source_reach_existing_account(self):
        # Hosted and the domestic runner are non-root; the test pins their real
        # UID as the proxy fixture identity and exercises SO_PEERCRED unchanged.
        self.assertGreater(os.geteuid(),0)
        self.app.close()
        self.app=MiniApplication(self.fx.center,self.root/'state',self.fx.stage.api.bindings,
             self.fx.stage.api.bindings[self.fx.stage.customer],self.fx.scenes,self.fx.identity.appid,'a'*32)
        self.app.gateway.provider.exchange=Mock(return_value={'appid':self.fx.identity.appid,'openid':'openid1'})
        self.server=self.app.listen_proxy(self.path,'https://example.test',os.geteuid(),os.getegid())
        status,body=self.request()
        self.assertEqual(status,200)
        self.assertEqual(self.fx.center.session(body['result']['session_token']),self.fx.uid1)
    def test_wrong_host_cross_origin_and_duplicate_origin_never_exchange(self):
        for kwargs in ({'host':'evil.test'},{'origins':('https://evil.test',)},
                       {'origins':('https://example.test','https://example.test')}):
            self.assertEqual(self.request(**kwargs)[0],403)
        self.app.gateway.provider.exchange.assert_not_called()
    def test_proxy_uses_original_center_persistent_source_quota(self):
        with self.fx.center.tx():
            for _ in range(40):self.fx.center.limit('auth-source:192.0.2.1',40,300)
        with patch.object(TrustedNginxSource,'__call__',return_value='192.0.2.1'):
            self.assertEqual(self.request()[0],403)
        self.app.gateway.provider.exchange.assert_not_called()
    def test_socket_close_never_deletes_replaced_file(self):
        self.path.rename(self.root/'old.sock');self.path.write_text('preserve')
        self.app.close();self.assertEqual(self.path.read_text(),'preserve')
    def test_active_socket_cannot_be_replaced_by_second_listener(self):
        with self.assertRaises(ValueError):self.app.listen_proxy(self.path,'https://example.test',65534,os.getegid())
    def test_proxy_directory_must_allow_pinned_nginx_group_traversal(self):
        with MiniApplication(self.fx.center,self.root/'other-state',self.fx.stage.api.bindings,
                self.fx.stage.api.bindings[self.fx.stage.customer],self.fx.scenes,self.fx.identity.appid,'a'*32) as other:
            self.root.chmod(0o700)
            with self.assertRaises(PermissionError):other.listen_proxy(self.root/'other.sock','https://example.test',65534,os.getegid())
            self.assertFalse((self.root/'other.sock').exists())
    def test_proxy_requires_pinned_class_and_https_config(self):
        for origin,peer in [('http://example.test',TrustedNginxSource(65534)),
                            ('https://example.test',lambda *_:'192.0.2.1')]:
            with self.assertRaises(ValueError):make_handler(self.app.gateway,proxy_origin=origin,trusted_proxy=peer)
    def test_original_proxy_source_bytes_are_pinned(self):
        from scripts import pr122_customer_source
        self.assertEqual(hashlib.sha256(Path(pr122_customer_source.__file__).read_bytes()).hexdigest(),
                         '3e8d531ede69577b72b6ee9089fdc8f481b2f91578f19e0e44d1841c168f3471')

if __name__=='__main__':unittest.main()
