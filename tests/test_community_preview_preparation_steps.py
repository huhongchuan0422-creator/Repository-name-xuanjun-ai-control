"""Isolated original preparation stages; no Docker/server/real data/identities.

Real private temporary files and SQLite; proxy/container results synthetic.
"""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch, Mock
from scripts import community_preview_site_prepare as s
from scripts import community_preview_control_carrier as carrier

class PreparationSteps(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path.cwd());self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.base=self.root/'opt';self.base.mkdir(mode=0o700)
        self.input=self.base/'image-f131-40059478387';self.input.mkdir(mode=0o700)
        self.data=self.root/'private';self.data.mkdir(mode=0o700)
        for name in ('data','config'):(self.data/name).mkdir(mode=0o700)
        (self.data/'config'/'center-keys.json').write_bytes(b'SYNTHETIC-KEY-NOT-A-REAL-KEY');(self.data/'config'/'center-keys.json').chmod(0o600)
        db=sqlite3.connect(str(self.data/'data'/'center.sqlite'));db.execute('CREATE TABLE sample(v TEXT)');db.execute("INSERT INTO sample VALUES('synthetic')");db.commit();db.close();(self.data/'data'/'center.sqlite').chmod(0o600)
        (self.data/'data'/'center.sqlite-wal').write_bytes(b'SYNTHETIC-WAL');(self.data/'data'/'center.sqlite-wal').chmod(0o600)
        self.stack=contextlib.ExitStack()
        for name,val in dict(BASE=str(self.base),INSTALL=str(self.base/'control-oci2330-v1'),INPUT=str(self.input),
                BACKUP=str(self.base/'backup-2330-to-f131-v1'),DATA=str(self.data),UID=os.geteuid(),
                FREEZE=str(self.base/'writer-freeze-reference.json'),ROOT_GID=os.getegid(),ROOT_ANCHOR=str(self.root),ALLOWED_GIDS=(os.getegid(),1008),ENTRY=str(self.base/'site-prepare-v1.py'),PERMIT=str(self.base/'site-prepare-approval.json')).items():
            self.stack.enter_context(patch.object(s,name,val))
        self.stack.enter_context(patch.object(s,'space'))
    def tearDown(self):self.stack.close();self.tmp.cleanup()
    def private(self,path,body):path=Path(path);path.write_bytes(body);path.chmod(0o600)
    def stage_carrier(self):
        raw=Path('deploy/community-preview/control-oci2330-v1.zip').read_bytes()
        m=Path('deploy/community-preview/control-oci2330-v1-manifest.json').read_bytes()
        self.assertEqual(len(raw),111330);self.assertEqual(s.sha(raw),s.CARRIER_SHA);self.assertEqual(s.sha(m),s.CARRIER_MANIFEST)
        self.private(self.input/'control-oci2330-v1.zip',raw)
        return raw,m
    def snapshot(self):
        with patch.object(s,'stopped') as stop:r=s.snapshot({'all_writers_frozen_evidence_sha256':'a'*64})
        self.assertEqual(stop.call_count,3);return r
    def permit(self,stage='install'):
        self.private(s.ENTRY,Path(s.__file__).read_bytes())
        p=dict(format=1,host=s.HOST,stage=stage,entry_sha256=s.sha(Path(s.ENTRY).read_bytes()),issued_at=100,expires_at=700,
            all_writers_frozen_evidence_sha256=None,snapshot_manifest_sha256=None)
        self.private(s.PERMIT,s.canonical(p));return p
    def auth(self,p,stage=None):
        self.private(s.PERMIT,s.canonical(p))
        with patch.object(s,'__file__',s.ENTRY),patch.object(s.os,'getuid',return_value=0),patch.object(s.os,'geteuid',return_value=0),patch.object(s.os,'uname',return_value=types.SimpleNamespace(nodename=s.HOST)),patch.object(s.time,'time',return_value=101):
            return s.authorize(stage or p['stage'],s.sha(s.canonical(p)))
    @contextlib.contextmanager
    def active_image(self):
        p=self.permit('image-load');clock=[101];privilege=[0]
        with patch.object(s,'__file__',s.ENTRY),patch.object(s,'_ACTIVE',('image-load',s.sha(s.canonical(p)))),patch.object(s.os,'getuid',return_value=0),patch.object(s.os,'geteuid',side_effect=lambda:privilege[0]),patch.object(s.os,'uname',return_value=types.SimpleNamespace(nodename=s.HOST)),patch.object(s.time,'time',side_effect=lambda:clock[0]):
            yield clock,privilege,p
    def test_capacity_crossing_expiry_or_revocation_zero_tar_intent_and_load(self):
        for failure in ('expiry','privilege','permit','entry'):
            with self.subTest(failure=failure),self.active_image() as (clock,privilege,p):
                def slow():
                    if failure=='expiry':clock[0]=701
                    elif failure=='privilege':privilege[0]=1
                    elif failure=='permit':self.private(s.PERMIT,b'{}')
                    else:self.private(s.ENTRY,b'changed')
                with patch.object(s,'image_present',return_value=False),patch.object(s,'daemon_capacity',side_effect=slow),patch.object(s,'capture') as run,self.assertRaises(s.Hold):
                    s._load_fixed_archive(b'SYNTHETIC','fmt',b'expected')
                run.assert_not_called()
                self.assertEqual(list(self.input.iterdir()),[])
    def test_original_artifact_expiry_during_capacity_zero_write_and_load(self):
        with self.active_image() as (clock,privilege,p):
            p.update(issued_at=s.EXPIRES-100,expires_at=s.EXPIRES+500);self.private(s.PERMIT,s.canonical(p));clock[0]=s.EXPIRES-1
            def slow():clock[0]=s.EXPIRES
            with patch.object(s,'_ACTIVE',('image-load',s.sha(s.canonical(p)))),patch.object(s,'image_present',return_value=False),patch.object(s,'daemon_capacity',side_effect=slow),patch.object(s,'capture') as run,self.assertRaisesRegex(s.Hold,'F131_ARTIFACT_EXPIRED'):
                s._load_fixed_archive(b'SYNTHETIC','fmt',b'expected')
            run.assert_not_called();self.assertEqual(list(self.input.iterdir()),[])
    def test_final_space_observation_expiry_zero_tar_and_load(self):
        with self.active_image() as (clock,privilege,p):
            def slow(*args):clock[0]=701
            with patch.object(s,'image_present',return_value=False),patch.object(s,'daemon_capacity'),patch.object(s,'space',side_effect=slow),patch.object(s,'capture') as run,self.assertRaises(s.Hold):
                s._load_fixed_archive(b'SYNTHETIC','fmt',b'expected')
            run.assert_not_called();self.assertEqual(list(self.input.iterdir()),[])
    def test_intent_canonical_serialization_expiry_zero_intent_and_load(self):
        original=s.canonical
        with self.active_image() as (clock,privilege,p):
            def slow(value):
                raw=original(value)
                if type(value) is dict and value.get('image')==s.NEW_IMAGE:clock[0]=701
                return raw
            with patch.object(s,'canonical',side_effect=slow),patch.object(s,'image_present',return_value=False),patch.object(s,'daemon_capacity'),patch.object(s,'capture') as run,self.assertRaises(s.Hold):
                s._load_fixed_archive(b'SYNTHETIC','fmt',b'expected')
            self.assertTrue((self.input/'community-backend-image.tar.gz').exists())
            self.assertFalse((self.input/'image-load-intent.json').exists());run.assert_not_called()
    def test_tar_or_intent_completion_expiry_stops_next_action(self):
        original=s.create_file
        for name in ('community-backend-image.tar.gz','image-load-intent.json'):
            with self.subTest(name=name),self.active_image() as (clock,privilege,p):
                def slow(parent,path,*args,**kwargs):
                    original(parent,path,*args,**kwargs)
                    if path==name:clock[0]=701
                with patch.object(s,'create_file',side_effect=slow),patch.object(s,'image_present',return_value=False),patch.object(s,'daemon_capacity'),patch.object(s,'capture') as run,self.assertRaises(s.Hold):
                    s._load_fixed_archive(b'SYNTHETIC','fmt',b'expected')
                run.assert_not_called();self.assertFalse((self.input/'image-load-observed.json').exists())
                if name=='community-backend-image.tar.gz':self.assertFalse((self.input/'image-load-intent.json').exists())
            # Separate synthetic attempts, not a production retry/cleanup.
            for path in self.input.iterdir():path.unlink()
    def test_authorize_own_entry_read_crossing_or_permission_change_zero_write(self):
        original=s.read
        for failure in ('expiry','permit_mode'):
            with self.subTest(failure=failure),self.active_image() as (clock,privilege,p):
                def slow(path,*args,**kwargs):
                    raw=original(path,*args,**kwargs)
                    if path==s.ENTRY:
                        if failure=='expiry':clock[0]=701
                        else:Path(s.PERMIT).chmod(0o644)
                    return raw
                fd=os.open(str(self.input),os.O_RDONLY|os.O_DIRECTORY)
                try:
                    with patch.object(s,'read',side_effect=slow),self.assertRaises(s.Hold):s.create_file(fd,'never',b'no')
                    self.assertFalse((self.input/'never').exists())
                finally:os.close(fd)
    def test_noncanonical_authority_or_expired_directory_zero_mutation(self):
        with self.active_image() as (clock,privilege,p):
            raw=json.dumps(p,indent=2).encode();self.private(s.PERMIT,raw)
            with patch.object(s,'_ACTIVE',('image-load',s.sha(raw))):
                fd=os.open(str(self.input),os.O_RDONLY|os.O_DIRECTORY)
                try:
                    with self.assertRaisesRegex(s.Hold,'CANONICAL'):s.new_dir(fd,'never')
                finally:os.close(fd)
            self.assertFalse((self.input/'never').exists())
    def test_temp_output_allocation_expiry_zero_child_spawn(self):
        original=tempfile.TemporaryFile
        for kind in ('capture','inspect'):
            with self.subTest(kind=kind),self.active_image() as (clock,privilege,p):
                def slow(*a,**kw):
                    file=original(*a,**kw);clock[0]=701;return file
                with patch.object(tempfile,'TemporaryFile',side_effect=slow),patch.object(s.subprocess,'Popen') as spawn,self.assertRaises(s.Hold):
                    if kind=='capture':s.capture(['SYNTHETIC-NOT-DOCKER'])
                    else:s.image_present('fmt',b'expected')
                spawn.assert_not_called()
    def child_call(self,kind):
        if kind=='capture':return s.capture(['SYNTHETIC-NOT-DOCKER'])
        return s.image_present('fmt',b'expected')
    def test_both_children_ordinary_and_base_exceptions_always_kill_and_wait(self):
        for kind in ('capture','inspect'):
            for error in (RuntimeError('synthetic'),OSError('synthetic'),KeyboardInterrupt(),SystemExit(7)):
                proc=types.SimpleNamespace(pid=987654321,wait=Mock(return_value=0))
                with self.subTest(kind=kind,error=type(error).__name__),patch.object(s.subprocess,'Popen',return_value=proc),patch.object(s,'child_status',side_effect=error),patch.object(s.os,'getpgid',return_value=proc.pid),patch.object(s.os,'killpg') as kill:
                    with self.assertRaises(type(error)):self.child_call(kind)
                    kill.assert_called_once_with(proc.pid,s.signal.SIGKILL);proc.wait.assert_called_once_with(timeout=2)
    def test_both_children_deadline_exception_inside_cleanup_boundary(self):
        for kind in ('capture','inspect'):
            proc=types.SimpleNamespace(pid=987654321,wait=Mock(return_value=0))
            with self.subTest(kind=kind),patch.object(s.subprocess,'Popen',return_value=proc),patch.object(s.time,'monotonic',side_effect=OSError('synthetic clock')),patch.object(s.os,'getpgid',return_value=proc.pid),patch.object(s.os,'killpg') as kill:
                with self.assertRaises(OSError):self.child_call(kind)
                kill.assert_called_once();proc.wait.assert_called_once_with(timeout=2)
    def test_both_children_cleanup_errors_hold_and_still_attempt_wait(self):
        import subprocess
        for kind in ('capture','inspect'):
            for failure in ('kill','wait','ownership','getpgid'):
                proc=types.SimpleNamespace(pid=987654321,wait=Mock(return_value=0))
                if failure=='wait':proc.wait.side_effect=subprocess.TimeoutExpired('synthetic',2)
                group=Mock(return_value=proc.pid if failure!='ownership' else proc.pid+1)
                if failure=='getpgid':group.side_effect=OSError('unknown ownership')
                with self.subTest(kind=kind,failure=failure),patch.object(s.subprocess,'Popen',return_value=proc),patch.object(s,'child_status',side_effect=RuntimeError('synthetic')),patch.object(s.os,'getpgid',group),patch.object(s.os,'killpg',side_effect=PermissionError('synthetic') if failure=='kill' else None) as kill:
                    with self.assertRaisesRegex(s.Hold,'CHILD_CLEANUP_UNKNOWN'):self.child_call(kind)
                    proc.wait.assert_called_once_with(timeout=2)
                    if failure in ('ownership','getpgid'):kill.assert_not_called()
                    else:kill.assert_called_once_with(proc.pid,s.signal.SIGKILL)
    def test_cleanup_failure_suppresses_otherwise_successful_child_result(self):
        import subprocess
        for kind in ('capture','inspect'):
            proc=types.SimpleNamespace(pid=987654321,wait=Mock(side_effect=subprocess.TimeoutExpired('synthetic',2)))
            status=types.SimpleNamespace(si_code=os.CLD_EXITED,si_status=0)
            with self.subTest(kind=kind),patch.object(s.subprocess,'Popen',return_value=proc),patch.object(s,'child_status',return_value=status),patch.object(s.os,'getpgid',return_value=proc.pid),patch.object(s.os,'killpg') as kill:
                with self.assertRaisesRegex(s.Hold,'CHILD_CLEANUP_UNKNOWN'):
                    if kind=='capture':s.capture(['SYNTHETIC-NOT-DOCKER'])
                    else:s.image_present('fmt',b'')
                kill.assert_called_once_with(proc.pid,s.signal.SIGKILL);proc.wait.assert_called_once_with(timeout=2)
    def test_bootstrap_original_gate_checks_after_its_protected_read(self):
        # Exact new gate AST, real protected fixture read, synthetic UID/host/
        # clock only. No bootstrap installation or execv is executed.
        source=Path('deploy/community-preview/prepare-site.sh').read_text().split("<<'PREPARE'\n",1)[1].rsplit('\nPREPARE',1)[0]
        tree=ast.parse(source);gate=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='gate')
        raw=b'{"expires_at":700,"issued_at":100}';p=json.loads(raw);self.private(self.base/'bootstrap-permit',raw)
        clock=[101]
        def read(parent,name,limit):
            value=s.read(str(self.base/'bootstrap-permit'),limit);clock[0]=701;return value
        def require(value):
            if not value:raise s.Hold('BOOTSTRAP_GATE')
        ns=dict(os=types.SimpleNamespace(getuid=lambda:0,geteuid=lambda:0,uname=lambda:types.SimpleNamespace(nodename=s.HOST)),HOST=s.HOST,read=read,base=None,raw=raw,p=p,need=require,json=json,time=types.SimpleNamespace(time=lambda:clock[0]))
        exec(compile(ast.Module(body=[gate],type_ignores=[]),'<exact-bootstrap-gate>','exec'),ns)
        with self.assertRaises(s.Hold):ns['gate']()
    def test_spawn_failure_never_signals_guessed_processgroup(self):
        for kind in ('capture','inspect'):
            with self.subTest(kind=kind),patch.object(s.subprocess,'Popen',side_effect=OSError('synthetic spawn')),patch.object(s.os,'getpgid') as group,patch.object(s.os,'killpg') as kill:
                with self.assertRaises(OSError):self.child_call(kind)
                group.assert_not_called();kill.assert_not_called()
    def test_real_owned_local_children_reaped_unrelated_child_survives(self):
        import subprocess,sys
        real=subprocess.Popen;unrelated=real([sys.executable,'-c','import time;time.sleep(10)'],start_new_session=True)
        try:
            for kind in ('capture','inspect'):
                children=[]
                def local_only(args,**kwargs):
                    child=real([sys.executable,'-c','import time;time.sleep(10)'],**kwargs);children.append(child);return child
                with self.subTest(kind=kind),patch.object(s.subprocess,'Popen',side_effect=local_only),patch.object(s,'child_status',side_effect=RuntimeError('synthetic after spawn')):
                    with self.assertRaises(RuntimeError):self.child_call(kind)
                self.assertIsNotNone(children[0].returncode)
                with self.assertRaises(ChildProcessError):os.waitpid(children[0].pid,os.WNOHANG)
                self.assertIsNone(unrelated.poll())
        finally:unrelated.terminate();unrelated.wait(timeout=2)
    def test_default_disabled_without_files_or_docker(self):
        with patch.object(s,'authorize') as a,patch.object(s,'capture') as c,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(s.main([]),2);a.assert_not_called();c.assert_not_called()
    def test_exact_frozen_carrier_and_unchanged_controller_product(self):
        raw,m=self.stage_carrier()
        self.assertEqual(json.loads(m)['files']['scripts/community_preview_update_composition.py']['sha256'],'f3007cdd26d53e7348164d404186602335ee5f237963f5d6f627e5376cfdc4f1')
    def test_stage_permit_exact_host_file_hash_scope_and_timing(self):
        p=self.permit();self.assertEqual(self.auth(p)['stage'],'install')
        for key,value in [('format',True),('host','other'),('stage','image-load'),('issued_at',True),('expires_at',100),('entry_sha256','0'*64),('snapshot_manifest_sha256','a'*64)]:
            q=dict(p);q[key]=value
            with self.subTest(key=key),self.assertRaises(s.Hold):self.auth(q,stage='install')
    def test_snapshot_needs_real_freeze_reference_not_boolean(self):
        p=self.permit('snapshot')
        with self.assertRaises(s.Hold):self.auth(p)
        p['all_writers_frozen_evidence_sha256']=True
        with self.assertRaises(s.Hold):self.auth(p)
        freeze=dict(format=1,host=s.HOST,old_id=s.OLD_ID,old_image=s.OLD_IMAGE,roots=[s.DATA+'/data',s.DATA+'/config'],issued_at=100,expires_at=700,all_writers_frozen=True,owner_review_reference_sha256='c'*64)
        self.private(s.FREEZE,s.canonical(freeze));p['all_writers_frozen_evidence_sha256']=s.sha(s.canonical(freeze));self.assertEqual(self.auth(p)['stage'],'snapshot')
        freeze['all_writers_frozen']=False;self.private(s.FREEZE,s.canonical(freeze))
        with self.assertRaises(s.Hold):self.auth(p)
    def test_protected_leaf_and_parent_symlink_or_public_mode_denied(self):
        p=self.base/'x';self.private(p,b'a');self.assertEqual(s.read(str(p),1),b'a')
        p.chmod(0o644)
        with self.assertRaises(s.Hold):s.read(str(p),1)
        p.unlink();p.symlink_to(self.data/'config'/'center-keys.json')
        with self.assertRaises((s.Hold,OSError)):s.read(str(p),100)
        link=self.base/'alias';link.symlink_to(self.data,target_is_directory=True)
        with self.assertRaises((s.Hold,OSError)):s.directory(str(link))
    def test_install_exact_carrier_without_changing_service_or_existing_paths(self):
        _,manifest=self.stage_carrier();r=s.install()
        self.assertFalse(r['update_executed']);self.assertEqual(Path(s.INSTALL+'/manifest.json').read_bytes(),manifest)
        self.assertEqual(Path(s.INSTALL+'/loader.py').stat().st_mode&0o777,0o600)
        self.assertEqual((self.base/'update-journal').stat().st_mode&0o777,0o700)
        with self.assertRaisesRegex(s.Hold,'EXISTING_INSTALL'):s.install()
    def test_install_rejects_bad_carrier_before_target_write(self):
        self.private(self.input/'control-oci2330-v1.zip',b'bad')
        with self.assertRaises(s.Hold):s.install()
        self.assertFalse(Path(s.INSTALL).exists());self.assertFalse((self.base/'update-journal').exists())
    def test_snapshot_full_private_dataset_readback_and_no_live_changes(self):
        before=s.copy_roots(s.DATA,None);r=self.snapshot()
        self.assertEqual(s.copy_roots(s.DATA,None),before);self.assertEqual(s.copy_roots(s.BACKUP+'/snapshot',None),before)
        self.assertEqual(r['manifest_sha256'],s.sha(s.read(s.BACKUP+'/private-manifest.json',8*1024*1024)))
        self.assertFalse(r['recovery_verified']);self.assertFalse(r['downgrade_verified'])
        self.assertIn('center.sqlite-wal',before['data']['entries']);self.assertIn('center-keys.json',before['config']['entries'])
        self.assertEqual(Path(s.BACKUP+'/private-manifest.json').stat().st_mode&0o777,0o600)
    def test_snapshot_no_freeze_actual_container_denial_before_writes(self):
        fake=types.SimpleNamespace(inspect_bound=lambda *a:{'running':True})
        with patch.object(s,'component',return_value=fake),self.assertRaisesRegex(s.Hold,'NOT_STOPPED'):
            s.snapshot({'all_writers_frozen_evidence_sha256':'a'*64})
        self.assertFalse(Path(s.BACKUP).exists())
    def test_freeze_guard_rejects_old_retained_id_when_current_name_changed(self):
        fake=types.SimpleNamespace(inspect_bound=lambda *a:{'running':False})
        for row,allowed in (([s.OLD_ID,s.OLD_IMAGE,False],True),(['a'*64,s.NEW_IMAGE,True],False),([s.OLD_ID,s.OLD_IMAGE,0],False)):
            raw=b'\n'.join(s.canonical(v) for v in row)
            with patch.object(s,'component',return_value=fake),patch.object(s,'capture',return_value=raw),patch.object(s.os,'lstat',side_effect=FileNotFoundError):
                if allowed:s.stopped()
                else:
                    with self.assertRaisesRegex(s.Hold,'ORIGINAL_NAME_NOT_BOUND'):s.stopped()
    def test_snapshot_existing_partial_preserved_not_reused(self):
        self.snapshot();raw=Path(s.BACKUP+'/private-manifest.json').read_bytes()
        with patch.object(s,'stopped'),self.assertRaises(FileExistsError):s.snapshot({'all_writers_frozen_evidence_sha256':'a'*64})
        self.assertEqual(Path(s.BACKUP+'/private-manifest.json').read_bytes(),raw)
    def test_snapshot_source_change_holds_without_completed_manifest(self):
        original=s.copy_roots;n=[0]
        def changing(a,b):
            r=original(a,b);n[0]+=1
            if n[0]==2:r['data']['bytes']+=1
            return r
        with patch.object(s,'stopped'),patch.object(s,'copy_roots',side_effect=changing),self.assertRaises(s.Hold):s.snapshot({'all_writers_frozen_evidence_sha256':'a'*64})
        self.assertFalse(Path(s.BACKUP+'/private-manifest.json').exists());self.assertTrue(Path(s.BACKUP+'/snapshot').exists())
    def test_expiry_after_readback_cannot_publish_backup_proof(self):
        actual=s.copy_roots;expired=[False]
        def copy(src,dst):
            result=actual(src,dst)
            if src==s.BACKUP+'/snapshot' and dst is None:expired[0]=True
            return result
        def gate():
            if expired[0]:raise s.Hold('STAGE_APPROVAL_EXPIRED')
        with patch.object(s,'stopped'),patch.object(s,'copy_roots',side_effect=copy),patch.object(s,'checkpoint',side_effect=gate),self.assertRaises(s.Hold):s.snapshot({'all_writers_frozen_evidence_sha256':'a'*64})
        self.assertTrue(Path(s.BACKUP+'/snapshot').exists());self.assertFalse(Path(s.BACKUP+'/private-manifest.json').exists())
    def test_bounded_names_python36_compat_uses_verified_proc_fd_path(self):
        fd=s.directory(s.DATA+'/data')
        try:
            real=s.os.scandir;seen=[]
            def no_fd_scandir(path):
                self.assertIsInstance(path,str)
                seen.append(path)
                return real(path)
            with patch.object(s.os,'scandir',side_effect=no_fd_scandir):
                names=s.bounded_names(fd)
            self.assertIn('center.sqlite',names)
            self.assertIn('center.sqlite-wal',names)
            self.assertEqual(len(seen),1)
            self.assertTrue(seen[0].startswith('/proc/self/fd/'))
            self.assertTrue(seen[0].rsplit('/',1)[1].isdigit())
        finally:
            os.close(fd)
    def test_bounded_names_enumeration_error_is_bounded_hold(self):
        fd=s.directory(s.DATA+'/data')
        try:
            with patch.object(s.os,'scandir',side_effect=PermissionError('private path must not escape')):
                with self.assertRaisesRegex(s.Hold,'TREE_ENUMERATION_UNKNOWN'):
                    s.bounded_names(fd)
        finally:
            os.close(fd)
    def test_bounded_names_rejects_proc_fd_identity_mismatch(self):
        fd=s.directory(s.DATA+'/data')
        other=s.directory(s.DATA+'/config')
        real=s.os.stat
        proc_path='/proc/self/fd/'+str(fd)
        try:
            def wrong_identity(path,*args,**kwargs):
                if path==proc_path:
                    return real('/proc/self/fd/'+str(other))
                return real(path,*args,**kwargs)
            with patch.object(s.os,'stat',side_effect=wrong_identity):
                with self.assertRaisesRegex(s.Hold,'TREE_ENUMERATION_UNKNOWN'):
                    s.bounded_names(fd)
        finally:
            os.close(fd);os.close(other)
    def test_tree_denies_links_specials_public_files_and_budget(self):
        p=self.data/'data'/'bad';p.symlink_to('/etc/passwd')
        with self.assertRaises(s.Hold):s.copy_roots(s.DATA,None)
        p.unlink();os.link(str(self.data/'data'/'center.sqlite'),str(p))
        with self.assertRaises(s.Hold):s.copy_roots(s.DATA,None)
        p.unlink();self.private(p,b'long');p.chmod(0o644)
        with self.assertRaises(s.Hold):s.copy_roots(s.DATA,None)
        p.chmod(0o600)
        with patch.object(s,'MAX_BYTES',1),self.assertRaises(s.Hold):s.copy_roots(s.DATA,None)
        with patch.object(s,'MAX_FILES',1),self.assertRaises(s.Hold):s.copy_roots(s.DATA,None)
    def test_clones_real_copies_synthetic_semantics_no_active_restore(self):
        r=self.snapshot();live=s.copy_roots(s.DATA,None)
        result={'format':1,'original_host_open':True,'center_integrity':True,'stores':[['SYNTHETIC']]}
        with patch.object(s,'clone_run',return_value=result) as run:out=s.validate_clones({'snapshot_manifest_sha256':r['manifest_sha256']})
        self.assertEqual([c.args for c in run.call_args_list],[('restore-old',s.OLD_IMAGE),('verify-f131',s.NEW_IMAGE),('verify-downgrade',s.OLD_IMAGE)])
        self.assertTrue(out['downgrade_logical_equality']);self.assertFalse(out['production_acceptance']);self.assertFalse(out['rollback_health_acceptance'])
        self.assertEqual(s.copy_roots(s.DATA,None),live)
    def test_clones_downgrade_difference_no_success_receipt(self):
        r=self.snapshot();a={'original_host_open':True,'center_integrity':True,'stores':['old']};b=dict(a,stores=['changed'])
        with patch.object(s,'clone_run',side_effect=[a,b,b]),self.assertRaises(s.Hold):s.validate_clones({'snapshot_manifest_sha256':r['manifest_sha256']})
        self.assertFalse(Path(s.BACKUP+'/clone-results.json').exists())
    def test_clones_manifest_tamper_or_old_digest_zero_container_calls(self):
        r=self.snapshot()
        for digest in ('0'*64,r['manifest_sha256']):
            if digest==r['manifest_sha256']:self.private(s.BACKUP+'/snapshot/config/center-keys.json',b'tampered')
            with patch.object(s,'clone_run') as run,self.assertRaises(s.Hold):s.validate_clones({'snapshot_manifest_sha256':digest})
            run.assert_not_called()
    def test_exact_container_args_no_live_mount_network_or_service(self):
        with patch.object(s,'capture',return_value=b'{"original_host_open":true}') as c:
            s.clone_run('verify-f131',s.NEW_IMAGE);args=c.call_args.args[0]
        self.assertEqual(args[:4],s.DOCKER+['run']);self.assertIn('none',args);self.assertIn('--pull',args);self.assertIn('never',args)
        self.assertNotIn('host',args);self.assertNotIn('--privileged',args);self.assertNotIn('--publish',args)
        mounts=[args[i+1] for i,v in enumerate(args) if v=='--mount']
        self.assertTrue(all('src='+s.BACKUP+'/verify-f131/' in m for m in mounts));self.assertNotIn('listen(',s.CLONE_CODE)
        self.assertIn('h.center.check_integrity()',s.CLONE_CODE);self.assertIn('PRAGMA foreign_key_check',s.CLONE_CODE)
        self.assertNotIn('configure_ocr',s.CLONE_CODE)
    def test_image_wrong_outer_or_expired_zero_load(self):
        self.private(self.input/'artifact12546452389.zip',b'bad')
        with patch.object(s,'capture') as c,self.assertRaises(s.Hold):s.image_load()
        c.assert_not_called()
        with patch.object(s.time,'time',return_value=s.EXPIRES),patch.object(s,'read') as r,self.assertRaises(s.Hold):s.image_load()
        r.assert_not_called()
    def test_clone_program_real_sqlite_row_factory_and_private_digest_only(self):
        import sys
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE sample(v TEXT)');db.execute("INSERT INTO sample VALUES('SYNTHETIC_PRIVATE_VALUE')");db.commit()
        class CenterFixture:
            def check_integrity(owner):
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        center=CenterFixture();center.db=db
        host=types.SimpleNamespace(center=center,persistence=types.SimpleNamespace(handles=[]),close=db.close)
        class HostFacade:
            @staticmethod
            def open(*args):
                self.assertEqual(args,('/var/lib/xuanjun-community-preview/config/host.json','/var/lib/xuanjun-community-preview/config/center-keys.json','/var/lib/xuanjun-community-preview/config/wechat.json'))
                return host
        # The host/Center facade is synthetic; actual SQLite and exact production
        # clone program execute. This is NOT actual-image or real-identity proof.
        output=io.StringIO()
        with patch.dict(sys.modules,{'scripts.community_platform_host':types.SimpleNamespace(PlatformHost=HostFacade)}),contextlib.redirect_stdout(output):
            exec(compile(s.CLONE_CODE,'<exact-clone-program>','exec'),{})
        value=json.loads(output.getvalue());self.assertTrue(value['original_host_open']);self.assertEqual(value['stores'][0][0][0],'sample')
        self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',output.getvalue())
    def test_fixed_image_import_durable_intent_unknown_never_retries(self):
        with patch.object(s,'daemon_capacity'),patch.object(s,'image_present',return_value=False),patch.object(s,'capture',side_effect=s.Hold('COMMAND_UNKNOWN_NO_RETRY')) as run:
            with self.assertRaises(s.Hold):s._load_fixed_archive(b'SYNTHETIC','fmt',b'expected')
            self.assertEqual(run.call_count,1)
            self.assertEqual(run.call_args.args[0],s.DOCKER+['image','load','--input',s.INPUT+'/community-backend-image.tar.gz'])
            self.assertTrue((self.input/'image-load-intent.json').exists());self.assertFalse((self.input/'image-load-observed.json').exists())
            with self.assertRaises(FileExistsError):s._load_fixed_archive(b'SYNTHETIC','fmt',b'expected')
            self.assertEqual(run.call_count,1)
    def test_exact_existing_image_reused_without_file_write_or_load(self):
        with patch.object(s,'image_present',return_value=True),patch.object(s,'capture') as run:
            r=s._load_fixed_archive(b'SYNTHETIC','fmt',b'expected')
        self.assertTrue(r['existing_exact_image_reused']);run.assert_not_called();self.assertFalse((self.input/'image-load-intent.json').exists())
    def test_daemon_storage_unknown_or_split_device_holds_before_load(self):
        for value in ({'root':'/unknown','driver':'overlayfs'},{'root':True,'driver':'overlay2'}):
            with patch.object(s,'capture',return_value=s.canonical(value)),patch.object(s,'directory') as read,self.assertRaises(s.Hold):s.daemon_capacity()
            read.assert_not_called()
    def test_daemon_metadata_bounded_exact_storage_and_change(self):
        root=self.root/'docker';root.mkdir(mode=0o700)
        for name in ('overlay2','image','tmp'):(root/name).mkdir(mode=0o700)
        (root/'image'/'overlay2').mkdir(mode=0o700)
        value={'root':str(root),'driver':'overlay2'}
        with patch.object(s,'capture',return_value=s.canonical(value)),patch.object(s,'space') as capacity:s.daemon_capacity()
        self.assertEqual(capacity.call_count,4)
        with patch.object(s,'capture',side_effect=[s.canonical(value),s.canonical(dict(value,root='/different'))]),self.assertRaisesRegex(s.Hold,'STORAGE_CHANGED'):s.daemon_capacity()
    def test_image_success_receipt_only_after_exact_inspection(self):
        with patch.object(s,'daemon_capacity'),patch.object(s,'image_present',return_value=False),patch.object(s,'capture',side_effect=[b'Loaded',b'expected']) as run:
            r=s._load_fixed_archive(b'SYNTHETIC','fmt',b'expected')
        self.assertEqual(run.call_count,2);self.assertFalse(r['service_changed']);self.assertTrue((self.input/'image-load-observed.json').exists())
    def test_actual_space_deficit_refuses_without_writes(self):
        fd=os.open(str(self.base),os.O_RDONLY|os.O_DIRECTORY)
        try:
            # Execute the production function body from exact AST, genuine FD,
            # synthetic fstatvfs metadata to make deterministic zero capacity.
            tree=ast.parse(Path(s.__file__).read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='space')
            ns={'os':types.SimpleNamespace(fstatvfs=lambda fd:types.SimpleNamespace(f_bavail=0,f_frsize=4096,f_favail=0)),'need':s.need,'RESERVE':s.RESERVE}
            exec(compile(ast.Module(body=[node],type_ignores=[]),'<exact-production-space>','exec'),ns)
            with self.assertRaises(s.Hold):ns['space'](fd,100,1)
        finally:os.close(fd)
    def test_wrapper_keeps_installed_a_entry_hash_and_syntax(self):
        import subprocess
        script=Path('deploy/community-preview/prepare-site.sh').read_bytes()
        self.assertIn(b'48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55',script)
        self.assertNotEqual(s.sha(Path(s.__file__).read_bytes()),'48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55')
        self.assertEqual(subprocess.run(['/bin/sh','-n'],input=script,capture_output=True,timeout=2).returncode,0)
    def test_bounded_child_and_default_source_python36(self):
        import sys
        self.assertEqual(s.capture([sys.executable,'-c','print("ok")']).strip(),b'ok')
        with self.assertRaises(s.Hold):s.capture([sys.executable,'-c','import time;time.sleep(2)'],timeout=.05)
        with self.assertRaises(s.Hold):s.capture([sys.executable,'-c','import os;os.write(1,b"x"*20000)'])
        ast.parse(Path(s.__file__).read_text(),feature_version=(3,6))
    def test_image_inspect_failure_not_absence(self):
        import subprocess
        # Exact error branch unit uses finite local child payload, no daemon.
        expected=b'fixed';real=subprocess.Popen
        for code,out,err,allowed in [(0,b'fixed',b'',True),(1,b'[]',('Error: No such image: '+s.NEW_IMAGE).encode(),False)]:
            script='import os;os.write(1,'+repr(out)+');os.write(2,'+repr(err)+');raise SystemExit('+str(code)+')'
            def launch(args,**kw):return real(['/usr/bin/python3','-c',script],**kw)
            with patch.object(s.subprocess,'Popen',side_effect=launch):self.assertEqual(s.image_present('fmt',expected),allowed)
        script='import os;os.write(2,b"permission denied SECRET");raise SystemExit(1)'
        with patch.object(s.subprocess,'Popen',side_effect=launch),self.assertRaises(s.Hold):s.image_present('fmt',expected)

if __name__=='__main__':unittest.main()
