"""Pure/compiler and refusal-boundary tests; no host assembly or admission."""
import copy
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

import epoch7_host_factory as f
import epoch7_host_phases as h
import epoch7_host_observer as o
import epoch7_timer_tail as t
import epoch7_bounded_stager as stager
import epoch7_delta as d
from test_epoch7_delta import fixture


class FactoryTests(unittest.TestCase):
    def test_loader_input_endpoint_is_finite_and_review_neutral(self):
        value=f.host_input_contract()
        self.assertEqual(set(value['seed_fields']),f.INPUTS-f.DERIVED_INPUTS)
        self.assertEqual(len(value['seed_fields']),16)
        self.assertEqual(len(value['private_fields']),11)
        self.assertEqual(len(value['cached_fields']),5)
        self.assertEqual(len(value['private_utf8_byte_fields']),6)
        self.assertFalse(value['install_admission'])
        self.assertEqual(value['runtime_manifest_sha256'],h.MANIFEST)
    def test_unmeasured_manager_ids_are_not_invented(self):
        value=ObservationInputTests().bundle();value['evidence']['writers']['manager'].pop('uids')
        value['evidence_sha256']=d.digest(value['evidence'])
        with self.assertRaisesRegex(ValueError,'MEASURED_SYSTEM_MANAGER'):f.observation_inputs(value)
    def test_missing_inputs_is_one_finite_list(self):
        self.assertEqual(f.missing_inputs({}),sorted(f.INPUTS))
        self.assertIn('resource_views',f.missing_inputs({}))
        self.assertIn('timer_raw_baseline',f.missing_inputs({}))
    def test_missing_input_refuses_before_constructing_host_or_fetching(self):
        with mock.patch.object(f,'ExistingInstallLock') as lock,mock.patch.object(f,'CompleteApprovalVerifier') as approval:
            with self.assertRaisesRegex(ValueError,'COMPLETE_MEASURED_INPUTS'):
                f.assemble_host_driver(b'{}',{},7000000001,'a'*64)
            lock.assert_not_called();approval.assert_not_called()
    def test_input_fingerprint_preserves_types_and_all_bytes(self):
        self.assertNotEqual(f.input_digest({'x':b'private'}),f.input_digest({'x':['bytes',7,h.sha(b'private')]}))
        self.assertNotEqual(f.input_digest({'x':b'private'}),f.input_digest({'x':{'type':'bytes','length':7,'sha256':h.sha(b'private')}}))
        self.assertNotEqual(f.input_digest({'x':True}),f.input_digest({'x':1}))
        self.assertNotEqual(f.input_digest({'x':b'private'}),f.input_digest({'x':b'private2'}))
    def test_nested_container_digest_binds_order_type_length_and_values(self):
        base={'a':[{'x':b'one'},2],'b':False}
        self.assertEqual(f.input_digest(base),f.input_digest({'b':False,'a':[{'x':b'one'},2]}))
        for changed in ({'a':[{'x':b'two'},2],'b':False},{'a':({'x':b'one'},2),'b':False},
                        {'a':[2,{'x':b'one'}],'b':False},{'a':[{'x':b'one'},2,2],'b':False},
                        {'a':[{'x':b'one'},2],'b':0}):
            self.assertNotEqual(f.input_digest(base),f.input_digest(changed))
        self.assertNotEqual(f.input_digest(b'one'),d.digest(['bytes',3,h.sha(b'one')]))
    def test_repeated_nested_proofs_keep_existing_canonical_limit(self):
        proof={'files':{str(i):{'stamp':list(range(9)),'raw':b'x'*2048} for i in range(128)}}
        repeated={'checkpoints':[copy.deepcopy(proof) for unused in range(17)]}
        pin=f.input_digest(repeated);repeated['checkpoints'][8]['files']['77']['raw']+=b'y'
        self.assertNotEqual(pin,f.input_digest(repeated))
    def test_no_live_callable_can_be_hidden_in_inputs(self):
        with self.assertRaisesRegex(ValueError,'FINITE_INPUT_TYPES'):f.input_digest({'x':lambda:True})
    def test_database_before_uses_supporting_full_stamp_and_renames_keys(self):
        row={'dev':8,'ino':9,'uid':0,'gid':0,'mode':0o600,'size':4096,'mtime_ns':11,'ctime_ns':12,'nlink':1}
        actual=f.runtime_database_before({'retained':{'database_sets':{d.DB:{'file':row}}}})
        self.assertEqual(actual['device'],8);self.assertEqual(actual['inode'],9)
        self.assertEqual(actual['mtime_ns'],11);self.assertNotIn('dev',actual)
    def test_missing_full_database_stamp_is_not_invented(self):
        s,c=fixture()
        with self.assertRaises(KeyError):f.runtime_database_before({'retained':{'database_sets':{d.DB:{'file':s['database']}}}})
    def test_sidecar_compiler_keeps_every_explicit_absence(self):
        supporting={'retained':{'database_sets':{p:{'sidecars':{}} for p in o.snap.DATABASES}}}
        result=f.retained_sidecar_pins(supporting)
        self.assertEqual(len(result),6);self.assertTrue(all(v is None for v in result.values()))
    def test_sidecar_compiler_retains_full_present_pin(self):
        supporting={'retained':{'database_sets':{p:{'sidecars':{}} for p in o.snap.DATABASES}}}
        base=next(p for p in o.snap.DATABASES if p!=d.DB)
        supporting['retained']['database_sets'][base]['sidecars']['-wal']={'kind':'FILE','size':0,'sha256':'a'*64}
        self.assertEqual(f.retained_sidecar_pins(supporting)[base+'-wal'],{'kind':'REGULAR','size':0,'sha256':'a'*64})
    def test_source_factory_does_not_offer_runner_or_approval_overrides(self):
        import inspect
        self.assertEqual(tuple(inspect.signature(f.assemble_host_driver).parameters),
                         ('approved_plan_raw','inputs','review_id','review_body_sha256'))


