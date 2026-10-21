"""Real file/SQLite tests. These are synthetic approvals, not live enrollment."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from production.cloud_connection.queue import Queue, Hold
from production.cloud_connection.private_transfer import Catalog, Receiver, export_chunk, CHUNK, read_object

NOW = 1800000000
PIN = 'a' * 64
POLICY = {'project':'project-fixture','max_objects':64,'max_object_bytes':64*1024*1024,
          'max_total_bytes':256*1024*1024,'recipients':['work-window'],'root_refs':['frozen-input']}


class PrivateTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/root')
        self.root = Path(self.tmp.name)
        self.src, self.dst = self.root/'source', self.root/'receiver'
        self.src.mkdir(mode=0o700)
        self.dst.mkdir(mode=0o700)
        (self.src/'dist').mkdir(mode=0o700)
        self.data = (b'export const version="project-fixture";\n' * 5000) + b'END'
        (self.src/'dist'/'module.mjs').write_bytes(self.data)
        self.doc = {'schema':1,'project':'project-fixture','approval_ref':'offline-approval',
                    'source_commit':'b'*40,'executor_sha256':PIN,'target':'uk',
                    'valid_from':NOW-1,'valid_until':NOW+3600,'recipients':['work-window'],
                    'objects':[{'ref':'module-object','root_ref':'frozen-input',
                                'relative_path':'dist/module.mjs','bytes':len(self.data),
                                'sha256':hashlib.sha256(self.data).hexdigest()}]}
        self.catalog = self.make_catalog()
        self.q = Queue(str(self.root/'queue.sqlite'), PIN, {332398908})
        # A validated future adapter's SUCCESS record, not current queue enrollment.
        self.request = {'request_id':'approved-transfer','project':'project-fixture','target':'uk',
                        'executor_sha256':PIN,'operation':'fetch_approved_object',
                        'arguments':{'manifest_sha256':self.catalog.sha,'object_ref':'module-object',
                                     'recipient_id':'work-window'}}
        self.q.db.execute('INSERT INTO connection_jobs VALUES(?,?,?,?,?,?,?,?)',
                          ('approved-transfer','project-fixture',json.dumps(self.request),'c'*64,
                           332398908,'SUCCESS','t-existing-invoke',json.dumps(self.receipt())))
        self.receiver = Receiver(self.q.db, str(self.dst), self.catalog, 'work-window')

    def make_catalog(self):
        raw=json.dumps(self.doc,sort_keys=True).encode()
        return Catalog(raw,hashlib.sha256(raw).hexdigest(),POLICY)

    def receipt(self):
        item=self.catalog.objects['module-object']
        return {'state':'SUCCESS','invoke_id':'t-existing-invoke','target':'uk',
                'manifest_sha256':self.catalog.sha,'object_ref':'module-object',
                'recipient_id':'work-window','bytes':item['bytes'],'sha256':item['sha256']}

    def tearDown(self):
        self.receiver.close()
        self.q.close()
        self.tmp.cleanup()

    def chunk(self, offset=0, recipient='work-window', now=NOW):
        return export_chunk(self.q.db,self.catalog,{'frozen-input':(str(self.src),0)},
                            'approved-transfer','module-object',recipient,offset,now)

    def complete(self):
        for offset in range(0,len(self.data),CHUNK):
            result=self.receiver.accept(self.chunk(offset),NOW)
        return result

    def test_rejected_parent_does_not_leak_descriptors(self):
        before=len(os.listdir('/proc/self/fd'))
        os.chmod(str(self.src/'dist'),0o777)
        try:
            for _ in range(20):
                with self.assertRaisesRegex(Hold,'SOURCE_PARENT'): self.chunk()
            self.assertEqual(len(os.listdir('/proc/self/fd')),before)
        finally: os.chmod(str(self.src/'dist'),0o700)

    def test_parent_fstat_failure_does_not_leak_descriptors(self):
        before=len(os.listdir('/proc/self/fd'))
        original=os.fstat
        def failing(fd):
            st=original(fd)
            if st.st_ino == os.stat(str(self.src/'dist')).st_ino:
                raise OSError('injected fstat failure')
            return st
        with patch('production.cloud_connection.private_transfer.os.fstat',side_effect=failing):
            for _ in range(20):
                with self.assertRaisesRegex(OSError,'injected'): self.chunk()
        self.assertEqual(len(os.listdir('/proc/self/fd')),before)

    def test_source_dup_failure_closes_root_descriptor(self):
        before=len(os.listdir('/proc/self/fd'))
        with patch('production.cloud_connection.private_transfer.os.dup',side_effect=OSError('dup failure')):
            for _ in range(20):
                with self.assertRaisesRegex(OSError,'dup failure'): self.chunk()
        self.assertEqual(len(os.listdir('/proc/self/fd')),before)

    def test_parent_fstat_interrupt_closes_descriptors(self):
        before=len(os.listdir('/proc/self/fd'))
        original=os.fstat
        def failing(fd):
            st=original(fd)
            if st.st_ino == os.stat(str(self.src/'dist')).st_ino:
                raise KeyboardInterrupt()
            return st
        with patch('production.cloud_connection.private_transfer.os.fstat',side_effect=failing):
            for _ in range(20):
                with self.assertRaises(KeyboardInterrupt): self.chunk()
        self.assertEqual(len(os.listdir('/proc/self/fd')),before)

    def test_non_os_project_object_full_sha(self):
        r=self.complete()
        self.assertEqual(r['state'],'SUCCESS')
        self.assertEqual((self.dst/r['private_ref']).read_bytes(),self.data)
        self.assertEqual(r['sha256'],hashlib.sha256(self.data).hexdigest())
        self.assertNotIn('relative_path',r)

    def test_receive_sha_tamper_preserves_partial(self):
        self.receiver.accept(self.chunk(),NOW)
        p=next(self.dst.glob('*.partial'))
        with p.open('r+b') as f: f.write(b'TAMPER')
        with self.assertRaisesRegex(Hold,'SHA'):
            for pos in range(CHUNK,len(self.data),CHUNK): self.receiver.accept(self.chunk(pos),NOW)
        self.assertTrue(p.exists())
        self.assertEqual(self.q.db.execute('SELECT state FROM connection_file_delivery').fetchone()[0],'PARTIAL')

    def test_recipient_cannot_be_claimed_by_envelope(self):
        with self.assertRaisesRegex(Hold,'RECIPIENT'):
            self.chunk(recipient='other-window')
        e=self.chunk(); e['recipient_id']='other-window'
        with self.assertRaisesRegex(Hold,'BINDING'): self.receiver.accept(e,NOW)

    def test_unknown_object(self):
        with self.assertRaises(Hold): self.catalog.object('../etc/shadow','work-window',NOW)

    def test_catalog_digest_does_not_authorize_itself(self):
        with self.assertRaises(Hold): Catalog(json.dumps(self.doc).encode(),'0'*64,POLICY)

    def test_project_budget_cannot_be_expanded_by_catalog(self):
        raw=json.dumps(self.doc,sort_keys=True).encode(); sha=hashlib.sha256(raw).hexdigest()
        for policy in (dict(POLICY,project='other-project'),dict(POLICY,max_object_bytes=16),
                       dict(POLICY,recipients=['other-window']),dict(POLICY,root_refs=['other-root'])):
            with self.assertRaises(Hold): Catalog(raw,sha,policy)

    def test_expired_and_future_catalog(self):
        for now in (NOW-2,NOW+3600):
            with self.assertRaises(Hold): self.chunk(now=now)

    def test_path_traversal_and_absolute(self):
        for path in ('../module','/etc/shadow','dist/../module','dist//module','dist/./module'):
            self.doc['objects'][0]['relative_path']=path
            with self.assertRaisesRegex(Hold,'PATH'): self.make_catalog()

    def test_duplicate_alias_and_count_limits(self):
        self.doc['objects'].append(dict(self.doc['objects'][0],ref='second-name'))
        with self.assertRaises(Hold): self.make_catalog()
        self.doc['objects']=self.doc['objects']*40
        with self.assertRaises(Hold): self.make_catalog()

    def test_duplicate_json_and_nonfinite(self):
        for raw in (b'{"schema":1,"schema":1}',b'{"schema":NaN}'):
            with self.assertRaises(Hold): Catalog(raw,hashlib.sha256(raw).hexdigest(),POLICY)

    def test_file_changed_from_approved_sha(self):
        p=self.src/'dist'/'module.mjs'; p.write_bytes(b'X'*len(self.data))
        with self.assertRaisesRegex(Hold,'SHA'): self.chunk()

    def test_symlink_and_hardlink_sources(self):
        p=self.src/'dist'/'module.mjs'; p.rename(self.src/'original'); p.symlink_to(self.src/'original')
        with self.assertRaises(OSError): self.chunk()
        p.unlink(); os.link(str(self.src/'original'),str(p))
        with self.assertRaisesRegex(Hold,'METADATA'): self.chunk()

    def test_parent_symlink_and_mode(self):
        d=self.src/'dist'; d.rename(self.src/'real'); d.symlink_to(self.src/'real')
        with self.assertRaises(OSError): self.chunk()
        d.unlink(); (self.src/'real').rename(d); os.chmod(str(d),0o777)
        with self.assertRaisesRegex(Hold,'PARENT'): self.chunk()

    def test_replaced_source_directory_is_detected(self):
        original=os.read; moved=[]
        def change(fd,n):
            b=original(fd,n)
            if not moved:
                (self.src/'dist').rename(self.src/'old-dist')
                (self.src/'dist').mkdir(mode=0o700); moved.append(True)
            return b
        with patch('production.cloud_connection.private_transfer.os.read',side_effect=change):
            with self.assertRaisesRegex(Hold,'MOVED'): self.chunk()

    def test_replaced_receiver_root_is_detected(self):
        self.dst.rename(self.root/'old-receiver'); self.dst.mkdir(mode=0o700)
        with self.assertRaisesRegex(Hold,'ROOT_MOVED'): self.receiver.accept(self.chunk(),NOW)
        self.assertEqual(list(self.dst.iterdir()),[])

    def test_first_chunk_and_out_of_order(self):
        with self.assertRaises(Hold): self.receiver.accept(self.chunk(CHUNK),NOW)
        self.assertEqual(list(self.dst.iterdir()),[])

    def test_idempotent_chunk_and_completed_object(self):
        e=self.chunk(); self.receiver.accept(e,NOW); self.receiver.accept(e,NOW)
        self.assertEqual(self.q.db.execute('SELECT COUNT(*) FROM connection_file_events').fetchone()[0],1)
        r=self.complete(); self.assertEqual(self.receiver.accept(e,NOW)['private_ref'],r['private_ref'])

    def test_chunk_corruption_and_oversize(self):
        e=self.chunk(); e['data']=base64.b64encode(b'bad').decode()
        with self.assertRaises(Hold): self.receiver.accept(e,NOW)
        e['data']='A'*1000000
        with self.assertRaisesRegex(Hold,'BOUND'): self.receiver.accept(e,NOW)

    def test_original_success_job_and_manifest_are_required(self):
        self.q.db.execute("UPDATE connection_jobs SET state='UNKNOWN' WHERE request_id='approved-transfer'")
        with self.assertRaisesRegex(Hold,'NOT_SUCCESS'): self.chunk()

    def test_original_receipt_cannot_be_cross_object_or_receiver(self):
        for key,value in [('object_ref','another'),('recipient_id','other'),('invoke_id','t-other'),('sha256','0'*64)]:
            r=self.receipt(); r[key]=value
            self.q.db.execute('UPDATE connection_jobs SET receipt_json=?',(json.dumps(r),))
            with self.assertRaisesRegex(Hold,'RECEIPT_BINDING'): self.chunk()

    def test_custody_quota_preserves_partial(self):
        e=self.chunk()
        with patch('production.cloud_connection.private_transfer.MAX_TOTAL',1):
            with self.assertRaisesRegex(Hold,'QUOTA'): self.receiver.accept(e,NOW)
        self.assertTrue(list(self.dst.glob('*.partial')))

    def test_failure_audit_is_private_immutable_and_bound(self):
        self.receiver.accept(self.chunk(),NOW)
        e=self.chunk(CHUNK); e['recipient_id']='other-window'
        with self.assertRaises(Hold) as caught: self.receiver.accept(e,NOW)
        self.assertTrue(caught.exception.failure_audit_recorded)
        row=self.q.db.execute('SELECT event_id,delivery_id,observed,code FROM connection_file_failures').fetchone()
        self.assertEqual((row[2],row[3]),(NOW,'ENVELOPE_BINDING'))
        self.assertNotIn('other-window',str(row))
        for sql in ('DELETE FROM connection_file_failures','UPDATE connection_file_failures SET code=\'OTHER\''):
            with self.assertRaises(sqlite3.IntegrityError): self.q.db.execute(sql)

    def test_short_write_resumes_until_complete(self):
        original=os.pwrite
        def short(fd,data,offset): return original(fd,data[:73],offset)
        with patch('production.cloud_connection.private_transfer.os.pwrite',side_effect=short):
            self.assertEqual(self.complete()['state'],'SUCCESS')

    def test_source_timeout_does_not_return_bytes(self):
        with patch('production.cloud_connection.private_transfer.time.monotonic',side_effect=[0,31]):
            with self.assertRaisesRegex(Hold,'TIMEOUT'): self.chunk()

    def test_oversized_and_total_catalog_are_rejected(self):
        self.doc['objects'][0]['bytes']=64*1024*1024+1
        with self.assertRaisesRegex(Hold,'SIZE'): self.make_catalog()
        self.doc['objects']=[dict(self.doc['objects'][0],ref='ref'+str(i),relative_path='file'+str(i),bytes=64*1024*1024) for i in range(5)]
        with self.assertRaisesRegex(Hold,'TOTAL'): self.make_catalog()

    def test_os_job_does_not_authorize_other_objects(self):
        # No broadening of the already-deployed /etc/os-release capability.
        self.q.db.execute('DROP TRIGGER connection_no_rebind')
        r=dict(self.request,operation='fetch_os_release',arguments={'path':'/etc/os-release','max_bytes':65536})
        self.q.db.execute('UPDATE connection_jobs SET request_json=?',(json.dumps(r),))
        with self.assertRaisesRegex(Hold,'SCOPE'): self.chunk()

    def test_nested_transaction_is_not_committed_or_rolled_back(self):
        self.q.db.execute('BEGIN IMMEDIATE')
        self.q.db.execute('CREATE TABLE upstream(value INTEGER)')
        with self.assertRaisesRegex(Hold,'TRANSACTION'): self.receiver.accept(self.chunk(),NOW)
        with self.assertRaisesRegex(Hold,'TRANSACTION'):
            Receiver(self.q.db,str(self.dst),self.catalog,'work-window')
        self.assertTrue(self.q.db.in_transaction)
        self.assertIsNotNone(self.q.db.execute("SELECT name FROM sqlite_master WHERE name='upstream'").fetchone())
        self.q.db.rollback()

    def test_two_connections_lock_contention(self):
        other=sqlite3.connect(str(self.root/'queue.sqlite'),timeout=0,isolation_level=None)
        other.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(sqlite3.OperationalError): self.receiver.accept(self.chunk(),NOW)
            self.assertFalse(self.q.db.in_transaction)
            self.assertEqual(list(self.dst.iterdir()),[])
        finally: other.rollback(); other.close()

    def test_real_commit_busy_preserves_unknown_bytes(self):
        # In DELETE journal, a held reader permits BEGIN/write but blocks COMMIT.
        reader=sqlite3.connect(str(self.root/'queue.sqlite'),timeout=0,isolation_level=None)
        reader.execute('BEGIN'); reader.execute('SELECT * FROM connection_jobs').fetchall()
        try:
            with self.assertRaises(sqlite3.OperationalError): self.receiver.accept(self.chunk(),NOW)
        finally: reader.rollback(); reader.close()
        self.assertFalse(self.q.db.in_transaction)
        self.assertTrue(list(self.dst.glob('*.partial')))
        with self.assertRaises((Hold,FileExistsError)): self.receiver.accept(self.chunk(),NOW)

    def test_final_commit_busy_reconciles_sha_without_rewrite(self):
        offsets=list(range(0,len(self.data),CHUNK))
        for pos in offsets[:-1]: self.receiver.accept(self.chunk(pos),NOW)
        reader=sqlite3.connect(str(self.root/'queue.sqlite'),timeout=0,isolation_level=None)
        reader.execute('BEGIN'); reader.execute('SELECT * FROM connection_jobs').fetchall()
        try:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                self.receiver.accept(self.chunk(offsets[-1]),NOW)
            self.assertFalse(caught.exception.failure_audit_recorded)
        finally: reader.rollback(); reader.close()
        with patch('production.cloud_connection.private_transfer.os.pwrite',side_effect=AssertionError('must not rewrite')):
            r=self.receiver.reconcile('approved-transfer','module-object',NOW)
        self.assertEqual(r['state'],'SUCCESS')
        proof=self.q.db.execute('SELECT bytes,sha256 FROM connection_file_events WHERE offset=-1').fetchone()
        self.assertEqual(proof,(len(self.data),hashlib.sha256(self.data).hexdigest()))
        events=self.q.db.execute('SELECT * FROM connection_file_events').fetchall()
        with patch('production.cloud_connection.private_transfer.os.pwrite',side_effect=AssertionError('must not rewrite')):
            self.assertEqual(self.receiver.accept(self.chunk(offsets[-1]),NOW),r)
        self.assertEqual(self.q.db.execute('SELECT * FROM connection_file_events').fetchall(),events)
        bad=self.chunk(offsets[-1]); block=b'X'+base64.b64decode(bad['data'])[1:]
        bad['data']=base64.b64encode(block).decode('ascii'); bad['chunk_sha256']=hashlib.sha256(block).hexdigest()
        with self.assertRaisesRegex(Hold,'REPLAY_MISMATCH'): self.receiver.accept(bad,NOW)
        final=self.dst/r['private_ref']
        with final.open('r+b') as f: f.write(b'X')
        with self.assertRaisesRegex(Hold,'REPLAY_MISMATCH'):
            self.receiver.accept(self.chunk(offsets[-1]),NOW)
        self.assertEqual(self.q.db.execute('SELECT * FROM connection_file_events').fetchall(),events)

    def test_wal_lock_contention(self):
        self.q.db.execute('PRAGMA journal_mode=WAL')
        self.test_two_connections_lock_contention()

    def test_rollback_failure_is_unknown_and_preserves_primary_cause(self):
        original=self.q.db
        class FailedRollback:
            def __getattr__(self,name): return getattr(original,name)
            def rollback(self): raise OSError('fixture rollback failure')
        self.receiver.db=FailedRollback()
        try:
            with patch('production.cloud_connection.private_transfer.os.pwrite',side_effect=KeyboardInterrupt()):
                with self.assertRaisesRegex(Hold,'ROLLBACK_FAILED_UNKNOWN') as caught:
                    self.receiver.accept(self.chunk(),NOW)
            self.assertIsInstance(caught.exception.__cause__,KeyboardInterrupt)
            self.assertTrue(list(self.dst.glob('*.partial')))
        finally:
            original.rollback(); self.receiver.db=original

    def test_process_restart_resumes_original_partial(self):
        self.receiver.accept(self.chunk(),NOW)
        script='''import sys,sqlite3
from production.cloud_connection.private_transfer import Catalog,Receiver
raw=bytes.fromhex(sys.argv[3]); c=Catalog(raw,sys.argv[4],__import__('json').loads(sys.argv[5]))
db=sqlite3.connect(sys.argv[1],isolation_level=None,timeout=0)
r=Receiver(db,sys.argv[2],c,'work-window'); v=r.reconcile('approved-transfer','module-object',1800000000)
assert v['state']=='PARTIAL' and v['received_bytes']==65536
r.close(); db.close()
'''
        raw=json.dumps(self.doc,sort_keys=True).encode()
        subprocess.run([sys.executable,'-B','-c',script,str(self.root/'queue.sqlite'),str(self.dst),raw.hex(),self.catalog.sha,json.dumps(POLICY)],check=True,timeout=10)
        self.assertEqual(self.complete()['state'],'SUCCESS')

    def test_interrupted_publication_reconciles_exact_inode(self):
        original=os.unlink
        def interrupt(name,*args,**kw):
            if str(name).endswith('.partial'): raise KeyboardInterrupt()
            return original(name,*args,**kw)
        with patch('production.cloud_connection.private_transfer.os.unlink',side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.complete()
        self.assertEqual(len(list(self.dst.iterdir())),2)
        self.assertEqual(self.receiver.reconcile('approved-transfer','module-object',NOW)['state'],'SUCCESS')
        self.assertEqual(len(list(self.dst.iterdir())),1)

    def test_audit_replace_upsert_update_delete_are_rejected(self):
        self.receiver.accept(self.chunk(),NOW)
        ident,binding,offset,state=self.q.db.execute('SELECT * FROM connection_file_delivery').fetchone()
        for sql,args in [
            ('INSERT OR REPLACE INTO connection_file_delivery VALUES(?,?,?,?)',(ident,binding,offset,state)),
            ('REPLACE INTO connection_file_delivery VALUES(?,?,?,?)',(ident,binding,offset,state)),
            ('INSERT INTO connection_file_delivery VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET binding=excluded.binding',(ident,binding,offset,state)),
            ('UPDATE connection_file_delivery SET id=? WHERE id=?',('different',ident)),
            ('DELETE FROM connection_file_delivery WHERE id=?',(ident,))]:
            with self.assertRaises(sqlite3.IntegrityError): self.q.db.execute(sql,args)
        event=self.q.db.execute('SELECT * FROM connection_file_events').fetchone()
        with self.assertRaises(sqlite3.IntegrityError): self.q.db.execute('INSERT OR REPLACE INTO connection_file_events VALUES(?,?,?,?)',event)

    def test_destination_symlink_refused(self):
        e=self.chunk()
        _,_,_,ident=self.receiver.binding('approved-transfer','module-object',NOW)
        (self.dst/(ident+'.partial')).symlink_to(self.src/'dist'/'module.mjs')
        with self.assertRaises(FileExistsError): self.receiver.accept(e,NOW)
        self.assertEqual((self.src/'dist'/'module.mjs').read_bytes(),self.data)

    def test_empty_file(self):
        # Build a separate approved empty object and rebind only the test fixture.
        self.doc['objects'][0].update(bytes=0,sha256=hashlib.sha256(b'').hexdigest())
        (self.src/'dist'/'module.mjs').write_bytes(b''); self.catalog=self.make_catalog()
        self.q.db.execute('DROP TRIGGER connection_no_rebind')
        self.request['arguments']['manifest_sha256']=self.catalog.sha
        self.q.db.execute('UPDATE connection_jobs SET request_json=?',(json.dumps(self.request),))
        self.q.db.execute('UPDATE connection_jobs SET receipt_json=?',(json.dumps(self.receipt()),))
        self.receiver.catalog=self.catalog
        self.assertEqual(self.receiver.accept(self.chunk(),NOW)['state'],'SUCCESS')
