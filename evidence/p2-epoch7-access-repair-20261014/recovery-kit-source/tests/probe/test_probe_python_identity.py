"""Pure/mock checks of the Python-only pair exception; no host probe execution."""
import copy
import stat
import types
import unittest
from unittest import mock

import probe_driver as p


class PythonPairReads(unittest.TestCase):
    def setUp(self):
        self.policy={'nonce':'a'*32,'python':{
            'path':'/usr/libexec/platform-python3.6',
            'sha256':p.epoch7_python_identity.RETAINED_SHA256}}
        self.ops=p.HostOps(self.policy,'1'*64)
        self.raw=b'\x7fELF'+b'x'*(p.epoch7_python_identity.RETAINED_SIZE-4)
        self.paths=('/', '/usr', '/usr/libexec')+tuple(p.epoch7_python_identity.PYTHON_PATHS)
        self.infos={}
        for index,target in enumerate(self.paths):
            directory=index<3
            self.infos[target]=types.SimpleNamespace(st_dev=1,st_ino=index+1 if directory else 8,
                st_mode=(stat.S_IFDIR if directory else stat.S_IFREG)|(0o555 if index==0 else 0o755),st_uid=0,st_gid=0,
                st_nlink=2,st_size=4096 if directory else len(self.raw),st_mtime_ns=1,st_ctime_ns=2)
        self.fd_paths={index+40:path for index,path in enumerate(self.paths)}
        self.read_counts={}
        self.attributes={}
    def sample(self,mutation=None):
        def read(fd,size):
            self.read_counts[fd]=self.read_counts.get(fd,0)+1
            if mutation:mutation(fd)
            return self.raw if self.read_counts[fd]==1 else b''
        with mock.patch.object(p.os,'lstat',side_effect=lambda target:copy.copy(self.infos[target])),\
             mock.patch.object(p.os,'open',side_effect=lambda target,flags:self.paths.index(target)+40),\
             mock.patch.object(p.os,'fstat',side_effect=lambda fd:copy.copy(self.infos[self.fd_paths[fd]])),\
             mock.patch.object(p.os,'listxattr',side_effect=lambda fd:self.attributes.get(self.fd_paths[fd],[])),\
             mock.patch.object(p.os,'read',side_effect=read),\
             mock.patch.object(p.os,'close'),\
             mock.patch.object(p,'digest',return_value=p.epoch7_python_identity.RETAINED_SHA256):
            return self.ops._python_pair_sample()
    def test_fixed_pair_and_all_ancestors_checked(self):
        sample,contents=self.sample()
        self.assertEqual(set(sample['ancestors']),set(self.paths[:3]))
        self.assertEqual(set(sample['files']),set(self.paths[3:]))
        self.assertEqual(contents[self.paths[3]],self.raw)
    def test_third_link_denied(self):
        self.infos[self.paths[3]].st_nlink=3
        self.assertRaises(ValueError,self.sample)
    def test_substituted_pair_inode_denied(self):
        self.infos[self.paths[4]].st_ino+=1
        self.assertRaises(ValueError,self.sample)
    def test_file_or_ancestor_acl_and_capability_denied(self):
        for target in self.paths:
            for name in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
                self.read_counts={};self.attributes={target:[name]}
                self.assertRaises(ValueError,self.sample)
    def test_writable_or_nonroot_ancestor_denied(self):
        for field,value in (('st_mode',stat.S_IFDIR|0o775),('st_uid',1002),('st_gid',1002)):
            original=getattr(self.infos['/usr'],field)
            setattr(self.infos['/usr'],field,value)
            self.assertRaises(ValueError,self.sample)
            setattr(self.infos['/usr'],field,original)
    def test_identity_change_while_hashing_denied(self):
        def change(fd):self.infos[self.fd_paths[fd]].st_ctime_ns+=1
        self.assertRaises(ValueError,self.sample,change)
    def test_symlink_substitution_denied(self):
        self.infos[self.paths[4]].st_mode=stat.S_IFLNK|0o777
        self.assertRaises(ValueError,self.sample)
    def test_non_elf_denied(self):
        self.raw=b'not an ELF executable'
        for target in self.paths[3:]:self.infos[target].st_size=len(self.raw)
        self.assertRaises(ValueError,self.sample)
    def test_proof_reread_preserves_exact_binding(self):
        sample,contents=self.sample()
        proof=p.epoch7_python_identity.build_pair_proof(sample,sample,p.epoch7_python_identity.package_claim())
        self.policy['python']['python_identity']=proof
        with mock.patch.object(self.ops,'_python_pair_sample',return_value=(sample,contents)) as read:
            raw,metadata=self.ops.read_python()
        self.assertEqual(read.call_count,2)
        self.assertEqual(raw,self.raw)
        self.assertEqual(metadata['nlink'],2)
        self.assertEqual(proof['package_signature_authenticity'],'NOT_VERIFIED')
    def test_proof_change_between_rounds_denied(self):
        sample,contents=self.sample()
        proof=p.epoch7_python_identity.build_pair_proof(sample,sample,p.epoch7_python_identity.package_claim())
        self.policy['python']['python_identity']=proof
        changed=copy.deepcopy(sample)
        for target in self.paths[3:]:changed['files'][target]['ctime_ns']+=1
        with mock.patch.object(self.ops,'_python_pair_sample',side_effect=[(sample,contents),(changed,contents)]):
            self.assertRaises(ValueError,self.ops.read_python)
    def test_proof_cannot_authorize_other_path_or_hash(self):
        sample,contents=self.sample()
        proof=p.epoch7_python_identity.build_pair_proof(sample,sample,p.epoch7_python_identity.package_claim())
        for key,value in (('path',self.paths[4]),('sha256','0'*64)):
            original=self.policy['python'][key]
            self.policy['python']['python_identity']=proof
            self.policy['python'][key]=value
            with mock.patch.object(self.ops,'_python_pair_sample',side_effect=AssertionError('NO_READ')):
                self.assertRaises(ValueError,self.ops.read_python)
            self.policy['python'][key]=original
    def test_policy_compiler_propagates_validated_proof(self):
        import test_probe_driver
        sample,contents=self.sample()
        proof=p.epoch7_python_identity.build_pair_proof(sample,sample,p.epoch7_python_identity.package_claim())
        source=test_probe_driver.CompilerTests();source.setUp()
        source.ingredients['python']=dict(self.policy['python'],python_identity=proof)
        policy=p.compile_policy(source.ingredients,source.offline,source.observation)
        self.assertEqual(policy['python']['python_identity'],proof)
        self.assertIsNot(policy['python']['python_identity'],proof)
        policy['python']['python_identity']['sample']['files'][self.paths[3]]['nlink']=3
        self.assertRaises(ValueError,p.validate_policy,policy)
    def test_no_proof_uses_unrelaxed_generic_reader(self):
        with mock.patch.object(self.ops,'read_file',return_value=(b'legacy',{})) as read,\
             mock.patch.object(self.ops,'_python_pair_sample',side_effect=AssertionError('NO_PAIR_EXCEPTION')):
            self.assertEqual(self.ops.read_python(),(b'legacy',{}))
            read.assert_called_once_with(self.paths[3],32*1024*1024,protected=True)
    def test_generic_reader_still_rejects_two_links(self):
        info=self.infos[self.paths[3]]
        with mock.patch.object(self.ops,'protected_parent'),\
             mock.patch.object(p.os,'lstat',return_value=info),\
             mock.patch.object(p.os,'open',return_value=40),\
             mock.patch.object(p.os,'fstat',return_value=info),\
             mock.patch.object(p.os,'read',side_effect=AssertionError('MUST_REJECT_BEFORE_READ')),\
             mock.patch.object(p.os,'close'):
            self.assertRaises(ValueError,self.ops.read_file,self.paths[3],32768)
    def test_invalid_proof_rejected_before_sampling(self):
        self.policy['python']['python_identity']={}
        with mock.patch.object(self.ops,'_python_pair_sample',side_effect=AssertionError('NO_READ')):
            self.assertRaises(ValueError,self.ops.read_python)


if __name__=='__main__':unittest.main()