class ObservationInputTests(unittest.TestCase):
    def bundle(self):
        value={'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED','snapshot':{'fixture':True},'policy':{'fixture':True},
            'evidence':{'writers':{'manager':{'pid':1,'uids':[0,0,0,0],'binary_path':'/usr/lib/systemd/systemd','binary_sha256':'a'*64,
                'boot_id':'fixture boot','starttime':42,'channels':{'socket':'fixture'}}}},'unit_metadata':{'fixture':True},
            'probe_metadata':{'retained_tls_schedule':{'raw':{unit:dict(line.split('=',1) for line in raw.decode().splitlines())
                for unit,raw in TimerTests().raw().items()},'missing_fields':[]}}}
        for key in ('snapshot','policy','evidence','unit_metadata','probe_metadata'):value[key+'_sha256']=d.digest(value[key])
        return value
    def test_manager_and_timer_rows_are_derived_not_requested(self):
        value=self.bundle();derived=f.observation_inputs(value)
        self.assertEqual(derived['manager']['uids'],[0]*4)
        self.assertEqual(derived['manager']['channels_sha256'],d.digest({'socket':'fixture'}))
        self.assertEqual(derived['timer_raw_baseline'],TimerTests().raw())
        self.assertEqual(derived['database_sidecar_policy'],f.SIDECAR_POLICY)
        self.assertTrue({'snapshot','manager','executable_specs','acceptance_facts','resource_views'}<=f.DERIVED_INPUTS)
    def test_forged_observation_section_never_enters_compilation(self):
        value=self.bundle();value['evidence']['writers']['manager']['starttime']=99
        with self.assertRaisesRegex(ValueError,'EVIDENCE_DIGEST'):f.observation_inputs(value)
    def test_incomplete_unit_metadata_is_not_a_source_for_executable_grants(self):
        value={'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED','unit_metadata':{'state':'INCOMPLETE'},
               'unit_metadata_sha256':d.digest({'state':'INCOMPLETE'})}
        with self.assertRaisesRegex(ValueError,'COMPLETE_UNIT_METADATA'):f.build_executable_specs(value,b'{}')


