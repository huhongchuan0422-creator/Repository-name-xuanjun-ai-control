"""Synthetic loopback-only API/worker/browser fixture, never installable service."""
import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from scripts.pr122_customer_core import Center
from scripts.pr122_customer_http import App
from scripts.pr122_customer_providers import Providers
from scripts.pr122_customer_edit_jobs import drain, get
from tests.test_pr122_customer_small_edit import SmallEditTests

fixture = SmallEditTests()
fixture.setUp()
fixture.revision = 2
fixture.body = b'<!doctype html><html><head><meta name="viewport" content="width=device-width"><style>body{margin:0;padding:24px;font-family:sans-serif}p{max-width:32rem;line-height:1.6}</style></head><body><p data-xj-small-text="TYPO_ONLY_V1">Welcome to Xuanjun</p><script>document.documentElement.dataset.fixture="ready";</script></body></html>'
fixture.install()
case = fixture.request()
stop = threading.Event()

def factory():
    return Center(fixture.root, {'v1': fixture.key}, 'v1', clock=lambda: fixture.now, mail_ready=True, scanner=lambda b: True)

api = HTTPServer(('127.0.0.1', 0), App(factory, Providers({}), 'https://wenwenwenyiyiyi.work', 'deploy/pr122-customer-center/ui', source_identity=lambda connection, headers: 'fixture-client').handler())

def worker():
    c = factory()
    try:
        while not stop.wait(.1):
            drain(c)
    finally:
        c.db.close()

class Render(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path != '/candidate':
            self.send_error(404)
            return
        c = factory()
        try:
            row = c.db.execute("SELECT id FROM preview_edit_jobs WHERE state='CANDIDATE_READY'").fetchone()
            if not row:
                self.send_error(404)
                return
            artifact = get(c, fixture.reviewer, 'project-a', row['id'])['result']['artifact']
            body = base64.b64decode(artifact['page_base64'])
            script = b'document.documentElement.dataset.fixture="ready";'
            style = b'body{margin:0;padding:24px;font-family:sans-serif}p{max-width:32rem;line-height:1.6}'
            h = lambda b: base64.b64encode(hashlib.sha256(b).digest()).decode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'sha256-" + h(script) + "'; style-src 'sha256-" + h(style) + "'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Candidate-SHA256', artifact['receipt']['after_sha256'])
            self.end_headers()
            self.wfile.write(body)
        finally:
            c.db.close()

render = HTTPServer(('127.0.0.1', 0), Render)
threads = [threading.Thread(target=api.serve_forever, daemon=True), threading.Thread(target=worker, daemon=True)]
for thread in threads:
    thread.start()
print(json.dumps({'api_port': api.server_port, 'render_port': render.server_port, 'case': case, 'before_sha256': fixture.sha, 'scope': 'SYNTHETIC_LOOPBACK_NOT_PRODUCTION'}), flush=True)
try:
    render.serve_forever()
finally:
    stop.set()
    api.shutdown()
    api.server_close()
    render.server_close()
    for thread in threads:
        thread.join(timeout=3)
    fixture.c.db.close()
    fixture.tmp.cleanup()
