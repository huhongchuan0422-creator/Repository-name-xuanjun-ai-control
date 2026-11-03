import hashlib
import importlib.util
import os
import pathlib
import json
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('r1_input', ROOT/'scripts/community_mini_r1_input.py')
r1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r1)


def environment(temp):
    control = 'a' * 40
    return dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REPOSITORY=r1.REPO,
                GITHUB_REF='refs/heads/'+r1.BRANCH, GITHUB_SHA=control,
                GITHUB_RUN_ID='99999999999', GITHUB_RUN_ATTEMPT='1',
                PREVIEW_CONTROL_SHA=control, PREVIEW_SOURCE_SHA=r1.SOURCE_SHA,
                PREVIEW_PRODUCT_TREE=r1.SOURCE_TREE, PREVIEW_PRODUCT_ZIP_SHA256=r1.ZIP_SHA256,
                PREVIEW_BINDING_ID=r1.BINDING_ID, PREVIEW_TARGET=r1.PROFILE,
                PREVIEW_ENABLED='true', IMAGE_BUILD_ENABLED='false', RUNNER_TEMP=str(temp),
                COMMUNITY_PREVIEW_PRODUCT_CONTEXT=str(pathlib.Path(temp)/'community-mini-product-context-99999999999-1.json'))


def source_available():
    return subprocess.run(['git', '-C', str(ROOT), 'cat-file', '-e', r1.SOURCE_SHA+'^{commit}'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


@unittest.skipUnless(source_available(), 'exact R1 source is supplied by the dedicated R1 affected scope')
class R1Input(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name); self.env = environment(self.root)

    def test_exact_archive_reproduces_reviewed_zip_and_stages_identity(self):
        raw, files = r1.build_archive()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), r1.ZIP_SHA256)
        self.assertEqual(len(files), 66)
        value = r1.receipt(raw, files, self.env)
        staged = r1.stage(raw, value, self.env)
        self.assertFalse(staged['payments'])
        identity = r1.identity(self.env)
        self.assertEqual(identity['product_source_sha'], r1.SOURCE_SHA)
        self.assertEqual(identity['backend_source_sha'], r1.SOURCE_SHA)
        self.assertEqual(len(identity['prepared_files']), 36)

    def test_context_rejects_any_changed_binding(self):
        for key, value in [('PREVIEW_SOURCE_SHA', 'b'*40), ('PREVIEW_PRODUCT_TREE', 'b'*40),
                           ('PREVIEW_PRODUCT_ZIP_SHA256', '0'*64), ('PREVIEW_BINDING_ID', 'other'),
                           ('PREVIEW_ENABLED', 'false'), ('IMAGE_BUILD_ENABLED', 'true')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                r1.control_context(dict(self.env, **{key: value}))

    def test_receipt_never_claims_upload_review_or_release(self):
        raw, files = r1.build_archive(); value = r1.receipt(raw, files, self.env)
        self.assertFalse(value['upload_performed'])
        self.assertFalse(value['review_submitted'])
        self.assertFalse(value['public_release'])
        self.assertFalse(value['payments'])

    def test_existing_prepare_path_accepts_only_staged_r1_and_keeps_payments_false(self):
        raw, files = r1.build_archive(); value = r1.receipt(raw, files, self.env)
        r1.stage(raw, value, self.env)
        output = self.root/'connected'
        env = dict(self.env, COMMUNITY_FIXED_PRODUCT_PREVIEW='true',
                   COMMUNITY_FIXED_PRODUCT_KIND='r1-7ca1ac2a',
                   COMMUNITY_CONNECTED_MINI_OUTPUT=str(output),
                   COMMUNITY_PREVIEW_PROFILE=r1.PROFILE)
        result = subprocess.run(['node', str(ROOT/'deploy/community-preview/prepare-mini.cjs')],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        prepared = json.loads((output/'CONNECTED_PREVIEW_RECEIPT.json').read_text())
        self.assertFalse(prepared['payments'])
        self.assertFalse(prepared['upload_performed'])
        self.assertEqual(prepared['frontend_source_sha'], r1.SOURCE_SHA)
        self.assertEqual(len(prepared['prepared_files']), 36)


if __name__ == '__main__':
    unittest.main()
