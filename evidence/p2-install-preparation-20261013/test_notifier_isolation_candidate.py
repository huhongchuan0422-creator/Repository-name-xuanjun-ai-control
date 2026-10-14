import json
import os
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notifier_isolation_candidate as mod


class Fixture(object):
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail
        self.checks = 0

    def preflight(self):
        self.calls.append('preflight')
        if self.fail == 'preflight':
            raise ValueError('DRIFT')
        return {'original': 'states'}

    def begin(self, before, acceptance):
        self.calls.append('durable_backups')

    def recheck(self):
        self.checks += 1
        self.calls.append('recheck')
        if self.fail == 'recheck' and self.checks == 1:
            raise ValueError('DRIFT')

    def record(self, state, **details):
        self.calls.append('journal:' + state)

    def stop(self, unit):
        self.calls.append('stop:' + unit)
        if self.fail == unit:
            raise RuntimeError('STOP_FAILED')

    def quiet(self, unit):
        self.calls.append('quiet:' + unit)
        if self.fail == 'residual' and unit == mod.TIMER:
            raise ValueError('RESIDUAL_PROCESS')

    def mask(self, unit):
        self.calls.append('mask:' + unit)

    def reload(self):
        self.calls.append('reload')

    def verify(self):
        self.calls.append('verify')
        if self.fail == 'verify':
            raise FileNotFoundError('PROCESS_RACE')
        return {'scoped': True}


