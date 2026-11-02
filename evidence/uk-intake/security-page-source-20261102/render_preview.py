"""Local blank, disabled UI preview only; no host/secret connection or listener."""
import json
import pathlib
import re
import sys
from playwright.sync_api import sync_playwright
from safe_input import Candidate, Principal, Request, PURPOSE, VERSION
ROOT = pathlib.Path(__file__).resolve().parent
class PreviewHost:
    def ready(self): return True
    def authorize_owner(self, principal): return True
    def csrf_for(self, principal, request): return ''
class PreviewStore:
    def ready(self): return True
    def metadata(self, qid):
        return Request(qid, 'preview-only', 'preview-only', PURPOSE, VERSION, 600, 'PENDING')
    def status(self, request, principal):
        from safe_input import Outcome
        return Outcome('PENDING')
# No submit/create/store methods exist in these preview-only objects.
page = Candidate(PreviewHost(), PreviewStore()).page(
    Principal('preview-only', 'preview-only'), 'PREVIEW_ONLY_NOT_A_REAL_REQUEST')[1]
page = re.sub(r'<form[^>]*>', '<fieldset disabled>', page).replace('</form>', '</fieldset>')
page = re.sub(r'<input type="hidden"[^>]*>', '', page)
page = page.replace('<h1>', '<p role="status"><strong>本地候选预览 · 未接线 · 不可输入/提交</strong></p><h1>')
(ROOT / 'preview-disabled.html').write_text(page, encoding='utf-8')
if '--html-only' in sys.argv:
    print('DISABLED_HTML_ONLY; no browser run')
    raise SystemExit(0)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
        args=['--disable-background-networking', '--disable-sync', '--no-first-run'])
    context = browser.new_context(offline=True)
    context.route('**/*', lambda route: route.abort())
    tab = context.new_page()
    results = []
    for width in (360, 390, 768):
        tab.set_viewport_size({'width': width, 'height': 844})
        tab.set_content(page)
        assert tab.locator('input[type=password]').count() == 3
        assert tab.locator('form').count() == 0
        assert tab.locator('button').is_disabled()
        assert tab.evaluate('document.documentElement.scrollWidth <= innerWidth')
        results.append({'width': width, 'masked_fields': 3, 'disabled': True, 'overflow': False})
        if width == 390:
            tab.screenshot(path=str(ROOT / 'preview-mobile-390.png'), full_page=True)
    browser.close()
(ROOT / 'preview-validation.json').write_text(json.dumps({
    'stage': 'LOCAL_DISABLED_UI_ONLY', 'network': 'offline; all requests aborted',
    'real_secret_input': False, 'results': results}, indent=2), encoding='utf-8')
print('LOCAL_DISABLED_UI_ONLY: 3 viewport checks passed; no live link or credentials')
