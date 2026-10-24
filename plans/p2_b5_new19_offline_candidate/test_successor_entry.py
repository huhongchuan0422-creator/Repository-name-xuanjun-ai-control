"""The production entry must fail before a host action without enrollment."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ENTRY=ROOT/'successor_controller/pr17_b5_successor_entry.py'


class EntryTests(unittest.TestCase):
    def test_help_and_no_action_are_inert(self):
        help_result=subprocess.run([sys.executable,'-B',str(ENTRY),'--help'],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                   timeout=10)
        self.assertEqual(help_result.returncode,0,help_result.stderr)
        self.assertIn(b'intake',help_result.stdout)
        missing=subprocess.run([sys.executable,'-B',str(ENTRY)],
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               timeout=10)
        self.assertNotEqual(missing.returncode,0)

    def test_local_checkout_cannot_execute_or_recover(self):
        for action in ('execute','intake','query','recover','close'):
            argv=[sys.executable,'-B',str(ENTRY),action]
            if action=='execute':
                argv += ['--batch','fixed','--attempt','fixed',
                         '--approval-ref','fixed','--window-start','1']
            result=subprocess.run(argv,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(result.returncode,2,(action,result.stderr))
            self.assertIn(b'"state": "HOLD"',result.stdout)
            self.assertIn(b'NOT_EXECUTED',result.stdout)


if __name__=='__main__':
    unittest.main()
