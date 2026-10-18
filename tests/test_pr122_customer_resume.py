"""Offline V2 fault injection: sandbox files and mocked command execution only."""
import errno
import fcntl
import json
import os
import stat
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import pr122_customer_release as r
from scripts import pr122_customer_resume as resume
from scripts.pr122_customer_core import Denied, canonical, digest
from tests import test_pr122_customer_release as release_tests


class ResumeTests(unittest.TestCase):
    # Borrow the fixture, not its TestCase: inherited tests would be counted twice.
    inventory = release_tests.ReleaseTests.inventory
    patches = release_tests.ReleaseTests.patches

    def setUp(self):
        release_tests.ReleaseTests.setUp(self)
        # The V1 fixture uses this as a failure selector, shadowing TestCase.fail.
        # V2 uses command_failure instead so assertion diagnostics still work.
        del self.fail
        self.approval.update(max_executions=5, attempt_policy=resume.POLICY,
                             recovery_actions=sorted(resume.ACTIONS))
        self.command_failure = None
        uid, gid = os.getuid(), os.getgid()
        for adapter in (
            patch.object(resume, 'trusted', lambda info: info.st_uid == uid
                         and info.st_gid == gid and not info.st_mode & 0o022),
            # resume imports this function directly; the fixture's attempts alias
            # patch alone does not adapt V2 receipt reads to the sandbox owner.
            patch.object(resume, 'read_private',
                         lambda path: json.loads(Path(path).read_bytes())),
            patch.object(resume.time, 'sleep', return_value=None),
            patch.object(r.subprocess, 'run',
                         side_effect=AssertionError('External process forbidden')),
        ):
            adapter.start()
            self.addCleanup(adapter.stop)

    def fake_run(self, args):
        self.calls.append(args)
        if self.command_failure:
            error = self.command_failure(args)
            if error is not None:
                raise error
        if args[0].endswith('curl'):
            return b'fixture html'
        if args[:3] == ['/usr/bin/systemctl', 'show', r.UNITS[3]]:
            return (str(r.UNIT / r.UNITS[3]).encode() if 'FragmentPath' in args
                    else b'success' if 'Result' in args else b'')
        return b''

    def receipt(self):
        return json.loads((r.STATE / r.TXN / 'receipt.json').read_bytes())

    def ledger(self):
        return json.loads((r.STATE / (r.TXN + '.attempts.json')).read_bytes())

    def curls(self):
        return [args for args in self.calls if args[0] == '/usr/bin/curl']

    def mutations(self):
        return [args for args in self.calls if args[0] == '/usr/bin/systemctl'
                and args[1] in ('daemon-reload', 'start', 'reload', 'enable')]

    def assert_mutations_once(self):
        expected = [
            ['/usr/bin/systemctl', 'daemon-reload'],
            ['/usr/bin/systemctl', 'start', r.UNITS[0]],
            ['/usr/bin/systemctl', 'start', r.UNITS[3]],
            ['/usr/bin/systemctl', 'reload', 'nginx'],
            ['/usr/bin/systemctl', 'enable', '--now', r.UNITS[2], r.UNITS[4], r.UNITS[5]],
        ]
        self.assertEqual(self.mutations(), expected)

    def assert_ledger(self, states):
        data = self.ledger()
        self.assertEqual(data['binding']['approval_comment'], 4)
        self.assertEqual(data['binding']['approval_sha256'], digest(canonical(self.approval)))
        self.assertEqual([row['state'] for row in data['attempts']], states)
        previous = None
        for number, row in enumerate(data['attempts'], 1):
            self.assertEqual(row['number'], number)
            self.assertEqual(row['attempt_id'], r.TXN + '-%02d' % number)
            self.assertEqual(row['previous_sha256'], previous)
            previous = digest(canonical(row))
        return data

    def transient_curl(self, count=None, returncode=7):
        def fail(args):
            if args[0] == '/usr/bin/curl' and (count is None or len(self.curls()) <= count):
                return r.CommandFailure(args, returncode, b'fixture transient failure')
        self.command_failure = fail

    def interrupt_file_once(self, target, error_number=errno.EINTR):
        original = resume.Journal._write_bytes
        injected = []

        def write(journal, fd, raw):
            if not injected and target.exists() and os.fstat(fd).st_ino == target.stat().st_ino:
                original(journal, fd, raw[:4])
                injected.append(bytes(raw))
                raise OSError(error_number, 'fixture partial write')
            return original(journal, fd, raw)
        return patch.object(resume.Journal, '_write_bytes', write), injected

    def stopped_between_attempts(self):
        self.transient_curl()
        with self.patches(), patch.object(resume.time, 'sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                r.apply(self.source, 4)
        self.assertEqual(self.receipt()['state'], 'RECOVERABLE_FAILURE')
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE'])

    def test_happy_path_consumes_one_of_five_and_records_fixed_checkpoints(self):
        with self.patches():
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(result['attempt_number'], 1)
        self.assertEqual(result['failures'], [])
        self.assertEqual(result['repairs'], [])
        self.assertIsNone(result['intent'])
        self.assertEqual(set(result['checkpoints']), {'DAEMON_RELOAD', 'START_RUNTIME',
                         'START_PUBLISHER', 'NGINX_WRITE', 'NGINX_RELOAD', 'TRIGGERS_ENABLE'})
        self.assertNotIn('_backup_bytes', self.receipt())
        self.assertTrue(all(cp['status'] == 'COMPLETE' for cp in result['files'].values()))
        self.assertEqual(os.readlink(r.CURRENT), self.base['main_current'])
        self.assertEqual(r.HTTPS.read_bytes().count(r.INCLUDE), 1)
        self.assert_ledger([resume.SUCCESS])
        self.assert_mutations_once()

    def test_partial_eintr_repaired_only_in_same_owned_inode_then_success(self):
        target = r.CODE / 'deploy/pr122-customer-center/ui/index.html'
        fault, injected = self.interrupt_file_once(target)
        snapshots = []

        def pause(_seconds):
            receipt = self.receipt()
            cp = receipt['files'][str(target)]
            self.assertEqual(cp['status'], 'WRITING')
            self.assertEqual(target.read_bytes(), b'fixt')
            self.assertFalse(receipt['activation_started'])
            self.assertEqual(self.calls, [])
            boot = r.CODE / 'boot.py'
            snapshots.append((target.stat().st_ino, boot.stat().st_ino, boot.stat().st_mtime_ns))

        with self.patches(), fault, patch.object(resume.time, 'sleep', pause):
            result = r.apply(self.source, 4)
        self.assertEqual(len(injected), 1)
        self.assertEqual(result['attempt_number'], 2)
        self.assertEqual(target.read_bytes(), injected[0])
        boot = r.CODE / 'boot.py'
        self.assertEqual(snapshots, [(target.stat().st_ino, boot.stat().st_ino, boot.stat().st_mtime_ns)])
        self.assertEqual(result['failures'][0]['evidence']['errno'], errno.EINTR)
        repair = result['repairs'][0]
        self.assertEqual(repair['action'], 'REPAIR_INCOMPLETE_OWNED_FILE')
        self.assertEqual(repair['path'], str(target))
        self.assertEqual(repair['attempt'], 2)
        self.assertTrue(repair['validated'])
        self.assertEqual(repair['result_sha256'], digest(injected[0]))
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])
        self.assert_mutations_once()

    def test_curl_rc7_retries_readonly_without_rewriting_completed_files_or_effects(self):
        self.transient_curl(count=1)
        snapshots = []

        def pause(_seconds):
            snapshots.append({path: (Path(path).stat().st_ino, Path(path).stat().st_mtime_ns)
                              for path in self.receipt()['files']})

        original_approval = canonical(self.approval)
        with self.patches(), patch.object(resume.time, 'sleep', pause), \
                patch.object(r, 'gate', return_value=self.approval) as gate:
            result = r.apply(self.source, 4)
        self.assertEqual(canonical(self.approval), original_approval)
        self.assertTrue(all(call.args == (4, self.base) for call in gate.call_args_list))
        self.assertEqual(result['attempt_number'], 2)
        self.assertEqual(len(self.curls()), 2)
        self.assertEqual(result['failures'][0]['step'], 'HTTPS_SMOKE')
        self.assertEqual(result['failures'][0]['evidence']['returncode'], 7)
        self.assertEqual(snapshots[0], {path: (Path(path).stat().st_ino, Path(path).stat().st_mtime_ns)
                                      for path in result['files']})
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])
        self.assert_mutations_once()

    def test_fifth_transient_failure_exhausts_original_permit_and_seals(self):
        self.transient_curl()
        with self.patches():
            with self.assertRaises(resume.Stopped) as caught:
                r.apply(self.source, 4)
            report = caught.exception.report
            self.assertEqual(report['state'], 'ATTEMPTS_EXHAUSTED')
            self.assertEqual(report['attempts_used'], 5)
            self.assertEqual(report['max_attempts'], 5)
            self.assertEqual(len(report['failures']), 5)
            self.assertFalse(report['automatic_retry_allowed'])
            self.assertEqual(report['production_acceptance'], 'NOT_VERIFIED')
            before = list(self.calls)
            ledger_bytes = (r.STATE / (r.TXN + '.attempts.json')).read_bytes()
            with self.assertRaises(Denied):
                r.apply(self.source, 4)
            self.assertEqual(self.calls, before)
            self.assertEqual((r.STATE / (r.TXN + '.attempts.json')).read_bytes(), ledger_bytes)
        self.assertEqual(len(self.curls()), 5)
        self.assertEqual(self.receipt()['state'], 'ATTEMPTS_EXHAUSTED')
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE'] * 5)
        self.assert_mutations_once()

    def test_success_stops_immediately_and_cannot_be_replayed(self):
        self.transient_curl(count=2)
        with self.patches():
            result = r.apply(self.source, 4)
            self.assertEqual(result['attempt_number'], 3)
            before = list(self.calls)
            with self.assertRaises(Denied):
                r.apply(self.source, 4)
            self.assertEqual(self.calls, before)
        self.assertEqual(len(self.curls()), 3)
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE'] * 2 + [resume.SUCCESS])

    def test_restart_reconstructs_receipt_and_remaining_original_budget(self):
        self.stopped_between_attempts()
        self.command_failure = None
        with self.patches():
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(result['attempt_number'], 2)
        self.assertEqual(len(self.curls()), 2)
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])
        self.assert_mutations_once()

    def test_restart_after_partial_write_repairs_recorded_inode(self):
        target = r.CODE / 'boot.py'
        fault, injected = self.interrupt_file_once(target)
        with self.patches(), fault, patch.object(resume.time, 'sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                r.apply(self.source, 4)
        before_inode = target.stat().st_ino
        self.assertEqual(self.receipt()['state'], 'RECOVERABLE_FAILURE')
        with self.patches():
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(target.stat().st_ino, before_inode)
        self.assertEqual(target.read_bytes(), injected[0])
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])

    def test_changed_permit_or_comment_cannot_reset_restart_budget(self):
        self.stopped_between_attempts()
        before = list(self.calls)
        old = canonical(self.ledger())
        original = dict(self.approval)
        for key, value in [('max_executions', 4), ('expires_unix', self.approval['expires_unix'] + 1),
                           ('recovery_actions', ['RETRY_TRANSIENT_READONLY_CHECK'])]:
            with self.subTest(key=key):
                self.approval = dict(original, **{key: value})
                with self.patches(), self.assertRaises(Denied):
                    r.apply(self.source, 4)
        self.approval = original
        with self.patches(), self.assertRaises(Denied):
            r.apply(self.source, 99)
        self.assertEqual(self.calls, before)
        self.assertEqual(canonical(self.ledger()), old)

    def test_global_lock_held_across_retry_delay_and_every_attempt(self):
        self.transient_curl(count=1)
        checked = []

        def pause(_seconds):
            with r.LOCK.open('w') as competing:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(competing, fcntl.LOCK_EX | fcntl.LOCK_NB)
            checked.append(True)

        with self.patches(), patch.object(resume.time, 'sleep', pause):
            self.assertEqual(r.apply(self.source, 4)['state'], resume.SUCCESS)
        self.assertEqual(checked, [True])

    def test_competing_global_lock_prevents_any_attempt_or_file_creation(self):
        with r.LOCK.open('w') as competing, self.patches():
            fcntl.flock(competing, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                r.apply(self.source, 4)
        self.assertFalse(r.STATE.exists())
        self.assertFalse(r.CODE.exists())
        self.assertEqual(self.calls, [])

    def assert_mutation_failure_sealed(self, result_unknown):
        def fail(args):
            if args[:3] == ['/usr/bin/systemctl', 'start', r.UNITS[0]]:
                return r.CommandFailure(args, 7, b'fixture service failure', result_unknown=result_unknown)
        self.command_failure = fail
        with self.patches():
            with self.assertRaises(resume.Stopped) as caught:
                r.apply(self.source, 4)
            self.assertEqual(caught.exception.report['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
            before = list(self.calls)
            with self.assertRaises(Denied):
                r.apply(self.source, 4)
            self.assertEqual(self.calls, before)
        self.assertEqual(self.receipt()['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
        self.assertEqual(self.receipt()['failures'][-1]['code'], 'UNKNOWN_OR_UNSAFE_EFFECT')
        self.assert_ledger(['HOLD_UNKNOWN_OR_PARTIAL'])
        self.assertEqual(self.curls(), [])

    def test_unknown_mutating_service_result_holds_without_retry(self):
        self.assert_mutation_failure_sealed(result_unknown=True)

    def test_service_rc7_is_not_misclassified_as_curl_transient(self):
        self.assert_mutation_failure_sealed(result_unknown=False)

    def test_incomplete_file_inode_replacement_is_never_adopted_or_repaired(self):
        target = r.CODE / 'boot.py'
        fault, _injected = self.interrupt_file_once(target)
        replacement_bytes = b'foreign inode with matching apparent purpose'

        def replace_owned_inode(_seconds):
            replacement = self.b / 'replacement'
            replacement.write_bytes(replacement_bytes)
            replacement.chmod(0o600)
            os.replace(replacement, target)

        with self.patches(), fault, patch.object(resume.time, 'sleep', replace_owned_inode):
            with self.assertRaises(Denied):
                r.apply(self.source, 4)
        self.assertEqual(target.read_bytes(), replacement_bytes)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.receipt()['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
        before = len(self.ledger()['attempts'])
        with self.patches(), self.assertRaises(Denied):
            r.apply(self.source, 4)
        self.assertEqual(len(self.ledger()['attempts']), before)

    def test_old_v1_transaction_remains_sealed_without_new_ledger(self):
        r.STATE.mkdir()
        txn = r.STATE / r.TXN
        txn.mkdir()
        for old_state in ('HOLD_PARTIAL', 'ROLLED_BACK', resume.SUCCESS, 'INSTALLING'):
            (txn / 'receipt.json').write_bytes(canonical({'state': old_state, 'approval': {'max_executions': 1}}))
            with self.subTest(state=old_state), self.patches(), self.assertRaisesRegex(Denied, 'SEALED'):
                r.apply(self.source, 4)
        self.assertFalse((r.STATE / (r.TXN + '.attempts.json')).exists())
        self.assertFalse(r.CODE.exists())
        self.assertEqual(self.calls, [])

    def test_owned_file_fsync_failure_is_unsafe_and_never_repaired(self):
        self.approval['recovery_actions'].remove('RECONCILE_OWNED_CHECKPOINTS')
        target = r.CODE / 'boot.py'
        original = os.fsync
        faults = []

        def fsync(fd):
            if not faults and target.exists() and os.fstat(fd).st_ino == target.stat().st_ino:
                faults.append(True)
                raise OSError(errno.EIO, 'fixture owned file fsync failure')
            return original(fd)

        with self.patches(), patch.object(resume.os, 'fsync', fsync):
            with self.assertRaises(resume.Stopped) as caught:
                r.apply(self.source, 4)
        self.assertEqual(faults, [True])
        self.assertEqual(caught.exception.report['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
        self.assertEqual(self.receipt()['repairs'], [])
        self.assertEqual(self.calls, [])
        self.assert_ledger(['HOLD_UNKNOWN_OR_PARTIAL'])
        with self.patches(), self.assertRaises(Denied):
            r.apply(self.source, 4)

    def test_failed_recoverable_ledger_fsync_preserves_unknown_fence_on_restart(self):
        self.approval['recovery_actions'].remove('RECONCILE_OWNED_CHECKPOINTS')
        self.transient_curl()
        original_save, original_fsync = r.atomic_json, os.fsync
        faults = []

        def save(path, data):
            if (not faults and path.name == r.TXN + '.attempts.json'
                    and data['attempts'][-1]['state'] == 'RECOVERABLE_INSTALL_FAILURE'):
                def fail_once(fd):
                    if not faults and stat.S_ISREG(os.fstat(fd).st_mode):
                        faults.append(True)
                        raise OSError(errno.EIO, 'fixture ledger fsync failure')
                    return original_fsync(fd)
                with patch.object(r.os, 'fsync', fail_once):
                    return original_save(path, data)
            return original_save(path, data)

        with self.patches(), patch.object(r, 'atomic_json', save):
            with self.assertRaises((OSError, Denied)):
                r.apply(self.source, 4)
        self.assertEqual(faults, [True])
        self.assertEqual(self.ledger()['attempts'][0]['state'], 'STARTED_UNKNOWN')
        before = list(self.calls)
        with self.patches(), self.assertRaises(Denied):
            r.apply(self.source, 4)
        self.assertEqual(self.calls, before)
        self.assertEqual(len(self.ledger()['attempts']), 1)

    def test_readonly_retry_requires_that_exact_recovery_action(self):
        self.approval['recovery_actions'] = ['REPAIR_INCOMPLETE_OWNED_FILE']
        self.transient_curl()
        with self.patches(), self.assertRaises(resume.Stopped) as caught:
            r.apply(self.source, 4)
        self.assertEqual(caught.exception.report['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
        self.assertEqual(len(self.curls()), 1)
        self.assert_ledger(['HOLD_UNKNOWN_OR_PARTIAL'])

    def test_proven_readonly_hold_reconciles_only_under_same_explicit_permit(self):
        self.transient_curl(returncode=22)
        with self.patches(), self.assertRaises(resume.Stopped):
            r.apply(self.source, 4)
        held = self.receipt()
        self.assertEqual(held['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
        self.assertIsNone(held['intent'])
        self.assert_ledger(['HOLD_UNKNOWN_OR_PARTIAL'])
        self.command_failure = None
        with self.patches():
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(result['attempt_number'], 2)
        self.assertEqual(result['reconciliations'][0]['code'], 'RECONCILED_OWNED_CHECKPOINTS')
        self.assertEqual(result['failures'][0]['prior_failure']['code'], 'UNKNOWN_OR_UNSAFE_EFFECT')
        self.assertEqual(result['files'], held['files'])
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])
        self.assert_mutations_once()

    def test_proven_readonly_hold_without_reconciliation_permission_stays_sealed(self):
        self.approval['recovery_actions'].remove('RECONCILE_OWNED_CHECKPOINTS')
        self.transient_curl(returncode=22)
        with self.patches(), self.assertRaises(resume.Stopped):
            r.apply(self.source, 4)
        self.assertIsNone(self.receipt()['intent'])
        before = list(self.calls)
        self.command_failure = None
        with self.patches(), self.assertRaisesRegex(Denied, 'RECONCILIATION_NOT_PERMITTED'):
            r.apply(self.source, 4)
        self.assertEqual(self.calls, before)
        self.assert_ledger(['HOLD_UNKNOWN_OR_PARTIAL'])

    def test_success_on_fifth_actual_attempt_uses_no_sixth_attempt(self):
        self.transient_curl(count=4)
        with self.patches():
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(result['attempt_number'], 5)
        self.assertEqual(len(self.curls()), 5)
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE'] * 4 + [resume.SUCCESS])
        self.assert_mutations_once()

    def test_curl_timeout_rc28_uses_same_bounded_readonly_recovery(self):
        self.transient_curl(count=1, returncode=28)
        with self.patches():
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(result['failures'][0]['evidence']['returncode'], 28)
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])
        self.assert_mutations_once()

    def test_partial_enospc_repaired_only_after_capacity_check(self):
        target = r.CODE / 'boot.py'
        fault, injected = self.interrupt_file_once(target, errno.ENOSPC)
        with self.patches(), fault:
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(result['failures'][0]['evidence']['errno'], errno.ENOSPC)
        self.assertEqual(target.read_bytes(), injected[0])
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])

    def test_insufficient_repair_capacity_holds_without_truncating_owned_file(self):
        target = r.CODE / 'boot.py'
        fault, _injected = self.interrupt_file_once(target, errno.ENOSPC)
        no_capacity = type('NoCapacity', (), {'f_bavail': 0, 'f_frsize': 4096})()
        with self.patches(), fault, patch.object(resume.os, 'fstatvfs', return_value=no_capacity):
            with self.assertRaises(resume.Stopped):
                r.apply(self.source, 4)
        self.assertEqual(target.read_bytes(), b'# re')
        self.assertEqual(self.receipt()['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
        self.assertEqual(self.receipt()['repairs'], [])
        self.assertEqual(self.calls, [])

    def test_completed_file_bytes_drift_is_never_automatically_repaired(self):
        self.transient_curl(count=1)
        before = []
        target = r.CODE / 'boot.py'

        def drift(_seconds):
            before.extend(self.calls)
            target.write_bytes(b'X' * target.stat().st_size)

        with self.patches(), patch.object(resume.time, 'sleep', drift):
            with self.assertRaises(Denied):
                r.apply(self.source, 4)
        self.assertEqual(self.calls, before)
        self.assertEqual(target.read_bytes(), b'X' * len(b'# reviewed boot'))
        self.assertEqual(self.receipt()['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
        self.assertFalse(any(item['action'] == 'REPAIR_INCOMPLETE_OWNED_FILE'
                             for item in self.receipt()['repairs']))

    def test_foreign_code_file_is_never_adopted_on_retry(self):
        self.transient_curl(count=1)
        before = []
        foreign = r.CODE / 'foreign.py'

        def drift(_seconds):
            before.extend(self.calls)
            foreign.write_bytes(b'foreign fixture bytes')

        with self.patches(), patch.object(resume.time, 'sleep', drift):
            with self.assertRaises(Denied):
                r.apply(self.source, 4)
        self.assertEqual(self.calls, before)
        self.assertEqual(foreign.read_bytes(), b'foreign fixture bytes')
        self.assertNotIn(str(foreign), self.receipt()['files'])
        self.assertEqual(self.receipt()['state'], 'HOLD_UNKNOWN_OR_PARTIAL')

    def test_changed_reviewed_source_on_restart_cannot_consume_new_attempt(self):
        self.stopped_between_attempts()
        (self.source / 'boot.py').write_bytes(b'changed reviewed source')
        before = list(self.calls)
        with self.patches(), self.assertRaisesRegex(Denied, 'SOURCE_HASH'):
            r.apply(self.source, 4)
        self.assertEqual(self.calls, before)
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE'])

    def test_durable_fence_change_stops_before_next_service_mutation(self):
        tampered = []

        def change_fence(args):
            if args[0] == '/usr/bin/systemd-analyze':
                data = self.ledger()
                data['attempts'][-1]['lease']['fence'] = 999
                raw = canonical(data)
                (r.STATE / (r.TXN + '.attempts.json')).write_bytes(raw)
                tampered.append(raw)
        self.command_failure = change_fence
        with self.patches(), self.assertRaisesRegex(Denied, 'FENCE'):
            r.apply(self.source, 4)
        self.assertEqual(self.mutations(), [['/usr/bin/systemctl', 'daemon-reload']])
        self.assertEqual((r.STATE / (r.TXN + '.attempts.json')).read_bytes(), tampered[0])
        self.assertEqual(self.receipt()['state'], 'INSTALLING')
        self.assertEqual(self.curls(), [])

    def test_expired_lease_stops_before_next_service_mutation(self):
        clock = [self.approval['issued_unix'] + 1]

        def expire(args):
            if args[0] == '/usr/bin/systemd-analyze':
                clock[0] = self.approval['expires_unix']
        self.command_failure = expire
        with self.patches(), patch.object(resume.time, 'time', side_effect=lambda: clock[0]):
            with self.assertRaises(resume.Stopped):
                r.apply(self.source, 4)
        self.assertEqual(self.mutations(), [['/usr/bin/systemctl', 'daemon-reload']])
        self.assertEqual(self.receipt()['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
        self.assert_ledger(['HOLD_UNKNOWN_OR_PARTIAL'])
        self.assertEqual(self.curls(), [])

    def test_replaced_lock_inode_blocks_further_effects_and_receipt_rewrites(self):
        before = []

        def replace_lock(args):
            if args[0] == '/usr/bin/systemd-analyze':
                replacement = self.b / 'replacement.lock'
                replacement.touch(mode=0o600)
                os.replace(replacement, r.LOCK)
                before.append((r.STATE / r.TXN / 'receipt.json').read_bytes())
        self.command_failure = replace_lock
        with self.patches(), self.assertRaisesRegex(Denied, 'LOCK_REPLACED'):
            r.apply(self.source, 4)
        self.assertEqual(self.mutations(), [['/usr/bin/systemctl', 'daemon-reload']])
        self.assertEqual((r.STATE / r.TXN / 'receipt.json').read_bytes(), before[0])
        self.assertEqual(self.ledger()['attempts'][0]['state'], 'STARTED_UNKNOWN')
        self.assertEqual(self.curls(), [])

    def test_restart_reconciles_durable_mkdir_intent_only_when_target_is_absent(self):
        original = os.mkdir
        faults = []

        def mkdir(path, *args, **kwargs):
            if Path(path) == r.CODE and not faults:
                self.assertEqual(self.receipt()['intent'], {'kind': 'mkdir', 'path': str(r.CODE)})
                self.assertFalse(r.CODE.exists())
                faults.append(True)
                raise KeyboardInterrupt('fixture interruption before mkdir')
            return original(path, *args, **kwargs)

        with self.patches(), patch.object(resume.os, 'mkdir', mkdir):
            with self.assertRaises(resume.Stopped):
                r.apply(self.source, 4)
        self.assertEqual(faults, [True])
        self.assertFalse(r.CODE.exists())
        self.assertEqual(self.receipt()['intent'], {'kind': 'mkdir', 'path': str(r.CODE)})
        backup = r.STATE / r.TXN / 'https.before'
        before = (backup.stat().st_ino, backup.stat().st_mtime_ns, backup.read_bytes())
        self.assertEqual(self.calls, [])
        with self.patches():
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(result['attempt_number'], 2)
        self.assertEqual(before, (backup.stat().st_ino, backup.stat().st_mtime_ns, backup.read_bytes()))
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])
        self.assert_mutations_once()

    def test_restart_reconciles_durable_file_create_intent_only_when_target_is_absent(self):
        target = r.CODE / 'boot.py'
        original = os.open
        faults = []

        def open_file(path, flags, *args, **kwargs):
            if Path(path) == target and flags & os.O_CREAT and not faults:
                self.assertEqual(self.receipt()['intent'], {'kind': 'file_create', 'path': str(target)})
                self.assertFalse(target.exists())
                faults.append(True)
                raise KeyboardInterrupt('fixture interruption before exclusive create')
            return original(path, flags, *args, **kwargs)

        with self.patches(), patch.object(resume.os, 'open', open_file):
            with self.assertRaises(resume.Stopped):
                r.apply(self.source, 4)
        self.assertEqual(faults, [True])
        self.assertFalse(target.exists())
        self.assertNotIn(str(target), self.receipt()['files'])
        self.assertEqual(self.receipt()['intent'], {'kind': 'file_create', 'path': str(target)})
        self.assertEqual(self.calls, [])
        with self.patches():
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(target.read_bytes(), (self.source / 'boot.py').read_bytes())
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])
        self.assert_mutations_once()

    def test_crash_after_file_create_before_durable_ownership_never_adopts_present_target(self):
        target = r.CODE / 'boot.py'
        original = resume.Journal.save
        crashed = []

        def crash_save(journal):
            intent = journal.receipt['intent']
            if (crashed or intent == {'kind': 'file_write', 'path': str(target)}):
                # Persisted file_create intent exists, but ownership is still only
                # in RAM. Block the exception handler's writes too, as power loss
                # would, leaving the actual on-disk crash boundary unchanged.
                crashed.append(True)
                raise OSError(errno.EIO, 'fixture process lost before ownership checkpoint')
            return original(journal)

        with self.patches(), patch.object(resume.Journal, 'save', crash_save):
            with self.assertRaises(OSError):
                r.apply(self.source, 4)
        held = self.receipt()
        self.assertEqual(held['state'], 'INSTALLING')
        self.assertEqual(held['intent'], {'kind': 'file_create', 'path': str(target)})
        self.assertNotIn(str(target), held['files'])
        self.assertNotIn(str(target), held['owned'])
        before = (target.stat().st_ino, target.read_bytes())
        self.assertEqual(before[1], b'')
        self.assert_ledger(['STARTED_UNKNOWN'])
        with self.patches(), self.assertRaises(Denied):
            r.apply(self.source, 4)
        self.assertEqual((target.stat().st_ino, target.read_bytes()), before)
        self.assertEqual(self.receipt(), held)
        self.assert_ledger(['STARTED_UNKNOWN'])
        self.assertEqual(self.calls, [])

    def test_restart_repairs_durable_owned_writing_checkpoint_and_skips_completed_files(self):
        target = r.CODE / 'deploy/pr122-customer-center/ui/index.html'
        original = resume.Journal._write_bytes
        completed = []
        crashed = []

        def interrupt(journal, fd, raw):
            if not crashed and target.exists() and os.fstat(fd).st_ino == target.stat().st_ino:
                durable = self.receipt()
                self.assertEqual(durable['files'][str(target)]['status'], 'WRITING')
                self.assertEqual(durable['intent'], {'kind': 'file_write', 'path': str(target)})
                completed.append({path: (Path(path).stat().st_ino, Path(path).stat().st_mtime_ns,
                                        Path(path).read_bytes()) for path, cp in durable['files'].items()
                                  if cp['status'] == 'COMPLETE'})
                crashed.append(True)
                raise KeyboardInterrupt('fixture interruption after durable owned WRITING')
            return original(journal, fd, raw)

        with self.patches(), patch.object(resume.Journal, '_write_bytes', interrupt):
            with self.assertRaises(resume.Stopped):
                r.apply(self.source, 4)
        self.assertEqual(self.receipt()['state'], 'HOLD_UNKNOWN_OR_PARTIAL')
        self.assertEqual(target.read_bytes(), b'')
        self.assertEqual(self.calls, [])
        before_inode = target.stat().st_ino
        self.assertGreater(len(completed[0]), 1)
        with self.patches():
            result = r.apply(self.source, 4)
        self.assertEqual(result['state'], resume.SUCCESS)
        self.assertEqual(result['attempt_number'], 2)
        self.assertEqual(target.stat().st_ino, before_inode)
        self.assertEqual(target.read_bytes(), b'fixture html')
        self.assertEqual(completed[0], {path: (Path(path).stat().st_ino, Path(path).stat().st_mtime_ns,
                                             Path(path).read_bytes()) for path in completed[0]})
        self.assertTrue(any(item['action'] == 'REPAIR_INCOMPLETE_OWNED_FILE'
                            and item['path'] == str(target) and item['validated']
                            for item in result['repairs']))
        self.assert_ledger(['RECOVERABLE_INSTALL_FAILURE', resume.SUCCESS])
        self.assert_mutations_once()


if __name__ == '__main__':
    unittest.main()
