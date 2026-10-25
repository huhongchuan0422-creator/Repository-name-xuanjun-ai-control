"""Protected approval record validation tests; no production host or B/C."""
import os
import tempfile
import unittest
from unittest.mock import patch
from scripts import community_preview_carrier_handoff_admission as h
from scripts import community_preview_carrier_handoff_entry as entry

class ApprovalRecord(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.parent=os.open(self.tmp.name,os.O_RDONLY|os.O_DIRECTORY)
        self.addCleanup(os.close,self.parent)
        self.uid=os.getuid()
        self.old=b'fixed-old-archive'
        self.new=b'fixed-new-archive'
        self.now=1800000000
        self.value={'format':1,'host':h.HOST,'operation':'execute',
            'attempt':entry.ATTEMPT,'old_archive_sha256':h.OLD_ARCHIVE,
            'old_manifest_sha256':h.OLD_MANIFEST,'new_archive_sha256':h.NEW_ARCHIVE,
            'new_manifest_sha256':h.NEW_MANIFEST,'issued_at':self.now-10,
            'expires_at':self.now+300}
        self.write_record(self.value)

    def write_record(self,value):
        try:os.unlink(entry.APPROVAL_NAME,dir_fd=self.parent)
        except FileNotFoundError:pass
        h.writefile(self.parent,entry.APPROVAL_NAME,h.canonical(value),self.uid)

    def validate(self,operation='execute'):
        with patch.object(entry.time,'time',return_value=self.now),patch.object(entry,'ROOT_UID',self.uid):
            with __import__('contextlib').ExitStack() as stack:
                fd,raw,identity=entry._approval_fd(self.parent,operation,self.old,self.new,self.uid,stack)
                return raw,identity

    def test_fixed_archive_reader_accepts_exact_protected_bytes(self):
        raw=b'PINNED_ARCHIVE_BYTES'
        h.writefile(self.parent,entry.OLD_INPUT_NAME,raw,self.uid)
        with patch.object(entry,'ROOT_UID',self.uid),patch.object(h,'OLD_ARCHIVE',h.sha(raw)):
            self.assertEqual(entry._read_fixed_archive(
                self.parent,entry.OLD_INPUT_NAME,h.OLD_ARCHIVE,self.uid),raw)

    def test_fixed_archive_reader_rejects_wrong_sha_and_hardlink(self):
        raw=b'PINNED_ARCHIVE_BYTES'
        h.writefile(self.parent,entry.OLD_INPUT_NAME,raw,self.uid)
        with patch.object(entry,'ROOT_UID',self.uid):
            with self.assertRaisesRegex(h.Hold,'FIXED_INPUT_SHA_MISMATCH'):
                entry._read_fixed_archive(self.parent,entry.OLD_INPUT_NAME,'0'*64,self.uid)
        os.link(os.path.join(self.tmp.name,entry.OLD_INPUT_NAME),
                os.path.join(self.tmp.name,'hardlink-copy'))
        with patch.object(entry,'ROOT_UID',self.uid),patch.object(h,'OLD_ARCHIVE',h.sha(raw)):
            with self.assertRaisesRegex(h.Hold,'FIXED_INPUT_IDENTITY_OR_MODE'):
                entry._read_fixed_archive(self.parent,entry.OLD_INPUT_NAME,h.OLD_ARCHIVE,self.uid)

    def test_fixed_archive_reader_rejects_symlink(self):
        os.symlink('missing',entry.NEW_INPUT_NAME,dir_fd=self.parent)
        with patch.object(entry,'ROOT_UID',self.uid):
            with self.assertRaises(OSError):
                entry._read_fixed_archive(self.parent,entry.NEW_INPUT_NAME,h.NEW_ARCHIVE,self.uid)

    def test_verified_source_bytes_are_loaded_from_fixed_path(self):
        import sys
        import scripts
        from pathlib import Path
        old_h=entry.h;old_call=entry.call
        old_h_mod=sys.modules.get('scripts.community_preview_carrier_handoff_admission')
        old_call_mod=sys.modules.get('scripts.community_preview_carrier_handoff_call')
        old_h_attr=getattr(scripts,'community_preview_carrier_handoff_admission',None)
        old_call_attr=getattr(scripts,'community_preview_carrier_handoff_call',None)
        source_h=Path(old_h.__file__).read_bytes()
        source_call=Path(old_call.__file__).read_bytes()
        root=tempfile.TemporaryDirectory();self.addCleanup(root.cleanup)
        scripts_dir=os.path.join(root.name,'scripts');os.mkdir(scripts_dir,0o700)
        for name,raw in (( 'community_preview_carrier_handoff_admission.py',source_h),
                         ( 'community_preview_carrier_handoff_call.py',source_call)):
            with open(os.path.join(scripts_dir,name),'wb') as stream:stream.write(raw)
            os.chmod(os.path.join(scripts_dir,name),0o600)
        def open_dir():
            return os.open(scripts_dir,os.O_RDONLY|os.O_DIRECTORY)
        try:
            with patch.object(entry,'ROOT_UID',self.uid),patch.object(entry,'SCRIPTS_DIR',scripts_dir),\
                 patch.object(entry,'_open_fixed_scripts_dir',side_effect=open_dir),\
                 patch.object(entry,'MODULE_PINS',{
                     'community_preview_carrier_handoff_admission.py':h.sha(source_h),
                     'community_preview_carrier_handoff_call.py':h.sha(source_call)}):
                self.assertTrue(entry._verify_runtime_sources())
                self.assertEqual(entry.h.__file__,os.path.join(scripts_dir,'community_preview_carrier_handoff_admission.py'))
                self.assertEqual(entry.call.__file__,os.path.join(scripts_dir,'community_preview_carrier_handoff_call.py'))
        finally:
            entry.h=old_h;entry.call=old_call
            if old_h_mod is None:sys.modules.pop('scripts.community_preview_carrier_handoff_admission',None)
            else:sys.modules['scripts.community_preview_carrier_handoff_admission']=old_h_mod
            if old_call_mod is None:sys.modules.pop('scripts.community_preview_carrier_handoff_call',None)
            else:sys.modules['scripts.community_preview_carrier_handoff_call']=old_call_mod
            if old_h_attr is None:delattr(scripts,'community_preview_carrier_handoff_admission')
            else:setattr(scripts,'community_preview_carrier_handoff_admission',old_h_attr)
            if old_call_attr is None:delattr(scripts,'community_preview_carrier_handoff_call')
            else:setattr(scripts,'community_preview_carrier_handoff_call',old_call_attr)

    def test_wrong_runtime_module_sha_holds_before_exec(self):
        from pathlib import Path
        raw=Path(h.__file__).read_bytes()
        root=tempfile.TemporaryDirectory();self.addCleanup(root.cleanup)
        scripts_dir=os.path.join(root.name,'scripts');os.mkdir(scripts_dir,0o700)
        with open(os.path.join(scripts_dir,'community_preview_carrier_handoff_admission.py'),'wb') as stream:stream.write(raw)
        os.chmod(os.path.join(scripts_dir,'community_preview_carrier_handoff_admission.py'),0o600)
        with patch.object(entry,'ROOT_UID',self.uid),patch.object(entry,'SCRIPTS_DIR',scripts_dir),\
             patch.object(entry,'_open_fixed_scripts_dir',side_effect=lambda:os.open(scripts_dir,os.O_RDONLY|os.O_DIRECTORY)),\
             patch.object(entry,'MODULE_PINS',dict(entry.MODULE_PINS,
                 **{'community_preview_carrier_handoff_admission.py':'0'*64})):
            with self.assertRaisesRegex(h.Hold,'HANDOFF_MODULE_SHA_MISMATCH'):
                entry._verify_runtime_sources()

    def test_cli_has_no_approval_bypass_switch(self):
        with patch.object(entry,'run') as run:
            self.assertEqual(entry.main(['--approve']),2)
            run.assert_not_called()

    def test_valid_exact_short_lived_record(self):
        raw,identity=self.validate()
        self.assertEqual(raw,h.canonical(self.value))
        self.assertTrue(identity)

    def test_missing_record_holds(self):
        os.unlink(entry.APPROVAL_NAME,dir_fd=self.parent)
        with patch.object(entry,'ROOT_UID',self.uid):
            with self.assertRaisesRegex(h.Hold,'APPROVAL_MISSING'):
                self.validate()

    def test_expired_record_holds(self):
        value=dict(self.value,issued_at=self.now-700,expires_at=self.now-1)
        self.write_record(value)
        with self.assertRaisesRegex(h.Hold,'APPROVAL_EXPIRED_OR_TTL_INVALID'):
            self.validate()

    def test_ttl_over_600_holds(self):
        self.write_record(dict(self.value,expires_at=self.now+601))
        with self.assertRaisesRegex(h.Hold,'APPROVAL_EXPIRED_OR_TTL_INVALID'):
            self.validate()

    def test_operation_host_attempt_and_pins_are_bound(self):
        for change,reason in (
            ({'operation':'rollback'},'APPROVAL_SCOPE_MISMATCH'),
            ({'host':'other-host'},'APPROVAL_SCOPE_MISMATCH'),
            ({'attempt':'other-attempt'},'APPROVAL_SCOPE_MISMATCH'),
            ({'new_archive_sha256':'0'*64},'APPROVAL_PIN_MISMATCH'),
            ({'old_manifest_sha256':'0'*64},'APPROVAL_PIN_MISMATCH')):
            value=dict(self.value);value.update(change);self.write_record(value)
            with self.assertRaisesRegex(h.Hold,reason):self.validate()

    def test_unknown_schema_noncanonical_and_duplicate_key_hold(self):
        self.write_record(dict(self.value,extra='no'))
        with self.assertRaisesRegex(h.Hold,'APPROVAL_SCHEMA'):self.validate()
        raw=b'{"format":1,"format":1}'
        os.unlink(entry.APPROVAL_NAME,dir_fd=self.parent)
        h.writefile(self.parent,entry.APPROVAL_NAME,raw,self.uid)
        with self.assertRaisesRegex(h.Hold,'APPROVAL_DUPLICATE_KEY'):self.validate()

    def test_symlink_hardlink_and_mode_rejected(self):
        os.unlink(entry.APPROVAL_NAME,dir_fd=self.parent)
        os.symlink('missing',entry.APPROVAL_NAME,dir_fd=self.parent)
        with patch.object(entry,'ROOT_UID',self.uid):
            with self.assertRaisesRegex(h.Hold,'APPROVAL_OPEN_REJECTED'):self.validate()
        os.unlink(entry.APPROVAL_NAME,dir_fd=self.parent)
        self.write_record(self.value)
        os.chmod(os.path.join(self.tmp.name,entry.APPROVAL_NAME),0o640)
        with self.assertRaisesRegex(h.Hold,'APPROVAL_FILE_IDENTITY_OR_MODE'):self.validate()

    def test_replacement_after_read_is_rejected(self):
        with patch.object(entry.time,'time',return_value=self.now),patch.object(entry,'ROOT_UID',self.uid):
            with __import__('contextlib').ExitStack() as stack:
                fd,raw,identity=entry._approval_fd(self.parent,'execute',self.old,self.new,self.uid,stack)
                replacement=dict(self.value,expires_at=self.now+250)
                os.unlink(entry.APPROVAL_NAME,dir_fd=self.parent)
                h.writefile(self.parent,entry.APPROVAL_NAME,h.canonical(replacement),self.uid)
                with self.assertRaisesRegex(h.Hold,'APPROVAL_REPLACED'):
                    entry._recheck_approval(self.parent,fd,raw,identity,'execute',self.old,self.new,self.uid)

if __name__=='__main__':unittest.main()
