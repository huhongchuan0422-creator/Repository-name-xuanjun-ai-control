import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / 'deploy' / 'community-preview' / 'Dockerfile.ui-successor'
STAMP = ROOT / 'deploy' / 'community-preview' / 'COMMUNITY_SOURCE_SHA.successor'
RUNTIME_CHANGED = {
    'scripts/community_platform_host.py',
    'demos/community-stage/ui-preview/sources.js',
    'services/ocr_engine/api.py',
    'scripts/community_ocr_dependency.json',
    'scripts/community_ocr_bridge.py',
    'scripts/community_identity_layout.py',
    'scripts/community_ocr_host.py',
    'scripts/community_license_layout.py',
    'scripts/community_license_inference.py',
    'clients/community-mini/pages/merchant-join/index.wxml',
    'demos/community-stage/onboarding.html',
    'demos/community-stage/onboarding.js',
    'scripts/community_merchant_onboarding.py',
    'scripts/community_wechat_applyment.py',
    'scripts/community_mini_application.py',
    'scripts/community_mini_http.py',
    'scripts/community_mini_merchant.py',
    'scripts/community_license_region.py',
    'scripts/community_license_region_areas.json',
    'scripts/community_reports.py',
    'scripts/community_split_rules.py',
    'scripts/community_wechat_payment_activation.py',
    'scripts/community_wechat_sp_actions.py',
    'scripts/community_ad_contract.py',
    'scripts/community_ad_store.py',
    'scripts/community_commerce.py',
    'scripts/community_merchant_store.py',
    'scripts/community_workbench.py',
    'scripts/community_stage_migration.py',
}


class CommunityUiSuccessorPackage(unittest.TestCase):
    def setUp(self):
        self.docker = DOCKERFILE.read_text()
        self.copies = []
        for line in self.docker.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == 'COPY':
                sources = parts[1:-1]
                destination = parts[-1]
                for source in sources:
                    target = destination
                    if len(sources) > 1:
                        self.assertTrue(destination.endswith('/'))
                        target += Path(source).name
                    self.copies.append((source, target))

    def frozen_runtime_binding(self):
        rows = []
        for source, _ in self.copies:
            if source == 'deploy/community-preview/COMMUNITY_SOURCE_SHA.successor':
                continue
            path = ROOT / source
            if path.is_dir():
                for child in sorted(item for item in path.rglob('*') if item.is_file()):
                    relative = child.relative_to(ROOT).as_posix()
                    rows.append(hashlib.sha256(child.read_bytes()).hexdigest() + '  ' + relative + '\n')
            else:
                rows.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + source + '\n')
        tree = hashlib.sha1(''.join(sorted(rows, key=lambda row: row.split('  ', 1)[1])).encode()).hexdigest()
        revision = hashlib.sha1(b'community-ui-successor-v1\0' + tree.encode()).hexdigest()
        return revision, tree

    def test_portal_script_is_copied_to_the_runtime_static_root_and_read_only(self):
        source = 'demos/community-stage/communities.js'
        target = '/app/demos/community-stage/communities.js'
        self.assertIn((source, target), self.copies)
        self.assertIn(target, self.docker.split('RUN chmod 0444 ', 1)[1].split('\n', 1)[0].split())
        entries = (ROOT / 'scripts' / 'community_web_entries.py').read_text()
        server = (ROOT / 'scripts' / 'community_mini_http.py').read_text()
        self.assertIn("'/community/portal.js':('communities.js'", entries)
        self.assertIn("'/community/portal.js':('communities.js'", server)

    def test_every_changed_runtime_module_is_copied_and_read_only(self):
        copied = {source: target for source, target in self.copies}
        read_only = set(self.docker.split('RUN chmod 0444 ', 1)[1].split('\n', 1)[0].split())
        self.assertEqual(set(copied).intersection(RUNTIME_CHANGED), RUNTIME_CHANGED)
        for source in RUNTIME_CHANGED:
            target = '/app/' + source
            self.assertEqual(copied[source], target)
            self.assertIn(target, read_only)

    def test_stamp_env_oci_and_tree_bind_the_exact_copied_runtime_sources(self):
        revision, tree = self.frozen_runtime_binding()
        stamp = STAMP.read_text().strip()
        self.assertRegex(stamp, r'^[0-9a-f]{40}$')
        self.assertEqual(stamp, revision)
        self.assertIn('ENV COMMUNITY_SOURCE_SHA=' + revision, self.docker)
        self.assertIn('org.opencontainers.image.revision=' + revision, self.docker)
        self.assertIn('community.source.tree=' + tree, self.docker)
        self.assertNotIn('5e26425d58bc2a1102a50be8aae3053200f6f875', self.docker + stamp)
        self.assertNotIn('13e61b850e2b9017bf261b7c49d453a7d3307f5f', self.docker + stamp)


if __name__ == '__main__':
    unittest.main()
