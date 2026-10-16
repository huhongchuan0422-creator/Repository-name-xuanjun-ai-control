"""New local synthetic production-shaped predecessor collector regressions.

Only the pure delta, snapshot, and successor-contract modules are loaded. No old
suite, host IO module, production path, network, subprocess, or authority is run.
The copied/reworked fixture builds a complete synthetic collector inventory.
Native and predecessor immutable byte pins are substituted ONLY in test scopes;
a separate test proves the unmodified real predecessor pin rejects these bytes.
Success here proves local semantics, never authentication of the unavailable
1641-byte real receipt and never host approval or production readiness.
"""
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]


def pure_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


d = pure_module('predecessor_test_delta', ROOT / 'baseline/helpers/epoch7_delta.py')
cs = pure_module('predecessor_test_successor_contract', ROOT / 'kit-overlay/helpers/epoch7_claim_successor.py')
with mock.patch.dict(sys.modules, {'epoch7_delta': d}):
    c = pure_module('successor_snapshot_under_test', ROOT / 'kit-overlay/helpers/epoch7_snapshot.py')
    legacy = pure_module('original_snapshot_reference', ROOT / 'baseline/helpers/epoch7_snapshot.py')
REAL_PREDECESSOR = cs.predecessor_contract()

def packed(v): return d.canonical(v) + b'\n'
def h(v): return hashlib.sha256(v.encode()).hexdigest()


def native_transition_fixture(original=None):
    """Synthetic bytes, never actual UK evidence or an authority bypass."""
    old = '/opt/xuanjun-control-releases/integration-' + c.NATIVE_ORIGINAL_RELEASE[:16] + '/stage1/native_ledger_bridge.py'
    client = '/etc/xuanjun-development/p2-native-ledger-client.json'
    if original is None:
        original = {'ledger': {'python': '/usr/bin/python3', 'pythonSha256': h('python'), 'bridge': old,
            'config': client, 'files': {old: h('bridge'), client: h('historical client')}},
            'gatewayIdentity': {'user': 'xuanjun_dev', 'exe': '/home/xuanjun_dev/bin/node',
                'sha256': h('node'), 'cgroup': '/system.slice/xuanjun-uk-openclaw.service'}}
    original = copy.deepcopy(original)
    def rendered(release):
        value = copy.deepcopy(original); ledger = value['ledger']; previous = ledger['bridge']
        bridge = '/opt/xuanjun-control-releases/integration-' + release[:16] + '/stage1/native_ledger_bridge.py'
        ledger['bridge'] = bridge; ledger['files'][bridge] = ledger['files'].pop(previous)
        return packed(value)
    prior, current = rendered(c.RETAINED_NATIVE_RELEASE), rendered(d.OLD_MANIFEST)
    approval = {'schema': 1, 'reviewer': 'CHATGPT_NATIVE_TASK5',
        'decision': 'APPROVED_ONE_EXACT_EPOCH5_RESUME_WITH_FENCED_RETAIN_ON_FAILURE',
        'transaction_id': d.TX, 'runtime_manifest_sha256': d.OLD_MANIFEST,
        'expected_epoch': 5, 'proposed_prepared_epoch': 6, 'authorized_attempts': 1,
        'failure_policy': 'FENCE_STOP_RETAIN_NO_REPLAY', 'legacy_restart': False,
        'historical_notification_replay': False, 'production_acceptance': 'PENDING',
        'recovery_plan_sha256': h('plan'), 'recovery_kit_manifest_sha256': h('kit'), 'snapshot_sha256': h('snapshot')}
    completed = list(c.NATIVE_PHASES[:5])
    phases = {phase: {'fixture': True} for phase in completed}
    phases['rebind_prepared_epoch'] = {'epoch': 6, 'descriptor_sha256': h('epoch6'),
        'tls_reference_sha256': h('tls candidate'), 'native_binding': {
            'old_sha256': c.sha(prior), 'new_sha256': c.sha(current), 'original_preserved': True}}
    attempt = {'schema': 1, 'stage': 'HOLD', 'automatic_retry': False, 'historical_replay': False,
        'legacy_restart': False, 'production_acceptance': 'PENDING', 'completed': completed, 'phase_evidence': phases,
        'authorization': {'review_id': 6170703284, 'body_sha256': h('approval'), 'approval': approval},
        'plan_sha256': h('plan'), 'kit_manifest_sha256': h('kit'), 'snapshot_sha256': h('snapshot')}
    return current, prior, packed(original), packed(attempt)


def native_raws(backend):
    return tuple(backend.raw[name] for name in (c.NATIVE, c.NATIVE_PRIOR, c.NATIVE_ORIGINAL, c.NATIVE_ATTEMPT))


