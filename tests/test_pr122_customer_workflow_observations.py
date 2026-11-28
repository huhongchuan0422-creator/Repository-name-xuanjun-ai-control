"""Collector tests: real request-document end-to-end on invented environment facts.
Nothing here is a claim about the target host; the shapes come from the frozen
original fixture conventions of test_pr122_customer_workflow_request.py.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts import pr122_customer_release as release
from scripts import pr122_customer_workflow as workflow
from scripts import pr122_customer_workflow_request as request
from scripts import pr122_customer_workflow_observations as collector
from scripts import pr122_customer_runtime as runtime
from scripts.pr122_account_admission import approved_account_prepare as account
from scripts.pr122_customer_core import Denied, canonical, digest


def source_fixture():
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
    return manifest, canonical(manifest), files


def static_fixture(manifest, raw):
    static = {key: digest(('fixture ' + key).encode())
              for key in request.STATIC_FIELDS if key.endswith('_sha256')}
    static.update(source_commit=manifest['source_commit'], source_tree=manifest['source_tree'],
                  state='READONLY_PLAN', transaction=release.TXN, production_changes=0,
                  main_current='/offline/approved-current', manifest_sha256=digest(raw),
                  scope_sha256=digest(canonical(manifest['files'])),
                  nginx={'master': 'offline-master-identity',
                         'files': {'/offline/nginx.conf': digest(b'fixture nginx')}})
    return static


class FakeBootstrap:
    def __init__(self, control):
        self.CONTROL = Path(control)
        self.canonical = canonical
        self.sha = digest

    def read(self, path, mode=None):
        return Path(path).read_bytes()


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.raw, self.files = source_fixture()
        self.static = static_fixture(self.manifest, self.raw)
        self.root = Path(tempfile.mkdtemp(prefix='xj-pr122-collector-'))
        self.addCleanup(lambda: __import__('shutil').rmtree(self.root, ignore_errors=True))
        self.probe = self.root / 'probe-result.json'
        self.probe.write_bytes(canonical({'state': 'READONLY_OBSERVED_ACCOUNT_CREATION_HOLD'}))
        self.wheels = self.root / 'wheels'
        self.wheels.mkdir()
        self.wheel_shas = {}
        for name in ('cryptography.whl', 'cffi.whl', 'pycparser.whl'):
            body = ('fixture wheel ' + name).encode()
            (self.wheels / name).write_bytes(body)
            self.wheel_shas[name] = digest(body)
        control = self.root / 'readonly-bootstrap-20261017'
        control.mkdir()
        for name in ('plan.json', 'old-wrapper', 'old-sudoers'):
            (control / name).write_bytes(('fixture ' + name).encode())
        self.bootstrap = FakeBootstrap(control)
        self.fake_runtime = SimpleNamespace(
            FIXED_INTERPRETER=runtime.FIXED_INTERPRETER, FIXED_HOST=runtime.FIXED_HOST,
            INTERPRETER_SHA256=runtime.INTERPRETER_SHA256, WHEELS=self.wheel_shas,
            _runtime_tree=lambda root: {}, _root_chain=lambda p: None,
            _protected_bytes=lambda p: b'')
        self.fake_account = SimpleNamespace(
            ACCOUNT=account.ACCOUNT, PROPOSED_ARGV=account.PROPOSED_ARGV,
            ACCOUNT_RECEIPT=self.root / 'account-preparation-20261017',
            OS=lambda: SimpleNamespace(platform_preconditions=lambda: {'uid_min': 100}))
        self.fake_channel = SimpleNamespace(
            canonical=canonical, sha=digest,
            plan=lambda ignore_transaction=False, expected_zip_sha256=None:
                {'transaction': 'fixture', 'new': {'zip_sha256': expected_zip_sha256}})
        self.fake_release = SimpleNamespace(
            plan=lambda folder: dict(self.static, isolated_python={'path': '/fixture/python'},
                                     account_uid=601, account_gid=601),
            source=lambda folder: (self.manifest, self.raw, self.files),
            CONFIG=release.CONFIG, TXN=release.TXN)
        self.venv = {'venv/bin/python': {'kind': 'file', 'mode': 0o755,
                                         'sha256': runtime.INTERPRETER_SHA256},
                     'venv/pyvenv.cfg': {'kind': 'file', 'mode': 0o644,
                                         'sha256': digest(b'fixture venv config')}}
        self.stdlib = {'/usr/lib/python3.11': {'os.py': digest(b'fixture stdlib')}}
        self.native = {'/usr/lib64/fixture-native.so': digest(b'fixture native')}

    def collect(self, **overrides):
        args = dict(release_module=self.fake_release, runtime_module=self.fake_runtime,
                    account_module=self.fake_account, bootstrap_module=self.bootstrap,
                    channel_module=self.fake_channel, probe_receipt=self.probe,
                    wheel_directory=self.wheels, artifact_zip_sha256=digest(b'fixture zip'),
                    artifact_id=123, ci_run_id=456,
                    platform=lambda: {'uid_min': 100}, venv_tree=lambda: copy.deepcopy(self.venv),
                    stdlib=lambda: copy.deepcopy(self.stdlib), native=lambda: copy.deepcopy(self.native))
        args.update(overrides)
        reports = []
        return collector.collect('/offline/source', reports=reports, **args), reports

    def test_complete_target_facts_build_an_exact_request_candidate(self):
        observations, reports = self.collect()
        self.assertEqual(reports, [])
        result = request.make_request(self.manifest, self.raw, observations)
        self.assertEqual(result['missing_inputs'], [])
        self.assertEqual((result['state'], result['permission']), ('NOT_EXECUTABLE', 'NOT_GRANTED'))
        plan = result['plan_candidate']
        rows = plan['workflow_contract']['stages']
        self.assertEqual([row['stage'] for row in rows], list(workflow.STAGES))
        self.assertEqual(rows[0]['adopt_receipt_sha256'], digest(self.probe.read_bytes()))
        # Dynamic live fields are excluded from the static customer plan scope.
        self.assertNotIn('isolated_python', observations['inputs']['stages']['CUSTOMER_APPLY']['static_plan'])
        self.assertNotIn('account_uid', observations['inputs']['stages']['CUSTOMER_APPLY']['static_plan'])
        runtime_stage = observations['inputs']['stages']['RUNTIME']['runtime_template']
        self.assertIsNone(runtime_stage['account_uid'])
        self.assertEqual(runtime_stage['runtime_module_sha256'],
                         digest(self.files[request.IMPLEMENTATIONS['RUNTIME']]))
        self.assertTrue(request.validate_inputs(plan, result['inputs_candidate'], self.manifest, self.raw))

    def test_missing_environment_sections_stay_unknown_and_are_never_invented(self):
        gone = self.root / 'definitely-absent.json'
        observations, reports = self.collect(probe_receipt=gone,
                                             bootstrap_module=FakeBootstrap(self.root / 'absent-control'))
        missing = request.make_request(self.manifest, self.raw, observations)['missing_inputs']
        self.assertIn('inputs.stages.PROBE.receipt_sha256', missing)
        self.assertIn('inputs.stages.POLICY_RESTORE', missing)
        self.assertIsNone(observations['adopt_receipts']['PROBE'])
        self.assertTrue(all(row['state'] == 'HOLD' for row in reports))
        # The account one-shot adoption pin only appears with the real receipt file.
        self.assertIsNone(observations['adopt_receipts']['ACCOUNT'])
        (self.fake_account.ACCOUNT_RECEIPT).mkdir(exist_ok=True)
        marker = self.fake_account.ACCOUNT_RECEIPT / 'ACCOUNT_CREATED_VERIFIED_NO_RETRY.json'
        marker.write_bytes(canonical({'state': 'ACCOUNT_CREATED_VERIFIED_NO_RETRY'}))
        observations, _ = self.collect(probe_receipt=gone,
                                       bootstrap_module=FakeBootstrap(self.root / 'absent-control'))
        self.assertEqual(observations['adopt_receipts']['ACCOUNT'], digest(marker.read_bytes()))

    def test_failing_release_plan_degrades_to_missing_static_plan(self):
        def fail(folder): raise Denied('HOLD:PREEXISTING:/usr/local/lib/xuanjun-customer-center')
        broken = SimpleNamespace(plan=fail, source=self.fake_release.source,
                                 CONFIG=release.CONFIG, TXN=release.TXN)
        observations, reports = self.collect(release_module=broken)
        self.assertIsNone(observations['static_plan'])
        self.assertIsNone(observations['inputs'])
        self.assertEqual([row['section'] for row in reports], ['static_plan'])
        result = request.make_request(self.manifest, self.raw, observations)
        self.assertIn('static_plan', result['missing_inputs'])
        self.assertIsNone(result['plan_candidate'])

    def test_vendor_wheel_pin_mismatch_holds_the_runtime_section_only(self):
        bad = dict(self.wheel_shas)
        bad['cffi.whl'] = digest(b'substituted wheel')
        self.fake_runtime.WHEELS = bad
        observations, reports = self.collect()
        self.assertIsNone(observations['inputs']['stages']['RUNTIME'])
        self.assertIn('inputs.stages.RUNTIME',
                      request.make_request(self.manifest, self.raw, observations)['missing_inputs'])
        self.assertIn({'section': 'runtime', 'state': 'HOLD', 'reason': 'VENDOR_WHEEL_PIN'}, reports)

    def test_collector_emits_no_authority_signature_or_credential_keys(self):
        observations, _ = self.collect()
        banned = {'approval', 'approval_comment', 'review_comment', 'signature', 'command',
                  'operations', 'module', 'decision', 'issued_unix', 'expires_unix', 'token'}
        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(banned.intersection(value), value)
                for child in value.values(): inspect(child)
            elif isinstance(value, list):
                for child in value: inspect(child)
        inspect(observations)
        body = json.dumps(observations)
        self.assertNotIn('INSTALL_APPROVED', body)
        self.assertNotIn('AUDIT_PASS', body)


if __name__ == '__main__':
    unittest.main()
