import json
import unittest
from unittest import mock
from korea.phase_c import source_contracts as source


class SourceContractTests(unittest.TestCase):
    def test_contract_never_exports_literal_default_or_docstring_or_executes(self):
        raw=b'''import os\nSECRET="LIVE_LITERAL_MUST_NOT_APPEAR"\nraise RuntimeError("must not execute")\nclass Store:\n    def load(self, role, fallback="PRIVATE_DEFAULT"):\n        """PRIVATE_DOCSTRING"""\n        return "TRADING_CREDENTIAL_MASTER_KEY"\n'''
        result=source.catalogue(raw)
        output=json.dumps(result)
        for value in ('LIVE_LITERAL_MUST_NOT_APPEAR','PRIVATE_DEFAULT','PRIVATE_DOCSTRING'):
            self.assertNotIn(value,output)
        self.assertEqual(result['definitions'][1]['name'],'Store.load')
        self.assertEqual(result['definitions'][1]['parameters'],['self','role','fallback'])
        self.assertIn('TRADING_CREDENTIAL_MASTER_KEY',result['recognized_role_markers'])
        self.assertFalse(result['semantics_or_role_permission_proven'])
    def test_probe_refuses_root_without_opening_sources(self):
        with mock.patch.object(source.os,'geteuid',return_value=0),mock.patch.object(source,'read_source') as read:
            with self.assertRaises(RuntimeError):source.collect()
            read.assert_not_called()
    def test_invalid_source_syntax_is_not_executed(self):
        with self.assertRaises(SyntaxError):source.catalogue(b'def invalid(')
