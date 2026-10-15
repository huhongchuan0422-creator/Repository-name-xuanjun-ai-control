from __future__ import print_function

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from korea.build_runtime_candidate import build_candidate


class KoreaInstallShellBehaviorTests(unittest.TestCase):
    """Execute the real shell transaction against disposable adapters and paths."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "root"; self.root.mkdir(mode=0o700)
        for name in ("opt", "var", "var/lib", "var/log", "etc", "etc/systemd",
                     "etc/systemd/system", "run", "run/lock"):
            (self.root / name).mkdir(mode=0o755, exist_ok=True)
        self.candidate = self.base / "candidate"
        manifest = build_candidate(self.candidate)
        self.manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.fakebin = self.base / "fakebin"; self.fakebin.mkdir()
        (self.fakebin / "python3.11").symlink_to(sys.executable)
        self._write_executable("systemctl", r'''#!/usr/bin/env bash
set -eu
root=${KOREA_CANDIDATE_TEST_ROOT:?}
case ${1:-} in
  is-enabled) printf 'disabled\n' ;;
  is-active) exit 1 ;;
  cat) cat "$root/etc/systemd/system/xuanjun-binance-shadow.service" ;;
  show)
    if [[ ${2:-} == xuanjun-binance-shadow.service ]]; then
      printf 'FragmentPath=%s\nDropInPaths=\nUser=xuanjun_binance\nGroup=xuanjun_binance\n' "$root/etc/systemd/system/xuanjun-binance-shadow.service"
      printf 'ExecStart={ path=/opt/xuanjun-binance/venv/bin/python ; argv[]=/opt/xuanjun-binance/venv/bin/python -B -I -m korea.migration_shadow_entry --continuous --config /etc/xuanjun-binance/shadow.json --acceptance-config /etc/xuanjun-binance/shadow-acceptance.json ; }\n'
    fi ;;
  daemon-reload|disable) : ;;
  *) : ;;
esac
''')
        self._write_executable("systemd-analyze", "#!/usr/bin/env bash\nexit 0\n")
        self._write_executable("cp", r'''#!/usr/bin/env bash
set -eu
if [[ ${KOREA_TEST_CP_FAIL:-0} == 1 ]]; then exit 41; fi
if [[ ${KOREA_TEST_CP_SLEEP:-0} == 1 ]]; then
  : >"${KOREA_CANDIDATE_TEST_ROOT}/cp-started"
  sleep 60
fi
exec /bin/cp "$@"
''')
        self.env = dict(os.environ)
        self.env.update({
            "KOREA_CANDIDATE_TEST_MODE": "1",
            "KOREA_CANDIDATE_TEST_ROOT": str(self.root),
            "PATH": str(self.fakebin) + os.pathsep + self.env.get("PATH", ""),
        })
        self.install = self.candidate / "migration-prep/korea/install-candidate.sh"

    def tearDown(self):
        self.temp.cleanup()

    def _write_executable(self, name, body):
        target = self.fakebin / name; target.write_text(body); target.chmod(0o755)

    def _run_install(self, candidate=None, manifest_sha=None, env=None):
        return subprocess.run(
            [str((candidate or self.candidate) / "migration-prep/korea/install-candidate.sh"),
             str(candidate or self.candidate), manifest_sha or self.manifest_sha],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=env or self.env, timeout=30, check=False,
        )

    @staticmethod
    def _rehash_candidate(candidate):
        manifest_path = candidate / "minimal-runtime-manifest.json"
        value = json.loads(manifest_path.read_text())
        for record in value["files"]:
            raw = (candidate / record["path"]).read_bytes()
            record["size"] = len(raw); record["sha256"] = hashlib.sha256(raw).hexdigest()
        content = "\n".join(item["path"] + "\0" + item["sha256"] for item in value["files"])
        value["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        manifest_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        manifest_path.chmod(0o600)
        return hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    def test_same_version_is_idempotent_but_different_version_holds(self):
        first = self._run_install()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self._run_install()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("ALREADY_INSTALLED=YES SAME_VERSION=YES", second.stdout)

        candidate_b = self.base / "candidate-b"; shutil.copytree(self.candidate, candidate_b)
        lock = candidate_b / "migration-prep/korea/requirements.lock"
        lock.write_text(lock.read_text() + "# distinct tested artifact\n")
        manifest_b = self._rehash_candidate(candidate_b)
        different = self._run_install(candidate_b, manifest_b)
        self.assertEqual(different.returncode, 2)
        self.assertIn("DIFFERENT_VERSION_REQUIRES_SEPARATE_APPROVED_UPGRADE", different.stderr)

    def test_exclusive_lock_and_partial_copy_cleanup_are_real_shell_behaviors(self):
        sleeping_env = dict(self.env); sleeping_env["KOREA_TEST_CP_SLEEP"] = "1"
        first = subprocess.Popen(
            [str(self.install), str(self.candidate), self.manifest_sha],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=sleeping_env, start_new_session=True,
        )
        marker = self.root / "cp-started"
        for _ in range(200):
            if marker.exists(): break
            time.sleep(0.02)
        self.assertTrue(marker.exists())
        busy = self._run_install()
        self.assertEqual(busy.returncode, 2)
        self.assertIn("INSTALL_TRANSACTION_BUSY", busy.stderr)
        os.killpg(first.pid, signal.SIGTERM)
        first.communicate(timeout=10)
        self.assertFalse((self.root / "run/xuanjun-binance-install.lock").exists())
        marker.unlink()

        failed_env = dict(self.env); failed_env["KOREA_TEST_CP_FAIL"] = "1"
        failed = self._run_install(env=failed_env)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((self.root / "etc/xuanjun-binance/install-transaction.json").exists())
        self.assertFalse((self.root / "opt/xuanjun-binance/current").exists())
        self.assertFalse((self.root / "etc/systemd/system/xuanjun-binance-shadow.service").exists())
        self.assertFalse((self.root / "run/xuanjun-binance-install.lock").exists())

    def test_sigterm_is_nonzero_and_cleans_only_attempt_owned_objects(self):
        env = dict(self.env); env["KOREA_TEST_CP_SLEEP"] = "1"
        process = subprocess.Popen(
            [str(self.install), str(self.candidate), self.manifest_sha],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
            start_new_session=True,
        )
        marker = self.root / "cp-started"
        for _ in range(200):
            if marker.exists(): break
            time.sleep(0.02)
        self.assertTrue(marker.exists())
        os.killpg(process.pid, signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        self.assertNotEqual(process.returncode, 0, stdout + stderr)
        self.assertIn("INTERRUPTED_SIGTERM", stderr)
        self.assertFalse((self.root / "run/xuanjun-binance-install.lock").exists())
        self.assertFalse((self.root / "etc/xuanjun-binance/install-transaction.json").exists())

    def test_replaced_unit_is_refused_by_check_and_uninstall(self):
        installed = self._run_install()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        transaction = self.root / "etc/xuanjun-binance/install-transaction.json"
        unit = self.root / "etc/systemd/system/xuanjun-binance-shadow.service"
        unit.write_text(unit.read_text() + "\n# replaced\n")
        check = subprocess.run([
            str(self.candidate / "migration-prep/korea/check-candidate.sh"),
            "--expected-transaction", str(transaction),
            "--expected-manifest-sha256", self.manifest_sha,
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env, check=False)
        self.assertEqual(check.returncode, 2)
        self.assertIn("UNIT_IDENTITY_MISMATCH", check.stderr)
        transaction_sha = hashlib.sha256(transaction.read_bytes()).hexdigest()
        uninstall = subprocess.run([
            str(self.candidate / "migration-prep/korea/uninstall-candidate.sh"),
            "--confirm-disabled-candidate-only", "--transaction-sha256", transaction_sha,
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env, check=False)
        self.assertEqual(uninstall.returncode, 2)
        self.assertIn("REPLACED_UNIT_REFUSED", uninstall.stderr)

    def test_successful_uninstall_removes_only_transaction_owned_objects(self):
        installed = self._run_install()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        transaction = self.root / "etc/xuanjun-binance/install-transaction.json"
        value = json.loads(transaction.read_text())
        transaction_sha = hashlib.sha256(transaction.read_bytes()).hexdigest()
        result = subprocess.run([
            str(self.candidate / "migration-prep/korea/uninstall-candidate.sh"),
            "--confirm-disabled-candidate-only", "--transaction-sha256", transaction_sha,
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STATE_CREDENTIALS_EVIDENCE_IDENTITY=PRESERVED", result.stdout)
        for path in value["owned_objects"]:
            self.assertFalse(Path(path).exists() or Path(path).is_symlink(), path)
        receipt = (self.root / "var/lib/xuanjun-binance/evidence" /
                   ("uninstalled-" + value["transaction_id"] + ".json"))
        self.assertTrue(receipt.is_file())
        self.assertTrue((self.root / "var/lib/xuanjun-binance").is_dir())


if __name__ == "__main__":
    unittest.main()
