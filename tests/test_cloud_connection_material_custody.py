"""Synthetic files and original Queue/Receiver only; no SDK or network."""
import base64
import copy
import hashlib
import io
import os
from pathlib import Path
import sqlite3
import contextlib
import json
import shlex
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_cloud_connection_approved_objects as original
NOW, ACTOR = original.NOW, original.ACTOR
from production.cloud_connection.archive_reader import read_archive_member, read_archive_member_metadata, ArchiveView
from production.cloud_connection.private_transfer import stamp, Receiver
from production.cloud_connection.material_custody import ingest_approved_batch, read_received_chunk, delivery_binding
from production.cloud_connection.oauth_resource import OAuthProjectResource
from production.cloud_connection.queue import Hold
from production.cloud_connection.worker import query_existing


class CustodyTests(original.ApprovedObjectTests):
    # Reuse setup helpers, not inherited test collection.
    def setUp(self):
        super().setUp()
        self.safe = tempfile.TemporaryDirectory(dir='/root' if os.geteuid()==0 else str(Path.cwd()))
        self.root = self.safe.name
        self.owner = os.geteuid()
        self.dest = self.root + '/received'
        os.mkdir(self.dest, 0o700)
        Path(self.root, 'package.json').write_bytes(self.body)
        os.chmod(self.root + '/package.json', 0o600)
        self.binding['roots']['fixture-root'] = [self.root, self.owner]
        self.policy = self.make_policy()
        self.q.approved_objects = self.policy
    def tearDown(self):
        super().tearDown(); self.safe.cleanup()
    def success(self):
        self.start(); query_existing(self.q, self.cloud(), 'fixture-request', lambda *a: self.fail('sink'))
    def ingest(self):
        return ingest_approved_batch(self.q.db, self.policy, self.dest, self.owner, NOW, True, lambda: NOW)
    def read(self, db=None):
        return read_received_chunk(db or self.q.db, self.policy.catalog, self.dest, self.owner,
            'fixture-request', 'fixture-object', 'fixture-reader', 0, NOW, True)
    def test_custody_whole_regular_chain_readonly(self):
        self.success(); result = self.ingest()
        self.assertEqual(result['bytes'], len(self.body))
        before = self.q.db.total_changes
        self.q.db.execute('PRAGMA query_only=ON')
        with patch.object(Receiver, '__init__', side_effect=AssertionError('write')), patch.object(self.policy, 'read_source', side_effect=AssertionError('source')):
            self.assertEqual(base64.b64decode(self.read()['data']), self.body)
        self.assertEqual(self.q.db.total_changes, before)
    def test_receipt_policy_binding_changed_no_source(self):
        self.success()
        changed=copy.deepcopy(self.binding);changed['roots']['fixture-root'][0]=self.root+'/different'
        self.policy=self.make_policy(changed)
        with patch.object(self.policy,'read_source') as read:
            with self.assertRaises(Hold):self.ingest()
            read.assert_not_called()
        self.assertIsNone(self.q.db.execute("SELECT name FROM sqlite_master WHERE name='connection_file_delivery'").fetchone())
    def test_request_expired_catalog_valid_no_source(self):
        self.success()
        with patch.object(self.policy,'read_source') as read:
            with self.assertRaises(Hold):ingest_approved_batch(self.q.db,self.policy,self.dest,self.owner,NOW+61,True,lambda:NOW+61)
            read.assert_not_called()
    def test_request_expires_during_source_no_accept(self):
        self.success();ticks=iter([NOW,NOW,NOW+61])
        with patch.object(Receiver,'accept') as accept:
            with self.assertRaises(Hold):ingest_approved_batch(self.q.db,self.policy,self.dest,self.owner,NOW,True,lambda:next(ticks))
            accept.assert_not_called()
        self.assertEqual(list(Path(self.dest).iterdir()),[])
    def prepare_five(self):
        from production.cloud_connection.queue import canonical
        from production.cloud_connection.worker import execute_ready, HOSTS
        archive=Path(self.root,'group.tar');self.group_data={};items=[]
        with tarfile.open(str(archive),'w',format=tarfile.USTAR_FORMAT) as tar:
            for n in range(5):
                ref='fixture-object-%d'%n;data=('inert member %d'%n).encode();self.group_data[ref]=data
                item=dict(ref=ref,root_ref='fixture-root',relative_path='dist/member%d.mjs'%n,bytes=len(data),sha256=hashlib.sha256(data).hexdigest());items.append(item)
                info=tarfile.TarInfo(item['relative_path']);info.size=len(data);tar.addfile(info,io.BytesIO(data))
        os.chmod(str(archive),0o600)
        self.binding['catalog']['objects']=items
        self.binding['catalog_sha256']=hashlib.sha256(canonical(self.binding['catalog']).encode()).hexdigest()
        self.binding['requests']={x['ref']:'fixture-request-%d'%n for n,x in enumerate(items)}
        self.binding['archives']={'fixture-root':dict(filename='group.tar',identity=list(stamp(archive.stat())),member_prefix='',max_headers=100,max_read_bytes=1048576,sha256=hashlib.sha256(archive.read_bytes()).hexdigest())}
        self.binding['archive_reader_sha256']=hashlib.sha256(Path('production/cloud_connection/archive_reader.py').read_bytes()).hexdigest()
        self.policy=self.make_policy();self.q.approved_objects=self.policy
        real_pread=os.pread;full=[]
        def observe(fd,count,offset):
            if count==archive.stat().st_size and offset==0:full.append(True)
            return real_pread(fd,count,offset)
        for n,item in enumerate(items):
            request=copy.deepcopy(self.request);request['request_id']='fixture-request-%d'%n
            request['arguments'].update(manifest_sha256=self.policy.catalog.sha,object_ref=item['ref'])
            command=self.policy.command(request);code=shlex.split(command['CommandContent'])[-1];output=io.StringIO()
            with patch('os.pread',side_effect=observe),patch('os.uname',return_value=type('Host',(),{'nodename':HOSTS['uk']})()),patch('os.geteuid',return_value=1002),patch('time.time',return_value=NOW),contextlib.redirect_stdout(output):
                exec(compile(code,'synthetic-member-metadata','exec'),{})
            invoke='fixture-invoke-%d'%n
            result={'InvocationResult':dict(InvokeId=invoke,InstanceId=original.TARGETS['uk'][2],InvocationStatus='Success',ExitCode=0,Output=output.getvalue())}
            class Cloud:
                def call(self,target,action,args):return {'InvokeId':invoke} if action=='RunCommand' else result
            self.q.submit(canonical(request),ACTOR,NOW);execute_ready(self.q,Cloud(),request['request_id'],NOW)
            query_existing(self.q,Cloud(),request['request_id'],lambda *a:self.fail('sink'))
        self.assertEqual(full,[]) # member proof never claims an entire archive hash
        return archive,observe,full
    def test_five_group_one_full_hash_and_exact_delivery(self):
        archive,observe,full=self.prepare_five()
        with patch('os.pread',side_effect=observe):result=self.ingest()
        self.assertEqual(len(full),1);self.assertEqual(result['objects'],5)
        self.q.db.execute('PRAGMA query_only=ON')
        for n,(ref,data) in enumerate(sorted(self.group_data.items())):
            result=read_received_chunk(self.q.db,self.policy.catalog,self.dest,self.owner,'fixture-request-%d'%n,ref,'fixture-reader',0,NOW,True)
            self.assertEqual(base64.b64decode(result['data']),data)
    def test_second_archive_root_refused(self):
        self.prepare_five();changed=copy.deepcopy(self.binding)
        changed['archives']['extra-root']=copy.deepcopy(changed['archives']['fixture-root'])
        with self.assertRaises(Hold):self.make_policy(changed)
    def test_bad_group_member_no_receiver(self):
        archive,observe,full=self.prepare_five()
        data=archive.read_bytes().replace(b'inert member 4',b'wrong member 4')
        archive.write_bytes(data)
        plan=self.policy.binding['archives']['fixture-root']
        plan['identity']=list(stamp(archive.stat()));plan['sha256']=hashlib.sha256(data).hexdigest()
        with patch.object(Receiver,'accept') as accept:
            with self.assertRaises(Hold):self.ingest()
            accept.assert_not_called()
        self.assertEqual(list(Path(self.dest).iterdir()),[])
    def test_group_archive_bad_hash_no_accept(self):
        self.prepare_five();self.policy.binding['archives']['fixture-root']['sha256']='0'*64
        with patch.object(Receiver,'accept') as accept:
            with self.assertRaises(Hold):self.ingest()
            accept.assert_not_called()
        self.assertEqual(list(Path(self.dest).iterdir()),[])
    def test_group_expiry_after_read_no_accept(self):
        self.prepare_five();ticks=iter([NOW]*6+[NOW+61])
        with patch.object(Receiver,'accept') as accept:
            with self.assertRaises(Hold):ingest_approved_batch(self.q.db,self.policy,self.dest,self.owner,NOW,True,lambda:next(ticks))
            accept.assert_not_called()
        self.assertEqual(list(Path(self.dest).iterdir()),[])
    def test_custody_default_disabled_no_source(self):
        with patch.object(self.policy, 'read_source') as read:
            with self.assertRaises(Hold): ingest_approved_batch(self.q.db, self.policy, self.dest, self.owner, NOW)
            read.assert_not_called()
    def test_custody_without_success_no_source_or_tables(self):
        self.submit()
        with patch.object(self.policy, 'read_source') as read:
            with self.assertRaises(Hold): self.ingest()
            read.assert_not_called()
        self.assertIsNone(self.q.db.execute("SELECT name FROM sqlite_master WHERE name='connection_file_delivery'").fetchone())
    def test_custody_completed_resume_no_source(self):
        self.success(); self.ingest()
        with patch.object(self.policy, 'read_source', side_effect=AssertionError('reread')): self.ingest()
    def test_custody_expired_no_source(self):
        self.success()
        with patch.object(self.policy, 'read_source') as read:
            with self.assertRaises(Hold): ingest_approved_batch(self.q.db,self.policy,self.dest,self.owner,NOW+100,True)
            read.assert_not_called()
    def test_custody_read_missing_delivery(self):
        self.success()
        with self.assertRaises((Hold,sqlite3.OperationalError)): self.read()
    def test_custody_foreign_file_refused(self):
        self.success(); self.ingest()
        name = next(Path(self.dest).glob('*.bin'))
        name.write_bytes(b'x'*len(self.body))
        with self.assertRaises(Hold): self.read()
    def test_custody_wrong_mode_and_missing_final_proof(self):
        self.success();self.ingest()
        original_db=self.q.db
        class NoProof:
            def execute(self,sql,args):
                if 'offset=-1' in sql:
                    class Empty:
                        def fetchone(self):return None
                    return Empty()
                return original_db.execute(sql,args)
        with self.assertRaises(Hold):self.read(NoProof())
        os.chmod(str(next(Path(self.dest).glob('*.bin'))),0o644)
        with self.assertRaises(Hold):self.read()
    def test_custody_link_refused(self):
        self.success(); self.ingest()
        name = next(Path(self.dest).glob('*.bin')); name.unlink(); name.symlink_to(self.root+'/package.json')
        with self.assertRaises((Hold,OSError)): self.read()
    def test_resource_custody_scope_and_readonly(self):
        self.success(); self.ingest()
        outer=self
        class Auth:
            def authenticate(self, authorization, scope, project, now):
                outer.assertEqual(scope,'project.files.read')
                if authorization!='synthetic-files-token': raise Hold('OAUTH_SCOPE')
                return 'fixture-reader'
        resource=OAuthProjectResource(self.q.db,{self.policy.catalog.sha:(self.policy.catalog,{})},Auth(),True,lambda:NOW,{self.policy.catalog.sha:[self.dest,self.owner]})
        args=dict(manifest_sha256=self.policy.catalog.sha,request_id='fixture-request',object_ref='fixture-object',offset=0)
        self.q.db.execute('PRAGMA query_only=ON')
        with self.assertRaises(Hold): resource.read('status-only',args,NOW)
        self.assertEqual(base64.b64decode(resource.read('synthetic-files-token',args,NOW)['data']),self.body)

    def test_archive_metadata_custody_resource_full_chain(self):
        archive=Path(self.root,'source.tar')
        with tarfile.open(str(archive),'w',format=tarfile.USTAR_FORMAT) as tar:
            info=tarfile.TarInfo('package.json');info.size=len(self.body);tar.addfile(info,io.BytesIO(self.body))
        os.chmod(str(archive),0o600)
        self.binding['archives']={'fixture-root':dict(filename='source.tar',identity=list(stamp(archive.stat())),member_prefix='',max_headers=100,max_read_bytes=1048576,sha256=hashlib.sha256(archive.read_bytes()).hexdigest())}
        self.binding['archive_reader_sha256']=hashlib.sha256(Path('production/cloud_connection/archive_reader.py').read_bytes()).hexdigest()
        self.policy=self.make_policy();self.q.approved_objects=self.policy
        command=self.policy.command(self.request)
        self.assertIn('read_archive_member',command['CommandContent'])
        from production.cloud_connection.worker import HOSTS
        code=shlex.split(command['CommandContent'])[-1]
        output=io.StringIO()
        with patch('os.uname',return_value=type('Host',(),{'nodename':HOSTS['uk']})()), patch('os.geteuid',return_value=1002), patch('time.time',return_value=NOW),contextlib.redirect_stdout(output):
            exec(compile(code,'synthetic-archive-command','exec'),{})
        observed=json.loads(output.getvalue())
        self.assertEqual(observed['sha256'],hashlib.sha256(self.body).hexdigest())
        self.assertNotIn('data',observed)
        self.success();self.ingest()
        self.assertEqual(base64.b64decode(self.read()['data']),self.body)
    def test_unknown_job_never_reads_or_replays(self):
        from production.cloud_connection.worker import execute_ready
        self.submit()
        with self.assertRaises(OSError):execute_ready(self.q,self.cloud(lost=True),'fixture-request',NOW)
        with patch.object(self.policy,'read_source') as read:
            with self.assertRaises(Hold):self.ingest()
            read.assert_not_called()
        self.assertEqual(self.q.inspect('fixture-request')['state'],'UNKNOWN')
    def test_receiver_commit_unknown_preserved_and_reconciled(self):
        self.success()
        real=self.q.db
        class LostCommit:
            def __init__(self):self.commits=0
            def __getattr__(self,name):return getattr(real,name)
            def commit(self):
                self.commits+=1
                if self.commits==2:raise OSError('synthetic lost commit')
                return real.commit()
        with self.assertRaises(OSError):ingest_approved_batch(LostCommit(),self.policy,self.dest,self.owner,NOW,True,lambda:NOW)
        self.assertEqual(len(list(Path(self.dest).glob('*.partial'))),1)
        self.assertEqual(self.q.inspect('fixture-request')['state'],'SUCCESS')
        # Do not automatically re-run ingest after an uncertain operation.
        self.assertEqual(next(Path(self.dest).glob('*.partial')).read_bytes(),self.body)


