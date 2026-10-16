"""Exact Python-pair propagation and bounded descriptor-reader regressions.

The fixed hash/proof validators are never patched. Positive proof orchestration
uses the public recorded metadata fixture at the read boundary; real temporary
hardlinks exercise the no-follow reader but cannot impersonate the retained ELF.
"""
import copy
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

import epoch7_delta as d
import epoch7_python_identity as p
import epoch7_resource_plan as plan
import epoch7_resource_observer as reader_module
import epoch7_host_factory as factory
from test_python_identity import sample_fixture,proof_fixture


def measured(path,proof=None):
    proof=proof_fixture() if proof is None else proof
    return dict({key:proof['sample']['files'][path][key] for key in p.METADATA_FIELDS},
                kind='FILE',sha256=p.RETAINED_SHA256,python_identity=copy.deepcopy(proof))


def executable_bundle():
    proof=proof_fixture();files={path:measured(path,proof) for path in p.PYTHON_PATHS}
    def regular(path):
        row=dict(files[p.PYTHON_PATHS[0]]);row.pop('python_identity')
        row.update(nlink=1,ino=900+len(files),sha256=d.digest(path));files[path]=row
        return row
    for path in ('/usr/bin/systemctl','/usr/bin/node','/usr/sbin/runuser','/usr/sbin/nginx',
                 '/home/xuanjun_dev/.openclaw/bin/openclaw','/usr/lib/node/openclaw.mjs'):regular(path)
    def reference(path,final):
        return {'reference_path':path,'links':[] if path==final else [{'path':path,'link':final,'metadata':{}}],
            'final':{'path':final,'format':'ELF','sha256':files[final]['sha256'],'metadata':copy.deepcopy(files[final])}}
    sections={name:{'state':'MEASURED_UNREVIEWED','evidence':evidence} for name,evidence in (
        ('python_reference',reference('/usr/bin/python3',p.PYTHON_PATHS[0])),
        ('runuser_binary',{'reference':reference('/usr/sbin/runuser','/usr/sbin/runuser')}),
        ('nginx_binary',{'reference':reference('/usr/sbin/nginx','/usr/sbin/nginx')}),
        ('launcher',{'path':'/home/xuanjun_dev/.openclaw/bin/openclaw',
            'sha256':files['/home/xuanjun_dev/.openclaw/bin/openclaw']['sha256'],
            'metadata':files['/home/xuanjun_dev/.openclaw/bin/openclaw'],
            'entry_script':{'path':'/usr/lib/node/openclaw.mjs','sha256':files['/usr/lib/node/openclaw.mjs']['sha256'],
                            'metadata':files['/usr/lib/node/openclaw.mjs']}}))}
    value={'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED',
        'unit_metadata':{'state':'COMPLETE_UNREVIEWED','unsupported_sections':[],'sections':sections},
        'evidence':{'retained':{'files':files,'native_components':{'components':{}}}},
        'policy':{'executables':{'systemctl':{'path':'/usr/bin/systemctl'}}}}
    refresh(value)
    native=d.canonical({'ledger':{'python':p.PYTHON_PATHS[0]},'gatewayIdentity':{'exe':'/usr/bin/node'}})
    return value,native


def refresh(value):
    for key in ('unit_metadata','evidence','policy'):value[key+'_sha256']=d.digest(value[key])


