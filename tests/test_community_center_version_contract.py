"""Exact website Center integration on synthetic, existing community fixtures."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import test_community_mini_center_identity as fixtures
from scripts.community_stage_package import build
from scripts.pr122_customer_core import Denied


class ExactWebsiteSource(unittest.TestCase):
    def test_package_rejects_missing_new_center_dependency(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            names = ('scripts/community_stage_local.py', 'scripts/community_stage_runtime.py',
                     'scripts/community_stage_package.py', 'clients/community-mini/app.json',
                     'scripts/pr122_customer_core.py', 'scripts/pr122_customer_source.py',
                     'scripts/pr122_customer_runtime.py', 'scripts/pr122_customer_evidence.py',
                     'scripts/pr122_customer_activity_evidence.py')
            for name in names:
                destination = target/name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((root/name).read_bytes())
            with self.assertRaisesRegex(ValueError, 'REQUIRED_SOURCE_MISSING'):
                build(target)

    def test_six_exact_upstream_blobs_are_packaged(self):
        root = Path(__file__).resolve().parents[1]
        pins = json.loads((root/'docs/development/COMMUNITY_PINNED_DEPENDENCIES_20261017.json').read_text())
        self.assertEqual(pins['integration']['target_commit'], '15c263e65f42cce18828a81bfc261e48c94636c7')
        self.assertEqual(len(pins['dependencies']), 6)
        package, _ = build(root)
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            for pin in pins['dependencies']:
                raw = (root/pin['path']).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), pin['sha256'])
                self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(), pin['source_blob_sha'])
                self.assertEqual(archive.read(pin['path']), raw)
                if pin['path'].endswith(('_source.py', '_runtime.py')):
                    self.assertEqual(pin['previous_pin']['sha256'], pin['sha256'])


class ExistingIdentityEvidenceIntegration(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ExistingCenterComposition()
        self.fx.setUp()
        self.c = self.fx.center

    def tearDown(self):
        self.fx.tearDown()

    def test_web_message_and_mini_use_same_account_project_and_database(self):
        token = self.fx.token()
        uid, pid, principal = self.fx.identity._resolve(token, 'shop1')
        self.assertEqual(uid, self.fx.uid1)
        self.assertEqual(principal.tenant_id, 'tenant1')
        message = self.c.message(uid, pid, 'Synthetic Center integration')
        self.assertEqual(self.c.messages(uid, pid)[0]['id'], message['id'])
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM message_evidence').fetchone()[0], 1)
        self.assertEqual(self.c.check_integrity()['integrity'], 'PASS')
        self.fx.reopen()
        self.assertEqual(self.fx.identity._resolve(token, 'shop1')[0], uid)
        self.assertEqual(self.fx.center.messages(uid, pid)[0]['id'], message['id'])
        self.assertEqual(self.fx.center.check_integrity()['integrity'], 'PASS')

    def test_revocation_blocks_both_existing_web_and_mini_access(self):
        token = self.fx.token()
        self.c.message(self.fx.uid1, 'project1', 'Synthetic private message')
        self.c.db.execute('UPDATE members SET active=0 WHERE user_id=?', (self.fx.uid1,))
        with self.assertRaises(Denied):
            self.c.messages(self.fx.uid1, 'project1')
        with self.assertRaises(PermissionError):
            self.fx.identity._resolve(token, 'shop1')

    def test_failed_evidence_capture_rolls_back_message_and_audit(self):
        before = {t: self.c.db.execute('SELECT count(*) FROM '+t).fetchone()[0]
                  for t in ('messages', 'message_evidence', 'audit')}
        self.c.evidence_context = lambda uid, pid: {'unexpected': 'fixture'}
        with self.assertRaisesRegex(Denied, 'TRUSTED_EVIDENCE_CONTEXT_FIELDS'):
            self.c.message(self.fx.uid1, 'project1', 'Must roll back')
        after = {t: self.c.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in before}
        self.assertEqual(before, after)

    def test_message_content_tampering_is_denied_without_new_identity(self):
        message = self.c.message(self.fx.uid1, 'project1', 'Original fixture')
        self.c.db.execute('UPDATE messages SET payload=? WHERE id=?',
                          (self.c.encrypt(b'Tampered fixture', message['id']), message['id']))
        with self.assertRaisesRegex(Denied, 'MESSAGE_CONTENT_INTEGRITY'):
            self.c.messages(self.fx.uid1, 'project1')


if __name__ == '__main__':
    unittest.main()
