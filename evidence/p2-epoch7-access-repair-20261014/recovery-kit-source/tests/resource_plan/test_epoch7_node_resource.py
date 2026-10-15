"""Direct Node alias propagation, owned config changes and real bounded reads."""
import copy
import os
import pathlib
import shutil
import tempfile
import types
import unittest
from unittest import mock
import epoch7_delta as d
import epoch7_host_factory as factory
import epoch7_resource_plan as plan
import epoch7_resource_observer as r
import epoch7_quiet_startup as q
import epoch7_pre_active_guards as guards
import epoch7_openclaw_recipe as oc
import unit_metadata as um
import snapshot_io as sio
from epoch7_recovery_sequence import PHASES
from test_epoch7_openclaw_direct import direct_fixture,node_reference_fixture
from test_epoch7_full_factory_fixture import make_seed,native_pins
from test_epoch7_python_resource import executable_bundle,refresh
import test_epoch7_quiet_startup as quiet_tests


def node():
    return {'path':oc.DIRECT_NODE_PATH,'sha256':'a'*64,'metadata':{
        'uid':1002,'gid':1002,'mode':0o755,'dev':8,'ino':123,'nlink':1,'size':42,'mtime_ns':1,'ctime_ns':2}}


def spec(proof):
    row=proof['final']['metadata'];value={key:row[key] for key in ('kind','uid','gid','mode','sha256')}
    return dict(value,path=proof['final']['path'],access_acl=plan.decode_acl(None,row['mode']),node_reference=copy.deepcopy(proof))


class NodePropagationTests(unittest.TestCase):
    def bundle(self):
        value,native=executable_bundle();native=q.snap.decode(native);image=node();proof=node_reference_fixture(image)
        native['gatewayIdentity']={'exe':image['path'],'sha256':image['sha256']}
        value['evidence']['retained']['native_components']['components'][image['path']]=dict(image['metadata'],kind='FILE',sha256=image['sha256'])
        launcher=value['unit_metadata']['sections']['launcher']['evidence']
        launcher.update(sha256=oc.DIRECT_WRAPPER_SHA,node_reference=proof)
        launcher['metadata']['sha256']=oc.DIRECT_WRAPPER_SHA
        launcher['entry_script']['path']=oc.DIRECT_ENTRY
        refresh(value);return value,d.canonical(native),proof
    def test_factory_binds_alias_proof_to_canonical_file_and_no_new_seed(self):
        value,native,proof=self.bundle();result=factory.build_executable_specs(value,native)
        self.assertEqual(result[oc.DIRECT_NODE_PATH],spec(proof))
        self.assertNotIn(oc.DIRECT_NODE_REFERENCE,result)
        self.assertEqual(len(factory.INPUTS-factory.DERIVED_INPUTS),16)
    def test_missing_foreign_or_changed_proof_refuses(self):
        for case in ('missing','hash','inode','lexical','entry'):
            value,native,proof=self.bundle();launcher=value['unit_metadata']['sections']['launcher']['evidence']
            if case=='missing':launcher.pop('node_reference')
            elif case=='hash':proof['final']['sha256']='b'*64
            elif case=='inode':proof['final']['metadata']['ino']+=1
            elif case=='lexical':proof['reference_path']='/tmp/node'
            else:launcher['entry_script']['path']='/tmp/entry.js'
            refresh(value)
            with self.subTest(case=case),self.assertRaises(ValueError):factory.build_executable_specs(value,native)
    def test_root_wrapper_cannot_import_directory_alias_grant(self):
        value,native,proof=self.bundle();launcher=value['unit_metadata']['sections']['launcher']['evidence']
        launcher['sha256']=launcher['metadata']['sha256']='c'*64;refresh(value)
        with self.assertRaisesRegex(ValueError,'ROOT_NODE_REFERENCE'):factory.build_executable_specs(value,native)
    def test_real107_full_factory_direct_variant_binds_all17_views(self):
        seed=make_seed(service_fixture=direct_fixture)
        with native_pins(seed):
            result=factory.prepare_host_inputs(seed)
            self.assertEqual(result['state'],'COMPILED_NOT_ADMITTED',result.get('unresolved'))
            inputs=result['inputs'];contract=factory.compile_host_contract(inputs)
        self.assertEqual(len(inputs['source_payloads']),107)
        self.assertFalse(result['install_admission'])
        proof=seed['observation']['openclaw_profile']['recipe_evidence']['launcher']['node_reference']
        for view in inputs['resource_views']:
            rows={row['path']:row for row in view['historical']}
            self.assertEqual(rows[oc.DIRECT_NODE_PATH],spec(proof))
            self.assertEqual(rows[um.NODE_ALIAS_PATH]['sha256'],q.sha(proof['link']['target'].encode()))
            for name,pin in oc.DIRECT_SOURCE_HASHES.items():self.assertEqual(rows[oc.DIRECT_PACKAGE_ROOT+'/'+name]['sha256'],pin)
        self.assertEqual(len(contract['live_controls']['service_role_contract']['units'][oc.GATEWAY]['roles']),2)
    def test_startup_source32_cannot_be_omitted_by_factory(self):
        args,unused=direct_fixture();facts=args[4]
        facts['openclaw_recipe_evidence']['files'].pop('dist/is-main-DYSvvM1W.mjs')
        with self.assertRaisesRegex(ValueError,'COMPLETE_STARTUP_SOURCE_SET'):factory.startup_source_specs({},facts)


