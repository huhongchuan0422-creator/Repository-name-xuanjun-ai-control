"""Isolated filesystem transaction tests; CI injects exact nested 1d/005c archives, never UK B/C."""
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
from types import SimpleNamespace
from scripts import community_preview_carrier_handoff_admission as h
from scripts import community_preview_carrier_handoff_call as handoff_call
from scripts import community_preview_carrier_handoff_entry as fixed_entry

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
        self.lease=os.open(h.LOCK,os.O_RDWR|os.O_NOFOLLOW,dir_fd=self.jfd)
        self.addCleanup(os.close,self.lease)
        self.lock_id=h.ident(os.fstat(self.lease))
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
            self.old_archive_bytes=old_archive
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
            old_data=io.BytesIO()
            with zipfile.ZipFile(old_data,'w',zipfile.ZIP_DEFLATED) as z:
                for key,body in self.old.items():
                    info=zipfile.ZipInfo(key);info.create_system=3;info.external_attr=0o100600<<16;info.compress_type=zipfile.ZIP_DEFLATED
                    z.writestr(info,body)
            self.old_archive_bytes=old_data.getvalue()
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
                                                          OLD_ARCHIVE=h.sha(self.old_archive_bytes),
                                                          NEW_MANIFEST=h.sha(self.new['manifest.json']),
                                                          NEW_ARCHIVE=h.sha(self.archive)))
        h.build_tree(self.parent,self.old,self.uid,name=h.TARGET)
        self.history_bodies={
            'b_intent':(h.HISTORY_NAMES['b_intent'],b'PRESERVED_OLD_B_INTENT',self.jfd),
            'b_approval':('bc-b-approval.json',b'EXPIRED_OLD_B_APPROVAL',self.parent),
            'freeze':('writer-freeze-reference.json',b'OLD_FREEZE_EVIDENCE',self.parent),
            'old_stage_permit':('site-prepare-approval.json',b'EXPIRED_OLD_STAGE_PERMIT',self.parent)}
        self.history_refs={}
        for key,(name,body,pfd) in self.history_bodies.items():
            h.writefile(pfd,name,body,self.uid)
            st=os.stat(name,dir_fd=pfd,follow_symlinks=False)
            self.history_refs[key]=(pfd,name,h.parent_ident(os.fstat(pfd)),h.ident(st),h.sha(body))
        for key,name in h.HISTORY_NAMES.items():
            if key not in self.history_refs:
                pfd=self.jfd if key in h.JOURNAL_HISTORY_KEYS else self.parent
                self.history_refs[key]=(pfd,name,h.parent_ident(os.fstat(pfd)),None,None)

    def enterContext(self,context):
        obj=context.__enter__();self.addCleanup(context.__exit__,None,None,None);return obj

    def execute(self,fault=None):
        return h.execute(self.parent,self.jfd,self.entry,self.lease,self.old,self.archive,self.uid,
                         self.parent_id,self.journal_id,self.entry_id,self.lock_id,'isolated-attempt-0001',
                         history_refs=self.history_refs,fault=fault)

    def test_artifact_redirect_strips_authorization_and_signed_url_is_not_logged(self):
        req=__import__('urllib.request',fromlist=['Request']).Request(
            'https://api.github.com/repos/example/repo/actions/artifacts/123/zip',
            headers={'Authorization':'Bearer DO_NOT_FORWARD','Accept':'application/vnd.github+json',
                     'User-Agent':'issue76-fixture-verifier'})
        handler=h.SafeArtifactRedirect()
        redirected=handler.redirect_request(req,None,302,'Found',{},'https://productionresultssa.blob.core.windows.net/actions-results/signed?sig=SECRET')
        self.assertIsNone(redirected.get_header('Authorization'))
        self.assertIsNone(redirected.get_header('Cookie'))
        self.assertEqual(redirected.get_header('Accept'),'application/vnd.github+json')
        self.assertNotIn('SECRET',repr(redirected.headers))

    def test_artifact_redirect_rejects_http_and_unlisted_hosts(self):
        req=__import__('urllib.request',fromlist=['Request']).Request(
            'https://api.github.com/repos/example/repo/actions/artifacts/123/zip',
            headers={'Authorization':'Bearer DO_NOT_FORWARD'})
        handler=h.SafeArtifactRedirect()
        for target in ('http://productionresultssa.blob.core.windows.net/a?sig=x',
                       'https://evil.example/a?sig=x',
                       'https://api.github.com.evil.example/repos/a/b/actions/artifacts/123/zip',
                       'https://api.github.com/repos/example/repo/issues/1'):
            with self.assertRaisesRegex(h.Hold,'ARTIFACT_REDIRECT_DESTINATION_REJECTED'):
                handler.redirect_request(req,None,302,'Found',{},target)

    def test_legal_exchange_and_owned_rollback(self):
        self.assertEqual(self.execute()['state'],'SWAPPED_OLD_RETAINED_IN_STAGE')
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
            self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
            'SWAPPED_OLD_RETAINED_IN_STAGE')
        self.assertEqual(h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
            self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
            'ROLLED_BACK_OLD_TARGET_RESTORED_NEW_STAGE_RETAINED')
        self.assertIsNotNone(h.childstat(self.jfd,h.ROLLBACK_INTENT))
        self.assertIsNotNone(h.childstat(self.jfd,h.ROLLBACK_RESULT))
        with self.assertRaisesRegex(h.Hold,'ROLLBACK_ALREADY_ATTEMPTED'):
            h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        target=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:self.assertEqual(h.readfile(target,'loader.py',self.uid),self.old['loader.py'])
        finally:os.close(target)

    def test_adapter_calls_real_rollback_with_fixed_archive_fixture(self):
        self.execute()
        ctx=SimpleNamespace(
            host_id=h.HOST,authority_check=lambda:True,
            parent_fd=self.parent,journal_fd=self.jfd,entry_fd=self.entry,lease_fd=self.lease,
            uid=self.uid,parent_identity=self.parent_id,journal_identity=self.journal_id,
            entry_identity=self.entry_id,lock_identity=self.lock_id,
            history_refs=self.history_refs,old_archive_bytes=self.old_archive_bytes,
            new_archive_bytes=self.archive,attempt='isolated-attempt-0001')
        result=handoff_call.rollback_from_original_entry(ctx)
        self.assertEqual(result['state'],'ROLLED_BACK_OLD_TARGET_RESTORED_NEW_STAGE_RETAINED')
        target=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:
            self.assertEqual(h.readfile(target,'loader.py',self.uid),self.old['loader.py'])
            self.assertEqual(h.readfile(target,'manifest.json',self.uid),self.old['manifest.json'])
        finally:os.close(target)
        with self.assertRaisesRegex(h.Hold,'ROLLBACK_ALREADY_ATTEMPTED'):
            handoff_call.rollback_from_original_entry(ctx)

    def test_fixed_entry_real_exchange_and_rollback_in_isolated_directory(self):
        # Only the fixed operator/absolute-directory opener are substituted for
        # a temporary fixture. Transaction, file integrity, locks, journal,
        # exchange and rollback are the real implementation.
        def fixture_directory(path, stack):
            if path==fixed_entry.PARENT:
                source=self.parent
            elif path==fixed_entry.JOURNAL:
                source=self.jfd
            else:
                raise AssertionError('UNEXPECTED_FIXED_DIRECTORY')
            fd=os.dup(source)
            stack.callback(os.close,fd)
            return fd
        with patch.object(fixed_entry,'identify_admin',return_value=1008),\
             patch.object(fixed_entry,'_protected_path_directory',side_effect=fixture_directory),\
             patch.object(fixed_entry,'ENTRY_SHA',h.sha(b'A_ENTRY_FIXTURE')),\
             patch.object(fixed_entry,'ROOT_UID',self.uid):
            result=fixed_entry.run('execute',lambda *args:True,
                self.old_archive_bytes,self.archive)
            self.assertEqual(result['state'],'SWAPPED_OLD_RETAINED_IN_STAGE')
            restored=fixed_entry.run('rollback',lambda *args:True,
                self.old_archive_bytes,self.archive)
            self.assertEqual(restored['state'],
                'ROLLED_BACK_OLD_TARGET_RESTORED_NEW_STAGE_RETAINED')
            with self.assertRaisesRegex(h.Hold,'ROLLBACK_ALREADY_ATTEMPTED'):
                fixed_entry.run('rollback',lambda *args:True,
                    self.old_archive_bytes,self.archive)
        target=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:
            self.assertEqual(h.readfile(target,'loader.py',self.uid),self.old['loader.py'])
            self.assertEqual(h.readfile(target,'manifest.json',self.uid),self.old['manifest.json'])
        finally:os.close(target)

    def test_duplicate_attempt_holds(self):
        self.execute()
        with self.assertRaisesRegex(h.Hold,'EXISTING_TRANSACTION_INSPECT_ONLY'):self.execute()

    def test_wrong_identity_holds_without_stage(self):
        with self.assertRaisesRegex(h.Hold,'PARENT_IDENTITY_CHANGED'):
            h.execute(self.parent,self.jfd,self.entry,self.lease,self.old,self.archive,self.uid,[],self.journal_id,self.entry_id,self.lock_id,'isolated-attempt-0001',history_refs=self.history_refs)
        self.assertIsNone(h.childstat(self.jfd,h.STATE))

    def test_wrong_candidate_sha_holds(self):
        with self.assertRaisesRegex(h.Hold,'CANDIDATE_ARCHIVE_SHA'):h.execute(
            self.parent,self.jfd,self.entry,self.lease,self.old,b'bad',self.uid,self.parent_id,
            self.journal_id,self.entry_id,self.lock_id,'isolated-attempt-0001',history_refs=self.history_refs)
        self.assertIsNone(h.childstat(self.jfd,h.STATE))

    def test_preintent_is_durable_before_stage_and_reopen_is_inspect_only(self):
        def fault(where):
            if where=='preintent_fsynced':raise RuntimeError('PRESTAGE_STOP')
        with self.assertRaisesRegex(RuntimeError,'PRESTAGE_STOP'):self.execute(fault)
        self.assertIsNotNone(h.childstat(self.jfd,h.PREINTENT))
        self.assertIsNone(h.childstat(self.parent,h.STAGE))
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
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
            h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        with self.assertRaisesRegex(h.Hold,'HISTORY_ABSENCE_CHANGED'):
            h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        binding=h.journal(self.jfd,self.uid)
        self.assertEqual(h.tree(self.parent,h.TARGET,self.uid,self.new,binding['stage_identity']),
                         binding['stage_identity'])
        self.assertEqual(h.tree(self.parent,h.STAGE,self.uid,self.old,binding['old_identity']),
                         binding['old_identity'])

    def test_partial_stage_write_is_owned_by_preintent_and_never_retried(self):
        def fault(where):
            if where=='stage_partial_write':raise RuntimeError('PARTIAL_STAGE_WRITE')
        with self.assertRaisesRegex(RuntimeError,'PARTIAL_STAGE_WRITE'):self.execute(fault)
        self.assertIsNotNone(h.childstat(self.jfd,h.PREINTENT))
        self.assertIsNotNone(h.childstat(self.parent,h.STAGE))
        self.assertIsNone(h.childstat(self.jfd,h.STATE))
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
            self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
            'UNKNOWN_INSPECT_ONLY')
        with self.assertRaisesRegex(h.Hold,'EXISTING_TRANSACTION_INSPECT_ONLY'):self.execute()

    def test_nested_mkdir_fsyncs_parent_directory(self):
        nested={'scripts/subdir/module.py':b'fixture'}
        seen=[]
        original=h.os.fsync
        def capture(fd):
            st=os.fstat(fd)
            if stat.S_ISDIR(st.st_mode):
                try:path=os.readlink('/proc/self/fd/'+str(fd))
                except OSError:path=''
                seen.append(path)
            return original(fd)
        with patch.object(h.os,'fsync',side_effect=capture):
            h.build_tree(self.parent,nested,self.uid,name='fsync-probe')
        self.assertTrue(any(path.endswith('/fsync-probe/scripts') for path in seen),seen)
        self.assertTrue(any(path.endswith('/fsync-probe') for path in seen),seen)

    def test_crash_after_intent_never_retries(self):
        def fault(where):
            if where=='intent_fsynced':raise RuntimeError('SYNTHETIC_CRASH')
        with self.assertRaisesRegex(RuntimeError,'SYNTHETIC_CRASH'):self.execute(fault)
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
                         'PREPARED_OR_REVERTED')
        with self.assertRaisesRegex(h.Hold,'EXISTING_TRANSACTION_INSPECT_ONLY'):self.execute()

    def test_after_exchange_error_preserves_old_and_unknown(self):
        def fault(where):
            if where=='after_exchange':raise RuntimeError('SYNTHETIC_AFTER')
        with self.assertRaisesRegex(h.Hold,'POST_SWITCH_UNKNOWN_INSPECT_ONLY'):self.execute(fault)
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
                         'SWAPPED_OLD_RETAINED_IN_STAGE')

    def test_foreign_replacement_refuses_rollback(self):
        self.execute()
        fd=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:
            file=os.open('loader.py',os.O_WRONLY,dir_fd=fd)
            try:os.write(file,b'BAD')
            finally:os.close(file)
        finally:os.close(fd)
        with self.assertRaises(h.Hold):h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)

    def test_contention_original_lock_holds(self):
        second=os.open(h.LOCK,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.jfd)
        try:
            fcntl.flock(second,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises((BlockingIOError,OSError)):self.execute()
        finally:fcntl.flock(second,fcntl.LOCK_UN);os.close(second)

    def test_real_nested_carriers_are_full_manifests_when_ci_fixture_set(self):
        if not (os.environ.get('HANDOFF_OLD_ARCHIVE') and os.environ.get('HANDOFF_NEW_ARCHIVE')):
            self.skipTest('CI fixture downloader not configured')
        self.assertGreater(len(self.old),8)
        self.assertGreater(len(self.new),8)
        self.assertTrue(h.verified_old_inventory(self.old))
        self.assertEqual(h.sha(self.new['manifest.json']),h.NEW_MANIFEST)

    def test_exchange_effect_then_exception_is_unknown_and_not_replayed(self):
        original=h.exchange
        def exchange_then_raise(parent,a,b):
            original(parent,a,b)
            raise OSError('SYNTHETIC_POST_EXCHANGE_EXCEPTION')
        with patch.object(h,'exchange',side_effect=exchange_then_raise):
            with self.assertRaisesRegex(h.Hold,'EXCHANGE_RESULT_UNKNOWN_INSPECT_ONLY'):
                self.execute()
        result=h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
            self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        self.assertEqual(result['state'],'SWAPPED_OLD_RETAINED_IN_STAGE')
        binding=h.journal(self.jfd,self.uid)
        self.assertEqual(h.tree(self.parent,h.TARGET,self.uid,self.new,binding['stage_identity']),
                         binding['stage_identity'])
        self.assertEqual(h.tree(self.parent,h.STAGE,self.uid,self.old,binding['old_identity']),
                         binding['old_identity'])
        with self.assertRaisesRegex(h.Hold,'EXISTING_TRANSACTION_INSPECT_ONLY'):self.execute()

    def test_parent_fsync_failure_after_exchange_is_unknown(self):
        original=h.os.fsync;armed={'value':False}
        def fault(stage):
            if stage=='after_exchange':armed['value']=True
        def fsync(fd):
            if armed['value'] and fd==self.parent:
                armed['value']=False
                raise OSError('SYNTHETIC_PARENT_FSYNC_FAILURE')
            return original(fd)
        with patch.object(h.os,'fsync',side_effect=fsync):
            with self.assertRaisesRegex(h.Hold,'POST_SWITCH_UNKNOWN_INSPECT_ONLY'):self.execute(fault)
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
            self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
            'SWAPPED_OLD_RETAINED_IN_STAGE')

    def test_history_replacement_refuses_rollback_before_exchange(self):
        self.execute()
        name,body,pfd=self.history_bodies['freeze']
        os.unlink(name,dir_fd=pfd)
        h.writefile(pfd,name,body,self.uid)
        with self.assertRaisesRegex(h.Hold,'HISTORY_FILE_IDENTITY_CHANGED'):
            h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        with self.assertRaisesRegex(h.Hold,'HISTORY_FILE_IDENTITY_CHANGED'):
            h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        # Independently prove no exchange: current target still has the new tree,
        # while the stage retains the old tree, without trusting changed history.
        binding=h.journal(self.jfd,self.uid)
        self.assertEqual(h.tree(self.parent,h.TARGET,self.uid,self.new,binding['stage_identity']),
                         binding['stage_identity'])
        self.assertEqual(h.tree(self.parent,h.STAGE,self.uid,self.old,binding['old_identity']),
                         binding['old_identity'])

    def test_entry_path_replacement_refuses_rollback(self):
        self.execute()
        os.unlink(h.ENTRY_NAME,dir_fd=self.parent)
        h.writefile(self.parent,h.ENTRY_NAME,b'A_ENTRY_FIXTURE',self.uid)
        with self.assertRaisesRegex(h.Hold,'ORIGINAL_ENTRY_FD_PATH_CHANGED'):
            h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)

    def test_replaced_original_lock_path_is_rejected_before_intent(self):
        os.unlink(h.LOCK,dir_fd=self.jfd)
        h.writefile(self.jfd,h.LOCK,b'REPLACEMENT_LOCK',self.uid)
        with self.assertRaisesRegex(h.Hold,'ORIGINAL_LOCK_FD_PATH_CHANGED'):
            self.execute()
        self.assertIsNone(h.childstat(self.jfd,h.PREINTENT))

    def test_copied_journal_parent_is_rejected(self):
        self.execute()
        copied=os.path.join(self.tmp.name,'journal-copy');os.mkdir(copied,0o700)
        for name in (h.STATE,h.PREINTENT,h.ROLLBACK_INTENT,h.ROLLBACK_RESULT):
            if h.childstat(self.jfd,name) is not None:
                with open(os.path.join(copied,name),'wb') as out:
                    out.write(h.readfile(self.jfd,name,self.uid))
                os.chmod(os.path.join(copied,name),0o600)
        other=os.open(copied,os.O_RDONLY|os.O_DIRECTORY)
        try:
            with self.assertRaisesRegex(h.Hold,'JOURNAL_PARENT_PATH_CHANGED'):
                h.status(self.parent,other,self.entry,self.lease,self.uid,self.old,self.new,
                    self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        finally:os.close(other)

    def test_rollback_fsync_failure_reconciles_without_replay(self):
        self.execute()
        original=h.os.fsync;armed={'value':False}
        # Arm at rollback intent fsync completion; then fail the first parent fsync after exchange.
        def wrapper(fd):
            if armed['value'] and fd==self.parent:
                armed['value']=False
                raise OSError('SYNTHETIC_ROLLBACK_FSYNC')
            return original(fd)
        with patch.object(h.os,'fsync',side_effect=wrapper):
            # writefile invokes fsync on its fd and then journal dir, not carrier parent.
            # Arm via exchange wrapper after the atomic reverse operation.
            original_exchange=h.exchange
            def exchange_then_arm(parent,a,b):
                original_exchange(parent,a,b);armed['value']=True
            with patch.object(h,'exchange',side_effect=exchange_then_arm):
                with self.assertRaisesRegex(h.Hold,'ROLLBACK_UNKNOWN_INSPECT_ONLY'):
                    h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
                        self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
            self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
            'ROLLBACK_APPLIED_RESULT_UNKNOWN')

    def test_lease_close_failure_after_exchange_is_unknown(self):
        original=h._close_lease
        def close_then_raise(fd):
            original(fd)
            raise OSError('SYNTHETIC_LEASE_CLOSE')
        with patch.object(h,'_close_lease',side_effect=close_then_raise):
            with self.assertRaisesRegex(h.Hold,'POST_SWITCH_CLOSE_UNKNOWN_INSPECT_ONLY'):
                self.execute()
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
            self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
            'SWAPPED_OLD_RETAINED_IN_STAGE')

    def test_rollback_lease_close_failure_is_reconciled_read_only(self):
        self.execute()
        original=h._close_lease
        def close_then_raise(fd):
            original(fd)
            raise OSError('SYNTHETIC_ROLLBACK_CLOSE')
        with patch.object(h,'_close_lease',side_effect=close_then_raise):
            with self.assertRaisesRegex(h.Hold,'ROLLBACK_CLOSE_UNKNOWN_INSPECT_ONLY'):
                h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
                    self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
            self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
            'ROLLED_BACK_OLD_TARGET_RESTORED_NEW_RETAINED')

    def test_history_change_blocks_status_reconstruction(self):
        self.execute()
        name,body,pfd=self.history_bodies['b_approval']
        os.unlink(name,dir_fd=pfd);h.writefile(pfd,name,body+b'X',self.uid)
        with self.assertRaisesRegex(h.Hold,'HISTORY_FILE_IDENTITY_CHANGED'):
            h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)

    def test_readonly_status_reopens_fresh_descriptors(self):
        self.execute()
        jfd=os.open(h.JOURNAL_DIR,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        entry=os.open(h.ENTRY_NAME,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.parent)
        lease=os.open(h.LOCK,os.O_RDWR|os.O_NOFOLLOW,dir_fd=jfd)
        try:
            refs=dict(self.history_refs)
            name,body,_=self.history_bodies['b_intent']
            st=os.stat(name,dir_fd=jfd,follow_symlinks=False)
            refs['b_intent']=(jfd,name,h.parent_ident(os.fstat(jfd)),h.ident(st),h.sha(body))
            result=h.status(self.parent,jfd,entry,lease,self.uid,self.old,self.new,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,refs)
            self.assertEqual(result['state'],'SWAPPED_OLD_RETAINED_IN_STAGE')
        finally:os.close(lease);os.close(entry);os.close(jfd)

    def test_absent_old_stage_permit_must_remain_absent(self):
        name,body,pfd=self.history_bodies['old_stage_permit']
        os.unlink(name,dir_fd=pfd)
        self.history_refs['old_stage_permit']=(pfd,name,h.parent_ident(os.fstat(pfd)),None,None)
        self.execute()
        h.writefile(pfd,name,body,self.uid)
        with self.assertRaisesRegex(h.Hold,'HISTORY_ABSENCE_CHANGED'):
            h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)

    def test_history_mutation_after_stage_holds_before_exchange(self):
        def fault(where):
            if where=='staged':
                name,body,pfd=self.history_bodies['freeze']
                os.unlink(name,dir_fd=pfd)
                h.writefile(pfd,name,body+b'CHANGED',self.uid)
        with self.assertRaisesRegex(h.Hold,'HISTORY_FILE_IDENTITY_CHANGED'):
            self.execute(fault)
        target=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:self.assertEqual(h.readfile(target,'loader.py',self.uid),self.old['loader.py'])
        finally:os.close(target)
        self.assertIsNotNone(h.childstat(self.jfd,h.PREINTENT))

    def test_entry_replacement_after_stage_holds_before_exchange(self):
        def fault(where):
            if where=='staged':
                os.unlink(h.ENTRY_NAME,dir_fd=self.parent)
                h.writefile(self.parent,h.ENTRY_NAME,b'REPLACED_ENTRY',self.uid)
        with self.assertRaisesRegex(h.Hold,'FINAL_LEASE_OR_PARENT_CHANGED'):
            self.execute(fault)
        target=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:self.assertEqual(h.readfile(target,'loader.py',self.uid),self.old['loader.py'])
        finally:os.close(target)

    def test_retained_path_conflict_refuses_rollback_before_exchange(self):
        self.execute()
        os.mkdir(h.RETAINED,0o700,dir_fd=self.parent)
        with self.assertRaisesRegex(h.Hold,'ROLLBACK_CONFLICT'):
            h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        target=os.open(h.TARGET,os.O_RDONLY|os.O_DIRECTORY,dir_fd=self.parent)
        try:self.assertEqual(h.readfile(target,'loader.py',self.uid),self.new['loader.py'])
        finally:os.close(target)

    def test_rollback_exchange_effect_then_exception_is_unknown(self):
        self.execute()
        original=h.exchange
        def exchange_then_raise(parent,a,b):
            original(parent,a,b)
            raise OSError('SYNTHETIC_ROLLBACK_EXCHANGE_RESULT_UNKNOWN')
        with patch.object(h,'exchange',side_effect=exchange_then_raise):
            with self.assertRaisesRegex(h.Hold,'ROLLBACK_EXCHANGE_UNKNOWN_INSPECT_ONLY'):
                h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
                    self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        self.assertEqual(h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
            self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)['state'],
            'ROLLBACK_APPLIED_RESULT_UNKNOWN')
        with self.assertRaisesRegex(h.Hold,'ROLLBACK_ALREADY_ATTEMPTED'):
            h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)

    def test_failed_b_output_appearing_after_handoff_holds(self):
        self.execute()
        h.writefile(self.jfd,h.HISTORY_NAMES['snapshot_result'],b'UNEXPECTED_RESULT',self.uid)
        with self.assertRaisesRegex(h.Hold,'HISTORY_ABSENCE_CHANGED'):
            h.status(self.parent,self.jfd,self.entry,self.lease,self.uid,self.old,self.new,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)
        with self.assertRaisesRegex(h.Hold,'HISTORY_ABSENCE_CHANGED'):
            h.rollback(self.parent,self.jfd,self.entry,self.lease,self.old,self.new,self.uid,
                self.parent_id,self.journal_id,self.entry_id,self.lock_id,self.history_refs)

    def test_original_evidence_unmodified(self):
        before={key:body for key,(name,body,pfd) in self.history_bodies.items()}
        self.execute()
        for key,(name,body,pfd) in self.history_bodies.items():
            self.assertEqual(h.readfile(pfd,name,self.uid),before[key])
        for key in h.ABSENT_HISTORY:
            pfd=self.jfd if key in h.JOURNAL_HISTORY_KEYS else self.parent
            self.assertIsNone(h.childstat(pfd,h.HISTORY_NAMES[key]))

if __name__=='__main__':unittest.main()
