import copy
import os
import pathlib
import shutil
import stat
import tempfile
import unittest
from unittest import mock

import epoch7_delta as d
import epoch7_exact_access as a
import epoch7_host_phases as h
from test_epoch7_host_phases import Authority


class ACLTests(unittest.TestCase):
    def test_binary_roundtrip_exact_named_grants(self):
        for purpose, before, uids in (
                ('release_traversal','user::rwx\ngroup::r-x\nother::---\n',[1002,1003,1004]),
                ('ledger_client_binding_read','user::rw-\ngroup::r--\nother::---\n',[1003])):
            text = a.propose(before,purpose,uids)['after_acl']
            self.assertEqual(a.decode_acl(a.encode_acl(text),0),text)
    def test_malformed_xattr_refused(self):
        for raw in (b'',b'\x02\0\0\0x',b'\x03\0\0\0',b'\x02\0\0\0'+b'\xff'*8):
            with self.assertRaises(ValueError): a.decode_acl(raw,0o750)
    def test_basic_acl_reads_mode_only(self):
        self.assertEqual(a.decode_acl(None,0o750),'user::rwx\ngroup::r-x\nother::---\n')


class ActualFDTests(unittest.TestCase):
    def setUp(self):
        base = str(pathlib.Path(__import__('epoch7_protected_fs').__file__).resolve().parent/'fixtures')
        self.root = tempfile.mkdtemp(prefix='acl-',dir=base)
        os.chmod(self.root,0o700)
        for path in (h.fs.TRANSACTION,'/etc/xuanjun-development','/opt/xuanjun-control-releases'):
            os.makedirs(self.root+path,mode=0o700,exist_ok=True)
        self.release = '/opt/xuanjun-control-releases'
        self.client = '/etc/xuanjun-development/p2-native-ledger-client.json'
        os.chmod(self.root+self.release,0o750)
        with open(self.root+self.client,'wb') as stream: stream.write(b'unchanged-client')
        os.chmod(self.root+self.client,0o640)
        self.io = h.HostPhaseFilesystem(Authority(),self.root)
        self.context = {'context_sha256':d.digest('context')}
        self.rows = []; self.resolved = {}
        probe = a.ExactAccessApplier.__new__(a.ExactAccessApplier); probe.io = self.io
        for path in (self.release,self.client):
            parent,leaf=self.io._parent(path)
            fd=os.open(leaf,h.fs.DIR_FLAGS if path==self.release else h.fs.READ_FLAGS,dir_fd=parent)
            try:
                before=probe._read(parent,leaf,fd,path)
            finally: os.close(fd);os.close(parent)
            purpose,uids=a.TARGETS[path]
            self.resolved[path] = before
            keys = {'kind','uid','gid','mode','access_acl','default_acl','sha256'}
            if path == self.release: keys |= {'dev','ino'}
            binding = {k:before[k] for k in keys}
            binding['state_source'] = 'stage_exact_release_observed' if path == self.release else 'inner_provision_observed_after'
            self.rows.append({'path':path,'before_binding':binding,'proposal':a.propose(before['access_acl'],purpose,uids)})
        self.effect = a.ExactAccessApplier(self.io,self.context,self.rows,d.digest(self.rows),lambda c,p:True,lambda p:self.resolved[p])
    def tearDown(self): shutil.rmtree(self.root)
    @unittest.skipUnless(any(int(row.split()[0]) <= 1002 and int(row.split()[0])+int(row.split()[2]) > 1004 for row in pathlib.Path('/proc/self/uid_map').read_text().splitlines()), 'executor maps only UID1000; exact1002/1003/1004 kernel ACL test needs UK/userns mapping')
    def test_actual_fd_acl_changes_only_two_named_access_sets(self):
        result=self.effect(self.context,None)
        self.assertEqual(result['status'],'OBSERVED')
        self.assertEqual(set(self.effect.observed),set(a.TARGETS))
        self.assertEqual(pathlib.Path(self.root+self.client).read_bytes(),b'unchanged-client')
        for path in a.TARGETS:
            self.assertEqual(os.stat(self.root+path).st_uid,os.geteuid())
        with self.assertRaisesRegex(ValueError,'ONE_EXACT_ATTEMPT'):self.effect(self.context,None)
    def test_changed_file_rejects_before_its_acl_and_cannot_retry(self):
        with open(self.root+self.client,'ab') as stream:stream.write(b'drift')
        attrs={}
        actual=a.get_attr
        def read(fd,name):return attrs.get((os.fstat(fd).st_ino,name),actual(fd,name))
        def write(fd,name,raw):attrs[(os.fstat(fd).st_ino,name)]=raw
        with mock.patch.object(a,'get_attr',side_effect=read), mock.patch.object(a.os,'setxattr',side_effect=write):
            with self.assertRaisesRegex(ValueError,'FULL_BEFORE_CAS'):self.effect(self.context,None)
        self.assertEqual(set(self.effect.observed),{self.release})
        with self.assertRaisesRegex(ValueError,'ONE_EXACT_ATTEMPT'):self.effect(self.context,None)
    def test_lost_authority_before_effect_changes_nothing(self):
        self.io.authority.fail=True
        with self.assertRaisesRegex(ValueError,'LOCK_LOST'):self.effect(self.context,None)
        fd=os.open(self.root+self.release,h.fs.DIR_FLAGS)
        try:self.assertIsNone(a.get_attr(fd,a.ACCESS))
        finally:os.close(fd)
    def test_unreviewed_named_rights_and_mask_expansion_refused(self):
        rows=copy.deepcopy(self.rows)
        rows[0]['proposal']['after_acl']=rows[0]['proposal']['after_acl'].replace('user:1002:--x','user:1002:rwx')
        with self.assertRaisesRegex(ValueError,'COMPILED_DELTA'):
            a.ExactAccessApplier(self.io,self.context,rows,d.digest(rows),lambda c,p:True,lambda p:self.resolved[p])
    def test_real_fd_xattr_roundtrip_for_mapped_fixture_uid(self):
        fd=os.open(self.root+self.client,h.fs.READ_FLAGS)
        text='user::rw-\nuser:%s:r--\ngroup::r--\nmask::r--\nother::---\n'%os.geteuid()
        try:
            os.setxattr(fd,a.ACCESS,a.encode_acl(text))
            self.assertEqual(a.decode_acl(a.get_attr(fd,a.ACCESS),0o640),text)
        finally:os.close(fd)
    def test_wrong_security_digest_refused(self):
        with self.assertRaisesRegex(ValueError,'DELTA_HASH'):
            a.ExactAccessApplier(self.io,self.context,self.rows,d.digest('wrong'),lambda c,p:True,lambda p:self.resolved[p])

if __name__=='__main__':unittest.main()


# Explicit evidence split: this exact fixed-UK-UID case is required separately.
UK_REQUIRED_CASE = 'ActualFDTests.test_actual_fd_acl_changes_only_two_named_access_sets'
def load_tests(loader, tests, pattern):
    def flat(suite):
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                for nested in flat(item): yield nested
            else: yield item
    cases=list(flat(tests))
    uk=[case for case in cases if '.'.join(case.id().split('.')[-2:])==UK_REQUIRED_CASE]
    if len(uk)!=1: raise AssertionError('Exact UK-required test split changed')
    return unittest.TestSuite(uk)