class BootCompilerTests(unittest.TestCase):
    def make(self):
        unit=b'[Service]\nType=simple\n[Install]\nWantedBy=multi-user.target\n'
        rendered={'/etc/systemd/system/'+name:unit for name in f.BOOT_UNITS}
        compiled={'rendered_targets':rendered,'old_rendered_targets':copy.deepcopy(rendered),'tls_config_bytes':b'{}'}
        fields={'WantedBy':['multi-user.target'],'RequiredBy':[],'Alias':[],'Also':[]}
        roots={root:{'present':False,'directories':{},'links':[]} for root in f.BOOT_LOOKUP_ROOTS}
        root='/etc/systemd/system';roots[root]={'present':True,'directories':{root:{}},'links':[],
            'selected_nonlinks':{},'scan_scope':'BOUNDED_RECURSIVE_NOFOLLOW','all_link_inventory_sha256':'a'*64}
        metadata={'sections':{'boot_links':{'state':'MEASURED_UNREVIEWED','evidence':{
            'units':sorted(f.BOOT_RESTORED),'roots':roots,'unsupported_roots':[]}},
            'legacy_gateway':{'state':'MEASURED_UNREVIEWED','evidence':{'public_install_fields':fields}}}}
        value={'unit_metadata':metadata,'unit_metadata_sha256':d.digest(metadata),'evidence':{'writers':{'units':{
            name:{'state':{'UnitFileState':'masked' if name in f.BOOT_RESTORED else 'enabled',
                          'LoadState':'masked' if name in f.BOOT_RESTORED else 'loaded'}} for name in f.BOOT_UNITS}}}}
        return value,compiled
    def refresh(self,value):value['unit_metadata_sha256']=d.digest(value['unit_metadata'])
    def test_complete_absence_with_authenticated_install_rules_derives_disabled(self):
        value,compiled=self.make();result=f.boot_before_from_observation(value,compiled)
        self.assertEqual(set(result),set(f.BOOT_UNITS))
        self.assertTrue(all(result[u]=='disabled' for u in f.BOOT_RESTORED))
        self.assertTrue(all(result[u]=='enabled' for u in set(f.BOOT_UNITS)-f.BOOT_RESTORED))
    def test_persistent_exact_dependency_preserves_enabled(self):
        value,compiled=self.make();unit='xuanjun-uk-openclaw.service';root='/etc/systemd/system'
        value['unit_metadata']['sections']['boot_links']['evidence']['roots'][root]['links'].append({
            'path':root+'/multi-user.target.wants/'+unit,'link':'../'+unit,'kind':'DEPENDENCY','unit':unit,
            'resolved_reference':root+'/'+unit,'metadata':{'uid':0,'gid':0,'nlink':1}})
        self.refresh(value);self.assertEqual(f.boot_before_from_observation(value,compiled)[unit],'enabled')
    def test_runtime_selected_nonlink_never_becomes_disabled(self):
        value,compiled=self.make();root='/run/systemd/generator.early'
        row=value['unit_metadata']['sections']['boot_links']['evidence']['roots'][root]
        row.update(present=True,directories={root:{}},scan_scope='BOUNDED_RECURSIVE_NOFOLLOW',all_link_inventory_sha256='a'*64)
        row['selected_nonlinks']={root+'/xuanjun-uk-openclaw.service':{
            'kind':'FILE','metadata':{'uid':0,'gid':0,'mode':0o644,'nlink':1}}}
        self.refresh(value)
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_SELECTED_NONLINK'):f.boot_before_from_observation(value,compiled)
    def test_missing_root_or_unknown_scan_never_defaults_disabled(self):
        value,compiled=self.make();value['unit_metadata']['sections']['boot_links']['evidence']['roots'].pop('/run/systemd/generator')
        self.refresh(value)
        with self.assertRaisesRegex(ValueError,'COMPLETE_LOOKUP_ROOTS'):f.boot_before_from_observation(value,compiled)
    def test_runtime_alias_static_or_also_requires_review(self):
        for field in ('Alias','Also','WantedBy'):
            value,compiled=self.make();fields=value['unit_metadata']['sections']['legacy_gateway']['evidence']['public_install_fields']
            fields[field]=[] if field=='WantedBy' else ['other.service'];self.refresh(value)
            with self.assertRaisesRegex(ValueError,'SUPPORTED_INSTALL_RULES'):f.boot_before_from_observation(value,compiled)
    def test_changed_install_rules_on_nonmasked_unit_are_not_assumed(self):
        value,compiled=self.make();unit=next(u for u in f.BOOT_UNITS if u not in f.BOOT_RESTORED)
        compiled['rendered_targets']['/etc/systemd/system/'+unit]+=b'RequiredBy=extra.target\n'
        with self.assertRaisesRegex(ValueError,'INSTALL_RULES_CHANGED'):f.boot_before_from_observation(value,compiled)
    def test_candidate_is_the_exact_source_compiled_projection(self):
        from test_epoch7_acceptance_rows import fixture as source_fixture
        compiled,identities,manifest,rendered,facts=source_fixture();snapshot,unused=fixture()
        compiled['activation_proposal'].update(db_path=d.DB,ledger_socket=d.SOCKET)
        compiled['tls_config_bytes']=h.packed({'release_sha256':h.MANIFEST,'root':'fixture'})
        snapshot['tls']['config_identity_sha256']=d.digest({'root':'fixture'})
        for row in compiled['runtime']['provisioning']:row.update(owner_uid=0,group_gid=0,mode=0o644)
        result=f.candidate_from_compiled(compiled,snapshot)
        self.assertEqual(set(result),{'manifest_sha256','activation','targets','tls_config_identity_sha256'})
        self.assertEqual(len(result['targets']),24)
        self.assertEqual(d.build_delta(snapshot,d.digest(snapshot),result)['controller_transition']['after'],result['activation'])
        compiled['activation_proposal']['binary_sha256']='0'*64
        with self.assertRaises(ValueError):f.candidate_from_compiled(compiled,snapshot)


