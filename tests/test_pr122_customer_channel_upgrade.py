"""Real filesystem channel upgrade/rollback in root-owned disposable fixtures.
Never accesses target paths, sudoers, credentials or services.
"""
import ast
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from contextlib import ExitStack
from types import SimpleNamespace
from scripts import pr122_customer_channel_upgrade as u


def archive(files,commit):
    manifest=u.canonical({'source_commit':commit*40,'source_tree':'c'*40,'files':[{'path':p,'size':len(b),'sha256':u.sha(b)} for p,b in files.items()]});out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz') as t:
        for p,b in {**files,'CUSTOMER_MANIFEST.json':manifest}.items():
            x=tarfile.TarInfo('customer-center/'+p);x.size=len(b);t.addfile(x,io.BytesIO(b))
    return out.getvalue(),manifest

class FullClosureReaderIntegration(unittest.TestCase):
    """Delta-3 direct regression (20261129): the REAL complete closure built by the
    original package builder from this exact tree (the 267 bound files +
    CUSTOMER_MANIFEST.json, i.e. the same 268-member shape as the Hosted archive
    that failed plan with HOLD:TAR_COUNT) goes straight through the shared reader.
    Pure bytes in/out: no root, no filesystem target paths. Small synthetic
    fixtures above never exercised >100 members, so this combination was untested
    while CI passed.
    """
    def _real_closure(self):
        from scripts.pr122_customer_package import build
        with tempfile.TemporaryDirectory() as td:
            build(td,'a'*40,'c'*40)
            raw=(Path(td)/u.ARCHIVE).read_bytes()
            receipt=json.loads((Path(td)/'CUSTOMER_PACKAGE_RECEIPT.json').read_bytes())
        return raw,receipt
    def test_real_full_closure_unpacks_and_matches_receipt(self):
        raw,receipt=self._real_closure()
        files,manifest,msha=u.unpack(raw)
        self.assertGreater(len(files),100)
        self.assertEqual(len(files),receipt['members'])
        self.assertEqual(len(manifest['files']),receipt['bound_files'])
        self.assertEqual(msha,receipt['manifest_sha256'])
        self.assertEqual({p for p in files},{'CUSTOMER_MANIFEST.json',*[x['path'] for x in manifest['files']]})
    def test_undeclared_extra_member_holds(self):
        raw,receipt=self._real_closure()
        import tarfile as tf
        out=io.BytesIO()
        with tf.open(fileobj=out,mode='w:gz') as t:
            with tf.open(fileobj=io.BytesIO(raw),mode='r:gz') as s:
                for m in s.getmembers():
                    t.addfile(m,s.extractfile(m))
            b=b'injected\n';x=tf.TarInfo('customer-center/scripts/UNDECLARED.py');x.size=len(b);t.addfile(x,io.BytesIO(b))
        with self.assertRaises(RuntimeError) as ctx:u.unpack(out.getvalue())
        self.assertIn('HOLD:MANIFEST_SET',str(ctx.exception))
    def test_missing_declared_member_holds(self):
        raw,receipt=self._real_closure()
        import tarfile as tf
        drop='customer-center/boot.py'
        out=io.BytesIO()
        with tf.open(fileobj=out,mode='w:gz') as t:
            with tf.open(fileobj=io.BytesIO(raw),mode='r:gz') as s:
                for m in s.getmembers():
                    if m.name==drop:continue
                    t.addfile(m,s.extractfile(m))
        with self.assertRaises(RuntimeError) as ctx:u.unpack(out.getvalue())
        self.assertIn('HOLD:',str(ctx.exception))

