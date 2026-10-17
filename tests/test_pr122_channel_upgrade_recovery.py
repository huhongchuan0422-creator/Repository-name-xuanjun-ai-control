"""Real fork/exit crash matrix on disposable Root-owned filesystem copies only."""
import json
import os
import time
import unittest
from unittest.mock import patch
from tests.test_pr122_customer_channel_upgrade import UpgradeTests, REAL_GATE
from scripts import pr122_customer_channel_upgrade as u

class RecoveryTests(unittest.TestCase):
    def fixture(self):
        f=UpgradeTests();f.setUp();self.addCleanup(f.doCleanups);return f

    def crash(self, action, label, **kwargs):
        pid=os.fork()
        if pid==0:
            def cut(s):
                if s==label:os._exit(73)
            try:action(checkpoint=cut,**kwargs)
            except BaseException:os._exit(74)
            os._exit(75)
        _,status=os.waitpid(pid,0)
        self.assertEqual(os.waitstatus_to_exitcode(status),73,label)

    def restored(self,p):
        u.verify_old(p)
        self.assertEqual(u.load_transaction()['state'],'ROLLED_BACK')
        if u.load_transaction().get('activation_started'):self.assertTrue((u.CONTROL/'previous').exists())

    def recovery_approval(self,r,comment=99):
        a={'decision':'RECOVERY_APPROVED','transaction':u.TXN,
           'event_sha256':u.sha(u.canonical(r)),
           'plan_sha256':u.sha(u.canonical(r['plan'])),
           'upgrade_script_sha256':u.sha(u.read(u.BASE/'channel.py')),
           'max_executions':1,'issued_unix':int(time.time())-1,
           'expires_unix':int(time.time())+300}
        body='XUANJUN_CUSTOMER_CHANNEL_RECOVERY\n'+json.dumps(a)
        trust={'source_writer_principal':'writer','reviewer_principal':'independent-auditor',
               'custody_evidence_sha256':'e'*64,'comment_id':comment,
               'body_sha256':u.sha(body.encode())}
        u.replace(u.TRUST,u.canonical(trust),0o600)
        return {'id':comment,'user':{'login':'huhongchuan0422-creator'},
                'issue_url':'https://api.github.com/repos/'+u.REPO+'/issues/122','body':body}

    def test_forward_real_process_exit_all_intent_mutated_done_boundaries(self):
        stages=['BACKUP_VERIFIED','STAGED','FENCED','OLD_MOVED','CANDIDATE_MOVED','CODE_REPLACED','TAR_REPLACED','GRANTED']
        for stage in ['PREPARING','BOUND']+[s+suffix for s in stages for suffix in (':INTENT',':MUTATED','')]:
            with self.subTest(stage=stage):
                f=UpgradeTests();f.setUp()
                try:
                    p=u.plan();self.crash(u.apply,stage)
                    with self.assertRaises(RuntimeError):u.apply()
                    self.assertEqual(u.rollback()['state'],'ROLLED_BACK');self.restored(p)
                finally:f.doCleanups()

    def test_rollback_real_process_exit_requires_fresh_bound_permission(self):
        stages=['RB_FENCED','RB_PREPARED','RB_PARKED','RB_CANDIDATE','RB_CODE','RB_TAR','RB_GRANTED']
        for label in [s+suffix for s in stages for suffix in (':INTENT',':MUTATED','')]:
            with self.subTest(stage=label):
                f=UpgradeTests();f.setUp()
                try:
                    p=u.plan();u.apply();self.crash(u.rollback,label)
                    with self.assertRaises(RuntimeError):u.rollback()
                    r=u.load_transaction();c=self.recovery_approval(r)
                    with patch.object(u,'__file__',str(u.BASE/'channel.py')):
                        result=u.rollback(recover=True,get=lambda _:c)
                    self.assertEqual(result['state'],'ROLLED_BACK');self.restored(p)
                finally:f.doCleanups()

    def test_partial_restore_tree_is_resumable_only_if_bytes_match(self):
        f=self.fixture();p=u.plan();u.apply()
        original=u.create;fired=[]
        def fail(path,raw,mode):
            original(path,raw,mode)
            if path.parent==u.CONTROL/'restored-candidate' and not fired:
                fired.append(True);raise OSError('injected partial restore')
        with patch.object(u,'create',side_effect=fail),self.assertRaises(OSError):u.rollback()
        r=u.load_transaction();c=self.recovery_approval(r)
        with patch.object(u,'__file__',str(u.BASE/'channel.py')):u.rollback(recover=True,get=lambda _:c)
        self.restored(p)

    def test_receipt_fsync_failure_after_fence_uses_independent_containment(self):
        f=self.fixture();p=u.plan();original=u.receipt
        def broken(r):
            if r.get('activation_started'):raise OSError('receipt fsync unavailable')
            return original(r)
        with patch.object(u,'receipt',side_effect=broken),self.assertRaises(OSError):u.apply()
        self.assertEqual(json.loads(u.read(u.BASE/'grant-state.json'))['state'],'HOLD_UPGRADE')
        self.assertEqual(u.rollback()['state'],'ROLLED_BACK');self.restored(p)

    def test_initial_receipt_failure_consumes_once_without_changing_old_objects(self):
        f=self.fixture();p=u.plan()
        with patch.object(u,'receipt',side_effect=OSError('receipt failed')),self.assertRaises(OSError):u.apply()
        u.verify_old(p)
        with self.assertRaises(RuntimeError):u.apply()
        u.rollback();self.restored(p)

    def test_before_initial_event_failure_is_unknown_and_never_retried(self):
        f=self.fixture();p=u.plan();original=u.create
        def fail(path,raw,mode):
            if path==u.CONTROL/'plan.json':raise OSError('initial persistence failed')
            return original(path,raw,mode)
        with patch.object(u,'create',side_effect=fail),self.assertRaises(OSError):u.apply()
        u.verify_old(p)
        with self.assertRaises(RuntimeError):u.apply()
        with self.assertRaises((RuntimeError,FileNotFoundError)):u.rollback()

    def test_journal_fsync_failure_between_mutation_and_done_is_recoverable(self):
        f=self.fixture();p=u.plan();original=u.event
        def fail(r,phase,status):
            if phase=='OLD_MOVED' and status=='DONE':raise OSError('journal fsync failed')
            return original(r,phase,status)
        with patch.object(u,'event',side_effect=fail),self.assertRaises(OSError):u.apply()
        self.assertFalse((u.BASE/'candidate').exists())
        self.assertEqual(json.loads(u.read(u.BASE/'grant-state.json'))['state'],'HOLD_UPGRADE')
        u.rollback();self.restored(p)

    def test_rollback_receipt_failure_cannot_claim_success_and_needs_new_permit(self):
        f=self.fixture();p=u.plan();u.apply();original=u.receipt
        def fail(r):
            if r.get('phase')=='RB_TAR':raise OSError('rollback receipt failed')
            return original(r)
        with patch.object(u,'receipt',side_effect=fail),self.assertRaises(OSError):u.rollback()
        with self.assertRaises(RuntimeError):u.rollback()
        r=u.load_transaction();c=self.recovery_approval(r)
        with patch.object(u,'__file__',str(u.BASE/'channel.py')):u.rollback(recover=True,get=lambda _:c)
        self.restored(p)

    def test_held_lock_denies_second_writer(self):
        self.fixture()
        with u.owner_lock(create_allowed=True):
            pid=os.fork()
            if pid==0:
                try:u.apply()
                except BlockingIOError:os._exit(0)
                except BaseException:os._exit(2)
                os._exit(3)
            _,status=os.waitpid(pid,0)
            self.assertEqual(os.waitstatus_to_exitcode(status),0)
        self.assertFalse(u.CONTROL.exists())

    def test_approval_and_baseline_rechecked_inside_lock(self):
        f=self.fixture();f.gate.side_effect=[{'id':123,'body_sha256':'d'*64,'rollback_approved':True,'expires_unix':9999999999},RuntimeError('revoked')]
        with self.assertRaises(RuntimeError):u.apply()
        self.assertFalse(u.CONTROL.exists())

    def test_approval_expiry_cross_plan_edit_and_same_subject_denied(self):
        self.fixture();p=u.plan();now=int(time.time())
        a={'decision':'REBIND_APPROVED','transaction':u.TXN,'plan_sha256':u.sha(u.canonical(p)),
           'new':p['new'],'upgrade_script_sha256':u.OLD_CODE,'max_executions':1,
           'rollback_approved':True,'issued_unix':now-1,'expires_unix':now+300}
        body='XUANJUN_CUSTOMER_CHANNEL_REBIND\n'+json.dumps(a)
        trust={'source_writer_principal':'writer','reviewer_principal':'auditor','custody_evidence_sha256':'e'*64,'comment_id':5,'body_sha256':u.sha(body.encode())}
        u.create(u.TRUST,u.canonical(trust),0o600)
        c={'id':5,'user':{'login':'huhongchuan0422-creator'},'issue_url':'https://api.github.com/repos/'+u.REPO+'/issues/122','body':body}
        with patch.object(u,'__file__',str(u.BASE/'channel.py')):
            REAL_GATE(p,lambda _:c)
            for bad in ({**p,'transaction':'wrong'},):
                with self.assertRaises(RuntimeError):REAL_GATE(bad,lambda _:c)
            with self.assertRaises(RuntimeError):REAL_GATE(p,lambda _:{**c,'body':body+' '})
            with patch.object(u.time,'time',return_value=now+1000),self.assertRaises(RuntimeError):REAL_GATE(p,lambda _:c)
            trust['reviewer_principal']='writer';u.replace(u.TRUST,u.canonical(trust),0o600)
            with self.assertRaises(RuntimeError):REAL_GATE(p,lambda _:c)

    def test_recovery_approval_cannot_be_reused_or_used_for_other_event(self):
        self.fixture();u.apply();self.crash(u.rollback,'RB_PARKED')
        r=u.load_transaction();c=self.recovery_approval(r)
        with patch.object(u,'__file__',str(u.BASE/'channel.py')):
            with self.assertRaises(RuntimeError):u.recovery_gate({**r,'phase':'wrong'},lambda _:c)
            u.recovery_gate(r,lambda _:c)
            with self.assertRaises(FileExistsError):u.recovery_gate(r,lambda _:c)

    def test_real_fsync_failure_matrix_never_grants_mixed_objects(self):
        # Enumerate every actual fsync call in a full forward and rollback run.
        for operation in ('apply','rollback'):
            counter=[]
            f=UpgradeTests();f.setUp()
            try:
                if operation=='rollback':u.apply()
                real=os.fsync
                def count(fd):counter.append(fd);return real(fd)
                with patch.object(os,'fsync',side_effect=count):getattr(u,operation)()
            finally:f.doCleanups()
            for cut in range(1,len(counter)+1):
                with self.subTest(operation=operation,fsync=cut):
                    f=UpgradeTests();f.setUp()
                    try:
                        p=u.plan()
                        if operation=='rollback':u.apply()
                        calls=[0]
                        def fail(fd):
                            calls[0]+=1
                            if calls[0]==cut:raise OSError('injected fsync error')
                            return real(fd)
                        with patch.object(os,'fsync',side_effect=fail):
                            try:getattr(u,operation)()
                            except OSError:pass
                        grant=json.loads(u.read(u.BASE/'grant-state.json'))['state']
                        if grant=='GRANTED':
                            code=u.sha(u.read(u.BASE/'channel.py'))
                            if code==u.OLD_CODE:u.verify_old(p)
                            else:
                                self.assertEqual(code,f.binding['channel_sha256'])
                                self.assertEqual(u.sha(u.read(u.BASE/u.ARCHIVE)),f.binding['tar_sha256'])
                                new,_,_=u.unpack(f.tar)
                                self.assertEqual(u.snapshot(u.BASE/'candidate'),{n:{'sha256':u.sha(b),'mode':0o400} for n,b in new.items()})
                        else:self.assertIn(grant,('HOLD_UPGRADE','UPGRADING'))
                        if u.CONTROL.exists():
                            with self.assertRaises(RuntimeError):u.apply()
                    finally:f.doCleanups()
            print('FSYNC_FAILURE_MATRIX '+operation+'='+str(len(counter)),flush=True)

if __name__=='__main__':unittest.main()
