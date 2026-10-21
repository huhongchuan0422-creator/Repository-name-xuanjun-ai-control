import calendar
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from production.cloud_connection.queue import Hold, Queue
from production.cloud_connection.runtime import Loop
from production.cloud_connection.credential_lifecycle import evaluate, record_on_existing_queue, utc


class CredentialLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/root')
        self.path=str(Path(self.tmp.name)/'queue.sqlite')
        self.q=Queue(self.path,'a'*64,{332398908})
        Loop(self.q,None,None,None)  # Original schema/outbox, no new scheduler.
        self.v={'schema':1,'credential_ref':'openai-tunnel-runtime','generation':'generation-1',
                'expiry_date':'2026-11-20','expires_at_utc':None,
                'verified_at_utc':'2026-10-21T16:00:00Z','source_ref':'original-platform-receipt'}
    def tearDown(self): self.q.close(); self.tmp.cleanup()
    def raw(self): return json.dumps(self.v,sort_keys=True).encode()
    def run_watch(self,now):
        raw=self.raw(); return record_on_existing_queue(self.q.db,raw,hashlib.sha256(raw).hexdigest(),utc(now))
    def test_date_only_does_not_invent_provider_utc(self):
        v=self.run_watch('2026-10-22T00:00:00Z')
        self.assertEqual(v['precision'],'DATE_ONLY_CONSERVATIVE_STOP')
        self.assertEqual(v['conservative_stop_unix'],utc('2026-11-19T00:00:00Z'))
        self.assertEqual(v['automatic_rotation'],'NOT_IMPLEMENTED')
    def test_exact_expiry(self):
        self.v['expires_at_utc']='2026-11-20T16:00:00Z'
        self.assertEqual(self.run_watch('2026-11-20T15:00:00Z')['state'],'WARN_1_DAY')
    def test_thresholds_and_stop(self):
        for when,expected in [('2026-10-22T00:00:00Z','TRACKED_NOT_DUE'),
                              ('2026-11-05T00:00:00Z','WARN_14_DAYS'),
                              ('2026-11-12T00:00:00Z','WARN_7_DAYS'),
                              ('2026-11-16T00:00:00Z','WARN_3_DAYS'),
                              ('2026-11-18T00:00:00Z','WARN_1_DAY'),
                              ('2026-11-19T00:00:00Z','STOP_EXPIRED_OR_CONSERVATIVE_BOUND')]:
            self.assertEqual(self.run_watch(when)['state'],expected)
    def test_same_threshold_is_deduplicated_after_reopen(self):
        self.run_watch('2026-11-12T00:00:00Z')
        other=sqlite3.connect(self.path,isolation_level=None,timeout=0)
        try:
            raw=self.raw(); record_on_existing_queue(other,raw,hashlib.sha256(raw).hexdigest(),utc('2026-11-12T01:00:00Z'))
        finally: other.close()
        self.assertEqual(self.q.db.execute('SELECT COUNT(*) FROM connection_outbox').fetchone()[0],1)
    def test_unknown_notification_is_not_replayed(self):
        self.run_watch('2026-11-12T00:00:00Z')
        self.q.db.execute("UPDATE connection_outbox SET state='UNKNOWN'")
        self.run_watch('2026-11-12T01:00:00Z')
        self.assertEqual(self.q.db.execute('SELECT state FROM connection_outbox').fetchall(),[('UNKNOWN',)])
    def test_generation_cannot_rebind_metadata(self):
        self.run_watch('2026-11-12T00:00:00Z'); self.v['expiry_date']='2026-12-20'
        with self.assertRaisesRegex(Hold,'REBOUND'): self.run_watch('2026-11-12T01:00:00Z')
    def test_new_authorized_generation_keeps_old_history(self):
        self.run_watch('2026-11-12T00:00:00Z'); self.v['generation']='generation-2'
        self.run_watch('2026-11-12T01:00:00Z')
        self.assertEqual(self.q.db.execute('SELECT COUNT(*) FROM connection_credential_watch').fetchone()[0],2)
    def test_clock_backwards_holds(self):
        self.run_watch('2026-11-12T01:00:00Z')
        with self.assertRaisesRegex(Hold,'CLOCK'): self.run_watch('2026-11-12T00:00:00Z')
    def test_nested_transaction_untouched(self):
        self.q.db.execute('BEGIN IMMEDIATE')
        with self.assertRaisesRegex(Hold,'TRANSACTION'): self.run_watch('2026-11-12T00:00:00Z')
        self.assertTrue(self.q.db.in_transaction); self.q.db.rollback()
    def test_no_new_database_or_outbox(self):
        db=sqlite3.connect(':memory:',isolation_level=None)
        raw=self.raw()
        try:
            with self.assertRaises(sqlite3.OperationalError): record_on_existing_queue(db,raw,hashlib.sha256(raw).hexdigest(),utc('2026-11-12T00:00:00Z'))
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),[])
        finally: db.close()
    def test_unknown_or_invalid_expiry_holds(self):
        for value in ('never','2026-11-99',None):
            self.v['expiry_date']=value
            with self.assertRaises(Hold): self.run_watch('2026-11-12T00:00:00Z')
    def test_metadata_tamper_and_secret_fields_rejected(self):
        raw=self.raw()
        with self.assertRaises(Hold): evaluate(raw,'0'*64,utc('2026-11-12T00:00:00Z'))
        self.v['api_key']='not-a-real-secret'
        with self.assertRaises(Hold): self.run_watch('2026-11-12T00:00:00Z')
    def test_future_or_stale_observation_rejected(self):
        for when in ('2026-10-20T00:00:00Z','2026-12-20T00:00:00Z'):
            with self.assertRaises(Hold): self.run_watch(when)
    def test_no_warning_post_inside_detector(self):
        self.run_watch('2026-11-12T00:00:00Z')
        body,state,comment=self.q.db.execute('SELECT body,state,comment_id FROM connection_outbox').fetchone()
        self.assertTrue(body.startswith('XJ_CREDENTIAL_EXPIRY_V1\n'))
        self.assertEqual((state,comment),('READY',None))

    def test_watch_history_replace_and_update_blocked(self):
        self.run_watch('2026-11-12T00:00:00Z')
        row=self.q.db.execute('SELECT * FROM connection_credential_watch').fetchone()
        with self.assertRaises(sqlite3.IntegrityError): self.q.db.execute('INSERT OR REPLACE INTO connection_credential_watch VALUES(?,?,?,?)',row)
        with self.assertRaises(sqlite3.IntegrityError): self.q.db.execute("UPDATE connection_credential_watch SET metadata_sha='changed'")
        with self.assertRaises(sqlite3.IntegrityError): self.q.db.execute('DELETE FROM connection_credential_watch')
