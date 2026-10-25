"""Offline negative checks for fixed-only diagnostic reason protocol."""
import socket
import ssl
import unittest
import urllib.error
from unittest.mock import patch
from tests.oauth import test_oauth_consent_csp as base
from production.cloud_connection import github_network as net, oauth_authority as authority
from production.cloud_connection.queue import Hold


class ReasonTests(unittest.TestCase):
    def test_fixed_wire_reason_map(self):
        examples = [
            (socket.gaierror('code=SECRET'), 'DNS'),
            (ssl.SSLError('token=SECRET'), 'TLS'),
            (TimeoutError('state=SECRET'), 'TIMEOUT'),
            (urllib.error.HTTPError('https://example.invalid', 403, 'SECRET', {}, None), 'HTTP_STATUS'),
            (urllib.error.HTTPError('https://example.invalid', 302, 'SECRET', {}, None), 'REDIRECT'),
            (Hold('GITHUB_BODY_LIMIT'), 'LIMIT'),
            (ValueError('secret=SECRET'), 'OTHER'),
        ]
        for error, expected in examples:
            with self.subTest(expected=expected):
                self.assertEqual(net._wire_reason(error), expected)
                self.assertNotIn('SECRET', net._wire_reason(error))

    def test_callback_wire_failure_is_fixed_only(self):
        f=base.Fixture();f.setUp()
        try:
            c=f.client(authority)
            gh=c.application.extensions['authlib.integrations.flask_client'].create_client('github')
            r=c.get('/authorize',query_string=base.args(),base_url=base.ISSUER)
            self.assertEqual(r.status_code,302)
            for reason in ('DNS','TLS','TIMEOUT','HTTP_STATUS','REDIRECT','LIMIT','OTHER','INJECTED'):
                with self.subTest(reason=reason), patch.object(gh,'authorize_access_token',side_effect=Hold('GITHUB_WIRE_'+reason)):
                    response=c.get('/github/callback',base_url=base.ISSUER)
                    self.assertEqual(response.status_code,401)
                    self.assertEqual(response.headers.get('X-Xuanjun-OAuth-Reason'), reason if reason!='INJECTED' else 'OTHER')
                    self.assertNotIn('INJECTED',str(response.headers)+response.get_data(as_text=True))
        finally:f.tearDown()

    def test_state_failure_never_enters_network(self):
        f=base.Fixture();f.setUp()
        try:
            c=f.client(authority)
            gh=c.application.extensions['authlib.integrations.flask_client'].create_client('github')
            with patch.object(gh,'authorize_access_token') as token:
                r=c.get('/github/callback',base_url=base.ISSUER)
                self.assertEqual(r.status_code,401)
                token.assert_not_called()
        finally:f.tearDown()

if __name__=='__main__':unittest.main()