def native_pin_context(raws):
    """Only map immutable byte pins for explicitly synthetic local fixtures."""
    current, prior, original, attempt = raws
    return mock.patch.multiple(c, NATIVE_CURRENT_SHA=c.sha(current), RETAINED_NATIVE_SHA=c.sha(prior),
        NATIVE_ORIGINAL_SHA=c.sha(original), NATIVE_ATTEMPT_SHA=c.sha(attempt))


def writer_fixture():
    units = {}
    for name in c.WRITER_UNITS:
        units[name] = {'state':dict(Id=name,LoadState='masked' if '/etc/systemd/system/'+name in c.LEGACY_MASKS else 'loaded',
            ActiveState='inactive',SubState='dead',MainPID='0',ControlPID='0',ControlGroup='',NeedDaemonReload='no',
            UnitFileState='masked' if '/etc/systemd/system/'+name in c.LEGACY_MASKS else 'disabled',ConditionResult='no'),
            'cgroup_entries':{}}
    masks={name:dict(kind='MASK',link='/dev/null',uid=0,gid=0,nlink=1,mode=0o777,dev=7,ino=7000+i)
           for i,name in enumerate(sorted(c.LEGACY_MASKS))}
    return {'units':units,'masks':masks,'scheduler_sha256':h('scheduler'),'control_files':{'fixture':{}},
        'processes':{'process_identity_sha256':h('process'),'fd_count':10,
                     'background_processes':[],'background_processes_sha256':d.digest([])},'manager':{'fixture':True}}


class FakeIO(object):
    def __init__(self):
        self.raw, self.meta, self.dirs = {}, {}, {}
        self.present = set(); self.events = []; self.calls = {}; self.logical = {}
        self.writer = writer_fixture()
    def add(self, name, raw, uid=0, gid=0, mode=0o600):
        self.raw[name] = raw
        self.meta[name] = dict(kind='FILE', sha256=c.sha(raw), uid=uid, gid=gid, mode=mode,
            dev=7, ino=1000 + len(self.meta), nlink=1, size=len(raw), mtime_ns=11, ctime_ns=12)
    def identity(self): return {'hostname': c.HOST, 'euid': 0}
    def check_locks(self): self.events.append('locks')
    def read(self, name, maximum=16777216):
        self.calls[name] = self.calls.get(name, 0) + 1
        return self.raw[name], copy.deepcopy(self.meta[name])
    def directory(self, name): return copy.deepcopy(self.dirs[name])
    def absent(self, name): return name not in self.present and name not in self.raw
    def mask(self, name):
        return dict(kind='MASK', link='/dev/null', uid=0, gid=0, dev=7, ino=3000+sorted(d.OWNER_MASKS).index(name),
                    mode=0o777, nlink=1, size=9, mtime_ns=11, ctime_ns=12)
    def directory_inventory(self, root): return copy.deepcopy({k:v for k,v in self.dirs.items() if k==root or k.startswith(root+'/')})
    def inventory(self, name):
        return {p: c.sha(raw) for p, raw in self.raw.items() if p.startswith(name + '/')}
    def writers(self, policy, paths): self.events.append('writers'); return copy.deepcopy(self.writer)
    def logical_manifest(self, raw): return copy.deepcopy(self.logical[raw])
    def tls(self, policy): return {'tree_fingerprint_sha256': h('tree'), 'certificate_sha256': h('cert')}
    def publisher(self, row): return {'target': row['target'], 'root_identity_matches': True, 'stage_absent': True}
    def release(self, root, pin): return {'inventory_sha256': h(root)}
    def native_identity(self,binding,effective):return {'fixture':h('native components')}
    def control_git_source(self,reference,row,journal_sha256):
        return {'schema':1,'path':row['target'],'head_commit':'a'*40,'head_tree':'b'*40,
            'publisher_reference_sha256':d.digest(reference),'publisher_journal_sha256':journal_sha256,
            'publisher_fingerprint_sha256':row['fingerprint'],'git_sha256':h('fixture binary git')}
    def prerequisites(self, plan, receipt, rpm): return {'fixture': 'prerequisites'}


