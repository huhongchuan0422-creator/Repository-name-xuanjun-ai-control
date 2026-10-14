"""Transport to installed plugin-owned endpoints; never dispatch generic agent RPC."""
import hashlib
import json
import os
import stat
import subprocess

from native_child_adapter import NativeContractError


class GatewayController(object):
    def __init__(self, config, runner=None):
        self.config = config
        self.runner = runner or self._run
        self.executable = config['openclaw_bin']
        self.sha256 = config['openclaw_sha256']

    def _run(self, argv):
        info = os.lstat(self.executable)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022
                or os.path.realpath(self.executable) != self.executable):
            raise NativeContractError('Gateway executable unsafe')
        with open(self.executable, 'rb') as source:
            if hashlib.sha256(source.read()).hexdigest() != self.sha256:
                raise NativeContractError('Gateway executable changed')
        process = subprocess.Popen(argv, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env={'HOME': self.config['service_home'],
            'PATH': self.config['path'], 'LANG': 'C.UTF-8'})
        try:
            output, _ = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise NativeContractError('Gateway effect unknown; no retry')
        if process.returncode or len(output) > 1048576:
            raise NativeContractError('Gateway response unconfirmed; no retry')
        return json.loads(output.decode('utf-8'))

    def _call(self, operation, value=None, **params):
        method = ('xuanjun.execution.start' if operation in ('admit', 'launch')
                  else 'xuanjun.execution.inspect')
        params.update(operation=operation)
        if value is not None:
            params['value'] = value
        result = self.runner([self.executable, 'gateway', 'call', method,
            '--params', json.dumps(params, sort_keys=True, separators=(',', ':'),
                                   allow_nan=False), '--json'])
        if not isinstance(result, dict):
            raise NativeContractError('plugin response is not an object')
        return result

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


def create_controller(config):
    return GatewayController(config)
