"""Finite guard fixtures only; no live host process or filesystem observations."""
import copy
import hashlib
import os
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent/'snapshot-candidate'),
    str(HERE.parent/'recovery-design-candidate'), str(HERE.parent/'diagnostics-candidate')]
import epoch7_live_controls as live
import epoch7_recovery_sequence as sequence
from test_epoch7_recovery_sequence import Rig, h


def identity(pid, role, kernel_thread=False):
    return dict(copy.deepcopy(role), pid=pid, starttime=1000+pid, comm='synthetic', kernel_thread=kernel_thread)


def role(unit=None, uid=0):
    return {'uids':[uid]*4, 'gids':[uid]*4, 'groups':[uid], 'executable':'/usr/bin/synthetic',
            'executable_sha256':h('fixture executable'), 'argv_sha256':h('fixture argv'), 'unit':unit}


def fixture():
    rig = Rig(); context = rig.driver.context
    manager = {'pid':1,'uids':[0]*4,'starttime':1001,
        'boot_id':'11111111-1111-4111-8111-111111111111',
        'executable':'/usr/lib/systemd/systemd','executable_sha256':h('manager'),'channels_sha256':h('channels')}
    roles = {u:role(u, 1003 if u == 'xuanjun-ledger.service' else 1004)
             for u in live.REQUIRED_ACTIVE if u.endswith('.service')}
    ssh = role(None,1002); ssh['executable']='/usr/bin/ssh'
    values = {name:{'section':name,'version':0} for name in live.SECTIONS}
    checkpoints, views = [], []
    for index in range(len(sequence.PHASES)+1):
        if index:
            for section in live.MUTATIONS[sequence.PHASES[index-1]]:
                values[section] = {'section':section,'version':index}
        units = {}
        for unit in live.snap.WRITER_UNITS:
            active = index > sequence.PHASES.index('activate_new_services') and unit in live.REQUIRED_ACTIVE
            if index == len(sequence.PHASES)-1 and unit == live.DEFERRED_TIMER: active = False
            props = {'Id':unit,'LoadState':'loaded','ActiveState':'active' if active else 'inactive',
                'SubState':'running' if active else 'dead','UnitFileState':'enabled' if active else 'disabled',
                'NeedDaemonReload':'no','ConditionResult':'no' if unit == live.snap.RUNNER else 'yes'}
            main = active and unit.endswith('.service')
            units[unit] = {'properties':props,'main_required':main,
                          'main_role_sha256':live.digest(roles[unit]) if main else None}
        views.append(copy.deepcopy(values))
        checkpoints.append({'resources':{k:live.digest(v) for k,v in values.items()},'units':units})
    contract = {'schema':1,'snapshot_sha256':context['snapshot_sha256'],
        'runtime_manifest_sha256':context['runtime_manifest_sha256'], 'manager':manager,
        'checkpoints':checkpoints,'process_roles':list(roles.values())+[ssh],
        'database_identities':{p:{'dev':1,'ino':n+20} for n,p in enumerate(live.snap.DATABASES)},
        'database_sidecar_policy':copy.deepcopy(live.SIDECAR_POLICY),
        'retained_sidecar_pins':{p:None for p in live.RETAINED_SIDECAR_PATHS}}
    return rig, context, contract, views


def process_view(contract, index, observer_pid=None):
    observer_pid = observer_pid or os.getpid()
    point = contract['checkpoints'][index]
    by_hash = {live.digest(r):r for r in contract['process_roles']}
    observer = identity(observer_pid, role())
    manager = identity(1, dict(role(), executable=contract['manager']['executable'],
                              executable_sha256=contract['manager']['executable_sha256']))
    rows = {'1':{'before':manager,'after':copy.deepcopy(manager)},
            str(observer_pid):{'before':observer,'after':copy.deepcopy(observer)}}
    units = {}
    for number,(unit,policy) in enumerate(sorted(point['units'].items()),1):
        main = observer_pid+100+number if policy['main_required'] else 0
        state = dict(policy['properties'], MainPID=main, ControlPID=0,
                     ControlGroup='/system.slice/'+unit if main else '')
        groups = {}
        if main:
            groups['/sys/fs/cgroup/systemd/system.slice/'+unit+'/cgroup.procs']=[main]
            item = identity(main,by_hash[policy['main_role_sha256']])
            rows[str(main)]={'before':item,'after':copy.deepcopy(item)}
        units[unit]={'before':state,'after':copy.deepcopy(state),'cgroup_present':bool(main),'cgroups':groups}
    pids = sorted(int(p) for p in rows)
    files = {path:None for path in live.DATABASE_PATHS}
    for path,pin in contract['database_identities'].items():
        files[path] = dict(pin,kind='REGULAR',uid=0,gid=0,mode=0o600,nlink=1)
    files.update(copy.deepcopy(contract['retained_sidecar_pins']))
    return {'manager_before':copy.deepcopy(contract['manager']), 'manager_after':copy.deepcopy(contract['manager']),
        'units':units,'pids_before':pids,'pids_after':list(pids),'processes':rows,'database_fds':[],
        'database_files':files,'observer_pid':observer_pid}


