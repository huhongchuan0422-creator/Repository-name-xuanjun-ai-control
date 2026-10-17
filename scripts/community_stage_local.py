"""Persistent local test host for StageRuntime. Never deploy this as production IAM.

Original per-component schemas are preserved, so no cross-file ACID is claimed.
An exclusive process lock prevents a second instance using the same directory.
"""
import fcntl
import os
import sqlite3
from pathlib import Path
from scripts.community_stage_runtime import StageRuntime
from scripts.community_demo_api import DemoService
from scripts.community_local_admin import LocalAdminPolicy
from scripts.community_order_store import connect
from scripts.community_merchant_store import open_store
from scripts.community_ad_store import open_offline
from scripts.community_refund_preview_store import open_refund_store
from scripts.community_saas_modules import connect as module_connect
from scripts.community_saas_offer_catalog import install as offer_install
from scripts.community_saas_order_preparation import install, install_lifecycle
from scripts.community_saas_offline_handoff import install_reviews
from scripts.community_saas_phase2 import OfflineSaas
from scripts.community_saas_phase2_http import make_handler
from http.server import HTTPServer


class LocalStage:
    def __init__(self, directory, bindings, merchant_scope, clock=None):
        self.handles = []
        self.lock = None
        self.server = None
        root = Path(directory)
        if root.is_symlink():
            raise ValueError('SYMLINK_DIRECTORY_DENIED')
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root = root.resolve(strict=True)
        if root.stat().st_mode & 0o077:
            raise ValueError('PRIVATE_DIRECTORY_REQUIRED')
        try:
            fd = os.open(str(root/'runtime.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            self.lock = os.fdopen(fd, 'w')
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def opened(name, opener):
                path = root/(name+'.sqlite')
                if path.is_symlink():
                    raise ValueError('SYMLINK_DATABASE_DENIED')
                if not path.exists():
                    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.close(fd)
                # Validate original schema before opening serial HTTP connection.
                checked = opener(str(path))
                checked.close()
                db = sqlite3.connect(str(path), check_same_thread=False)
                self.handles.append(db)
                db.execute('PRAGMA foreign_keys=ON')
                return db
            o = opened('orders', connect)
            m = opened('merchants', open_store)
            a = opened('ads', open_offline)
            r = opened('refunds', open_refund_store)
            q = opened('modules', module_connect)
            offer_install(q)
            def saas_orders(path):
                db = sqlite3.connect(path)
                try:
                    install(db); install_lifecycle(db); install_reviews(db)
                    return db
                except BaseException:
                    db.close()
                    raise
            s = opened('saas-orders', saas_orders)
            policy = LocalAdminPolicy(os.urandom(32).hex(), os.urandom(32).hex(), merchant_scope)
            self.demo = DemoService(o, m, a, None, r, os.urandom(32), policy)
            self.runtime = StageRuntime(self.demo, OfflineSaas(q, s, q), bindings, clock)
        except BaseException:
            self.close()
            raise

    def listen(self, principals, port=0):
        if self.server is not None:
            raise ValueError('ALREADY_LISTENING')
        if (type(principals) is not dict or
            any(p not in self.runtime.bindings for p in principals.values()) or
            any(type(t) is not str or not t.isascii() or not 32 <= len(t) <= 256 for t in principals)):
            raise ValueError('REGISTERED_TOKEN_BINDINGS_REQUIRED')
        if type(port) is not int or not (port == 0 or 1024 <= port <= 65535):
            raise ValueError('INVALID_PORT')
        parent = make_handler(self.runtime, dict(principals))
        class Handler(parent):
            def do_GET(handler):
                assets = {'/offline/community-stage': ('index.html', 'text/html'),
                          '/offline/community-stage.js': ('app.js', 'text/javascript')}
                asset = assets.get(handler.path)
                if asset is None:
                    return super(Handler, handler).do_GET()
                if handler.headers.get('Host') != '127.0.0.1:' + str(handler.server.server_port):
                    return handler.answer(403, {'error': 'HOST_DENIED'})
                blob = (Path(__file__).resolve().parents[1]/'demos'/'community-stage'/asset[0]).read_bytes()
                handler.send_response(200)
                handler.send_header('Content-Type', asset[1] + '; charset=utf-8')
                handler.send_header('Content-Length', str(len(blob)))
                handler.send_header('Cache-Control', 'no-store')
                handler.send_header('X-Content-Type-Options', 'nosniff')
                handler.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'")
                handler.end_headers()
                handler.wfile.write(blob)
        self.server = HTTPServer(('127.0.0.1', port), Handler)
        return self.server

    def close(self):
        if self.server is not None:
            self.server.server_close()
            self.server = None
        for db in reversed(self.handles):
            db.close()
        self.handles = []
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
