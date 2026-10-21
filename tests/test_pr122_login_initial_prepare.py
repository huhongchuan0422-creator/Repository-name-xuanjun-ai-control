"""Synthetic only. FilesystemTests require an actual non-root local runner.

LogicTests isolate the filesystem boundary explicitly; they are not evidence of
non-root publication. No real credential, authorization or provider is used.
"""
import base64
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from tools import pr122_login_initial_prepare as initial


p = initial.prepare
SENTINEL = 'synthetic-secret-never-display'


def inputs(output='/unused/synthetic-output'):
    source = p.canonical({'subject': 'CANONICAL_IDENTITY_INVENTORY',
                          'target': p.INITIAL_TARGET, 'observed_unix': 1000})
    return dict(assessment={
        'schema': 1, 'target': p.INITIAL_TARGET, 'deployment_profile': p.PROFILE,
        'initialization_mode': p.INITIAL_LOGIN, 'manifest_sha256': 'a' * 64,
        'target_state': 'ABSENT', 'identity_decision': 'NO_EXISTING_AUTHORITATIVE_IDENTITY',
        'observation_ref': '/var/lib/xuanjun-customer-preflight/synthetic.json',
        'observation_sha256': p.digest(source), 'observed_unix': 1000},
        observation=source, manifest_sha256='a' * 64, key_id='synthetic-data',
        backup_key_ref='synthetic-custody', smtp={
            'host': 'smtp.synthetic.invalid', 'port': 465, 'tls_mode': 'implicit_tls',
            'username': 'test@synthetic.invalid', 'sender': 'test@synthetic.invalid',
            'password': SENTINEL}, output_path=output)


