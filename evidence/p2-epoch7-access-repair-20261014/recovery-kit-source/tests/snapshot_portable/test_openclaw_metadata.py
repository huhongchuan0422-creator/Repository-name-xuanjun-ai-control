"""Fixed-source/private-projection fixtures. No Node, source, systemd or host execution."""
import copy
import contextlib
import stat
import pathlib
import sys
import time
import types
import unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'recovery-design-candidate'),str(HERE.parent/'isolated-probe-candidate'),
    str(HERE.parent/'sequence-candidate'),str(HERE.parent/'sequence-candidate'/'openclaw-overlay'),
    str(HERE.parent/'live-controls-candidate'),str(HERE.parent/'diagnostics-candidate')]
import epoch7_snapshot as c
import epoch7_delta as d
import openclaw_metadata as o
import unit_metadata as u
import node_sqlite_probe as n
from test_probe_metadata import Fake as Base,ROOT,packed,h

NODE='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node'
PACKAGE='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw'
ACCOUNT={'user':'xuanjun_dev','uid':1002,'gid':1002,'home':'/home/xuanjun_dev'}
UNIT=('[Service]\nUser=xuanjun_dev\nGroup=xuanjun_dev\nEnvironment=TOKEN=private-fixture-secret\n'
      'ExecStart='+u.LAUNCHER+' gateway --port 18789\n').encode()
WRAPPER=('#!/bin/bash\nexport HOME=/home/xuanjun_dev\nexec '+NODE+' '+PACKAGE+'/openclaw.mjs "$@"\n').encode()

def node():return {'path':NODE,'sha256':h('node'),'metadata':{'dev':1,'ino':2,'mode':0o755,'uid':1002,'gid':1002,
    'nlink':1,'size':123,'mtime_ns':3,'ctime_ns':4}}
def synthetic_observation():
    image=node();retained={'native_components':{'components':{NODE:dict(image['metadata'],kind='FILE',sha256=image['sha256'])}}}
    snapshot={'retained_resource_sha256':d.digest(retained)}
    evidence={'snapshot_sha256':d.digest(snapshot),'retained':retained,'writers':{'manager':{'fixture':'manager'}}}
    units={'sections':{'native_gateway':{'state':'MEASURED_UNREVIEWED','evidence':{'gateway_identity':{
        'user':'xuanjun_dev','exe':NODE,'sha256':image['sha256'],'cgroup':'/system.slice/'+u.GATEWAY}}}}}
    value={'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED','install_admission':'NOT_GRANTED',
        'snapshot':snapshot,'evidence':evidence,'unit_metadata':units}
    refresh(value);return value

def refresh(value):
    for key in ('snapshot','evidence','unit_metadata','openclaw_profile'):
        if key in value:value[key+'_sha256']=d.digest(value[key])

def add_attempt(value):
    binding=n.binding_from_observation(value)
    policy={'schema':2,'node_sqlite_reviewed':True,'node_sqlite':binding,'nonce':'a'*32}
    policy_sha=c.sha(d.canonical(policy)+b'\n')
    proof={'schema':1,'status':'PASS_OBSERVED','node':node(),'diagnostic_sha256':c.sha(n.SOURCE),
        'policy_sha256':policy_sha,'probe_input_sha256':binding['probe_input_sha256'],'nonce':policy['nonce'],
        'argv_sha256':d.digest(n.argv(node(),policy['nonce'])),'environment_sha256':d.digest(n.ENV),
        'execution_identity':copy.deepcopy(n.EXECUTION_IDENTITY),'cleanup_state':'OBSERVED','error':None,
        'result':{'schema':1,'node_version':'24.21.0','exec_path':NODE,'exec_argv':[],
            'sqlite':{'available':True,'version':'3.51.3','text':True,'blob':True,'json':True,'error':None}}}
    receipt={'path':n.script_path(policy['nonce']).rsplit('/',1)[0]+'/created-receipt.json','sha256':h('receipt'),
        'metadata':dict(node()['metadata'],uid=0,gid=0,mode=0o600),'node_sqlite_event_sha256':d.digest(proof)}
    value['finite_probe']={'schema':1,'nonce':policy['nonce'],'stage':'RESULT_RECORDED','resume_authority':False,
        'operator_acknowledgement_is_external_approval_proof':False,'policy':policy,'policy_sha256':policy_sha,
        'result':{'failure':None,'resume_authority':False,'last_command_cleanup':[],
            'cases':[{'case':i,'status':'FAIL_OBSERVED' if i in (6,8) else 'PASS_OBSERVED',
                'expected_rejection_observed':i in (6,8)} for i in range(1,9)],
            'cleanup':[{'status':'REMOVED'}],'node_sqlite':proof,'created_receipt':receipt}}

