"""Offline tests. All secrets and provider responses below are synthetic."""
import ast
import json
import importlib.util
import io
import http.client
import threading
import socket
import hashlib
import urllib.parse
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(os.environ.get('PR122_CANDIDATE_ROOT',
            str(Path(__file__).resolve().parents[1]/'deploy/pr122-oauth-candidate')))
sys.path.insert(0, str(ROOT))
from pr122_oauth_candidate import core, oauth
from pr122_oauth_candidate import http_candidate

ORIGIN = 'https://wenwenwenyiyiyi.work'


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.service = core.SecureSecretsPortalService(self.root/'state', self.root/'ops')
        oauth.configure_state_root(self.root/'state')
        transport = patch('urllib.request.urlopen',side_effect=AssertionError('EXTERNAL_NETWORK_FORBIDDEN'))
        blocked = transport.start()
        self.addCleanup(transport.stop)
        self.addCleanup(blocked.assert_not_called)

    def session(self, form):
        return self.service.create_session('synthetic-customer', 'synthetic-account', ORIGIN, [form])

    def configure(self, form):
        s = self.session(form)
        payload = {'client_key': 'synthetic-key', 'client_secret': 'synthetic-secret'}
        result = getattr(self.service, 'submit_'+form)(s['session_id'], s['csrf_token'], ORIGIN, payload)
        self.assertEqual(result['status'], 'CONFIGURED')
        self.assertNotIn('synthetic-secret', json.dumps(result))
        return s

    def test_import_boundary(self):
        forbidden = {'accounts', 'database', 'trading_execution', 'binance_integration', 'sqlalchemy'}
        for file in (ROOT/'pr122_oauth_candidate').glob('*.py'):
            tree = ast.parse(file.read_text())
            for node in ast.walk(tree):
                names = [x.name for x in node.names] if isinstance(node, ast.Import) else (
                    [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
                self.assertFalse({x.split('.')[0] for x in names} & forbidden, file.name)
            self.assertNotIn('/opt/trading-system', file.read_text())
        self.assertFalse(forbidden & set(sys.modules))

    def test_manifest_matches_all_modules(self):
        manifest = json.loads((ROOT/'MANIFEST.json').read_text())
        actual = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (ROOT/'pr122_oauth_candidate').glob('*.py')}
        self.assertEqual(manifest['files'],actual)
        self.assertFalse(manifest['production_change'])

    def test_forbidden_forms(self):
        for forms in (None, [], ['binance_trading'], ['finance_collection_readonly'], ['tiktok','telegram']):
            with self.assertRaisesRegex(ValueError, 'OAUTH_FORMS_ONLY'):
                self.service.create_session('c', 'a', ORIGIN, forms)
        self.assertFalse(hasattr(self.service, 'submit_binance_credential'))

    def test_render_both_providers(self):
        for form in ('douyin','tiktok'):
            s = self.session(form)
            response = getattr(oauth, 'render_'+form+'_page')(self.service,s['session_id'])
            self.assertEqual(response[0],200)
            self.assertIn('/submit/'+form,response[2])

    def test_cross_form_rejected(self):
        s = self.session('douyin')
        r = self.service.submit_tiktok(s['session_id'],s['csrf_token'],ORIGIN,
                                      {'client_key':'synthetic','client_secret':'synthetic'})
        self.assertEqual(r['sanitized_error_code'],'FORM_NOT_ALLOWED')
        self.assertFalse(list((self.root/'ops/values').glob('*')))

    def test_csrf_and_origin_rejected(self):
        s = self.session('tiktok')
        for csrf, origin, expected in [('bad',ORIGIN,'CSRF_INVALID'),
                                      (s['csrf_token'],'https://wrong.invalid','ORIGIN_INVALID')]:
            r = self.service.submit_tiktok(s['session_id'],csrf,origin,{})
            self.assertEqual(r['sanitized_error_code'],expected)

    def test_form_replay_rejected(self):
        s = self.configure('tiktok')
        r = self.service.submit_tiktok(s['session_id'],s['csrf_token'],ORIGIN,{})
        self.assertEqual(r['sanitized_error_code'],'FORM_ALREADY_USED')

    def test_expired_form_rejected(self):
        s = self.session('douyin')
        record = self.service.sessions.get(s['session_id'])
        record.expires_at = core.utc_now()-timedelta(seconds=1)
        self.service.sessions.save(record)
        r = self.service.submit_douyin(s['session_id'],s['csrf_token'],ORIGIN,{})
        self.assertEqual(r['sanitized_error_code'],'SESSION_EXPIRED')

    def test_state_root_and_restart(self):
        s = self.configure('douyin')
        restored = core.SecureSecretsPortalService(self.root/'state',self.root/'ops')
        self.assertEqual(restored.sessions.get(s['session_id']).used_forms,{'douyin':'CONFIGURED'})
        self.assertEqual(restored.operations_store.read_secret(core.DOUYIN_CLIENT_SECRET_REF),'synthetic-secret')
        for f in (self.root/'ops/values').glob('*'):
            self.assertEqual(f.stat().st_mode & 0o777,0o600)

    def test_missing_key_start_and_bad_callback(self):
        url, result = oauth.handle_tiktok_oauth_start(self.service,ORIGIN)
        self.assertIsNone(url)
        self.assertEqual(result['status'],'REJECTED')
        for func in (oauth.handle_tiktok_oauth_callback,oauth.handle_douyin_oauth_callback):
            self.assertEqual(func(self.service,ORIGIN,{})['status'],'REJECTED')

    def test_tiktok_redirect_mismatch_then_replay(self):
        self.configure('tiktok')
        url, _ = oauth.handle_tiktok_oauth_start(self.service,ORIGIN)
        state = parse_qs(urlsplit(url).query)['state'][0]
        query = {'state':[state],'code':['synthetic-code']}
        r = oauth.handle_tiktok_oauth_callback(self.service,'https://wrong.invalid',query)
        self.assertEqual(r['sanitized_error_code'],'REDIRECT_URI_MISMATCH')
        self.assertEqual(oauth.handle_tiktok_oauth_callback(self.service,ORIGIN,query)['status'],'REJECTED')

    def test_exchange_failure_is_bounded(self):
        self.configure('tiktok')
        url, _ = oauth.handle_tiktok_oauth_start(self.service,ORIGIN)
        state = parse_qs(urlsplit(url).query)['state'][0]
        with patch.object(oauth.TikTokOpenApiClient,'exchange_access_token',side_effect=TimeoutError):
            r = oauth.handle_tiktok_oauth_callback(self.service,ORIGIN,{'state':[state],'code':['synthetic']})
        self.assertEqual(r['sanitized_error_code'],'AUTH_CODE_EXCHANGE_FAILED')

    def test_tiktok_full_fake_callback_and_replay(self):
        self.configure('tiktok')
        url, _ = oauth.handle_tiktok_oauth_start(self.service,ORIGIN)
        state = parse_qs(urlsplit(url).query)['state'][0]
        query = {'state':[state],'code':['synthetic']}
        token = {'access_token':'synthetic-access', 'refresh_token':'synthetic-refresh',
                 'open_id':'synthetic-open-id','scope':'user.info.basic','expires_in':3600}
        user = {'data':{'user':{'open_id':'synthetic-open-id','display_name':'Synthetic'}}}
        with patch.object(oauth.TikTokOpenApiClient,'exchange_access_token',return_value=token), \
             patch.object(oauth.TikTokOpenApiClient,'user_info',return_value=user):
            result = oauth.handle_tiktok_oauth_callback(self.service,ORIGIN,query)
        self.assertEqual(result['status'],'PASS')
        self.assertNotIn('synthetic-access',json.dumps(result))
        self.assertNotIn('synthetic-refresh',json.dumps(result))
        self.assertEqual(oauth.handle_tiktok_oauth_callback(self.service,ORIGIN,query)['status'],'REJECTED')
        self.assertTrue((self.root/'state/tiktok-token-state').is_dir())
        self.assertEqual(self.service.operations_store.read_secret(core.TIKTOK_ACCESS_TOKEN_REF),'synthetic-access')

    def test_douyin_full_fake_callback_and_replay(self):
        self.configure('douyin')
        state = oauth.DouyinOAuthStateStore(self.root/'state/douyin-oauth-state').create_state(
            redirect_uri=ORIGIN+oauth.DOUYIN_REDIRECT_PATH, scopes=['user_info'],
            client_key_fingerprint='synthetic')
        query = {'state':[state['state']],'code':['synthetic']}
        token = {'data': {'access_token':'synthetic-access','refresh_token':'synthetic-refresh',
                         'open_id':'synthetic-open-id','scope':'user_info','expires_in':3600}}
        user = {'data':{'open_id':'synthetic-open-id','nickname':'Synthetic'}}
        with patch.object(oauth.DouyinOpenApiClient,'exchange_access_token',return_value=token), \
             patch.object(oauth.DouyinOpenApiClient,'user_info',return_value=user):
            result = oauth.handle_douyin_oauth_callback(self.service,ORIGIN,query)
        self.assertEqual(result['status'],'PASS')
        self.assertNotIn('synthetic-access',json.dumps(result))
        self.assertNotIn('synthetic-refresh',json.dumps(result))
        self.assertEqual(oauth.handle_douyin_oauth_callback(self.service,ORIGIN,query)['status'],'REJECTED')
        self.assertEqual(self.service.operations_store.read_secret(core.DOUYIN_ACCESS_TOKEN_REF),'synthetic-access')


class InventoryTests(unittest.TestCase):
    def setUp(self):
        source = Path(os.environ.get('PR122_INVENTORY_SOURCE',
                      str(Path(__file__).resolve().parents[1]/'scripts/pr122_domestic_channel_inventory.py')))
        spec = importlib.util.spec_from_file_location('inventory_under_test',source)
        self.inventory = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.inventory)

    def test_wrong_host_never_runs_commands(self):
        with patch.object(self.inventory.os,'uname',return_value=SimpleNamespace(nodename='wrong')), \
             patch.object(self.inventory,'command') as command:
            with self.assertRaises(SystemExit):
                self.inventory.main()
            command.assert_not_called()

    def test_inventory_does_not_emit_sudo_policy(self):
        calls = []
        def command(args):
            calls.append(args)
            if args[0] == 'sudo':
                return SimpleNamespace(returncode=0,stdout='NOPASSWD: /synthetic-sensitive-policy\n')
            if args[0] == 'ss':
                return SimpleNamespace(returncode=0,stdout='LISTEN 0 5 127.0.0.1:19444 0.0.0.0:*\n')
            return SimpleNamespace(returncode=0,stdout='Id=test.service\nActiveState=active\n')
        output = io.StringIO()
        with patch.object(self.inventory.os,'uname',return_value=SimpleNamespace(nodename='iZvt5t8tlrm8oiZ')), \
             patch.object(self.inventory.pwd,'getpwuid',return_value=SimpleNamespace(pw_name='githubrunner')), \
             patch.object(self.inventory,'command',side_effect=command),redirect_stdout(output):
            self.inventory.main()
        value = json.loads(output.getvalue())
        self.assertEqual(value['loopback_tcp_ports'],[19444])
        self.assertFalse(value['production_mutation'])
        self.assertNotIn('synthetic-sensitive',output.getvalue())
        self.assertIn(['sudo','-n','-l'],calls)
        self.assertTrue(all(c[0] in {'ss','systemctl','sudo'} for c in calls))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.server = http_candidate.make_server(root/'state',root/'ops')
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup)
        transport = patch('urllib.request.urlopen',side_effect=AssertionError('EXTERNAL_NETWORK_FORBIDDEN'))
        blocked = transport.start()
        self.addCleanup(transport.stop)
        self.addCleanup(blocked.assert_not_called)

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def request(self,method,path,body=None,headers=None):
        conn = http.client.HTTPConnection(*self.server.server_address,timeout=5)
        base = {'Host':http_candidate.HOST,'X-Forwarded-Proto':'https'}
        base.update(headers or {})
        try:
            conn.request(method,path,body,base)
            response = conn.getresponse()
            return response.status,dict(response.getheaders()),response.read().decode()
        finally:
            conn.close()

    def test_health_is_not_production_ready(self):
        status,headers,body = self.request('GET','/healthz')
        self.assertEqual(status,200)
        self.assertFalse(json.loads(body)['production_accepted'])
        self.assertIn('Content-Security-Policy',headers)

    def test_wrong_host_and_plaintext_rejected(self):
        for headers in ({'Host':'wrong.invalid'},{'X-Forwarded-Proto':'http'}):
            self.assertEqual(self.request('GET','/healthz',headers=headers)[0],400)

    def test_old_capabilities_are_never_faked(self):
        for method,path in [('POST','/submit/siliconflow'),('POST','/telegram-webhook/example'),
                            ('GET','/telegram-canary/status'),('POST','/integrations/tiktok/disconnect')]:
            self.assertEqual(self.request(method,path)[0],503)

    def test_provider_calls_disabled_by_default(self):
        with patch.object(oauth.TikTokOpenApiClient,'exchange_access_token') as exchange:
            self.assertEqual(self.request('GET',oauth.TIKTOK_REDIRECT_PATH+'?state=x&code=x')[0],503)
            exchange.assert_not_called()

    def test_http_render_submit_and_replay(self):
        service = self.server.portal_service
        session = service.create_session('synthetic','synthetic',ORIGIN,['tiktok'])
        self.assertEqual(self.request('GET','/p/'+session['session_id'])[0],200)
        body = urllib.parse.urlencode({'session_id':session['session_id'],
                'csrf_token':session['csrf_token'],'client_key':'synthetic-key',
                'client_secret':'synthetic-secret'})
        headers = {'Origin':ORIGIN,'Content-Type':'application/x-www-form-urlencoded'}
        status,_,response = self.request('POST','/submit/tiktok',body,headers)
        self.assertEqual(status,200)
        self.assertNotIn('synthetic-secret',response)
        status,_,_ = self.request('POST','/submit/tiktok',body,headers)
        self.assertEqual(status,400)

    def test_body_and_origin_limits(self):
        self.assertEqual(self.request('POST','/submit/tiktok','x=1')[0],403)
        headers = {'Origin':ORIGIN,'Content-Type':'application/x-www-form-urlencoded'}
        self.assertEqual(self.request('POST','/submit/tiktok','x='+'a'*8192,headers)[0],413)
        self.assertEqual(self.request('POST','/submit/tiktok','x=1&x=2',headers)[0],400)
        self.assertEqual(self.request('POST','/submit/tiktok','x=1',{'Origin':ORIGIN,'Content-Type':'application/json'})[0],415)

    def test_second_state_root_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'ONE_STATE_ROOT_PER_PROCESS'):
            http_candidate.make_server(Path(self.tmp.name)/'second',Path(self.tmp.name)/'other')

    def test_duplicate_content_length_rejected(self):
        conn = http.client.HTTPConnection(*self.server.server_address,timeout=5)
        try:
            conn.putrequest('POST','/submit/tiktok',skip_host=True)
            for key,value in [('Host',http_candidate.HOST),('X-Forwarded-Proto','https'),
                              ('Origin',ORIGIN),('Content-Length','0'),('Content-Length','0')]:
                conn.putheader(key,value)
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(response.status,400)
            response.read()
        finally:
            conn.close()


class FactoryTests(unittest.TestCase):
    def test_bind_failure_does_not_deadlock_or_keep_global_lease(self):
        with tempfile.TemporaryDirectory() as directory,socket.socket() as occupied:
            root = Path(directory)
            occupied.bind(('127.0.0.1',0))
            occupied.listen(1)
            with self.assertRaises(OSError):
                http_candidate.make_server(root/'failed',root/'ops',port=occupied.getsockname()[1])
            server = http_candidate.make_server(root/'fresh',root/'ops')
            server.server_close()


if __name__ == '__main__':
    unittest.main()
