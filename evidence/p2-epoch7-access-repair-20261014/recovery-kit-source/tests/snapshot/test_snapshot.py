"""Synthetic fixtures only. Never creates or queries production host paths."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'recovery-design-candidate')]
import epoch7_snapshot as c
import epoch7_delta as d
import snapshot_io as io
import reviewed_scanner as reviewed


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


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.p,self.io=fixture()
        self.native_patch=native_pin_context(native_raws(self.io));self.native_patch.start()
    def tearDown(self): self.native_patch.stop()
    def collect(self): return c.collect(self.p,self.io)
    def alter(self,name,value):
        self.io.add(name,packed(value),**{k:self.io.meta[name][k] for k in ('uid','gid','mode')})
        self.p['files'][name]={k:self.io.meta[name][k] for k in ('sha256','uid','gid','mode')}
        if name.startswith(c.TRANSACTION+'/'):self.p['transaction_inventory'][name[len(c.TRANSACTION)+1:]]=c.sha(packed(value))
    def test_exact_snapshot_contract_and_private_evidence(self):
        s,e=self.collect();self.assertEqual(d.validate_snapshot(s,d.digest(s)),s)
        self.assertEqual(len(s['targets']),24);self.assertEqual(sum(r['kind']=='FILE' for r in s['targets'].values()),22)
        self.assertEqual(d.digest(e['retained']),s['retained_resource_sha256']);self.assertEqual(len(e['retained']['database_sets']),3)
        self.assertEqual(e['retained']['native_binding_transition'],c.validate_native_transition(*native_raws(self.io)))
        self.assertEqual(e['install_admission'],'NOT_GRANTED')
    def test_full_stamp_metadata_emitted(self):
        s,e=self.collect()
        for row in list(s['targets'].values())+[s['generation']]:
            self.assertTrue({'size','mtime_ns','ctime_ns','nlink'}<=set(row))
    def test_both_attempts_and_policy_publications_absent(self):
        s,e=self.collect()
        for n in ('epoch7-recovery-execution.json','epoch7-recovery-sequence.json','epoch7-owner-identity-publication.json','epoch7-server-identity-publication.json'):
            self.assertIs(s['absent_paths'][n],True)
    def test_public_output_contains_only_digests_and_fixed_status(self):
        s,e=self.collect();out=c.public_summary(s,e)
        self.assertEqual(set(out),{'schema','snapshot_sha256','evidence_sha256','install_admission','production_acceptance','target_mutations'})
        self.assertNotIn('private fixture',json.dumps([s,e,out]));self.assertNotIn('FIXTURE_SQLITE',json.dumps([s,e,out]))
    def test_missing_expected_pin(self):
        self.p['files'].pop(c.ACTIVE)
        with self.assertRaisesRegex(ValueError,'MISSING_EXPECTED'):self.collect()
        self.assertFalse(self.io.events)
    def test_unmeasured_ancestor(self):
        self.p['directories'].pop('/etc')
        with self.assertRaisesRegex(ValueError,'UNMEASURED'):self.collect()
    def test_bad_hash_before_observation(self):
        self.p['files'][c.ACTIVE]['sha256']=None
        with self.assertRaisesRegex(ValueError,'HASH'):self.collect()
    def test_wrong_host(self):
        self.io.identity=lambda:{'hostname':'other','euid':0}
        with self.assertRaisesRegex(ValueError,'HOST'):self.collect()
    def test_stale_file_pin(self):
        self.io.meta[c.ACTIVE]['sha256']=h('changed')
        with self.assertRaisesRegex(ValueError,'FILE_PIN'):self.collect()
    def test_receipt_permissions_and_hardlinks(self):
        for key,value in (('uid',1),('mode',0o644),('nlink',2)):
            p,f=fixture();f.meta[c.TRANSACTION+'/epoch5-recovery-execution.json'][key]=value
            with self.assertRaises(ValueError):c.collect(p,f)
    def test_all_absence_members_block(self):
        for n in d.ABSENT_EFFECT_PATHS:
            p,f=fixture();f.present.add(c.TRANSACTION+'/'+n)
            with self.assertRaisesRegex(ValueError,'UNCLASSIFIED_ATTEMPT'):c.collect(p,f)
    def test_extra_transaction_file_blocks(self):
        self.io.add(c.TRANSACTION+'/unknown.json',b'{}')
        with self.assertRaisesRegex(ValueError,'TRANSACTION_INVENTORY'):self.collect()
    def test_policy_or_socket_or_plugin_presence_blocks(self):
        for name in c.ADDITIVE_PATHS|c.SOCKET_PATHS|{c.PLUGIN_PATH}:
            p,f=fixture();f.present.add(name)
            with self.assertRaisesRegex(ValueError,'UNCLASSIFIED_PLUGIN'):c.collect(p,f)
    def test_activation_hash_chain_checked(self):
        bad=self.io.raw[c.EPOCHS].replace(b'"seq":1',b'"seq":9')
        self.io.add(c.EPOCHS,bad,mode=0o644);self.p['files'][c.EPOCHS]['sha256']=c.sha(bad)
        with self.assertRaisesRegex(ValueError,'EPOCH_JOURNAL'):self.collect()
    def test_activation_journal_reconciliation_required(self):
        active=c.decode(self.io.raw[c.ACTIVE]);active['instance']='cccccccc-cccc-4ccc-8ccc-cccccccccccc';self.alter(c.ACTIVE,active)
        with self.assertRaisesRegex(ValueError,'RECONCILIATION'):self.collect()
    def test_old_epoch_is_not_relabelled(self):
        active=c.decode(self.io.raw[c.ACTIVE]);active['epoch']=5;self.alter(c.ACTIVE,active)
        with self.assertRaisesRegex(ValueError,'EXACT_PREPARED'):self.collect()
    def test_consumed_attempt_approval_exact(self):
        x=c.decode(self.io.raw[c.TRANSACTION+'/epoch5-recovery-execution.json']);x['authorization']['review_id']=1
        self.alter(c.TRANSACTION+'/epoch5-recovery-execution.json',x)
        with self.assertRaisesRegex(ValueError,'CONSUMED'):self.collect()
    def test_database_logical_identity_required(self):
        self.p['databases'][d.DB]['logical_manifest_sha256']=h('wrong')
        with self.assertRaisesRegex(ValueError,'DATABASE_LOGICAL'):self.collect()
    def test_unexpected_sidecar_blocks(self):
        self.io.present.add(d.DB+'-wal')
        with self.assertRaisesRegex(ValueError,'SIDECAR'):self.collect()
    def test_tls_ready_required(self):
        name=c.TRANSACTION+'/tls-lifecycle.json';x=c.decode(self.io.raw[name]);x['state']='HOLD';self.alter(name,x)
        with self.assertRaisesRegex(ValueError,'TLS_READY'):self.collect()
    def test_tls_tree_and_certificate_bound(self):
        self.io.tls=lambda p:{'tree_fingerprint_sha256':h('wrong'),'certificate_sha256':h('cert')}
        with self.assertRaisesRegex(ValueError,'TLS_RETAINED'):self.collect()
    def test_sandbox_restored_required(self):
        name=c.TRANSACTION+'/sandbox-profile.json';x=c.decode(self.io.raw[name]);x['state']='APPLIED';self.alter(name,x)
        with self.assertRaisesRegex(ValueError,'SANDBOX'):self.collect()
    def test_native_identity_fields_cannot_change(self):
        x=c.decode(self.io.raw[c.NATIVE]);x['gatewayIdentity']['fixture']='changed';self.alter(c.NATIVE,x)
        with self.assertRaisesRegex(ValueError,'NATIVE_OWNED_REBIND_HASHES'):self.collect()
    def test_bootstrap_temporary_blocks(self):
        self.io.present.add(c.NATIVE+'.tmp')
        with self.assertRaisesRegex(ValueError,'BOOTSTRAP'):self.collect()
    def test_two_writer_scans_and_full_file_reread(self):
        self.collect();self.assertEqual(self.io.events.count('writers'),2)
        self.assertTrue(all(self.io.calls[n]>=2 for n in self.p['files']))
    def test_late_file_inode_change_blocks(self):
        old=self.io.read
        def read(name,maximum=16777216):
            raw,row=old(name,maximum)
            if name==c.ACTIVE and self.io.calls[name]>1:row['ino']+=1
            return raw,row
        self.io.read=read
        with self.assertRaisesRegex(ValueError,'RETAINED_FILE_RACE'):self.collect()
    def test_writer_observation_drift_blocks(self):
        count=[0]
        def writer(p,paths):
            count[0]+=1;value=writer_fixture();value['processes']['process_identity_sha256']=h(str(count[0]));return value
        self.io.writers=writer
        with self.assertRaisesRegex(ValueError,'WRITER_OBSERVATION'):self.collect()
    def test_missing_writer_evidence_blocks(self):
        self.io.writers=lambda p,paths:{}
        with self.assertRaisesRegex(ValueError,'WRITER_EVIDENCE_KEYS'):self.collect()
    def test_wrong_generation_acl_blocks(self):
        self.io.dirs[d.GENERATION]['access_acl']+='user:1002:r-x\n'
        with self.assertRaisesRegex(ValueError,'ACL'):self.collect()
    def test_reread_permission_error_propagates(self):
        self.io.inventory=lambda p:(_ for _ in ()).throw(PermissionError())
        with self.assertRaises(PermissionError):self.collect()
    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
            with self.assertRaises(ValueError):c.decode(raw)


class DescriptorTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp(prefix='snapshot-fixture-',dir=str(HERE/'tests'))
        os.chmod(self.root,0o700);os.mkdir(self.root+'/safe',0o700)
        self.pins={n:{'uid':os.getuid(),'gid':os.getgid(),'mode':0o700} for n in ('/','/safe')}
        self.reader=io.DescriptorReader(self.pins,self.root)
        with open(self.root+'/safe/file','wb') as f:f.write(b'fixture')
        os.chmod(self.root+'/safe/file',0o600)
    def tearDown(self):shutil.rmtree(self.root)
    def test_regular_read_full_stamp(self):
        raw,m=self.reader.read('/safe/file');self.assertEqual(raw,b'fixture');self.assertEqual(m['sha256'],c.sha(raw));self.assertEqual(m['nlink'],1)
    def test_file_info_does_not_read_content(self):
        with mock.patch.object(io.os,'read',side_effect=AssertionError('content read forbidden')):
            row=self.reader.file_info('/safe/file')
        self.assertEqual(row['size'],7);self.assertNotIn('sha256',row)
    def test_file_info_rejects_alias_and_hardlink(self):
        os.symlink('file',self.root+'/safe/link')
        with self.assertRaises(ValueError):self.reader.file_info('/safe/link')
        os.link(self.root+'/safe/file',self.root+'/safe/hard')
        with self.assertRaises(ValueError):self.reader.file_info('/safe/file')
    def test_file_info_rejects_unsafe_mode(self):
        os.chmod(self.root+'/safe/file',0o666)
        with self.assertRaises(ValueError):self.reader.file_info('/safe/file')
    def test_symlink_leaf_rejected(self):
        os.symlink('file',self.root+'/safe/link')
        with self.assertRaises(ValueError):self.reader.read('/safe/link')
    def test_symlink_ancestor_rejected(self):
        os.symlink('safe',self.root+'/alias');self.pins['/alias']=self.pins['/safe']
        with self.assertRaises(OSError):self.reader.read('/alias/file')
    def test_hardlink_rejected(self):
        os.link(self.root+'/safe/file',self.root+'/safe/hard')
        with self.assertRaises(ValueError):self.reader.read('/safe/file')
    def test_wrong_directory_pin(self):
        self.pins['/safe']['mode']=0o755
        with self.assertRaisesRegex(ValueError,'ANCESTOR'):self.reader.read('/safe/file')
    def test_bound_rejected(self):
        with self.assertRaises(ValueError):self.reader.read('/safe/file',maximum=2)
    def test_absence_and_dangling_link(self):
        self.assertTrue(self.reader.absent('/safe/missing'));os.symlink('missing',self.root+'/safe/dangling')
        self.assertFalse(self.reader.absent('/safe/dangling'));self.assertTrue(self.reader.absent('/safe/missing/child'))
    def test_directory_base_acl(self):
        row=self.reader.directory('/safe');self.assertEqual(row['access_acl'],'user::rwx\ngroup::---\nother::---\n')
    def test_read_io_error_propagates(self):
        with mock.patch.object(io.os,'read',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.reader.read('/safe/file')
    def test_detects_replacement_during_read(self):
        original=io.os.read;once=[False]
        def changed(fd,count):
            data=original(fd,count)
            if not once[0]:
                once[0]=True;os.rename(self.root+'/safe/file',self.root+'/safe/old')
                with open(self.root+'/safe/file','wb') as f:f.write(b'fixture')
                os.chmod(self.root+'/safe/file',0o600)
            return data
        with mock.patch.object(io.os,'read',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'FILE_.*RACE'):self.reader.read('/safe/file')
    def test_unknown_acl_fails_closed(self):
        with mock.patch.object(io,'xattr',return_value=b'fixtureacl'):
            with self.assertRaisesRegex(ValueError,'ACL'):self.reader.read('/safe/file')
    def test_no_production_fallback(self):
        with self.assertRaisesRegex(ValueError,'FIXED_HOST_ROOT'):io.collect_host('/missing',h('missing'))


class ReuseTests(unittest.TestCase):
    def test_selected_functions_identical_to_frozen_sources(self):
        manifest=json.loads((HERE/'reviewed_sources.json').read_text())
        for filename,row in manifest.items():
            original=(ROOT/row['source']).read_bytes();self.assertEqual(c.sha(original),row['source_sha256'])
            def funcs(raw):return {n.name:ast.dump(n) for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)}
            old,new=funcs(original),funcs((HERE/filename).read_bytes())
            for name in row['functions']:self.assertEqual(old[name],new[name])
    def test_actual_cache_verifier_runtime_imports(self):
        import marshal,struct,types
        source=b'fixture_value = 1\n';relative='stage1/fixture.py'
        filename='/opt/xuanjun-control-releases/.integration-'+'a'*16+'/'+relative
        code=compile(source,filename,'exec',dont_inherit=True,optimize=0)
        data=importlib.util.MAGIC_NUMBER+struct.pack('<II',123,len(source))+marshal.dumps(code)
        if sys.version_info[:2]==(3,6):
            self.assertEqual(reviewed.verify_cache_bytes(data,source,relative,types.SimpleNamespace(st_mtime=123)),
                             filename[:-len('/'+relative)])
        else:
            with self.assertRaisesRegex(ValueError,'CPYTHON36'):
                reviewed.verify_cache_bytes(data,source,relative,types.SimpleNamespace(st_mtime=123))
    def test_no_old_capture_resume_or_pins(self):
        source=(HERE/'reviewed_scanner.py').read_text()
        for bad in ('def snapshot(', 'def resume(', 'def capture_host(', 'DB_SHA =', 'MANIFEST_SHA =', 'urllib'):
            self.assertNotIn(bad,source)
    def test_core_has_no_subprocess_network_sqlite_or_effect_api(self):
        source=(HERE/'epoch7_snapshot.py').read_text()
        for bad in ('subprocess.', 'socket.', 'sqlite3.', 'os.open(', 'os.chmod(', 'os.rename(', 'os.unlink('):self.assertNotIn(bad,source)
    def test_no_cli_service_mutation_or_acme(self):
        source=(HERE/'snapshot_io.py').read_text()
        for bad in ("'start'", "'stop'", "'restart'", "'daemon-reload'", "'certbot'", "'renew'", 'O_CREAT', 'O_TRUNC', 'O_WRONLY'):
            self.assertNotIn(bad,source)
    def test_private_db_copy_manifest_without_production_open(self):
        import sqlite3
        root=tempfile.mkdtemp(prefix='db-fixture-',dir=str(HERE/'tests'))
        try:
            name=root+'/fixture.sqlite'
            with sqlite3.connect(name) as db:db.execute('create table fixture(v text)');db.execute("insert into fixture values('private')")
            raw=pathlib.Path(name).read_bytes()
            value=reviewed.manifest_from_copy(raw,io.reviewed_database.database_manifest)
            self.assertEqual(value['sha256'],c.sha(raw));self.assertEqual(value['counts']['fixture'],1)
            self.assertNotIn('private',json.dumps(value))
        finally:shutil.rmtree(root)


class ObservationTests(unittest.TestCase):
    def setUp(self):
        import observe_epoch7 as observation
        self.o=observation;self.patches=[]
        payloads={'stage1/source_%03d.py'%i:b'x=1\n' for i in range(102)}
        self.manifests=[]
        for i in range(3):
            raw=packed({'fixture_version':i,'files':{n:c.sha(v) for n,v in payloads.items()},
                        'rendering':{'identity_files':[]}})
            self.manifests.append((c.sha(raw),raw))
        self.patch(d,'OLD_MANIFEST',self.manifests[-1][0])
        self.patch(observation,'RELEASE_MANIFESTS',tuple(x[0] for x in self.manifests))
        self.p,self.f=fixture();self.f.pins=copy.deepcopy(self.p['directories']);self.f.policy={}
        native_patch=native_pin_context(native_raws(self.f));native_patch.start();self.patches.append(native_patch)
        self.patch(observation,'ORIGINAL_PLAN_SHA',c.sha(self.f.raw[c.PLAN]))
        baseline=packed({'sections':{'remaining_control_entry_inventory':{'scheduler_metadata':[], 'registered_control_units':{}}}})
        self.f.add(observation.READINESS,baseline);self.patch(observation,'READINESS_SHA',c.sha(baseline))
        boots=[]
        for name in sorted(observation.BOOTSTRAP):
            if name!=c.NATIVE:
                uid=1003 if name.endswith('github-intake-token') else 1004
                self.f.add(name,b'private bootstrap fixture',uid=uid,gid=1003 if uid==1003 else 1006)
            m=self.f.meta[name]
            boots.append(dict(target=name,temp=name+'.tmp',state='PUBLISHED',owner_uid=m['uid'],group_gid=m['gid'],
                **{k:m[k] for k in ('sha256','dev','ino','mode')}))
        self.f.add(c.TRANSACTION+'/bootstrap-files.json',packed({'schema':1,'files':boots}))
        for digest,raw in self.manifests:
            root='/opt/xuanjun-control-releases/integration-'+digest[:16]
            self.f.add(root+'/INTEGRATION_MANIFEST.json',raw,mode=0o444)
            for rel,data in payloads.items():self.f.add(root+'/'+rel,data,mode=0o444)
            self.f.add(root+'/stage1/__pycache__/source_000.cpython-36.pyc',b'cache fixture',mode=0o444)
        self.f.cache_staging=lambda *args:'/opt/xuanjun-control-releases/.integration-'+'a'*16
        self.f.scheduler_inventory=lambda root:{}
        self.f._manager=lambda:{'fixture':True}
        self.f.add('/usr/lib/systemd/systemd',b'fixture systemd',mode=0o755)
        names=sorted(n for n in c.WRITER_UNITS if n.startswith(('xj-','xuanjun-')))
        self.f.command=lambda label,args:(''.join(n+' disabled\n' for n in names)).encode()
        for name in names:
            leaf='/etc/systemd/system/'+name
            if leaf not in self.f.raw and leaf not in c.LEGACY_MASKS:self.f.add(leaf,b'fixture unit',mode=0o644)
        self.f.mask=lambda name:dict(kind='MASK',link='/dev/null',uid=0,gid=0,dev=7,ino=3000+names.index(os.path.basename(name)),mode=0o777,nlink=1,size=9,mtime_ns=11,ctime_ns=12)
        for name in c.PUBLISHERS:self.f.dirs[name]=dict(self.f.dirs[d.GENERATION],path=name,uid=1003,gid=1003,mode=0o700)
        old=self.f.read
        def read(name,maximum=16777216):
            parent=os.path.dirname(name)
            while parent!='/':
                self.f.pins.setdefault(parent,{'uid':0,'gid':0,'mode':0o700 if parent==c.TRANSACTION or parent.startswith(c.TRANSACTION+'/') else 0o755})
                parent=os.path.dirname(parent)
            return old(name,maximum)
        self.f.read=read
    def patch(self,obj,name,value):
        p=mock.patch.object(obj,name,value);p.start();self.patches.append(p)
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def test_missing_hashes_are_measured_in_one_observation(self):
        value=self.o.observe_with_io(self.f)
        self.assertEqual(value['kind'],'EPOCH7_OBSERVATION_ONLY_UNREVIEWED')
        self.assertEqual(value['independent_acceptance'],'PENDING')
        self.assertEqual(value['install_admission'],'NOT_GRANTED')
        d.validate_snapshot(value['snapshot'],value['snapshot_sha256'])
        self.assertEqual(value['policy']['files'][c.NATIVE]['sha256'],c.sha(self.f.raw[c.NATIVE]))
    def test_historical_plan_pin_is_not_optional(self):
        self.patch(self.o,'ORIGINAL_PLAN_SHA',h('unknown'))
        with self.assertRaisesRegex(ValueError,'ORIGINAL_PLAN_PIN'):self.o.measured_policy(self.f)
    def test_historical_manifest_pin_is_not_learned_from_current_bytes(self):
        root='/opt/xuanjun-control-releases/integration-'+self.manifests[0][0][:16]
        self.f.meta[root+'/INTEGRATION_MANIFEST.json']['sha256']=h('changed')
        with self.assertRaisesRegex(ValueError,'HISTORICAL_MANIFEST'):self.o.measured_policy(self.f)
    def test_unknown_release_file_blocks(self):
        root='/opt/xuanjun-control-releases/integration-'+self.manifests[0][0][:16]
        self.f.add(root+'/unknown.py',b'unknown',mode=0o444)
        with self.assertRaisesRegex(ValueError,'UNCLASSIFIED_RELEASE'):self.o.measured_policy(self.f)
    def test_unknown_control_unit_blocks(self):
        previous=self.f.command;self.f.command=lambda l,a:previous(l,a)+b'xuanjun-unreviewed.service enabled\n'
        with self.assertRaisesRegex(ValueError,'CONTROL_UNIT_SET'):self.o.measured_policy(self.f)
    def test_unknown_bootstrap_path_blocks(self):
        rows=c.decode(self.f.raw[c.TRANSACTION+'/bootstrap-files.json']);rows['files'][0]['target']='/etc/shadow'
        self.f.add(c.TRANSACTION+'/bootstrap-files.json',packed(rows))
        with self.assertRaisesRegex(ValueError,'BOOTSTRAP_SCOPE'):self.o.measured_policy(self.f)
    def test_new_staged_sidecar_is_not_adopted(self):
        self.f.add(d.DB+'-wal',b'')
        with self.assertRaisesRegex(ValueError,'UNCLASSIFIED_DB_SIDECAR'):self.o.measured_policy(self.f)
    def test_no_host_fallback_or_execution(self):
        with self.assertRaisesRegex(ValueError,'FIXED_HOST_ROOT'):self.o.observe_host()
    def test_native_historical_before_release_stays_338e(self):
        self.assertEqual(c.RETAINED_NATIVE_RELEASE[:16],'338e488c4203e23d')
        self.assertNotEqual(c.RETAINED_NATIVE_RELEASE,d.OLD_MANIFEST)
    def test_wrong_native_after_bytes_rejected_even_when_policy_repin_attempted(self):
        current=c.decode(self.f.raw[c.NATIVE]);current['ledger']['pythonSha256']=h('unknown interpreter')
        self.f.add(c.NATIVE,packed(current),mode=0o644)
        with self.assertRaises(ValueError):self.o.measured_policy(self.f)
    def test_private_output_requires_new_fixed_scope_path(self):
        with self.assertRaisesRegex(ValueError,'OUTPUT_SCOPE'):self.o.persist_private('/tmp/not-authorized.json',{})
    def test_observation_does_not_contain_final_candidate_manifest(self):
        value=self.o.observe_with_io(self.f)
        self.assertEqual(value['snapshot']['activation']['epoch'],7)
        self.assertNotIn('31bdef45b0a4b8980cf4544af5381a215bea8e5901caccca014cf0aa9a659846',json.dumps(value))


class NativeComponentTests(unittest.TestCase):
    def setUp(self):
        import types
        self.uid=mock.patch.object(io.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=1002));self.uid.start()
        client='/etc/xuanjun-development/p2-native-ledger-client.json'
        self.old='/opt/xuanjun-control-releases/integration-'+c.RETAINED_NATIVE_RELEASE[:16]+'/stage1/native_ledger_bridge.py'
        self.live='/opt/xuanjun-control-releases/integration-'+d.OLD_MANIFEST[:16]+'/stage1/native_ledger_bridge.py'
        gateway={'user':'xuanjun_dev','exe':'/home/xuanjun_dev/bin/node','sha256':h('node'),'cgroup':'/system.slice/xuanjun-uk-openclaw.service'}
        self.before={'ledger':{'python':'/usr/bin/python3','pythonSha256':h('python'),'bridge':self.live,'config':client,
                              'files':{self.live:h('livebridge'),client:h('oldclient')}},'gatewayIdentity':gateway}
        self.current=copy.deepcopy(self.before);self.current['ledger'].update(bridge=self.live,files={self.live:h('livebridge'),client:h('currentclient')})
        self.rows={'/usr/bin/python3':(h('python'),0),gateway['exe']:(h('node'),1002),self.old:(h('oldbridge'),0),
                   self.live:(h('livebridge'),0),client:(h('currentclient'),0)}
        class Proxy:pass
        self.proxy=Proxy();self.proxy.read=lambda name,maximum=0:(b'',{'sha256':self.rows[name][0],'uid':self.rows[name][1]})
        self.proxy.executable_reference=lambda name:{'reference_path':name,'links':[],
            'final':{'path':name,'sha256':self.rows[name][0],'format':'ELF',
                     'metadata':self.proxy.read(name)[1]}}
    def tearDown(self):self.uid.stop()
    def run_check(self):return io.LocalReadOnlyIO.native_identity(self.proxy,self.before,self.current)
    def test_retained_old_client_hash_does_not_masquerade_as_current_client(self):
        result=self.run_check();self.assertEqual(result['retained_client_sha256'],h('oldclient'))
        self.assertEqual(result['current_client_sha256'],h('currentclient'))
        self.assertEqual(result['identity_admission'],'NOT_GRANTED')
    def test_actual_controller_shape_has_no_gateway_identity(self):
        self.current.pop('gatewayIdentity')
        self.current.update(contextFiles={},contextPath='/fixture',agentIds={},engine={},workspaceRoot='/fixture')
        self.assertEqual(self.run_check()['identity_admission'],'NOT_GRANTED')
    def test_wrong_retained_bridge_version(self):
        self.before['ledger']['bridge']=self.old
        with self.assertRaisesRegex(ValueError,'RETAINED_AND_CURRENT'):self.run_check()
    def test_wrong_current_config_hash(self):
        self.current['ledger']['files'][self.current['ledger']['config']]=h('oldclient')
        with self.assertRaisesRegex(ValueError,'COMPONENT_PIN'):self.run_check()
    def test_changed_gateway_or_interpreter_not_allowed(self):
        self.current['ledger']['pythonSha256']=h('changed')
        with self.assertRaisesRegex(ValueError,'RETAINED_AND_CURRENT'):self.run_check()


class OutputAndManagerTests(unittest.TestCase):
    def test_fixed_private_output_exclusive_and_digest_only(self):
        import observe_epoch7 as observation
        root=tempfile.mkdtemp(prefix='observation-output-',dir=str(HERE/'tests'));os.chmod(root,0o700)
        try:
            with mock.patch.object(c,'CAND',root), mock.patch.object(observation,'authority',
                    side_effect=lambda logical,info,declared=None:{k:io.metadata(info)[k] for k in ('uid','gid','mode')}):
                name=root+'/epoch7-observation-'+('a'*16)+'.private.json'
                result={'schema':1,'install_admission':'NOT_GRANTED','sha256':h('fixture')}
                self.assertEqual(observation.persist_private(name,result),c.sha(packed(result)))
                self.assertEqual(stat.S_IMODE(os.stat(name).st_mode),0o600)
                with self.assertRaises(FileExistsError):observation.persist_private(name,result)
                self.assertEqual(pathlib.Path(name).read_bytes(),packed(result))
        finally:shutil.rmtree(root)
    def test_writer_dict_cannot_replace_measured_unit_inventory(self):
        with self.assertRaisesRegex(ValueError,'WRITER_EVIDENCE_KEYS'):c.validate_writers({'all_stopped':True})
    def test_busy_cgroup_rejected(self):
        value=writer_fixture();unit=sorted(c.WRITER_UNITS)[0]
        value['units'][unit]['cgroup_entries']={'/sys/fs/cgroup/systemd/system.slice/'+unit+'/cgroup.procs':h('999\n')}
        with self.assertRaisesRegex(ValueError,'CGROUP_NOT_EMPTY'):c.validate_writers(value)
    def test_manager_is_observed_per_session_not_fixed_bootfile(self):
        source=(HERE/'snapshot_io.py').read_text()
        self.assertIn("'/proc/sys/kernel/random/boot_id'",source)
        self.assertIn("'/run/systemd/private'",source)
        self.assertIn("'/run/dbus/system_bus_socket'",source)
        self.assertNotIn('expected_boot_id',source)
    def test_real_v4_identity_render_roundtrip(self):
        root=ROOT/'p2-epoch5-repair/runtime-v4-extracted/xuanjun-p2-package'
        raw=(root/'deploy/integration-manifest.json').read_bytes();manifest=c.decode(raw);digest=c.sha(raw)
        namespace={'__name__':'fixture_pinned_renderer'}
        renderer=(root/'scripts/uk-integration-install.py').read_bytes()
        self.assertEqual(c.sha(renderer),'943f4d04861d8b580008af457d90187622a9de2d1c8cd66c93a721b8ac2be0f3')
        exec(compile(renderer,'<fixture pinned renderer>','exec'),namespace)
        for name in manifest['rendering']['identity_files']:
            original=(root/name).read_bytes();rendered=namespace['render_identity_bytes'](name,original,digest,manifest)
            restored=rendered.replace(('integration-'+digest[:16]).encode(),b'@@RELEASE_DIRECTORY@@').replace(digest.encode(),b'@@ARTIFACT_SHA256@@')
            self.assertEqual(original,restored)


if __name__=='__main__':unittest.main()
