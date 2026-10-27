import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import community_preview_prepared_resume_delivery as d


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
        proof=canon({'proof':'preserved'});active=canon({'attempt':'attempt','plan_sha256':'a'*64})
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
    def test_existing_prepared_atomic_update_resume_query_and_recover(self):
        before=(self.base/'bc-c-resume-approval-old.json').read_bytes()
        self.assertEqual(d.inspect()['phase'],'PREPARED')
        receipt=d.update();self.assertTrue(receipt['updated'])
        self.assertEqual(d.tree_manifest(d.CONTROL)[0],d.NEW_MANIFEST)
        self.assertTrue((self.base/'retained').is_dir())
        self.assertEqual((self.base/'bc-c-resume-approval-old.json').read_bytes(),before)
        self.assertEqual(d.inspect()['new_id'],None)
        self.assertEqual(d.invoke('resume'),0);self.assertEqual(d.invoke('recover'),0)
        self.assertEqual(self.marker.read_text().splitlines(),['--reopen-prepared','--recover-known-failure'])
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