class OwnedParentTests(unittest.TestCase):
    def setUp(self):
        self.expected=node_reference_fixture(node());self.changed=copy.deepcopy(self.expected)
        row=self.changed['ancestors']['/home/xuanjun_dev/.openclaw']
        for key in ('size','mtime_ns','ctime_ns'):row[key]+=1
        self.state={'admission':'ADMITTED','stage':'apply_fresh_sandbox_INTENT',
            'completed':list(PHASES[:PHASES.index('apply_fresh_sandbox')])}
        self.row={'schema':1,'context_sha256':'f'*64,'original_sha256':'b'*64,
            'candidate_sha256':'c'*64,'current_sha256':'c'*64,'state':'APPLIED'}
        self.metadata={'uid':0,'gid':0,'mode':0o600,'nlink':1}
        self.temp=tempfile.TemporaryDirectory(prefix='node-owned-receipt-')
        io=types.SimpleNamespace(read_journal=lambda name:{'data':b'protected outer fixture'},
            _parent=lambda path:(os.open(self.temp.name,os.O_RDONLY|os.O_DIRECTORY),'receipt'),
            _read_at=lambda *args,**kwargs:(self.metadata,d.canonical(self.row)))
        self.authority=types.SimpleNamespace(receipt=lambda:True,io=io,context={'context_sha256':'f'*64},
            validate_outer=lambda raw:{'state':copy.deepcopy(self.state)})
    def tearDown(self):self.temp.cleanup()
    def test_identical_proof_needs_no_config_exception(self):
        self.assertTrue(r.same_node_reference(self.expected,self.expected,types.SimpleNamespace()))
    def test_exact_owned_applied_config_allows_only_parent_three_fields(self):
        self.assertTrue(r.same_node_reference(self.changed,self.expected,self.authority))
    def test_pre_mutation_parent_drift_rejects(self):
        self.state.update(stage='rebind_tls_metadata_only_INTENT',completed=list(PHASES[:8]))
        with self.assertRaisesRegex(ValueError,'OWNED_CONFIG_PHASE'):r.same_node_reference(self.changed,self.expected,self.authority)
    def test_intent_without_completed_write_rejects(self):
        self.row['state']='APPLY_INTENT'
        with self.assertRaisesRegex(ValueError,'OWNED_CONFIG_RECEIPT'):r.same_node_reference(self.changed,self.expected,self.authority)
    def test_old_context_or_unprotected_receipt_rejects(self):
        self.row['context_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'OWNED_CONFIG_RECEIPT'):r.same_node_reference(self.changed,self.expected,self.authority)
        self.row['context_sha256']='f'*64;self.metadata['gid']=1002
        with self.assertRaisesRegex(ValueError,'PRIVATE_SANDBOX'):r.same_node_reference(self.changed,self.expected,self.authority)
    def test_wrong_prefix_or_unadmitted_claim_rejects(self):
        for key,value in (('completed',[]),('admission','UNKNOWN')):
            before=copy.deepcopy(self.state);self.state[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'OWNED_CONFIG_PHASE'):
                r.same_node_reference(self.changed,self.expected,self.authority)
            self.state=before
    def test_other_ancestor_nlink_or_elf_drift_never_exempt(self):
        for case in ('other_parent','nlink','elf','link'):
            changed=copy.deepcopy(self.changed)
            if case=='other_parent':changed['ancestors']['/home']['mtime_ns']+=1
            elif case=='nlink':changed['ancestors']['/home/xuanjun_dev/.openclaw']['nlink']+=1
            elif case=='elf':changed['final']['metadata']['ino']+=1
            else:changed['link']['metadata']['ino']+=1
            with self.subTest(case=case),self.assertRaisesRegex(ValueError,'IMMUTABLE_DRIFT'):
                r.same_node_reference(changed,self.expected,self.authority)
    def test_cli_capture_only_after_completed_sandbox(self):
        self.row['state']='CLI_CAPTURED'
        with self.assertRaisesRegex(ValueError,'CLI_AFTER_SANDBOX'):r.same_node_reference(self.changed,self.expected,self.authority)
        self.state.update(stage='install_verified_plugin_INTENT',completed=list(PHASES[:10]))
        self.assertTrue(r.same_node_reference(self.changed,self.expected,self.authority))


class QuietNodeTests(unittest.TestCase):
    def make(self):
        value,blocks,raw,inventory=quiet_tests.QuietTests().make();image=node();proof=node_reference_fixture(image)
        value.relay_metadata=None;value.bind_resource_views([{'targets':[{'path':q.RELAY,'kind':'FILE','uid':0,'gid':1002,'mode':0o640}],
            'historical':[spec(proof)]} for unused in range(17)])
        raw[q.LAUNCHER]=um.DIRECT_DIST_WRAPPER;relay=q.snap.decode(raw[q.RELAY]);relay['openclaw_sha256']=oc.DIRECT_WRAPPER_SHA
        raw[q.RELAY]=d.canonical(relay);block=blocks[q.GATEWAY]
        block['quiet_startup']['package_root']=oc.DIRECT_PACKAGE_ROOT
        block['sources'].update({q.LAUNCHER:oc.DIRECT_WRAPPER_SHA,image['path']:image['sha256']})
        block['roles'][0]['identity']={'executable':image['path'],'executable_sha256':image['sha256']}
        value.io.node_directory_reference.return_value=copy.deepcopy(proof)
        return value,blocks,raw,proof
    def test_fresh_before_after_alias_and_native_hash_use_real_parser(self):
        value,blocks,unused,proof=self.make()
        self.assertEqual(quiet_tests.QuietTests().observe(value,blocks),blocks[q.GATEWAY]['quiet_startup'])
        self.assertEqual(value.io.node_directory_reference.call_count,2)
        value.io.node_directory_reference.assert_called_with(oc.DIRECT_NODE_PATH,node()['sha256'])
    def test_missing_bound_proof_or_changed_reference_rejects(self):
        for case in ('missing','early','late'):
            value,blocks,unused,proof=self.make()
            if case=='missing':value.node_reference=None
            else:
                changed=copy.deepcopy(proof);changed['link']['metadata']['ino']+=1
                value.io.node_directory_reference.side_effect=[changed,proof] if case=='early' else [proof,changed]
            with self.subTest(case=case),self.assertRaises(ValueError):quiet_tests.QuietTests().observe(value,blocks)
    def test_all17_views_must_share_exact_proof(self):
        value,blocks,unused,proof=self.make();value.relay_metadata=None
        views=[{'targets':[{'path':q.RELAY,'kind':'FILE','uid':0,'gid':1002,'mode':0o640}],
            'historical':[spec(proof)]} for unused in range(17)]
        views[8]['historical']=[]
        with self.assertRaisesRegex(ValueError,'NODE_REFERENCE_TRANSITION'):value.bind_resource_views(views)
    def test_inner_guard_cannot_skip_required_proof(self):
        value,blocks,unused,proof=self.make();guard=object.__new__(guards.PreActiveGateGuards)
        guard.observer=types.SimpleNamespace(quiet=value,live_contract={'service_role_contract':{'units':blocks}})
        guard._check=mock.Mock();guard.io=mock.Mock();guard.authority=value.authority
        native=d.canonical({'gatewayIdentity':{'exe':node()['path'],'sha256':node()['sha256']}})
        guard.io.node_directory_reference.return_value=proof;guard._native_node_reference(native)
        value.node_reference=None
        with self.assertRaisesRegex(ValueError,'NODE_REFERENCE_REQUIRED'):guard._native_node_reference(native)


class ConcreteNodeReaderTests(unittest.TestCase):
    def setUp(self):
        base=str(pathlib.Path(r.__file__).resolve().parent/'fixtures')
        self.root=tempfile.mkdtemp(prefix='node-reference-',dir=base)
        for path in um.NODE_REFERENCE_ANCESTORS:os.makedirs(self.root+path,exist_ok=True)
        for path in um.NODE_REFERENCE_ANCESTORS:os.chmod(self.root+path,0o755)
        self.raw=b'\x7fELF'+b'real bounded fixture bytes'*8192
        pathlib.Path(self.root+oc.DIRECT_NODE_PATH).write_bytes(self.raw);os.chmod(self.root+oc.DIRECT_NODE_PATH,0o755)
        os.symlink('node-v24.21.0',self.root+um.NODE_ALIAS_PATH)
        roots={os.lstat(self.root).st_ino,os.lstat(self.root+'/home').st_ino};self.patches=[]
        for name in ('stat','lstat','fstat'):
            original=getattr(os,name)
            def mapped(*args,_call=original,**kwargs):
                info=_call(*args,**kwargs);owner=0 if info.st_ino in roots else 1002
                return types.SimpleNamespace(**dict({k:getattr(info,k) for k in
                    ('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')},st_uid=owner,st_gid=owner))
            patch=mock.patch.object(os,name,side_effect=mapped);patch.start();self.patches.append(patch)
        dirs={path:[dict({k:sio.metadata(os.lstat(self.root+path))[k] for k in ('uid','gid','mode')},
            access_acl=plan.decode_acl(None,0o755),default_acl='')] for path in um.NODE_REFERENCE_ANCESTORS}
        self.reader=r.ResourceReader(dirs,mock.Mock(),self.root);self.reader.start();owner=self.reader
        class Capture(sio.LocalReadOnlyIO):
            def __init__(self):sio.DescriptorReader.__init__(self,{},root=owner.root)
            def check_locks(self):owner.check()
            def _authority(self,fd,path):return owner._directory(fd,path)
        self.proof=Capture().node_directory_reference(oc.DIRECT_NODE_PATH,q.sha(self.raw));self.spec=spec(self.proof)
    def tearDown(self):
        for patch in reversed(self.patches):patch.stop()
        shutil.rmtree(self.root)
    def test_real_two_round_reader_matches_exact_proof(self):
        self.assertEqual(self.reader.observe(self.spec),self.spec)
    def test_real_alias_replacement_or_elf_byte_drift_rejects(self):
        os.unlink(self.root+um.NODE_ALIAS_PATH);os.symlink(um.NODE_VERSION_DIRECTORY,self.root+um.NODE_ALIAS_PATH)
        with self.assertRaises(ValueError):self.reader.observe(self.spec)
        os.unlink(self.root+um.NODE_ALIAS_PATH);os.symlink('node-v24.21.0',self.root+um.NODE_ALIAS_PATH)
        pathlib.Path(self.root+oc.DIRECT_NODE_PATH).write_bytes(b'\x7fELFchanged')
        with self.assertRaises(ValueError):self.reader.observe(self.spec)
    def test_proof_on_other_file_never_changes_generic_single_link_rule(self):
        self.spec['path']='/usr/bin/node'
        with self.assertRaisesRegex(ValueError,'NODE_REFERENCE_SPEC'):self.reader.observe(self.spec)
    def test_expired_deadline_does_not_read_alias(self):
        self.reader.deadline=0
        with mock.patch.object(os,'readlink') as read,self.assertRaisesRegex(ValueError,'DEADLINE'):
            self.reader.observe(self.spec)
        read.assert_not_called()


if __name__=='__main__':unittest.main()
