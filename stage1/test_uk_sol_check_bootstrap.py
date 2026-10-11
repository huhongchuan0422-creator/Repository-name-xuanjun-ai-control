import hashlib
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sol_bootstrap', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'uk-sol-check-bootstrap.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BootstrapTests(unittest.TestCase):
    def test_manifest_and_narrow_sudo_rule(self):
        with open(os.path.join(os.path.dirname(__file__), '..', 'scripts', 'uk-sol-canary.py'), 'rb') as stream:
            self.assertEqual(hashlib.sha256(stream.read()).hexdigest(), b.DIGEST)
        self.assertTrue(b.RULE.endswith(b'xuanjun-uk-sol-check ""\n'))
        self.assertNotIn(b'ALL\n', b.RULE)

    def test_no_effect_on_wrong_host(self):
        with patch.object(b.socket, 'gethostname', return_value='wrong'), patch.object(b.subprocess, 'run') as run:
            with self.assertRaises(SystemExit):
                b.main()
            run.assert_not_called()

    def test_existing_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = os.path.join(temp, 'target')
            open(target, 'w').close()
            link = os.path.join(temp, 'link')
            os.symlink(target, link)
            with self.assertRaises(ValueError):
                b.check_destination(link)
