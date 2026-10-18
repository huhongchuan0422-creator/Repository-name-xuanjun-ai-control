"""Actual built Kit, strict inventory and cached module imports. No Prepare."""
import importlib.util
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
HERE=Path(__file__).resolve().parent

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
builder=load(HERE/'build_kit.py','kit_builder')
entry=load(HERE/'runtime/versioned_entry.py','kit_entry')
class KitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='p2-kit5-',dir='/')
        self.root=Path(self.temp.name)/'epoch7-attempt5-candidate-v1'
        raw,self.manifest=builder.build('a'*40,'b'*40)
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            for row in archive.getmembers():
                p=Path(self.temp.name)/row.name
                p.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
                with p.open('xb') as out:out.write(archive.extractfile(row).read())
                p.chmod(0o444)
        self.pin=builder.sha(builder.canonical(self.manifest))
    def tearDown(self):self.temp.cleanup()
    def test_actual_native_module_import_closure(self):
        with entry.imports(str(self.root),self.pin) as report:
            import native_recovery,attempt_ledger,authority_store,receipt_provider,issuer_service
            self.assertTrue(native_recovery.NativeRecovery)
            self.assertEqual(attempt_ledger.MAX_ATTEMPTS,5)
            self.assertFalse(report['production_authorized'])
    def test_manifest_pin_refuses(self):
        with self.assertRaises(ValueError):
            with entry.imports(str(self.root),'f'*64):pass
    def test_extra_file_refuses(self):
        (self.root/'extra').write_bytes(b'x')
        with self.assertRaises(ValueError):
            with entry.imports(str(self.root),self.pin):pass
    def test_symlink_refuses(self):
        (self.root/'extra').symlink_to(self.root/'attempt5-manifest.json')
        with self.assertRaises(ValueError):
            with entry.imports(str(self.root),self.pin):pass
    def test_changed_source_refuses(self):
        path=self.root/'attempt5/runtime/native_recovery.py';path.chmod(0o600);path.write_bytes(b'changed');path.chmod(0o444)
        with self.assertRaises(ValueError):
            with entry.imports(str(self.root),self.pin):pass
    def test_inherited_257_files_remain_exact(self):
        self.assertEqual(len(self.manifest['inherited_files']),257)
        for name,pin in self.manifest['inherited_files'].items():self.assertEqual(builder.sha((self.root/name).read_bytes()),pin)
if __name__=='__main__':unittest.main()
