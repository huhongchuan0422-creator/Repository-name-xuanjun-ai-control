"""The production entry must fail before a host action without enrollment."""
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
ENTRY=ROOT/'successor_controller/pr17_b5_successor_entry.py'
sys.path[:0]=[str(ROOT),str(ROOT/'successor_controller'),str(ROOT/'reused-6825')]
import pr17_b5_successor_entry as entry
import pr17_b5_successor_review as c53


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

    def test_recovery_routes_actual_observer_states_without_repost(self):
        called=[]
        class Transaction:
            def resume_recovered_custody(self):
                called.append('custody');return {'state':'CUSTODY_COMPLETE_DELIVERY_NOT_PROVEN'}
            def resume_recovered_b5_http_wait(self):
                called.append('wait');return {'state':'B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY'}
        def attempted(_):raise c53.Hold('ENTRY_INTAKE_ALREADY_ATTEMPTED')
        with patch.object(entry,'_recover',return_value=Transaction()),\
             patch.object(entry,'_verified_window',side_effect=attempted):
            import pr17_b5_successor_authority as authority
            for state,expected in (('SUCCESS_SNAPSHOT_READONLY','custody'),
                ('B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY','wait')):
                with patch.object(authority,'inspect_recovered_candidate_readonly',
                                  return_value={'state':state}):
                    entry.dispatch('recover')
                self.assertEqual(called[-1],expected)
            with patch.object(authority,'inspect_recovered_candidate_readonly',
                              return_value={'state':'UNKNOWN_OR_PENDING_NO_REPOST'}):
                self.assertEqual(entry.dispatch('recover')['state'],
                                 'UNKNOWN_OR_PENDING_NO_REPOST')
            self.assertEqual(called,['custody','wait'])


if __name__=='__main__':
    unittest.main()
