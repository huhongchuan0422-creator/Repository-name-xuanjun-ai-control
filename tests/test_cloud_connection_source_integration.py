"""Source contact-point integration; synthetic approvals/identity, no live grant."""
import base64
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from production.cloud_connection.queue import Hold, Queue
from production.cloud_connection.runtime import Loop, code_pin
from production.cloud_connection.private_mcp import PrivateMcp
from production.cloud_connection.worker import ExistingProjectFiles, fixed_command
from production.cloud_connection.credential_lifecycle import utc
import test_cloud_connection_private_transfer as transfer
import test_cloud_connection_credential_lifecycle as lifecycle


class ProjectContactTests(unittest.TestCase):
    setUp = transfer.PrivateTransferTests.setUp
    tearDown = transfer.PrivateTransferTests.tearDown
    make_catalog = transfer.PrivateTransferTests.make_catalog
    receipt = transfer.PrivateTransferTests.receipt

    def adapter(self, enabled=False, recipient=None, catalogs=True):
        registry = {self.catalog.sha:(self.catalog, {'frozen-input':(str(self.src),0)})} if catalogs else None
        return ExistingProjectFiles(self.q.db,registry,recipient,enabled)

    def args(self):
        return dict(manifest_sha256=self.catalog.sha,request_id='approved-transfer',object_ref='module-object',offset=0)

    def test_project_operation_never_falls_back_to_os_probe(self):
        for operation in ('fetch_approved_object','project_fixed_action','run_shell'):
            with self.assertRaisesRegex(Hold,'NOT_ENROLLED'):
                fixed_command({'operation':operation})

    def test_default_disabled(self):
        with self.assertRaisesRegex(Hold,'DISABLED'):
            self.adapter().read(self.args(),transfer.NOW)

    def test_no_authenticated_source_refuses_before_file_read(self):
        with patch('production.cloud_connection.private_transfer.read_object',side_effect=AssertionError('no file access')):
            with self.assertRaisesRegex(Hold,'SOURCE_MISSING'):
                self.adapter(True).read(self.args(),transfer.NOW)

    def test_claimed_recipient_is_not_identity(self):
        for key in ('authenticated_recipient','recipient_id','_meta'):
            a=self.args(); a[key]='work-window'
            with self.assertRaisesRegex(Hold,'ARGUMENTS'):
                self.adapter(True,lambda:'work-window').read(a,transfer.NOW)

    def test_missing_catalog_and_wrong_recipient(self):
        with self.assertRaisesRegex(Hold,'CATALOG_REQUIRED'):
            self.adapter(True,lambda:'work-window',False).read(self.args(),transfer.NOW)
        with self.assertRaisesRegex(Hold,'RECIPIENT'):
            self.adapter(True,lambda:'other-window').read(self.args(),transfer.NOW)

    def test_mcp_internal_bridge_to_original_success_and_receiver(self):
        # Existing future SUCCESS fixture is explicitly synthetic, not dispatch.
        (self.root/'private-results').mkdir(mode=0o700)
        os.chmod(str(self.root/'queue.sqlite'),0o600)
        m=PrivateMcp(self.root)
        try:
            with self.assertRaisesRegex(Hold,'NOT_ENROLLED'): m.read_project_chunk(self.args(),transfer.NOW)
            m.project_files=ExistingProjectFiles(m.db,{self.catalog.sha:(self.catalog,{'frozen-input':(str(self.src),0)})},lambda:'work-window',True)
            for offset in range(0,len(self.data),transfer.CHUNK):
                a=self.args(); a['offset']=offset
                envelope=m.read_project_chunk(a,transfer.NOW)
                result=self.receiver.accept(envelope,transfer.NOW)
            self.assertEqual(result['state'],'SUCCESS')
            self.assertEqual((self.dst/result['private_ref']).read_bytes(),self.data)
            self.assertEqual(result['invoke_id'],'t-existing-invoke')
            # Internal host injection does not register a new tool.
            with self.assertRaisesRegex(Hold,'TOOL_NOT_ENROLLED'): m.call('read_project_chunk',self.args())
        finally: m.close()

    def test_os_job_cannot_authorize_project_object(self):
        # Use another original job rather than mutate immutable history.
        r={'schema':1,'request_id':'os-only','project':'project-fixture','target':'uk',
           'operation':'fetch_os_release','executor_sha256':transfer.PIN,
           'arguments':{'path':'/etc/os-release','max_bytes':65536},'expires_unix':transfer.NOW+60}
        import json
        self.q.submit(json.dumps(r),332398908,transfer.NOW)
        self.q.begin_dispatch('os-only',transfer.NOW)
        self.q.record_invoke('os-only','t-os')
        self.q.terminal('os-only','t-os',{'state':'SUCCESS','invoke_id':'t-os'})
        a=self.args(); a['request_id']='os-only'
        with self.assertRaisesRegex(Hold,'SCOPE'):
            self.adapter(True,lambda:'work-window').read(a,transfer.NOW)


