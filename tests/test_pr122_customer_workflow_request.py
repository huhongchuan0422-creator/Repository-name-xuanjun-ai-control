"""Offline request and original-CLI routing regressions.

Fixture evidence is synthetic and never establishes production acceptance.
Every privileged operation, authority lookup and command is mocked. File-reader
tests use disposable local files; no protected target-host path is accessed.
"""
import copy
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from scripts import pr122_customer_release as release
from scripts import pr122_customer_workflow as workflow
from scripts import pr122_customer_workflow_request as request
from scripts import pr122_customer_workflow_operations as operations
from scripts import pr122_customer_runtime as runtime
from scripts import pr122_customer_resume as resume
from scripts import pr122_customer_attempts as attempts
from scripts.pr122_account_admission import approved_account_prepare as account
from scripts.pr122_customer_core import Denied, canonical, digest


def fixture():
    """Shape-correct invented observations, not a claim about the target host."""
    root = Path(release.__file__).resolve().parent.parent
    names = set(request.IMPLEMENTATIONS.values()) | {
        'scripts/' + name for name in (
            'pr122_customer_workflow_request.py', 'pr122_customer_workflow.py',
            'pr122_customer_workflow_operations.py', 'pr122_customer_preparation.py',
            'pr122_customer_runtime_stage.py', 'pr122_customer_workflow_apply.py',
            'pr122_customer_resume.py', 'pr122_customer_attempts.py',
            'pr122_customer_review.py', 'pr122_customer_profile.py')}
    files = {name: (root / name).read_bytes() for name in sorted(names)}
    manifest = {'source_commit': 'a' * 40, 'source_tree': 'b' * 40,
                'files': [{'path': name, 'size': len(raw), 'sha256': digest(raw)}
                          for name, raw in files.items()]}
    raw = canonical(manifest)
    static = {key: digest(('fixture ' + key).encode())
              for key in request.STATIC_FIELDS if key.endswith('_sha256')}
    static.update(source_commit=manifest['source_commit'], source_tree=manifest['source_tree'],
                  state='READONLY_PLAN', transaction=release.TXN, production_changes=0,
                  main_current='/offline/approved-current', manifest_sha256=digest(raw),
                  scope_sha256=digest(canonical(manifest['files'])),
                  nginx={'master': 'offline-master-identity',
                         'files': {'/offline/nginx.conf': digest(b'fixture nginx')}})
    template = {'schema': 1, 'host': runtime.FIXED_HOST,
                'source_commit': manifest['source_commit'],
                'runtime_module_sha256': digest(files[request.IMPLEMENTATIONS['RUNTIME']]),
                'wheel_directory': '/offline/reviewed-wheels',
                'interpreter_sha256': runtime.INTERPRETER_SHA256,
                'stdlib_trees': {'/usr/lib/python3.11': {'os.py': digest(b'fixture stdlib')}},
                'native_files': {'/usr/lib64/fixture-native.so': digest(b'fixture native')},
                'abi': {'python': '3.11', 'machine': 'x86_64', 'glibc_min': '2.34'},
                'expected_venv_tree': {
                    'venv/bin/python': {'kind': 'file', 'mode': 0o755,
                                        'sha256': runtime.INTERPRETER_SHA256},
                    'venv/pyvenv.cfg': {'kind': 'file', 'mode': 0o644,
                                      'sha256': digest(b'fixture venv config')}},
                'account_uid': None, 'account_gid': None}
    stages = {
        'PROBE': {'receipt_sha256': digest(b'original read-only probe')},
        'ACCOUNT': {'account': account.ACCOUNT,
                    'argv_sha256': digest(canonical(list(account.PROPOSED_ARGV))),
                    'platform_sha256': digest(b'fixture account platform')},
        'RUNTIME': {'runtime_template': template,
                    'account_binding': 'VERIFIED_ACCOUNT_CHECKPOINT'},
        'POLICY_RESTORE': {'transaction': 'readonly-bootstrap-20261017',
                           'plan_sha256': digest(b'fixture bootstrap plan'),
                           'old_wrapper_sha256': digest(b'fixture original wrapper'),
                           'old_policy_sha256': digest(b'fixture original policy')},
        'CHANNEL_REBIND': {'plan_sha256': digest(b'fixture channel plan'),
                           'zip_sha256': digest(b'fixture reviewed zip')},
        'CUSTOMER_APPLY': {'static_plan': copy.deepcopy(static)},
    }
    artifact = {key: static[key] for key in (
        'source_commit', 'source_tree', 'manifest_sha256', 'artifact_tar_sha256')}
    artifact.update(artifact_zip_sha256=stages['CHANNEL_REBIND']['zip_sha256'],
                    artifact_id=123, ci_run_id=456)
    adoption = {stage: None for stage in workflow.STAGES}
    adoption['PROBE'] = stages['PROBE']['receipt_sha256']
    observations = {'static_plan': static, 'inputs': {'schema': 1, 'stages': stages},
                    'artifact': artifact, 'adopt_receipts': adoption,
                    'recovery_actions': {stage: sorted(workflow.RECOVERY[stage])
                                         for stage in workflow.STAGES}}
    return manifest, raw, files, observations


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.commands = self.stack.enter_context(patch.object(
            release.subprocess, 'run', side_effect=AssertionError('Actual commands forbidden')))
        self.stack.enter_context(patch.object(release.os, 'system',
            side_effect=AssertionError('Actual shell forbidden')))
        self.stack.enter_context(patch.object(release, 'run',
            side_effect=AssertionError('Actual release command forbidden')))
        self.stack.enter_context(patch.object(release, 'github',
            side_effect=AssertionError('Actual GitHub access forbidden')))
        self.manifest, self.raw, self.files, self.observations = fixture()

    def build(self):
        return request.make_request(self.manifest, self.raw, self.observations)

    def rebind_input(self, plan, inputs, stage):
        row = next(row for row in plan['workflow_contract']['stages'] if row['stage'] == stage)
        row['input_sha256'] = digest(canonical(inputs['stages'][stage]))


