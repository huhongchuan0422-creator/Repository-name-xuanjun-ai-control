"""Real private temporary files + frozen wrapper/caller; synthetic Owner/TTY/Docker.
No actual sudo, Docker, UK, upload or production identity is used.
"""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from scripts import community_preview_stage_a as a
from scripts import community_preview_stage_a_bundle as b
from scripts import community_preview_control_carrier as carrier

class StageATest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path.cwd());self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700);self.base=self.root/'base';self.base.mkdir(mode=0o700)
        self.inputs=self.base/'image-f131-40059478387';self.clock=[100];self.reads=0;self.loads=0
        self.image=b'SYNTHETIC_IMAGE_NOT_PRODUCTION'
        self.payload=dict(a.PAYLOAD);self.payload['artifact12546452389.zip']=(len(self.image),a.sha(self.image))
        self.blobs={'community_preview_site_prepare.py':Path('scripts/community_preview_site_prepare.py').read_bytes(),
            'prepare-site.sh':Path('deploy/community-preview/prepare-site.sh').read_bytes(),
            'control-oci2330-v1.zip':carrier.build()[0],'artifact12546452389.zip':self.image}
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        for key,value in dict(BASE=str(self.base),INPUT=str(self.inputs),PAYLOAD=self.payload).items():self.stack.enter_context(patch.object(a,key,value))
        self.owner={'sudo_uid':os.getuid(),'sudo_gid':os.getgid(),'kernel_loginuid':os.getuid()}
        self.stack.enter_context(patch.object(a,'owner_context',return_value=self.owner))
        self.stack.enter_context(patch.object(a.time,'time',side_effect=lambda:self.clock[0]))
        self.tty_file=self.root/'synthetic-tty';self.tty_file.write_bytes(b'');self.tty_file.chmod(0o600)
        self.tty_fd=None;self.answers=[];self.events=[]
        def open_tty():
            self.tty_fd=os.open(str(self.tty_file),os.O_RDWR);return self.tty_fd
        self.stack.enter_context(patch.object(a,'open_terminal',side_effect=open_tty))
        self.stack.enter_context(patch.object(a,'check_terminal',side_effect=lambda fd:self.assertEqual(fd,self.tty_fd)))
        self.stack.enter_context(patch.object(a.select,'select',side_effect=lambda read,*rest:(read,[],[])))
        real_read=os.read;real_chown=os.fchown;uid=os.getuid();gid=os.getgid()
        def read(fd,size):
            if fd==self.tty_fd:
                self.reads+=1;self.clock[0]=100 if self.reads==1 else 200
                return self.answers.pop(0)
            return real_read(fd,size)
        self.stack.enter_context(patch.object(a.os,'read',side_effect=read))
        # Fixture ownership only; cannot grant real root on Hosted nonroot.
        self.stack.enter_context(patch.object(a.os,'fchown',side_effect=lambda fd,u,g:real_chown(fd,uid if u==0 else u,gid if g==0 else g)))
        self.obj=a.StageA(self.blobs,'a'*64)
        self.answers=[('APPROVE_INSTALL '+self.obj.scope+'\n').encode(),('APPROVE_IMAGE_LOAD '+self.obj.scope+'\n').encode()]
        s=self.obj.s;self.s=s
        for name,val in dict(BASE=str(self.base),INPUT=str(self.inputs),ENTRY=str(self.base/'site-prepare-v1.py'),PERMIT=str(self.base/'site-prepare-approval.json'),INSTALL=str(self.base/'control-oci2330-v1'),ROOT_ANCHOR=str(self.root),UID=uid,ROOT_GID=gid).items():setattr(s,name,val)
        s.space=lambda fd,required,files:self.events.append(('space',files+128))
        self.stack.enter_context(patch.object(a.os,'getuid',return_value=0));self.stack.enter_context(patch.object(a.os,'geteuid',return_value=0))
        self.stack.enter_context(patch.object(a.os,'uname',return_value=types.SimpleNamespace(nodename=a.HOST)))
        s.image_present=lambda *args:False;s.daemon_capacity=lambda:None
        # Freeze original outer-archive verification by reuse. Only synthetic
        # image bytes enter the original protected import primitive below.
        s.image_load=lambda:s._load_fixed_archive(b'SYNTHETIC_TAR','fmt',b'EXPECTED')
        s.capture=self.dispatch
    def dispatch(self,args,timeout=10):
        if args[:1]==['/bin/sh']:
            self.events.append(('caller',args[-2]));return self.wrapper(args)
        self.assertEqual(args[:3],self.s.DOCKER)
        if args[3:5]==['image','load']:
            self.loads+=1;self.events.append(('load',));return b'Loaded'
        if args[3:5]==['image','inspect']:return b'EXPECTED'
        self.fail('Unapproved synthetic transport')
    def wrapper(self,args):
        # Execute exact original wrapper Python AST and actual original main.
        # Only root filesystem anchor/UID/host/exec boundary are fixtures.
        source=self.blobs['prepare-site.sh'].decode().split("<<'PREPARE'\n",1)[1].rsplit('\nPREPARE',1)[0]
        tree=ast.parse(source);uid=self.owner['sudo_uid']
        class FixtureProjection(ast.NodeTransformer):
            def visit_Assign(inner,node):
                if any(isinstance(x,ast.Name) and x.id=='BASE' for x in node.targets):node.value=ast.Constant(str(self.base))
                return inner.generic_visit(node)
            def visit_Compare(inner,node):
                if isinstance(node.left,ast.Attribute) and node.left.attr=='st_uid':
                    node.comparators=[ast.Constant(uid) if isinstance(x,ast.Constant) and x.value==0 else x for x in node.comparators]
                return inner.generic_visit(node)
            def visit_FunctionDef(inner,node):
                if node.name=='directory':
                    for child in ast.walk(node):
                        if isinstance(child,ast.Call) and isinstance(child.func,ast.Attribute) and child.func.attr=='open' and child.args and isinstance(child.args[0],ast.Constant) and child.args[0].value=='/':child.args[0]=ast.Constant(str(self.root))
                        if isinstance(child,ast.For):child.iter=ast.parse('path[len(FIXTURE_ROOT)+1:].split("/")',mode='eval').body
                return inner.generic_visit(node)
        tree=ast.fix_missing_locations(FixtureProjection().visit(tree))
        class ExecReturned(BaseException):pass
        def execv(exe,argv):
            self.assertEqual(exe,'/usr/bin/python3');self.assertEqual(argv[4],self.s.ENTRY)
            self.assertEqual(self.s.main(argv[5:]),0);raise ExecReturned()
        output=io.StringIO()
        with patch.object(sys,'argv',['',args[-2],args[-1]]),patch.object(a.os,'execv',side_effect=execv),contextlib.redirect_stdout(output):
            try:exec(compile(tree,'<original-wrapper-fixture>','exec'),{'FIXTURE_ROOT':str(self.root)})
            except ExecReturned:pass
        return output.getvalue().encode()
    def test_full_install_then_image_original_wrapper_and_caller(self):
        result=self.obj.run();self.assertEqual(result['state'],'STAGE_A_ORIGINAL_CALLER_COMPLETED');self.assertEqual(self.loads,1)
        self.assertEqual([x for x in self.events if x[0]=='caller'],[('caller','install'),('caller','image-load')])
        self.assertIn(('space',192),self.events)
        permits=[json.loads((self.base/('site-prepare-approval.'+phase+'.json')).read_text()) for phase in ('install','image-load')]
        self.assertEqual([p['issued_at'] for p in permits],[100,200])
        for p in permits:self.assertEqual(p['expires_at']-p['issued_at'],600);self.assertIsNone(p['all_writers_frozen_evidence_sha256']);self.assertIsNone(p['snapshot_manifest_sha256'])
        self.assertFalse((self.base/a.PERMIT).exists());self.assertEqual(set(self.inputs.iterdir()),{self.inputs/n for n in self.payload}|{self.inputs/'community-backend-image.tar.gz',self.inputs/'image-load-intent.json',self.inputs/'image-load-observed.json'})
    def test_no_actual_confirmation_zero_permit_or_target_write(self):
        self.answers=[b'copied chat approved=true\n']
        with self.assertRaises(a.Hold):self.obj.run()
        self.assertFalse(self.inputs.exists());self.assertFalse((self.base/a.PERMIT).exists());self.assertFalse((self.base/a.ATTEMPT).exists());self.assertEqual(self.loads,0)
    def test_existing_attempt_or_conflicting_inputs_hold(self):
        (self.base/a.ATTEMPT).write_text('preserve')
        with self.assertRaises(a.Hold):self.obj.run()
        self.assertEqual((self.base/a.ATTEMPT).read_text(),'preserve');self.assertEqual(self.reads,0)
    def test_expiry_after_input_copy_zero_permit_no_caller(self):
        original=self.obj.stage_inputs
        def delayed():original();self.clock[0]=701
        with patch.object(self.obj,'stage_inputs',side_effect=delayed),self.assertRaises(a.Hold):self.obj.run()
        self.assertFalse((self.base/a.PERMIT).exists());self.assertEqual(self.loads,0);self.assertFalse(any(x[0]=='caller' for x in self.events))
    def test_original_install_failure_never_advances_or_retries(self):
        with patch.object(self.obj,'call',side_effect=RuntimeError('synthetic original failure')),self.assertRaises(RuntimeError):self.obj.run()
        self.assertEqual(self.reads,1);self.assertTrue((self.base/a.PERMIT).exists());self.assertEqual(self.loads,0)
        second=a.StageA(self.blobs,'a'*64)
        try:
            second.s=self.s
            with self.assertRaises(a.Hold):second.run()
        finally:second.close()
    def test_second_stage_denied_preserves_completed_install(self):
        self.answers[1]=b'NO\n'
        with self.assertRaises(a.Hold):self.obj.run()
        self.assertTrue((self.base/'control-oci2330-v1').exists());self.assertTrue((self.base/'site-prepare-approval.install.json').exists());self.assertEqual(self.loads,0)
    def test_public_payload_mismatch_before_any_permission(self):
        blobs=dict(self.blobs);blobs['prepare-site.sh']=b'changed'
        with self.assertRaises(a.Hold):a.StageA(blobs,'a'*64)
        self.assertFalse((self.base/a.PERMIT).exists())
    def test_generated_outer_failure_does_not_exit_parent_even_errexit(self):
        command=b.outer_script('fixed.zip',1,'a'*64,'b'*64,'c'*64).decode()
        # Fake sudo child returns 17, never executes embedded root program.
        fake=self.root/'sudo-fixture';fake.write_text('#!/bin/sh\nexit 17\n');fake.chmod(0o700)
        command=command.replace('/usr/bin/sudo',str(fake))
        prefix='set -e\n'
        proc=subprocess.run(['/bin/bash'],input=(prefix+command+'\nprintf "PARENT_ALIVE\\n"\n').encode(),capture_output=True,timeout=3)
        self.assertEqual(proc.returncode,0);self.assertIn(b'STAGE_A_INNER_EXIT=17',proc.stdout);self.assertIn(b'STAGE_A_OUTER_EXIT=17',proc.stdout);self.assertIn(b'PARENT_ALIVE',proc.stdout)
    def test_image_failure_or_permission_archive_conflict_holds_without_retry(self):
        original=self.obj.call
        def fail_image(raw):
            if self.obj.phase=='image-load':raise RuntimeError('synthetic image unknown')
            return original(raw)
        with patch.object(self.obj,'call',side_effect=fail_image),self.assertRaises(RuntimeError):self.obj.run()
        self.assertTrue((self.base/'site-prepare-approval.install.json').exists())
        p=json.loads((self.base/a.PERMIT).read_text());self.assertEqual(p['stage'],'image-load');self.assertEqual(self.loads,0)
    def test_archive_conflict_preserves_existing_and_active_permission(self):
        original=self.obj.call
        def conflict(raw):
            result=original(raw)
            path=self.base/'site-prepare-approval.install.json';path.write_text('existing-preserve');path.chmod(0o600)
            return result
        with patch.object(self.obj,'call',side_effect=conflict),self.assertRaises(FileExistsError):self.obj.run()
        self.assertEqual((self.base/'site-prepare-approval.install.json').read_text(),'existing-preserve')
        self.assertTrue((self.base/a.PERMIT).exists());self.assertEqual(self.loads,0)
    def test_root_input_directory_symlink_never_follows(self):
        target=self.root/'other';target.mkdir(mode=0o700);self.inputs.symlink_to(target,target_is_directory=True)
        with self.assertRaises(OSError):self.obj.run()
        self.assertEqual(list(target.iterdir()),[]);self.assertEqual(self.reads,0)
    def test_failed_fd_cleanup_still_closes_other_owned_fds(self):
        fd1=os.open(str(self.tty_file),os.O_RDONLY);fd2=os.open(str(self.tty_file),os.O_RDONLY);fd3=os.open(str(self.tty_file),os.O_RDONLY)
        self.obj.input=fd1;self.obj.tty=fd2;self.obj.parent=fd3;real=os.close;calls=[]
        def close(fd):
            calls.append(fd)
            if fd==fd1:raise OSError('synthetic cleanup')
            real(fd)
        try:
            with patch.object(a.os,'close',side_effect=close),self.assertRaisesRegex(a.Hold,'CLEANUP_UNKNOWN'):self.obj.close()
            self.assertEqual(calls,[fd1,fd2,fd3]);self.assertIsNone(self.obj.parent)
        finally:real(fd1)
    def test_replaced_active_permit_never_deleted_as_completed_record(self):
        original=self.obj.write
        def replace(fd,name,raw):
            original(fd,name,raw)
            if name=='site-prepare-approval.install.json':
                current=self.base/a.PERMIT;body=current.read_bytes();current.unlink();current.write_bytes(body);current.chmod(0o600)
        with patch.object(self.obj,'write',side_effect=replace),self.assertRaisesRegex(a.Hold,'PERMIT_IDENTITY_CHANGED'):self.obj.run()
        self.assertTrue((self.base/a.PERMIT).exists());self.assertEqual(self.loads,0)
    def test_second_confirmation_or_permit_serialization_expiry_zero_second_permit(self):
        original=self.obj.permit
        def late_permit():
            if self.obj.phase=='image-load':self.clock[0]=801
            return original()
        with patch.object(self.obj,'permit',side_effect=late_permit),self.assertRaises(a.Hold):self.obj.run()
        self.assertFalse((self.base/a.PERMIT).exists());self.assertEqual(self.loads,0)
    def outer_validator(self,raw,command,symlink=False):
        incoming=self.root/'incoming.zip';incoming.write_bytes(raw);incoming.chmod(0o600)
        if symlink:
            other=self.root/'original.zip';incoming.rename(other);incoming.symlink_to(other)
        body=command.decode().split("<<'STAGE_A'\n",1)[1].rsplit('\nSTAGE_A',1)[0]
        tree=ast.parse(body)
        class Fixture(ast.NodeTransformer):
            def visit_Assign(inner,node):
                if any(isinstance(x,ast.Name) and x.id=='PATH' for x in node.targets):node.value=ast.Constant(str(incoming))
                return inner.generic_visit(node)
            def visit_Call(inner,node):
                if isinstance(node.func,ast.Name) and node.func.id=='exec':node.func=ast.Name(id='fixture_exec',ctx=ast.Load())
                if isinstance(node.func,ast.Attribute) and node.func.attr=='open' and node.args and isinstance(node.args[0],ast.Constant) and node.args[0].value=='/':node.args[0]=ast.Constant(str(self.root))
                return inner.generic_visit(node)
            def visit_For(inner,node):
                if isinstance(node.target,ast.Name) and node.target.id=='part':node.iter=ast.parse('PATH[len(FIXTURE_ROOT)+1:].split("/")[:-1]',mode='eval').body
                return inner.generic_visit(node)
        tree=ast.fix_missing_locations(Fixture().visit(tree));calls=[]
        def verified_entry(code,ns):
            ns['run']=lambda blobs,manifest:(calls.append((blobs,manifest)) or 0)
        with patch.object(a.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=self.owner['sudo_uid'] or 1000)),contextlib.redirect_stdout(io.StringIO()):
            try:exec(compile(tree,'<exact-outer-validator-projection>','exec'),{'FIXTURE_ROOT':str(self.root),'fixture_exec':verified_entry})
            except SystemExit as result:return result.code,calls
    def test_full_single_bundle_validator_and_symlink_tamper_rejection(self):
        image=self.root/'synthetic-image.zip';image.write_bytes(self.image)
        name,raw,command,report=b.build(image)
        code,calls=self.outer_validator(raw,command);self.assertEqual(code,0);self.assertEqual(set(calls[0][0]),set(self.payload))
        # Exact outer SHA remains original, so altered input never reaches entry.
        code,calls=self.outer_validator(raw[:-1]+b'x',command);self.assertEqual(code,2);self.assertEqual(calls,[])
        code,calls=self.outer_validator(raw,command,symlink=True);self.assertEqual(code,2);self.assertEqual(calls,[])
    def test_terminal_timeout_or_operator_change_zero_permission(self):
        with patch.object(a.select,'select',return_value=([],[],[])),self.assertRaises(a.Hold):self.obj.run()
        self.assertFalse((self.base/a.PERMIT).exists());self.assertFalse((self.base/a.ATTEMPT).exists())
        obj=a.StageA(self.blobs,'a'*64);obj.s=self.s
        changed=dict(self.owner,kernel_loginuid=999999)
        with patch.object(a,'owner_context',side_effect=[self.owner,self.owner,changed]),self.assertRaisesRegex(a.Hold,'OPERATOR_CHANGED'):obj.run()
        self.assertFalse((self.base/a.PERMIT).exists());self.assertFalse((self.base/a.ATTEMPT).exists())
    def test_new_sources_and_complete_outer_python36_syntax(self):
        for name in ('community_preview_stage_a.py','community_preview_stage_a_bundle.py'):
            ast.parse(Path('scripts/'+name).read_text(),feature_version=(3,6))
        command=b.outer_script('fixed.zip',1,'a'*64,'b'*64,'c'*64).decode()
        ast.parse(command.split("<<'STAGE_A'\n",1)[1].rsplit('\nSTAGE_A',1)[0],feature_version=(3,6))
    def test_owner_context_missing_kernel_identity_is_not_servertrust(self):
        # Actual production function AST, synthetic OS/NSS/env data only.
        tree=ast.parse(Path(a.__file__).read_text());node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='owner_context')
        fake=types.SimpleNamespace(getuid=lambda:0,geteuid=lambda:0,uname=lambda:types.SimpleNamespace(nodename=a.HOST),environ={'SUDO_USER':'admin','SUDO_UID':'1000','SUDO_GID':'1000'},getpid=lambda:123,open=lambda *x:9,O_RDONLY=0,O_NOFOLLOW=0,read=lambda *x:b'4294967295',close=lambda fd:None)
        ns=dict(os=fake,pwd=types.SimpleNamespace(getpwnam=lambda name:types.SimpleNamespace(pw_uid=1000,pw_gid=1000)),need=a.need,HOST=a.HOST)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual-owner-context>','exec'),ns)
        with self.assertRaisesRegex(a.Hold,'LOGINUID'):ns['owner_context']()

if __name__=='__main__':unittest.main()
