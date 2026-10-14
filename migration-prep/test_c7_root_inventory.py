import errno
import os
import shutil
import tempfile
import unittest

import c7_root_inventory
from c7_root_inventory import (InventoryProblem, NoCrontab, cron_inventory,
                               redacted_text_summary, systemd_inventory)


class RedactionTests(unittest.TestCase):
    def test_only_counts_and_digest_are_returned(self):
        raw = b"# comment\n/opt/trading-system/run.py --secret hidden-value\n"
        value = redacted_text_summary(raw)
        self.assertEqual(value["active_line_count"], 1)
        self.assertEqual(value["writer_marker_line_count"], 1)
        self.assertNotIn("hidden", repr(value))

    def test_bytes_required(self):
        with self.assertRaises(ValueError):
            redacted_text_summary("not bytes")

    def test_crontab_absence_and_read_failure_are_distinct(self):
        original = c7_root_inventory.pwd.getpwnam
        try:
            c7_root_inventory.pwd.getpwnam = lambda unused: object()
            absent = cron_inventory("root", runner=lambda unused: (_ for _ in ()).throw(NoCrontab()))
            failed = cron_inventory("root", runner=lambda unused: (_ for _ in ()).throw(
                OSError(errno.EACCES, "denied")))
        finally:
            c7_root_inventory.pwd.getpwnam = original
        self.assertEqual(absent, {"status": "CONFIRMED_NO_CRONTAB", "complete": True})
        self.assertEqual(failed, {"status": "READ_FAILED", "complete": False})


class SystemdCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.directory)

    def write(self, name, value=b"[Service]\nExecStart=/bin/true\n"):
        path = os.path.join(self.directory, name)
        with open(path, "wb") as stream:
            stream.write(value)
        return path

    def test_regular_and_authorized_link_are_fully_recorded_without_content(self):
        target = self.write("real.service", b"[Service]\nEnvironment=SECRET=hidden\n")
        os.symlink("real.service", os.path.join(self.directory, "alias.service"))
        result = systemd_inventory(roots=(self.directory,))
        self.assertEqual(result["status"], "PASS_COMPLETE")
        self.assertEqual(result["outcome_counts"]["READ_REGULAR"], 1)
        self.assertEqual(result["outcome_counts"]["RESOLVED_SYMLINK"], 1)
        self.assertEqual(result["outcome_counts"]["DIRECTORY_TRAVERSED"], 1)
        link = [item for item in result["outcomes"]
                if item["outcome"] == "RESOLVED_SYMLINK"][0]
        self.assertIn("effective_unit_name_sha256", link)
        self.assertEqual(result["incomplete_count"], 0)
        self.assertNotIn("SECRET", repr(result))
        self.assertNotIn(target, repr(result))

    def test_permission_walk_error_and_missing_root_hold(self):
        def denied_walk(root, followlinks=False, onerror=None):
            onerror(OSError(errno.EACCES, "denied", root))
            if False:
                yield root, [], []
        denied = systemd_inventory(roots=(self.directory,), walk_fn=denied_walk)
        missing = systemd_inventory(roots=(os.path.join(self.directory, "missing"),))
        self.assertEqual(denied["status"], "HOLD_INCOMPLETE")
        self.assertEqual(denied["outcome_counts"]["PERMISSION_DENIED"], 1)
        self.assertEqual(missing["status"], "HOLD_INCOMPLETE")
        self.assertEqual(missing["roots"][0]["outcome"], "MISSING_DURING_READ")

    def test_dangling_and_outside_links_hold(self):
        os.symlink("missing.service", os.path.join(self.directory, "dangling.service"))
        outside = tempfile.NamedTemporaryFile(delete=False)
        try:
            outside.write(b"[Service]\n"); outside.close()
            os.symlink(outside.name, os.path.join(self.directory, "outside.service"))
            result = systemd_inventory(roots=(self.directory,))
        finally:
            os.unlink(outside.name)
        self.assertEqual(result["status"], "HOLD_INCOMPLETE")
        self.assertEqual(result["outcome_counts"]["DANGLING_SYMLINK"], 1)
        self.assertEqual(result["outcome_counts"]["SYMLINK_TARGET_OUTSIDE_ALLOWED_ROOTS"], 1)

    def test_symlink_directory_is_explicit_and_holds(self):
        child = os.path.join(self.directory, "child")
        os.mkdir(child)
        os.symlink("child", os.path.join(self.directory, "linked-dir"))
        result = systemd_inventory(roots=(self.directory,))
        self.assertEqual(result["status"], "HOLD_INCOMPLETE")
        self.assertEqual(result["outcome_counts"]["SYMLINK_DIRECTORY_NOT_TRAVERSED"], 1)

    def test_nonregular_read_failure_and_concurrent_alteration_hold(self):
        fifo = os.path.join(self.directory, "unit.fifo")
        os.mkfifo(fifo)
        self.write("change.service")
        def changed(unused):
            raise InventoryProblem("CONCURRENT_ALTERATION")
        changed_result = systemd_inventory(roots=(self.directory,), stable_reader=changed)
        self.assertEqual(changed_result["status"], "HOLD_INCOMPLETE")
        self.assertEqual(changed_result["outcome_counts"]["NONREGULAR_SKIPPED"], 1)
        self.assertEqual(changed_result["outcome_counts"]["CONCURRENT_ALTERATION"], 1)
        def failed(unused):
            raise OSError(errno.EACCES, "denied")
        failed_result = systemd_inventory(roots=(self.directory,), stable_reader=failed)
        self.assertEqual(failed_result["outcome_counts"]["PERMISSION_DENIED"], 1)
        self.assertEqual(failed_result["status"], "HOLD_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
