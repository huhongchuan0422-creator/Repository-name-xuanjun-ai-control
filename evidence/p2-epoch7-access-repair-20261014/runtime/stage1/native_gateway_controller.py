"""Transport to installed plugin-owned endpoints; never dispatch generic agent RPC."""
import hashlib
import json
import grp
import os
import pwd
import socket
import stat
import struct

from native_child_adapter import NativeContractError
from ledger_server_identity import _bounded_owned_command


def strict_json(raw):
    import math
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result or key in ('__proto__', 'constructor', 'prototype'):
                raise NativeContractError('duplicate or unsafe Gateway JSON key')
            result[key] = value
        return result
    def finite(token):
        value = float(token)
        if not math.isfinite(value):
            raise NativeContractError('nonfinite Gateway JSON')
        return value
    def constant(unused):
        raise NativeContractError('nonfinite Gateway JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=finite, parse_constant=constant)


class GatewayController(object):
    def __init__(self, config, runner=None):
        self.config = config
        self.runner = runner or self._run
        self.executable = config['openclaw_bin']
        self.sha256 = config['openclaw_sha256']

    def _run(self, argv):
        info = os.lstat(self.executable)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022
                or info.st_uid != self.config['openclaw_owner_uid'] or info.st_size > 33554432
                or os.path.realpath(self.executable) != self.executable):
            raise NativeContractError('Gateway executable unsafe')
        # Do not let a replacement FIFO/symlink turn executable pinning into an
        # unbounded open/read before the process deadline starts.
        fd = os.open(self.executable, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            def stamp(value):
                return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                    value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
            if stamp(os.fstat(fd)) != stamp(info):
                raise NativeContractError('Gateway executable changed')
            digest, total = hashlib.sha256(), 0
            while True:
                raw = os.read(fd, min(65536, 33554433 - total))
                if not raw: break
                total += len(raw)
                if total > 33554432: raise NativeContractError('Gateway executable changed')
                digest.update(raw)
            if (total != info.st_size or digest.hexdigest() != self.sha256 or
                    stamp(os.fstat(fd)) != stamp(info) or
                    stamp(os.lstat(self.executable)) != stamp(info)):
                raise NativeContractError('Gateway executable changed')
        finally:
            os.close(fd)
        try:
            output = _bounded_owned_command(argv, {'HOME': self.config['gateway_home'],
                'PATH': self.config['gateway_path'], 'LANG': 'C.UTF-8'}, 30, 1048576)
        except Exception:
            raise NativeContractError('Gateway effect unknown; no retry')
        return strict_json(output.decode('utf-8'))

    def _call(self, operation, value=None, **params):
        method = ('xuanjun.owner.delivery' if operation=='owner_cycle' else
                  'xuanjun.execution.start' if operation in ('admit', 'launch')
                  else 'xuanjun.execution.inspect')
        params.update(operation='cycle' if operation=='owner_cycle' else operation)
        if value is not None:
            params['value'] = value
        result = self.runner([self.executable, 'gateway', 'call', method,
            '--params', json.dumps(params, sort_keys=True, separators=(',', ':'),
                                   allow_nan=False), '--json'])
        if not isinstance(result, dict):
            raise NativeContractError('plugin response is not an object')
        return result

    def owner_cycle(self):
        return self._call('owner_cycle')

    def preflight(self, config):
        return self._call('preflight')

    def admit(self, request, key):
        raw = json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if hashlib.sha256(raw.encode('utf-8')).hexdigest() != key:
            raise NativeContractError('admission request hash mismatch')
        return self._call('admit', request_json=raw, idempotency_key=key)

    def launch(self, admission):
        return self._call('launch', admission)

    def inspect(self, receipt):
        return self._call('inspect', receipt)

    def report(self, receipt):
        return self._call('report', receipt)

    def stop(self, receipt):
        return self._call('stop', receipt)


class RelayController(object):
    def __init__(self, config):
        self.socket_path=config['relay_socket']
        self.server_user=config['server_user']
        self.client_group=config['client_group']

    def _call(self, operation, value=None, **params):
        server_uid=pwd.getpwnam(self.server_user).pw_uid
        client_gid=grp.getgrnam(self.client_group).gr_gid
        parent=os.path.dirname(self.socket_path)
        parent_info=os.lstat(parent)
        socket_info=os.lstat(self.socket_path)
        if (os.path.realpath(self.socket_path)!=self.socket_path
                or not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid!=0
                or parent_info.st_mode&0o022
                or not stat.S_ISSOCK(socket_info.st_mode)
                or socket_info.st_uid!=server_uid or socket_info.st_gid!=client_gid
                or stat.S_IMODE(socket_info.st_mode)!=0o660):
            raise NativeContractError('Gateway relay socket identity rejected')
        request={'operation':operation}
        request.update(params)
        if value is not None: request['value']=value
        raw=(json.dumps(request,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
        if len(raw)>1048576: raise NativeContractError('relay request limit')
        client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        client.settimeout(30)
        try:
            client.connect(self.socket_path)
            client.sendall(raw)
            response=bytearray()
            while b'\n' not in response:
                chunk=client.recv(min(65536,1048577-len(response)))
                if not chunk: raise NativeContractError('Gateway relay truncated')
                response.extend(chunk)
                if len(response)>1048576: raise NativeContractError('Gateway relay response limit')
            result=strict_json(bytes(response).split(b'\n',1)[0].decode('utf-8'))
            if not isinstance(result,dict) or set(result)!={'ok','result','error'}:
                raise NativeContractError('Gateway relay response shape')
            if result['ok'] is not True:
                raise NativeContractError('Gateway relay rejected: '+str(result.get('error')))
            return result['result']
        finally:
            client.close()

    def owner_cycle(self): return self._call('owner_cycle')
    def preflight(self, config): return self._call('preflight')
    def admit(self, request, key):
        raw=json.dumps(request,sort_keys=True,separators=(',',':'),allow_nan=False)
        if hashlib.sha256(raw.encode('utf-8')).hexdigest()!=key:
            raise NativeContractError('admission request hash mismatch')
        return self._call('admit',request_json=raw,idempotency_key=key)
    def launch(self, admission): return self._call('launch',admission)
    def inspect(self, receipt): return self._call('inspect',receipt)
    def report(self, receipt): return self._call('report',receipt)
    def stop(self, receipt): return self._call('stop',receipt)


def create_controller(config):
    # Dispatcher receives only a peer-authenticated local relay socket.
    config_path = __file__ + '.json'
    fd = os.open(config_path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022 or info.st_size > 65536):
            raise NativeContractError('unsafe transport config')
        raw = os.read(fd, 65537)
        if len(raw) > 65536:
            raise NativeContractError('transport config limit')
    finally:
        os.close(fd)
    transport = strict_json(raw.decode('utf-8'))
    required={'relay_socket','server_user','client_group'}
    if (not isinstance(transport,dict) or set(transport)!=required
            or transport.get('relay_socket')!='/run/xuanjun-development/p2-gateway.sock'
            or transport.get('server_user')!='xuanjun_dev'
            or transport.get('client_group')!='xuanjun-dispatcher'):
        raise NativeContractError('transport config keys mismatch')
    return RelayController(transport)
