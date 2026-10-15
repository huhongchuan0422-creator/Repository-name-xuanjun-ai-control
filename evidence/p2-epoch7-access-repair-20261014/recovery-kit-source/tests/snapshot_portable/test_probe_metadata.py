"""Read-only ingredient fixtures. No UK paths, commands or service effects."""
import copy
import hashlib
import json
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent/'recovery-design-candidate'), str(HERE.parent/'isolated-probe-candidate')]
import epoch7_snapshot as c
import epoch7_delta as d
import probe_metadata as p
import observe_epoch7 as observe
import snapshot_io

ROOT = c.CAND+'/epoch7-recovery-candidate-r2/xuanjun-p2-package'
try:
    import activation_control as staged_activation
except ImportError:
    LOCAL_RUNTIME = HERE.parent/'runtime-build-101b465c'/'xuanjun-p2-package'
else:
    LOCAL_RUNTIME = pathlib.Path(staged_activation.__file__).resolve().parents[1]

def packed(value): return d.canonical(value)+b'\n'
def h(value): return hashlib.sha256(value.encode('utf-8')).hexdigest()

class Fake(object):
    def __init__(self):
        self.files={};self.metadata={};self.reads=[];self.infos=[]
        self.host=c.HOST+'.example.invalid'
        self.python='/usr/bin/python3.6'
        self.manager={'binary_path':'/usr/lib/systemd/systemd','binary_sha256':h('manager'),
            'boot_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','pid':1,'starttime':19,
            'binary_identity':[3,23],'channels':{'fixture':{'uid':0,'gid':0}}}
        spec={
            'ledger':('xuanjun-dispatcher',1003,'xuanjun-control-db',1006,{'xuanjun-dispatcher':1003}),
            'broker':('root',0,'root',0,{'xuanjun-ledger-client':1007}),
            'dashboard':('xuanjun-callback',1004,'xuanjun-control-db',1006,{'xuanjun-ledger-client':1007}),
            'callback':('xuanjun-callback',1004,'xuanjun-control-db',1006,{'xuanjun-ledger-client':1007}),
            'native':('xuanjun_dev',1002,'xuanjun_dev',1002,{'docker':994,'xuanjun-ledger-client':1007})}
        self.nss={'profiles':{},'existing_accounts':{}}
        for role,(user,uid,group,gid,extras) in spec.items():
            self.nss['profiles'][role]={'user':user,'uid':uid,'group':group,'gid':gid,
                'supplementary_groups':extras,'protect_home':'read-only' if role=='native' else 'yes'}
            self.nss['existing_accounts'][user]={'uid':uid,'primary_gid':uid,'global_group_gids':[uid]}
        self.add(p.MACHINE_ID,b'0123456789abcdef0123456789abcdef\n',mode=0o444)
        self.add(self.python,b'fixture python executable',mode=0o755)
        self.add('/usr/bin/systemctl',b'fixture systemctl executable',mode=0o755)
        self.settings={'agentIds':['fixture'],'engine':'openclaw','workspaceRoot':'/fixture',
            'ledger':{'python':'/usr/bin/python3','pythonSha256':c.sha(self.files[self.python])},
            'contextPath':p.SDK_PREFIX+'context.py','contextFiles':{}}
        for name in ('context.py','executor.py','identity.py','lib.py','util.py'):
            name=p.SDK_PREFIX+name;self.add(name,('sdk fixture '+name).encode(),uid=1002,gid=1002)
            self.settings['contextFiles'][name]={'sha256':c.sha(self.files[name]),'uid':1002}
        self.bind()
        for name in ('deploy/integration-manifest.json',)+p.CANDIDATE_SOURCES:
            self.add(ROOT+'/'+name,(LOCAL_RUNTIME/name).read_bytes(),mode=0o444)
    def add(self,name,raw,uid=0,gid=0,mode=0o600):
        self.files[name]=raw;self.metadata[name]={'kind':'FILE','uid':uid,'gid':gid,'mode':mode,
            'nlink':1,'size':len(raw),'sha256':c.sha(raw),'dev':3,'ino':100+len(self.metadata),
            'mtime_ns':11,'ctime_ns':12}
    def bind(self):
        self.add(p.CONTROLLER,packed(self.settings),uid=0,gid=1002,mode=0o640)
        rows=[dict(target=n,rendered_sha256=h(n),uid=0,gid=0,mode=0o644) for n in sorted(d.TARGETS)]
        row=next(r for r in rows if r['target']==p.CONTROLLER)
        row.update(rendered_sha256=c.sha(self.files[p.CONTROLLER]),uid=0,gid=1002,mode=0o640)
        self.add(p.PROVISION,packed(dict(schema=1,failure_policy='FENCE_STOP_RETAIN_NO_REPLAY',rollback_complete=False,targets=rows)))
    def read(self,name,maximum=16777216):
        self.reads.append((name,maximum));raw=self.files[name]
        if len(raw)>maximum:raise ValueError('FIXTURE_READ_BOUND')
        return raw,copy.deepcopy(self.metadata[name])
    def file_info(self,name):
        self.infos.append(name);row=copy.deepcopy(self.metadata[name]);row.pop('sha256');return row
    def full_hostname(self):return self.host
    def canonical_python(self,unused):return self.python
    def probe_manager(self):return copy.deepcopy(self.manager)
    def probe_nss(self):return copy.deepcopy(self.nss)
    def timer_schedule(self):return {'systemctl_sha256':c.sha(self.files['/usr/bin/systemctl']),
        'raw':{unit:{name:'0' for name in fields} for unit,fields in snapshot_io.TLS_TIMER_FIELDS.items()}}

