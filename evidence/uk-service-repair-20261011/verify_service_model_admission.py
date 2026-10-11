"""Focused, side-effect-bounded verification of reviewed service admission only.

Does not import or launch the recovered dispatcher/broker or load credentials.
Usage: python verify_service_model_admission.py ORIGINAL FIXED
"""
import ast
import hashlib
import json
import os
import pathlib
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


ORIGINAL, FIXED = map(pathlib.Path, sys.argv[1:3])
sys.argv[1:] = []


def reviewed_admission(path):
    tree = ast.parse(path.read_text())
    names = {'SHA', 'SAFE_USER', 'REQUIRED', 'REQUIRED_V2'}
    body = [n for n in tree.body if
            (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))
            or (isinstance(n, ast.FunctionDef) and n.name in {'_canonical', '_validate_model', 'load_config', 'build_loop'})]
    namespace = dict(os=os, pwd=pwd, re=re, stat=stat, subprocess=subprocess,
                     hashlib=hashlib, json=json)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.ns = reviewed_admission(FIXED)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name).resolve()
        self.config_path = self.root / 'config.json'
        base = str(self.root)
        self.config = dict(config_version=2, control_repository='o/r',
            source_commit='a'*40, repositories={'o/r':base+'/source'},
            db_path=base+'/state/ledger.db', dispatcher_lock=base+'/locks/d',
            github_writer_lock=base+'/locks/g', workspace_root=base+'/work',
            service_home=base+'/service', worker_home=base+'/worker',
            codex_home=base+'/auth', worker_user='xj_test_worker',
            codex_bin=base+'/bin/codex', gh_bin=base+'/bin/gh', path='/usr/bin',
            required_checks=['ci'], model='gpt-5.6-sol', max_workers=1,
            activation_descriptor=base+'/state/active.json',
            activation_epoch_journal=base+'/state/epoch', activation_lock=base+'/state/lock',
            broker_socket=base+'/run/broker.sock', broker_client=base+'/bin/broker',
            release_sha256='b'*64, ledger_uuid='c'*36, generation=1,
            instance='d'*36, ledger_socket=base+'/run/ledger.sock')
        self.runner = mock.Mock(return_value=types.SimpleNamespace(returncode=0, stdout=b'a'*40+b'\n'))
        self.real_stat = os.stat

    def tearDown(self):
        self.tmp.cleanup()

    def fake_stat(self, path, *args, **kwargs):
        if str(path) in (self.config['codex_bin'], self.config['gh_bin']):
            return types.SimpleNamespace(st_mode=stat.S_IFREG|0o755, st_uid=0)
        return self.real_stat(path, *args, **kwargs)

    def load(self, ns=None):
        self.config_path.write_text(json.dumps(self.config))
        self.config_path.chmod(0o600)
        with mock.patch.object(os, 'stat', side_effect=self.fake_stat), mock.patch.object(pwd, 'getpwnam', side_effect=KeyError):
            return (ns or self.ns)['load_config'](str(self.config_path), run=self.runner)

    def assert_model_rejected(self, model):
        self.config['model'] = model
        with self.assertRaisesRegex(ValueError, 'unsupported config/model'):
            self.load()
        self.runner.assert_not_called()

    def test_original_61_admission_reproduced_without_binary_execution(self):
        self.config['model'] = 'gpt-6.1-sol'
        loaded = self.load(reviewed_admission(ORIGINAL))
        self.assertEqual(loaded['model'], 'gpt-6.1-sol')
        self.runner.assert_called_once()

    def test_56_admitted_with_exact_source_binding(self):
        self.assertEqual(self.load()['model'], 'gpt-5.6-sol')
        self.runner.assert_called_once()

    def test_61_rejected_before_binary_invocation(self):
        self.assert_model_rejected('gpt-6.1-sol')

    def test_astra_rejected(self):
        self.assert_model_rejected('gpt-6-astra')

    def test_wildcard_rejected(self):
        self.assert_model_rejected('*')

    def test_provider_alias_rejected(self):
        self.assert_model_rejected('other/gpt-5.6-sol')

    def test_non_string_models_rejected(self):
        for value in (None, [], {}, True, 56):
            with self.subTest(value=value):
                self.assert_model_rejected(value)

    def test_missing_model_schema_still_rejected(self):
        del self.config['model']
        with self.assertRaisesRegex(ValueError, 'configuration keys mismatch'):
            self.load()
        self.runner.assert_not_called()

    def test_direct_runtime_61_rejected_before_activation_or_db(self):
        activation = mock.Mock(side_effect=AssertionError('activation touched'))
        self.ns['ActivationStore'] = activation
        with self.assertRaisesRegex(ValueError, 'unsupported config/model'):
            self.ns['build_loop']({'config_version':2, 'model':'gpt-6.1-sol'})
        activation.assert_not_called()

    def test_direct_runtime_missing_model_rejected_before_activation(self):
        activation = mock.Mock(side_effect=AssertionError('activation touched'))
        self.ns['ActivationStore'] = activation
        with self.assertRaisesRegex(ValueError, 'unsupported config/model'):
            self.ns['build_loop']({'config_version':2})
        activation.assert_not_called()

    def test_runtime_56_reaches_existing_activation_boundary(self):
        class BoundaryReached(Exception):
            pass
        activation = mock.Mock(side_effect=BoundaryReached)
        self.ns['ActivationStore'] = activation
        with self.assertRaises(BoundaryReached):
            self.ns['build_loop'](self.config)
        activation.assert_called_once()

    def test_runtime_legacy_version_guard_preserved(self):
        self.ns['ActivationStore'] = mock.Mock()
        with self.assertRaisesRegex(ValueError, 'broker-backed configuration version 2'):
            self.ns['build_loop']({'config_version':1,'model':'gpt-5.6-sol'})
        self.ns['ActivationStore'].assert_not_called()

    def test_mismatched_source_head_still_rejected(self):
        self.runner.return_value.stdout = b'e'*40
        with self.assertRaisesRegex(ValueError, 'HEAD does not match approved commit'):
            self.load()

    def test_world_writable_config_still_rejected(self):
        self.config_path.write_text(json.dumps(self.config))
        self.config_path.chmod(0o666)
        with self.assertRaisesRegex(ValueError, 'unsafe configuration file'):
            self.ns['load_config'](str(self.config_path), run=self.runner)
        self.runner.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
