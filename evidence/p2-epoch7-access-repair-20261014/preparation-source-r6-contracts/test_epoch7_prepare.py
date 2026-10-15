"""Portable synthetic preparation tests. No host reads or approval fetches."""
import copy
import errno
import io
import os
import pathlib
import tempfile
import time
import types
import unittest
from unittest import mock
import epoch7_prepare as p
import epoch7_prepare_data as data
import epoch7_host_factory as factory
import epoch7_delta as d
import epoch7_topology_projection as topology
from test_epoch7_full_factory_fixture import make_seed,native_pins,meta,directory,packed
from test_node_sqlite_probe import fixture_proof
from test_epoch7_topology_projection import fixture as topology_fixture
import node_sqlite_probe as node
import epoch7_additive_identity as owner
import epoch7_additive_server as server


def fixture_kit():
    default=pathlib.Path(__file__).resolve().parent.parent/'r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6'
    return pathlib.Path(os.environ.get('EPOCH7_PREP_TEST_KIT_ROOT',str(default))).resolve()


class R6BindingTests(unittest.TestCase):
    def test_candidate_binds_exact_reviewed_artifact(self):
        self.assertIs(p.PINS_BOUND,True)
        self.assertEqual(p.KIT_SHA,'70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc')
        self.assertEqual(p.ENTRY_SHA,'c56ba6d8281eeb1ecc062875a7f13defc223f6d5dd073a4490d1602b8cf1d3a5')
        p.require_binding()
        self.assertTrue(p.KIT_ROOT.endswith('/epoch7-recovery-candidate-r6'))
        self.assertTrue(p.PREP_ROOT.endswith('/epoch7-preparation-candidate-r6-contracts'))
    def test_unbound_bootstrap_refuses_before_any_open(self):
        with mock.patch.object(p,'PINS_BOUND',False),mock.patch.object(p.os,'open',side_effect=AssertionError('no host reads')):
            with self.assertRaisesRegex(ValueError,'R6_ARTIFACT_UNBOUND'):p.bootstrap_entry()
    def test_unbound_operations_refuse_before_host_or_input_reads(self):
        for operation in ('propose-topology','prepare'):
            args=['--operation',operation,'--observation','/fixed','--observation-sha256','a'*64]
            if operation=='prepare':args+=['--topology-review-id','7000000001',
                '--retained-renewal-timer','enable-after-reviewed-checks']
            with mock.patch.object(p,'PINS_BOUND',False),mock.patch.object(p.os,'geteuid',side_effect=AssertionError('no host boundary')),\
                 mock.patch.object(p.os,'open',side_effect=AssertionError('no host reads')):
                with self.assertRaisesRegex(ValueError,'R6_ARTIFACT_UNBOUND'):p.main(args)


def seed_fixture():
    seed=make_seed();observation=seed['observation'];support=observation['evidence']['retained']
    support['additive_paths_absent']=sorted((owner.PATH,server.PATH))
    support['prerequisites']['directories'][owner.PARENT]=directory()
    tools={'/usr/lib/systemd/systemd':b'\x7fELFsynthetic manager','/usr/bin/systemctl':b'\x7fELFsynthetic systemctl'}
    manager=observation['evidence']['writers']['manager'];manager['binary_sha256']=data.sha(tools[manager['binary_path']])
    for path,raw in tools.items():
        support['files'][path]=meta(raw,mode=0o755)
        observation['policy']['files'][path]={k:support['files'][path][k] for k in ('sha256','uid','gid','mode')}
    for label in ('systemctl','systemd'):
        observation['policy']['executables'][label]['sha256']=support['files'][observation['policy']['executables'][label]['path']]['sha256']
    observation['openclaw_profile']['recipe_evidence']['quiet_bootstrap']['manager_sha256']=d.digest(manager)
    observation['openclaw_profile_sha256']=d.digest(observation['openclaw_profile'])
    observation['unit_metadata']['sections']['command_resolutions']['evidence']['provenance'].update(
        manager_sha256=d.digest(manager),systemctl_sha256=data.sha(tools['/usr/bin/systemctl']))
    for unit in server.UNIT_PROPERTIES:
        observation['evidence']['writers']['units'][unit]['state'].update(DropInPaths='',NeedDaemonReload='no')
    support['policy_sha256']=d.digest(observation['policy'])
    observation['snapshot']['retained_resource_sha256']=d.digest(support)
    writers=observation['evidence']['writers'];observation['snapshot']['writer_exclusion']['evidence_sha256']=d.digest(writers)
    observation['evidence']['writer_observation_comparison']=factory.snap.validate_writer_transition(writers,writers)
    observation['evidence']['snapshot_sha256']=d.digest(observation['snapshot'])
    for key in ('snapshot','evidence','policy','unit_metadata','probe_metadata'):observation[key+'_sha256']=d.digest(observation[key])
    attempt=observation['finite_probe'];policy=attempt['policy'];policy['node_sqlite']=node.binding_from_observation(observation)
    pin=data.sha(packed(policy));binding=policy['node_sqlite'];proof=fixture_proof(binding['node'],policy['nonce'],pin,binding['probe_input_sha256'])
    receipt=packed({'schema':1,'nonce':policy['nonce'],'policy_sha256':pin,'events':[{'event':'NODE_SQLITE_OBSERVED','detail':proof}]})
    attempt['policy_sha256']=pin;attempt['result']['node_sqlite']=proof
    attempt['result']['created_receipt'].update(sha256=data.sha(receipt),metadata={k:v for k,v in meta(receipt,mode=0o600).items() if k not in ('kind','sha256')},node_sqlite_event_sha256=d.digest(proof))
    return seed,tools


