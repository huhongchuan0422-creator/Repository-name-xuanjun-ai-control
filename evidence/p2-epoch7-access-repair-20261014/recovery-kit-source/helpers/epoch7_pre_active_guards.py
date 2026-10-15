"""Concrete read-only facade for the deliberately narrow retained RecoveryGate.

Original snapshot identity is provenance, not a claim that every current byte is
unchanged. Actual immutable constituents and explicitly owned transitions are
checked before returning that provenance projection. Never usable after ACTIVE.
"""
import copy
import grp
import os
import pwd
import time

import epoch7_delta as d
import epoch7_snapshot as snap
import epoch7_protected_fs as fs
import epoch7_python_identity as python_identity
from epoch7_injected_recovery import RecoveryGate
from epoch7_command_runner import ExactCommandRunner
from epoch7_live_controls import validate_cleanup_process_view,FiniteLiveControls
from epoch7_host_phases import CoreHostPhases,need,sha
from epoch7_host_observer import Epoch7HostObserver
from snapshot_io import LocalReadOnlyIO,PYTHON_REFERENCES

STABLE_DIR={'path','kind','uid','gid','mode','dev','ino','access_acl','default_acl'}


class PreActiveGateGuards(object):
    def __init__(self,observer,authority,diagnostics,executable_check):
        need(isinstance(observer,Epoch7HostObserver) and callable(executable_check),
             'INNER_CONCRETE_OBSERVER_REQUIRED')
        self.observer,self.authority,self.diagnostics=observer,authority,diagnostics
        self.executable=executable_check;self.gate=None;self.core=None;self.controls=None;self.retained_io=None
        self.deadline=None
        owner=self
        class RetainedReadOnlyIO(LocalReadOnlyIO):
            def check_locks(self):owner._check()
            def command(self,label,args):return owner._command(label,args)
        self.io=RetainedReadOnlyIO(copy.deepcopy(observer.policy),{})

    def bind(self,gate,retained_io,core,controls):
        need(self.gate is None and isinstance(gate,RecoveryGate) and gate.guards is self and
             isinstance(retained_io,fs.ProtectedFilesystem) and retained_io.gate is gate and
             isinstance(core,CoreHostPhases) and isinstance(controls,FiniteLiveControls) and
             controls.observer is self.observer,'INNER_EXACT_COMPOSITION')
        self.gate,self.retained_io,self.core,self.controls=gate,retained_io,core,controls

    def _check(self):
        self.authority.receipt()
        need(self.deadline is not None and time.monotonic()<self.deadline,'INNER_GUARD_DEADLINE')
        need(self.gate is not None and self.core is not None and self.controls is not None,'INNER_GUARD_NOT_BOUND')
        # Only the already observed owned generation chmod changes this reader's
        # ancestor policy; never mutate the reviewed snapshot policy itself.
        current=self.gate.current_generation
        self.io.pins[d.GENERATION]={k:current[k] for k in ('uid','gid','mode')}

    def install_lock_held(self):
        need(self.gate is not None and hasattr(self.observer,'fresh_evidence'),'INNER_FRESH_PREFLIGHT_REQUIRED')
        self.deadline=self.controls._begin_guard()
        self._check()
        need(d.same(self.observer.fresh_snapshot,self.gate.snapshot) and
             d.digest(self.observer.fresh_evidence['retained'])==self.gate.snapshot['retained_resource_sha256'],
             'INNER_FRESH_SNAPSHOT_BINDING')
        return self.observer.lock.held()

    def _phase(self):
        scope=self.diagnostics.scope
        phase=scope[len('phase:'):] if type(scope) is str and scope.startswith('phase:') else 'stage_exact_release'
        need(phase in ('stage_exact_release','preserve_prior_receipts','rebind_prepared_epoch',
             'quiesce_exact_epoch','replace_retained_targets','publish_reviewed_identities','change_generation_access'),
             'INNER_PREACTIVE_PHASE_SCOPE')
        return phase

    def _command(self,label,args):
        self._check()
        if label=='git':
            from snapshot_io import CONTROL_GIT_ARGS,CONTROL_GIT_ENV
            need(args==CONTROL_GIT_ARGS,'INNER_EXACT_GIT_QUERY')
            binary='/usr/bin/git';operation='stage_source_verify'
        elif label=='rpm':
            prefix=['-q','--qf','%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}']
            need(type(args) is list and len(args)==4 and args[:3]==prefix,'INNER_EXACT_RPM_QUERY')
            raw=self.io.read(snap.TRANSACTION+'/rpm-prerequisites.json')[0]
            packages=snap.decode(raw)['packages']
            need(args[3] in {row['name'] for row in packages},'INNER_RETAINED_RPM_SCOPE')
            binary=self.observer.policy['executables']['rpm']['path'];operation='retained_rpm_query'
        else:
            need(label=='systemctl_inventory' and args==['list-unit-files','--no-legend','--no-pager'],
                 'INNER_FIXED_READ_ONLY_TOOL')
            binary=self.observer.policy['executables']['systemctl']['path'];operation='service_show'
        need(self.executable(binary) is True,'INNER_QUERY_BINARY_PIN')
        remaining=int(self.deadline-time.monotonic());need(remaining>=1,'INNER_QUERY_DEADLINE')
        spec={'phase':self._phase(),'operation':operation,'argv':[binary]+args,
              'cwd':'/','env':(dict(CONTROL_GIT_ENV) if label=='git' else {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}),
              'timeout':min(5,remaining),'accepted_returncodes':[0]}
        def admitted():self._check();return True
        result=ExactCommandRunner({'query':spec},admitted,self.diagnostics).run('query')
        need(self.executable(binary) is True,'INNER_QUERY_BINARY_AFTER_PIN');return result.stdout

    def _preserved_file(self,path,wanted,maximum=16777216):
        self._check()
        if 'python_identity' in wanted:
            proof=python_identity.validate_pair_proof(wanted['python_identity'])
            need(path in python_identity.PYTHON_PATHS and
                 d.same(wanted,dict(proof['sample']['files'][path],python_identity=proof)),
                 'INNER_EXACT_PYTHON_PAIR_ROW')
            actual=self.io.read_python(path,maximum=maximum)[1]
        else:actual=self.io.read(path,maximum=maximum)[1]
        need(d.same(actual,wanted),'INNER_PRESERVED_FILE_DRIFT')
        self._check();return actual

    def _native_python_reference(self,components,native_raw):
        reference=components.get('python_reference')
        paired=any('python_identity' in row for row in components['components'].values())
        need(reference is not None or not paired,'INNER_NATIVE_PYTHON_REFERENCE_REQUIRED')
        if reference is None:return
        path=snap.decode(native_raw)['ledger']['python']
        need(type(reference) is dict and set(reference)=={'reference_path','links','final'} and
             path in PYTHON_REFERENCES and reference['reference_path']==path and
             reference['final']['path']==path and reference['links']==[],
             'INNER_NATIVE_PYTHON_REFERENCE_SCOPE')
        self._check();actual=self.io.executable_reference(path)
        need(d.same(actual,reference),'INNER_NATIVE_PYTHON_REFERENCE_DRIFT');self._check()

    def _native_node_reference(self,native_raw):
        # This proof is already bound to all17 approved immutable views. Inner
        # CAS guards repeat it even though no active process profile exists yet.
        quiet=getattr(self.observer,'quiet',None)
        proof=getattr(quiet,'node_reference',None)
        from epoch7_openclaw_recipe import DIRECT_WRAPPER_SHA,LAUNCHER,GATEWAY
        blocks=(getattr(self.observer,'live_contract',None) or {}).get('service_role_contract',{}).get('units',{})
        direct=blocks.get(GATEWAY,{}).get('sources',{}).get(LAUNCHER)==DIRECT_WRAPPER_SHA
        need(not direct or proof is not None,'INNER_NATIVE_NODE_REFERENCE_REQUIRED')
        if proof is None:return
        from unit_metadata import validate_node_reference
        identity=snap.decode(native_raw)['gatewayIdentity']
        expected=validate_node_reference(proof,identity['exe'],identity['sha256'])
        self._check();actual=self.io.node_directory_reference(identity['exe'],identity['sha256'])
        from epoch7_resource_observer import same_node_reference
        need(same_node_reference(actual,expected,self.authority),'INNER_NATIVE_NODE_REFERENCE_DRIFT');self._check()

    def _prerequisites(self,retained):
        raw=self.io.read(snap.PLAN)[0];plan=snap.decode(raw)['runtime']['prerequisites']
        expected=retained['prerequisites'];identities={}
        for name in plan['groups']:
            group=grp.getgrnam(name);identities['group:'+name]={'gid':group.gr_gid,'members':sorted(group.gr_mem)}
        for name,row in plan['users'].items():
            user=pwd.getpwnam(name)
            need((user.pw_uid,user.pw_gid,user.pw_dir,user.pw_shell)==
                 (row['uid'],row['gid'],row['home'],'/sbin/nologin'),'INNER_NSS_USER_DRIFT')
            identities['user:'+name]={'uid':user.pw_uid,'gid':user.pw_gid,
                                     'groups':sorted(os.getgrouplist(name,user.pw_gid))}
        need(identities==expected['identities'],'INNER_NSS_MEMBERSHIP_DRIFT')
        for path,before in expected['directories'].items():
            if path==d.GENERATION:
                actual=self.retained_io.read_generation();wanted=self.gate.current_generation
            elif path=='/opt/xuanjun-control-releases' and hasattr(self.core,'staged_release_parent'):
                actual=self.core.io.release_parent()[0];wanted=self.core.staged_release_parent
                actual=dict(actual,path=path);wanted=dict(wanted,path=path)
            else:actual=self.io.directory(path);wanted=before
            need(all(actual[k]==wanted[k] for k in STABLE_DIR),'INNER_DIRECTORY_AUTHORITY_DRIFT')
        for path,wanted in expected['binaries'].items():
            self._preserved_file(path,wanted,maximum=536870912)
        rpm=snap.decode(self.io.read(snap.TRANSACTION+'/rpm-prerequisites.json')[0])
        versions={}
        for row in rpm['packages']:
            output=self._command('rpm',['-q','--qf','%{NAME} %{EPOCHNUM} %{VERSION} %{RELEASE} %{ARCH}',row['name']])
            need(output.decode('utf-8','strict').split()==row['candidate'],'INNER_RETAINED_RPM_DRIFT')
            versions[row['name']]=sha(output)
        need(versions==expected['rpm_versions'],'INNER_RPM_VERSION_PROJECTION')

    def read_preserved_pins(self):
        self._check();retained=self.observer.fresh_evidence['retained']
        mutable={snap.ACTIVE,snap.EPOCHS,snap.NATIVE}|set(d.TARGETS)
        for path,wanted in retained['files'].items():
            if path not in mutable:
                self._preserved_file(path,wanted)
        native=self.io.read(snap.NATIVE)[0]
        active=self.core.store.read()
        expected_native=self.core.native_before if active['epoch']==7 else self.core.native_after
        need(native==expected_native,'INNER_OWNED_NATIVE_TRANSITION_DRIFT')
        for path,wanted in retained['native_components']['components'].items():
            if path not in d.TARGETS:
                self._preserved_file(path,wanted,maximum=268435456)
        self._native_python_reference(retained['native_components'],expected_native)
        self._native_node_reference(expected_native)
        for path,expected in retained['database_sets'].items():
            need(self.io.read(path,maximum=67108864)[1]==expected['file'],'INNER_PRESERVED_DB_DRIFT')
            for suffix in ('-wal','-shm','-journal'):
                if suffix in expected['sidecars']:
                    need(self.io.read(path+suffix)[1]==expected['sidecars'][suffix],'INNER_PRESERVED_DB_SIDECAR_DRIFT')
                else:need(self.io.absent(path+suffix),'INNER_UNEXPECTED_DB_SIDECAR')
        for root,pin in sorted(self.observer.policy['releases'].items()):
            need(d.same(self.io.release(root,pin),retained['release_evidence'][root]),'INNER_RETAINED_CACHE_DRIFT')
        publisher=snap.decode(self.io.read(snap.TRANSACTION+'/publisher-bootstrap.json')[0])
        need([self.io.publisher(row) for row in publisher['directories']]==retained['publishers'],
             'INNER_PUBLISHER_DRIFT')
        self._prerequisites(retained)
        reference=snap.decode(self.io.read(snap.PLAN)[0])['runtime']['publisher']
        control=next(row for row in publisher['directories'] if row['target']=='/var/lib/xuanjun-development/control.git')
        need(self.io.control_git_source(reference,control,sha(self.io.read(snap.TRANSACTION+'/publisher-bootstrap.json')[0]))==
             retained['control_git'],'INNER_CONTROL_HEAD_RECONCILIATION_DRIFT')
        need(self.observer.tls_contents()=={k:self.gate.snapshot['tls'][k] for k in
             ('certificate_sha256','tree_fingerprint_sha256')},'INNER_TLS_CONTENT_DRIFT')
        self._check()
        # This hash identifies the verified original evidence, whose mutable
        # fields were checked against owned transition records above/elsewhere.
        return copy.deepcopy(self.gate.delta['preserve'])

    def read_activation_evidence(self):
        self._check();value=self.core.store.read();raw=self.io.read(snap.EPOCHS)[0]
        prefix=self.observer.epoch7_prefix
        need(raw.startswith(prefix) and sha(prefix)==self.gate.snapshot['epoch_journal_sha256'],
             'INNER_PRESERVED_EPOCH7_PREFIX')
        return {'descriptor':value,'preserved_epoch7_prefix_sha256':sha(prefix)}

    def read_generation(self):self._check();return self.retained_io.read_generation()

    def read_sandbox(self):
        self._check();raw=self.io.read(snap.TRANSACTION+'/sandbox-profile.json')[0]
        value=snap.decode(raw);profile=self.io.read(snap.PROFILE)[0]
        need(value['state']=='RESTORED' and value['current_sha256']==value['original_sha256']==sha(profile),
             'INNER_RESTORED_SANDBOX_REQUIRED')
        return {'state':value['state'],'journal_sha256':sha(raw),'profile_sha256':sha(profile)}

    def read_targets(self):
        self._check();return {path:self.retained_io.read_target(path) for path in sorted(d.TARGETS)}
    def read_additive_absence(self,path):self._check();return self.retained_io.read_additive_absence(path)
    def read_additive_target(self,path):self._check();return self.retained_io.read_additive_target(path)

    def read_writer_exclusion(self):
        self._check()
        measured=self.observer.processes(self.observer.context,self._phase(),'inner')
        validate_cleanup_process_view(measured,self.observer.live_contract,os.getpid())
        for path in snap.LEGACY_MASKS-d.OWNER_MASKS:
            # Gateway remains masked throughout every inner target phase.
            need(self.io.mask(path)['link']=='/dev/null','INNER_LEGACY_MASK_DRIFT')
        scheduler={}
        for root in sorted(snap.SCHEDULER_ROOTS):
            scheduler.update(__import__('reviewed_scanner').bounded_file_inventory(root,optional=True))
        need(scheduler==self.observer.policy['scheduler_files'],'INNER_SCHEDULER_DRIFT')
        raw=self._command('systemctl_inventory',['list-unit-files','--no-legend','--no-pager'])
        names={line.split()[0] for line in raw.decode('utf-8','strict').splitlines()
               if line.split() and line.split()[0].startswith(('xj-','xuanjun-'))}
        need(names==set(self.observer.policy['control_units']),'INNER_CONTROL_UNIT_SET_DRIFT')
        for paths in self.observer.policy['control_units'].values():
            for path,wanted in paths.items():
                if path in d.TARGETS or path in snap.LEGACY_MASKS:continue
                need(sha(self.io.read(path)[0])==wanted,'INNER_CONTROL_SCRIPT_DRIFT')
        self._check()
        return dict({key:True for key in ('all_stopped','cgroups_empty','legacy_masks_preserved',
            'scheduler_excluded','runner_excluded','database_fds_excluded')},evidence_sha256=d.digest(measured))
