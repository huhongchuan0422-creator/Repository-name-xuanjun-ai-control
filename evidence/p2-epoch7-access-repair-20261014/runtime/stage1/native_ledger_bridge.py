#!/usr/bin/env python3
"""Synchronous client of the EXISTING ledger socket; no direct DB access."""
import argparse
import json
import os
import socket
import stat
import struct
import sys
from ledger_server_identity import POLICY_PATH, SOCKET_PATH, load_server_verifier
from ledger_read_transport import (MonotonicIODeadline, server_session,
                                   peer_credentials, _read_response, _strict_json)


def main(argv=None, server_verifier=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args(argv)
    fd = os.open(args.config, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 65536:
            raise ValueError('protected socket client config required')
        config = _strict_json(os.read(fd, 65537))
    finally:
        os.close(fd)
    validate_config(config)
    if server_verifier is None:
        server_verifier = load_server_verifier()
    path = config['socket_path']
    if not os.path.isabs(path) or os.path.realpath(path) != path:
        raise ValueError('canonical ledger socket required')
    raw = sys.stdin.buffer.read(1048577)
    if len(raw) > 1048576:
        raise ValueError('native request limit')
    payload = _strict_json(raw)
    if isinstance(payload,dict) and payload.get('operation')=='owner_delivery_cycle':
        if set(payload)!={'operation','request'} or payload['request'] is not None:
            raise ValueError('owner cycle params rejected')
        from owner_feishu_bridge_cycle import run_cycle
        from owner_feishu_https import installed_binding,OwnerFeishuHTTPS
        binding=installed_binding()
        api=OwnerFeishuHTTPS(binding)
        result=run_cycle(lambda request: socket_call(config,{'operation':'owner_delivery','request':request},server_verifier=server_verifier),api,binding)
    else:
        result=socket_call(config,payload,server_verifier=server_verifier)
    sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',', ':'),allow_nan=False))


def validate_config(config):
    if (type(config) is not dict or set(config) != {'socket_path', 'server_identity_policy'}
            or config['socket_path'] != SOCKET_PATH or config['server_identity_policy'] != POLICY_PATH):
        raise ValueError('socket client config mismatch')


def socket_call(config, payload, server_verifier=None):
    validate_config(config)
    if server_verifier is None:
        server_verifier = load_server_verifier()
    deadline = MonotonicIODeadline(10, message='NATIVE_SOCKET_DEADLINE_EXCEEDED')
    path = config['socket_path']
    packed = (json.dumps({'operation': 'NATIVE_GATEWAY', 'payload': payload},
                        sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    if len(packed) >= 1048576:
        raise ValueError('native wire limit')
    session = server_session(server_verifier, path, deadline)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        deadline.arm(connection)
        connection.connect(path)
        if session.verify(peer_credentials(connection, deadline)) is not True:
            raise ValueError('ledger socket server identity rejected')
        deadline.arm(connection)
        connection.sendall(packed)
        deadline.check()
        value = _read_response(connection, deadline)
        if (not isinstance(value, dict) or set(value) != {'accepted', 'result'}
                or value['accepted'] is not True):
            raise ValueError('native operation unconfirmed')
        if session.finish(peer_credentials(connection, deadline)) is not True:
            raise ValueError('ledger socket server identity changed')
        deadline.check()
        return value['result']
    finally:
        connection.close()


if __name__ == '__main__':
    try:main()
    except Exception:
        sys.stderr.write('HOLD_CANONICAL_SOCKET\n')
        sys.exit(2)
