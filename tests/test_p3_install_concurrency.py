"""TEST_ONLY SQLite/fs fixtures for same-attempt process and thread contention."""
import multiprocessing
import os
import queue
import sqlite3
import threading
import unittest
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from src.p3_admission_v2 import canonical
from install import p3_carrier_install as installer
from src.p3_operation_kernel import RunnerOperationStore
from tests import test_p3_carrier_install as carrier_fixtures


def worker(spec, barrier, output):
    def connect(): return sqlite3.connect(spec['db'], timeout=30)
    store = RunnerOperationStore(connect)
    def hook(phase):
        if phase == 'after_rename':
            fd = os.open(spec['marker'], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try: os.write(fd, b'R\n')
            finally: os.close(fd)
    try:
        barrier.wait(timeout=30)
        value = installer.install(spec['root'],spec['manifest'],spec['manifest_sha'],spec['archive_sha'],
                                  spec['releases'],spec['state'],'install-attempt-01',lambda:True,
                                  enforce_root=False,operation_store=store,archive_path=spec['archive'],fault_hook=hook,ownership_guard=spec['guard'])
        output.put(('ok',value['state']))
    except BaseException as error:
        output.put(('error',type(error).__name__+':'+str(error)))


class ConcurrentInstallTests(unittest.TestCase):
    def setUp(self):
        carrier_fixtures.CarrierInstallTests.setUp(self)
    def tearDown(self):
        carrier_fixtures.CarrierInstallTests.tearDown(self)
    def spec(self):
        return {'db':self.dbpath,'root':self.root,'manifest':self.manifest_path,'manifest_sha':self.manifest_sha,
                'archive_sha':self.archive_sha,'releases':self.releases,'state':self.state,
                'archive':self.archive,'guard':self.guard,'marker':os.path.join(self.tmp,'rename-count')}
    def check_result(self,results):
        self.assertEqual(12,len(results),results)
        self.assertEqual([], [value for kind,value in results if kind!='ok'],results)
        states=[value for _,value in results]
        self.assertEqual(1,states.count('INSTALLED_DEFAULT_OFF_NOT_BOUND'),states)
        self.assertEqual(11,states.count('IN_PROGRESS_OR_HOLD'),states)
        with open(self.spec()['marker'],'rb') as f:self.assertEqual([b'R\n'],f.readlines())
        stage=self.store.get('p3-stage:install-attempt-01')
        self.assertEqual('SUCCEEDED',stage['state'])
        self.assertEqual('SUCCEEDED',self.store.get('p3-install:install-attempt-01')['state'])
        target=os.path.join(self.releases,'p3-'+self.archive_sha[:20],'src','module.py')
        with open(target,'rb') as f:self.assertEqual(b'default_off = True\n',f.read())
        self.assertFalse(os.path.exists(os.path.join(self.releases,'.p3-stage-install-attempt-01')))
    def test_twelve_threads_one_winner_no_loser_mutation(self):
        barrier=threading.Barrier(12); output=queue.Queue(); spec=self.spec()
        threads=[threading.Thread(target=worker,args=(spec,barrier,output)) for _ in range(12)]
        for t in threads:t.start()
        for t in threads:t.join(45)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.check_result([output.get_nowait() for _ in range(12)])
    def test_twelve_processes_one_winner_no_loser_mutation(self):
        ctx=multiprocessing.get_context('fork');barrier=ctx.Barrier(12);output=ctx.Queue();spec=self.spec()
        processes=[ctx.Process(target=worker,args=(spec,barrier,output)) for _ in range(12)]
        for p in processes:p.start()
        for p in processes:p.join(45)
        self.assertFalse(any(p.is_alive() for p in processes))
        self.assertEqual([0]*12,[p.exitcode for p in processes])
        self.check_result([output.get(timeout=5) for _ in range(12)])
        output.close();output.join_thread()
    def test_real_process_exit_after_rename_requires_matching_fence(self):
        ctx=multiprocessing.get_context('fork')
        def crashed():
            def connect(): return sqlite3.connect(self.dbpath, timeout=30)
            def stop(phase):
                if phase=='after_rename': os._exit(77)
            installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                operation_store=RunnerOperationStore(connect),archive_path=self.archive,fault_hook=stop,ownership_guard=self.guard)
        process=ctx.Process(target=crashed);process.start();process.join(30)
        self.assertEqual(77,process.exitcode)
        stage=self.store.get('p3-stage:install-attempt-01')
        journal=self.store.get('p3-install:install-attempt-01')
        self.assertEqual('RUNNING',journal['state'])
        args=(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,self.releases,self.state,'install-attempt-01')
        wrong=installer.recover(*args,operation_store=self.store,owner_fence='0'*64)
        self.assertEqual('RECOVERY_OWNER_ACTIVE',wrong['recovery'])
        self.assertEqual(journal,self.store.get('p3-install:install-attempt-01'))
        result=installer.recover(*args,operation_store=self.store,owner_fence=stage['adapter_correlation'])
        self.assertEqual('RECOVERY_OWNER_ACTIVE',result['state'])
        duplicate=installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                operation_store=self.store,archive_path=self.archive,ownership_guard=self.guard)
        self.assertEqual('IN_PROGRESS_OR_HOLD',duplicate['state'])

    def test_one_hundred_live_owner_recover_calls_cannot_change_journal(self):
        entered=threading.Event();release=threading.Event();output=[];renames=[]
        def hook(phase):
            if phase=='before_rename':entered.set();release.wait(20)
            if phase=='after_rename':renames.append(1)
        def run():
            try:output.append(installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                operation_store=self.store,archive_path=self.archive,ownership_guard=self.guard,fault_hook=hook))
            except Exception as e:output.append(type(e).__name__+':'+str(e))
        thread=threading.Thread(target=run);thread.start();self.assertTrue(entered.wait(10))
        before=self.store.get('p3-install:install-attempt-01')
        fence=self.store.get('p3-stage:install-attempt-01')['adapter_correlation']
        barrier=threading.Barrier(100); answers=queue.Queue()
        def recover_attempt():
            try:
                barrier.wait(timeout=15)
                result=installer.recover(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                    self.releases,self.state,'install-attempt-01',operation_store=self.store,owner_fence=fence)
                answers.put(('ok',result['state']))
            except Exception as e:answers.put(('error',type(e).__name__+':'+str(e)))
        calls=[threading.Thread(target=recover_attempt) for _ in range(100)]
        for call in calls:call.start()
        for call in calls:call.join(20)
        self.assertFalse(any(call.is_alive() for call in calls))
        self.assertEqual([('ok','RECOVERY_OWNER_ACTIVE')]*100,[answers.get_nowait() for _ in range(100)])
        self.assertEqual(before,self.store.get('p3-install:install-attempt-01'))
        release.set();thread.join(20);self.assertFalse(thread.is_alive())
        self.assertEqual('INSTALLED_DEFAULT_OFF_NOT_BOUND',output[0]['state'])
        self.assertEqual([1],renames)
        self.assertEqual('SUCCEEDED',self.store.get('p3-install:install-attempt-01')['state'])

    def test_signed_stop_takeover_before_rename_fences_old_installer(self):
        entered=threading.Event();release=threading.Event();output=[];renames=[]
        def hook(phase):
            if phase=='before_rename':entered.set();release.wait(20)
            if phase=='after_rename':renames.append(1)
        def run():
            try:output.append(installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                operation_store=self.store,archive_path=self.archive,ownership_guard=self.guard,fault_hook=hook))
            except Exception as e:output.append(type(e).__name__+':'+str(e))
        thread=threading.Thread(target=run);thread.start();self.assertTrue(entered.wait(10))
        old=self.ownership.read('p3-install:install-attempt-01');before=self.store.get('p3-install:install-attempt-01')
        keys={role:Ed25519PrivateKey.generate() for role in ('recovery','stop')}
        for role,key in keys.items():
            self.ownership.trust.keys[role]=(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw),role,'test-recovery-authority')
        now=int(time.time())
        admission=dict(operation_id=old['operation_id'],attempt_id=old['attempt_id'],observed_owner_token=old['owner_token'],
            observed_epoch=old['epoch'],observed_fence=old['fence'],observed_lease_expires_at=old['lease_expires_at'],
            observed_heartbeat_seq=old['heartbeat_seq'],observed_heartbeat_at=old['heartbeat_at'],
            authority_identity='test-recovery-authority',reason='fixture-stop',proof_kind='STOP_RECEIPT',
            issued_at=now-1,expires_at=now+60,key_id='recovery')
        admission['signature']=keys['recovery'].sign(b'P3-RECOVERY-ADMISSION-V2\x00'+canonical(admission)).hex()
        receipt=dict(operation_id=old['operation_id'],attempt_id=old['attempt_id'],owner_token=old['owner_token'],
            epoch=old['epoch'],fence=old['fence'],heartbeat_seq=old['heartbeat_seq'],stopped_at=now,
            authority_identity='test-recovery-authority',key_id='stop')
        receipt['signature']=keys['stop'].sign(b'P3-OWNER-STOP-V2\x00'+canonical(receipt)).hex()
        claimed=self.guard.claim_recovery(admission,receipt)
        self.assertEqual(old['epoch']+1,claimed['epoch'])
        release.set();thread.join(20);self.assertFalse(thread.is_alive())
        self.assertEqual('OWNER_LOST',output[0]['state'])
        self.assertEqual([],renames)
        self.assertEqual(before,self.store.get('p3-install:install-attempt-01'))

    def test_revoked_authority_is_rechecked_inside_rename_lock(self):
        renames=[]
        def hook(phase):
            if phase=='before_rename':self.ownership.trust.revoked=frozenset(('fixture-install',))
            if phase=='after_rename':renames.append(1)
        result=installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
            self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
            operation_store=self.store,archive_path=self.archive,ownership_guard=self.guard,fault_hook=hook)
        self.assertEqual('OWNER_LOST',result['state'])
        self.assertEqual([],renames)
        self.assertFalse(os.path.exists(os.path.join(self.releases,'p3-'+self.archive_sha[:20])))

    def test_install_requires_guard_and_same_database(self):
        args=(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,self.releases,self.state,
              'install-attempt-01',lambda:True)
        with self.assertRaisesRegex(PermissionError,'OWNERSHIP_GUARD_REQUIRED'):
            installer.install(*args,enforce_root=False,operation_store=self.store,archive_path=self.archive)
        from src.p3_recovery_authority import OwnershipStore,OwnershipGuard,OWNERSHIP_MIGRATION
        other=os.path.join(self.tmp,'other.sqlite')
        def other_connect():return sqlite3.connect(other,timeout=10)
        db=other_connect();db.execute(OWNERSHIP_MIGRATION);db.commit();db.close()
        other_owner=OwnershipStore(other_connect,self.ownership.trust,lambda:int(time.time()),10)
        other_guard=OwnershipGuard(other_owner,self.lockdir_fd,'guard',self.guard.install_authority_reader)
        try:
            with self.assertRaisesRegex(PermissionError,'SAME_DURABLE_DATABASE_REQUIRED'):
                installer.install(*args,enforce_root=False,operation_store=self.store,
                                  archive_path=self.archive,ownership_guard=other_guard)
        finally:other_guard.close()
        self.assertIsNone(self.store.get('p3-stage:install-attempt-01'))

    def test_bad_guard_authority_rejects_without_rename(self):
        self.guard.install_authority_reader=lambda op,attempt,context: {'invalid':True}
        with self.assertRaises(ValueError):
            installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                operation_store=self.store,archive_path=self.archive,ownership_guard=self.guard)
        self.assertIsNone(self.store.get('p3-install:install-attempt-01'))
        self.assertFalse(os.path.exists(os.path.join(self.releases,'p3-'+self.archive_sha[:20])))

    def test_wrong_owner_fence_cannot_change_running_stage(self):
        entered=threading.Event(); release=threading.Event(); results=[]
        def pause(phase):
            if phase=='before_receipt': entered.set(); release.wait(15)
        def winner():
            try:
                results.append(installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                    self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                    operation_store=self.store,archive_path=self.archive,fault_hook=pause,ownership_guard=self.guard)['state'])
            except Exception as error: results.append(type(error).__name__+':'+str(error))
        thread=threading.Thread(target=winner);thread.start();self.assertTrue(entered.wait(15))
        before=self.store.get('p3-stage:install-attempt-01')
        self.assertEqual('RUNNING',before['state'])
        self.assertFalse(self.store.transition_owned('p3-stage:install-attempt-01','0'*64,'RUNNING','UNKNOWN',{'phase':'forged'}))
        for _ in range(11):
            result=installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                operation_store=self.store,archive_path=self.archive,ownership_guard=self.guard)
            self.assertEqual('IN_PROGRESS_OR_HOLD',result['state'])
        self.assertEqual(before,self.store.get('p3-stage:install-attempt-01'))
        release.set();thread.join(15)
        self.assertEqual(['INSTALLED_DEFAULT_OFF_NOT_BOUND'],results)
        self.assertEqual('SUCCEEDED',self.store.get('p3-stage:install-attempt-01')['state'])

    def test_loser_cannot_mark_owner_unknown_and_recovery_requires_fence(self):
        entered=threading.Event(); release=threading.Event(); errors=[]
        def crash(phase):
            if phase=='after_rename':
                entered.set(); release.wait(15); raise RuntimeError('winner-crash')
        def winner():
            try:
                installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                                  self.releases,self.state,'install-attempt-01',lambda:True,
                                  enforce_root=False,operation_store=self.store,archive_path=self.archive,fault_hook=crash,ownership_guard=self.guard)
            except Exception as e:errors.append(str(e))
        t=threading.Thread(target=winner);t.start();self.assertTrue(entered.wait(15))
        before=self.store.get('p3-stage:install-attempt-01')
        for _ in range(11):
            out=installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                                  self.releases,self.state,'install-attempt-01',lambda:True,
                                  enforce_root=False,operation_store=self.store,archive_path=self.archive,ownership_guard=self.guard)
            self.assertEqual('IN_PROGRESS_OR_HOLD',out['state'])
        self.assertEqual(before,self.store.get('p3-stage:install-attempt-01'))
        # The writer transaction is held across rename; do not block this test
        # on a second write. Wrong-fence CAS is tested while stage is RUNNING.
        release.set();t.join(15);self.assertEqual(['winner-crash'],errors)
        journal=self.store.get('p3-install:install-attempt-01');self.assertEqual('UNKNOWN',journal['state'])
        args=(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,self.releases,self.state,'install-attempt-01')
        wrong=installer.recover(*args,operation_store=self.store,owner_fence='0'*64)
        self.assertEqual('RECOVERY_OWNER_ACTIVE',wrong['recovery'])
        self.assertEqual(journal,self.store.get('p3-install:install-attempt-01'))
        ok=installer.recover(*args,operation_store=self.store,owner_fence=before['adapter_correlation'])
        self.assertEqual('RECOVERY_OWNER_ACTIVE',ok['state'])
