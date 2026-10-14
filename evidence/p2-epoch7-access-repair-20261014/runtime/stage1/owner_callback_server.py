"""Loopback-only HTTP adapter for the fenced Owner callback core.

TLS is terminated by the reviewed reverse proxy. This process never accepts a
public bind address and never registers approval requests.
"""
import argparse
import json
import os
import re
import stat
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from activation_control import ActivationStore
from uk_owner_callback_core import apply


def read_secret(path, pattern, binary=False):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError('UNSAFE_SECRET_FILE')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb' if binary else 'r') as stream:
        value = stream.read(513)
    if len(value) > 512:
        raise ValueError('SECRET_TOO_LONG')
    value = value.rstrip(b'\r\n') if binary else value.strip()
    if not re.fullmatch(pattern, value):
        raise ValueError('INVALID_SECRET')
    return value


def handler(config):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def setup(self):
            BaseHTTPRequestHandler.setup(self)
            self.connection.settimeout(config.get('socket_timeout', 5))

        def log_message(self, *_):
            pass

        def send_response(self, code, message=None):
            # BaseHTTPRequestHandler otherwise discloses Python/server versions.
            self.log_request(code)
            self.send_response_only(code, message)

        def respond(self, status, body):
            data = json.dumps(body, sort_keys=True, separators=(',', ':')).encode('ascii')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != '/owner-callback':
                self.respond(404, {'accepted': False})
                return
            if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
                self.respond(415, {'accepted': False})
                return
            try:
                length = int(self.headers.get('Content-Length', ''))
            except ValueError:
                length = -1
            if not 2 <= length <= 8192:
                self.respond(413, {'accepted': False})
                return
            try:
                body = self.rfile.read(length)
            except socket.timeout:
                self.close_connection = True
                self.respond(408, {'accepted': False})
                return
            if len(body) != length:
                self.close_connection = True
                self.respond(400, {'accepted': False})
                return
            try:
                result = apply(config['activation'], body,
                               self.headers.get('Authorization', ''),
                               self.headers.get('X-Xuanjun-Signature', ''),
                               config['token'], config['hmac_key'],
                               config['owner_id'], config['owner_chat_id'])
            except (ValueError, KeyError, TypeError):
                self.respond(403, {'accepted': False})
                return
            except Exception:
                self.respond(503, {'accepted': False})
                return
            self.respond(200, result)

        def do_GET(self):
            self.respond(405, {'accepted': False})
    return Handler


class BoundedThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, request_handler, max_workers=8):
        if not isinstance(max_workers, int) or isinstance(max_workers, bool) or not 1 <= max_workers <= 32:
            raise ValueError('INVALID_MAX_WORKERS')
        self._slots = threading.BoundedSemaphore(max_workers)
        HTTPServer.__init__(self, address, request_handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(False):
            self.shutdown_request(request)
            return
        try:
            ThreadingMixIn.process_request(self, request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            ThreadingMixIn.process_request_thread(self, request, client_address)
        finally:
            self._slots.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--activation-descriptor', required=True)
    parser.add_argument('--activation-epoch-journal', required=True)
    parser.add_argument('--activation-lock', required=True)
    parser.add_argument('--auth-file', required=True)
    parser.add_argument('--hmac-key-file', required=True)
    parser.add_argument('--owner-id-file', required=True)
    parser.add_argument('--owner-chat-id-file', required=True)
    parser.add_argument('--port', type=int, default=18557)
    parser.add_argument('--socket-timeout', type=float, default=5)
    parser.add_argument('--max-workers', type=int, default=8)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit('INVALID_PORT')
    config = {
        'activation': ActivationStore(args.activation_descriptor,
                                      args.activation_epoch_journal,
                                      args.activation_lock),
        'token': read_secret(args.auth_file, r'[A-Za-z0-9_-]{32,256}'),
        'hmac_key': read_secret(args.hmac_key_file, rb'[ -~]{32,512}', binary=True),
        'owner_id': read_secret(args.owner_id_file, r'[0-9]{1,32}'),
        'owner_chat_id': read_secret(args.owner_chat_id_file, r'-?[0-9]{1,32}'),
        'socket_timeout': args.socket_timeout,
    }
    if not 0.1 <= args.socket_timeout <= 30:
        raise SystemExit('INVALID_SOCKET_TIMEOUT')
    config['activation'].read(require_active=True)
    BoundedThreadingHTTPServer(('127.0.0.1', args.port), handler(config),
                               max_workers=args.max_workers).serve_forever()


if __name__ == '__main__':
    main()
