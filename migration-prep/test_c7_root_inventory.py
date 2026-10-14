import errno
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

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

    @staticmethod
    def completed(returncode=0, stdout=b"", stderr=b""):
        value = mock.Mock()
        value.returncode = returncode
        value.stdout = stdout
        value.stderr = stderr
        return value

    def assert_crontab_call(self, run_mock):
        run_mock.assert_called_once_with(
            ["/usr/bin/crontab", "-u", "root", "-l"],
            stdout=c7_root_inventory.subprocess.PIPE,
            stderr=c7_root_inventory.subprocess.PIPE,
            timeout=20,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})

    def test_crontab_default_chain_reads_bytes_and_exact_argv(self):
        result = self.completed(stdout=b"* * * * * /bin/true\n")
        with mock.patch.object(c7_root_inventory.subprocess, "run",
                               return_value=result) as run_mock:
            value = cron_inventory("root")
        self.assertEqual(value["status"], "READ")
        self.assertTrue(value["complete"])
        self.assertEqual(value["active_line_count"], 1)
        self.assert_crontab_call(run_mock)

    def test_crontab_default_chain_exact_absence(self):
        result = self.completed(returncode=1, stderr=b"no crontab for root\n")
        with mock.patch.object(c7_root_inventory.subprocess, "run",
                               return_value=result) as run_mock:
            value = cron_inventory("root")
        self.assertEqual(value, {"status": "CONFIRMED_NO_CRONTAB", "complete": True})
        self.assert_crontab_call(run_mock)

    def test_crontab_default_chain_permission_failure(self):
        with mock.patch.object(c7_root_inventory.subprocess, "run",
                               side_effect=PermissionError(errno.EACCES, "denied")) as run_mock:
            value = cron_inventory("root")
        self.assertEqual(value, {"status": "READ_FAILED", "complete": False,
                                 "outcome": "CRONTAB_PERMISSION_DENIED"})
        self.assert_crontab_call(run_mock)

    def test_crontab_default_chain_timeout(self):
        error = c7_root_inventory.subprocess.TimeoutExpired(
            ["/usr/bin/crontab", "-u", "root", "-l"], 20)
        with mock.patch.object(c7_root_inventory.subprocess, "run",
                               side_effect=error) as run_mock:
            value = cron_inventory("root")
        self.assertEqual(value, {"status": "READ_FAILED", "complete": False,
                                 "outcome": "CRONTAB_TIMEOUT"})
        self.assert_crontab_call(run_mock)

    def test_crontab_default_chain_abnormal_return(self):
        result = self.completed(returncode=2, stderr=b"permission denied\n")
        with mock.patch.object(c7_root_inventory.subprocess, "run",
                               return_value=result) as run_mock:
            value = cron_inventory("root")
        self.assertEqual(value, {"status": "READ_FAILED", "complete": False,
                                 "outcome": "CRONTAB_COMMAND_FAILED"})
        self.assert_crontab_call(run_mock)

    def test_crontab_interface_rejects_illegal_types(self):
        with self.assertRaisesRegex(TypeError, "CRONTAB_USER_STRING_REQUIRED"):
            cron_inventory(["root"])
        with self.assertRaisesRegex(TypeError, "CRONTAB_READER_CALLABLE_REQUIRED"):
            cron_inventory("root", runner=["not", "callable"])
        result = self.completed(stdout="not-bytes")
        with mock.patch.object(c7_root_inventory.subprocess, "run", return_value=result):
            value = cron_inventory("root")
        self.assertEqual(value, {"status": "READ_FAILED", "complete": False,
                                 "outcome": "CRONTAB_RESULT_TYPE_INVALID"})

    def test_main_default_cron_chain_emits_hold_and_failed_item(self):
        def subprocess_result(command, **unused):
            if command[0] == "/usr/sbin/visudo":
                return self.completed(stdout=b"parsed OK\n")
            if command[:5] == ["/usr/bin/sudo", "-n", "-l", "-U"]:
                return self.completed(stdout=b"policy\n")
            user = command[2]
            if user == "githubrunner":
                return self.completed(returncode=2, stderr=b"permission denied\n")
            return self.completed(stdout=b"")

        systemd = {"status": "PASS_COMPLETE", "roots": [], "outcomes": []}
        output = io.StringIO()
        with mock.patch.object(c7_root_inventory.sys, "argv", ["c7_root_inventory.py"]), \
                mock.patch.object(c7_root_inventory.os, "geteuid", return_value=0), \
                mock.patch.object(c7_root_inventory.socket, "gethostname",
                                  return_value="iZ6wee8q9z4t03hvqumwfhZ"), \
                mock.patch.object(c7_root_inventory.pwd, "getpwnam", return_value=object()), \
                mock.patch.object(c7_root_inventory.subprocess, "run",
                                  side_effect=subprocess_result) as run_mock, \
                mock.patch.object(c7_root_inventory, "parsed_sources", return_value=[]), \
                mock.patch.object(c7_root_inventory, "effective_policy", return_value={}), \
                mock.patch.object(c7_root_inventory, "systemd_inventory", return_value=systemd), \
                redirect_stdout(output):
            status = c7_root_inventory.main()
        value = json.loads(output.getvalue())
        self.assertEqual(status, 2)
        self.assertEqual(value["status"], "HOLD_INCOMPLETE")
        self.assertIn({"stage": "CRONTAB", "subject": "githubrunner",
                       "outcome": "CRONTAB_COMMAND_FAILED"}, value["failed_items"])
        cron_calls = [call.args[0] for call in run_mock.call_args_list
                      if call.args[0][0] == "/usr/bin/crontab"]
        self.assertEqual(cron_calls, [
            ["/usr/bin/crontab", "-u", "root", "-l"],
            ["/usr/bin/crontab", "-u", "yibi", "-l"],
            ["/usr/bin/crontab", "-u", "githubrunner", "-l"]])


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

    def test_injection_contracts_are_typed_and_invalid_results_hold(self):
        self.write("unit.service")
        with self.assertRaisesRegex(TypeError, "SYSTEMD_ROOTS_STRING_SEQUENCE_REQUIRED"):
            systemd_inventory(roots=self.directory)
        with self.assertRaisesRegex(TypeError, "SYSTEMD_WALK_CALLABLE_REQUIRED"):
            systemd_inventory(roots=(self.directory,), walk_fn=[])
        with self.assertRaisesRegex(TypeError, "SYSTEMD_STABLE_READER_CALLABLE_REQUIRED"):
            systemd_inventory(roots=(self.directory,), stable_reader=[])

        invalid_read = systemd_inventory(
            roots=(self.directory,), stable_reader=lambda unused: b"not-a-tuple")
        self.assertEqual(invalid_read["status"], "HOLD_INCOMPLETE")
        self.assertEqual(invalid_read["outcome_counts"][
            "STABLE_READER_RESULT_TYPE_INVALID"], 1)

        def invalid_walk(root, followlinks=False, onerror=None):
            yield root, (), []
        invalid_walk_result = systemd_inventory(
            roots=(self.directory,), walk_fn=invalid_walk)
        self.assertEqual(invalid_walk_result["status"], "HOLD_INCOMPLETE")
        self.assertEqual(invalid_walk_result["outcome_counts"][
            "WALK_RESULT_TYPE_INVALID"], 1)


if __name__ == "__main__":
    unittest.main()