def collected_fixture():
    seed,tools=seed_fixture()
    return seed,{'observation':seed['observation'],'compiled':seed['compiled'],
        'buffers':{key:seed[key] for key in data.RAW_PATHS},'manifest_raw':seed['source_manifest_raw'],
        'source_payloads':seed['source_payloads'],'tool_sources':tools,'socket_dropins':topology_fixture()['dropins']}


class PureTests(unittest.TestCase):
    def test_real107_full_factory_compiles_new_identity_policies_and_final_body(self):
        seed,collected=collected_fixture();root=pathlib.Path(__file__).resolve().parent.parent
        entry=p.load_entry((fixture_kit()/'epoch7_recovery_entry.py').read_bytes())
        cache={'xuanjun-p2-package/'+path:raw for path,raw in seed['source_payloads'].items()}
        cache['xuanjun-p2-package/deploy/integration-manifest.json']=seed['source_manifest_raw']
        kit=entry.VerifiedKit('/fixture/authenticated-kit',{'runtime_source_commit':factory.SOURCE,
            'runtime_source_tree':factory.SOURCE_TREE,'runtime_manifest_sha256':factory.MANIFEST},cache,seed['kit_manifest_sha256'])
        # This review is explicitly synthetic test input. Production calls the
        # authenticated HTTPS fetch before invoking this pure builder.
        proposal=__import__('test_epoch7_topology_projection').project(topology_fixture())
        review={'review_id':7000000001,'approval_body_sha256':'3'*64,'evidence_sha256':proposal['topology_sha256']}
        with native_pins(seed):
            bundle=p.compile_private_bundle(kit,collected,proposal['topology_raw'],review,True,data)
        self.assertEqual(set(json_value(bundle['plan_raw'])),{'host_contract','resource_observer','live_controls'})
        self.assertEqual(bundle['summary']['resource_checkpoints'],17)
        self.assertEqual(bundle['unsigned_approval']['recovery_plan_sha256'],data.sha(bundle['plan_raw']))
        self.assertEqual(bundle['unsigned_approval']['retained_authorization']['total_target_count'],26)
        self.assertEqual(len(json_value(bundle['seed_raw'])['seed']),11)
        self.assertEqual(len(seed['source_payloads']),107)
        self.assertEqual(bundle['summary']['install_admission'],'NOT_GRANTED')
    def test_complete_observation_and_probe_are_required_before_gathering(self):
        seed,unused=seed_fixture()
        with native_pins(seed):data.validate_observation(seed['observation'],factory)
        for kind in ('retained','unit','probe'):
            value=copy.deepcopy(seed['observation'])
            if kind=='retained':value['evidence']['retained']['policy_sha256']='1'*64
            elif kind=='unit':value['unit_metadata']['state']='INCOMPLETE'
            else:value.pop('finite_probe')
            with self.subTest(kind=kind),self.assertRaises(ValueError):data.validate_observation(value,factory)
    def test_json_duplicate_nonfinite_and_boundary_reject(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'',b'[]' * 200):
            with self.assertRaises(ValueError):data.parse(raw,64)
    def test_cached_paths_never_resolve_or_read_undeclared(self):
        path=data.CachedPath('/fixed',{'/fixed/one':b'value'})
        self.assertEqual((path/'one').read_bytes(),b'value')
        for child in ('../other','/other','a//b','a\\b'):
            with self.assertRaises(ValueError):path/child
        with self.assertRaises(ValueError):(path/'two').read_bytes()
    def test_historical_pins_reject_before_any_execution(self):
        with mock.patch('builtins.compile',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(ValueError,'ORIGINAL_PLAN_PIN'):
                data.reproduce_v4(b'{}',b'',{},b'',{},b'',{})
    def test_six_exact_retained_buffers_and_stamps(self):
        files={};measured={}
        for key,path in data.RAW_PATHS.items():
            raw=(key+'\n').encode();row=meta(raw)
            files[path]=row;measured[key]={'raw':raw,'metadata':row}
        observation={'evidence':{'retained':{'files':files}}}
        self.assertEqual(set(data.retained_buffers(observation,measured)),set(data.RAW_PATHS))
        for field in data.STAT_FIELDS:
            changed=copy.deepcopy(measured);changed['native_before']['metadata'][field]+=1
            with self.subTest(field=field),self.assertRaises(ValueError):data.retained_buffers(observation,changed)
        changed=copy.deepcopy(measured);changed['native_before']['raw']+=b' '
        with self.assertRaises(ValueError):data.retained_buffers(observation,changed)
    def test_missing_or_extra_buffer_refuses(self):
        for value in ({},{'unexpected':{}}):
            with self.assertRaises(ValueError):data.retained_buffers({},value)
    def test_exact_timer_boolean_required_before_compiler(self):
        for timer in (None,0,1,'true',False):
            with self.subTest(timer=timer),self.assertRaises(ValueError):p.compile_private_bundle(None,{},b'',{},timer,data)
    def test_real_owner_and_server_addition_compilers(self):
        seed,c=collected_fixture();obs=c['observation']
        owner_raw,addition=data.owner_policy(obs,c['compiled'],c['manifest_raw'])
        owner.validate_compiled(addition,factory.MANIFEST)
        top={'schema':1,'purpose':'ROOT_MANAGER_SHARED_INIT_PROOF','creator':{'pid':1,'uid':0,'gid':0,
            'exe':'/usr/lib/systemd/systemd','cgroup_sha256':'1'*64,'pid_namespace_role':'SYSTEM_INIT_SHARED_WITH_CLIENTS'},
            'endpoint_identity':{'uid':1003,'gid':1007,'mode':0o660},
            'clients':{role:{'same_pid_namespace':True,'same_proc_namespace':True,'readpaths_verified':True} for role in server.PROFILES},
            'exclusive_delivery_reviewed':True,'systemd_version':239,'evidence_records_sha256':'2'*64}
        topraw=packed(top);review={'review_id':7000000001,'approval_body_sha256':'3'*64,'evidence_sha256':data.sha(topraw)}
        raw,addition=p.server_policy(obs,c['compiled'],c['manifest_raw'],c['source_payloads'],c['tool_sources'],topraw,review,data,c['socket_dropins'])
        server.validate_compiled(addition,factory.MANIFEST)
        self.assertEqual(json_value(raw)['files']['/usr/bin/systemctl'],data.sha(c['tool_sources']['/usr/bin/systemctl']))
    def test_tool_source_hash_drift_refuses(self):
        seed,c=collected_fixture();top=topology_fixture();proposal=__import__('test_epoch7_topology_projection').project(top)
        c['tool_sources']['/usr/bin/systemctl']+=b'bad'
        with self.assertRaisesRegex(ValueError,'SERVER_TOOL_MEASURED_BINDING'):
            p.server_policy(c['observation'],c['compiled'],c['manifest_raw'],c['source_payloads'],c['tool_sources'],proposal['topology_raw'],{},data,c['socket_dropins'])
    def test_wire_uses_exact_named_utf8_fields(self):
        seed,unused=seed_fixture();wire=data.seed_wire(seed);value=json_value(wire)
        self.assertEqual(set(value),{'schema','seed'})
        self.assertEqual(len(value['seed']),11)
        for key in data.RAW_PATHS:self.assertEqual(value['seed'][key].encode(),seed[key])
        changed=copy.deepcopy(seed);changed['native_before']=b'\xff'
        with self.assertRaises(UnicodeError):data.seed_wire(changed)
    def test_unexpected_seed_field_refuses(self):
        seed,unused=seed_fixture();seed['authority']=True
        with self.assertRaises(ValueError):data.seed_wire(seed)


def json_value(raw):return data.parse(raw,64*1024*1024)


class CleanupTests(unittest.TestCase):
    def test_close_attempts_every_owned_fd_and_preserves_primary(self):
        value=p.Gatherer(None,time.monotonic()+30);tree=types.SimpleNamespace(closed=False,opened=[[10],[11]])
        value.trees={'fixed':tree};primary=ValueError('primary')
        with mock.patch.object(p.os,'close',side_effect=OSError(errno.EIO,'private text')) as close:value.close(primary)
        self.assertEqual(close.call_count,2);self.assertTrue(primary.preparation_cleanup_failed)
    def test_close_failure_without_primary_is_static(self):
        with mock.patch.object(p.os,'close',side_effect=OSError('private text')):
            with self.assertRaises(p.CleanupError):p.close_fd(10)
    def test_xattr_unknown_or_present_never_means_absent(self):
        for effect in (OSError(errno.EACCES,'private'),None):
            with mock.patch.object(p.os,'getxattr',side_effect=effect,return_value=b''):
                with self.assertRaises(ValueError):p.no_attributes(10)
    def test_deadline_rejects_before_read(self):
        value=p.Gatherer(None,0)
        with mock.patch.object(p.os,'open',side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(ValueError,'DEADLINE'):value.read('/fixed/file',10)
    def test_periodic_alarm_and_primary_cleanup_preservation(self):
        primary=ValueError('first')
        with mock.patch.object(p.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(p.signal,'getsignal',return_value=None),\
             mock.patch.object(p.signal,'signal'),mock.patch.object(p.signal,'setitimer',side_effect=[None,OSError('private')]) as timer:
            with self.assertRaises(ValueError) as caught:
                with p.budget(1):raise primary
        self.assertIs(caught.exception,primary);self.assertTrue(primary.preparation_cleanup_failed)
        self.assertEqual(timer.call_args_list[0][0],(p.signal.ITIMER_REAL,1,.1))


# Only UID/GID observation is mapped for portable disposable files. All opens,
# no-follow traversal, byte reads/writes, xattrs, races and serializers are real.
def mapped_info(info):
    values={name:getattr(info,name) for name in dir(info) if name.startswith('st_')}
    values.update(st_uid=0,st_gid=0)
    return types.SimpleNamespace(**values)


def fixture_owners():
    # Offline fixture policy only: Hosted '/' is root-owned, while the private
    # checkout and fixture directories belong to the nonroot test runner.
    # Production still calls DescriptorTree with its unchanged root-only default.
    return ((0,0),(os.getuid(),os.getgid()))


def local_entry():
    root=pathlib.Path(__file__).resolve().parent.parent
    real=p.load_entry((fixture_kit()/'epoch7_recovery_entry.py').read_bytes())
    class Tree(object):
        def __init__(self,path):
            self.real=real.DescriptorTree(path,owners=fixture_owners())
            self.fd=self.real.fd;self.closed=False
            self.opened=[[fd,parent,name,logical,tuple(list(stamp[:3])+[0,0]+list(stamp[5:]))]
                         for fd,parent,name,logical,stamp in self.real.opened]
        def parent(self,name):return self.real.parent(name)
        def read(self,*args,**kwargs):return self.real.read(*args,**kwargs)
        def recheck(self):
            for fd,parent,name,logical,before in self.opened:
                if real.stamp(self._authority(fd,True))!=before:raise ValueError('LOCAL_ANCESTRY_RACE')
                if parent is not None and real.stamp(mapped_info(os.stat(name,dir_fd=parent,follow_symlinks=False)))!=before:
                    raise ValueError('LOCAL_BINDING_RACE')
        def _authority(self,*args,**kwargs):return mapped_info(self.real._authority(*args,**kwargs))
    proxy=types.SimpleNamespace(**{name:getattr(os,name) for name in dir(os) if not name.startswith('__')})
    proxy.stat=lambda *args,**kwargs:mapped_info(os.stat(*args,**kwargs))
    proxy.fstat=lambda *args,**kwargs:mapped_info(os.fstat(*args,**kwargs))
    return types.SimpleNamespace(DescriptorTree=Tree,stamp=real.stamp),proxy


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='prep-boundary-',dir=str(pathlib.Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup);self.root=self.temp.name
        self.entry,self.proxy=local_entry()
        self.patch=mock.patch.object(p,'os',self.proxy);self.patch.start();self.addCleanup(self.patch.stop)
    def test_real_read_and_recheck_preserve_exact_bytes(self):
        path=self.root+'/fixed';pathlib.Path(path).write_bytes(b'original\n');os.chmod(path,0o600)
        value=p.Gatherer(self.entry,time.monotonic()+30)
        try:
            raw,row=value.read(path,32,private=True);self.assertEqual(raw,b'original\n')
            value.recheck();self.assertEqual(row['size'],9)
        finally:value.close()
    def test_replaced_file_or_changed_bytes_refuse(self):
        path=self.root+'/fixed';pathlib.Path(path).write_bytes(b'old');os.chmod(path,0o600)
        value=p.Gatherer(self.entry,time.monotonic()+30)
        try:
            value.read(path,32,private=True);pathlib.Path(path).write_bytes(b'new')
            with self.assertRaises(ValueError):value.recheck()
        finally:value.close()
    def test_leaf_symlink_is_never_followed(self):
        target=self.root+'/target';pathlib.Path(target).write_bytes(b'private');os.symlink(target,self.root+'/alias')
        value=p.Gatherer(self.entry,time.monotonic()+30)
        try:
            with self.assertRaises(OSError):value.read(self.root+'/alias',32)
        finally:value.close()
    def test_generic_two_link_file_refuses(self):
        target=self.root+'/target';pathlib.Path(target).write_bytes(b'private');os.link(target,self.root+'/alias')
        value=p.Gatherer(self.entry,time.monotonic()+30)
        try:
            with self.assertRaisesRegex(ValueError,'FILE_AUTHORITY'):value.read(target,32)
        finally:value.close()
    def test_bounded_file_and_private_mode_refuse(self):
        path=self.root+'/fixed';pathlib.Path(path).write_bytes(b'0123456789');os.chmod(path,0o644)
        value=p.Gatherer(self.entry,time.monotonic()+30)
        try:
            for maximum,private in ((5,False),(20,True)):
                with self.assertRaises(ValueError):value.read(path,maximum,private)
        finally:value.close()
    def bundle(self):
        return {'plan_raw':b'{"plan":1}\n','seed_raw':b'{"seed":"private fixture"}\n',
            'unsigned_approval':{'decision':'UNSIGNED_TEST'},'summary':{'install_admission':'NOT_GRANTED'}}
    def test_exclusive_outputs_private_exact_and_no_overwrite(self):
        bundle=self.bundle()
        with mock.patch.object(p,'CAND',self.root):
            rows=p.publish_bundle(self.entry,bundle,{'expected_review_body':{}},{'schema':1,'files':{}},time.monotonic()+30)
            self.assertEqual(len(rows),3)
            for row in rows:
                raw=pathlib.Path(row['path']).read_bytes();self.assertEqual(data.sha(raw),row['sha256'])
                self.assertEqual(os.stat(row['path']).st_mode&0o777,0o600)
            with self.assertRaisesRegex(ValueError,'OUTPUT_EXISTS'):
                p.publish_bundle(self.entry,bundle,{'expected_review_body':{}},{},time.monotonic()+30)
            self.assertEqual(len(os.listdir(self.root)),3)
    def test_output_failure_keeps_protected_partial_and_no_success(self):
        bundle=self.bundle();original=self.proxy.write;calls=[0]
        def write(fd,raw):
            calls[0]+=1
            if calls[0]==2:raise OSError(errno.ENOSPC,'private text')
            return original(fd,raw)
        with mock.patch.object(p,'CAND',self.root),mock.patch.object(self.proxy,'write',side_effect=write):
            with self.assertRaises(OSError) as caught:
                p.publish_bundle(self.entry,bundle,{'expected_review_body':{}},{},time.monotonic()+30)
        self.assertEqual(len(caught.exception.preparation_outputs),1)
        self.assertEqual(len(caught.exception.preparation_created_paths),2)
        self.assertEqual(len(os.listdir(self.root)),2)
        for name in os.listdir(self.root):self.assertEqual(os.stat(self.root+'/'+name).st_mode&0o777,0o600)


class FixtureAuthorityTests(unittest.TestCase):
    setUp=FilesystemTests.setUp
    def test_fixture_owners_are_only_root_and_current_coherent_pair(self):
        with mock.patch.object(os,'getuid',return_value=1001),mock.patch.object(os,'getgid',return_value=1007):
            self.assertEqual(fixture_owners(),((0,0),(1001,1007)))
    def test_original_authority_accepts_exact_pairs_and_rejects_foreign_or_mixed(self):
        real=p.load_entry((fixture_kit()/'epoch7_recovery_entry.py').read_bytes())
        tree=object.__new__(real.DescriptorTree);tree.owners=((0,0),(1001,1007))
        for uid,gid,accepted in ((0,0,True),(1001,1007,True),(1001,0,False),(0,1007,False),(1002,1007,False)):
            info=types.SimpleNamespace(st_mode=0o40755,st_uid=uid,st_gid=gid)
            with self.subTest(uid=uid,gid=gid),mock.patch.object(real.os,'fstat',return_value=info),\
                 mock.patch.object(real.os,'getxattr',side_effect=OSError(errno.ENODATA,'no fixture ACL')):
                if accepted:self.assertIs(tree._authority(42,True),info)
                else:
                    with self.assertRaisesRegex(ValueError,'UNTRUSTED_AUTHORITY'):tree._authority(42,True)
    def test_real_full_ancestry_and_hosted_mixed_ownership(self):
        tree=self.entry.DescriptorTree(self.root)
        try:
            tree.real.recheck();tree.recheck()
            rows=tree.real.opened
            self.assertEqual(rows[0][3],'/');self.assertEqual(rows[-1][3],self.root)
            pairs=[(os.fstat(row[0]).st_uid,os.fstat(row[0]).st_gid) for row in rows]
            self.assertTrue(all(pair in fixture_owners() for pair in pairs))
            self.assertEqual(pairs[-1],(os.getuid(),os.getgid()))
            if os.environ.get('GITHUB_ACTIONS')=='true':
                self.assertNotEqual(os.geteuid(),0)
                self.assertEqual(pairs[0],(0,0))
                self.assertIn((os.getuid(),os.getgid()),pairs)
                self.assertGreater(len(set(pairs)),1)
        finally:tree.real.close()

class SocketInventoryTests(unittest.TestCase):
    setUp=FilesystemTests.setUp
    # These additional cases use the same exact reader and map only the three
    # fixed logical systemd roots to disposable local directories.
    def reader(self):
        mapping={}
        for index,prefix in enumerate(('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')):
            path=self.root+'/scope'+str(index);os.mkdir(path,0o755);mapping[prefix]=path
        entry=types.SimpleNamespace(DescriptorTree=lambda logical:self.entry.DescriptorTree(mapping[logical]))
        return p.Gatherer(entry,time.monotonic()+30),mapping
    def test_socket_absence_is_explicit_and_rechecked(self):
        reader,mapping=self.reader()
        try:
            proof=reader.socket_dropins();topology.validate_socket_dropins(proof)
            self.assertTrue(all(row['present'] is False and row['metadata'] is None for row in proof['roots'].values()))
            reader.recheck()
            os.mkdir(mapping['/etc/systemd/system']+'/xuanjun-ledger.socket.d',0o755)
            with self.assertRaises(ValueError):reader.socket_dropins()
        finally:reader.close()
    def test_socket_existing_empty_directory_has_metadata(self):
        reader,mapping=self.reader()
        try:
            os.mkdir(mapping['/etc/systemd/system']+'/xuanjun-ledger.socket.d',0o755)
            # Initial protected parent capture precedes this local setup. Start
            # a fresh reader to reproduce an actually stable measured parent.
            proof=reader.socket_dropins();topology.validate_socket_dropins(proof)
            self.assertTrue(proof['roots']['/etc/systemd/system/xuanjun-ledger.socket.d']['present'])
        finally:reader.close()
    def test_socket_directory_symlink_is_not_followed(self):
        reader,mapping=self.reader()
        try:
            os.symlink(self.root,mapping['/etc/systemd/system']+'/xuanjun-ledger.socket.d')
            with self.assertRaisesRegex(ValueError,'DIRECTORY_TYPE'):reader.socket_dropins()
        finally:reader.close()

class SourceLoadingTests(unittest.TestCase):
    def test_frozen_new_helper_bytes_match_independent_pins(self):
        root=pathlib.Path(__file__).resolve().parent
        for name,wanted in p.PREPARATION_SOURCES.items():self.assertEqual(data.sha((root/(name+'.py')).read_bytes()),wanted)
    def test_mutated_source_never_executes(self):
        cache={name:b'mutated' for name in p.PREPARATION_SOURCES}
        with mock.patch.object(p.sys,'modules',{}),mock.patch('builtins.compile',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(ValueError,'SOURCE_PIN'):
                with p.preparation_modules(cache):pass
    def test_actual_r6_cached_import_closure_with_pinned_preparation_helpers(self):
        import subprocess
        root=pathlib.Path(__file__).resolve().parent.parent
        kit=fixture_kit()
        wrapper=pathlib.Path(__file__).resolve().parent/'epoch7_prepare.py'
        script="""import os,pathlib,types
raw=pathlib.Path(%r).read_bytes();module=types.ModuleType('prep');module.__file__=%r
exec(compile(raw,module.__file__,'exec'),module.__dict__)
entry=module.load_entry(pathlib.Path(%r).read_bytes())
kit=entry._verify(%r,module.KIT_SHA,%r)
cache={name:pathlib.Path(%r+'/'+name+'.py').read_bytes() for name in module.PREPARATION_SOURCES}
with kit.imports(),module.preparation_modules(cache) as pair:
 import epoch7_host_factory
 assert len(pair)==2
 print('AUTHENTICATED_CACHED_IMPORTS_OK')
"""%(str(wrapper),str(wrapper),str(kit/'epoch7_recovery_entry.py'),str(kit),fixture_owners(),str(pathlib.Path(__file__).resolve().parent))
        result=subprocess.run([p.sys.executable,'-I','-B','-S','-c',script],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode('utf-8','replace'))
        self.assertEqual(result.stdout,b'AUTHENTICATED_CACHED_IMPORTS_OK\n')


class FinalBoundaryTests(unittest.TestCase):
    def test_budget_failure_after_publication_retains_all_output_paths(self):
        import contextlib
        rows=[{'path':'/fixed/'+str(i),'sha256':'a'*64,'bytes':12} for i in range(3)]
        for error in (p.DeadlineError(),p.CleanupError()):
            @contextlib.contextmanager
            def boundary():
                yield 100
                raise error
            flags=types.SimpleNamespace(isolated=1,no_site=1)
            with self.subTest(error=type(error).__name__),mock.patch.object(p.sys,'flags',flags),\
                 mock.patch.object(p.sys,'dont_write_bytecode',True),mock.patch.object(p,'budget',boundary),\
                 mock.patch.object(p,'run_preparation',return_value={'outputs':rows}):
                with self.assertRaises(type(error)) as caught:
                    p.main(['--operation','prepare','--observation','/fixed','--observation-sha256','a'*64,
                        '--topology-review-id','7000000001','--retained-renewal-timer','enable-after-reviewed-checks'])
                self.assertEqual(caught.exception.preparation_outputs,rows)
                self.assertEqual(caught.exception.preparation_created_paths,[row['path'] for row in rows])


class PostPublicationTests(unittest.TestCase):
    setUp=FilesystemTests.setUp
    bundle=FilesystemTests.bundle
    def test_later_oversize_creates_nothing(self):
        bundle=self.bundle();bundle['seed_raw']=b'x'*(64*1024*1024+1)
        with mock.patch.object(p,'CAND',self.root),self.assertRaisesRegex(ValueError,'ALL_OUTPUT_BOUNDS'):
            p.publish_bundle(self.entry,bundle,{'expected_review_body':{}},{},time.monotonic()+30)
        self.assertEqual(os.listdir(self.root),[])
    def test_first_output_changed_during_second_write_refuses(self):
        bundle=self.bundle();write=self.proxy.write;calls=[0]
        first=self.root+'/epoch7-approved-plan-'+data.sha(bundle['plan_raw'])[:16]+'.private.json'
        def mutate(fd,raw):
            calls[0]+=1
            if calls[0]==2:pathlib.Path(first).write_bytes(b'changed')
            return write(fd,raw)
        with mock.patch.object(p,'CAND',self.root),mock.patch.object(self.proxy,'write',side_effect=mutate):
            with self.assertRaises(ValueError) as caught:
                p.publish_bundle(self.entry,bundle,{'expected_review_body':{}},{},time.monotonic()+30)
        self.assertEqual(len(caught.exception.preparation_created_paths),3)
    def test_only_owned_parent_delta_allows_complete_input_recheck(self):
        path=self.root+'/captured';pathlib.Path(path).write_bytes(b'unchanged');os.chmod(path,0o600)
        with mock.patch.object(p,'CAND',self.root):
            gather=p.Gatherer(self.entry,time.monotonic()+30)
            try:
                gather.read(path,100,private=True)
                outputs=p.publish_bundle(self.entry,self.bundle(),{'expected_review_body':{}},{},time.monotonic()+30)
                gather.accept_owned_publication(outputs);gather.recheck()
                p.verify_publication(self.entry,outputs,time.monotonic()+30)
                pathlib.Path(path).write_bytes(b'drift')
                with self.assertRaises(ValueError):gather.recheck()
            finally:gather.close()
    def test_unowned_parent_change_before_publication_cannot_rebase(self):
        path=self.root+'/captured';pathlib.Path(path).write_bytes(b'unchanged');os.chmod(path,0o600)
        with mock.patch.object(p,'CAND',self.root):
            gather=p.Gatherer(self.entry,time.monotonic()+30)
            try:
                gather.read(path,100,private=True);pathlib.Path(self.root+'/unexpected').write_bytes(b'new')
                outputs=p.publish_bundle(self.entry,self.bundle(),{'expected_review_body':{}},{},time.monotonic()+30)
                with self.assertRaisesRegex(ValueError,'BEFORE_DRIFT'):gather.accept_owned_publication(outputs)
            finally:gather.close()
    def test_output_drift_after_publication_is_not_hidden_by_inputs(self):
        with mock.patch.object(p,'CAND',self.root):
            outputs=p.publish_bundle(self.entry,self.bundle(),{'expected_review_body':{}},{},time.monotonic()+30)
            pathlib.Path(outputs[0]['path']).write_bytes(b'drift')
            with self.assertRaises(ValueError):p.verify_publication(self.entry,outputs,time.monotonic()+30)


class FinalInventoryTests(unittest.TestCase):
    setUp=FilesystemTests.setUp
    bundle=FilesystemTests.bundle
    def test_unrelated_entry_created_during_publication_refuses(self):
        write=self.proxy.write;calls=[0]
        def mutate(fd,raw):
            calls[0]+=1
            if calls[0]==2:pathlib.Path(self.root+'/unrelated').write_bytes(b'extra')
            return write(fd,raw)
        with mock.patch.object(p,'CAND',self.root),mock.patch.object(self.proxy,'write',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'UNOWNED_DIRECTORY_CHANGE') as caught:
                p.publish_bundle(self.entry,self.bundle(),{'expected_review_body':{}},{},time.monotonic()+30)
        self.assertEqual(len(caught.exception.preparation_created_paths),3)
    def test_first_parent_authority_failure_closes_every_descriptor(self):
        tree=self.entry.DescriptorTree(self.root);fds=[row[0] for row in tree.opened]
        entry=types.SimpleNamespace(DescriptorTree=lambda unused:tree,stamp=self.entry.stamp)
        with mock.patch.object(p,'CAND',self.root),mock.patch.object(tree,'_authority',side_effect=ValueError('fixed')):
            with self.assertRaisesRegex(ValueError,'fixed'):
                p.publish_bundle(entry,self.bundle(),{'expected_review_body':{}},{},time.monotonic()+30)
        self.assertTrue(tree.closed)
        for fd in fds:
            with self.assertRaises(OSError) as caught:os.fstat(fd)
            self.assertEqual(caught.exception.errno,errno.EBADF)
        self.assertEqual(os.listdir(self.root),[])


class ArmFailureTests(unittest.TestCase):
    def test_initial_timer_arm_failure_restores_prior_handler(self):
        primary=OSError(errno.EIO,'private text');old=object()
        with mock.patch.object(p.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(p.signal,'getsignal',return_value=old),\
             mock.patch.object(p.signal,'signal') as handler,mock.patch.object(p.signal,'setitimer',side_effect=[primary,None]) as timer:
            with self.assertRaises(OSError) as caught:
                with p.budget(1):self.fail('must not yield after failed arm')
        self.assertIs(caught.exception,primary)
        self.assertEqual(handler.call_args_list[-1][0],(p.signal.SIGALRM,old))
        self.assertEqual(timer.call_args_list[-1][0],(p.signal.ITIMER_REAL,0))


class StatusDeliveryTests(unittest.TestCase):
    def test_unbuffered_status_is_exact_one_json_line(self):
        calls=[]
        with mock.patch.object(p.os,'write',side_effect=lambda fd,raw:(calls.append((fd,raw)) or len(raw))):
            p.deliver_status({'state':'HOLD','safe':True})
        self.assertTrue(all(fd==1 for fd,raw in calls))
        self.assertEqual(b''.join(raw for fd,raw in calls),p.packed({'state':'HOLD','safe':True}))
    def test_blocked_pipe_is_bounded_and_restores_handler(self):
        import fcntl,signal
        read,write=os.pipe();before=signal.getsignal(signal.SIGALRM);actual_write=os.write
        try:
            flags=fcntl.fcntl(write,fcntl.F_GETFL);fcntl.fcntl(write,fcntl.F_SETFL,flags|os.O_NONBLOCK)
            while True:
                try:actual_write(write,b'x'*4096)
                except BlockingIOError:break
            fcntl.fcntl(write,fcntl.F_SETFL,flags)
            started=time.monotonic()
            with mock.patch.object(p,'STATUS_SECONDS',.05),mock.patch.object(p.os,'write',side_effect=lambda fd,raw:actual_write(write,raw)):
                with self.assertRaises(p.StatusDeliveryError):p.deliver_status({'state':'HOLD'})
            self.assertLess(time.monotonic()-started,1.0)
            self.assertEqual(signal.getsignal(signal.SIGALRM),before)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
        finally:os.close(write);os.close(read)
    def test_partial_delivery_failure_is_never_retried_by_entrypoint(self):
        error=p.StatusDeliveryError()
        with mock.patch.object(p,'main',side_effect=error),mock.patch.object(p,'deliver_status') as deliver:
            self.assertEqual(p.entrypoint([]),2)
        deliver.assert_not_called()
    def test_primary_failure_reports_paths_once_even_when_sink_fails(self):
        error=ValueError('private text');error.preparation_created_paths=['/fixed/output']
        error.preparation_outputs=[{'path':'/fixed/output','sha256':'1'*64,'bytes':5}]
        with mock.patch.object(p,'main',side_effect=error),mock.patch.object(p,'deliver_status',side_effect=p.StatusDeliveryError()) as deliver:
            self.assertEqual(p.entrypoint([]),2)
        self.assertEqual(deliver.call_count,1)
        self.assertEqual(deliver.call_args[0][0]['created_output_paths'],['/fixed/output'])
        self.assertNotIn('private text',repr(deliver.call_args[0][0]))
    def test_output_bound_rejects_before_any_sink_write(self):
        with mock.patch.object(p.os,'write') as write:
            with self.assertRaises(p.StatusDeliveryError):p.deliver_status({'payload':'x'*131072})
        write.assert_not_called()
    def test_parser_errors_do_not_use_buffered_output(self):
        with mock.patch('builtins.print',side_effect=AssertionError('no print')):
            with self.assertRaisesRegex(ValueError,'ARGUMENTS'):p.main(['--unknown'])

class SafeFailureTests(unittest.TestCase):
    def test_contract_boundary_labels_require_exact_single_valueerror(self):
        labels=('EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY','EPOCH7_PREP_MANAGER_OBSERVATION_BINDING',
                'EPOCH7_PREP_TOOL_OBSERVATION_BINDING')
        for label in labels:
            cases=((ValueError(label),label),(ValueError(label+' secret contents'),None),
                   (ValueError(label+'_secret'),None),(ValueError(label,'secret contents'),None),
                   (RuntimeError(label),None))
            for error,expected in cases:
                with self.subTest(label=label,error=repr(error)),mock.patch.object(p,'CURRENT_PHASE','COLLECT_INPUTS'),\
                     mock.patch.object(p,'main',side_effect=error),mock.patch.object(p,'deliver_status') as deliver:
                    self.assertEqual(p.entrypoint([]),2)
                row=deliver.call_args[0][0]
                self.assertEqual(row['phase'],'COLLECT_INPUTS')
                self.assertEqual(row['failure_label'],expected)
                self.assertEqual(row['failure_code'],type(error).__name__)
                self.assertNotIn('secret',repr(row))
    def test_fixed_phase_and_exact_static_label_are_reported(self):
        with mock.patch.object(p,'CURRENT_PHASE','COLLECT_INPUTS'),mock.patch.object(p,'main',
             side_effect=ValueError('EPOCH7_PREP_RETAINED_BUFFER_CHANGED')),mock.patch.object(p,'deliver_status') as deliver:
            self.assertEqual(p.entrypoint([]),2)
        row=deliver.call_args[0][0]
        self.assertEqual(row['phase'],'COLLECT_INPUTS')
        self.assertEqual(row['failure_label'],'EPOCH7_PREP_RETAINED_BUFFER_CHANGED')
        self.assertEqual(row['failure_code'],'ValueError')
    def test_unknown_helper_text_or_label_prefix_never_leaks(self):
        for error in (ValueError('secret contents'),ValueError('EPOCH7_PREP_RETAINED_BUFFER_CHANGED secret'),
                      ValueError('EPOCH7_PREP_ARGUMENTS','secret contents'),RuntimeError('secret contents')):
            with self.subTest(error=type(error).__name__),mock.patch.object(p,'CURRENT_PHASE','PROJECT_TOPOLOGY'),\
                 mock.patch.object(p,'main',side_effect=error),mock.patch.object(p,'deliver_status') as deliver:
                self.assertEqual(p.entrypoint([]),2)
            row=deliver.call_args[0][0]
            self.assertIsNone(row['failure_label'])
            self.assertEqual(row['phase'],'PROJECT_TOPOLOGY')
            self.assertNotIn('secret',repr(row))
        with mock.patch.object(p,'CURRENT_PHASE','INPUT_VALIDATION'):
            with self.assertRaisesRegex(ValueError,'PHASE'):p.phase('request supplied phase')
            self.assertEqual(p.CURRENT_PHASE,'INPUT_VALIDATION')


class ProposalFinalVerificationTests(unittest.TestCase):
    def invoke(self,change=None,recheck_error=None):
        import contextlib,socket
        @contextlib.contextmanager
        def imports():yield
        kit=types.SimpleNamespace(raw_manifest=b'authenticated manifest',digest='1'*64,
            cache={'probe_driver.py':b'driver','probe_helpers.py':b'helpers','node_sqlite_probe.py':b'node'},
            manifest={'modules':{name:name+'.py' for name in ('probe_driver','probe_helpers','node_sqlite_probe')}},imports=imports)
        final=types.SimpleNamespace(raw_manifest=kit.raw_manifest,cache=dict(kit.cache))
        if change=='manifest':final.raw_manifest=b'changed'
        if change=='cache':final.cache['probe_driver.py']=b'changed'
        entry=types.SimpleNamespace(verify_kit=mock.Mock(side_effect=(kit,final)))
        gather=mock.Mock();gather.recheck.side_effect=recheck_error
        projection=types.SimpleNamespace(project_topology=mock.Mock(return_value={
            'expected_review_body':{'decision':'fixture only'},'topology_sha256':'2'*64}),fetch_topology_review=mock.Mock())
        @contextlib.contextmanager
        def modules(cache):yield data,projection
        collected={'observation':{},'receipt_raw':b'fixture','receipt_metadata':{},
                   'manifest_raw':b'fixture manifest','socket_dropins':{}}
        args=types.SimpleNamespace(operation='propose-topology',observation='/fixed',observation_sha256='3'*64)
        with mock.patch.object(p.os,'geteuid',return_value=0),mock.patch.object(socket,'gethostname',return_value=p.HOST),\
             mock.patch.object(p,'bootstrap_entry',return_value=entry),mock.patch.object(p,'Gatherer',return_value=gather),\
             mock.patch.object(p,'preparation_sources',return_value=({},{})),mock.patch.object(p,'preparation_modules',modules),\
             mock.patch.object(p,'collect_inputs',return_value=collected),mock.patch.object(p,'publish_bundle') as publish,\
             mock.patch.object(p,'compile_private_bundle') as compile_bundle:
            result=None;error=None
            try:result=p.run_preparation(args,time.monotonic()+10)
            except BaseException as caught:error=caught
        self.assertEqual(entry.verify_kit.call_args_list,[mock.call(p.KIT_ROOT,p.KIT_SHA)]*2)
        projection.fetch_topology_review.assert_not_called();publish.assert_not_called();compile_bundle.assert_not_called()
        gather.close.assert_called_once_with(error)
        return result,error,gather
    def test_proposal_rereads_entire_kit_and_captured_inputs_without_effects(self):
        result,error,gather=self.invoke()
        self.assertIsNone(error);self.assertEqual(result['state'],'TOPOLOGY_REVIEW_REQUIRED')
        self.assertEqual(result['install_admission'],'NOT_GRANTED');gather.recheck.assert_called_once_with()
    def test_proposal_changed_manifest_or_cache_refuses_unsigned_output(self):
        for change in ('manifest','cache'):
            with self.subTest(change=change):
                result,error,gather=self.invoke(change)
                self.assertIsNone(result);self.assertEqual(error.args,('EPOCH7_PREP_KIT_FINAL_CHANGED',))
                gather.recheck.assert_not_called()
    def test_proposal_final_input_drift_preserves_failure_and_closes(self):
        primary=ValueError('EPOCH7_PREP_GATHER_OBSERVATION_DRIFT')
        result,error,gather=self.invoke(recheck_error=primary)
        self.assertIsNone(result);self.assertIs(error,primary);gather.recheck.assert_called_once_with()


if __name__=='__main__':unittest.main()