class Lock(object):
    def __init__(self): self.is_held=True
    def held(self): return self.is_held


class Verifier(object):
    def __init__(self,raw,context): self.wanted={'recovery_plan_sha256':hashlib.sha256(raw).hexdigest()};self.context=context
    def _bound(self): pass
    def verify_outer_review(self,context): return sequence.observation(context,'verify_outer_review',h('authenticated fixture'))


class Authority(object):
    def __init__(self,lock): self.lock=lock;self.current=None;self.calls=[];self.admitted=True
    def receipt(self):
        if not self.lock.held(): raise ValueError('fixture lock unavailable')
    def phase(self,phase):
        self.receipt(); self.calls.append(phase)
        if phase != self.current: raise ValueError('fixture INTENT mismatch')
    def cleanup(self,operation,unit):
        self.receipt()
        if (operation,unit) not in sequence.CLEANUP or not self.admitted:
            raise ValueError('fixture exact ADMITTED claim required')


class Observer(object):
    def __init__(self,rig,context,contract,views):
        self.rig,self.context,self.contract,self.views=rig,context,contract,views
        self.resource_mutator=None;self.process_mutator=None;self.unit_result=None;self.resources_calls=[]
        self.deadlines=[]
    def bind_plan(self,plan):
        self.bound_plan=copy.deepcopy(plan)
        return True
    def begin_guard(self,deadline):self.deadlines.append(deadline)
    def preflight(self,context):
        raise ValueError('fixture preflight missing real supporting snapshot')
    def resources(self,context,phase,boundary,names):
        index=sequence.PHASES.index(phase)+(1 if boundary=='after' else 0)
        values={k:copy.deepcopy(self.views[index][k]) for k in names}
        self.resources_calls.append((phase,boundary,tuple(names)))
        if self.resource_mutator:self.resource_mutator(values,phase,boundary)
        return values
    def processes(self,context,phase,boundary):
        index=sequence.PHASES.index(phase)+(1 if boundary=='after' else 0)
        value=process_view(self.contract,index)
        if self.process_mutator:self.process_mutator(value,phase,boundary)
        return value
    def unit(self,context,operation,unit):
        return copy.deepcopy(self.unit_result or process_view(self.contract,0)['units'][unit])
    def tls_contents(self,context):
        return {'certificate_sha256':context['tls_change']['certificate_sha256'],
                'tree_fingerprint_sha256':h('measured fixture tree')}


def controls():
    rig,context,contract,views=fixture()
    raw=live.canonical({'live_controls':contract})
    lock=Lock();verifier=Verifier(raw,context);authority=Authority(lock)
    observer=Observer(rig,context,contract,views)
    control=live.FiniteLiveControls(raw,context,verifier,lock,authority,observer)
    return control,observer,authority,contract,context