class FixedPolicyPairSynthetic(unittest.TestCase):
    """Delta-2 direct regression, no root and no filesystem: the plan gate accepts
    the restored live pair, and accepts the declared pending bootstrap pair ONLY
    when the protected backups verify byte-identical to the fixed originals (then
    the plan uses the restored identity, equal to the later restored plan).
    Unknown live bytes or drifted backups stay HOLD. Execution keeps the separate
    live POLICY_RESTORE_NOT_COMPLETE gate in apply.
    """
    def _pair(self, live_exec, live_policy, old_wrapper, old_sudoers):
        from scripts.pr122_account_admission import domestic_bootstrap as b
        files={u.EXEC:live_exec,u.POLICY:live_policy}
        backups={'old-wrapper':old_wrapper,'old-sudoers':old_sudoers}
        with patch.object(u,'read',side_effect=lambda path:files[path]),\
             patch.object(b,'new_wrapper',return_value=b'NEWWRAP'),\
             patch.object(b,'new_policy',return_value=b'NEWPOL'),\
             patch.object(b,'read',side_effect=lambda path,mode=None:backups[str(path).rsplit('/',1)[-1]]):
            return u._fixed_policy_pair()
    def test_restored_pair_returned_directly(self):
        self.assertEqual(self._pair(u.expected_wrapper(),u.expected_policy(),b'X',b'Y'),(u.expected_wrapper(),u.expected_policy()))
    def test_pending_pair_plans_from_verified_backups(self):
        # Same returned identity as the restored case -> pending and restored plans are equal by contract.
        self.assertEqual(self._pair(b'NEWWRAP',b'NEWPOL',u.expected_wrapper(),u.expected_policy()),(u.expected_wrapper(),u.expected_policy()))
    def test_drifted_backup_holds(self):
        with self.assertRaises(RuntimeError) as ctx:self._pair(b'NEWWRAP',b'NEWPOL',b'WRONG',u.expected_policy())
        self.assertEqual(str(ctx.exception),'HOLD:BACKUP_DRIFT')
    def test_unknown_live_bytes_hold(self):
        with self.assertRaises(RuntimeError) as ctx:self._pair(b'OTHER',u.expected_policy(),u.expected_wrapper(),u.expected_policy())
        self.assertEqual(str(ctx.exception),'HOLD:UNCHANGED_FIXED_POLICY')
    def test_apply_keeps_full_live_restore_gate(self):
        import inspect
        src=inspect.getsource(u.apply)
        self.assertIn("need(read(EXEC)==expected_wrapper() and read(POLICY)==expected_policy(),'POLICY_RESTORE_NOT_COMPLETE')",src)

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.geteuid(),0,'Disposable root fixture required')
        self.tmp=tempfile.TemporaryDirectory(prefix='pr122-upgrade-fixture-',dir='/root');self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        base=root/'channel';base.mkdir(mode=0o700);control=base/'upgrades'/'fixed';exe=root/'channel-exec';policy=root/'policy';inputs=root/'inputs';inputs.mkdir(mode=0o700)
        for key,value in {'BASE':base,'CONTROL':control,'EXEC':exe,'POLICY':policy,'INPUT':inputs/'artifact.zip','TRUST':base/'trust.json'}.items():self.stack.enter_context(patch.object(u,key,value))
        self.stack.enter_context(patch.object(u,'owner',return_value=None))
        self.oldcode=b'# old approved fixture\n';self.oldfiles={'boot.py':b'# old fixture'};oldtar,_=archive(self.oldfiles,'a')
        self.stack.enter_context(patch.object(u,'OLD_CODE',u.sha(self.oldcode)));self.stack.enter_context(patch.object(u,'OLD_TAR',u.sha(oldtar)))
        u.create(base/'channel.py',self.oldcode,0o444);u.create(base/u.ARCHIVE,oldtar,0o400);u.create(base/'grant-state.json',b'{"state":"GRANTED"}',0o600)
        old,_,_=u.unpack(oldtar);u.tree_write(base/'candidate',old);u.create(exe,u.expected_wrapper(),0o755);u.create(policy,u.expected_policy(),0o440)
        self.newcode=b'# new approved fixture\n';self.newfiles={'boot.py':b'# new fixture'};tar,manifest=archive(self.newfiles,'b');self.tar=tar
        self.binding={'state':'REBIND_CANDIDATE_ONLY','original_channel_sha256':u.OLD_CODE,'channel_sha256':u.sha(self.newcode),'source_commit':'b'*40,'source_tree':'c'*40,'tar_sha256':u.sha(tar),'manifest_sha256':u.sha(manifest),'archive_members':2,'bound_files':1,'actions':['inspect','plan','apply','rollback'],'sudoers_changed':False,'vendor_file_count':160}
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as z:
            z.writestr(u.ARCHIVE,tar);z.writestr('rebind-candidate/channel.py',self.newcode);z.writestr('rebind-candidate/REBIND_BINDING.json',u.canonical(self.binding))
        u.create(u.INPUT,raw.getvalue(),0o400)
        self.stack.enter_context(patch.object(u,'FROZEN_ZIP',u.sha(raw.getvalue())))
        self.gate=self.stack.enter_context(patch.object(u,'gate',return_value={'id':123,'body_sha256':'d'*64,'rollback_approved':True,'expires_unix':9999999999}))
    def test_actual_upgrade_and_preserved_rollback(self):
        original=u.plan();self.assertFalse(u.CONTROL.exists());result=u.apply();self.assertEqual(result['state'],'BOUND');self.assertEqual(u.read(u.BASE/'channel.py'),self.newcode)
        self.assertEqual(u.read(u.EXEC),u.expected_wrapper());self.assertEqual(u.read(u.POLICY),u.expected_policy())
        with self.assertRaises(RuntimeError):u.apply()
        self.assertEqual(u.rollback()['state'],'ROLLED_BACK');self.assertEqual(u.read(u.BASE/'channel.py'),self.oldcode);self.assertTrue((u.CONTROL/'previous'/u.ARCHIVE).exists())
        self.assertEqual(u.snapshot(u.BASE/'candidate'),original['old']['files'])
        with self.assertRaises(RuntimeError):u.rollback()
    def test_all_activation_interruptions_recover_without_blind_apply_retry(self):
        for stage in ('BACKUP_VERIFIED','STAGED','FENCED','OLD_MOVED','CANDIDATE_MOVED','CODE_REPLACED','TAR_REPLACED','GRANTED'):
            with self.subTest(stage=stage):
                # A separate disposable transaction directory per subcase.
                original=u.CONTROL;self.stack.enter_context(patch.object(u,'CONTROL',original.parent/stage))
                def stop(value):
                    if value==stage:raise RuntimeError('SIMULATED_POWER_LOSS')
                with self.assertRaises(RuntimeError):u.apply(checkpoint=stop)
                with self.assertRaises(RuntimeError):u.apply()
                self.assertEqual(u.rollback()['state'],'ROLLED_BACK');self.assertEqual(u.read(u.BASE/'channel.py'),self.oldcode);self.assertEqual(json.loads(u.read(u.BASE/'grant-state.json')),{'state':'GRANTED'})
    def test_tampered_archive_or_old_candidate_rejected_without_changes(self):
        p=u.BASE/'candidate/boot.py';p.chmod(0o600);p.write_bytes(b'wrong');p.chmod(0o400)
        with self.assertRaises(RuntimeError):u.apply()
        self.assertFalse(u.CONTROL.exists())
    def test_unenrolled_permission_cannot_apply(self):
        self.gate.side_effect=RuntimeError('HOLD:NO_OWNER_ANCHOR')
        with self.assertRaises(RuntimeError):u.apply()
        self.assertFalse(u.CONTROL.exists());self.assertEqual(u.read(u.BASE/'channel.py'),self.oldcode)
    def test_rollback_never_overwrites_unrelated_drift(self):
        u.apply();u.POLICY.chmod(0o600);u.POLICY.write_bytes(b'unrelated');u.POLICY.chmod(0o440)
        with self.assertRaises(RuntimeError):u.rollback()
        self.assertEqual(u.read(u.POLICY),b'unrelated')
    def test_gate_requires_exact_owner_anchor_plan_and_self_hash(self):
        self.gate.side_effect=None;self.gate.return_value={}
        # Exercise the real gate through the original saved implementation.
        p=u.plan();trust={'source_writer_principal':'writer','reviewer_principal':'auditor','custody_evidence_sha256':'e'*64,'comment_id':5,'body_sha256':'f'*64}
        u.create(u.TRUST,u.canonical(trust),0o600)
        with patch.object(u,'__file__',str(u.BASE/'channel.py')):
            with self.assertRaises(RuntimeError):REAL_GATE(p,lambda _: {'id':5,'user':{'login':'wrong'},'issue_url':'/issues/122','body':'not approval'})

    def test_actual_anchor_gate_positive_expired_and_same_subject_denied(self):
        import time
        p=u.plan();a={'decision':'REBIND_APPROVED','transaction':u.TXN,'plan_sha256':u.sha(u.canonical(p)),'new':p['new'],'upgrade_script_sha256':u.OLD_CODE,'max_executions':1,'rollback_approved':True,'issued_unix':int(time.time())-1,'expires_unix':int(time.time())+300}
        body='XUANJUN_CUSTOMER_CHANNEL_REBIND\n'+json.dumps(a)
        trust={'source_writer_principal':'writer','reviewer_principal':'auditor','custody_evidence_sha256':'e'*64,'comment_id':5,'body_sha256':u.sha(body.encode())}
        u.create(u.TRUST,u.canonical(trust),0o600)
        def get(_):return {'id':5,'user':{'login':'huhongchuan0422-creator'},'issue_url':'https://api.github.com/repos/'+u.REPO+'/issues/122','body':body}
        with patch.object(u,'__file__',str(u.BASE/'channel.py')):
            self.assertEqual(REAL_GATE(p,get)['id'],5)
            with patch.object(u.time,'time',return_value=int(time.time())+1000),self.assertRaises(RuntimeError):REAL_GATE(p,get)
            trust['reviewer_principal']='writer';u.replace(u.TRUST,u.canonical(trust),0o600)
            with self.assertRaises(RuntimeError):REAL_GATE(p,get)

