import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import current_point as cp
import run_current_point as launch

class Mechanisms(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, mapping):
        rows = [{"path": n, "bytes": len(b), "sha256": cp.sha(b)}
                for n, b in sorted(mapping.items())]
        h = hashlib.sha256()
        for r in rows:
            h.update((r["path"]+"\0"+r["sha256"]+"\0"+str(r["bytes"])+"\n").encode())
        return {"files": rows, "source_aggregate_sha256": h.hexdigest()}

    def db(self):
        p = self.root/"live.db"
        c = sqlite3.connect(p)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE synthetic (v TEXT)")
        c.execute("INSERT INTO synthetic VALUES ('committed-wal')")
        c.commit()
        return p, c

    def backup(self, p, name="copy.db", seconds=90):
        s = p.stat()
        # Tests explicitly replace only parent trust: pytest temp is under world-writable /tmp.
        with patch.object(cp, "chain"):
            return cp.backup_database(p, self.root/name, (s.st_dev, s.st_ino, s.st_uid), seconds)

    def test_wal_commits_included_uncommitted_excluded_live_main_unchanged(self):
        p, writer = self.db()
        before = cp.hashfile(p)
        self.assertTrue(Path(str(p)+"-wal").stat().st_size > 0)
        writer.execute("INSERT INTO synthetic VALUES ('uncommitted')")
        try:
            result = self.backup(p)
            with sqlite3.connect(self.root/"copy.db") as c:
                self.assertEqual(c.execute("SELECT v FROM synthetic").fetchall(), [("committed-wal",)])
            self.assertEqual(cp.hashfile(p), before)
            self.assertFalse(result["final_trading_checkpoint"])
            self.assertEqual(stat.S_IMODE((self.root/"copy.db").stat().st_mode), 0o400)
        finally:
            writer.rollback()
            writer.close()

    def test_concurrent_writer_not_frozen_and_copy_integrity(self):
        p, c = self.db()
        c.execute("CREATE TABLE large (payload BLOB)")
        c.executemany("INSERT INTO large VALUES (?)", [(b"x"*4096,)]*1800)
        c.commit()
        stop, started = threading.Event(), threading.Event()
        count = []
        def writes():
            w = sqlite3.connect(p)
            try:
                while not stop.is_set():
                    w.execute("INSERT INTO synthetic VALUES ('concurrent')")
                    w.commit()
                    count.append(1)
                    started.set()
                    time.sleep(.01)
            finally:
                w.close()
        t = threading.Thread(target=writes)
        t.start()
        self.assertTrue(started.wait(3))
        try:
            r = self.backup(p, seconds=5)
            self.assertTrue(count)
            self.assertEqual(r["integrity_check"], "PASS")
            self.assertFalse(r["writer_frozen"])
        finally:
            stop.set(); t.join(5); c.close()

    def test_deadline_preserves_failed_new_copy(self):
        p, c = self.db()
        try:
            with self.assertRaisesRegex(cp.Hold, "BACKUP_DEADLINE"):
                self.backup(p, seconds=-1)
            self.assertTrue((self.root/"copy.db").exists())
        finally:
            c.close()

    def test_wrong_database_inode_rejected_before_target(self):
        p, c = self.db()
        try:
            with patch.object(cp, "chain"), self.assertRaisesRegex(cp.Hold, "DATABASE_IDENTITY"):
                cp.backup_database(p, self.root/"copy.db", (p.stat().st_dev, -1, 0))
            self.assertFalse((self.root/"copy.db").exists())
        finally:
            c.close()

    def test_database_symlink_rejected(self):
        p, c = self.db(); link = self.root/"linked.db"; link.symlink_to(p)
        try:
            with patch.object(cp, "chain"), self.assertRaises(cp.Hold):
                cp.backup_database(link, self.root/"copy.db", (0, 0, 0))
        finally:
            c.close()

    def test_corrupt_database_never_passes(self):
        p = self.root/"bad.db"; p.write_bytes(b"not a database")
        with self.assertRaises(sqlite3.DatabaseError):
            self.backup(p)

    def test_existing_backup_never_overwritten(self):
        p, c = self.db(); target = self.root/"copy.db"; target.write_bytes(b"preserve")
        try:
            with self.assertRaisesRegex(cp.Hold, "BACKUP_EXISTS"):
                self.backup(p)
            self.assertEqual(target.read_bytes(), b"preserve")
        finally:
            c.close()

    def test_actual_source_hash_drift_rejected(self):
        p = self.root/"entry.py"; p.write_bytes(b"new")
        row = self.manifest({"entry.py": b"old"})["files"][0]
        with patch.object(cp, "chain"), self.assertRaisesRegex(cp.Hold, "SOURCE_BYTES_DRIFT"):
            cp.stable_bytes(p, row)

    def test_path_traversal_and_secret_directories_rejected(self):
        for name in ("../entry.py", "/entry.py", "a//entry.py", "a\\entry.py", "./entry.py"):
            with self.subTest(name=name), self.assertRaises(cp.Hold):
                cp.relative(name)
        for name in ("config/key.py", "runtime/a.py", "secrets/b.py", ".env"):
            self.assertFalse(cp.selected(Path(name)))

    def test_duplicate_manifest_rejected(self):
        m = self.manifest({"a.py": b"a"}); m["files"].append(m["files"][0])
        with self.assertRaisesRegex(cp.Hold, "SOURCE_ORDER"):
            cp.manifest_rows(m)

    def test_extra_source_file_rejected_not_silently_dropped(self):
        source = self.root/"source"; source.mkdir(); (source/"a.py").write_bytes(b"a")
        (source/"new.py").write_bytes(b"extra")
        dest = self.root/"payload"; dest.mkdir()
        with self.assertRaisesRegex(cp.Hold, "SOURCE_FILE_SET"):
            cp.collect_sources(source, dest, self.manifest({"a.py": b"a"}))

    def test_hardlink_source_rejected(self):
        a = self.root/"a.py"; a.write_bytes(b"a"); os.link(a, self.root/"b.py")
        with patch.object(cp, "chain"), self.assertRaisesRegex(cp.Hold, "HARDLINK"):
            cp.stable_bytes(a, self.manifest({"a.py": b"a"})["files"][0])

    def package(self):
        source = self.manifest({"entry.py": b"# synthetic\n", "requirements.txt": b""})
        payload = self.root/"payload"; payload.mkdir()
        (payload/"code").mkdir(); (payload/"database").mkdir()
        for r in source["files"]:
            (payload/"code"/r["path"]).write_bytes(b"# synthetic\n" if r["path"] == "entry.py" else b"")
        live, c = self.db()
        try:
            s = live.stat()
            with patch.object(cp, "chain"):
                db = cp.backup_database(live, payload/"database/trading.db", (s.st_dev,s.st_ino,s.st_uid))
        finally:
            c.close()
        return cp.make_archive(payload, source["files"], db, self.root), source

    def test_encrypt_decrypt_receive_exact_files_and_database(self):
        r, source = self.package()
        import subprocess
        plain = self.root/"decrypted.tar.gz"
        subprocess.run(["/usr/bin/openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                        "-iter", "200000", "-md", "sha256", "-in", str(self.root/"payload.enc"),
                        "-out", str(plain), "-pass", "file:"+str(self.root/"payload.key")], check=True)
        result = cp.receive_archive(plain, self.root/"received", r, source)
        self.assertEqual(result["database_integrity_check"], "PASS")
        self.assertFalse(result["production_deployed"])
        self.assertEqual(stat.S_IMODE((self.root/"payload.key").stat().st_mode), 0o600)
        with self.assertRaisesRegex(cp.Hold, "RECEIVE_EXISTS"):
            cp.receive_archive(plain, self.root/"received", r, source)

    def test_tampered_archive_hash_rejected_before_destination(self):
        r, source = self.package()
        p = self.root/"payload.tar.gz"; p.write_bytes(p.read_bytes()+b"tamper")
        with self.assertRaisesRegex(cp.Hold, "PLAINTEXT_HASH"):
            cp.receive_archive(p, self.root/"received", r, source)
        self.assertFalse((self.root/"received").exists())

    def test_archive_link_traversal_duplicate_extra_all_rejected(self):
        source = self.manifest({"entry.py": b"a"})
        for kind in ("link", "traversal", "duplicate", "extra"):
            with self.subTest(kind=kind):
                p = self.root/(kind+".tar.gz")
                with tarfile.open(p, "w:gz") as t:
                    m = tarfile.TarInfo("entry.py" if kind == "extra" else
                                        "../escape" if kind == "traversal" else "code/entry.py")
                    if kind == "link":
                        m.type = tarfile.SYMTYPE; m.linkname = "/tmp/escape"; t.addfile(m)
                    else:
                        m.size = 1; t.addfile(m, io.BytesIO(b"a"))
                        if kind == "duplicate": t.addfile(m, io.BytesIO(b"a"))
                expected = {"plaintext_tar_sha256": cp.hashfile(p), "database": {"bytes":0,"sha256":"0"*64}}
                with self.assertRaises(cp.Hold):
                    cp.receive_archive(p, self.root/(kind+"-recv"), expected, source)

