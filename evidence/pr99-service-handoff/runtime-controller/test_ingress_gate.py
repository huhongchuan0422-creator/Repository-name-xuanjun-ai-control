"""Real ordinary queue/thread/fd tests; not installed apps/M99/admission."""
import copy
import gc
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import ingress_gate as g


class IngressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'original-seal-fd'
        self.fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        now=int(time.time());self.binding={'schema':1,'source_host':os.uname().nodename,
          'transaction_id':'ordinary-fixture','plan_digest':'a'*64,'inventory_sha256':'b'*64,
          'epoch':7,'origin':'fixture-application','issued_at':now-1,'expires_at':now+1000}
        self.admitted=True;self.boot=True
        self.gate=self.build()

    def build(self):
        return g.ApplicationIngressGate(self.binding,self.fd,lambda mode,b,r:self.admitted,
             lambda:True,lambda b,r,h:self.boot,'c'*64,4)

    def tearDown(self):
        self.gate=None;gc.collect();os.close(self.fd);self.temp.cleanup()

    def test_seal_rejects_new_jobs_but_finishes_accepted_queue(self):
        self.gate.submit('job', 'accepted');self.assertEqual(self.gate.seal()['status'],'WAITING')
        with self.assertRaises(g.IngressHold):self.gate.submit('job', 'late')
        seen=[];self.gate.process_one(lambda item:seen.append(item))
        self.assertEqual(seen,['accepted']);self.assertEqual(self.gate.query()['status'],'DRAINED')

    def test_active_synchronous_write_must_finish_before_drain(self):
        entered=threading.Event();release=threading.Event();errors=[]
        def work():entered.set();release.wait(5)
        def run():
            try:self.gate.run_sync('sync',work)
            except BaseException as e:errors.append(type(e).__name__)
        thread=threading.Thread(target=run);thread.start();self.assertTrue(entered.wait(2))
        try:
            self.assertEqual(self.gate.seal()['pending'],1)
            self.assertEqual(self.gate.wait_drained(0)['status'],'WAITING')
        finally:release.set();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(self.gate.query()['status'],'DRAINED')

    def test_concurrent_seal_and_submit_cannot_accept_after_seal_returns(self):
        self.gate.seal();accepted=[];rejected=[]
        def put():
            try:self.gate.submit('job', 'never');accepted.append(True)
            except g.IngressHold:rejected.append(True)
        threads=[threading.Thread(target=put) for _ in range(8)]
        for t in threads:t.start()
        for t in threads:t.join(3)
        self.assertEqual(accepted,[]);self.assertEqual(len(rejected),8)
        self.assertEqual(self.gate.query()['status'],'DRAINED')

    def test_queued_exception_is_unknown_and_not_retried(self):
        token=self.gate.submit('job', 'payload');self.gate.seal();calls=[]
        def fail(item):calls.append(item);raise TimeoutError('original-result-unknown')
        with self.assertRaises(TimeoutError):self.gate.process_one(fail)
        self.assertEqual(self.gate.wait_drained(0)['status'],'UNKNOWN')
        with self.assertRaises(queue.Empty):self.gate.process_one(fail)
        self.assertEqual(calls,['payload'])
        with self.assertRaises(g.IngressHold):self.gate.reconcile_unknown(token,lambda *a:None)
        value=self.gate.reconcile_unknown(token,lambda *a:{'outcome':'COMMITTED','proof_sha256':'d'*64})
        self.assertEqual(value['status'],'DRAINED');self.assertEqual(calls,['payload'])

    def test_sync_exception_requires_original_terminal_accounting(self):
        with self.assertRaises(OSError):self.gate.run_sync('sync',lambda:(_ for _ in ()).throw(OSError()))
        self.gate.seal();self.assertEqual(self.gate.query()['unknown'],1)
        token=next(iter(self.gate.tickets))
        with self.assertRaises(g.IngressHold):
            self.gate.reconcile_unknown(token,lambda *a:{'outcome':'UNKNOWN','proof_sha256':'d'*64})
        self.assertEqual(self.gate.reconcile_unknown(token,lambda *a:{'outcome':'ABORTED_WITH_NO_EFFECT','proof_sha256':'d'*64})['status'],'DRAINED')

    def test_recreated_object_same_pid_is_not_an_empty_success(self):
        self.gate.submit('job', 'lost-after-crash');self.gate.seal();raw=os.pread(self.fd,16385,0)
        self.gate=None;gc.collect();self.gate=self.build()
        self.assertEqual(self.gate.query()['status'],'UNKNOWN_PRIOR_PROCESS')
        self.assertIsNone(self.gate.query()['pending'])
        with self.assertRaises(g.IngressHold):self.gate.submit('job', 'replay')
        self.assertEqual(os.pread(self.fd,16385,0),raw)

    def test_second_live_instance_cannot_borrow_same_original_fd(self):
        with self.assertRaises(g.IngressHold):self.build()

    def test_other_process_cannot_take_borrowed_original_seal_fd(self):
        code='import os,fcntl,sys\nf=os.open(sys.argv[1],os.O_RDWR)\ntry:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError:sys.exit(0)\nsys.exit(1)'
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(self.path)],capture_output=True)
        self.assertEqual(result.returncode,0)

    def test_real_new_process_preserves_seal_and_reports_unknown(self):
        self.gate.submit('job', 'not-replayed');self.gate.seal();raw=os.pread(self.fd,16385,0)
        self.gate=None;gc.collect();os.close(self.fd)
        code='''import sys,os,json
sys.path.insert(0,sys.argv[1])
import ingress_gate as g
fd=os.open(sys.argv[2],os.O_RDWR)
gate=g.ApplicationIngressGate(json.loads(sys.argv[3]),fd,lambda *a:True,lambda:True,lambda *a:True,'c'*64)
print(gate.query()['status'])
os.close(fd)
'''
        try:
            result=subprocess.run([sys.executable,'-I','-B','-c',code,str(Path(g.__file__).parent),
                 str(self.path),json.dumps(self.binding)],capture_output=True,text=True)
        finally:self.fd=os.open(self.path,os.O_RDWR)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'UNKNOWN_PRIOR_PROCESS')
        self.assertEqual(os.pread(self.fd,16385,0),raw)

    def test_partial_seal_is_closed_and_preserved(self):
        os.pwrite(self.fd,b'{',0)
        with self.assertRaises(g.IngressHold):self.gate.query()
        with self.assertRaises(g.IngressHold):self.gate.submit('job', 'late')
        self.assertEqual(os.pread(self.fd,100,0),b'{')

    def test_short_seal_write_cannot_reopen_or_retry(self):
        pwrite=os.pwrite
        def partial(fd,raw,offset):return pwrite(fd,raw[:7],offset)
        with patch.object(g.os,'pwrite',side_effect=partial):
            with self.assertRaises(g.IngressHold):self.gate.seal()
        raw=os.pread(self.fd,16385,0)
        with self.assertRaises(g.IngressHold):self.gate.seal()
        with self.assertRaises(g.IngressHold):self.gate.submit('job', 'late')
        self.assertEqual(os.pread(self.fd,16385,0),raw)

    def test_missing_bootstrap_cannot_certify_even_empty_queue(self):
        self.boot=False
        with self.assertRaises(g.IngressHold):self.gate.seal()
        self.assertEqual(os.fstat(self.fd).st_size,0)

    def test_removed_or_foreign_seal_is_not_overwritten(self):
        self.gate.seal();raw=os.pread(self.fd,16385,0)
        other=json.loads(raw);other['binding']['epoch']=8
        os.ftruncate(self.fd,0);os.pwrite(self.fd,g.encode(other),0)
        with self.assertRaises(g.IngressHold):self.gate.query()
        self.assertNotEqual(os.pread(self.fd,16385,0),raw)

    def test_untracked_external_queue_injection_is_held(self):
        self.gate.jobs.put_nowait(('untracked','hidden'))
        with self.assertRaises(g.IngressHold):self.gate.seal()

    def test_withdrawn_admission_has_no_seal_write(self):
        self.admitted=False
        with self.assertRaises(g.IngressHold):self.gate.seal()
        self.assertEqual(os.fstat(self.fd).st_size,0)

    def test_grant_lost_after_sync_handler_keeps_unknown_outcome(self):
        def work():self.admitted=False
        with self.assertRaises(g.IngressHold):self.gate.run_sync('sync',work)
        self.admitted=True;self.gate.seal()
        self.assertEqual(self.gate.query()['status'],'UNKNOWN')

    def test_grant_lost_after_queued_handler_keeps_unknown_without_replay(self):
        self.gate.submit('job', 'accepted');self.gate.seal()
        def work(item):self.admitted=False
        with self.assertRaises(g.IngressHold):self.gate.process_one(work)
        self.admitted=True
        self.assertEqual(self.gate.query()['status'],'UNKNOWN')
        with self.assertRaises(queue.Empty):self.gate.process_one(work)

    def test_forked_or_changed_process_cannot_use_parent_gate(self):
        foreign={**self.gate.process,'pid':self.gate.process['pid']+1}
        with patch.object(g,'runtime_identity',return_value=foreign):
            with self.assertRaises(g.IngressHold):self.gate.submit('job', 'late')
            with self.assertRaises(g.IngressHold):self.gate.seal()
        self.assertEqual(os.fstat(self.fd).st_size,0)

    def test_capacity_is_bounded_without_losing_accepted_work(self):
        for i in range(4):self.gate.submit('job'+str(i), 'accepted')
        with self.assertRaises(g.IngressHold):self.gate.submit('job', 'overflow')
        self.assertEqual(self.gate.seal()['pending'],4)

    def test_wait_is_bounded(self):
        self.gate.submit('job', 'accepted');self.gate.seal()
        for value in (-1,61,True):
            with self.assertRaises(g.IngressHold):self.gate.wait_drained(value)
        self.assertEqual(self.gate.wait_drained(0)['status'],'WAITING')

    def test_original_job_id_maps_unknown_and_rejects_duplicate_completed_job(self):
        self.assertEqual(self.gate.submit('known-original-job','payload'),'known-original-job')
        with self.assertRaises(g.IngressHold):self.gate.submit('known-original-job','duplicate')
        seen=[];self.gate.process_one(lambda item:seen.append(item))
        with self.assertRaises(g.IngressHold):self.gate.submit('known-original-job','replay')
        self.assertEqual(seen,['payload'])


if __name__=='__main__':unittest.main()
