#!/usr/bin/env python3
"""Loopback formal authority issuer; intentionally separate from TEST_ONLY UI."""
from __future__ import print_function

import argparse
import base64
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from development_authority import (authority_payload, close_verified_ledger,
                                   canonical_bytes, load_private_key, load_public_key, open_verified_ledger,
                                   sign_payload, SQLiteReplayGuard)
from secure_file_input import read_owned_secret_file


def load_config(path):
    value = json.loads(read_owned_secret_file(path, 'AUTHORITY_ISSUER_CONFIG'))
    required = {'ledger_db', 'replay_db', 'replay_device', 'replay_inode',
                'forbidden_ledger_paths', 'issuer', 'instance_id',
                'version', 'anchor_id', 'service_id', 'bearer_token_file',
                'private_key_file', 'deployment_public_key_file',
                'deployment_anchor_id', 'deployment_signature'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('EXACT_AUTHORITY_ISSUER_CONFIG_REQUIRED')
    strings = required - {'forbidden_ledger_paths', 'replay_device', 'replay_inode',
                          'deployment_signature'}
    if any(not isinstance(value[x], str) or not value[x] for x in strings):
        raise ValueError('EXACT_AUTHORITY_ISSUER_CONFIG_REQUIRED')
    if (not isinstance(value['forbidden_ledger_paths'], list)
            or any(not isinstance(x, str) or not os.path.isabs(x)
                   for x in value['forbidden_ledger_paths'])):
        raise ValueError('EXACT_AUTHORITY_ISSUER_CONFIG_REQUIRED')
    signature=value['deployment_signature']
    if not isinstance(signature,dict) or set(signature)!={'algorithm','anchor_id','canonical_sha256','value'}:
        raise ValueError('SIGNED_DEPLOYMENT_CONFIG_REQUIRED')
    unsigned={k:v for k,v in value.items() if k!='deployment_signature'}
    raw=canonical_bytes(unsigned)
    if (signature['algorithm']!='Ed25519'
            or signature['anchor_id']!=value['deployment_anchor_id']
            or signature['canonical_sha256']!=hashlib.sha256(raw).hexdigest()):
        raise ValueError('SIGNED_DEPLOYMENT_CONFIG_REQUIRED')
    deployment_key=load_public_key(read_owned_secret_file(
        value['deployment_public_key_file'],'AUTHORITY_DEPLOYMENT_PUBLIC_KEY').encode('ascii'))
    try: deployment_key.verify(base64.b64decode(signature['value'],validate=True),raw)
    except Exception: raise ValueError('SIGNED_DEPLOYMENT_CONFIG_INVALID')
    token = read_owned_secret_file(value['bearer_token_file'],
                                   'AUTHORITY_READER_TOKEN').strip()
    if len(token) < 32:
        raise ValueError('AUTHORITY_READER_TOKEN_TOO_SHORT')
    private_key = load_private_key(read_owned_secret_file(
        value['private_key_file'], 'AUTHORITY_ISSUER_PRIVATE_KEY').encode('ascii'))
    replay = SQLiteReplayGuard(value['replay_db'])
    replay_identity = os.stat(value['replay_db'], follow_symlinks=False)
    replay.close()
    if ((replay_identity.st_dev, replay_identity.st_ino) !=
            (value['replay_device'], value['replay_inode'])):
        raise ValueError('FORMAL_REPLAY_LEDGER_IDENTITY_REQUIRED')
    result = dict(value); result['bearer_token'] = token
    result['private_key'] = private_key
    return result


def make_server(config, host='127.0.0.1', port=8787):
    if host not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('LOOPBACK_HOST_REQUIRED')
    # Startup identity check; each request reopens and rechecks the same path.
    connection, fd, identity = open_verified_ledger(
        config['ledger_db'], config['forbidden_ledger_paths'], formal_only=True)
    close_verified_ledger(connection, fd)
    replay_identity = (config['replay_device'], config['replay_inode'])

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
            if (set(query) != {'task_id', 'request_id', 'purpose', 'target_sha256'}
                    or any(len(query[x]) != 1 or not query[x][0] for x in query)):
                self.send_json(400, {'error': 'EXACT_AUTHORITY_QUERY_REQUIRED'}); return
            connection = fd = None
            try:
                connection, fd, current = open_verified_ledger(
                    config['ledger_db'], config['forbidden_ledger_paths'], formal_only=True)
                if current != identity:
                    raise ValueError('FORMAL_LEDGER_IDENTITY_CHANGED')
                request = {'task_id': query['task_id'][0],
                           'request_id': query['request_id'][0],
                           'service_id': service,
                           'purpose': query['purpose'][0],
                           'target_sha256': query['target_sha256'][0]}
                trust = {x: config[x] for x in ('issuer', 'instance_id', 'version')}
                payload = authority_payload(connection, request, trust)
                current_replay = os.stat(config['replay_db'], follow_symlinks=False)
                if (current_replay.st_dev, current_replay.st_ino) != replay_identity:
                    raise ValueError('FORMAL_REPLAY_LEDGER_IDENTITY_CHANGED')
                guard = SQLiteReplayGuard(config['replay_db'])
                try:
                    replay_key = (config['issuer'], config['instance_id'],
                                  request['purpose'], request['target_sha256'],
                                  request['request_id'])
                    if not guard(replay_key):
                        self.send_json(409, {'error': 'AUTHORITY_REPLAY_REJECTED'})
                        return
                finally:
                    guard.close()
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
