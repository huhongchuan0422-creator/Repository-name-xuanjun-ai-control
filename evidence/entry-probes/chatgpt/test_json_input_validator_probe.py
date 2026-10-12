# -*- coding: utf-8 -*-
from __future__ import absolute_import

import unittest

from json_input_validator_probe import validate_json_bytes


class JsonProbeTests(unittest.TestCase):
    def test_valid_utf8_json(self):
        self.assertEqual(validate_json_bytes(b'{"a":1}'), {"a": 1})

    def test_duplicate_key_rejected(self):
        with self.assertRaises(ValueError):
            validate_json_bytes(b'{"a":1,"a":2}')

    def test_non_finite_rejected(self):
        with self.assertRaises(ValueError):
            validate_json_bytes(b'{"a":NaN}')

    def test_invalid_utf8_rejected(self):
        with self.assertRaises(UnicodeDecodeError):
            validate_json_bytes(b'\xff')


if __name__ == "__main__":
    unittest.main()