class Fake(Base):
    def __init__(self):
        super(Fake,self).__init__();self.observation=synthetic_observation();self.absences=[]
        self.expected={};self.read_count={}
        self.backup=c.TRANSACTION+'/'+u.GATEWAY+'.backup'
        self.add(self.backup,UNIT);self.add(u.LAUNCHER,WRAPPER,uid=1002,gid=1002,mode=0o755)
        self.add(c.PROFILE,packed({'gateway':{'auth':{'token':'private-fixture-secret'}}}),uid=1002,gid=1002)
        for relative in o.SOURCE_HASHES:
            raw=packed({'name':'openclaw','version':o.VERSION,'bin':{'openclaw':'openclaw.mjs'}}) if relative=='package.json' else ('// synthetic '+relative).encode()
            self.add(PACKAGE+'/'+relative,raw,uid=1002,gid=1002,mode=0o644);self.expected[relative]=c.sha(raw)
        self.relay={'openclaw_bin':u.LAUNCHER,'openclaw_sha256':c.sha(WRAPPER),'openclaw_owner_uid':1002,
            'gateway_home':'/home/xuanjun_dev','gateway_path':'/usr/bin:/bin','dispatcher_user':'xuanjun-dispatcher'}
        self.add(o.RELAY,packed(self.relay),uid=0,gid=1002,mode=0o640)
        receipt=c.decode(self.files[o.PROVISION]);pin=next(x for x in receipt['targets'] if x['target']==o.RELAY)
        pin.update(rendered_sha256=c.sha(self.files[o.RELAY]),uid=0,gid=1002,mode=0o640);self.add(o.PROVISION,packed(receipt))
        self.dropins={unit:{root+'/'+unit+'.d':{'present':False,'files':{}} for root in
            ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')} for unit in u.UNITS}
        sections=self.observation['unit_metadata']['sections']
        sections.update({key:{'state':'MEASURED_UNREVIEWED','evidence':evidence} for key,evidence in {
            'launcher':{'sha256':c.sha(WRAPPER),'recipe':u.launcher_recipe(WRAPPER,NODE)},
            'legacy_gateway':{'backup_path':self.backup,'backup_sha256':c.sha(UNIT),
                'original_unit':{'path':'/etc/systemd/system/'+u.GATEWAY,'sha256':c.sha(UNIT)}},
            'dropins':{'units':copy.deepcopy(self.dropins)}}.items()})
        refresh(self.observation)
        self.selected={key:None for key in o.ENV_KEYS};self.selected['HOME']='/root'
    def absent(self,path):self.absences.append(path);return path not in self.files
    def verify_node_descriptor(self,path,expected):
        n.validate_node({'path':path,'sha256':expected['sha256'],'metadata':{k:expected[k] for k in n.META}})
        return node()
    def gateway_account_home(self):return copy.deepcopy(ACCOUNT)
    def gateway_manager_environment(self):return {'selected':copy.deepcopy(self.selected),
        'selectors':{key:self.selected[key] for key in o.SELECTORS},'source':'SYSTEM_MANAGER_CHILD_ENVIRONMENT',
        'manager_sha256':d.digest(self.observation['evidence']['writers']['manager']),'systemctl_sha256':h('systemctl')}
    def unit_dropins(self,units):
        if tuple(units)!=u.UNITS:raise ValueError('UNIT_DROPIN_SCOPE')
        return copy.deepcopy(self.dropins)
    def collect(self):
        with mock.patch.object(o,'SOURCE_HASHES',self.expected):
            return o.collect_openclaw_profile(self,self.observation['unit_metadata'],self.observation,ROOT)
    def attach(self):
        self.observation['openclaw_profile']=self.collect();refresh(self.observation);return self.observation

class ProjectionTests(unittest.TestCase):
    def setUp(self):self.io=Fake()
    def project(self,**overrides):
        args=dict(manager_selected={key:None for key in o.ENV_KEYS},account=ACCOUNT,unit_raw=UNIT,
            wrapper_raw=WRAPPER,node_path=NODE,config_raw=b'{}',
            dotenv_raw_by_path={path:None for path in o.dotenv_paths(UNIT)},relay_config_raw=packed(self.io.relay))
        args.update(overrides);return o.quiet_projection(**args)
    def test_literal_supported_projection(self):
        value=self.project();self.assertEqual(value['selected_environment']['HOME'],ACCOUNT['home'])
        self.assertEqual(value['node_exec_argv'],[]);self.assertEqual(value['config_projection'],
            {'env_shell_enabled':None,'proxy_enabled':None,'proxy_url_present':False,'include_present':False})
        self.assertNotIn(b'private-fixture-secret',packed(value))
    def test_all_selected_manager_unsafe_values_rejected(self):
        for key in o.ENV_KEYS:
            if key=='HOME':continue
            env={name:None for name in o.ENV_KEYS};env[key]='private-fixture-secret'
            with self.assertRaises(ValueError):self.project(manager_selected=env)
    def test_unit_literal_override_and_reset(self):
        self.project(unit_raw=UNIT+b'Environment=NODE_OPTIONS=unsafe\nEnvironment=\n')
        with self.assertRaises(ValueError):self.project(unit_raw=UNIT+b'Environment=NODE_OPTIONS=unsafe\n')
    def test_unknown_environment_mechanisms_refused(self):
        for name in ('EnvironmentFile','PassEnvironment','UnsetEnvironment','PAMName','RootImage','BindPaths'):
            with self.assertRaises(ValueError):self.project(unit_raw=UNIT+(name+'=unsafe\n').encode())
    def test_percent_substitution_refused(self):
        with self.assertRaises(ValueError):self.project(unit_raw=UNIT+b'Environment=HOME=%h\n')
    def test_every_selected_config_declaration_refused(self):
        for key in o.ENV_KEYS:
            for value in ({'env':{key:'x'}},{'env':{'vars':{key:'x'}}}):
                with self.assertRaises(ValueError):self.project(config_raw=packed(value))
    def test_casefolded_or_trimmed_config_environment_refused(self):
        for key in ('home','openclaw_config_path',' HOME '):
            with self.assertRaises(ValueError):self.project(config_raw=packed({'env':{'vars':{key:'x'}}}))
    def test_config_active_or_include_refused(self):
        for value in ({'env':{'shellEnv':{'enabled':True}}},{'proxy':{'enabled':True}},
                      {'proxy':{'proxyUrl':'http://private.invalid'}},{'gateway':{'$include':'secret'}}):
            with self.assertRaises(ValueError):self.project(config_raw=packed(value))
    def test_false_blank_and_unrelated_config_allowed(self):
        self.project(config_raw=packed({'env':{'shellEnv':{'enabled':False},'vars':{'TOKEN':'private-fixture-secret'}},
            'proxy':{'enabled':False,'proxyUrl':' '}}))
    def test_dotenv_values_never_returned(self):
        paths={path:None for path in o.dotenv_paths(UNIT)};paths['/.env']=b'TOKEN="private-fixture-secret"\n'
        result=self.project(dotenv_raw_by_path=paths);self.assertNotIn(b'private-fixture-secret',packed(result))
        self.assertEqual(result['dotenv_declarations']['/.env'],['TOKEN'])
    def test_dotenv_selected_names_and_ambiguous_syntax_refused(self):
        for raw in (b'NODE_OPTIONS=""',b'export OPENCLAW_HOME=/home/xuanjun_dev',b'home=/elsewhere',b'openclaw_config_path=/elsewhere',b'TOKEN="multi\nline"',b'not-a-declaration'):
            with self.assertRaises(ValueError):o.dotenv_names(raw)
    def test_working_directory_finite_paths(self):
        for cwd in ('/','/home/xuanjun_dev','/home/xuanjun_dev/.openclaw'):
            self.assertIn(cwd.rstrip('/')+'/.env',o.dotenv_paths(UNIT+('WorkingDirectory='+cwd+'\n').encode()))
        with self.assertRaises(ValueError):o.dotenv_paths(UNIT+b'WorkingDirectory=/arbitrary\n')
    def test_missing_dotenv_path_refused(self):
        with self.assertRaises(ValueError):self.project(dotenv_raw_by_path={})
    def test_dropin_environment_or_user_override_refused(self):
        for raw in (b'[Service]\nEnvironment=NODE_OPTIONS=unsafe\n',b'[Service]\nUser=root\n'):
            with self.assertRaises(ValueError):self.project(dropin_raws=[raw])
        self.project(dropin_raws=[b'[Service]\nSupplementaryGroups=docker xuanjun-ledger-client\n'])
    def test_wrapper_export_scope_refused(self):
        with self.assertRaises(ValueError):self.project(wrapper_raw=WRAPPER.replace(b'export HOME=',b'export NODE_OPTIONS='))
    def test_export_after_exec_is_not_effective(self):
        with self.assertRaisesRegex(ValueError,'TRAILING_STATEMENT'):
            self.project(wrapper_raw=WRAPPER+b'export HOME=/home/xuanjun_dev\n')
    def test_non_dev_account_refused(self):
        with self.assertRaises(ValueError):self.project(account=dict(ACCOUNT,uid=0))

class CollectorTests(unittest.TestCase):
    def setUp(self):self.io=Fake()
    def test_complete31_fixed_files(self):
        value=self.io.collect();self.assertEqual(value['missing_fields'],[])
        self.assertEqual(value['state'],'COMPLETE_UNREVIEWED');recipe=value['recipe_evidence']
        self.assertEqual(set(recipe['files']),set(o.SOURCE_HASHES));self.assertEqual(len(recipe['files']),31)
        self.assertEqual(recipe['quiet_bootstrap']['package_absence'],{name:'ABSENT' for name in o.ABSENT})
        self.assertNotIn('node_probe',recipe);self.assertNotIn(b'private-fixture-secret',packed(value))
    def test_receipt_scoped_actual_metadata_matrix(self):
        import probe_metadata as p
        # These are the two confirmed dev-readable provisioning targets. The
        # separate protected() matrix stays root:root; no wildcard owner rule.
        for target,expected in ((o.RELAY,(0,1002,0o640)),(p.CONTROLLER,(0,1002,0o640))):
            io=Fake();self.assertEqual(tuple(io.metadata[target][k] for k in ('uid','gid','mode')),expected)
            p.binding(io);self.assertEqual(io.collect()['missing_fields'],[])
            for key,bad in (('uid',1002),('gid',0),('gid',1003),('mode',0o644),('mode',0o600)):
                io=Fake();io.metadata[target][key]=bad
                if target==p.CONTROLLER:
                    with self.assertRaises(ValueError):p.binding(io)
                else:self.assertIn('relay',io.collect()['missing_fields'])
        for target in (o.PROVISION,self.io.backup,ROOT+'/deploy/integration-manifest.json'):
            p.protected(self.io.metadata[target],1048576)
            for key,bad in (('uid',1002),('gid',1002),('mode',0o666)):
                row=dict(self.io.metadata[target]);row[key]=bad
                with self.assertRaises(ValueError):p.protected(row,1048576)
    def test_actual_relay_receipt_metadata_succeeds(self):
        self.assertEqual(tuple(self.io.metadata[o.RELAY][k] for k in ('uid','gid','mode')),(0,1002,0o640))
        self.assertEqual(self.io.collect()['missing_fields'],[])
    def test_wrong_relay_gid_or_mode_rejected(self):
        for key,bad in (('gid',0),('gid',1003),('mode',0o644),('mode',0o600),('uid',1002),('nlink',2)):
            io=Fake();io.metadata[o.RELAY][key]=bad
            self.assertIn('relay',io.collect()['missing_fields'])
    def test_wrong_relay_receipt_metadata_is_not_a_new_grant(self):
        for key,bad in (('gid',1003),('mode',0o644)):
            io=Fake();receipt=c.decode(io.files[o.PROVISION]);pin=next(row for row in receipt['targets'] if row['target']==o.RELAY)
            pin[key]=bad;io.metadata[o.RELAY][key]=bad;io.add(o.PROVISION,packed(receipt))
            self.assertIn('relay',io.collect()['missing_fields'])
    def test_relay_exception_does_not_relax_receipt_or_backup_group(self):
        for path,field in ((o.PROVISION,'relay'),(self.io.backup,'unit')):
            io=Fake();io.metadata[path]['gid']=1002
            self.assertIn(field,io.collect()['missing_fields'])
    def test_unknown_fields_aggregate_and_never_emit_environment(self):
        self.io.selected['NODE_OPTIONS']='private-fixture-secret'
        del self.io.files[PACKAGE+'/dist/entry.js'];del self.io.files[c.PROFILE]
        result=self.io.collect();self.assertIn('source:dist/entry.js',result['missing_fields'])
        self.assertIn('config',result['missing_fields']);self.assertIn('quiet_projection',result['missing_fields'])
        self.assertNotIn('recipe_evidence',result);self.assertNotIn(b'private-fixture-secret',packed(result))
    def test_wrong_source_bytes_refused(self):
        path=PACKAGE+'/dist/entry.js';self.io.add(path,b'changed',uid=1002,gid=1002,mode=0o644)
        self.assertIn('source:dist/entry.js',self.io.collect()['missing_fields'])
    def test_wrong_source_mode_or_owner_refused(self):
        path=PACKAGE+'/dist/entry.js'
        for field,bad in (('uid',0),('mode',0o666),('nlink',2)):
            io=Fake();io.metadata[path][field]=bad;self.assertIn('source:dist/entry.js',io.collect()['missing_fields'])
    def test_each_absence_is_actual_measurement(self):
        for rel in o.ABSENT:
            io=Fake();io.add(PACKAGE+'/'+rel,b'present',uid=1002,gid=1002)
            self.assertIn('absence:'+rel,io.collect()['missing_fields'])
    def test_node_descriptor_unavailable_holds(self):
        self.io.observation['evidence']['retained']['native_components']['components']={}
        self.assertIn('node',self.io.collect()['missing_fields'])
    def test_missing_candidate_and_staged_dotenv_hold(self):
        with mock.patch.object(o,'SOURCE_HASHES',self.io.expected):
            result=o.collect_openclaw_profile(self.io,self.io.observation['unit_metadata'],self.io.observation)
        self.assertIn('relay_cwd',result['missing_fields'])
        self.io.add(ROOT+'/stage1/.env',b'TOKEN=secret');self.assertIn('relay_cwd',self.io.collect()['missing_fields'])
    def test_occupied_original_kit_has_no_staged_cwd_or_dotenv_authority(self):
        old=c.CAND+'/epoch7-recovery-candidate-r2/xuanjun-p2-package'
        with mock.patch.object(o,'SOURCE_HASHES',self.io.expected):
            result=o.collect_openclaw_profile(self.io,self.io.observation['unit_metadata'],self.io.observation,old)
        self.assertIn('relay_cwd',result['missing_fields'])
        self.assertEqual(result['sections']['relay_cwd']['reason'],'OPENCLAW_STAGED_CWD_REQUIRED')
        self.io.absences=[]
        o.prime_profile_scope(self.io,self.io.observation['unit_metadata'],old)
        self.assertNotIn(old+'/stage1/.env',self.io.absences)
        o.prime_profile_scope(self.io,self.io.observation['unit_metadata'],ROOT)
        self.assertIn(ROOT+'/stage1/.env',self.io.absences)
    def test_late_file_change_refused(self):
        read=self.io.read;count=[0]
        def changed(path,maximum=16777216):
            raw,row=read(path,maximum)
            if path==c.PROFILE:
                count[0]+=1
                if count[0]>=3:row['ino']+=1
            return raw,row
        self.io.read=changed;self.assertIn('stability',self.io.collect()['missing_fields'])
    def test_prime_scope_is_fixed_and_before_digest(self):
        self.assertEqual(o.prime_profile_scope(self.io,self.io.observation['unit_metadata'],ROOT),{})
        self.assertEqual(set(self.io.absences),{PACKAGE+'/'+x for x in tuple(o.SOURCE_HASHES)+o.ABSENT}|
            set(o.dotenv_paths(UNIT))|{ROOT+'/stage1/.env'})
    def test_original_full_probe_chain_required(self):
        value=self.io.attach();self.assertIsNone(o.recipe_from_observation(value));add_attempt(value)
        result=o.recipe_from_observation(value);self.assertEqual(result['node_probe']['proof'],value['finite_probe']['result']['node_sqlite'])
    def test_unknown_profile_and_unexecuted_probe_do_not_admit(self):
        value=self.io.attach();value['openclaw_profile']['state']='UNKNOWN';refresh(value)
        self.assertIsNone(o.recipe_from_observation(value))
        value=self.io.attach();value['finite_probe']={'stage':'HOLD_NOT_EXECUTED'}
        self.assertIsNone(o.recipe_from_observation(value))
    def test_malformed_digest_or_self_consistent_leaf_substitution_rejected(self):
        value=self.io.attach();add_attempt(value);value['openclaw_profile_sha256']='0'*64
        with self.assertRaises(ValueError):o.recipe_from_observation(value)
        value=self.io.attach();add_attempt(value);value['finite_probe']['result']['node_sqlite']['policy_sha256']='1'*64
        with self.assertRaises(ValueError):o.recipe_from_observation(value)
    def test_unknown_cleanup_and_failed_other_case_refused(self):
        for key in ('cleanup','case'):
            value=self.io.attach();add_attempt(value)
            if key=='cleanup':value['finite_probe']['result']['cleanup']=[{'status':'UNKNOWN'}]
            else:value['finite_probe']['result']['cases'][2]['status']='FAIL_OBSERVED'
            with self.assertRaises(ValueError):o.recipe_from_observation(value)
    def test_exact_recipe_consumer_accepts_full_adapter(self):
        import epoch7_openclaw_recipe as recipe
        value=self.io.attach();add_attempt(value);actual=o.recipe_from_observation(value)
        with mock.patch.object(recipe,'SOURCE_HASHES',self.io.expected):
            checked,sources,result=recipe.check_inputs({'rendered_targets':{o.RELAY:packed(self.io.relay)}},
                {'openclaw_recipe_evidence':actual},{'native_identity':value['unit_metadata']['sections']['native_gateway']['evidence']['gateway_identity'],
                'unit_sha256':c.sha(self.io.files[self.io.backup])})
        self.assertEqual(checked,actual);self.assertEqual(len(sources),33);self.assertEqual(result['node_version'],'24.21.0')
    def test_late_dropin_appearance_refused(self):
        original=self.io.unit_dropins;calls=[0]
        def changed(units):
            calls[0]+=1;value=original(units)
            if calls[0]>1:
                root=next(iter(value[u.GATEWAY]));value[u.GATEWAY][root]['present']=True
            return value
        self.io.unit_dropins=changed;self.assertIn('stability',self.io.collect()['missing_fields'])
    def test_late_node_inode_change_refused(self):
        original=self.io.verify_node_descriptor;calls=[0]
        def changed(path,pin):
            calls[0]+=1;value=original(path,pin)
            if calls[0]>1:value['metadata']['ino']+=1
            return value
        self.io.verify_node_descriptor=changed;self.assertIn('stability',self.io.collect()['missing_fields'])
    def test_missing_frozen_ancestor_rejects_profile(self):
        self.io.observation['policy']={'directories':{}};self.io.pins={}
        self.assertIn('stability',self.io.collect()['missing_fields'])
    def test_exact_reviewed_source_pin_contract(self):
        import epoch7_openclaw_recipe as recipe
        self.assertEqual(o.SOURCE_HASHES,recipe.SOURCE_HASHES);self.assertEqual(o.ABSENT,recipe.ABSENT)
        self.assertEqual(o.ENV_KEYS,recipe.ENV_KEYS)

class ConcreteReaderTests(unittest.TestCase):
    def descriptor(self,magic=b'\x7fELF',late_inode=False):
        import snapshot_io as concrete
        expected=dict(node()['metadata'],kind='FILE',sha256=node()['sha256'])
        info=types.SimpleNamespace(**{'st_'+key:value for key,value in node()['metadata'].items()})
        info.st_mode|=stat.S_IFREG
        late=copy.copy(info)
        if late_inode:late.st_ino+=1
        @contextlib.contextmanager
        def parent(path):yield (10,'node')
        io=types.SimpleNamespace(parent=parent)
        with mock.patch.object(concrete.os,'stat',side_effect=[info,late]), \
             mock.patch.object(concrete.os,'fstat',return_value=info), \
             mock.patch.object(concrete.os,'open',return_value=11) as opened, \
             mock.patch.object(concrete.os,'read',return_value=magic), \
             mock.patch.object(concrete.os,'close') as close:
            try:return concrete.LocalReadOnlyIO.verify_node_descriptor(io,NODE,expected)
            finally:
                close.assert_called_once_with(11)
                self.assertTrue(opened.call_args[0][1]&concrete.os.O_NOFOLLOW)
    def test_descriptor_rebinds_exact_elf_without_execution(self):
        self.assertEqual(self.descriptor(),node())
    def test_descriptor_rejects_nonelf_and_replacement_and_closes_fd(self):
        with self.assertRaises(ValueError):self.descriptor(magic=b'#!sh')
        with self.assertRaises(ValueError):self.descriptor(late_inode=True)
    def test_selected_manager_reader_discards_other_values_and_binds_twice(self):
        import snapshot_io as concrete
        io=Fake();io.deadline=time.monotonic()+30;io.check_locks=lambda:None
        io.probe_manager=lambda:copy.deepcopy(io.observation['evidence']['writers']['manager'])
        raw=b'HOME=/root\nTOKEN=private-fixture-secret\nPATH=/usr/bin\n'
        with mock.patch.object(concrete,'bounded_query',return_value=raw) as query:
            result=concrete.LocalReadOnlyIO.gateway_manager_environment(io)
        self.assertEqual(query.call_count,2);self.assertEqual(result['selected']['HOME'],'/root')
        self.assertEqual(result['selectors']['HOME'],'/root');self.assertNotIn(b'private-fixture-secret',packed(result))
        self.assertNotIn('PATH',result['selected'])
    def test_changed_or_duplicate_manager_value_refused(self):
        import snapshot_io as concrete
        io=Fake();io.deadline=time.monotonic()+30;io.check_locks=lambda:None
        io.probe_manager=lambda:copy.deepcopy(io.observation['evidence']['writers']['manager'])
        for values in ([b'HOME=/root\n',b'HOME=/different\n'],[b'HOME=/root\nHOME=/root\n']):
            with mock.patch.object(concrete,'bounded_query',side_effect=values):
                with self.assertRaises(ValueError):concrete.LocalReadOnlyIO.gateway_manager_environment(io)
    def test_account_home_is_measured_twice(self):
        import snapshot_io as concrete
        account=types.SimpleNamespace(pw_name='xuanjun_dev',pw_uid=1002,pw_gid=1002,pw_dir='/home/xuanjun_dev')
        with mock.patch.object(concrete.pwd,'getpwnam',return_value=account) as call:
            self.assertEqual(concrete.LocalReadOnlyIO.gateway_account_home(object()),ACCOUNT)
        self.assertEqual(call.call_count,2)
    def test_observe_host_primes_before_policy_and_finishes_after(self):
        import observe_epoch7 as observer
        import contextlib
        io=Fake();io.observed_metadata={};io.pins={};reader=mock.Mock();reader.pins={};order=[]
        reader.read.side_effect=lambda name:(b'',dict(uid=0,gid=0,mode=0o600 if name==c.INSTALL_LOCK else 0o644,sha256=h('lock')))
        @contextlib.contextmanager
        def locks(*args):yield {}
        def prime(*args):order.append('prime');return {}
        def strict(*args):order.append('strict');return copy.deepcopy(io.observation)
        def finish(*args):order.append('finish');return {'state':'fixture'}
        with mock.patch.object(observer.os,'geteuid',return_value=0),mock.patch.object(observer.socket,'gethostname',return_value=c.HOST), \
             mock.patch.object(observer,'ObservationReader',return_value=reader),mock.patch.object(observer,'ObservationIO',return_value=io), \
             mock.patch.object(observer.concrete,'existing_locks',side_effect=locks),mock.patch.object(observer,'observe_with_io',side_effect=strict), \
             mock.patch.object(o,'prime_profile_scope',side_effect=prime),mock.patch.object(o,'collect_openclaw_profile',side_effect=finish):
            result=observer.observe_host(candidate_root=ROOT)
        self.assertEqual(order,['prime','strict','finish']);self.assertEqual(result['openclaw_profile_sha256'],d.digest(result['openclaw_profile']))

if __name__=='__main__':unittest.main()
