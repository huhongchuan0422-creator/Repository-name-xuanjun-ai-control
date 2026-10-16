"""Local-only D6 tests: actual production AST, synthetic census boundaries.

No production module import, /proc access, database access, host invocation,
claim, or external operation is performed. Compatible with Python 3.6.
"""
import ast
import collections
import copy
import hashlib
import os
import tarfile
import types
import unittest


CANDIDATE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECOVERY = os.path.dirname(CANDIDATE)
ARCHIVE = os.path.join(RECOVERY, 'b-resource-aggregate-fix-candidate',
                       'artifact', 'epoch7-kit-resourcebind.tar.gz')
ROOT = 'epoch7-recovery-candidate-r7-resourcebind/helpers/'
SOURCE_PATH = os.path.join(CANDIDATE, 'kit-overlay', 'helpers',
                           'epoch7_host_observer.py')
BASELINE_SHA256 = 'ec0d0618251469a5e0df241097c14b2aa608a6152ad6ea24ee1bed3ee1466cee'
ORIGINAL_LINE = "        after=self._pids();need(before==after and self._database_paths()==(db_files,db_before),'CENSUS_PROCESS_OR_DATABASE_RACE')\n"
SUFFIX_MARKER = '        # Reobserve every unit/cgroup after the global /proc scan.\n'
RACE_CODE = 'EPOCH7_HOST_CENSUS_PROCESS_OR_DATABASE_RACE'
ATTR = 'epoch7_census_race'


def archived(name):
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        return archive.extractfile(ROOT + name).read()


BASELINE_BYTES = archived('epoch7_host_observer.py')
with open(SOURCE_PATH, 'rb') as source_file:
    SOURCE_BYTES = source_file.read()
BASELINE = BASELINE_BYTES.decode('utf-8')
SOURCE = SOURCE_BYTES.decode('utf-8')


def find_method(source):
    tree = ast.parse(source)
    census = next(node for node in tree.body
                  if isinstance(node, ast.ClassDef) and node.name == 'LinuxProcessCensus')
    return next(node for node in census.body
                if isinstance(node, ast.FunctionDef) and node.name == 'processes')


def isolated_function(node, namespace):
    # An empty parsed module has the interpreter's correct AST fields on both
    # Python 3.6 and current Python. Only the selected function is executable.
    module = ast.parse('')
    module.body = [copy.deepcopy(node)]
    ast.fix_missing_locations(module)
    exec(compile(module, '<actual-production-ast>', 'exec'), namespace)
    return namespace[node.name]


need_node = next(node for node in ast.parse(archived('epoch7_host_phases.py')).body
                 if isinstance(node, ast.FunctionDef) and node.name == 'need')
PRODUCTION_NEED = isolated_function(need_node, {})
controls = ast.parse(archived('epoch7_live_controls.py'))
MAX_FD_ROWS = next(ast.literal_eval(node.value) for node in controls.body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'MAX_FD_ROWS'
                           for target in node.targets))


def production_processes(source):
    return isolated_function(find_method(source), {
        'copy': copy, 'need': PRODUCTION_NEED, 'MAX_FD_ROWS': MAX_FD_ROWS,
        'os': types.SimpleNamespace(getpid=lambda: 4242),
    })


BASELINE_PROCESSES = production_processes(BASELINE)
PROCESSES = production_processes(SOURCE)


