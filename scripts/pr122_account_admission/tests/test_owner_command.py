import importlib.util
from pathlib import Path
import tempfile
import unittest

P = Path(__file__).resolve().parents[1] / 'build_owner_command.py'
spec = importlib.util.spec_from_file_location('owner_command', P)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class CommandTests(unittest.TestCase):
    def test_commit_must_be_full_immutable(self):
        for commit in ('main', 'abc', 'a'*40+';id', 'G'*40):
            with self.assertRaises(ValueError): m.render(commit, '.')
    def test_hashes_before_execution_and_no_pipe_execution(self):
        with tempfile.TemporaryDirectory() as d:
            for n in m.FILES: (Path(d)/n).write_bytes(b'fixture:'+n.encode())
            result=m.render('a'*40,d)
            self.assertEqual(result.count('sha256sum --check --status'),3)
            self.assertLess(result.rfind('sha256sum'), result.index('/usr/bin/python3'))
            self.assertNotIn('curl |',result)
            self.assertNotIn('--location',result)
            self.assertIn('curl --disable --noproxy',result)
            self.assertIn('/usr/bin/env -i PATH=',result)
            self.assertIn('/'+'a'*40+'/',result)
            self.assertIn('[ "$(/bin/hostname)" = iZvt5t8tlrm8oiZ ]',result)
            self.assertIn('/bin/mkdir -m 700',result)
    def test_verify_and_rollback_recheck_hashes_without_download(self):
        with tempfile.TemporaryDirectory() as d:
            for n in m.FILES: (Path(d)/n).write_bytes(b'fixture')
            for action in ('verify','rollback'):
                result=m.render('a'*40,d,action)
                self.assertNotIn('/usr/bin/curl',result)
                self.assertNotIn('/bin/mkdir',result)
                self.assertEqual(result.count('sha256sum --check --status'),3)
                self.assertIn('domestic_bootstrap.py" '+action,result)
    def test_arbitrary_action_denied(self):
        with self.assertRaises(ValueError):m.render('a'*40,'.','enroll')
    def test_rendered_shell_syntax_only(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            for n in m.FILES: (Path(d)/n).write_bytes(b'fixture')
            for action in ('install','verify','rollback'):
                r=subprocess.run(['/bin/bash','-n'],input=m.render('a'*40,d,action),text=True,capture_output=True)
                self.assertEqual(r.returncode,0,r.stderr)
    def test_missing_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):m.render('b'*40,d)
            f=Path(d)/'target';f.write_bytes(b'x')
            (Path(d)/m.FILES[0]).symlink_to(f)
            with self.assertRaises(ValueError):m.render('b'*40,d)

if __name__=='__main__':unittest.main()
