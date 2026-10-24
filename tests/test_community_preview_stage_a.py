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
        self.real_select=a.select.select
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
        self.obj.capture_bootstrap=self.dispatch
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
        self.assertEqual(proc.returncode,0);record=json.loads(proc.stdout.splitlines()[-2]);self.assertEqual(record['child_exit'],17);self.assertFalse(record['stage_a_result_valid']);self.assertEqual(record['state'],'HOLD_CHILD_NONZERO');self.assertIn(b'PARENT_ALIVE',proc.stdout)
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
    def real_chain_scripts(self):
        # Separate shell -> bootstrap Python -> exec caller Python. Original
        # wrapper AST/caller bodies run with fixture roots/UID/clock only;
        # every OS subprocess/resource limit and regular file write is real.
        common="""import ast,contextlib,hashlib,os,sys,time,types
from pathlib import Path
sys.path.insert(0,REPO)
from scripts import community_preview_stage_a as a
uid=os.getuid();gid=os.getgid();real_chown=os.fchown;real_exec=os.execv
root,base,phase,digest,now=sys.argv[1:]
root=Path(root);base=Path(base);inputs=base/'image-f131-40059478387'
blobs={n:(inputs/n).read_bytes() for n in a.PAYLOAD}
a.BASE=str(base);a.PAYLOAD=dict(a.PAYLOAD);a.PAYLOAD['artifact12546452389.zip']=(len(blobs['artifact12546452389.zip']),a.sha(blobs['artifact12546452389.zip']))
s=a.original(blobs)
for k,v in dict(BASE=str(base),INPUT=str(inputs),ENTRY=str(base/'site-prepare-v1.py'),PERMIT=str(base/'site-prepare-approval.json'),INSTALL=str(base/'control-oci2330-v1'),ROOT_ANCHOR=str(root),UID=uid,ROOT_GID=gid).items():setattr(s,k,v)
os.getuid=lambda:0;os.geteuid=lambda:0;os.uname=lambda:types.SimpleNamespace(nodename=a.HOST)
os.fchown=lambda fd,u,g:real_chown(fd,uid if u==0 else u,gid if g==0 else g)
time.time=lambda:float(now)
s.space=lambda *args:None;s.image_present=lambda *args:False;s.daemon_capacity=lambda:None
import json
probe=s.capture([sys.executable,'-c','import resource,json;print(json.dumps(resource.getrlimit(resource.RLIMIT_FSIZE)))'])
assert json.loads(probe)==[16384,16384]  # frozen caller child policy remains intact
s.image_load=lambda:s._load_fixed_archive(b'Z'*57365044,'fmt',b'EXPECTED')
def docker(args,timeout=10):
 assert args[:3]==s.DOCKER
 if args[3:5]==['image','load']:return b'Loaded'
 if args[3:5]==['image','inspect']:return b'EXPECTED'
 raise RuntimeError('UNEXPECTED_DOCKER_FIXTURE')
s.capture=docker
""".replace('REPO',repr(str(Path.cwd())))
        caller=self.root/'caller-worker.py';caller.write_text(common+"\nraise SystemExit(s.main(['--stage',phase,'--approval-sha256',digest]))\n")
        bootstrap=self.root/'bootstrap-worker.py'
        tail="""
source=blobs['prepare-site.sh'].decode().split("<<'PREPARE'\\n",1)[1].rsplit('\\nPREPARE',1)[0]
tree=ast.parse(source)
class Project(ast.NodeTransformer):
 def visit_Assign(self,node):
  if any(isinstance(x,ast.Name) and x.id=='BASE' for x in node.targets):node.value=ast.Constant(str(base))
  return self.generic_visit(node)
 def visit_Compare(self,node):
  if isinstance(node.left,ast.Attribute) and node.left.attr=='st_uid':node.comparators=[ast.Constant(uid) if isinstance(x,ast.Constant) and x.value==0 else x for x in node.comparators]
  return self.generic_visit(node)
 def visit_FunctionDef(self,node):
  if node.name=='directory':
   for child in ast.walk(node):
    if isinstance(child,ast.Call) and isinstance(child.func,ast.Attribute) and child.func.attr=='open' and child.args and isinstance(child.args[0],ast.Constant) and child.args[0].value=='/':child.args[0]=ast.Constant(str(root))
    if isinstance(child,ast.For):child.iter=ast.parse('path[len(FIXTURE_ROOT)+1:].split("/")',mode='eval').body
  return self.generic_visit(node)
def projected_exec(exe,argv):
 assert exe=='/usr/bin/python3' and argv[4]==s.ENTRY
 real_exec(sys.executable,[sys.executable,'-I','-B','-S',CALLER,str(root),str(base),phase,digest,now])
os.execv=projected_exec;sys.argv=['',phase,digest]
exec(compile(ast.fix_missing_locations(Project().visit(tree)),'<original-bootstrap-real-process>','exec'),{'FIXTURE_ROOT':str(root)})
""".replace('CALLER',repr(str(caller)))
        bootstrap.write_text(common+tail)
        shell=self.root/'original-bootstrap-chain.sh'
        shell.write_text('#!/bin/sh\nexec '+sys.executable+' -I -B -S '+str(bootstrap)+' '+str(self.root)+' '+str(self.base)+' "$1" "$2" "$3"\n')
        return shell
    def use_real_capture(self,force_old_limit=False):
        shell=self.real_chain_scripts()
        real=a.StageA.capture_bootstrap
        def capture(args,timeout=300):
            with patch.object(a.select,'select',self.real_select):
                return real(self.obj,['/bin/sh',str(shell),args[-2],args[-1],str(self.clock[0])],timeout=10)
        self.obj.capture_bootstrap=capture
        if force_old_limit:
            # At the exact adapter boundary, simulate the rejected inherited
            # 16KiB policy; do not change original caller or fake write results.
            real_set=a.resource.setrlimit
            def old(kind,value):
                real_set(kind,(16384,16384) if kind==a.resource.RLIMIT_FSIZE else value)
            return patch.object(a.resource,'setrlimit',side_effect=old)
        return contextlib.nullcontext()
    def test_real_subprocess_bootstrap_exec_caller_and_phase_file_budgets(self):
        with self.use_real_capture():result=self.obj.run()
        self.assertEqual(result['state'],'STAGE_A_ORIGINAL_CALLER_COMPLETED')
        self.assertEqual((self.base/'site-prepare-v1.py').stat().st_size,32470)
        self.assertEqual((self.inputs/'community-backend-image.tar.gz').stat().st_size,57365044)
    def test_real_subprocess_old_16k_limit_truncates_and_stops_before_caller(self):
        with self.use_real_capture(force_old_limit=True),self.assertRaises(a.Hold):self.obj.run()
        self.assertEqual((self.base/'site-prepare-v1.py').stat().st_size,16384)
        self.assertFalse((self.base/'control-oci2330-v1').exists())
        self.assertFalse((self.base/'stage-a-install-result.json').exists())
    def test_bootstrap_stdout_budget_is_separate_from_regular_files(self):
        self.obj.preflight();self.obj.confirm('install')
        try:
            with patch.object(a.select,'select',self.real_select),self.assertRaisesRegex(a.Hold,'OUTPUT_LIMIT'):
                a.StageA.capture_bootstrap(self.obj,[sys.executable,'-c','import os;os.write(1,b"x"*20000)'],timeout=3)
        finally:self.obj.close()
    def test_structured_child_status_not_top_level_shell_status(self):
        command=b.outer_script('fixed.zip',1,'a'*64,'b'*64,'c'*64).decode()
        valid={'state':'STAGE_A_ORIGINAL_CALLER_COMPLETED','image':'sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a','site_update':False,'private_data':False,'ocr_enabled':False,'servertrust':False}
        for code,body,expected in ((0,'',False),(0,json.dumps(valid),True),(2,json.dumps(valid),False),(143,'',False),(0,'{"state":"HOLD_STAGE_A_PRESERVE_NO_RETRY"}',False)):
            fake=self.root/'sudo-result-fixture';fake.write_text('#!/bin/sh\nprintf \'%s\\n\' \''+body+'\'\nexit '+str(code)+'\n');fake.chmod(0o700)
            fixture=command.replace('/usr/bin/sudo',str(fake))
            proc=subprocess.run(['/bin/bash'],input=('set -e\n'+fixture+'\nprintf "PARENT_ALIVE\n"\n').encode(),capture_output=True,timeout=3)
            self.assertEqual(proc.returncode,0)
            record=json.loads(proc.stdout.splitlines()[-2]);self.assertEqual(record['child_exit'],code);self.assertEqual(record['stage_a_result_valid'],expected);self.assertTrue(record['shell_exit_not_acceptance']);self.assertFalse(record['servertrust'])
    def test_two_ack_lines_can_be_prequeued_not_independent_owner_auth(self):
        # Both responses exist before the first prompt; acceptance must never
        # imply the second line was typed afterwards or independently signed.
        self.assertEqual(len(self.answers),2);result=self.obj.run();self.assertFalse(result['servertrust'])
    def test_real_pty_background_first_read_uses_kernel_job_control(self):
        code=r"""import os,sys,fcntl,termios,signal,time
sys.path.insert(0,REPO)
from scripts.community_preview_stage_a import check_terminal
# Private test-session HUP on PTY teardown must not kill the test driver.
signal.signal(signal.SIGHUP,signal.SIG_IGN)
master,slave=os.openpty();reader=None;done=False
try:
 fcntl.ioctl(slave,termios.TIOCSCTTY,0)
 reader=os.fork()
 if reader==0:
  try:
   os.setpgid(0,0);signal.signal(signal.SIGTTIN,signal.SIG_DFL)
   assert os.tcgetpgrp(slave)!=os.getpgrp()
   check_terminal(slave)  # production check must admit initial background
   data=os.read(slave,256)
   assert data==b'queued-operator-line\n'
   os._exit(0)
  except BaseException:os._exit(3)
 end=time.monotonic()+2;status=None
 while time.monotonic()<end:
  pid,value=os.waitpid(reader,os.WNOHANG|os.WUNTRACED)
  if pid:
   status=value;break
  time.sleep(.01)
 assert status is not None and os.WIFSTOPPED(status) and os.WSTOPSIG(status)==signal.SIGTTIN
 # Test driver models sudo's kernel handoff; production never tcsetpgrp's.
 os.tcsetpgrp(slave,reader);os.kill(reader,signal.SIGCONT);os.write(master,b'queued-operator-line\n')
 end=time.monotonic()+2
 while time.monotonic()<end:
  pid,value=os.waitpid(reader,os.WNOHANG)
  if pid:
   done=True;assert os.WIFEXITED(value) and os.WEXITSTATUS(value)==0;break
  time.sleep(.01)
 assert done
 print('BACKGROUND_SIGTTIN_FOREGROUND_READ_OK_NOT_ACTUAL_SUDO')
finally:
 if reader and not done:
  try:os.kill(reader,signal.SIGKILL)
  except ProcessLookupError:pass
  try:os.waitpid(reader,0)
  except ChildProcessError:pass
 os.close(master);os.close(slave)
""".replace('REPO',repr(str(Path.cwd())))
        proc=subprocess.run([sys.executable,'-c',code],start_new_session=True,capture_output=True,timeout=5)
        self.assertEqual(proc.returncode,0,proc.stderr.decode());self.assertIn(b'BACKGROUND_SIGTTIN_FOREGROUND_READ_OK',proc.stdout)
    def test_owner_context_missing_kernel_identity_is_not_servertrust(self):
        # Actual production function AST, synthetic OS/NSS/env data only.
        tree=ast.parse(Path(a.__file__).read_text());node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='owner_context')
        fake=types.SimpleNamespace(getuid=lambda:0,geteuid=lambda:0,uname=lambda:types.SimpleNamespace(nodename=a.HOST),environ={'SUDO_USER':'admin','SUDO_UID':'1000','SUDO_GID':'1000'},getpid=lambda:123,open=lambda *x:9,O_RDONLY=0,O_NOFOLLOW=0,read=lambda *x:b'4294967295',close=lambda fd:None)
        ns=dict(os=fake,pwd=types.SimpleNamespace(getpwnam=lambda name:types.SimpleNamespace(pw_uid=1000,pw_gid=1000)),need=a.need,HOST=a.HOST)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual-owner-context>','exec'),ns)
        with self.assertRaisesRegex(a.Hold,'LOGINUID'):ns['owner_context']()

if __name__=='__main__':unittest.main()
