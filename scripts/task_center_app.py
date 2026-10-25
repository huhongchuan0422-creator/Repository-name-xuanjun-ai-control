"""Loopback-only TEST_ONLY task-center web application.

The API rebuilds every projection from the canonical Supervisor SQLite file.
It exposes no mutation endpoint and cannot dispatch production work.
"""
from __future__ import print_function

import argparse
import json
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(__file__))
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from task_supervisor import Supervisor


ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
ASSET_ROOT = os.path.join(ROOT, 'demos', 'task-center-digital-twin')
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
    '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
}


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def build_handler(db_path, authority_key, tenant_id, principal_id):
    class TaskCenterHandler(BaseHTTPRequestHandler):
        server_version = 'XuanjunTaskCenter/1.0-TEST_ONLY'

        def log_message(self, fmt, *args):
            sys.stderr.write('task-center-app: ' + fmt % args + '\n')

        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; object-src 'none'; "
                             "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split('?', 1)[0]
            if path == '/api/projection':
                supervisor = None
                try:
                    supervisor = Supervisor(db_path)
                    authority = TestTenantAuthority(authority_key)
                    gateway = GatewayKernel(supervisor, authority)
                    context = authority.issue(tenant_id, principal_id)
                    self._send(200, _json_bytes(gateway.projection(context)),
                               'application/json; charset=utf-8')
                except Exception as exc:
                    self._send(500, _json_bytes({
                        'mode': 'TEST_ONLY', 'error': type(exc).__name__,
                        'detail': str(exc), 'production_status':
                        'NOT_IMPLEMENTED'}),
                        'application/json; charset=utf-8')
                finally:
                    if supervisor is not None:
                        supervisor.close()
                return
            asset = ASSETS.get(path)
            if asset is None:
                self._send(404, b'not found\n', 'text/plain; charset=utf-8')
                return
            with open(os.path.join(ASSET_ROOT, asset[0]), 'rb') as stream:
                self._send(200, stream.read(), asset[1])

        def do_POST(self):
            self._send(405, b'read only\n', 'text/plain; charset=utf-8')

    return TaskCenterHandler


def make_server(db_path, authority_key, tenant_id, principal_id,
                host='127.0.0.1', port=8765):
    if host not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('LOOPBACK_HOST_REQUIRED')
    if not os.path.isfile(db_path):
        raise ValueError('CANONICAL_SQLITE_REQUIRED')
    handler = build_handler(os.path.realpath(db_path), authority_key,
                            tenant_id, principal_id)
    return HTTPServer((host, port), handler)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--test-authority-key', required=True)
    parser.add_argument('--tenant', required=True)
    parser.add_argument('--principal', default='local-ui-viewer')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    key = args.test_authority_key.encode('utf-8')
    server = make_server(args.db, key, args.tenant, args.principal,
                         args.host, args.port)
    receipt = {'state': 'STARTED', 'mode': 'TEST_ONLY',
               'url': 'http://%s:%d/' % server.server_address,
               'db': os.path.realpath(args.db), 'tenant_id': args.tenant,
               'mutation_api': 'DISABLED',
               'production_status': 'NOT_IMPLEMENTED'}
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True), flush=True)
    previous_term = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM,
                  lambda _signum, _frame: (_ for _ in ()).throw(
                      KeyboardInterrupt()))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        signal.signal(signal.SIGTERM, previous_term)
        print(json.dumps({'state': 'STOPPED', 'mode': 'TEST_ONLY'},
                         sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
