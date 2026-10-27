import hashlib
import json
import os
import tempfile
import unittest
import io
import pty
import re
import select
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import community_preview_prepared_resume_delivery as d
from scripts import community_preview_update_checkpoint as u


def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def sha(v):return hashlib.sha256(v).hexdigest()


class PreparedResumeDelivery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.base=root/'opt/xuanjun-community-preview';self.base.mkdir(parents=True,mode=0o700)
        self.journal=self.base/'update-journal';self.journal.mkdir(mode=0o700)
        self.backup=self.base/'backup-2330-to-f131-v1';self.backup.mkdir(mode=0o700)
        self.attempt=self.journal/'attempt';self.attempt.mkdir(mode=0o700)
        (self.journal/'community-update.lock').write_bytes(b'lock');os.chmod(self.journal/'community-update.lock',0o600)
        (self.base/'site-prepare-v1.py').write_bytes(b'entry');os.chmod(self.base/'site-prepare-v1.py',0o600)
        self.marker=root/'called'
        loader=("def load(value):\n class M:\n  @staticmethod\n  def main(args):\n"
                f"   with open({str(self.marker)!r},'ab') as f:f.write((' '.join(args)+'\\n').encode())\n"
                "   return 0\n return M\n").encode()
        old_extra=b'old';new_extra=b'new'
        self.old_bodies={'loader.py':loader,'scripts/value.py':old_extra}
        self.new_bodies={'loader.py':loader,'scripts/value.py':new_extra}
        self.old_manifest=self.manifest(self.old_bodies);self.new_manifest=self.manifest(self.new_bodies)
        self.old_bodies['manifest.json']=self.old_manifest;self.new_bodies['manifest.json']=self.new_manifest
        self.write_tree(self.base/'control-stopped-v1',self.old_bodies)
        proof=canon({'proof':'preserved'});active=json.dumps({'attempt':'attempt','plan_sha256':'a'*64},sort_keys=True).encode()
        checkpoint=canon({'approval_sha256':'b'*64,'handoff_sha256':'c'*64,'new_id':None,'phase':'PREPARED','plan_sha256':'a'*64,'sequence':1})
        self.write(self.backup/'stopped-handoff-v1.json',proof);self.write(self.journal/'active-attempt.json',active)
        self.write(self.attempt/'checkpoint.json',checkpoint);self.write(self.attempt/'event-000001.json',checkpoint)
        self.write(self.base/'bc-c-resume-approval-old.json',canon({'old':True}))
        real_read=d.read
        def fixture_read(path,limit=8*1024*1024,uid=0,mode=0o600):
            return real_read(path,limit,os.getuid() if uid==0 else uid,mode)
        self.patches=[
            patch.object(d,'BASE',str(self.base)),patch.object(d,'CONTROL',str(self.base/'control-stopped-v1')),
            patch.object(d,'JOURNAL',str(self.journal)),patch.object(d,'ATTEMPT','attempt'),patch.object(d,'PLAN','a'*64),
            patch.object(d,'PROOF',str(self.backup/'stopped-handoff-v1.json')),patch.object(d,'ACTIVE',str(self.journal/'active-attempt.json')),
            patch.object(d,'CHECKPOINT',str(self.attempt/'checkpoint.json')),patch.object(d,'EVENT',str(self.attempt/'event-000001.json')),
            patch.object(d,'PROOF_SHA',sha(proof)),patch.object(d,'ACTIVE_SHA',sha(active)),patch.object(d,'PREPARED_SHA',sha(checkpoint)),
            patch.object(d,'OLD_MANIFEST',sha(self.old_manifest)),patch.object(d,'NEW_MANIFEST',sha(self.new_manifest)),patch.object(d,'LOADER_SHA',sha(loader)),
            patch.object(d,'DELIVERY',str(self.base/'delivery')),patch.object(d,'INTENT',str(self.base/'delivery/intent.json')),
            patch.object(d,'RECEIPT',str(self.base/'delivery/receipt.json')),patch.object(d,'STAGE','stage'),patch.object(d,'RETAINED','retained'),
            patch.object(d,'source',lambda:(json.loads(self.new_manifest),dict(self.new_bodies))),
            patch.object(d,'read',fixture_read),patch.object(d.os,'fchown',lambda *args:None),
        ]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def manifest(self,bodies):
        return canon({'format':1,'mode':'STOPPED_HANDOFF_V1','install_root':str(self.base/'control-stopped-v1'),'updates_enabled':False,
                      'files':{n:{'bytes':len(b),'sha256':sha(b),'uid':0,'mode':'0600'} for n,b in bodies.items()}})
    def write(self,path,body):path.write_bytes(body);os.chmod(path,0o600)
    def write_tree(self,root,bodies):
        root.mkdir(mode=0o700)
        for name,body in bodies.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            for parent in list(path.parents):
                if parent==root.parent:break
                os.chmod(parent,0o700)
            self.write(path,body)
    def append(self,sequence,phase,new_id=None):
        value=canon({'approval_sha256':'b'*64,'handoff_sha256':'c'*64,
                     'new_id':new_id,'phase':phase,'plan_sha256':'a'*64,
                     'sequence':sequence})
        self.write(self.attempt/('event-%06d.json'%sequence),value)
        self.write(self.attempt/'checkpoint.json',value)
    def test_existing_prepared_atomic_update_resume_query_and_recover(self):
        before=(self.base/'bc-c-resume-approval-old.json').read_bytes()
        self.assertEqual(d.inspect()['phase'],'PREPARED')
        receipt=d.update();self.assertTrue(receipt['updated'])
        self.assertEqual(d.tree_manifest(d.CONTROL)[0],d.NEW_MANIFEST)
        self.assertTrue((self.base/'retained').is_dir())
        self.assertEqual((self.base/'bc-c-resume-approval-old.json').read_bytes(),before)
        self.assertEqual(d.inspect()['new_id'],None)
        self.assertEqual(d.invoke('resume'),0)
        for sequence,phase,new_id in (
            (2,'STOPPED_HANDOFF_ACCEPTED',None),(3,'OLD_RENAME_INTENT',None),
            (4,'OLD_RETAINED',None),(5,'NEW_RUN_INTENT',None),
            (6,'NEW_KNOWN','d'*64),(7,'KNOWN_FAILURE','d'*64)):
            self.append(sequence,phase,new_id)
        queried=d.query();self.assertEqual((queried['phase'],queried['sequence'],queried['new_id']),('KNOWN_FAILURE',7,'d'*64))
        self.assertEqual(d.invoke('recover'),0)
        for sequence,phase in ((8,'RECOVERY_STOP_NEW_INTENT'),
                               (9,'RECOVERY_RENAME_NEW_INTENT'),
                               (10,'RECOVERY_RESTORE_OLD_INTENT'),
                               (11,'RECOVERY_START_OLD_INTENT'),
                               (12,'ROLLED_BACK_PREVIEW_HOLD')):
            self.append(sequence,phase,'d'*64)
        self.assertEqual(d.query()['phase'],'ROLLED_BACK_PREVIEW_HOLD')
        self.assertEqual(self.marker.read_text().splitlines(),['--reopen-prepared','--recover-known-failure'])

    def test_query_accepts_exact_normal_success_history_and_rejects_jump(self):
        d.update()
        for sequence,phase,new_id in (
            (2,'STOPPED_HANDOFF_ACCEPTED',None),(3,'OLD_RENAME_INTENT',None),
            (4,'OLD_RETAINED',None),(5,'NEW_RUN_INTENT',None),
            (6,'NEW_KNOWN','d'*64),(7,'COMMITTED','d'*64)):
            self.append(sequence,phase,new_id)
        self.assertEqual(d.query()['phase'],'COMMITTED')
        bad=canon({'approval_sha256':'b'*64,'handoff_sha256':'c'*64,
                   'new_id':'d'*64,'phase':'RECOVERY_START_OLD_INTENT',
                   'plan_sha256':'a'*64,'sequence':7})
        self.write(self.attempt/'event-000007.json',bad);self.write(self.attempt/'checkpoint.json',bad)
        with self.assertRaisesRegex(d.Hold,'EVENT_PHASE_TRANSITION'):d.query()

    def test_unknown_preserves_known_id_and_exact_id_contract_matches_checkpoint(self):
        d.update()
        for sequence,phase,new_id in (
            (2,'STOPPED_HANDOFF_ACCEPTED',None),(3,'OLD_RENAME_INTENT',None),
            (4,'OLD_RETAINED',None),(5,'NEW_RUN_INTENT',None),
            (6,'NEW_KNOWN','d'*64),(7,d.HOLD_PHASE,'d'*64)):
            self.append(sequence,phase,new_id)
        result=d.query();self.assertEqual((result['phase'],result['new_id']),(d.HOLD_PHASE,'d'*64))
        cases=(
            (d.HOLD_PHASE,'x'*64,'CHECKPOINT_ID'),
            (d.HOLD_PHASE,'d'*63,'CHECKPOINT_ID'),
            ('NEW_KNOWN',None,'CHECKPOINT_ID_REQUIRED'),
            ('OLD_RETAINED','d'*64,'CHECKPOINT_UNEXPECTED_ID'),
            (d.HOLD_PHASE,'e'*64,'EVENT_ID_CHANGED'),
        )
        for phase,new_id,reason in cases:
            with self.subTest(phase=phase,new_id=new_id,reason=reason):
                self.append(7,phase,new_id)
                with self.assertRaisesRegex(d.Hold,reason):d.query()
        self.append(7,d.HOLD_PHASE,None)
        with self.assertRaisesRegex(d.Hold,'EVENT_ID_CHANGED'):d.query()

    def test_read_side_acceptance_matches_original_validator_for_every_phase_and_id_class(self):
        original=object.__new__(u.Journal)
        original.plan={'plan_sha256':'a'*64}
        original.handoff_binding={'approval_sha256':'b'*64,'handoff_sha256':'c'*64}
        ids=(None,'d'*64,'d'*63,'x'*64,1)
        for phase in sorted(u.TRANSITIONS):
            for new_id in ids:
                value={'approval_sha256':'b'*64,'handoff_sha256':'c'*64,
                       'new_id':new_id,'phase':phase,'plan_sha256':'a'*64,
                       'sequence':1}
                with self.subTest(phase=phase,new_id=new_id):
                    try:original.validate_record(value);expected=True
                    except u.Hold:expected=False
                    try:d.validate_journal_record(value);actual=True
                    except d.Hold:actual=False
                    self.assertEqual(actual,expected)

    def test_recover_refuses_prepared_without_calling_loader(self):
        d.update()
        with self.assertRaisesRegex(d.Hold,'KNOWN_FAILURE_REQUIRED'):d.invoke('recover')
        self.assertFalse(self.marker.exists())

    def test_cli_preserves_success_exit_and_does_not_claim_unexecuted_after_boundary(self):
        with patch.object(d,'main',return_value=0):self.assertEqual(d.cli(['resume']),0)
        output=io.StringIO()
        with patch.object(d,'main',side_effect=d.Hold('BOUNDARY_HOLD')),redirect_stdout(output):
            self.assertEqual(d.cli(['resume']),2)
        self.assertEqual(json.loads(output.getvalue())['site_executed'],'UNKNOWN')
        output=io.StringIO()
        with patch.object(d,'main',side_effect=d.Hold('INSPECT_HOLD')),redirect_stdout(output):
            self.assertEqual(d.cli(['inspect']),2)
        self.assertIs(json.loads(output.getvalue())['site_executed'],False)

    def test_entry_file_replacement_during_stable_read_is_rejected(self):
        path=Path(self.tmp.name)/'entry.py';self.write(path,b'x'*70000)
        real_read=os.read;changed=[]
        def replace_after_first(fd,size):
            part=real_read(fd,size)
            if not changed:
                replacement=path.with_suffix('.new');self.write(replacement,b'y'*70000)
                os.replace(replacement,path);changed.append(True)
            return part
        with patch.object(d.os,'read',replace_after_first),self.assertRaisesRegex(d.Hold,'FILE_CHANGED_DURING_READ'):
            d.read(str(path),131072,os.getuid(),0o600)

    def test_shell_bootstrap_preserves_real_pty_stdin(self):
        fixture=Path(self.tmp.name)/'delivery.py'
        body=("import os\n"
              "def cli(args):\n"
              " print('TTY='+str(os.isatty(0)),flush=True)\n"
              " return 0 if input('PROMPT:')=='ACK' else 2\n").encode()
        self.write(fixture,body)
        source=Path('deploy/community-preview/issue76-prepared-resume-r18.sh').read_text()
        source=source.replace('/home/admin/community_preview_prepared_resume_delivery.py',str(fixture))
        source=re.sub(r"expected='[0-9a-f]{64}'","expected='%s'"%sha(body),source,count=1)
        source=source.replace("pwd.getpwnam('admin').pw_uid",str(os.getuid()))
        source=source.replace('sudo -n /usr/bin/python3',sys.executable)
        wrapper=Path(self.tmp.name)/'entry.sh';wrapper.write_text(source);os.chmod(wrapper,0o700)
        master,slave=pty.openpty()
        process=subprocess.Popen([str(wrapper),'resume'],stdin=slave,stdout=slave,stderr=slave,close_fds=True)
        os.close(slave);output=b''
        try:
            while b'PROMPT:' not in output:
                ready,_,_=select.select([master],[],[],5);self.assertTrue(ready,'PTY_PROMPT_TIMEOUT')
                output+=os.read(master,4096)
            os.write(master,b'ACK\n');self.assertEqual(process.wait(timeout=5),0)
        finally:
            os.close(master)
            if process.poll() is None:process.kill();process.wait()
        self.assertIn(b'TTY=True',output)
    def test_interruption_after_exchange_reopens_without_second_exchange(self):
        original=d.exchange;calls=[]
        def crash(a,b):original(a,b);calls.append((a,b));raise d.Hold('INJECTED_AFTER_EXCHANGE')
        with patch.object(d,'exchange',crash):
            with self.assertRaisesRegex(d.Hold,'INJECTED_AFTER_EXCHANGE'):d.update()
        self.assertEqual(d.tree_manifest(d.CONTROL)[0],d.NEW_MANIFEST)
        receipt=d.update();self.assertTrue(receipt['updated']);self.assertEqual(len(calls),1)
    def test_interruption_after_retaining_old_tree_finishes_receipt_only(self):
        original=d.write_exclusive;crashed=[]
        def crash(path,raw):
            if path==d.RECEIPT and not crashed:
                crashed.append(True);raise d.Hold('INJECTED_BEFORE_RECEIPT')
            return original(path,raw)
        with patch.object(d,'write_exclusive',crash):
            with self.assertRaisesRegex(d.Hold,'INJECTED_BEFORE_RECEIPT'):d.update()
        self.assertEqual(d.tree_manifest(d.CONTROL)[0],d.NEW_MANIFEST)
        self.assertEqual(d.tree_manifest(str(self.base/'retained'))[0],d.OLD_MANIFEST)
        self.assertTrue(d.update()['updated'])
    def test_wrong_prepared_state_or_old_carrier_holds_before_exchange(self):
        changed=canon({'approval_sha256':'b'*64,'handoff_sha256':'c'*64,'new_id':'d'*64,'phase':'PREPARED','plan_sha256':'a'*64,'sequence':1})
        self.write(self.attempt/'checkpoint.json',changed)
        with self.assertRaisesRegex(d.Hold,'EXACT_PREPARED_BYTES_REQUIRED'):d.update()


if __name__=='__main__':unittest.main()
