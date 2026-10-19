"""Purely local, synthetic boundary tests for offline LOGIN_ONLY preparation.

No provider, server, subprocess, production configuration, secret, or repository
service is used. A passing preparation is deliberately NOT_INSTALLABLE.
"""
from __future__ import annotations

import ast
import base64
import copy
import getpass
import importlib.util
import io
import json
import os
from pathlib import Path
import smtplib
import socket
import stat
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from types import SimpleNamespace
import urllib.request
import warnings


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr122_offline_login_config_under_test", ROOT / "tools/pr122_login_config_prepare.py"
)
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)

PROFILE = "OFFICIAL_LOGIN_ONLY_V1"
ADMIN_KEYS = {
    "deployment_profile", "keys", "active_key", "providers", "backup_key",
    "backup_key_ref", "authority_verify_key",
}
RUNTIME_KEYS = {"deployment_profile", "keys", "active_key", "providers"}
BUNDLE_FILES = {"config.json", "runtime.json", "PREPARATION.json"}
SYNTHETIC_PASSWORD = "synthetic-SMTP-password-DO-NOT-USE-6728"
ERROR_SENTINEL = "synthetic-exception-secret-MUST-NOT-BE-PRINTED-8871"


def encoded(byte: int) -> str:
    return base64.b64encode(bytes([byte]) * 32).decode("ascii")


def fixture() -> dict:
    return {
        "deployment_profile": PROFILE,
        "keys": {"synthetic-key-id-6728": encoded(17)},
        "active_key": "synthetic-key-id-6728",
        "providers": {
            "smtp": {
                "host": "smtp.synthetic-example.invalid",
                "port": 587,
                "tls_mode": "starttls",
                "username": "synthetic-login@synthetic-example.invalid",
                "sender": "synthetic-sender@synthetic-example.invalid",
                "password": SYNTHETIC_PASSWORD,
            }
        },
        "backup_key": encoded(29),
        "backup_key_ref": "synthetic-backup-ref-6728",
        "authority_verify_key": encoded(41),
    }


def interactive_values():
    value = fixture()
    smtp = value["providers"]["smtp"]
    data_key = value["keys"][value["active_key"]]
    return [value["active_key"], data_key, data_key,
            value["backup_key"], value["backup_key"], value["backup_key_ref"],
            value["authority_verify_key"], value["authority_verify_key"],
            smtp["host"], str(smtp["port"]), smtp["tls_mode"],
            smtp["username"], smtp["sender"], smtp["password"], smtp["password"]]


def secret_values(value=None):
    value = fixture() if value is None else value
    return [
        *value["keys"].values(), *value["keys"].keys(), value["active_key"],
        value["backup_key"], value["backup_key_ref"], value["authority_verify_key"],
        value["providers"]["smtp"]["host"],
        value["providers"]["smtp"]["username"],
        value["providers"]["smtp"]["sender"],
        value["providers"]["smtp"]["password"],
        ERROR_SENTINEL,
    ]


class TTY(io.StringIO):
    def isatty(self):
        return True


