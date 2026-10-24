import json
import os
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parent

import successor_contract as contract
from successor_source_loader import read_exact_42
sys.path[:0]=[str(ROOT/'successor_controller'),str(ROOT/'reused-6825')]
from pr17_b5_successor_loader import read_fixed_local_source
import pr17_b5_successor_binder as frozen_binder

class ExactSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'release'
        self.root.mkdir()
        self.manifest = (ROOT / 'RUNTIME_SOURCE_MANIFEST.json').read_bytes()
        listing = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_bytes())
        for row in listing['files']:
            if row['release_path'] is None:
                continue
            target = self.root / row['release_path']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / row['bundle_path']).read_bytes())

    def test_exact_tree(self):
        result = read_exact_42(str(self.root), self.manifest)
        self.assertEqual(len(result), 42)
        contract.validate((ROOT / 'SUCCESSOR_SPEC.json').read_bytes(),
                          (ROOT / 'ORIGINAL_REVIEWED_SPEC.json').read_bytes(),
                          (ROOT / 'EXTERNAL_RELEASE_BINDER.json').read_bytes(),
                          self.manifest, result)

    def test_packaged_new19_tree_is_complete_and_exact(self):
        # Exercise the actual deliverable path, not just a tree assembled by
        # the test from other repository paths.
        result=read_exact_42(str(ROOT/'new19-source'),self.manifest)
        self.assertEqual(len(result),42)
        contract.validate((ROOT/'SUCCESSOR_SPEC.json').read_bytes(),
                          (ROOT/'ORIGINAL_REVIEWED_SPEC.json').read_bytes(),
                          (ROOT/'EXTERNAL_RELEASE_BINDER.json').read_bytes(),
                          self.manifest,result)
        spec=frozen_binder.verify_spec_bytes((ROOT/'SUCCESSOR_SPEC.json').read_bytes())
        pinned=read_fixed_local_source(spec,str((ROOT/'new19-source').resolve()))
        self.assertEqual(len(pinned),43)

    def test_changed_file_and_symlink_parent_rejected(self):
        target = self.root / 'production/cloud_connection/queue.py'
        target.write_bytes(target.read_bytes() + b'\n')
        with self.assertRaises(contract.Hold):
            read_exact_42(str(self.root), self.manifest)
        target.write_bytes((ROOT / 'new19-source/production/cloud_connection/queue.py').read_bytes())
        moved = self.root / 'production/cloud_connection'
        relocated = self.root / 'elsewhere'
        moved.rename(relocated)
        os.symlink(relocated, moved)
        with self.assertRaises(contract.Hold):
            read_exact_42(str(self.root), self.manifest)

    def test_root_symlink_rejected(self):
        alias = Path(self.tmp.name) / 'alias'
        os.symlink(self.root, alias)
        with self.assertRaises(contract.Hold):
            read_exact_42(str(alias), self.manifest)


if __name__ == '__main__':
    unittest.main()
