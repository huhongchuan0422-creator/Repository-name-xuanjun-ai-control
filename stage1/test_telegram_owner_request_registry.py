import tempfile
import unittest
from pathlib import Path
from telegram_owner_request_registry import create, lookup

class RegistryTests(unittest.TestCase):
    def test_registered_request(self):
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'db.sqlite')
            request=create(path,'task',2,'123','123',now=100,ttl=60)
            row=lookup(path,request)
            self.assertEqual(row['task_id'],'task')
            self.assertEqual(row['fence'],2)
            self.assertEqual(row['expires_at'],160)
            self.assertEqual(row['consumed'],0)
    def test_reject_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                create(str(Path(d)/'db.sqlite'),'task',0,'123','123')
if __name__=="__main__":unittest.main()
