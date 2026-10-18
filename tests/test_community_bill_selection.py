"""Deterministic browser-DOM contract for existing bill selection boundaries."""
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CommunityBillSelection(unittest.TestCase):
    def test_selection_and_request_ownership(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node unavailable')
        subprocess.run([
            node, str(ROOT / 'tests/community_bill_selection_dom.cjs'),
            str(ROOT / 'demos/community-stage/workbench.js'),
            str(ROOT / 'demos/community-stage/workbench.html'),
        ], check=True, timeout=30)


if __name__ == '__main__':
    unittest.main()
