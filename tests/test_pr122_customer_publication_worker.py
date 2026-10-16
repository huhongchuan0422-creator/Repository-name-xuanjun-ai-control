import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from tests.test_pr122_customer_preview import PreviewTests
from tests.test_pr122_customer_center import CustomerTests
from scripts.pr122_customer_publication_worker import enqueue,drain
from scripts.pr122_customer_core import Denied

class PublicationTests(unittest.TestCase):
    imported=CustomerTests.imported
    install=PreviewTests.install
    publication=PreviewTests.publication
    def setUp(self):PreviewTests.setUp(self)
    def queue(self,r,receipt,report):
        with patch('socket.socket',side_effect=OSError('socket absent fixture')):return enqueue(self.c,self.reviewer,'project-a',r['id'],receipt['id'],report)
    def test_queue_worker_publishes_valid_report_without_manual_step(self):
        r,receipt,report,trust,_=self.publication();q=self.queue(r,receipt,report)
        with patch('socket.socket',side_effect=AssertionError('no network')):result=drain(self.c,trust,self.auth)
        self.assertEqual(result['done'],1);self.assertEqual(result['model_api_calls'],0)
        self.assertEqual(self.c.db.execute('SELECT state FROM preview_publication_jobs WHERE id=?',(q['id'],)).fetchone()[0],'DONE')
    def test_invalid_signature_is_held_without_delivery_or_retry(self):
        r,receipt,report,trust,_=self.publication();report['payload']['summary']='tampered';q=self.queue(r,receipt,report)
        self.assertEqual(drain(self.c,trust,self.auth)['held'],1);self.assertEqual(drain(self.c,trust,self.auth)['done'],0)
        self.assertEqual(self.c.db.execute('SELECT state FROM preview_publication_jobs WHERE id=?',(q['id'],)).fetchone()[0],'HOLD_UNKNOWN')
    def test_owner_cannot_submit_test_report_and_duplicates_are_one_job(self):
        r,receipt,report,trust,_=self.publication()
        with self.assertRaises(Denied):enqueue(self.c,self.owner,'project-a',r['id'],receipt['id'],report)
        first=self.queue(r,receipt,report);second=self.queue(r,receipt,report);self.assertEqual(first['id'],second['id']);self.assertEqual(self.c.db.execute('SELECT COUNT(*) FROM preview_publication_jobs').fetchone()[0],1)
    def test_interrupted_processing_is_not_retried_automatically(self):
        r,receipt,report,trust,_=self.publication();q=self.queue(r,receipt,report);self.c.db.execute("UPDATE preview_publication_jobs SET state='PROCESSING' WHERE id=?",(q['id'],))
        self.assertEqual(drain(self.c,trust,self.auth),{'done':0,'held':0,'unknown':1,'model_api_calls':0,'automatic_retry':False})
    def test_revoked_reviewer_report_cannot_publish(self):
        r,receipt,report,trust,_=self.publication();self.queue(r,receipt,report)
        p={**self.p,'reviewer_emails':[]};self.imported(2,[p])
        self.assertEqual(drain(self.c,trust,self.auth)['held'],1)
    def test_two_reports_survive_global_source_revision_without_overwriting(self):
        import base64,copy
        from scripts.pr122_customer_changes import Changes
        service=Changes(self.c);b=service.submit(self.owner,'project-a',self.path,self.sha,'同时调整标题颜色');service.assess(self.reviewer,'project-a',b['id'],1,'IN_SCOPE_SMALL',10,[],[],'同一页面小改')
        a,receipt,report,trust,private=self.publication();second=copy.deepcopy(report);second['payload']['case']=b['id'];second['payload']['request_sha256']=service._request_sha(service._events(self.owner,'project-a',b['id']));second['signature']=base64.b64encode(private.sign(__import__('scripts.pr122_customer_core',fromlist=['canonical']).canonical(second['payload']))).decode()
        self.queue(a,receipt,report);self.queue(b,receipt,second);result=drain(self.c,trust,self.auth)
        self.assertEqual(result['done'],2);self.assertEqual(result['held'],0)
        self.assertEqual(len(service.page_updates(self.owner,'project-a',self.path,self.sha)['updates']),2)
    def test_completed_job_duplicate_returns_done_and_status_is_role_bound(self):
        from scripts.pr122_customer_publication_worker import status
        r,receipt,report,trust,_=self.publication();q=self.queue(r,receipt,report);drain(self.c,trust,self.auth)
        self.assertEqual(self.queue(r,receipt,report)['state'],'DONE')
        self.assertEqual(status(self.c,self.reviewer,'project-a',q['id'])['state'],'DONE')
        with self.assertRaises(Denied):status(self.c,self.owner,'project-a',q['id'])
        with self.assertRaises(Denied):status(self.c,self.other,'project-a',q['id'])
    def test_effective_nondumpable_after_uid_drop_in_disposable_child(self):
        self.assertEqual(os.geteuid(),0,'Hosted root fixture only')
        code='from scripts.pr122_customer_publication_worker import nondumpable;import os;os.setgroups([]);os.setgid(65534);os.setuid(65534);nondumpable();print("NONDUMPABLE_AFTER_DROP=PASS")'
        r=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertIn('NONDUMPABLE_AFTER_DROP=PASS',r.stdout)
