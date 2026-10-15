"""Synthetic writer-transition and injected proc regressions; no host census."""
import copy
import io
import pathlib
import sys
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'recovery-design-candidate')]
import epoch7_snapshot as c
import epoch7_delta as d
import snapshot_io as concrete
from test_snapshot import fixture, writer_fixture, native_pin_context, native_raws


def sample(count=567):
    value = writer_fixture()
    value['processes']['fd_count'] = count
    return value


def background():
    row = {'pid': 123, 'starttime': 456, 'uids': [1002] * 4,
        'gids': [1002] * 4, 'groups': [1002, 1007], 'comm': 'ssh',
        'executable': '/usr/bin/ssh', 'executable_sha256': 'a' * 64,
        'argv_sha256': 'b' * 64, 'unit': None, 'kernel_thread': False}
    return [{'before': copy.deepcopy(row), 'after': copy.deepcopy(row)}]


class WriterComparisonTests(unittest.TestCase):
    def test_count_only_increase_decrease_equal_and_boundaries(self):
        for first, last in ((567, 568), (568, 567), (567, 567), (0, 1000000), (1000000, 0)):
            with self.subTest(first=first, last=last):
                before, after = sample(first), sample(last)
                original = copy.deepcopy((before, after))
                record = c.validate_writer_transition(before, after)
                self.assertEqual((before, after), original)
                self.assertEqual(record['fd_count_before'], first)
                self.assertEqual(record['fd_count_after'], last)
                self.assertEqual(record['before_sha256'], d.digest(before))
                self.assertEqual(record['after_sha256'], d.digest(after))
                self.assertEqual(c.validate_writer_comparison(record, after), record)

    def test_projection_omits_exactly_one_key_without_mutating_inputs(self):
        before, after = sample(), sample(568)
        expected = copy.deepcopy(after); expected['processes'].pop('fd_count')
        record = c.validate_writer_transition(before, after)
        self.assertEqual(record['safety_sha256'], d.digest(expected))
        self.assertNotEqual(record['before_sha256'], record['after_sha256'])

    def test_process_identity_digest_change_rejected(self):
        before, after = sample(), sample(568)
        after['processes']['process_identity_sha256'] = 'a' * 64
        with self.assertRaisesRegex(ValueError, 'WRITER_OBSERVATION_CHANGED'):
            c.validate_writer_transition(before, after)

    def test_every_nontelemetry_fixture_leaf_remains_in_comparison(self):
        before = sample()
        def leaves(value, path=()):
            if type(value) is dict:
                for key, child in value.items():
                    for result in leaves(child, path + (key,)): yield result
            elif type(value) is list:
                for key, child in enumerate(value):
                    for result in leaves(child, path + (key,)): yield result
            else: yield path, value
        for path, value in leaves(before):
            if path == ('processes', 'fd_count'): continue
            after = copy.deepcopy(before); parent = after
            for key in path[:-1]: parent = parent[key]
            parent[path[-1]] = (not value if type(value) is bool else
                               value + 1 if type(value) is int else
                               value + 'x' if type(value) is str else 'changed')
            with self.subTest(path=path):
                with self.assertRaises((ValueError, TypeError)):
                    c.validate_writer_transition(before, after)

    def test_cgroup_entries_changed_or_nonempty_rejected(self):
        unit = 'xuanjun-ledger.service'
        for digest in (c.sha(b''), c.sha(b'123\n')):
            after = sample(568)
            after['units'][unit]['cgroup_entries']['/sys/fs/cgroup/systemd/system.slice/' + unit + '/cgroup.procs'] = digest
            with self.assertRaises(ValueError): c.validate_writer_transition(sample(), after)

    def test_timer_optional_raw_property_appearance_is_still_drift(self):
        before = sample(); after = copy.deepcopy(before)
        before['units']['xuanjun-p2-tls-renew.timer']['state'].pop('ControlGroup')
        with self.assertRaisesRegex(ValueError, 'WRITER_OBSERVATION_CHANGED'):
            c.validate_writer_transition(before, after)

    def test_raw_nested_unknown_field_not_silently_projected_away(self):
        for path in (('manager',), ('control_files',), ('units', 'xuanjun-ledger.service', 'state')):
            after = sample(568); row = after
            for key in path: row = row[key]
            row['unrecognized'] = 'observed change'
            with self.assertRaisesRegex(ValueError, 'WRITER_OBSERVATION_CHANGED'):
                c.validate_writer_transition(sample(), after)

    def test_changed_type_cannot_hide_behind_python_boolean_integer_equality(self):
        after = sample(); after['manager']['fixture'] = 1
        self.assertEqual(sample(), after)
        with self.assertRaisesRegex(ValueError, 'WRITER_OBSERVATION_CHANGED'):
            c.validate_writer_transition(sample(), after)

    def test_all_background_identity_fields_still_bound(self):
        before = sample(); before['processes']['background_processes'] = background()
        before['processes']['background_processes_sha256'] = d.digest(background())
        changes = {'pid': 124, 'starttime': 457, 'uids': [1003] * 4, 'gids': [1003] * 4,
            'groups': [1002], 'comm': 'other', 'executable': '/other',
            'executable_sha256': 'c' * 64, 'argv_sha256': 'd' * 64, 'unit': 'other', 'kernel_thread': True}
        for key, value in changes.items():
            after = copy.deepcopy(before)
            for side in ('before', 'after'): after['processes']['background_processes'][0][side][key] = value
            after['processes']['background_processes_sha256'] = d.digest(after['processes']['background_processes'])
            with self.subTest(key=key):
                with self.assertRaises(ValueError): c.validate_writer_transition(before, after)

    def test_background_digest_or_pair_race_rejected(self):
        for defect in ('digest', 'pair'):
            before = sample(); before['processes']['background_processes'] = background()
            before['processes']['background_processes_sha256'] = d.digest(background())
            after = copy.deepcopy(before)
            if defect == 'digest': after['processes']['background_processes_sha256'] = '0' * 64
            else:
                after['processes']['background_processes'][0]['after']['starttime'] += 1
                after['processes']['background_processes_sha256'] = d.digest(after['processes']['background_processes'])
            with self.assertRaises(ValueError): c.validate_writer_transition(before, after)

    def test_unknown_or_missing_top_and_process_keys_rejected(self):
        for parent, key in (((), 'extra'), (('processes',), 'extra')):
            for side in (0, 1):
                pair = [sample(), sample(568)]; row = pair[side]
                for item in parent: row = row[item]
                row[key] = 0
                with self.assertRaises(ValueError): c.validate_writer_transition(*pair)
        for key in sample()['processes']:
            after = sample(); after['processes'].pop(key)
            with self.assertRaises(ValueError): c.validate_writer_transition(sample(), after)

    def test_invalid_count_types_and_bounds_in_either_sample(self):
        for value in (-1, 1000001, True, False, None, '567', 567.0, [], {}):
            for side in (0, 1):
                pair = [sample(), sample()]; pair[side]['processes']['fd_count'] = value
                with self.subTest(value=value, side=side):
                    with self.assertRaises(ValueError): c.validate_writer_transition(*pair)

    def test_invalid_sample_before_cannot_be_hidden_by_after(self):
        before = sample(); before['units']['xuanjun-ledger.service']['state']['ActiveState'] = 'active'
        with self.assertRaisesRegex(ValueError, 'WRITER_NOT_STOPPED'):
            c.validate_writer_transition(before, sample())

    def test_comparison_missing_extra_and_type_keys_rejected(self):
        record = c.validate_writer_transition(sample(), sample(568))
        for key in record:
            broken = dict(record); broken.pop(key)
            with self.assertRaisesRegex(ValueError, 'WRITER_COMPARISON_KEYS'):
                c.validate_writer_comparison(broken, sample(568))
        broken = dict(record, extra=0)
        with self.assertRaises(ValueError): c.validate_writer_comparison(broken, sample(568))
        for value in (None, [], 'comparison'):
            with self.assertRaises(ValueError): c.validate_writer_comparison(value, sample(568))

    def test_every_comparison_field_tamper_rejected(self):
        record = c.validate_writer_transition(sample(), sample(568))
        for key, value in (('schema', True), ('schema', 2), ('comparison', 'IGNORE_PROCESSES'),
                ('before_sha256', '0' * 64), ('after_sha256', '0' * 64), ('safety_sha256', '0' * 64),
                ('fd_count_before', 566), ('fd_count_after', 569), ('fd_count_before', True),
                ('fd_count_after', 568.0), ('fd_count_before', -1), ('fd_count_after', 1000001)):
            broken = dict(record); broken[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError): c.validate_writer_comparison(broken, sample(568))

    def test_after_raw_evidence_tamper_rejected(self):
        record = c.validate_writer_transition(sample(), sample(568))
        after = sample(568); after['manager']['fixture'] = False
        with self.assertRaisesRegex(ValueError, 'WRITER_COMPARISON_BINDING'):
            c.validate_writer_comparison(record, after)