class ExpiryLoopContactTests(unittest.TestCase):
    setUp=lifecycle.CredentialLifecycleTests.setUp
    tearDown=lifecycle.CredentialLifecycleTests.tearDown
    raw=lifecycle.CredentialLifecycleTests.raw

    def loop(self, watch=None, uncertain=False):
        owner=self
        if not hasattr(self,'posts'): self.posts=[]
        class Github:
            def comments(self,since): return []
            def call(self,suffix,body):
                owner.posts.append(body)
                if uncertain: raise Hold('POST_UNKNOWN')
                return {'id':42}
        return Loop(self.q,Github(),None,None,expiry_watch=watch)

    def watch(self):
        raw=self.raw(); return raw,hashlib.sha256(raw).hexdigest()

    def test_default_off_no_watch_table(self):
        self.loop().tick(utc('2026-11-12T00:00:00Z'))
        self.assertEqual(self.posts,[])
        self.assertIsNone(self.q.db.execute("SELECT name FROM sqlite_master WHERE name='connection_credential_watch'").fetchone())

    def test_original_outbox_delivers_once_after_database_reopen(self):
        self.loop(self.watch()).tick(utc('2026-11-12T00:00:00Z'))
        self.q.close(); self.q=Queue(self.path,'a'*64,{332398908})
        self.loop(self.watch()).tick(utc('2026-11-12T01:00:00Z'))
        self.assertEqual(len(self.posts),1)
        self.assertEqual(self.q.db.execute('SELECT state FROM connection_outbox').fetchone(),('SENT',))

    def test_unknown_outbox_not_reposted_after_reopen(self):
        self.loop(self.watch(),True).tick(utc('2026-11-12T00:00:00Z'))
        self.q.close(); self.q=Queue(self.path,'a'*64,{332398908})
        self.loop(self.watch()).tick(utc('2026-11-12T01:00:00Z'))
        self.assertEqual(len(self.posts),1)
        self.assertEqual(self.q.db.execute('SELECT state FROM connection_outbox').fetchone(),('UNKNOWN',))

    def test_expiry_stop_does_not_ingest_or_dispatch(self):
        loop=self.loop(self.watch())
        with patch.object(loop,'ingest',side_effect=AssertionError('must stop')):
            with self.assertRaisesRegex(Hold,'EXPIRY_STOP'): loop.tick(utc('2026-11-19T00:00:00Z'))
        self.assertEqual(len(self.posts),1)

    def test_invalid_metadata_does_not_ingest(self):
        loop=self.loop((self.raw(),'0'*64))
        with patch.object(loop,'ingest',side_effect=AssertionError('must stop')):
            with self.assertRaisesRegex(Hold,'BINDING'): loop.tick(utc('2026-11-12T00:00:00Z'))

    def test_code_pin_binds_imported_candidate_dependencies(self):
        root=Path(self.tmp.name)/'code'; root.mkdir()
        names=('queue.py','worker.py','runtime.py','private_transfer.py','credential_lifecycle.py','fixed_actions.py','pr122_baseline_collector.py','archive_reader.py','material_custody.py')
        for name in names: (root/name).write_bytes(b'fixture')
        first=code_pin(root)
        (root/'credential_lifecycle.py').write_bytes(b'changed')
        self.assertNotEqual(first,code_pin(root))
        for name in ('archive_reader.py','material_custody.py'):
            before=code_pin(root)
            (root/name).write_bytes(b'changed')
            self.assertNotEqual(before,code_pin(root))
        (root/'private_transfer.py').unlink()
        with self.assertRaises(FileNotFoundError): code_pin(root)
