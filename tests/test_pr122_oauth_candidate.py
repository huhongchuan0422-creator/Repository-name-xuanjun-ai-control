"""Offline tests. All secrets and provider responses below are synthetic."""
import ast
import json
import importlib.util
import io
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

ORIGIN = 'https://wenwenwenyiyiyi.work'


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.service = core.SecureSecretsPortalService(self.root/'state', self.root/'ops')
        oauth.configure_state_root(self.root/'state')

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


if __name__ == '__main__':
    unittest.main()
