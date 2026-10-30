"""Host CLI early rejection/redaction; mocks only, never opens a host."""
import io
import contextlib
import unittest
from unittest.mock import patch
from scripts.community_platform_host import main


class ApplicantOcrPreflightCli(unittest.TestCase):
    def check_rejection(self, message, expected):
        args=['--plan','/synthetic/plan','--center-keys','/synthetic/keys',
              '--wechat-secret','/synthetic/wechat',
              '--applicant-ocr-key-reference','/synthetic/ocr-key',
              '--applicant-ocr-store-reference','/synthetic/ocr-db']
        out=io.StringIO()
        with patch('scripts.community_platform_host.PlatformHost.preflight_applicant_ocr_plan',
                   side_effect=PermissionError(message)), \
             patch('scripts.community_platform_host.PlatformHost.open') as opened, \
             contextlib.redirect_stdout(out):
            self.assertEqual(main(args),2)
            opened.assert_not_called()
        self.assertEqual(out.getvalue(),expected+'\n')

    def test_onboarding_rejection_precedes_host_open(self):
        self.check_rejection('OCR_ONBOARDING_REQUIRED','OCR_ONBOARDING_REQUIRED')

    def test_arbitrary_exception_is_redacted_before_host_open(self):
        self.check_rejection('secret provider value','BACKEND_NOT_READY')


if __name__ == '__main__':
    unittest.main()