class SnapshotProjectionTests(unittest.TestCase):
    def test_only_volatile_exclusion_digest_can_change(self):
        a,c=fixture();b=copy.deepcopy(a);b['writer_exclusion']['evidence_sha256']=d.digest('fresh census')
        self.assertEqual(o.immutable_snapshot(a),o.immutable_snapshot(b))
        self.assertNotEqual(d.digest(a),d.digest(b))
    def test_writer_flag_cannot_be_excluded(self):
        a,c=fixture();a['writer_exclusion']['database_fds_excluded']=False
        with self.assertRaises(ValueError):o.immutable_snapshot(a)
    def test_policy_bytes_and_target_state_are_not_omitted(self):
        a,c=fixture();b=copy.deepcopy(a);b['targets'][next(p for p in sorted(d.TARGETS) if p not in d.OWNER_MASKS and p!='/etc/xuanjun-development/dispatcher.json')]['sha256']=d.digest('changed')
        self.assertNotEqual(o.immutable_snapshot(a),o.immutable_snapshot(b))


class CleanupAuthorityTests(unittest.TestCase):
    def make(self,state):
        authority=object.__new__(h.ClaimAuthority)
        authority.receipt=mock.Mock();authority.io=mock.Mock();authority.io.read_journal.return_value={'data':b'claim'}
        authority.validate_outer=mock.Mock(return_value={'state':state})
        return authority
    def test_authenticated_approval_without_admitted_claim_is_insufficient(self):
        for state in ({},{'admission':'UNKNOWN'},{'admission':'NOT_GRANTED'}):
            with self.assertRaisesRegex(ValueError,'ADMITTED_OUTER_CLAIM'):self.make(state).cleanup('fence')
    def test_cleanup_survives_forward_phase_failure(self):
        a=self.make({'admission':'ADMITTED','stage':'HOLD'});self.assertEqual(a.cleanup('fence')['state']['stage'],'HOLD')
        a.receipt.assert_called_once_with()
    def test_cleanup_cannot_name_arbitrary_unit_or_operation(self):
        a=self.make({'admission':'ADMITTED'})
        for operation,unit in (('run','nginx.service'),('stop_unit','other.service'),('fence','nginx.service')):
            with self.assertRaisesRegex(ValueError,'FIXED_CLEANUP'):a.cleanup(operation,unit)