class ContractTests(unittest.TestCase):
    def test_complete_finite_contract_accepted(self):
        unused,context,contract,unused=fixture()
        self.assertEqual(live.validate_contract(contract,context),contract)

    def test_every_unrelated_resource_change_rejected(self):
        unused,context,contract,unused=fixture()
        for index,phase in enumerate(sequence.PHASES):
            for section in live.SECTIONS-live.MUTATIONS[phase]:
                with self.subTest(phase=phase,section=section):
                    bad=copy.deepcopy(contract);bad['checkpoints'][index+1]['resources'][section]=h('drift')
                    with self.assertRaisesRegex(ValueError,'CROSS_PHASE'):
                        live.validate_contract(bad,context)

    def test_missing_extra_or_reordered_checkpoints_not_adopted(self):
        for mode in ('missing','extra','reordered'):
            unused,context,contract,unused=fixture()
            if mode=='missing':contract['checkpoints'].pop()
            elif mode=='extra':contract['checkpoints'].append(copy.deepcopy(contract['checkpoints'][-1]))
            else:contract['checkpoints'][2],contract['checkpoints'][7]=contract['checkpoints'][7],contract['checkpoints'][2]
            with self.assertRaises(ValueError):live.validate_contract(contract,context)

    def test_active_service_before_activation_refused(self):
        unused,context,contract,unused=fixture()
        contract['checkpoints'][4]['units']['xuanjun-ledger.service']=copy.deepcopy(
            contract['checkpoints'][15]['units']['xuanjun-ledger.service'])
        with self.assertRaisesRegex(ValueError,'PREMATURE'):live.validate_contract(contract,context)

    def test_all_required_final_services_must_be_active(self):
        unused,context,contract,unused=fixture()
        contract['checkpoints'][15]['units']['xuanjun-ledger.service']=copy.deepcopy(
            contract['checkpoints'][0]['units']['xuanjun-ledger.service'])
        with self.assertRaisesRegex(ValueError,'FINAL_ACTIVE'):live.validate_contract(contract,context)

    def test_unknown_background_or_main_role_refused(self):
        for mutation in ('background','main'):
            unused,context,contract,unused=fixture()
            if mutation=='background':contract['process_roles'][-1]['executable']='/usr/bin/bash'
            else:contract['checkpoints'][15]['units']['xuanjun-ledger.service']['main_role_sha256']=h('not reviewed')
            with self.assertRaises(ValueError):live.validate_contract(contract,context)

    def test_exact_plan_hash_and_observer_are_required(self):
        rig,context,contract,views=fixture();raw=live.canonical({'live_controls':contract})
        lock=Lock();verifier=Verifier(raw,context);authority=Authority(lock)
        with self.assertRaisesRegex(ValueError,'OBSERVER'):
            live.FiniteLiveControls(raw,context,verifier,lock,authority,None)
        with self.assertRaisesRegex(ValueError,'RAW_HASH'):
            live.FiniteLiveControls(raw+b' ',context,verifier,lock,authority,Observer(rig,context,contract,views))

    def test_sidecar_policy_must_be_explicit_exact_and_signed(self):
        for defect in ('missing','mode','path','bool'):
            unused,context,contract,unused=fixture()
            if defect=='missing':del contract['database_sidecar_policy']
            elif defect=='mode':contract['database_sidecar_policy']['mode']=0o660
            elif defect=='path':contract['database_sidecar_policy']['paths'].append('/tmp/other')
            else:contract['database_sidecar_policy']['nlink']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):live.validate_contract(contract,context)

    def test_access_phase_tracks_client_and_release_parent_acl_sections(self):
        self.assertEqual(live.MUTATIONS['apply_reviewed_access'],{'access','targets','release'})

    def test_rebind_phase_tracks_exact_tls_candidate_publication(self):
        self.assertEqual(live.MUTATIONS['rebind_prepared_epoch'],{'activation','native','tls'})

    def test_retained_timer_stays_inactive_until_final_checkpoint(self):
        unused,context,contract,unused=fixture();unit=live.DEFERRED_TIMER
        self.assertEqual(contract['checkpoints'][15]['units'][unit]['properties']['ActiveState'],'inactive')
        self.assertEqual(contract['checkpoints'][16]['units'][unit]['properties']['ActiveState'],'active')
        self.assertEqual(live.MUTATIONS['post_install_checks'],{'boot'})
        contract['checkpoints'][15]['units'][unit]=copy.deepcopy(contract['checkpoints'][16]['units'][unit])
        with self.assertRaisesRegex(ValueError,'FINAL_ACTIVE'):live.validate_contract(contract,context)


