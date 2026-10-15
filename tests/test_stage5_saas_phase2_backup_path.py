"""Offline recovery path-safety regression. No production databases."""
import os
import pathlib
import sqlite3
import tempfile
import unittest

from scripts.community_saas_phase2_recovery import backup, verify_backup

class BackupPathSafety(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        self.source=self.root/"source.sqlite"
        db=sqlite3.connect(self.source)
        db.execute("CREATE TABLE sample(value TEXT)")
        db.execute("INSERT INTO sample VALUES('untouched')")
        db.commit()
        db.close()

    def test_valid_backup_and_verify(self):
        target=self.root/"copy.sqlite"
        receipt=backup(self.source,target)
        self.assertEqual(receipt["destination"],str(target))
        self.assertTrue(verify_backup(target,receipt["sha256"])["verified"])

    def test_source_symlink_forbidden(self):
        link=self.root/"source-link.sqlite"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError,"SOURCE_DB_MISSING"):
            backup(link,self.root/"copy.sqlite")

    def test_backup_symlink_forbidden(self):
        target=self.root/"copy.sqlite"
        target.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError,"BACKUP_PATH_UNSAFE"):
            backup(self.source,target)
        with self.assertRaisesRegex(ValueError,"SOURCE_DB_MISSING"):
            verify_backup(target,"0"*64)

    def test_existing_backup_never_overwritten(self):
        target=self.root/"copy.sqlite"
        target.write_text("do not replace")
        with self.assertRaisesRegex(ValueError,"BACKUP_PATH_UNSAFE"):
            backup(self.source,target)
        self.assertEqual(target.read_text(),"do not replace")

    def test_destination_created_during_backup_not_replaced(self):
        target=self.root/"copy.sqlite"
        original=os.link
        def race(source,dest):
            pathlib.Path(dest).write_text("concurrent")
            return original(source,dest)
        from unittest.mock import patch
        with patch("scripts.community_saas_phase2_recovery.os.link",side_effect=race):
            with self.assertRaises(FileExistsError):
                backup(self.source,target)
        self.assertEqual(target.read_text(),"concurrent")

if __name__=="__main__":
    unittest.main()
