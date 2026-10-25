"""Isolated DOTS native source-write probe for existing issue #19.

No network, process execution, filesystem writes, host or lease operations.
Run manually in an approved test environment: python3 test_receipt_binding.py
Existing repository CI does NOT automatically execute this file.
"""
import hashlib
import json
import re
import unittest


def receipt_binding(task_id, commit, payload):
    """Bind exact UTF-8 bytes to a task and lowercase Git commit identity."""
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("TASK_REQUIRED")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("COMMIT_REQUIRED")
    if not isinstance(payload, str):
        raise TypeError("TEXT_REQUIRED")
    return {
        "task_id": task_id,
        "commit": commit,
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "payload_bytes": len(payload.encode("utf-8")),
    }


class ReceiptBindingTests(unittest.TestCase):
    def test_exact_utf8_roundtrip(self):
        text = '玄钧\n"quoted"\\path'
        value = receipt_binding("issue-19-probe", "a" * 40, text)
        self.assertEqual(json.loads(json.dumps(value)), value)
        self.assertEqual(value["payload_bytes"], len(text.encode("utf-8")))
        self.assertEqual(value["payload_sha256"],
                         hashlib.sha256(text.encode("utf-8")).hexdigest())

    def test_modified_bytes_change_binding(self):
        before = receipt_binding("issue-19-probe", "a" * 40, "source\n")
        after = receipt_binding("issue-19-probe", "a" * 40, "source")
        self.assertNotEqual(before["payload_sha256"], after["payload_sha256"])

    def test_invalid_commit_rejected(self):
        for commit in ("", "A" * 40, "a" * 39, "a" * 41, "g" * 40, None):
            with self.subTest(commit=commit), self.assertRaises(ValueError):
                receipt_binding("issue-19-probe", commit, "source")

    def test_invalid_task_rejected(self):
        for task in ("", " ", None):
            with self.subTest(task=task), self.assertRaises(ValueError):
                receipt_binding(task, "a" * 40, "source")

    def test_non_text_rejected(self):
        with self.assertRaises(TypeError):
            receipt_binding("issue-19-probe", "a" * 40, b"source")


if __name__ == "__main__":
    unittest.main()
