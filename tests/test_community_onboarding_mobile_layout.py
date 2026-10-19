"""Real Chromium layout, pure local HTML with no HTTP listener or network."""
from pathlib import Path
import re
import unittest
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]

class OnboardingMobileLayout(unittest.TestCase):
    def test_application_and_material_identifiers_wrap_without_clipping(self):
        markup=(ROOT/'demos/community-stage/onboarding.html').read_text()
        markup=re.sub(r'<script\b[^>]*>.*?</script>','',markup,flags=re.S)
        markup=re.sub(r'<link\b[^>]*>','',markup)
        css=(ROOT/'demos/community-stage/onboarding.css').read_text()
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.route('**/*',lambda route:route.abort())
                page.set_content(markup+'<style>'+css+'</style>')
                page.evaluate('''() => {
                  document.getElementById('detail').hidden=false;
                  document.getElementById('applicationVersion').textContent='申请编号 ma_'+'a'.repeat(32)+' · 版本 123';
                  document.getElementById('historyRows').textContent='操作账号 '+'a'.repeat(64)+' · REOPEN 审核说明 '+'b'.repeat(80);
                  document.getElementById('historyMaterials').textContent='营业执照：第1版（v_'+'c'.repeat(32)+'）';
                  document.querySelector('#applicationHistory details').open=true;
                }''')
                for width in (360,768,1440):
                    page.set_viewport_size({'width':width,'height':900})
                    with self.subTest(width=width):
                        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                        self.assertIn('ma_'+'a'*32,page.locator('#applicationVersion').inner_text())
                        self.assertNotEqual(page.locator('#applicationVersion').evaluate('e=>getComputedStyle(e).overflowX'),'hidden')
            finally:browser.close()

if __name__=='__main__':unittest.main()
