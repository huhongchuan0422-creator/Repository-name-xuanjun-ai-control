"""Ordinary real queues/threads/held fd; business API and source authority fixtures."""
import gc
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest

import ingress_gate as g
import wecom_queue_binding as w


class ObservedShapeFixture:
    def __init__(self):
        self.jobs=queue.Queue(8);self.effects=[];self.fail=False;self.entered=None;self.release=None
    def accept_callback(self,job):
        self.jobs.put_nowait(job)
        if self.entered is not None:
            self.entered.set();self.release.wait(4)
        self.effects.append('callback-audit')
        return 'accepted'
    def worker_once(self,job=None):
        job=job or self.jobs.get(timeout=1)
        self.effects.append(job['id'])
        if self.fail:raise TimeoutError('fixture result unknown')
        return 'processed'


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();path=Path(self.temp.name)/'original-seal'
        self.fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        now=int(time.time());b={'schema':1,'source_host':os.uname().nodename,
          'transaction_id':'ordinary-adapter-fixture','plan_digest':'a'*64,'inventory_sha256':'b'*64,
          'epoch':7,'origin':'original-wecom-fixture','issued_at':now-1,'expires_at':now+1000}
        self.gate=g.ApplicationIngressGate(b,self.fd,lambda *a:True,lambda:True,lambda *a:True,'c'*64,8)
        self.app=ObservedShapeFixture();self.source_ok=True;self.startup_ok=True
    def tearDown(self):
        self.app=None;self.binding=None;self.gate=None;gc.collect();os.close(self.fd);self.temp.cleanup()
    def attach(self):
        self.binding=w.WeComQueueBinding(self.app,self.gate,
          lambda app,pin:self.source_ok and pin==w.SOURCE_SHA256,
          lambda app:self.startup_ok,lambda job:'callback-'+job['id'],lambda job:'queue-'+job['id'])
        return self.binding
    def test_real_queue_is_acknowledged_after_original_worker(self):
        self.attach();self.assertEqual(self.app.accept_callback({'id':'one'}),'accepted')
        self.assertEqual(self.gate.query()['pending'],1)
        self.assertEqual(self.app.worker_once(),'processed')
        self.assertEqual(self.gate.jobs.unfinished_tasks,0)
        self.assertEqual(self.app.effects,['callback-audit','one'])
    def test_seal_finishes_accepted_job_and_rejects_new_callback(self):
        self.attach();self.app.accept_callback({'id':'one'});self.assertEqual(self.gate.seal()['status'],'WAITING')
        with self.assertRaises(g.IngressHold):self.app.accept_callback({'id':'two'})
        self.app.worker_once();self.assertEqual(self.gate.query()['status'],'DRAINED')
        self.assertNotIn('two',self.app.effects)
    def test_callback_audit_after_enqueue_is_still_inflight(self):
        self.attach();self.app.entered=threading.Event();self.app.release=threading.Event();errors=[]
        def invoke():
            try:self.app.accept_callback({'id':'one'})
            except BaseException as error:errors.append(type(error).__name__)
        thread=threading.Thread(target=invoke);thread.start();self.assertTrue(self.app.entered.wait(2))
        try:
            self.app.worker_once();state=self.gate.seal()
            self.assertEqual(state['status'],'WAITING');self.assertEqual(state['pending'],1)
        finally:self.app.release.set();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(self.gate.query()['status'],'DRAINED')
    def test_unknown_worker_result_is_not_replayed(self):
        self.attach();self.app.accept_callback({'id':'one'});self.app.fail=True
        with self.assertRaises(TimeoutError):self.app.worker_once()
        self.assertEqual(self.gate.seal()['status'],'UNKNOWN')
        with self.assertRaises(queue.Empty):self.app.worker_once()
        self.assertEqual(self.app.effects.count('one'),1)
        self.gate.reconcile_unknown('queue-one',lambda *a:{'outcome':'COMMITTED','proof_sha256':'d'*64})
        self.assertEqual(self.gate.query()['status'],'DRAINED')
    def test_direct_job_bypass_rejected(self):
        self.attach()
        with self.assertRaises(w.QueueBindingHold):self.app.worker_once(job={'id':'bypass'})
        self.assertEqual(self.app.effects,[])
    def test_original_nonempty_queue_is_not_replaced(self):
        old=self.app.jobs;old.put_nowait({'id':'existing'})
        with self.assertRaises(w.QueueBindingHold):self.attach()
        self.assertIs(self.app.jobs,old);self.assertEqual(old.get_nowait(),{'id':'existing'})
    def test_unfinished_original_work_preserved(self):
        old=self.app.jobs;old.put_nowait({'id':'active'});old.get_nowait()
        with self.assertRaises(w.QueueBindingHold):self.attach()
        self.assertIs(self.app.jobs,old);self.assertEqual(old.unfinished_tasks,1)
    def test_existing_gate_ticket_is_not_abandoned(self):
        self.gate.submit('prior',{'id':'prior'});old=self.app.jobs
        with self.assertRaises(w.QueueBindingHold):self.attach()
        self.assertIs(self.app.jobs,old);self.assertEqual(self.gate.query()['pending'],1)
    def test_second_binding_rejected_without_replacing_first(self):
        first=self.attach()
        with self.assertRaises(w.QueueBindingHold):self.attach()
        self.assertIs(vars(self.app)['_pr99_queue_binding'],first)
    def test_nonexclusive_startup_does_not_change_original(self):
        self.startup_ok=False;old=self.app.jobs
        with self.assertRaises(w.QueueBindingHold):self.attach()
        self.assertIs(self.app.jobs,old)
    def test_withdrawn_original_binding_cannot_run_original_worker(self):
        self.attach();self.app.accept_callback({'id':'one'});self.source_ok=False
        with self.assertRaises(w.QueueBindingHold):self.app.worker_once()
        self.assertNotIn('one',self.app.effects)
        self.assertEqual(self.gate.query()['pending'],1)
    def test_changed_application_binding_is_held(self):
        self.attach();self.app.jobs=queue.Queue()
        with self.assertRaises(w.QueueBindingHold):self.binding.query()
    def test_legacy_queue_get_cannot_bypass_worker_accounting(self):
        self.attach()
        with self.assertRaises(w.QueueBindingHold):self.app.jobs.get()
        with self.assertRaises(w.QueueBindingHold):self.app.jobs.get_nowait()
        self.assertEqual(self.gate.query()['pending'],0)
    def test_instance_replacement_by_verifier_cannot_run_worker(self):
        self.attach();self.app.accept_callback({'id':'one'})
        def verify(*args):self.app.jobs=queue.Queue();return True
        self.binding.verify=verify
        with self.assertRaises(w.QueueBindingHold):self.app.worker_once()
        self.assertNotIn('one',self.app.effects)


if __name__=='__main__':unittest.main()