class CollectorComparisonTests(unittest.TestCase):
    def collect(self, counts=(567, 568), late_change=False):
        policy, backend = fixture(); held = []
        def writer(unused_policy, paths):
            self.assertEqual(paths, c.DATABASES)
            row = sample(counts[len(held)]); held.append(copy.deepcopy(row))
            return row
        backend.writers = writer
        if late_change:
            original = backend.read
            def changed(path, maximum=16777216):
                raw, row = original(path, maximum)
                if path == c.ACTIVE and len(held) == 2: row['ino'] += 1
                return raw, row
            backend.read = changed
        with native_pin_context(native_raws(backend)):
            snapshot, evidence = c.collect(policy, backend)
        return snapshot, evidence, backend, held

    def test_count_only_collect_finishes_tail_and_preserves_digests(self):
        snapshot, evidence, backend, held = self.collect()
        self.assertEqual(len(held), 2)
        record = evidence['writer_observation_comparison']
        self.assertEqual(c.validate_writer_comparison(record, evidence['writers']), record)
        self.assertEqual(record['before_sha256'], d.digest(held[0]))
        self.assertEqual(record['after_sha256'], d.digest(held[1]))
        self.assertEqual(evidence['writers'], held[1])
        self.assertEqual(snapshot['writer_exclusion']['evidence_sha256'], d.digest(held[1]))
        self.assertGreaterEqual(backend.calls[c.ACTIVE], 2)
        self.assertEqual(evidence['install_admission'], 'NOT_GRANTED')
        d.validate_snapshot(snapshot, d.digest(snapshot))

    def test_late_file_race_still_holds_after_count_only_comparison(self):
        with self.assertRaisesRegex(ValueError, 'RETAINED_FILE_RACE'):
            self.collect(late_change=True)

    def test_fresh_telemetry_cannot_contaminate_retained_identity(self):
        first, first_e, unused, unused_rows = self.collect((567, 568))
        last, last_e, unused, unused_rows = self.collect((699, 698))
        self.assertEqual(first_e['retained'], last_e['retained'])
        self.assertEqual(first['retained_resource_sha256'], last['retained_resource_sha256'])
        first['writer_exclusion'].pop('evidence_sha256')
        last['writer_exclusion'].pop('evidence_sha256')
        self.assertEqual(first, last)
        self.assertNotEqual(d.digest(first_e), d.digest(last_e))

    def test_comparison_is_transient_top_sibling_only(self):
        snapshot, evidence, unused, unused_rows = self.collect()
        self.assertEqual(set(evidence), {'schema', 'kind', 'snapshot_sha256', 'retained',
            'writers', 'writer_observation_comparison', 'install_admission', 'production_acceptance', 'target_mutations'})
        self.assertNotIn('writer_observation_comparison', evidence['retained'])
        self.assertEqual(snapshot['retained_resource_sha256'], d.digest(evidence['retained']))


