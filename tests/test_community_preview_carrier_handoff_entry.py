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
