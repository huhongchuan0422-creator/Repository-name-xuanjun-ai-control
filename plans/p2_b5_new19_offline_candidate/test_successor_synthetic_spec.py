"""Explicit isolated six-slot data; production pins remain unchanged."""
import copy
import hashlib
import json
import pathlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from unittest.mock import patch

HERE=pathlib.Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'successor_controller'),str(HERE/'reused-6825'),
              str(HERE/'new19-source')]
import pr17_b5_successor_review as c53
from pr17_b5_successor_release_gate import ExternalReleaseGate
from pr17_b5_successor_witness import SuccessorEvidenceStore
import test_successor_bundle_offline as six
from test_successor_release_gate import fixture_gate
from pr17_b5_successor_witness import WitnessStore
from test_successor_os_boundary import SealedOSBoundary
import pr17_b5_successor_entry as entry
from production.cloud_connection.queue import EXISTING_SCHEMA


class SyntheticSpec:
    """Only fixture digests are changed in memory, never the shipped spec."""
    def __init__(self):
        sample=six.SyntheticSixSlotTests();sample.setUp()
        self.source=sample.source
        self.baselines=dict(sample.baselines)
        self.spec=copy.deepcopy(sample.spec)
        self.object_bytes={}
        for number,obj in enumerate(self.spec['objects'],1):
            seed=hashlib.sha256(('synthetic-object-%02d:%s'%
                (number,obj['relative_path'])).encode()).digest()
            size=obj['bytes']
            raw=(seed*((size+len(seed)-1)//len(seed)))[:size]
            self.object_bytes[obj['relative_path']]=raw
            obj['sha256']=c53.sha(raw)
        resource=json.loads(self.baselines[c53.CONFIGS[1]])
        resource['settings'].update(
            issuer='https://fixture.invalid/issuer',
            endpoint='https://fixture.invalid/introspect',
            audience='https://fixture.invalid/resource')
        self.baselines[c53.CONFIGS[1]]=c53.canon(resource)
        resource_sha=c53.sha(self.baselines[c53.CONFIGS[1]])
        self.baselines[c53.CONFIGS[2]]=(
            'OAUTH_CONFIG_SHA256='+resource_sha+'\n'
            'OAUTH_SOURCE_MANIFEST_SHA256='+c53.binder.E78_MANIFEST+'\n'
            'SSL_CERT_FILE='+c53.binder.CERT+'\n').encode()
        for path in c53.CONFIGS[:2]+c53.SLOTS:
            self.spec['observed_baseline']['files'][path]={
                'bytes':len(self.baselines[path]),
                'sha256':c53.sha(self.baselines[path])}
        self.raw=c53.canon(self.spec)
        self.spec_sha=c53.sha(self.raw)
        self.resource_sha=resource_sha

    @staticmethod
    def _write_sparse_gnu_tar(path,members,total_bytes=559237632):
        import tarfile
        headers=[]
        for name,data in members:
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600
            info.uid=0;info.gid=0;info.mtime=0
            headers.append((info.tobuf(format=tarfile.GNU_FORMAT),data))
        occupied=sum(len(header)+((len(data)+511)//512)*512
                     for header,data in headers)
        filler=tarfile.TarInfo('unselected-filler.bin')
        filler.mode=0o600;filler.uid=0;filler.gid=0;filler.mtime=0
        filler_bytes=total_bytes-occupied-512-1024
        if filler_bytes<=0 or filler_bytes%512:
            raise AssertionError('FIXTURE_FILLER_ALIGNMENT')
        filler.size=filler_bytes
        with path.open('xb') as out:
            for header,data in headers:
                out.write(header);out.write(data)
                padding=(-len(data))%512
                if padding:out.write(bytes(padding))
            out.write(filler.tobuf(format=tarfile.GNU_FORMAT))
            out.seek(filler_bytes,os.SEEK_CUR)
            out.write(bytes(1024));out.flush();os.fsync(out.fileno())
        path.chmod(0o600)
        if path.stat().st_size!=total_bytes:
            raise AssertionError('FIXTURE_ARCHIVE_SIZE')

    def original_fixture(self,root,create):
        root=pathlib.Path(root)
        archive_root=root/c53.binder.ARCHIVE_ROOT.lstrip('/')
        package_root=root/c53.binder.PACKAGE_ROOT.lstrip('/')
        archive=archive_root/'source-tree.tar.pending'
        if create:
            archive_root.mkdir(parents=True,mode=0o700)
            package_root.mkdir(parents=True,mode=0o700)
            members=[]
            for number,obj in enumerate(self.spec['objects']):
                raw=self.object_bytes[obj['relative_path']]
                if number<5:
                    members.append((c53.binder.ARCHIVE_PREFIX+
                                    obj['relative_path'],raw))
                else:
                    target=package_root/obj['relative_path']
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.parent.chmod(0o700)
                    target.write_bytes(raw);target.chmod(0o600)
            self._write_sparse_gnu_tar(archive,members)
        if not archive.is_file():
            raise AssertionError('FIXTURE_ARCHIVE_ABSENT')
        digest=hashlib.sha256()
        with archive.open('rb') as stream:
            while True:
                block=stream.read(1024*1024)
                if not block:break
                digest.update(block)
        st=archive.stat()
        identity=(st.st_dev,st.st_ino,st.st_mode,0,0,st.st_nlink,
                  st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        return {'sha256':digest.hexdigest(),'identity':identity}

    def active(self,archive=None):
        stack=ExitStack()
        stack.enter_context(patch.object(c53.binder,'RESOURCE_SHA',self.resource_sha))
        stack.enter_context(patch.object(c53.binder,'SPEC_SHA256',self.spec_sha))
        stack.enter_context(patch.object(c53,'SPEC_CANON_SHA',
                                         c53.sha(c53.canon(self.spec))))
        if archive is not None:
            stack.enter_context(patch.object(c53.binder,'ARCHIVE_SHA',
                                             archive['sha256']))
            stack.enter_context(patch.object(c53.binder,'ARCHIVE_IDENTITY',
                                             tuple(archive['identity'])))
            roots={'b5-original-archive':[c53.binder.ARCHIVE_ROOT,0],
                   'b5-original-packages':[c53.binder.PACKAGE_ROOT,0]}
            meta=dict(filename='source-tree.tar.pending',
                identity=list(archive['identity']),
                member_prefix=c53.binder.ARCHIVE_PREFIX,max_headers=65536,
                max_read_bytes=32*1024*1024,sha256=archive['sha256'])
            stack.enter_context(patch.object(c53,'ROOTS',roots))
            stack.enter_context(patch.object(c53,'ARCHIVE_META',meta))
        return stack


class SyntheticSpecTests(unittest.TestCase):
    def setUp(self):
        self.fixture=SyntheticSpec()

    def test_real_verify_generate_validate_and_release_gate(self):
        f=self.fixture
        with f.active():
            spec=c53.binder.verify_spec_bytes(f.raw)
            c53.verify_observed_bytes(spec,f.baselines)
            bundle=c53.make_bundle(spec,f.baselines,f.source,
                batch_id='isolated-unit-batch-20261024',
                approval_ref='fixture-only',window_start=1792830000)
            self.assertTrue(c53.validate_bundle(spec,bundle,
                verified_baselines=f.baselines,verified_source_blobs=f.source))
            # The external binder is a fixture with this exact synthetic
            # spec digest; the real release gate still hashes all controller
            # and runtime bytes on every phase.
            gate=fixture_gate(spec,'publish')
            self.assertEqual(gate.check('publish',spec),'a'*40)
            with tempfile.TemporaryDirectory() as parent:
                root=pathlib.Path(parent)/'evidence';root.mkdir(mode=0o700)
                (root/'register.lock').write_bytes(b'')
                os.chmod(root/'register.lock',0o600)
                store=SuccessorEvidenceStore(str(root),enabled=True,
                                             test_only=True,clock=lambda:1792830001)
                binding={'batch':'isolated-unit-batch-20261024',
                    'job':spec['fixed_paths']['job_proposed'],'attempt':'fixture-attempt',
                    'ids':spec['batch']['draft_request_ids'],
                    'catalog_sha256':bundle['catalog_sha'],
                    'recipient':c53.RECIP,'project':c53.PROJ,
                    'subject':c53.SUBJECT,'commit':c53.COMMIT,
                    'valid_from':1792830000,'valid_until':1792833600}
                record=json.loads(gate.read_binder())
                keys=('controller_commit','controller_manifest_sha256',
                      'controller_code_pin_sha256','successor_spec_sha256',
                      'runtime_manifest_sha256','runtime_code_pin_sha256',
                      'target_release')
                payload={key:record[key] for key in keys}
                payload.update(binder_sha256=c53.sha(gate.read_binder()),
                               catalog_sha256=bundle['catalog_sha'])
                store.register_exact(binding,'release',source_id='fixture-version',
                    source_raw=b'fixture source record',
                    witness_identity='fixture-registrar',payload=payload)
                registered=ExternalReleaseGate.from_registered(store,binding,
                    read_binder=gate.read_binder,
                    read_manifest=gate.read_manifest,
                    read_source=gate.read_source,
                    read_current=gate.read_current,
                    read_installed_runtime=gate.read_installed_runtime)
                self.assertEqual(registered.check('publish',spec),'a'*40)
        self.assertEqual(len(bundle['requests']),19)
        self.assertFalse(bundle['authority_verified'])

    def test_each_slot_change_and_spec_change_rejected(self):
        f=self.fixture
        with f.active():
            for path in c53.CONFIGS[:2]+c53.SLOTS:
                changed=dict(f.baselines)
                changed[path]+=b'X'
                with self.subTest(path=path),self.assertRaisesRegex(
                        c53.Hold,'BASELINE_HASH_CHANGED'):
                    c53.verify_observed_bytes(f.spec,changed)
            with self.assertRaisesRegex(Exception,'SUCCESSOR_SPEC_BYTES_CHANGED'):
                c53.binder.verify_spec_bytes(f.raw+b' ')

    def test_runtime_source_change_rejected(self):
        f=self.fixture
        with f.active():
            changed=dict(f.source)
            changed['production/cloud_connection/queue.py']+=b'X'
            with self.assertRaisesRegex(Exception,'SOURCE_BYTES_CHANGED'):
                c53.make_bundle(f.spec,f.baselines,changed,
                    batch_id='isolated-unit-batch-20261024',
                    approval_ref='fixture-only',window_start=1792830000)

    def test_actual_entry_prepare_uses_fixed_tree_and_registered_stores(self):
        f=self.fixture
        start=int(time.time())-10
        with f.active():
            spec=c53.binder.verify_spec_bytes(f.raw)
            with tempfile.TemporaryDirectory() as temp:
                root=pathlib.Path(temp)
                archive=f.original_fixture(root,True)
                with f.active(archive):
                    bundle=c53.make_bundle(spec,f.baselines,f.source,
                        batch_id='c53-recovery-draft',approval_ref='fixture-only',
                        window_start=start)
                gate=fixture_gate(spec)
                files={entry.SPEC:f.raw,
                    entry.BINDER:gate.read_binder(),
                    entry.MANIFEST:gate.read_manifest()}
                files.update(f.baselines)
                files.update({entry.SOURCE+'/'+name:raw
                              for name,raw in f.source.items()})
                files.update({entry.ROOT+'/'+row['path']:
                              gate.read_source(row['path'])
                              for row in json.loads(gate.read_manifest())['files']})
                database=root/c53.DB.lstrip('/')
                database.parent.mkdir(parents=True,exist_ok=True)
                con=sqlite3.connect(str(database))
                for sql in EXISTING_SCHEMA.values():
                    con.execute(sql)
                con.execute('CREATE TABLE connection_cursor '
                            '(id INTEGER PRIMARY KEY CHECK(id=1), since TEXT NOT NULL)')
                con.execute('CREATE TABLE connection_outbox '
                            '(request_id TEXT PRIMARY KEY, body TEXT NOT NULL, '
                            "state TEXT NOT NULL CHECK(state IN ('READY','POSTING','SENT','UNKNOWN')), "
                            'comment_id INTEGER)')
                con.execute('INSERT INTO connection_jobs VALUES (?,?,?,?,?,?,?,?)',
                    ('fixture-historical-success','other-project','{}','0'*64,
                     332398908,'SUCCESS','historical-invoke','x'*20000))
                con.commit();con.close()
                database.chmod(0o600)
                lock=root/c53.LOCK.lstrip('/')
                lock.write_bytes(b'');lock.chmod(0o600)
                receiver=root/spec['fixed_paths']['receiver_root'].lstrip('/')
                receiver.mkdir(parents=True,mode=0o700)
                for path,raw in files.items():
                    target=root/path.lstrip('/')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(raw)
                    target.chmod(0o600 if path in f.baselines else 0o644)
                for base in c53.BASES:
                    current=root/(base+'/current').lstrip('/')
                    current.parent.mkdir(parents=True,exist_ok=True)
                    (root/(base+'/releases').lstrip('/')).mkdir(
                        parents=True,exist_ok=True)
                    current.symlink_to(base+'/releases/'+spec['source']['old_release'])
                for store_root in (WitnessStore.__init__.__globals__['ROOT'],
                                  SuccessorEvidenceStore.__init__.__globals__['SUCCESSOR_ROOT']):
                    target=root/store_root.lstrip('/')
                    target.mkdir(parents=True,mode=0o700)
                    (target/'register.lock').write_bytes(b'')
                    (target/'register.lock').chmod(0o600)
                allowed=set(files)|{spec['fixed_paths']['receiver_root'],
                                   c53.DB,c53.LOCK,c53.DB+'-wal',
                                   c53.DB+'-shm',c53.DB+'-journal',
                                   entry.SOURCE,entry.ROOT,entry.SPEC,
                                   entry.BINDER,entry.MANIFEST,
                                   *c53.BASES}
                allowed.update((WitnessStore.__init__.__globals__['ROOT'],
                                SuccessorEvidenceStore.__init__.__globals__['SUCCESSOR_ROOT']))
                allowed.update(base+'/current' for base in c53.BASES)
                original_paths={c53.binder.ARCHIVE_ROOT,c53.binder.PACKAGE_ROOT,
                    c53.binder.ARCHIVE_ROOT+'/source-tree.tar.pending'}
                original_paths.update(c53.binder.PACKAGE_ROOT+'/'+obj['relative_path']
                                      for obj in spec['objects'][5:])
                allowed.update(original_paths)
                job_root=spec['fixed_paths']['job_proposed']
                release_roots=(*spec['fixed_paths']['stage_proposed'],
                               *spec['fixed_paths']['target_release'])
                generated_roots=(job_root,*release_roots)
                replace_stages=tuple(path+'.l2-b5-staged-'+c53.COMMIT[:12]
                    for path in c53.CONFIGS+c53.SLOTS)
                current_stages=tuple(base+'/current.l2-b5-staged-'+c53.COMMIT[:12]
                    for base in c53.BASES)
                allowed.update(generated_roots+replace_stages+current_stages)
                pins={path:(target.stat().st_dev,target.stat().st_ino)
                      for path in files if (target:=root/path.lstrip('/')).exists()}
                pins[c53.DB]=(spec['observed_baseline']['db']['dev'],
                               spec['observed_baseline']['db']['ino'])
                pins[c53.LOCK]=(spec['observed_baseline']['worker_lock']['dev'],
                                 spec['observed_baseline']['worker_lock']['ino'])
                for path in original_paths:
                    target=root/path.lstrip('/')
                    if target.is_file():
                        st=target.stat();pins[path]=(st.st_dev,st.st_ino)
                store_roots=(WitnessStore.__init__.__globals__['ROOT'],
                             SuccessorEvidenceStore.__init__.__globals__['SUCCESSOR_ROOT'])
                boundary=SealedOSBoundary(root,allowed,pins,
                    dynamic_roots=store_roots+(job_root,),
                    recursive_dynamic_roots=release_roots+
                        (spec['fixed_paths']['receiver_root'],))
                binding=entry._binding(spec,'c53-recovery-draft','fixture-attempt',
                                       start,bundle['catalog_sha'])
                record=json.loads(gate.read_binder())
                keys=('controller_commit','controller_manifest_sha256',
                      'controller_code_pin_sha256','successor_spec_sha256',
                      'runtime_manifest_sha256','runtime_code_pin_sha256',
                      'target_release')
                payload={key:record[key] for key in keys}
                payload.update(binder_sha256=c53.sha(gate.read_binder()),
                               catalog_sha256=bundle['catalog_sha'])
                actual_uname=os.uname()
                synthetic_uname=type(actual_uname)((actual_uname.sysname,c53.HOST,
                    actual_uname.release,actual_uname.version,actual_uname.machine))
                original_connect=sqlite3.connect
                class DatabaseList:
                    def __init__(self,cursor):self.cursor=cursor
                    def fetchall(self):
                        rows=self.cursor.fetchall()
                        return [(n,label,c53.DB if path==str(database) else path)
                                for n,label,path in rows]
                class SQLiteBoundary:
                    def __init__(self,connection):self.connection=connection
                    def execute(self,sql,*args):
                        result=self.connection.execute(sql,*args)
                        return DatabaseList(result) if sql=='PRAGMA database_list' else result
                    def __getattr__(self,name):return getattr(self.connection,name)
                def connect(path,*args,**kwargs):
                    if path=='file:'+c53.DB+'?mode=ro':
                        path='file:'+str(database)+'?mode=ro'
                        return SQLiteBoundary(original_connect(path,*args,**kwargs))
                    if type(path) is str and path.startswith('file:/proc/self/fd/'):
                        return SQLiteBoundary(original_connect(path,*args,**kwargs))
                    return original_connect(path,*args,**kwargs)
                with boundary.active(),patch.object(sqlite3,'connect',side_effect=connect),\
                     patch.object(os,'uname',return_value=synthetic_uname),\
                     patch.object(os,'geteuid',return_value=0),\
                     patch.object(os,'getegid',return_value=0),\
                     patch.dict(os.environ,{'SUDO_UID':'1000'}),\
                     patch.object(entry,'__file__',entry.ROOT+
                                  '/successor_controller/pr17_b5_successor_entry.py'),\
                     patch.object(entry,'LOCAL_ROOT',entry.ROOT):
                    witness,evidence=entry._stores()
                    witness.register(binding,owner_source_id='fixture-owner',
                        owner_source_raw=b'fixture-only owner statement',
                        analyst_source_id='fixture-analyst',
                        analyst_source_raw=b'fixture-only analyst statement',
                        witness_identity='fixture-registrar')
                    evidence.register_exact(binding,'release',
                        source_id='fixture-version',source_raw=b'fixture source record',
                        witness_identity='fixture-registrar',payload=payload)
                    # First admission/execute runs in a fresh interpreter below.
                    # Parent setup stops after immutable witness/release registration;
                    # inherited CI/test-harness descriptors must not be normalized away.
                execute=subprocess.run([sys.executable,'-B',str(HERE/
                    'test_successor_synthetic_spec.py'),'--child-execute',str(root),str(start)],
                    capture_output=True,text=True,timeout=20,check=False,close_fds=True)
                self.assertEqual(execute.returncode,0,execute.stderr+'\\n'+execute.stdout)
                executed=json.loads(execute.stdout)
                self.assertEqual(executed['state'],'WINDOW_ENABLED_NOT_DELIVERED',executed)
                self.assertEqual(executed['new_requests'],0)
                child=subprocess.run([sys.executable,'-B',str(HERE/
                    'test_successor_synthetic_spec.py'),'--child-query',str(root)],
                    capture_output=True,text=True,timeout=20,check=False)
                self.assertEqual(child.returncode,0,child.stderr+'\n'+child.stdout)
                self.assertEqual(json.loads(child.stdout)['state'],
                                 'WINDOW_ENABLED_NO_POST')
                intake=subprocess.run([sys.executable,'-B',str(HERE/
                    'test_successor_synthetic_spec.py'),'--child-intake',str(root)],
                    capture_output=True,text=True,timeout=20,check=False)
                self.assertEqual(intake.returncode,0,intake.stderr+'\n'+intake.stdout)
                self.assertEqual(json.loads(intake.stdout)['state'],
                                 'INTAKE_SENT_AWAITING_READY')
                pending=subprocess.run([sys.executable,'-B',str(HERE/
                    'test_successor_synthetic_spec.py'),'--child-query',str(root)],
                    capture_output=True,text=True,timeout=20,check=False)
                self.assertEqual(pending.returncode,0,pending.stderr+'\n'+pending.stdout)
                self.assertEqual(json.loads(pending.stdout)['state'],
                                 'UNKNOWN_OR_PENDING_NO_REPOST')
                premature=subprocess.run([sys.executable,'-B',str(HERE/
                    'test_successor_synthetic_spec.py'),'--child-recover',str(root)],
                    capture_output=True,text=True,timeout=20,check=False)
                self.assertEqual(premature.returncode,0,
                                 premature.stderr+'\n'+premature.stdout)
                self.assertEqual(json.loads(premature.stdout)['state'],
                                 'UNKNOWN_OR_PENDING_NO_REPOST')
                for action,expected in (('--child-worker-ready',
                                           'UNKNOWN_OR_PENDING_NO_REPOST'),
                                          ('--child-worker-success',
                                           'SUCCESS_SNAPSHOT_READONLY')):
                    worker=subprocess.run([sys.executable,'-B',str(HERE/
                        'test_successor_synthetic_spec.py'),action,str(root)],
                        capture_output=True,text=True,timeout=20,check=False)
                    self.assertEqual(worker.returncode,0,worker.stderr+'\n'+worker.stdout)
                    observed=subprocess.run([sys.executable,'-B',str(HERE/
                        'test_successor_synthetic_spec.py'),'--child-query',str(root)],
                        capture_output=True,text=True,timeout=20,check=False)
                    self.assertEqual(observed.returncode,0,
                                     observed.stderr+'\n'+observed.stdout)
                    self.assertEqual(json.loads(observed.stdout)['state'],expected,
                                     observed.stdout)
                recovered=subprocess.run([sys.executable,'-B',str(HERE/
                    'test_successor_synthetic_spec.py'),'--child-recover-trace',str(root)],
                    capture_output=True,text=True,timeout=20,check=False)
                self.assertEqual(recovered.returncode,0,
                                 recovered.stderr+'\n'+recovered.stdout)
                self.assertEqual(json.loads(recovered.stdout)['state'],
                                 'CUSTODY_COMPLETE_DELIVERY_NOT_PROVEN',
                                 recovered.stdout)
                waiting=subprocess.run([sys.executable,'-B',str(HERE/
                    'test_successor_synthetic_spec.py'),'--child-query',str(root)],
                    capture_output=True,text=True,timeout=20,check=False)
                self.assertEqual(waiting.returncode,0,waiting.stderr+'\n'+waiting.stdout)
                self.assertEqual(json.loads(waiting.stdout)['state'],
                                 'B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY')
                closed=subprocess.run([sys.executable,'-B',str(HERE/
                    'test_successor_synthetic_spec.py'),'--child-http-close-trace',
                    str(root)],capture_output=True,text=True,timeout=20,check=False)
                self.assertEqual(closed.returncode,0,closed.stderr+'\n'+closed.stdout)
                self.assertEqual(json.loads(closed.stdout)['state'],
                                 'RECEIVED_VERIFIED_19_CLOSED',closed.stdout)
                # Recovery consumes the same sealed source bytes; a changed
                # import after the successful observation cannot be accepted.
                queue_source=root/(entry.SOURCE+
                    '/production/cloud_connection/queue.py').lstrip('/')
                queue_source.write_bytes(queue_source.read_bytes()+b'X')
                changed=subprocess.run([sys.executable,'-B',str(HERE/
                    'test_successor_synthetic_spec.py'),'--child-query',str(root)],
                    capture_output=True,text=True,timeout=20,check=False)
                self.assertNotEqual(changed.returncode,0)
                self.assertIn('SUCCESSOR_SOURCE_NOT_BOUND',changed.stderr)


def child_query(root,action='query',execute_start=None):
    """Fresh interpreter, same sealed test tree and original read-only entry."""
    f=SyntheticSpec()
    archive=f.original_fixture(pathlib.Path(root),False)
    with f.active(archive):
        spec=c53.binder.verify_spec_bytes(f.raw)
        known={entry.ROOT,entry.SOURCE,entry.SPEC,entry.MANIFEST,entry.BINDER,
               c53.DB,c53.LOCK,c53.DB+'-wal',c53.DB+'-shm',c53.DB+'-journal',
               spec['fixed_paths']['receiver_root'],
               *c53.CONFIGS,*c53.SLOTS,*c53.BASES,
               WitnessStore.__init__.__globals__['ROOT'],
               SuccessorEvidenceStore.__init__.__globals__['SUCCESSOR_ROOT']}
        known.update(entry.SOURCE+'/'+name for name in f.source)
        known.update(entry.ROOT+'/'+row['path'] for row in
                     json.loads((pathlib.Path(root)/entry.MANIFEST.lstrip('/')).read_bytes())['files'])
        for base in c53.BASES:
            known.add(base+'/current')
            known.update(base+'/releases/'+c53.COMMIT+'/'+name for name in
                         f.source)
        original_paths={c53.binder.ARCHIVE_ROOT,c53.binder.PACKAGE_ROOT,
            c53.binder.ARCHIVE_ROOT+'/source-tree.tar.pending'}
        original_paths.update(c53.binder.PACKAGE_ROOT+'/'+obj['relative_path']
                              for obj in spec['objects'][5:])
        known.update(original_paths)
        job=spec['fixed_paths']['job_proposed']
        release_roots=(*spec['fixed_paths']['stage_proposed'],
                       *spec['fixed_paths']['target_release'])
        generated_roots=(job,*release_roots)
        replace_stages=tuple(path+'.l2-b5-staged-'+c53.COMMIT[:12]
            for path in c53.CONFIGS+c53.SLOTS)
        current_stages=tuple(base+'/current.l2-b5-staged-'+c53.COMMIT[:12]
            for base in c53.BASES)
        known.update(generated_roots+replace_stages+current_stages)
        known.update(job+'/'+name for name in (
            'reservation.json','window-open.json','activation-identity.json',
            'NEW_WORKER_START_ATTEMPT.json'))
        known.update(job+'/checkpoint-%03d.json'%i for i in range(1,65))
        known.update(job+'/original-%d.bin'%i for i in range(3))
        known.update(job+'/protected-original-%d.bin'%i for i in range(3))
        known.add(job+'/original-links.json')
        pins={}
        for path in known:
            target=pathlib.Path(root)/path.lstrip('/')
            if target.is_file() and not target.is_symlink():
                st=target.stat();pins[path]=(st.st_dev,st.st_ino)
        for path,key in ((c53.DB,'db'),(c53.LOCK,'worker_lock')):
            row=spec['observed_baseline'][key]
            pins[path]=(row['dev'],row['ino'])
        actual=os.uname()
        synthetic=type(actual)((actual.sysname,c53.HOST,
            actual.release,actual.version,actual.machine))
        def recorded_status(argv,**kwargs):
            if argv[:2]==['/usr/bin/systemctl','show']:
                return type('Result',(),{'returncode':0,'stdout':(
                    'ActiveState=active\nSubState=running\nMainPID=123\n'
                    'NRestarts=0\nExecMainStartTimestampMonotonic=4000\n').encode()})()
            if argv==['/usr/bin/systemctl','is-active','--quiet',
                      'xuanjun-cloud-connection.service']:
                return type('Result',(),{'returncode':0,'stdout':b''})()
            raise AssertionError('UNRECORDED_CHILD_OS_ACTION')
        from production.cloud_connection.worker import Github,PREFIX
        comment_ids=iter(range(10000,10019))
        def recorded_comment(self,suffix,data=None):
            if suffix!='/issues/17/comments' or type(data) is not dict or \
                    type(data.get('body')) is not str or \
                    not data['body'].startswith(PREFIX):
                raise AssertionError('UNRECORDED_GITHUB_ACTION')
            return {'id':next(comment_ids),'user':{'id':332398908},
                    'body':data['body'],'created_at':'fixture-time',
                    'updated_at':'fixture-time'}
        database=pathlib.Path(root)/c53.DB.lstrip('/')
        original_connect=sqlite3.connect
        class DatabaseList:
            def __init__(self,cursor):self.cursor=cursor
            def fetchall(self):
                return [(n,label,c53.DB if path==str(database) else path)
                        for n,label,path in self.cursor.fetchall()]
        class SQLiteBoundary:
            def __init__(self,connection):self.connection=connection
            def execute(self,sql,*args):
                result=self.connection.execute(sql,*args)
                return DatabaseList(result) if sql=='PRAGMA database_list' else result
            def __getattr__(self,name):return getattr(self.connection,name)
        def connect(path,*args,**kwargs):
            if path==c53.DB:
                return SQLiteBoundary(original_connect(str(database),*args,**kwargs))
            if type(path) is str and path.startswith('file:'+c53.DB+'?'):
                return SQLiteBoundary(original_connect(
                    'file:'+str(database)+path[len('file:'+c53.DB):],
                    *args,**kwargs))
            if type(path) is str and path.startswith('file:/proc/self/fd/'):
                return SQLiteBoundary(original_connect(path,*args,**kwargs))
            return original_connect(path,*args,**kwargs)
        store_roots=(WitnessStore.__init__.__globals__['ROOT'],
                     SuccessorEvidenceStore.__init__.__globals__['SUCCESSOR_ROOT'])
        with SealedOSBoundary(root,known,pins,
             dynamic_roots=store_roots+(job,),
             recursive_dynamic_roots=release_roots+
                (spec['fixed_paths']['receiver_root'],)).active(),\
             patch.object(sqlite3,'connect',side_effect=connect),\
             patch('subprocess.run',side_effect=recorded_status),\
             patch.object(Github,'call',recorded_comment),\
             patch.object(os,'uname',return_value=synthetic),\
             patch.object(os,'geteuid',return_value=0),\
             patch.object(os,'getegid',return_value=0),\
             patch.dict(os.environ,{'SUDO_UID':'1000'}),\
             patch.object(entry,'__file__',entry.ROOT+
                          '/successor_controller/pr17_b5_successor_entry.py'),\
             patch.object(entry,'LOCAL_ROOT',entry.ROOT):
            if action=='execute':
                if execute_start is None:
                    raise AssertionError('EXECUTE_START_REQUIRED')
                tx=entry._prepare('c53-recovery-draft','fixture-attempt',
                                  'fixture-only',int(execute_start))
                guard_calls=[]
                original_guarded=tx.guarded
                def child_traced_guarded(name,*args):
                    guard_calls.append(name)
                    try:return original_guarded(name,*args)
                    except BaseException as exc:
                        guard_calls.append('ERROR:'+name+':'+str(exc))
                        raise
                tx.guarded=child_traced_guarded
                def execute_run(argv,**kwargs):
                    if argv[:2]==['/usr/bin/systemctl','show']:
                        return recorded_status(argv,**kwargs)
                    if argv[0:1]!=['/usr/bin/systemctl']:
                        raise AssertionError('UNRECORDED_EXTERNAL_OS_ACTION')
                    return type('Result',(),{'returncode':3 if
                        argv[1:3]==['is-active','--quiet'] and
                        argv[-1]=='xuanjun-cloud-connection.service' and
                        not tx.b.tried_start else 0,'stdout':b''})()
                settings=json.loads(tx.bundle['files'][c53.CONFIGS[1]])['settings']
                metadata={'resource':settings['audience'],
                    'authorization_servers':[settings['issuer']],
                    'scopes_supported':['connection.status','project.files.read'],
                    'bearer_methods_supported':['header']}
                class Response:
                    status=200
                    def getheader(self,*args):return 'application/json'
                    def read(self,*args):return json.dumps(metadata).encode()
                class RecordedHTTP:
                    def __init__(self,host,port,timeout):
                        if (host,port)!=('127.0.0.1',18769):
                            raise AssertionError('UNRECORDED_HTTP_TARGET')
                    def request(self,*args,**kwargs):pass
                    def getresponse(self):return Response()
                    def close(self):pass
                with patch('subprocess.run',side_effect=execute_run),\
                     patch('pr17_b5_successor_fixed_io.http.client.HTTPConnection',
                           RecordedHTTP):
                    result=tx.execute()
                if result.get('state')=='HOLD_PRESERVE_HISTORY':
                    result=dict(result,_guard_calls=guard_calls)
                if tx.b.authority.original.queue is not None:
                    tx.b.authority.original.queue.close()
            elif action=='http-close-trace':
                tx=entry._recover()
                from pr17_b5_successor_authority import inspect_recovered_candidate_readonly
                observed=inspect_recovered_candidate_readonly(tx)
                if observed.get('state')!='B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY':
                    raise AssertionError('B5_HTTP_WAIT_REQUIRED')
                tx.resume_recovered_b5_http_wait()
                original=tx.b.authority.original
                now=int(time.time())
                auth=original.resource.authenticator
                auth.secret_provider=lambda:'fixture-client-secret'
                auth.wall_clock=lambda:now
                auth.monotonic=lambda:1.0
                claims={'active':True,'iss':auth.issuer,'token_type':'Bearer',
                    'exp':now+600,'iat':now-1,'aud':auth.audience,
                    'scope':'project.files.read','sub':c53.SUBJECT}
                class IntrospectionResponse:
                    def __enter__(self):return self
                    def __exit__(self,*_):return False
                    def getcode(self):return 200
                    def read(self,*_):return json.dumps(claims).encode()
                auth.open_url=lambda request,timeout:IntrospectionResponse()
                requests=tx.bundle['requests']
                objects=[original.policy.catalog.objects[
                         request['arguments']['object_ref']] for request in requests]
                invokes={}
                for request in requests:
                    row=original.queue.db.execute(
                        'SELECT state,invoke_id FROM connection_jobs WHERE request_id=?',
                        (request['request_id'],)).fetchone()
                    if row is None or row[0]!='SUCCESS' or not row[1]:
                        raise AssertionError('FIXTURE_SUCCESS_INVOKE_ABSENT')
                    invokes[request['request_id']]=row[1]
                custody={'state':'MATERIAL_CUSTODY_COMPLETE','objects':19,
                    'bytes':93592,'catalog_sha256':original.policy.catalog.sha,
                    'analyst_receipt':'NOT_VERIFIED','source_execution':False}
                from successor_analyst_read import receive_all
                proof=receive_all(requests=requests,objects=objects,
                    catalog_sha=original.policy.catalog.sha,project=c53.PROJ,
                    recipient=c53.RECIP,success_invokes=invokes,custody=custody,
                    read_project_chunk=lambda **args:original.resource.read(
                        'Bearer fixture-http-token-0123456789',args,now))
                rows=[{'request_id':request['request_id'],
                       'object_ref':'b5-material-%02d'%(number+1),
                       'invoke_id':invokes[request['request_id']],
                       'bytes':objects[number]['bytes'],
                       'sha256':objects[number]['sha256'],
                       'result_ref':'fixture-http-result-%02d'%(number+1)}
                      for number,request in enumerate(requests)]
                binding=tx.b.authority._witness_binding()
                evidence=tx.b.authority.evidence_store
                evidence.register_exact(binding,'b5_http',
                    source_id='fixture-http-witness',
                    source_raw=b'fixture nonsecret HTTP result witness',
                    witness_identity='fixture-registrar',
                    payload={'proof_sha256':proof['proof_sha256'],
                        'custody_receipt_sha256':c53.sha(c53.canon(custody)),
                        'rows':rows,'subject':c53.SUBJECT,
                        'scope':'project.files.read',
                        'catalog_sha256':original.policy.catalog.sha,
                        'recipient':c53.RECIP})
                evidence.register_exact(binding,'B5_EXPOSURE_CLOSE',
                    source_id='fixture-independent-close',
                    source_raw=b'fixture independent close decision',
                    witness_identity='fixture-close-registrar',
                    payload={'scope':'B5_EXPOSURE_CLOSE','job':tx.b.job,
                        'decision_id':'fixture-close-decision','approved':True,
                        'phase':'AFTER_B5_HTTP'})
                guard_calls=[]
                original_guarded=tx.guarded
                def traced_close(name,*args):
                    guard_calls.append(name)
                    try:return original_guarded(name,*args)
                    except BaseException as exc:
                        guard_calls.append('ERROR:'+name+':'+str(exc));raise
                tx.guarded=traced_close
                result=tx.close_after_b5_http(proof)
                result=dict(result,_guard_calls=guard_calls)
                if original.queue is not None:original.queue.close()
            elif action=='recover-trace':
                tx=entry._recover()
                guard_calls=[]
                original_guarded=tx.guarded
                def traced_guarded(name,*args):
                    guard_calls.append(name)
                    try:return original_guarded(name,*args)
                    except BaseException as exc:
                        guard_calls.append('ERROR:'+name+':'+str(exc))
                        raise
                tx.guarded=traced_guarded
                from pr17_b5_successor_authority import inspect_recovered_candidate_readonly
                observed=inspect_recovered_candidate_readonly(tx)
                if observed.get('state')=='SUCCESS_SNAPSHOT_READONLY':
                    result=tx.resume_recovered_custody()
                elif observed.get('state')=='B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY':
                    result=tx.resume_recovered_b5_http_wait()
                else:
                    result=observed
                result=dict(result,_guard_calls=guard_calls)
            elif action in ('worker-ready','worker-success'):
                from production.cloud_connection.queue import Queue,canonical
                tx=entry._recover()
                policy=tx.b.authority.original.policy
                if tx.b.authority.original.queue is not None:
                    tx.b.authority.original.queue.close()
                requests=tx.bundle['requests']
                q=Queue(c53.DB,requests[0]['executor_sha256'],[332398908],
                        approved_objects=policy)
                try:
                    for i,request in enumerate(requests,1):
                        rid=request['request_id']
                        if action=='worker-ready':
                            q.submit(canonical(request),332398908,int(time.time()))
                        else:
                            q.begin_dispatch(rid,int(time.time()))
                            invoke='fixture-invoke-%02d'%i
                            q.record_invoke(rid,invoke)
                            obj=policy.catalog.objects[request['arguments']['object_ref']]
                            q.terminal(rid,invoke,{'state':'SUCCESS','invoke_id':invoke,
                                'target':'uk','manifest_sha256':policy.catalog.sha,
                                'object_ref':obj['ref'],'recipient_id':c53.RECIP,
                                'bytes':obj['bytes'],'sha256':obj['sha256'],
                                'action_binding_sha256':policy.sha})
                finally:q.close()
                result={'state':'RECORDED_FIXTURE_WORKER_'+action.upper()}
            else:result=entry.dispatch(action)
        print(json.dumps(result,sort_keys=True))
        return 0


if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--child-execute':
        raise SystemExit(child_query(sys.argv[2],'execute',sys.argv[3]))
    if len(sys.argv)==3 and sys.argv[1] in (
            '--child-query','--child-intake','--child-worker-ready',
            '--child-worker-success','--child-recover','--child-recover-trace',
            '--child-http-close-trace'):
        raise SystemExit(child_query(sys.argv[2],
            sys.argv[1][8:] if sys.argv[1]!='--child-query' else 'query'))
    unittest.main()
