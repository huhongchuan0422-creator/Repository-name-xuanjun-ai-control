"""Local successor preflight/collector/inner-gate integration, synthetic IO only.

Actual production AST methods are executed, including complete collect and
comparison plus FiniteLiveControls validation. OS descriptors, clocks, protected
IO, process observations, approval provenance, and command output are explicit
synthetic boundaries. No host modules, old suites, production filesystem, process
census, network, approval fetch, claim publication, or phases are executed.
"""
import ast
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_predecessor_snapshot as fixture

ROOT = pathlib.Path(__file__).resolve().parents[1]
d, snap, successor = fixture.d, fixture.c, fixture.cs
OWNER_PID = 4242


def source(name):
    candidate = ROOT / 'kit-overlay/helpers' / name
    if not candidate.exists(): candidate = ROOT / 'baseline/helpers' / name
    return ast.parse(candidate.read_text())


def selected(name, names, namespace, class_name=None):
    tree = source(name)
    if class_name:
        tree = next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==class_name)
    body = [copy.deepcopy(node) for node in tree.body
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names]
    assert {node.name for node in body}==set(names)
    module=ast.parse('');module.body=body;ast.fix_missing_locations(module)
    exec(compile(module,'<actual-production-ast:'+name+'>','exec'),namespace)
    return namespace


def pure_live_module():
    tree=source('epoch7_live_controls.py')
    tree.body=[node for node in tree.body if not (
        isinstance(node,ast.Import) and any(alias.name.startswith('epoch7_') for alias in node.names)
        or isinstance(node,ast.ImportFrom) and (node.module or '').startswith('epoch7_'))]
    seq_tree=source('epoch7_recovery_sequence.py')
    names={'PHASES','STOP_UNITS','CLEANUP','ADAPTER_BOUNDS','MAX_JOURNAL_BYTES'}
    seq_ns={}
    for node in seq_tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id in names for target in node.targets):
            part=ast.parse('');part.body=[copy.deepcopy(node)];ast.fix_missing_locations(part)
            exec(compile(part,'<actual-sequence-constants>','exec'),seq_ns)
    seq_ns.update(d=d,copy=copy)
    selected('epoch7_recovery_sequence.py',{'observation','check_observation'},seq_ns)
    seq_ns['need']=snap.need
    module=types.ModuleType('preflight_integration_live')
    module.__dict__.update(d=d,snap=snap,**{key:seq_ns[key] for key in names | {'observation','check_observation'}})
    ast.fix_missing_locations(tree)
    exec(compile(tree,'<actual-pure-live-controls>','exec'),module.__dict__)
    return module


live=pure_live_module()


def role(unit=None, uid=0):
    return {'uids':[uid]*4,'gids':[uid]*4,'groups':[uid], 'executable':'/usr/bin/synthetic',
        'executable_sha256':fixture.h('synthetic executable'), 'argv_sha256':fixture.h('synthetic argv'),'unit':unit}


def identity(pid, item):
    return dict(copy.deepcopy(item),pid=pid,starttime=1000+pid,comm='synthetic',kernel_thread=False)