class PythonSpecTests(unittest.TestCase):
    def test_file_spec_preserves_only_exact_scoped_proof(self):
        row=measured(p.PYTHON_PATHS[0]);spec=plan.file_spec(p.PYTHON_PATHS[0],row)
        self.assertEqual(spec['python_identity'],proof_fixture())
        self.assertEqual(spec['access_acl'],'user::rwx\ngroup::r-x\nother::r-x\n')
        spec['python_identity']['sample']['files'][p.PYTHON_PATHS[0]]['ino']+=1
        self.assertEqual(row['python_identity'],proof_fixture())
    def test_both_fixed_names_have_identical_proof(self):
        self.assertEqual(plan.file_spec(p.PYTHON_PATHS[0],measured(p.PYTHON_PATHS[0]))['python_identity'],
                         plan.file_spec(p.PYTHON_PATHS[1],measured(p.PYTHON_PATHS[1]))['python_identity'])
    def test_unproved_two_links_and_any_generic_hardlink_refuse(self):
        row=measured(p.PYTHON_PATHS[0]);row.pop('python_identity')
        for path in (p.PYTHON_PATHS[0],'/usr/bin/unrelated'):
            with self.assertRaisesRegex(ValueError,'SINGLE_LINK'):plan.file_spec(path,row)
    def test_proof_cannot_grant_other_path(self):
        with self.assertRaisesRegex(ValueError,'PAIR_PATH'):plan.file_spec('/usr/bin/python3',measured(p.PYTHON_PATHS[0]))
    def test_proof_cannot_hide_changed_or_untyped_measured_metadata(self):
        for key in p.METADATA_FIELDS:
            row=measured(p.PYTHON_PATHS[0]);row[key]+=1
            with self.assertRaisesRegex(ValueError,'PAIR_METADATA'):plan.file_spec(p.PYTHON_PATHS[0],row)
        row=measured(p.PYTHON_PATHS[0]);row['uid']=False
        with self.assertRaisesRegex(ValueError,'PAIR_METADATA'):plan.file_spec(p.PYTHON_PATHS[0],row)
    def test_null_proof_and_acl_grant_refuse(self):
        for key,value in (('python_identity',None),('access_acl','user:1002:rwx\n'),
                          ('capability',True),('default_acl',True),('elf_header',False)):
            row=measured(p.PYTHON_PATHS[0]);row[key]=value
            with self.assertRaises(ValueError):plan.file_spec(p.PYTHON_PATHS[0],row)
    def test_generic_single_link_shape_is_unchanged(self):
        row=measured(p.PYTHON_PATHS[0]);row.pop('python_identity');row['nlink']=1
        self.assertEqual(set(plan.file_spec('/usr/bin/other',row)),reader_module.FILE_FIELDS)
    def test_factory_preserves_pair_and_alias_without_new_seed(self):
        value,native=executable_bundle();result=factory.build_executable_specs(value,native)
        self.assertEqual(len(factory.INPUTS-factory.DERIVED_INPUTS),17)
        for path in p.PYTHON_PATHS:self.assertEqual(result[path],plan.file_spec(path,measured(path)))
        self.assertEqual(result['/usr/bin/python3']['reference']['final']['metadata']['python_identity'],proof_fixture())
    def test_native_alias_refuses_even_when_unit_alias_is_measured(self):
        value,native=executable_bundle()
        reference=copy.deepcopy(value['unit_metadata']['sections']['python_reference']['evidence'])
        value['evidence']['retained']['native_components']['python_reference']=reference;refresh(value)
        native=d.canonical({'ledger':{'python':'/usr/bin/python3'},'gatewayIdentity':{'exe':'/usr/bin/node'}})
        with self.assertRaisesRegex(ValueError,'NATIVE_PYTHON_CANONICAL_REQUIRED'):factory.build_executable_specs(value,native)
    def test_canonical_native_reference_preserves_pair_and_separate_unit_alias(self):
        value,native=executable_bundle()
        reference=copy.deepcopy(value['unit_metadata']['sections']['python_reference']['evidence'])
        reference.update(reference_path=p.PYTHON_PATHS[0],links=[])
        value['evidence']['retained']['native_components']['python_reference']=reference;refresh(value)
        result=factory.build_executable_specs(value,native)
        self.assertEqual(result['/usr/bin/python3']['reference']['reference_path'],'/usr/bin/python3')
        for path in p.PYTHON_PATHS:self.assertEqual(result[path],plan.file_spec(path,measured(path)))
    def test_unmeasured_native_alias_requires_actual_reference(self):
        value,native=executable_bundle()
        native=d.canonical({'ledger':{'python':'/usr/bin/python3'},'gatewayIdentity':{'exe':'/usr/bin/node'}})
        with self.assertRaisesRegex(ValueError,'NATIVE_EXECUTABLE_METADATA'):factory.build_executable_specs(value,native)
    def test_native_alias_reference_cannot_change_requested_path(self):
        value,native=executable_bundle()
        reference=copy.deepcopy(value['unit_metadata']['sections']['python_reference']['evidence'])
        value['evidence']['retained']['native_components']['python_reference']=reference;refresh(value)
        with self.assertRaisesRegex(ValueError,'NATIVE_PYTHON_ALIAS_SCOPE'):factory.build_executable_specs(value,native)
    def test_factory_requires_both_measured_members(self):
        value,native=executable_bundle();del value['evidence']['retained']['files'][p.PYTHON_PATHS[1]];refresh(value)
        with self.assertRaisesRegex(ValueError,'BOTH_MEASURED'):factory.build_executable_specs(value,native)
    def test_duplicate_measurements_cannot_silently_replace_pair_proof(self):
        value,native=executable_bundle();row=copy.deepcopy(value['evidence']['retained']['files'][p.PYTHON_PATHS[0]])
        for item in row['python_identity']['sample']['files'].values():item['ino']+=1
        row['ino']+=1
        value['evidence']['retained']['native_components']['components'][p.PYTHON_PATHS[0]]=row;refresh(value)
        with self.assertRaisesRegex(ValueError,'MEASUREMENT_CONFLICT'):factory.build_executable_specs(value,native)
    def test_factory_rejects_conflicting_alias_proof(self):
        value,native=executable_bundle();final=value['unit_metadata']['sections']['python_reference']['evidence']['final']
        proof=final['metadata']['python_identity']
        for row in proof['sample']['files'].values():row['ino']+=1
        final['metadata']['ino']+=1;refresh(value)
        with self.assertRaisesRegex(ValueError,'FINAL_CONFLICT'):factory.build_executable_specs(value,native)
    def test_factory_rejects_missing_alias_proof_and_wrong_companion_stamp(self):
        value,native=executable_bundle();del value['unit_metadata']['sections']['python_reference']['evidence']['final']['metadata']['python_identity'];refresh(value)
        with self.assertRaisesRegex(ValueError,'SINGLE_LINK'):factory.build_executable_specs(value,native)
        value,native=executable_bundle();value['evidence']['retained']['files'][p.PYTHON_PATHS[1]]['ino']+=1;refresh(value)
        with self.assertRaisesRegex(ValueError,'PAIR_METADATA'):factory.build_executable_specs(value,native)

    def test_pair_proof_survives_all_seventeen_actual_runtime_views(self):
        from test_epoch7_resource_plan import SeventeenCheckpointTests
        fixture=SeventeenCheckpointTests();fixture.setUp()
        try:
            for path in p.PYTHON_PATHS:
                fixture.support['retained']['native_components']['components'][path]=measured(path)
                fixture.exes[path]=plan.file_spec(path,measured(path))
            fixture.snapshot['retained_resource_sha256']=d.digest(fixture.support['retained'])
            views=plan.build_resource_views(fixture.snapshot,fixture.support,fixture.compiled,fixture.additions,
                fixture.security,fixture.manifest_raw,fixture.payloads,fixture.installer,fixture.native_after,
                fixture.tls_before,fixture.profile_candidate,fixture.legacy,release_parent=fixture.fresh_parent,executable_specs=fixture.exes,
                policy=fixture.policy,publisher_journal_raw=fixture.publisher_raw,nss_projection=fixture.nss)
            self.assertEqual(len(views),17)
            for view in views:
                rows={row['path']:row for row in view['historical']}
                for path in p.PYTHON_PATHS:self.assertEqual(rows[path],plan.file_spec(path,measured(path)))
        finally:fixture.tearDown()