class SyntheticCensus(object):
    def __init__(self):
        self.events = []
        self.calls = collections.Counter()
        self.failures = {}
        self.process_meta = {}
        self.pids = [[10, 20], [10, 20]]
        self.units = [{'private-unit.service': {'cgroups': {'/private/group': [10]}}}]
        self.units.append(copy.deepcopy(self.units[0]))
        files = {'/private/database.db': {'dev': 7, 'ino': 91}}
        identities = {(7, 91): ('/private/database.db', '/private/database.db')}
        self.databases = [(files, identities), copy.deepcopy((files, identities))]
        self.identity_changes = set()
        self.ancestry_changes = set()
        self.fd_totals = {10: 1, 20: 1}

    def hit(self, name, detail=None):
        self.calls[name] += 1
        self.events.append((name, detail))
        failure = self.failures.get((name, self.calls[name]))
        if failure is not None:
            raise failure
        return self.calls[name]

    def _start(self, context, phase):
        self.hit('_start', (context, phase))

    def verify_systemd_controller_mount(self):
        self.hit('verify_systemd_controller_mount')

    def _manager(self):
        self.hit('_manager')
        return {'pid': 1, 'pin': 'synthetic-manager'}

    def _all_units(self):
        index = self.hit('_all_units')
        return copy.deepcopy(self.units[index - 1])

    def _pids(self):
        index = self.hit('_pids')
        return copy.deepcopy(self.pids[index - 1])

    def _database_paths(self):
        index = self.hit('_database_paths')
        return copy.deepcopy(self.databases[index - 1])

    def _identity(self, pid, membership):
        self.hit('_identity', (pid, membership))
        count = sum(1 for name, detail in self.events
                    if name == '_identity' and detail[0] == pid)
        if pid == 10:
            self.process_meta[pid] = {'ancestor': 100 if count == 2 and
                                     pid in self.ancestry_changes else 1}
        return {'pid': pid, 'unit': membership,
                'starttime': 999 if count == 2 and pid in self.identity_changes else 123,
                'argv_sha256': 'synthetic-argv-hash'}

    def _fds(self, pid, identities):
        self.hit('_fds', (pid, copy.deepcopy(identities)))
        return [{'pid': pid, 'fd': 3, 'path': '/private/database.db'}], self.fd_totals[pid]

    def _check(self):
        self.hit('_check')


def run(census, method=PROCESSES):
    return method(census, {'context': 'synthetic'}, 'synthetic-phase', 'synthetic-boundary')


class RejectDiagnosticsError(Exception):
    def __setattr__(self, name, value):
        if name == ATTR:
            raise RuntimeError('diagnostic attribute rejected')
        super(RejectDiagnosticsError, self).__setattr__(name, value)