class IsolationTests(unittest.TestCase):
    def effects(self, adapter):
        return [c for c in adapter.calls if c.startswith(('stop:', 'mask:')) or c == 'reload']

    def test_order_and_durable_intents(self):
        a = Fixture()
        self.assertEqual(mod.isolate(a, 'PR17:123'), {'scoped': True})
        self.assertEqual(self.effects(a), ['stop:' + mod.TIMER, 'stop:' + mod.SERVICE,
                                         'mask:' + mod.TIMER, 'mask:' + mod.SERVICE, 'reload'])
        self.assertLess(a.calls.index('durable_backups'), a.calls.index('stop:' + mod.TIMER))
        for unit in mod.UNITS:
            intent = 'TIMER_STOP_INTENT' if unit == mod.TIMER else 'SERVICE_STOP_INTENT'
            self.assertLess(a.calls.index('journal:' + intent), a.calls.index('stop:' + unit))
            self.assertLess(a.calls.index('journal:MASK_INTENT:' + unit), a.calls.index('mask:' + unit))

    def test_preflight_drift_zero_effects(self):
        a = Fixture('preflight')
        with self.assertRaises(ValueError):mod.isolate(a, 'PR17:123')
        self.assertEqual(self.effects(a), [])
        self.assertNotIn('durable_backups', a.calls)

    def test_pre_effect_drift_hold_without_stop(self):
        a = Fixture('recheck')
        with self.assertRaises(ValueError):mod.isolate(a, 'PR17:123')
        self.assertEqual(self.effects(a), [])
        self.assertEqual(a.calls[-1], 'journal:HOLD_NOTIFIER_ISOLATION')

    def test_timer_stop_failure_never_stops_service(self):
        a = Fixture(mod.TIMER)
        with self.assertRaises(RuntimeError):mod.isolate(a, 'PR17:123')
        self.assertEqual(self.effects(a), ['stop:' + mod.TIMER])
        self.assertEqual(a.calls[-1], 'journal:HOLD_NOTIFIER_ISOLATION')

    def test_residual_timer_blocks_service_stop_and_masks(self):
        a = Fixture('residual')
        with self.assertRaises(ValueError):mod.isolate(a, 'PR17:123')
        self.assertEqual(self.effects(a), ['stop:' + mod.TIMER])

    def test_service_stop_failure_no_masks(self):
        a = Fixture(mod.SERVICE)
        with self.assertRaises(RuntimeError):mod.isolate(a, 'PR17:123')
        self.assertEqual(self.effects(a), ['stop:' + mod.TIMER, 'stop:' + mod.SERVICE])

    def test_process_race_holds_without_restore_or_restart(self):
        a = Fixture('verify')
        with self.assertRaises(FileNotFoundError):mod.isolate(a, 'PR17:123')
        self.assertEqual(a.calls[-1], 'journal:HOLD_NOTIFIER_ISOLATION')
        self.assertFalse(any('restart' in c or 'restore' in c for c in a.calls))

    def test_out_of_scope_stop_has_zero_subprocess_effects(self):
        with mock.patch.object(mod.subprocess, 'run') as run:
            with self.assertRaises(ValueError):mod.FixedHost().stop('other.service')
            run.assert_not_called()

    @unittest.skipIf(os.geteuid() != 0, 'Root-owned scratch directory fixture; never elevate CI')
    def test_real_exclusive_backups_and_durable_receipt(self):
        with tempfile.TemporaryDirectory() as path:
            a = mod.FixedHost()
            a.payloads = {u: ('original:' + u).encode() for u in mod.UNITS}
            try:
                with mock.patch.object(mod, 'OLD', path):
                    a.begin({u: {'mode': 420, 'enabled': 'original'} for u in mod.UNITS}, 'PR17:123')
                    original = {}
                    for u in mod.UNITS:
                        with open(path + '/notifier/' + u + '.backup', 'rb') as f:
                            original[u] = f.read()
                    a.record('TIMER_STOP_INTENT')
                    a.record('HOLD_NOTIFIER_ISOLATION', failed_stage='TIMER_STOP_INTENT')
                    with open(path + '/notifier/notifier-isolation-receipt.json') as f:
                        receipt = json.load(f)
                    self.assertEqual(receipt['state'], 'HOLD_NOTIFIER_ISOLATION')
                    self.assertEqual(receipt['before'][mod.TIMER]['enabled'], 'original')
                    with self.assertRaises(FileExistsError):
                        mod.FixedHost().begin({}, 'PR17:123')
                    for u in mod.UNITS:
                        with open(path + '/notifier/' + u + '.backup', 'rb') as f:
                            self.assertEqual(f.read(), original[u])
            finally:a.close()

    def test_unknown_pending_journal_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as path:
            a = mod.FixedHost()
            a.directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            a.receipt = {'before': {}}
            try:
                with open(path + '/receipt.pending', 'wb') as f:f.write(b'unknown')
                with self.assertRaises(FileExistsError):a.record('TIMER_STOP_INTENT')
                with open(path + '/receipt.pending', 'rb') as f:self.assertEqual(f.read(), b'unknown')
                self.assertFalse(os.path.exists(path + '/notifier-isolation-receipt.json'))
            finally:a.close()

    def test_bounded_reader_rejects_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as path:
            p = path + '/original'
            with open(p, 'wb') as f:f.write(b'original')
            os.symlink(p, path + '/alias')
            a = mod.FixedHost()
            with self.assertRaises(ValueError):a.read(path + '/alias')
            os.link(p, path + '/hardlink')
            with self.assertRaises(ValueError):a.read(p)

    def test_real_verify_process_race_is_not_accepted(self):
        a = mod.FixedHost()
        a.database_files = {mod.DB: {'device': 1, 'inode': 2}}
        payload = b'unit'
        with mock.patch.object(a, 'recheck'), mock.patch.object(a, 'quiet',
                return_value={'LoadState': 'masked', 'UnitFileState': 'masked'}), \
                mock.patch.object(a, 'read', return_value=(payload, None)), \
                mock.patch.dict(mod.UNIT_HASHES, {u: mod.sha(payload) for u in mod.UNITS}), \
                mock.patch.object(mod.os, 'listdir', return_value=['999999999']), \
                mock.patch.object(mod.os, 'open', side_effect=FileNotFoundError('race')):
            with self.assertRaises(FileNotFoundError):a.verify()

    def test_real_cgroup_permission_error_is_not_empty(self):
        def denied(*args, **kwargs):
            kwargs['onerror'](PermissionError('denied'))
        with mock.patch.object(mod.os.path, 'isdir', return_value=True), \
                mock.patch.object(mod.os, 'lstat', return_value=type('Info', (), {'st_mode': 0o40755})()), \
                mock.patch.object(mod.os, 'walk', side_effect=denied):
            with self.assertRaises(PermissionError):mod.FixedHost().members(mod.SERVICE)

    def test_absent_exact_unit_cgroup_is_empty_with_controller_present(self):
        with mock.patch.object(mod.os.path, 'isdir', return_value=True), \
                mock.patch.object(mod.os, 'lstat', side_effect=FileNotFoundError('unit removed')), \
                mock.patch.object(mod.os, 'walk') as walk:
            self.assertEqual(mod.FixedHost().members(mod.SERVICE), [])
            walk.assert_not_called()

    def test_missing_controller_remains_hold(self):
        with mock.patch.object(mod.os.path, 'isdir', return_value=False):
            with self.assertRaises(ValueError):mod.FixedHost().members(mod.SERVICE)

    def test_unit_cgroup_stat_denied_remains_hold(self):
        with mock.patch.object(mod.os.path, 'isdir', return_value=True), \
                mock.patch.object(mod.os, 'lstat', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):mod.FixedHost().members(mod.SERVICE)

    def test_nested_cgroup_disappearing_during_scan_remains_hold(self):
        def vanished(*args, **kwargs):
            kwargs['onerror'](FileNotFoundError('nested race'))
        with mock.patch.object(mod.os.path, 'isdir', return_value=True), \
                mock.patch.object(mod.os, 'lstat', return_value=type('Info', (), {'st_mode': 0o40755})()), \
                mock.patch.object(mod.os, 'walk', side_effect=vanished):
            with self.assertRaises(FileNotFoundError):mod.FixedHost().members(mod.SERVICE)


if __name__ == '__main__':unittest.main()
