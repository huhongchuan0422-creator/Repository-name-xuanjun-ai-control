"""Render the existing native-source adapter artifact, not a WeChat acceptance test."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
class PomeloPreview(unittest.TestCase):
    def test_actual_snapshot_recommendation_click_opens_four_image_detail(self):
        out = ROOT / 'pomelo-preview-evidence'
        out.mkdir(exist_ok=True)
        with zipfile.ZipFile(ROOT / 'deploy/community-preview/pomelo-recommendation-preview.zip') as archive:
            html = archive.read('pomelo-recommendation-preview.html')
        target = out / 'pomelo-recommendation-preview.html'
        target.write_bytes(html)
        # Verify all embedded actual native source bytes against the consumer manifest.
        text = html.decode()
        decoder = json.JSONDecoder()
        files, _ = decoder.raw_decode(text.split('const files=', 1)[1])
        manifest = json.loads((ROOT / 'deploy/community-preview/hangzhou-snapshot/manifest.json').read_bytes())['files']
        for name, content in files.items():
            self.assertEqual(hashlib.sha256(content.encode()).hexdigest(), manifest[name], name)
        errors, requests = [], []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport=dict(width=390,height=844))
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('http://**/*', lambda route: (requests.append(route.request.url), route.abort()))
            page.route('https://**/*', lambda route: (requests.append(route.request.url), route.abort()))
            page.goto(target.as_uri())
            expect(page.get_by_text('爱心商城',exact=True)).to_be_visible()
            page.screenshot(path=str(out / 'recommendation.png'), full_page=True)
            page.locator('[data-handler="openRecommendation"]').click()
            expect(page.locator('.showcase-price')).to_have_text('¥10.00 / 份')
            expect(page.get_by_text('展示库存：100 份',exact=True)).to_be_visible()
            expect(page.locator('.showcase-gallery img')).to_have_count(4)
            for image in page.locator('.showcase-gallery img').all():
                expect(image).to_be_visible()
                self.assertTrue(image.evaluate('(image)=>image.complete&&image.naturalWidth===800'))
            expect(page.get_by_text('仅供浏览，不提供下单或支付。',exact=True)).to_be_visible()
            self.assertIn('Ivar Leidus',page.locator('.showcase-detail').inner_text())
            self.assertIn('Allen Timothy Chang',page.locator('.showcase-detail').inner_text())
            self.assertEqual(page.locator('.showcase-detail [data-handler]').count(),0)
            page.screenshot(path=str(out / 'detail.png'), full_page=True)
            self.assertEqual(errors,[])
            self.assertEqual(requests,[])
            evidence = page.evaluate('window.__nativeEvidence')
            (out/'receipt.json').write_text(json.dumps(dict(scope='ISOLATED_BROWSER_PREVIEW_NOT_WECHAT',source_commit='73c55d6ea775c1fe6f6f8908b62dc593a86649e0',html_sha256=hashlib.sha256(html).hexdigest(),manifest_sha256=hashlib.sha256((ROOT/'deploy/community-preview/hangzhou-snapshot/manifest.json').read_bytes()).hexdigest(),calls=evidence['calls'],remote_requests=requests,errors=errors),sort_keys=True))
            browser.close()
if __name__ == '__main__':
    unittest.main()
