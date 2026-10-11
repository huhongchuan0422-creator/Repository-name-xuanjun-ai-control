import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('runtime_align', Path(__file__).resolve().parents[1] / 'scripts/uk-codex-runtime-align.py')
align = importlib.util.module_from_spec(spec)
spec.loader.exec_module(align)


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'agents': {'defaults': {
            'model': {'primary': align.ALLOW[0], 'fallbacks': []},
            'modelPolicy': {'allow': list(align.ALLOW)}}},
            'plugins': {'entries': {'codex': {'enabled': True}}}}

    def test_policy_rejects_other_models_disabled_plugin_and_existing_fallback(self):
        self.assertTrue(align.policy_ok(self.cfg))
        for change in ('wildcard', 'astra', 'fallback', 'disabled'):
            cfg = copy.deepcopy(self.cfg)
            if change == 'wildcard':
                cfg['agents']['defaults']['modelPolicy']['allow'] = ['openai/*']
            elif change == 'astra':
                cfg['agents']['defaults']['model']['primary'] = 'openai/gpt-6-astra'
            elif change == 'fallback':
                cfg['agents']['defaults']['model']['fallbacks'] = [align.ALLOW[1]]
            else:
                cfg['plugins']['entries']['codex']['enabled'] = False
            self.assertFalse(align.policy_ok(cfg))

    def test_fallback_native_validation_failure_preserves_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'openclaw.json'
            original = json.dumps(self.cfg).encode()
            path.write_bytes(original)
            path.chmod(0o600)
            failure = type('Result', (), {'returncode': 1, 'stdout': b'{"valid":false}'})()
            with patch.object(align, 'CONFIG', path), patch.object(align.subprocess, 'run', return_value=failure):
                with self.assertRaisesRegex(RuntimeError, 'VALIDATION_FAILED'):
                    align.activate_fallback({'CLI': '/fixed/cli'})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_concurrent_change_after_validation_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'openclaw.json'
            path.write_text(json.dumps(self.cfg))
            path.chmod(0o600)
            changed = b'concurrent owner change'
            def validate(*args, **kwargs):
                path.write_bytes(changed)
                return type('Result', (), {'returncode': 0, 'stdout': b'{"valid":true}'})()
            with patch.object(align, 'CONFIG', path), patch.object(align.subprocess, 'run', side_effect=validate):
                with self.assertRaisesRegex(RuntimeError, 'CONCURRENT_CONFIG_CHANGE'):
                    align.activate_fallback({'CLI': '/fixed/cli'})
            self.assertEqual(path.read_bytes(), changed)

    def test_verified_fallback_keeps_primary_and_exact_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'openclaw.json'
            path.write_text(json.dumps(self.cfg))
            path.chmod(0o600)
            success = type('Result', (), {'returncode': 0, 'stdout': b'{"valid":true}'})()
            with patch.object(align, 'CONFIG', path), patch.object(align.subprocess, 'run', return_value=success):
                align.activate_fallback({'CLI': '/fixed/cli'})
            result = json.loads(path.read_bytes())
            self.assertEqual(result['agents']['defaults']['model']['primary'], align.ALLOW[0])
            self.assertEqual(result['agents']['defaults']['model']['fallbacks'], [align.ALLOW[1]])
            self.assertEqual(result['agents']['defaults']['modelPolicy']['allow'], align.ALLOW)

    def test_wrong_host_stops_before_any_mutation(self):
        with patch.object(align.sys, 'argv', ['script']), patch.object(align.os, 'geteuid', return_value=0), patch.object(align.socket, 'gethostname', return_value='TOKYO'), patch.object(align.os, 'open') as opened:
            with self.assertRaisesRegex(SystemExit, 'WRONG_SERVER'):
                align.main()
            opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()
