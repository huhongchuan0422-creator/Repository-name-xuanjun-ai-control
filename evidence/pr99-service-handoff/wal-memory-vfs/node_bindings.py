"""Opt-in bindings for original capture I/O and original SWAS query transport.

No dispatch, path guard implementation, trust issuer, Writer or automatic entry.
An admitted original controller must supply its held fd / original PathGuard.
Synthetic integration tests are not host, fence or M99 dynamic acceptance.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time

import lost_invoke_reconciliation as lost
from sqlite_wal_vfs import recover


class BindingHold(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise BindingHold(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return lost.encode(value)


def finalize_captured_sqlite(main, wal, schema_sha256, output_fd,
                             expected_fence, verify_fence, assert_output_binding):
    """Recover bytes and write only through the original exclusive held fd.

    This does not capture a live database or verify authority. The callbacks must
    be from the admitted caller, not functions invented by a deployment wrapper.
    No truncation, unlink, cleanup or retry; interrupted outputs stay preserved.
    """
    require(type(output_fd) is int and callable(verify_fence) and
            callable(assert_output_binding), 'ADMITTED_OUTPUT_AND_FENCE_REQUIRED')
    require(type(expected_fence) is str and lost.SHA.fullmatch(expected_fence), 'FENCE_DIGEST_REQUIRED')
    before = os.fstat(output_fd)
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
            before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o600 and
            before.st_size == 0 and fcntl.fcntl(output_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDWR and
            not fcntl.fcntl(output_fd, fcntl.F_GETFL) & os.O_APPEND, 'EXCLUSIVE_EMPTY_OUTPUT_REQUIRED')
    identity = (before.st_dev, before.st_ino)

    def bound():
        require(assert_output_binding() is True, 'OUTPUT_BINDING_REQUIRED')
        current = os.fstat(output_fd)
        require((current.st_dev, current.st_ino) == identity and current.st_nlink == 1,
                'OUTPUT_IDENTITY_DRIFT')
        require(verify_fence() == expected_fence, 'FENCE_CHANGED_PRESERVE')

    bound()
    result, recovery = recover(main, wal, schema_sha256, bound)
    bound()
    require(os.fstat(output_fd).st_size == 0, 'OUTPUT_CHANGED_BEFORE_WRITE')
    position = 0
    while position < len(result):
        bound()
        written = os.pwrite(output_fd, result[position:position+1048576], position)
        require(written > 0, 'OUTPUT_PARTIAL_WRITE_PRESERVE')
        position += written
    os.fsync(output_fd)
    bound()
    require(os.fstat(output_fd).st_size == len(result) and
            os.pread(output_fd, len(result)+1, 0) == result, 'OUTPUT_POSTCHECK_UNKNOWN')
    os.fchmod(output_fd, 0o400)
    os.fsync(output_fd)
    bound()
    return {'class': 'FINAL_FENCED_SQLITE_CANDIDATE', 'fence_proof_sha256': expected_fence,
            'sha256': sha(result), 'bytes': len(result), 'schema_sha256': schema_sha256,
            'integrity': 'PASS', 'source_wal_captured': wal is not None,
            'source_database_opened': False, 'recovery': recovery}


def snapshot_sqlite_with_original_io(paths, source, destination, verify_fence,
                                    expected_schema_sha256, clock=time.monotonic):
    """Original PathGuard protocol -> WAL VFS -> held output -> original receipt.

    No substitute guard is constructed. This function requires the separately
    released/admitted original M99 guard. Absence is a dependency HOLD, not an
    instruction to fall back to the old pathname SQLite capture implementation.
    """
    require(paths is not None and all(callable(getattr(paths, method, None)) for method in
        ('check', 'read', 'exists', 'mkdir', 'write', 'create_fd', 'sync')),
        'ORIGINAL_ADMITTED_MATERIAL_IO_REQUIRED')
    source, destination = Path(source), Path(destination)
    require(source.is_absolute() and destination.is_absolute() and '..' not in source.parts and
            '..' not in destination.parts and source != destination and
            source not in destination.parents and destination not in source.parents,
            'MATERIAL_SCOPE')
    started = clock()
    paths.check()
    proof = verify_fence()
    require(type(proof) is str and lost.SHA.fullmatch(proof), 'FENCE_DIGEST_REQUIRED')

    def bound():
        require(clock()-started < 90, 'CAPTURE_DEADLINE_PRESERVE')
        require(paths.check() is True, 'MATERIAL_IO_BINDING_REQUIRED')
        require(verify_fence() == proof, 'FENCE_CHANGED_PRESERVE')
        return proof

    bound()
    require(not paths.exists(source.with_name(source.name+'-journal')), 'ROLLBACK_JOURNAL_HOLD')
    wal_path = source.with_name(source.name+'-wal')
    wal_present = paths.exists(wal_path)
    main = paths.read(source, 67108864)
    wal = paths.read(wal_path, 67108864) if wal_present else None
    bound()
    paths.mkdir(destination, mode=0o700)
    paths.sync(destination.parent)
    capture = destination/'captured'
    paths.mkdir(capture, mode=0o700)
    paths.write(capture/'source.db', main, 0o600)
    if wal_present:
        paths.write(capture/'source.db-wal', wal, 0o600)
    target = destination/'final.db'
    fd = paths.create_fd(target, mode=0o600)
    try:
        receipt = finalize_captured_sqlite(main, wal, expected_schema_sha256, fd,
            proof, bound, paths.check)
    finally:
        os.close(fd)
    require(paths.exists(wal_path) == wal_present and paths.read(source, 67108864) == main and
            (not wal_present or paths.read(wal_path, 67108864) == wal), 'SOURCE_DRIFT_PRESERVE')
    bound()
    require(sha(paths.read(target, 67108864)) == receipt['sha256'], 'OUTPUT_POSTCHECK_UNKNOWN')
    paths.sync(destination)
    paths.write(destination/'sqlite-checkpoint.receipt.json', encode(receipt), 0o600)
    bound()
    return receipt


class ReconciledQueryTransport:
    """Attach lost-ID recovery to the ORIGINAL DomesticStartTransport instance.

    query_only uses original receipt validation, original filenames and held fd;
    it never calls the original pathname query or dispatch method. The persistent
    controller and trust callback are external required inputs, not created here.
    """
    def __init__(self, original, directory_fd, assert_directory_binding):
        require(type(directory_fd) is int and callable(assert_directory_binding),
                'ORIGINAL_ADMITTED_CONTROLLER_REQUIRED')
        lost.validate_intent(original.intent)
        require(original.intent['command_sha256'] == sha(original.shell.encode()) and
                original.operation_id == original.intent['operation_id'] and
                original.source_sha == original.intent['source_sha256'], 'ORIGINAL_TRANSPORT_BINDING')
        self.original = original
        self.fd = directory_fd
        self.check = assert_directory_binding
        self.intent = json.loads(encode(original.intent))
        self._bound()

    def _bound(self):
        require(self.check() is True, 'ORIGINAL_CONTROLLER_BINDING_REQUIRED')
        own = os.fstat(self.fd)
        named = os.stat(self.original.state, follow_symlinks=False)
        require(stat.S_ISDIR(own.st_mode) and stat.S_ISDIR(named.st_mode) and
                (own.st_dev, own.st_ino) == (named.st_dev, named.st_ino) and
                own.st_uid == os.geteuid() and stat.S_IMODE(own.st_mode) == 0o700,
                'ORIGINAL_CONTROLLER_IDENTITY')
        require(self.original.intent == self.intent, 'TRANSPORT_INTENT_MUTATED')
        return True

    def _read(self, name, optional=False):
        self._bound()
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=self.fd)
        except FileNotFoundError:
            require(optional, 'ORIGINAL_RECORD_MISSING')
            return None
        try:
            value = lost._read(fd)
            linked = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            own = os.fstat(fd)
            require((linked.st_dev, linked.st_ino) == (own.st_dev, own.st_ino), 'RECORD_NAME_DRIFT')
        finally:
            os.close(fd)
        self._bound()
        return value

    def _persist(self, value):
        self._bound()
        name = 'cloud-start.result.json'
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=self.fd)
        except FileExistsError:
            require(self._read(name) == value, 'CONCURRENT_RESULT_CONFLICT_PRESERVE')
            return
        try:
            self._bound()
            raw = encode(value); position = 0
            while position < len(raw):
                count = os.write(fd, raw[position:])
                require(count > 0, 'RESULT_PARTIAL_WRITE_PRESERVE')
                position += count
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        require(self._read(name) == value, 'RESULT_PERSIST_POSTCHECK_UNKNOWN')

    def dispatch_once(self):
        raise BindingHold('RECONCILIATION_QUERY_ONLY_NO_DISPATCH')

    def query_only(self):
        self._bound()
        require(self._read('cloud-start.intent.json') == self.intent, 'ORIGINAL_INTENT_BINDING')
        found = lost.bind_missing_invoke(self.fd, self._bound,
                                        self.original.rpc, self.original.credentials)
        if found['status'] == 'UNKNOWN_NO_MATCH_NO_REPLAY':
            return {'status': 'UNKNOWN_NO_INVOKE_NO_REPLAY', 'operation_id': self.intent['operation_id']}
        record = self._read('cloud-start.invocation.json'); invoke = found['invoke_id']
        require(record == dict(self.intent, invoke_id=invoke), 'ORIGINAL_INVOCATION_BINDING')
        saved = self._read('cloud-start.result.json', optional=True)
        if saved is not None:
            return self.original.validate_saved_result(saved, invoke)
        try:
            response = self.original.rpc(lost.ENDPOINT, '2020-06-01', 'DescribeInvocationResult',
                self.original.credentials, RegionId=lost.REGION, InstanceId=lost.INSTANCE, InvokeId=invoke)
            detail = response.get('InvocationResult', {})
            require(type(detail) is dict and detail.get('InstanceId') == lost.INSTANCE and
                    detail.get('InvokeId') == invoke, 'REMOTE_RESULT_IDENTITY')
            status = detail.get('InvocationStatus')
            if status in ('Pending', 'Running', 'Stopping'):
                result = {'status': 'PENDING_QUERY_ONLY', 'invoke_id': invoke,
                          'operation_id': self.intent['operation_id']}
            else:
                require(status in ('Success', 'Failed', 'Error', 'Timeout', 'Cancelled', 'Stopped') and
                        type(detail.get('ExitCode')) is int, 'REMOTE_RESULT_STATUS_UNKNOWN')
                if status != 'Success' or detail['ExitCode'] != 0:
                    terminal = 'REMOTE_FAILED_QUERY_HOST_STATE_NO_REPLAY'
                else:
                    output = detail.get('Output')
                    require(type(output) is str and len(output) <= 40000, 'OUTPUT_BOUND')
                    try:
                        value = json.loads(output)
                    except (ValueError, UnicodeError):
                        value = json.loads(base64.b64decode(output, validate=True))
                    require(type(value) is dict and value.get('host') == lost.HOST and
                            type(value.get('uid')) is int and value['uid'] == 0 and
                            value.get('source_sha256') == self.intent['source_sha256'] and
                            value.get('operation_id') == self.intent['operation_id'], 'OUTPUT_IDENTITY')
                    receipt = value.get('receipt')
                    require(type(receipt) is dict and receipt.get('status') == 'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER'
                            and receipt.get('production_cutover') is False and receipt.get('services_installed') is True
                            and receipt.get('health') == {'portal': 200, 'contact': 200, 'customer-service': 200},
                            'OUTPUT_START_RECEIPT')
                    terminal = 'THREE_APPS_STARTED_NO_TRAFFIC_CUTOVER'
                result = self.original.terminal_result(terminal, invoke)
        except Exception:
            self._bound()
            return {'status': 'UNKNOWN_QUERY_ONLY_NO_REPLAY', 'invoke_id': invoke,
                    'operation_id': self.intent['operation_id']}
        self._bound()
        require(self._read('cloud-start.intent.json') == self.intent and
                self._read('cloud-start.invocation.json') == record, 'QUERY_RECORD_DRIFT')
        if result['status'] == 'PENDING_QUERY_ONLY':
            return result
        result = self.original.validate_saved_result(result, invoke)
        self._persist(result)
        return result


if __name__ == '__main__':
    raise SystemExit('ORIGINAL_ADMITTED_INPUTS_REQUIRED_NO_PRODUCTION_ENTRY')
