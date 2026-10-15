"""Python pair adapters: temporary local files and bounded synthetic OS facts.

The temporary ELF fixture is not the UK interpreter. Only its byte digest and
local UID/GID presentation are mapped; the shared proof validator stays real.
No host commands, package queries, production paths or services are used.
"""
import contextlib
import copy
import hashlib
import os
import pathlib
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parent.parent/'recovery-design-candidate')]
import epoch7_snapshot as c
import epoch7_delta as d
import epoch7_python_identity as p
import snapshot_io as s
import observe_epoch7 as observation
import probe_metadata as probe
import unit_metadata as units
from test_python_identity import proof_fixture
from test_probe_metadata import Fake as ProbeFake, ROOT
from test_unit_metadata import Fake as UnitFake

RAW = b'\x7fELF' + b'f'*(p.RETAINED_SIZE-4)
REAL_SHA = c.sha


def fixture_sha(raw):
    return p.RETAINED_SHA256 if raw == RAW else REAL_SHA(raw)


class ConcretePairReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='epoch7-python-pair-fixture-')
        self.root = self.temp.name
        os.makedirs(self.root+'/usr/libexec')
        for path in (self.root+'/usr', self.root+'/usr/libexec'): os.chmod(path, 0o755)
        self.first = self.root+p.PYTHON_PATHS[0]; self.second = self.root+p.PYTHON_PATHS[1]
        with open(self.first,'wb') as stream: stream.write(RAW)
        os.chmod(self.first, 0o755); os.link(self.first,self.second); os.chmod(self.root,0o555)
        original = {name:getattr(os,name) for name in ('stat','lstat','fstat')}
        def measured(call):
            def invoke(*args,**kwargs):
                value=call(*args,**kwargs)
                return types.SimpleNamespace(**dict({key:getattr(value,key) for key in
                    ('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')},
                    st_uid=0,st_gid=0))
            return invoke
        self.patches=[mock.patch.object(s.os,name,side_effect=measured(call)) for name,call in original.items()]
        self.patches.append(mock.patch.object(c,'sha',side_effect=fixture_sha))
        for patch in self.patches:patch.start()
        pins={path:{'uid':0,'gid':0,'mode':0o555 if path=='/' else 0o755} for path in p.ANCESTOR_PATHS}
        self.reader=s.DescriptorReader(pins,root=self.root)
    def tearDown(self):
        for patch in reversed(self.patches):patch.stop()
        os.chmod(self.root,0o755);self.temp.cleanup()
    def test_two_real_names_shared_inode_two_full_rounds(self):
        with mock.patch.object(self.reader,'_python_pair_round',wraps=self.reader._python_pair_round) as rounds:
            raw,row=self.reader.read_python(p.PYTHON_PATHS[0])
        self.assertEqual(raw,RAW);self.assertEqual(rounds.call_count,2)
        proof=p.validate_pair_proof(row['python_identity'])
        self.assertEqual(row,dict(proof['sample']['files'][p.PYTHON_PATHS[0]],python_identity=proof))
        self.assertEqual(self.reader.read_python(p.PYTHON_PATHS[1])[1]['python_identity'],proof)
    def test_generic_read_and_file_info_still_refuse_pair(self):
        for name in p.PYTHON_PATHS:
            with self.assertRaises(ValueError):self.reader.read(name)
            with self.assertRaises(ValueError):self.reader.file_info(name)
    def test_scope_and_limit_reject_before_io(self):
        with mock.patch.object(self.reader,'_python_pair_round',side_effect=AssertionError('no read')):
            for path in ('/tmp/python','/usr/bin/python3','/usr/libexec/../libexec/platform-python3.6'):
                with self.assertRaises(ValueError):self.reader.read_python(path)
            for limit in (True,0,p.RETAINED_SIZE-1,536870913):
                with self.assertRaises(ValueError):self.reader.read_python(p.PYTHON_PATHS[0],limit)
    def test_third_hardlink_and_single_link_refused(self):
        third=self.root+'/usr/libexec/third';os.link(self.first,third)
        with self.assertRaises(ValueError):self.reader.read_python(p.PYTHON_PATHS[0])
        os.unlink(third);os.unlink(self.second)
        with self.assertRaises(ValueError):self.reader.read_python(p.PYTHON_PATHS[0])
    def test_second_name_replacement_or_symlink_refused(self):
        os.unlink(self.second)
        with open(self.second,'wb') as stream:stream.write(RAW)
        os.chmod(self.second,0o755)
        with self.assertRaises(ValueError):self.reader.read_python(p.PYTHON_PATHS[0])
        os.unlink(self.second);os.symlink(self.first,self.second)
        with self.assertRaises(ValueError):self.reader.read_python(p.PYTHON_PATHS[0])
    def test_wrong_bytes_and_mode_refused(self):
        with open(self.first,'r+b') as stream:stream.seek(4);stream.write(b'x')
        with self.assertRaises(ValueError):self.reader.read_python(p.PYTHON_PATHS[0])
        with open(self.first,'wb') as stream:stream.write(RAW)
        os.chmod(self.first,0o775)
        with self.assertRaises(ValueError):self.reader.read_python(p.PYTHON_PATHS[0])
    def test_no_follow_ancestor(self):
        os.rename(self.root+'/usr/libexec',self.root+'/usr/real')
        os.symlink('real',self.root+'/usr/libexec')
        with self.assertRaises(OSError):self.reader.read_python(p.PYTHON_PATHS[0])
    def test_xattr_presence_and_errors_refuse(self):
        for value in (b'',b'acl-or-capability'):
            with mock.patch.object(s,'xattr',return_value=value):
                with self.assertRaises(ValueError):self.reader.read_python(p.PYTHON_PATHS[0])
        with mock.patch.object(s,'xattr',side_effect=PermissionError('fixture')):
            with self.assertRaises(PermissionError):self.reader.read_python(p.PYTHON_PATHS[0])
    def test_capability_change_after_read_refused(self):
        original=s.xattr;calls=[0]
        def changed(fd,name):
            if name=='security.capability':
                calls[0]+=1
                if calls[0]==6:return b'late-capability'
            return original(fd,name)
        with mock.patch.object(s,'xattr',side_effect=changed):
            with self.assertRaises(ValueError):self.reader.read_python(p.PYTHON_PATHS[0])
    def test_file_change_between_rounds_refused(self):
        original=self.reader._python_pair_round;calls=[0]
        def changed():
            value=original();calls[0]+=1
            if calls[0]==1:os.utime(self.first,ns=(11,12))
            return value
        with mock.patch.object(self.reader,'_python_pair_round',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'PRE_POST_CHANGED'):self.reader.read_python(p.PYTHON_PATHS[0])
    def test_all_descriptors_close_on_partial_failure(self):
        opened=[];closed=[];opener=s.os.open;closer=s.os.close
        def opened_call(*args,**kwargs):
            fd=opener(*args,**kwargs);opened.append(fd);return fd
        def closed_call(fd):closed.append(fd);return closer(fd)
        with mock.patch.object(s.os,'open',side_effect=opened_call),mock.patch.object(s.os,'close',side_effect=closed_call),mock.patch.object(s.os,'read',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.reader.read_python(p.PYTHON_PATHS[0])
        self.assertEqual(set(opened),set(closed));self.assertEqual(len(opened),len(closed))
    def test_close_failure_does_not_skip_other_descriptors(self):
        closed=[];closer=s.os.close
        def fail_once(fd):
            closer(fd);closed.append(fd)
            if len(closed)==1:raise OSError('fixture close report')
        with mock.patch.object(s.os,'close',side_effect=fail_once):
            with self.assertRaises(OSError):self.reader.read_python(p.PYTHON_PATHS[0])
        self.assertEqual(len(closed),5)


class AliasAndNativeTests(unittest.TestCase):
    def setUp(self):
        self.io=object.__new__(s.LocalReadOnlyIO);self.proof=proof_fixture()
        self.links={'/usr/bin/python3':'/etc/alternatives/python3',
            '/etc/alternatives/python3':'/usr/bin/python3.6','/usr/bin/python3.6':p.PYTHON_PATHS[0],
            '/usr/libexec/platform-python':p.PYTHON_PATHS[0]}
        self.stats={path:types.SimpleNamespace(st_mode=stat.S_IFLNK|0o777,st_uid=0,st_gid=0,
            st_dev=1,st_ino=i+100,st_nlink=1,st_size=len(link),st_mtime_ns=1,st_ctime_ns=2)
            for i,(path,link) in enumerate(sorted(self.links.items()))}
        row=self.proof['sample']['files'][p.PYTHON_PATHS[0]]
        self.stats[p.PYTHON_PATHS[0]]=types.SimpleNamespace(**dict(
            {'st_'+key:value for key,value in row.items() if key in p.METADATA_FIELDS},st_mode=stat.S_IFREG|row['mode']))
        @contextlib.contextmanager
        def parent(path):yield 99,path
        self.io.parent=parent
        self.io.read_python=mock.Mock(side_effect=lambda path,maximum:(RAW,dict(self.proof['sample']['files'][path],python_identity=copy.deepcopy(self.proof))))
        self.patches=[mock.patch.object(s.os,'stat',side_effect=lambda name,**kw:copy.copy(self.stats[name])),
                      mock.patch.object(s.os,'readlink',side_effect=lambda name,**kw:self.links[name])]
        for patch in self.patches:patch.start()
    def tearDown(self):
        for patch in reversed(self.patches):patch.stop()
    def test_alias_and_canonical_references_preserve_requested_path(self):
        for reference in s.PYTHON_REFERENCES:
            value=self.io.executable_reference(reference)
            self.assertEqual(value['reference_path'],reference)
            self.assertEqual(value['final']['path'],p.PYTHON_PATHS[0])
            self.assertEqual(value['final']['metadata']['python_identity'],self.proof)
            self.assertEqual(self.io.canonical_python(reference),p.PYTHON_PATHS[0])
        self.assertEqual(self.io.executable_reference(p.PYTHON_PATHS[0])['links'],[])
    def test_unknown_or_dot_alias_forms_refused(self):
        for reference in ('/tmp/python','/usr/bin/../bin/python3',p.PYTHON_PATHS[1]):
            with self.assertRaises(ValueError):self.io.canonical_python(reference)
        for link in ('/tmp/python','/usr/bin/../bin/python3.6','//usr/bin/python3.6','python3\n','./python3.6'):
            self.links['/usr/bin/python3']=link
            with self.assertRaises(ValueError):self.io.executable_reference('/usr/bin/python3')
    def test_alias_owner_or_late_chain_change_refused(self):
        self.stats['/usr/bin/python3'].st_uid=1002
        with self.assertRaises(ValueError):self.io.executable_reference('/usr/bin/python3')
        self.stats['/usr/bin/python3'].st_uid=0
        def changed(name,**kw):self.stats[name].st_ctime_ns+=1;return self.links[name]
        with mock.patch.object(s.os,'readlink',side_effect=changed):
            with self.assertRaises(ValueError):self.io.executable_reference('/usr/bin/python3')
    def test_native_identity_preserves_reference_and_both_file_proofs(self):
        bridge='/opt/xuanjun-control-releases/integration-'+d.OLD_MANIFEST[:16]+'/stage1/native_ledger_bridge.py'
        client='/etc/xuanjun-development/p2-native-ledger-client.json';node='/usr/bin/node'
        def read(path,maximum):
            raw=path.encode();return raw,dict(kind='FILE',uid=1002 if path==node else 0,sha256=REAL_SHA(raw))
        self.io.read=read
        ledger={'python':'/usr/bin/python3','pythonSha256':p.RETAINED_SHA256,'bridge':bridge,'config':client,
                'files':{path:REAL_SHA(path.encode()) for path in (bridge,client)}}
        native={'ledger':ledger,'gatewayIdentity':{'user':'xuanjun_dev','exe':node,'sha256':REAL_SHA(node.encode()),
                'cgroup':'/system.slice/xuanjun-uk-openclaw.service'}}
        with mock.patch.object(s.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=1002)):
            result=self.io.native_identity(native,{'ledger':copy.deepcopy(ledger)})
        self.assertNotIn('/usr/bin/python3',result['components'])
        self.assertEqual(result['python_reference']['reference_path'],'/usr/bin/python3')
        for path in p.PYTHON_PATHS:self.assertEqual(result['components'][path]['python_identity'],self.proof)


