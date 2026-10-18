"""Real six-store backup/restore and failure isolation; synthetic customer data."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
import test_community_mini_center_identity as center_fixture
from scripts.community_mini_application import MiniApplication
from scripts.community_stage_recovery import snapshot,restore
from scripts.community_order_store import create_order,state

class CompleteStoreRecovery(unittest.TestCase):
    def setUp(self):
        self.fx=center_fixture.ExistingCenterComposition('test_core_bytes_are_identical_to_explicit_website_pin');self.fx.setUp()
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.app=self.open(self.root/'state')
        self.scope=self.fx.stage.api.bindings[self.fx.stage.customer]
        create_order(self.app.stage.demo.db,self.scope,'persisted_order',101)
    def open(self,path):
        return MiniApplication(self.fx.center,path,self.fx.stage.api.bindings,
            self.fx.stage.api.bindings[self.fx.stage.customer],self.fx.scenes,self.fx.identity.appid,'a'*32)
    def tearDown(self):self.app.close();self.tmp.cleanup();self.fx.tearDown()
    def backup(self):
        self.fx.center.db.execute("UPDATE settings SET v='1' WHERE k='maintenance'")
        return snapshot(self.app,self.root/'backup')
    def test_original_order_and_all_schemas_survive_new_directory_restore(self):
        receipt=self.backup();dest=self.root/'restored'
        self.assertTrue(restore(self.root/'backup',receipt['manifest_sha256'],dest)['restored'])
        with self.open(dest) as reopened:
            self.assertEqual(state(reopened.stage.demo.db,self.scope,'persisted_order')['amount_minor'],101)
            self.assertEqual(len(reopened.stage.handles),6)
        self.assertFalse(receipt['cross_database_atomic'])
    def test_backup_requires_center_maintenance_and_no_listener(self):
        with self.assertRaises(PermissionError):snapshot(self.app,self.root/'backup')
        self.fx.center.db.execute("UPDATE settings SET v='1' WHERE k='maintenance'")
        self.app.listen()
        with self.assertRaises(PermissionError):snapshot(self.app,self.root/'backup')
        self.assertFalse((self.root/'backup').exists())
    def test_digest_or_file_change_cannot_create_restore_target(self):
        receipt=self.backup();source=self.root/'backup';dest=self.root/'restored'
        with self.assertRaises(ValueError):restore(source,'0'*64,dest)
        (source/'orders.sqlite').write_bytes(b'changed')
        with self.assertRaises(ValueError):restore(source,receipt['manifest_sha256'],dest)
        self.assertFalse(dest.exists())
    def test_existing_destination_never_overwritten(self):
        receipt=self.backup();dest=self.root/'existing';dest.mkdir();(dest/'keep').write_text('original')
        with self.assertRaises(FileExistsError):restore(self.root/'backup',receipt['manifest_sha256'],dest)
        self.assertEqual((dest/'keep').read_text(),'original')
    def test_hash_valid_but_corrupt_database_cleans_only_new_target(self):
        self.backup();source=self.root/'backup';manifest=json.loads((source/'snapshot.json').read_bytes())
        (source/'orders.sqlite').write_bytes(b'not sqlite')
        manifest['files']['orders.sqlite']=hashlib.sha256(b'not sqlite').hexdigest()
        raw=json.dumps(manifest).encode();(source/'snapshot.json').write_bytes(raw)
        dest=self.root/'restored'
        with self.assertRaises(Exception):restore(source,hashlib.sha256(raw).hexdigest(),dest)
        self.assertFalse(dest.exists());self.assertTrue(source.exists())
    def test_linked_snapshot_files_fail_closed(self):
        receipt=self.backup();source=self.root/'backup';os.link(source/'orders.sqlite',self.root/'alias')
        with self.assertRaises(ValueError):restore(source,receipt['manifest_sha256'],self.root/'restored')
    def test_uncommitted_source_is_rejected_before_backup_creation(self):
        self.fx.center.db.execute("UPDATE settings SET v='1' WHERE k='maintenance'")
        self.app.stage.demo.db.execute('BEGIN')
        try:
            with self.assertRaises(PermissionError):snapshot(self.app,self.root/'backup')
        finally:self.app.stage.demo.db.rollback()
        self.assertFalse((self.root/'backup').exists())

if __name__=='__main__':unittest.main()
