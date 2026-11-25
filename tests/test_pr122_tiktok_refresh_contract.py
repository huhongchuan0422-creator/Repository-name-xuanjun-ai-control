"""Synthetic checks for the PR #122 TikTok renewal contract."""

import io
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

PACKAGE = Path(__file__).resolve().parents[1] / "deploy" / "pr122-oauth-candidate"
sys.path.insert(0, str(PACKAGE))

from pr122_oauth_candidate import core, oauth, tiktok

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
CLIENT_KEY = "synthetic-client-key"
CLIENT_SECRET = "synthetic-client-secret"
OPEN_ID = "synthetic-open-id"
ACCESS = core.TIKTOK_ACCESS_TOKEN_REF
REFRESH = core.TIKTOK_REFRESH_TOKEN_REF
BINDING = "binding:tiktok"


def reply(generation, access_seconds=41, refresh_seconds=7601):
    return {
        "access_token": f"synthetic-access-{generation}",
        "refresh_token": f"synthetic-refresh-{generation}",
        "expires_in": access_seconds,
        "refresh_expires_in": refresh_seconds,
        "open_id": OPEN_ID,
        "scope": "user.info.basic",
        "token_type": "Bearer",
    }


class TikTokRefreshContractTests(unittest.TestCase):
    def setUp(self):
        def block_network(*args, **kwargs):
            raise AssertionError("Network disabled for synthetic contract test")

        for method in ("urllib.request.urlopen", "socket.socket.connect",
                       "socket.socket.connect_ex", "socket.getaddrinfo"):
            guard = self.enterContext(patch(method, side_effect=block_network))
            self.addCleanup(guard.assert_not_called)
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.service = self.reopen()
        initial = self.lifecycle(reply(0, access_seconds=1), NOW - timedelta(seconds=30))
        with self.service.database.transaction():
            self.put_ref(self.service, core.TIKTOK_CLIENT_KEY_REF, CLIENT_KEY)
            self.put_ref(self.service, core.TIKTOK_CLIENT_SECRET_REF, CLIENT_SECRET)
            self.put_ref(self.service, ACCESS, reply(0)["access_token"])
            self.put_ref(self.service, REFRESH, reply(0)["refresh_token"])
            self.service.database.put(BINDING, {
                "verified": True, "identity_hash": core._sha(OPEN_ID), "account": {},
                "client_key_fingerprint": core._sha(CLIENT_KEY)[:12], "lifecycle": initial,
            })
            self.service.database.put("lifecycle:tiktok", initial)

    def reopen(self):
        return core.SecureSecretsPortalService(self.root / "state", self.root / "operations")

    def lifecycle(self, payload, now):
        parsed = tiktok.parse_token_response(payload, client_key=CLIENT_KEY, now=now)
        self.assertEqual(parsed["status"], "PASS")
        return parsed["lifecycle"].as_public_dict()

    def put_ref(self, service, name, value):
        stored = service.operations_store.store_secret(
            name, value, "tiktok", "readonly_oauth", "synthetic contract", actor="fixture"
        )
        self.assertEqual(stored["status"], "CONFIGURED")

    def assert_pair(self, generation, service):
        with service.database.transaction():
            self.assertEqual(service.operations_store.read_secret(ACCESS),
                             reply(generation)["access_token"])
            self.assertEqual(service.operations_store.read_secret(REFRESH),
                             reply(generation)["refresh_token"])

    def refresh_entry(self):
        operation = getattr(oauth, "refresh_tiktok_credentials", None)
        self.assertTrue(callable(operation), "Missing service entry: oauth.refresh_tiktok_credentials")
        return operation

    def fake_provider(self):
        return Mock(spec_set=["refresh_access_token"])

    def test_actual_parser_uses_both_response_lifetimes_in_seconds(self):
        parsed = self.lifecycle(reply(1), NOW)
        self.assertEqual(datetime.fromisoformat(parsed["access_token_expires_at"]),
                         NOW + timedelta(seconds=41))
        self.assertEqual(datetime.fromisoformat(parsed["refresh_token_expires_at"]),
                         NOW + timedelta(seconds=7601))

    def test_actual_transaction_does_not_commit_half_a_pair(self):
        def fail_before_commit(point):
            if point == "write:secret:" + REFRESH:
                raise OSError("synthetic write failure")

        with patch.object(self.service.database, "checkpoint", side_effect=fail_before_commit):
            with self.assertRaises(OSError):
                with self.service.database.transaction():
                    self.put_ref(self.service, ACCESS, reply(1)["access_token"])
                    self.put_ref(self.service, REFRESH, reply(1)["refresh_token"])
        self.assert_pair(0, self.reopen())

    def test_transport_contract_posts_refresh_grant_without_new_scope(self):
        client = tiktok.TikTokOpenApiClient()
        refresh = getattr(client, "refresh_access_token", None)
        self.assertTrue(callable(refresh), "Missing transport entry: TikTokOpenApiClient.refresh_access_token")
        with patch.object(client, "_post_form", return_value=reply(1)) as post:
            self.assertEqual(refresh(client_key=CLIENT_KEY, client_secret=CLIENT_SECRET,
                                     refresh_token=reply(0)["refresh_token"]), reply(1))
        post.assert_called_once_with(tiktok.TIKTOK_ACCESS_TOKEN_URL, {
            "grant_type": "refresh_token", "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET, "refresh_token": reply(0)["refresh_token"],
        })

    def test_http_invalid_grant_drops_provider_error_details(self):
        client = tiktok.TikTokOpenApiClient()
        body = io.BytesIO(b'{"error":"invalid_grant","error_description":"synthetic detail"}')
        failure = HTTPError(tiktok.TIKTOK_ACCESS_TOKEN_URL, 400, "Bad Request", {}, body)
        with patch.object(client, "_post_form", side_effect=failure) as post:
            self.assertEqual(client.refresh_access_token(client_key=CLIENT_KEY,
                client_secret=CLIENT_SECRET, refresh_token=reply(0)["refresh_token"]),
                {"error": "invalid_grant"})
        post.assert_called_once()

    def test_same_account_two_callers_share_one_provider_request(self):
        refresh = self.refresh_entry()
        peer = self.reopen()
        provider = self.fake_provider()
        entered, release = threading.Event(), threading.Event()

        def reply_after_peer_starts(**kwargs):
            entered.set()
            self.assertTrue(release.wait(timeout=3))
            return reply(1)

        provider.refresh_access_token.side_effect = reply_after_peer_starts
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(refresh, self.service, client=provider, now=NOW)
            try:
                self.assertTrue(entered.wait(timeout=3))
                ready = threading.Event()

                def second_caller():
                    ready.set()
                    return refresh(peer, client=provider, now=NOW)

                second = pool.submit(second_caller)
                self.assertTrue(ready.wait(timeout=3))
                self.assertEqual(second.result(timeout=3)["status"], "UNKNOWN")
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3)["status"], "PASS")
        provider.refresh_access_token.assert_called_once()
        self.assert_pair(1, self.reopen())

    def test_rotation_updates_pair_and_both_expiries_then_uses_replacement(self):
        refresh = self.refresh_entry()
        provider = self.fake_provider()
        provider.refresh_access_token.side_effect = [reply(1), reply(2, 73, 9211)]

        refresh(self.service, client=provider, now=NOW)
        reopened = self.reopen()
        self.assert_pair(1, reopened)
        binding = reopened.database.get(BINDING)
        self.assertEqual(binding["identity_hash"], core._sha(OPEN_ID))
        self.assertEqual(binding["lifecycle"], self.lifecycle(reply(1), NOW))
        self.assertEqual(reopened.database.get("lifecycle:tiktok"), binding["lifecycle"])

        later = NOW + timedelta(seconds=42)
        refresh(reopened, client=provider, now=later)
        self.assertEqual(
            [call.kwargs["refresh_token"] for call in provider.refresh_access_token.call_args_list],
            [reply(0)["refresh_token"], reply(1)["refresh_token"]],
        )
        self.assert_pair(2, self.reopen())
        self.assertEqual(self.reopen().database.get(BINDING)["lifecycle"],
                         self.lifecycle(reply(2, 73, 9211), later))

    def test_provider_failure_or_lost_response_is_not_replayed_after_reopen(self):
        refresh = self.refresh_entry()
        provider = self.fake_provider()
        provider.refresh_access_token.side_effect = TimeoutError("synthetic response lost")
        result = refresh(self.service, client=provider, now=NOW)
        self.assertEqual(result["status"], "UNKNOWN")
        refresh(self.reopen(), client=provider, now=NOW + timedelta(seconds=1))
        provider.refresh_access_token.assert_called_once()
        self.assert_pair(0, self.reopen())

    def test_invalid_grant_does_not_automatically_replay_old_refresh_token(self):
        refresh = self.refresh_entry()
        provider = self.fake_provider()
        provider.refresh_access_token.return_value = {"error": "invalid_grant"}
        result = refresh(self.service, client=provider, now=NOW)
        self.assertEqual(result["status"], "REAUTHORIZATION_REQUIRED")
        refresh(self.reopen(), client=provider, now=NOW + timedelta(seconds=1))
        provider.refresh_access_token.assert_called_once()
        self.assert_pair(0, self.reopen())

    def test_write_failure_after_provider_success_preserves_old_pair_without_replay(self):
        refresh = self.refresh_entry()
        provider = self.fake_provider()
        provider.refresh_access_token.return_value = reply(1)

        def fail_after_rotation(point):
            if point == "write:secret:" + REFRESH:
                raise OSError("synthetic persistence failure")

        with patch.object(self.service.database, "checkpoint", side_effect=fail_after_rotation):
            result = refresh(self.service, client=provider, now=NOW)
        self.assertNotEqual(result["status"], "PASS")
        self.assert_pair(0, self.reopen())
        refresh(self.reopen(), client=provider, now=NOW + timedelta(seconds=1))
        provider.refresh_access_token.assert_called_once()

    def test_commit_ack_loss_retains_committed_pair_without_replay(self):
        refresh = self.refresh_entry()
        provider = self.fake_provider()
        provider.refresh_access_token.return_value = reply(1)
        pair_written = False

        def lose_commit_ack(point):
            nonlocal pair_written
            if point == "write:secret:" + REFRESH:
                pair_written = True
            elif point == "after_commit" and pair_written:
                pair_written = False
                raise OSError("synthetic commit acknowledgement lost")

        with patch.object(self.service.database, "checkpoint", side_effect=lose_commit_ack):
            refresh(self.service, client=provider, now=NOW)
        self.assert_pair(1, self.reopen())
        refresh(self.reopen(), client=provider, now=NOW + timedelta(seconds=1))
        provider.refresh_access_token.assert_called_once()

    def test_expired_refresh_token_requires_reauthorization_without_a_request(self):
        provider = self.fake_provider()
        result = self.refresh_entry()(self.service, client=provider,
                                      now=NOW + timedelta(hours=3))
        self.assertEqual(result["sanitized_error_code"], "TIKTOK_REFRESH_EXPIRED")
        provider.refresh_access_token.assert_not_called()

    def test_missing_expiry_does_not_replace_stored_pair(self):
        provider = self.fake_provider()
        payload = reply(1)
        del payload["refresh_expires_in"]
        provider.refresh_access_token.return_value = payload
        refresh = self.refresh_entry()
        self.assertEqual(refresh(self.service, client=provider, now=NOW)["status"], "UNKNOWN")
        self.assertEqual(refresh(self.reopen(), client=provider, now=NOW)["status"], "UNKNOWN")
        provider.refresh_access_token.assert_called_once()
        self.assert_pair(0, self.reopen())

    def test_wrong_account_or_scope_is_rejected_by_the_response_parser(self):
        for change in ({"open_id": "different-synthetic-id"},
                       {"scope": "user.info.basic,video.publish"}, {"scope": ""},
                       {"expires_in": True}, {"expires_in": 10 ** 30}):
            with self.subTest(change=change):
                self.assertIsNone(oauth._parse_tiktok_refresh(
                    {**reply(1), **change}, CLIENT_KEY, core._sha(OPEN_ID), NOW))

    def authorize(self, generation):
        origin = "https://oauth-candidate.invalid"
        oauth.configure_state_root(self.root / "state")
        url, _ = oauth.handle_tiktok_oauth_start(self.service, origin)
        state = parse_qs(urlsplit(url).query)["state"][0]
        account = {"data": {"user": {"open_id": OPEN_ID, "display_name": "Synthetic"}}}
        with patch.object(oauth.TikTokOpenApiClient, "exchange_access_token",
                          return_value=reply(generation)), \
                patch.object(oauth.TikTokOpenApiClient, "user_info", return_value=account):
            result = oauth.handle_tiktok_oauth_callback(self.service, origin,
                {"state": [state], "code": ["synthetic-authorization-code"]})
        self.assertEqual(result["status"], "PASS")

    def test_verified_reauthorization_recovers_an_unresolved_attempt(self):
        refresh = self.refresh_entry()
        provider = self.fake_provider()
        provider.refresh_access_token.side_effect = TimeoutError
        self.assertEqual(refresh(self.service, client=provider, now=NOW)["status"], "UNKNOWN")
        self.authorize(1)
        reopened = self.reopen()
        self.assert_pair(1, reopened)
        expiry = datetime.fromisoformat(reopened.database.get(BINDING)["lifecycle"]["access_token_expires_at"])
        provider.refresh_access_token.side_effect = None
        provider.refresh_access_token.return_value = reply(2)
        self.assertEqual(refresh(reopened, client=provider, now=expiry)["status"], "PASS")
        self.assertEqual(provider.refresh_access_token.call_args.kwargs["refresh_token"],
                         reply(1)["refresh_token"])
        self.assert_pair(2, reopened)

    def test_late_refresh_result_cannot_overwrite_new_verified_authorization(self):
        refresh = self.refresh_entry()
        provider = self.fake_provider()

        def return_after_authorization(**kwargs):
            self.authorize(2)
            return reply(1)

        provider.refresh_access_token.side_effect = return_after_authorization
        result = refresh(self.service, client=provider, now=NOW)
        self.assertEqual(result["sanitized_error_code"], "TIKTOK_REFRESH_BINDING_SUPERSEDED")
        self.assert_pair(2, self.reopen())
