"""Real filesystem isolated transfer tests; synthetic archive, never UK B/C."""
import fcntl
import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from scripts import community_preview_carrier_handoff_admission as h

class HandoffAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=self.tmp.name
        os.mkdir(os.path.join(base,'carrier'),0o700)
        self.parent=os.open(os.path.join(base,'carrier'),os.O_RDONLY|os.O_DIRECTORY)
        os.mkdir('update-journal',0o700,dir_fd=self.parent)
        self.jfd=os.open('update-journal',os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        self.addCleanup(os.close,self.parent);self.addCleanup(os.close,self.jfd)
        self.uid=os.getuid()
        fd=os.open('community-update.lock',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=self.jfd)
        os.close(fd)
        h.writefile(self.parent,h.ENTRY_NAME,b'A_ENTRY_FIXTURE',self.uid)
        self.entry=os.open(h.ENTRY_NAME,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.parent)
        self.addCleanup(os.close,self.entry)
        self.entry_id=h.ident(os.fstat(self.entry))
        self.parent_id=h.parent_ident(os.fstat(self.parent))
        self.journal_id=h.dirident(os.fstat(self.jfd))
        old_archive_path=os.environ.get('HANDOFF_OLD_ARCHIVE')
        new_archive_path=os.environ.get('HANDOFF_NEW_ARCHIVE')
        if old_archive_path and new_archive_path:
            old_archive=open(old_archive_path,'rb').read()
            old_manifest=open(os.environ['HANDOFF_OLD_MANIFEST'],'rb').read()
            new_archive=open(new_archive_path,'rb').read()
            new_manifest=open(os.environ['HANDOFF_NEW_MANIFEST'],'rb').read()
            self.old=h.members(old_archive,h.OLD_MANIFEST,h.OLD_ARCHIVE)
            self.new=h.members(new_archive,h.NEW_MANIFEST,h.NEW_ARCHIVE)
            if self.old['manifest.json']!=old_manifest or self.new['manifest.json']!=new_manifest:
                raise AssertionError('OUTER_AND_INNER_MANIFEST_MISMATCH')
            self.archive=new_archive
        else:
            old_loader=b'OLD_LOADER'
            old_meta={'format':1,'mode':'STOPPED_HANDOFF_V1',
            'install_root':'/opt/xuanjun-community-preview/control-stopped-v1',
            'updates_enabled':False,
            'files':{'loader.py':{'bytes':len(old_loader),'sha256':h.sha(old_loader),
                                 'uid':0,'mode':'0600'}}}
            self.old={'manifest.json':h.canonical(old_meta),'loader.py':old_loader}
            self.new={'manifest.json':b'','loader.py':b'NEW_LOADER'}
            meta={'format':1,'mode':'STOPPED_HANDOFF_V1',
              'install_root':'/opt/xuanjun-community-preview/control-stopped-v1',
              'updates_enabled':False,
              'files':{'loader.py':{'bytes':len(self.new['loader.py']),
                                   'sha256':h.sha(self.new['loader.py']),'uid':0,'mode':'0600'}}}
            self.new['manifest.json']=h.canonical(meta)
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:
                for key,body in self.new.items():
                    info=zipfile.ZipInfo(key);info.create_system=3
                    info.external_attr=0o100600<<16;info.compress_type=zipfile.ZIP_DEFLATED
                    z.writestr(info,body)
            self.archive=data.getvalue()
            self.stack=self.enterContext(patch.multiple(h,OLD_MANIFEST=h.sha(self.old['manifest.json']),
                                                          NEW_MANIFEST=h.sha(self.new['manifest.json']),
                                                          NEW_ARCHIVE=h.sha(self.archive)))
        h.build_tree(self.parent,self.old,self.uid,name=h.TARGET)
        self.history_bodies={
            'b_intent':('original-B-intent.json',b'PRESERVED_OLD_B_INTENT',self.jfd),
            'b_approval':('bc-b-approval.json',b'EXPIRED_OLD_B_APPROVAL',self.parent),
            'freeze':('writer-freeze-reference.json',b'OLD_FREEZE_EVIDENCE',self.parent),
            'old_stage_permit':('site-prepare-approval.json',b'EXPIRED_OLD_STAGE_PERMIT',self.parent)}
        self.history_refs={}
        for key,(name,body,pfd) in self.history_bodies.items():
            h.writefile(pfd,name,body,self.uid)
            st=os.stat(name,dir_fd=pfd,follow_symlinks=False)
            self.history_refs[key]=(pfd,name,h.parent_ident(os.fstat(pfd)),h.ident(st),h.sha(body))

    def enterContext(self,context):
        obj=context.__enter__();self.addCleanup(context.__exit__,None,None,None);return obj

    def execute(self,fault=None):
        return h.execute(self.parent,self.jfd,self.entry,self.old,self.archive,self.uid,
                         self.parent_id,self.journal_id,self.entry_id,'isolated-attempt-0001',
                         history_refs=self.history_refs,fault=fault)

    def test_legal_exchange_and_owned_rollback(self):
        self.assertEqual(self.execute()['state'],'SWAPPED_OLD_RETAINED_IN_STAGE')
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.uid,self.old,self.new,self.parent_id,self.journal_id,self.entry_id,self.history_refs)['state'],
                         'SWAPPED_OLD_RETAINED_IN_STAGE')
        self.assertEqual(h.rollback(self.parent,self.jfd,self.entry,self.old,self.new,self.uid,self.parent_id,self.journal_id,self.entry_id,self.history_refs)['state'],
                         'ROLLED_BACK_OLD_TARGET_RESTORED_NEW_STAGE_RETAINED')
        self.assertIsNotNone(h.childstat(self.jfd,h.ROLLBACK_INTENT))
        self.assertIsNotNone(h.childstat(self.jfd,h.ROLLBACK_RESULT))
        with self.assertRaisesRegex(h.Hold,'ROLLBACK_ALREADY_ATTEMPTED'):
            h.rollback(self.parent,self.jfd,self.entry,self.old,self.new,self.uid,self.entry_id)
        target=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:self.assertEqual(h.readfile(target,'loader.py',self.uid),self.old['loader.py'])
        finally:os.close(target)

    def test_duplicate_attempt_holds(self):
        self.execute()
        with self.assertRaisesRegex(h.Hold,'EXISTING_TRANSACTION_INSPECT_ONLY'):self.execute()

    def test_wrong_identity_holds_without_stage(self):
        with self.assertRaisesRegex(h.Hold,'PARENT_IDENTITY_CHANGED'):
            h.execute(self.parent,self.jfd,self.entry,self.old,self.archive,self.uid,[],self.journal_id,self.entry_id,'isolated-attempt-0001',history_refs=self.history_refs)
        self.assertIsNone(h.childstat(self.jfd,h.STATE))

    def test_wrong_candidate_sha_holds(self):
        with self.assertRaisesRegex(h.Hold,'CANDIDATE_ARCHIVE_SHA'):h.execute(
            self.parent,self.jfd,self.entry,self.old,b'bad',self.uid,self.parent_id,
            self.journal_id,self.entry_id,'isolated-attempt-0001',history_refs=self.history_refs)
        self.assertIsNone(h.childstat(self.jfd,h.STATE))

    def test_preintent_is_durable_before_stage_and_reopen_is_inspect_only(self):
        def fault(where):
            if where=='preintent_fsynced':raise RuntimeError('PRESTAGE_STOP')
        with self.assertRaisesRegex(RuntimeError,'PRESTAGE_STOP'):self.execute(fault)
        self.assertIsNotNone(h.childstat(self.jfd,h.PREINTENT))
        self.assertIsNone(h.childstat(self.parent,h.STAGE))
        self.assertEqual(h.status(self.parent,self.jfd,self.uid,self.old,self.new)['state'],
                         'UNKNOWN_INSPECT_ONLY')
        with self.assertRaisesRegex(h.Hold,'EXISTING_TRANSACTION_INSPECT_ONLY'):self.execute()

    def test_active_attempt_prevents_first_persistent_write(self):
        h.writefile(self.jfd,'active-attempt.json',b'UNKNOWN_ACTIVE',self.uid)
        with self.assertRaisesRegex(h.Hold,'ACTIVE_BUSINESS_ATTEMPT'):self.execute()
        self.assertIsNone(h.childstat(self.jfd,h.PREINTENT))

    def test_changed_old_member_holds_before_intent(self):
        self.old['loader.py']=b'NOT_OLD_LOADER'
        with self.assertRaisesRegex(h.Hold,'OLD_MEMBER_MANIFEST_BINDING'):self.execute()
        self.assertIsNone(h.childstat(self.jfd,h.PREINTENT))

    def test_manifest_unchanged_disk_and_inventory_mutated_holds(self):
        # A matching disk and caller-provided inventory must not bypass fixed manifest.
        fake=b'FAKE_LOADER!'
        self.old['loader.py']=fake
        target=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:
            fd=os.open('loader.py',os.O_WRONLY|os.O_TRUNC,dir_fd=target)
            try:os.write(fd,fake)
            finally:os.close(fd)
        finally:os.close(target)
        with self.assertRaisesRegex(h.Hold,'OLD_MEMBER_MANIFEST_BINDING'):
            self.execute()
        self.assertIsNone(h.childstat(self.jfd,h.PREINTENT))

    def test_rollback_active_attempt_refused_before_swap(self):
        self.execute()
        h.writefile(self.jfd,'active-attempt.json',b'INFLIGHT',self.uid)
        with self.assertRaisesRegex(h.Hold,'ROLLBACK_CONFLICT'):
            h.rollback(self.parent,self.jfd,self.entry,self.old,self.new,self.uid,self.entry_id)
        self.assertEqual(h.status(self.parent,self.jfd,self.uid,self.old,self.new)['state'],
                         'SWAPPED_OLD_RETAINED_IN_STAGE')

    def test_crash_after_intent_never_retries(self):
        def fault(where):
            if where=='intent_fsynced':raise RuntimeError('SYNTHETIC_CRASH')
        with self.assertRaisesRegex(RuntimeError,'SYNTHETIC_CRASH'):self.execute(fault)
        self.assertEqual(h.status(self.parent,self.jfd,self.uid,self.old,self.new)['state'],
                         'PREPARED_OR_REVERTED')
        with self.assertRaisesRegex(h.Hold,'EXISTING_TRANSACTION_INSPECT_ONLY'):self.execute()

    def test_after_exchange_error_preserves_old_and_unknown(self):
        def fault(where):
            if where=='after_exchange':raise RuntimeError('SYNTHETIC_AFTER')
        with self.assertRaisesRegex(h.Hold,'POST_SWITCH_UNKNOWN_INSPECT_ONLY'):self.execute(fault)
        self.assertEqual(h.status(self.parent,self.jfd,self.uid,self.old,self.new)['state'],
                         'SWAPPED_OLD_RETAINED_IN_STAGE')

    def test_foreign_replacement_refuses_rollback(self):
        self.execute()
        fd=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:
            file=os.open('loader.py',os.O_WRONLY,dir_fd=fd)
            try:os.write(file,b'BAD')
            finally:os.close(file)
        finally:os.close(fd)
        with self.assertRaises(h.Hold):h.rollback(self.parent,self.jfd,self.entry,self.old,self.new,self.uid,self.entry_id)

    def test_contention_original_lock_holds(self):
        second=os.open(h.LOCK,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.jfd)
        try:
            fcntl.flock(second,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises((BlockingIOError,OSError)):self.execute()
        finally:fcntl.flock(second,fcntl.LOCK_UN);os.close(second)

    def test_original_evidence_unmodified(self):
        before=self.history_bodies['b_intent'][1]
        self.execute()
        self.assertEqual(h.readfile(self.jfd,self.history_bodies['b_intent'][0],self.uid),before)

if __name__=='__main__':unittest.main()
