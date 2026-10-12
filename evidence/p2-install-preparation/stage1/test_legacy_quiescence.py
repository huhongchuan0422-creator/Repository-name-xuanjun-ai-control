import subprocess
import unittest
import os
import tempfile
from legacy_quiescence import ALLOWED_UNITS, measure_quiescence, cgroup_empty


class QuiescenceTests(unittest.TestCase):
    def setUp(self):
        self.bindings = {u: {'fragment_path': '/etc/systemd/system/' + u,
                            'sha256': 'a' * 64, 'cgroup': '/system.slice/' + u}
                         for u in ALLOWED_UNITS}
        self.overrides = {}
        self.empty = True

    def run_unit(self, argv, **kwargs):
        u = argv[2]
        d = {'Id': u, 'LoadState': 'loaded', 'ActiveState': 'inactive',
             'SubState': 'dead', 'MainPID': '0', 'ControlGroup': '',
             'UnitFileState': 'masked', 'FragmentPath': '/etc/systemd/system/' + u}
        d.update(self.overrides)
        return subprocess.CompletedProcess(argv, 0, ('\n'.join(k+'='+v for k,v in d.items())).encode())

    def measure(self):
        return measure_quiescence(self.bindings, '/sys/fs/cgroup/systemd',
                                  self.run_unit, lambda path: 'a'*64,
                                  lambda root, group: self.empty)

    def test_only_measured_stopped_masked_empty_units_produce_proof(self):
        self.assertTrue(all(self.measure()['proof'].values()))

    def test_active_main_pid_or_enabled_unit_cannot_migrate(self):
        for override in ({'ActiveState':'active'}, {'MainPID':'42'},
                         {'UnitFileState':'enabled'}, {'SubState':'exited'}):
            self.overrides = override
            with self.assertRaises(ValueError): self.measure()

    def test_descendant_process_blocks_proof(self):
        self.empty = False
        with self.assertRaisesRegex(ValueError, 'CGROUP_NOT_EMPTY'): self.measure()

    def test_missing_parent_and_changed_identity_block_proof(self):
        del self.bindings['xuanjun-uk-openclaw.service']
        with self.assertRaisesRegex(ValueError, 'EXACT_LEGACY'): self.measure()

    def test_substituted_fragment_or_cgroup_blocks_proof(self):
        for override in ({'FragmentPath':'/tmp/other.service'}, {'ControlGroup':'/other'}):
            self.overrides = override
            with self.assertRaises(ValueError): self.measure()

    def test_real_descendant_membership_and_missing_hierarchy(self):
        with tempfile.TemporaryDirectory() as root:
            root = os.path.realpath(root)
            group = '/system.slice/xuanjun-uk-stage1-minimal.service'
            path = root + group
            os.makedirs(path + '/child')
            for directory in (path, path + '/child'):
                with open(directory + '/cgroup.procs', 'w') as f: f.write('')
            self.assertTrue(cgroup_empty(root, group))
            with open(path + '/child/cgroup.procs', 'w') as f: f.write('42\n')
            self.assertFalse(cgroup_empty(root, group))
        with self.assertRaisesRegex(ValueError, 'ROOT_UNAVAILABLE'):
            cgroup_empty(root, group)

    def test_real_symlinked_descendant_blocks_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            root = os.path.realpath(root)
            group = '/system.slice/xuanjun-uk-stage1-minimal.service'
            path = root + group
            os.makedirs(path)
            with open(path + '/cgroup.procs', 'w') as f: f.write('')
            os.symlink('/tmp', path + '/child')
            with self.assertRaisesRegex(ValueError, 'SYMLINKED'):
                cgroup_empty(root, group)


if __name__ == '__main__': unittest.main()
