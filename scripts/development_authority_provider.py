#!/usr/bin/env python3
"""Loopback formal authority issuer; intentionally separate from TEST_ONLY UI."""
from __future__ import print_function

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from development_authority import (authority_payload, close_verified_ledger,
                                   load_private_key, open_verified_ledger,
                                   sign_payload)
from secure_file_input import read_owned_secret_file


def load_config(path):
    value = json.loads(read_owned_secret_file(path, 'AUTHORITY_ISSUER_CONFIG'))
    required = {'ledger_db', 'forbidden_ledger_paths', 'issuer', 'instance_id',
                'version', 'anchor_id', 'service_id', 'bearer_token_file',
                'private_key_file'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('EXACT_AUTHORITY_ISSUER_CONFIG_REQUIRED')
    strings = required - {'forbidden_ledger_paths'}
    if any(not isinstance(value[x], str) or not value[x] for x in strings):
        raise ValueError('EXACT_AUTHORITY_ISSUER_CONFIG_REQUIRED')
    if (not isinstance(value['forbidden_ledger_paths'], list)
            or any(not isinstance(x, str) or not os.path.isabs(x)
                   for x in value['forbidden_ledger_paths'])):
        raise ValueError('EXACT_AUTHORITY_ISSUER_CONFIG_REQUIRED')
    token = read_owned_secret_file(value['bearer_token_file'],
                                   'AUTHORITY_READER_TOKEN').strip()
    if len(token) < 32:
        raise ValueError('AUTHORITY_READER_TOKEN_TOO_SHORT')
    private_key = load_private_key(read_owned_secret_file(
        value['private_key_file'], 'AUTHORITY_ISSUER_PRIVATE_KEY').encode('ascii'))
    result = dict(value); result['bearer_token'] = token
    result['private_key'] = private_key
    return result


def make_server(config, host='127.0.0.1', port=8787):
    if host not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('LOOPBACK_HOST_REQUIRED')
    # Startup identity check; each request reopens and rechecks the same path.
    connection, fd, identity = open_verified_ledger(
        config['ledger_db'], config['forbidden_ledger_paths'])
    close_verified_ledger(connection, fd)

    class Handler(BaseHTTPRequestHandler):
        server_version = 'XuanjunDevelopmentAuthority/3'
        def log_message(self, fmt, *args):
            return
        def send_json(self, status, body):
            raw = json.dumps(body, sort_keys=True, separators=(',', ':')).encode()
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            if urlsplit(self.path).path != '/api/v3/development-authority':
                self.send_json(404, {'error': 'NOT_FOUND'}); return
            auth = self.headers.get('Authorization', '')
            service = self.headers.get('X-Xuanjun-Service-Identity', '')
            if (not hmac.compare_digest(auth, 'Bearer ' + config['bearer_token'])
                    or not hmac.compare_digest(service, config['service_id'])):
                self.send_json(403, {'error': 'AUTHORITY_READER_FORBIDDEN'}); return
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            if (set(query) != {'task_id', 'request_id'}
                    or any(len(query[x]) != 1 or not query[x][0] for x in query)):
                self.send_json(400, {'error': 'EXACT_AUTHORITY_QUERY_REQUIRED'}); return
            connection = fd = None
            try:
                connection, fd, current = open_verified_ledger(
                    config['ledger_db'], config['forbidden_ledger_paths'])
                if current != identity:
                    raise ValueError('FORMAL_LEDGER_IDENTITY_CHANGED')
                request = {'task_id': query['task_id'][0],
                           'request_id': query['request_id'][0],
                           'service_id': service}
                trust = {x: config[x] for x in ('issuer', 'instance_id', 'version')}
                payload = authority_payload(connection, request, trust)
                self.send_json(200, sign_payload(payload, config['anchor_id'],
                                                 config['private_key']))
            except KeyError:
                self.send_json(404, {'error': 'TASK_NOT_FOUND'})
            except Exception as exc:
                self.send_json(503, {'error': str(exc)})
            finally:
                if connection is not None:
                    close_verified_ledger(connection, fd)
    return HTTPServer((host, port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config-file', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args(argv)
    server = make_server(load_config(args.config_file), args.host, args.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