def proc_stat(start=456):
    fields = ['S', '1', '0', '0', '0', '0', '0'] + ['0'] * 12 + [str(start)] + ['0'] * 10
    return ('123 (daemon) ' + ' '.join(fields) + '\n').encode('ascii')


class ConcreteCensusInvariantTests(unittest.TestCase):
    """Exercise the unchanged concrete census with only in-memory proc/FD IO."""
    def scan(self, defect=None, count=1):
        backend = object.__new__(concrete.LocalReadOnlyIO)
        reads = {}; listings = {}
        def opened(path, mode):
            self.assertEqual(mode, 'rb')
            name = path.rsplit('/', 1)[-1]; reads[name] = reads.get(name, 0) + 1
            if defect == 'unreadable': raise PermissionError('fixture')
            if name == 'stat': raw = proc_stat(457 if defect == 'pid_reuse' and reads[name] == 2 else 456)
            elif name == 'status':
                uid = 1003 if defect == 'writer_uid' else (1 if defect == 'uid_race' and reads[name] == 2 else 0)
                raw = ('Uid:\t' + ' '.join([str(uid)] * 4) + '\n').encode('ascii')
            elif name == 'comm': raw = b'Runner.Worker\n' if defect == 'runner' else b'daemon\n'
            else: raise AssertionError(path)
            return io.BytesIO(raw)
        def listing(path):
            listings[path] = listings.get(path, 0) + 1
            if path == '/proc':
                return ['123', '124'] if defect == 'pid_set_race' and listings[path] == 2 else ['123']
            self.assertEqual(path, '/proc/123/fd')
            if defect == 'fd_race' and listings[path] == 2: return []
            return [str(n) for n in range(count)]
        def fd_stat(path):
            self.assertTrue(path.startswith('/proc/123/fd/'))
            return types.SimpleNamespace(st_dev=7 if defect == 'database_fd' else 8, st_ino=91)
        with mock.patch('builtins.open', side_effect=opened), \
             mock.patch.object(concrete.os, 'listdir', side_effect=listing), \
             mock.patch.object(concrete.os, 'getpid', return_value=999), \
             mock.patch.object(concrete.os.path, 'lexists', side_effect=lambda path: path == c.DATABASES[0]), \
             mock.patch.object(concrete.os, 'lstat', return_value=types.SimpleNamespace(st_dev=7, st_ino=91)), \
             mock.patch.object(concrete.os, 'stat', side_effect=fd_stat):
            return backend._process_scan(c.DATABASES)

    def test_two_individually_stable_scans_allow_unrelated_descriptor_count_drift(self):
        before, after = sample(), sample()
        before['processes'] = self.scan(count=1)
        after['processes'] = self.scan(count=2)
        self.assertEqual(before['processes']['process_identity_sha256'], after['processes']['process_identity_sha256'])
        record = c.validate_writer_transition(before, after)
        self.assertEqual((record['fd_count_before'], record['fd_count_after']), (1, 2))

    def test_database_descriptor_holder_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'DATABASE_FD_HOLDER'): self.scan('database_fd')

    def test_pid_reuse_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'PID_REUSE'): self.scan('pid_reuse')

    def test_within_scan_fd_race_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'PROC_FD_OR_UID_RACE'): self.scan('fd_race')

    def test_within_scan_uid_race_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'PROC_FD_OR_UID_RACE'): self.scan('uid_race')

    def test_global_pid_set_race_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'PROCESS_SCAN_RACE'): self.scan('pid_set_race')

    def test_forbidden_writer_account_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'WRITER_ACCOUNT_PROCESS'): self.scan('writer_uid')

    def test_runner_process_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'WRITER_ACCOUNT_PROCESS'): self.scan('runner')

    def test_unreadable_process_is_not_count_telemetry(self):
        with self.assertRaises(PermissionError): self.scan('unreadable')


if __name__ == '__main__': unittest.main()