def fixture():
    f = FakeIO()
    for name in c.MANDATORY_FILES:
        f.add(name, packed({}), mode=0o644 if name in d.TARGETS else 0o600)
    profile = packed({'agents': {}, 'plugins': {}}); f.add(c.PROFILE, profile, uid=1002, gid=1002)
    f.add(c.TRANSACTION + '/sandbox-profile-original.json', profile)
    candidate = packed({'agents': {'fixture': True}}); f.add(c.TRANSACTION + '/sandbox-profile-candidate.json', candidate)
    f.add(c.TRANSACTION + '/sandbox-profile.json', packed(dict(schema=1, state='RESTORED', current_sha256=c.sha(profile),
        original_sha256=c.sha(profile), candidate_sha256=c.sha(candidate))))
    f.add(c.TRANSACTION + '/epoch5-recovery-execution.json', packed(dict(stage='HOLD', automatic_retry=False,
        authorization={'review_id': 6170703284}, production_acceptance='PENDING')))
    active = dict(schema=1, state='PREPARED', epoch=7, generation=1, release_sha256=d.OLD_MANIFEST,
        config_sha256=f.meta['/etc/xuanjun-development/dispatcher.json']['sha256'], binary_sha256=d.OLD_BINARY,
        ledger_uuid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', instance='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        db_path=d.DB, ledger_socket=d.SOCKET)
    f.add(c.ACTIVE, packed(active), mode=0o644)
    f.add(c.ACTIVATION_LOCK,b'',mode=0o644)
    f.add(c.INSTALL_LOCK,b'')
    last = '0'*64; journal = b''
    for epoch in range(1, 8):
        desc = dict(active, epoch=epoch)
        line = packed(dict(schema=1, seq=epoch, epoch=epoch, state='PREPARED', previous_sha256=last,
            descriptor_sha256=c.sha(packed(desc)), descriptor=desc, proof={}))
        journal += line; last = c.sha(line)
    f.add(c.EPOCHS, journal, mode=0o644)
    tls_config = dict(schema=1, root=c.TLS, domain='uk.wenwenwenyiyiyi.work', transaction_id=d.TX,
        transaction_directory=c.TRANSACTION, accept_acme_terms=True,
        **{k: active[k] for k in ('release_sha256', 'instance', 'generation', 'ledger_uuid')})
    f.add(c.TLS_CONFIG, packed(tls_config))
    f.add(c.TRANSACTION + '/epoch6-tls-renewal-candidate.json', packed(tls_config))
    f.add(c.TRANSACTION + '/tls-lifecycle.json', packed(dict(schema=1, state='READY_ISSUED_AND_RENEWAL_DRYRUN_VERIFIED',
        config=tls_config, fingerprint=h('tree'), certificate_sha256=h('cert'))))
    for name, raw in zip((c.NATIVE, c.NATIVE_PRIOR, c.NATIVE_ORIGINAL, c.NATIVE_ATTEMPT), native_transition_fixture()):
        f.add(name, raw, mode=0o644 if name == c.NATIVE else 0o600)
    boots = []
    for i in range(7):
        name = c.NATIVE if i == 0 else '/etc/xuanjun-owner-callback/fixture-' + str(i)
        if i: f.add(name, ('private fixture ' + str(i)).encode(), uid=1004, gid=1006)
        m = f.meta[name]
        boots.append(dict(target=name, temp=name+'.tmp', state='PUBLISHED', owner_uid=m['uid'], group_gid=m['gid'],
                          **{k:m[k] for k in ('sha256','dev','ino','mode')}))
    f.add(c.TRANSACTION + '/bootstrap-files.json', packed(dict(schema=1, files=boots)))
    pubs = [dict(target=name, stage=name+'.tmp', state='PUBLISHED', dev=7, ino=6000+i, fingerprint=h(name))
            for i,name in enumerate(sorted(c.PUBLISHERS))]
    f.add(c.TRANSACTION + '/publisher-bootstrap.json', packed(dict(schema=1, directories=pubs)))
    dbpins = {}
    for name in c.DATABASES:
        data = ('FIXTURE_SQLITE_' + name).encode(); f.add(name, data, uid=1002 if name == c.SOURCE_DB else 0)
        logical = {'sha256':c.sha(data), 'size':len(data), 'counts':{}, 'pragmas':{}, 'schema_sha256':h('schema'),
                   'table_sha256':{}, 'quick_check':'ok'}; f.logical[data] = logical
        dbpins[name] = dict(sha256=c.sha(data), uid=f.meta[name]['uid'], gid=0, mode=0o600,
                           sidecars={}, logical_manifest_sha256=d.digest(logical))
    f.add(c.TRANSACTION + '/ledger-cutover.json', packed(dict(stage='STAGED', source_replaced=False, activation_executed=False,
        task_replay=False, migration={'rollback': f.logical[f.raw[c.ROLLBACK_DB]], 'generation':f.logical[f.raw[d.DB]]})))
    f.add(c.PLAN, packed({'cutover':dict(source=c.SOURCE_DB, rollback_snapshot=c.ROLLBACK_DB, staged_generation=d.DB),
                         'runtime':{'prerequisites':{},'publisher':{'path':c.BASE+'/publisher-realm-38503014520/protected-publisher-inputs.json',
                             'sha256':h('publisher'),'source_commit':'a'*40,'source_tree':'b'*40}}}))
    provision = []
    for name in sorted(d.TARGETS):
        m = f.meta.get(name, dict(sha256=h(name), uid=0, gid=0, mode=0o644))
        provision.append(dict(target=name, rendered_sha256=m['sha256'], uid=m['uid'], gid=m['gid'], mode=m['mode'],
                              previous={'masked':True} if name in d.OWNER_MASKS else None))
    f.add(c.TRANSACTION + '/epoch6-runtime-provisioning.json', packed(dict(schema=1,
        failure_policy='FENCE_STOP_RETAIN_NO_REPLAY', rollback_complete=False, targets=provision)))
    files = {n: {k:m[k] for k in ('sha256','uid','gid','mode')} for n,m in f.meta.items() if n not in c.DATABASES}
    executables = {}
    for label in ('systemctl','openssl','rpm','systemd','git'):
        name = '/usr/bin/'+label; f.add(name, ('fixture binary '+label).encode(), mode=0o755)
        files[name] = {k:f.meta[name][k] for k in ('sha256','uid','gid','mode')}
        executables[label] = {'path':name,'sha256':files[name]['sha256']}
    dirs = {'/': {'uid':0,'gid':0,'mode':0o755}}
    for name in list(files) + list(c.DATABASES):
        parent=os.path.dirname(name)
        while parent != '/':
            dirs[parent]={'uid':0,'gid':0,'mode':0o700 if parent==c.TRANSACTION or parent.startswith(c.TRANSACTION+'/') else 0o755}
            parent=os.path.dirname(parent)
    dirs[d.GENERATION]={'uid':1003,'gid':1006,'mode':0o750}
    f.dirs[d.GENERATION]=dict(path=d.GENERATION, kind='DIRECTORY', uid=1003, gid=1006, mode=0o750, dev=7, ino=4000,
        nlink=2,size=4096,mtime_ns=11,ctime_ns=12,access_acl='user::rwx\ngroup::r-x\nother::---\n',default_acl='')
    for name,attributes in dirs.items():
        if name==c.TRANSACTION or name.startswith(c.TRANSACTION+'/'):
            f.dirs[name]=dict(path=name,kind='DIRECTORY',dev=7,ino=5000+len(f.dirs),nlink=2,size=4096,mtime_ns=11,ctime_ns=12,
                access_acl='user::rwx\ngroup::---\nother::---\n',default_acl='',**attributes)
    releases = {}
    for digest in ('1'*64,'2'*64,d.OLD_MANIFEST):
        releases['/opt/xuanjun-control-releases/integration-'+digest[:16]] = dict(manifest_sha256=digest,
            payloads={'stage1/native.py':h('native')}, caches={}, cache_staging='/opt/xuanjun-control-releases/.integration-'+'a'*16)
    controls = {name:{'/etc/systemd/system/'+name:h(name)} for name in c.WRITER_UNITS if name.startswith(('xuanjun-','xj-'))}
    policy=dict(schema=1,kind='EPOCH7_MEASURED_READ_ONLY_PINS',hostname=c.HOST,transaction_id=d.TX,
        owner_evidence_sha256=h('fixture owner evidence'),files=files,directories=dirs,
        transaction_inventory={n[len(c.TRANSACTION)+1:]:m['sha256'] for n,m in files.items() if n.startswith(c.TRANSACTION+'/')},
        releases=releases,databases=dbpins,scheduler_files={},control_units=controls,executables=executables)
    return policy,f


