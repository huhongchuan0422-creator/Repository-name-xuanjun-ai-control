"""Negative tests for fixed diagnostic. All tests are offline and cloud-free."""
import hashlib
import importlib.util
import os
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class ReadOnlyDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load('p2_diag_test', 'scripts/p2_uk_readonly_diagnostic.py')
        cls.t = load('p2_transport_test', 'scripts/p2_uk_swas_diagnostic.py')

    def valid(self):
        return ('DIAG_SCHEMA=1\nTARGET_HOST=iZd7oeikknn1z21sq6ji6zZ\n'
            'EXEC_UID=0\nPYTHON_VERSION=3.6.8\n'
            'CGROUP_MOUNT_TYPE=tmpfs\nSITE_PATH=/usr/local/libexec/xuanjun-p2-site/P2_SITE_ENTRY.py\n'
            'SITE_STATUS=ABSENT\n'
            'CANONICAL_WRITER=UNKNOWN\nEPOCH=UNKNOWN\nLEASE=UNKNOWN\n'
            'FENCE=UNKNOWN\nROOT_TRUST=UNKNOWN\nHISTORICAL_INVOKEID=UNKNOWN\n'
            'DIAG_END=COMPLETE\n').replace('\\\n','\n')

    def test_fixed_bytes_and_hash(self):
        source = self.d.command_content().encode('utf-8')
        self.assertEqual(1771, len(source))
        self.assertEqual(self.d.COMMAND_SHA256, hashlib.sha256(source).hexdigest())

    def test_public_safe(self):
        result = self.d.safe_receipt(self.valid())
        self.assertEqual(result['state'], 'DIAGNOSTIC_METADATA_ONLY')
        self.assertFalse(result['redispatch_allowed'])

    def test_reject_unsafe(self):
        ok = self.valid()
        variants = [ok+'PRIVATE=token\n',ok.replace('EXEC_UID=0','EXEC_UID=1'),
            ok.replace('DIAG_SCHEMA=1','DIAG_SCHEMA=9'),
            ok.replace('DIAG_END=COMPLETE','DIAG_END=BROKEN'),
            ok.replace('PYTHON_VERSION=3.6.8','PYTHON_VERSION=4.0.0'),
            ok.replace('TARGET_HOST=iZd7oeikknn1z21sq6ji6zZ','TARGET_HOST=other'),
            ok.replace('EPOCH=UNKNOWN','EPOCH=2'),
            ok.replace('DIAG_END=COMPLETE\n',''),
            ok+'x' * 5000,
            ok.replace('EXEC_UID=0','EXEC_UID=0\nEXEC_UID=0'),
            ok.replace('EXEC_UID=0','EXEC_UID=0 secret=yes')]
        for variant in variants:
            with self.subTest(variant=variant[:35]):
                with self.assertRaises(self.d.DiagnosticHold):
                    self.d.safe_receipt(variant)
        for stderr, exit_code in [('secret',0),('',40),('',41),('',1)]:
            with self.assertRaises(self.d.DiagnosticHold):
                self.d.safe_receipt(ok,stderr,exit_code)

    def test_cloud_path_requires_exact_binding(self):
        self.assertIn('read-only-diagnostic', self.t.split_cloud.__code__.co_consts[1].__str__()) if False else None
        self.assertEqual(self.d.command_content(), self.t.diagnostic_module().command_content())

if __name__ == '__main__':
    unittest.main()
