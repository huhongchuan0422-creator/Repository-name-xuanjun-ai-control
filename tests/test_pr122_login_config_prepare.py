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


INITIAL = "FIRST_LOGIN_ONLY_V1"
INITIAL_HOST = "iZvt5t8tlrm8oiZ"


def first_fixture():
    value = fixture()
    value.pop("authority_verify_key")
    value["initialization_mode"] = INITIAL
    return value


def initial_assessment():
    # Synthetic statements exercise syntax/binding, never target authenticity.
    observation = {"target": INITIAL_HOST, "observed_unix": 100000,
                   "subject": "CANONICAL_IDENTITY_INVENTORY",
                   "synthetic_source_note": "NOT_TARGET_EVIDENCE"}
    assessment = {"schema": 1, "target": INITIAL_HOST,
                  "deployment_profile": PROFILE, "initialization_mode": INITIAL,
                  "manifest_sha256": "a" * 64, "target_state": "ABSENT",
                  "identity_decision": "NO_EXISTING_AUTHORITATIVE_IDENTITY",
                  "observation_ref": "/var/lib/xuanjun-customer-preflight/synthetic-observation.json",
                  "observation_sha256": prepare.digest(prepare.canonical(observation)),
                  "observed_unix": 100000}
    return assessment, observation


class FirstLoginSchemaTests(OfflineOnly):
    def test_explicit_first_pair_omits_authority_and_runtime_marker(self):
        source = first_fixture()
        original = copy.deepcopy(source)
        admin, runtime = prepare.derive_pair(source)
        self.assertEqual(source, original)
        self.assertEqual(admin, source)
        self.assertEqual(set(admin), ADMIN_KEYS - {"authority_verify_key"} | {"initialization_mode"})
        self.assertEqual(set(runtime), RUNTIME_KEYS)
        self.assertNotIn("authority_verify_key", admin)
        self.assertNotIn("initialization_mode", runtime)
        self.assertIs(prepare.validate_pair(admin, runtime), True)

    def test_first_pair_deep_copies_and_retains_all_original_key_versions(self):
        source = first_fixture()
        source["keys"]["synthetic-retired-id"] = encoded(53)
        original = copy.deepcopy(source)
        admin, runtime = prepare.derive_pair(source)
        self.assertEqual(admin["keys"], original["keys"])
        self.assertEqual(runtime["keys"], original["keys"])
        self.assertEqual(admin["backup_key_ref"], original["backup_key_ref"])
        admin["keys"][source["active_key"]] = encoded(91)
        runtime["providers"]["smtp"]["password"] = "changed-runtime-only"
        self.assertEqual(source, original)
        self.assertEqual(runtime["keys"], original["keys"])
        self.assertEqual(admin["providers"], original["providers"])

    def test_first_rejects_any_present_authority_field(self):
        for value in (None, "", encoded(41), False, ERROR_SENTINEL):
            with self.subTest(authority=value):
                source = first_fixture()
                source["authority_verify_key"] = value
                self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_unknown_marker_full_and_unmarked_authority_omission_rejected(self):
        for value in (None, "", True, {}, "FIRST", INITIAL + " "):
            with self.subTest(marker=repr(value)):
                source = first_fixture()
                source["initialization_mode"] = value
                self.assert_config_error(lambda: prepare.derive_pair(source))
        for mode in ("FULL", None, "LOGIN_ONLY"):
            with self.subTest(profile=mode):
                source = first_fixture()
                source["deployment_profile"] = mode
                self.assert_config_error(lambda: prepare.derive_pair(source))
        source = first_fixture()
        source.pop("initialization_mode")
        self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_first_requires_every_data_backup_and_reference_field(self):
        for key in ("keys", "active_key", "backup_key", "backup_key_ref"):
            with self.subTest(missing=key):
                source = first_fixture()
                source.pop(key)
                self.assert_config_error(lambda: prepare.derive_pair(source))
        for field in ("backup_key", "backup_key_ref"):
            for value in (None, "", False):
                with self.subTest(field=field, value=repr(value)):
                    source = first_fixture()
                    source[field] = value
                    self.assert_config_error(lambda: prepare.derive_pair(source))

    def test_first_backup_key_must_differ_from_every_data_key(self):
        source = first_fixture()
        for key_id in (source["active_key"], "synthetic-retired-id"):
            with self.subTest(key_id=key_id):
                value = copy.deepcopy(source)
                value["keys"][key_id] = value["backup_key"]
                error = self.assert_config_error(lambda: prepare.derive_pair(value))
                self.assertEqual(error.code, "INITIAL_KEY_SEPARATION")

    def test_first_runtime_whitelist_and_exact_binding_remain(self):
        for key, value in (("initialization_mode", INITIAL), ("authority_verify_key", encoded(41)),
                           ("backup_key", encoded(29)), ("unknown", "value")):
            with self.subTest(extra=key):
                admin, runtime = prepare.derive_pair(first_fixture())
                runtime[key] = value
                self.assert_config_error(lambda: prepare.validate_pair(admin, runtime))
        for key, value in (("deployment_profile", "FULL"), ("active_key", "other"),
                           ("keys", {"synthetic-key-id-6728": encoded(91)}),
                           ("providers", {"smtp": {}})):
            with self.subTest(mismatch=key):
                admin, runtime = prepare.derive_pair(first_fixture())
                runtime[key] = value
                self.assert_config_error(lambda: prepare.validate_pair(admin, runtime))

    def test_first_reuse_has_no_generation_or_claim_of_custody(self):
        source = first_fixture()
        with patch.object(prepare, "prepare_initial_pair", side_effect=AssertionError("No regeneration")) as generated:
            admin, runtime = prepare.derive_pair(source)
            report = prepare.redacted_report(admin, runtime)
        generated.assert_not_called()
        self.assertEqual(admin, source)
        self.assertEqual(report["production"], "NOT_INSTALLABLE")
        self.assertEqual(report["key_provenance"], "NOT_VERIFIED")
        self.assertEqual(report["target_acceptance"], "NOT_VERIFIED")
        self.assert_redacted(report)


