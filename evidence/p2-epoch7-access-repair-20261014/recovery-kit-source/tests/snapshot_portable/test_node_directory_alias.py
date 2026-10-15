"""Fixed direct-dist wrapper and Node directory-alias fixtures; no UK execution."""
import contextlib
import copy
import os
import pathlib
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent),str(HERE.parent.parent/'recovery-design-candidate')]
import epoch7_snapshot as c
import snapshot_io as s
import unit_metadata as u
import openclaw_metadata as o
from test_openclaw_metadata import Fake as ProfileFake, NODE, UNIT, ACCOUNT, packed, node, refresh
from test_unit_metadata import Fake as UnitFake
from test_snapshot import native_pin_context,native_transition_fixture


def node_reference_fixture(expected_node=None):
    image=node() if expected_node is None else copy.deepcopy(expected_node)
    def directory(index,root):
        return {'kind':'DIRECTORY','uid':0 if root else 1002,'gid':0 if root else 1002,'mode':0o755,
            'dev':1,'ino':index+100,'nlink':2,'size':4096,'mtime_ns':3,'ctime_ns':4,
            'access_acl':False,'default_acl':False,'capability':False}
    link={'kind':'SYMLINK','uid':1002,'gid':1002,'mode':0o777,'dev':1,'ino':99,'nlink':1,
          'size':len('node-v24.21.0'),'mtime_ns':3,'ctime_ns':4}
    row=dict(image['metadata'],kind='FILE',sha256=image['sha256'],elf_header=True,
             access_acl=False,default_acl=False,capability=False)
    proof={'schema':1,'kind':'FIXED_NODE_DIRECTORY_ALIAS','reference_path':u.NODE_REFERENCE_PATH,
        'link':{'path':u.NODE_ALIAS_PATH,'target':'node-v24.21.0','metadata':link},
        'final':{'path':image['path'],'sha256':image['sha256'],'metadata':row},
        'ancestors':{path:directory(index,path in ('/','/home'))
                     for index,path in enumerate(u.NODE_REFERENCE_ANCESTORS)},'reread':'EXACT_PRE_POST'}
    return u.validate_node_reference(proof,image['path'],image['sha256'])