class SyntheticAdmission:
    """Test double only. Never authentication or an actual Owner confirmation."""
    def __init__(self):
        self.claims = []
        self.checks = []

    def claim(self, request, now):
        self.claims.append(request)
        return p.canonical({'schema': 1, 'decision': 'ADMITTED',
                            'request_sha256': p.digest(request), 'authority_ref': 'fixture-only',
                            'issued_unix': 1000, 'expires_unix': 1100})

    def check(self, request, grant, now):
        self.checks.append(request)
        return grant


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.adapter = SyntheticAdmission()
        self.entropy = Mock(side_effect=[b'd' * 32, b'b' * 32])
        self.clock = Mock(return_value=1001)
        self.driver = initial.InitialPreparation(admission=self.adapter,
            entropy_source=self.entropy, clock=self.clock)
        self.preflight = patch.object(p, '_preflight_output').start()
        self.writer = patch.object(p, 'write_bundle').start()
        self.reader = patch.object(p, 'inspect_bundle').start()
        self.addCleanup(patch.stopall)

    def refuse(self, data=None):
        result = self.driver.run(**(inputs() if data is None else data))
        self.assertEqual(result['state'], 'NOT_PREPARED')
        self.entropy.assert_not_called()
        self.writer.assert_not_called()
        return result

    def test_default_and_boolean_are_not_admission(self):
        for adapter in (None, True, {'approved': True}):
            driver = initial.InitialPreparation(admission=adapter, entropy_source=self.entropy,
                                                clock=self.clock)
            self.assertEqual(driver.run(**inputs())['error'], 'ADAPTER_REQUIRED')
        self.entropy.assert_not_called()
        self.writer.assert_not_called()

    def test_no_default_entropy_or_clock(self):
        for kwargs in ({'admission': self.adapter, 'clock': self.clock},
                       {'admission': self.adapter, 'entropy_source': self.entropy}):
            self.assertEqual(initial.InitialPreparation(**kwargs).run(**inputs())['error'],
                             'ADAPTER_REQUIRED')

    def test_denial_cancellation_boolean_and_exception_grants(self):
        for value in (True, None, b'{}', b'{"decision":"CANCELLED"}'):
            with self.subTest(value=value):
                self.driver = initial.InitialPreparation(admission=Mock(claim=Mock(return_value=value)),
                    entropy_source=self.entropy, clock=self.clock)
                self.refuse()
        self.adapter.claim = Mock(side_effect=KeyboardInterrupt(SENTINEL))
        self.driver = initial.InitialPreparation(admission=self.adapter,
            entropy_source=self.entropy, clock=self.clock)
        self.refuse()

    def test_expired_grant_before_entropy(self):
        self.clock.return_value = 1100
        self.assertEqual(self.refuse()['error'], 'ADMISSION_EXPIRED')

    def test_grant_binding_and_lifetime(self):
        original = self.adapter.claim
        for change in ({'request_sha256': 'b' * 64}, {'issued_unix': 1002},
                       {'expires_unix': 1400}, {'schema': True}, {'decision': 'DENIED'}):
            with self.subTest(change=change):
                def claim(request, now):
                    value = json.loads(original(request, now)); value.update(change)
                    return p.canonical(value)
                self.adapter.claim = claim
                self.driver = initial.InitialPreparation(admission=self.adapter,
                    entropy_source=self.entropy, clock=self.clock)
                self.refuse()

    def test_wrong_target_existing_identity_and_manifest(self):
        for field, value in (('target', 'wrong'), ('target_state', 'EXISTING'),
                             ('identity_decision', 'UNKNOWN'), ('manifest_sha256', 'b' * 64)):
            data = inputs(); data['assessment'][field] = value
            self.driver = initial.InitialPreparation(admission=self.adapter,
                entropy_source=self.entropy, clock=self.clock)
            self.refuse(data)
        self.assertFalse(self.adapter.claims)

    def test_corrupt_observation_before_admission(self):
        data = inputs(); data['observation'] += b' '
        self.refuse(data)
        self.assertFalse(self.adapter.claims)

    def test_invalid_smtp_before_entropy(self):
        data = inputs(); data['smtp']['port'] = True
        self.refuse(data)

    def test_existing_or_nonprivate_output_before_entropy(self):
        for code in ('OUTPUT_EXISTS', 'DIRECTORY_POLICY'):
            self.preflight.side_effect = p.ConfigError(code)
            self.driver = initial.InitialPreparation(admission=self.adapter,
                entropy_source=self.entropy, clock=self.clock)
            self.assertEqual(self.refuse()['error'], code)

    def test_revoked_before_generation(self):
        self.adapter.check = Mock(return_value=False)
        self.refuse()

    def test_expiry_or_revocation_after_generation_before_write(self):
        for expired in (True, False):
            self.clock.side_effect = [1001, 1001, 1100 if expired else 1001]
            self.adapter.check = SyntheticAdmission().check
            if not expired:
                self.adapter.check = Mock(side_effect=lambda request, grant, now:
                    grant if self.adapter.check.call_count == 1 else False)
            self.entropy.side_effect = [b'd' * 32, b'b' * 32]
            self.driver = initial.InitialPreparation(admission=self.adapter,
                entropy_source=self.entropy, clock=self.clock)
            result = self.driver.run(**inputs())
            self.assertEqual(result['state'], 'NOT_PREPARED')
            self.writer.assert_not_called()

    def test_clock_rollback_and_nonfinite_refused(self):
        for values in ([1001, 1000], [float('nan')], [True]):
            self.clock.side_effect = values
            self.driver = initial.InitialPreparation(admission=self.adapter,
                entropy_source=self.entropy, clock=self.clock)
            self.refuse()

    def test_exact_binding_and_only_two_separate_keys(self):
        data = inputs()
        result = self.driver.run(**data)
        self.assertEqual(result['state'], 'PREPARED_OFFLINE_SYNTHETIC_CANDIDATE')
        self.assertEqual(self.entropy.call_args_list, [unittest.mock.call(32)] * 2)
        config = self.writer.call_args.args[1]
        self.assertEqual(set(config), p.INITIAL_ADMIN_FIELDS)
        self.assertNotEqual(config['backup_key'], config['keys'][config['active_key']])
        request = json.loads(self.adapter.claims[0])
        self.assertEqual(request['output'], data['output_path'])
        self.assertEqual(request['material_classes'], ['data', 'backup'])
        self.assertEqual(len(self.adapter.checks), 2)
        self.reader.assert_called_once_with(Path(data['output_path']))

    def test_snapshot_survives_caller_mutation(self):
        data = inputs(); original = self.adapter.claim
        def claim(request, now):
            data['smtp']['password'] = 'mutated'
            data['assessment']['target'] = 'mutated'
            return original(request, now)
        self.adapter.claim = claim
        self.driver.run(**data)
        self.assertEqual(self.writer.call_args.args[1]['providers']['smtp']['password'], SENTINEL)

    def test_bad_or_repeated_entropy_is_not_retried(self):
        for values in ([b'x' * 31], [b'x' * 32, b'x' * 32], [OSError(SENTINEL)]):
            self.entropy.reset_mock(); self.entropy.side_effect = values
            self.driver = initial.InitialPreparation(admission=self.adapter,
                entropy_source=self.entropy, clock=self.clock)
            result = self.driver.run(**inputs())
            self.assertEqual(result['state'], 'NOT_PREPARED')
            count = self.entropy.call_count
            self.assertEqual(self.driver.run(**inputs())['error'], 'ATTEMPT_ALREADY_USED')
            self.assertEqual(self.entropy.call_count, count)
            self.writer.assert_not_called()

    def test_write_or_readback_exception_unknown_no_retry_no_secret(self):
        for during_read in (False, True):
            self.entropy.side_effect = [b'd' * 32, b'b' * 32]
            self.writer.reset_mock(); self.writer.side_effect = None
            self.reader.reset_mock(); self.reader.side_effect = None
            (self.reader if during_read else self.writer).side_effect = KeyboardInterrupt(SENTINEL)
            self.driver = initial.InitialPreparation(admission=self.adapter,
                entropy_source=self.entropy, clock=self.clock)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                result = self.driver.run(**inputs())
                repeat = self.driver.run(**inputs())
            self.assertEqual(result['state'], 'UNKNOWN')
            self.assertFalse(result['retry_allowed'])
            self.assertEqual(repeat['error'], 'ATTEMPT_ALREADY_USED')
            self.writer.assert_called_once()
            text = json.dumps(result) + out.getvalue() + err.getvalue()
            for secret in (SENTINEL, 'synthetic-custody', base64.b64encode(b'd' * 32).decode()):
                self.assertNotIn(secret, text)
            self.assertEqual(result['production'], 'NOT_INSTALLABLE')
            self.assertEqual(result['target_acceptance'], 'NOT_VERIFIED')