def finite_process_contract(context, backend):
    manager={'pid':1,'uids':[0]*4,'starttime':1001,'boot_id':'11111111-1111-4111-8111-111111111111',
        'executable':'/usr/lib/systemd/systemd','executable_sha256':fixture.h('manager'),
        'channels_sha256':fixture.h('manager channels')}
    roles={unit:role(unit,1003 if unit=='xuanjun-ledger.service' else 1004)
           for unit in live.REQUIRED_ACTIVE if unit.endswith('.service')}
    ssh=role(None,1002);ssh['executable']='/usr/bin/ssh'
    rows={name:[{'path':'/synthetic/'+name,'version':0}] for name in live.SECTIONS}
    checkpoints=[];views=[]
    for index in range(len(live.PHASES)+1):
        if index:
            for section in live.MUTATIONS[live.PHASES[index-1]]:
                rows[section]=[{'path':'/synthetic/'+section,'version':index}]
        units={}
        for unit in snap.WRITER_UNITS:
            active=index>live.PHASES.index('activate_new_services') and unit in live.REQUIRED_ACTIVE
            if index==len(live.PHASES)-1 and unit==live.DEFERRED_TIMER:active=False
            properties={'Id':unit,'LoadState':'loaded','ActiveState':'active' if active else 'inactive',
                'SubState':'running' if active else 'dead','UnitFileState':'enabled' if active else 'disabled',
                'NeedDaemonReload':'no','ConditionResult':'no' if unit==snap.RUNNER else 'yes'}
            main=active and unit.endswith('.service')
            units[unit]={'properties':properties,'main_required':main,
                'main_role_sha256':live.digest(roles[unit]) if main else None}
        views.append(copy.deepcopy(rows))
        checkpoints.append({'resources':{key:live.digest(value) for key,value in rows.items()},'units':units})
    contract={'schema':1,'snapshot_sha256':context['snapshot_sha256'],
        'runtime_manifest_sha256':context['runtime_manifest_sha256'],'manager':manager,
        'checkpoints':checkpoints,'process_roles':list(roles.values())+[ssh],
        'database_identities':{name:{key:backend.meta[name][key] for key in ('dev','ino')} for name in snap.DATABASES},
        'database_sidecar_policy':copy.deepcopy(live.SIDECAR_POLICY),
        'retained_sidecar_pins':{name:None for name in live.RETAINED_SIDECAR_PATHS}}
    live.validate_contract(contract,context)
    return contract,views


def process_view(contract):
    point=contract['checkpoints'][0]
    observer=identity(OWNER_PID,role())
    manager=identity(1,dict(role(),executable=contract['manager']['executable'],
                            executable_sha256=contract['manager']['executable_sha256']))
    units={}
    for unit,policy in point['units'].items():
        state=dict(policy['properties'],MainPID=0,ControlPID=0,ControlGroup='')
        units[unit]={'before':state,'after':copy.deepcopy(state),'cgroup_present':False,'cgroups':{}}
    files={name:None for name in live.DATABASE_PATHS}
    for name,pin in contract['database_identities'].items():
        files[name]=dict(pin,kind='REGULAR',uid=0,gid=0,mode=0o600,nlink=1)
    return {'manager_before':copy.deepcopy(contract['manager']),'manager_after':copy.deepcopy(contract['manager']),
        'units':units,'pids_before':[1,OWNER_PID],'pids_after':[1,OWNER_PID],
        'processes':{'1':{'before':manager,'after':copy.deepcopy(manager)},
                     str(OWNER_PID):{'before':observer,'after':copy.deepcopy(observer)}},
        'database_fds':[],'database_files':files,'observer_pid':OWNER_PID}


class SuccessorPreflightIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.PredecessorSnapshotTests('test_new_mode_retains_actual_facts_and_bound_comparison_only_result')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;self.io=f.io;self.policy=f.policy
        # Production-shaped empty NSS/prerequisite inventories avoid all local
        # host lookups while traversing the real retained guard methods.
        plan=json.loads(self.io.raw[snap.PLAN].decode())
        plan['runtime']['prerequisites']={'groups':[],'users':{}}
        self.io.add(snap.PLAN,fixture.packed(plan))
        rpm_path=snap.TRANSACTION+'/rpm-prerequisites.json'
        self.io.add(rpm_path,fixture.packed({'packages':[]}))
        for name in (snap.PLAN,rpm_path):
            self.policy['files'][name]={key:self.io.meta[name][key] for key in ('sha256','uid','gid','mode')}
            if name.startswith(snap.TRANSACTION+'/'):
                self.policy['transaction_inventory'][name[len(snap.TRANSACTION)+1:]]=self.io.meta[name]['sha256']
        self.io.native_identity=lambda *args:{'components':{},'python_reference':None}
        self.io.prerequisites=lambda *args:{'identities':{},'directories':{},'binaries':{},'rpm_versions':{}}
        for unit,paths in self.policy['control_units'].items():
            for name in paths:
                if name not in self.io.raw and name not in snap.LEGACY_MASKS:
                    self.io.add(name,unit.encode())
        self.io.pins=copy.deepcopy(self.policy['directories'])
        raw=self.io.raw.pop(f.old_path);meta=self.io.meta.pop(f.old_path)
        parent=self.io.dirs[snap.TRANSACTION]
        self.io.dirs[snap.TRANSACTION]=copy.deepcopy(f.historical_evidence['retained']['transaction_directories'][snap.TRANSACTION])
        self.historical,self.support=snap.collect(self.policy,self.io)
        self.io.raw[f.old_path]=raw;self.io.meta[f.old_path]=meta;self.io.dirs[snap.TRANSACTION]=parent
        self.original=copy.deepcopy((self.historical,self.support,self.policy))
        measured=snap._read_predecessor(self.policy,self.io,f.contract)
        self.claim={'schema':1,'kind':'EXACT_CLAIM_ONLY_SUCCESSOR','predecessor':f.contract,
            'implementation':{'source_commit':'a'*40,'source_tree':'b'*40,'kit_manifest_sha256':fixture.h('synthetic kit')},
            'admission_expires_at_utc':'2099-01-01T00:00:00Z','authorized_successors':1,'automatic_retry':False,
            'effect_scope':'UNCHANGED_107_PAYLOADS_16_PHASES','measured_predecessor_sha256':d.digest(measured)}
        successor.validate_contract(self.claim)
        self.context={'context_sha256':fixture.h('synthetic successor context'),'snapshot_sha256':d.digest(self.historical),
            'runtime_manifest_sha256':d.OLD_MANIFEST,'adapter_bounds':copy.deepcopy(live.ADAPTER_BOUNDS),
            'claim_successor':copy.deepcopy(self.claim)}
        self.contract,self.views=finite_process_contract(self.context,self.io)
        self.closed=[];self.clock=types.SimpleNamespace(monotonic=lambda:100.0)
        self.fake_os=types.SimpleNamespace(fstat=lambda fd:('synthetic descriptor',fd),close=self.closed.append,
            getpid=lambda:OWNER_PID,path=os.path,O_ACCMODE=os.O_ACCMODE,O_RDONLY=os.O_RDONLY,O_PATH=getattr(os,'O_PATH',0))
        self.live_clock=mock.patch.object(live,'time',self.clock);self.live_clock.start();self.addCleanup(self.live_clock.stop)
        self.live_os=mock.patch.object(live,'os',self.fake_os);self.live_os.start();self.addCleanup(self.live_os.stop)
        backend=self.io
        class SyntheticLocalReadOnlyIO(fixture.FakeIO):
            def __init__(self,policy,locks):
                self.__dict__.update(backend.__dict__)
                self.deadline=130.0;self.policy=policy;self.pins=copy.deepcopy(policy['directories']);self.locks=locks
        read_module=types.ModuleType('snapshot_io');read_module.LocalReadOnlyIO=SyntheticLocalReadOnlyIO
        read_module.stamp=lambda value:value;read_module.PYTHON_REFERENCES=('/usr/bin/python3',)
        resources=types.ModuleType('epoch7_resource_observer')
        selected('epoch7_resource_observer.py',{'_resource_path','_resource_directories','resource_directories_digest'},
            resources.__dict__)
        resources.__dict__.update(d=d,need=snap.need,os=os,
            DIRECTORY_FIELDS={'uid','gid','mode','access_acl','default_acl'})
        recipe=types.ModuleType('epoch7_openclaw_recipe')
        recipe.DIRECT_WRAPPER_SHA=fixture.h('unused synthetic wrapper')
        recipe.LAUNCHER='/synthetic/unused';recipe.GATEWAY='xuanjun-uk-openclaw.service'
        scanner=types.ModuleType('reviewed_scanner');scanner.bounded_file_inventory=lambda *args,**kwargs:{}
        self.modules=mock.patch.dict(sys.modules,{'snapshot_io':read_module,'epoch7_live_controls':live,
            'epoch7_resource_observer':resources,'epoch7_openclaw_recipe':recipe,'reviewed_scanner':scanner})
        self.modules.start();self.addCleanup(self.modules.stop)
        namespace={'snap':snap,'d':d,'copy':copy,'need':snap.need,'sha':snap.sha,'time':self.clock,'os':self.fake_os}
        selected('epoch7_host_observer.py',{'immutable_snapshot'},namespace)
        methods={}
        selected('epoch7_host_observer.py',{'preflight','begin_guard','_bound','bind_plan','tls_contents'},
            namespace,'Epoch7HostObserver')
        for name in ('preflight','begin_guard','_bound','bind_plan','tls_contents'):methods[name]=namespace[name]
        self.Observer=type('ActualObserverMethodsWithSyntheticBoundaries',(object,),methods)
        self.observer=self.Observer();observer=self.observer
        observer.context=copy.deepcopy(self.context);observer.policy=copy.deepcopy(self.policy)
        observer.policy_sha=d.digest(self.policy);observer.reviewed_snapshot=copy.deepcopy(self.historical)
        observer.historical_evidence=copy.deepcopy(self.support);observer.historical_evidence_sha=d.digest(self.support)
        self.lock=types.SimpleNamespace(fd=81,is_held=True);self.lock.held=lambda:self.lock.is_held
        observer.lock=self.lock;observer.activation=types.SimpleNamespace(_locked=lambda:82)
        self.authority_calls=[]
        def receipt():
            self.authority_calls.append('receipt');snap.need(self.lock.held(),'SYNTHETIC_LOCK_REQUIRED')
        self.authority=types.SimpleNamespace(receipt=receipt,phase=lambda *args:receipt(),cleanup=lambda *args:receipt())
        observer.authority=self.authority
        directories={'/':[{'uid':0,'gid':0,'mode':0o755,'access_acl':'user::rwx\\ngroup::r-x\\nother::r-x\\n','default_acl':''}]}
        observer.resource_reader=types.SimpleNamespace(digest=fixture.h('all synthetic resource views'),
            views=self.views,reader=types.SimpleNamespace(directories=directories,guard_deadline=None))
        observer.census=types.SimpleNamespace(manager_pin=self.contract['manager'],database_identities=self.contract['database_identities'],
            retained_sidecars=self.contract['retained_sidecar_pins'],guard_deadline=None)
        observer.tls=types.SimpleNamespace(guard_deadline=None,contents=lambda:{key:self.historical['tls'][key]
            for key in ('certificate_sha256','tree_fingerprint_sha256')})
        observer.bound_plan=None;observer.live_contract=None;observer.guard_deadline=None
        observer.driver_gate=None;observer.quiet=None
        self.process_mutator=None
        def processes(context,phase,boundary):
            snap.need(context==self.context and phase=='stage_exact_release','SYNTHETIC_PROCESS_SCOPE')
            value=process_view(self.contract)
            if self.process_mutator:self.process_mutator(value)
            return value
        observer.processes=processes;observer.resources=lambda *args:{};observer.unit=lambda *args:{}
        plan={'live_controls':self.contract,'resource_observer':{'views_sha256':observer.resource_reader.digest,
            'directories_sha256':resources.resource_directories_digest(directories),'snapshot_policy_sha256':observer.policy_sha}}
        raw_plan=live.canonical(plan)
        self.verifier=types.SimpleNamespace(_bound=lambda:None,context=self.context,
            wanted={'recovery_plan_sha256':snap.sha(raw_plan)})
        self.controls=live.FiniteLiveControls(raw_plan,self.context,self.verifier,self.lock,self.authority,observer)
        self.Guards,self.Gate=self.actual_inner_classes()

    def actual_inner_classes(self):
        namespace={'snap':snap,'d':d,'copy':copy,'need':snap.need,'sha':snap.sha,'time':self.clock,'os':self.fake_os,
            'validate_cleanup_process_view':live.validate_cleanup_process_view,
            'STABLE_DIR':{'path','kind','uid','gid','mode','dev','ino','access_acl','default_acl'},
            'PYTHON_REFERENCES':('/usr/bin/python3',)}
        names={'install_lock_held','_check','_phase','_preserved_file','_native_python_reference','_native_node_reference',
            '_prerequisites','read_preserved_pins','read_activation_evidence','read_generation','read_sandbox',
            'read_targets','read_writer_exclusion'}
        selected('epoch7_pre_active_guards.py',names,namespace,'PreActiveGateGuards')
        guards=type('ActualPreActiveMethodsWithSyntheticBoundaries',(object,),{name:namespace[name] for name in names})
        gate_ns={'d':d,'copy':copy};selected('epoch7_injected_recovery.py',{'check'},gate_ns,'RecoveryGate')
        gate=type('ActualGateCheckWithSyntheticBindings',(object,),{'check':gate_ns['check']})
        return guards,gate

    def inner_gate(self):
        guard=self.Guards();gate=self.Gate()
        guard.observer=self.observer;guard.authority=self.authority;guard.controls=self.controls
        guard.io=self.io;guard.deadline=None;guard.diagnostics=types.SimpleNamespace(scope='admission')
        guard.gate=gate
        guard.core=types.SimpleNamespace(store=types.SimpleNamespace(read=lambda:copy.deepcopy(self.historical['activation'])),
            native_before=self.io.raw[snap.NATIVE],native_after=b'unused')
        def mask(name):return copy.deepcopy(self.io.writer['masks'][name])
        self.io.mask=mask
        guard.retained_io=types.SimpleNamespace(read_generation=lambda:copy.deepcopy(self.historical['generation']),
            read_target=lambda name:copy.deepcopy(self.historical['targets'][name]))
        def command(label,args):
            snap.need(label=='systemctl_inventory' and args==['list-unit-files','--no-legend','--no-pager'],
                      'SYNTHETIC_EXACT_SYSTEMCTL_BOUNDARY')
            return ('\n'.join(sorted(self.policy['control_units']))+'\n').encode()
        guard._command=command
        gate.snapshot=copy.deepcopy(self.historical);gate.snapshot_sha256=d.digest(gate.snapshot)
        gate.candidate={'activation':dict(self.historical['activation'],epoch=8)};gate.candidate_sha256=d.digest(gate.candidate)
        gate.delta={'preserve':{'retained_resource_sha256':self.historical['retained_resource_sha256']}}
        gate.delta_sha256=d.digest(gate.delta);gate.preserved=copy.deepcopy(gate.delta['preserve'])
        gate.expected={'synthetic_exact_review':True,'claim_successor':self.claim};gate.expected_sha256=d.digest(gate.expected)
        gate.additions=[];gate.additions_sha256=d.digest([]);gate.review_id=7000000001;gate.authorization=None
        gate.current_generation=copy.deepcopy(self.historical['generation']);gate.current_targets=copy.deepcopy(self.historical['targets'])
        gate.current_additive_targets={};gate.guards=guard
        gate.verifier=types.SimpleNamespace(verify_exact=lambda review_id,expected:{'review_id':review_id,
            'body_sha256':fixture.h('synthetic authenticated review boundary'),'binding':copy.deepcopy(expected)})
        return gate,guard

    def test_actual_observer_collector_controls_and_inner_gate_close_both_hashes(self):
        result=self.controls.preflight(self.context)
        self.assertEqual(result['status'],'OBSERVED')
        support=self.observer.fresh_evidence
        self.assertEqual(support['live_snapshot']['schema'],2)
        self.assertFalse(support['live_snapshot']['absent_paths'][successor.OLD_OUTER])
        self.assertIn(self.fixture.old_path,support['live_evidence']['retained']['transaction_inventory'])
        self.assertNotEqual(d.digest(support['live_evidence']['retained']),self.historical['retained_resource_sha256'])
        self.assertEqual(result['evidence_sha256'],d.digest(support))
        self.assertEqual(support['reconciliation']['measured_predecessor_sha256'],self.claim['measured_predecessor_sha256'])
        gate,guard=self.inner_gate()
        result=gate.check()
        self.assertEqual(result['review_id'],gate.review_id)
        self.assertEqual(guard.read_preserved_pins(),gate.delta['preserve'])
        self.assertEqual((self.historical,self.support,self.policy),self.original)
        self.assertEqual(self.closed,[82])

    def test_changed_approved_predecessor_fails_actual_observer(self):
        self.context['claim_successor']['measured_predecessor_sha256']='f'*64
        self.observer.context=copy.deepcopy(self.context)
        self.observer.begin_guard(130.0)
        with self.assertRaisesRegex(ValueError,'APPROVED_PREDECESSOR'):
            self.observer.preflight(self.context)
        self.assertEqual(self.closed,[82])

    def test_extra_old_transaction_child_fails_actual_collector(self):
        self.io.add(snap.TRANSACTION+'/epoch7-unreviewed-old-child.json',b'{}\\n')
        with self.assertRaisesRegex(ValueError,'TRANSACTION_INVENTORY_CHANGED'):
            self.controls.preflight(self.context)
        self.assertEqual(self.closed,[82])

    def test_old_inner_and_fixed_successors_refuse_actual_preflight(self):
        for name in (successor.OLD_INNER,successor.NEW_OUTER,successor.NEW_INNER):
            with self.subTest(name=name):
                path=snap.TRANSACTION+'/'+name;self.io.present.add(path)
                with self.assertRaisesRegex(ValueError,'PREDECESSOR_FIXED_ABSENCES'):
                    self.controls.preflight(self.context)
                self.io.present.remove(path)

    def test_nonparent_directory_stamp_and_old_file_stamp_drift_refuse(self):
        child=next(name for name in self.io.dirs if name.startswith(snap.TRANSACTION+'/'))
        self.io.dirs[child]['mtime_ns']+=1
        with self.assertRaisesRegex(ValueError,'OTHER_DIRECTORY_DRIFT'):
            self.controls.preflight(self.context)
        self.io.dirs[child]['mtime_ns']-=1;self.io.meta[snap.ACTIVE]['mtime_ns']+=1
        with self.assertRaisesRegex(ValueError,'ORIGINAL_RETAINED_DRIFT'):
            self.controls.preflight(self.context)

    def test_actual_process_validator_rejects_unknown_and_changed_process(self):
        self.process_mutator=lambda value:value['pids_after'].append(9999)
        with self.assertRaisesRegex(ValueError,'PROCESS_CENSUS_RACE_OR_BOUND'):
            self.controls.preflight(self.context)
        self.assertEqual(self.closed,[82])

    def test_actual_controls_revalidate_observer_returned_proof(self):
        original=self.observer.preflight
        def preflight(context):
            historical,evidence=original(context)
            evidence['live_evidence']['retained']['predecessor']['record']['metadata']['mtime_ns']+=1
            return historical,evidence
        self.observer.preflight=preflight
        with self.assertRaisesRegex(ValueError,'EVIDENCE_BINDING|RETAINED_BINDING'):
            self.controls.preflight(self.context)

    def test_actual_controls_reject_rehashed_measurement_without_new_approval(self):
        original=self.observer.preflight
        def preflight(context):
            historical,evidence=original(context)
            raw=evidence['live_evidence'];current=evidence['live_snapshot']
            raw['retained']['predecessor']['record']['metadata']['mtime_ns']+=1
            current['retained_resource_sha256']=d.digest(raw['retained']);raw['snapshot_sha256']=d.digest(current)
            evidence['reconciliation']=snap.validate_predecessor_collection(current,raw,self.policy,
                historical,self.support,self.claim['predecessor'])
            return historical,evidence
        self.observer.preflight=preflight
        with self.assertRaisesRegex(ValueError,'SUCCESSOR_RECONCILIATION_BINDING'):
            self.controls.preflight(self.context)

    def test_inner_gate_rejects_tampered_live_proof_after_controls(self):
        self.controls.preflight(self.context)
        gate,guard=self.inner_gate()
        self.observer.fresh_evidence['live_evidence']['retained']['predecessor']['record']['metadata']['mtime_ns']+=1
        with self.assertRaisesRegex(ValueError,'PREDECESSOR_RETAINED_BINDING'):gate.check()

    def test_inner_gate_rejects_tampered_comparison_after_controls(self):
        self.controls.preflight(self.context)
        gate,guard=self.inner_gate()
        self.observer.fresh_evidence['reconciliation']['comparison_only_snapshot']['receipts']['bootstrap-files.json']='f'*64
        with self.assertRaisesRegex(ValueError,'INNER_SUCCESSOR_LIVE_EVIDENCE_MUTATED'):gate.check()

    def test_inner_gate_uses_original_support_not_live_retained_as_original(self):
        self.controls.preflight(self.context)
        gate,guard=self.inner_gate()
        self.observer.historical_evidence['retained']=copy.deepcopy(self.observer.fresh_evidence['live_evidence']['retained'])
        with self.assertRaisesRegex(ValueError,'PREDECESSOR_HISTORICAL_BINDING|INNER_FRESH_SNAPSHOT_BINDING'):
            gate.check()


if __name__=='__main__':unittest.main()
