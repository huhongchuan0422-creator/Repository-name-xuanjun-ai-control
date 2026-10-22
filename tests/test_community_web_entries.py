import re
import unittest
from scripts.community_web_entries import asset,entries,PAGES,ASSETS,PREFIX

class RoleEntries(unittest.TestCase):
    def test_catalog_distinguishes_native_consumer_and_scoped_web_roles_without_grants(self):
        value=entries()
        self.assertFalse(value['production_acceptance'])
        roles=value['roles'];self.assertEqual([r['role'] for r in roles],['CONSUMER','MERCHANT','COMMUNITY','PLATFORM'])
        self.assertEqual(roles[0]['kind'],'WECHAT_MINIPROGRAM')
        self.assertEqual(roles[0]['scene'],'shop1')
        self.assertEqual(roles[-1]['scope'],'MERCHANT_ADMISSION_REVIEW')
        self.assertTrue(all('REQUIRED' in r['authorization'] for r in roles))
        self.assertNotIn('token',repr(value));self.assertNotIn('csrf',repr(value))
    def test_original_pages_assets_and_role_links_close_under_exact_prefix(self):
        for path in PAGES:
            raw,mime=asset(path);text=raw.decode()
            self.assertIn('text/html',mime)
            self.assertIn('aria-label="角色入口"',text)
            for link in re.findall(r'(?:href|src)=["\']([^"\']+)',text):
                self.assertTrue(link.startswith(PREFIX+'/'),link)
                self.assertIsNotNone(asset(link[len(PREFIX):]),link)
    def test_original_scripts_rebase_requests_and_review_route_without_credentials(self):
        for path in ASSETS:
            raw,mime=asset(path);text=raw.decode()
            if path.endswith('.js'):
                self.assertNotRegex(text,r"fetch\(['\"]/(?:merchant|community)/")
        js=asset('/merchant/onboarding.js')[0].decode()
        self.assertIn("location.pathname==='/community-preview/merchant/review'",js)
        self.assertIn("fetch('/community-preview/merchant/onboarding'",js)
        self.assertIn("link.href='/community-preview/merchant/workbench'",js)
        self.assertIn('credentials:',js)
    def test_unregistered_paths_queries_traversal_and_external_urls_never_read_files(self):
        for path in ['/etc/passwd','/merchant/../workbench','/merchant/workbench?role=admin',
                     'https://evil.invalid/merchant/workbench','/platform/anything',PREFIX+'/merchant/workbench']:
            self.assertIsNone(asset(path))

if __name__=='__main__':unittest.main()
