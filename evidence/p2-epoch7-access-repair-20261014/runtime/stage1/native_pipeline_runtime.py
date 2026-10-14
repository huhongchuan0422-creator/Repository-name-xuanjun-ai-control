"""Connect the existing pipeline to an explicitly reviewed native controller.

No Gateway RPCs are invented here. The controller must supply the installed
launch/inspect/report implementation and enforce isolation before launch.
"""
import hashlib
import json
import time

from native_child_adapter import NativeContractError


class NativePipelineWorker(object):
    requires_boundary_proof = True

    def __init__(self, controller, claim, workdir, sandbox, clock=None, wait=None):
        if sandbox not in ('workspace-write', 'read-only'):
            raise NativeContractError('native sandbox rejected')
        self.controller, self.claim = controller, dict(claim)
        self.workdir, self.sandbox = workdir, sandbox
        self.clock, self.wait = clock or time.monotonic, wait or time.sleep

    def run(self, prompt, timeout_seconds, heartbeat, lease_check):
        raise NativeContractError('delegated model dispatch prohibited by owner policy')
        if not lease_check():
            raise NativeContractError('native lease expired before admission')
        request = {
            'task_id': self.claim['task_id'], 'spec_hash': self.claim['spec_hash'],
            'lease': self.claim['worker_id'], 'fence': self.claim['fence'],
            'epoch': self.claim['epoch'], 'generation': self.claim['generation'],
            'instance': self.claim['instance'], 'workdir': self.workdir,
            'sandbox': self.sandbox, 'provider': 'openai', 'model': 'gpt-5.6-sol',
            'prompt': prompt, 'timeout_seconds': timeout_seconds}
        key = hashlib.sha256(json.dumps(request, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        # This call must persist the idempotent launch intent in the EXISTING
        # canonical controller. Missing proof must fail before model dispatch.
        admission = self.controller.admit(request, key)
        if (not isinstance(admission, dict) or admission.get('request') != request
                or admission.get('idempotency_key') != key
                or admission.get('isolation_enforced') is not True):
            raise NativeContractError('native isolation admission unconfirmed')
        if not lease_check():
            raise NativeContractError('native lease expired before launch')
        receipt = self.controller.launch(admission)
        if (not isinstance(receipt, dict) or not receipt.get('run_id')
                or not receipt.get('session_id') or not receipt.get('execution_unit_id')
                or receipt.get('idempotency_key') != key):
            raise NativeContractError('native launch effect unknown; do not replay')
        deadline = self.clock() + timeout_seconds
        while True:
            if not lease_check():
                # A stop request is not a proof that descendants stopped.
                self.controller.stop(receipt)
                raise NativeContractError('native lease lost; stop reconciliation required')
            heartbeat()
            observed = self.controller.inspect(receipt)
            if (not isinstance(observed, dict) or any(observed.get(k) != receipt[k]
                    for k in ('run_id', 'session_id', 'execution_unit_id'))):
                raise NativeContractError('native observation identity unconfirmed')
            if observed.get('state') in ('completed', 'failed', 'cancelled'):
                if (observed.get('process_alive') is not False
                        or observed.get('unit_active') is not False
                        or observed.get('descendants_exited') is not True):
                    raise NativeContractError('native execution stop unconfirmed')
                report = self.controller.report(receipt)
                if (not isinstance(report, dict) or report.get('request') != request
                        or any(report.get(k) != receipt[k] for k in
                               ('run_id', 'session_id', 'execution_unit_id'))
                        or report.get('idempotency_key') != key
                        or not isinstance(report.get('durable_receipt_id'), str)
                        or not report['durable_receipt_id']
                        or not isinstance(report.get('result'), dict)):
                    raise NativeContractError('native durable result unconfirmed')
                result = dict(report['result'])
                if (result.get('provider') != 'openai' or result.get('model') != 'gpt-5.6-sol'
                        or result.get('model_verified') is not True):
                    raise NativeContractError('native observed model unconfirmed')
                result['worker_boundary_stopped'] = True
                return result
            if observed.get('state') not in ('queued', 'running'):
                raise NativeContractError('native process/effects unknown; do not replay')
            if self.clock() >= deadline:
                self.controller.stop(receipt)
                raise NativeContractError('native deadline; stop reconciliation required')
            self.wait(min(1, max(0, deadline - self.clock())))


class ExistingOutboxNotifier(object):
    """Use the existing controller outbox; never create a delivery database."""
    REPOSITORY = 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
    PR = 17

    def __init__(self, controller):
        self.controller = controller

    def send(self, report, idempotency_key):
        receipt = self.controller.notify(self.REPOSITORY, self.PR, report,
                                         idempotency_key)
        return self._check(receipt, idempotency_key)

    def reconcile(self, idempotency_key):
        receipt = self.controller.notification_receipt(self.REPOSITORY, self.PR,
                                                       idempotency_key)
        if receipt is None:
            return None
        return self._check(receipt, idempotency_key)

    @staticmethod
    def _check(receipt, key):
        if (not isinstance(receipt, dict) or receipt.get('idempotency_key') != key
                or receipt.get('repository') != ExistingOutboxNotifier.REPOSITORY
                or receipt.get('pr_number') != ExistingOutboxNotifier.PR
                or not isinstance(receipt.get('message_id'), str)
                or not receipt['message_id']):
            raise NativeContractError('fixed PR17 notification ACK unconfirmed')
        return {'idempotency_key': key, 'message_id': receipt['message_id']}


class NativePipelineRuntime(object):
    def __init__(self, controller, notifier=None):
        methods = ('admit', 'launch', 'inspect', 'report', 'stop', 'preflight')
        if notifier is None:
            methods += ('notify', 'notification_receipt')
        if any(not callable(getattr(controller, name, None)) for name in methods):
            raise NativeContractError('complete installed controller/outbox required')
        self.controller = controller
        self.notifier = notifier or ExistingOutboxNotifier(controller)

    def preflight(self, config):
        # Require actual installed-controller acknowledgement BEFORE claiming
        # work or opening a new ledger. No returned model text is consulted.
        result = self.controller.preflight(config)
        if (not isinstance(result, dict) or result.get('ready') is not True
                or result.get('canonical_existing') is not True
                or result.get('isolation_enforced') is not True
                or result.get('outbox_existing') is not True):
            raise NativeContractError('installed native runtime is not ready')

    def worker(self, claim, workdir, sandbox):
        return NativePipelineWorker(self.controller, claim, workdir, sandbox)


def load_reviewed_controller(path, digest, config):
    """Execute exactly hash-verified root-owned installed controller bytes.

    This is an explicit deployment dependency, not a claim that a controller
    endpoint has already been installed. No dynamic import of worker bytes.
    """
    import os
    import stat
    import re
    if (not isinstance(path, str) or not os.path.isabs(path)
            or os.path.realpath(path) != path
            or not re.fullmatch(r'[0-9a-f]{64}', digest or '')):
        raise NativeContractError('pinned canonical controller required')
    parent = os.path.dirname(path)
    while True:
        info = os.lstat(parent)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise NativeContractError('controller parent is not root-protected')
        if parent == '/':
            break
        parent = os.path.dirname(parent)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                 | getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022 or info.st_size > 262144):
            raise NativeContractError('unsafe installed controller')
        raw = b''
        while len(raw) <= 262144:
            part = os.read(fd, 65536)
            if not part:
                break
            raw += part
        if len(raw) > 262144 or hashlib.sha256(raw).hexdigest() != digest:
            raise NativeContractError('installed controller hash mismatch')
    finally:
        os.close(fd)
    namespace = {'__name__': 'xuanjun_reviewed_native_controller', '__file__': path}
    exec(compile(raw, path, 'exec'), namespace)
    factory = namespace.get('create_controller')
    if not callable(factory):
        raise NativeContractError('installed controller factory missing')
    from native_github_notifier import FixedPr17GithubNotifier
    notifier = FixedPr17GithubNotifier(config['gh_bin'], config['service_home'], config['path'])
    runtime = NativePipelineRuntime(factory(config), notifier=notifier)
    runtime.binary_sha256 = digest
    return runtime
