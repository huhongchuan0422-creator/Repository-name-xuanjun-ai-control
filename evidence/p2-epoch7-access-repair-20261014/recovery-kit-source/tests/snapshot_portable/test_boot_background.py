"""Injected proc and directory fixtures. No host census, NSS or commands."""
import contextlib
import copy
import hashlib
import io
import os
import pathlib
import stat
import sys
import types
import unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'recovery-design-candidate')]
import snapshot_io as s
import epoch7_snapshot as c
import epoch7_delta as d
import unit_metadata as u

def statraw(pid=123,start=456,flags=0):
    fields=['S','1','0','0','0','0',str(flags)]+['0']*12+[str(start)]+['0']*10
    return (str(pid)+' (ssh) '+' '.join(fields)+'\n').encode()

class SshTests(unittest.TestCase):
    def setUp(self):
        self.io=object.__new__(s.LocalReadOnlyIO)
        self.io._ssh_image=mock.Mock(return_value=('a'*64,[1,2]))
        self.files={'stat':statraw(),'status':b'Name:\tssh\nUid:\t1002 1002 1002 1002\nGid:\t1002 1002 1002 1002\nGroups:\t1007 1002\n',
            'comm':b'ssh\n','cmdline':b'ssh\0private-host-token\0','cgroup':b'1:name=systemd:/user.slice/user-1002.slice/session-1.scope\n'}
    def read(self,name,limit):return self.files[name]
    def test_exact_identity_schema_and_hash_only_argv(self):
        identity,private=self.io._ssh_identity(123,self.read)
        self.assertEqual(set(identity),{'pid','starttime','uids','gids','groups','comm','executable','executable_sha256','argv_sha256','unit','kernel_thread'})
        self.assertEqual(identity['groups'],[1002,1007]);self.assertEqual(identity['uids'],[1002]*4)
        self.assertEqual(identity['argv_sha256'],c.sha(self.files['cmdline']));self.assertIsNone(identity['unit'])
        self.assertFalse(identity['kernel_thread']);self.assertNotIn(b'private-host-token',d.canonical(identity))
        self.assertNotIn(b'session-1',d.canonical(private))
    def test_kernel_uid_comm_and_argv_rejected(self):
        for key,value in [('stat',statraw(flags=0x00200000)),('status',self.files['status'].replace(b'1002 1002 1002 1002',b'0 0 0 0',1)),('comm',b'not-ssh\n'),('cmdline',b'')]:
            old=self.files[key];self.files[key]=value
            with self.assertRaises(ValueError):self.io._ssh_identity(123,self.read)
            self.files[key]=old
    def test_relevant_cgroup_missing_controller_duplicate_rejected(self):
        for raw in (('1:name=systemd:/system.slice/'+next(iter(c.WRITER_UNITS))+'\n').encode(),b'0::/user.slice\n',b'1:name=systemd:/\n2:name=systemd:/\n'):
            self.files['cgroup']=raw
            with self.assertRaises(ValueError):self.io._ssh_identity(123,self.read)
    def test_systemd_root_is_explicitly_supported(self):
        self.files['cgroup']=b'1:name=systemd:/\n';self.assertIsNone(self.io._ssh_identity(123,self.read)[0]['unit'])
    def test_pid_reuse_inside_identity_rejected(self):
        n=[0]
        def changed(name,limit):
            if name=='stat':
                n[0]+=1
                if n[0]==2:return statraw(start=999)
            return self.files[name]
        with self.assertRaisesRegex(ValueError,'PID_REUSE'):self.io._ssh_identity(123,changed)
    def census(self,files=None):
        files=files or self.files
        def opened(path,mode):return io.BytesIO(files[path.rsplit('/',1)[-1]])
        def listing(path):
            if path=='/proc':return ['123']
            if path=='/proc/123/fd':return []
            raise AssertionError(path)
        with mock.patch('builtins.open',side_effect=opened),mock.patch.object(s.os,'listdir',side_effect=listing),mock.patch.object(s.os,'readlink',return_value='/usr/bin/ssh'),mock.patch.object(s.os,'getpid',return_value=999):
            return self.io._process_scan(())
    def test_full_census_emits_explicit_stable_background_list(self):
        r=self.census();self.assertEqual(len(r['background_processes']),1)
        row=r['background_processes'][0];self.assertEqual(row['before'],row['after'])
        self.assertEqual(r['background_processes_sha256'],d.digest(r['background_processes']))
        self.assertEqual(self.io._ssh_image.call_count,2)
    def test_changed_executable_identity_between_scans_rejected(self):
        self.io._ssh_image.side_effect=[('a'*64,[1,2]),('a'*64,[1,3])]
        with self.assertRaisesRegex(ValueError,'IDENTITY_CHANGED'):self.census()
    def test_complete_no_ssh_scan_emits_explicit_empty(self):
        files=copy.deepcopy(self.files);files['status']=files['status'].replace(b'1002',b'0')
        r=self.census(files);self.assertEqual(r['background_processes'],[]);self.io._ssh_image.assert_not_called()
    def test_unreadable_proc_fails_whole_census(self):
        with mock.patch.object(s.os,'listdir',return_value=['123']),mock.patch.object(s.os,'getpid',return_value=999),mock.patch('builtins.open',side_effect=PermissionError):
            with self.assertRaises(PermissionError):self.io._process_scan(())
    def image_fixture(self,change=None):
        raw=b'\x7fELFfixture';info=types.SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o755,
            st_uid=0,st_gid=0,st_nlink=1,st_size=len(raw),st_mtime_ns=1,st_ctime_ns=2)
        row=dict(s.metadata(info),sha256=c.sha(raw));self.io.read=mock.Mock(return_value=(raw,row))
        if change:change(info)
        with mock.patch.object(s.os,'readlink',return_value='/usr/bin/ssh'),mock.patch.object(s.os,'open',return_value=99),\
             mock.patch.object(s.os,'fstat',return_value=info),mock.patch.object(s.os,'read',side_effect=[raw,b'']),\
             mock.patch.object(s.os,'close') as closed:
            try:return s.LocalReadOnlyIO._ssh_image(self.io,123)
            finally:closed.assert_called_once_with(99)
    def test_opened_proc_executable_hash_bound_to_canonical_file(self):
        digest,identity=self.image_fixture();self.assertEqual(digest,c.sha(b'\x7fELFfixture'));self.assertEqual(identity,[1,2])
    def test_proc_executable_inode_or_mode_change_rejected_and_closed(self):
        for field,value in (('st_ino',9),('st_uid',1002),('st_nlink',2),('st_mode',stat.S_IFREG|0o777)):
            with self.assertRaises(ValueError):self.image_fixture(lambda info:setattr(info,field,value))

