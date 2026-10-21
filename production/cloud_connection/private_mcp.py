"""Private stdio MCP adapter: status and already-approved OS release files only.

No network listener, cloud credentials, shell, dispatch, installation or new
filesystem paths from tool arguments. Requires separately enrolled transport
and workspace access; writing this file does not create that enrollment.
"""
import base64
import json
import os
import re
from pathlib import Path
import sqlite3
import stat
import sys

from .queue import Hold, TOKEN, unique
from .runtime import PrivateStore

PROTOCOLS = ('2024-11-05', '2025-03-26', '2025-06-18')
TOOLS = [
    {'name': 'connection_status',
     'description': 'Read an existing cloud connection request status. Never dispatches or retries a task.',
     'inputSchema': {'type': 'object', 'properties': {'request_id': {'type': 'string'}},
                     'required': ['request_id'], 'additionalProperties': False},
     'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False}},
    {'name': 'read_result_file',
     'description': 'Retrieve the already approved, non-sensitive /etc/os-release result of a SUCCESS request. No arbitrary path or secret file access.',
     'inputSchema': {'type': 'object', 'properties': {'request_id': {'type': 'string'}},
                     'required': ['request_id'], 'additionalProperties': False},
     'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False}},
]


class PrivateMcp:
    def __init__(self, state_root, project_files=None):
        self.root = str(state_root)
        self.project_files = project_files
        self.initialized = False
        self.ready = False
        self.guard = PrivateStore(self.root)
        self.files = PrivateStore(self.root + '/private-results')
        fd = os.open('queue.sqlite', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.guard.fd)
        try:
            s = os.fstat(fd)
            if (not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_nlink != 1
                    or stat.S_IMODE(s.st_mode) != 0o600):
                raise Hold('STATE_DATABASE_METADATA')
        finally:
            os.close(fd)
        self.db = sqlite3.connect('file:' + self.root + '/queue.sqlite?mode=ro', uri=True, timeout=0)
        self.db.execute('PRAGMA query_only=ON')

    def close(self):
        self.db.close()
        self.files.close()
        self.guard.close()

    def lookup(self, arguments):
        if (type(arguments) is not dict or set(arguments) != {'request_id'}
                or type(arguments['request_id']) is not str or not TOKEN.fullmatch(arguments['request_id'])):
            raise Hold('EXACT_REQUEST_ID_REQUIRED')
        rid = arguments['request_id']
        row = self.db.execute('SELECT state,invoke_id,receipt_json,request_json,actor_id '
                              'FROM connection_jobs WHERE request_id=?', (rid,)).fetchone()
        if row is None:
            raise Hold('REQUEST_NOT_FOUND')
        if row[4] != 332398908:
            raise Hold('REQUEST_ACTOR_NOT_ENROLLED')
        request = json.loads(row[3], object_pairs_hook=unique)
        if request.get('request_id') != rid:
            raise Hold('STATE_IDENTITY_MISMATCH')
        return rid, row, request

    def read_project_chunk(self, arguments, now):
        # Internal candidate contact point only. Not a registered MCP tool;
        # main() supplies no adapter, catalog or authenticated identity source.
        if self.project_files is None:
            raise Hold('PROJECT_TRANSFER_NOT_ENROLLED')
        return self.project_files.read(arguments, now)

    def call(self, name, arguments):
        if name not in ('connection_status', 'read_result_file'):
            raise Hold('TOOL_NOT_ENROLLED')
        rid, row, request = self.lookup(arguments)
        state, invoke, raw_receipt = row[:3]
        value = {'request_id': rid, 'state': state, 'invoke_id': invoke,
                 'target': request['target'], 'production_authorization': 'NOT_GRANTED'}
        if name == 'read_result_file':
            if (state != 'SUCCESS' or request.get('operation') != 'fetch_os_release'
                    or request.get('arguments') != {'path': '/etc/os-release', 'max_bytes': 65536}):
                raise Hold('NO_APPROVED_FILE_RESULT')
            receipt = json.loads(raw_receipt, object_pairs_hook=unique)
            if receipt.get('state') != 'SUCCESS' or receipt.get('invoke_id') != invoke:
                raise Hold('RESULT_IDENTITY_MISMATCH')
            ref = receipt.get('file_ref', '')
            if not ref.startswith('server-private:'):
                raise Hold('PRIVATE_REFERENCE')
            data = self.files.read(ref.split(':', 1)[1])
            import hashlib
            digest = hashlib.sha256(data).hexdigest()
            if digest != receipt.get('sha256') or len(data) != receipt.get('bytes'):
                raise Hold('PRIVATE_FILE_SHA')
            value.update(bytes=len(data), sha256=digest, mime_type='text/plain',
                         encoding='base64', data=base64.b64encode(data).decode())
        return {'content': [{'type': 'text', 'text': json.dumps(value, sort_keys=True)}],
                'structuredContent': value, 'isError': False}

    def handle(self, message):
        if (type(message) is not dict or message.get('jsonrpc') != '2.0'
                or type(message.get('method')) is not str):
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}}
        method = message['method']
        if 'id' not in message:
            if method == 'notifications/initialized' and self.initialized:
                self.ready = True
            # Notifications never invoke tools or read result files.
            return None
        mid = message['id']
        if type(mid) not in (int, str):
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid id'}}
        p = message.get('params', {})
        try:
            if type(p) is not dict:
                raise Hold('PARAMETERS')
            if method == 'initialize':
                # Tunnel discovery and the connector can initialize the same
                # stdio child. Repeating this handshake grants no authority
                # and must neither fail nor reset an established ready state.
                version = p.get('protocolVersion')
                if type(version) is not str or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', version):
                    raise Hold('PROTOCOL_VERSION_FORMAT')
                negotiated = version if version in PROTOCOLS else PROTOCOLS[-1]
                self.initialized = True
                result = {'protocolVersion': negotiated, 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'xuanjun-private-connection', 'version': '1.0.0'},
                          'instructions': 'Read existing connection status and approved non-sensitive OS release results only. No dispatch, arbitrary paths, production approval or shell. Private transport/workspace enrollment is required separately.'}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                if not self.ready:
                    raise Hold('INITIALIZATION_REQUIRED')
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                if not self.ready:
                    raise Hold('INITIALIZATION_REQUIRED')
                if set(p) - {'_meta'} != {'name', 'arguments'} or ('_meta' in p and type(p['_meta']) is not dict):
                    raise Hold('TOOL_CALL_FIELDS')
                result = self.call(p['name'], p['arguments'])
            else:
                return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': 'Method not found'}}
        except (Hold, OSError, sqlite3.Error, ValueError, KeyError, TypeError):
            # No filesystem paths, file contents or credential exception text.
            return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32000, 'message': 'HOLD_PRIVATE_TOOL'}}
        return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def main():
    if os.geteuid() != 0 or os.uname().nodename != 'iZd7oeikknn1z21sq6ji6zZ':
        raise SystemExit('EXACT_ENROLLED_UK_HOST_ONLY')
    adapter = PrivateMcp('/var/lib/xuanjun-cloud-connection')
    try:
        while True:
            raw = sys.stdin.buffer.readline(16385)
            if not raw:
                break
            if len(raw) > 16384 or not raw.endswith(b'\n'):
                raise SystemExit('MCP_INPUT_BOUND')
            try:
                msg = json.loads(raw.decode(), object_pairs_hook=unique,
                                 parse_constant=lambda x: (_ for _ in ()).throw(Hold('NONFINITE')))
                response = adapter.handle(msg)
            except (ValueError, UnicodeError, Hold):
                response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
            if response is not None:
                print(json.dumps(response, sort_keys=True), flush=True)
    finally:
        adapter.close()


if __name__ == '__main__':
    main()
