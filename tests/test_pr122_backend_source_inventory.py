import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('source_inventory',ROOT/'deploy/pr122-backend-migration/source_inventory.py')
module = importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(module)


class InventoryTests(unittest.TestCase):
    def test_static_catalogue_never_executes_source_or_prints_literal_values(self):
        data=b"raise RuntimeError('must not execute')\nclass Synthetic:\n def write(self):\n  store_secret('SYNTHETIC_PRIVATE_VALUE')\n"
        result=module.catalogue(data,hashlib.sha256(data).hexdigest())
        self.assertEqual(result['status'],'PUBLIC_SOURCE_BYTES_MATCH')
        self.assertEqual(result['lexical_write_capable_calls'],[dict(scope='Synthetic.write',line=4,call='store_secret')])
        self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',json.dumps(result))

    def test_unbound_bytes_not_parsed_or_published(self):
        with mock.patch.object(module.ast,'parse',side_effect=AssertionError('must not parse')):
            result=module.catalogue(b'SYNTHETIC_PRIVATE_VALUE','a'*64)
        self.assertEqual(result['status'],'SOURCE_VERSION_MISMATCH')
        self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',json.dumps(result))

    def test_parse_error_never_echoes_source(self):
        data=b'SYNTHETIC_PRIVATE_VALUE = !'
        result=module.catalogue(data,hashlib.sha256(data).hexdigest())
        self.assertEqual(result['status'],'SOURCE_PARSE_UNKNOWN')
        self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',json.dumps(result))

    def test_collection_rejects_root_or_wrong_host_before_reads(self):
        with mock.patch.object(module.os,'geteuid',return_value=0):
            with mock.patch.object(module,'read_public_source',side_effect=AssertionError('must not read')):
                with self.assertRaisesRegex(RuntimeError,'TOKYO_NONROOT_REQUIRED'):module.collect()

    def test_permission_errors_stay_unknown_with_no_exception_detail(self):
        with mock.patch.object(module.os,'geteuid',return_value=1001),mock.patch.object(module.os,'uname',return_value=type('Host',(),{'nodename':module.SOURCE_HOST})()):
            with mock.patch.object(module,'read_public_source',side_effect=PermissionError('SYNTHETIC_PRIVATE_VALUE')):
                result=module.collect()
        self.assertEqual(len(result['files']),5)
        self.assertEqual(result['status'],'FIXED_SOURCE_SCOPE_INCOMPLETE')
        self.assertFalse(result['all_writer_custody_proven'])
        self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',json.dumps(result))


if __name__=='__main__':unittest.main()
