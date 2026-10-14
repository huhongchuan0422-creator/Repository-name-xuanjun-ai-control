"""Real frozen activation append/publish in a confined local fixture."""
import fcntl
import os
import pathlib
import shutil
import tempfile
import unittest

import epoch7_host_phases as h
from test_epoch7_delta import fixture


class RealActivationTests(unittest.TestCase):
    def setUp(self):
        base=str(pathlib.Path(__import__('epoch7_protected_fs').__file__).resolve().parent/'fixtures')
        self.root=tempfile.mkdtemp(prefix='activation-',dir=base)
        directory=self.root+os.path.dirname(h.snap.ACTIVE)
        os.makedirs(directory,mode=0o700)
        self.lockpath=self.root+h.snap.ACTIVATION_LOCK
        with open(self.lockpath,'wb') as stream:stream.write(b'')
        os.chmod(self.lockpath,0o644)
        self.lockmeta=dict(h.fs.metadata(os.lstat(self.lockpath)),kind='FILE',sha256=h.sha(b''))
        self.store=h.BoundedActivationStore(self.lockmeta,self.root)
        snap,candidate=fixture()
        self.old=snap['activation'];self.new=candidate['activation']
        self.new['release_sha256']=h.MANIFEST
        self.new['binary_sha256']=h.d.NEW_BINARY
        records=[]
        for epoch in range(1,8):
            current=dict(self.old,epoch=epoch)
            self.store._append(current,records,{'fixture':True})
            records=self.store._journal()
        self.store._write_descriptor(self.old)
        self.proof={key:h.d.digest(key) for key in ('approval_body_sha256','snapshot_sha256','recovery_plan_sha256')}
        self.proof.update(controller_transition_sha256=h.d.digest(h.d.controller_transition(self.old,self.new)),old_descriptor_sha256=self.store.head(self.old),new_descriptor_sha256=self.store.head(self.new),
            all_writers_excluded=True,install_lock_held=True,retained_resources_verified=True)
    def tearDown(self):shutil.rmtree(self.root)
    def test_real_append_publish_readback_and_fence(self):
        result=h.rebind_prepared_epoch7(self.store,self.old,self.new,self.proof)
        self.assertEqual(self.store.read(),result)
        proof={k:True for k in ('identity_verified','coordinator_inactive','parent_unit_inactive','cgroups_empty','restart_inhibited')}
        self.store.transition('PREPARED','QUIESCED',8,result['instance'],proof)
        self.store.transition('QUIESCED','ACTIVE',8,result['instance'],{'database_reopened':True})
        fenced=self.store.fence(8,result['instance'])
        self.assertEqual((fenced['epoch'],fenced['state'],fenced['release_sha256']),(9,'PREPARED',h.MANIFEST))
        self.assertEqual(self.store.read(),fenced)
        self.assertEqual(len(self.store._journal()),11)
    def test_busy_activation_lock_fails_nonblocking_without_append(self):
        fd=os.open(self.lockpath,os.O_RDONLY)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):h.rebind_prepared_epoch7(self.store,self.old,self.new,self.proof)
            self.assertEqual(len(self.store._journal()),7)
        finally:os.close(fd)
    def test_missing_lock_is_never_created(self):
        os.unlink(self.lockpath)
        with self.assertRaises(FileNotFoundError):self.store._locked()
        self.assertFalse(os.path.exists(self.lockpath))
    def test_changed_lock_metadata_is_never_repaired(self):
        os.chmod(self.lockpath,0o600)
        with self.assertRaisesRegex(ValueError,'LOCK_DRIFT'):self.store._locked()
        self.assertEqual(os.stat(self.lockpath).st_mode&0o777,0o600)

if __name__=='__main__':unittest.main()
