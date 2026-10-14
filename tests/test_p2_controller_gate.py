import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "evidence" / "p2-native-wiring-work-20261012"

class P2ControllerGate(unittest.TestCase):
    def test_node_syntax_and_regressions(self):
        files = [
            ROOT / "controller" / "canonical.mjs",
            ROOT / "controller" / "strict-json.mjs",
            ROOT / "controller" / "workspace.mjs",
            ROOT / "controller" / "ledger.mjs",
            ROOT / "controller" / "controller.mjs",
            ROOT / "controller" / "host.mjs",
            ROOT / "controller" / "index.mjs",
            ROOT / "controller" / "plugin.mjs",
        ]
        for path in files:
            self.assertTrue(path.is_file() and not path.is_symlink(), str(path))
            result = subprocess.run(["node", "--check", str(path)], cwd=ROOT,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        for script in ["test_controller.mjs", "test_host.mjs"]:
            result = subprocess.run(["node", script], cwd=ROOT,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=20, check=False)
            self.assertEqual(result.returncode, 0,
                             result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace"))
        print("P2_CONTROLLER_EXACT_SOURCE_GATE_PASS; UK_RUNTIME=NOT_RUN; RELEASE=NOT_GRANTED")

if __name__ == "__main__":
    unittest.main()
