"""Deterministic bind-token/scanner collision regressions; synthetic local data only."""
import unittest
from unittest.mock import patch
from scripts import pr122_customer_core as core
from tests import test_pr122_customer_center as fixtures

class BindTokenTests(unittest.TestCase):
    setUp=fixtures.CustomerTests.setUp
    imported=fixtures.CustomerTests.imported
    collision='a'*12+'sk-'+'B'*28

    def issued(self):
        with patch.object(core.secrets,'token_urlsafe',return_value=self.collision) as url, \
             patch.object(core.secrets,'token_hex',return_value='ab'*32) as hexadecimal:
            value=self.c.binding_challenge(self.owner,'project-a','TELEGRAM','123')
        return value['challenge'],url,hexadecimal

    def test_generated_bind_token_avoids_real_scanner_collision(self):
        token,url,hexadecimal=self.issued()
        result=self.c.channel_event('TELEGRAM','collision_success','123','/bind '+token)
        self.assertTrue(result['provider_verified'])
        self.assertTrue(result['web_confirmation_required'])
        self.assertEqual(token,'ab'*32);self.assertEqual(len(token),64)
        hexadecimal.assert_called_once_with(32);url.assert_not_called()
        self.assertEqual(len(self.c.pending_links(self.owner,'project-a')),1)

    def test_collision_pattern_remains_rejected_by_unmodified_scanner(self):
        with self.assertRaisesRegex(core.Denied,'USE_OAUTH_OR_SECRETREF'):
            core.safe_text('/bind '+self.collision)

    def test_real_secret_shapes_still_rejected_without_events(self):
        for number,secret in enumerate(('sk-'+('C'*24),'api_key=synthetic','password=synthetic',
                                        'access_token=synthetic','appsecret=synthetic','BEGIN RSA PRIVATE KEY')):
            for prefix in ('/bind ','/project project-a '):
                with self.subTest(prefix=prefix,secret=secret),self.assertRaisesRegex(core.Denied,'USE_OAUTH_OR_SECRETREF'):
                    self.c.channel_event('TELEGRAM','secret_'+str(number),'123',prefix+secret)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM messages').fetchone()[0],0)

    def test_subject_scope_rejection_does_not_consume(self):
        token,_,_=self.issued()
        with self.assertRaisesRegex(core.Denied,'CHALLENGE_SCOPE'):
            self.c.channel_event('TELEGRAM','wrong_subject','999','/bind '+token)
        self.assertTrue(self.c.channel_event('TELEGRAM','right_subject','123','/bind '+token)['provider_verified'])

    def test_channel_scope_rejection_does_not_consume(self):
        token,_,_=self.issued()
        with self.assertRaisesRegex(core.Denied,'CHALLENGE_SCOPE'):
            self.c.channel_event('FEISHU','wrong_channel','123','/bind '+token)
        self.assertTrue(self.c.channel_event('TELEGRAM','right_channel','123','/bind '+token)['provider_verified'])

    def test_token_remains_single_use_and_event_replay_idempotent(self):
        token,_,_=self.issued()
        self.c.channel_event('TELEGRAM','first_event','123','/bind '+token)
        self.assertTrue(self.c.channel_event('TELEGRAM','first_event','123','/bind '+token)['duplicate'])
        with self.assertRaisesRegex(core.Denied,'INVALID_CHALLENGE'):
            self.c.channel_event('TELEGRAM','new_event','123','/bind '+token)

    def test_token_expiry_remains_enforced(self):
        token,_,_=self.issued();self.now+=301
        with self.assertRaisesRegex(core.Denied,'INVALID_CHALLENGE'):
            self.c.channel_event('TELEGRAM','expired_event','123','/bind '+token)

    def test_nonsecret_legacy_urlsafe_bind_still_consumed(self):
        token='legacy_urlsafe-A_'+('Q'*27)
        payload={'project':'project-a','channel':'TELEGRAM','subject':'123'}
        with self.c.tx():
            self.c.db.execute('INSERT INTO challenges VALUES(?,?,?,?,?,0)',
                (core.digest(token.encode()),'bind',self.owner,self.c.encrypt(core.canonical(payload),'challenge'),self.now+300))
        self.assertTrue(self.c.channel_event('TELEGRAM','legacy_event','123','/bind '+token)['provider_verified'])

    def test_other_challenge_generation_unchanged(self):
        with patch.object(core.secrets,'token_urlsafe',return_value='ordinary_other_challenge') as url, \
             patch.object(core.secrets,'token_hex') as hexadecimal:
            with self.c.tx():value=self.c.challenge('confirm_link',self.owner,{},300)
        self.assertEqual(value,'ordinary_other_challenge');url.assert_called_once_with(32);hexadecimal.assert_not_called()

    def test_unknown_hex_token_is_not_a_valid_binding(self):
        with self.assertRaisesRegex(core.Denied,'INVALID_CHALLENGE'):
            self.c.channel_event('TELEGRAM','unknown_event','123','/bind '+('ff'*32))

if __name__=='__main__':unittest.main()
