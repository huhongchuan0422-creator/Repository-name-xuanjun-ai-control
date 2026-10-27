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
        self.assertTrue(self.service.database.get('binding:tiktok')['verified'])
        self.assertEqual(self.service.operations_store.read_secret(core.TIKTOK_ACCESS_TOKEN_REF),'synthetic-access')

    def test_douyin_full_fake_callback_and_replay(self):
        self.configure('douyin')
        state = oauth.DouyinOAuthStateStore(self.root/'state/douyin-oauth-state').create_state(
            redirect_uri=ORIGIN+oauth.DOUYIN_REDIRECT_PATH, scopes=['user_info'],
            client_key_fingerprint=core._sha('synthetic-key')[:12])
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


# Actual child processes are used below; no provider/network calls are made.
import multiprocessing
import signal
from pr122_oauth_candidate.storage import Database


def process_consume(root, form, state, barrier, output):
    cls = oauth.TikTokOAuthStateStore if form == 'tiktok' else oauth.DouyinOAuthStateStore
    store = cls(Path(root)/('state/'+form+'-oauth-state'))
    barrier.wait(timeout=10)
    output.put(store.consume_state(state)['status'])


def process_submit(root, form, session, barrier, output):
    root = Path(root)
    service = core.SecureSecretsPortalService(root/'state',root/'ops')
    barrier.wait(timeout=10)
    result = getattr(service,'submit_'+form)(session['session_id'],session['csrf_token'],ORIGIN,
        {'client_key':'parallel-key','client_secret':'parallel-secret'})
    output.put(result['status'])


def process_crash(root, form, session, phase, sender):
    root = Path(root)
    service = core.SecureSecretsPortalService(root/'state', root/'ops')
    def checkpoint(point):
        if point == phase:
            sender.send('REACHED')
            signal.pause()
    service.database.checkpoint = checkpoint
    getattr(service,'submit_'+form)(session['session_id'],session['csrf_token'],ORIGIN,
                                   {'client_key':'new-key','client_secret':'new-secret'})


def process_callback(root, form, state, barrier, output, phase=None, sender=None):
    root = Path(root)
    service = core.SecureSecretsPortalService(root/'state',root/'ops')
    oauth.configure_state_root(root/'state')
    token = {'access_token':'activated-access','refresh_token':'activated-refresh',
        'open_id':'synthetic-open-id','scope':'user.info.basic' if form == 'tiktok' else 'user_info',
        'expires_in':3600}
    user = {'data':{'user':{'open_id':'synthetic-open-id'}}} if form == 'tiktok' else {'data':{'open_id':'synthetic-open-id'}}
    client = oauth.TikTokOpenApiClient if form == 'tiktok' else oauth.DouyinOpenApiClient
    def checkpoint(point):
        if point == phase:
            sender.send('REACHED'); signal.pause()
    if phase: service.database.checkpoint = checkpoint
    if barrier: barrier.wait(timeout=10)
    with patch.object(client,'exchange_access_token',return_value=token if form == 'tiktok' else {'data':token}), \
         patch.object(client,'user_info',return_value=user):
        result = getattr(oauth,'handle_'+form+'_oauth_callback')(service,ORIGIN,
            {'state':[state],'code':['synthetic']})
    if output: output.put(result['status'])


def process_state_crash(root, form, state, phase, sender):
    cls = oauth.TikTokOAuthStateStore if form == 'tiktok' else oauth.DouyinOAuthStateStore
    store = cls(Path(root)/('state/'+form+'-oauth-state'))
    def checkpoint(point):
        if point == phase:
            sender.send('REACHED'); signal.pause()
    store.database.checkpoint = checkpoint
    store.consume_state(state)