class SyntheticInitialMaterialTests(OfflineOnly):
    def setUp(self):
        super().setUp()
        self.assessment, self.observation = initial_assessment()
        self.options = {"manifest_sha256": "a" * 64, "now": 100001,
                        "key_id": "synthetic-initial-key", "backup_key_ref": "synthetic-planned-custody",
                        "smtp": copy.deepcopy(fixture()["providers"]["smtp"])}
        self.entropy = self.stack.enter_context(patch.object(
            prepare.os, "urandom", side_effect=AssertionError("Default entropy forbidden")))

    def generate(self, entropy, assessment=None, observation=None, **overrides):
        source = self.observation if observation is None else observation
        if type(source) is dict:
            source = prepare.canonical(source)
        return prepare.prepare_initial_pair(
            self.assessment if assessment is None else assessment,
            source,
            **{**self.options, **overrides}, entropy_source=entropy)

    def test_lone_surrogate_inputs_are_rejected_before_any_entropy(self):
        from unittest.mock import Mock
        valid_raw = prepare.canonical(self.observation)
        for surrogate in ("\ud800", "\udc00"):
            for field in ("password", "username", "sender", "backup_key_ref", "key_id"):
                with self.subTest(field=field, codepoint=hex(ord(surrogate))):
                    options = copy.deepcopy(self.options)
                    value = "synthetic-" + surrogate + "-value"
                    if field in ("password", "username", "sender"):
                        options["smtp"][field] = value + ("@example.invalid" if field != "password" else "")
                    else:
                        options[field] = value
                    entropy = Mock(side_effect=[b"D" * 32, b"B" * 32])
                    self.assert_config_error(lambda: prepare.prepare_initial_pair(
                        self.assessment, valid_raw, **options, entropy_source=entropy))
                    entropy.assert_not_called()
            with self.subTest(field="assessment.observation_ref", codepoint=hex(ord(surrogate))):
                assessment = {**self.assessment, "observation_ref":
                              "/var/lib/xuanjun-customer-preflight/synthetic-" + surrogate + ".json"}
                entropy = Mock(side_effect=[b"D" * 32, b"B" * 32])
                self.assert_config_error(lambda: self.generate(entropy, assessment=assessment, observation=valid_raw))
                entropy.assert_not_called()
            for kind in ("top_value", "nested_value", "top_key", "nested_key", "invalid_utf8"):
                with self.subTest(source=kind, codepoint=hex(ord(surrogate))):
                    body = copy.deepcopy(self.observation)
                    if kind in ("top_value", "invalid_utf8"):
                        body["extra"] = "synthetic-" + surrogate
                    elif kind == "nested_value":
                        body["extra"] = {"rows": [1, {"value": "synthetic-" + surrogate}]}
                    elif kind == "top_key":
                        body["synthetic-" + surrogate] = "value"
                    else:
                        body["extra"] = {"rows": [{"synthetic-" + surrogate: "value"}]}
                    raw = (json.dumps(body, ensure_ascii=False).encode("utf-8", "surrogatepass")
                           if kind == "invalid_utf8" else json.dumps(body, ensure_ascii=True).encode("utf-8"))
                    assessment = {**self.assessment, "observation_sha256": prepare.digest(raw)}
                    entropy = Mock(side_effect=[b"D" * 32, b"B" * 32])
                    self.assert_config_error(lambda: self.generate(entropy, assessment=assessment, observation=raw))
                    entropy.assert_not_called()
        # Scalar Unicode and valid JSON-escaped surrogate pairs remain valid.
        body = {**self.observation, "extra": {"rows": [{"测试": "\U0001f680"}]}}
        for escaped in (False, True):
            with self.subTest(valid_unicode_escaped=escaped):
                raw = json.dumps(body, ensure_ascii=escaped).encode("utf-8")
                assessment = {**self.assessment, "observation_sha256": prepare.digest(raw)}
                smtp = {**self.options["smtp"], "password": "synthetic-测试-\U0001f680"}
                entropy = Mock(side_effect=[b"D" * 32, b"B" * 32])
                admin, runtime = self.generate(entropy, assessment=assessment, observation=raw,
                                               smtp=smtp, backup_key_ref="synthetic-托管-\U0001f680")
                self.assertEqual(entropy.call_count, 2)
                self.assertEqual(admin["providers"]["smtp"], smtp)
                self.assertEqual(runtime["providers"]["smtp"], smtp)

    def test_entropy_callback_cannot_modify_the_validated_input_snapshot(self):
        from unittest.mock import Mock, call
        for mutate_on_call in (1, 2):
            with self.subTest(mutate_on_call=mutate_on_call):
                smtp = copy.deepcopy(self.options["smtp"])
                expected = copy.deepcopy(smtp)
                calls = []
                def injected(size):
                    calls.append(size)
                    if len(calls) == mutate_on_call:
                        smtp.update(password="synthetic-invalid-\ud800", host="https://changed.invalid",
                                    tls_mode="none", port=True, unexpected="synthetic-mutation")
                    return b"D" * 32 if len(calls) == 1 else b"B" * 32
                entropy = Mock(side_effect=injected)
                admin, runtime = self.generate(entropy, smtp=smtp)
                self.assertEqual(entropy.call_args_list, [call(32), call(32)])
                self.assertNotEqual(smtp, expected)
                self.assertEqual(admin["providers"]["smtp"], expected)
                self.assertEqual(runtime["providers"]["smtp"], expected)
                self.assertIs(prepare.validate_pair(admin, runtime), True)
                self.assertEqual(admin["backup_key_ref"], self.options["backup_key_ref"])

    def test_exactly_two_explicit_synthetic_values_and_no_extra_secret(self):
        from unittest.mock import Mock, call
        injected = Mock(side_effect=[b"D" * 32, b"B" * 32])
        before = copy.deepcopy((self.assessment, self.observation, self.options))
        admin, runtime = self.generate(injected)
        self.assertEqual(injected.call_args_list, [call(32), call(32)])
        self.assertEqual(admin["keys"], {self.options["key_id"]: base64.b64encode(b"D" * 32).decode()})
        self.assertEqual(admin["backup_key"], base64.b64encode(b"B" * 32).decode())
        self.assertEqual(admin["backup_key_ref"], self.options["backup_key_ref"])
        self.assertEqual(set(admin), ADMIN_KEYS - {"authority_verify_key"} | {"initialization_mode"})
        self.assertEqual(admin["initialization_mode"], INITIAL)
        self.assertEqual(set(runtime), RUNTIME_KEYS)
        self.assertEqual((self.assessment, self.observation, self.options), before)
        self.entropy.assert_not_called()

    def test_state_identity_and_profile_rejected_before_entropy(self):
        from unittest.mock import Mock
        cases = [("target_state", value) for value in ("UNKNOWN", "EXISTING", "RESTORE", "PARTIAL", "CONFLICT", None)]
        cases += [("identity_decision", value) for value in ("MAPPED_EXISTING", "UNKNOWN", "EXISTING", True)]
        cases += [("deployment_profile", "FULL"), ("initialization_mode", None), ("target", "foreign-host")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                assessment = copy.deepcopy(self.assessment)
                assessment[field] = value
                injected = Mock(side_effect=AssertionError("Entropy before eligibility"))
                error = self.assert_config_error(lambda: self.generate(injected, assessment=assessment))
                self.assertEqual(error.code, "INITIAL_ASSESSMENT")
                injected.assert_not_called()

    def test_exact_assessment_schema_and_source_binding_required_before_entropy(self):
        from unittest.mock import Mock
        invalid = []
        for key in self.assessment:
            value = copy.deepcopy(self.assessment)
            value.pop(key)
            invalid.append(value)
        invalid.extend((None, [], {}, {**self.assessment, "approved": True},
                        {**self.assessment, "schema": True},
                        {**self.assessment, "manifest_sha256": "b" * 64},
                        {**self.assessment, "observation_sha256": "G" * 64}))
        for value in invalid:
            with self.subTest(value=repr(value)):
                injected = Mock()
                operation = lambda: prepare.prepare_initial_pair(
                    value, prepare.canonical(self.observation), **self.options, entropy_source=injected)
                self.assert_config_error(operation)
                injected.assert_not_called()
        for field, value in (("target", "foreign-host"), ("observed_unix", 99999),
                             ("subject", "UNRELATED_OBSERVATION")):
            with self.subTest(observation=field):
                injected = Mock()
                observation = {**self.observation, field: value}
                assessment = {**self.assessment, "observation_sha256": prepare.digest(prepare.canonical(observation))}
                self.assert_config_error(lambda: self.generate(injected, assessment=assessment, observation=observation))
                injected.assert_not_called()

    def test_freshness_boundaries_and_exact_time_types(self):
        from unittest.mock import Mock
        for now in (100000, 118000, 100001.5):
            with self.subTest(allowed_now=now):
                injected = Mock(side_effect=[b"D" * 32, b"B" * 32])
                self.generate(injected, now=now)
                self.assertEqual(injected.call_count, 2)
        for now in (99999, 118001, True, "100001", float('nan'), float('inf'), -float('inf'), -1):
            with self.subTest(denied_now=repr(now)):
                injected = Mock()
                self.assert_config_error(lambda: self.generate(injected, now=now))
                injected.assert_not_called()
        for observed in (True, "100000", 100000.0, -1):
            with self.subTest(observed=repr(observed)):
                injected = Mock()
                self.assert_config_error(lambda: self.generate(
                    injected, assessment={**self.assessment, "observed_unix": observed},
                    observation={**self.observation, "observed_unix": observed}))
                injected.assert_not_called()

    def test_noncanonical_or_out_of_scope_observation_paths_rejected_before_entropy(self):
        from unittest.mock import Mock
        paths = ("relative.json", "/etc/secret", "/var/lib/xuanjun-customer-preflight/../outside",
                 "/var/lib/xuanjun-customer-preflight//source.json",
                 "/var/lib/xuanjun-customer-preflight/./source.json",
                 "/var/lib/xuanjun-customer-preflight", "//var/lib/xuanjun-customer-preflight/source.json")
        for path in paths:
            with self.subTest(path=path):
                injected = Mock()
                self.assert_config_error(lambda: self.generate(
                    injected, assessment={**self.assessment, "observation_ref": path}))
                injected.assert_not_called()

    def test_all_configuration_inputs_validated_before_entropy(self):
        from unittest.mock import Mock
        cases = ({"key_id": ""}, {"key_id": "bad/key"}, {"key_id": True},
                 {"backup_key_ref": ""}, {"backup_key_ref": None},
                 {"smtp": {}}, {"smtp": {**self.options["smtp"], "port": True}},
                 {"smtp": {**self.options["smtp"], "tls_mode": "none"}},
                 {"smtp": {**self.options["smtp"], "password": ""}})
        for options in cases:
            with self.subTest(options=repr(options)):
                injected = Mock()
                self.assert_config_error(lambda: self.generate(injected, **options))
                injected.assert_not_called()

    def test_missing_or_noncallable_entropy_has_no_default(self):
        import inspect
        signature = inspect.signature(prepare.prepare_initial_pair)
        self.assertIs(signature.parameters["entropy_source"].default, inspect.Parameter.empty)
        with self.assertRaises(TypeError):
            prepare.prepare_initial_pair(self.assessment, prepare.canonical(self.observation), **self.options)
        for value in (None, b"D" * 32, True, "os.urandom"):
            with self.subTest(value=repr(value)):
                error = self.assert_config_error(lambda: self.generate(value))
                self.assertEqual(error.code, "INITIAL_ENTROPY")
        self.entropy.assert_not_called()

    def test_bad_entropy_type_length_and_duplicates_are_not_retried(self):
        from unittest.mock import Mock
        for value in (None, "D" * 32, bytearray(b"D" * 32), b"", b"D" * 31, b"D" * 33):
            for position in (0, 1):
                with self.subTest(value=repr(value), position=position):
                    injected = Mock(side_effect=[value, b"B" * 32] if position == 0 else [b"D" * 32, value])
                    error = self.assert_config_error(lambda: self.generate(injected))
                    self.assertEqual(error.code, "INITIAL_ENTROPY")
                    self.assertLessEqual(injected.call_count, 2)
        injected = Mock(side_effect=[b"D" * 32, b"D" * 32])
        error = self.assert_config_error(lambda: self.generate(injected))
        self.assertEqual(error.code, "INITIAL_ENTROPY")
        self.assertEqual(injected.call_count, 2)

    def test_entropy_exceptions_are_sanitized_without_retry(self):
        from unittest.mock import Mock
        for error in (OSError(ERROR_SENTINEL), ValueError(ERROR_SENTINEL),
                      EOFError(ERROR_SENTINEL), KeyboardInterrupt(ERROR_SENTINEL)):
            for position in (0, 1):
                with self.subTest(error=type(error).__name__, position=position):
                    injected = Mock(side_effect=[error] if position == 0 else [b"D" * 32, error])
                    caught = self.assert_config_error(lambda: self.generate(injected))
                    self.assertEqual(caught.code, "INITIAL_ENTROPY")
                    self.assertEqual(injected.call_count, position + 1)

    def test_generation_is_pure_and_report_does_not_certify_real_custody(self):
        from unittest.mock import Mock
        injected = Mock(side_effect=[b"D" * 32, b"B" * 32])
        with patch.object(os, "open", side_effect=AssertionError("Filesystem forbidden")) as opened, \
             patch("builtins.open", side_effect=AssertionError("Filesystem forbidden")) as builtin_open, \
             patch.object(prepare, "write_bundle", side_effect=AssertionError("Publication forbidden")) as written:
            admin, runtime = self.generate(injected)
            report = prepare.redacted_report(admin, runtime)
        opened.assert_not_called()
        builtin_open.assert_not_called()
        written.assert_not_called()
        self.assertEqual(report["production"], "NOT_INSTALLABLE")
        self.assertEqual(report["key_provenance"], "NOT_VERIFIED")
        self.assertEqual(report["target_acceptance"], "NOT_VERIFIED")
        serialized = json.dumps(report)
        for secret in (*admin["keys"].values(), admin["backup_key"], self.options["backup_key_ref"]):
            self.assertNotIn(secret, serialized)

    def test_cli_cannot_select_initial_generation(self):
        for args in (("--initialization-mode", INITIAL), ("--first-login-only",),
                     ("--generate-keys",), ("--entropy-source", "synthetic")):
            with self.subTest(args=args), patch.object(prepare, "prepare_initial_pair") as generated, \
                 patch.object(prepare, "collect_interactive") as collect, \
                 patch.object(prepare.sys, "stdout", io.StringIO()), \
                 patch.object(prepare.sys, "stderr", io.StringIO()):
                self.assertNotEqual(prepare.main(list(args)), 0)
                generated.assert_not_called()
                collect.assert_not_called()

    def test_source_raw_digest_and_strict_json_precede_entropy(self):
        from unittest.mock import Mock
        valid = prepare.canonical(self.observation)
        duplicate = valid[:-1] + b',"synthetic_extra":1,"synthetic_extra":2}'
        nonfinite = valid[:-1] + b',"synthetic_extra":NaN}'
        overflow = valid[:-1] + b',"synthetic_extra":1e999}'
        nested_overflow = valid[:-1] + b',"synthetic_extra":{"rows":[1,{"value":-1e999}]}}'
        for source in (valid + b" ", self.observation, None, [], b"{not-json}",
                       duplicate, nonfinite, overflow, nested_overflow):
            with self.subTest(source=repr(source)):
                injected = Mock()
                assessment = dict(self.assessment)
                if type(source) is bytes and source != valid + b" ":
                    assessment["observation_sha256"] = prepare.digest(source)
                self.assert_config_error(lambda: prepare.prepare_initial_pair(
                    assessment, source, **self.options, entropy_source=injected))
                injected.assert_not_called()
        # A differently serialized but exactly hash-bound source is legitimate.
        source = json.dumps({**self.observation, "synthetic_extra": {"rows": [1.25, {"value": -2.5}]}}, indent=2).encode()
        injected = Mock(side_effect=[b"D" * 32, b"B" * 32])
        self.generate(injected, assessment={**self.assessment, "observation_sha256": prepare.digest(source)},
                      observation=source)
        self.assertEqual(injected.call_count, 2)


if __name__ == "__main__":
    unittest.main()
