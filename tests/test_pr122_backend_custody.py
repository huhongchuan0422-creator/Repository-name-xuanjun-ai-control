import copy
import hashlib
import http.client
import json
import multiprocessing
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'deploy/pr122-oauth-candidate'), str(ROOT/'deploy/pr122-backend-migration')]
import custody
import isolated_runtime
from pr122_oauth_candidate import core, oauth
from pr122_oauth_candidate.storage import Database
from pr122_oauth_candidate.tiktok import TikTokOAuthStateStore

GENERATION = 'a'*64
CUTOVER = 'synthetic-cutover-1'
SOURCE_ID = 'account-source-1234567890'
SYNTHETIC_SECRET = 'SYNTHETIC_PRIVATE_VALUE_DO_NOT_EMIT'


def fixture():
    snapshot = dict(schema_version=1, source_generation=GENERATION, cutover_id=CUTOVER,
                    sessions=[], secrets={}, oauth_states={}, lifecycles={}, legacy_bindings={})
    fence = dict(source_host=custody.SOURCE_HOST, target_host=custody.TARGET_HOST,
                 source_sha256=custody.SOURCE_SHA256, source_generation=GENERATION,
                 cutover_id=CUTOVER, writer_fenced=True, inflight_requests=0,
                 account_identity_hashes={'tiktok': custody.digest(SOURCE_ID)})
    return snapshot, fence


def add_clients(snapshot):
    for name, value in [('CLIENT_KEY', 'synthetic-client'), ('CLIENT_SECRET', SYNTHETIC_SECRET)]:
        snapshot['secrets']['TIKTOK_'+name] = dict(value=value, provider='tiktok', scope='readonly',
            purpose='synthetic-test', actor='test', metadata={}, value_path='/MUST/NOT/OPEN')


def add_session(snapshot):
    nonce = 'synthetic-csrf'
    snapshot['sessions'] = [dict(submission_id='portal_synthetic', customer_id='customer-test',
        account_id='account-test', exchange='UNIFIED', credential_schema='UNIFIED_SECURE_SECRETS_PORTAL_V1',
        required_credential_types=['tiktok'], created_at='2026-10-15T00:00:00+00:00',
        expires_at='2099-10-15T01:00:00+00:00', status='PENDING', nonce=nonce,
        attempt_count=2, request_correlation_id=custody.ORIGIN, token_hash=custody.digest(nonce),
        portal_origin=custody.ORIGIN, attempts={'tiktok': 2}, used_forms={'tiktok': 'CONFIGURED'},
        idempotency_key='synthetic-idempotency', result={'status': 'CONFIGURED'}, used_at=None)]


def add_state(snapshot, consumed=None):
    add_clients(snapshot)
    snapshot['oauth_states']['tiktok'] = [dict(state_hash=custody.digest('synthetic-state'),
        redirect_uri=custody.ORIGIN+'/integrations/tiktok/oauth/callback', scopes=['user.info.basic'],
        client_key_fingerprint=custody.digest('synthetic-client')[:12],
        created_at='2026-10-15T00:00:00+00:00', expires_at='2099-10-15T01:00:00+00:00',
        consumed_at=consumed)]


def add_tokens(snapshot, inactive=False):
    add_clients(snapshot)
    for name, value in [('ACCESS_TOKEN', 'synthetic-access-token'), ('REFRESH_TOKEN', 'synthetic-refresh-token')]:
        snapshot['secrets']['TIKTOK_'+name] = dict(value=value, provider='tiktok', metadata={})
    lifecycle = dict(token_state_version=1, open_id_masked=custody.masked(SOURCE_ID),
        union_id_masked='MISSING', client_key_fingerprint=custody.digest('synthetic-client')[:12],
        granted_scopes=['user.info.basic'], access_token_expires_at='2099-10-15T01:00:00+00:00',
        refresh_token_expires_at='2099-11-15T01:00:00+00:00', revoked=inactive,
        reauthorization_required=inactive)
    snapshot['lifecycles']['tiktok'] = lifecycle
    snapshot['legacy_bindings']['tiktok'] = dict(status='CONNECTED', account={
        'open_id_masked': custody.masked(SOURCE_ID)})


