import json
import io
from contextlib import redirect_stdout
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import test_install_controller as fixture
from korea.phase_c import artifact, root_handoff as handoff


@unittest.skipUnless(os.geteuid()==0,'Synthetic private-root bootstrap fixtures')
class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.InstallTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixture.InstallTests.tearDownClass()
    def setUp(self):
        self.f=fixture.InstallTests();self.f.setUp()
        self.helper=(self.f.origin/(artifact.PREFIX+'root_handoff.py')).read_bytes()
    def validate(self,pin=None,raw=None):
        return handoff.validate(self.f.raw if raw is None else raw,self.f.plan_path.read_bytes(),
                                self.f.pin if pin is None else pin,self.helper,fixture.NOW)
    def test_exact_helper_archive_plan_and_single_use_body_verified_before_import(self):
        files,a=self.validate()
        self.assertEqual(a['max_attempts'],1)
        self.assertEqual(files[artifact.PREFIX+'root_handoff.py'],self.helper)
        for change in ({'handoff_sha256':'0'*64},{'artifact_sha256':'0'*64},{'plan_sha256':'0'*64},
                       {'controller_sha256':'0'*64},{'service_start_allowed':True},{'expires_at':fixture.NOW}):
            _,pin=self.f.make_pin(**change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.validate(pin=pin)
    def test_extraction_private_no_bytecode_no_reuse_and_no_escape(self):
        files,_=self.validate();stage=self.f.root/'stage';handoff.extract_new(files,stage)
        self.assertEqual(stage.stat().st_mode&0o777,0o700)
        self.assertFalse(list(stage.rglob('__pycache__')))
        self.assertEqual((stage/(artifact.PREFIX+'install_controller.py')).read_bytes(),files[artifact.PREFIX+'install_controller.py'])
        with self.assertRaises(FileExistsError):handoff.extract_new(files,stage)
        escaped=self.f.root/'escape-stage'
        with self.assertRaises(ValueError):handoff.extract_new({'../escape':b'bad'},escaped)
        self.assertFalse(escaped.exists());self.assertFalse((self.f.root/'escape').exists())
    def test_root_handoff_main_validates_before_candidate_subprocess(self):
        helper=self.f.root/'handoff.py';helper.write_bytes(self.helper);helper.chmod(0o400)
        fake_host=mock.Mock(nodename=handoff.HOST)
        with mock.patch.object(handoff,'__file__',str(helper)),mock.patch.object(handoff,'PIN',self.f.pin_path),\
             mock.patch.object(handoff,'STAGING',self.f.root),mock.patch.object(handoff.os,'uname',return_value=fake_host),\
             mock.patch.object(handoff.sys,'version_info',(3,11)),mock.patch.dict(handoff.os.environ,handoff.ENV,clear=True),\
             mock.patch.object(handoff.time,'time',return_value=fixture.NOW),\
             mock.patch.object(handoff,'current_body',return_value=self.f.pin['approval_body']),\
             mock.patch.object(handoff.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(handoff.main(['--archive',str(self.f.install_archive),'--plan',str(self.f.plan_path)]),0)
            args=run.call_args.args[0];self.assertEqual(args[1:4],['-I','-B','-u'])
            self.assertEqual(run.call_args.kwargs['env'],handoff.ENV)
    def test_bootstrap_and_entry_success_exit_not_caught_as_failure(self):
        for name in ('root_handoff.py','entry.py'):
            raw=(self.f.origin/(artifact.PREFIX+name)).read_text()
            # Replace only main at the executable guard to exercise the REAL exit
            # wrapper, without granting a host or running any controller action.
            import ast
            tree=ast.parse(raw);guard=tree.body[-1]
            self.assertIsInstance(guard,ast.If)
            lines=raw.splitlines(keepends=True)
            synthetic=''.join(lines[:guard.lineno-1])+"def main(*args): return 0\n"+''.join(lines[guard.lineno-1:])
            target=self.f.root/name;target.write_text(synthetic)
            # entry imports only the candidate package; the wrapper has no host side effects.
            code="import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2],run_name='__main__')"
            result=subprocess.run([sys.executable,'-I','-B','-c',code,str(self.f.origin/'migration-prep'),str(target)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            self.assertNotIn('HOLD',result.stdout+result.stderr)
    def test_duplicate_approval_json_fields_rejected(self):
        with self.assertRaises(ValueError):handoff.parse('{"a":1,"a":2}')
    def test_compressed_expansion_is_bounded_before_tar_parser(self):
        import gzip
        bomb=gzip.compress(b'0'*(16*1024*1024+1),mtime=0)
        _,pin=self.f.make_pin(artifact_sha256=handoff.sha(bomb))
        with self.assertRaisesRegex(ValueError,'ARCHIVE_EXPANSION_LIMIT'):self.validate(pin=pin,raw=bomb)
        from gate_common import GateError
        from korea.phase_c.install_controller import package_bytes
        with self.assertRaisesRegex(GateError,'C_INSTALL_ARCHIVE_EXPANSION_LIMIT'):package_bytes(bomb)
