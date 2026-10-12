import os
import tempfile
import unittest
from legacy_host_adapter import LegacyHostAdapter
from legacy_quiescence import ALLOWED_UNITS


class HostAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = os.path.realpath(self.temp.name)
        self.calls = []
        self.adapter = LegacyHostAdapter(self.root, run=lambda *a,**k:self.calls.append(a))
        self.bindings = {u:{'fragment_path':'/etc/systemd/system/'+u,
                            'sha256':'a'*64,'cgroup':'/system.slice/'+u}
                         for u in ALLOWED_UNITS}

    def test_wrong_host_or_identity_blocks_before_any_service_action(self):
        with self.assertRaisesRegex(ValueError, 'FIXED_UK_ROOT'):
            self.adapter.stop_and_inhibit(self.bindings)
        self.assertEqual(self.calls, [])
        self.assertEqual(os.listdir(self.root), [])

    def test_arbitrary_root_file_cannot_become_mask_target(self):
        self.adapter._authority = lambda: None
        self.bindings['xuanjun-uk-openclaw.service']['fragment_path'] = '/etc/passwd'
        with self.assertRaisesRegex(ValueError, 'EFFECT_UNIT_BINDING'):
            self.adapter.stop_and_inhibit(self.bindings)
        self.assertEqual(self.calls, [])
        self.assertEqual(os.listdir(self.root), [])

    def test_unreviewed_unit_set_blocks_before_backups_or_stop(self):
        self.adapter._authority = lambda: None
        self.bindings['another.service'] = self.bindings['xuanjun-uk-openclaw.service']
        with self.assertRaisesRegex(ValueError, 'EXACT_LEGACY'):
            self.adapter.stop_and_inhibit(self.bindings)
        self.assertEqual(self.calls, [])


if __name__ == '__main__': unittest.main()
