"""Run exact candidate runtime tests in an isolated process, never a host install."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

class P2RuntimeProcessCheckpoint(unittest.TestCase):
    def test_required_runtime_process_and_identity_cases(self):
        root=Path(__file__).resolve().parents[1]
        base=root/'evidence/p2-epoch7-access-repair-20261014'
        code='''import pathlib,sys,unittest
base=pathlib.Path(sys.argv[1]).resolve()
sys.path[:0]=[str(base/'runtime/stage1'),str(base/'runtime-process')]
import ledger_server_identity,native_gateway_controller
for module in (ledger_server_identity,native_gateway_controller):
 assert pathlib.Path(module.__file__).resolve().parent==base/'runtime/stage1'
names=['test_runtime_command_lifetime','test_gateway_command_lifetime','test_ledger_server_identity']
suite=unittest.defaultTestLoader.loadTestsFromNames(names)
assert suite.countTestCases()>=74,'REQUIRED_TEST_DISCOVERY_REDUCED'
result=unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful() and not result.skipped,'REQUIRED_TEST_FAILED_OR_SKIPPED'
print('HOSTED_RUNTIME_CHECKPOINT_ONLY_NO_UK_OR_PRODUCTION_ACCEPTANCE')
'''
        # Inherit output directly: no outer PIPE/communicate drain can hide a hang.
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(base)],
            cwd=str(root),timeout=90,stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode,0)

if __name__=='__main__':unittest.main()