REAL_GATE=u.gate



# Unprivileged source/pin checks; no host execution or artifact verification.
class FrozenPinTests(unittest.TestCase):
    def test_exact_audited_zip_pin(self):
        self.assertEqual(u.FROZEN_ZIP, 'a662b76d6c3fb010e0944dea157ff898040007cd69124d498bec26c7701138d3')

    def test_original_baseline_and_transaction_not_reset(self):
        self.assertEqual(u.TXN, 'pr122-customer-preview-channel-20261017')
        self.assertEqual(u.OLD_CODE, '0804e33edac6ad07a711456c0c15708266b2ad8a75c4cb3bdc5964a9b79a96bd')
        self.assertEqual(u.OLD_TAR, '7dd77ef573c338201ddc886b23585422ad4a07ae563a9c6ff92fe5b2f9d97b98')

    def test_wrong_zip_rejected_before_parse(self):
        with patch.object(u, 'read', return_value=b'unapproved offline fixture'), patch.object(u.zipfile, 'ZipFile', side_effect=AssertionError('must not parse')):
            with self.assertRaisesRegex(RuntimeError, 'FROZEN_ZIP_IDENTITY'):
                u.bundle()

    def test_consumed_transaction_rejected_before_host_reads(self):
        with patch.object(u, 'owner'), patch.object(u.os.path, 'lexists', return_value=True), patch.object(u, 'read', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(RuntimeError, 'TRANSACTION_EXISTS_DO_NOT_RETRY'):
                u.plan()

    def test_unprivileged_owner_rejected(self):
        with patch.object(u.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(RuntimeError, 'OWNER_HOST_REQUIRED'):
                u.owner()

    def test_same_writer_reviewer_rejected_before_fetch(self):
        trust={'source_writer_principal':'writer', 'reviewer_principal':'writer', 'custody_evidence_sha256':'e'*64, 'comment_id':5, 'body_sha256':'f'*64}
        with patch.object(u, 'read', return_value=json.dumps(trust).encode()), patch.object(Path, 'stat', return_value=SimpleNamespace(st_mode=0o100600)):
            with self.assertRaisesRegex(RuntimeError, 'INDEPENDENT_OWNER_ANCHOR'):
                u.gate({}, lambda _: self.fail('must not fetch'))

    def test_candidate_code_is_compile_only(self):
        source=Path(u.__file__).read_text()
        tree=ast.parse(source)
        bundle=next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='bundle')
        calls=[n.func.id for n in ast.walk(bundle) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertIn('compile', calls)
        self.assertNotIn('exec', calls)
        self.assertNotIn('eval', calls)
        self.assertNotIn('__import__', calls)

