"""Positive mixed CLI contract; failures are real FAIL, never expectedFailure.

Stage exact pinned files under P2_MIXED_CLI_SOURCE_ROOT before running.
No network, injected adapters, production configuration, or attempt quota.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import socket
from contextlib import contextmanager
import subprocess
import sys
import tempfile
import unittest

PINS = {'production/p2_artifacts/__init__.py': {'commit': 'ea31dbbec2a8710b964efb38fa2975684bbd9739', 'git_blob': 'fd4d33afc0352f413c7a6d114759618f1a9fb6d8'}, 'production/p2_artifacts/__main__.py': {'commit': 'ea31dbbec2a8710b964efb38fa2975684bbd9739', 'git_blob': '9cb7e62c1ffb040149cf467460c084069a412a98'}, 'production/p2_artifacts/installer.py': {'commit': 'ea31dbbec2a8710b964efb38fa2975684bbd9739', 'git_blob': '2be13684afb604360e5db1acc2645a70d7fff20b'}, 'production/p2_runtime/__init__.py': {'commit': '499bcc43f4c992b21035c22446ccc4d915873fb1', 'git_blob': '61ae1b4fc311403ec6fa416464c4e71243b232b8'}, 'production/p2_install/coordinator.py': {'commit': 'a4a1614b985a3b45f050906f1768039f24453cf2', 'git_blob': 'd5bf5b5c2443f6daf71fee0cda6db61eafe4a486'}, 'production/p2_install/journal.py': {'commit': 'a4a1614b985a3b45f050906f1768039f24453cf2', 'git_blob': '6c4e198949d8e2379ed6d47b6882b47534d4dd46'}, 'tests/p2_install/test_component_chain_integration.py': {'commit': 'a4a1614b985a3b45f050906f1768039f24453cf2', 'git_blob': '74b380a6081a832d24af3d7a65667292adc36802'}}


def retain_tree(source, target):
    """Copy ordinary entries only. Never open or remove special entries."""
    rows = []
    def visit(path, destination, relative):
        try:
            info = path.lstat()
            kind = ("directory" if stat.S_ISDIR(info.st_mode) else
                    "file" if stat.S_ISREG(info.st_mode) else
                    "socket" if stat.S_ISSOCK(info.st_mode) else
                    "fifo" if stat.S_ISFIFO(info.st_mode) else
                    "symlink" if stat.S_ISLNK(info.st_mode) else "special")
            row = {"path": relative, "type": kind, "mode": stat.S_IMODE(info.st_mode),
                   "size": info.st_size, "inode": info.st_ino, "mtime_ns": info.st_mtime_ns}
            rows.append(row)
            if kind == "directory":
                destination.mkdir(mode=0o700, parents=True, exist_ok=True)
                for child in sorted(path.iterdir()):
                    visit(child, destination / child.name, str(Path(relative) / child.name))
            elif kind == "file":
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as src:
                    current = os.fstat(src.fileno())
                    if not stat.S_ISREG(current.st_mode) or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
                        raise OSError("ENTRY_CHANGED")
                    h = hashlib.sha256()
                    with destination.open("xb") as out:
                        while True:
                            data = src.read(65536)
                            if not data:
                                break
                            out.write(data)
                            h.update(data)
                        out.flush()
                        os.fsync(out.fileno())
                    destination.chmod(stat.S_IMODE(info.st_mode))
                    row["sha256"] = h.hexdigest()
            # socket/fifo/symlink/device: metadata only, no dereference.
        except OSError as exc:
            rows.append({"path": relative, "collection_error": type(exc).__name__,
                         "errno": exc.errno})
    visit(Path(source), Path(target), ".")
    return rows


def save_result(evidence, report, replacements=()):
    """Public JSON uses path aliases; raw request hashes refer to original bytes."""
    def redact(value):
        if isinstance(value, str):
            for original, alias in sorted(replacements, key=lambda pair: -len(pair[0])):
                value = value.replace(original, alias)
            return value
        if isinstance(value, list):
            return [redact(v) for v in value]
        if isinstance(value, dict):
            return {k: redact(v) for k, v in value.items()}
        return value
    pending = evidence / "result.json.pending"
    with pending.open("w") as out:
        json.dump(redact(report), out, indent=2, sort_keys=True)
        out.flush()
        os.fsync(out.fileno())
    os.replace(pending, evidence / "result.json")
    fd = os.open(evidence, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def evidence_session(evidence, report, state):
    try:
        yield
    except BaseException as exc:
        report["execution_error"] = {"type": type(exc).__name__, "detail": str(exc)}
        report["outcome"] = "FAIL"
        raise
    else:
        report["outcome"] = "PASS"
    finally:
        try:
            if state.get("root") is not None:
                report["filesystem"] = retain_tree(state["root"], evidence / "retained-state")
        except Exception as exc:
            report["collection_error"] = type(exc).__name__
        report["evidence_status"] = "PARTIAL" if report.get("collection_error") or any(
            "collection_error" in row for row in report.get("filesystem", [])) else "COMPLETE"
        replacements = [(str(evidence), "<EVIDENCE>")] + state.get("aliases", [])
        if state.get("root") is not None:
            replacements.append((str(state["root"]), "<FIXTURE>"))
        replacements.append((sys.executable, "<PYTHON>"))
        save_result(evidence, report, replacements)
        print("MIXED_CLI_EVIDENCE=" + str(evidence), flush=True)

class MixedCLIIntegration(unittest.TestCase):
    def check_chain(self, runtime_flag):
        source = Path(os.environ.get("P2_MIXED_CLI_SOURCE_ROOT", Path(__file__).resolve().parents[2]))
        evidence = Path(tempfile.mkdtemp(prefix="p2-mixed-cli-", dir=os.environ.get("P2_MIXED_CLI_EVIDENCE_DIR")))
        report = {"scope": "ISOLATED_TEST_ONLY", "python": sys.version,
                  "runtime_flag": runtime_flag, "sources": {}, "calls": [], "requests": [],
                  "test_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "pins_role": "FAILURE_BASELINE_NOT_FIXED_ACCEPTANCE",
                  "quota": "NONE", "production_executed": False}
        state = {"aliases": [(str(source.resolve()), "<SOURCE>")]}
        fixture = None
        try:
            with evidence_session(evidence, report, state):
                stage = evidence / "source"
                source_hashes = report["sources"]
                for relative, pin in PINS.items():
                    raw = (source / relative).read_bytes()
                    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                    self.assertEqual(blob, pin["git_blob"], relative)
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    target.chmod(0o400)
                    source_hashes[relative] = dict(pin, sha256=hashlib.sha256(raw).hexdigest())
                sys.path.insert(0, str(stage))
                try:
                    spec = importlib.util.spec_from_file_location("pinned_chain_fixture", stage / "tests/p2_install/test_component_chain_integration.py")
                    fixture_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(fixture_module)
                finally:
                    sys.path.remove(str(stage))
                fixture = fixture_module.ExactComponentChain()
                fixture.setUp()  # Reuse only filesystem/archive/service fixture, no injected calls.
                state["root"] = fixture.coord.parent
                records = report["calls"]
                fixture.plan["batches"] = ["artifact", "service"]
                plan = evidence / "plan.json"
                plan.write_text(json.dumps(fixture.plan))
                report["plan"] = fixture.plan
                for batch, request in (("artifact", fixture.artifact_req), ("service", fixture.runtime_req)):
                    request_path = evidence / (batch + "-request.json")
                    raw = json.dumps(request, sort_keys=True).encode()
                    request_path.write_bytes(raw)
                    report["requests"].append({"request": request, "sha256": hashlib.sha256(raw).hexdigest()})
                    for action in ("execute", "inspect", "recover"):
                        command = [sys.executable, "-B", "-m", "production.p2_install.coordinator", action,
                            "--root", str(fixture.coord), "--plan", str(plan), "--request", str(request_path),
                            "--component-root", "artifact=" + str(fixture.artifacts),
                            "--component-root", "service=" + str(fixture.runtime)]
                        if runtime_flag:
                            command.append("--runtime")
                        record = {"batch": batch, "action": action, "argv": command,
                            "request_sha256": hashlib.sha256(raw).hexdigest(), "exit_code": None}
                        records.append(record)
                        try:
                            result = subprocess.run(command, cwd=stage, capture_output=True, timeout=20,
                                env={"PATH": os.defpath, "HOME": str(evidence), "PYTHONDONTWRITEBYTECODE": "1"})
                        except subprocess.TimeoutExpired as exc:
                            record.update(timeout=True, stdout=(exc.stdout or b"").decode(errors="replace"),
                                          stderr=(exc.stderr or b"").decode(errors="replace"))
                            raise
                        record.update(exit_code=result.returncode,
                            stdout=result.stdout.decode(errors="replace"), stderr=result.stderr.decode(errors="replace"))
                        try:
                            record["response"] = json.loads(record["stdout"])
                        except ValueError:
                            record["response"] = None
                effects = {"program_exists": fixture.program.is_file(), "socket_exists": fixture.socket.exists()}
                report["effects"] = effects
                failures = [{"batch": r["batch"], "action": r["action"], "exit_code": r["exit_code"],
                    "response": r["response"]} for r in records if r["exit_code"] != 0 or
                    not isinstance(r["response"], dict) or r["response"].get("status") != "COMMITTED"]
                self.assertEqual(failures, [], json.dumps(failures, sort_keys=True))
                self.assertTrue(effects["program_exists"])
                self.assertTrue(effects["socket_exists"])
        finally:
            if fixture is not None:
                # Preserve the original synthetic state as well as its snapshot.
                # Reuse fixture process cleanup, suppress only directory deletion.
                fixture.tmp._finalizer.detach()
                fixture.tmp.cleanup = lambda: None
                fixture.tearDown()

    def test_mixed_cli_default(self):
        self.check_chain(False)

    def test_mixed_cli_runtime_flag(self):
        self.check_chain(True)


class EvidenceCollectionTests(unittest.TestCase):
    def test_ordinary_files_fifo_and_symlink_without_opening_special_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state"
            source.mkdir()
            (source / "empty").mkdir()
            (source / "data").write_bytes(b"ordinary")
            os.mkfifo(source / "pipe")
            (source / "link").symlink_to(root / "absent")
            rows = retain_tree(source, root / "retained")
            kinds = {r["path"]: r["type"] for r in rows}
            self.assertEqual(kinds["pipe"], "fifo")
            self.assertEqual(kinds["link"], "symlink")
            self.assertEqual((root / "retained/data").read_bytes(), b"ordinary")
            self.assertTrue((root / "retained/empty").is_dir())
            self.assertTrue(stat.S_ISFIFO((source / "pipe").lstat().st_mode))
            self.assertEqual(next(r["sha256"] for r in rows if r["path"] == "data"), hashlib.sha256(b"ordinary").hexdigest())

    def test_live_socket_fifo_symlink_and_ordinary_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "state"
            source.mkdir()
            (source / "nested").mkdir()
            (source / "nested" / "data").write_bytes(b"persisted")
            (source / "escape").symlink_to(root / "outside")
            os.mkfifo(source / "pipe")
            with socket.socket(socket.AF_UNIX) as live:
                live.bind(str(source / "app.sock"))
                report = {}
                with evidence_session(root, report, {"root": source}):
                    pass
                types = {r["path"]: r["type"] for r in report["filesystem"]}
                self.assertEqual(types["app.sock"], "socket")
                self.assertEqual(types["pipe"], "fifo")
                self.assertEqual(types["escape"], "symlink")
                self.assertEqual((root / "retained-state/nested/data").read_bytes(), b"persisted")
                self.assertFalse((root / "retained-state/app.sock").exists())
                self.assertTrue(stat.S_ISSOCK((source / "app.sock").lstat().st_mode))
                self.assertEqual(json.loads((root / "result.json").read_text())["outcome"], "PASS")

    def test_exception_result_persisted_with_partial_calls_and_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {"calls": [{"stdout": "partial", "request_sha256": "a" * 64}]}
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                with evidence_session(root, report, {}):
                    raise RuntimeError("synthetic " + str(root))
            saved = json.loads((root / "result.json").read_text())
            self.assertEqual(saved["outcome"], "FAIL")
            self.assertEqual(saved["calls"], report["calls"])
            self.assertIn("<EVIDENCE>", saved["execution_error"]["detail"])
            self.assertNotIn(str(root), (root / "result.json").read_text())

    def test_collection_failure_still_persists_execution_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {"calls": []}
            with evidence_session(root, report, {"root": root / "absent"}):
                pass
            saved = json.loads((root / "result.json").read_text())
            self.assertEqual(saved["filesystem"][0]["collection_error"], "FileNotFoundError")
            self.assertEqual(saved["outcome"], "PASS")
            self.assertEqual(saved["evidence_status"], "PARTIAL")

if __name__ == "__main__":
    unittest.main()
