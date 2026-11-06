"""Image-only exact CLI acceptance; real bundled OCR, synthetic protected inputs.

Executed explicitly by Docker verify, not the source-only discovery suite.
Missing services, pinned models, native libraries or nonroot identity fail.
No provider requests, production roots, live keys, or model stubs are used.
"""
import os
import unittest
from cryptography.fernet import Fernet
import test_community_platform_host as host_fixture


class CompleteImageStartup(unittest.TestCase):
    def setUp(self):
        self.assertNotEqual(os.geteuid(),0,'Image startup acceptance must run as nonroot')
        from services.ocr_engine import api, ocr_core
        # Enforce actual installed immutable models before any synthetic stores.
        ocr_core._verified_model_paths()
        self.fx=host_fixture.FormalHost();self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        key=Fernet.generate_key()
        self.key_path=self.fx.write('synthetic-image-ocr-key.json',{'ocr_encryption_key':key.decode('ascii')})
        self.db_path=self.fx.root/'synthetic-image-ocr.sqlite'
        self.store=api.SecureSQLiteJobStore(str(self.db_path),key)
        self.db_path.chmod(0o600)
        self.refs=(self.key_path,self.db_path)

    def test_real_scanner_and_ocr_compose_with_original_pins_and_no_provider_activation(self):
        from scripts.community_uploaded_image_scanner import UploadedImageScanner
        with self.fx.open() as host:
            self.assertEqual(host.configure_applicant_image_scanner(),'APPLICANT_IMAGE_SCANNER_CONFIGURED')
            service=host.configure_applicant_ocr(*map(str,self.refs))
            self.assertIsInstance(host.center.scanner,UploadedImageScanner)
            self.assertIs(service,host.application.gateway.ocr)
            self.assertTrue(service.applicant_mode)
            self.assertFalse(host.application.onboarding.wechat_applyment.enabled)
            self.assertIsNone(getattr(host.application.gateway,'payments',None))

    def test_complete_cli_scanner_ocr_refs_health_sigterm_and_restart(self):
        self.fx._assert_actual_nonroot_cli_unix_health_sigterm_and_restart(
            image_scanner=True,ocr_references=self.refs)

    def test_complete_cli_missing_scanner_runtime_fails_closed(self):
        self.fx._assert_missing_image_scanner_in_copied_runtime_fails_real_host_and_cli(
            ocr_references=self.refs)


if __name__=='__main__':unittest.main()