class PureAliasTests(unittest.TestCase):
    def setUp(self):self.proof=node_reference_fixture()
    def validate(self,value=None):return u.validate_node_reference(self.proof if value is None else value,NODE,node()['sha256'])
    def test_genuine188_bytes_hash_and_exact_recipe(self):
        self.assertEqual(len(u.DIRECT_DIST_WRAPPER),188)
        self.assertEqual(c.sha(u.DIRECT_DIST_WRAPPER),u.DIRECT_DIST_WRAPPER_SHA)
        recipe=u.launcher_recipe(u.DIRECT_DIST_WRAPPER,NODE)
        self.assertEqual(recipe['executable'],u.NODE_REFERENCE_PATH)
        self.assertEqual(recipe['entry_script'],u.NODE_PACKAGE_ROOT+'/dist/entry.js')
        self.assertEqual(recipe['environment_names'],[])
    def test_quote_expansion_and_unknown_wrapper_changes_refused(self):
        for raw in (u.DIRECT_DIST_WRAPPER+b'echo unsafe\n',u.DIRECT_DIST_WRAPPER.replace(b'"$@"',b'$@'),
                    u.DIRECT_DIST_WRAPPER.replace(b'node/bin/node',b'node/bin/other'),
                    u.DIRECT_DIST_WRAPPER.replace(b'"/home',b'"${HOME}'),
                    u.DIRECT_DIST_WRAPPER.replace(b'set -euo pipefail',b'set -e')):
            with self.assertRaises(ValueError):u.launcher_recipe(raw,NODE)
    def test_exact_relative_or_absolute_target_only(self):
        value=copy.deepcopy(self.proof);value['link']['target']=u.NODE_VERSION_DIRECTORY
        value['link']['metadata']['size']=len(u.NODE_VERSION_DIRECTORY)
        self.validate(value)
        for target in ('../node-v24.21.0','/tmp/node','node-v24.22.0','./node-v24.21.0'):
            value=copy.deepcopy(self.proof);value['link']['target']=target
            value['link']['metadata']['size']=len(target)
            with self.assertRaises(ValueError):self.validate(value)
    def test_native_hash_path_and_complete_schema_required(self):
        for expected_path,expected_sha in ((u.NODE_REFERENCE_PATH,node()['sha256']),(NODE,'0'*64)):
            with self.assertRaises(ValueError):u.validate_node_reference(self.proof,expected_path,expected_sha)
        for key in self.proof:
            value=copy.deepcopy(self.proof);del value[key]
            with self.assertRaises(ValueError):self.validate(value)
    def test_only_two_coherent_alias_owner_pairs_are_allowed(self):
        for uid,gid in ((0,0),(1002,1002)):
            value=copy.deepcopy(self.proof);value['link']['metadata'].update(uid=uid,gid=gid)
            self.assertEqual(self.validate(value)['link']['metadata']['uid'],uid)
        for uid,gid in ((0,1002),(1002,0),(1003,1003),(1,1)):
            value=copy.deepcopy(self.proof);value['link']['metadata'].update(uid=uid,gid=gid)
            with self.assertRaises(ValueError):self.validate(value)
    def test_link_type_ownership_and_size_are_bound(self):
        for key,bad in (('uid',0),('gid',0),('kind','DIRECTORY'),('nlink',2),('size',1),('mode',0o755),('mode',0o100777),('ino',True)):
            value=copy.deepcopy(self.proof);value['link']['metadata'][key]=bad
            with self.assertRaises(ValueError):self.validate(value)
    def test_final_file_and_all_ancestor_authority_is_strict(self):
        for key,bad in (('uid',0),('gid',0),('nlink',2),('mode',0o775),('mode',0o4755),('capability',True),
                        ('mode',0o100755),('access_acl',None),('elf_header',False),('size',u.NODE_MAXIMUM+1)):
            value=copy.deepcopy(self.proof);value['final']['metadata'][key]=bad
            with self.assertRaises(ValueError):self.validate(value)
        for path in u.NODE_REFERENCE_ANCESTORS:
            for key,bad in (('mode',0o775),('uid',1003),('capability',True),('default_acl',None)):
                value=copy.deepcopy(self.proof);value['ancestors'][path][key]=bad
                with self.assertRaises(ValueError):self.validate(value)
    def test_measurement_kind_cannot_be_admitted_even_after_no_unsafe_dirs(self):
        value=copy.deepcopy(self.proof);value.update(kind='FIXED_NODE_DIRECTORY_ALIAS_MEASUREMENT',
            admission='NOT_GRANTED',unsafe_ancestors=[])
        u.validate_node_reference_measurement(value,NODE,node()['sha256'])
        with self.assertRaises(ValueError):self.validate(value)
        for path in (u.NODE_TOOLS,u.NODE_VERSION_DIRECTORY):value['ancestors'][path]['mode']=0o775
        value['unsafe_ancestors']=sorted((u.NODE_TOOLS,u.NODE_VERSION_DIRECTORY))
        u.validate_node_reference_measurement(value,NODE,node()['sha256'])
        with self.assertRaises(ValueError):self.validate(value)
        value['ancestors']['/home/xuanjun_dev']['mode']=0o775
        with self.assertRaises(ValueError):u.validate_node_reference_measurement(value,NODE,node()['sha256'])
    def test_direct_profile_has_one_additional_fixed_source(self):
        direct=o.source_hashes(u.DIRECT_DIST_WRAPPER_SHA)
        self.assertEqual(len(direct),32);self.assertEqual(len(o.source_hashes('0'*64)),31)
        self.assertEqual(set(direct)-set(o.SOURCE_HASHES),{'dist/is-main-DYSvvM1W.mjs'})
        self.assertEqual(direct['dist/is-main-DYSvvM1W.mjs'],
            'cedd59a24eadaaf873515fabea73b776a66d40773c8ee5298f4946b9eef10469')


