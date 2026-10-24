"""Default-branch registration policy only; no provider or server I/O."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml'

class EntryRegistration(unittest.TestCase):
    def block(self):
        text=WORKFLOW.read_text()
        return textwrap.dedent(text.split("python - <<'REGISTRATION'\n",1)[1].split('          REGISTRATION',1)[0])

    def run_guard(self,**patch):
        env=dict(os.environ,PREVIEW_ENABLED='true',PREVIEW_SOURCE_SHA='a'*40,
            PREVIEW_TARGET='uk-path-candidate',PREVIEW_EVIDENCE_RUN_ID='40041063448',
            RUN_SHA='a'*40,RUN_REF='refs/heads/feature/chatgpt-community-wechat-sp-offline-20261017',
            RUN_REPOSITORY='huhongchuan0422-creator/Repository-name-xuanjun-ai-control')
        env.update(patch)
        return subprocess.run([sys.executable,'-I','-B','-c',self.block()],env=env,
            capture_output=True,text=True,timeout=5)

    def test_default_off_is_success_without_upload(self):
        result=self.run_guard(PREVIEW_ENABLED='false',PREVIEW_SOURCE_SHA='',PREVIEW_EVIDENCE_RUN_ID='')
        self.assertEqual(result.returncode,0)
        self.assertEqual(result.stdout.strip(),'PREVIEW_DISABLED_NO_UPLOAD')

    def test_exact_original_reference_is_registration_only(self):
        result=self.run_guard()
        self.assertEqual(result.returncode,0)
        self.assertIn('REGISTRATION_ONLY_NO_UPLOAD',result.stdout)

    def test_main_other_branch_or_repository_cannot_request_preview(self):
        for patch in ({'RUN_REF':'refs/heads/main'},{'RUN_REF':'refs/heads/other'},
                      {'RUN_REPOSITORY':'other/repository'}):
            with self.subTest(patch=patch):self.assertNotEqual(self.run_guard(**patch).returncode,0)

    def test_missing_wrong_or_malformed_sha_is_rejected(self):
        for patch in ({'PREVIEW_SOURCE_SHA':''},{'PREVIEW_SOURCE_SHA':'b'*40},
                      {'RUN_SHA':'not-a-sha','PREVIEW_SOURCE_SHA':'not-a-sha'}):
            with self.subTest(patch=patch):self.assertNotEqual(self.run_guard(**patch).returncode,0)

    def test_wrong_target_and_missing_evidence_fail_closed(self):
        for patch in ({'PREVIEW_TARGET':'legacy'},{'PREVIEW_TARGET':'unknown'},
                      {'PREVIEW_EVIDENCE_RUN_ID':''},{'PREVIEW_EVIDENCE_RUN_ID':'../jobs'}):
            with self.subTest(patch=patch):self.assertNotEqual(self.run_guard(**patch).returncode,0)

    def test_switch_is_not_truthy_string(self):
        self.assertNotEqual(self.run_guard(PREVIEW_ENABLED='yes').returncode,0)

    def test_minimal_registration_has_no_upload_or_host_execution(self):
        text=WORKFLOW.read_text()
        self.assertIn('contents: read',text)
        self.assertIn('runs-on: ubuntu-latest',text)
        self.assertIn('timeout-minutes: 5',text)
        self.assertIn('type: boolean\n        default: false',text)
        self.assertIn('options: [uk-path-candidate]',text)
        self.assertNotIn('self-hosted',text.split('jobs:',1)[1])
        for forbidden in ('${{ secrets.','miniprogram-ci','ci.preview(', 'workflow_dispatches',
                          'ssh ', 'sudo ', 'docker ', 'environment:'):
            self.assertNotIn(forbidden,text)
        self.assertNotIn('\n  push:',text)

if __name__=='__main__':unittest.main()