def verifier(provider, records):
    return dict(raw_open_id=SOURCE_ID,
        access_token_sha256=custody.digest(records['TIKTOK_ACCESS_TOKEN']['value']),
        account=dict(status='PASS', open_id_masked=custody.masked(SOURCE_ID),
                     union_id_masked='MISSING', display_name='Synthetic Test', avatar_present=False))


def child_prepare(parent, snapshot, fence, queue):
    try:
        custody.prepare_generation(parent, snapshot, generation=GENERATION,
                                   cutover_id=CUTOVER, fence=fence)
        queue.put('PREPARED')
    except custody.Hold as error:
        queue.put(str(error))


def child_interrupt(parent, snapshot, fence):
    def crash(point):
        if point == 'MAIN_COMMITTED':
            os._exit(73)
    custody.prepare_generation(parent, snapshot, generation=GENERATION,
                               cutover_id=CUTOVER, fence=fence, checkpoint=crash)


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pr122-custody-test-')
        self.parent = Path(self.temp.name)
        self.snapshot, self.fence = fixture()
        self.target = self.parent/('handoff-'+CUTOVER)

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, **kwargs):
        return custody.prepare_generation(self.parent, self.snapshot, generation=GENERATION,
            cutover_id=CUTOVER, fence=self.fence, **kwargs)

    def rejected(self, code, **kwargs):
        with self.assertRaisesRegex(custody.Hold, code):
            self.prepare(**kwargs)
        self.assertFalse(self.target.exists())

    def test_empty_generation_is_private_and_does_not_activate(self):
        before = copy.deepcopy(self.snapshot)
        receipt = self.prepare()
        self.assertEqual(self.snapshot, before)
        self.assertFalse(receipt['activated'])
        self.assertFalse(receipt['production_approved'])
        self.assertTrue((self.target/'READY.json').exists())
        self.assertFalse((self.parent/'current').exists())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.target/'oauth-candidate.sqlite3').stat().st_mode), 0o600)

    def test_session_identity_csrf_attempts_used_forms_and_idempotency_preserved(self):
        add_session(self.snapshot)
        self.prepare()
        service = core.SecureSecretsPortalService(self.target, self.target/'operations')
        actual = service.sessions.get('portal_synthetic')
        self.assertEqual(service.sessions._serialize(actual), self.snapshot['sessions'][0])
        self.assertEqual(actual.attempts, {'tiktok': 2})
        self.assertEqual(service._validate_submit('portal_synthetic', 'synthetic-csrf', custody.ORIGIN,
                         None, None, 'tiktok')['sanitized_error_code'], 'FORM_ALREADY_USED')

    def test_expired_session_stays_expired(self):
        add_session(self.snapshot)
        self.snapshot['sessions'][0]['expires_at'] = '2026-10-15T01:00:00+00:00'
        self.prepare()
        service = core.SecureSecretsPortalService(self.target, self.target/'operations')
        self.assertEqual(service._validate_submit('portal_synthetic', 'synthetic-csrf', custody.ORIGIN,
                         None, None, 'tiktok')['sanitized_error_code'], 'SESSION_EXPIRED')

    def test_legacy_mixed_trading_session_not_silently_dropped(self):
        add_session(self.snapshot)
        self.snapshot['sessions'][0]['required_credential_types'] = ['tiktok', 'binance']
        self.rejected('LEGACY_MIXED_SESSION')

    def test_multi_oauth_form_renderer_gap_rejected_before_side_effect(self):
        add_session(self.snapshot)
        self.snapshot['sessions'][0]['required_credential_types'] = ['tiktok', 'douyin']
        self.rejected('LEGACY_MIXED_SESSION')

    def test_duplicate_session_rejected(self):
        add_session(self.snapshot)
        self.snapshot['sessions'].append(copy.deepcopy(self.snapshot['sessions'][0]))
        self.rejected('SESSION_ID_INVALID_OR_DUPLICATE')

    def test_wrong_origin_rejected(self):
        add_session(self.snapshot)
        self.snapshot['sessions'][0]['portal_origin'] = 'https://invalid.example'
        self.rejected('SESSION_ORIGIN_MISMATCH')

    def test_csrf_hash_mismatch_rejected(self):
        add_session(self.snapshot)
        self.snapshot['sessions'][0]['token_hash'] = 'f'*64
        self.rejected('SESSION_CSRF_HASH_MISMATCH')

    def test_timezone_less_session_rejected(self):
        add_session(self.snapshot)
        self.snapshot['sessions'][0]['created_at'] = '2026-10-15T00:00:00'
        self.rejected('TIMEZONE_REQUIRED')

    def test_negative_or_bool_attempts_rejected(self):
        for bad in (-1, True):
            with self.subTest(value=bad):
                add_session(self.snapshot)
                self.snapshot['sessions'][0]['attempts']['tiktok'] = bad
                self.rejected('SESSION_ATTEMPTS_INVALID')

    def test_new_state_consumed_once_after_conversion_and_restart(self):
        add_state(self.snapshot)
        self.prepare()
        root = self.target/'tiktok-oauth-state'
        self.assertEqual(TikTokOAuthStateStore(root).consume_state('synthetic-state')['status'], 'PASS')
        self.assertEqual(TikTokOAuthStateStore(root).consume_state('synthetic-state')['sanitized_error_code'], 'STATE_ALREADY_CONSUMED')

    def test_consumed_state_remains_consumed(self):
        add_state(self.snapshot, '2026-10-15T00:01:00+00:00')
        self.prepare()
        self.assertEqual(TikTokOAuthStateStore(self.target/'tiktok-oauth-state').consume_state('synthetic-state')['sanitized_error_code'], 'STATE_ALREADY_CONSUMED')

    def test_state_client_binding_mismatch_rejected(self):
        add_state(self.snapshot)
        self.snapshot['oauth_states']['tiktok'][0]['client_key_fingerprint'] = '0'*12
        self.rejected('OAUTH_CLIENT_BINDING_MISMATCH')

    def test_state_redirect_or_privileged_scope_rejected(self):
        for field, bad, code in [('redirect_uri','https://invalid.example','OAUTH_REDIRECT_MISMATCH'),
                                 ('scopes',['video.publish'],'OAUTH_SCOPE_INVALID')]:
            with self.subTest(field=field):
                self.snapshot, self.fence = fixture()
                add_state(self.snapshot)
                self.snapshot['oauth_states']['tiktok'][0][field] = bad
                self.rejected(code)

    def test_partial_client_pair_rejected(self):
        add_clients(self.snapshot)
        del self.snapshot['secrets']['TIKTOK_CLIENT_SECRET']
        self.rejected('PARTIAL_CREDENTIAL_PAIR')

    def test_trading_secretref_rejected(self):
        self.snapshot['secrets']['BINANCE_API_KEY'] = dict(value=SYNTHETIC_SECRET, provider='binance')
        self.rejected('OAUTH_SECRETREFS_ONLY')

    def test_wrong_secret_provider_rejected(self):
        add_clients(self.snapshot)
        self.snapshot['secrets']['TIKTOK_CLIENT_SECRET']['provider'] = 'douyin'
        self.rejected('SECRET_PROVIDER_MISMATCH')

    def test_active_legacy_token_cannot_be_accepted_without_verifier(self):
        add_tokens(self.snapshot)
        self.rejected('LIVE_IDENTITY_VERIFICATION_ADAPTER_REQUIRED')

    def test_verified_exact_identity_token_pair_activates_only_offline_binding(self):
        add_tokens(self.snapshot)
        receipt = self.prepare(verify_identity=verifier)
        oauth.configure_state_root(self.target)
        self.assertTrue(oauth.tiktok_connection_status()['connected'])
        self.assertFalse(receipt['activated'])
        self.assertNotIn(SYNTHETIC_SECRET, json.dumps(receipt))
        self.assertNotIn(SOURCE_ID, json.dumps(receipt))

    def test_masked_collision_without_exact_anchor_rejected(self):
        add_tokens(self.snapshot)
        self.fence['account_identity_hashes'] = {}
        self.rejected('EXACT_PRIVATE_ACCOUNT_IDENTITY_ANCHOR_REQUIRED', verify_identity=verifier)

    def test_wrong_token_identity_or_account_rejected(self):
        add_tokens(self.snapshot)
        def bad(provider, records):
            result = verifier(provider, records)
            result['access_token_sha256'] = '0'*64
            return result
        self.rejected('TOKEN_IDENTITY_PROOF_MISMATCH', verify_identity=bad)

    def test_verifier_exception_cannot_disclose_secret_or_write_target(self):
        add_tokens(self.snapshot)
        def failed(*args):
            raise ValueError(SYNTHETIC_SECRET)
        self.rejected('IDENTITY_VERIFICATION_FAILED_PRESERVE_SOURCE', verify_identity=failed)

    def test_revoked_binding_stays_inactive_without_blocking_future_binding_key(self):
        add_tokens(self.snapshot, inactive=True)
        self.prepare()
        db = Database(self.target)
        self.assertIsNone(db.get('binding:tiktok'))
        self.assertIsNotNone(db.get('migration:inactive:tiktok'))
        oauth.configure_state_root(self.target)
        self.assertFalse(oauth.tiktok_connection_status()['connected'])

    def test_legacy_disconnected_stays_disconnected(self):
        add_tokens(self.snapshot)
        self.snapshot['legacy_bindings']['tiktok'] = {'status': 'DISCONNECTED'}
        self.prepare()
        oauth.configure_state_root(self.target)
        self.assertFalse(oauth.tiktok_connection_status()['connected'])

    def test_expired_token_is_preserved_without_network_verification_or_activation(self):
        add_tokens(self.snapshot)
        self.snapshot['lifecycles']['tiktok']['access_token_expires_at'] = '2026-10-15T01:00:00+00:00'
        self.prepare()
        self.assertIsNotNone(Database(self.target).get('secret:TIKTOK_ACCESS_TOKEN'))
        self.assertIsNone(Database(self.target).get('binding:tiktok'))

    def test_privileged_token_scope_is_not_imported(self):
        add_tokens(self.snapshot)
        self.snapshot['lifecycles']['tiktok']['granted_scopes'] = ['video.publish']
        self.rejected('TOKEN_SCOPE_INVALID')

    def test_unknown_or_mismatched_source_and_unfenced_writer_rejected(self):
        for field, bad in [('writer_fenced',False),('inflight_requests',1),('source_sha256','0'*64),
                           ('source_host','wrong'),('cutover_id','wrong')]:
            with self.subTest(field=field):
                self.snapshot, self.fence = fixture()
                self.fence[field] = bad
                self.rejected('PRIVATE_FENCED_SOURCE_ATTESTATION_REQUIRED')

    def test_snapshot_generation_mismatch_rejected(self):
        self.snapshot['source_generation'] = '0'*64
        self.rejected('SNAPSHOT_SOURCE_BINDING_MISMATCH')

    def test_nonfinite_data_and_size_limit_rejected(self):
        self.snapshot['extra'] = float('inf')
        self.rejected('SNAPSHOT_FORMAT_INVALID')
        self.snapshot, self.fence = fixture()
        self.snapshot['extra'] = 'x'*2000001
        self.rejected('SNAPSHOT_SIZE_LIMIT')

    def test_existing_target_is_not_overwritten(self):
        self.prepare()
        before = (self.target/'HANDOFF.json').read_bytes()
        with self.assertRaisesRegex(custody.Hold, 'TARGET_ALREADY_EXISTS_NO_BLIND_RETRY'):
            self.prepare()
        self.assertEqual((self.target/'HANDOFF.json').read_bytes(), before)

    def test_symlink_or_world_readable_parent_rejected(self):
        link = self.parent/'link'
        link.symlink_to(self.parent, target_is_directory=True)
        with self.assertRaisesRegex(custody.Hold, 'TARGET_PARENT_SYMLINK_REJECTED'):
            custody.prepare_generation(link, self.snapshot, generation=GENERATION, cutover_id=CUTOVER, fence=self.fence)
        self.parent.chmod(0o755)
        self.rejected('TARGET_PRIVATE_PARENT_REQUIRED')
        self.parent.chmod(0o700)

    def test_partial_commit_retains_failed_generation_and_blocks_runtime(self):
        add_clients(self.snapshot)
        def fault(stage):
            if stage == 'MAIN_COMMITTED':
                raise RuntimeError(SYNTHETIC_SECRET)
        with self.assertRaisesRegex(custody.Hold, 'PREPARATION_UNKNOWN_PRESERVE_EVIDENCE'):
            self.prepare(checkpoint=fault)
        self.assertTrue((self.target/'oauth-candidate.sqlite3').exists())
        self.assertTrue((self.target/'FAILED.json').exists())
        self.assertFalse((self.target/'READY.json').exists())
        self.assertNotIn(SYNTHETIC_SECRET, (self.target/'FAILED.json').read_text())
        with self.assertRaisesRegex(RuntimeError, 'OFFLINE_GENERATION_NOT_READY'):
            isolated_runtime.make_isolated_server(self.target)

    def test_hard_process_exit_preserves_unready_generation_and_denies_retry(self):
        process = multiprocessing.get_context('fork').Process(target=child_interrupt,
            args=(str(self.parent), self.snapshot, self.fence))
        process.start(); process.join(10)
        self.assertFalse(process.is_alive())
        self.assertEqual(process.exitcode, 73)
        self.assertTrue(self.target.exists())
        self.assertFalse((self.target/'READY.json').exists())
        with self.assertRaisesRegex(custody.Hold, 'TARGET_ALREADY_EXISTS_NO_BLIND_RETRY'):
            self.prepare()

    def test_cross_process_same_generation_has_exactly_one_winner(self):
        ctx = multiprocessing.get_context('fork');queue = ctx.Queue()
        processes = [ctx.Process(target=child_prepare, args=(str(self.parent), self.snapshot, self.fence, queue)) for _ in range(2)]
        for p in processes:p.start()
        for p in processes:p.join(10);self.assertFalse(p.is_alive());self.assertEqual(p.exitcode,0)
        actual = sorted(queue.get(timeout=2) for _ in processes)
        self.assertEqual(actual, ['PREPARED', 'TARGET_ALREADY_EXISTS_NO_BLIND_RETRY'])
        self.assertTrue((self.target/'READY.json').exists())

    def test_isolated_runtime_health_provider_disabled_and_disconnect_always_denied(self):
        self.prepare()
        server = isolated_runtime.make_isolated_server(self.target)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            self.assertEqual(server.server_address[0], '127.0.0.1')
            self.assertFalse(server.provider_calls_enabled)
            for method, path, headers, expected in [
                ('GET','/healthz',{'Host':'wenwenwenyiyiyi.work','X-Forwarded-Proto':'https'},200),
                ('GET','/integrations/tiktok/oauth/start',{'Host':'wenwenwenyiyiyi.work','X-Forwarded-Proto':'https'},503),
                ('POST','/integrations/tiktok/disconnect',{'Host':'invalid.example','Origin':'https://invalid.example'},403)]:
                c = http.client.HTTPConnection(*server.server_address, timeout=3)
                c.request(method,path,headers=headers);response=c.getresponse();body=response.read();c.close()
                self.assertEqual(response.status, expected)
                if method=='POST':self.assertIs(json.loads(body)['operation_performed'], False)
        finally:
            server.shutdown();server.server_close();thread.join(3)

    def test_ready_marker_wrong_identity_is_rejected(self):
        self.prepare()
        (self.target/'READY.json').chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'READY_IDENTITY_INVALID'):
            isolated_runtime.make_isolated_server(self.target)


if __name__ == '__main__':
    unittest.main(verbosity=2)