class DirectUnitFactsTests(unittest.TestCase):
    def setUp(self):
        self.io=UnitFake();self.proof=node_reference_fixture()
        original=c.decode(self.io.native_raws[2]);original['gatewayIdentity'].update(exe=NODE,sha256=node()['sha256'])
        self.io.native_raws=native_transition_fixture(original)
        for path,raw in zip((c.NATIVE,c.NATIVE_PRIOR,c.NATIVE_ORIGINAL,c.NATIVE_ATTEMPT),self.io.native_raws):
            self.io.add(path,raw,mode=0o644 if path==c.NATIVE else 0o600)
        self.io.add(u.LAUNCHER,u.DIRECT_DIST_WRAPPER,uid=1002,gid=1002,mode=0o711)
        self.io.add(u.NODE_PACKAGE_ROOT+'/dist/entry.js',b'// literal direct fixture only\n',uid=1002,gid=1002,mode=0o644)
        self.io.node_directory_reference=mock.Mock(return_value=copy.deepcopy(self.proof))
    def collect(self):
        with native_pin_context(self.io.native_raws):return u.collect_unit_facts(self.io)
    def test_direct_launcher_records_real_validated_alias_and_rechecks(self):
        result=self.collect();self.assertEqual(result['state'],'COMPLETE_UNREVIEWED',result['unsupported_sections'])
        launch=result['sections']['launcher']['evidence']
        self.assertEqual(launch['node_reference'],self.proof)
        self.assertEqual(launch['recipe']['executable'],u.NODE_REFERENCE_PATH)
        self.assertEqual(self.io.node_directory_reference.call_count,2)
    def test_unknown_alias_is_aggregated_without_admission(self):
        self.io.node_directory_reference.side_effect=ValueError('NODE_REFERENCE_EXACT_TARGET')
        result=self.collect();self.assertIn('launcher',result['unsupported_sections'])
        self.assertEqual(result['install_admission'],'NOT_GRANTED')
    def test_late_alias_race_refuses_launcher(self):
        changed=copy.deepcopy(self.proof);changed['link']['metadata']['ino']+=1
        self.io.node_directory_reference.side_effect=[self.proof,changed]
        self.assertEqual(self.collect()['sections']['launcher']['reason'],'LAUNCHER_NODE_ALIAS_LATE_RACE')
    def test_direct_private_source_candidates_remain_unreviewed(self):
        facts=self.collect();self.io.absent=lambda path:path not in self.io.files
        self.io.add('/etc/nginx/mime.types',b'types { text/html html; }\n',mode=0o644)
        self.io.add(u.NODE_PACKAGE_ROOT+'/package.json',packed({'name':'openclaw','version':'2026.9.9',
            'bin':{'openclaw':'openclaw.mjs'}}),uid=1002,gid=1002,mode=0o644)
        result=u.collect_source_review_inputs(self.io,facts)
        self.assertEqual(result['state'],'COMPLETE_UNREVIEWED',result['unsupported_sections'])
        evidence=result['sections']['openclaw_literal_sources']['evidence']
        self.assertEqual(evidence['known_2026_9_9_inputs']['state'],'MEASURED_DIRECT_ENTRY_UNREVIEWED')
        self.assertEqual(evidence['entry_path'],u.NODE_PACKAGE_ROOT+'/dist/entry.js')
        self.assertEqual(evidence['source_closure'],'NOT_VERIFIED')


