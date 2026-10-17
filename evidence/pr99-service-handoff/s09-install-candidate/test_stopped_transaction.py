import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('tx', Path(__file__).with_name('stopped_transaction.py'))
tx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tx)

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.units = self.base/'units'; self.units.mkdir()
        self.state = self.base/'state'; self.state.mkdir(mode=0o700)
        self.before = {n:'LoadState=not-found\n' for n in tx.ORIGINAL}
        self.permit = {'nonce':'test_nonce_1234567890'}
        self.accepted = {'status':'COPIED_RELEASE_RESTART_CLEANUP_PASS_NOT_PRODUCTION', 'application_processes_stopped':True}
        self.original_read = tx.read_regular
        def read(path,*args,**kwargs):
            if str(path).endswith('restart-acceptance-v1/receipt.json'):
                return json.dumps(self.accepted).encode()
            return self.original_read(path,*args,**kwargs)
        for name,value in [('snapshot',lambda:self.before),('stopped',lambda n:True),('systemctl',lambda *args:''),('read_regular',read)]:
            p=patch.object(tx,name,value);p.start();self.addCleanup(p.stop)
    def install(self):
        tx.install(self.units,self.state,self.permit,'a'*64)
    def test_install_stopped_and_rollback(self):
        self.install()
        self.assertTrue((self.state/'receipt.json').exists())
        tx.rollback(self.units,self.state,self.permit,'b'*64)
        self.assertEqual(list(self.units.iterdir()),[])
        self.assertTrue((self.state/'rollback.receipt.json').exists())
    def test_never_overwrite(self):
        p=self.units/tx.NAMES[0];p.write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError,'TARGET_UNIT_PRESENT'):self.install()
        self.assertEqual(p.read_bytes(),b'foreign')
    def test_rollback_refuses_changed_unit(self):
        self.install();p=self.units/tx.NAMES[0];p.write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError,'ROLLBACK_CONFLICT'):tx.rollback(self.units,self.state,self.permit,'b'*64)
        self.assertEqual(len(list(self.units.iterdir())),3)
    def test_rollback_refuses_running_unit(self):
        self.install()
        with patch.object(tx,'stopped',lambda n:False):
            with self.assertRaisesRegex(RuntimeError,'ROLLBACK_CONFLICT'):tx.rollback(self.units,self.state,self.permit,'b'*64)
        self.assertEqual(len(list(self.units.iterdir())),3)
    def test_partial_failure_preserves_created(self):
        real=tx.write_exclusive
        def write(path,data,*args):
            if Path(path)==self.units/tx.NAMES[1]:raise OSError('fault')
            return real(path,data,*args)
        with patch.object(tx,'write_exclusive',write):
            with self.assertRaises(OSError):self.install()
        self.assertTrue((self.state/'failure.json').exists())
        self.assertEqual(len(list(self.units.iterdir())),1)
        tx.rollback(self.units,self.state,self.permit,'b'*64)
        self.assertEqual(list(self.units.iterdir()),[])
    def test_missing_creation_marker_not_owned(self):
        self.install();(self.state/(tx.NAMES[0]+'.created')).unlink()
        with self.assertRaises(FileNotFoundError):tx.rollback(self.units,self.state,self.permit,'b'*64)
        self.assertEqual(len(list(self.units.iterdir())),3)
    def test_no_activation_or_external_network(self):
        for data in tx.unit_bytes().values():
            self.assertIn(b'PrivateNetwork=yes',data)
            self.assertNotIn(b'[Install]',data)
            self.assertNotIn(b'Restart=always',data)
    def test_admission_binds_source_and_expiry(self):
        path=self.base/'admission.json'; source=b'exact source'
        permit={'schema':1,'host':tx.HOST,'action':'install-stopped','source_sha256':tx.digest(source),'manifest_sha256':tx.digest(tx.encode(tx.manifest())),'issued_at':100,'expires_at':200,'nonce':'test_nonce_1234567890','independent_review_comment_id':123}
        path.write_bytes(tx.encode(permit));path.chmod(0o600)
        with patch.object(tx,'ADMISSION',str(path)),patch.object(tx.time,'time',lambda:150):
            tx.admission('install-stopped',source)
            with self.assertRaisesRegex(RuntimeError,'ADMISSION_ACTION_SOURCE'):tx.admission('install-stopped',b'other source')
        with patch.object(tx,'ADMISSION',str(path)),patch.object(tx.time,'time',lambda:201):
            with self.assertRaisesRegex(RuntimeError,'ADMISSION_EXPIRED'):tx.admission('install-stopped',source)
    def test_symlink_input_rejected(self):
        p=self.base/'real';p.write_bytes(b'bytes');(self.base/'link').symlink_to(p)
        with self.assertRaises(OSError):self.original_read(self.base/'link')

if __name__=='__main__':unittest.main()