def complete_synthetic_ancestors(policy, backend):
    for index, (name, pin) in enumerate(sorted(policy['directories'].items())):
        if name == '/' or name in backend.dirs:
            continue
        mode = pin['mode']
        def bits(number):
            return ''.join(char if number & bit else '-' for char, bit in (('r',4),('w',2),('x',1)))
        backend.dirs[name] = dict(path=name, kind='DIRECTORY', dev=7, ino=9000+index,
            nlink=2, size=4096, mtime_ns=11, ctime_ns=12,
            access_acl='user::'+bits((mode>>6)&7)+'\ngroup::'+bits((mode>>3)&7)+'\nother::'+bits(mode&7)+'\n',
            default_acl='', **pin)


def synthetic_predecessor():
    state = {'schema': 1, 'stage': 'HOLD', 'failed_stage': 'CLAIM_INTENT',
        'failed_phase': 'admission', 'failed_operation': 'create_inner_attempt',
        'admission': 'UNKNOWN', 'receipt_status': 'OBSERVED', 'completed': [],
        'phase_evidence': {}, 'containment': [], 'containment_status': 'NOT_ATTEMPTED',
        'secondary_errors': [], 'interruption': None, 'automatic_retry': False,
        'legacy_restart': False, 'historical_notification_replay': False,
        'prerequisite_replay': False, 'preflight_evidence': {'synthetic': True}}
    binding = {'review_id': cs.OLD_REVIEW_ID, 'approval_body_sha256': cs.OLD_REVIEW_SHA256,
        'authorization_sha256': h('synthetic authorization'), 'delta_sha256': h('synthetic delta'),
        'complete_delta_sha256': h('synthetic complete delta'),
        'additive_targets_sha256': h('synthetic additives'), 'snapshot_sha256': h('synthetic snapshot')}
    value = {'schema': 1, 'name': cs.OLD_OUTER, 'transaction_id': d.TX,
        'context_sha256': h('synthetic old context'), 'binding': binding, 'state': state}
    return packed(value), binding, state


class PredecessorSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.modules_patch = mock.patch.dict(sys.modules, {'epoch7_claim_successor': cs})
        self.modules_patch.start(); self.addCleanup(self.modules_patch.stop)
        self.policy, self.io = fixture()
        complete_synthetic_ancestors(self.policy, self.io)
        self.original_policy = copy.deepcopy(self.policy)
        native_values = dict(zip(('NATIVE_CURRENT_SHA', 'RETAINED_NATIVE_SHA',
            'NATIVE_ORIGINAL_SHA', 'NATIVE_ATTEMPT_SHA'), (c.sha(raw) for raw in native_raws(self.io))))
        self.native_patch = mock.patch.multiple(c, **native_values)
        self.legacy_patch = mock.patch.multiple(legacy, **native_values)
        self.native_patch.start(); self.addCleanup(self.native_patch.stop)
        self.legacy_patch.start(); self.addCleanup(self.legacy_patch.stop)
        self.historical_snapshot, self.historical_evidence = c.collect(self.policy, self.io)
        self.raw, self.binding, self.state = synthetic_predecessor()
        self.predecessor_patch = mock.patch.multiple(cs, PREDECESSOR_SIZE=len(self.raw),
            PREDECESSOR_SHA256=c.sha(self.raw), PREDECESSOR_BINDING_SHA256=d.digest(self.binding),
            PREDECESSOR_STATE_SHA256=c.sha(packed(self.state)))
        self.predecessor_patch.start(); self.addCleanup(self.predecessor_patch.stop)
        self.contract = cs.predecessor_contract()
        self.old_path = c.TRANSACTION + '/' + cs.OLD_OUTER
        self.io.add(self.old_path, self.raw)
        self.io.dirs[c.TRANSACTION].update(size=8192, mtime_ns=31, ctime_ns=32)
        self.original_observation = copy.deepcopy((self.historical_snapshot, self.historical_evidence))

    def collect(self):
        return c.collect(self.policy, self.io, predecessor=self.contract)

    def reconcile(self, snapshot=None, evidence=None):
        if snapshot is None:
            snapshot, evidence = self.collect()
        return c.validate_predecessor_collection(snapshot, evidence, self.policy,
            self.historical_snapshot, self.historical_evidence, self.contract)

    def test_new_mode_retains_actual_facts_and_bound_comparison_only_result(self):
        snapshot, evidence = self.collect()
        proof = self.reconcile(snapshot, evidence)
        self.assertEqual(snapshot['schema'], 2)
        self.assertIs(snapshot['absent_paths'][cs.OLD_OUTER], False)
        self.assertEqual(evidence['retained']['transaction_inventory'][self.old_path], c.sha(self.raw))
        self.assertEqual(evidence['retained']['transaction_directories'][c.TRANSACTION]['mtime_ns'], 31)
        self.assertEqual(d.digest(evidence['retained']), snapshot['retained_resource_sha256'])
        self.assertNotEqual(snapshot['retained_resource_sha256'], self.historical_snapshot['retained_resource_sha256'])
        measured = evidence['retained']['predecessor']
        self.assertEqual(set(measured), {'schema','record','ancestors','absent'})
        self.assertEqual(proof['measured_predecessor_sha256'], d.digest(measured))
        self.assertEqual(proof['live_snapshot_sha256'], d.digest(snapshot))
        self.assertEqual(proof['live_evidence_sha256'], d.digest(evidence))
        self.assertEqual(proof['comparison_only_snapshot'], self.historical_snapshot)
        self.assertEqual(proof['kind'], 'COMPARISON_ONLY_PREDECESSOR_RECONCILIATION')
        self.assertEqual(self.policy, self.original_policy)
        self.assertEqual((self.historical_snapshot,self.historical_evidence),self.original_observation)
        self.assertNotIn('synthetic old context', json.dumps(evidence))
        self.assertEqual(set(measured['ancestors']), set(c._predecessor_ancestors()))
        self.assertGreaterEqual(self.io.calls[self.old_path], 2)

    def test_legacy_mode_unchanged_and_refuses_existing_predecessor(self):
        with self.assertRaisesRegex(ValueError, 'TRANSACTION_INVENTORY_CHANGED'):
            c.collect(self.policy, self.io)
        del self.io.raw[self.old_path]; del self.io.meta[self.old_path]
        self.io.dirs[c.TRANSACTION] = copy.deepcopy(self.historical_evidence['retained']['transaction_directories'][c.TRANSACTION])
        self.assertEqual(c.collect(self.policy,self.io), legacy.collect(self.policy,self.io))

    def test_real_fixed_pin_rejects_synthetic_record(self):
        self.predecessor_patch.stop()
        try:
            self.assertEqual(cs.predecessor_contract(), REAL_PREDECESSOR)
            with self.assertRaisesRegex(ValueError, 'PREDECESSOR_BYTES'):
                c.collect(self.policy,self.io,predecessor=REAL_PREDECESSOR)
        finally:
            # Restore the fixture patch so its registered cleanup stops it once
            # on Python 3.6 as well as newer unittest.mock implementations.
            self.predecessor_patch.start()

    def test_contract_mutations_each_refuse_before_read(self):
        for name in self.contract:
            with self.subTest(field=name):
                changed = copy.deepcopy(self.contract)
                changed[name] = None
                before = dict(self.io.calls)
                with self.assertRaisesRegex(ValueError, 'EXACT_PREDECESSOR_CONTRACT'):
                    c.collect(self.policy,self.io,predecessor=changed)
                self.assertEqual(self.io.calls, before)

    def test_old_inner_and_each_fixed_successor_presence_refuse(self):
        for name in (cs.OLD_INNER, cs.NEW_OUTER, cs.NEW_INNER):
            with self.subTest(name=name):
                path = c.TRANSACTION + '/' + name
                self.io.present.add(path)
                with self.assertRaisesRegex(ValueError, 'PREDECESSOR_FIXED_ABSENCES'):
                    self.collect()
                self.io.present.remove(path)

    def test_any_extra_or_missing_transaction_file_refuses(self):
        extra = c.TRANSACTION + '/unreviewed.json'
        self.io.add(extra, b'{}\n')
        with self.assertRaisesRegex(ValueError, 'TRANSACTION_INVENTORY_CHANGED'):
            self.collect()
        del self.io.raw[extra]; del self.io.meta[extra]
        missing = c.TRANSACTION + '/prerequisites.json'
        del self.io.raw[missing]
        with self.assertRaises(KeyError): self.collect()

    def test_no_policy_rewriting_permitted(self):
        self.policy['files'][self.old_path] = {k:self.io.meta[self.old_path][k] for k in ('sha256','uid','gid','mode')}
        self.policy['transaction_inventory'][cs.OLD_OUTER] = c.sha(self.raw)
        with self.assertRaisesRegex(ValueError, 'UNMODIFIED_HISTORICAL_POLICY'):
            self.collect()

    def test_exact_raw_and_full_metadata_mutations_refuse(self):
        original = self.io.raw[self.old_path]
        self.io.raw[self.old_path] = original + b' '
        with self.assertRaisesRegex(ValueError, 'PREDECESSOR_BYTES'): self.collect()
        self.io.raw[self.old_path] = original
        for key, value in (('uid',1),('gid',1),('mode',0o644),('nlink',2),('size',0),
                           ('ino',0),('sha256','f'*64),('kind','LINK')):
            with self.subTest(key=key):
                old = self.io.meta[self.old_path][key]
                self.io.meta[self.old_path][key] = value
                with self.assertRaises(ValueError): self.collect()
                self.io.meta[self.old_path][key] = old
        del self.io.meta[self.old_path]['mtime_ns']
        with self.assertRaisesRegex(ValueError, 'FILE_METADATA_KEYS'): self.collect()

    def test_ancestry_authority_and_acl_mutations_refuse(self):
        for name in c._predecessor_ancestors():
            for key,value in (('uid',1),('mode',0o777),('kind','LINK'),('default_acl','user:99:rwx\n')):
                with self.subTest(name=name,key=key):
                    old = self.io.dirs[name][key]; self.io.dirs[name][key] = value
                    with self.assertRaises(ValueError): self.collect()
                    self.io.dirs[name][key] = old

    def test_final_record_stamp_reread_detects_race(self):
        original = self.io.read
        calls = [0]
        def read(name, **kwargs):
            raw,meta = original(name,**kwargs)
            if name == self.old_path:
                calls[0] += 1
                if calls[0] == 2: meta['ctime_ns'] += 1
            return raw,meta
        self.io.read = read
        with self.assertRaisesRegex(ValueError, 'RECORD_OR_ANCESTRY_RACE'): self.collect()

    def test_final_ancestor_reread_detects_race(self):
        original = self.io.directory
        calls = [0]
        def directory(name):
            result = original(name)
            if name == '/var':
                calls[0] += 1
                if calls[0] == 2: result['ino'] += 1
            return result
        self.io.directory = directory
        with self.assertRaisesRegex(ValueError, 'RECORD_OR_ANCESTRY_RACE'): self.collect()

    def test_final_fixed_new_name_absence_reread_detects_race(self):
        original = self.io.absent
        calls = [0]
        def absent(name):
            if name == c.TRANSACTION+'/'+cs.NEW_INNER:
                calls[0] += 1
                if calls[0] == 2: return False
            return original(name)
        self.io.absent = absent
        with self.assertRaisesRegex(ValueError, 'PREDECESSOR_FIXED_ABSENCES'): self.collect()

    def test_final_old_original_file_inventory_and_absence_checks_remain(self):
        original = self.io.writers
        calls = [0]
        def writers(policy, paths):
            result = original(policy, paths); calls[0] += 1
            if calls[0] == 2: self.io.meta[c.ACTIVE]['ctime_ns'] += 1
            return result
        self.io.writers = writers
        with self.assertRaisesRegex(ValueError, 'RETAINED_FILE_RACE'): self.collect()

    def test_comparison_allows_only_parent_size_and_times(self):
        for key in ('dev','ino','nlink'):
            with self.subTest(key=key):
                old=self.io.dirs[c.TRANSACTION][key]; self.io.dirs[c.TRANSACTION][key]+=1
                snapshot,evidence=self.collect()
                with self.assertRaisesRegex(ValueError, 'PARENT_STABLE_IDENTITY_DRIFT'):
                    self.reconcile(snapshot,evidence)
                self.io.dirs[c.TRANSACTION][key]=old

    def test_comparison_rejects_other_transaction_directory_stamps(self):
        name=next(name for name in self.io.dirs if name.startswith(c.TRANSACTION+'/'))
        self.io.dirs[name]['mtime_ns'] += 1
        with self.assertRaisesRegex(ValueError, 'OTHER_DIRECTORY_DRIFT'): self.reconcile()

    def test_comparison_rejects_original_retained_stamp_drift(self):
        self.io.meta[c.ACTIVE]['mtime_ns'] += 1
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_RETAINED_DRIFT'): self.reconcile()

    def test_comparison_rejects_forged_hidden_inventory_and_absence(self):
        for target in ('inventory','absence','proof','parent'):
            with self.subTest(target=target):
                snapshot,evidence=self.collect()
                if target=='inventory': evidence['retained']['transaction_inventory'].pop(self.old_path)
                elif target=='absence': snapshot['absent_paths'][cs.OLD_OUTER]=True
                elif target=='proof': evidence['retained']['predecessor']['record']['raw_sha256']='f'*64
                else: evidence['retained']['predecessor']['ancestors'][c.TRANSACTION]['ctime_ns']+=1
                snapshot['retained_resource_sha256']=d.digest(evidence['retained'])
                evidence['snapshot_sha256']=d.digest(snapshot)
                with self.assertRaises(ValueError): self.reconcile(snapshot,evidence)

    def test_comparison_rejects_original_snapshot_change_even_with_rehashed_proof(self):
        snapshot,evidence=self.collect()
        snapshot['cache_inventories'][next(iter(snapshot['cache_inventories']))]='f'*64
        evidence['snapshot_sha256']=d.digest(snapshot)
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_SNAPSHOT_DRIFT'): self.reconcile(snapshot,evidence)

    def test_original_writer_transient_digest_change_still_allowed(self):
        self.io.writer['processes']['fd_count'] += 3
        snapshot,evidence=self.collect()
        result=self.reconcile(snapshot,evidence)
        self.assertNotEqual(result['comparison_only_snapshot']['writer_exclusion']['evidence_sha256'],
                            self.historical_snapshot['writer_exclusion']['evidence_sha256'])

    def test_raw_schema_binding_and_state_mutations_reject_with_fixed_test_pins(self):
        for where in ('schema','binding','state','canonical'):
            with self.subTest(where=where):
                value=json.loads(self.raw.decode())
                if where=='schema': value['schema']=2
                elif where=='binding': value['binding']['review_id']+=1
                elif where=='state': value['state']['completed']=['stage_exact_release']
                changed=(packed(value) if where!='canonical' else self.raw[:-1])
                original=self.io.raw[self.old_path]
                self.io.raw[self.old_path]=changed
                with self.assertRaisesRegex(ValueError,'PREDECESSOR_BYTES'): self.collect()
                self.io.raw[self.old_path]=original


    def test_final_exact_inventory_reread_detects_addition(self):
        original=self.io.inventory; calls=[0]
        def inventory(name):
            result=original(name); calls[0]+=1
            if calls[0]==2: result[c.TRANSACTION+'/unexpected-final.json']=h('unexpected')
            return result
        self.io.inventory=inventory
        with self.assertRaisesRegex(ValueError,'DIRECTORY_OR_TRANSACTION_RACE'): self.collect()

    def test_final_old_inner_absence_reread_detects_creation(self):
        original=self.io.absent; calls=[0]
        def absent(name):
            if name==c.TRANSACTION+'/'+cs.OLD_INNER:
                calls[0]+=1
                if calls[0]>=3: return False
            return original(name)
        self.io.absent=absent
        with self.assertRaisesRegex(ValueError,'NEW_ATTEMPT_RACE'): self.collect()

    def test_production_semantic_validator_checks_each_no_phase_field(self):
        # Repin only the synthetic byte/state identities to reach each real
        # semantic check. This is not an interface available to production IO.
        cases={'stage':'ADMITTED','failed_stage':'OTHER','failed_phase':'phase',
            'failed_operation':'other','admission':'ADMITTED','receipt_status':'UNKNOWN',
            'completed':['one'],'phase_evidence':{'one':{}},'containment':[{}],
            'containment_status':'ATTEMPTED','secondary_errors':[{}],
            'interruption':'KeyboardInterrupt','automatic_retry':True,'legacy_restart':True,
            'historical_notification_replay':True,'prerequisite_replay':True}
        original_meta=copy.deepcopy(self.io.meta[self.old_path])
        for key,changed in cases.items():
            with self.subTest(key=key):
                value=json.loads(self.raw.decode()); value['state'][key]=changed
                raw=packed(value); self.io.raw[self.old_path]=raw
                self.io.meta[self.old_path].update(size=len(raw),sha256=c.sha(raw))
                with mock.patch.multiple(cs, PREDECESSOR_SIZE=len(raw),
                        PREDECESSOR_SHA256=c.sha(raw), PREDECESSOR_STATE_SHA256=c.sha(packed(value['state']))):
                    with self.assertRaisesRegex(ValueError,'PREDECESSOR_NO_PHASE_HOLD'):
                        c.collect(self.policy,self.io,predecessor=cs.predecessor_contract())
        self.io.raw[self.old_path]=self.raw; self.io.meta[self.old_path]=original_meta

    def test_production_semantic_validator_checks_envelope_binding_and_review(self):
        for key in ('schema','name','transaction_id','context_sha256','binding_hash','state_hash','review_id'):
            with self.subTest(key=key):
                value=json.loads(self.raw.decode())
                if key=='schema': value[key]=2
                elif key in ('name','transaction_id','context_sha256'): value[key]='wrong'
                elif key=='binding_hash': value['binding']['delta_sha256']=h('changed')
                elif key=='state_hash': value['state']['preflight_evidence']={'synthetic':'changed'}
                else: value['binding']['review_id']+=1
                raw=packed(value); self.io.raw[self.old_path]=raw
                self.io.meta[self.old_path].update(size=len(raw),sha256=c.sha(raw))
                pins={'PREDECESSOR_SIZE':len(raw),'PREDECESSOR_SHA256':c.sha(raw)}
                if key=='review_id': pins['PREDECESSOR_BINDING_SHA256']=d.digest(value['binding'])
                with mock.patch.multiple(cs,**pins):
                    with self.assertRaises(ValueError):
                        c.collect(self.policy,self.io,predecessor=cs.predecessor_contract())

    def test_historical_evidence_tampering_is_not_reconciled(self):
        snapshot,evidence=self.collect()
        self.historical_evidence['retained']['files'][c.ACTIVE]['mtime_ns']+=1
        with self.assertRaisesRegex(ValueError,'HISTORICAL_BINDING'):
            self.reconcile(snapshot,evidence)


class FrozenBaselineTests(unittest.TestCase):
    def test_all_256_archive_files_are_byte_identical(self):
        import tarfile
        archive=ROOT.parent/'b-resource-aggregate-fix-candidate/artifact/epoch7-kit-resourcebind.tar.gz'
        prefix='epoch7-recovery-candidate-r7-resourcebind/'
        compared=0
        with tarfile.open(str(archive),'r:gz') as handle:
            for member in handle.getmembers():
                if not member.isfile(): continue
                self.assertTrue(member.name.startswith(prefix))
                relative=member.name[len(prefix):]
                with open(str(ROOT/'baseline'/relative),'rb') as stored:
                    self.assertEqual(handle.extractfile(member).read(),stored.read(),relative)
                compared+=1
        self.assertEqual(compared,256)


if __name__ == '__main__':
    unittest.main()
