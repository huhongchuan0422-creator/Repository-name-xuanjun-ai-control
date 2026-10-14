"""Journal legacy exclusion and ledger migration as one recoverable operation.

The platform adapter owns reviewed stop/fence and exact restoration primitives.
This orchestration never activates a generation or restarts an unknown writer.
"""
import hashlib
import fcntl
import json
import os
import stat
import tempfile

from ledger_install_stage import stage_existing_registry

STAGES = ('VALIDATED', 'STOP_REQUESTED', 'QUIESCED', 'STAGE_REQUESTED',
          'STAGED', 'HOLD')


def _atomic_receipt(path, value):
    parent = os.path.dirname(path)
    info = os.lstat(parent)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077 or os.path.realpath(parent) != parent):
        raise ValueError('UNSAFE_TRANSACTION_JOURNAL_PARENT')
    if os.path.lexists(path):
        old = os.lstat(path)
        if (not stat.S_ISREG(old.st_mode) or old.st_uid != os.geteuid()
                or stat.S_IMODE(old.st_mode) != 0o600):
            raise ValueError('UNSAFE_TRANSACTION_JOURNAL')
    fd, temporary = tempfile.mkstemp(prefix='.cutover-', dir=parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


class LedgerCutoverTransaction(object):
    def __init__(self, receipt_path, adapter, stage=stage_existing_registry):
        if (not os.path.isabs(receipt_path)
                or os.path.realpath(receipt_path) != receipt_path):
            raise ValueError('CANONICAL_TRANSACTION_RECEIPT_REQUIRED')
        self.receipt_path, self.adapter, self.stage = receipt_path, adapter, stage

    def execute(self, plan):
        parent = os.path.dirname(self.receipt_path)
        info = os.lstat(parent)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or os.path.realpath(parent) != parent):
            raise ValueError('UNSAFE_TRANSACTION_JOURNAL_PARENT')
        fd = os.open(self.receipt_path + '.lock',
                     os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            lock = os.fstat(fd)
            if (not stat.S_ISREG(lock.st_mode) or lock.st_uid != os.geteuid()
                    or stat.S_IMODE(lock.st_mode) != 0o600):
                raise ValueError('UNSAFE_TRANSACTION_LOCK')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('HOLD_TRANSACTION_WRITER_EXISTS')
            return self._execute_locked(plan)
        finally:
            os.close(fd)

    def _execute_locked(self, plan):
        required = {'schema', 'transaction_id', 'source', 'rollback_snapshot',
                    'staged_generation', 'repository', 'legacy_bindings'}
        if not isinstance(plan, dict) or set(plan) not in (required,required|{'legacy_isolation'}) or plan['schema'] != 1:
            raise ValueError('EXACT_CUTOVER_PLAN_REQUIRED')
        raw = json.dumps(plan, sort_keys=True, separators=(',', ':')).encode('utf-8')
        plan_sha = hashlib.sha256(raw).hexdigest()
        if os.path.lexists(self.receipt_path):
            # A crash after a stop or DB operation is not permission to replay.
            raise ValueError('HOLD_EXISTING_TRANSACTION_RECONCILIATION_REQUIRED')
        validated = self.adapter.preflight(plan)
        if validated is not True:
            raise ValueError('HOLD_CUTOVER_PREFLIGHT_FAILED')
        receipt = {'schema': 1, 'transaction_id': plan['transaction_id'],
                   'plan_sha256': plan_sha, 'stage': 'VALIDATED',
                   'source_replaced': False, 'activation_executed': False,
                   'task_replay': False}
        _atomic_receipt(self.receipt_path, receipt)

        def record(stage, **details):
            receipt.update(details)
            receipt['stage'] = stage
            _atomic_receipt(self.receipt_path, receipt)

        try:
            # Persist intent BEFORE any effect. A failure/crash leaves an
            # unambiguous reconciliation boundary and never restarts tasks.
            record('STOP_REQUESTED')
            self.adapter.stop_and_inhibit(plan['legacy_bindings'])
            observation = self.adapter.measure_quiescence(plan['legacy_bindings'])
            if (not isinstance(observation, dict)
                    or not isinstance(observation.get('proof'), dict)):
                raise ValueError('HOLD_MEASURED_PROOF_UNAVAILABLE')
            record('QUIESCED', quiescence=observation)
            record('STAGE_REQUESTED')
            result = self.stage(plan['source'], plan['rollback_snapshot'],
                                plan['staged_generation'], plan['repository'],
                                observation['proof'])
            record('STAGED', migration=result)
            return dict(receipt)
        except Exception as error:
            # Do not log raw subprocess/authentication output or reactivate
            # legacy/new writers after unclassified side effects.
            failed_stage = receipt['stage']
            record('HOLD', failed_stage=failed_stage,
                   error_type=type(error).__name__,
                   recovery='RECONCILE_BEFORE_RESTORE_OR_RESTART')
            raise
