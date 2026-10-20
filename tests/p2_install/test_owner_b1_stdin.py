"""Targeted B1 argv + original request pipe checks; no Docker/UK execution."""
import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(os.environ.get('P2_B1_OWNER_SCRIPT',
    str(Path(__file__).resolve().parents[2] / 'scripts/p2_b1_owner_first_install_20261020.py')))
spec = importlib.util.spec_from_file_location('owner_b1_operation', SCRIPT)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class OwnerB1StdinTests(unittest.TestCase):
    def test_three_actions_keep_stdin_open_without_tty(self):
        for action in ('execute', 'inspect', 'recover'):
            with self.subTest(action=action):
                argv = owner.command(action)
                self.assertEqual(argv[:3], ['/bin/docker', 'run', '--interactive'])
                self.assertEqual(argv.count('--interactive'), 1)
                self.assertTrue(set(argv).isdisjoint({'-t', '--tty', '-it', '-ti'}))
                self.assertFalse(any(a.startswith('--tty=') for a in argv))
                self.assertEqual(argv[-5:], ['-B', '-S', '-m', 'production.p2_artifacts', action])

    def test_main_passes_exact_execute_request_bytes_to_docker_client(self):
        tree = ast.parse(SCRIPT.read_text())
        loops = [n for n in ast.walk(tree) if isinstance(n, ast.For)
                 and isinstance(n.target, ast.Name) and n.target.id == 'action']
        self.assertEqual(len(loops), 1)
        self.assertEqual(ast.literal_eval(loops[0].iter), ('execute', 'inspect', 'recover'))
        calls = [n for n in ast.walk(loops[0]) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == 'run'
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == 'subprocess'
                 and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == 'args']
        self.assertEqual(len(calls), 1)
        value = next(k.value for k in calls[0].keywords if k.arg == 'input')
        self.assertIsInstance(value, ast.Subscript)
        self.assertEqual(value.value.id, 'files')
        self.assertEqual(ast.literal_eval(value.slice), 'execute-request.json')

    def test_three_original_requests_survive_real_child_stdin_byte_for_byte(self):
        unused_zip, files, unused_tools, request = owner.validate_payload()
        original = files['execute-request.json']
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         '21ec24e119516493577dc5a4019ba913f076306565171a1d3ebbaa9e9efb659b')
        self.assertEqual((request['installation_id'], request['batch_id'], request['attempt_id']),
                         ('p2-uk-isolated-20261020', 'b1-release', 'b1-release-a1'))
        for action in ('execute', 'inspect', 'recover'):
            with self.subTest(action=action):
                self.assertEqual(files[action + '-request.json'], original)
                # Real OS pipe check only. This is not Docker stdin acceptance.
                process = subprocess.run([sys.executable, '-I', '-B', '-S', '-c',
                    'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'],
                    input=files[action + '-request.json'], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=10)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(process.stdout, original)
                self.assertEqual(process.stderr, b'')


if __name__ == '__main__':
    unittest.main()
