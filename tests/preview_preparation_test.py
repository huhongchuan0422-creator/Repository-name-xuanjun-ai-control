"""Build a real source ZIP, verify it, extract empty, and use workflow cwd."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from scripts.community_stage_package import build

ROOT = Path(__file__).resolve().parents[1]


class Preparation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        data, digest = build(ROOT)
        archive_path = self.root / 'community-stage-source.zip'
        archive_path.write_bytes(data)
        self.assertEqual(hashlib.sha256(archive_path.read_bytes()).hexdigest(), digest)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.assertEqual(list(self.source.iterdir()), [])
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read('MANIFEST.json'))
            for name, expected in manifest['files'].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)
            archive.extractall(self.source)
        self.mini = self.source / 'clients/community-mini'
        self.out = self.root / 'connected-preview'

    def run_prepare(self):
        return subprocess.run(
            ['node', 'deploy/community-preview/prepare-mini.cjs'], cwd=self.source,
            env=dict(os.environ, COMMUNITY_CONNECTED_MINI_OUTPUT=str(self.out)),
            capture_output=True, text=True, timeout=15)

    def denied(self):
        result = self.run_prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.out.exists())
        self.assertFalse(list(self.root.glob('.connected-mini-*')))

    def test_real_zip_prepares_nonempty_home_without_mutating_source(self):
        before = (self.mini / 'app.js').read_bytes()
        result = self.run_prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads((self.out / 'CONNECTED_PREVIEW_RECEIPT.json').read_text())
        self.assertEqual(receipt['scene'], 'shop1')
        self.assertFalse(receipt['upload_performed'])
        self.assertFalse(receipt['real_wechat_login_verified'])
        self.assertFalse(receipt['payments'])
        self.assertGreater((self.out / 'pages/home/index.wxml').stat().st_size, 0)
        self.assertEqual((self.mini / 'app.js').read_bytes(), before)
        self.assertNotEqual(self.run_prepare().returncode, 0)

    def test_bad_baseline_leaves_no_output(self):
        (self.mini / 'app.js').write_text('invalid baseline')
        self.denied()

    def test_missing_home_input_leaves_no_output(self):
        (self.mini / 'pages/home/index.wxml').unlink()
        self.denied()

    def test_wrong_appid_leaves_no_output(self):
        p = self.mini / 'project.config.json'
        value = json.loads(p.read_text())
        value['appid'] = 'wx0000000000000000'
        p.write_text(json.dumps(value))
        self.denied()

    def test_source_symlink_is_rejected(self):
        p = self.mini / 'app.wxss'
        p.unlink()
        p.symlink_to(self.mini / 'app.json')
        self.denied()

    def test_dangling_output_symlink_is_not_followed(self):
        self.out.symlink_to(self.root / 'missing')
        result = self.run_prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.out.is_symlink())
        self.assertFalse((self.root / 'missing').exists())


if __name__ == '__main__':
    unittest.main()