class Approval(unittest.TestCase):
    def setUp(self):
        self.value = {"decision":"APPROVED_WITH_EXACT_PRECONDITIONS", "action":launch.ACTION,
                      "max_attempts":1, "source_commit":"a"*40, "binding_sha256":"b"*64,
                      "source_host":launch.SOURCE_HOST,"target_host":launch.HOST,
                      "issued_at":1000,"expires_at":2000}
        self.args = argparse.Namespace(approval_id=7, source_commit="a"*40,
                                      binding_sha256="b"*64,confirm_independent_auditor=True)

    def record(self):
        body = "<!-- PR99_CURRENT_POINT_APPROVAL_V1\n"+json.dumps(self.value)+"\nPR99_CURRENT_POINT_APPROVAL_V1 -->"
        self.args.approval_sha256 = launch.digest(body.encode())
        return {"id":7,"issue_url":"https://api.github.com/repos/"+launch.REPO+"/issues/99",
                "body":body,"user":{"id":332398908,"login":"huhongchuan0422-creator","type":"User"}}

    def test_valid_exact_approval(self):
        self.assertEqual(launch.verify_approval(self.record(),self.args,1500),self.value)

    def test_forged_author_id_login_type_and_missing_root_confirmation(self):
        for key,value in (("id",1),("login","attacker"),("type","Bot")):
            r = self.record(); r["user"][key]=value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                launch.verify_approval(r,self.args,1500)
        r = self.record(); self.args.confirm_independent_auditor=False
        with self.assertRaises(RuntimeError): launch.verify_approval(r,self.args,1500)

    def test_wrong_old_commit_artifact_action_host_or_count_rejected(self):
        for key,value in (("source_commit","c"*40),("binding_sha256","d"*64),
                          ("action","PR99_OLD_INSTALL"),("max_attempts",2),
                          ("source_host","other"),("target_host","other")):
            old=self.value[key]; self.value[key]=value
            r=self.record()
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                launch.verify_approval(r,self.args,1500)
            self.value[key]=old

    def test_expired_future_and_overlong_permits_rejected(self):
        r=self.record()
        for now in (999,2000,2001):
            with self.assertRaises(RuntimeError): launch.verify_approval(r,self.args,now)
        self.value["expires_at"]=100000
        with self.assertRaises(RuntimeError): launch.verify_approval(self.record(),self.args,1500)

    def test_body_edit_wrong_id_and_wrong_pr_rejected(self):
        for key,value in (("body","edited"),("id",8),("issue_url","https://api.github.com/repos/x/y/issues/99")):
            r=self.record(); r[key]=value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                launch.verify_approval(r,self.args,1500)

if __name__ == "__main__":
    unittest.main()
