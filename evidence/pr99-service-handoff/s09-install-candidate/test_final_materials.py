import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import final_materials as f
from migration_transaction import Hold, encode


class MaterialsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=self.root/'source';self.source.mkdir(mode=0o700)
        (self.source/'data').mkdir()
        (self.source/'data'/'fixture.json').write_bytes(b'{"fixture":true}')
        self.dest=self.root/'received'
        self.names=['data/fixture.json']
    def snapshot(self,proof=lambda:'a'*64):
        return f.snapshot_fenced_files(self.source,self.dest,self.names,proof)
    def test_real_file_copy_and_exact_verification(self):
        receipt=self.snapshot()
        self.assertTrue(f.verify_received(self.dest,receipt,f.sha(encode(receipt))))
        self.assertEqual((self.dest/self.names[0]).read_bytes(),b'{"fixture":true}')
    def test_final_fence_must_remain_same(self):
        calls=iter(['a'*64,'b'*64])
        with self.assertRaisesRegex(Hold,'FENCE_CHANGED'):self.snapshot(lambda:next(calls))
        self.assertTrue((self.dest/self.names[0]).exists())
        self.assertFalse((self.dest/'final-checkpoint.receipt.json').exists())
    def test_source_changed_after_copy_preserved(self):
        count=0
        def proof():
            nonlocal count
            count+=1
            if count==2:(self.source/self.names[0]).write_bytes(b'drift')
            return 'a'*64
        with self.assertRaisesRegex(Hold,'SOURCE_CHANGED'):self.snapshot(proof)
        self.assertEqual((self.dest/self.names[0]).read_bytes(),b'{"fixture":true}')
    def test_replay_preserves_destination(self):
        self.snapshot()
        with self.assertRaises(FileExistsError):self.snapshot()
        self.assertTrue((self.dest/'final-checkpoint.receipt.json').exists())
    def test_no_fence_no_directory(self):
        with self.assertRaisesRegex(Hold,'FENCE_PROOF_REQUIRED'):self.snapshot(lambda:None)
        self.assertFalse(self.dest.exists())
    def test_traversal_duplicates_empty(self):
        for names in (['../private'],['/private'],['data//fixture'],['data/./fixture'],[],['same','same']):
            with self.subTest(names=names),self.assertRaises(Hold):
                f.snapshot_fenced_files(self.source,self.dest,names,lambda:'a'*64)
        self.assertFalse(self.dest.exists())
    def test_symlink_source_rejected(self):
        (self.source/'link').symlink_to(self.source/self.names[0])
        self.names=['link']
        with self.assertRaisesRegex(Hold,'INPUT_SYMLINK'):self.snapshot()
    def test_hardlink_source_rejected(self):
        import os
        os.link(self.source/self.names[0],self.source/'hard')
        with self.assertRaisesRegex(Hold,'INPUT_TYPE_SIZE'):self.snapshot()
    def test_extra_received_file_rejected(self):
        r=self.snapshot();(self.dest/'extra').write_bytes(b'extra')
        with self.assertRaisesRegex(Hold,'RECEIVED_EXACT_SET'):f.verify_received(self.dest,r,f.sha(encode(r)))
    def test_received_content_tamper_rejected(self):
        r=self.snapshot();p=self.dest/self.names[0];p.chmod(0o600);p.write_bytes(b'different')
        with self.assertRaisesRegex(Hold,'RECEIVED_HASH_SIZE'):f.verify_received(self.dest,r,f.sha(encode(r)))
    def test_preliminary_class_rejected(self):
        r=self.snapshot();r['class']='PRELIMINARY'
        with self.assertRaisesRegex(Hold,'CHECKPOINT_BINDING'):f.verify_received(self.dest,r,f.sha(encode(r)))
    def test_manifest_wrong_approved_hash_rejected(self):
        r=self.snapshot()
        with self.assertRaisesRegex(Hold,'CHECKPOINT_BINDING'):f.verify_received(self.dest,r,'f'*64)
    def test_copy_failure_preserves_partial_no_receipt(self):
        with patch.object(f,'write_bytes',side_effect=OSError('full')):
            with self.assertRaises(OSError):self.snapshot()
        self.assertTrue(self.dest.exists())
        self.assertFalse((self.dest/'final-checkpoint.receipt.json').exists())
    def test_route_cutover_restore_actual_bytes(self):
        route=self.root/'route.conf';route.write_bytes(b'old');route.chmod(0o600)
        state=self.root/'route-state'
        r=f.replace_owned_route(route,f.sha(b'old'),b'new',state)
        self.assertEqual(route.read_bytes(),b'new')
        self.assertIn('HTTPS_PENDING',r['status'])
        r=f.restore_owned_route(route,state)
        self.assertEqual(route.read_bytes(),b'old');self.assertFalse(r['source_writer_resumed'])
        self.assertEqual((state/'after').read_bytes(),b'new')
    def test_route_conflict_does_not_create_state(self):
        route=self.root/'route.conf';route.write_bytes(b'foreign');route.chmod(0o600)
        state=self.root/'route-state'
        with self.assertRaisesRegex(Hold,'ROUTE_CAS_CONFLICT'):
            f.replace_owned_route(route,f.sha(b'old'),b'new',state)
        self.assertFalse(state.exists());self.assertEqual(route.read_bytes(),b'foreign')
    def test_rollback_foreign_route_never_overwritten(self):
        route=self.root/'route.conf';route.write_bytes(b'old');route.chmod(0o600)
        state=self.root/'route-state';f.replace_owned_route(route,f.sha(b'old'),b'new',state)
        route.write_bytes(b'foreign')
        with self.assertRaisesRegex(Hold,'ROLLBACK_FOREIGN_ROUTE'):f.restore_owned_route(route,state)
        self.assertEqual(route.read_bytes(),b'foreign')
    def test_route_symlink_rejected(self):
        target=self.root/'actual';target.write_bytes(b'old')
        route=self.root/'route';route.symlink_to(target)
        with self.assertRaisesRegex(Hold,'INPUT_SYMLINK'):
            f.replace_owned_route(route,f.sha(b'old'),b'new',self.root/'state')
        self.assertEqual(target.read_bytes(),b'old')
    def test_route_crash_after_replace_keeps_snapshots(self):
        route=self.root/'route';route.write_bytes(b'old');route.chmod(0o600)
        state=self.root/'state';real=f.sync_directory
        def sync(p):
            if p==route.parent and route.read_bytes()==b'new':raise OSError('crash')
            return real(p)
        with patch.object(f,'sync_directory',sync):
            with self.assertRaises(OSError):f.replace_owned_route(route,f.sha(b'old'),b'new',state)
        self.assertEqual(route.read_bytes(),b'new')
        self.assertEqual((state/'before').read_bytes(),b'old')
        self.assertEqual((state/'after').read_bytes(),b'new')

if __name__=='__main__':unittest.main()
