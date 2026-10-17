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
            self.assertEqual(result.count('sha256sum --check --status'),4)
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
                self.assertEqual(result.count('sha256sum --check --status'),4)
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
    def test_install_never_implicitly_enrolls_or_executes(self):
        with tempfile.TemporaryDirectory() as d:
            for n in m.FILES: (Path(d)/n).write_bytes(b'fixture')
            result=m.render('a'*40,d)
            self.assertNotIn('domestic_owner.py" enroll',result)
            self.assertNotIn('domestic_owner.py" execute',result)
    def test_explicit_all_stages_uses_real_parameter_bindings(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            for n in m.FILES: (Path(d)/n).write_bytes(b'fixture')
            result=m.render('a'*40,d,'install,enroll,execute,export,rollback',comment_id=123,body_sha256='b'*64,custody_sha256='c'*64)
            self.assertIn('--comment-id 123 --body-sha256 '+'b'*64,result)
            self.assertLess(result.index('domestic_owner.py" enroll'),result.index('domestic_owner.py" execute'))
            self.assertLess(result.index('domestic_owner.py" execute'),result.index('domestic_owner.py" export'))
            self.assertEqual(subprocess.run(['/bin/bash','-n'],input=result,text=True,capture_output=True).returncode,0)
    def test_stage_injection_duplicates_and_wrong_order_denied(self):
        for stage in ('execute;id','execute,execute','enroll,install','rollback,export','execute,enroll'):
            with self.assertRaises(ValueError):m.render('a'*40,'.',stage)
    def test_enroll_requires_exact_inputs_not_placeholder(self):
        for kw in ({},{'comment_id':0,'body_sha256':'b'*64,'custody_sha256':'c'*64},{'comment_id':123,'body_sha256':'UNKNOWN','custody_sha256':'c'*64},{'comment_id':True,'body_sha256':'b'*64,'custody_sha256':'c'*64}):
            with self.assertRaises(ValueError):m.render('a'*40,'.','enroll',**kw)
    def test_unused_permission_inputs_rejected(self):
        with self.assertRaises(ValueError):m.render('a'*40,'.','execute',comment_id=123)
    def test_missing_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):m.render('b'*40,d)
            f=Path(d)/'target';f.write_bytes(b'x')
            (Path(d)/m.FILES[0]).symlink_to(f)
            with self.assertRaises(ValueError):m.render('b'*40,d)

if __name__=='__main__':unittest.main()