class DirectProfileTests(unittest.TestCase):
    def setUp(self):
        self.io=ProfileFake();self.proof=node_reference_fixture()
        self.io.add(u.LAUNCHER,u.DIRECT_DIST_WRAPPER,uid=1002,gid=1002,mode=0o711)
        self.io.relay['openclaw_sha256']=u.DIRECT_DIST_WRAPPER_SHA
        self.io.add(o.RELAY,packed(self.io.relay),uid=0,gid=1002,mode=0o640)
        receipt=c.decode(self.io.files[o.PROVISION]);row=next(x for x in receipt['targets'] if x['target']==o.RELAY)
        row['rendered_sha256']=c.sha(self.io.files[o.RELAY]);self.io.add(o.PROVISION,packed(receipt))
        self.io.observation['unit_metadata']['sections']['launcher']['evidence']={
            'sha256':u.DIRECT_DIST_WRAPPER_SHA,'recipe':u.launcher_recipe(u.DIRECT_DIST_WRAPPER,NODE),
            'node_reference':copy.deepcopy(self.proof)}
        extra='dist/is-main-DYSvvM1W.mjs';raw=b'// synthetic direct entry guard\n'
        self.io.add(u.NODE_PACKAGE_ROOT+'/'+extra,raw,uid=1002,gid=1002,mode=0o644)
        self.extra={extra:c.sha(raw)}
        self.io.node_directory_reference=mock.Mock(return_value=copy.deepcopy(self.proof))
        refresh(self.io.observation)
    def collect(self):
        with mock.patch.object(o,'DIRECT_ONLY_SOURCE_HASHES',self.extra):return self.io.collect()
    def test_direct_profile_32_sources_lexical_and_canonical_are_distinct(self):
        value=self.collect();self.assertEqual(value['state'],'COMPLETE_UNREVIEWED',value['missing_fields'])
        recipe=value['recipe_evidence'];self.assertEqual(len(recipe['files']),32)
        self.assertEqual(recipe['package_root'],u.NODE_PACKAGE_ROOT)
        self.assertEqual(recipe['launcher']['node_reference'],self.proof)
        self.assertEqual(recipe['launcher']['recipe']['executable'],u.NODE_REFERENCE_PATH)
        self.assertEqual(recipe['node']['path'],NODE)
        self.assertEqual(self.io.node_directory_reference.call_count,2)
    def test_missing_alias_proof_or_32nd_source_holds(self):
        evidence=self.io.observation['unit_metadata']['sections']['launcher']['evidence']
        del evidence['node_reference'];self.assertIn('launcher',self.collect()['missing_fields'])
        evidence['node_reference']=self.proof
        del self.io.files[u.NODE_PACKAGE_ROOT+'/dist/is-main-DYSvvM1W.mjs']
        self.assertIn('source:dist/is-main-DYSvvM1W.mjs',self.collect()['missing_fields'])
    def test_node_descriptor_and_alias_late_change_hold(self):
        changed=copy.deepcopy(self.proof);changed['final']['metadata']['ino']+=1
        self.io.node_directory_reference.side_effect=[self.proof,changed]
        self.assertIn('stability',self.collect()['missing_fields'])
        self.io.node_directory_reference.side_effect=None
        self.io.observation['evidence']['retained']['native_components']['components'][NODE]['ino']+=1
        self.assertIn('node',self.collect()['missing_fields'])
    def test_quiet_projection_requires_independent_hash_and_proof(self):
        args=dict(manager_selected={key:None for key in o.ENV_KEYS},account=ACCOUNT,unit_raw=UNIT,
            wrapper_raw=u.DIRECT_DIST_WRAPPER,node_path=NODE,config_raw=b'{}',
            dotenv_raw_by_path={path:None for path in o.dotenv_paths(UNIT)},relay_config_raw=packed(self.io.relay))
        with self.assertRaises(ValueError):o.quiet_projection(**args)
        args['node_reference']=self.proof
        with self.assertRaises(ValueError):o.quiet_projection(**args)
        args['node_sha256']=node()['sha256'];o.quiet_projection(**args)
        args['node_sha256']='0'*64
        with self.assertRaises(ValueError):o.quiet_projection(**args)


class ConcreteNodeDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='epoch7-node-directory-fixture-');self.root=self.temp.name
        for path in u.NODE_REFERENCE_ANCESTORS:
            real=self.root+path if path!='/' else self.root
            os.makedirs(real,exist_ok=True);os.chmod(real,0o755)
        self.raw=b'\x7fELF'+b'x'*150000;self.sha=c.sha(self.raw)
        self.file=self.root+NODE
        with open(self.file,'wb') as stream:stream.write(self.raw)
        os.chmod(self.file,0o755);os.symlink('node-v24.21.0',self.root+u.NODE_ALIAS_PATH)
        roots={os.lstat(self.root).st_ino,os.lstat(self.root+'/home').st_ino}
        self.patches=[]
        for name in ('stat','lstat','fstat'):
            original=getattr(os,name)
            def fake(*args,_call=original,**kwargs):
                value=_call(*args,**kwargs);uid=0 if value.st_ino in roots else 1002
                return types.SimpleNamespace(**dict({key:getattr(value,key) for key in
                    ('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')},st_uid=uid,st_gid=uid))
            self.patches.append(mock.patch.object(s.os,name,side_effect=fake))
        for patch in self.patches:patch.start()
        self.io=object.__new__(s.LocalReadOnlyIO)
        pins={path:{'uid':0 if path in ('/','/home') else 1002,'gid':0 if path in ('/','/home') else 1002,'mode':0o755}
              for path in u.NODE_REFERENCE_ANCESTORS}
        s.DescriptorReader.__init__(self.io,pins,root=self.root);self.io.check_locks=mock.Mock()
    def tearDown(self):
        for patch in reversed(self.patches):patch.stop()
        self.temp.cleanup()
    def test_real_component_symlink_and_streamed_hash_two_rounds(self):
        original=s.os.read;sizes=[]
        def read(fd,maximum):sizes.append(maximum);return original(fd,maximum)
        with mock.patch.object(s.os,'read',side_effect=read):proof=self.io.node_directory_reference(NODE,self.sha)
        self.assertEqual(proof['link']['target'],'node-v24.21.0')
        self.assertEqual(proof['final']['metadata']['size'],len(self.raw))
        self.assertEqual(proof['final']['sha256'],self.sha);self.assertTrue(all(size<=65536 for size in sizes))
        self.assertGreater(len(sizes),4);u.validate_node_reference(proof,NODE,self.sha)
    def test_alias_target_escape_symlink_leaf_and_wrong_hash_refused(self):
        with self.assertRaises(ValueError):self.io.node_directory_reference(NODE,'0'*64)
        os.unlink(self.root+u.NODE_ALIAS_PATH);os.symlink('../node-v24.21.0',self.root+u.NODE_ALIAS_PATH)
        with self.assertRaises(ValueError):self.io.node_directory_reference(NODE,self.sha)
        os.unlink(self.root+u.NODE_ALIAS_PATH);os.symlink('node-v24.21.0',self.root+u.NODE_ALIAS_PATH)
        os.rename(self.file,self.file+'.saved');os.symlink('node.saved',self.file)
        with self.assertRaises(ValueError):self.io.node_directory_reference(NODE,self.sha)
    def test_pre_narrowing_measurement_is_distinct_and_not_admissible(self):
        for path in (u.NODE_TOOLS,u.NODE_VERSION_DIRECTORY):os.chmod(self.root+path,0o775)
        with self.assertRaises(ValueError):self.io.node_directory_reference(NODE,self.sha)
        value=self.io.measure_node_directory_reference(NODE,self.sha)
        self.assertEqual(value['unsafe_ancestors'],sorted((u.NODE_TOOLS,u.NODE_VERSION_DIRECTORY)))
        with self.assertRaises(ValueError):u.validate_node_reference(value,NODE,self.sha)
        for path in (u.NODE_TOOLS,u.NODE_VERSION_DIRECTORY):os.chmod(self.root+path,0o755)
        self.io.node_directory_reference(NODE,self.sha)
    def test_first_close_interrupt_attempts_every_owned_descriptor_once(self):
        original_close=s.os.close;closed=[];interrupted=KeyboardInterrupt('fixture cleanup interrupt')
        def close(fd):
            closed.append(fd);original_close(fd)
            if len(closed)==1:raise interrupted
        with mock.patch.object(s.os,'close',side_effect=close):
            with self.assertRaises(KeyboardInterrupt) as caught:self.io.node_directory_reference(NODE,self.sha)
        self.assertIs(caught.exception,interrupted)
        self.assertEqual(str(caught.exception.__cause__),'NODE_REFERENCE_CLEANUP_UNKNOWN')
        self.assertEqual(len(closed),8);self.assertEqual(len(set(closed)),8)
        for fd in closed:
            with self.assertRaises(OSError):os.fstat(fd)
    def test_primary_read_failure_survives_cleanup_interrupt(self):
        original_close=s.os.close;closed=[];primary=ValueError('FIXTURE_NODE_READ_FAILED')
        def close(fd):
            closed.append(fd);original_close(fd)
            if len(closed)==1:raise KeyboardInterrupt('fixture cleanup interrupt')
        with mock.patch.object(s.os,'read',side_effect=primary),mock.patch.object(s.os,'close',side_effect=close):
            with self.assertRaises(ValueError) as caught:self.io.node_directory_reference(NODE,self.sha)
        self.assertIs(caught.exception,primary)
        self.assertEqual(str(caught.exception.__cause__),'NODE_REFERENCE_CLEANUP_UNKNOWN')
        self.assertEqual(len(closed),8);self.assertEqual(len(set(closed)),8)
        for fd in closed:
            with self.assertRaises(OSError):os.fstat(fd)
    def test_unknown_acl_capability_and_midread_change_refuse(self):
        with mock.patch.object(s,'xattr',return_value=b'present'):
            with self.assertRaises(ValueError):self.io.node_directory_reference(NODE,self.sha)
        original=s.os.read;once=[False]
        def changed(fd,maximum):
            value=original(fd,maximum)
            if not once[0]:once[0]=True;os.utime(self.file,ns=(1,2))
            return value
        with mock.patch.object(s.os,'read',side_effect=changed):
            with self.assertRaises(ValueError):self.io.node_directory_reference(NODE,self.sha)


if __name__=='__main__':unittest.main()