class BootLinksTests(unittest.TestCase):
    ROOTS=('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system','/run/systemd/system.control','/run/systemd/transient','/run/systemd/generator.early','/run/systemd/generator','/run/systemd/generator.late')
    def setUp(self):
        self.io=object.__new__(s.LocalReadOnlyIO);self.entries={};self.stats={};self.links={}
        for root in self.ROOTS:self.directory(root)
        self.io.absent=lambda path:path not in self.stats
        self.io._authority=lambda fd,path:None
        @contextlib.contextmanager
        def parent(path):yield os.path.dirname(path),os.path.basename(path)
        self.io.parent=parent
    def info(self,mode):return types.SimpleNamespace(st_dev=1,st_ino=len(self.stats)+1,st_uid=0,st_gid=0,st_nlink=1,st_size=1,st_mode=mode,st_mtime_ns=1,st_ctime_ns=2)
    def directory(self,path):
        self.stats[path]=self.info(stat.S_IFDIR|0o755);self.entries[path]=[]
        parent=os.path.dirname(path)
        if parent in self.entries:self.entries[parent].append(os.path.basename(path))
    def link(self,path,target):
        self.stats[path]=self.info(stat.S_IFLNK|0o777);self.links[path]=target
        self.entries[os.path.dirname(path)].append(os.path.basename(path))
    def collect(self):
        def statfn(name,dir_fd=None,**unused):return copy.copy(self.stats[os.path.join(dir_fd,name) if dir_fd else name])
        with mock.patch.object(s.os,'stat',side_effect=statfn),mock.patch.object(s.os,'open',side_effect=lambda name,flags,dir_fd:os.path.join(dir_fd,name)),mock.patch.object(s.os,'fstat',side_effect=lambda fd:copy.copy(self.stats[fd])),mock.patch.object(s.os,'listdir',side_effect=lambda fd:list(self.entries[fd])),mock.patch.object(s.os,'readlink',side_effect=lambda name,dir_fd:self.links[os.path.join(dir_fd,name)]),mock.patch.object(s.os,'close'):
            return self.io.boot_links()
    def test_empty_complete_roots_do_not_infer_disabled(self):
        r=self.collect();self.assertEqual(r['unsupported_roots'],[]);self.assertEqual(r['restored_enablement'],'NOT_INFERRED')
        self.assertEqual(set(r['roots']),set(self.ROOTS))
        for root,row in r['roots'].items():self.assertEqual(row['links'],[]);self.assertIn(root,row['directories'])
    def test_mask_dependency_and_direct_alias_preserved(self):
        root=self.ROOTS[0];dep=root+'/multi-user.target.wants';self.directory(dep)
        self.link(root+'/'+u.GATEWAY,'/dev/null');self.link(dep+'/'+u.GATEWAY,'../'+u.GATEWAY)
        self.link(root+'/friendly.service',u.GATEWAY)
        r=self.collect();links=r['roots'][root]['links'];self.assertEqual(len(links),3)
        self.assertEqual({x['kind'] for x in links},{'BASE_MASK','DEPENDENCY','ALIAS_OR_BASE'})
        self.assertEqual(r['restored_enablement'],'NOT_INFERRED')
    def test_runtime_link_remains_evidence_without_state_default(self):
        root=self.ROOTS[1];dep=root+'/multi-user.target.wants';self.directory(dep)
        self.link(dep+'/xuanjun-uk-owner-callback.service','/etc/systemd/system/xuanjun-uk-owner-callback.service')
        r=self.collect();self.assertEqual(len(r['roots'][root]['links']),1)
        self.assertEqual(r['runtime_alias_semantics'],'REQUIRES_SYSTEMD239_REVIEW')
    def test_root_absence_is_explicit(self):
        self.stats.pop(self.ROOTS[1]);r=self.collect()
        self.assertEqual(r['roots'][self.ROOTS[1]],{'present':False,'directories':{},'links':[]})
    def test_wrong_link_owner_is_unknown_but_other_roots_survive(self):
        root=self.ROOTS[0];self.link(root+'/'+u.GATEWAY,'/dev/null');self.stats[root+'/'+u.GATEWAY].st_uid=1002
        r=self.collect();self.assertEqual(r['unsupported_roots'],[root]);self.assertTrue(r['roots'][self.ROOTS[1]]['present'])
    def test_symlink_dependency_directory_not_traversed(self):
        root=self.ROOTS[0];self.link(root+'/escape.target.wants','/etc/shadow');r=self.collect()
        self.assertEqual(r['roots'][root]['reason'],'BOOT_DEPENDENCY_DIRECTORY_TYPE')
    def test_entry_bound(self):
        root=self.ROOTS[0];self.entries[root]=['x']*4097;r=self.collect()
        self.assertEqual(r['roots'][root]['reason'],'BOOT_DIRECTORY_ENTRY_BOUND')
    def test_selected_regular_dependency_rejected(self):
        root=self.ROOTS[0];dep=root+'/multi-user.target.wants';self.directory(dep)
        path=dep+'/'+u.GATEWAY;self.stats[path]=self.info(stat.S_IFREG|0o644);self.entries[dep].append(u.GATEWAY)
        self.assertEqual(self.collect()['roots'][root]['reason'],'BOOT_SELECTED_DEPENDENCY_NOT_LINK')
    def test_install_occurrence_projection_and_unknown_directive(self):
        fields=u.install_fields(b'[Install]\nWantedBy=multi-user.target\nAlias=\nAlias=other.service\n')
        self.assertEqual(fields['Alias'],['','other.service'])
        with self.assertRaises(ValueError):u.install_fields(b'[Install]\nWantedBy=%i.target\n')
        with self.assertRaises(ValueError):u.install_fields(b'[Install]\nEnvironment=SECRET\n')
    def test_nested_directory_link_and_custom_target_not_omitted(self):
        root=self.ROOTS[0];nested=root+'/custom';self.directory(nested);nested+='/nested';self.directory(nested)
        self.link(nested+'/alias.service','/opt/custom/'+u.GATEWAY)
        row=self.collect()['roots'][root];self.assertEqual(len(row['links']),1)
        self.assertEqual(row['links'][0]['resolved_reference'],'/opt/custom/'+u.GATEWAY)
        self.assertEqual(row['scan_scope'],'BOUNDED_RECURSIVE_NOFOLLOW')
    def test_recursion_bound_is_explicit_unknown(self):
        root=self.ROOTS[0];path=root
        for unused in range(9):path+='/nested';self.directory(path)
        self.assertEqual(self.collect()['roots'][root]['reason'],'BOOT_RECURSION_BOUND')

if __name__=='__main__':unittest.main()