class CensusRaceClassificationTests(unittest.TestCase):
    def assert_complete_scan_counts(self, census):
        self.assertEqual(census.calls['_pids'], 2)
        self.assertEqual(census.calls['_database_paths'], 2)
        self.assertEqual(census.calls['_identity'], 4)
        self.assertEqual(census.calls['_fds'], 2)
        self.assertEqual([detail for name, detail in census.events if name == '_identity'],
                         [(10, 'private-unit.service'), (10, 'private-unit.service'),
                          (20, None), (20, None)])
        names = [name for name, unused in census.events]
        second_pids = len(names) - 1 - names[::-1].index('_pids')
        second_db = len(names) - 1 - names[::-1].index('_database_paths')
        self.assertEqual(second_db, second_pids + 1)

    def assert_race(self, census, classification, pid_list, db_map):
        with self.assertRaises(ValueError) as raised:
            run(census)
        self.assertEqual(raised.exception.args, (RACE_CODE,))
        self.assertEqual(getattr(raised.exception, ATTR), {
            'classification': classification, 'pid_list': pid_list, 'db_map': db_map})
        self.assert_complete_scan_counts(census)
        self.assertEqual(census.calls['_all_units'], 1)
        self.assertEqual(census.calls['_manager'], 1)
        self.assertFalse(hasattr(census, 'scoped_meta'))
        # All diagnostics are fixed enums. No PID, path, argv, or environment.
        values = set(getattr(raised.exception, ATTR).values())
        self.assertLessEqual(values, {'PID_LIST_CHANGED', 'DB_MAP_CHANGED',
                                    'BOTH_CHANGED', 'CHANGED', 'UNCHANGED'})

    def test_baseline_pin_and_only_target_line_changed(self):
        self.assertEqual(hashlib.sha256(BASELINE_BYTES).hexdigest(), BASELINE_SHA256)
        self.assertEqual(BASELINE.count(ORIGINAL_LINE), 1)
        def method_text(source):
            tree = ast.parse(source)
            cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                       and node.name == 'LinuxProcessCensus')
            index = next(i for i,node in enumerate(cls.body)
                         if isinstance(node, ast.FunctionDef) and node.name == 'processes')
            start = cls.body[index].lineno - 1
            end = cls.body[index+1].lineno - 1 if index+1 < len(cls.body) else None
            return ''.join(source.splitlines(True)[start:end]).rstrip()
        original, current = method_text(BASELINE), method_text(SOURCE)
        prefix, suffix = original.split(ORIGINAL_LINE)
        self.assertTrue(current.startswith(prefix))
        self.assertTrue(current.endswith(suffix))
        self.assertEqual(current.count(SUFFIX_MARKER), 1)
        self.assertEqual(current.split(SUFFIX_MARKER, 1)[1],
                         original.split(SUFFIX_MARKER, 1)[1])

    def test_static_boundary_call_counts_are_unchanged(self):
        def counts(source):
            return collections.Counter(node.func.attr for node in ast.walk(find_method(source))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'self')
        self.assertEqual(counts(SOURCE), counts(BASELINE))
        self.assertEqual(counts(SOURCE)['_pids'], 2)
        self.assertEqual(counts(SOURCE)['_database_paths'], 2)

    def test_success_matches_baseline_return_shape_values_and_calls(self):
        candidate, baseline = SyntheticCensus(), SyntheticCensus()
        result = run(candidate)
        self.assertEqual(result, run(baseline, BASELINE_PROCESSES))
        self.assertEqual(set(result), {'manager_before', 'manager_after', 'units',
            'pids_before', 'pids_after', 'processes', 'database_fds',
            'database_files', 'observer_pid'})
        self.assertEqual(candidate.events, baseline.events)
        self.assertEqual(candidate.scoped_meta, baseline.scoped_meta)
        self.assert_complete_scan_counts(candidate)
        self.assertEqual(candidate.calls['_all_units'], 2)
        self.assertEqual(candidate.calls['_manager'], 2)
        self.assertEqual(candidate.calls['verify_systemd_controller_mount'], 2)
        self.assertEqual(candidate.calls['_check'], 1)

    def test_pid_list_changed_still_observes_second_db_map(self):
        census = SyntheticCensus()
        census.pids[1].append(30)
        self.assert_race(census, 'PID_LIST_CHANGED', 'CHANGED', 'UNCHANGED')

    def test_db_files_changed(self):
        census = SyntheticCensus()
        census.databases[1][0]['/private/database.db']['ino'] = 92
        self.assert_race(census, 'DB_MAP_CHANGED', 'UNCHANGED', 'CHANGED')

    def test_db_identity_map_changed_independently(self):
        census = SyntheticCensus()
        census.databases[1][1][(7, 91)] = ('/private/other.db', '/private/other.db')
        self.assert_race(census, 'DB_MAP_CHANGED', 'UNCHANGED', 'CHANGED')

    def test_both_changed(self):
        census = SyntheticCensus()
        census.pids[1].remove(20)
        census.databases[1][0]['/private/database.db']['ino'] = 92
        self.assert_race(census, 'BOTH_CHANGED', 'CHANGED', 'CHANGED')

    def test_empty_census_preserves_success_and_exact_scan_counts(self):
        census = SyntheticCensus()
        census.pids = [[], []]
        census.units = [{}, {}]
        result = run(census)
        self.assertEqual(result['processes'], {})
        self.assertEqual(result['database_fds'], [])
        self.assertEqual(census.calls['_pids'], 2)
        self.assertEqual(census.calls['_database_paths'], 2)
        self.assertEqual(census.calls['_identity'], 0)

    def test_second_db_failure_keeps_primary_identity_args_traceback_and_unknown(self):
        for pid_changed in (False, True):
            for error in (PermissionError(13, 'denied', '/private/database.db'),
                          ValueError('EPOCH7_HOST_CENSUS_DATABASE_IDENTITY_CHANGED'),
                          FileNotFoundError(2, 'missing', '/private/database.db')):
                with self.subTest(pid_changed=pid_changed, error=type(error).__name__):
                    census = SyntheticCensus()
                    original_args = error.args
                    if pid_changed:
                        census.pids[1].append(30)
                    census.failures[('_database_paths', 2)] = error
                    try:
                        run(census)
                    except Exception as caught:
                        self.assertIs(caught, error)
                        frames = []
                        trace = caught.__traceback__
                        while trace is not None:
                            frames.append(trace.tb_frame.f_code.co_name)
                            trace = trace.tb_next
                    else:
                        self.fail('second DB observation did not fail closed')
                    self.assertEqual(frames[-4:], ['run', 'processes', '_database_paths', 'hit'])
                    self.assertEqual(frames.count('processes'), 1)
                    self.assertEqual(error.args, original_args)
                    self.assertIsNone(error.__cause__)
                    self.assertIsNone(error.__context__)
                    self.assertEqual(getattr(error, ATTR), {
                        'classification': 'UNKNOWN',
                        'pid_list': 'CHANGED' if pid_changed else 'UNCHANGED',
                        'db_map': 'UNKNOWN'})
                    self.assert_complete_scan_counts(census)
                    self.assertEqual(census.calls['_all_units'], 1)

    def test_rejected_optional_diagnostic_attribute_cannot_replace_primary(self):
        census = SyntheticCensus()
        error = RejectDiagnosticsError('primary DB observation failure')
        census.pids[1].append(30)
        census.failures[('_database_paths', 2)] = error
        with self.assertRaises(RejectDiagnosticsError) as raised:
            run(census)
        self.assertIs(raised.exception, error)
        self.assertEqual(error.args, ('primary DB observation failure',))
        self.assertFalse(hasattr(error, ATTR))
        self.assertIsNone(error.__context__)
        self.assert_complete_scan_counts(census)

    def test_all_existing_predicates_remain_fail_closed(self):
        def duplicate_membership(census):
            census.units[0]['other.service'] = {'cgroups': {'/other': [10]}}

        def fd_limit(census):
            census.fd_totals = {10: MAX_FD_ROWS // 2 + 1, 20: MAX_FD_ROWS // 2 + 1}

        def ancestry_race(census):
            census.ancestry_changes.add(10)

        def identity_race(census):
            census.identity_changes.add(20)

        def membership_race(census):
            census.units[1] = {}

        cases = [
            (duplicate_membership, 'CENSUS_MULTIPLE_CGROUP_UNITS'),
            (fd_limit, 'CENSUS_FD_TOTAL_BOUND'),
            (ancestry_race, 'CENSUS_ANCESTRY_RACE'),
            (identity_race, 'CENSUS_PROCESS_IDENTITY_RACE'),
            (membership_race, 'CENSUS_MEMBERSHIP_AFTER_SCAN_CHANGED'),
        ]
        for configure, reason in cases:
            with self.subTest(reason=reason):
                candidate, baseline = SyntheticCensus(), SyntheticCensus()
                configure(candidate)
                configure(baseline)
                errors = []
                for census, method in ((candidate, PROCESSES), (baseline, BASELINE_PROCESSES)):
                    with self.assertRaises(ValueError) as raised:
                        run(census, method)
                    errors.append(raised.exception)
                self.assertEqual(errors[0].args, ('EPOCH7_HOST_' + reason,))
                self.assertEqual(errors[0].args, errors[1].args)
                self.assertEqual(candidate.events, baseline.events)
                self.assertFalse(hasattr(errors[0], ATTR))

    def test_boundary_failures_and_all_checks_keep_original_exception(self):
        boundaries = [('_start', 1), ('verify_systemd_controller_mount', 1),
            ('_manager', 1), ('_all_units', 1), ('_pids', 1),
            ('_database_paths', 1), ('_identity', 1), ('_fds', 1),
            ('_pids', 2), ('_all_units', 2), ('_manager', 2),
            ('verify_systemd_controller_mount', 2), ('_check', 1)]
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                error = RuntimeError('original boundary failure')
                candidate, baseline = SyntheticCensus(), SyntheticCensus()
                candidate.failures[boundary] = error
                baseline.failures[boundary] = error
                for census, method in ((candidate, PROCESSES), (baseline, BASELINE_PROCESSES)):
                    with self.assertRaises(RuntimeError) as raised:
                        run(census, method)
                    self.assertIs(raised.exception, error)
                self.assertEqual(candidate.events, baseline.events)
                self.assertFalse(hasattr(error, ATTR))


if __name__ == '__main__':
    unittest.main(verbosity=2)
