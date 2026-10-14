"""Pure actual-source/compiled-byte fixtures. No filesystem or host effects."""
import ast
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
import epoch7_acceptance_rows as m
import activation_control
import epoch7_runtime_acceptance as acceptance

BASE=Path(__file__).resolve().parent.parent
RUNTIME=Path(activation_control.__file__).resolve().parent.parent


def fixture():
    manifest_raw=(RUNTIME/'deploy/integration-manifest.json').read_bytes()
    manifest=json.loads(manifest_raw.decode())
    installer={};exec(compile((RUNTIME/'scripts/uk-integration-install.py').read_bytes(),'<pure-renderer>','exec'),installer)
    rendered={name:installer['render_identity_bytes'](name,(RUNTIME/name).read_bytes(),m.MANIFEST,manifest) for name in manifest['files']}
    hashes={name:m.sha(raw) for name,raw in rendered.items()}
    # Public genuine unit bytes plus explicitly synthetic compiled records. No
    # private original plan or credentials are needed by these portable tests.
    targets={path:b'{"synthetic":"UNREVIEWED_FIXTURE"}\n' for path in m.TARGETS}
    for role,(unit,user,uid,gid) in m.ROLES.items():
        if unit==m.GATEWAY:continue
        relative='deploy/'+('uk-owner-workbench/' if role in ('callback','dashboard') else '')+unit
        targets['/etc/systemd/system/'+unit]=rendered[relative]
    targets[m.GATEWAY_DROPIN]=rendered['deploy/xuanjun-uk-openclaw-p2-docker.conf']
    activation={'schema':1,'state':'PREPARED','epoch':8,'generation':1,
        'release_sha256':m.MANIFEST,'binary_sha256':manifest['files']['stage1/native_gateway_controller.py'],'config_sha256':m.sha(targets[m.CONFIG+'dispatcher.json']),
        'ledger_uuid':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','instance':'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        'db_path':'/var/lib/xuanjun-development/generations/1/control.db','ledger_socket':'/run/xuanjun-development/ledger.sock'}
    compiled={'kind':'PRIVATE_RETAINED_BINDINGS_NOT_INSTALL_PLAN','install_admission':False,
        'manifest_sha256':m.MANIFEST,'rendered_targets':targets,'old_rendered_targets':copy.deepcopy(targets),
        'runtime':{'provisioning':[{'target':path,'rendered_sha256':m.sha(raw)} for path,raw in sorted(targets.items())]},
        'activation_proposal':activation}
    identities={path:b'{"fixture":"SYNTHETIC_NONSECRET_POLICY"}\n' for path in m.ADDITIONS}
    accounts={name:{'uid':uid,'primary_gid':uid,'global_group_gids':[uid]}
              for name,uid in (('xuanjun_dev',1002),('xuanjun-dispatcher',1003),('xuanjun-callback',1004))}
    raw=b'[Service]\nUser=xuanjun_dev\nGroup=xuanjun_dev\nSupplementaryGroups=fixture-group\n'
    old_dropin=compiled['old_rendered_targets'][m.GATEWAY_DROPIN]
    facts={'accounts':accounts,'nss_by_primary':{user:{gid:[int(gid)] for gid in pairs}
        for user,pairs in m.NSS_PAIRS.items()},'group_ids':{'xuanjun_dev':1002,'xuanjun-dispatcher':1003,
        'xuanjun-callback':1004,'xuanjun-control-db':1006,'xuanjun-ledger-client':1007,'docker':990,'fixture-group':1010},
        'gateway_base_unit':{'path':'/etc/systemd/system/'+m.GATEWAY,'sha256':m.sha(raw),'public_service_fields':m.unit_fields(raw)},
        'unit_dropins':{row[0]:[] for row in m.ROLES.values()},
        'bootstrap':{path:{'kind':'FILE','uid':1004,'gid':1006,'mode':0o600,'nlink':1,'sha256':'c'*64}
                     for path in m.OWNER_PRIVATE}}
    facts['gateway_base_unit']['public_service_fields']['ExecStart']=[['/home/xuanjun_dev/.openclaw/bin/openclaw','gateway','run']]
    facts['unit_dropins'][m.GATEWAY]=[{'path':m.GATEWAY_DROPIN,'sha256':m.sha(old_dropin),'public_service_fields':m.unit_fields(old_dropin)}]
    return compiled,identities,manifest_raw,hashes,facts


