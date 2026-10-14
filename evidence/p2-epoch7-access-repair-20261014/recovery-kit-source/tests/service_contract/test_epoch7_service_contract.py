"""Pure compiler fixtures over the exact local107-file package and rendered units."""
import copy
import base64
import hashlib
import json
import pathlib
import sys
import unittest
HERE=pathlib.Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'snapshot-candidate'),str(HERE.parent/'recovery-design-candidate'),str(HERE.parent/'diagnostics-candidate')]
import epoch7_service_contract as sc
from test_epoch7_live_controls import fixture
import epoch7_live_controls as live


def runtime_fixture_root():
    """Exact public runtime, including mixed legacy/current local test sessions."""
    public=json.loads((HERE/'fixtures/public-service-units.json').read_text())
    candidates=[]
    try:
        import activation_control
        candidates.append(pathlib.Path(activation_control.__file__).resolve().parent.parent)
    except ImportError:pass
    candidates.append(HERE.parent/'runtime-build-101b465c/xuanjun-p2-package')
    for root in candidates:
        path=root/'deploy/integration-manifest.json'
        if path.is_file() and sc.sha(path.read_bytes())==public['runtime_manifest_sha256']:return root
    raise AssertionError('exact public runtime fixture is unavailable')


def compiler_fixture():
    public=json.loads((HERE/'fixtures/public-service-units.json').read_text())
    manifest=public['runtime_manifest_raw'].encode('utf-8')
    assert sc.sha(manifest)==public['runtime_manifest_sha256']
    files=json.loads(manifest.decode())['files']
    for row in public['units'].values():
        assert sc.sha(row['template'].encode())==row['source_sha256']==files[row['source']]
        expected=row['template'].replace('@@RELEASE_DIRECTORY@@','integration-'+sc.sha(manifest)[:16]).replace(
            '@@RELEASE@@','/opt/xuanjun-control-releases/integration-'+sc.sha(manifest)[:16]).replace('@@ARTIFACT_SHA256@@',sc.sha(manifest))
        assert expected==row['rendered']
    targets={p:row['rendered'] for p,row in public['units'].items()}
    services=sorted(set(sc.DIRECT)|{'xj-root-broker.socket','xuanjun-ledger.socket',
                                   'xuanjun-p2-gateway-relay.socket','xuanjun-github-intake.timer'})
    compiled={'kind':'PRIVATE_RETAINED_BINDINGS_NOT_INSTALL_PLAN','install_admission':False,
        'manifest_sha256':sc.sha(manifest),'rendered_targets':targets,
        'runtime':{'services':services,'provisioning':[{'target':p,'owner_uid':0,'group_gid':0,'mode':420,
        'rendered_sha256':sc.sha(v.encode())} for p,v in sorted(targets.items())]}}
    unused,ctx,contract,views=fixture()
    states={u:dict(p['properties'],MainPID=0,ControlPID=0,ControlGroup='',DropInPaths='',
                   FragmentPath='/etc/systemd/system/'+u) for u,p in contract['checkpoints'][0]['units'].items()}
    states[sc.GATEWAY].update(LoadState='masked',UnitFileState='masked')
    gids={'root':0,'xuanjun_dev':1002,'xuanjun-dispatcher':1003,'xuanjun-callback':1004,
          'xuanjun-control-db':1006,'xuanjun-ledger-client':1007,'docker':991}
    accounts={u:{'uid':gids[u],'primary_gid':gids[u],'global_group_gids':[gids[u]]}
              for u in ('root','xuanjun_dev','xuanjun-dispatcher','xuanjun-callback')}
    initgroups={user+':'+str(gids[group]):sorted(set([gids[group]]))
                for unused,user,group,extra in sc.DIRECT.values()}
    executable={'path':'/usr/libexec/platform-python3.6','sha256':'1'*64,'format':'ELF'}
    boot=set(compiled['runtime']['services'])|{sc.GATEWAY,sc.NGINX,live.DEFERRED_TIMER}
    facts={'schema':1,'unit_states':states,'nss':{'accounts':accounts,'groups':gids,'initgroups':initgroups},
        'executables':{'/usr/bin/python3':executable},'runtime_manifest_bytes':manifest,
        'background_processes':[],'source_bytes':{},'command_resolutions':{},'boot_before':{u:'disabled' for u in boot},
        'dropin_inventory':{u:{prefix+'/'+u+'.d':{'present':False,'files':{}} for prefix in
            ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')} for u in sc.DIRECT}}
    cb='/etc/systemd/system/xuanjun-uk-owner-callback.service';raw=compiled['rendered_targets'][cb]
    argv=sc.literal_argv(sc.one(sc.unit_sections(raw)['Service'],'ExecStart'))
    owner={'argv':argv,'python_exe':executable['path'],'python_sha256':executable['sha256'],
           'unit_file':cb,'unit_sha256':sc.sha(raw.encode()),'script':argv[1],
           'script_sha256':json.loads(manifest.decode())['files']['stage1/owner_callback_server.py'],
           'release_sha256':compiled['manifest_sha256'],'callback_uid':1004}
    native=json.dumps({'gatewayIdentity':{'user':'xuanjun_dev','exe':'/home/xuanjun_dev/.openclaw/tools/node/bin/node',
        'sha256':'2'*64,'cgroup':'/system.slice/'+sc.GATEWAY}}).encode()
    gateway=b'[Service]\nType=simple\nUser=xuanjun_dev\nGroup=xuanjun_dev\nExecStart=/home/xuanjun_dev/.openclaw/bin/openclaw gateway --port 18789\n'
    facts['gateway_restoration']={'path':sc.UNIT_ROOT+sc.GATEWAY,'sha256':sc.sha(gateway),
        'uid':0,'gid':0,'mode':420,'legacy_receipt_sha256':'8'*64}
    changes=[]
    for p,raw in sorted(targets.items()):
        after={'kind':'FILE','sha256':sc.sha(raw.encode()),'uid':0,'gid':0,'mode':420}
        before=dict(after,sha256=sc.sha(('synthetic prior '+p).encode()))
        changes.append({'path':p,'operation':'REPLACE_EXACT_FILE','before':before,'after':after})
    delta={'kind':'OFFLINE_EPOCH7_DELTA_NOT_INSTALL_PLAN','runtime_manifest_sha256':sc.sha(manifest),'changes':changes}
    return (compiled,{sc.OWNER:json.dumps(owner).encode()},native,gateway,facts),delta


class CompilerTests(unittest.TestCase):
    def setUp(self):self.args,self.delta=compiler_fixture()
    def compile(self):return sc.compile_service_contract(*self.args,candidate_delta=self.delta)
    def repin(self,path,raw):
        self.args[0]['rendered_targets'][path]=raw
        next(r for r in self.args[0]['runtime']['provisioning'] if r['target']==path)['rendered_sha256']=sc.sha(raw.encode())
        next(r for r in self.delta['changes'] if r['path']==path)['after']['sha256']=sc.sha(raw.encode())
    def test_derives_six_direct_roles_and_seventeen_checkpoints_without_future_argv(self):
        result=self.compile()
        self.assertEqual(result['state'],'HOLD');self.assertIsNone(result['unit_checkpoints'])
        self.assertEqual(len(result['process_roles']),6);self.assertEqual(len(result['derived_unit_checkpoints']),17)
        self.assertEqual({r['unit'] for r in result['process_roles']},set(sc.DIRECT))
        self.assertEqual({r['code'] for r in result['unresolved']},
            {'OPENCLAW_PINNED_SOURCE_TOPOLOGY_RECIPE','NGINX_PINNED_SOURCE_TOPOLOGY_RECIPE',
             'DISPATCHER_STARTUP_GIT_RESOLUTION','RELAY_PREFLIGHT_OPENCLAW_CHILD_RECIPE'})
    def test_actual_cmdline_hash_preserves_argv0_not_canonical_binary_alias(self):
        result=self.compile();role=next(r for r in result['process_roles'] if r['unit']=='xuanjun-ledger.service')
        argv=result['derivations']['xuanjun-ledger.service']['argv']
        self.assertEqual(argv[0],'/usr/bin/python3');self.assertEqual(role['executable'],'/usr/libexec/platform-python3.6')
        self.assertEqual(role['argv_sha256'],hashlib.sha256(b'\0'.join(x.encode() for x in argv)+b'\0').hexdigest())
    def test_primary_override_does_not_union_implicit_passwd_gid(self):
        result=self.compile();role=next(r for r in result['process_roles'] if r['unit']=='xuanjun-uk-owner-callback.service')
        self.assertEqual(role['gids'],[1006]*4);self.assertEqual(role['groups'],[1006,1007])
        self.assertNotIn(1004,role['groups'])
    def test_missing_unit_primary_measurement_reports_all_affected_roles(self):
        self.args[4]['nss']['initgroups'].pop('xuanjun-callback:1006')
        result=self.compile();self.assertEqual(len(result['process_roles']),4)
        missing=[r['unit'] for r in result['unresolved'] if r['code']=='MEASURED_INTERPRETER_OR_UNIT_INITGROUPS']
        self.assertEqual(set(missing),{'xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service'})
    def test_missing_canonical_interpreter_is_not_silently_aliased(self):
        self.args[4]['executables']={};self.assertEqual(self.compile()['process_roles'],[])
    def test_dynamic_execstart_and_duplicate_credentials_rejected(self):
        path='/etc/systemd/system/xuanjun-ledger.service';original=self.args[0]['rendered_targets'][path]
        for raw in (original.replace('ExecStart=/usr/bin/python3','ExecStart=/usr/bin/python3 $FLAGS'),
                    original.replace('User=xuanjun-dispatcher','User=xuanjun-dispatcher\nUser=root')):
            self.repin(path,raw)
            with self.assertRaises(ValueError):self.compile()
    def test_unmeasured_dropins_not_ignored(self):
        self.args[4]['unit_states']['xuanjun-ledger.service']['DropInPaths']='/etc/systemd/system/xuanjun-ledger.service.d/override.conf'
        result=self.compile();self.assertNotIn('xuanjun-ledger.service',{r['unit'] for r in result['process_roles']})
    def test_wrong_identity_payload_rejected(self):
        owner=json.loads(self.args[1][sc.OWNER].decode());owner['python_sha256']='3'*64
        self.args[1][sc.OWNER]=json.dumps(owner).encode()
        with self.assertRaisesRegex(ValueError,'OWNER_POLICY'):self.compile()
    def test_manifest_and_rendered_target_hashes_required(self):
        self.args[4]['runtime_manifest_bytes']+=b' '
        with self.assertRaisesRegex(ValueError,'MANIFEST_BYTES'):self.compile()
    def test_source_bytes_cannot_escape_manifest(self):
        self.args[4]['source_bytes']['/tmp/evil']=b'bad'
        with self.assertRaisesRegex(ValueError,'SOURCE_MANIFEST'):self.compile()
    def test_finite_cached_states_bind_exact_reviewed_targets(self):
        result=self.compile();transition=result['unit_transition_contract']
        self.assertEqual(len(transition['units']),15)
        self.assertEqual(transition['targets']['/etc/systemd/system/nginx.service']['sha256'],
                         sc.sha(self.args[0]['rendered_targets']['/etc/systemd/system/nginx.service'].encode()))
        self.assertEqual(transition['units']['nginx.service']['reloaded']['UnitFileState'],'disabled')
        self.assertEqual(result['derived_unit_checkpoints'][15][live.DEFERRED_TIMER]['properties']['ActiveState'],'inactive')
        self.assertEqual(result['derived_unit_checkpoints'][16][live.DEFERRED_TIMER]['properties']['SubState'],'waiting')
    def test_hold_cannot_be_used_as_complete_host_input(self):
        with self.assertRaisesRegex(ValueError,'HOLD'):sc.require_complete_service_contract(self.compile())
    def test_hidden_dropin_files_not_excused_by_empty_cached_DropInPaths(self):
        unit='xj-root-broker.service';root='/run/systemd/system/'+unit+'.d'
        self.args[4]['dropin_inventory'][unit][root]={'present':True,'files':{root+'/override.conf':{}}}
        result=self.compile();self.assertNotIn(unit,{r['unit'] for r in result['process_roles']})
    def test_measured_public_field_adapter_requires_bundle_digest(self):
        facts=self.args[4];nss=facts['nss'];by_primary={}
        for key,groups in nss['initgroups'].items():
            user,gid=key.split(':');by_primary.setdefault(user,{})[gid]=groups
        metadata={'sections':{
            'unit_nss':{'evidence':{'accounts':nss['accounts'],'named_groups':nss['groups'],'nss_by_primary':by_primary}},
            'python_reference':{'evidence':{'final':facts['executables']['/usr/bin/python3']}},
            'dropins':{'evidence':{'units':facts['dropin_inventory']}}},'unsupported_sections':['legacy_gateway']}
        observation={'unit_metadata':metadata,'unit_metadata_sha256':live.digest(metadata),
            'evidence':{'writers':{'units':{u:{'state':v} for u,v in facts['unit_states'].items()},
                'processes':{'background_processes':[],'background_processes_sha256':live.digest([])}}}}
        normalized=sc.service_facts_from_observation(observation,facts['runtime_manifest_bytes'],facts['boot_before'],[])
        self.assertEqual(normalized['fresh_facts']['nss']['initgroups'],nss['initgroups'])
        self.assertIsNone(normalized['retained_gateway_unit'])
        self.assertEqual(normalized,sc.service_facts_from_observation(observation,
            facts['runtime_manifest_bytes'],facts['boot_before']))
        with self.assertRaisesRegex(ValueError,'BACKGROUND_PROJECTION_CONTRADICTION'):
            sc.service_facts_from_observation(observation,facts['runtime_manifest_bytes'],facts['boot_before'],[{}])
        for defect in ('missing','digest'):
            broken=copy.deepcopy(observation)
            if defect=='missing':broken['evidence']['writers']['processes'].pop('background_processes')
            else:broken['evidence']['writers']['processes']['background_processes_sha256']='0'*64
            with self.subTest(defect=defect),self.assertRaisesRegex(ValueError,'BACKGROUND_PROJECTION_REQUIRED'):
                sc.service_facts_from_observation(broken,facts['runtime_manifest_bytes'],facts['boot_before'])
        observation['unit_metadata_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'DIGEST'):
            sc.service_facts_from_observation(observation,facts['runtime_manifest_bytes'],facts['boot_before'],[])
    def test_forged_complete_label_cannot_supply_missing_source_recipe(self):
        result=self.compile();result.update(state='COMPLETE',unresolved=[],unit_checkpoints=result['derived_unit_checkpoints'])
        with self.assertRaisesRegex(ValueError,'SOURCE_RECIPE_HOLD'):sc.require_complete_service_contract(result)
    def test_gateway_public_projection_needs_exact_path_and_account(self):
        args=list(self.args);fields=sc.unit_sections(args[3])['Service']
        fields['ExecStart']=[sc.literal_argv(fields['ExecStart'][0])]
        args[3]={'path':sc.UNIT_ROOT+sc.GATEWAY,'sha256':sc.sha(self.args[3]),'public_service_fields':fields}
        result=sc.compile_service_contract(*args,candidate_delta=self.delta)
        self.assertEqual(result['derivations'][sc.GATEWAY]['unit_sha256'],args[3]['sha256'])
        fields['ExecStart'].insert(0,[]);fields['User']=['root','xuanjun_dev'];fields['Group']=['root','']
        sc.compile_service_contract(*args,candidate_delta=self.delta)
        fields['ExecStart'].append([])
        with self.assertRaisesRegex(ValueError,'COMMAND_RESET'):
            sc.compile_service_contract(*args,candidate_delta=self.delta)
        fields['ExecStart'].pop()
        args[3]['path']='/tmp/unowned.service'
        with self.assertRaisesRegex(ValueError,'PARSED_GATEWAY'):
            sc.compile_service_contract(*args,candidate_delta=self.delta)
    def test_retained_byte_identical_unit_has_no_transition_exception(self):
        path='/etc/systemd/system/nginx.service';row=next(r for r in self.delta['changes'] if r['path']==path)
        row.update(operation='RETAIN',before=copy.deepcopy(row['after']))
        result=self.compile();self.assertNotIn(path,result['unit_transition_contract']['targets'])
        self.assertNotIn('nginx.service',result['unit_transition_contract']['units'])
    def test_owner_mask_replacement_is_included_even_without_old_file_bytes(self):
        path='/etc/systemd/system/xuanjun-uk-owner-callback.service'
        row=next(r for r in self.delta['changes'] if r['path']==path)
        row.update(operation='REPLACE_EXACT_OWNER_MASK',before={'kind':'MASK','link':'/dev/null'})
        self.assertIn(path,self.compile()['unit_transition_contract']['targets'])
    def test_retained_flag_cannot_hide_changed_target(self):
        self.delta['changes'][0]['operation']='RETAIN'
        with self.assertRaisesRegex(ValueError,'RETAIN_OR_REPLACE'):self.compile()
    def test_missing_gateway_restore_evidence_is_an_explicit_hold(self):
        self.args[4].pop('gateway_restoration')
        self.assertIn('GATEWAY_RESTORATION_SOURCE_EVIDENCE',{r['code'] for r in self.compile()['unresolved']})
    def test_gateway_restore_policy_is_independent_of_retained_dropin(self):
        result=self.compile();row=result['unit_transition_contract']['gateway_restoration']
        self.assertEqual(row['sha256'],sc.sha(self.args[3]));self.assertEqual(row['boot_before'],'disabled')
        self.assertEqual(row['before']['LoadState'],'masked')
    def add_git_facts(self):
        # Exact public source is test data, parsed as AST without import/exec.
        root=runtime_fixture_root()
        source=(root/'stage1/development_service.py').read_bytes()
        facts=self.args[4];facts['source_bytes']['stage1/development_service.py']=source
        python=facts['executables']['/usr/bin/python3'];python.update(dev=8,ino=99)
        git={'path':'/usr/bin/git','sha256':'5'*64,'format':'ELF','dev':8,'ino':88}
        facts['executables']['git']=git
        facts['command_resolutions']['xuanjun-development-dispatcher.service']={
            'command':'git','path_environment':'/usr/local/bin:/usr/bin','entries':[
                {'directory':'/usr/local/bin','uid':0,'gid':0,'mode':493,'dev':8,'ino':10,'git':None},
                {'directory':'/usr/bin','uid':0,'gid':0,'mode':493,'dev':8,'ino':11,
                 'git':{k:git[k] for k in ('path','sha256','dev','ino')}}]}
        path='/etc/xuanjun-development/dispatcher.json';raw='{"fixture":"public-synthetic-config"}\n'
        self.args[0]['rendered_targets'][path]=raw
        self.args[0]['runtime']['provisioning'].append({'target':path,'owner_uid':0,'group_gid':0,'mode':420,'rendered_sha256':sc.sha(raw.encode())})
        after={'kind':'FILE','sha256':sc.sha(raw.encode()),'uid':0,'gid':0,'mode':420}
        self.delta['changes'].append({'path':path,'operation':'REPLACE_EXACT_FILE',
            'before':dict(after,sha256='6'*64),'after':after})
    def test_exact_readonly_git_child_from_public_pinned_ast(self):
        self.add_git_facts();result=self.compile();unit='xuanjun-development-dispatcher.service'
        block=result['derived_service_role_contract']['units'][unit]
        self.assertEqual([r['name'] for r in block['roles']],['main','startup_git'])
        child=block['roles'][1]
        self.assertEqual(child['command']['sha256'],sc.cmdline_sha256(['git','-c','core.hooksPath=/dev/null','rev-parse','HEAD']))
        self.assertEqual(child['maximum'],1);self.assertEqual(child['parent'],{'kind':'ROLE','role':'main'})
        self.assertEqual(child['identity']['uids'],[1003]*4)
        self.assertNotIn(unit,{r['unit'] for r in result['process_roles']})
        self.assertNotIn('DISPATCHER_STARTUP_GIT_RESOLUTION',{r['code'] for r in result['unresolved']})
    def test_git_family_cannot_admit_write_command_or_foreign_parent(self):
        import epoch7_service_roles as sr
        self.add_git_facts();block=self.compile()['derived_service_role_contract']['units']['xuanjun-development-dispatcher.service']
        for field,value in [('command',{'mode':'EXACT_ARGV_SHA256','sha256':sc.cmdline_sha256(['git','push'])}),
                            ('parent',{'kind':'MANAGER','pid':1}),('maximum',2)]:
            bad=copy.deepcopy(block);bad['roles'][1][field]=value
            with self.assertRaises(ValueError):
                sr.validate_contract({'schema':1,'units':{'xuanjun-development-dispatcher.service':bad}},live.digest,live._path,live._role)
    def test_git_resolution_cannot_skip_earlier_executable(self):
        self.add_git_facts();row=self.args[4]['command_resolutions']['xuanjun-development-dispatcher.service']['entries'][0]
        row['git']={'path':'/usr/local/bin/git','sha256':'7'*64,'dev':8,'ino':77}
        with self.assertRaisesRegex(ValueError,'FIRST_EXECUTABLE'):self.compile()
    def test_writable_git_search_directory_rejected(self):
        self.add_git_facts();self.args[4]['command_resolutions']['xuanjun-development-dispatcher.service']['entries'][0]['mode']=511
        with self.assertRaisesRegex(ValueError,'PROTECTED_SEARCH'):self.compile()
    def test_unknown_git_binary_inode_not_invented(self):
        self.add_git_facts();self.args[4]['executables']['git'].pop('ino')
        with self.assertRaises(ValueError):self.compile()
    def test_changed_startup_source_does_not_authorize_git_recipe(self):
        self.add_git_facts();self.args[4]['source_bytes']['stage1/development_service.py']+=b'\n# drift'
        with self.assertRaisesRegex(ValueError,'SOURCE_MANIFEST_PIN'):self.compile()
    def test_no_implicit_boot_state(self):
        self.args[4]['boot_before'].pop(sc.GATEWAY)
        with self.assertRaisesRegex(ValueError,'BOOT'):self.compile()

class NginxRecipeTests(unittest.TestCase):
    def setUp(self):
        import epoch7_nginx_recipe as nr
        self.nr=nr;self.args,self.delta=compiler_fixture()
        root=runtime_fixture_root()
        compiled,facts=self.args[0],self.args[4]
        substitutions={'@@OWNER_HOST@@':'fixture.example.invalid','@@TLS_CERT@@':'/fixture/cert.pem',
                       '@@TLS_KEY@@':'/fixture/key.pem'}
        for target,relative in ((nr.UNIT,'deploy/p2-nginx.service'),(nr.MAIN,'deploy/p2-nginx-main.conf'),
            (nr.OWNER,'deploy/uk-owner-workbench/nginx.conf.template')):
            raw=(root/relative).read_bytes();facts['source_bytes'][relative]=raw;text=raw.decode()
            if target==nr.OWNER:
                for key,value in substitutions.items():text=text.replace(key,value)
            if target not in compiled['rendered_targets']:
                compiled['rendered_targets'][target]=text
                compiled['runtime']['provisioning'].append({'target':target,'owner_uid':0,'group_gid':0,
                    'mode':420,'rendered_sha256':sc.sha(text.encode()),
                    'replacements':substitutions if target==nr.OWNER else {}})
                after={'kind':'FILE','sha256':sc.sha(text.encode()),'uid':0,'gid':0,'mode':420}
                self.delta['changes'].append({'path':target,'operation':'REPLACE_EXACT_FILE',
                    'before':dict(after,sha256='7'*64),'after':after})
        facts['nss']['accounts']['nginx']={'uid':990,'primary_gid':990,'global_group_gids':[990]}
        facts['nss']['groups']['nginx']=990;facts['nss']['initgroups']['nginx:990']=[990,992]
        facts['executables']['/usr/sbin/nginx']={'path':'/usr/sbin/nginx','sha256':nr.VENDOR_ELF,
            'format':'ELF','dev':8,'ino':400}
        facts['dropin_inventory']['nginx.service']={prefix+'/nginx.service.d':{'present':False,'files':{}}
            for prefix in ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')}
        raw=b'types { text/plain txt text; application/json json; }\n'
        facts['nginx_recipe_evidence']={'schema':1,'online_cpu_count':2,
            'manager_credentials':{'uids':[0]*4,'gids':[0]*4,'groups':[0,777]},
            'mime_types':{'path':nr.MIME,'raw':raw,'sha256':sc.sha(raw)},
            'rpm_nevra':list(nr.VENDOR_NEVRA),'source_match':None}
        self.facts=facts;self.measured=facts['nginx_recipe_evidence']

    def compile(self):return sc.compile_service_contract(*self.args,candidate_delta=self.delta)

    def test_official_vendor_recipe_derives_exact_roles_from_fresh_pins(self):
        result=self.compile();recipe=result['derivations'][sc.NGINX]
        self.assertTrue(recipe['deployed_source_match']);self.assertEqual(result['state'],'HOLD')
        self.assertNotIn(sc.NGINX,{r['unit'] for r in result['unresolved']})
        roles=recipe['block']['roles'];self.assertEqual(roles[0]['identity']['groups'],[0,777])
        self.assertEqual(roles[1]['identity']['groups'],[990,992]);self.assertEqual(roles[1]['maximum'],2)
        self.assertEqual(roles[0]['command']['values'],['nginx: master process /usr/sbin/nginx -c '+self.nr.MAIN])
        self.assertEqual(roles[1]['command']['values'],['nginx: worker process'])
        self.assertEqual(recipe['vendor_profile']['rpm_signature'],'NOT_VERIFIED')

    def test_version_alone_cannot_match_deployed_vendor_source(self):
        self.facts['executables']['/usr/sbin/nginx']['sha256']='9'*64
        result=self.compile();self.assertFalse(result['derivations'][sc.NGINX]['deployed_source_match'])
        self.assertIn('NGINX_DEPLOYED_SOURCE_MATCH',{r['code'] for r in result['unresolved']})

    def test_new_version_requires_new_source_recipe(self):
        self.measured['rpm_nevra'][2]='1.26.0'
        with self.assertRaisesRegex(ValueError,'MATCHED_VERSION'):self.compile()

    def test_missing_measured_inode_never_invented(self):
        self.facts['executables']['/usr/sbin/nginx'].pop('ino');self.facts['executables']['/usr/sbin/nginx'].pop('dev')
        self.assertIn('NGINX_PINNED_SOURCE_TOPOLOGY_RECIPE',{r['code'] for r in self.compile()['unresolved']})

    def test_mime_file_cannot_import_cache_or_other_config(self):
        row=self.measured['mime_types']
        for raw in (b'include /tmp/extra.conf;',b'types { include evil; }',b'types { text/plain txt; } load_module evil;'):
            row.update(raw=raw,sha256=sc.sha(raw))
            with self.subTest(raw=raw),self.assertRaises(ValueError):self.compile()

    def test_mime_bytes_are_bound_to_measured_digest(self):
        self.measured['mime_types']['raw']+=b' '
        with self.assertRaisesRegex(ValueError,'MIME_DIGEST'):self.compile()

    def test_owner_substitution_cannot_add_directive(self):
        row=next(r for r in self.args[0]['runtime']['provisioning'] if r['target']==self.nr.OWNER)
        row['replacements']['@@TLS_KEY@@']='/fixture/key.pem;include /tmp/evil'
        with self.assertRaises(ValueError):self.compile()

    def test_hidden_dropin_does_not_fit_reviewed_base_profile(self):
        self.facts['dropin_inventory']['nginx.service']['/run/systemd/system/nginx.service.d']={
            'present':True,'files':{'extra.conf':{}}}
        with self.assertRaisesRegex(ValueError,'DROPIN_CLOSURE'):self.compile()

    def test_cpu_count_bound_is_not_unlimited_workers(self):
        self.measured['online_cpu_count']=257
        with self.assertRaisesRegex(ValueError,'CPU_COUNT_BOUND'):self.compile()

    def test_master_credentials_require_actual_root_manager(self):
        self.measured['manager_credentials']['gids']=[42]*4
        with self.assertRaisesRegex(ValueError,'MANAGER_CREDENTIALS'):self.compile()

    def test_caller_verified_flag_is_not_source_match(self):
        self.measured['source_match']={'verified':True}
        with self.assertRaisesRegex(ValueError,'SOURCE_BINDING'):self.compile()


class ObservationAdapterTests(unittest.TestCase):
    """Synthetic collector-shaped evidence, never a claim about the UK host."""
    def setUp(self):
        self.args,self.delta=compiler_fixture();facts=self.args[4];nss=facts['nss']
        by_primary={}
        for key,groups in nss['initgroups'].items():
            user,gid=key.split(':');by_primary.setdefault(user,{})[gid]=groups
        unit='xuanjun-development-dispatcher.service';self.unit=unit
        manager={'uids':[0]*4,'gids':[0]*4,'groups':[0,777],'fixture':'manager'}
        fields=sc.unit_sections(self.args[3])['Service']
        fields['ExecStart']=[sc.literal_argv(fields['ExecStart'][0])]
        original={k:v for k,v in facts['gateway_restoration'].items() if k!='legacy_receipt_sha256'}
        sections={
            'unit_nss':{'evidence':{'accounts':nss['accounts'],'named_groups':nss['groups'],'nss_by_primary':by_primary}},
            'python_reference':{'evidence':{'final':facts['executables']['/usr/bin/python3']}},
            'dropins':{'evidence':{'units':facts['dropin_inventory']}},
            'legacy_gateway':{'evidence':{'original_unit':original,'backup_sha256':sc.sha(self.args[3]),
                'journal_sha256':'8'*64,'public_service_fields':fields}},
            'online_cpus':{'evidence':{'online_count':2}}}
        resolution={'command':'git','path_environment':'/usr/bin','entries':[{
            'directory':'/usr/bin','uid':0,'gid':0,'mode':493,'dev':8,'ino':10,
            'git':{'path':'/usr/bin/git','sha256':'7'*64,'dev':8,'ino':20}}]}
        sections['command_resolutions']={'state':'MEASURED_UNREVIEWED','evidence':{
            'unit':unit,'resolution':resolution,'collector_path_used':False,'provenance':{
            'source':'SYSTEM_MANAGER_CHILD_ENVIRONMENT','manager_sha256':live.digest(manager),
            'dropins_sha256':live.digest(facts['dropin_inventory'][unit]),'systemctl_sha256':'9'*64,
            'unit_sha256':'6'*64,'distro_matching_build':'NOT_VERIFIED'}}}
        import epoch7_nginx_recipe as nr
        mime=b'types { text/plain txt; }\n'
        source={'sections':{'nginx_mime_types':{'state':'MEASURED_UNREVIEWED','evidence':{
            'path':nr.MIME,'sha256':sc.sha(mime),'private_content_base64':base64.b64encode(mime).decode('ascii')}}}}
        self.observation={'unit_metadata':{'sections':sections,'unsupported_sections':[]},
            'source_review_inputs':source,'evidence':{'writers':{'manager':manager,
            'units':{u:{'state':v} for u,v in facts['unit_states'].items()},
            'processes':{'background_processes':[],'background_processes_sha256':live.digest([])}},
            'retained':{'prerequisites':{'rpm_nevra':{'nginx':list(nr.VENDOR_NEVRA)}}}}}
        self.repin()

    def repin(self):
        self.observation['unit_metadata_sha256']=live.digest(self.observation['unit_metadata'])
        self.observation['source_review_inputs_sha256']=live.digest(self.observation['source_review_inputs'])

    def normalize(self):
        return sc.service_facts_from_observation(self.observation,self.args[4]['runtime_manifest_bytes'],
            self.args[4]['boot_before'])

    def test_measured_manager_api_path_is_sufficient_without_vendor_c_equivalence(self):
        facts=self.normalize()['fresh_facts']
        self.assertEqual(facts['command_resolutions'][self.unit]['path_environment'],'/usr/bin')
        self.assertEqual(facts['executables']['git']['ino'],20)

    def test_collector_path_or_changed_manager_or_dropins_rejected(self):
        for defect in ('collector','manager','dropins'):
            original=copy.deepcopy(self.observation)
            row=self.observation['unit_metadata']['sections']['command_resolutions']['evidence']
            if defect=='collector':row['collector_path_used']=True
            else:row['provenance'][defect+'_sha256']='0'*64
            self.repin()
            with self.subTest(defect=defect),self.assertRaisesRegex(ValueError,'PATH_PROVENANCE'):self.normalize()
            self.observation=original

    def test_original_gateway_projection_normalizes_exact_restore_policy(self):
        result=self.normalize()
        self.assertEqual(result['fresh_facts']['gateway_restoration'],self.args[4]['gateway_restoration'])
        self.assertEqual(result['retained_gateway_unit']['sha256'],sc.sha(self.args[3]))

    def test_wrong_original_gateway_hash_is_rejected(self):
        self.observation['unit_metadata']['sections']['legacy_gateway']['evidence']['original_unit']['sha256']='0'*64
        self.repin()
        with self.assertRaisesRegex(ValueError,'RESTORE_PUBLIC_PROJECTION'):self.normalize()

    def test_private_mime_and_measured_credentials_feed_recipe_without_raw_environment(self):
        value=self.normalize()['fresh_facts']['nginx_recipe_evidence']
        self.assertEqual(value['mime_types']['raw'],b'types { text/plain txt; }\n')
        self.assertEqual(value['manager_credentials']['groups'],[0,777])
        self.assertIsNone(value['source_match'])

    def test_private_source_digest_and_decoded_bytes_are_both_checked(self):
        self.observation['source_review_inputs_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SOURCE_REVIEW_INPUT_DIGEST'):self.normalize()
        self.repin()
        self.observation['source_review_inputs']['sections']['nginx_mime_types']['evidence']['sha256']='0'*64
        self.repin()
        with self.assertRaisesRegex(ValueError,'MIME_SOURCE_BYTES_BINDING'):self.normalize()

    def test_missing_cpu_measurement_does_not_create_nginx_recipe(self):
        self.observation['unit_metadata']['sections'].pop('online_cpus');self.repin()
        self.assertNotIn('nginx_recipe_evidence',self.normalize()['fresh_facts'])


if __name__=='__main__':unittest.main()
