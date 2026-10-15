"""Offline candidate: bounded capture for an already-owned POSIX subprocess.

No launcher, CLI, shell, automatic retry, host wiring or production path exists.
Raw output is private, potentially credential-bearing data. Only public_summary
or failure_patch may enter the ordinary attempt journal or user-facing reports.
Python 3.6 compatible. A caller must start a fresh session before handing over
its subprocess; this module never accepts a command line or environment.
"""
import base64
import hashlib
import io
import json
import math
import os
import selectors
import signal
import stat
import subprocess
import time


MAX_STREAM_BYTES = 1048576
DEFAULT_STREAM_BYTES = 65536
MAX_TIMEOUT_SECONDS = 600.0
MAX_CLEANUP_SECONDS = 2.0
READ_CHUNK = 4096
PHASES = frozenset((
    'stage_exact_release', 'preserve_prior_receipts', 'rebind_prepared_epoch',
    'quiesce_exact_epoch', 'provision_from_retained_resources',
    'reopen_existing_database', 'activate_exact_epoch', 'activate_new_services',
    'post_install_checks'))
OPERATIONS = frozenset((
    'plugin_inventory', 'plugin_install', 'plugin_config_set', 'plugin_enable',
    'plugin_config_validate', 'plugin_runtime_inspect', 'plugin_uninstall',
    'plugin_config_unset', 'daemon_reload', 'nginx_config_test', 'service_start',
    'service_stop', 'service_is_active', 'boot_enable', 'boot_disable',
    'boot_is_enabled', 'database_reopen', 'stage_source_verify',
    'stage_smoke_check', 'acl_read', 'acl_apply', 'service_show', 'runtime_access_probe', 'local_https_probe', 'tls_inspect', 'retained_rpm_query'))
REASONS = frozenset(('SUCCESS', 'EXIT_NONZERO', 'OUTPUT_LIMIT', 'TIMEOUT',
                     'INTERRUPTED', 'CAPTURE_ERROR'))


class EvidenceError(ValueError):
    """Static messages only: exception text must not contain command/output."""


def require(value, label):
    if not value:
        raise EvidenceError(label)


def _number(value, maximum):
    return (type(value) in (int, float) and math.isfinite(value)
            and 0 < value <= maximum)


def _metadata(phase, operation, epoch, sequence):
    require(isinstance(phase, str) and isinstance(operation, str)
            and phase in PHASES and operation in OPERATIONS, 'EVIDENCE_FIXED_LABELS')
    require(type(epoch) is int and 1 <= epoch <= 999999999,
            'EVIDENCE_EPOCH_BOUND')
    require(type(sequence) is int and 1 <= sequence <= 9999,
            'EVIDENCE_SEQUENCE_BOUND')
    return {'schema': 1, 'failed_stage': phase + '_INTENT',
            'operation': operation, 'epoch': epoch, 'sequence': sequence}


def _error_class(error):
    # Never retain str(error), repr(error), its args, cmd, env or traceback.
    if isinstance(error, KeyboardInterrupt):
        return 'KeyboardInterrupt'
    if isinstance(error, SystemExit):
        return 'SystemExit'
    if isinstance(error, OSError):
        return 'OSError'
    return 'Exception'


def _owned_group_while_locked(process):
    """Prove a live OR unreaped exited child, without releasing its PID pin.

    The caller holds the Popen wait-owner lock and exclusively owns this child.
    An external raw waitpid/SIGCHLD reaper is outside that ownership contract.
    """
    if process.returncode is not None:
        return False
    if not all(hasattr(os, item) for item in ('waitid', 'P_PID', 'WEXITED',
                                            'WNOHANG', 'WNOWAIT')):
        return False
    try:
        exited = os.waitid(os.P_PID, process.pid,
                           os.WEXITED | os.WNOHANG | os.WNOWAIT)
        # None proves a still-running direct child; a matching exited result
        # proves an unreaped zombie. Both retain ownership of the numeric PID.
        if exited is not None and exited.si_pid != process.pid:
            return False
        return os.getpgid(process.pid) == process.pid and os.getsid(process.pid) == process.pid
    except OSError:
        return False


