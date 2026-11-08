"""TEST_ONLY SQLite/fs fixtures for same-attempt process and thread contention."""
import multiprocessing
import os
import queue
import sqlite3
import threading
import unittest
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
                                  enforce_root=False,operation_store=store,archive_path=spec['archive'],fault_hook=hook)
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
                'archive':self.archive,'marker':os.path.join(self.tmp,'rename-count')}
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
                operation_store=RunnerOperationStore(connect),archive_path=self.archive,fault_hook=stop)
        process=ctx.Process(target=crashed);process.start();process.join(30)
        self.assertEqual(77,process.exitcode)
        stage=self.store.get('p3-stage:install-attempt-01')
        journal=self.store.get('p3-install:install-attempt-01')
        self.assertEqual('RUNNING',journal['state'])
        args=(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,self.releases,self.state,'install-attempt-01')
        wrong=installer.recover(*args,operation_store=self.store,owner_fence='0'*64)
        self.assertEqual('OWNER_FENCE_MISMATCH_HOLD',wrong['recovery'])
        self.assertEqual(journal,self.store.get('p3-install:install-attempt-01'))
        result=installer.recover(*args,operation_store=self.store,owner_fence=stage['adapter_correlation'])
        self.assertEqual('SWITCHED',result['state'])
        duplicate=installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                operation_store=self.store,archive_path=self.archive)
        self.assertEqual('IN_PROGRESS_OR_HOLD',duplicate['state'])

    def test_wrong_owner_fence_cannot_change_running_stage(self):
        entered=threading.Event(); release=threading.Event(); results=[]
        def pause(phase):
            if phase=='before_receipt': entered.set(); release.wait(15)
        def winner():
            try:
                results.append(installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                    self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                    operation_store=self.store,archive_path=self.archive,fault_hook=pause)['state'])
            except Exception as error: results.append(type(error).__name__+':'+str(error))
        thread=threading.Thread(target=winner);thread.start();self.assertTrue(entered.wait(15))
        before=self.store.get('p3-stage:install-attempt-01')
        self.assertEqual('RUNNING',before['state'])
        self.assertFalse(self.store.transition_owned('p3-stage:install-attempt-01','0'*64,'RUNNING','UNKNOWN',{'phase':'forged'}))
        for _ in range(11):
            result=installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
                operation_store=self.store,archive_path=self.archive)
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
                                  enforce_root=False,operation_store=self.store,archive_path=self.archive,fault_hook=crash)
            except Exception as e:errors.append(str(e))
        t=threading.Thread(target=winner);t.start();self.assertTrue(entered.wait(15))
        before=self.store.get('p3-stage:install-attempt-01')
        for _ in range(11):
            out=installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                                  self.releases,self.state,'install-attempt-01',lambda:True,
                                  enforce_root=False,operation_store=self.store,archive_path=self.archive)
            self.assertEqual('IN_PROGRESS_OR_HOLD',out['state'])
        self.assertEqual(before,self.store.get('p3-stage:install-attempt-01'))
        self.assertFalse(self.store.transition_owned('p3-stage:install-attempt-01','0'*64,'RUNNING','UNKNOWN',{'phase':'forged'}))
        release.set();t.join(15);self.assertEqual(['winner-crash'],errors)
        journal=self.store.get('p3-install:install-attempt-01');self.assertEqual('UNKNOWN',journal['state'])
        args=(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,self.releases,self.state,'install-attempt-01')
        wrong=installer.recover(*args,operation_store=self.store,owner_fence='0'*64)
        self.assertEqual('OWNER_FENCE_MISMATCH_HOLD',wrong['recovery'])
        self.assertEqual(journal,self.store.get('p3-install:install-attempt-01'))
        ok=installer.recover(*args,operation_store=self.store,owner_fence=before['adapter_correlation'])
        self.assertEqual('SWITCHED',ok['state'])
