"""Review UI tests: offline DOM guardrails and original Center browser journey.

The browser case requires an admitted host with loopback sockets and Chromium.
All documents, scanner behavior and signed project authority are synthetic fixtures.
"""
import hashlib
import hmac
from pathlib import Path
import queue
import os
import shutil
import subprocess
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectReviewDOM(unittest.TestCase):
    def test_offline_review_actions_and_identity_races(self):
        subprocess.run(['node', str(ROOT / 'tests/community_project_review_dom.cjs'),
                        str(ROOT / 'demos/community-stage/project-review.js')],
                       check=True, capture_output=True, text=True)


class ProjectReviewBrowser(unittest.TestCase):
    def test_original_reviewer_download_begin_approve_and_clear(self):
        from playwright.sync_api import sync_playwright, expect
        import test_community_mini_center_identity as fixture
        from scripts.pr122_customer_core import canonical
        from scripts.community_center_operations import CenterOperations
        from scripts.community_commerce import Commerce
        from scripts.community_mini_http import serve
        ready = queue.Queue()

        def host():
            fx = server = None
            try:
                fx = fixture.ExistingCenterComposition(); fx.setUp()
                center = fx.center
                _, _, original = center.project(fx.uid1, 'project1')
                requirement = dict(id='document1', title='Synthetic review PDF', purpose='Fixture',
                    required=True, identity_requirements=[], official_url='https://example.org',
                    instructions='Inspect synthetic document', minimum_permissions=[], fees=[],
                    verified_at=center.now(), formats=['application/pdf'], valid_until=center.now()+3600,
                    submission_type='PRIVATE_DOCUMENT', category='MATERIAL')
                project = dict(original, requirements=[requirement], reviewer_emails=['two@example.org'])
                payload = dict(revision=2, expires=center.now()+3600, projects=[project])
                key = b'a'*32
                center.import_authority(dict(payload=payload, signature=hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()), key)
                center.scanner = lambda content: content == b'%PDF-1.4 synthetic review fixture'
                saved = center.save(fx.uid1, 'project1', 'document1', 0, 'DOCUMENT', b'%PDF-1.4 synthetic review fixture')
                center.transition(fx.uid1, 'project1', 'document1', saved['revision'], 'submit')
                reviewer = center.login('two@example.org', 'FixturePassword123!')
                commerce = Commerce(CenterOperations(center, fx.stage.api, {'merchant':dict(user_id=fx.uid1, project='project1', project_roles=['OWNER'], principal=fx.stage.merchant)}), fx.identity)
                server = serve(fx.gateway, commerce=commerce)
                ready.put((server, reviewer)); server.serve_forever(poll_interval=.05)
            except BaseException as error:
                ready.put(error)
            finally:
                if server: server.server_close()
                if fx: fx.tearDown()

        thread = threading.Thread(target=host, daemon=True); thread.start()
        state = ready.get(timeout=15)
        if isinstance(state, BaseException):
            thread.join(timeout=10)
            raise state
        server, reviewer = state
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, chromium_sandbox=True,
                    executable_path=(os.environ.get('COMMUNITY_CHROMIUM_EXECUTABLE')
                        or os.environ.get('COMMUNITY_CHROMIUM_PATH')
                        or shutil.which('google-chrome')
                        or shutil.which('google-chrome-stable')
                        or shutil.which('chromium')))
                try:
                    context = browser.new_context(extra_http_headers={'X-Center-Session': reviewer['token']}, accept_downloads=True)
                    page = context.new_page(); errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto('http://127.0.0.1:' + str(server.server_port) + '/community/project-review')
                    page.evaluate('csrf => configureCommunityProjectReview({csrf, workspace:"project1"})', reviewer['csrf'])
                    expect(page.locator('#reviewItems')).to_contain_text('SUBMITTED')
                    page.get_by_role('button', name='查看材料与审核').click()
                    expect(page.locator('#reviewSelected')).to_contain_text('当前版本 2')
                    with page.expect_download() as pending:
                        page.get_by_role('button', name='下载当前材料').click()
                    download = pending.value
                    self.assertEqual(Path(download.path()).read_bytes(), b'%PDF-1.4 synthetic review fixture')
                    page.locator('#reviewBegin').click()
                    expect(page.locator('#reviewSelected')).to_contain_text('IN_REVIEW')
                    expect(page.locator('#reviewSelected')).to_contain_text('当前版本 3')
                    page.locator('#reviewApprove').click()
                    expect(page.locator('#reviewNotice')).to_contain_text('填写审核意见')
                    page.locator('#reviewReason').fill('Synthetic document inspected')
                    page.locator('#reviewApprove').click()
                    expect(page.locator('#reviewSelected')).to_contain_text('ACCEPTED')
                    expect(page.locator('#reviewSelected')).to_contain_text('当前版本 4')
                    page.locator('#reviewReload').click()
                    expect(page.locator('#reviewItems')).to_contain_text('ACCEPTED')
                    for width in (360, 768, 1440):
                        page.set_viewport_size({'width':width, 'height':900})
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                    self.assertEqual(page.evaluate('localStorage.length + sessionStorage.length'), 0)
                    page.evaluate('configureCommunityProjectReview(null)')
                    expect(page.locator('#reviewItems')).to_be_empty()
                    expect(page.locator('#reviewVersions')).to_be_empty()
                    expect(page.locator('#reviewReload')).to_be_disabled()
                    self.assertFalse(errors)
                finally:
                    browser.close()
        finally:
            server.shutdown(); thread.join(timeout=10)


if __name__ == '__main__':
    unittest.main()
