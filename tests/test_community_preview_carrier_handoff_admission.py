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
        for name in ('carrier','journal'):
            os.mkdir(os.path.join(base,name),0o700)
        self.parent=os.open(os.path.join(base,'carrier'),os.O_RDONLY|os.O_DIRECTORY)
        self.jfd=os.open(os.path.join(base,'journal'),os.O_RDONLY|os.O_DIRECTORY)
        self.addCleanup(os.close,self.parent);self.addCleanup(os.close,self.jfd)
        self.uid=os.getuid()
        fd=os.open('community-update.lock',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=self.jfd)
        os.close(fd)
        self.entry_path=os.path.join(base,'entry')
        with open(self.entry_path,'wb') as file:file.write(b'A_ENTRY_FIXTURE')
        os.chmod(self.entry_path,0o600)
        self.entry=os.open(self.entry_path,os.O_RDONLY|os.O_NOFOLLOW)
        self.addCleanup(os.close,self.entry)
        self.entry_id=h.ident(os.fstat(self.entry))
        self.parent_id=h.parent_ident(os.fstat(self.parent))
        self.old={'manifest.json':b'OLD_TEST_MANIFEST','loader.py':b'OLD_LOADER'}
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
        h.build_tree(self.parent,self.old,self.uid) if False else None
        os.mkdir(h.TARGET,0o700,dir_fd=self.parent)
        fd=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:
            for key,body in self.old.items():h.writefile(fd,key,body,self.uid)
        finally:os.close(fd)

    def enterContext(self,context):
        obj=context.__enter__();self.addCleanup(context.__exit__,None,None,None);return obj

    def execute(self,fault=None):
        return h.execute(self.parent,self.jfd,self.entry,self.old,self.archive,self.uid,
                         self.parent_id,self.entry_id,'isolated-attempt-0001',fault=fault)

    def test_legal_exchange_and_owned_rollback(self):
        self.assertEqual(self.execute()['state'],'SWAPPED_OLD_RETAINED_IN_STAGE')
        self.assertEqual(h.status(self.parent,self.jfd,self.uid,self.old,self.new)['state'],
                         'SWAPPED_OLD_RETAINED_IN_STAGE')
        self.assertEqual(h.rollback(self.parent,self.jfd,self.entry,self.old,self.new,self.uid,self.entry_id)['state'],
                         'ROLLED_BACK_OLD_TARGET_RESTORED_NEW_STAGE_RETAINED')
        self.assertEqual(h.readfile(os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent),
                                    'loader.py',self.uid),b'OLD_LOADER')

    def test_duplicate_attempt_holds(self):
        self.execute()
        with self.assertRaisesRegex(h.Hold,'EXISTING_TRANSACTION_INSPECT_ONLY'):self.execute()

    def test_wrong_identity_holds_without_stage(self):
        with self.assertRaisesRegex(h.Hold,'PARENT_IDENTITY_CHANGED'):
            h.execute(self.parent,self.jfd,self.entry,self.old,self.archive,self.uid,[],self.entry_id,'isolated-attempt-0001')
        self.assertIsNone(h.childstat(self.jfd,h.STATE))

    def test_wrong_candidate_sha_holds(self):
        with self.assertRaisesRegex(h.Hold,'CANDIDATE_ARCHIVE_SHA'):h.execute(
            self.parent,self.jfd,self.entry,self.old,b'bad',self.uid,self.parent_id,
            self.entry_id,'isolated-attempt-0001')
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
        with self.assertRaisesRegex(h.Hold,'TREE_BYTES_CHANGED'):self.execute()
        self.assertIsNone(h.childstat(self.jfd,h.PREINTENT))

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
        fd=os.open('original-B-intent',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=self.jfd)
        os.write(fd,b'HISTORICAL_INTENT');os.close(fd)
        self.execute()
        self.assertEqual(h.readfile(self.jfd,'original-B-intent',self.uid),b'HISTORICAL_INTENT')

if __name__=='__main__':unittest.main()
