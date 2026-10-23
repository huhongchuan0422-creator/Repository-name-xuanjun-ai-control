"""Consent display uses only the validated stored flow; synthetic, network forbidden."""
import json
import re
import unittest
from html.parser import HTMLParser
from tests.oauth import test_oauth_consent_csp as t


class Fields(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.values = {}
        self.key = None
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        if tag == 'dd':
            self.key = dict(attrs).get('data-consent-field')
            if self.key is not None:
                self.values[self.key] = ''
    def handle_endtag(self, tag):
        if tag == 'dd':
            self.key = None
    def handle_data(self, value):
        if self.key is not None:
            self.values[self.key] += value


class ConsentScopeDisplayTests(unittest.TestCase):
    def setUp(self):
        self.b = t.Fixture()
        self.b.setUp()
        self.c = self.b.client()
        self.db = self.b.keeper
    def tearDown(self):
        self.b.tearDown()
    def start(self, scope='connection.status', owner=True):
        params = [(k, v) for k, v in t.args() if k != 'scope']
        if scope is not None:
            params.append(('scope', scope))
        response = self.c.get('/authorize', query_string=params, base_url=t.ISSUER)
        self.assertEqual(response.status_code, 302)
        if owner:
            self.db.execute("UPDATE oauth_flows SET sub='github:332398908'")
            self.db.commit()
    def get(self, path='/consent'):
        return self.c.get(path, base_url=t.ISSUER)
    def read(self, response):
        self.assertEqual(response.status_code, 200)
        return Fields(response.get_data(as_text=True)).values
    def test_status_only(self):
        self.start()
        self.assertEqual(self.read(self.get()), {'client_id':'offline-status-client',
            'resource':t.ISSUER+'/mcp', 'scope':'connection.status'})
    def test_files_not_hidden(self):
        self.start('connection.status project.files.read')
        self.assertEqual(self.read(self.get())['scope'], 'connection.status project.files.read')
    def test_scope_order_not_rewritten(self):
        self.start('project.files.read connection.status')
        self.assertEqual(self.read(self.get())['scope'], 'project.files.read connection.status')
    def test_missing_scope_not_defaulted(self):
        self.start(None)
        self.assertEqual(self.read(self.get())['scope'], '(not explicitly requested)')
    def test_empty_scope_not_defaulted(self):
        self.start('')
        self.assertEqual(self.read(self.get())['scope'], '(not explicitly requested)')
    def test_query_cannot_override_saved_request(self):
        self.start()
        response = self.get('/consent?client_id=foreign&resource=https://foreign.invalid&scope=project.files.read')
        self.assertEqual(self.read(response), {'client_id':'offline-status-client',
            'resource':t.ISSUER+'/mcp', 'scope':'connection.status'})
    def test_display_escape(self):
        self.start()
        params = json.loads(self.db.execute('SELECT params FROM oauth_flows').fetchone()[0])
        # Synthetic DB-only corruption tests rendering, not a valid authorize input.
        value = '<script>synthetic&"</script>'
        params['scope'] = value
        params['resource'] = value
        self.db.execute('UPDATE oauth_flows SET params=?', (json.dumps(params),))
        self.db.commit()
        response = self.get()
        fields = self.read(response)
        self.assertEqual(fields['scope'], value)
        self.assertEqual(fields['resource'], value)
        self.assertNotIn('<script>', response.get_data(as_text=True))
    def test_no_sensitive_values_added_to_display(self):
        self.start()
        response = self.get()
        text = response.get_data(as_text=True)
        fields = self.read(response)
        self.assertEqual(set(fields), {'client_id','resource','scope'})
        for value in ('A'*43, 'B'*40, 'LOCAL-TEST-ONLY', 'redirect_uri', 'code_challenge'):
            self.assertNotIn(value, text)
        # Existing hidden CSRF remains required; it is not a displayed detail.
        self.assertEqual(len(re.findall('name="csrf"', text)), 1)
        self.assertNotIn('csrf', fields)
    def test_missing_flow_not_displayed(self):
        response = self.get()
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('data-consent-field', response.get_data(as_text=True))
    def test_unbound_owner_not_displayed(self):
        self.start(owner=False)
        response = self.get()
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('data-consent-field', response.get_data(as_text=True))
    def test_expired_and_used_not_displayed(self):
        for statement in ('UPDATE oauth_flows SET expires=0','UPDATE oauth_flows SET used=1'):
            self.start()
            self.db.execute(statement)
            self.db.commit()
            response = self.get()
            self.assertEqual(response.status_code, 401)
            self.assertNotIn('data-consent-field', response.get_data(as_text=True))
    def test_post_unchanged_single_issue_no_details(self):
        self.start()
        form = self.get()
        csrf = re.search(r'name="csrf" value="([^"]+)"', form.get_data(as_text=True)).group(1)
        response = self.c.post('/consent', base_url=t.ISSUER, data={'csrf':csrf,'approve':'yes'})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('data-consent-field', response.get_data(as_text=True))
        self.assertEqual(self.db.execute('SELECT scope FROM oauth_codes').fetchone()[0], 'connection.status')
        again = self.c.post('/consent', base_url=t.ISSUER, data={'csrf':csrf,'approve':'yes'})
        self.assertEqual(again.status_code, 401)
        self.assertEqual(self.db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0], 1)
    def test_security_headers_unchanged(self):
        self.start()
        response = self.get()
        for key, value in [('Cache-Control','no-store'),('Pragma','no-cache'),
                           ('Referrer-Policy','no-referrer'),('X-Content-Type-Options','nosniff')]:
            self.assertEqual(response.headers[key], value)
        self.assertEqual(response.headers['Content-Security-Policy'],
            "default-src 'none'; form-action 'self' "+t.CALLBACK+"; frame-ancestors 'none'")


if __name__ == '__main__':
    unittest.main()
