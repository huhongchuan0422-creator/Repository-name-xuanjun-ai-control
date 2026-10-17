"""Real filesystem channel upgrade/rollback in root-owned disposable fixtures.
Never accesses target paths, sudoers, credentials or services.
"""
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
from scripts import pr122_customer_channel_upgrade as u


def archive(files,commit):
    manifest=u.canonical({'source_commit':commit*40,'source_tree':'c'*40,'files':[{'path':p,'size':len(b),'sha256':u.sha(b)} for p,b in files.items()]});out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz') as t:
        for p,b in {**files,'CUSTOMER_MANIFEST.json':manifest}.items():
            x=tarfile.TarInfo('customer-center/'+p);x.size=len(b);t.addfile(x,io.BytesIO(b))
    return out.getvalue(),manifest

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

