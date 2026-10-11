import importlib.util
import os
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sol_diag', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'uk-sol-diagnostic.py'))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class DiagnosticTests(unittest.TestCase):
    def test_only_known_status_and_target_can_be_emitted(self):
        raw = {'provider': 'openai', 'status': 'usable', 'access_token': 'private',
               'profiles': [{'id': 'private@example.test', 'reason': 'secret=value',
                             'model': 'openai/gpt-6.1-sol'}]}
        result = d.summarize(raw)
        self.assertNotIn('private', str(result))
        self.assertNotIn('secret=value', str(result))
        self.assertIn({'field': 'model', 'value': d.TARGET}, result)

    def test_wrong_host_does_not_execute_cli(self):
        with patch.object(d.socket, 'gethostname', return_value='wrong'), patch.object(d.subprocess, 'run') as run:
            with self.assertRaises(SystemExit):
                d.main()
            run.assert_not_called()
