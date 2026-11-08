"""Prevent supported-document values from returning as unknown-type fixtures."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import unittest


class UnknownDocumentFixture(unittest.TestCase):
    def test_negative_type_is_outside_production_supported_types(self):
        source = ast.parse(Path('scripts/community_license_inference.py').read_text())
        supported = next(ast.literal_eval(n.value) for n in source.body
                         if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'EXPECTED_FIELDS' for t in n.targets))
        checks = ast.parse(Path('tests/community_license_runtime_checks.py').read_text())
        method = next(n for n in ast.walk(checks) if isinstance(n, ast.FunctionDef) and n.name == 'test_unknown_type_rejected_not_misrouted_to_id')
        negative = next(ast.literal_eval(n.value) for n in ast.walk(method)
                        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'document_type' for t in n.targets))
        self.assertIn('bank_card', supported)
        self.assertNotIn(negative, supported)

    def test_fixture_is_existing_hash_verified_synthetic_png(self):
        fixture = json.loads(Path('tests/fixtures/community_license_columns90_image.json').read_text())
        self.assertEqual(fixture['scope'], 'SYNTHETIC_TEST_ONLY_NOT_REAL_LICENSE')
        raw = base64.b64decode(fixture['png_base64'], validate=True)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture['png_sha256'])
        self.assertTrue(raw.startswith(b'\x89PNG\r\n\x1a\n'))