class TimerTests(unittest.TestCase):
    def raw(self):
        return {t.TIMER:b'NextElapseUSecMonotonic=0\nLastTriggerUSecMonotonic=0\nActiveEnterTimestampMonotonic=0\n',
                t.SERVICE:b'ActiveEnterTimestampMonotonic=0\nExecMainStartTimestampMonotonic=0\n'}
    def test_exact_timespan_microseconds(self):
        self.assertEqual(t.timespan_us('1h 2min 3.123456s'),3723123456)
        self.assertEqual(t.timespan_us('1.001ms'),1001)
        self.assertEqual(t.timespan_us('0'),0)
        self.assertEqual(t.timespan_us('1y'),31557600000000)
        self.assertEqual(t.timespan_us('12month'),31557600000000)
    def test_unknown_infinity_reordering_overflow_and_precision_reject(self):
        for raw in ('infinity','n/a','','-1s','1 s','1min 1h','1s 1s','1.1us','18446744073709551615us','0.1min','1.1234567s'):
            with self.assertRaises(ValueError,msg=raw):t.timespan_us(raw)
    def test_raw_properties_cannot_be_missing_duplicated_or_altered(self):
        good=self.raw()[t.TIMER]
        for raw in (good+b'Unknown=0\n',good+b'LastTriggerUSecMonotonic=0\n',b'NextElapseUSecMonotonic=0\n'):
            with self.assertRaises(ValueError):t.parse_query(raw,t.TIMER)
    def test_nonzero_prior_service_or_trigger_refuses_before_start(self):
        for unit,field in ((t.TIMER,b'LastTriggerUSecMonotonic'),(t.SERVICE,b'ExecMainStartTimestampMonotonic')):
            raw=self.raw();raw[unit]=raw[unit].replace(field+b'=0',field+b'=1s' if unit==t.TIMER else field+b'=1')
            with self.assertRaisesRegex(ValueError,'PRIOR_TRIGGER'):t.compile_timer_contract(raw)
    def test_stopped_infinity_is_explicit_disarmed_but_active_requires_finite(self):
        raw=self.raw();raw[t.TIMER]=raw[t.TIMER].replace(b'NextElapseUSecMonotonic=0',b'NextElapseUSecMonotonic=infinity')
        self.assertIsNone(t.compile_timer_contract(raw)['baseline'][t.TIMER]['NextElapseUSecMonotonic'])
        with self.assertRaisesRegex(ValueError,'MUST_BE_FINITE'):t.parse_query(raw[t.TIMER],t.TIMER)
    def test_contract_binds_all_measured_raw_values_and_final_margin(self):
        c=t.compile_timer_contract(self.raw())
        self.assertEqual(c['minimum_margin_seconds'],180);self.assertEqual(c['tail_seconds'],60)
        self.assertEqual(c['timer_start_phase'],'post_install_checks')
    def test_no_certbot_or_renew_command(self):
        source=pathlib.Path(t.__file__).read_text()
        self.assertNotIn("'certbot'",source);self.assertNotIn("'renew'",source)


class ActualNoBytecodeTests(unittest.TestCase):
    def test_bounded_smoke_environment_prevents_import_cache(self):
        with tempfile.TemporaryDirectory() as root:
            with open(root+'/local_module.py','w') as stream:stream.write('value=1\n')
            env=dict(stager.SMOKE_ENV);env['PYTHONPATH']=root
            result=subprocess.run([os.path.realpath(__import__('sys').executable),'-c','import local_module; assert local_module.value==1'],
                                  env=env,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
            self.assertEqual(result.returncode,0)
            self.assertEqual(os.listdir(root),['local_module.py'])

if __name__=='__main__':unittest.main()
