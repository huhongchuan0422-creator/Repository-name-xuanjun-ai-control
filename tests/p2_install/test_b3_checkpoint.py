import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from production.p2_install import b3_checkpoint as c


class Checkpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p2-b3-test-', dir='/tmp')
        self.root = Path(self.tmp.name)/'b3-initialize'
        self.root.mkdir(mode=0o700)
        (self.root/'.initialize.lock').write_bytes(b'')
        (self.root/'.initialize.lock').chmod(0o600)
        (self.root/'commit-receipt.json').write_bytes(b'original-test-receipt')
        self.pin = hashlib.sha256(b'original-test-receipt').hexdigest()
        self.before = (self.root/'commit-receipt.json').stat()
        self.contract = 'a'*64
        self.evidence = {'status':'HOLD','reason':'RUNTIME_UNAVAILABLE'}

    def tearDown(self):
        after = (self.root/'commit-receipt.json').stat()
        for key in ('st_ino','st_mtime_ns','st_mode','st_size','st_nlink'):
            self.assertEqual(getattr(self.before,key),getattr(after,key))
        self.tmp.cleanup()

    def retain(self, action='execute', evidence=None):
        return c.retain(self.root,self.pin,self.contract,'CP05',evidence or self.evidence,action)

    def test_inspect_no_effect(self):
        self.assertEqual(self.retain('inspect')['status'],'NOT_EXECUTED')
        self.assertFalse((self.root/'checkpoints').exists())

    def test_repeated_response_returns_original(self):
        first = self.retain()
        p = Path(first['reference']['path']); before = p.stat()
        self.assertEqual(first,self.retain('recover'))
        self.assertEqual(first,self.retain('inspect'))
        self.assertEqual(before.st_ino,p.stat().st_ino)
        self.assertEqual(before.st_mtime_ns,p.stat().st_mtime_ns)
        self.assertFalse(first['installation_stage_complete'])

    def test_conflict_never_overwrites(self):
        first = self.retain()
        with self.assertRaisesRegex(ValueError,'IMMUTABLE_CONFLICT'):
            self.retain(evidence={'status':'VALIDATED'})
        self.assertEqual(self.retain(), first)

    def test_cp03_not_replayed(self):
        with self.assertRaisesRegex(ValueError,'CHECKPOINT_STAGE'):
            c.retain(self.root,self.pin,self.contract,'CP03',self.evidence)

    def test_wrong_original_pin_no_write(self):
        with self.assertRaisesRegex(ValueError,'CP03_RECEIPT_CHANGED'):
            c.retain(self.root,'b'*64,self.contract,'CP05',self.evidence)
        self.assertFalse((self.root/'checkpoints').exists())

    def test_sigkill_after_publish_new_process_recovers_reference(self):
        program = '''import os,signal,sys
sys.path.insert(0,sys.argv[1])
from production.p2_install import b3_checkpoint as c
c._checkpoint=lambda name:os.kill(os.getpid(),signal.SIGKILL)
c.retain(sys.argv[2],sys.argv[3],'a'*64,'CP05',{'status':'HOLD','reason':'RUNTIME_UNAVAILABLE'})
'''
        result = subprocess.run([sys.executable,'-B','-c',program,str(REPO),str(self.root),self.pin],timeout=10)
        self.assertEqual(result.returncode,-signal.SIGKILL)
        recovery = '''import json,sys
sys.path.insert(0,sys.argv[1])
from production.p2_install import b3_checkpoint as c
print(json.dumps(c.retain(sys.argv[2],sys.argv[3],'a'*64,'CP05',{'status':'HOLD','reason':'RUNTIME_UNAVAILABLE'},'recover')))
'''
        result = subprocess.run([sys.executable,'-B','-c',recovery,str(REPO),str(self.root),self.pin],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),self.retain('inspect'))


if __name__ == '__main__':
    unittest.main()