class RequestTests(OfflineCase):
    def test_missing_all_inputs_is_explicit_nonexecutable_without_candidates(self):
        result = request.make_request(self.manifest, self.raw, {})
        self.assertEqual(result['state'], 'NOT_EXECUTABLE')
        self.assertEqual(result['permission'], 'NOT_GRANTED')
        self.assertEqual(result['max_actual_attempts_requested'], 5)
        self.assertEqual(set(result['missing_inputs']), set(self.observations))
        for key in ('plan_candidate', 'inputs_candidate', 'artifact_candidate', 'workflow_contract_sha256'):
            self.assertIsNone(result[key])

    def test_each_missing_top_level_fact_stays_unknown_without_fabricated_values(self):
        for key in self.observations:
            with self.subTest(key=key):
                values = copy.deepcopy(self.observations)
                del values[key]
                result = request.make_request(self.manifest, self.raw, values)
                self.assertEqual(result['missing_inputs'], [key])
                self.assertIsNone(result['plan_candidate'])

    def test_each_missing_stage_reports_its_exact_path(self):
        for stage in workflow.STAGES:
            with self.subTest(stage=stage):
                values = copy.deepcopy(self.observations)
                values['inputs']['stages'][stage] = None
                result = request.make_request(self.manifest, self.raw, values)
                self.assertEqual(result['missing_inputs'], ['inputs.stages.' + stage])
                self.assertIsNone(result['plan_candidate'])

    def test_complete_request_remains_nonexecutable_and_binds_exact_six_stages(self):
        result = self.build()
        self.assertEqual((result['state'], result['permission']), ('NOT_EXECUTABLE', 'NOT_GRANTED'))
        self.assertEqual(result['missing_inputs'], [])
        plan = result['plan_candidate']
        rows = plan['workflow_contract']['stages']
        self.assertEqual([row['stage'] for row in rows], list(workflow.STAGES))
        for row in rows:
            stage = row['stage']
            self.assertEqual(row['input_sha256'], digest(canonical(self.observations['inputs']['stages'][stage])))
            self.assertEqual(row['implementation_sha256'], digest(self.files[request.IMPLEMENTATIONS[stage]]))
        self.assertEqual(result['workflow_contract_sha256'], digest(canonical(plan['workflow_contract'])))
        self.assertTrue(request.validate_inputs(plan, result['inputs_candidate'], self.manifest, self.raw))

    def test_request_never_contains_approval_signature_or_executable_command(self):
        result = self.build()
        banned = {'approval', 'approval_comment', 'review_comment', 'signature', 'command',
                  'commands', 'operations', 'module', 'decision', 'issued_unix', 'expires_unix'}
        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(banned.intersection(value), value)
                for child in value.values(): inspect(child)
            elif isinstance(value, list):
                for child in value: inspect(child)
        inspect(result)
        self.assertNotIn('INSTALL_APPROVED', json.dumps(result))
        self.assertNotIn('AUDIT_PASS', json.dumps(result))

    def test_request_does_not_mutate_or_alias_supplied_observations(self):
        before = copy.deepcopy(self.observations)
        result = self.build()
        self.assertEqual(self.observations, before)
        result['plan_candidate']['workflow_contract']['stages'][0]['recovery_actions'].clear()
        result['inputs_candidate']['stages']['CUSTOMER_APPLY']['static_plan'].clear()
        result['artifact_candidate'].clear()
        self.assertEqual(self.observations, before)

    def test_requested_prior_probe_and_account_pins_are_preserved(self):
        self.observations['adopt_receipts']['ACCOUNT'] = digest(b'original successful account receipt')
        rows = self.build()['plan_candidate']['workflow_contract']['stages']
        self.assertEqual(rows[0]['adopt_receipt_sha256'], self.observations['inputs']['stages']['PROBE']['receipt_sha256'])
        self.assertEqual(rows[1]['adopt_receipt_sha256'], self.observations['adopt_receipts']['ACCOUNT'])

    def test_probe_must_have_matching_exact_adoption_pin(self):
        for value in (None, 'f' * 64):
            with self.subTest(value=value):
                self.observations['adopt_receipts']['PROBE'] = value
                with self.assertRaisesRegex(Denied, 'REQUEST_EXISTING_PROBE_REQUIRED'): self.build()

    def test_extra_observation_fields_cannot_inject_authority_or_adapters(self):
        for key in ('approval', 'command', 'module', 'operations', 'signature'):
            with self.subTest(key=key):
                values = copy.deepcopy(self.observations)
                values[key] = 'untrusted'
                with self.assertRaisesRegex(Denied, 'REQUEST_OBSERVATION_SCHEMA'):
                    request.make_request(self.manifest, self.raw, values)

    def test_stage_recovery_actions_cannot_expand_scope(self):
        for actions in (['RUN_COMMAND'], ['RECONCILE_ACCOUNT', 'RECONCILE_ACCOUNT']):
            with self.subTest(actions=actions):
                self.observations['recovery_actions']['ACCOUNT'] = actions
                with self.assertRaisesRegex(Denied, 'WORKFLOW_RECOVERY_SCOPE'): self.build()

    def test_unknown_or_missing_stages_fail_closed(self):
        for key in ('inputs', 'adopt_receipts', 'recovery_actions'):
            with self.subTest(key=key):
                values = copy.deepcopy(self.observations)
                target = values[key]['stages'] if key == 'inputs' else values[key]
                target['ARBITRARY_STAGE'] = target.pop('ACCOUNT')
                with self.assertRaises(Denied):
                    request.make_request(self.manifest, self.raw, values)

    def test_artifact_requires_exact_source_tree_manifest_tar_zip_and_positive_ids(self):
        for key in request.ARTIFACT_FIELDS:
            with self.subTest(key=key):
                values = copy.deepcopy(self.observations)
                values['artifact'][key] = 0 if key in ('artifact_id', 'ci_run_id') else 'f' * (40 if key in ('source_commit', 'source_tree') else 64)
                with self.assertRaisesRegex(Denied, 'REQUEST_ARTIFACT_BINDING'):
                    request.make_request(self.manifest, self.raw, values)

    def test_artifact_boolean_ids_are_not_integer_ids(self):
        for key in ('artifact_id', 'ci_run_id'):
            with self.subTest(key=key):
                self.observations['artifact'][key] = True
                with self.assertRaisesRegex(Denied, 'REQUEST_ARTIFACT_BINDING'): self.build()
                self.observations['artifact'][key] = 123

    def test_static_plan_cannot_smuggle_dynamic_identity_or_execution_fields(self):
        for key in ('account_uid', 'account_gid', 'isolated_python', 'command'):
            with self.subTest(key=key):
                values = copy.deepcopy(self.observations)
                values['static_plan'][key] = 1001
                with self.assertRaisesRegex(Denied, 'REQUEST_STATIC_PLAN_FIELDS'):
                    request.make_request(self.manifest, self.raw, values)

    def test_changed_stage_bytes_or_implementation_pin_fail_exact_validation(self):
        result = self.build()
        for stage in workflow.STAGES:
            for changed in ('input', 'implementation'):
                with self.subTest(stage=stage, changed=changed):
                    plan, inputs = copy.deepcopy(result['plan_candidate']), copy.deepcopy(result['inputs_candidate'])
                    if changed == 'input': inputs['stages'][stage]['unreviewed'] = True
                    else:
                        next(row for row in plan['workflow_contract']['stages'] if row['stage'] == stage)['implementation_sha256'] = 'f' * 64
                    with self.assertRaisesRegex(Denied, 'REQUEST_STAGE_BINDING'):
                        request.validate_inputs(plan, inputs, self.manifest, self.raw)

    def test_rehashed_account_override_still_fails_fixed_account_contract(self):
        for key, value in (('account', 'root'), ('argv_sha256', 'f' * 64), ('platform_sha256', 'invalid')):
            with self.subTest(key=key):
                values = copy.deepcopy(self.observations)
                values['inputs']['stages']['ACCOUNT'][key] = value
                with self.assertRaisesRegex(Denied, 'REQUEST_FIXED_ACCOUNT'):
                    request.make_request(self.manifest, self.raw, values)

    def test_runtime_identity_is_derived_only_from_verified_account_checkpoint(self):
        for key, value in (('account_uid', 0), ('account_gid', 1001), ('host', 'foreign'),
                           ('interpreter_sha256', 'f' * 64), ('source_commit', 'f' * 40),
                           ('wheel_directory', '/offline/../unreviewed')):
            with self.subTest(key=key):
                values = copy.deepcopy(self.observations)
                values['inputs']['stages']['RUNTIME']['runtime_template'][key] = value
                with self.assertRaisesRegex(Denied, 'REQUEST_RUNTIME_TEMPLATE'):
                    request.make_request(self.manifest, self.raw, values)

    def test_runtime_closure_facts_cannot_be_omitted(self):
        for key in ('stdlib_trees', 'native_files', 'expected_venv_tree'):
            with self.subTest(key=key):
                values = copy.deepcopy(self.observations)
                values['inputs']['stages']['RUNTIME']['runtime_template'][key] = {}
                result = request.make_request(self.manifest, self.raw, values)
                self.assertEqual(result['missing_inputs'], ['inputs.stages.RUNTIME.runtime_template.' + key])
                self.assertIsNone(result['plan_candidate'])
                self.assertEqual(result['state'], 'NOT_EXECUTABLE')

    def test_nested_unknown_facts_are_reported_without_a_plan_candidate(self):
        self.observations['inputs']['stages']['ACCOUNT']['platform_sha256'] = 'UNKNOWN'
        result = self.build()
        self.assertEqual(result['missing_inputs'], ['inputs.stages.ACCOUNT.platform_sha256'])
        self.assertEqual(result['permission'], 'NOT_GRANTED')
        self.assertIsNone(result['plan_candidate'])

    def test_runtime_closure_rejects_foreign_paths_startup_hooks_and_unsafe_modes(self):
        mutations = (
            lambda t: t.update(stdlib_trees={'/foreign': {'os.py': 'a' * 64}}),
            lambda t: t.update(native_files={'/usr/lib/../foreign.so': 'a' * 64}),
            lambda t: t['stdlib_trees']['/usr/lib/python3.11'].update({'../escape': 'a' * 64}),
            lambda t: t['expected_venv_tree'].update({'venv/lib/startup.pth': {'kind': 'file', 'mode': 0o644, 'sha256': 'a' * 64}}),
            lambda t: t['expected_venv_tree']['venv/bin/python'].update(mode=0o777),
            lambda t: t['expected_venv_tree'].update({'venv/bin/python3': {'kind': 'symlink', 'target': '/foreign'}}),
        )
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                values = copy.deepcopy(self.observations)
                mutate(values['inputs']['stages']['RUNTIME']['runtime_template'])
                with self.assertRaises((Denied, runtime.Denied)):
                    request.make_request(self.manifest, self.raw, values)

    def test_customer_static_plan_must_match_whole_plan_exactly(self):
        self.observations['inputs']['stages']['CUSTOMER_APPLY']['static_plan']['main_current'] = '/foreign'
        with self.assertRaisesRegex(Denied, 'REQUEST_CUSTOMER_STATIC_PLAN'): self.build()

    def test_manifest_source_and_scope_drift_are_rejected(self):
        for key in ('source_commit', 'source_tree', 'manifest_sha256', 'scope_sha256'):
            with self.subTest(key=key):
                values = copy.deepcopy(self.observations)
                values['static_plan'][key] = 'f' * (40 if key in ('source_commit', 'source_tree') else 64)
                with self.assertRaisesRegex(Denied, 'REQUEST_SOURCE_BINDING'):
                    request.make_request(self.manifest, self.raw, values)

    def test_manifest_missing_fixed_implementation_fails_before_request(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['files'] = [row for row in manifest['files'] if row['path'] != request.IMPLEMENTATIONS['ACCOUNT']]
        with self.assertRaisesRegex(Denied, 'REQUEST_IMPLEMENTATION_CLOSURE'):
            request.make_request(manifest, canonical(manifest), {})

    def test_manifest_rejects_duplicates_path_escape_and_invalid_member_types(self):
        for name in ('/absolute', '../escape', 'scripts/./alias', 'scripts//empty', 'scripts/../escape'):
            with self.subTest(path=name):
                manifest = copy.deepcopy(self.manifest)
                manifest['files'][0]['path'] = name
                with self.assertRaisesRegex(Denied, 'REQUEST_MANIFEST_MEMBER'):
                    request.source_index(manifest, canonical(manifest))
        manifest = copy.deepcopy(self.manifest)
        manifest['files'].append(copy.deepcopy(manifest['files'][0]))
        with self.assertRaisesRegex(Denied, 'REQUEST_MANIFEST_MEMBER'):
            request.source_index(manifest, canonical(manifest))


class LocalReaderTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_json_rejects_duplicate_keys_nonfinite_and_invalid_utf8(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff', b'{'):
            with self.subTest(raw=raw), self.assertRaises(Denied): request.strict_json(raw)

    def test_json_read_is_bounded_and_regular_without_any_command(self):
        target = self.root / 'observations.json'
        target.write_bytes(b'{"fixture":true}')
        self.assertEqual(request.read_json(target), {'fixture': True})
        self.commands.assert_not_called()

    def test_json_rejects_oversized_bytes_and_hardlinks(self):
        with patch.object(request, 'MAX_JSON', 3), self.assertRaisesRegex(Denied, 'REQUEST_JSON_SIZE'):
            request.strict_json(b'null')
        target = self.root / 'data.json'
        target.write_bytes(b'{}')
        os.link(target, self.root / 'duplicate.json')
        with self.assertRaisesRegex(Denied, 'REQUEST_FILE'): request.read_json(target)

    def test_json_never_follows_final_symlink(self):
        target = self.root / 'data.json'
        target.write_bytes(b'{}')
        alias = self.root / 'alias.json'
        alias.symlink_to(target)
        with self.assertRaises((OSError, Denied)): request.read_json(alias)

    def test_json_detects_named_inode_change(self):
        target = self.root / 'data.json'
        target.write_bytes(b'{}')
        before = target.stat()
        changed = SimpleNamespace(st_dev=before.st_dev, st_ino=before.st_ino + 1,
                                  st_size=before.st_size, st_mtime_ns=before.st_mtime_ns,
                                  st_ctime_ns=before.st_ctime_ns)
        with patch.object(request.os, 'lstat', return_value=changed), self.assertRaisesRegex(Denied, 'REQUEST_FILE_CHANGED'):
            request.read_json(target)

    def test_json_open_is_nonblocking_before_type_check(self):
        # Never open an actual FIFO: verify the guard before any filesystem call.
        sentinel = RuntimeError('open intercepted before touching target')
        with patch.object(request.os, 'open', side_effect=sentinel) as opened:
            with self.assertRaisesRegex(RuntimeError, 'open intercepted'):
                request.read_json(self.root / 'could-be-fifo')
        self.assertTrue(opened.call_args.args[1] & os.O_NONBLOCK)

    def test_protected_json_rejects_unowned_or_public_file_before_parsing(self):
        target = self.root / 'data.json'
        target.write_bytes(b'{}')
        info = target.stat()
        for uid, mode in ((1234, stat.S_IFREG | 0o600), (0, stat.S_IFREG | 0o644), (0, stat.S_IFREG | 0o400)):
            fake = SimpleNamespace(st_mode=mode, st_uid=uid, st_nlink=1, st_size=info.st_size)
            with self.subTest(uid=uid, mode=mode), patch.object(request.os, 'fstat', return_value=fake), \
                 patch.object(attempts, 'protected_directory'):
                with self.assertRaisesRegex(Denied, 'REQUEST_PROTECTED_MODE'):
                    request.read_json(target, protected=True)

    def test_protected_parent_denial_stops_before_open(self):
        target = self.root / 'data.json'
        with patch.object(attempts, 'protected_directory', side_effect=Denied('HOLD:ATTEMPT_DIRECTORY_TRUST')) as parents, \
             patch.object(request.os, 'open') as opened:
            with self.assertRaisesRegex(Denied, 'ATTEMPT_DIRECTORY_TRUST'):
                request.read_json(target, protected=True)
        parents.assert_called_once_with(target.parent)
        opened.assert_not_called()

    def test_protected_module_bytes_use_code_mode_without_weakening_json_mode(self):
        target = self.root / 'module.py'
        target.write_bytes(b'# inert fixture\n')
        target.chmod(0o755)
        actual_fstat = os.fstat
        def fake_root(fd):
            info = actual_fstat(fd)
            return SimpleNamespace(**{key: (0 if key == 'st_uid' else getattr(info, key)) for key in
                ('st_mode', 'st_uid', 'st_nlink', 'st_size', 'st_dev', 'st_ino', 'st_mtime_ns', 'st_ctime_ns')})
        with patch.object(attempts, 'protected_directory'), patch.object(request.os, 'fstat', side_effect=fake_root):
            self.assertEqual(request.read_bytes(target, protected=True, code=True), b'# inert fixture\n')
            with self.assertRaisesRegex(Denied, 'REQUEST_PROTECTED_MODE'):
                request.read_bytes(target, protected=True)
            target.chmod(0o777)
            with self.assertRaisesRegex(Denied, 'REQUEST_PROTECTED_MODE'):
                request.read_bytes(target, protected=True, code=True)

    def populate_source(self):
        for name, raw in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (self.root / 'CUSTOMER_MANIFEST.json').write_bytes(self.raw)

    def test_review_source_validates_bytes_without_executing_candidate_code(self):
        self.files['fixture_never_import.py'] = b'raise AssertionError("must never execute")\n'
        self.manifest['files'].append({'path': 'fixture_never_import.py',
                                      'size': len(self.files['fixture_never_import.py']),
                                      'sha256': digest(self.files['fixture_never_import.py'])})
        self.raw = canonical(self.manifest)
        self.populate_source()
        self.assertEqual(request.read_review_source(self.root), (self.manifest, self.raw))
        self.commands.assert_not_called()

    def test_review_source_byte_drift_is_rejected(self):
        self.populate_source()
        (self.root / request.IMPLEMENTATIONS['ACCOUNT']).write_bytes(b'changed')
        with self.assertRaisesRegex(Denied, 'REQUEST_SOURCE_HASH'): request.read_review_source(self.root)

    def test_review_source_symlink_member_is_rejected(self):
        self.populate_source()
        member = self.root / request.IMPLEMENTATIONS['ACCOUNT']
        member.unlink()
        member.symlink_to(self.root / 'CUSTOMER_MANIFEST.json')
        with self.assertRaisesRegex(Denied, 'REQUEST_SOURCE_FILE'): request.read_review_source(self.root)


class OriginalEntryTests(OfflineCase):
    def setUp(self):
        super().setUp()
        result = self.build()
        self.plan, self.inputs = result['plan_candidate'], result['inputs_candidate']
        self.stack.enter_context(patch.object(release, 'CONFIG', Path('/offline/root-config')))
        self.stack.enter_context(patch.object(release.os, 'getuid', return_value=0))
        self.stack.enter_context(patch.object(release.os, 'geteuid', return_value=0))
        self.stack.enter_context(patch.object(release.os, 'getgid', return_value=0))
        self.stack.enter_context(patch.object(release.os, 'getegid', return_value=0))
        self.stack.enter_context(patch.object(release.os, 'uname', return_value=SimpleNamespace(nodename=runtime.FIXED_HOST)))
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        def read(path, protected=False):
            self.assertTrue(protected)
            if path == release.CONFIG / 'WHOLE_WORKFLOW_PLAN.json': return copy.deepcopy(self.plan)
            if path == release.CONFIG / 'WHOLE_WORKFLOW_INPUTS.json': return copy.deepcopy(self.inputs)
            raise AssertionError('Unexpected protected read: ' + str(path))
        self.reader = self.stack.enter_context(patch.object(request, 'read_json', side_effect=read))
        self.protected = self.stack.enter_context(patch.object(attempts, 'protected_directory'))
        self.module_reader = self.stack.enter_context(patch.object(request, 'read_bytes',
            side_effect=lambda path, **kwargs: Path(path).read_bytes()))
        self.archive = self.stack.enter_context(patch.object(release, 'archive_binding', return_value=self.plan['artifact_tar_sha256']))
        self.source = self.stack.enter_context(patch.object(release, 'source', return_value=(self.manifest, self.raw, self.files)))
        self.apply = self.stack.enter_context(patch.object(release, 'workflow_apply', return_value={'state': 'fixture-only'}))
        self.legacy = self.stack.enter_context(patch.object(release, 'apply', side_effect=AssertionError('Legacy fallback forbidden')))

    def test_fixed_protected_paths_and_original_default_operations_route(self):
        self.assertEqual(release.workflow_entry('/offline/source', 123), {'state': 'fixture-only'})
        self.assertEqual(self.reader.call_args_list, [
            call(release.CONFIG / 'WHOLE_WORKFLOW_PLAN.json', protected=True),
            call(release.CONFIG / 'WHOLE_WORKFLOW_INPUTS.json', protected=True)])
        self.apply.assert_called_once_with('/offline/source', 123, self.plan)
        self.assertNotIn('operations', self.apply.call_args.kwargs)
        self.protected.assert_called_once_with(Path('/offline/source'))
        self.assertEqual(self.module_reader.call_count, 16)
        for observed in self.module_reader.call_args_list:
            self.assertEqual(observed.kwargs, {'protected': True, 'code': True})
        self.legacy.assert_not_called()

    def test_direct_owner_host_and_sudo_caller_are_checked_before_reads(self):
        cases = [('getuid', 1000), ('geteuid', 1000), ('getgid', 1000), ('getegid', 1000),
                 ('host', 'foreign'), ('sudo', '1000')]
        for kind, value in cases:
            with self.subTest(kind=kind), ExitStack() as stack:
                if kind in ('getuid', 'geteuid', 'getgid', 'getegid'): stack.enter_context(patch.object(release.os, kind, return_value=value))
                elif kind == 'host': stack.enter_context(patch.object(release.os, 'uname', return_value=SimpleNamespace(nodename=value)))
                else: stack.enter_context(patch.dict(os.environ, SUDO_UID=value))
                with self.assertRaisesRegex(Denied, 'WORKFLOW_DIRECT_OWNER_REQUIRED'):
                    release.workflow_entry('/offline/source', 123)
        self.reader.assert_not_called()
        self.apply.assert_not_called()

    def test_entry_rejects_boolean_negative_comment_and_missing_source(self):
        for folder, comment in (('/offline/source', True), ('/offline/source', 0),
                                ('/offline/source', -1), ('', 123), (None, 123)):
            with self.subTest(folder=folder, comment=comment), self.assertRaisesRegex(Denied, 'WORKFLOW_ENTRY_ARGUMENTS'):
                release.workflow_entry(folder, comment)
        self.reader.assert_not_called()

    def test_missing_either_protected_file_never_falls_back(self):
        original = self.reader.side_effect
        for missing in ('WHOLE_WORKFLOW_PLAN.json', 'WHOLE_WORKFLOW_INPUTS.json'):
            with self.subTest(missing=missing):
                def read(path, protected=False):
                    if path.name == missing: raise FileNotFoundError(str(path))
                    return original(path, protected)
                self.reader.side_effect = read
                with self.assertRaises(FileNotFoundError): release.workflow_entry('/offline/source', 123)
        self.apply.assert_not_called()
        self.legacy.assert_not_called()

    def test_changed_signed_inputs_fail_before_original_apply(self):
        self.inputs['stages']['ACCOUNT']['platform_sha256'] = 'f' * 64
        with self.assertRaisesRegex(Denied, 'REQUEST_STAGE_BINDING'):
            release.workflow_entry('/offline/source', 123)
        self.apply.assert_not_called()

    def test_unprotected_source_directory_stops_before_config_and_gate(self):
        self.protected.side_effect = Denied('HOLD:ATTEMPT_DIRECTORY_TRUST')
        with self.assertRaisesRegex(Denied, 'ATTEMPT_DIRECTORY_TRUST'):
            release.workflow_entry('/offline/source', 123)
        self.reader.assert_not_called()
        self.apply.assert_not_called()

    def test_unprotected_loaded_module_stops_before_original_apply(self):
        self.module_reader.side_effect = Denied('HOLD:REQUEST_PROTECTED_MODE')
        with self.assertRaisesRegex(Denied, 'REQUEST_PROTECTED_MODE'):
            release.workflow_entry('/offline/source', 123)
        self.apply.assert_not_called()

    def test_entry_archive_mismatch_stops_before_original_apply(self):
        self.archive.return_value = 'f' * 64
        with self.assertRaisesRegex(Denied, 'WORKFLOW_ENTRY_ARCHIVE_BINDING'):
            release.workflow_entry('/offline/source', 123)
        self.module_reader.assert_not_called()
        self.apply.assert_not_called()

    def test_each_fixed_entry_dependency_must_match_reviewed_bytes(self):
        names = ('pr122_customer_release.py', 'pr122_customer_workflow_request.py',
                 'pr122_customer_workflow.py', 'pr122_customer_workflow_operations.py',
                 'pr122_customer_preparation.py', 'pr122_customer_runtime_stage.py',
                 'pr122_customer_workflow_apply.py', 'pr122_customer_resume.py',
                 'pr122_customer_attempts.py', 'pr122_customer_review.py',
                 'pr122_customer_runtime.py', 'pr122_customer_channel_upgrade.py',
                 'pr122_account_admission/approved_account_prepare.py',
                 'pr122_account_admission/domestic_bootstrap.py',
                 'pr122_account_admission/readonly_probe.py')
        for name in names:
            path = 'scripts/' + name
            original = self.files[path]
            with self.subTest(name=name):
                self.files[path] = original + b'\n# drift'
                try:
                    with self.assertRaisesRegex(Denied, 'WORKFLOW_ENTRY_SOURCE_DRIFT'):
                        release.workflow_entry('/offline/source', 123)
                finally: self.files[path] = original
        self.apply.assert_not_called()


class OriginalAuthorityRouteTests(OfflineCase):
    def setUp(self):
        super().setUp()
        result = self.build()
        self.plan, self.inputs = result['plan_candidate'], result['inputs_candidate']
        self.approval = {'attempt_policy': workflow.POLICY, 'max_executions': 5,
                         'workflow_contract_sha256': result['workflow_contract_sha256'],
                         'artifact_zip_sha256': self.inputs['stages']['CHANNEL_REBIND']['zip_sha256']}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.lock = Path(self.temp.name) / 'original-transaction.lock'
        self.stack.enter_context(patch.object(release, 'LOCK', self.lock))
        self.stack.enter_context(patch.object(release.os, 'geteuid', return_value=0))
        self.stack.enter_context(patch.object(release.os, 'uname', return_value=SimpleNamespace(nodename=runtime.FIXED_HOST)))
        self.gate = self.stack.enter_context(patch.object(release, 'gate', return_value=self.approval))
        self.config = self.stack.enter_context(patch.object(request, 'read_json', return_value=self.inputs))
        self.source = self.stack.enter_context(patch.object(release, 'source', return_value=(self.manifest, self.raw, self.files)))
        self.archive = self.stack.enter_context(patch.object(release, 'archive_binding', return_value=self.plan['artifact_tar_sha256']))
        self.adapter = self.stack.enter_context(patch.object(operations, 'OriginalOperations'))
        self.coordinator = self.stack.enter_context(patch.object(workflow, 'Coordinator'))
        self.coordinator.return_value.run.return_value = {'state': 'fixture-only'}

    def test_same_original_lock_gate_adapter_and_coordinator_are_used(self):
        import fcntl
        events = []
        self.gate.side_effect = lambda *args: events.append('gate') or self.approval
        self.config.side_effect = lambda *args, **kwargs: events.append('inputs') or self.inputs
        original_flock = fcntl.flock
        def lock(stream, flags):
            events.append('lock')
            return original_flock(stream, flags)
        def construct(*args):
            events.append('coordinator')
            fd = args[-1]
            self.assertEqual(os.fstat(fd).st_ino, self.lock.stat().st_ino)
            self.assertEqual(args[:5], (release, '/offline/source', 123, self.plan, self.approval))
            self.assertIs(args[5], self.adapter.return_value)
            return Mock(run=Mock(return_value={'state': 'fixture-only'}))
        self.coordinator.side_effect = construct
        with patch.object(fcntl, 'flock', side_effect=lock):
            self.assertEqual(release.workflow_apply('/offline/source', 123, self.plan), {'state': 'fixture-only'})
        self.assertEqual(events, ['lock', 'gate', 'inputs', 'coordinator'])
        self.gate.assert_called_once_with(123, self.plan)
        self.config.assert_called_once_with(release.CONFIG / 'WHOLE_WORKFLOW_INPUTS.json', protected=True)
        self.adapter.assert_called_once_with(release, '/offline/source', self.plan, self.inputs)

    def test_original_gate_rejection_never_constructs_adapter_or_ledger(self):
        self.gate.side_effect = Denied('HOLD:INDEPENDENT_REVIEW_SIGNATURE')
        with self.assertRaisesRegex(Denied, 'INDEPENDENT_REVIEW_SIGNATURE'):
            release.workflow_apply('/offline/source', 123, self.plan)
        self.config.assert_not_called()
        self.adapter.assert_not_called()
        self.coordinator.assert_not_called()

    def test_legacy_permission_is_rejected_by_contract_before_adapters(self):
        self.approval['attempt_policy'] = 'CONTROLLED_INSTALL_RESUME_V2'
        with self.assertRaisesRegex(Denied, 'WORKFLOW_EXPLICIT_NEW_PERMISSION'):
            release.workflow_apply('/offline/source', 123, self.plan)
        self.adapter.assert_not_called()
        self.coordinator.assert_not_called()

    def test_default_adapter_zip_mismatch_never_constructs_or_runs_coordinator(self):
        self.approval['artifact_zip_sha256'] = 'f' * 64
        with self.assertRaisesRegex(Denied, 'WORKFLOW_ENTRY_ARTIFACT_BINDING'):
            release.workflow_apply('/offline/source', 123, self.plan)
        self.adapter.assert_not_called()
        self.coordinator.assert_not_called()
        self.coordinator.return_value.run.assert_not_called()

    def test_archive_mismatch_never_constructs_or_runs_coordinator(self):
        self.archive.return_value = 'f' * 64
        with self.assertRaisesRegex(Denied, 'WORKFLOW_ENTRY_ARCHIVE_BINDING'):
            release.workflow_apply('/offline/source', 123, self.plan)
        self.adapter.assert_not_called()
        self.coordinator.assert_not_called()

    def test_default_adapter_revalidates_reopened_inputs_under_original_lock(self):
        self.inputs['stages']['ACCOUNT']['platform_sha256'] = 'f' * 64
        with self.assertRaisesRegex(Denied, 'REQUEST_STAGE_BINDING'):
            release.workflow_apply('/offline/source', 123, self.plan)
        self.gate.assert_called_once_with(123, self.plan)
        self.config.assert_called_once_with(release.CONFIG / 'WHOLE_WORKFLOW_INPUTS.json', protected=True)
        self.adapter.assert_not_called()
        self.coordinator.assert_not_called()

    def test_original_busy_lock_stops_before_gate_or_inputs(self):
        import fcntl
        with patch.object(fcntl, 'flock', side_effect=BlockingIOError('fixture busy lock')):
            with self.assertRaises(BlockingIOError):
                release.workflow_apply('/offline/source', 123, self.plan)
        self.gate.assert_not_called()
        self.config.assert_not_called()
        self.coordinator.assert_not_called()


class CliTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(release.os, 'umask'))
        self.routes = {name: self.stack.enter_context(patch.object(release, name,
                       return_value={'route': name}))
                       for name in ('plan', 'apply', 'rollback', 'workflow_entry', 'workflow_request')}

    def main(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(release.sys, 'argv', ['release'] + args), redirect_stdout(stdout), redirect_stderr(stderr):
            release.main()
        return json.loads(stdout.getvalue())

    def test_workflow_apply_dispatches_only_to_fixed_original_entry(self):
        self.assertEqual(self.main(['workflow-apply', '--source', '/offline/source', '--approval', '123']),
                         {'route': 'workflow_entry'})
        self.routes['workflow_entry'].assert_called_once_with('/offline/source', 123)
        for name in ('plan', 'apply', 'rollback', 'workflow_request'): self.routes[name].assert_not_called()

    def test_workflow_request_dispatches_only_local_observations(self):
        self.assertEqual(self.main(['workflow-request', '--source', '/offline/source', '--observations', '/offline/facts.json']),
                         {'route': 'workflow_request'})
        self.routes['workflow_request'].assert_called_once_with('/offline/source', '/offline/facts.json')

    def test_workflow_request_without_observations_preserves_missing_facts(self):
        self.main(['workflow-request', '--source', '/offline/source'])
        self.routes['workflow_request'].assert_called_once_with('/offline/source', None)

    def test_cli_missing_arguments_and_nonpositive_approval_fail_before_dispatch(self):
        for args in (['workflow-apply'], ['workflow-apply', '--source', '/offline/source'],
                     ['workflow-apply', '--approval', '123'], ['workflow-request'],
                     ['workflow-apply', '--source', '/offline/source', '--approval', '0'],
                     ['workflow-apply', '--source', '/offline/source', '--approval', '-1']):
            with self.subTest(args=args), self.assertRaises(SystemExit) as stopped: self.main(args)
            self.assertEqual(stopped.exception.code, 2)
        for route in self.routes.values(): route.assert_not_called()

    def test_cli_cannot_accept_adapters_commands_modules_or_alternate_plan_inputs(self):
        for flag in ('--operations', '--command', '--module', '--plan', '--inputs'):
            with self.subTest(flag=flag), self.assertRaises(SystemExit) as stopped:
                self.main(['workflow-apply', '--source', '/offline/source', '--approval', '123', flag, 'untrusted'])
            self.assertEqual(stopped.exception.code, 2)
        for route in self.routes.values(): route.assert_not_called()

    def test_review_observations_never_reach_apply_and_request_cannot_carry_approval(self):
        cases = [['workflow-apply', '--source', '/offline/source', '--approval', '123', '--observations', '/offline/facts.json'],
                 ['workflow-request', '--source', '/offline/source', '--approval', '123'],
                 ['apply', '--source', '/offline/source', '--approval', '123', '--observations', '/offline/facts.json']]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(SystemExit): self.main(args)
        for route in self.routes.values(): route.assert_not_called()

    def test_original_plan_apply_and_rollback_dispatch_are_unchanged(self):
        self.assertEqual(self.main(['plan', '--source', '/offline/source']), {'route': 'plan'})
        self.assertEqual(self.main(['apply', '--source', '/offline/source', '--approval', '123']), {'route': 'apply'})
        self.assertEqual(self.main(['rollback']), {'route': 'rollback'})
        self.routes['plan'].assert_called_once_with('/offline/source')
        self.routes['apply'].assert_called_once_with('/offline/source', 123)
        self.routes['rollback'].assert_called_once_with()

    def test_workflow_hold_summary_is_reported_with_nonzero_status(self):
        summary = {'state': 'HOLD', 'attempts_used': 5}
        self.routes['workflow_entry'].side_effect = workflow.WorkflowStopped(summary)
        stdout = io.StringIO()
        with patch.object(release.sys, 'argv', ['release', 'workflow-apply', '--source', '/offline/source', '--approval', '123']), redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as stopped: release.main()
        self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(json.loads(stdout.getvalue()), summary)

    def test_legacy_hold_report_is_preserved(self):
        report = {'state': 'HOLD', 'fixture': 'legacy'}
        self.routes['apply'].side_effect = resume.Stopped(report)
        stdout = io.StringIO()
        with patch.object(release.sys, 'argv', ['release', 'apply', '--source', '/offline/source', '--approval', '123']), redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as stopped: release.main()
        self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(json.loads(stdout.getvalue()), report)

    def test_offline_request_uses_no_gate_lock_or_host_plan(self):
        self.routes['workflow_request'].assert_not_called()
        with patch.object(request, 'read_review_source', return_value=(self.manifest, self.raw)) as source, \
             patch.object(request, 'read_json', return_value=self.observations) as observations, \
             patch.object(release, 'gate', side_effect=AssertionError('Gate forbidden')):
            result = ORIGINAL_WORKFLOW_REQUEST('/offline/source', '/offline/facts.json')
        source.assert_called_once_with('/offline/source')
        observations.assert_called_once_with('/offline/facts.json')
        self.assertEqual(result['state'], 'NOT_EXECUTABLE')
        self.routes['plan'].assert_not_called()


ORIGINAL_WORKFLOW_REQUEST = release.workflow_request


if __name__ == '__main__':
    unittest.main()
