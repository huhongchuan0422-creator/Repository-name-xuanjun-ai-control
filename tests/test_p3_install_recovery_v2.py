"""Entry-level RecoveryAdmissionV2 tests; keys and authority are TEST_ONLY."""
import queue
import threading
import time
import unittest
from src.p3_admission_v2 import canonical
from install import p3_carrier_install as installer
from tests import test_p3_carrier_install as fixture

class InstallRecoveryV2Tests(unittest.TestCase):
    def setUp(self):
        fixture.CarrierInstallTests.setUp(self)
        self.now=[1000]
        self.ownership.clock=lambda:self.now[0]
        def install_authority(op,attempt,context):
            value=dict(operation_id=op,attempt_id=attempt,authority_identity='test-authority',
                issued_at=self.now[0]-1,expires_at=self.now[0]+300,key_id='fixture-install',**context)
            value['signature']=self.install_key.sign(b'P3-INSTALL-OWNER-V1\x00'+canonical(value)).hex()
            return value
        self.guard.install_authority_reader=install_authority
    def tearDown(self):fixture.CarrierInstallTests.tearDown(self)
    def proof(self,row,kind='EXPIRED_STALE',issued=None,expires=None):
        now=self.now[0]
        value=dict(operation_id=row['operation_id'],attempt_id=row['attempt_id'],observed_owner_token=row['owner_token'],
            observed_epoch=row['epoch'],observed_fence=row['fence'],observed_lease_expires_at=row['lease_expires_at'],
            observed_heartbeat_seq=row['heartbeat_seq'],observed_heartbeat_at=row['heartbeat_at'],authority_identity='test-authority',
            reason='TEST_ONLY',proof_kind=kind,issued_at=now-1 if issued is None else issued,
            expires_at=now+60 if expires is None else expires,key_id='fixture-recovery')
        value['signature']=self.recovery_key.sign(b'P3-RECOVERY-ADMISSION-V2\x00'+canonical(value)).hex()
        return value
    def stop(self,row):
        value=dict(operation_id=row['operation_id'],attempt_id=row['attempt_id'],owner_token=row['owner_token'],
            epoch=row['epoch'],fence=row['fence'],heartbeat_seq=row['heartbeat_seq'],stopped_at=self.now[0],
            authority_identity='test-authority',key_id='fixture-stop')
        value['signature']=self.stop_key.sign(b'P3-OWNER-STOP-V2\x00'+canonical(value)).hex()
        return value
    def recover(self,proof,stop=None):
        return installer.recover(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
            self.releases,self.state,'install-attempt-01',operation_store=self.store,
            ownership_guard=self.guard,recovery_admission=proof,stop_receipt=stop)
    def paused_owner(self,point):
        entered=threading.Event();release=threading.Event();results=[];renames=[]
        def hook(phase):
            if phase=='after_rename':renames.append(1)
            if phase==point:entered.set();release.wait(30)
        def run():
            try:results.append(installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                operation_store=self.store,archive_path=self.archive,ownership_guard=self.guard,fault_hook=hook))
            except Exception as e:results.append(type(e).__name__+':'+str(e))
        thread=threading.Thread(target=run);thread.start();self.assertTrue(entered.wait(10))
        self.addCleanup(lambda:(release.set(),thread.join(10)))
        return release,thread,results,renames
    def test_active_owner_rejects_100_concurrent_recoveries(self):
        release,thread,results,renames=self.paused_owner('before_rename')
        op='p3-install:install-attempt-01';before=self.store.get(op);proof=self.proof(self.ownership.read(op))
        barrier=threading.Barrier(100);answers=queue.Queue()
        def call():
            try:barrier.wait(20);answers.put(('ok',self.recover(proof)['state']))
            except Exception as e:answers.put(('error',type(e).__name__+':'+str(e)))
        workers=[threading.Thread(target=call) for _ in range(100)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(25)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual([('ok','RECOVERY_OWNER_ACTIVE')]*100,[answers.get_nowait() for _ in range(100)])
        self.assertEqual(before,self.store.get(op));release.set();thread.join(20)
        self.assertEqual('INSTALLED_DEFAULT_OFF_NOT_BOUND',results[0]['state']);self.assertEqual([1],renames)
    def test_heartbeat_advanced_after_observation_rejects_stale_cas(self):
        release,thread,results,renames=self.paused_owner('before_rename')
        op='p3-install:install-attempt-01';observed=self.ownership.read(op)
        old={'owner_token':observed['owner_token'],'epoch':observed['epoch'],'fence':observed['fence']}
        self.now[0]=1010;self.assertTrue(self.ownership.heartbeat(op,old,observed['heartbeat_seq'],60))
        self.now[0]=1200;proof=self.proof(observed);before=self.store.get(op)
        self.assertEqual('RECOVERY_OWNER_ACTIVE',self.recover(proof)['state'])
        self.assertEqual(before,self.store.get(op));release.set();thread.join(20)
        self.assertEqual('OWNER_LOST',results[0]['state']);self.assertEqual([],renames)
    def exercise_takeover(self,kind):
        release,thread,results,renames=self.paused_owner('before_rename')
        op='p3-install:install-attempt-01';old=self.ownership.read(op)
        if kind=='EXPIRED_STALE':self.now[0]=1200
        proof=self.proof(old,kind);stop=self.stop(old) if kind=='STOP_RECEIPT' else None
        outcome=self.recover(proof,stop)
        self.assertEqual('NOT_SWITCHED_HOLD',outcome['state'])
        claimed=self.ownership.read(op);self.assertEqual('RECOVERY_CLAIMED',claimed['state'])
        self.assertEqual(old['epoch']+1,claimed['epoch']);self.assertNotEqual(old['fence'],claimed['fence'])
        after=self.store.get(op);release.set();thread.join(20)
        self.assertEqual('OWNER_LOST',results[0]['state']);self.assertEqual([],renames)
        self.assertEqual(after,self.store.get(op))
    def test_valid_stop_receipt_claims_new_owner_and_fences_old(self):self.exercise_takeover('STOP_RECEIPT')
    def test_expired_stale_claims_new_owner_and_fences_old(self):self.exercise_takeover('EXPIRED_STALE')
    def test_expired_or_tampered_admission_does_not_change_journal(self):
        release,thread,results,renames=self.paused_owner('before_rename')
        op='p3-install:install-attempt-01';row=self.ownership.read(op);before=self.store.get(op)
        proof=self.proof(row,'STOP_RECEIPT');stop=self.stop(row)
        invalid=(dict(proof,signature='0'*128),self.proof(row,'STOP_RECEIPT',issued=900,expires=999))
        for item in invalid:
            self.assertEqual('RECOVERY_OWNER_ACTIVE',self.recover(item,stop)['state'])
            self.assertEqual(before,self.store.get(op))
        release.set();thread.join(20)
        self.assertEqual('INSTALLED_DEFAULT_OFF_NOT_BOUND',results[0]['state']);self.assertEqual([1],renames)
    def test_locked_rename_commits_before_signed_recovery_reconciles(self):
        release,thread,results,renames=self.paused_owner('after_rename')
        op='p3-install:install-attempt-01';row=self.ownership.read(op);before=self.store.get(op)
        proof=self.proof(row,'STOP_RECEIPT');stop=self.stop(row);answers=[];started=threading.Event()
        def recovery():
            started.set()
            try:answers.append(self.recover(proof,stop))
            except Exception as e:answers.append(type(e).__name__+':'+str(e))
        waiter=threading.Thread(target=recovery);waiter.start();self.assertTrue(started.wait(5));time.sleep(.1)
        self.assertTrue(waiter.is_alive());self.assertEqual(before,self.store.get(op))
        release.set();thread.join(20);waiter.join(20)
        self.assertEqual('INSTALLED_DEFAULT_OFF_NOT_BOUND',results[0]['state'])
        self.assertEqual('SWITCHED',answers[0]['state']);self.assertEqual([1],renames)
        self.assertEqual('SUCCEEDED',self.store.get(op)['state'])
