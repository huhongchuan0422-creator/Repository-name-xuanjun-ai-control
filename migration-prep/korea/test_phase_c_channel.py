"""Synthetic filesystem/root grant model, never a Korea sudo grant or C install."""
import copy
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import concurrent.futures
import unittest
from unittest import mock

from korea import phase_c_channel as channel
from korea import grant_phase_c_channel as grant

NOW = 1792144000


class GrantModel(grant.Context):
    def __init__(self, root):
        self.root = root
        self.record = None
        self.validations = []
        self.fail_validation = 0

    def path(self, value):
        return self.root / value.lstrip('/')

    def identity(self):
        pass  # Explicitly modeled, not a production account or host claim.

    def now(self):
        return NOW

    def current(self, comment_id):
        return self.record

    def visudo(self, path=None):
        self.validations.append(str(path))
        if self.fail_validation == len(self.validations):
            raise ValueError('SYNTHETIC_VISUDO_FAILURE')


class ChannelModel(channel.Context):
    def __init__(self, root):
        self.root = root
        self.executed = []

    def path(self, value):
        return self.root / value.lstrip('/')

    def identity(self):
        pass

    def execute(self, args):
        self.executed.append(args)
        raise SystemExit(0)  # Replaces exec only in the synthetic test context.


@unittest.skipUnless(os.geteuid() == 0, 'Root-owned synthetic fixtures require Hosted root')
class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/root', prefix='pr99-channel-test-')
        self.root = Path(self.tmp.name)
        self.model = GrantModel(self.root)
        for raw in ('/usr/local/libexec', '/usr/local/sbin', '/etc/sudoers.d', '/var/lib'):
            self.model.path(raw).mkdir(mode=0o755, parents=True, exist_ok=True)
        self.source = Path(channel.__file__).read_bytes()
        self.dispatcher = self.root / 'dispatcher.py'
        self.dispatcher.write_bytes(self.source)
        self.installer = Path(grant.__file__).read_bytes()
        self.a = dict(schema_version=1, decision='APPROVED_WITH_EXACT_PRECONDITIONS',
            action=grant.ACTION, host=grant.HOST, max_attempts=1, approval_comment_id=123,
            dispatcher_sha256=grant.DISPATCHER_SHA, installer_sha256=grant.sha(self.installer),
            wrapper_sha256=grant.sha(grant.WRAPPER_BYTES), sudoers_sha256=grant.sha(grant.POLICY_BYTES),
            runner='githubrunner', runner_uid=1001, arbitrary_root_commands_allowed=False,
            phase_c_install_allowed=False, service_actions_allowed=False,
            network_changes_allowed=False, credentials_allowed=False, database_export_allowed=False,
            writer_allowed=False, source_commit='a' * 40, issued_at=NOW-1, expires_at=NOW+3600)
        self.set_record()

    def tearDown(self):
        self.tmp.cleanup()

    def set_record(self):
        body = 'SYNTHETIC TEST ONLY\n<!-- '+grant.MARKER+'\n'+json.dumps(self.a)+'\n'+grant.MARKER+' -->'
        self.model.record = dict(id=123, body=body,
            issue_url='https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/issues/99')
        self.body_sha = grant.sha(body.encode())

    def execute_grant(self):
        return grant.grant(self.dispatcher, 123, self.body_sha, self.installer, self.model)

    def test_dispatcher_digest_and_frozen_handoff_pin_match_actual_source(self):
        self.assertEqual(grant.sha(self.source), grant.DISPATCHER_SHA)
        helper = Path(__file__).parent / 'phase_c/root_handoff.py'
        self.assertEqual(channel.digest(helper.read_bytes()), channel.HANDOFF_SHA)
        self.assertEqual(channel.WRAPPER_BYTES, grant.WRAPPER_BYTES)
        self.assertEqual(channel.POLICY_BYTES, grant.POLICY_BYTES)

    def test_wrong_action_expiry_version_host_scope_or_multiple_use_rejected_before_claim(self):
        original = copy.deepcopy(self.a)
        for change in (dict(action='OLD_PHASE_B'), dict(host='other'), dict(max_attempts=2),
                       dict(expires_at=NOW), dict(source_commit='invalid'),
                       dict(dispatcher_sha256='0'*64), dict(installer_sha256='0'*64),
                       dict(wrapper_sha256='0'*64), dict(sudoers_sha256='0'*64),
                       dict(phase_c_install_allowed=True), dict(runner_uid=True)):
            self.a = dict(original, **change)
            self.set_record()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.execute_grant()
            self.assertFalse(self.model.path(grant.WORK).exists())
        self.a = original

    def test_changed_body_or_wrong_dispatcher_does_not_write(self):
        self.model.record['body'] += '\nedited'
        with self.assertRaises(ValueError):
            self.execute_grant()
        self.set_record()
        self.dispatcher.write_bytes(b'unreviewed')
        with self.assertRaises(ValueError):
            self.execute_grant()
        self.assertFalse(self.model.path(grant.WORK).exists())

    def test_other_pr_or_revoked_second_read_has_no_claim(self):
        self.model.record['issue_url'] = 'https://api.github.com/repos/example/project/issues/99'
        with self.assertRaises(ValueError):
            self.execute_grant()
        self.set_record()
        changed = dict(self.model.record, body=self.model.record['body']+' edited')
        with mock.patch.object(self.model, 'current', side_effect=[self.model.record, changed]):
            with self.assertRaises(ValueError):
                self.execute_grant()
        self.assertFalse(self.model.path(grant.WORK).exists())

    def test_duplicate_json_and_nonfinite_constants_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(ValueError):
                grant.parse(raw)

    def test_existing_grant_or_symlink_source_is_not_overwritten(self):
        self.model.path(grant.PROGRAM).write_bytes(b'old source')
        with self.assertRaises(ValueError):
            self.execute_grant()
        self.assertEqual(self.model.path(grant.PROGRAM).read_bytes(), b'old source')
        self.model.path(grant.PROGRAM).unlink()
        target = self.dispatcher.with_suffix('.saved')
        self.dispatcher.rename(target)
        self.dispatcher.symlink_to(target)
        with self.assertRaises(OSError):
            self.execute_grant()

    def test_grant_umask077_exact_modes_only_two_commands_no_c_execution(self):
        old_umask = os.umask(0o077)
        try:
            result = self.execute_grant()
        finally:
            os.umask(old_umask)
        self.assertEqual(result['status'], 'FIXED_CHANNEL_READY_NO_PHASE_C_EXECUTION')
        self.assertFalse(result['phase_c_install_called'])
        for raw, mode in ((grant.PROGRAM, 0o444), (grant.WRAPPER, 0o755), (grant.POLICY, 0o440)):
            self.assertEqual(stat.S_IMODE(self.model.path(raw).stat().st_mode), mode)
        self.assertEqual(len(self.model.validations), 3)
        policy = self.model.path(grant.POLICY).read_text()
        self.assertEqual(len(policy.splitlines()), 2)
        self.assertNotIn('*', policy)
        self.assertNotIn('ALL=(ALL)', policy)
        self.assertEqual(self.model.path(grant.WRAPPER).read_bytes(), channel.WRAPPER_BYTES)
        with self.assertRaises(ValueError):
            self.execute_grant()

    def test_post_install_sudoers_failure_preserves_claim_and_files_without_retry(self):
        self.model.fail_validation = 3
        with self.assertRaises(ValueError):
            self.execute_grant()
        work = self.model.path(grant.WORK)
        self.assertTrue((work/'consumed-approval.json').exists())
        self.assertEqual(json.loads((work/'failure.json').read_text())['status'], 'HOLD_PRESERVE_EVIDENCE')
        self.assertTrue(self.model.path(grant.POLICY).is_file())
        with self.assertRaises(ValueError):
            self.execute_grant()

    def test_concurrent_grants_only_one_permanent_claim_and_success(self):
        def attempt(_):
            try:
                return self.execute_grant()['status']
            except (ValueError, FileExistsError):
                return 'REJECTED'
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(results.count('FIXED_CHANNEL_READY_NO_PHASE_C_EXECUTION'), 1)
        self.assertEqual(results.count('REJECTED'), 3)
        self.assertTrue((self.model.path(grant.WORK)/'consumed-approval.json').is_file())

    def test_wrong_extra_or_shell_arguments_rejected_before_identity_and_reads(self):
        model = ChannelModel(self.root)
        for args in ([], ['bash'], ['inspect', '--anything'], ['install', '/tmp/untrusted'], ['install;id']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                channel.main(args, model)
        self.assertEqual(model.executed, [])

    def test_inspect_only_reads_explicit_public_keys_not_private_pin_or_plan(self):
        model = ChannelModel(self.root)
        p = model.path('/etc/xuanjun-pr99-release/phase-c-offline-install-admission.json')
        p.parent.mkdir(mode=0o700, parents=True)
        p.write_bytes(b'not JSON; never read by inspect')
        p.chmod(0o600)
        private = p.parent/'phase-c-inputs'
        private.mkdir(mode=0o700)
        (private/'install-plan.json').write_bytes(b'PRIVATE PLAN MUST NOT BE READ')
        with mock.patch.object(channel, 'read', side_effect=FileNotFoundError) as read:
            result = channel.main(['inspect'], model)
        self.assertEqual(read.call_count, 3)
        self.assertTrue(all(str(x.args[0]).endswith('.pem') for x in read.call_args_list))
        self.assertTrue(result['inputs']['install_admission']['present'])
        self.assertFalse(result['database_read'])
        self.assertEqual(model.executed, [])

    def test_install_hash_failure_never_executes_or_consumes_existing_c_permit(self):
        model = ChannelModel(self.root)
        root = model.path(channel.INPUT)
        root.mkdir(mode=0o700, parents=True)
        root.chmod(0o700)
        helper = root/'root_handoff.py'
        helper.write_bytes(b'tampered')
        helper.chmod(0o400)
        with self.assertRaisesRegex(ValueError, 'FROZEN_HANDOFF_HASH'):
            channel.main(['install'], model)
        self.assertEqual(model.executed, [])

    def test_install_execs_only_fixed_python_frozen_handoff_and_fixed_inputs(self):
        model = ChannelModel(self.root)
        root = model.path(channel.INPUT)
        root.mkdir(mode=0o700, parents=True)
        root.chmod(0o700)
        helper = (Path(__file__).parent/'phase_c/root_handoff.py').read_bytes()
        payloads = {'root_handoff.py': helper, 'review.tar.gz': b'synthetic archive', 'install-plan.json': b'{}'}
        for name, raw in payloads.items():
            (root/name).write_bytes(raw)
            (root/name).chmod(0o400)
        with mock.patch.object(channel, 'ARCHIVE_SHA', channel.digest(b'synthetic archive')):
            with self.assertRaises(SystemExit):
                channel.main(['install'], model)
        args = model.executed[0]
        self.assertEqual(args[:4], ['/usr/bin/python3.11', '-I', '-B', '-u'])
        self.assertEqual(args[4:], [str(root/'root_handoff.py'), '--archive', str(root/'review.tar.gz'),
                                   '--plan', str(root/'install-plan.json')])

    def test_symlink_group_writable_hardlink_and_oversized_inputs_rejected(self):
        p = self.root/'regular'
        p.write_bytes(b'public')
        p.chmod(0o400)
        self.assertEqual(channel.read(p, 10), b'public')
        p.chmod(0o660)
        with self.assertRaises(ValueError):
            channel.read(p, 10)
        p.chmod(0o400)
        with self.assertRaises(ValueError):
            channel.read(p, 2)
        link = self.root/'link'
        link.symlink_to(p)
        with self.assertRaises(ValueError):
            channel.read(link, 10)
        link.unlink()
        os.link(p, link)
        with self.assertRaises(ValueError):
            channel.read(p, 10)

    def test_production_wrong_host_uid_or_environment_rejected(self):
        with mock.patch.object(os, 'geteuid', return_value=1001), self.assertRaises(ValueError):
            channel.Context().identity()
        with mock.patch.object(os, 'uname', return_value=mock.Mock(nodename='other')), self.assertRaises(ValueError):
            channel.Context().identity()

    def test_wrapper_shell_and_actual_sudoers_parser_when_available(self):
        wrapper = self.root/'wrapper'
        wrapper.write_bytes(channel.WRAPPER_BYTES)
        subprocess.run(['/bin/sh', '-n', str(wrapper)], check=True)
        parser = shutil.which('visudo')
        if parser:
            policy = self.root/'policy'
            policy.write_bytes(channel.POLICY_BYTES)
            policy.chmod(0o440)
            r = subprocess.run([parser, '-cf', str(policy)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout+r.stderr)


if __name__ == '__main__':
    unittest.main()
