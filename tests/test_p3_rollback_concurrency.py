"""TEST_ONLY 12-way rollback/recovery races using local SQLite and directories."""
import multiprocessing
import json
import os
import queue
import sqlite3
import threading
import unittest
from unittest import mock
from install import p3_carrier_install as installer
from src.p3_operation_kernel import RunnerOperationStore
from tests import test_p3_carrier_install as fixture


def worker(spec, barrier, output):
    def connect(): return sqlite3.connect(spec['db'],timeout=30)
    def hook(phase):
        if phase=='after_rename':
            fd=os.open(spec['marker'],os.O_CREAT|os.O_WRONLY|os.O_APPEND,0o600)
            try:os.write(fd,b'R\n')
            finally:os.close(fd)
    try:
        barrier.wait(timeout=30)
        result=installer.rollback(spec['root'],spec['manifest'],spec['manifest_sha'],spec['archive_sha'],
            spec['releases'],spec['state'],'rollback-attempt-01',lambda:True,enforce_root=False,
            operation_store=RunnerOperationStore(connect),original_install_attempt='install-attempt-01',fault_hook=hook)
        output.put(('ok',result['state']))
    except BaseException as error:output.put(('error',type(error).__name__+':'+str(error)))


class RollbackConcurrencyTests(unittest.TestCase):
    def setUp(self):
        fixture.CarrierInstallTests.setUp(self)
        installer.install(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
            self.releases,self.state,'install-attempt-01',lambda:True,enforce_root=False,
            operation_store=self.store,archive_path=self.archive,ownership_guard=self.guard)
    def tearDown(self):fixture.CarrierInstallTests.tearDown(self)
    def spec(self):
        return {'db':self.dbpath,'root':self.root,'manifest':self.manifest_path,'manifest_sha':self.manifest_sha,
                'archive_sha':self.archive_sha,'releases':self.releases,'state':self.state,
                'guard':self.guard,'marker':os.path.join(self.tmp,'rollback-renames')}
    def check(self,results):
        self.assertEqual(12,len(results),results)
        self.assertEqual([], [x for x in results if x[0]!='ok'],results)
        states=[x[1] for x in results]
        self.assertEqual(1,states.count('ROLLED_BACK_DEFAULT_OFF_QUARANTINED'),states)
        self.assertEqual(11,states.count('IN_PROGRESS_OR_HOLD'),states)
        with open(self.spec()['marker'],'rb') as f:self.assertEqual([b'R\n'],f.readlines())
        owner=self.store.get('p3-rollback-owner:install-attempt-01')
        journal=self.store.get('p3-rollback:rollback-attempt-01')
        guard=self.store.get('p3-recovery-guard:install-attempt-01')
        self.assertEqual('SUCCEEDED',owner['state']);self.assertEqual('SUCCEEDED',journal['state'])
        self.assertEqual('SUCCEEDED',guard['state'])
        self.assertEqual('ROLLED_BACK',json.loads(owner['receipt_json'])['phase'])
        self.assertEqual('SWITCHED',json.loads(journal['receipt_json'])['phase'])
        target=os.path.join(self.releases,'p3-'+self.archive_sha[:20])
        self.assertFalse(os.path.exists(target))
        with open(os.path.join(self.releases,'.p3-stage-install-attempt-01','src','module.py'),'rb') as f:
            self.assertEqual(b'default_off = True\n',f.read())
    def test_twelve_threads_single_rollback_winner(self):
        barrier=threading.Barrier(12);out=queue.Queue();spec=self.spec()
        threads=[threading.Thread(target=worker,args=(spec,barrier,out)) for _ in range(12)]
        for t in threads:t.start()
        for t in threads:t.join(45)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.check([out.get_nowait() for _ in range(12)])
    def test_twelve_processes_single_rollback_winner(self):
        ctx=multiprocessing.get_context('fork'); barrier=ctx.Barrier(12);out=ctx.Queue();spec=self.spec()
        processes=[ctx.Process(target=worker,args=(spec,barrier,out)) for _ in range(12)]
        for p in processes:p.start()
        for p in processes:p.join(45)
        self.assertFalse(any(p.is_alive() for p in processes))
        self.assertEqual([0]*12,[p.exitcode for p in processes])
        self.check([out.get(timeout=5) for _ in range(12)])
        out.close();out.join_thread()
    def test_real_rollback_owner_exit_then_fence_reconcile(self):
        ctx=multiprocessing.get_context('fork')
        def crashed():
            def connect():return sqlite3.connect(self.dbpath,timeout=30)
            def hook(phase):
                if phase=='after_rename':os._exit(77)
            installer.rollback(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'rollback-attempt-01',lambda:True,enforce_root=False,
                operation_store=RunnerOperationStore(connect),original_install_attempt='install-attempt-01',fault_hook=hook)
        p=ctx.Process(target=crashed);p.start();p.join(30);self.assertEqual(77,p.exitcode)
        owner=self.store.get('p3-rollback-owner:install-attempt-01')
        journal=self.store.get('p3-rollback:rollback-attempt-01')
        guard=self.store.get('p3-recovery-guard:install-attempt-01')
        self.assertEqual('RUNNING',owner['state']);self.assertEqual('RUNNING',journal['state']);self.assertEqual('RUNNING',guard['state'])
        wrong=installer.recover_rollback(self.releases,'rollback-attempt-01','install-attempt-01',operation_store=self.store,owner_fence='0'*64)
        self.assertEqual('OWNER_FENCE_MISMATCH_HOLD',wrong['recovery'])
        self.assertEqual(owner,self.store.get('p3-rollback-owner:install-attempt-01'))
        self.assertEqual(journal,self.store.get('p3-rollback:rollback-attempt-01'))
        self.assertEqual(guard,self.store.get('p3-recovery-guard:install-attempt-01'))
        right=installer.recover_rollback(self.releases,'rollback-attempt-01','install-attempt-01',
            operation_store=self.store,owner_fence=owner['adapter_correlation'])
        self.assertEqual('ROLLED_BACK_DEFAULT_OFF_QUARANTINED',right['state'])
        self.assertEqual('SUCCEEDED',self.store.get('p3-rollback-owner:install-attempt-01')['state'])
        self.assertEqual('SUCCEEDED',self.store.get('p3-rollback:rollback-attempt-01')['state'])
        self.assertEqual('SUCCEEDED',self.store.get('p3-recovery-guard:install-attempt-01')['state'])
        self.assertFalse(os.path.exists(os.path.join(self.releases,'p3-'+self.archive_sha[:20])))
    def test_install_recovery_is_disabled_and_rollback_still_works(self):
        fence=self.store.get('p3-stage:install-attempt-01')['adapter_correlation']
        result=installer.recover(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
            self.releases,self.state,'install-attempt-01',operation_store=self.store,owner_fence=fence)
        self.assertEqual('RECOVERY_OWNER_ACTIVE',result['state'])
        self.assertIsNone(self.store.get('p3-recovery-guard:install-attempt-01'))
        result=installer.rollback(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
            self.releases,self.state,'rollback-attempt-01',lambda:True,enforce_root=False,
            operation_store=self.store,original_install_attempt='install-attempt-01')
        self.assertEqual('ROLLED_BACK_DEFAULT_OFF_QUARANTINED',result['state'])

    def test_concurrent_matching_rollback_recover_has_one_reconciler(self):
        ctx=multiprocessing.get_context('fork')
        def crashed():
            def connect():return sqlite3.connect(self.dbpath,timeout=30)
            def hook(phase):
                if phase=='after_rename':os._exit(77)
            installer.rollback(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'rollback-attempt-01',lambda:True,enforce_root=False,
                operation_store=RunnerOperationStore(connect),original_install_attempt='install-attempt-01',fault_hook=hook)
        p=ctx.Process(target=crashed);p.start();p.join(30);self.assertEqual(77,p.exitcode)
        fence=self.store.get('p3-rollback-owner:install-attempt-01')['adapter_correlation']
        barrier=threading.Barrier(12);out=queue.Queue()
        def recover():
            try:
                barrier.wait(15)
                result=installer.recover_rollback(self.releases,'rollback-attempt-01','install-attempt-01',
                    operation_store=self.store,owner_fence=fence)
                out.put(('ok',result['state']))
            except Exception as e:out.put(('error',str(e)))
        threads=[threading.Thread(target=recover) for _ in range(12)]
        for t in threads:t.start()
        for t in threads:t.join(30)
        self.assertFalse(any(t.is_alive() for t in threads))
        rows=[out.get_nowait() for _ in range(12)]
        self.assertEqual([], [r for r in rows if r[0]!='ok'],rows)
        states=[r[1] for r in rows]
        self.assertEqual(1,states.count('ROLLED_BACK_DEFAULT_OFF_QUARANTINED'),states)
        self.assertEqual(11,states.count('IN_PROGRESS_OR_HOLD'),states)
        self.assertEqual('SUCCEEDED',self.store.get('p3-rollback:rollback-attempt-01')['state'])
        self.assertEqual('SUCCEEDED',self.store.get('p3-recovery-guard:install-attempt-01')['state'])

    def test_install_recover_is_serialized_while_rollback_active(self):
        entered=threading.Event();release=threading.Event();output=[]
        def hook(phase):
            if phase=='before_rename':entered.set();release.wait(15)
        def run():
            try:output.append(installer.rollback(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'rollback-attempt-01',lambda:True,enforce_root=False,
                operation_store=self.store,original_install_attempt='install-attempt-01',fault_hook=hook)['state'])
            except Exception as e:output.append(type(e).__name__+':'+str(e))
        t=threading.Thread(target=run);t.start();self.assertTrue(entered.wait(15))
        before=self.store.get('p3-rollback:rollback-attempt-01')
        fence=self.store.get('p3-stage:install-attempt-01')['adapter_correlation']
        for _ in range(12):
            result=installer.recover(self.root,self.manifest_path,self.manifest_sha,self.archive_sha,
                self.releases,self.state,'install-attempt-01',operation_store=self.store,owner_fence=fence)
            self.assertEqual('RECOVERY_OWNER_ACTIVE',result['state'])
        self.assertEqual(before,self.store.get('p3-rollback:rollback-attempt-01'))
        release.set();t.join(15);self.assertEqual(['ROLLED_BACK_DEFAULT_OFF_QUARANTINED'],output)
