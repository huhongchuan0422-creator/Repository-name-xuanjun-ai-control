import importlib.util
import pathlib
import tempfile
import unittest
from cryptography.fernet import Fernet

PATH=pathlib.Path(__file__).resolve().parents[1]/'services/ocr_engine/secure_store.py'
spec=importlib.util.spec_from_file_location('recovery_store',PATH)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class RecoveryJournal(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=module.SecureSQLiteJobStore(self.temp.name+'/ocr.sqlite',Fernet.generate_key())
        self.job=self.store.create('tenant','owner','app','id_front','digest','original-key','attachment','7',2)
    def tearDown(self):self.temp.cleanup()
    def test_exact_lookup_both_routes_immutable(self):
        with self.store._connect() as db:before=tuple(db.execute('SELECT * FROM ocr_jobs').fetchone())
        for locator in ({'job_id':self.job['job_id']},{'original_key':'original-key'}):
            self.assertEqual(self.store.resolve_recovery_job('tenant','owner','app','id_front',**locator),self.job)
        with self.store._connect() as db:self.assertEqual(before,tuple(db.execute('SELECT * FROM ocr_jobs').fetchone()))
    def test_lookup_scope_denial(self):
        for args in [('other','owner','app','id_front'),('tenant','other','app','id_front'),('tenant','owner','other','id_front'),('tenant','owner','app','id_back')]:
            with self.assertRaises(PermissionError):self.store.resolve_recovery_job(*args,original_key='original-key')
        with self.assertRaises(ValueError):self.store.resolve_recovery_job('tenant','owner','app','id_front')
    def test_receipt_replay_conflict_scope_and_encryption(self):
        result={'recovery_id':'reference','visible':'synthetic-private-value'}
        self.assertEqual(self.store.recovery_record('tenant','owner','view','key',{'revision':8},result),result)
        self.assertEqual(self.store.recovery_record('tenant','owner','view','key',{'revision':8},{'other':'ignored'}),result)
        with self.assertRaises(ValueError):self.store.recovery_record('tenant','owner','view','key',{'revision':9},result)
        self.assertIsNone(self.store.recovery_receipt('tenant','other','view','key'))
        self.assertEqual(self.store.recovery_receipt('tenant','owner','view','key'),result)
        self.assertNotIn(b'synthetic-private-value',pathlib.Path(self.store.db_path).read_bytes())
        self.assertEqual(self.store.get(self.job['job_id'],'tenant'),self.job)

if __name__=='__main__':unittest.main()