class PythonReaderTests(unittest.TestCase):
    def setUp(self):
        # Protected kit tests map this module unchanged; only disposable helper
        # fixtures are used, so the production confinement rule remains active.
        base=str(pathlib.Path(reader_module.__file__).resolve().parent/'fixtures')
        self.root=tempfile.mkdtemp(prefix='python-pair-',dir=base)
        for path in ('/usr','/usr/libexec'):os.mkdir(self.root+path,0o755)
        self.raw=b'\x7fELF'+b'x'*(p.RETAINED_SIZE-4)
        pathlib.Path(self.root+p.PYTHON_PATHS[0]).write_bytes(self.raw)
        os.chmod(self.root+p.PYTHON_PATHS[0],0o755)
        os.link(self.root+p.PYTHON_PATHS[0],self.root+p.PYTHON_PATHS[1])
        directories={}
        for path in p.ANCESTOR_PATHS:
            info=os.lstat(self.root+path);mode=info.st_mode&0o7777
            directories[path]=[{'uid':info.st_uid,'gid':info.st_gid,'mode':mode,
                'access_acl':plan.decode_acl(None,mode),'default_acl':''}]
        self.reader=reader_module.ResourceReader(directories,mock.Mock(),self.root);self.reader.start()
        self.spec=plan.file_spec(p.PYTHON_PATHS[0],measured(p.PYTHON_PATHS[0]))
    def tearDown(self):shutil.rmtree(self.root)
    def test_actual_reader_hashes_both_names_and_all_ancestors(self):
        value=self.reader._python_pair_sample()
        self.assertEqual(set(value['files']),set(p.PYTHON_PATHS));self.assertEqual(set(value['ancestors']),set(p.ANCESTOR_PATHS))
        self.assertEqual(value['files'][p.PYTHON_PATHS[0]],value['files'][p.PYTHON_PATHS[1]])
        self.assertEqual(value['files'][p.PYTHON_PATHS[0]]['sha256'],reader_module.sha(self.raw))
        self.assertTrue(value['files'][p.PYTHON_PATHS[0]]['elf_header'])
        with self.assertRaises(ValueError):self.reader.observe(self.spec)
    def test_real_validator_requires_two_equal_pinned_read_rounds(self):
        sample=sample_fixture()
        with mock.patch.object(self.reader,'_python_pair_sample',side_effect=[sample,copy.deepcopy(sample)]) as read:
            self.assertEqual(self.reader.observe(self.spec),self.spec);self.assertEqual(read.call_count,2)
    def test_each_reread_stamp_or_byte_drift_refuses(self):
        for key,value in (('ino',999),('sha256','0'*64),('nlink',3),('capability',True)):
            sample=sample_fixture();changed=copy.deepcopy(sample)
            for row in changed['files'].values():row[key]=value
            with mock.patch.object(self.reader,'_python_pair_sample',side_effect=[sample,changed]),self.assertRaises(ValueError):
                self.reader.observe(self.spec)
    def test_reread_ancestor_change_is_not_hidden(self):
        sample=sample_fixture();changed=copy.deepcopy(sample);changed['ancestors']['/usr']['ctime_ns']+=1
        with mock.patch.object(self.reader,'_python_pair_sample',side_effect=[sample,changed]),self.assertRaisesRegex(ValueError,'PINNED_PRE_POST_CHANGED'):
            self.reader.observe(self.spec)
    def test_failed_read_closes_every_opened_pair_descriptor(self):
        before=set(os.listdir('/proc/self/fd'))
        with mock.patch.object(reader_module.os,'read',side_effect=OSError('fixture read failure')),self.assertRaises(OSError):
            self.reader._python_pair_sample()
        self.assertEqual(set(os.listdir('/proc/self/fd')),before)
    def test_current_spec_must_match_proof_before_any_read(self):
        for key,value in (('path','/usr/bin/python3'),('sha256','0'*64),('mode',0o777),('access_acl','')):
            spec=dict(self.spec);spec[key]=value
            with mock.patch.object(self.reader,'_python_pair_sample') as read,self.assertRaises(ValueError):self.reader.observe(spec)
            read.assert_not_called()
    def test_three_links_and_symlink_companion_are_rejected_by_actual_reader(self):
        os.link(self.root+p.PYTHON_PATHS[0],self.root+'/usr/libexec/third')
        with self.assertRaisesRegex(ValueError,'FILE_BOUND'):self.reader._python_pair_sample()
        os.unlink(self.root+'/usr/libexec/third');os.unlink(self.root+p.PYTHON_PATHS[1])
        os.symlink(p.PYTHON_PATHS[0],self.root+p.PYTHON_PATHS[1])
        with self.assertRaisesRegex(ValueError,'FILE_BOUND'):self.reader._python_pair_sample()
    def test_unreadable_security_xattr_is_never_absence(self):
        original=reader_module.get_attr
        def get(fd,name):
            if name=='security.capability':raise PermissionError('fixture capability unreadable')
            return original(fd,name)
        with mock.patch.object(reader_module,'get_attr',side_effect=get),self.assertRaises(PermissionError):
            self.reader._python_pair_sample()
    def test_pair_read_detects_inode_replacement_during_hash(self):
        original=os.read;changed=[]
        def read(fd,count):
            value=original(fd,count)
            if value and not changed:
                changed.append(True);path=self.root+p.PYTHON_PATHS[1];os.unlink(path)
                pathlib.Path(path).write_bytes(self.raw)
            return value
        with mock.patch.object(reader_module.os,'read',side_effect=read),self.assertRaises(ValueError):self.reader._python_pair_sample()
    def test_pair_read_obeys_existing_guard_deadline(self):
        self.reader.guard_deadline=0;self.reader.start()
        with self.assertRaisesRegex(ValueError,'TOTAL_DEADLINE'):self.reader.observe(self.spec)
    def test_generic_file_with_same_pair_still_rejects_multiple_links(self):
        row=reader_module.fs.metadata(os.lstat(self.root+p.PYTHON_PATHS[0]))
        spec={k:row[k] for k in ('uid','gid','mode')};spec.update(path=p.PYTHON_PATHS[0],kind='FILE',
            sha256=reader_module.sha(self.raw),access_acl=plan.decode_acl(None,row['mode']))
        with self.assertRaisesRegex(ValueError,'FILE_BOUND'):self.reader.observe(spec)
    def test_actual_collector_row_shape_reaches_read_boundary_after_real_validation(self):
        class ReadBoundary(Exception):pass
        proof=proof_fixture();row=dict(proof['sample']['files'][p.PYTHON_PATHS[0]],python_identity=proof)
        reference={'reference_path':p.PYTHON_PATHS[0],'links':[],
            'final':{'path':p.PYTHON_PATHS[0],'format':'ELF','sha256':p.RETAINED_SHA256,'metadata':row}}
        with mock.patch.object(self.reader,'_parent',side_effect=ReadBoundary),self.assertRaises(ReadBoundary):
            self.reader.executable_reference(reference)
        row['capability']=True
        with mock.patch.object(self.reader,'_parent') as read,self.assertRaisesRegex(ValueError,'PYTHON_METADATA_BINDING'):
            self.reader.executable_reference(reference)
        read.assert_not_called()
    def test_alias_final_metadata_rejects_unscoped_extra_fields(self):
        row=reader_module.fs.metadata(os.lstat(self.root+p.PYTHON_PATHS[0]));row.update(kind='FILE',sha256=reader_module.sha(self.raw),unreviewed=True)
        reference={'reference_path':p.PYTHON_PATHS[0],'links':[],
            'final':{'path':p.PYTHON_PATHS[0],'format':'ELF','sha256':row['sha256'],'metadata':row}}
        with self.assertRaisesRegex(ValueError,'METADATA_FIELDS'):self.reader.executable_reference(reference)