class OfflineOnly(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target, names in (
            (socket, ("socket", "create_connection", "getaddrinfo")),
            (smtplib, ("SMTP", "SMTP_SSL")),
            (urllib.request, ("urlopen",)),
            (subprocess, ("Popen", "run", "call", "check_call", "check_output")),
            (os, ("system", "popen")),
        ):
            for name in names:
                self.stack.enter_context(patch.object(
                    target, name,
                    side_effect=AssertionError("Network, providers and subprocesses forbidden"),
                ))

    def assert_redacted(self, value, config=None):
        serialized = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        for secret in secret_values(config):
            self.assertNotIn(secret, serialized)

    def assert_config_error(self, operation):
        with self.assertRaises(prepare.ConfigError) as caught:
            operation()
        error = caught.exception
        self.assertIsInstance(error.code, str)
        self.assertRegex(error.code, r"^[A-Z][A-Z0-9_]*$")
        self.assert_redacted(str(error))
        self.assert_redacted(error.code)
        return error


class SchemaTests(OfflineOnly):
    def test_minimal_exact_schema_and_same_source_runtime(self):
        source = fixture()
        original = copy.deepcopy(source)
        admin, runtime = prepare.derive_pair(source)
        self.assertEqual(source, original)
        self.assertEqual(admin, source)
        self.assertEqual(set(admin), ADMIN_KEYS)
        self.assertEqual(set(runtime), RUNTIME_KEYS)
        self.assertEqual(runtime, {key: source[key] for key in RUNTIME_KEYS})
        self.assertIs(prepare.validate_pair(admin, runtime), True)

    def test_both_returned_objects_are_independent_deep_copies(self):
        source = fixture()
        admin, runtime = prepare.derive_pair(source)
        admin["keys"]["synthetic-key-id-6728"] = encoded(91)
        admin["providers"]["smtp"]["password"] = "changed-admin-only"
        self.assertEqual(source, fixture())
        self.assertEqual(runtime["keys"], fixture()["keys"])
        self.assertEqual(runtime["providers"], fixture()["providers"])
        runtime["providers"]["smtp"]["password"] = "changed-runtime-only"
        self.assertEqual(source, fixture())
        self.assertEqual(admin["providers"]["smtp"]["password"], "changed-admin-only")

    def test_both_supported_tls_modes(self):
        for mode, port in (("starttls", 587), ("implicit_tls", 465)):
            with self.subTest(mode=mode):
                source = fixture()
                source["providers"]["smtp"].update(tls_mode=mode, port=port)
                self.assertIs(prepare.validate_pair(*prepare.derive_pair(source)), True)

    def test_multiple_existing_keys_are_preserved_without_generation(self):
        source = fixture()
        source["keys"]["synthetic-retired-id"] = encoded(53)
        admin, runtime = prepare.derive_pair(source)
        self.assertEqual(admin["keys"], source["keys"])
        self.assertEqual(runtime["keys"], source["keys"])

    def test_missing_or_extra_admin_fields_fail(self):
        for key in ADMIN_KEYS:
            with self.subTest(missing=key):
                source = fixture()
                del source[key]
                self.assert_config_error(lambda: prepare.derive_pair(source))
        for key in ("extra", "telegram", "deployment_plan", "database", "installation"):
            with self.subTest(extra=key):
                source = fixture()
                source[key] = ERROR_SENTINEL
                self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_non_objects_and_wrong_profile_fail(self):
        for value in (None, [], "config", 1, True):
            with self.subTest(value=repr(value)):
                self.assert_config_error(lambda: prepare.derive_pair(value))
        for profile in (None, "FULL", "", "official_login_only_v1", PROFILE + " "):
            with self.subTest(profile=profile):
                source = fixture()
                source["deployment_profile"] = profile
                self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_no_extra_provider_or_smtp_field(self):
        for key in ("telegram", "feishu", "web_ai", "secretref", "anything"):
            with self.subTest(provider=key):
                source = fixture()
                source["providers"][key] = {"secret": ERROR_SENTINEL}
                self.assert_config_error(lambda: prepare.derive_pair(source))
        source = fixture()
        source["providers"]["smtp"]["unexpected"] = ERROR_SENTINEL
        self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_missing_smtp_fields_and_wrong_containers_fail(self):
        for key in fixture()["providers"]["smtp"]:
            with self.subTest(missing=key):
                source = fixture()
                del source["providers"]["smtp"][key]
                self.assert_config_error(lambda: prepare.derive_pair(source))
        for value in (None, [], "smtp", {}, True):
            for destination in ("providers", "smtp"):
                with self.subTest(destination=destination, value=repr(value)):
                    source = fixture()
                    if destination == "providers":
                        source["providers"] = value
                    else:
                        source["providers"]["smtp"] = value
                    self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_port_is_integer_in_range_not_bool_or_string(self):
        for port in (0, -1, 65536, 1.0, 587.0, True, False, "587", None):
            with self.subTest(port=repr(port)):
                source = fixture()
                source["providers"]["smtp"]["port"] = port
                self.assert_config_error(lambda: prepare.derive_pair(source))
        for port in (1, 65535):
            source = fixture()
            source["providers"]["smtp"]["port"] = port
            self.assertIs(prepare.validate_pair(*prepare.derive_pair(source)), True)

    def test_smtp_host_rejects_url_whitespace_and_control_characters(self):
        for host in (None, "", True, "https://smtp.example.invalid", "smtp.example.invalid/path",
                     "smtp example.invalid", "smtp.example.invalid\r", "smtp.example.invalid\n",
                     "smtp.example.invalid\x00", "-bad.example.invalid", "bad..example.invalid"):
            with self.subTest(host=repr(host)):
                source = fixture()
                source["providers"]["smtp"]["host"] = host
                self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_prepared_pair_satisfies_existing_pure_runtime_context_validator(self):
        # Only the existing pure validator is invoked, never factory, plan,
        # application construction, configuration loading or provider actions.
        from scripts import pr122_customer_ops as ops
        admin, runtime = prepare.derive_pair(fixture())
        with patch.object(ops, "factory", side_effect=AssertionError("Factory forbidden")) as factory, \
             patch.object(ops, "load_config", side_effect=AssertionError("Configuration read forbidden")) as load_config, \
             patch.object(ops, "Center", side_effect=AssertionError("Application creation forbidden")) as center:
            self.assertIs(ops.validate_runtime_contexts(admin, runtime), True)
        factory.assert_not_called()
        load_config.assert_not_called()
        center.assert_not_called()

    def test_plaintext_or_unknown_tls_modes_fail(self):
        for mode in (None, "", "none", "ssl", "tls", "STARTTLS", False):
            with self.subTest(mode=repr(mode)):
                source = fixture()
                source["providers"]["smtp"]["tls_mode"] = mode
                self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_mail_addresses_must_be_full_single_addresses(self):
        bad = (None, "", "local-user", "@example.invalid", "user@", "two@example.invalid,other@example.invalid",
               "Display Name <user@example.invalid>", "a b@example.invalid", "a@example.invalid\r", "a@example.invalid\n")
        for field in ("username", "sender"):
            for value in bad:
                with self.subTest(field=field, value=repr(value)):
                    source = fixture()
                    source["providers"]["smtp"][field] = value
                    self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_password_rejects_empty_non_string_and_control_delimiters(self):
        for value in (None, "", False, 123, "abc\rdef", "abc\ndef", "abc\x00def"):
            with self.subTest(value=repr(value)):
                source = fixture()
                source["providers"]["smtp"]["password"] = value
                self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_key_material_must_be_strict_base64_of_exactly_32_bytes(self):
        invalid = (None, 32, "", "not-base64!", encoded(17) + "\n", " " + encoded(17),
                   base64.b64encode(b"a" * 31).decode(), base64.b64encode(b"a" * 33).decode(),
                   encoded(17).rstrip("="), "☃")
        for field in ("keys", "backup_key", "authority_verify_key"):
            for value in invalid:
                with self.subTest(field=field, value=repr(value)):
                    source = fixture()
                    if field == "keys":
                        source[field][source["active_key"]] = value
                    else:
                        source[field] = value
                    self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_empty_or_bad_key_mapping_and_unresolved_active_key_fail(self):
        for value in (None, [], "key", {}, {"": encoded(17)}):
            with self.subTest(keys=repr(value)):
                source = fixture()
                source["keys"] = value
                self.assert_config_error(lambda: prepare.derive_pair(source))
        for value in (None, "", "missing-id", [], 1):
            with self.subTest(active=repr(value)):
                source = fixture()
                source["active_key"] = value
                self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_backup_reference_required(self):
        for value in (None, "", False, 1):
            with self.subTest(value=repr(value)):
                source = fixture()
                source["backup_key_ref"] = value
                self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_runtime_forbids_admin_only_unknown_and_missing_fields(self):
        for key in RUNTIME_KEYS:
            admin, runtime = prepare.derive_pair(fixture())
            del runtime[key]
            with self.subTest(missing=key):
                self.assert_config_error(lambda: prepare.validate_pair(admin, runtime))
        for key in ("backup_key", "backup_key_ref", "authority_verify_key", "unknown"):
            admin, runtime = prepare.derive_pair(fixture())
            runtime[key] = ERROR_SENTINEL
            with self.subTest(extra=key):
                self.assert_config_error(lambda: prepare.validate_pair(admin, runtime))

    def test_runtime_must_equal_admin_derived_fields(self):
        changes = (
            ("deployment_profile", "FULL"),
            ("keys", {"synthetic-key-id-6728": encoded(101)}),
            ("active_key", "different-id"),
        )
        for field, value in changes:
            admin, runtime = prepare.derive_pair(fixture())
            runtime[field] = value
            with self.subTest(field=field):
                self.assert_config_error(lambda: prepare.validate_pair(admin, runtime))
        for field, value in (("password", "different-valid-password"), ("port", 465),
                             ("sender", "different@synthetic-example.invalid")):
            admin, runtime = prepare.derive_pair(fixture())
            runtime["providers"]["smtp"][field] = value
            with self.subTest(smtp=field):
                self.assert_config_error(lambda: prepare.validate_pair(admin, runtime))

    def test_report_is_redacted_and_always_not_installable(self):
        admin, runtime = prepare.derive_pair(fixture())
        report = prepare.redacted_report(admin, runtime)
        self.assertIsInstance(report, dict)
        self.assert_redacted(report)
        self.assertIn("NOT_INSTALLABLE", json.dumps(report))

    def test_report_cannot_certify_invalid_pair(self):
        admin, runtime = prepare.derive_pair(fixture())
        runtime["providers"]["smtp"]["password"] = "different-secret"
        self.assert_config_error(lambda: prepare.redacted_report(admin, runtime))


class InteractiveAndCliTests(OfflineOnly):
    def test_collect_requires_both_input_and_output_tty_before_secret_input(self):
        for stdin_tty, stdout_tty in ((False, False), (True, False), (False, True)):
            with self.subTest(stdin_tty=stdin_tty, stdout_tty=stdout_tty):
                input_stream = TTY() if stdin_tty else io.StringIO()
                output_stream = TTY() if stdout_tty else io.StringIO()
                with patch.object(prepare.sys, "stdin", input_stream), \
                     patch.object(prepare.sys, "stdout", output_stream), \
                     patch.object(getpass, "getpass") as prompt:
                    self.assert_config_error(prepare.collect_interactive)
                    prompt.assert_not_called()

    def test_getpass_warning_fails_closed_without_printing_secret(self):
        def unsafe_getpass(*args, **kwargs):
            warnings.warn(ERROR_SENTINEL, getpass.GetPassWarning)
            return SYNTHETIC_PASSWORD
        output = TTY()
        errors = io.StringIO()
        with patch.object(prepare.sys, "stdin", TTY()), \
             patch.object(prepare.sys, "stdout", output), \
             patch.object(prepare.sys, "stderr", errors), \
             patch.object(getpass, "getpass", side_effect=unsafe_getpass), \
             patch("builtins.input", return_value="synthetic-key-id-6728"):
            self.assert_config_error(prepare.collect_interactive)
        self.assert_redacted(output.getvalue() + errors.getvalue())

    def test_successful_collection_hides_all_fields_and_preserves_existing_values(self):
        output, errors = TTY(), io.StringIO()
        with patch.object(prepare.sys, "stdin", TTY()), \
             patch.object(prepare.sys, "stdout", output), \
             patch.object(prepare.sys, "stderr", errors), \
             patch.object(getpass, "getpass", side_effect=interactive_values()) as get_secret, \
             patch("builtins.input", side_effect=AssertionError("Visible input is forbidden")):
            admin, runtime = prepare.collect_interactive()
        self.assertEqual(admin, fixture())
        self.assertEqual(get_secret.call_count, len(interactive_values()))
        self.assertIs(prepare.validate_pair(admin, runtime), True)
        self.assert_redacted(output.getvalue() + errors.getvalue())

    def test_every_confirmation_must_match(self):
        for repeat_index in (2, 4, 7, 14):
            values = interactive_values()
            values[repeat_index] = "different-synthetic-confirmation"
            output = TTY()
            with self.subTest(repeat_index=repeat_index), \
                 patch.object(prepare.sys, "stdin", TTY()), \
                 patch.object(prepare.sys, "stdout", output), \
                 patch.object(getpass, "getpass", side_effect=values):
                self.assert_config_error(prepare.collect_interactive)
            self.assert_redacted(output.getvalue())

    def test_hidden_input_eof_interrupt_or_exception_is_sanitized(self):
        for exception in (EOFError(ERROR_SENTINEL), KeyboardInterrupt(ERROR_SENTINEL), OSError(ERROR_SENTINEL)):
            output, errors = TTY(), io.StringIO()
            with self.subTest(exception=type(exception).__name__), \
                 patch.object(prepare.sys, "stdin", TTY()), \
                 patch.object(prepare.sys, "stdout", output), \
                 patch.object(prepare.sys, "stderr", errors), \
                 patch.object(getpass, "getpass", side_effect=exception):
                self.assert_config_error(prepare.collect_interactive)
            self.assert_redacted(output.getvalue() + errors.getvalue())

    def test_interactive_port_requires_decimal_ascii_integer(self):
        for port in ("587.0", " 587", "587 ", "+587", "1e3", "０２５", "", "65536", "0"):
            values = interactive_values()
            values[9] = port
            with self.subTest(port=port), patch.object(prepare.sys, "stdin", TTY()), \
                 patch.object(prepare.sys, "stdout", TTY()), \
                 patch.object(getpass, "getpass", side_effect=values):
                self.assert_config_error(prepare.collect_interactive)

    def test_in_memory_cli_never_writes_files(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(prepare.sys, "stdout", output), \
             patch.object(prepare.sys, "stderr", errors), \
             patch.object(prepare, "collect_interactive", return_value=prepare.derive_pair(fixture())), \
             patch.object(prepare, "write_bundle", side_effect=AssertionError("Unexpected disk write")) as write:
            self.assertEqual(prepare.main([]), 0)
        write.assert_not_called()
        self.assert_redacted(output.getvalue() + errors.getvalue())
        self.assertIn("NOT_INSTALLABLE", output.getvalue())

    def test_protected_paths_fail_before_input_or_any_filesystem_open(self):
        for root in ("/etc", "/var", "/usr", "/run", "/proc", "/sys", "/dev", "/root"):
            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(root=root), patch.object(prepare.sys, "stdout", output), \
                 patch.object(prepare.sys, "stderr", errors), \
                 patch.object(prepare, "collect_interactive") as collect, \
                 patch.object(os, "open", side_effect=AssertionError("Protected path touched")) as opened:
                result = prepare.main(["--output", root + "/synthetic-output"])
            self.assertNotEqual(result, 0)
            collect.assert_not_called()
            opened.assert_not_called()
            self.assert_redacted(output.getvalue() + errors.getvalue())

    def test_cli_rejects_secret_and_online_arguments_before_collecting(self):
        for args in (("--password", ERROR_SENTINEL), ("--config", ERROR_SENTINEL),
                     ("--install",), ("--smtp-test",), ("--allow-root",),
                     ("--generate-keys",), ("--output", "/unused", "--password", ERROR_SENTINEL)):
            output = io.StringIO()
            errors = io.StringIO()
            with self.subTest(args=args), patch.object(prepare.sys, "stdout", output), \
                 patch.object(prepare.sys, "stderr", errors), \
                 patch.object(prepare, "collect_interactive") as collect:
                try:
                    result = prepare.main(list(args))
                except SystemExit as error:
                    result = error.code
                self.assertNotEqual(result, 0)
                collect.assert_not_called()
                self.assert_redacted(output.getvalue() + errors.getvalue())

    def test_cli_sanitizes_unexpected_exceptions_and_interrupts(self):
        for exception in (OSError(ERROR_SENTINEL), ValueError(ERROR_SENTINEL), KeyboardInterrupt(ERROR_SENTINEL)):
            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(exception=type(exception).__name__), \
                 patch.object(prepare.sys, "stdout", output), \
                 patch.object(prepare.sys, "stderr", errors), \
                 patch.object(prepare, "collect_interactive", side_effect=exception):
                result = prepare.main([])
            self.assertIsInstance(result, int)
            self.assertNotEqual(result, 0)
            self.assert_redacted(output.getvalue() + errors.getvalue())


class BundleBoundaryTests(OfflineOnly):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-login-prepare-", dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.parent.chmod(0o700)
        self.output = self.parent / "offline-output"

    def write(self):
        return prepare.write_bundle(self.output, fixture())

    def assert_valid_bundle(self):
        self.assertEqual({path.name for path in self.output.iterdir()}, BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        for name in BUNDLE_FILES:
            path = self.output / name
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.stat().st_uid, os.getuid())
        admin = json.loads((self.output / "config.json").read_text())
        runtime = json.loads((self.output / "runtime.json").read_text())
        self.assertIs(prepare.validate_pair(admin, runtime), True)
        self.assertEqual(admin, fixture())
        self.assertEqual(set(runtime), RUNTIME_KEYS)
        report = prepare.inspect_bundle(self.output)
        self.assert_redacted(report)
        self.assertIn("NOT_INSTALLABLE", json.dumps(report))
        self.assert_redacted((self.output / "PREPARATION.json").read_text())

    def test_private_new_directory_is_atomically_published_and_inspectable(self):
        report = self.write()
        self.assert_redacted(report)
        self.assertIn("NOT_INSTALLABLE", json.dumps(report))
        self.assert_valid_bundle()
        self.assertEqual({path.name for path in self.parent.iterdir()}, {self.output.name})

    def test_permissive_umask_does_not_expose_output(self):
        old = os.umask(0)
        try:
            self.write()
        finally:
            os.umask(old)
        self.assert_valid_bundle()

    def test_root_is_refused_even_with_safe_output_parent(self):
        with patch.object(os, "geteuid", return_value=0), patch.object(os, "getuid", return_value=0):
            self.assert_config_error(self.write)
        self.assertFalse(self.output.exists())

    def test_existing_directory_is_never_replaced_or_modified(self):
        self.output.mkdir(mode=0o700)
        sentinel = self.output / "unrelated-existing-file"
        sentinel.write_text(ERROR_SENTINEL)
        self.assert_config_error(self.write)
        self.assertEqual(sentinel.read_text(), ERROR_SENTINEL)
        self.assertEqual({path.name for path in self.output.iterdir()}, {sentinel.name})

    def test_existing_file_is_never_replaced(self):
        self.output.write_text(ERROR_SENTINEL)
        self.assert_config_error(self.write)
        self.assertEqual(self.output.read_text(), ERROR_SENTINEL)

    def test_existing_valid_bundle_is_never_overwritten(self):
        self.write()
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.assert_config_error(self.write)
        after = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.assertEqual(before, after)

    def test_output_symlinks_are_rejected_even_if_dangling(self):
        for dangling in (False, True):
            with self.subTest(dangling=dangling):
                target = self.parent / ("missing" if dangling else "real")
                if not dangling:
                    target.mkdir(mode=0o700)
                self.output.symlink_to(target, target_is_directory=True)
                self.assert_config_error(self.write)
                self.assertTrue(self.output.is_symlink())
                self.output.unlink()
                if not dangling:
                    self.assertEqual(list(target.iterdir()), [])

    def test_symlinked_parent_is_rejected(self):
        real = self.parent / "real"
        real.mkdir(mode=0o700)
        link = self.parent / "linked"
        link.symlink_to(real, target_is_directory=True)
        self.assert_config_error(lambda: prepare.write_bundle(link / "new", fixture()))
        self.assertEqual(list(real.iterdir()), [])

    def test_non_private_parent_is_rejected(self):
        for mode in (0o755, 0o750, 0o770, 0o777):
            with self.subTest(mode=oct(mode)):
                self.parent.chmod(mode)
                try:
                    self.assert_config_error(self.write)
                finally:
                    self.parent.chmod(0o700)
                self.assertFalse(self.output.exists())

    def test_group_writable_ancestor_is_rejected(self):
        ancestor = self.parent / "shared-ancestor"
        ancestor.mkdir(mode=0o770)
        ancestor.chmod(0o770)
        private = ancestor / "private-parent"
        private.mkdir(mode=0o700)
        self.assert_config_error(lambda: prepare.write_bundle(private / "output", fixture()))
        self.assertEqual(list(private.iterdir()), [])

    def test_output_files_are_opened_with_exclusive_no_follow_flags(self):
        real_open = os.open
        creates = []
        def spy_open(path, flags, mode=0o777, *args, **kwargs):
            if flags & os.O_CREAT:
                creates.append((os.fspath(path), flags, mode))
            return real_open(path, flags, mode, *args, **kwargs)
        with patch.object(os, "open", side_effect=spy_open):
            self.write()
        self.assertGreaterEqual(len(creates), 3)
        for filename, flags, mode in creates:
            with self.subTest(filename=filename):
                self.assertTrue(flags & os.O_EXCL)
                self.assertTrue(flags & os.O_NOFOLLOW)
                self.assertEqual(mode, 0o600)

    def test_short_writes_are_completed_before_publication(self):
        real_write = os.write
        def short_write(fd, data):
            return real_write(fd, data[:max(1, min(7, len(data)))])
        with patch.object(os, "write", side_effect=short_write):
            self.write()
        self.assert_valid_bundle()

    def test_failed_staging_directory_is_private_and_not_inspectable(self):
        with patch.object(os, "write", side_effect=OSError(ERROR_SENTINEL)):
            self.assert_config_error(self.write)
        stages = list(self.parent.iterdir())
        self.assertTrue(stages)
        self.assertFalse(self.output.exists())
        for path in stages:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            self.assert_config_error(lambda: prepare.inspect_bundle(path))
            for child in path.iterdir():
                self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o600)

    def test_readback_corruption_prevents_publication(self):
        real_write = os.write
        corrupted = False
        def corrupt_first_write(fd, data):
            nonlocal corrupted
            if not corrupted:
                corrupted = True
                altered = b"!" + bytes(data[1:])
                return real_write(fd, altered)
            return real_write(fd, data)
        with patch.object(os, "write", side_effect=corrupt_first_write):
            self.assert_config_error(self.write)
        self.assertFalse(self.output.exists())

    def test_post_rename_fsync_failure_is_unknown_never_success_or_retry(self):
        real_fsync = os.fsync
        def fail_after_publication(fd):
            if self.output.exists():
                raise OSError(ERROR_SENTINEL)
            return real_fsync(fd)
        with patch.object(os, "fsync", side_effect=fail_after_publication):
            error = self.assert_config_error(self.write)
        self.assertEqual(error.code, "PUBLISH_DURABILITY_UNKNOWN")
        self.assertTrue(self.output.exists())
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.assert_config_error(self.write)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_non_linux_atomic_publication_is_refused_without_fallback(self):
        with patch.object(prepare.sys, "platform", "unsupported-platform"):
            error = self.assert_config_error(self.write)
        self.assertEqual(error.code, "ATOMIC_PUBLISH_UNAVAILABLE")
        self.assertFalse(self.output.exists())

    def test_write_failure_and_zero_length_write_cannot_publish_valid_output(self):
        for effect in (OSError(ERROR_SENTINEL), lambda fd, data: 0):
            with self.subTest(effect=repr(effect)), patch.object(os, "write", side_effect=effect):
                self.assert_config_error(self.write)
            self.assertFalse(self.output.exists())

    def test_open_failure_cannot_publish_output(self):
        real_open = os.open
        def fail_create(path, flags, mode=0o777, *args, **kwargs):
            if flags & os.O_CREAT:
                raise OSError(ERROR_SENTINEL)
            return real_open(path, flags, mode, *args, **kwargs)
        with patch.object(os, "open", side_effect=fail_create):
            self.assert_config_error(self.write)
        self.assertFalse(self.output.exists())

    def test_fsync_failure_before_publication_fails_closed(self):
        with patch.object(os, "fsync", side_effect=OSError(ERROR_SENTINEL)):
            self.assert_config_error(self.write)
        self.assertFalse(self.output.exists())

    def test_atomic_rename_failure_cannot_publish_output(self):
        with patch.object(prepare, "_rename_noreplace", side_effect=OSError(ERROR_SENTINEL)):
            self.assert_config_error(self.write)
        self.assertFalse(self.output.exists())

    def test_keyboard_interrupt_during_write_leaves_no_valid_output(self):
        with patch.object(os, "write", side_effect=KeyboardInterrupt(ERROR_SENTINEL)):
            try:
                self.write()
            except (KeyboardInterrupt, prepare.ConfigError):
                pass
            else:
                self.fail("An interrupted write must not report success")
        self.assertFalse(self.output.exists())

    def test_concurrent_destination_creation_cannot_be_overwritten(self):
        real_rename = prepare._rename_noreplace
        def race(*args, **kwargs):
            self.output.mkdir(mode=0o700)
            (self.output / "concurrent-owner").write_text(ERROR_SENTINEL)
            return real_rename(*args, **kwargs)
        with patch.object(prepare, "_rename_noreplace", side_effect=race):
            self.assert_config_error(self.write)
        self.assertEqual((self.output / "concurrent-owner").read_text(), ERROR_SENTINEL)
        self.assertEqual({path.name for path in self.output.iterdir()}, {"concurrent-owner"})

    def test_missing_preparation_marker_is_not_a_valid_bundle(self):
        self.write()
        (self.output / "PREPARATION.json").unlink()
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_existing_partial_bundle_is_not_valid(self):
        self.output.mkdir(mode=0o700)
        for name, value in (("config.json", fixture()), ("runtime.json", prepare.derive_pair(fixture())[1])):
            path = self.output / name
            path.write_text(json.dumps(value))
            path.chmod(0o600)
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_unknown_file_or_subdirectory_invalidates_bundle(self):
        self.write()
        unexpected = self.output / "unexpected"
        unexpected.write_text(ERROR_SENTINEL)
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))
        unexpected.unlink()
        unexpected.mkdir(mode=0o700)
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_modified_preparation_marker_invalidates_bundle(self):
        self.write()
        marker = self.output / "PREPARATION.json"
        marker.write_text(json.dumps({"status": "NOT_INSTALLABLE", "unexpected": ERROR_SENTINEL}))
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_changed_config_and_runtime_cannot_reuse_old_marker(self):
        self.write()
        for name in ("config.json", "runtime.json"):
            path = self.output / name
            content = json.loads(path.read_text())
            content["providers"]["smtp"]["password"] = "changed-consistent-synthetic-secret"
            path.write_text(json.dumps(content))
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_pair_mismatch_cannot_be_inspected_as_valid(self):
        self.write()
        path = self.output / "runtime.json"
        content = json.loads(path.read_text())
        content["providers"]["smtp"]["password"] = "changed-only-runtime"
        path.write_text(json.dumps(content))
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_inspect_rejects_symlink_files(self):
        self.write()
        path = self.output / "runtime.json"
        outside = self.parent / "outside-runtime.json"
        outside.write_bytes(path.read_bytes())
        outside.chmod(0o600)
        path.unlink()
        path.symlink_to(outside)
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_inspect_rejects_non_private_files_or_directory(self):
        self.write()
        for name in BUNDLE_FILES:
            with self.subTest(name=name):
                path = self.output / name
                path.chmod(0o644)
                try:
                    self.assert_config_error(lambda: prepare.inspect_bundle(self.output))
                finally:
                    path.chmod(0o600)
        self.output.chmod(0o755)
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_inspect_rejects_malformed_or_duplicate_json_fields(self):
        self.write()
        path = self.output / "config.json"
        original = path.read_bytes()
        for malformed in (b"not-json", b"[]", b'{"deployment_profile":"FULL","deployment_profile":"OFFICIAL_LOGIN_ONLY_V1"}'):
            with self.subTest(malformed=malformed):
                path.write_bytes(malformed)
                self.assert_config_error(lambda: prepare.inspect_bundle(self.output))
                path.write_bytes(original)

    def test_inspect_rejects_hardlinked_files(self):
        self.write()
        os.link(self.output / "config.json", self.parent / "hardlink-config")
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_inspect_rejects_fifo_without_blocking(self):
        self.write()
        path = self.output / "runtime.json"
        path.unlink()
        os.mkfifo(path, 0o600)
        self.assert_config_error(lambda: prepare.inspect_bundle(self.output))

    def test_missing_or_noncanonical_parent_path_is_not_created(self):
        missing = self.parent / "not-created" / "output"
        self.assert_config_error(lambda: prepare.write_bundle(missing, fixture()))
        self.assertFalse(missing.parent.exists())
        for path in ("relative-output", str(self.parent) + "/../output", str(self.output) + "/", str(self.parent) + "//output"):
            with self.subTest(path=path):
                self.assert_config_error(lambda: prepare.write_bundle(path, fixture()))
        self.assertFalse(self.output.exists())

    def test_foreign_owned_ancestor_is_rejected_without_changing_ownership(self):
        real_fstat = os.fstat
        def foreign_owner(fd):
            result = real_fstat(fd)
            return SimpleNamespace(st_mode=result.st_mode, st_uid=os.getuid() + 3000)
        with patch.object(os, "fstat", side_effect=foreign_owner):
            self.assert_config_error(self.write)
        self.assertFalse(self.output.exists())

    def test_inspect_rejects_empty_or_oversized_files(self):
        self.write()
        path = self.output / "runtime.json"
        original = path.read_bytes()
        for raw in (b"", b"x" * (1_048_576 + 1)):
            with self.subTest(size=len(raw)):
                path.write_bytes(raw)
                self.assert_config_error(lambda: prepare.inspect_bundle(self.output))
                path.write_bytes(original)

    def test_cli_unsupported_platform_fails_before_prompting(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(prepare.sys, "platform", "unsupported-platform"), \
             patch.object(prepare.sys, "stdout", output), \
             patch.object(prepare.sys, "stderr", errors), \
             patch.object(prepare, "collect_interactive") as collect:
            result = prepare.main(["--output", str(self.output)])
        self.assertNotEqual(result, 0)
        collect.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assert_redacted(output.getvalue() + errors.getvalue())

    def test_cli_existing_destination_fails_before_prompting(self):
        self.output.mkdir(mode=0o700)
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(prepare.sys, "stdout", output), \
             patch.object(prepare.sys, "stderr", errors), \
             patch.object(prepare, "collect_interactive") as collect:
            result = prepare.main(["--output", str(self.output)])
        self.assertNotEqual(result, 0)
        collect.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])
        self.assert_redacted(output.getvalue() + errors.getvalue())

    def _assert_actual_rename_then_fault_is_unknown(self, exception):
        real_rename = prepare._rename_noreplace
        renamed = []
        def publish_then_fail(*args, **kwargs):
            real_rename(*args, **kwargs)
            renamed.append(True)
            raise exception
        with patch.object(prepare, "_rename_noreplace", side_effect=publish_then_fail):
            error = self.assert_config_error(self.write)
        self.assertEqual(renamed, [True], "The real atomic rename must have completed")
        self.assertEqual(error.code, "PUBLISH_DURABILITY_UNKNOWN")
        self.assert_valid_bundle()
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        retry_error = self.assert_config_error(self.write)
        self.assertEqual(retry_error.code, "OUTPUT_EXISTS")
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_real_rename_then_keyboard_interrupt_reports_unknown(self):
        self._assert_actual_rename_then_fault_is_unknown(KeyboardInterrupt(ERROR_SENTINEL))

    def test_real_rename_then_eof_reports_unknown(self):
        self._assert_actual_rename_then_fault_is_unknown(EOFError(ERROR_SENTINEL))

    def test_real_rename_then_oserror_reports_unknown(self):
        self._assert_actual_rename_then_fault_is_unknown(OSError(ERROR_SENTINEL))

    def test_real_rename_then_unclassified_config_error_reports_unknown(self):
        self._assert_actual_rename_then_fault_is_unknown(prepare.ConfigError("BUNDLE_JSON"))

    def test_trace_interrupts_after_helper_returns_before_published_assignment(self):
        source = (ROOT / "tools/pr122_login_config_prepare.py").read_text()
        tree = ast.parse(source)
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == "write_bundle")
        assignments = [node for node in ast.walk(function)
                       if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "published"
                               for target in node.targets)
                       and isinstance(node.value, ast.Constant) and node.value.value is True]
        self.assertEqual(len(assignments), 1, "Find the exact post-helper published=True assignment")
        assignment_line = assignments[0].lineno
        for index, exception in enumerate((KeyboardInterrupt(ERROR_SENTINEL),
                                           EOFError(ERROR_SENTINEL), OSError(ERROR_SENTINEL))):
            self.output = self.parent / ("trace-window-" + str(index))
            observations = []
            def trace(frame, event, arg):
                if (frame.f_code is prepare.write_bundle.__code__ and event == "line"
                        and frame.f_lineno == assignment_line):
                    observations.append({
                        "published": frame.f_locals.get("published"),
                        "publication_attempted": frame.f_locals.get("publication_attempted"),
                        "target_exists": self.output.is_dir(),
                    })
                    raise exception
                return trace
            with self.subTest(exception=type(exception).__name__):
                previous_trace = prepare.sys.gettrace()
                try:
                    prepare.sys.settrace(trace)
                    error = self.assert_config_error(self.write)
                finally:
                    prepare.sys.settrace(previous_trace)
                self.assertEqual(observations, [{"published": False,
                                                 "publication_attempted": True,
                                                 "target_exists": True}])
                self.assertEqual(error.code, "PUBLISH_DURABILITY_UNKNOWN")
                self.assert_valid_bundle()

    def test_unclassified_helper_faults_after_attempt_are_always_unknown(self):
        exceptions = (KeyboardInterrupt(ERROR_SENTINEL), EOFError(ERROR_SENTINEL),
                      OSError(ERROR_SENTINEL), RuntimeError(ERROR_SENTINEL),
                      prepare.ConfigError("BUNDLE_JSON"))
        for index, exception in enumerate(exceptions):
            self.output = self.parent / ("helper-fault-" + str(index))
            with self.subTest(exception=type(exception).__name__), \
                 patch.object(prepare, "_rename_noreplace", side_effect=exception):
                error = self.assert_config_error(self.write)
            self.assertEqual(error.code, "PUBLISH_DURABILITY_UNKNOWN")
            self.assertFalse(self.output.exists())

    def test_known_atomic_helper_rejections_preserve_specific_nonpublication_code(self):
        for index, code in enumerate(("OUTPUT_EXISTS", "ATOMIC_PUBLISH_UNAVAILABLE", "OUTPUT_FAILED")):
            self.output = self.parent / ("known-rejection-" + str(index))
            with self.subTest(code=code), \
                 patch.object(prepare, "_rename_noreplace", side_effect=prepare.ConfigError(code)):
                error = self.assert_config_error(self.write)
            self.assertEqual(error.code, code)
            self.assertFalse(self.output.exists())

    def test_parent_fsync_interruptions_after_real_publication_report_unknown(self):
        real_fsync = os.fsync
        for index, exception in enumerate((KeyboardInterrupt(ERROR_SENTINEL), EOFError(ERROR_SENTINEL))):
            self.output = self.parent / ("parent-fsync-interrupt-" + str(index))
            def fail_after_publication(fd):
                if self.output.exists():
                    raise exception
                return real_fsync(fd)
            with self.subTest(exception=type(exception).__name__), \
                 patch.object(os, "fsync", side_effect=fail_after_publication):
                error = self.assert_config_error(self.write)
            self.assertEqual(error.code, "PUBLISH_DURABILITY_UNKNOWN")
            self.assert_valid_bundle()

    def test_real_publication_then_final_close_fault_reports_unknown(self):
        real_close = os.close
        for close_index in (1, 2):
            for exception_type in (KeyboardInterrupt, EOFError, OSError):
                self.output = self.parent / ("close-window-" + str(close_index) + "-" + exception_type.__name__)
                closed_after_publication = []
                raised = []
                def close_then_fault(fd):
                    real_close(fd)
                    if self.output.exists():
                        closed_after_publication.append(fd)
                        if len(closed_after_publication) == close_index:
                            raised.append(True)
                            raise exception_type(ERROR_SENTINEL)
                with self.subTest(close_index=close_index, exception=exception_type.__name__), \
                     patch.object(os, "close", side_effect=close_then_fault):
                    error = self.assert_config_error(self.write)
                self.assertEqual(raised, [True])
                self.assertEqual(error.code, "PUBLISH_DURABILITY_UNKNOWN")
                self.assertEqual(len(closed_after_publication), 2, "Both final FDs must be closed despite the fault")
                for fd in closed_after_publication:
                    with self.assertRaises(OSError):
                        os.fstat(fd)
                self.assert_valid_bundle()

    def test_main_actual_write_success_then_wrapper_fault_reports_unknown(self):
        real_write_bundle = prepare.write_bundle
        exception_factories = (
            ("KeyboardInterrupt", KeyboardInterrupt), ("EOFError", EOFError),
            ("OSError", OSError),
            ("ConfigError", lambda ignored: prepare.ConfigError("PUBLISH_DURABILITY_UNKNOWN")),
        )
        for index, (exception_name, exception_type) in enumerate(exception_factories):
            self.output = self.parent / ("main-return-window-" + str(index))
            completed = []
            def write_then_fault(*args, **kwargs):
                real_write_bundle(*args, **kwargs)
                completed.append(True)
                raise exception_type(ERROR_SENTINEL)
            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(exception=exception_name), \
                 patch.object(prepare, "write_bundle", side_effect=write_then_fault), \
                 patch.object(prepare, "collect_interactive", return_value=prepare.derive_pair(fixture())), \
                 patch.object(prepare.sys, "stdout", output), \
                 patch.object(prepare.sys, "stderr", errors):
                result = prepare.main(["--output", str(self.output)])
            self.assertEqual(completed, [True])
            self.assertNotEqual(result, 0)
            self.assertEqual(output.getvalue(), "")
            response = json.loads(errors.getvalue())
            self.assertEqual(response["error"], "PUBLISH_DURABILITY_UNKNOWN")
            self.assertEqual(response["state"], "UNKNOWN")
            self.assertEqual(response["production"], "NOT_INSTALLABLE")
            self.assert_redacted(errors.getvalue())
            self.assert_valid_bundle()

    def test_main_output_fault_after_actual_publication_reports_unknown(self):
        for index, exception_type in enumerate((KeyboardInterrupt, EOFError, OSError)):
            self.output = self.parent / ("main-output-window-" + str(index))
            failures = []
            class FailingOutput(io.StringIO):
                def write(stream, text):
                    failures.append(True)
                    raise exception_type(ERROR_SENTINEL)
            output, errors = FailingOutput(), io.StringIO()
            with self.subTest(exception=exception_type.__name__), \
                 patch.object(prepare, "collect_interactive", return_value=prepare.derive_pair(fixture())), \
                 patch.object(prepare.sys, "stdout", output), \
                 patch.object(prepare.sys, "stderr", errors):
                result = prepare.main(["--output", str(self.output)])
            self.assertEqual(failures, [True])
            self.assertNotEqual(result, 0)
            self.assertEqual(output.getvalue(), "")
            response = json.loads(errors.getvalue())
            self.assertEqual(response["error"], "PUBLISH_DURABILITY_UNKNOWN")
            self.assertEqual(response["state"], "UNKNOWN")
            self.assertEqual(response["production"], "NOT_INSTALLABLE")
            self.assert_redacted(errors.getvalue())
            self.assert_valid_bundle()

    def test_cli_success_only_reports_redacted_not_installable_summary(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(prepare, "collect_interactive", return_value=prepare.derive_pair(fixture())), \
             patch.object(prepare.sys, "stdout", output), \
             patch.object(prepare.sys, "stderr", errors):
            result = prepare.main(["--output", str(self.output)])
        self.assertEqual(result, 0)
        self.assert_redacted(output.getvalue() + errors.getvalue())
        self.assertIn("NOT_INSTALLABLE", output.getvalue())
        self.assert_valid_bundle()


class CanonicalPathRegressionTests(OfflineOnly):
    @staticmethod
    def rejected_paths():
        # Strings are intentional: Path would erase some noncanonical spellings
        # before the API received them. No protected directory is ever opened.
        for root in ("etc", "var", "usr", "run", "proc", "sys", "dev", "root"):
            for path in (
                "//" + root + "/synthetic-output",
                "///" + root + "/synthetic-output",
                "////" + root + "/synthetic-output",
                "/" + root + "//synthetic-output",
                "/" + root + "/./synthetic-output",
                "/" + root + "/../" + root + "/synthetic-output",
                "//" + root + "//synthetic-output",
                "///" + root + "/./synthetic-output",
                "/" + root + "/private//synthetic-output",
                "/" + root + "/private/./synthetic-output",
                "/" + root + "/private/../synthetic-output",
                "/" + root + "/synthetic-output/",
            ):
                yield path
        # Noncanonical spelling is forbidden for ordinary roots too; this
        # cannot be implemented as only a special-case protected-root filter.
        for path in ("//synthetic/offline-output", "///synthetic/offline-output",
                     "/synthetic//offline-output", "/synthetic/./offline-output",
                     "/synthetic/../offline-output", "/synthetic/offline-output/"):
            yield path

    def assert_rejected_without_io(self, operation):
        for path in self.rejected_paths():
            with self.subTest(path=path), \
                 patch.object(os, "open", side_effect=AssertionError("Path must fail before os.open")) as opened, \
                 patch("builtins.open", side_effect=AssertionError("Path must fail before open")) as builtin_open, \
                 patch.object(prepare, "collect_interactive", side_effect=AssertionError("Path must fail before input")) as collect:
                error = self.assert_config_error(lambda: operation(path))
            self.assertEqual(error.code, "PATH_POLICY")
            opened.assert_not_called()
            builtin_open.assert_not_called()
            collect.assert_not_called()

    def test_path_rejects_every_noncanonical_protected_alias_without_io(self):
        self.assert_rejected_without_io(prepare._path)

    def test_preflight_rejects_every_noncanonical_protected_alias_without_io(self):
        self.assert_rejected_without_io(prepare._preflight_output)

    def test_write_rejects_every_noncanonical_protected_alias_without_io(self):
        self.assert_rejected_without_io(lambda path: prepare.write_bundle(path, fixture()))

    def test_inspect_rejects_every_noncanonical_protected_alias_without_io(self):
        self.assert_rejected_without_io(prepare.inspect_bundle)

    def test_main_rejects_every_noncanonical_protected_alias_before_io_and_input(self):
        for path in self.rejected_paths():
            output, errors = io.StringIO(), io.StringIO()
            with self.subTest(path=path), \
                 patch.object(prepare.sys, "stdout", output), \
                 patch.object(prepare.sys, "stderr", errors), \
                 patch.object(os, "open", side_effect=AssertionError("Path must fail before os.open")) as opened, \
                 patch("builtins.open", side_effect=AssertionError("Path must fail before open")) as builtin_open, \
                 patch.object(prepare, "collect_interactive", side_effect=AssertionError("Path must fail before input")) as collect:
                result = prepare.main(["--output", path])
            self.assertNotEqual(result, 0)
            self.assertEqual(json.loads(errors.getvalue())["error"], "PATH_POLICY")
            self.assertEqual(json.loads(errors.getvalue())["state"], "NOT_PREPARED")
            self.assertEqual(output.getvalue(), "")
            self.assert_redacted(errors.getvalue())
            opened.assert_not_called()
            builtin_open.assert_not_called()
            collect.assert_not_called()


class SourceIsolationTests(OfflineOnly):
    def test_tool_imports_no_provider_network_process_or_application_module(self):
        source = (ROOT / "tools/pr122_login_config_prepare.py").read_text()
        tree = ast.parse(source)
        forbidden = {"socket", "smtplib", "subprocess", "requests", "urllib", "http", "httpx", "scripts", "pr122_customer_core", "pr122_customer_http"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for name in modules:
                self.assertNotIn(name.split(".")[0], forbidden)
        forbidden_calls = {"system", "popen", "fork", "forkpty", "execv", "execve", "spawnv", "spawnve", "getenv"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                    self.assertNotIn(node.func.attr, forbidden_calls)

    def test_unknown_error_content_cannot_become_a_reported_error_code(self):
        error = prepare.ConfigError(ERROR_SENTINEL)
        self.assert_redacted(str(error))
        self.assert_redacted(error.code)
        self.assertRegex(error.code, r"^[A-Z][A-Z0-9_]*$")


if __name__ == "__main__":
    unittest.main()