def _signal_owned_group(process):
    """Signal only a session still pinned by our live/unreaped direct child.

    Never poll first: poll could reap an exited leader while its descendants
    still own our pipes. WNOWAIT plus the exclusive wait lock keeps that leader's
    PID pinned through killpg. Already reaped/unproven IDs are never signalled.
    """
    if process.returncode is not None:
        return 'SKIPPED_UNPROVEN'
    lock = getattr(process, '_waitpid_lock', None)
    if lock is None or not lock.acquire(False):
        return 'SKIPPED_UNPROVEN'
    try:
        if not _owned_group_while_locked(process):
            return 'SKIPPED_UNPROVEN'
        # Exit after the proof still leaves an unreaped zombie. Its group ID
        # cannot be recycled before this signal under exclusive wait ownership.
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return 'SENT'
        except ProcessLookupError:
            return 'NOT_FOUND'
    finally:
        lock.release()


def capture_owned_process(process, phase, operation, epoch, sequence,
                          timeout_seconds, cleanup_seconds=2.0,
                          stream_limit=DEFAULT_STREAM_BYTES):
    """Return private evidence; never launch or retry a command.

    stdout/stderr must be binary unbuffered pipes, stdin must be DEVNULL or an
    already-closed input. The caller owns a fresh session/process group. Output
    limits stop the command rather than merely truncate after an unbounded read.
    Descendant containment stays UNKNOWN, even after a successful kill/reap.
    """
    result = _metadata(phase, operation, epoch, sequence)
    require(_number(timeout_seconds, MAX_TIMEOUT_SECONDS), 'EVIDENCE_TIMEOUT')
    require(_number(cleanup_seconds, MAX_CLEANUP_SECONDS), 'EVIDENCE_CLEANUP')
    require(type(stream_limit) is int and 1 <= stream_limit <= MAX_STREAM_BYTES,
            'EVIDENCE_OUTPUT_BOUND')
    require(isinstance(process, subprocess.Popen), 'EVIDENCE_PROCESS_OBJECT')
    require(type(process.pid) is int and process.pid > 1
            and process.pid != os.getpgrp(), 'EVIDENCE_OWNED_GROUP')
    # Already reaped pipe data may still be captured, but that numeric PID is
    # no longer signalling authority. Otherwise preserve live/zombie ownership
    # until either successful EOF or group cleanup; never poll at handoff.
    if process.returncode is None:
        lock = getattr(process, '_waitpid_lock', None)
        require(lock is not None and lock.acquire(False), 'EVIDENCE_OWNED_GROUP')
        try:
            require(_owned_group_while_locked(process), 'EVIDENCE_OWNED_GROUP')
        finally:
            lock.release()
    require(getattr(process, 'stdin', None) is None
            or process.stdin.closed, 'EVIDENCE_STDIN_NOT_CLOSED')
    require(process.stdout is not None and process.stderr is not None
            and process.stdout is not process.stderr, 'EVIDENCE_TWO_PIPES')
    require(all(isinstance(getattr(process, name), io.FileIO)
                for name in ('stdout', 'stderr')), 'EVIDENCE_UNBUFFERED_PIPES')
    started = time.monotonic()
    deadline = started + timeout_seconds
    selector = None
    retained = {'stdout': bytearray(), 'stderr': bytearray()}
    observed = {'stdout': 0, 'stderr': 0}
    eof = {'stdout': False, 'stderr': False}
    cleanup = {'budget_seconds': cleanup_seconds, 'group_signal': 'NOT_NEEDED',
               'direct_process': 'UNKNOWN', 'output': 'INCOMPLETE',
               'descendants': 'UNKNOWN'}
    reason = None
    failure_class = None
    interrupted = None

    def cleanup_error(key, error):
        nonlocal interrupted
        cleanup[key] = _error_class(error)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            interrupted = error

    def drain(until, enforce_limit):
        while selector is not None and selector.get_map():
            remaining = until - time.monotonic()
            if remaining <= 0:
                return 'TIMEOUT'
            events = selector.select(min(remaining, 0.05))
            if time.monotonic() >= until:
                return 'TIMEOUT'
            for key, unused in events:
                try:
                    chunk = os.read(key.fd, READ_CHUNK)
                except BlockingIOError:
                    continue
                name = key.data
                if not chunk:
                    eof[name] = True
                    selector.unregister(key.fileobj)
                    continue
                observed[name] += len(chunk)
                room = stream_limit - len(retained[name])
                if room > 0:
                    retained[name].extend(chunk[:room])
                if enforce_limit and observed[name] > stream_limit:
                    return 'OUTPUT_LIMIT'
            # The final EOF batch can empty the map: do not skip its deadline
            # check or reap our owned leader before an already-late cleanup.
            if time.monotonic() >= until:
                return 'TIMEOUT'
        while True:
            if time.monotonic() >= until:
                return 'TIMEOUT'
            exited = process.poll() is not None
            remaining = until - time.monotonic()
            if remaining <= 0:
                return 'TIMEOUT'
            if exited:
                return None
            time.sleep(min(remaining, 0.01))

    try:
        selector = selectors.DefaultSelector()
        for name in ('stdout', 'stderr'):
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        reason = drain(deadline, True)
        if reason is None:
            reason = 'SUCCESS' if process.returncode == 0 else 'EXIT_NONZERO'
    except BaseException as error:
        failure_class = _error_class(error)
        reason = ('INTERRUPTED' if isinstance(error, (KeyboardInterrupt, SystemExit))
                  else 'CAPTURE_ERROR')
        interrupted = error if reason == 'INTERRUPTED' else None
    finally:
        if reason in ('TIMEOUT', 'OUTPUT_LIMIT', 'INTERRUPTED', 'CAPTURE_ERROR'):
            # A single shared absolute budget covers kill, drain and reap.
            cleanup_deadline = time.monotonic() + cleanup_seconds
            try:
                cleanup['group_signal'] = _signal_owned_group(process)
            except BaseException as error:
                cleanup['group_signal'] = 'FAILED'
                cleanup_error('signal_error_class', error)
            try:
                drain(cleanup_deadline, False)
            except BaseException as error:
                cleanup_error('drain_error_class', error)
        else:
            cleanup_deadline = time.monotonic()
        # Close pipes before reap. An escaped descendant must not hold us at EOF.
        for name in ('stdout', 'stderr'):
            try:
                getattr(process, name).close()
            except BaseException as error:
                cleanup_error(name + '_close_error_class', error)
        try:
            if selector is not None:
                selector.close()
        except BaseException as error:
            cleanup_error('selector_close_error_class', error)
        try:
            remaining = cleanup_deadline - time.monotonic()
            if process.poll() is None and remaining > 0:
                process.wait(timeout=remaining)
            if process.poll() is not None:
                cleanup['direct_process'] = 'EXITED'
        except BaseException as error:
            cleanup_error('reap_error_class', error)
    cleanup['output'] = 'COMPLETE' if all(eof.values()) else 'INCOMPLETE'
    result.update(reason=reason, returncode=process.returncode,
                  timeout_seconds=timeout_seconds, stream_limit=stream_limit,
                  cleanup=cleanup, failure_class=failure_class)
    for name in ('stdout', 'stderr'):
        raw = bytes(retained[name])
        result[name] = {'prefix_b64': base64.b64encode(raw).decode('ascii'),
                        'prefix_sha256': hashlib.sha256(raw).hexdigest(),
                        'retained_bytes': len(raw), 'observed_bytes': observed[name],
                        'eof_observed': eof[name],
                        'truncated': observed[name] > len(raw)}
    # Interruption is a failure result, never converted to success. The caller
    # persists it, fences/stops, then propagates interruption as appropriate.
    result['interruption_requires_propagation'] = interrupted is not None
    return result


