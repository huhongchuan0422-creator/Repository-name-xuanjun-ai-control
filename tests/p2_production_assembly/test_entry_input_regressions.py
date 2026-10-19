"""Regress UK entry Manifest and published lifecycle input compatibility.

These are source/input regressions, never installation or UK activation evidence.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / 'production/p2_attempt5/native_adapter.py'
ENTRY = ROOT / 'production/p2_attempt5/entry.py'
spec = importlib.util.spec_from_file_location('input_regression_adapter', str(ADAPTER))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

PARENT = ('/var/lib/xuanjun-p2-preparation/'
          'artifact-11796280855-p2pkg-38372304180-1/'
          'complete-install-candidate-38503014520')


class ManifestFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(ENTRY.read_text())
        checks = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == 'require' and len(n.args) > 1
                  and isinstance(n.args[1], ast.Str)
                  and n.args[1].s == 'INHERITED_CORE_SOURCE']
        if len(checks) != 1:
            raise AssertionError('exact entry identity gate not found')
        cls.expression = compile(ast.Expression(checks[0].args[0]), str(ENTRY), 'eval')

    def check(self, manifest):
        return eval(self.expression, {'manifest': manifest,
            'inherited': {'source_commit': 'commit', 'source_tree': 'tree'}})

    def test_runtime_only_manifest(self):
        self.assertTrue(self.check({'runtime_source_commit': 'commit',
                                    'runtime_source_tree': 'tree'}))

    def test_historical_only_manifest(self):
        self.assertTrue(self.check({'reviewed_core_commit': 'commit',
                                    'reviewed_core_tree': 'tree'}))

    def test_runtime_identity_takes_precedence(self):
        self.assertTrue(self.check({'runtime_source_commit': 'commit',
            'runtime_source_tree': 'tree', 'reviewed_core_commit': 'different',
            'reviewed_core_tree': 'different'}))

    def test_missing_identity_rejected(self):
        self.assertFalse(self.check({}))

    def test_wrong_identity_rejected(self):
        self.assertFalse(self.check({'runtime_source_commit': 'different',
                                    'runtime_source_tree': 'tree'}))

    def test_partial_identity_rejected(self):
        self.assertFalse(self.check({'runtime_source_commit': 'commit'}))


class LifecycleInputTests(unittest.TestCase):
    def setUp(self):
        self.plan_raw = b'{"contract":"retained"}'
        self.seed_raw = b'{"schema":2,"seed":{"original":"retained"}}'
        self.plan = self.ref('approved-plan', self.plan_raw)
        self.seed = self.ref('resume-inputs', self.seed_raw)
        self.kit = mock.Mock()
        self.kit._private_resume_inputs.return_value = ('original', {}, {})
        self.data = {self.plan['path']: self.plan_raw, self.seed['path']: self.seed_raw}

    def ref(self, kind, raw):
        pin = hashlib.sha256(raw).hexdigest()
        return {'path': PARENT + '/epoch7-lifecycle-' + kind + '-' +
                pin[:16] + '.private.json', 'sha256': pin}

    def read(self, path, expected, bound):
        raw = self.data[path]
        self.assertLessEqual(len(raw), bound)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError('P2_NATIVE_ADAPTER_FILE_SHA')
        return raw

    def invoke(self):
        with mock.patch.object(adapter, 'read', side_effect=self.read):
            return adapter.private_resume_inputs(self.kit, self.plan, self.seed)

    def test_lifecycle_pair_preserves_exact_bytes_and_seed(self):
        raw, plan, seed = self.invoke()
        self.assertEqual(raw, self.plan_raw)
        self.assertEqual(plan, {'contract': 'retained'})
        self.assertEqual(seed, {'original': 'retained'})
        self.kit._private_resume_inputs.assert_not_called()

    def test_changed_seed_rejected(self):
        self.data[self.seed['path']] = b'{"schema":2,"seed":{"changed":true}}'
        with self.assertRaisesRegex(RuntimeError, 'FILE_SHA'):
            self.invoke()

    def test_same_names_outside_fixed_parent_rejected(self):
        self.plan['path'] = '/other/' + os.path.basename(self.plan['path'])
        with self.assertRaisesRegex(RuntimeError, 'PRIVATE_INPUT_PATH'):
            self.invoke()

    def test_successor_still_uses_frozen_loader(self):
        self.plan['path'] = self.plan['path'].replace('lifecycle', 'successor')
        self.seed['path'] = self.seed['path'].replace('lifecycle', 'successor')
        self.assertEqual(self.invoke()[0], 'original')
        self.kit._private_resume_inputs.assert_called_once_with(
            self.plan['path'], self.plan['sha256'], self.seed['path'], self.seed['sha256'])

    def test_mixed_families_not_adopted_by_lifecycle_reader(self):
        self.seed['path'] = self.seed['path'].replace('lifecycle', 'successor')
        self.kit._private_resume_inputs.side_effect = RuntimeError('FROZEN_REJECTION')
        with self.assertRaisesRegex(RuntimeError, 'FROZEN_REJECTION'):
            self.invoke()

    def test_invalid_envelopes_rejected(self):
        for value in ({'schema': True, 'seed': {}},
                      {'schema': 1, 'seed': {}},
                      {'schema': 2, 'seed': []},
                      {'schema': 2, 'seed': {}, 'extra': 1}):
            raw = json.dumps(value).encode('ascii')
            self.seed = self.ref('resume-inputs', raw)
            self.data[self.seed['path']] = raw
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, 'PRIVATE_SEED_SCHEMA'):
                    self.invoke()

    def test_duplicate_fields_rejected(self):
        raw = b'{"schema":2,"schema":2,"seed":{}}'
        self.seed = self.ref('resume-inputs', raw)
        self.data[self.seed['path']] = raw
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_KEY'):
            self.invoke()

    def test_bad_reference_rejected_before_read(self):
        self.plan['sha256'] = 'UNKNOWN'
        with mock.patch.object(adapter, 'read') as reader:
            with self.assertRaisesRegex(RuntimeError, 'SHA256'):
                adapter.private_resume_inputs(self.kit, self.plan, self.seed)
            reader.assert_not_called()

    def test_frozen_hydration_and_contract_checks_remain_in_driver(self):
        tree = ast.parse(ADAPTER.read_text())
        driver = next(n for n in tree.body
                      if isinstance(n, ast.FunctionDef) and n.name == 'build_driver')
        attributes = [n.attr for n in ast.walk(driver) if isinstance(n, ast.Attribute)]
        self.assertIn('_hydrate_seed', attributes)
        self.assertIn('_authenticate_probe_receipt', attributes)
        self.assertIn('compile_host_contract', attributes)
        calls = [n for n in ast.walk(driver)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == 'private_resume_inputs']
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
