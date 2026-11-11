from __future__ import print_function

import hashlib
import os
import tempfile
import unittest
from unittest import mock

from production_dependency_inventory import build, public_view


class ProductionDependencyInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "writer.py")
        with open(self.path, "w") as stream:
            stream.write("import os\n"
                         "DB='/private/trading.db'\n"
                         "REF='BINANCE_TRADING_SECRET_REF'\n"
                         "def run():\n    return 'new_order'\n"
                         "if __name__ == '__main__':\n    run()\n")
        with open(self.path, "rb") as stream:
            raw = stream.read()
        self.private = {
            "roots": [self.temp.name],
            "records": [{
                "path_id": "WP001", "source_path": self.path,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "path_class": "FORMAL", "static_role": "DIRECT_WRITE_CAPABLE_SOURCE"}]}

    def tearDown(self):
        self.temp.cleanup()

    def test_private_is_exact_and_public_redacts_paths_and_reference_names(self):
        with mock.patch("production_dependency_inventory.process_path_index",
                        return_value={}), mock.patch(
                            "production_dependency_inventory.readable_trigger_sources",
                            return_value=[]):
            private = build(self.private, 4, 2, "caller", 0)
        public = public_view(private)
        self.assertEqual(private["writer_count"], 1)
        self.assertFalse(private["production_dependency_closure"])
        self.assertEqual(private["writer_records"][0]["credential_reference_names"],
                         ["BINANCE_TRADING_SECRET_REF"])
        self.assertIn("/private/trading.db",
                      private["writer_records"][0]["data_path_references"])
        self.assertNotIn(self.path, repr(public))
        self.assertNotIn("BINANCE_TRADING_SECRET_REF", repr(public))
        self.assertNotIn("/private/trading.db", repr(public))
        self.assertTrue(public["source_paths_redacted"])


if __name__ == "__main__":
    unittest.main()