def _name(evidence):
    require(isinstance(evidence['failed_stage'], str)
            and evidence['failed_stage'].endswith('_INTENT'), 'EVIDENCE_STAGE')
    _metadata(evidence['failed_stage'][:-7], evidence['operation'],
              evidence['epoch'], evidence['sequence'])
    return 'command-e%d-n%04d.json' % (evidence['epoch'], evidence['sequence'])


def public_summary(evidence, reference=None):
    """Content-free allowlist. Never expose command, output or output hashes."""
    name = _name(evidence)
    require(evidence['schema'] == 1 and type(evidence['schema']) is int,
            'EVIDENCE_SCHEMA')
    require(evidence['reason'] in REASONS, 'EVIDENCE_REASON')
    require(evidence['returncode'] is None or (type(evidence['returncode']) is int
            and -2147483648 <= evidence['returncode'] <= 2147483647),
            'EVIDENCE_RETURN_CODE')
    result = {key: evidence[key] for key in (
        'schema', 'failed_stage', 'operation', 'epoch', 'sequence',
        'reason', 'returncode')}
    result['diagnostic_state'] = 'UNAVAILABLE'
    if reference is not None:
        require(set(reference) == {'name', 'sha256'} and reference['name'] == name
                and isinstance(reference['sha256'], str)
                and len(reference['sha256']) == 64
                and all(c in '0123456789abcdef' for c in reference['sha256']),
                'EVIDENCE_REFERENCE')
        result['diagnostic_state'] = 'PERSISTED_PRIVATE'
        result['diagnostic_reference'] = dict(reference)
    return result


