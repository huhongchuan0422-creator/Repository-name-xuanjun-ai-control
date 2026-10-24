"""Fixed IO boundary tests; no host mutation or systemctl execution."""
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT),str(ROOT/'reused-6825'),str(ROOT/'new19-source'),
                str(ROOT/'successor_controller')]
from pr17_b5_successor_fixed_io import FixedR2IO
import pr17_b5_successor_review as c53


class FixedIOTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((ROOT/'SUCCESSOR_SPEC.json').read_bytes())
        self.io=FixedR2IO(self.spec)

    def test_exact_journal_and_runtime_paths(self):
        job=self.io.job
        self.assertEqual(self.io._path(job+'/reservation.json'),
                         job+'/reservation.json')
        self.assertEqual(self.io._path(job+'/checkpoint-001.json'),
                         job+'/checkpoint-001.json')
        rid=next(iter(self.io.ids))
        self.assertEqual(self.io._path(job+'/intake-'+rid+'.intent.json'),
                         job+'/intake-'+rid+'.intent.json')
        name=next(iter(self.io.runtime_files))
        self.assertEqual(self.io._path(self.io.stage[0]+'/'+name),
                         self.io.stage[0]+'/'+name)

    def test_arbitrary_child_and_command_rejected_without_side_effect(self):
        for path in (self.io.job+'/arbitrary',
                     self.io.job+'/checkpoint-9999.json',
                     self.io.stage[0]+'/etc/passwd',
                     self.io.target[0]+'/arbitrary',
                     self.io.job+'/../other'):
            with self.subTest(path=path),self.assertRaises(c53.Hold):
                self.io._path(path)
        for argv in (['/bin/sh','-c','true'],
                     ['/usr/bin/systemctl','restart','unrelated.service']):
            with self.subTest(argv=argv),self.assertRaisesRegex(
                    c53.Hold,'FIXED_IO_COMMAND_SCOPE'):
                self.io.command(argv,1)
        with self.assertRaisesRegex(c53.Hold,'FIXED_IO_WRITE_SCOPE'):
            self.io.newfile(self.io.job+'/reservation.json',b'{}',0o644)
        with self.assertRaisesRegex(c53.Hold,'FIXED_IO_DIR_MODE'):
            self.io.mkdir(self.io.job,0o755)

    def test_exact_restore_paths_and_resource_stop_observation(self):
        for name in c53.CONFIGS+c53.SLOTS:
            self.assertEqual(self.io._path(name+'.l2-b5-staged-'+c53.COMMIT[:12]+'-restore'),
                             name+'.l2-b5-staged-'+c53.COMMIT[:12]+'-restore')
        for base in c53.BASES:
            name=base+'/current.l2-b5-staged-'+c53.COMMIT[:12]+'-restore'
            self.assertEqual(self.io._path(name),name)
        with patch('pr17_b5_successor_fixed_io.subprocess.run') as run:
            run.return_value.returncode=3
            self.assertEqual(self.io.command(['/usr/bin/systemctl','is-active','--quiet',
                'xuanjun-cloud-oauth-resource.service'],10,(3,)),3)
            self.assertEqual(run.call_count,1)

    def test_database_same_inode_growth_and_replacement(self):
        # A real SQLite header and file-backed page growth; no production DB.
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'queue.sqlite'
            db=sqlite3.connect(str(path));db.execute('CREATE TABLE t(x BLOB)');db.commit();db.close()
            path.chmod(0o600)
            original=path.stat()
            self.io.spec['observed_baseline']['db'].update(
                dev=original.st_dev,ino=original.st_ino,bytes=original.st_size)
            with patch.object(self.io,'state_directory',return_value=os.open(temp,os.O_RDONLY|os.O_DIRECTORY)):
                with patch.object(self.io,'database_identity',side_effect=lambda st:
                                  self.assertEqual((st.st_dev,st.st_ino),(original.st_dev,original.st_ino))):
                    self.io.check_original_database()
            db=sqlite3.connect(str(path));db.execute('INSERT INTO t VALUES (?)',(b'x'*100000,));db.commit();db.close()
            self.assertGreater(path.stat().st_size,original.st_size)
            with patch.object(self.io,'state_directory',return_value=os.open(temp,os.O_RDONLY|os.O_DIRECTORY)):
                with patch.object(self.io,'database_identity',side_effect=lambda st:
                                  self.assertEqual((st.st_dev,st.st_ino),(original.st_dev,original.st_ino))):
                    self.io.check_original_database()
            path.rename(Path(temp)/'old.sqlite')
            db=sqlite3.connect(str(path));db.execute('CREATE TABLE t(x)');db.close()
            with patch.object(self.io,'state_directory',return_value=os.open(temp,os.O_RDONLY|os.O_DIRECTORY)):
                with self.assertRaises(AssertionError):
                    with patch.object(self.io,'database_identity',side_effect=lambda st:
                                      self.assertEqual((st.st_dev,st.st_ino),(original.st_dev,original.st_ino))):
                        self.io.check_original_database()

    def test_stability_observes_elapsed_time_without_restart(self):
        calls=[]
        with patch.object(self.io,'command',side_effect=lambda argv,timeout: calls.append(tuple(argv))):
            self.assertTrue(self.io.stable_unit('xuanjun-cloud-connection.service'))
        self.assertGreaterEqual(len(calls),2)
        self.assertTrue(all(x[1:3]==('is-active','--quiet') for x in calls))

    def test_resource_readiness_has_total_deadline(self):
        from pr17_b5_successor_fixed_io import signal
        from production.cloud_connection import oauth_entrypoint
        config={'enabled':True,'hostname':c53.HOST,
                'settings':{'issuer':'issuer','audience':'audience'}}
        class SlowHTTP:
            def __init__(self,*args,**kwargs):pass
            def request(self,*args,**kwargs):time.sleep(4)
            def close(self):pass
        previous=signal.getsignal(signal.SIGALRM)
        with patch.object(oauth_entrypoint,'private_bytes',return_value=json.dumps(config).encode()):
            with patch('pr17_b5_successor_fixed_io.http.client.HTTPConnection',SlowHTTP):
                start=time.monotonic()
                with self.assertRaisesRegex(c53.Hold,'FIXED_IO_RESOURCE_DEADLINE'):
                    self.io.resource_ready()
                self.assertLess(time.monotonic()-start,3.8)
        self.assertEqual(signal.getsignal(signal.SIGALRM),previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))


if __name__ == '__main__':
    unittest.main()
