"""Protected Python provider wiring only; no SDK credentials or network calls."""
import contextlib
import io
import unittest
from unittest.mock import Mock, patch
from scripts.community_ocr_host import HostOcr
from scripts import community_platform_host as platform


class BankProviderInjection(unittest.TestCase):
    def service(self, provider=None):
        captured = {}
        def compose(*args, **kwargs):
            captured.update(kwargs)
            return Mock(), Mock()
        with patch('scripts.community_ocr_bridge.compose', side_effect=compose):
            service = HostOcr(Mock(), '', Mock(), Mock(), applicant_mode=True, bank_card_infer=provider)
        self.addCleanup(service.close)
        return captured['infer']

    def test_bank_uses_original_trusted_callable_with_unchanged_limits_and_bytes(self):
        provider = Mock(return_value={'fields': {}})
        with patch('scripts.community_license_inference.run_license_layout_ocr') as local:
            infer = self.service(provider)
            result = infer(b'synthetic-bytes', 'bank_card', max_bytes=123, max_pixels=456)
        self.assertEqual(result, {'fields': {}})
        provider.assert_called_once_with(b'synthetic-bytes', 'bank_card', max_bytes=123, max_pixels=456)
        local.assert_not_called()

    def test_bank_unknown_failure_never_retries_or_falls_back(self):
        provider = Mock(side_effect=TimeoutError('PRIVATE_PROVIDER_MESSAGE'))
        with patch('scripts.community_license_inference.run_license_layout_ocr') as local:
            infer = self.service(provider)
            with self.assertRaises(TimeoutError) as raised:
                infer(b'synthetic-bytes', document_type='bank_card', max_bytes=123)
        provider.assert_called_once()
        local.assert_not_called()
        self.assertEqual(raised.exception.ocr_diagnostic['reason'], 'INFERENCE_FAILED')
        self.assertNotIn('PRIVATE_PROVIDER_MESSAGE', str(raised.exception.ocr_diagnostic))

    def test_other_document_types_and_default_bank_keep_original_inference(self):
        provider = Mock()
        with patch('scripts.community_license_inference.run_license_layout_ocr', return_value={'original': True}) as local:
            infer = self.service(provider)
            for kind in ('business_license', 'id_front', 'id_back'):
                self.assertEqual(infer(b'synthetic-bytes', kind), {'original': True})
            provider.assert_not_called()
            default = self.service()
            self.assertEqual(default(b'synthetic-bytes', 'bank_card'), {'original': True})
            self.assertEqual(local.call_count, 4)

    def test_strings_cannot_load_provider_or_open_store(self):
        with patch('scripts.community_ocr_bridge.compose') as compose:
            with self.assertRaisesRegex(ValueError, 'BANK_CARD_INFERENCE_CALLABLE_REQUIRED'):
                HostOcr(Mock(), '', Mock(), Mock(), bank_card_infer='module:provider')
        compose.assert_not_called()

    def test_protected_main_passes_callable_to_original_configure_and_does_not_invoke_it(self):
        provider = Mock()
        host = Mock()
        host.__enter__ = Mock(return_value=host)
        host.__exit__ = Mock(return_value=False)
        args = ['--plan', '/synthetic/plan', '--center-keys', '/synthetic/center', '--wechat-secret', '/synthetic/wechat',
                '--applicant-ocr-key-reference', '/synthetic/ocr-key', '--applicant-ocr-store-reference', '/synthetic/ocr-store']
        with patch.object(platform.PlatformHost, 'preflight_applicant_ocr_plan', return_value='VALIDATED'), patch.object(platform.PlatformHost, 'open', return_value=host):
            self.assertEqual(platform.main(args, bank_card_infer=provider), 0)
        host.configure_applicant_ocr.assert_called_once_with('/synthetic/ocr-key', '/synthetic/ocr-store', bank_card_infer=provider)
        host.serve.assert_called_once()
        provider.assert_not_called()

    def test_invalid_direct_injection_is_rejected_before_key_or_store_handling(self):
        from types import SimpleNamespace
        host = platform.PlatformHost.__new__(platform.PlatformHost)
        host.application = SimpleNamespace(server=None)
        host.ocr = None
        with patch.object(host, 'preflight_applicant_ocr') as preflight:
            with self.assertRaisesRegex(ValueError, 'BANK_CARD_INFERENCE_CALLABLE_REQUIRED'):
                host.configure_applicant_ocr('/synthetic/key', '/synthetic/store', bank_card_infer='module:provider')
        preflight.assert_not_called()

    def test_original_host_passes_exact_provider_to_hostocr_without_invoking_it(self):
        from types import SimpleNamespace
        host = platform.PlatformHost.__new__(platform.PlatformHost)
        host.application = SimpleNamespace(server=None, onboarding=Mock(), center=Mock(), identity=Mock(), operations=Mock(), gateway=SimpleNamespace())
        host.ocr = None
        host.plan = dict(center_root='/synthetic/center', runtime_directory='/synthetic/runtime')
        class Store:
            db_path = '/synthetic/ocr'
        api = SimpleNamespace(SecureSQLiteJobStore=Store)
        store = Store()
        provider = Mock()
        def file_info(path):
            return SimpleNamespace(st_dev=1, st_ino=2 if str(path)=='/synthetic/ocr' else 3)
        with patch.object(platform, '_directory'), patch.object(platform, '_file', side_effect=file_info), patch('scripts.community_mini_merchant.MiniMerchant') as merchant, patch('scripts.community_ocr_host.HostOcr') as service:
            result = host.configure_ocr('', api, store, applicant_mode=True, bank_card_infer=provider)
        service.assert_called_once_with(merchant.return_value, '', api, store, applicant_mode=True, bank_card_infer=provider)
        self.assertIs(result, host.application.gateway.ocr)
        provider.assert_not_called()

    def test_main_rejects_provider_without_existing_ocr_references_before_open(self):
        args = ['--plan', '/synthetic/plan', '--center-keys', '/synthetic/center', '--wechat-secret', '/synthetic/wechat']
        with patch.object(platform.PlatformHost, 'open') as opening, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                platform.main(args, bank_card_infer=Mock())
        opening.assert_not_called()


if __name__ == '__main__':
    unittest.main()
