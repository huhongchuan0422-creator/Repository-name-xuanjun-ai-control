"""Real pinned Artifact read/verify/stage; only disposable Hosted root paths."""
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('p2_delivery',str(HERE/'prepare.py'))
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)

class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=delivery.download(artifact_api=True)
        cls.rows,cls.bundle,cls.kit=delivery.verify(cls.raw)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/root')
        self.addCleanup(self.tmp.cleanup)
        self.root=self.tmp.name+'/delivery'
    def tar(self,name,kind=tarfile.REGTYPE,duplicate=False):
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w:gz') as archive:
            row=tarfile.TarInfo(name);row.type=kind;row.size=0
            archive.addfile(row,io.BytesIO(b''))
            if duplicate:archive.addfile(row,io.BytesIO(b''))
        return out.getvalue()
    def test_actual_artifact_zip_pin(self):
        self.assertEqual(delivery.sha(self.raw),delivery.ZIP_SHA)
    def test_actual_kit_and_source_bindings(self):
        manifest=delivery.decode(self.rows['MANIFEST.json'])
        self.assertEqual((manifest['source_commit'],manifest['source_tree']),
            (delivery.COMMIT,delivery.TREE))
        self.assertEqual(len(manifest['files']),40)
        self.assertEqual(manifest['tests'],175)
    def test_actual_257_legacy_files(self):
        km=delivery.decode(self.rows['attempt5-manifest.json'])
        self.assertEqual(len(km['inherited_files']),257)
        for name,pin in km['inherited_files'].items():
            self.assertEqual(delivery.sha(self.kit[name]),pin)
    def test_tampered_zip_rejected(self):
        with self.assertRaises(delivery.Hold):delivery.verify(self.raw+b'changed')
    def test_absolute_tar_path_rejected(self):
        with self.assertRaises(delivery.Hold):delivery.tar_rows(self.tar('/evil'))
    def test_parent_tar_path_rejected(self):
        with self.assertRaises(delivery.Hold):delivery.tar_rows(self.tar('a/../evil'))
    def test_symlink_tar_rejected(self):
        with self.assertRaises(delivery.Hold):delivery.tar_rows(self.tar('link',tarfile.SYMTYPE))
    def test_duplicate_tar_rejected(self):
        with self.assertRaises(delivery.Hold):delivery.tar_rows(self.tar('file',duplicate=True))
    def test_real_staging_and_private_receipt(self):
        receipt=delivery.stage(self.raw,self.root)
        self.assertFalse(receipt['install_executed'])
        path=Path(self.root)/delivery.COMMIT
        self.assertEqual(json.loads((path/'PREPARATION_RECEIPT.json').read_text()),receipt)
        self.assertEqual((path/'kit/attempt5-manifest.json').read_bytes(),
            self.rows['attempt5-manifest.json'])
        self.assertEqual(os.stat(str(path/'PREPARATION_RECEIPT.json')).st_mode&0o777,0o600)
    def test_existing_version_never_overwritten(self):
        delivery.stage(self.raw,self.root)
        before=(Path(self.root)/delivery.COMMIT/'PREPARATION_RECEIPT.json').read_bytes()
        with self.assertRaises(delivery.Hold):delivery.stage(self.raw,self.root)
        self.assertEqual((Path(self.root)/delivery.COMMIT/'PREPARATION_RECEIPT.json').read_bytes(),before)
    def test_output_symlink_refused(self):
        os.symlink(self.tmp.name,self.root)
        with self.assertRaises(OSError):delivery.stage(self.raw,self.root)
    def test_partial_output_retained_after_fsync_failure(self):
        original=delivery.os.fsync
        def fail(fd):
            if os.path.isfile('/proc/self/fd/'+str(fd)):
                raise OSError('TEST_FSYNC_FAILURE')
            return original(fd)
        with mock.patch.object(delivery.os,'fsync',side_effect=fail):
            with self.assertRaises(OSError):delivery.stage(self.raw,self.root)
        version=Path(self.root)/delivery.COMMIT
        self.assertTrue(version.exists())
        self.assertFalse((version/'PREPARATION_RECEIPT.json').exists())
        with self.assertRaises(delivery.Hold):delivery.stage(self.raw,self.root)
    def test_unknown_metadata_does_not_open_database(self):
        with mock.patch.object(delivery.os,'lstat',side_effect=PermissionError()):
            result=delivery.observe()
        self.assertTrue(all(v['state']=='UNKNOWN_METADATA_ERROR' for v in result.values()))
    def test_wrong_host_main_refuses_before_writes(self):
        with mock.patch.object(delivery.os,'uname',return_value=type('U',(),{'nodename':'OTHER_HOST'})()):
            with self.assertRaises(delivery.Hold):delivery.main()
        self.assertFalse(Path(self.root).exists())
    def test_concurrent_delivery_lock(self):
        base=delivery.directory(self.root,create=True);os.close(base)
        lock=os.open(self.root+'/.delivery.lock',os.O_CREAT|os.O_RDWR,0o600)
        import fcntl
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            with self.assertRaises(BlockingIOError):delivery.stage(self.raw,self.root)
        finally:os.close(lock)
        self.assertFalse((Path(self.root)/delivery.COMMIT).exists())
    def test_child_restart_refuses_existing_version(self):
        delivery.stage(self.raw,self.root)
        source=HERE/'prepare.py'
        raw=Path(self.tmp.name)/'artifact.zip';raw.write_bytes(self.raw)
        code=('import sys,importlib.util;'
            's=importlib.util.spec_from_file_location("d",sys.argv[1]);'
            'd=importlib.util.module_from_spec(s);s.loader.exec_module(d);'
            'd.stage(open(sys.argv[2],"rb").read(),sys.argv[3])')
        r=subprocess.run([__import__('sys').executable,'-I','-B','-S','-c',code,
            str(source),str(raw),self.root],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertNotEqual(r.returncode,0)
        self.assertIn(b'VERSION_DIRECTORY_EXISTS_RETAINED_NO_OVERWRITE',r.stderr)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(DeliveryTests))
    assert result.wasSuccessful() and result.testsRun==16 and not result.skipped