# Keep exactly the new custody tests; the original module runs separately.
for name in list(vars(original.ApprovedObjectTests)):
    if name.startswith('test_') and name not in vars(CustodyTests): setattr(CustodyTests,name,None)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/root' if os.geteuid()==0 else str(Path.cwd())); self.root=self.tmp.name
        self.owner=os.geteuid(); self.raw=b'inert archive member\n'
        self.item=dict(ref='archive-object',root_ref='archive-root',relative_path='dist/fixed.mjs',bytes=len(self.raw),sha256=hashlib.sha256(self.raw).hexdigest())
    def tearDown(self): self.tmp.cleanup()
    def archive(self, names=None, kind=None, prefix='', mode='w'):
        path=Path(self.root,'fixed.tar')
        with tarfile.open(str(path),mode,format=tarfile.USTAR_FORMAT) as tar:
            for name in names or [prefix+'dist/fixed.mjs']:
                info=tarfile.TarInfo(name); info.size=len(self.raw)
                if kind: info.type=kind; info.linkname='elsewhere'; info.size=0
                tar.addfile(info,io.BytesIO(self.raw) if not kind else None)
        os.chmod(str(path),0o600)
        return dict(filename='fixed.tar',identity=list(stamp(path.stat())),member_prefix=prefix,max_headers=100,max_read_bytes=1048576,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    def read(self, plan): return read_archive_member(self.root,self.owner,self.item,plan)
    def test_exact_member(self): self.assertEqual(self.read(self.archive()),self.raw)
    def test_exact_dot_prefix(self): self.assertEqual(self.read(self.archive(prefix='./')),self.raw)
    def test_duplicate_or_alias_or_traversal(self):
        for names in [['dist/fixed.mjs','dist/fixed.mjs'],['./dist/fixed.mjs'],['../bad','dist/fixed.mjs']]:
            with self.subTest(names=names),self.assertRaises(Hold): self.read(self.archive(names))
    def test_links(self):
        for kind in [tarfile.SYMTYPE,tarfile.LNKTYPE]:
            with self.subTest(kind=kind),self.assertRaises(Hold): self.read(self.archive(kind=kind))
    def test_member_and_archive_hash(self):
        p=self.archive(); p['sha256']='0'*64
        with self.assertRaises(Hold):self.read(p)
        p=self.archive(); self.item['sha256']='0'*64
        with self.assertRaises(Hold):self.read(p)
    def test_changed_identity(self):
        p=self.archive(); p['identity'][1]+=1
        with self.assertRaises(Hold):self.read(p)
    def test_missing_member(self):
        with self.assertRaises(Hold):self.read(self.archive(['different']))
    def test_compressed_refused(self):
        with self.assertRaises((Hold,tarfile.TarError)):self.read(self.archive(mode='w:gz'))
    def test_metadata_and_headers_bounds(self):
        p=self.archive(['first','dist/fixed.mjs']);p['max_headers']=1
        with self.assertRaises(Hold):self.read(p)
        p=self.archive();p['max_read_bytes']=1024
        with self.assertRaises(Hold):self.read(p)
    def test_member_size_and_sparse_refused(self):
        p=self.archive();self.item['bytes']+=1
        with self.assertRaises(Hold):self.read(p)
        self.item['bytes']-=1
        with self.assertRaises((Hold,tarfile.TarError)):self.read(self.archive(kind=tarfile.GNUTYPE_SPARSE))
    def test_trailing_payload_refused(self):
        p=self.archive();path=Path(self.root,'fixed.tar')
        with path.open('ab') as f:f.write(b'not-an-approved-second-archive')
        p['identity']=list(stamp(path.stat()));p['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(Hold):self.read(p)
    def test_timeout_before_hash_read(self):
        p=self.archive()
        with patch('production.cloud_connection.archive_reader.time.monotonic',side_effect=[0,31]),patch('os.pread') as read:
            with self.assertRaises(Hold):self.read(p)
            read.assert_not_called()
    def test_bad_consumed_eof_header_and_missing_eof(self):
        for mode in ('bad','missing'):
            p=self.archive();path=Path(self.root,'fixed.tar');data=path.read_bytes()
            data=data[:1024]+b'X'*512+data[1536:] if mode=='bad' else data[:1024]
            path.write_bytes(data);p['identity']=list(stamp(path.stat()));p['sha256']=hashlib.sha256(data).hexdigest()
            with self.subTest(mode=mode),self.assertRaises(Hold):self.read(p)
    def test_directory_aliases_refused(self):
        for names in [['foo/','foo','dist/fixed.mjs'],['.','./','dist/fixed.mjs']]:
            with self.subTest(names=names),self.assertRaises(Hold):self.read(self.archive(names))
    def test_metadata_proves_member_not_entire_archive(self):
        p=self.archive();p['sha256']='0'*64
        self.assertEqual(read_archive_member_metadata(self.root,self.owner,self.item,p),self.raw)
        with self.assertRaises(Hold):self.read(p)
    def test_unbounded_parser_read_refused_before_io(self):
        v=ArchiveView(-1,100,100,10**20)
        with patch('os.pread') as read:
            with self.assertRaises(Hold):v.read(-1)
            with self.assertRaises(Hold):v.read(65537)
            read.assert_not_called()

if __name__=='__main__':unittest.main()
