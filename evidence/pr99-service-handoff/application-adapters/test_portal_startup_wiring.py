import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import portal_startup_wiring as wiring
from credential_key_binding import CredentialBindingHold

# Exact builder returned by Owner's hash-pinned Tokyo source extraction.
BUILDER = b'''def build_service(state_root):
    load_local_credential_env()
    state_root = ensure_private_dir(Path(state_root))
    session_repo = FileBackedSubmissionSessionRepository(state_root / 'sessions')
    credential_repository = CredentialRepository()
    operations_store = OperationsSecretRefStore(Path('/opt/trading-system/runtime/v8-domestic-operations/operations-secretref-store'))
    credential_intake = None
    try:
        credential_intake = SecureCredentialIntakeService(credential_store=CredentialStore(repository=credential_repository), session_repository=FileBackedSubmissionSessionRepository(state_root / 'credential-intake-sessions'), audit_sink=CredentialIntakeAuditSink(SensitiveValueRedactor()), token_ttl_seconds=1800)
    except Exception:
        credential_intake = None
    return SecureSecretsPortalService(credential_intake=credential_intake, credential_status_bridge=StatusOnlyOperationsBridge(credential_repository), operations_store=operations_store, session_repository=session_repo, ttl_seconds=1800, max_attempts_per_form=3)
'''


class WiringTests(unittest.TestCase):
    def namespace(self):
        repository = object()
        native = object()
        def obj(*args, **kwargs):
            return SimpleNamespace(args=args, **kwargs)
        return dict(Path=Path, load_local_credential_env=lambda: None,
                    ensure_private_dir=lambda x: x, CredentialRepository=lambda: repository,
                    CredentialStore=native, FileBackedSubmissionSessionRepository=obj,
                    OperationsSecretRefStore=obj, SecureCredentialIntakeService=obj,
                    CredentialIntakeAuditSink=obj, SensitiveValueRedactor=obj,
                    SecureSecretsPortalService=obj, StatusOnlyOperationsBridge=obj), repository, native

    def test_original_builder_passes_actual_repository_to_binding(self):
        namespace, repository, native = self.namespace()
        store, calls = object(), []
        def bind(repo, cls):
            calls.append((repo, cls))
            return store
        with patch.object(wiring, 'PORTAL_SHA', hashlib.sha256(BUILDER).hexdigest()):
            builder = wiring.compile_wired_builder(BUILDER, namespace, bind)
            service = builder('/private-test-state')
        self.assertEqual(calls, [(repository, native)])
        self.assertIs(service.credential_intake.credential_store, store)
        self.assertIs(service.credential_status_bridge.args[0], repository)

    def test_original_silent_failure_is_now_explicit_hold(self):
        namespace, _, _ = self.namespace()
        def fail(*args):
            raise RuntimeError('private detail must not escape')
        with patch.object(wiring, 'PORTAL_SHA', hashlib.sha256(BUILDER).hexdigest()):
            builder = wiring.compile_wired_builder(BUILDER, namespace, fail)
            with self.assertRaisesRegex(CredentialBindingHold, '^CREDENTIAL_INTAKE_STARTUP_FAILED$'):
                builder('/private-test-state')

    def test_wrong_source_hash_cannot_compile(self):
        with self.assertRaisesRegex(CredentialBindingHold, 'PORTAL_SOURCE_CHANGED'):
            wiring.compile_wired_builder(BUILDER, {}, lambda *args: None)

    def test_no_exclusive_startup_cannot_replace_original(self):
        original = lambda path: None
        module = SimpleNamespace(build_service=original)
        with self.assertRaises(CredentialBindingHold):
            wiring.install_startup_binding(module, BUILDER, lambda *args: None, lambda x: False)
        self.assertIs(module.build_service, original)


if __name__ == '__main__':
    unittest.main()
