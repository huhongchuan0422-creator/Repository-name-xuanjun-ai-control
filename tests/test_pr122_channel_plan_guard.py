import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('plan_guard', Path(__file__).resolve().parents[1] / 'scripts/pr122_channel_plan_guard.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class PlanGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='pr122-plan-guard-', dir='/root')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.zip = self.root / 'REVIEW_ARTIFACT.zip'
        self.helper = self.root / 'approved-upgrade.py'
        self.zip.write_bytes(b'fixture outer ZIP exact bytes')
        self.package_sha = g.sha(self.zip.read_bytes())
        self.result = {'new': {'zip_sha256': self.package_sha, 'binding': {'source_commit': g.SOURCE, 'channel_sha256': g.CHANNEL_SHA}}, 'production_service_changes': 0}
        code = "from pathlib import Path\nINPUT=Path(" + repr(str(self.zip)) + ")\nBASE=Path(" + repr(str(g.BASE)) + ")\ndef read(path):raise AssertionError('fixture must use pinned bytes')\ndef plan():\n assert read(INPUT)==b'fixture outer ZIP exact bytes'\n return " + repr(self.result) + "\ndef apply():raise AssertionError('apply prohibited')\ndef rollback():raise AssertionError('rollback prohibited')\nif __name__=='__main__':raise AssertionError('main prohibited')\n"
        self.helper.write_text(code)
        for path in (self.zip, self.helper):
            path.chmod(0o400)
        patches = {'INPUT': self.zip, 'HELPER': self.helper, 'ZIP_SHA': self.package_sha, 'HELPER_SHA': g.sha(self.helper.read_bytes())}
        for name, value in patches.items():
            p = patch.object(g, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(g.os, 'uname', return_value=SimpleNamespace(nodename=g.HOST))
        p.start();self.addCleanup(p.stop)
        p = patch.object(g.sys, 'flags', SimpleNamespace(isolated=1))
        p.start();self.addCleanup(p.stop)
        p = patch.object(g.sys, 'dont_write_bytecode', True)
        p.start();self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'SUDO_UID': ''})
        p.start();self.addCleanup(p.stop)

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_mode) for p in self.root.iterdir()}

    def test_exact_inputs_plan_only_and_no_file_changes(self):
        before = self.snapshot()
        result = g.plan()
        self.assertEqual(result['plan'], self.result)
        self.assertEqual(result['plan_sha256'], g.sha(g.canonical(self.result)))
        self.assertFalse(result['apply_called'])
        self.assertFalse(result['rollback_called'])
        self.assertEqual(self.snapshot(), before)

    def test_wrong_outer_zip_is_rejected_before_helper_execution(self):
        self.zip.chmod(0o600)
        self.zip.write_bytes(b'an internally consistent alternative ZIP is still wrong')
        self.zip.chmod(0o400)
        with self.assertRaisesRegex(RuntimeError, 'EXACT_INPUT_SHA256'):
            g.plan()

    def test_wrong_helper_is_rejected_before_execution(self):
        self.helper.chmod(0o600)
        self.helper.write_text("raise AssertionError('MUST NOT EXECUTE')")
        self.helper.chmod(0o400)
        with self.assertRaisesRegex(RuntimeError, 'EXACT_INPUT_SHA256'):
            g.plan()

    def test_symlink_hardlink_and_writable_files_rejected(self):
        saved = self.zip.read_bytes()
        self.zip.unlink();self.zip.symlink_to(self.helper)
        with self.assertRaises(RuntimeError):g.plan()
        self.zip.unlink();self.zip.write_bytes(saved);self.zip.chmod(0o666)
        with self.assertRaises(RuntimeError):g.plan()
        self.zip.chmod(0o400);os.link(self.zip, self.root / 'second-link')
        with self.assertRaises(RuntimeError):g.plan()

    def test_runner_nonroot_wrong_host_and_unsafe_python_are_denied(self):
        with patch.dict(os.environ, {'SUDO_UID': '1002'}), self.assertRaises(RuntimeError):g.plan()
        with patch.object(g.os, 'geteuid', return_value=1002), self.assertRaises(RuntimeError):g.plan()
        with patch.object(g.os, 'uname', return_value=SimpleNamespace(nodename='wrong-host')), self.assertRaises(RuntimeError):g.plan()
        with patch.object(g.sys, 'dont_write_bytecode', False), self.assertRaises(RuntimeError):g.plan()

    def test_apply_rollback_extra_args_not_exposed(self):
        for args in ([], ['apply'], ['rollback'], ['plan', '--anything']):
            with patch.object(g.sys, 'argv', ['guard.py', *args]), patch.object(g, 'plan', side_effect=AssertionError('must not call')), self.assertRaises(RuntimeError):g.main()

    def test_changed_baseline_between_two_plan_reads_rejected(self):
        code = self.helper.read_text().replace('def plan():', 'counter=0\ndef plan():\n global counter\n counter+=1').replace(' return ' + repr(self.result), ' return {**' + repr(self.result) + ", 'generation':counter}")
        self.helper.chmod(0o600)
        self.helper.write_text(code)
        self.helper.chmod(0o400)
        with patch.object(g, 'HELPER_SHA', g.sha(self.helper.read_bytes())), self.assertRaisesRegex(RuntimeError, 'PLAN_BASELINE_CHANGED'):g.plan()


if __name__ == '__main__':
    unittest.main()
