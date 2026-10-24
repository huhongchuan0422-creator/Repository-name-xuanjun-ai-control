"""Fixed job read scope and original observer release, without service actions."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE=Path(__file__).parent.resolve()
sys.path[:0]=[str(HERE/'reused-6825'),str(HERE/'new19-source')]
from pr17_c53_r2_local_adapter import ProtectedReads
from pr17_b5_deployment_composition import OriginalComposition
from production.cloud_connection.queue import Queue
from production.cloud_connection.oauth_resource import OAuthProjectResource
import pr17_c53_r2_review_transaction as c53

JOB='/opt/xuanjun-cloud-connection/l2-c53-recovery-once'

class ScopeTests(unittest.TestCase):
    def test_only_current_fixed_job_journal_is_readable(self):
        class Legacy:
            def read(self,path):return b'{}',(7,8)
        def private(path,limit,contents=True):
            self.assertEqual(limit,262144)
            return b'{}' if contents else (7,8)
        ids=tuple('new-%02d'%i for i in range(19))
        reader=ProtectedReads(Legacy(),private,JOB,ids)
        for path in (JOB+'/reservation.json',JOB+'/window-open.json',
                     JOB+'/checkpoint-001.json',JOB+'/checkpoint-064.json',
                     JOB+'/intake-new-00.intent.json',
                     JOB+'/intake-new-18.sent.json',c53.CONFIGS[0]):
            self.assertEqual(reader.read(path)[0],b'{}')
        for path in (JOB+'/checkpoint-065.json',
                     JOB+'/intake-other.intent.json',
                     JOB+'/intake-new-00.result.json',
                     '/tmp/reservation.json',JOB+'/../other/reservation.json'):
            with self.assertRaisesRegex(Exception,'ADAPTER_READ_SCOPE'):
                reader.read(path)

    def make_observer(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        queue=Queue(os.path.join(temp.name,'queue.sqlite'),'b'*64,[332398908])
        self.addCleanup(lambda:queue.db.close())
        resource=object.__new__(OAuthProjectResource);resource.db=queue.db
        original=object.__new__(OriginalComposition)
        original.queue,original.resource=queue,resource
        original.runtime_phase='observe'
        return original,queue

    def test_closeout_releases_owned_observer_before_new_fd(self):
        original,queue=self.make_observer()
        self.assertTrue(original.release_observer_for_closeout())
        self.assertIsNone(original.queue)
        self.assertIsNone(original.resource)
        self.assertEqual(original.runtime_phase,'closeout_detached')
        with self.assertRaises(sqlite3.ProgrammingError):
            queue.db.execute('SELECT 1')

    def test_failed_close_is_unknown_and_detached(self):
        original,queue=self.make_observer()
        with mock.patch.object(Queue,'close',side_effect=OSError('close failed')):
            with self.assertRaisesRegex(Exception,'CLOSEOUT_OBSERVER_CLOSE_UNKNOWN'):
                original.release_observer_for_closeout()
        self.assertEqual(original.runtime_phase,'uncertain')
        self.assertIsNone(original.queue)
        with self.assertRaises(sqlite3.ProgrammingError):
            queue.db.execute('SELECT 1')

    def test_custody_phase_cannot_claim_observer_release(self):
        original,queue=self.make_observer()
        original.runtime_phase='custody'
        with self.assertRaisesRegex(Exception,'CLOSEOUT_OBSERVER_PHASE_UNKNOWN'):
            original.release_observer_for_closeout()
        self.assertIs(original.queue,queue)

if __name__=='__main__':unittest.main()