class ProcessTests(unittest.TestCase):
    def setUp(self):
        unused,self.context,self.contract,unused=fixture()
    def validate(self,value,index=15,allow=False):
        return live.validate_process_view(value,self.contract,self.contract['checkpoints'][index],os.getpid(),allow)
    def test_exact_stopped_and_active_census(self):
        for index in (0,14,15,16):self.validate(process_view(self.contract,index),index)
    def test_is_active_only_cannot_prove_stopped(self):
        with self.assertRaisesRegex(ValueError,'SCHEMA'):
            live.validate_unit_row('xuanjun-ledger.service',{'inactive_observed':True},stopped=True)
    def test_stop_requires_pid_zero_and_empty_nested_cgroup(self):
        for defect in ('pid','cgroup','missing_pid','race'):
            row=process_view(self.contract,0)['units']['xuanjun-ledger.service']
            if defect=='pid':row['before']['MainPID']=row['after']['MainPID']=72
            elif defect=='cgroup':
                row['cgroup_present']=True
                root='/sys/fs/cgroup/systemd/system.slice/xuanjun-ledger.service'
                row['cgroups']={root+'/cgroup.procs':[],root+'/child/cgroup.procs':[72]}
            elif defect=='missing_pid':row['before'].pop('MainPID');row['after'].pop('MainPID')
            else:row['after']['MainPID']=72
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                live.validate_unit_row('xuanjun-ledger.service',row,stopped=True)
    def test_unreviewed_executable_argv_groups_and_uid_refused(self):
        for key,value in (('executable','/tmp/other'),('argv_sha256',h('changed')),
            ('groups',[1003,9999]),('uids',[0]*4)):
            measured=process_view(self.contract,15)
            pid=measured['units']['xuanjun-ledger.service']['before']['MainPID']
            measured['processes'][str(pid)]['before'][key]=copy.deepcopy(value)
            measured['processes'][str(pid)]['after'][key]=copy.deepcopy(value)
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(measured)
    def test_pid_reuse_process_census_and_manager_changes_refused(self):
        for defect in ('pid_reuse','new_pid','manager','missing_manager','missing_observer'):
            value=process_view(self.contract,15)
            if defect=='pid_reuse':value['processes']['1']['after']['starttime']+=1
            elif defect=='new_pid':value['pids_after'].append(999999)
            elif defect=='manager':value['manager_after']['starttime']+=1
            else:
                pid=1 if defect=='missing_manager' else os.getpid()
                del value['processes'][str(pid)]
                value['pids_before'].remove(pid);value['pids_after'].remove(pid)
            with self.subTest(defect=defect),self.assertRaises(ValueError):self.validate(value)
    def test_unit_main_process_must_match_approved_main_role(self):
        value=process_view(self.contract,15);unit='xuanjun-ledger.service'
        pid=value['units'][unit]['before']['MainPID']
        extra=copy.deepcopy(next(r for r in self.contract['process_roles'] if r['unit']==unit))
        extra['argv_sha256']=h('approved child but not main');self.contract['process_roles'].append(extra)
        for side in ('before','after'):value['processes'][str(pid)][side]['argv_sha256']=extra['argv_sha256']
        with self.assertRaisesRegex(ValueError,'MAIN_PROCESS'):self.validate(value)
    def test_unknown_writer_or_runner_never_hidden_in_normal_census(self):
        for defect in ('writer','runner'):
            value=process_view(self.contract,15);pid=os.getpid()+9000
            item=identity(pid,role(uid=1003 if defect=='writer' else 0))
            if defect=='runner':item['comm']='Runner.Listener'
            value['processes'][str(pid)]={'before':item,'after':copy.deepcopy(item)}
            value['pids_before']=value['pids_after']=sorted(int(p) for p in value['processes'])
            with self.subTest(defect=defect),self.assertRaises(ValueError):self.validate(value)
    def test_kernel_thread_is_explicit_root_empty_argv_no_fake_executable(self):
        value=process_view(self.contract,0)
        pid=max(int(key) for key in value['processes'])+100
        item=identity(pid,dict(role(),executable=None,executable_sha256=None,
                            argv_sha256=hashlib.sha256(b'').hexdigest()),True)
        value['processes'][str(pid)]={'before':item,'after':copy.deepcopy(item)}
        value['pids_before']=value['pids_after']=sorted(int(p) for p in value['processes'])
        self.validate(value,0)
        for key,bad in (('kernel_thread',False),('executable','/fake-kernel'),('uids',[1002]*4),('argv_sha256',h('nonempty'))):
            changed=copy.deepcopy(value)
            for side in ('before','after'):changed['processes'][str(pid)][side][key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(changed,0)
    def test_only_active_ledger_may_hold_generation_database(self):
        value=process_view(self.contract,15)
        pid=value['units']['xuanjun-ledger.service']['before']['MainPID']
        row=dict(self.contract['database_identities'][live.d.DB],pid=pid,fd=7,path=live.d.DB,
                 storage_path=live.d.DB,flags=os.O_RDWR)
        value['database_fds']=[row];self.validate(value)
        for path in live.snap.DATABASES:
            if path==live.d.DB:continue
            bad=copy.deepcopy(value);bad['database_fds'][0].update(self.contract['database_identities'][path],
                                                                 path=path,storage_path=path)
            with self.assertRaisesRegex(ValueError,'UNAUTHORIZED'):self.validate(bad)
    def test_observer_db_fd_allowed_only_explicit_reopen_readonly_scope(self):
        value=process_view(self.contract,11)
        value['database_fds']=[dict(self.contract['database_identities'][live.d.DB],
            pid=os.getpid(),fd=8,path=live.d.DB,storage_path=live.d.DB,flags=os.O_RDONLY)]
        with self.assertRaises(ValueError):self.validate(value,11)
        self.validate(value,11,True)
        value['database_fds'][0]['flags']=os.O_RDWR
        with self.assertRaisesRegex(ValueError,'OBSERVER_DATABASE'):self.validate(value,11,True)

    def test_exact_canonical_sidecars_accepted_only_for_active_ledger(self):
        value=process_view(self.contract,15)
        pid=value['units']['xuanjun-ledger.service']['before']['MainPID']
        for number,suffix in enumerate(live.DATABASE_SUFFIXES):
            path=live.d.DB+suffix
            row={'kind':'REGULAR','dev':1,'ino':100+number,'uid':1003,'gid':1006,'mode':0o600,'nlink':1}
            value['database_files'][path]=row
            value['database_fds'].append({'pid':pid,'fd':10+number,'path':live.d.DB,'storage_path':path,
                                         'dev':1,'ino':row['ino'],'flags':os.O_RDWR})
        self.validate(value)
        stopped=process_view(self.contract,14);stopped['database_files']=value['database_files']
        with self.assertRaisesRegex(ValueError,'SIDECAR'):self.validate(stopped,14)

    def test_sidecar_metadata_path_or_fd_identity_drift_refused(self):
        for defect in ('owner','group','mode','hardlink','symlink','unknown_path','source','rollback',
                       'fd_inode','missing_file','duplicate_fd','nonledger_holder'):
            value=process_view(self.contract,15);path=live.d.DB+'-wal'
            row={'kind':'REGULAR','dev':1,'ino':100,'uid':1003,'gid':1006,'mode':0o600,'nlink':1}
            value['database_files'][path]=row
            pid=value['units']['xuanjun-ledger.service']['before']['MainPID']
            value['database_fds']=[{'pid':pid,'fd':7,'path':live.d.DB,'storage_path':path,
                                    'dev':1,'ino':100,'flags':os.O_RDWR}]
            if defect=='owner':row['uid']=0
            elif defect=='group':row['gid']=1003
            elif defect=='mode':row['mode']=0o660
            elif defect=='hardlink':row['nlink']=2
            elif defect=='symlink':row['kind']='SYMLINK'
            elif defect=='unknown_path':value['database_files'][live.d.DB+'-other']=row
            elif defect in ('source','rollback'):
                target=live.snap.SOURCE_DB if defect=='source' else live.snap.ROLLBACK_DB
                value['database_files'][target+'-wal']=row
                value['database_files'][path]=None
            elif defect=='fd_inode':value['database_fds'][0]['ino']=101
            elif defect=='missing_file':value['database_files'][path]=None
            elif defect=='duplicate_fd':value['database_fds'].append(copy.deepcopy(value['database_fds'][0]))
            else:value['database_fds'][0]['pid']=os.getpid()
            with self.subTest(defect=defect),self.assertRaises(ValueError):self.validate(value)

    def test_base_identity_or_incomplete_file_census_refused(self):
        for defect in ('base_absent','changed_inode','alias','missing_suffix'):
            value=process_view(self.contract,15)
            if defect=='base_absent':value['database_files'][live.d.DB]=None
            elif defect=='changed_inode':value['database_files'][live.d.DB]['ino']+=100
            elif defect=='alias':value['database_files'][live.d.DB+'-wal']=copy.deepcopy(value['database_files'][live.d.DB])
            else:del value['database_files'][live.d.DB+'-shm']
            with self.subTest(defect=defect),self.assertRaises(ValueError):self.validate(value)

    def test_retained_cold_sidecars_require_exact_measured_pins_and_no_holders(self):
        path=live.snap.SOURCE_DB+'-shm'
        pin={'kind':'REGULAR','dev':1,'ino':500,'uid':1002,'gid':1002,'mode':0o600,'nlink':1,
             'size':32768,'mtime_ns':1,'ctime_ns':2,'sha256':h('measured cold shm')}
        self.contract['retained_sidecar_pins'][path]=pin
        value=process_view(self.contract,15);self.validate(value)
        live.validate_contract(self.contract,self.context)
        for defect in ('hash','size','mode','inode','absence','holder'):
            changed=copy.deepcopy(value)
            if defect=='hash':changed['database_files'][path]['sha256']=h('changed')
            elif defect=='size':changed['database_files'][path]['size']+=1
            elif defect=='mode':changed['database_files'][path]['mode']=0o644
            elif defect=='inode':changed['database_files'][path]['ino']+=1
            elif defect=='absence':changed['database_files'][path]=None
            else:
                pid=changed['units']['xuanjun-ledger.service']['before']['MainPID']
                changed['database_fds']=[dict(pid=pid,fd=9,path=live.snap.SOURCE_DB,storage_path=path,
                                             dev=1,ino=500,flags=os.O_RDONLY)]
            with self.subTest(defect=defect),self.assertRaises(ValueError):self.validate(changed)

    def test_cleanup_keeps_exact_background_identity_and_empty_fds(self):
        value=process_view(self.contract,0);pid=os.getpid()+9000
        ssh=next(r for r in self.contract['process_roles'] if r['unit'] is None)
        item=identity(pid,ssh);value['processes'][str(pid)]={'before':item,'after':copy.deepcopy(item)}
        value['pids_before']=value['pids_after']=sorted(int(p) for p in value['processes'])
        value['database_files'][live.d.DB+'-wal']={'kind':'REGULAR','dev':1,'ino':100,
                                                'uid':1003,'gid':1006,'mode':0o600,'nlink':1}
        live.validate_cleanup_process_view(value,self.contract,os.getpid())
        for defect in ('argv','groups','executable','fd','runner'):
            changed=copy.deepcopy(value)
            if defect in ('argv','groups','executable'):
                key={'argv':'argv_sha256','groups':'groups','executable':'executable_sha256'}[defect]
                bad=[1002,1006] if defect=='groups' else h('changed')
                for side in ('before','after'):changed['processes'][str(pid)][side][key]=bad
            elif defect=='fd':changed['database_fds']=[{'unproved':True}]
            else:
                for side in ('before','after'):changed['units'][live.snap.RUNNER][side]['ConditionResult']='yes'
            with self.subTest(defect=defect),self.assertRaises(ValueError):
                live.validate_cleanup_process_view(changed,self.contract,os.getpid())

    def test_cleanup_still_rejects_active_or_missing_census(self):
        with self.assertRaises(ValueError):
            live.validate_cleanup_process_view(process_view(self.contract,15),self.contract,os.getpid())
        value=process_view(self.contract,0);value['pids_after'].append(os.getpid()+9999)
        with self.assertRaises(ValueError):live.validate_cleanup_process_view(value,self.contract,os.getpid())


class ControlsTests(unittest.TestCase):
    def _preflight_fixture(self):
        rig,context,contract,views=fixture();snapshot=copy.deepcopy(rig.gate.snapshot)
        retained={'fixture':'protected retained evidence'}
        snapshot['retained_resource_sha256']=live.digest(retained)
        context['snapshot_sha256']=live.digest(snapshot)
        context.pop('context_sha256');context['context_sha256']=live.digest(context)
        contract['snapshot_sha256']=context['snapshot_sha256']
        raw=live.canonical({'live_controls':contract});lock=Lock();authority=Authority(lock)
        observer=Observer(rig,context,contract,views)
        control=live.FiniteLiveControls(raw,context,Verifier(raw,context),lock,authority,observer)
        writers={'fixture':'fresh benign root process/FD evidence'}
        fresh=copy.deepcopy(snapshot);fresh['writer_exclusion']['evidence_sha256']=live.digest(writers)
        evidence={'schema':1,'kind':'PRIVATE_EPOCH7_ADMISSION_SPLIT_EVIDENCE',
            'snapshot_sha256':context['snapshot_sha256'],'retained':retained,'writers':writers,
            'install_admission':'NOT_GRANTED','production_acceptance':'NOT_VERIFIED','target_mutations':0,
            'fresh_snapshot_sha256':live.digest(fresh),'fresh_writer_exclusion':fresh['writer_exclusion'],
            'fresh_process_proof':process_view(contract,0)}
        observer.preflight=lambda context:(copy.deepcopy(snapshot),copy.deepcopy(evidence))
        return control,context,snapshot,evidence

    def test_admission_split_preserves_reviewed_identity_and_binds_fresh_writer_evidence(self):
        control,context,snapshot,evidence=self._preflight_fixture()
        self.assertNotEqual(context['snapshot_sha256'],evidence['fresh_snapshot_sha256'])
        result=control.preflight(context)
        self.assertEqual(result['evidence_sha256'],live.digest(evidence))
        self.assertEqual(live.digest(snapshot),context['snapshot_sha256'])

    def test_admission_split_rejects_fresh_hash_exclusion_or_process_drift(self):
        for defect in ('hash','exclusion','writer_digest','process','old_kind'):
            control,context,snapshot,evidence=self._preflight_fixture()
            if defect=='hash':evidence['fresh_snapshot_sha256']=h('fake')
            elif defect=='exclusion':evidence['fresh_writer_exclusion']['all_stopped']=False
            elif defect=='writer_digest':evidence['writers']['fixture']='other proof'
            elif defect=='old_kind':evidence['kind']='PRIVATE_DIGEST_ONLY_EPOCH7_SNAPSHOT'
            else:evidence['fresh_process_proof']['pids_after'].append(os.getpid()+9999)
            with self.subTest(defect=defect),self.assertRaises(ValueError):control.preflight(context)

    def test_full_finite_sequence_before_after_progression(self):
        control,observer,authority,contract,context=controls()
        for phase in sequence.PHASES:
            authority.current=phase
            sequence.check_observation(control.before_phase(context,phase),context,'before:'+phase)
            self.assertTrue(control.effect_check(context,phase))
            result=sequence.observation(context,phase,h('actual effect receipt fixture'))
            sequence.check_observation(control.after_phase(context,phase,result),context,'after:'+phase)
        self.assertEqual(control.next_index,len(sequence.PHASES))
    def test_reordered_repeated_or_unopened_phase_refused(self):
        control,observer,authority,contract,context=controls();phase=sequence.PHASES[0];authority.current=phase
        with self.assertRaises(ValueError):control.before_phase(context,sequence.PHASES[1])
        with self.assertRaises(ValueError):control.effect_check(context,phase)
        control.before_phase(context,phase)
        with self.assertRaises(ValueError):control.before_phase(context,phase)
    def test_each_boundary_requires_all_resource_hashes(self):
        for section in live.SECTIONS:
            control,observer,authority,contract,context=controls();authority.current=sequence.PHASES[0]
            observer.resource_mutator=lambda values,*unused:values[section].update(version=999)
            with self.subTest(section=section),self.assertRaisesRegex(ValueError,'RESOURCE_DRIFT'):
                control.before_phase(context,sequence.PHASES[0])
    def test_effect_omits_only_its_fixed_mutable_domains(self):
        control,observer,authority,contract,context=controls();phase=sequence.PHASES[0];authority.current=phase
        control.before_phase(context,phase);observer.resources_calls=[]
        self.assertTrue(control.effect_check(context,phase))
        self.assertTrue(all(set(names)==live.SECTIONS-live.MUTATIONS[phase]
                            for unused,unused2,names in observer.resources_calls))
    def test_runtime_drift_does_not_revoke_exact_cleanup_claim_authority(self):
        control,observer,authority,contract,context=controls()
        observer.resource_mutator=lambda *unused:(_ for _ in ()).throw(ValueError('runtime drift'))
        self.assertTrue(control.cleanup_check(context,'fence'))
        authority.lock.is_held=False
        with self.assertRaises(ValueError):control.cleanup_check(context,'fence')
    def test_cleanup_unknown_unit_or_operation_rejected(self):
        control,observer,authority,contract,context=controls()
        for op,unit in (('restart',None),('stop_unit','other.service')):
            with self.assertRaises(ValueError):control.cleanup_check(context,op,unit)

    def test_approval_and_lock_without_admitted_claim_cannot_authorize_cleanup(self):
        control,observer,authority,contract,context=controls();authority.admitted=False
        self.assertTrue(authority.lock.held())
        authority.receipt()
        with self.assertRaisesRegex(ValueError,'ADMITTED'):control.cleanup_check(context,'fence')
    def test_full_stop_observation_and_partial_proof_rejection(self):
        control,observer,authority,contract,context=controls();unit='xuanjun-ledger.service'
        result=control.observe_stopped_unit(context,'observe_stopped_after',unit)
        sequence.check_observation(result,context,'observe_stopped_after:'+unit)
        observer.unit_result={'inactive_observed':True}
        with self.assertRaises(ValueError):control.observe_stopped_unit(context,'observe_stopped_after',unit)
    def test_changed_context_or_contract_rejected_before_checks(self):
        control,observer,authority,contract,context=controls()
        control.contract['manager']['starttime']+=1
        with self.assertRaisesRegex(ValueError,'MUTATED'):control.verify_outer_review(context)

    def test_second_resource_read_rejects_race_before_or_effect(self):
        for boundary in ('before','effect'):
            control,observer,authority,contract,context=controls()
            phase=sequence.PHASES[0];authority.current=phase
            if boundary=='effect':control.before_phase(context,phase)
            observer.resources_calls=[]
            def mutate(values,*unused):
                if len(observer.resources_calls)==2:values['historical']['version']=999
            observer.resource_mutator=mutate
            with self.subTest(boundary=boundary),self.assertRaisesRegex(ValueError,'RESOURCE_DRIFT'):
                (control.before_phase if boundary=='before' else control.effect_check)(context,phase)

    def test_activation_effect_accepts_only_reviewed_stable_unit_transitions(self):
        control,observer,authority,contract,context=controls();index=14;phase=sequence.PHASES[index]
        control.next_index=index;authority.current=phase;control.before_phase(context,phase)
        original=observer.processes
        def mixed(context,phase,boundary):
            before=process_view(contract,14);after=process_view(contract,15)
            unit='xuanjun-ledger.service';before['units'][unit]=after['units'][unit]
            pid=after['units'][unit]['before']['MainPID'];before['processes'][str(pid)]=after['processes'][str(pid)]
            before['pids_before']=before['pids_after']=sorted(int(p) for p in before['processes'])
            return before
        observer.processes=mixed
        self.assertTrue(control.effect_check(context,phase))
        for defect in ('activating','unit_file_state','control_pid'):
            def bad(context,phase,boundary):
                value=mixed(context,phase,boundary)
                for side in ('before','after'):
                    row=value['units']['xuanjun-ledger.service'][side]
                    if defect=='activating':row.update(ActiveState='activating',SubState='start')
                    elif defect=='unit_file_state':row['UnitFileState']='unreviewed'
                    else:row['ControlPID']=99999
                return value
            observer.processes=bad
            with self.subTest(defect=defect),self.assertRaises(ValueError):control.effect_check(context,phase)

    def test_postcheck_effect_permits_only_exact_deferred_timer_transition(self):
        control,observer,authority,contract,context=controls();index=15;phase=sequence.PHASES[index]
        control.next_index=index;authority.current=phase;control.before_phase(context,phase)
        observer.processes=lambda *unused:process_view(contract,16)
        self.assertTrue(control.effect_check(context,phase))
        def bad(*unused):
            value=process_view(contract,16)
            for side in ('before','after'):value['units']['xuanjun-ledger.service'][side]['ActiveState']='inactive'
            return value
        observer.processes=bad
        with self.assertRaises(ValueError):control.effect_check(context,phase)

    def test_database_observer_exception_is_only_live_reopen_effect(self):
        for index in (10,11,12):
            control,observer,authority,contract,context=controls();phase=sequence.PHASES[index]
            control.next_index=index;authority.current=phase;control.before_phase(context,phase)
            def mutate(value,*unused):
                value['database_fds']=[dict(contract['database_identities'][live.d.DB],
                    pid=os.getpid(),fd=8,path=live.d.DB,storage_path=live.d.DB,flags=os.O_RDONLY)]
            observer.process_mutator=mutate
            if index==11:self.assertTrue(control.effect_check(context,phase))
            else:
                with self.assertRaises(ValueError):control.effect_check(context,phase)
            with self.assertRaises(ValueError):
                control.after_phase(context,phase,sequence.observation(context,phase,h('effect')))

    def test_phase_and_guard_deadlines_are_shared_and_fail_closed(self):
        control,observer,authority,contract,context=controls();phase=sequence.PHASES[0];authority.current=phase
        with mock.patch.object(live.time,'monotonic',return_value=100):control.before_phase(context,phase)
        self.assertEqual(control.phase_deadline,700)
        self.assertEqual(observer.deadlines[-1],130)
        with mock.patch.object(live.time,'monotonic',return_value=690):control.effect_check(context,phase)
        self.assertEqual(observer.deadlines[-1],700)
        with mock.patch.object(live.time,'monotonic',return_value=700):
            with self.assertRaisesRegex(ValueError,'DEADLINE'):control.effect_check(context,phase)
        with mock.patch.object(live.time,'monotonic',return_value=900):
            result=control.observe_stopped_unit(context,'observe_stopped_after','xuanjun-ledger.service')
        self.assertEqual(observer.deadlines[-1],930)
        sequence.check_observation(result,context,'observe_stopped_after:xuanjun-ledger.service')

    def test_adapter_returning_after_guard_deadline_rejected(self):
        control,observer,authority,contract,context=controls();phase=sequence.PHASES[0];authority.current=phase
        with mock.patch.object(live.time,'monotonic',side_effect=[100,100,100,131]):
            with self.assertRaisesRegex(ValueError,'DEADLINE'):control.before_phase(context,phase)

    def test_observer_plan_binding_rejection_precedes_any_guard(self):
        rig,context,contract,views=fixture();raw=live.canonical({'live_controls':contract})
        lock=Lock();verifier=Verifier(raw,context);authority=Authority(lock)
        observer=Observer(rig,context,contract,views);observer.bind_plan=lambda plan:False
        with self.assertRaisesRegex(ValueError,'APPROVED_PLAN_BINDING'):
            live.FiniteLiveControls(raw,context,verifier,lock,authority,observer)
    def test_missing_complete_preflight_evidence_cannot_become_admission(self):
        control,observer,authority,contract,context=controls()
        observer.preflight=lambda context: (observer.rig.snapshot,{'snapshot_sha256':context['snapshot_sha256'],'retained':{}})
        with self.assertRaisesRegex(ValueError,'SUPPORT_BINDING'):control.preflight(context)


if __name__=='__main__':unittest.main()
