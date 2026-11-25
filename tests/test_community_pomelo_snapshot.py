"""Direct regression for the existing snapshot consumer; no provider calls."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import community_mini_snapshot_build as build
import community_mini_snapshot_input as stage

class PomeloSnapshot(unittest.TestCase):
    def test_final_snapshot_is_consumed_with_exact_pins(self):
        p = ROOT / 'deploy/community-preview/hangzhou-snapshot'
        archive = (p / 'snapshot.zip').read_bytes()
        manifest = (p / 'manifest.json').read_bytes()
        self.assertEqual(hashlib.sha256((p / 'backend-pair.json').read_bytes()).hexdigest(), build.BACKEND_PAIR_SHA256)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'staged'
            stage.prepare(archive, manifest, build.MANIFEST, build.ARCHIVE, dest)
            for name in ('index.js', 'index.wxml', 'index.wxss'):
                relative = 'pages/checkout/' + name
                self.assertEqual((dest / 'clients/community-mini' / relative).read_bytes(), (ROOT / 'clients/community-mini' / relative).read_bytes())

    def test_only_three_original_uploaded_files_change(self):
        p = ROOT / 'deploy/community-preview/hangzhou-snapshot'
        files = json.loads((p / 'manifest.json').read_bytes())['files']
        changed = ['pages/checkout/index.js', 'pages/checkout/index.wxml', 'pages/checkout/index.wxss']
        untouched = {k: v for k, v in files.items() if k not in changed}
        # d344-lineage 57-file snapshot bound to c741 trio; 54 non-checkout entries unchanged vs their pins.
        digest = hashlib.sha256(json.dumps(untouched, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest, 'd20c1e3432128f3d54c02620f87c28662ed1f51164639f6792a2a34b66d9a08b')
        self.assertEqual(len(files), 57)

if __name__ == '__main__':
    unittest.main()