class AtomicityTests(unittest.TestCase):
    setUp = CandidateTests.setUp
    session = CandidateTests.session
    configure = CandidateTests.configure
    def state(self, form, **kwargs):
        cls = oauth.TikTokOAuthStateStore if form == 'tiktok' else oauth.DouyinOAuthStateStore
        store = cls(self.root/('state/'+form+'-oauth-state'))
        scopes = ['user.info.basic'] if form == 'tiktok' else ['user_info']
        return store, store.create_state(redirect_uri=ORIGIN+'/integrations/'+form+'/oauth/callback',
            scopes=scopes,client_key_fingerprint=core._sha('synthetic-key')[:12],**kwargs)

    def parallel(self, target, args, count=6):
        ctx = multiprocessing.get_context('fork')
        barrier, output = ctx.Barrier(count), ctx.Queue()
        children = [ctx.Process(target=target,args=(*args,barrier,output)) for _ in range(count)]
        try:
            for child in children: child.start()
            results = [output.get(timeout=20) for _ in children]
            for child in children:
                child.join(timeout=5)
                self.assertEqual(child.exitcode,0)
            return results
        finally:
            for child in children:
                if child.is_alive(): child.kill()
                child.join(timeout=5)
            output.close()

    def test_r1_both_providers_process_race_exactly_one_pass(self):
        for form in ('douyin','tiktok'):
            _, state = self.state(form)
            results = self.parallel(process_consume,(str(self.root),form,state['state']))
            self.assertEqual(results.count('PASS'),1)
            self.assertEqual(results.count('REJECTED'),5)

    def test_r1_expiry_and_restart_replay(self):
        for form in ('douyin','tiktok'):
            store, expired = self.state(form,now=core.utc_now()-timedelta(days=1))
            self.assertEqual(store.consume_state(expired['state'])['sanitized_error_code'],'STATE_EXPIRED')
            store, fresh = self.state(form)
            self.assertEqual(store.consume_state(fresh['state'])['status'],'PASS')
            reloaded = type(store)(store.root)
            self.assertEqual(reloaded.consume_state(fresh['state'])['sanitized_error_code'],'STATE_ALREADY_CONSUMED')

    def test_r1_write_failure_never_pass_and_can_recover(self):
        for form in ('douyin','tiktok'):
            store, state = self.state(form)
            with patch.object(store.database,'checkpoint',side_effect=OSError('synthetic')):
                with self.assertRaises(OSError): store.consume_state(state['state'])
            self.assertEqual(type(store)(store.root).consume_state(state['state'])['status'],'PASS')

    def test_r1_commit_ack_loss_does_not_allow_replay(self):
        for form in ('douyin','tiktok'):
            store, state = self.state(form)
            def checkpoint(point):
                if point == 'after_commit': raise OSError('synthetic')
            with patch.object(store.database,'checkpoint',side_effect=checkpoint):
                with self.assertRaises(OSError): store.consume_state(state['state'])
            self.assertEqual(type(store)(store.root).consume_state(state['state'])['sanitized_error_code'],'STATE_ALREADY_CONSUMED')

    def test_r2_both_provider_process_duplicate_rejected(self):
        for form in ('douyin','tiktok'):
            session = self.session(form)
            results = self.parallel(process_submit,(str(self.root),form,session))
            self.assertEqual(results.count('CONFIGURED'),1)
            self.assertEqual(results.count('REJECTED'),5)
            self.assertEqual(self.service.operations_store.read_secret(form.upper()+'_CLIENT_KEY'),'parallel-key')
            self.assertEqual(self.service.operations_store.read_secret(form.upper()+'_CLIENT_SECRET'),'parallel-secret')

    def test_r2_every_write_failure_preserves_old_pair_and_form(self):
        for form in ('douyin','tiktok'):
            self.configure(form)
            # attempts, key, audit, secret, audit, used_forms = six writes.
            for fail_at in range(1,7):
                session = self.session(form)
                calls = []
                def checkpoint(point):
                    if point.startswith('write:'):
                        calls.append(point)
                        if len(calls) == fail_at: raise OSError('synthetic partial write')
                with patch.object(self.service.database,'checkpoint',side_effect=checkpoint):
                    r = getattr(self.service,'submit_'+form)(session['session_id'],session['csrf_token'],ORIGIN,
                        {'client_key':'new-key','client_secret':'new-secret'})
                self.assertEqual(r['status'],'UNKNOWN')
                restored = core.SecureSecretsPortalService(self.root/'state',self.root/'ops')
                self.assertEqual(restored.operations_store.read_secret(form.upper()+'_CLIENT_KEY'),'synthetic-key')
                self.assertEqual(restored.operations_store.read_secret(form.upper()+'_CLIENT_SECRET'),'synthetic-secret')
                self.assertEqual(restored.sessions.get(session['session_id']).used_forms,{})

    def test_r2_sigkill_before_and_after_commit_restart_consistency(self):
        ctx = multiprocessing.get_context('fork')
        for form in ('douyin','tiktok'):
            self.configure(form)
            for phase in ('write:secret:'+form.upper()+'_CLIENT_KEY','before_commit','after_commit'):
                session = self.session(form)
                receiver,sender = ctx.Pipe(duplex=False)
                child = ctx.Process(target=process_crash,args=(str(self.root),form,session,phase,sender))
                child.start()
                try:
                    self.assertTrue(receiver.poll(10),'fault point not reached')
                    self.assertEqual(receiver.recv(),'REACHED')
                    child.kill();child.join(timeout=5)
                    self.assertEqual(child.exitcode,-signal.SIGKILL)
                    restored = core.SecureSecretsPortalService(self.root/'state',self.root/'ops')
                    used = restored.sessions.get(session['session_id']).used_forms
                    if phase == 'after_commit':
                        self.assertEqual(used,{form:'CONFIGURED'})
                        self.assertEqual(restored.operations_store.read_secret(form.upper()+'_CLIENT_KEY'),'new-key')
                        self.assertEqual(restored.operations_store.read_secret(form.upper()+'_CLIENT_SECRET'),'new-secret')
                    else:
                        self.assertEqual(used,{})
                        self.assertEqual(restored.operations_store.read_secret(form.upper()+'_CLIENT_KEY'),'synthetic-key')
                        self.assertEqual(restored.operations_store.read_secret(form.upper()+'_CLIENT_SECRET'),'synthetic-secret')
                finally:
                    if child.is_alive(): child.kill()
                    child.join(timeout=5); receiver.close(); sender.close()

    def callback(self, form, identity='synthetic-open-id', user_identity=None, fail_user=False):
        store,state = self.state(form)
        token = {'access_token':'new-access','refresh_token':'new-refresh','open_id':identity,
                 'scope':'user.info.basic' if form == 'tiktok' else 'user_info','expires_in':3600}
        user_identity = identity if user_identity is None else user_identity
        user = {'data':{'user':{'open_id':user_identity,'display_name':'Synthetic'}}} if form == 'tiktok' else {'data':{'open_id':user_identity,'nickname':'Synthetic'}}
        client = oauth.TikTokOpenApiClient if form == 'tiktok' else oauth.DouyinOpenApiClient
        response = token if form == 'tiktok' else {'data':token}
        with patch.object(client,'exchange_access_token',return_value=response), \
             patch.object(client,'user_info',side_effect=TimeoutError if fail_user else None,return_value=user):
            return getattr(oauth,'handle_'+form+'_oauth_callback')(self.service,ORIGIN,
                {'state':[state['state']],'code':['synthetic']})

    def protected(self, form):
        with self.service.database.transaction():
            return {key:self.service.database.get(key) for key in (
                'secret:'+form.upper()+'_ACCESS_TOKEN','secret:'+form.upper()+'_REFRESH_TOKEN',
                'binding:'+form,'lifecycle:'+form)}

    def test_r3_user_timeout_preserves_verified_old_generation(self):
        for form in ('douyin','tiktok'):
            self.configure(form)
            self.assertEqual(self.callback(form)['status'],'PASS')
            old = self.protected(form)
            result = self.callback(form,identity='other-account',fail_user=True)
            self.assertEqual(result['status'],'UNKNOWN')
            self.assertEqual(self.protected(form),old)
            self.assertNotIn('EXISTING',json.dumps(result))

    def test_r3_token_user_identity_mismatch_never_activated(self):
        for form in ('douyin','tiktok'):
            self.configure(form)
            self.assertEqual(self.callback(form,user_identity='other-account')['sanitized_error_code'],'ACCOUNT_IDENTITY_MISMATCH')
            self.assertTrue(all(v is None for v in self.protected(form).values()))

    def test_r3_existing_different_account_rejected(self):
        for form in ('douyin','tiktok'):
            self.configure(form); self.assertEqual(self.callback(form)['status'],'PASS')
            old = self.protected(form)
            self.assertEqual(self.callback(form,identity='different-account')['sanitized_error_code'],'ACCOUNT_BINDING_MISMATCH')
            self.assertEqual(self.protected(form),old)

    def test_r3_each_activation_write_failure_preserves_generation(self):
        for form in ('douyin','tiktok'):
            self.configure(form); self.assertEqual(self.callback(form)['status'],'PASS')
            old = self.protected(form)
            for fail_at in range(1,7):
                calls = []
                def checkpoint(point):
                    if point.startswith(('write:secret:','write:audit:','write:binding:','write:lifecycle:')):
                        calls.append(point)
                        if len(calls) == fail_at: raise OSError('synthetic')
                with patch.object(self.service.database,'checkpoint',side_effect=checkpoint):
                    result = self.callback(form)
                self.assertEqual(result['status'],'UNKNOWN')
                self.assertEqual(self.protected(form),old)

    def kill_at(self, target, args, signum=signal.SIGKILL):
        ctx = multiprocessing.get_context('fork')
        receiver,sender = ctx.Pipe(duplex=False)
        child = ctx.Process(target=target,args=(*args,sender))
        child.start()
        try:
            self.assertTrue(receiver.poll(10),'fault point not reached')
            self.assertEqual(receiver.recv(),'REACHED')
            os.kill(child.pid,signum); child.join(timeout=5)
            self.assertEqual(child.exitcode,-signum)
        finally:
            if child.is_alive(): child.kill()
            child.join(timeout=5); receiver.close(); sender.close()

    def test_r1_sigkill_durable_claim_and_rollback(self):
        for form in ('douyin','tiktok'):
            for phase in ('before_commit','after_commit'):
                store,state = self.state(form)
                self.kill_at(process_state_crash,(str(self.root),form,state['state'],phase))
                result = type(store)(store.root).consume_state(state['state'])
                self.assertEqual(result['status'],'REJECTED' if phase == 'after_commit' else 'PASS')

    def test_r3_same_state_callbacks_across_processes_one_pass(self):
        for form in ('douyin','tiktok'):
            self.configure(form); _, state = self.state(form)
            results = self.parallel(process_callback,(str(self.root),form,state['state']))
            self.assertEqual(results.count('PASS'),1)
            self.assertEqual(results.count('REJECTED'),5)

    def test_r3_sigkill_every_activation_write_and_commit(self):
        for form in ('douyin','tiktok'):
            self.configure(form); self.assertEqual(self.callback(form)['status'],'PASS')
            for phase in ('write:secret:'+form.upper()+'_ACCESS_TOKEN',
                          'write:secret:'+form.upper()+'_REFRESH_TOKEN',
                          'write:binding:'+form,'write:lifecycle:'+form,
                          'before_commit','after_commit'):
                old = self.protected(form)
                _, state = self.state(form)
                self.kill_at(process_callback,(str(self.root),form,state['state'],None,None,phase))
                self.service = core.SecureSecretsPortalService(self.root/'state',self.root/'ops')
                current = self.protected(form)
                if phase == 'after_commit':
                    self.assertEqual(current['secret:'+form.upper()+'_ACCESS_TOKEN']['value'],'activated-access')
                    self.assertEqual(current['secret:'+form.upper()+'_REFRESH_TOKEN']['value'],'activated-refresh')
                    self.assertTrue(current['binding:'+form]['verified'])
                else: self.assertEqual(current,old)
                cls = oauth.TikTokOAuthStateStore if form == 'tiktok' else oauth.DouyinOAuthStateStore
                self.assertEqual(cls(self.root/('state/'+form+'-oauth-state')).consume_state(state['state'])['status'],'REJECTED')

    def test_r2_sigterm_rolls_back_uncommitted_pair(self):
        for form in ('douyin','tiktok'):
            self.configure(form); session = self.session(form)
            self.kill_at(process_crash,(str(self.root),form,session,'write:secret:'+form.upper()+'_CLIENT_KEY'),signal.SIGTERM)
            restored = core.SecureSecretsPortalService(self.root/'state',self.root/'ops')
            self.assertEqual(restored.operations_store.read_secret(form.upper()+'_CLIENT_KEY'),'synthetic-key')
            self.assertEqual(restored.operations_store.read_secret(form.upper()+'_CLIENT_SECRET'),'synthetic-secret')
            self.assertEqual(restored.sessions.get(session['session_id']).used_forms,{})

    def test_r3_commit_ack_failure_reports_unknown_not_connected(self):
        for form in ('douyin','tiktok'):
            self.configure(form)
            def checkpoint(point):
                if point == 'after_commit': raise OSError('synthetic ack loss')
            with patch.object(self.service.database,'checkpoint',side_effect=checkpoint):
                result = self.callback(form)
            self.assertEqual(result['status'],'UNKNOWN')
            self.assertTrue(self.protected(form)['binding:'+form]['verified'])

    def test_r2_invalid_second_credential_keeps_old_generation(self):
        for form in ('douyin','tiktok'):
            self.configure(form); session = self.session(form)
            result = getattr(self.service,'submit_'+form)(session['session_id'],session['csrf_token'],ORIGIN,
                {'client_key':'different-key','client_secret':'synthetic\nbad-secret'})
            self.assertEqual(result['status'],'UNKNOWN')
            self.assertEqual(self.service.operations_store.read_secret(form.upper()+'_CLIENT_KEY'),'synthetic-key')
            self.assertEqual(self.service.operations_store.read_secret(form.upper()+'_CLIENT_SECRET'),'synthetic-secret')
            self.assertEqual(self.service.sessions.get(session['session_id']).used_forms,{})

    def test_r3_status_requires_current_valid_generation(self):
        self.configure('tiktok'); self.assertEqual(self.callback('tiktok')['status'],'PASS')
        self.assertTrue(oauth.tiktok_connection_status()['connected'])
        with self.service.database.transaction():
            binding = self.service.database.get('binding:tiktok')
            binding['lifecycle']['access_token_expires_at'] = (core.utc_now()-timedelta(seconds=1)).isoformat()
            self.service.database.put('binding:tiktok',binding)
        self.assertFalse(oauth.tiktok_connection_status()['connected'])

    def test_r3_changed_client_key_state_rejected(self):
        self.configure('tiktok'); _,state = self.state('tiktok')
        self.service.operations_store.store_secret(core.TIKTOK_CLIENT_KEY_REF,'changed','tiktok','readonly','test','synthetic')
        with patch.object(oauth.TikTokOpenApiClient,'exchange_access_token') as exchange:
            result = oauth.handle_tiktok_oauth_callback(self.service,ORIGIN,
                {'state':[state['state']],'code':['synthetic']})
            self.assertEqual(result['sanitized_error_code'],'CLIENT_KEY_CHANGED')
            exchange.assert_not_called()

    def test_database_private_and_symlink_rejected(self):
        self.assertEqual(self.service.database.path.stat().st_mode & 0o777,0o600)
        linked = self.root/'linked'; linked.symlink_to(self.root/'state',target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError,'SYMLINK'): Database(linked)


if __name__ == '__main__':
    unittest.main()