class RootPolicyTests(unittest.TestCase):
    def test_original_root_rejection_before_entropy_or_write(self):
        entropy = Mock()
        driver = initial.InitialPreparation(admission=SyntheticAdmission(),
            entropy_source=entropy, clock=lambda: 1001)
        with patch.object(os, 'geteuid', return_value=0), patch.object(p, 'write_bundle') as writer:
            result = driver.run(**inputs())
        self.assertEqual(result['error'], 'NONROOT_ONLY')
        entropy.assert_not_called()
        writer.assert_not_called()


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        # Never skip or weaken the original NONROOT_ONLY security check.
        self.assertNotEqual(os.geteuid(), 0, 'Requires actual non-root runner')
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.parent.chmod(0o700)
        self.output = self.parent / 'synthetic-initial'
        self.entropy = Mock(side_effect=[b'd' * 32, b'b' * 32])
        self.driver = initial.InitialPreparation(admission=SyntheticAdmission(),
            entropy_source=self.entropy, clock=lambda: 1001)

    def test_real_safe_write_readback_only_three_files_and_separate_keys(self):
        result = self.driver.run(**inputs(str(self.output)))
        self.assertEqual(result['state'], 'PREPARED_OFFLINE_SYNTHETIC_CANDIDATE')
        self.assertEqual(set(os.listdir(self.output)), p.BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        for file in self.output.iterdir():
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
            self.assertEqual(file.stat().st_uid, os.geteuid())
        config = json.loads((self.output / 'config.json').read_bytes())
        self.assertNotIn('authority_verify_key', config)
        self.assertNotEqual(config['backup_key'], config['keys'][config['active_key']])
        self.assertEqual(p.inspect_bundle(self.output)['production'], 'NOT_INSTALLABLE')

    def test_existing_directory_untouched_without_entropy(self):
        self.output.mkdir(mode=0o700)
        sentinel = self.output / 'sentinel'; sentinel.write_text('untouched')
        self.assertEqual(self.driver.run(**inputs(str(self.output)))['state'], 'NOT_PREPARED')
        self.entropy.assert_not_called()
        self.assertEqual(sentinel.read_text(), 'untouched')

    def test_nonprivate_parent_no_entropy_or_output(self):
        self.parent.chmod(0o755)
        self.assertEqual(self.driver.run(**inputs(str(self.output)))['state'], 'NOT_PREPARED')
        self.entropy.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_symlink_output_no_entropy_or_overwrite(self):
        self.output.symlink_to(self.parent / 'absent')
        self.assertEqual(self.driver.run(**inputs(str(self.output)))['state'], 'NOT_PREPARED')
        self.entropy.assert_not_called()
        self.assertTrue(self.output.is_symlink())

    def test_collision_during_publication_preserves_competitor(self):
        original = p._rename_noreplace
        def collision(fd, source, destination):
            self.output.mkdir(mode=0o700)
            (self.output / 'sentinel').write_text('competitor')
            return original(fd, source, destination)
        with patch.object(p, '_rename_noreplace', side_effect=collision):
            self.assertEqual(self.driver.run(**inputs(str(self.output)))['state'], 'UNKNOWN')
        self.assertEqual((self.output / 'sentinel').read_text(), 'competitor')

    def test_post_publish_interruption_preserves_bundle_and_never_retries(self):
        original = p.write_bundle
        def interrupted(*args):
            original(*args)
            raise KeyboardInterrupt(SENTINEL)
        with patch.object(p, 'write_bundle', side_effect=interrupted) as writer:
            self.assertEqual(self.driver.run(**inputs(str(self.output)))['state'], 'UNKNOWN')
            before = {f.name: f.read_bytes() for f in self.output.iterdir()}
            self.assertEqual(self.driver.run(**inputs(str(self.output)))['error'], 'ATTEMPT_ALREADY_USED')
            writer.assert_called_once()
        self.assertEqual(before, {f.name: f.read_bytes() for f in self.output.iterdir()})


if __name__ == '__main__':
    unittest.main()
