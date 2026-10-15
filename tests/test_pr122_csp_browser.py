import http.server, importlib.util, tempfile, threading, unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("release",ROOT/"scripts/pr122_website_release.py")
release=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(release)

class HeaderServer(http.server.ThreadingHTTPServer):
    policy=""

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Content-Security-Policy",self.server.policy)
        super().end_headers()
    def log_message(self,*_): pass

class CspBrowserTest(unittest.TestCase):
    def test_synthetic_hashed_inline_language_layout_and_interaction_in_real_chromium(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); public=root/"public"; public.mkdir()
            (public/"index.html").write_text("""<!doctype html><html><head>
<style>body{background:rgb(1, 2, 3)} #state{display:block}</style>
<script>document.documentElement.lang=localStorage.getItem('lang')||'zh-CN'</script>
</head><body><button id="go">切换</button><div id="state">ready</div>
<script>document.querySelector('#go').addEventListener('click',()=>{document.querySelector('#state').textContent='done'})</script>
</body></html>""")
            with release.Deadline(5) as deadline: result=release.write_csp_metadata(public,root,deadline)
            self.assertEqual(result["script_hash_count"],2); self.assertEqual(result["style_hash_count"],1)
            policy=__import__("json").loads((root/"release-metadata/inline-csp.json").read_text())["policy"]
            self.assertNotIn("'unsafe-inline'",policy)
            handler=lambda *a,**k: Handler(*a,directory=str(public),**k)
            server=HeaderServer(("127.0.0.1",0),handler); server.policy=policy
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True); page=browser.new_page()
                    errors=[]; page.on("console",lambda msg: errors.append(msg.text) if msg.type=="error" else None)
                    page.goto(f"http://127.0.0.1:{server.server_port}/index.html")
                    self.assertEqual(page.locator("html").get_attribute("lang"),"zh-CN")
                    self.assertEqual(page.locator("body").evaluate("e=>getComputedStyle(e).backgroundColor"),"rgb(1, 2, 3)")
                    page.locator("#go").click(); self.assertEqual(page.locator("#state").text_content(),"done")
                    self.assertEqual(errors,[]); browser.close()
            finally: server.shutdown(); thread.join()

if __name__=="__main__": unittest.main()