class PythonInnerGuardTests(unittest.TestCase):
    def setUp(self):
        import epoch7_pre_active_guards as guards
        self.guard=object.__new__(guards.PreActiveGateGuards);self.guard._check=mock.Mock();self.guard.io=mock.Mock()
        self.proof=proof_fixture();self.path=p.PYTHON_PATHS[0]
        self.row=dict(self.proof['sample']['files'][self.path],python_identity=self.proof)
        self.guard.io.read_python.return_value=(b'read-boundary fixture',copy.deepcopy(self.row))
    def test_fixed_proof_row_uses_pair_reader_and_preserves_full_row(self):
        self.assertEqual(self.guard._preserved_file(self.path,self.row),self.row)
        self.guard.io.read.assert_not_called();self.guard.io.read_python.assert_called_once_with(self.path,maximum=16777216)
    def test_generic_row_never_uses_pair_reader(self):
        row={'kind':'FILE','sha256':'1'*64,'nlink':1};self.guard.io.read.return_value=(b'fixture',row)
        self.assertEqual(self.guard._preserved_file('/usr/bin/other',row),row);self.guard.io.read_python.assert_not_called()
    def test_unrelated_path_cannot_use_python_proof(self):
        with self.assertRaisesRegex(ValueError,'EXACT_PYTHON_PAIR_ROW'):self.guard._preserved_file('/usr/bin/other',self.row)
        self.guard.io.read_python.assert_not_called();self.guard.io.read.assert_not_called()
    def test_full_metadata_and_proof_reread_drift_refuses(self):
        for key,value in (('ino',999),('capability',True),('python_identity',None)):
            current=copy.deepcopy(self.row);current[key]=value;self.guard.io.read_python.return_value=(b'fixture',current)
            with self.assertRaisesRegex(ValueError,'PRESERVED_FILE_DRIFT'):self.guard._preserved_file(self.path,self.row)
    def test_native_reference_is_reread_and_must_remain_canonical(self):
        reference={'reference_path':self.path,'links':[],'final':{'path':self.path,'format':'ELF',
            'sha256':p.RETAINED_SHA256,'metadata':self.row}}
        components={'components':{self.path:self.row},'python_reference':reference}
        self.guard.io.executable_reference.return_value=copy.deepcopy(reference)
        native=d.canonical({'ledger':{'python':self.path}})
        self.guard._native_python_reference(components,native)
        self.guard.io.executable_reference.assert_called_once_with(self.path)
        self.guard.io.executable_reference.return_value['final']['metadata']['ino']+=1
        with self.assertRaisesRegex(ValueError,'REFERENCE_DRIFT'):self.guard._native_python_reference(components,native)
        reference['reference_path']='/usr/bin/python3'
        with self.assertRaisesRegex(ValueError,'REFERENCE_SCOPE'):
            self.guard._native_python_reference(components,d.canonical({'ledger':{'python':'/usr/bin/python3'}}))
    def test_pair_rows_require_reference_evidence(self):
        with self.assertRaisesRegex(ValueError,'REFERENCE_REQUIRED'):
            self.guard._native_python_reference({'components':{self.path:self.row}},b'{}')


if __name__=='__main__':unittest.main()
