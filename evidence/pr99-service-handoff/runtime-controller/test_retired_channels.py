import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from retired_channels import isolate_retired_units, RetirementHold, UNITS, STOP_EDGES


class Tests(unittest.TestCase):
    def setUp(self):
        host = patch('retired_channels.os.uname', return_value=SimpleNamespace(nodename='iZ6wee8q9z4t03hvqumwfhZ'))
        uid = patch('retired_channels.os.geteuid', return_value=0)
        host.start(); uid.start()
        self.addCleanup(host.stop); self.addCleanup(uid.stop)

    def runner(self, foreign='', timeout=False):
        self.calls = []
        def run(argv, **kwargs):
            self.calls.append(argv)
            if argv[1] == 'show' and 'LoadState' in argv[-1]:
                body = 'LoadState=loaded\nActiveState=active\nMainPID=123\n'
                body += '\n'.join(key + '=' + (foreign if key == 'RequiredBy' else '') for key in STOP_EDGES)
            elif argv[1] == 'show':
                body = 'ActiveState=inactive\nMainPID=0\nControlPID=0\nUnitFileState=masked-runtime\n'
            else:
                if timeout:
                    raise subprocess.TimeoutExpired(argv, 30)
                body = ''
            return SimpleNamespace(returncode=0, stdout=body.encode(), stderr=b'')
        return run

    def test_exact_retired_scope(self):
        result = isolate_retired_units(lambda *args: True, self.runner())
        effects = [call for call in self.calls if call[1] in ('mask', 'stop')]
        self.assertEqual([call[-1] for call in effects], list(UNITS))
        self.assertFalse(result['database_fenced'])
        self.assertFalse(result['data_deleted'])

    def test_foreign_dependency_blocks_before_any_stop(self):
        with self.assertRaisesRegex(RetirementHold, 'PROPAGATE'):
            isolate_retired_units(lambda *args: True, self.runner('binance-executor.service'))
        self.assertFalse(any(call[1] in ('mask', 'stop') for call in self.calls))

    def test_missing_admission_no_command(self):
        runner = self.runner()
        with self.assertRaises(RetirementHold):
            isolate_retired_units(lambda *args: False, runner)
        self.assertEqual(self.calls, [])

    def test_unknown_not_retried(self):
        with self.assertRaisesRegex(RetirementHold, 'UNKNOWN'):
            isolate_retired_units(lambda *args: True, self.runner(timeout=True))
        self.assertEqual(len([call for call in self.calls if call[1] == 'stop']), 1)


if __name__ == '__main__':
    unittest.main()
