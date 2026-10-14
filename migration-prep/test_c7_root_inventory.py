import unittest

from c7_root_inventory import redacted_text_summary


class RedactionTests(unittest.TestCase):
    def test_only_counts_and_digest_are_returned(self):
        raw = b"# comment\n/opt/trading-system/run.py --secret hidden\n/usr/bin/true\n"
        value = redacted_text_summary(raw)
        self.assertEqual(value["active_line_count"], 2)
        self.assertEqual(value["writer_marker_line_count"], 1)
        self.assertNotIn("hidden", repr(value))

    def test_bytes_required(self):
        with self.assertRaises(ValueError):
            redacted_text_summary("not bytes")


if __name__ == "__main__":
    unittest.main()