class ProjectionTests(unittest.TestCase):
    def setUp(self):self.proof=proof_fixture()
    def pair_row(self):return dict(self.proof['sample']['files'][p.PYTHON_PATHS[0]],python_identity=copy.deepcopy(self.proof))
    def test_observation_records_both_exact_file_rows(self):
        backend=object.__new__(observation.ObservationIO);backend.observed_metadata={}
        with mock.patch.object(s.LocalReadOnlyIO,'read_python',return_value=(RAW,self.pair_row())):
            result=backend.read_python(p.PYTHON_PATHS[0])
        self.assertEqual(result[1],self.pair_row());self.assertEqual(set(backend.observed_metadata),set(p.PYTHON_PATHS))
        for row in backend.observed_metadata.values():self.assertEqual(row['python_identity'],self.proof)
    def test_local_io_checks_existing_locks_before_and_after(self):
        backend=object.__new__(s.LocalReadOnlyIO);backend.check_locks=mock.Mock()
        with mock.patch.object(s.DescriptorReader,'read_python',return_value=(RAW,self.pair_row())):
            backend.read_python(p.PYTHON_PATHS[0])
        self.assertEqual(backend.check_locks.call_count,2)
    def test_probe_ingredients_preserve_pair_proof_and_retained_hash(self):
        io=ProbeFake();io.python=p.PYTHON_PATHS[0]
        io.settings['ledger']['pythonSha256']=p.RETAINED_SHA256;io.bind()
        io.read_python=mock.Mock(return_value=(RAW,self.pair_row()))
        with mock.patch.object(c,'sha',side_effect=fixture_sha):result=probe.collect_probe_ingredients(io,ROOT)
        self.assertEqual(result['ingredient_state'],'COMPLETE_UNREVIEWED')
        self.assertEqual(result['ingredients']['python'],{'path':p.PYTHON_PATHS[0],
            'sha256':p.RETAINED_SHA256,'python_identity':self.proof})
        self.assertEqual(io.read_python.call_count,2)
        self.assertNotIn(p.PYTHON_PATHS[0],[path for path,unused in io.reads])
    def test_probe_missing_proof_wrong_hash_and_late_pair_change_hold(self):
        for failure in ('missing','hash','race'):
            io=ProbeFake();io.python=p.PYTHON_PATHS[0]
            io.settings['ledger']['pythonSha256']=p.RETAINED_SHA256 if failure!='hash' else '0'*64;io.bind()
            row=self.pair_row();second=copy.deepcopy(row)
            if failure=='missing':row.pop('python_identity');second=row
            if failure=='race':second['ctime_ns']+=1
            io.read_python=mock.Mock(side_effect=[(RAW,row),(RAW,second)])
            with mock.patch.object(c,'sha',side_effect=fixture_sha):result=probe.collect_probe_ingredients(io,ROOT)
            self.assertIn('python',result['missing_fields']);self.assertNotIn('ingredients',result)
    def test_unit_metadata_preserves_proof_and_missing_proof_is_unknown(self):
        io=UnitFake()
        def reference():return {'reference_path':'/usr/bin/python3','links':[],
            'final':{'path':p.PYTHON_PATHS[0],'sha256':p.RETAINED_SHA256,'format':'ELF','metadata':self.pair_row()}}
        io.python_reference=reference
        from test_snapshot import native_pin_context
        with native_pin_context(io.native_raws):result=units.collect_unit_facts(io)
        self.assertEqual(result['sections']['python_reference']['state'],'MEASURED_UNREVIEWED')
        self.assertEqual(result['sections']['python_reference']['evidence']['final']['metadata']['python_identity'],self.proof)
        bad=reference();bad['final']['metadata'].pop('python_identity');io.python_reference=lambda:bad
        with native_pin_context(io.native_raws):result=units.collect_unit_facts(io)
        self.assertEqual(result['sections']['python_reference']['state'],'UNKNOWN')


if __name__=='__main__':unittest.main()
