"""Preparation-only regressions. No production path, network, approval or claims.

Real successor loader hydration, factory, compiler, serialization and no-follow
exclusive output mechanics run. Source identity, private native byte pins,
historical host metadata and root ownership are explicitly synthetic fixtures.
The real unavailable predecessor bytes are never claimed to be authenticated.
"""
import ast
import copy
import contextlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'tests'))
sys.dont_write_bytecode = True
# Definitions only; discovery is restricted to this file, no historical suites.
import test_successor_approval_factory_entry as fixture
from test_epoch7_full_factory_fixture import directory, meta, fixture_proof, np

spec = importlib.util.spec_from_file_location('preparation_under_test', HERE / 'epoch7_prepare_successor.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
claim, factory, entry = fixture.claim, fixture.factory, fixture.entry


def complete_historical_fixture():
    """Complete missing archival fixture rows, not any real historical evidence."""
    seed = fixture.original_synthetic_seed()
    observation = seed['observation']; policy = observation['policy']; evidence = observation['evidence']
    retained = evidence['retained']
    retained['transaction_inventory'] = {claim.TRANSACTION + '/' + name: pin
                                       for name,pin in policy['transaction_inventory'].items()}
    dirs = {claim.TRANSACTION}
    for path in retained['transaction_inventory']:
        parent = os.path.dirname(path)
        while parent.startswith(claim.TRANSACTION):
            dirs.add(parent); parent = os.path.dirname(parent)
    retained['transaction_directories'] = {name: dict(directory(**policy['directories'][name], ino=800+i), path=name)
                                          for i,name in enumerate(sorted(dirs))}
    observation['snapshot']['retained_resource_sha256'] = factory.d.digest(retained)
    evidence['snapshot_sha256'] = factory.d.digest(observation['snapshot'])
    for name in ('snapshot', 'evidence'):
        observation[name + '_sha256'] = factory.d.digest(observation[name])
    attempt = observation['finite_probe']; probe_policy = attempt['policy']
    probe_policy['node_sqlite'] = np.binding_from_observation(observation)
    pin = p.sha(p.packed(probe_policy)); node = probe_policy['node_sqlite']['node']
    proof = fixture_proof(node, probe_policy['nonce'], pin, probe_policy['node_sqlite']['probe_input_sha256'])
    receipt = p.packed({'schema': 1, 'nonce': probe_policy['nonce'], 'policy_sha256': pin,
                       'events': [{'event': 'NODE_SQLITE_OBSERVED', 'detail': proof}]})
    attempt['policy_sha256'] = pin; attempt['result']['node_sqlite'] = proof
    attempt['result']['created_receipt'].update(sha256=p.sha(receipt),
        metadata={k:v for k,v in meta(receipt, mode=0o600).items() if k not in ('kind','sha256')},
        node_sqlite_event_sha256=factory.d.digest(proof))
    seed['fresh_release_parent']['observation_sha256'] = factory.d.digest(observation)
    return seed


def private_wire(seed):
    value = dict(seed, claim_successor=fixture.synthetic_contract(seed['kit_manifest_sha256']))
    private = fixture.private_seed(value); private.pop('claim_successor')
    return private


def measurement_fixture(private):
    policy = private['observation']['policy']
    ancestors = {name: dict(directory(**policy['directories'][name], ino=900+i), path=name)
                 for i,name in enumerate(factory.snap._predecessor_ancestors())}
    directories = copy.deepcopy(private['observation']['evidence']['retained']['transaction_directories'])
    directories[claim.TRANSACTION].update(size=8192, mtime_ns=22, ctime_ns=23)
    ancestors[claim.TRANSACTION] = directories[claim.TRANSACTION]
    record = {'schema': 1, 'raw_sha256': claim.PREDECESSOR_SHA256, 'raw_size': claim.PREDECESSOR_SIZE,
        'binding_sha256': claim.PREDECESSOR_BINDING_SHA256, 'state_sha256': claim.PREDECESSOR_STATE_SHA256,
        'context_sha256': p.sha(b'synthetic original context'),
        'metadata': dict(kind='FILE', sha256=claim.PREDECESSOR_SHA256, uid=0, gid=0, mode=0o600,
            dev=8, ino=901, nlink=1, size=claim.PREDECESSOR_SIZE, mtime_ns=22, ctime_ns=23)}
    measurement = {'schema': 1, 'record': record, 'ancestors': ancestors,
        'absent': {claim.OLD_INNER: True, claim.NEW_OUTER: True, claim.NEW_INNER: True}}
    inventory = copy.deepcopy(private['observation']['evidence']['retained']['transaction_inventory'])
    inventory[claim.TRANSACTION+'/'+claim.OLD_OUTER] = claim.PREDECESSOR_SHA256
    changes = p.validate_transaction_relation(measurement, directories, inventory, private, factory.snap, claim)
    return {'measurement': measurement, 'transaction_directories': directories,
            'transaction_inventory': inventory, 'transaction_parent_delta': changes}


def mapped(info):
    values = {name:getattr(info,name) for name in dir(info) if name.startswith('st_')}
    values.update(st_uid=0, st_gid=0)
    return types.SimpleNamespace(**values)


def local_entry():
    """Genuine descriptor ops on local fixture files; only ownership is synthetic."""
    class Tree:
        def __init__(self, path):
            self.real = entry.DescriptorTree(path, owners=((0,0),(os.getuid(),os.getgid())))
            self.fd = self.real.fd; self.closed = False
            self.opened = [[fd,parent,name,logical,tuple(list(stamp[:3])+[0,0]+list(stamp[5:]))]
                           for fd,parent,name,logical,stamp in self.real.opened]
        def read(self,*args,**kwargs): return self.real.read(*args,**kwargs)
        def _authority(self,*args,**kwargs): return mapped(self.real._authority(*args,**kwargs))
        def recheck(self):
            for fd,parent,name,logical,before in self.opened:
                if entry.stamp(self._authority(fd,True)) != before: raise ValueError('LOCAL_ANCESTRY_RACE')
                if parent is not None and entry.stamp(mapped(os.stat(name,dir_fd=parent,follow_symlinks=False))) != before:
                    raise ValueError('LOCAL_PATH_RACE')
    proxy = types.SimpleNamespace(**{name:getattr(os,name) for name in dir(os) if not name.startswith('__')})
    proxy.stat = lambda *args,**kwargs: mapped(os.stat(*args,**kwargs))
    proxy.fstat = lambda *args,**kwargs: mapped(os.fstat(*args,**kwargs))
    return types.SimpleNamespace(DescriptorTree=Tree,stamp=entry.stamp), proxy


class PurePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = complete_historical_fixture()
        cls.private = private_wire(cls.seed)
        cls.measured = measurement_fixture(cls.private)
        cls.kit = fixture.fixture_kit(cls.seed)
    def compile(self, private=None, measured=None, kit=None, expiry='2099-01-01T00:00:00Z'):
        with fixture.native_pins(self.seed):
            return p.compile_successor_bundle(kit or self.kit, private or self.private,
                                              measured or self.measured, expiry)
    def test_real_factory_serialization_and_loader_roundtrip(self):
        before = copy.deepcopy(self.private); bundle = self.compile()
        envelope = json.loads(bundle['seed_raw']); packet = json.loads(bundle['packet_raw'])
        self.assertEqual(envelope['schema'], 2)
        self.assertEqual(len(envelope['seed']), 13)
        self.assertEqual(set(envelope['seed']), entry.PRIVATE_SEED_FIELDS)
        self.assertEqual({k:v for k,v in envelope['seed'].items() if k!='claim_successor'}, before)
        self.assertEqual(self.private, before)
        with fixture.native_pins(self.seed):
            seed = self.kit._hydrate_seed(envelope['seed'], factory)
            prepared = factory.prepare_host_inputs(seed)
            self.assertEqual(p.packed(factory.compile_host_contract(prepared['inputs'])), bundle['plan_raw'])
        self.assertEqual(len(seed['source_payloads']), 107)
        self.assertEqual(len(prepared['inputs']['resource_views']), 17)
        self.assertEqual(packet['final_review_body']['recovery_plan_sha256'], p.sha(bundle['plan_raw']))
        self.assertEqual(packet['claim_successor']['measured_predecessor_sha256'], claim.digest(self.measured['measurement']))
        self.assertEqual(packet['claim_successor']['implementation']['kit_manifest_sha256'], self.kit.digest)
        policy = 'PREPARED_START_30S_ORDERED_GUARDS_PUBLICATION_MIN_V1'
        self.assertEqual(bundle['claim_successor']['schema'], 1)
        self.assertEqual(bundle['claim_successor']['timing_policy'], policy)
        self.assertEqual(envelope['seed']['claim_successor'], bundle['claim_successor'])
        self.assertEqual(packet['claim_successor'], bundle['claim_successor'])
        self.assertEqual(packet['final_review_body']['sequence_contract']['claim_successor'],
                         bundle['claim_successor'])
        self.assertIsNone(packet['final_review_id']); self.assertIsNone(packet['final_review_body_sha256'])
        self.assertEqual(packet['production_resume'], 'NOT_EXECUTED')
        self.assertEqual(packet['final_review_body']['sequence_contract']['inner_attempt_name'], claim.NEW_INNER)
        self.assertEqual(packet['final_review_body']['sequence_contract']['outer_receipt_name'], claim.NEW_OUTER)
    def test_expiry_and_fresh_proof_change_plan_seed_and_unsigned_body(self):
        baseline = self.compile()
        expiry = self.compile(expiry='2099-01-02T00:00:00Z')
        changed = copy.deepcopy(self.measured)
        changed['measurement']['record']['metadata']['ctime_ns'] += 1
        fresh = self.compile(measured=changed)
        for result in (expiry,fresh):
            for name in ('plan_raw','seed_raw','packet_raw'): self.assertNotEqual(result[name],baseline[name])
        self.assertEqual(json.loads(expiry['packet_raw'])['final_review_body']['sequence_contract']['claim_successor']['admission_expires_at_utc'],
                         '2099-01-02T00:00:00Z')
    def test_changed_new_source_and_manifest_are_bound(self):
        baseline=self.compile(); kit=copy.copy(self.kit); kit.manifest=copy.deepcopy(kit.manifest)
        kit.manifest['kit_source_commit']='c'*40; kit.digest='d'*64
        result=self.compile(kit=kit)
        self.assertNotEqual(result['plan_raw'],baseline['plan_raw'])
        self.assertEqual(result['claim_successor']['implementation']['source_commit'],'c'*40)
        self.assertEqual(result['claim_successor']['implementation']['kit_manifest_sha256'],'d'*64)
    def test_absent_inner_and_successor_are_all_required(self):
        for name in (claim.OLD_INNER, claim.NEW_OUTER, claim.NEW_INNER):
            with self.subTest(name=name):
                changed=copy.deepcopy(self.measured);changed['measurement']['absent'][name]=False
                with self.assertRaises(ValueError):self.compile(measured=changed)
    def test_parent_identity_and_extra_child_refuse(self):
        for field in ('ino','dev','uid','gid','mode','nlink'):
            changed=copy.deepcopy(self.measured)
            changed['transaction_directories'][claim.TRANSACTION][field]+=1
            with self.subTest(field=field), self.assertRaises((p.Hold,ValueError)):self.compile(measured=changed)
        changed=copy.deepcopy(self.measured);changed['transaction_inventory'][claim.TRANSACTION+'/extra']='0'*64
        with self.assertRaises(p.Hold):self.compile(measured=changed)
    def test_original_private_field_mutation_is_not_hidden(self):
        changed=copy.deepcopy(self.private);changed['native_before']+=' '
        with self.assertRaises(ValueError):self.compile(private=changed)
    def test_unbound_source_refuses_before_host_read(self):
        with mock.patch.object(p,'open_chain',side_effect=AssertionError('host access forbidden')):
            with self.assertRaisesRegex(p.Hold,'SUCCESSOR_ARTIFACT_UNBOUND'):p.prepare('2099-01-01T00:00:00Z',time.monotonic()+20)
    def test_missing_expiry_and_malformed_source_refuse(self):
        for expiry in (None,'2099-01-01','2099-01-01T00:00:00+00:00'):
            with self.assertRaises(ValueError):self.compile(expiry=expiry)
        kit=copy.copy(self.kit);kit.manifest=dict(self.kit.manifest,kit_source_commit=None)
        with self.assertRaises(ValueError):self.compile(kit=kit)
        envelope=json.loads(self.compile()['seed_raw'])
        for policy in (None, 'PREPARE_TO_PUBLICATION_30S', True):
            changed=copy.deepcopy(envelope['seed'])
            if policy is None:changed['claim_successor'].pop('timing_policy')
            else:changed['claim_successor']['timing_policy']=policy
            with self.subTest(timing_policy=policy),fixture.native_pins(self.seed),self.assertRaises(ValueError):
                self.kit._hydrate_seed(changed,factory)
    def test_no_claim_resume_driver_or_network_call_in_tool(self):
        tree=ast.parse((HERE/'epoch7_prepare_successor.py').read_text())
        denied={'assemble_host_driver','successor_resume','successor_resume_once','prepare_successor','commit_successor',
                'create_attempt','claim_outer','fetch','urlopen','flock','system','Popen','run'}
        called={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
        self.assertFalse(called & denied)


class PrivatePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='successor-private-',dir=str(HERE));self.addCleanup(self.temp.cleanup)
        self.root=self.temp.name;self.loader,self.proxy=local_entry()
        self.patch=mock.patch.multiple(p,os=self.proxy,CAND=self.root);self.patch.start();self.addCleanup(self.patch.stop)
        self.bundle={'plan_raw':b'{"synthetic_plan":1}\n','seed_raw':b'{"schema":2,"seed":{}}\n',
                     'packet_raw':b'{"final_review_id":null}\n'}
    def publish(self):return p.publish_bundle(self.loader,self.bundle,time.monotonic()+30)
    def test_real_exclusive_three_private_outputs_and_no_overwrite(self):
        prior=pathlib.Path(self.root)/'epoch7-successor-approved-plan-retained.private.json'
        prior.write_bytes(b'retained prior successor artifact');prior.chmod(0o600)
        prior_before=prior.stat()
        rows=self.publish();self.assertEqual(len(rows),3)
        self.assertEqual(prior.read_bytes(),b'retained prior successor artifact')
        self.assertEqual(prior.stat(),prior_before)
        for row in rows:
            path=pathlib.Path(row['path']);self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(p.sha(path.read_bytes()),row['sha256'])
            self.assertTrue(path.name.startswith('epoch7-lifecycle-'))
        before={f.name:f.read_bytes() for f in pathlib.Path(self.root).iterdir()}
        with self.assertRaises(ValueError):self.publish()
        self.assertEqual(before,{f.name:f.read_bytes() for f in pathlib.Path(self.root).iterdir()})
    def test_existing_third_output_refuses_before_any_creation(self):
        name='epoch7-lifecycle-review-packet-'+p.sha(self.bundle['packet_raw'])[:16]+'.private.json'
        path=pathlib.Path(self.root)/name;path.write_bytes(b'preserve me');path.chmod(0o600)
        with self.assertRaises(ValueError):self.publish()
        self.assertEqual(list(pathlib.Path(self.root).iterdir()),[path]);self.assertEqual(path.read_bytes(),b'preserve me')
    def test_first_write_interruption_retains_partial_and_never_creates_second(self):
        with mock.patch.object(self.proxy,'write',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt) as caught:self.publish()
        self.assertEqual(len(list(pathlib.Path(self.root).iterdir())),1)
        self.assertEqual(len(caught.exception.preparation_created_paths),1)
        self.assertEqual(caught.exception.preparation_outputs,[])
    def test_first_readback_failure_retains_first_and_stops(self):
        with mock.patch.object(self.loader.DescriptorTree,'read',return_value=b'wrong'):
            with self.assertRaises(p.Hold) as caught:self.publish()
        self.assertEqual(len(list(pathlib.Path(self.root).iterdir())),1)
        self.assertEqual(caught.exception.preparation_outputs,[])
    def test_second_create_failure_retains_first_and_no_third(self):
        real=self.proxy.open;count=[0]
        def opened(path,flags,*args,**kwargs):
            if flags & os.O_CREAT:
                count[0]+=1
                if count[0]==2:raise OSError('synthetic second create failure')
            return real(path,flags,*args,**kwargs)
        with mock.patch.object(self.proxy,'open',side_effect=opened):
            with self.assertRaises(OSError) as caught:self.publish()
        self.assertEqual(count[0],2);self.assertEqual(len(list(pathlib.Path(self.root).iterdir())),1)
        self.assertEqual(len(caught.exception.preparation_outputs),1)
    def test_final_read_detects_changed_output(self):
        rows=self.publish();pathlib.Path(rows[0]['path']).write_bytes(b'changed')
        with self.assertRaises(p.Hold):p.verify_publication(self.loader,rows,time.monotonic()+30)
    def test_private_read_refuses_symlink_and_wrong_mode(self):
        # Separate real absolute traversal coverage, outside the composed namespace.
        held,rows,parent=p.open_chain()
        try:
            p.recheck(rows)
            self.assertEqual(len(rows),len(self.root.strip('/').split('/'))+1)
            self.assertEqual(rows[-1][2],parent)
        finally:p.close_all(held)
        root=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            path=pathlib.Path(self.root)/'original';path.write_bytes(b'keep');path.chmod(0o600)
            raw,metadata=p.read_exact(root,'original',4,p.sha(b'keep'));self.assertEqual(raw,b'keep')
            os.symlink('original',pathlib.Path(self.root)/'alias')
            with self.assertRaises(OSError):p.read_exact(root,'alias',4,p.sha(b'keep'))
            path.chmod(0o644)
            with self.assertRaises(p.Hold):p.read_exact(root,'original',4,p.sha(b'keep'))
        finally:os.close(root)


@contextlib.contextmanager
def synthetic_import_scope(unused_kit):
    """Explicit source/import boundary only; compatible with the target3.6 API."""
    yield


class ComposedPreparationTests(unittest.TestCase):
    """Real orchestration/compiler/writer in an explicit private fixture namespace."""
    @classmethod
    def setUpClass(cls):
        cls.seed=complete_historical_fixture();cls.private=private_wire(cls.seed)
        cls.measured=measurement_fixture(cls.private)
    def exercise(self, drift=False):
        with tempfile.TemporaryDirectory(prefix='prepare-composed-',dir=str(HERE)) as anchor:
            # Only this composed fixture maps logical '/' to a private anchor.
            # Real open_chain, recheck, DescriptorTree and relative openat calls run.
            root='/parent/candidate'
            def physical(path):
                return anchor+path if isinstance(path,str) and path.startswith('/') else path
            os.mkdir(physical('/parent'),0o700);os.mkdir(physical(root),0o700)
            loader,proxy=local_entry();proxy.geteuid=lambda:0
            proxy.open=lambda path,*args,**kwargs:os.open(physical(path),*args,**kwargs)
            proxy.stat=lambda path,*args,**kwargs:mapped(os.stat(physical(path),*args,**kwargs))
            old_root=root+'/old-kit';new_root=root+'/new-kit'
            raw_old=b'synthetic original entry boundary';raw_new=b'synthetic successor entry boundary'
            for path,raw in ((old_root,raw_old),(new_root,raw_new)):
                os.mkdir(physical(path),0o755);file=pathlib.Path(physical(path))/'epoch7_recovery_entry.py';file.write_bytes(raw);file.chmod(0o444)
            originals={'seed':p.packed({'schema':1,'seed':self.private}),
                       'plan':b'{"synthetic_original_plan":true}\n',
                       'packet':b'{"synthetic_original_packet":true}\n'}
            files=tuple((role,'original-'+role+'.private.json',len(raw),p.sha(raw)) for role,raw in originals.items())
            for role,leaf,size,pin in files:
                file=pathlib.Path(physical(root))/leaf;file.write_bytes(originals[role]);file.chmod(0o600)
            kit=fixture.fixture_kit(self.seed);kit.root=new_root
            old_kit=copy.copy(kit);old_kit.root=old_root
            new_loader=types.SimpleNamespace(**loader.__dict__,RUNTIME=entry.RUNTIME,verify_kit=lambda *unused:kit)
            old_loader=types.SimpleNamespace(**loader.__dict__,RUNTIME=entry.RUNTIME,verify_kit=lambda *unused:old_kit)
            events=[];measure_calls=[0]
            def bootstrap(rows,held,parent,successor):
                selected=new_root if successor else old_root
                fd=os.open(os.path.basename(selected),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                held.append(fd);rows.append((parent,os.path.basename(selected),fd,p.directory(fd)))
                raw=raw_new if successor else raw_old
                read,metadata=p.read_exact(fd,'epoch7_recovery_entry.py',len(raw),p.sha(raw),private=False)
                events.append('bootstrap-new' if successor else 'bootstrap-old')
                return (new_loader,kit,(fd,read,metadata)) if successor else (old_loader,old_kit,(fd,read,metadata))
            def original(loader,kit,raws):
                self.assertEqual(raws,originals);events.append('original-authenticated-boundary')
                return copy.deepcopy(self.private)
            def measurement(*unused):
                measure_calls[0]+=1;events.append('measure-'+str(measure_calls[0]))
                value=copy.deepcopy(self.measured)
                if drift and measure_calls[0]==3:value['measurement']['record']['metadata']['ctime_ns']+=1
                return value
            sys_proxy=types.SimpleNamespace(flags=types.SimpleNamespace(isolated=True,no_site=True),dont_write_bytecode=True)
            with mock.patch.multiple(p,CAND=root,OLD_ROOT=old_root,NEW_ROOT=new_root,FILES=files,
                    OLD_ENTRY_BYTES=len(raw_old),OLD_ENTRY_SHA=p.sha(raw_old),
                    NEW_ENTRY_BYTES=len(raw_new),NEW_ENTRY_SHA=p.sha(raw_new),os=proxy,sys=sys_proxy), \
                 mock.patch.object(p,'require_binding'),mock.patch.object(p.socket,'gethostname',return_value=p.HOST), \
                 mock.patch.object(p,'cold_uuid_parser'),mock.patch.object(p,'bootstrap',side_effect=bootstrap), \
                 mock.patch.object(p,'verify_kit_identity'),mock.patch.object(p,'validate_original',side_effect=original), \
                 mock.patch.object(p,'authenticated_imports',side_effect=synthetic_import_scope), \
                 mock.patch.object(entry,'os',proxy), \
                 mock.patch.object(p,'measure_predecessor',side_effect=measurement),fixture.native_pins(self.seed):
                # Each actual fixture ancestor remains independently guarded.
                for logical in ('/','/parent',root):
                    held,rows,parent=p.open_chain()
                    try:
                        self.assertEqual(len(rows),3)
                        self.assertEqual(len({row[2] for row in rows}),3)
                        marker=pathlib.Path(physical(logical))/'unowned-change'
                        marker.mkdir(mode=0o700)
                        try:
                            with self.assertRaisesRegex(p.Hold,'PATH_IDENTITY'):p.recheck(rows)
                        finally:marker.rmdir()
                    finally:p.close_all(held)
                alias=physical('/parent/alias');os.symlink('candidate',alias)
                try:
                    with mock.patch.object(p,'CAND','/parent/alias'),self.assertRaises(OSError):p.open_chain()
                finally:os.unlink(alias)
                if drift:
                    with self.assertRaisesRegex(p.Hold,'PREDECESSOR_FINAL_CHANGED') as caught:
                        p.prepare('2099-01-01T00:00:00Z',time.monotonic()+60)
                    outputs=caught.exception.preparation_outputs
                    self.assertEqual(len(caught.exception.preparation_created_paths),3)
                else:
                    result=p.prepare('2099-01-01T00:00:00Z',time.monotonic()+60)
                    self.assertEqual(result['state'],'PREPARED_NOT_ADMITTED');outputs=result['outputs']
            self.assertEqual(len(outputs),3);self.assertEqual(measure_calls[0],3)
            self.assertEqual(events[:3],['bootstrap-old','bootstrap-new','original-authenticated-boundary'])
            for row in outputs:self.assertEqual(p.sha(pathlib.Path(physical(row['path'])).read_bytes()),row['sha256'])
            for role,leaf,size,pin in files:self.assertEqual((pathlib.Path(physical(root))/leaf).read_bytes(),originals[role])
    def test_composed_preparation_runs_real_factory_and_publication(self):self.exercise()
    def test_postpublication_proof_drift_retains_all_three_outputs(self):self.exercise(drift=True)


class StatusSafetyTests(unittest.TestCase):
    def test_successful_outputs_retained_if_status_fails(self):
        outputs=[{'path':'/synthetic/one','bytes':1,'sha256':'a'*64}]
        result={'state':'PREPARED_NOT_ADMITTED','outputs':outputs}
        with mock.patch.object(p,'prepare',return_value=result), \
             mock.patch.object(p.os,'write',side_effect=OSError('synthetic status interruption')):
            with self.assertRaises(OSError) as caught:p.main(['--operation','prepare','--admission-expires-at-utc','2099-01-01T00:00:00Z'])
        self.assertEqual(caught.exception.preparation_outputs,outputs)
        self.assertEqual(caught.exception.preparation_created_paths,['/synthetic/one'])
    def test_cleanup_error_reports_unknown(self):
        sent=[]
        with mock.patch.object(p,'main',side_effect=p.CleanupError()), \
             mock.patch.object(p.os,'write',side_effect=lambda fd,raw: sent.append(raw) or len(raw)):
            self.assertEqual(p.entrypoint([]),2)
        self.assertTrue(json.loads(b''.join(sent))['cleanup_unknown'])
    def test_bare_descriptor_cleanup_error_is_explicit(self):
        with mock.patch.object(p.os,'close',side_effect=OSError('synthetic cleanup uncertainty')):
            with self.assertRaises(p.CleanupError):p.close_all([42])
    def test_timer_restoration_failure_is_explicit_cleanup(self):
        with mock.patch.object(p.signal,'getitimer',return_value=(0.0,0.0)), \
             mock.patch.object(p.signal,'getsignal',return_value=object()), \
             mock.patch.object(p.signal,'signal'), \
             mock.patch.object(p.signal,'setitimer',side_effect=[None,OSError('synthetic timer cleanup')]):
            with self.assertRaises(p.CleanupError):
                with p.budget(10):pass
    def test_import_cleanup_preserves_primary_and_marks_unknown(self):
        class Scope:
            def __enter__(self):return self
            def __exit__(self,*unused):raise OSError('synthetic scope cleanup')
        kit=types.SimpleNamespace(manifest={'modules':{}},imports=lambda:Scope())
        with self.assertRaises(p.CleanupError):
            with p.authenticated_imports(kit):pass
        primary=ValueError('first failure')
        with self.assertRaises(ValueError) as caught:
            with p.authenticated_imports(kit):raise primary
        self.assertIs(caught.exception,primary);self.assertTrue(primary.cleanup_unknown)
    def test_inherited_reader_cleanup_cause_is_detected(self):
        primary=ValueError('first protected read failure')
        primary.__cause__=ValueError('READER_PARENT_CLEANUP_UNKNOWN')
        self.assertTrue(p.cleanup_unknown(primary))
        other=ValueError('read failed');other.__context__=OSError('unclassified nested I/O')
        self.assertTrue(p.cleanup_unknown(other))
        self.assertFalse(p.cleanup_unknown(ValueError('ordinary semantic refusal')))
    def test_budget_is_one_shot_and_terminal_check_remains(self):
        calls=[]
        with mock.patch.object(p.signal,'getitimer',return_value=(0.0,0.0)), \
             mock.patch.object(p.signal,'getsignal',return_value=object()), \
             mock.patch.object(p.signal,'signal'), \
             mock.patch.object(p.signal,'setitimer',side_effect=lambda *args:calls.append(args)), \
             mock.patch.object(p.time,'monotonic',side_effect=[10,12]):
            with self.assertRaises(p.Deadline):
                with p.budget(1):pass
        self.assertEqual(calls[0],(p.signal.ITIMER_REAL,1,0))
        self.assertEqual(calls[-1],(p.signal.ITIMER_REAL,0))


class DescriptorMeasurementTests(unittest.TestCase):
    def setUp(self):
        import snapshot_io
        self.io_module=snapshot_io
        self.temp=tempfile.TemporaryDirectory(prefix='predecessor-fd-',dir=str(HERE));self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        tx=self.root/claim.TRANSACTION.lstrip('/');tx.mkdir(parents=True);tx.chmod(0o700)
        (tx/'original.json').write_bytes(b'original protected evidence\n');(tx/'original.json').chmod(0o600)
        self.tx=tx
        policy={'directories':{},'transaction_inventory':{'original.json':p.sha((tx/'original.json').read_bytes())}}
        for name in ('/',)+factory.snap._predecessor_ancestors():
            actual=self.root if name=='/' else self.root/name.lstrip('/')
            info=actual.stat();policy['directories'][name]={'uid':0,'gid':0,'mode':info.st_mode&0o777}
        proxy=types.SimpleNamespace(**{name:getattr(os,name) for name in dir(os) if not name.startswith('__')})
        def path(value):return str(self.root/value.lstrip('/')) if isinstance(value,str) and value.startswith('/') else value
        proxy.open=lambda name,flags,*args,**kwargs:os.open(path(name),flags,*args,**kwargs)
        proxy.stat=lambda name,*args,**kwargs:mapped(os.stat(path(name),*args,**kwargs))
        proxy.lstat=lambda name,*args,**kwargs:mapped(os.lstat(path(name),*args,**kwargs))
        proxy.fstat=lambda fd:mapped(os.fstat(fd))
        self.scope=mock.patch.multiple(p,os=proxy);self.scope.start();self.addCleanup(self.scope.stop)
        for module in (entry,snapshot_io):
            patch=mock.patch.object(module,'os',proxy);patch.start();self.addCleanup(patch.stop)
        reader=snapshot_io.DescriptorReader(policy['directories'])
        historical=reader.directory(claim.TRANSACTION)
        self.private={'observation':{'policy':policy,'evidence':{'retained':{
            'transaction_inventory':{claim.TRANSACTION+'/original.json':policy['transaction_inventory']['original.json']},
            'transaction_directories':{claim.TRANSACTION:historical}}}}}
        state={'schema':1,'stage':'HOLD','failed_stage':'CLAIM_INTENT','failed_phase':'admission',
            'failed_operation':'create_inner_attempt','admission':'UNKNOWN','receipt_status':'OBSERVED',
            'completed':[],'phase_evidence':{},'containment':[],'containment_status':'NOT_ATTEMPTED',
            'secondary_errors':[],'interruption':None,'automatic_retry':False,'legacy_restart':False,
            'historical_notification_replay':False,'prerequisite_replay':False}
        binding={'review_id':claim.OLD_REVIEW_ID,'approval_body_sha256':claim.OLD_REVIEW_SHA256}
        raw=p.packed({'schema':1,'name':claim.OLD_OUTER,'transaction_id':claim.TX,
                      'context_sha256':'e'*64,'binding':binding,'state':state})
        (tx/claim.OLD_OUTER).write_bytes(raw);(tx/claim.OLD_OUTER).chmod(0o600)
        self.raw=raw
        self.pins=mock.patch.multiple(claim,PREDECESSOR_SHA256=p.sha(raw),PREDECESSOR_SIZE=len(raw),
            PREDECESSOR_BINDING_SHA256=claim.digest(binding),PREDECESSOR_STATE_SHA256=p.sha(p.packed(state)))
    def measure(self):return p.measure_predecessor(entry,self.private,time.monotonic()+30)
    def test_real_descriptor_measurement_and_final_ancestry(self):
        with self.pins: result=self.measure()
        self.assertEqual(result['measurement']['record']['metadata']['size'],len(self.raw))
        self.assertEqual(result['measurement']['record']['metadata']['ino'],(self.tx/claim.OLD_OUTER).stat().st_ino)
        self.assertEqual(set(result['transaction_inventory']),{claim.TRANSACTION+'/original.json',claim.TRANSACTION+'/'+claim.OLD_OUTER})
        self.assertTrue(result['measurement']['absent'][claim.OLD_INNER])
    def test_real_unmodified_predecessor_pin_rejects_synthetic_receipt(self):
        with self.assertRaisesRegex(ValueError,'PREDECESSOR_BYTES'):self.measure()
    def test_real_descriptor_rejects_old_inner_and_extra_child(self):
        for name in (claim.OLD_INNER,'unreviewed.json'):
            path=self.tx/name;path.write_bytes(b'exists');path.chmod(0o600)
            try:
                with self.pins,self.assertRaises((ValueError,p.Hold)):self.measure()
            finally:path.unlink()
    def test_real_descriptor_rejects_changed_original_bytes(self):
        (self.tx/'original.json').write_bytes(b'changed')
        with self.pins,self.assertRaises(p.Hold):self.measure()
    def test_real_descriptor_final_predecessor_reread_detects_drift(self):
        original=self.io_module.DescriptorReader.read;count=[0]
        def read(reader,name,*args,**kwargs):
            result=original(reader,name,*args,**kwargs)
            if name==claim.TRANSACTION+'/'+claim.OLD_OUTER:
                count[0]+=1
                if count[0]==2:(self.tx/claim.OLD_OUTER).write_bytes(self.raw+b' ')
            return result
        with self.pins,mock.patch.object(self.io_module.DescriptorReader,'read',read),self.assertRaises((ValueError,p.Hold)):
            self.measure()


if __name__=='__main__':unittest.main()
