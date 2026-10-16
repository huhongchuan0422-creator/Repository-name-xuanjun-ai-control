"""Real authorized source-to-candidate execution, never a publication fixture."""
import unittest
from unittest.mock import patch
from tests.test_pr122_customer_center import CustomerTests
from tests.test_pr122_customer_preview import PreviewTests
from scripts.pr122_customer_core import Denied, canonical, digest
from scripts.pr122_customer_changes import Changes
from scripts.pr122_customer_small_edit import build_candidate, recipe


class SmallEditTests(unittest.TestCase):
    imported = CustomerTests.imported
    install = PreviewTests.install

    def setUp(self):
        CustomerTests.setUp(self)
        self.path = '/preview/consumer/'
        self.revision = 1
        self.body = b'<!doctype html><html><body><h1 data-xj-small-text="TYPO_ONLY_V1">Welcome to Xuanjun</h1><script>const untouched=true;</script></body></html>'
        self.install()

    def request(self, text='将「Welcome」改为「Welcomes」', category='IN_SCOPE_SMALL'):
        service = Changes(self.c)
        case = service.submit(self.owner, 'project-a', self.path, self.sha, text)
        service.assess(self.reviewer, 'project-a', case['id'], 1, category, 1, [], [], '单处文案错字')
        return case['id']

    def build(self, case):
        return build_candidate(self.c, self.reviewer, 'project-a', case)

    def test_actual_byte_patch_zero_network_no_historical_lookup_and_no_publication(self):
        case = self.request()
        with patch('socket.socket', side_effect=AssertionError('no API')), patch.object(Changes, '_evidence', side_effect=AssertionError('no contract retrieval')):
            result = self.build(case)
        self.assertEqual(result['page_bytes'], self.body.replace(b'Welcome', b'Welcomes'))
        self.assertEqual(result['receipt']['model_api_calls'], 0)
        self.assertEqual(result['receipt']['historical_contract_lookups'], 0)
        self.assertEqual(result['receipt']['after_sha256'], digest(result['page_bytes']))
        self.assertEqual(result['receipt_sha256'], digest(canonical(result['receipt'])))
        self.assertEqual(self.build(case), result)
        # The signed source and page remain the original version.
        from scripts.pr122_customer_preview import original
        self.assertEqual(original(self.c, self.owner, 'project-a', digest(self.path.encode()), self.sha)[1], self.body)

    def test_chinese_explicit_request_and_bounded_edit_distance(self):
        self.body = '<html><body><p data-xj-small-text="TYPO_ONLY_V1">欢迎来到玄均云汇</p></body></html>'.encode()
        self.revision = 2
        self.install()
        result = self.build(self.request('把「玄均云汇」改成「玄钧云汇」。'))
        self.assertIn('玄钧云汇'.encode(), result['page_bytes'])

    def test_owner_cannot_self_execute_or_use_another_project(self):
        case = self.request()
        with self.assertRaises(Denied):
            build_candidate(self.c, self.owner, 'project-a', case)
        with self.assertRaises(Denied):
            build_candidate(self.c, self.reviewer, 'project-missing', case)

    def test_unassessed_disputed_or_non_small_cases_do_not_execute(self):
        service = Changes(self.c)
        case = service.submit(self.owner, 'project-a', self.path, self.sha, '将「Welcome」改为「Welcomes」')
        with self.assertRaises(Denied):
            self.build(case['id'])
        case = self.request(category='PROVIDER_DEFECT')
        with self.assertRaises(Denied):
            self.build(case)

    def test_stale_preview_and_revoked_owner_are_denied(self):
        case = self.request()
        self.revision = 2
        self.install(self.body.replace(b'Welcome', b'New title'))
        with self.assertRaises(Denied):
            self.build(case)
        self.imported(2, [])
        with self.assertRaises(Denied):
            self.build(case)

    def test_contract_reassignment_does_not_reuse_prior_request(self):
        case = self.request()
        self.imported(2, [{**self.p, 'contract_ref': 'contract-b'}])
        with self.assertRaisesRegex(Denied, 'REQUEST_CONTRACT_BINDING'):
            self.build(case)

    def test_prices_permissions_and_legal_text_require_other_execution_path(self):
        for text in ('将「免费」改为「付费」', '将「价格」改为「价各」', '将「登录」改为「登路」', '将「十九」改为「19」', '将「privacy」改为「privaty」'):
            with self.subTest(text=text), self.assertRaises(Denied):
                recipe(text)

    def test_no_markup_entities_control_chars_or_obfuscated_request(self):
        for text in ('将「Welcome」改为「<img>」', '将「Welcome」改为「a&b」', '将「W」改为「Ｗ」', '将「Welcome」改为「Wel\u200bcome」', '请让页面看起来更漂亮', '将「a」改为「abcdefgh」'):
            with self.subTest(text=text), self.assertRaises(Denied):
                recipe(text)

    def test_script_attribute_link_and_sensitive_context_not_modified(self):
        for fragment in ('<p>Welcome</p>', '<script>Welcome</script>', '<p title="Welcome">Other</p>', '<a><span>Welcome</span></a>', '<p>Welcome price</p>', '<p>Welcome 100</p>'):
            self.revision += 1
            self.install(('<html><body>' + fragment + '</body></html>').encode())
            with self.subTest(fragment=fragment), self.assertRaises(Denied):
                self.build(self.request())

    def test_multiple_occurrences_and_malformed_html_are_not_guessed(self):
        for fragment in ('<p data-xj-small-text="TYPO_ONLY_V1">Welcome Welcome</p>', '<p data-xj-small-text="TYPO_ONLY_V1">Welcome</p><span data-xj-small-text="TYPO_ONLY_V1">Welcome</span>', '<p data-xj-small-text="TYPO_ONLY_V1">Welcome</span>'):
            self.revision += 1
            self.install(('<html><body>' + fragment + '</body></html>').encode())
            with self.subTest(fragment=fragment), self.assertRaises(Denied):
                self.build(self.request())


if __name__ == '__main__':
    unittest.main()