def observation_fixture(facts):
    nss={'accounts':copy.deepcopy(facts['accounts']),'nss_by_primary':copy.deepcopy(facts['nss_by_primary']),
        'named_groups':dict(facts['group_ids'],root=0,nginx=991),'unsupported':{}}
    nss['accounts']['root']={'uid':0,'primary_gid':0,'global_group_gids':[0]}
    nss['nss_by_primary']['root']={'0':[0]}
    all_units={row[0] for row in m.ROLES.values()}|{'xj-root-broker.service','nginx.service'};units={}
    for unit in all_units:
        roots={prefix+'/'+unit+'.d':{'present':False,'files':{}} for prefix in
            ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')}
        for row in facts['unit_dropins'].get(unit,[]):
            parent=row['path'].rsplit('/',1)[0];roots[parent]['present']=True
            roots[parent]['files'][row['path']]={'sha256':row['sha256'],
                'metadata':{'kind':'FILE','uid':0,'gid':0,'nlink':1,'mode':0o644,'sha256':row['sha256']},
                'public_service_fields':copy.deepcopy(row['public_service_fields'])}
        units[unit]=roots
    sections={name:{'state':'MEASURED_UNREVIEWED','evidence':{}} for name in
        ('unit_nss','python_reference','native_gateway','legacy_gateway','launcher','nginx_binary',
         'runuser_binary','nginx_config','online_cpus','dropins','boot_links','command_resolutions')}
    sections['unit_nss']['evidence']=nss
    sections['legacy_gateway']['evidence']={'raw_unit_returned':False,
        'backup_sha256':facts['gateway_base_unit']['sha256'],
        'public_service_fields':copy.deepcopy(facts['gateway_base_unit']['public_service_fields'])}
    sections['dropins']['evidence']={'units':units,'unsupported':[],'raw_unit_bytes_returned':False}
    metadata={'schema':1,'kind':'PRIVATE_UNIT_FACTS_UNREVIEWED','state':'COMPLETE_UNREVIEWED',
        'unsupported_sections':[],'sections':sections}
    retained={'bootstrap':copy.deepcopy(facts['bootstrap'])}
    snapshot={'retained_resource_sha256':m.digest(retained)}
    evidence={'retained':retained,'snapshot_sha256':m.digest(snapshot)}
    return {'schema':1,'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED','install_admission':'NOT_GRANTED',
        'snapshot':snapshot,'snapshot_sha256':m.digest(snapshot),'evidence':evidence,
        'evidence_sha256':m.digest(evidence),'unit_metadata':metadata,'unit_metadata_sha256':m.digest(metadata)}


class ObservationProjectionTests(unittest.TestCase):
    def setUp(self):
        self.args=fixture();self.observation=observation_fixture(self.args[-1])
    def update_metadata_hash(self):self.observation['unit_metadata_sha256']=m.digest(self.observation['unit_metadata'])
    def test_exact_collector_projection_matches_manual_fixture_without_io(self):
        before=copy.deepcopy(self.observation)
        with patch('os.open',side_effect=AssertionError('NO_IO')):
            facts=m.acceptance_facts_from_observation(self.observation)
        self.assertEqual(facts,self.args[-1]);self.assertEqual(before,self.observation)
        self.assertEqual(m.compile_access_rows(*(self.args[:-1]+(facts,))),m.compile_access_rows(*self.args))
    def test_unknown_seventh_unit_not_silently_ignored(self):
        roots=self.observation['unit_metadata']['sections']['dropins']['evidence']['units']['xj-root-broker.service']
        next(iter(roots.values()))['state']='UNKNOWN';self.update_metadata_hash()
        with self.assertRaisesRegex(ValueError,'MEASURED_DROPIN_ROOT'):m.acceptance_facts_from_observation(self.observation)
    def test_exact_eight_unit_inventory_required_before_six_role_projection(self):
        units=self.observation['unit_metadata']['sections']['dropins']['evidence']['units']
        self.assertEqual(set(units),{row[0] for row in m.ROLES.values()}|{'xj-root-broker.service','nginx.service'})
        self.assertEqual(len(units),8)
        self.assertEqual(set(m.acceptance_facts_from_observation(self.observation)['unit_dropins']),
                         {row[0] for row in m.ROLES.values()})
        units.pop('nginx.service');self.update_metadata_hash()
        with self.assertRaisesRegex(ValueError,'COMPLETE_EIGHT_UNIT_INVENTORY'):
            m.acceptance_facts_from_observation(self.observation)
    def test_unknown_or_missing_eighth_unit_root_not_silently_ignored(self):
        for prefix in ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system'):
            value=copy.deepcopy(self.observation)
            roots=value['unit_metadata']['sections']['dropins']['evidence']['units']['nginx.service']
            roots[prefix+'/nginx.service.d']['state']='UNKNOWN'
            value['unit_metadata_sha256']=m.digest(value['unit_metadata'])
            with self.assertRaisesRegex(ValueError,'MEASURED_DROPIN_ROOT'):
                m.acceptance_facts_from_observation(value)
            roots.pop(prefix+'/nginx.service.d');value['unit_metadata_sha256']=m.digest(value['unit_metadata'])
            with self.assertRaisesRegex(ValueError,'COMPLETE_DROPIN_ROOTS'):
                m.acceptance_facts_from_observation(value)
    def test_eighth_unit_file_authority_validated_before_projection(self):
        roots=self.observation['unit_metadata']['sections']['dropins']['evidence']['units']['nginx.service']
        root='/etc/systemd/system/nginx.service.d';raw=b'[Service]\nUser=nginx\nGroup=nginx\n'
        row={'sha256':m.sha(raw),'metadata':{'kind':'FILE','uid':0,'gid':0,'nlink':1,
             'mode':0o644,'sha256':m.sha(raw)},'public_service_fields':m.unit_fields(raw)}
        roots[root]={'present':True,'files':{root+'/10-fixture.conf':row}};self.update_metadata_hash()
        self.assertEqual(m.acceptance_facts_from_observation(self.observation),self.args[-1])
        row['metadata']['uid']=991;self.update_metadata_hash()
        with self.assertRaisesRegex(ValueError,'DROPIN_METADATA_BINDING'):
            m.acceptance_facts_from_observation(self.observation)
    def test_missing_or_unknown_unconsumed_section_holds(self):
        self.observation['unit_metadata']['sections']['launcher']['state']='UNKNOWN';self.update_metadata_hash()
        with self.assertRaisesRegex(ValueError,'ALL_UNIT_SECTIONS_MEASURED'):m.acceptance_facts_from_observation(self.observation)
        self.observation['unit_metadata']['sections'].pop('launcher');self.update_metadata_hash()
        with self.assertRaisesRegex(ValueError,'COMPLETE_UNIT_SECTION_SET'):m.acceptance_facts_from_observation(self.observation)
    def test_added_boot_and_command_sections_must_be_present_and_measured(self):
        for section in ('boot_links','command_resolutions'):
            value=copy.deepcopy(self.observation)
            value['unit_metadata']['sections'][section]['state']='UNKNOWN'
            value['unit_metadata_sha256']=m.digest(value['unit_metadata'])
            with self.assertRaisesRegex(ValueError,'ALL_UNIT_SECTIONS_MEASURED'):
                m.acceptance_facts_from_observation(value)
            value['unit_metadata']['sections'].pop(section)
            value['unit_metadata_sha256']=m.digest(value['unit_metadata'])
            with self.assertRaisesRegex(ValueError,'COMPLETE_UNIT_SECTION_SET'):
                m.acceptance_facts_from_observation(value)
    def test_report_metadata_and_retained_digest_drift_hold(self):
        for key in ('snapshot_sha256','evidence_sha256','unit_metadata_sha256'):
            value=copy.deepcopy(self.observation);value[key]='0'*64
            with self.assertRaisesRegex(ValueError,'OBSERVATION_DIGEST_BINDING'):m.acceptance_facts_from_observation(value)
    def test_hold_report_or_incomplete_metadata_cannot_project(self):
        self.observation['kind']='EPOCH7_OBSERVATION_ONLY_HOLD'
        with self.assertRaisesRegex(ValueError,'COMPLETE_OBSERVATION_REQUIRED'):m.acceptance_facts_from_observation(self.observation)
    def test_missing_exact_primary_pair_not_filled_from_global_groups(self):
        self.observation['unit_metadata']['sections']['unit_nss']['evidence']['nss_by_primary']['xuanjun-callback'].pop('1006')
        self.update_metadata_hash()
        with self.assertRaises(KeyError):m.acceptance_facts_from_observation(self.observation)
    def test_unmeasured_dropin_metadata_rejected(self):
        roots=self.observation['unit_metadata']['sections']['dropins']['evidence']['units'][m.GATEWAY]
        row=roots['/etc/systemd/system/'+m.GATEWAY+'.d']['files'][m.GATEWAY_DROPIN]
        row['metadata']['uid']=1002;self.update_metadata_hash()
        with self.assertRaisesRegex(ValueError,'DROPIN_METADATA_BINDING'):m.acceptance_facts_from_observation(self.observation)


class RowCompilerTests(unittest.TestCase):
    def setUp(self):self.args=fixture()
    def compile(self):return m.compile_access_rows(*self.args)
    def test_exact_six_roles_all_required_pins_no_effects(self):
        with patch('os.open',side_effect=AssertionError('NO_IO')),patch('subprocess.Popen',side_effect=AssertionError('NO_COMMAND')):
            rows=self.compile()
        self.assertEqual({row['role'] for row in rows},set(m.ROLES))
        for row in rows:self.assertEqual({p['path']:p['kind'] for p in row['paths']},m.required_paths()[row['role']])
    def test_fixed_local_module_closure_matches_actual_public_source(self):
        modules={path.stem:path for path in (RUNTIME/'stage1').glob('*.py')};edges={}
        for name,path in modules.items():
            imported=set()
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Import):imported.update(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node,ast.ImportFrom) and node.module:imported.add(node.module.split('.')[0])
            edges[name]=imported&set(modules)
        for role,roots in acceptance.READ_MODULE_ROOTS.items():
            seen=set();pending=list(roots)
            while pending:
                name=pending.pop()
                if name in seen:continue
                seen.add(name);pending+=list(edges[name]-seen)
            self.assertEqual(set(acceptance.READ_MODULE_CLOSURE[role]),seen)
            for name in seen:self.assertIn(m.RELEASE+'/stage1/'+name+'.py',m.required_paths()[role])
        rows=self.compile()
        for row in rows:
            # RuntimeAcceptanceChecks adds these exact fields before its 8KiB limit.
            value=dict(row,mode='access',context_sha256='f'*64)
            self.assertLessEqual(len(acceptance.canonical(value)),8192)
    def test_deterministic_without_input_mutation(self):
        before=copy.deepcopy(self.args);first=self.compile();self.assertEqual(first,self.compile());self.assertEqual(before,self.args)
    def test_gateway_groups_derived_from_base_plus_retained_dropin_overlay(self):
        row=next(row for row in self.compile() if row['role']=='gateway')
        self.assertEqual(row['identity']['unit_supplementary_groups'],[990,1007,1010])
        self.assertEqual(row['identity']['groups'],[990,1002,1007,1010])
    def test_overridden_primary_does_not_invent_passwd_group(self):
        rows={row['role']:row for row in self.compile()}
        for role in ('callback','dashboard'):
            self.assertEqual(rows[role]['identity']['nss_groups'],[1006])
            self.assertNotIn(1004,rows[role]['identity']['groups'])
        self.assertEqual(rows['ledger']['identity']['nss_groups'],[1006])
        self.assertEqual(rows['ledger']['identity']['unit_supplementary_groups'],[1003])
        self.assertIn(1003,rows['ledger']['identity']['groups'])  # Explicit unit grant stays.
    def test_explicit_membership_in_old_primary_is_preserved_when_measured(self):
        self.args[4]['nss_by_primary']['xuanjun-callback']['1006']=[1004,1006]
        row=next(row for row in self.compile() if row['role']=='callback')
        self.assertIn(1004,row['identity']['groups'])
    def test_missing_extra_or_root_pair_is_rejected(self):
        for mutation in ('missing','extra','root','no_primary'):
            args=fixture();pairs=args[4]['nss_by_primary']['xuanjun-callback']
            if mutation=='missing':pairs.pop('1006')
            elif mutation=='extra':pairs['1004']=[1004]
            elif mutation=='root':pairs['1006']=[0,1006]
            else:pairs['1006']=[1007]
            with self.assertRaises(ValueError):m.compile_access_rows(*args)
    def test_later_dropin_reset_is_respected(self):
        unit=m.GATEWAY;raw=b'[Service]\nSupplementaryGroups=\nSupplementaryGroups=xuanjun-ledger-client\n'
        self.args[4]['unit_dropins'][unit].append({'path':'/etc/systemd/system/'+unit+'.d/90-test.conf','sha256':m.sha(raw),'public_service_fields':m.unit_fields(raw)})
        row=next(row for row in self.compile() if row['role']=='gateway')
        self.assertEqual(row['identity']['unit_supplementary_groups'],[1007])
    def test_dropin_root_priority_then_basename_order(self):
        unit=m.GATEWAY;entries=self.args[4]['unit_dropins'][unit]
        for root,groups in (('/usr/lib/systemd/system','fixture-group'),('/run/systemd/system','docker')):
            raw=('[Service]\nSupplementaryGroups=\nSupplementaryGroups='+groups+'\n').encode()
            entries.append({'path':root+'/'+unit+'.d/90-groups.conf','sha256':m.sha(raw),
                'public_service_fields':m.unit_fields(raw)})
        entries.sort(key=lambda row:row['path'])
        row=next(row for row in self.compile() if row['role']=='gateway')
        self.assertEqual(row['identity']['unit_supplementary_groups'],[990])
    def test_retained_dropin_public_fields_must_match_pinned_old_bytes(self):
        self.args[4]['unit_dropins'][m.GATEWAY][0]['public_service_fields']['SupplementaryGroups']=['fixture-group']
        with self.assertRaisesRegex(ValueError,'RETAINED_DROPIN_BEFORE_BYTES'):self.compile()
    def test_gateway_raw_or_unparsed_secret_fields_are_not_accepted(self):
        self.args[4]['gateway_base_unit']['public_service_fields']['Environment']=['SECRET=not-emitted']
        with self.assertRaisesRegex(ValueError,'PUBLIC_UNIT_FIELDS'):self.compile()
    def test_actual_quiesced_serializer_matches_descriptor_writer(self):
        proposal=self.args[0]['activation_proposal'];raw=m.quiesced_descriptor_bytes(proposal)
        value=json.loads(raw.decode());self.assertEqual(value['state'],'QUIESCED');self.assertEqual(value['epoch'],8)
        store=object.__new__(activation_control.ActivationStore);store.parent='/fixture';store.descriptor='/fixture/active.json'
        captured=[]
        with patch.object(activation_control.tempfile,'mkstemp',return_value=(123,'/fixture/tmp')), \
             patch.object(activation_control.os,'fchmod'),patch.object(activation_control.os,'fsync'), \
             patch.object(activation_control.os,'close'),patch.object(activation_control.os,'replace'), \
             patch.object(activation_control.os.path,'exists',return_value=False), \
             patch.object(activation_control,'_write_all',side_effect=lambda fd,data:captured.append(data)), \
             patch.object(activation_control,'_fsync_dir'):
            store._write_descriptor(value)
        self.assertEqual(captured,[raw])
        for row in self.compile():
            for path in row['paths']:
                if path['path']==m.ACTIVE:self.assertEqual(path['sha256'],m.sha(raw))
        self.assertEqual(proposal['state'],'PREPARED')
    def test_activation_controller_must_match_exact_runtime_payload(self):
        self.args[0]['activation_proposal']['binary_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'ACTIVATION_CONTROLLER_BYTES'):self.compile()
    def test_active_or_wrong_epoch_proposal_rejected(self):
        for key,value in (('state','ACTIVE'),('epoch',9)):
            bad=copy.deepcopy(self.args[0]['activation_proposal']);bad[key]=value
            with self.assertRaises(ValueError):m.quiesced_descriptor_bytes(bad)
    def test_missing_secret_metadata_no_default(self):
        self.args[4]['bootstrap'].pop(next(iter(m.OWNER_PRIVATE)))
        with self.assertRaisesRegex(ValueError,'FIVE_OWNER_PRIVATE_FACTS'):self.compile()
    def test_secret_root_owner_or_broader_mode_rejected(self):
        for field,value in (('uid',0),('gid',1004),('mode',0o640),('nlink',2)):
            args=fixture();next(iter(args[4]['bootstrap'].values()))[field]=value
            with self.assertRaisesRegex(ValueError,'OWNER_PRIVATE_METADATA'):m.compile_access_rows(*args)
    def test_missing_named_group_no_numeric_guess(self):
        self.args[4]['group_ids'].pop('docker')
        with self.assertRaisesRegex(ValueError,'MISSING_NAMED_GROUP_GID'):self.compile()
    def test_wrong_nss_uid_rejected(self):
        self.args[4]['accounts']['xuanjun-callback']['uid']=1002
        with self.assertRaisesRegex(ValueError,'EXACT_ROLE_UID'):self.compile()
    def test_missing_dropin_inventory_is_not_empty_default(self):
        self.args[4]['unit_dropins'].pop(m.GATEWAY)
        with self.assertRaisesRegex(ValueError,'COMPLETE_UNIT_DROPIN_INVENTORY'):self.compile()
    def test_unpinned_gateway_backup_rejected(self):
        self.args[4]['gateway_base_unit']['sha256']='unmeasured'
        with self.assertRaisesRegex(ValueError,'EXACT_HASH'):self.compile()
    def test_unexpected_dropin_location_rejected(self):
        self.args[4]['unit_dropins'][m.GATEWAY][0]['path']='/run/systemd/system/other.conf'
        with self.assertRaisesRegex(ValueError,'FIXED_UNIT_DROPIN_PATH'):self.compile()
    def test_nonliteral_group_or_continuation_hold(self):
        for raw in (b'[Service]\nUser=%i\n',b'[Service]\nUser=xuanjun_dev\nSupplementaryGroups="docker"\n',b'[Service]\nUser=xuanjun_dev\\\n'):
            with self.assertRaises(ValueError):m.unit_identity([raw])
    def test_duplicate_dropin_or_changed_current_bytes_rejected(self):
        original=self.args[4]['unit_dropins'][m.GATEWAY][0]
        self.args[4]['unit_dropins'][m.GATEWAY].append(copy.deepcopy(original))
        with self.assertRaisesRegex(ValueError,'SORTED_UNIQUE_UNIT_DROPINS'):self.compile()
        self.args[4]['unit_dropins'][m.GATEWAY].pop();original['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'RETAINED_DROPIN_BEFORE_BYTES'):self.compile()
    def test_rendered_target_hash_drift_rejected(self):
        self.args[0]['rendered_targets'][m.CONFIG+'dispatcher.json']+=b' '
        with self.assertRaisesRegex(ValueError,'TARGET_RENDERED_BYTES'):self.compile()
    def test_release_file_set_and_source_hash_bound(self):
        self.args[3]['stage1/ledger_service.py']='0'*64
        with self.assertRaisesRegex(ValueError,'UNRENDERED_PAYLOAD_HASH'):self.compile()
        self.args[3].pop('stage1/ledger_service.py')
        with self.assertRaisesRegex(ValueError,'EXACT107_RENDERED_PAYLOAD_SET'):self.compile()
    def test_two_exact_additive_paths_required(self):
        self.args[1]['/etc/other.json']=b'{}'
        with self.assertRaisesRegex(ValueError,'EXACT_TWO_IDENTITIES'):self.compile()
    def test_missing_facts_consolidated(self):
        self.assertEqual(m.missing_inputs({}),sorted(m.FACTS))


if __name__=='__main__':unittest.main()
