import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'reused-6825'),str(ROOT/'successor_controller')]

import pr17_b5_successor_binder as binder
from pr17_b5_successor_backend import R2HostBackend

class DisposableIO:
    """Temporary path mapping only; never an actual UK lock or admission."""
    def __init__(self,root):self.root=root
    def path(self,path):
        assert path.startswith('/opt/xuanjun-cloud-')
        return self.root/path.lstrip('/')
    def absent(self,path):
        if self.path(path).exists():raise ValueError('TARGET_ALREADY_EXISTS')
    def mkdir(self,path,mode):self.path(path).mkdir(mode=mode)
    def newfile(self,path,raw,mode):
        fd=os.open(self.path(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
        try:os.write(fd,raw);os.fsync(fd)
        finally:os.close(fd)
    def parent(self,path):
        return os.open(self.path(path),os.O_RDONLY|os.O_DIRECTORY)


class ActualBackendPublisherTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        for name in ('connection','oauth'):
            (self.root/('opt/xuanjun-cloud-'+name)/'releases').mkdir(parents=True)
        self.spec=binder.verify_spec_bytes((ROOT/'SUCCESSOR_SPEC.json').read_bytes())
        listed=json.loads((ROOT/'SOURCE_MANIFEST.json').read_bytes())
        self.blobs={x['release_path']:(ROOT/x['bundle_path']).read_bytes()
                    for x in listed['files'] if x['release_path'] is not None}
        self.blobs[binder.MANIFEST_PATH]=(ROOT/'RUNTIME_SOURCE_MANIFEST.json').read_bytes()
        self.io=DisposableIO(self.root)
        self.backend=R2HostBackend(legacy_io=self.io,spec=self.spec,
            source_blobs=self.blobs,observed_bytes={},authority=None)
        self.backend.lock_fd=1
        self.backend.before={'fixture-original-six':'local-test-only'}
        self.backend.generator_inputs_verified=True

    def publish(self):
        self.backend.publish_two_releases_exact(binder.COMMIT,binder.MANIFEST,
                                                 binder.CODEPIN,self.spec)

    def test_real_backend_writes_42_plus_manifest_twice(self):
        self.publish()
        for target in self.spec['fixed_paths']['target_release']:
            for name,raw in self.blobs.items():
                self.assertEqual((self.io.path(target)/name).read_bytes(),raw)
        with self.assertRaises(Exception):
            self.publish()

    def test_wrong_source_fails_before_directory_write(self):
        name='production/cloud_connection/queue.py'
        self.backend.source_blobs[name]+=b'wrong'
        with self.assertRaisesRegex(Exception,'SOURCE_BYTES_CHANGED'):
            self.publish()
        self.assertFalse(self.io.path(self.spec['fixed_paths']['stage_proposed'][0]).exists())


if __name__=='__main__':
    unittest.main()