def failure_patch(evidence, reference=None):
    require(evidence['reason'] != 'SUCCESS', 'EVIDENCE_FAILURE_REQUIRED')
    summary = public_summary(evidence, reference)
    return {'stage': 'HOLD', 'failed_stage': summary['failed_stage'],
            'failed_operation': summary['operation'],
            'error_type': 'BoundedCommandFailure', 'command_failure': summary}


def publish_protected(directory, evidence, owner_uid=0, owner_gid=0):
    """No-overwrite private evidence, fsynced before returning its reference.

    Production must retain the default root UID/GID and a transaction-owned
    0700 directory. Non-root identities are supported only for offline tests.
    A failed/uncertain write remains for reconciliation; never delete or retry.
    """
    name = _name(evidence)
    require(os.path.isabs(directory) and os.path.realpath(directory) == directory,
            'EVIDENCE_DIRECTORY_ALIAS')
    require(os.geteuid() == owner_uid, 'EVIDENCE_WRITER_AUTHORITY')
    raw = (json.dumps(evidence, sort_keys=True, separators=(',', ':'),
                      allow_nan=False) + '\n').encode('utf-8')
    require(len(raw) <= 3 * MAX_STREAM_BYTES, 'EVIDENCE_FILE_BOUND')
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        info = os.fstat(parent)
        require(stat.S_ISDIR(info.st_mode)
                and (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) ==
                (owner_uid, owner_gid, 0o700), 'EVIDENCE_DIRECTORY_AUTHORITY')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        os.fchmod(fd, 0o600)
        item = os.fstat(fd)
        require(stat.S_ISREG(item.st_mode) and item.st_nlink == 1
                and (item.st_uid, item.st_gid, stat.S_IMODE(item.st_mode)) ==
                (owner_uid, owner_gid, 0o600), 'EVIDENCE_FILE_AUTHORITY')
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            require(count > 0, 'EVIDENCE_SHORT_WRITE')
            offset += count
        os.fsync(fd)
        os.fsync(parent)
        current = os.stat(directory, follow_symlinks=False)
        require((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino),
                'EVIDENCE_DIRECTORY_CHANGED')
        return {'name': name, 'sha256': hashlib.sha256(raw).hexdigest()}
    except Exception:
        # Do not include the original OSError path or message in outer journals.
        raise EvidenceError('EVIDENCE_PERSISTENCE_UNCONFIRMED') from None
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)
