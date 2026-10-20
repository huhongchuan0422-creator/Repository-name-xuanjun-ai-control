"""Synthetic cross-process B2 tests, using exact ea31 from frozen B1 payload."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(os.environ.get('P2_B2_REPO', Path(__file__).resolve().parents[2]))
B1 = Path(os.environ.get('P2_B1_OWNER_SCRIPT', REPO / 'scripts/p2_b1_owner_first_install_20261020.py'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class EvidenceImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = tempfile.TemporaryDirectory()
        spec = importlib.util.spec_from_file_location('frozen_b1', B1)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        unused_zip, unused_files, tools, unused_request = module.validate_payload()
        for name, raw in tools.items():
            path = Path(cls.vendor.name) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        cls.env = dict(os.environ, PYTHONPATH=str(REPO) + os.pathsep + cls.vendor.name,
                       PYTHONDONTWRITEBYTECODE='1')

    @classmethod
    def tearDownClass(cls):
        cls.vendor.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.root = self.base / 'b2-evidence'
        self.source.mkdir(mode=0o700)
        self.root.mkdir(mode=0o700)
        self.request = {'schema': 1, 'scope': 'ISOLATED_TEST_ONLY', 'inputs': {},
            'origin_scope': 'SYNTHETIC_TEST_ONLY', 'installation_id': 'test-install',
            'batch_id': 'b2-preserve', 'attempt_id': 'b2-a1', 'root': str(self.root),
            'source_root': str(self.source), 'sources': {}}
        for name in ('b1-receipt.json', 'b1-summary.json'):
            raw = json.dumps({'synthetic': True, 'name': name}).encode()
            (self.source / name).write_bytes(raw)
            self.request['sources'][name] = {'sha256': digest(raw), 'origin_ref': 'synthetic:' + name}
        self.before = self.snapshot(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, root):
        return {str(p.relative_to(root)): (digest(p.read_bytes()), p.stat().st_ino,
                p.stat().st_mtime_ns, p.stat().st_mode) for p in root.rglob('*') if p.is_file()}

    def call(self, action, request=None):
        process = subprocess.run([sys.executable, '-B', '-m',
            'production.p2_install.evidence_import', action], cwd=REPO, env=self.env,
            input=json.dumps(request or self.request).encode(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=15)
        self.assertEqual(process.stderr, b'', process.stderr)
        return json.loads(process.stdout), process.returncode

    def test_separate_processes_duplicate_import_and_originals_unchanged(self):
        first, code = self.call('execute')
        self.assertEqual((code, first['status']), (0, 'COMMITTED'), first)
        before = self.snapshot(self.root)
        for action in ('inspect', 'recover', 'execute', 'recover'):
            result, code = self.call(action)
            self.assertEqual((code, result['status']), (0, 'COMMITTED'), result)
            self.assertEqual(result['receipt'], first['receipt'])
            self.assertEqual(self.snapshot(self.root), before)
        self.assertEqual(self.snapshot(self.source), self.before)
        index = json.loads((self.root / 'versions/test-install--b2-preserve/INDEX.json').read_text())
        self.assertFalse(index['production_history'])
        self.assertEqual(index['origin_scope'], 'SYNTHETIC_TEST_ONLY')

    def crash_then_recover(self, location):
        marker = self.base / 'checkpoint'
        code = '''import json,os,signal,sys
from pathlib import Path
from production.p2_install import evidence_import as e
marker=Path(sys.argv[1])
def pause(*args):
 marker.write_text('REACHED');os.kill(os.getpid(),signal.SIGSTOP)
if sys.argv[2]=='installed_file':
 e.artifacts._interrupt_hook=pause
else:
 original=e.publish
 def publish(path,raw):
  original(path,raw)
  if path.name=='b2-input.tar':pause()
 e.publish=publish
print(json.dumps(e.dispatch(json.load(sys.stdin),'execute')))
'''
        child = subprocess.Popen([sys.executable, '-B', '-c', code, str(marker), location],
            cwd=REPO, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            child.stdin.write(json.dumps(self.request).encode()); child.stdin.close()
            deadline = time.monotonic() + 10
            while not marker.exists():
                self.assertIsNone(child.poll(), 'child exited before crash checkpoint')
                self.assertLess(time.monotonic(), deadline, 'crash checkpoint timeout')
                time.sleep(0.01)
            before = self.snapshot(self.root)
            self.assertTrue(before)
            child.kill(); child.wait(timeout=5)
            self.assertEqual(child.returncode, -signal.SIGKILL)
            recovered, code = self.call('recover')
            self.assertEqual((code, recovered['status']), (0, 'COMMITTED'), recovered)
            after = self.snapshot(self.root)
            for name, value in before.items():
                self.assertEqual(after[name], value, name)
            again, code = self.call('inspect')
            self.assertEqual((code, again['receipt']), (0, recovered['receipt']))
            self.assertEqual(self.snapshot(self.source), self.before)
        finally:
            if child.poll() is None:
                child.kill(); child.wait(timeout=5)
            child.stdout.close(); child.stderr.close()

    def test_sigkill_after_first_real_installed_file_new_process_recovers(self):
        self.crash_then_recover('installed_file')

    def test_sigkill_after_archive_publish_before_intent_new_process_recovers(self):
        self.crash_then_recover('before_intent')

    def test_unknown_source_never_imports(self):
        self.request['sources']['b1-summary.json']['sha256'] = None
        result, code = self.call('execute')
        self.assertEqual((code, result['status']), (2, 'UNKNOWN'))
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.snapshot(self.source), self.before)

    def test_changed_source_digest_rejected_before_artifact_effect(self):
        (self.source / 'b1-summary.json').write_bytes(b'changed')
        changed = self.snapshot(self.source)
        result, code = self.call('execute')
        self.assertEqual((code, result['status']), (2, 'UNKNOWN'))
        self.assertEqual(result['error']['code'], 'SOURCE_DIGEST_MISMATCH')
        self.assertFalse((self.root / '.p2_artifacts').exists())
        self.assertEqual(self.snapshot(self.source), changed)

    def test_unknown_real_origin_rejected_without_writes(self):
        self.request['origin_scope'] = 'ISOLATED_B1_EVIDENCE'
        result, code = self.call('execute')
        self.assertEqual((code, result['status']), (2, 'UNKNOWN'))
        self.assertEqual(result['error']['code'], 'UNKNOWN_B1_ORIGIN')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_source_symlink_rejected_without_copying_target(self):
        path = self.source / 'b1-summary.json'
        path.unlink()
        path.symlink_to(self.source / 'b1-receipt.json')
        result, code = self.call('execute')
        self.assertEqual((code, result['status']), (2, 'UNKNOWN'))
        self.assertFalse((self.root / '.p2_artifacts').exists())

    def test_changed_identity_does_not_overwrite_prior_import(self):
        first, code = self.call('execute')
        self.assertEqual((code, first['status']), (0, 'COMMITTED'))
        preserved = self.snapshot(self.root)
        self.request['attempt_id'] = 'different-attempt'
        result, code = self.call('recover')
        self.assertEqual((code, result['status']), (2, 'UNKNOWN'))
        self.assertEqual(self.snapshot(self.root), preserved)
        self.assertEqual(self.snapshot(self.source), self.before)


if __name__ == '__main__':
    unittest.main()