class IngredientsTests(unittest.TestCase):
    def setUp(self): self.io=Fake()
    def collect(self):return p.collect_probe_ingredients(self.io,ROOT)
    def missing(self,result,field):
        self.assertEqual(result['ingredient_state'],'INCOMPLETE')
        self.assertIn(field,result['missing_fields']);self.assertNotIn('ingredients',result)
    def test_complete_exact_compiler_schema(self):
        r=self.collect();self.assertEqual(r['ingredient_state'],'COMPLETE_UNREVIEWED')
        self.assertEqual(set(r['ingredients']),p.INGREDIENT_FIELDS)
        self.assertEqual(r['ingredients']['hostname'],self.io.host)
        self.assertEqual(r['ingredients']['python']['path'],'/usr/bin/python3.6')
        self.assertEqual(len(r['ingredients']['sdk_bindings']),5)
        self.assertEqual(r['unsupported_sections'],[])
        self.assertEqual(r['candidate_source_evidence']['runtime_manifest_sha256'],p.RUNTIME_MANIFEST)
        import probe_driver as mod
        # These are explicit synthetic consent inputs for the PURE compiler test.
        offline=dict(nonce='a'*32,driver_sha256=h('driver'),helper_sha256=h('helper'),
            candidate_sources=r['candidate_source_evidence']['candidate_sources'],
            ledger_capability_reviewed=True,cleanup_reviewed=True,node_sqlite_reviewed=True)
        from test_openclaw_metadata import synthetic_observation
        policy=mod.compile_policy(r['ingredients'],offline,synthetic_observation())
        self.assertEqual(policy['runtime_manifest_sha256'],p.RUNTIME_MANIFEST)
        self.assertEqual(policy['profiles']['ledger']['protect_home'],'yes')
        self.assertEqual(policy['profiles']['native']['protect_home'],'read-only')
    def test_no_review_flags_nonce_or_secret_contents(self):
        r=self.collect();raw=packed(r)
        for forbidden in (b'ledger_capability_reviewed',b'cleanup_reviewed',b'"nonce"',self.io.files[p.MACHINE_ID].strip(),
                          b'sdk fixture ',b'fixture python executable',b'"workspaceRoot"'):
            self.assertNotIn(forbidden,raw)
        self.assertEqual(r['install_admission'],'NOT_GRANTED')
        self.assertEqual(r['independent_acceptance'],'PENDING')
        self.assertEqual(r['probe_execution'],'NOT_PERFORMED')
    def test_only_fixed_and_declared_paths_read(self):
        self.collect()
        allowed={p.MACHINE_ID,p.PROVISION,p.CONTROLLER,self.io.python,'/usr/bin/systemctl'}
        allowed.update(self.io.settings['contextFiles'])
        allowed.update(ROOT+'/'+n for n in ('deploy/integration-manifest.json',)+p.CANDIDATE_SOURCES)
        self.assertEqual({n for n,unused in self.io.reads},allowed)
        self.assertEqual(set(self.io.infos),set(self.io.settings['contextFiles']))
    def test_one_failure_reports_all_other_measurements(self):
        del self.io.files[p.MACHINE_ID]
        self.io.manager['binary_path']='/untrusted/manager'
        r=self.collect();self.missing(r,'machine_id_sha256');self.assertIn('manager',r['missing_fields'])
        self.assertEqual(r['sections']['sdk']['state'],'MEASURED_UNREVIEWED')
        self.assertEqual(r['sections']['profiles']['state'],'MEASURED_UNREVIEWED')
        self.assertEqual(r['unsupported_sections'],['machine_id','manager'])
    def test_exact_machine_bytes_digest(self):
        r=self.collect();self.assertEqual(r['ingredients']['machine_id_sha256'],c.sha(self.io.files[p.MACHINE_ID]))
        self.assertNotEqual(r['ingredients']['machine_id_sha256'],c.sha(self.io.files[p.MACHINE_ID].strip()))
    def test_machine_format_and_authority_fail(self):
        for raw,uid in ((b'bad machine id\n',0),(b'a'*32+b'\n',1002)):
            self.io=Fake();self.io.add(p.MACHINE_ID,raw,uid=uid)
            self.missing(self.collect(),'machine_id_sha256')
    def test_hostname_wrong_host_and_race_fail(self):
        self.io.host='other.example';self.missing(self.collect(),'hostname')
        self.io=Fake()
        with mock.patch.object(self.io,'full_hostname',side_effect=[c.HOST,c.HOST+'.changed']):
            self.missing(self.collect(),'hostname')
    def test_oversized_sdk_is_metadata_only(self):
        name=p.SDK_PREFIX+'context.py';self.io.metadata[name]['size']=p.SDK_MAXIMUM+1
        r=self.collect();self.missing(r,'sdk_bindings')
        evidence=r['sections']['sdk']['evidence']
        self.assertEqual(evidence['metadata'][name]['size'],p.SDK_MAXIMUM+1)
        self.assertIn(name,evidence['unsupported_files'])
        self.assertNotIn(name,[n for n,unused in self.io.reads])
        self.assertEqual(len(evidence['bindings']),4)
    def test_all_sdk_failures_collected_once(self):
        for name in self.io.settings['contextFiles']:self.io.metadata[name]['size']=p.SDK_MAXIMUM+1
        r=self.collect();self.assertEqual(len(r['sections']['sdk']['evidence']['unsupported_files']),5)
        self.assertEqual(r['missing_fields'],['sdk_bindings'])
    def test_sdk_scope_escape_rejected_before_read(self):
        self.io.settings['contextFiles']={'/etc/shadow':{'sha256':h('secret'),'uid':1002}}
        self.io.settings['contextPath']='/etc/shadow';self.io.bind()
        self.missing(self.collect(),'sdk_bindings')
        self.assertNotIn('/etc/shadow',[n for n,unused in self.io.reads]);self.assertEqual(self.io.infos,[])
    def test_sdk_hash_mode_owner_links_and_size(self):
        name=p.SDK_PREFIX+'context.py'
        for key,value in (('uid',0),('mode',0o666),('nlink',2),('size',0)):
            self.io=Fake();self.io.metadata[name][key]=value;self.missing(self.collect(),'sdk_bindings')
        self.io=Fake();self.io.files[name]=b'changed';self.missing(self.collect(),'sdk_bindings')
    def test_controller_receipt_mismatch_and_owner(self):
        self.io.files[p.CONTROLLER]+=b' ';r=self.collect()
        self.missing(r,'python');self.assertIn('sdk_bindings',r['missing_fields'])
        self.io=Fake();self.io.metadata[p.CONTROLLER]['uid']=1002
        self.missing(self.collect(),'python')
    def test_receipt_target_scope_and_mode(self):
        for mode,count in ((0o644,24),(0o600,23)):
            self.io=Fake();receipt=c.decode(self.io.files[p.PROVISION]);receipt['targets']=receipt['targets'][:count]
            self.io.add(p.PROVISION,packed(receipt),mode=mode);self.missing(self.collect(),'python')
    def test_binding_late_race_invalidates_dependent_fields(self):
        real=self.io.read;calls={}
        def changed(name,maximum=16777216):
            raw,row=real(name,maximum);calls[name]=calls.get(name,0)+1
            if name==p.CONTROLLER and calls[name]==3:row['ctime_ns']+=1
            return raw,row
        with mock.patch.object(self.io,'read',side_effect=changed):r=self.collect()
        self.missing(r,'python');self.assertIn('sdk_bindings',r['missing_fields'])
        self.assertEqual(r['sections']['protected_controller_binding']['reason'],'PROBE_BINDING_LATE_RACE')
    def test_python_wrong_hash_or_alias_scope(self):
        self.io.files[self.io.python]=b'changed';self.missing(self.collect(),'python')
        self.io=Fake();self.io.python='/home/xuanjun_dev/python'
        self.missing(self.collect(),'python');self.assertNotIn(self.io.python,[n for n,unused in self.io.reads])
    def test_python_reference_scope_before_resolution(self):
        self.io.settings['ledger']['python']='/tmp/python';self.io.bind()
        with mock.patch.object(self.io,'canonical_python',side_effect=AssertionError('must not resolve')) as call:
            self.missing(self.collect(),'python');call.assert_not_called()
    def test_read_failure_sanitizes_private_exception(self):
        real=self.io.read
        def fail(name,maximum=16777216):
            if name=='/usr/bin/systemctl':raise PermissionError('secret path or data')
            return real(name,maximum)
        with mock.patch.object(self.io,'read',side_effect=fail):r=self.collect()
        self.missing(r,'systemctl');self.assertNotIn(b'secret path or data',packed(r))
        self.assertEqual(r['sections']['systemctl']['reason'],'READ_PERMISSION_UNAVAILABLE')
    def test_manager_observation_changed(self):
        second=copy.deepcopy(self.io.manager);second['starttime']+=1
        with mock.patch.object(self.io,'probe_manager',side_effect=[self.io.manager,second]):
            self.missing(self.collect(),'manager')
    def test_nss_changed_or_missing(self):
        second=copy.deepcopy(self.io.nss);second['existing_accounts']['root']['global_group_gids'].append(99)
        with mock.patch.object(self.io,'probe_nss',side_effect=[self.io.nss,second]):self.missing(self.collect(),'profiles')
        with mock.patch.object(self.io,'probe_nss',side_effect=KeyError('private NSS value')):
            self.missing(self.collect(),'profiles')
    def test_nss_current_membership_separate_from_proposed_group(self):
        r=self.collect();profile=r['ingredients']['profiles']['broker']
        self.assertEqual(profile['supplementary_groups'],{'xuanjun-ledger-client':1007})
        self.assertEqual(r['sections']['profiles']['evidence']['existing_accounts']['root']['global_group_gids'],[0])
        self.assertNotIn('protect_home',profile)
    def test_native_primary_group_must_match_compiler(self):
        self.io.nss['profiles']['native']['group']='different';self.missing(self.collect(),'profiles')
    def test_wrong_role_uid_or_group_is_not_complete(self):
        for key,value in (('uid',1002),('group','xuanjun_dev'),('supplementary_groups',{})):
            self.io=Fake();self.io.nss['profiles']['ledger'][key]=value
            self.missing(self.collect(),'profiles')
    def test_metadata_hash_disagreement_fails(self):
        self.io.metadata[p.MACHINE_ID]['sha256']=h('wrong')
        r=self.collect();self.missing(r,'machine_id_sha256')
        self.assertEqual(r['sections']['machine_id']['reason'],'PROBE_FILE_CONTENT_METADATA')
    def test_candidate_wrong_root_reads_nothing_outside_scope(self):
        r=p.collect_probe_ingredients(self.io,'/opt/new-release')
        self.assertIsNone(r['candidate_source_evidence'])
        self.assertEqual(r['sections']['staged_candidate']['reason'],'PROBE_STAGED_CANDIDATE_SCOPE')
        self.assertFalse(any(n.startswith('/opt/new-release') for n,unused in self.io.reads))
    def test_occupied_original_kit_root_is_not_an_alternate(self):
        old=c.CAND+'/epoch7-recovery-candidate/xuanjun-p2-package'
        with self.assertRaisesRegex(ValueError,'PROBE_STAGED_CANDIDATE_SCOPE'):
            p.candidate_sources(self.io,old)
        self.assertEqual(self.io.reads,[])
        self.assertEqual(p.candidate_sources(self.io,ROOT)['root'],ROOT)
    def test_candidate_missing_root_does_not_invent_sources(self):
        r=p.collect_probe_ingredients(self.io)
        self.assertIsNone(r['candidate_source_evidence'])
        self.assertEqual(r['sections']['staged_candidate']['reason'],'CANDIDATE_ROOT_NOT_SUPPLIED')
        self.assertEqual(r['ingredient_state'],'COMPLETE_UNREVIEWED')
    def test_candidate_old_manifest_and_source_drift(self):
        target=ROOT+'/deploy/integration-manifest.json';self.io.add(target,packed({'files':{},'old':d.OLD_MANIFEST}))
        r=self.collect();self.assertIsNone(r['candidate_source_evidence'])
        self.assertEqual(r['sections']['staged_candidate']['reason'],'PROBE_EXACT_STAGED_RUNTIME')
        self.io=Fake();self.io.add(ROOT+'/'+p.CANDIDATE_SOURCES[0],b'changed source')
        r=self.collect();self.assertEqual(r['sections']['staged_candidate']['reason'],'PROBE_STAGED_SOURCE_HASH')
    def test_interrupt_is_not_swallowed(self):
        with mock.patch.object(self.io,'full_hostname',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.collect()
    def test_actual_controller_has_no_gateway_identity(self):
        self.assertNotIn('gatewayIdentity',self.io.settings)
        self.assertEqual(self.collect()['ingredient_state'],'COMPLETE_UNREVIEWED')

class HostEnvelopeTests(unittest.TestCase):
    def test_probe_metadata_survives_snapshot_hold(self):
        # Every concrete host boundary is replaced; no actual host access.
        fake=Fake();fake.observed_metadata={'fixture':{}};fake.pins={}
        reader=mock.Mock();reader.pins={}
        reader.read.side_effect=lambda name:(b'',dict(uid=0,gid=0,mode=0o600 if name==c.INSTALL_LOCK else 0o644,sha256=h('lock')))
        import contextlib
        @contextlib.contextmanager
        def locks(*unused):yield {'fixture':'held'}
        with mock.patch.object(observe.os,'geteuid',return_value=0),mock.patch.object(observe.socket,'gethostname',return_value=c.HOST), \
             mock.patch.object(observe,'ObservationReader',return_value=reader),mock.patch.object(observe,'ObservationIO',return_value=fake), \
             mock.patch.object(observe.concrete,'existing_locks',side_effect=locks), \
             mock.patch.object(observe,'observe_with_io',side_effect=ValueError('RETAINED_SNAPSHOT_HOLD')):
            result=observe.observe_host(candidate_root=ROOT)
        self.assertEqual(result['kind'],'EPOCH7_OBSERVATION_ONLY_HOLD')
        self.assertEqual(result['probe_metadata']['ingredient_state'],'COMPLETE_UNREVIEWED')
        self.assertEqual(result['probe_metadata_sha256'],d.digest(result['probe_metadata']))
        self.assertEqual(result['unit_metadata_sha256'],d.digest(result['unit_metadata']))
        self.assertEqual(result['unit_metadata']['state'],'INCOMPLETE')
        self.assertEqual(result['unit_metadata']['source_closure'],'NOT_VERIFIED')
        self.assertNotIn('snapshot',result)

if __name__=='__main__':unittest.main()
