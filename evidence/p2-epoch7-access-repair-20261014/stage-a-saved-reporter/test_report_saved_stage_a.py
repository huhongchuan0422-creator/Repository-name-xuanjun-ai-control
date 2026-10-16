"""Reconstruction tests: fixed public inputs, synthetic full data, no host calls."""
import ast,base64,contextlib,copy,hashlib,importlib.util,io,json,os,pathlib,signal,stat,sys,types,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
FIXTURES=pathlib.Path(os.environ.get('STAGE_A_TEST_FIXTURE_ROOT',str(ROOT/'fixtures')))
PACKET=pathlib.Path(os.environ.get('STAGE_A_TEST_PACKET',str(ROOT/'baseline/evidence/p2-epoch7-access-repair-20261014/saved-evidence-r7-actual-20261015/packet.json')))
KIT=pathlib.Path(os.environ.get('EPOCH7_PREP_TEST_KIT_ROOT',str(ROOT/'kit/epoch7-recovery-candidate-r7')))
COVERAGE=pathlib.Path(os.environ.get('STAGE_A_COVERAGE_ROOT',str(ROOT/'coverage-candidate')))
if not COVERAGE.is_dir():COVERAGE=ROOT/'stage-a-saved-coverage-candidate'
os.environ['EPOCH7_PREP_TEST_KIT_ROOT']=str(KIT)
sys.path[:0]=[str(HERE),str(FIXTURES/'saved-evidence-r7'),str(FIXTURES/'r7-saved-preparation-candidate')]
import report_saved_stage_a as r
import test_export_schema as sf
import test_epoch7_prepare_data_r7 as cf
import epoch7_prepare_data as data
import epoch7_topology_projection as topology
import export_schema as schema
import verify_exported_evidence as offline
spec=importlib.util.spec_from_file_location('coverage_fixture',str(COVERAGE/'test_saved_authority_coverage.py'))
coverage_fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(coverage_fixture)

@contextlib.contextmanager
def unchanged_imports():yield

def synthetic_pipeline_fixture(d):
    # Augment the genuine public full-factory fixture with explicitly synthetic
    # fields required by the later exact saved-metadata schema. No host evidence.
    seed=cf.make_seed();obs=seed['observation'];meta=obs['unit_metadata']
    obs['independent_acceptance']='PENDING';meta.update(independent_acceptance='PENDING',install_admission='NOT_GRANTED')
    old_node=meta['sections']['native_gateway']['evidence']['gateway_identity']['exe']
    meta['sections']['native_gateway']['evidence']['gateway_identity']['exe']=schema.NODE_PATH
    components=obs['evidence']['retained']['native_components']['components'];components[schema.NODE_PATH]=copy.deepcopy(components[old_node])
    obs['snapshot']['retained_resource_sha256']=r.sha(r.canonical(obs['evidence']['retained']))
    obs['snapshot_sha256']=r.sha(r.canonical(obs['snapshot']));obs['evidence']['snapshot_sha256']=obs['snapshot_sha256']
    obs['evidence_sha256']=r.sha(r.canonical(obs['evidence']))
    provenance=meta['sections']['command_resolutions']['evidence']['provenance']
    provenance.update(upstream_version='239',distro_matching_build='NOT_VERIFIED',public_unit_environment={'environment_names':[],'path_overrides':'PROVEN_ABSENT_IN_SUPPORTED_SYNTAX'})
    inventory=meta['sections']['dropins']['evidence']['units']
    for roots in inventory.values():
        for row in roots.values():
            for item in row['files'].values():item['metadata'].update(dev=8,ino=900,size=42,mtime_ns=11,ctime_ns=12)
    provenance['dropins_sha256']=r.sha(r.canonical(inventory['xuanjun-development-dispatcher.service']))
    boot=meta['sections']['boot_links']['evidence'];boot.update(restored_enablement='NOT_INFERRED',runtime_alias_semantics='REQUIRES_SYSTEMD239_REVIEW')
    for base in topology.DROPIN_ROOTS:
        dirs={}
        for path in [base]+[base+'/'+unit+'.d' for unit,roots in inventory.items() if roots[base+'/'+unit+'.d']['present']]:
            authority=obs['policy']['directories'].get(path,{'uid':0,'gid':0,'mode':0o755})
            stamp=dict(authority,dev=8,ino=800+len(dirs),nlink=2,size=4096,mtime_ns=11,ctime_ns=12)
            files=next((roots[path]['files'] for roots in inventory.values() if path in roots),{})
            dirs[path]={'metadata':stamp,'entry_count':len(files),'inventory_sha256':'7'*64}
        boot['roots'][base]={'present':True,'directories':dirs,'links':[],'selected_nonlinks':{},'scan_scope':'BOUNDED_RECURSIVE_NOFOLLOW','all_link_inventory_sha256':'8'*64}
    obs['unit_metadata_sha256']=r.sha(r.canonical(meta))
    with mock.patch.object(sf.old,'saved_metadata_observation',side_effect=lambda:copy.deepcopy(obs)):
        value=sf.fixture()
    # The saved run has three server starts; the public seed has one.
    records=value['observation']['finite_probe']['result']['server_observations']
    ready=next(row for row in records if row['event']=='SERVER_READY')
    records.extend([copy.deepcopy(ready),copy.deepcopy(ready)])
    ledger=next(event['detail'] for event in value['receipt']['events'] if event['event']=='OUTPUT_CAPTURED' and 'observations' in event['detail'])
    ledger['observations']=copy.deepcopy(records)
    ledger_raw=b''.join(r.canonical(row)+b'\n' for row in records)
    ledger.update(sha256=r.sha(ledger_raw),bytes=len(ledger_raw))
    # Use an exact public replacement-event template in this synthetic fixture.
    # Unlike UNITS_LOADED, replacement intents may recur; validators stay exact.
    published=json.loads(PACKET.read_bytes())
    replacements=[event for event in published['probe_receipt']['events'] if event['event']=='REPLACE_INTENT']
    while len(value['receipt']['events'])<129:
        value['receipt']['events'].append(copy.deepcopy(replacements[len(value['receipt']['events'])%len(replacements)]))
    probe_raw,metadata=sf.bind(value);obs=value['observation']
    manifest=json.loads((KIT/'recovery-kit-manifest.json').read_bytes())
    kit=types.SimpleNamespace(manifest=manifest,cache={name:(KIT/name).read_bytes() for name in manifest['files']},imports=unchanged_imports)
    with mock.patch.object(d,'POLICY_SHA',obs['policy_sha256']),mock.patch.object(d,'SNAPSHOT_SHA',obs['snapshot_sha256']):
        packet=d.export_value(obs,probe_raw,metadata,value['receipt'],kit,topology,schema)
    raw=r.canonical(obs)+b'\n'
    diagnostic={'schema':1,'kind':'OWNER_R7_RECEIPT_BOUND_CONTINUATION','kit_source_commit':d.SOURCE,'kit_manifest_sha256':d.MANIFEST_SHA,'success':True,
        'observation':{'private_file_sha256':r.sha(raw),'kit_manifest_sha256':d.MANIFEST_SHA,'probe_observations_complete':True}}
    diag_raw=r.canonical(diagnostic)+b'\n'
    class Tree:
        def __init__(self,root):self.root=root;self.fd=17
        def __enter__(self):return self
        def __exit__(self,*unused):return False
        def read(self,path,bound,private=False):
            if self.root==d.BASE:return {d.FILE:raw,d.RECEIPT:diag_raw}[path]
            return probe_raw
        def recheck(self):pass
    entry=types.SimpleNamespace(DescriptorTree=Tree,decode=lambda b:json.loads(b.decode()),verify_kit=lambda *args:kit)
    info=types.SimpleNamespace(**{'st_'+k:v for k,v in metadata.items() if k!='mode'});info.st_mode=stat.S_IFREG|metadata['mode']
    body=packet['unsigned_expected_review_body'];seven={k:packet[k] if k in ('topology_sha256','expected_review_body_sha256') else packet['bindings'][k] for k in d.RECOMPUTED}
    patches=[mock.patch.object(d,'POLICY_SHA',obs['policy_sha256']),mock.patch.object(d,'SNAPSHOT_SHA',obs['snapshot_sha256']),
        mock.patch.object(d,'OBS_SHA',r.sha(raw)),mock.patch.object(d,'RECEIPT_SHA',r.sha(diag_raw)),
        mock.patch.object(r,'OBS_CANONICAL_SHA',r.sha(r.canonical(obs))),mock.patch.object(r,'EXPECTED_BINDINGS',packet['bindings']),
        mock.patch.object(r,'EXPECTED_SEVEN',seven),mock.patch.object(r,'retained_body',return_value=(r.canonical(body),body)),
        mock.patch.object(d.os,'stat',return_value=info),cf.native_pins(seed)]
    return value,entry,kit,patches


class InputAndProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=r.load_exporter();cls.packet_raw=PACKET.read_bytes();cls.packet=json.loads(cls.packet_raw)
    def test_published_dependency_exact_bytes(self):
        raw=r.unpack(r.EMBEDDED_EXPORTER);self.assertEqual(raw,(FIXTURES/'saved-evidence-r7/export_saved_evidence.py').read_bytes());self.assertEqual(r.sha(raw),'a436d97072bf0062a94f9ccbd030aef1a08214f12f74645efd12d89d9f464815')
    def test_exact_retained_body_slice(self):
        raw,body=r.retained_body();self.assertEqual(r.sha(self.packet_raw),r.PACKET_SHA);self.assertEqual(raw,self.packet_raw[r.BODY_OFFSET:r.BODY_OFFSET+r.BODY_BYTES]);self.assertEqual(body,self.packet['unsigned_expected_review_body'])
    def test_actual_seven_pins_and_body(self):self.assertEqual(r.verify_projection(self.packet,self.d),r.EXPECTED_SEVEN)
    def test_each_actual_binding_tamper_rejected(self):
        for key in r.EXPECTED_BINDINGS:
            value=copy.deepcopy(self.packet);value['bindings'][key]='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):r.verify_projection(value,self.d)
    def test_each_seven_hash_tamper_rejected(self):
        for key in r.EXPECTED_SEVEN:
            value=copy.deepcopy(self.packet);target=value if key in ('topology_sha256','expected_review_body_sha256') else value['bindings'];target[key]='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):r.verify_projection(value,self.d)
    def test_body_change_rejected(self):
        value=copy.deepcopy(self.packet);value['unsigned_expected_review_body']['production_resume_authorized']=True
        with self.assertRaises(ValueError):r.verify_projection(value,self.d)
    def test_wrong_nonce_or_observation_rejected(self):
        for key in ('nonce','observation_id','observation_file_sha256','diagnostic_receipt_sha256','observation_full_canonical_sha256'):
            value=copy.deepcopy(self.packet);value[key]='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):r.verify_projection(value,self.d)
    def test_original_body_embedding_corruption(self):
        with mock.patch.object(r,'ORIGINAL_BODY_BASE64',base64.b64encode(b'{}').decode()),self.assertRaises(ValueError):r.retained_body()
    def test_embedded_tamper_and_trailing_data(self):
        for key,value in [('sha256','0'*64),('bytes',1),('zlib_base64',r.EMBEDDED_EXPORTER['zlib_base64']+'AAAA')]:
            row=dict(r.EMBEDDED_EXPORTER);row[key]=value
            with self.subTest(key=key),self.assertRaises(Exception):r.unpack(row)
    def test_fixed_case_record_counts(self):
        value=r.case_summary(self.packet);self.assertEqual([value[k] for k in ('case_count','server_record_count','event_count','resource_count','removed_count','stopped_and_empty_count')],[8,9,129,35,34,6]);self.assertEqual(value['prior_failed_attempt']['state'],'HOLD')
    def test_missing_event_and_cleanup_fail(self):
        for section in ('events','resources'):
            v=copy.deepcopy(self.packet);v['probe_receipt'][section].pop()
            with self.subTest(section=section),self.assertRaises(ValueError):r.case_summary(v)
        v=copy.deepcopy(self.packet);v['finite_probe']['result']['cleanup'][0]['status']='UNKNOWN'
        with self.assertRaises(ValueError):r.case_summary(v)
    def test_missing_expected_refusal_fails(self):
        v=copy.deepcopy(self.packet);v['finite_probe']['result']['cases'][5]['expected_rejection_observed']=False
        with self.assertRaises(ValueError):r.case_summary(v)
    def test_incomplete_probe_is_not_completed(self):
        for key,value in [('failure','SECRET'),('incomplete_case',{})]:
            v=copy.deepcopy(self.packet);v['finite_probe']['result'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):r.case_summary(v)
    def test_actual_cache_identity_and_closure(self):
        archive=pathlib.Path(os.environ.get('EPOCH7_EXPORT_TEST_ARCHIVE',str(ROOT/'baseline/evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-dc18f73e.tar.gz')))
        entry,kit=offline.authenticated_kit(archive.read_bytes(),self.d);r.authenticate_observer(kit,self.d);self.assertEqual(len(kit.cache),252)
    def test_observer_source_tamper_refused(self):
        manifest=json.loads((KIT/'recovery-kit-manifest.json').read_bytes());cache={name:(KIT/name).read_bytes() for name in manifest['files']};cache['helpers/snapshot_io.py']=b'bad'
        with self.assertRaises(ValueError):r.authenticate_observer(types.SimpleNamespace(manifest=manifest,cache=cache),self.d)
    def test_authenticate_registers_full_cache_static_errors(self):
        manifest=json.loads((KIT/'recovery-kit-manifest.json').read_bytes());kit=types.SimpleNamespace(manifest=manifest,cache={name:(KIT/name).read_bytes() for name in manifest['files']})
        r.authenticate_observer(kit,self.d);self.assertTrue('FACTORY_COMPLETE_SERVICE_METADATA' in self.d.SAFE_CODES)
        self.assertIn(self.d.KIT+'/helpers/epoch7_host_factory.py',self.d.SAFE_FILES)

class PrivacyAndFailureTests(unittest.TestCase):
    def test_mapper_output_has_only_safe_values(self):
        d=r.load_exporter();mapper=r.load_mapper(d);value=mapper.summarize_saved_authority(coverage_fixture.synthetic_full_observation());self.assertLess(len(r.public_bytes({'A2':value})),r.MAX_OUTPUT)
    def test_raw_keys_strings_numeric_values_rejected(self):
        for value in ({'path':'/etc/private'},{'uid':0},{'value':'SECRET=abc'},{'value':'hello'},{'value':123},{'mtime_ns':1234567890123456789}):
            with self.subTest(value=value),self.assertRaises(ValueError):r.public_bytes(value)
    def test_depth_and_count_and_size_limits(self):
        value='SAFE'
        for unused in range(22):value={'nested':value}
        for v in (value,{'rows':['SAFE']*513},{'rows':[{'label':'X'*160} for x in range(512)]}):
            if v is not value and len(v.get('rows',[]))==512:
                with mock.patch.object(r,'MAX_OUTPUT',100),self.assertRaises(ValueError):r.public_bytes(v)
            else:
                with self.assertRaises(ValueError):r.public_bytes(v)
    def test_private_error_is_hash_and_static_code_only(self):
        value=r.safe_error(ValueError('/private/SECRET_ENV=one'),r.load_exporter());self.assertNotIn('SECRET',json.dumps(value));self.assertEqual(value['code'],'UNLISTED_CODE')
    def test_deadline_has_explicit_category(self):self.assertEqual(r.safe_error(r.InitialDeadline(),r.load_exporter())['code'],'STAGE_A_DEADLINE')
    def test_error_projection_failure_is_contained(self):
        d=types.SimpleNamespace(error_summary=mock.Mock(side_effect=KeyboardInterrupt()))
        self.assertEqual(r.safe_error(ValueError('private payload q7Z9=unpublished-value'),d)['code'],'ERROR_PROJECTION_UNAVAILABLE')
    def test_mapper_static_error_registration(self):
        d=r.load_exporter();mapper=r.load_mapper(d)
        try:mapper.summarize_saved_authority({})
        except ValueError as error:self.assertEqual(r.safe_error(error,d)['code'],'SAVED_AUTHORITY_FULL_OBSERVATION_REQUIRED')
    def test_unknown_ancillary_keys_and_reason_are_opaque(self):
        value=r.ancillary_status({'unit_metadata':{'state':'UNKNOWN','sections':{'SECRET_PATH':{'state':'UNKNOWN','reason':'SECRET_TOKEN'}}}});raw=r.public_bytes({'ancillary':value});self.assertNotIn(b'SECRET',raw);self.assertIn(b'UNKNOWN',raw)
    def test_nested_status_and_unresolved_are_visible_without_private_values(self):
        observation={'source_review_inputs':{'state':'COMPLETE_UNREVIEWED','sections':{'sources':{'state':'MEASURED_UNREVIEWED','evidence':{'files':[{'path':'SECRET_PATH','state':'UNKNOWN'}],'source_closure':'NOT_VERIFIED','unresolved':[{'path':'SECRET_PATH','reason':'SECRET_REASON'}]}}}}}
        row=r.ancillary_status(observation)[2];raw=r.public_bytes({'ancillary':[row]})
        self.assertIn({'state':'UNKNOWN','record_count':1},row['recursive_status_counts']);self.assertEqual(row['unresolved_count'],1);self.assertEqual(row['source_closure_counts'],[{'state':'NOT_VERIFIED','record_count':1}]);self.assertNotIn(b'SECRET',raw)
    def test_bad_ancillary_shape_remains_visible(self):
        value=r.ancillary_status({'unit_metadata':{'state':'UNKNOWN','sections':[]}});self.assertEqual(value[1]['sections_state'],'INVALID_OR_OVERSIZE')
    def test_existing_alarm_refused(self):
        with mock.patch.object(r.signal,'getitimer',return_value=(1.0,0.0)),self.assertRaises(ValueError):
            with r.initial_bounded():pass
    def test_timer_setup_failure_cleanup(self):
        with mock.patch.object(r.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(r.signal,'signal') as sethandler,mock.patch.object(r.signal,'setitimer',side_effect=[OSError('SECRET'),None]),self.assertRaises(OSError):
            with r.initial_bounded():pass
        self.assertEqual(sethandler.call_count,2)
    def test_timer_cleanup_preserves_interrupt(self):
        error=KeyboardInterrupt()
        with mock.patch.object(r.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(r.signal,'signal'),mock.patch.object(r.signal,'setitimer',side_effect=[None,OSError()]):
            with self.assertRaises(KeyboardInterrupt) as got:
                with r.initial_bounded():raise error
        self.assertIs(got.exception,error);self.assertTrue(error.diagnostic_cleanup_failed)
    def test_timer_cleanup_failure_without_primary(self):
        with mock.patch.object(r.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(r.signal,'signal'),mock.patch.object(r.signal,'setitimer',side_effect=[None,OSError()]):
            with self.assertRaises(ValueError) as got:
                with r.initial_bounded():pass
        self.assertTrue(got.exception.diagnostic_cleanup_failed)
    def test_no_action_call_sites(self):
        tree=ast.parse(r.REPORTER_BODY_BYTES);calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
        self.assertFalse(calls&{'observe','collect','execute_reviewed_probe','run_preparation','fetch','chmod','fchmod','unlink','mkdir','write','write_bytes','create'})

class OrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.d=r.load_exporter();cls.fixture=synthetic_pipeline_fixture(cls.d)
    def context(self):
        value,entry,kit,patches=self.fixture
        stack=contextlib.ExitStack()
        for patch in patches:stack.enter_context(patch)
        return stack,value,entry,kit
    def test_genuine_full_validator_projection_mapper_one_pipeline(self):
        stack,value,entry,kit=self.context()
        with stack:
            result=r.run_report(entry,kit,self.d,r.load_mapper(self.d));raw=r.public_bytes(result)
        self.assertTrue(result['reporting_complete']);self.assertEqual(result['stage_a_approval'],'HOLD');self.assertEqual(result['A4']['case_count'],8);self.assertLess(len(raw),r.MAX_OUTPUT)
        self.assertEqual(result['A1']['observation_wall_clock'],'NOT_RETAINED');self.assertEqual(result['A6']['filesystem_atime_effect'],'POSSIBLE_NOT_MEASURED')
    def test_genuine_full_validator_unknown_section_fails(self):
        stack,value,entry,kit=self.context();bad=copy.deepcopy(value['observation']);bad['unit_metadata']['sections']['boot_links']['state']='UNKNOWN'
        with stack,self.assertRaises(ValueError):self.d.validate_saved_observation(bad,data)
    def test_complete_raw_pin_failure_before_decode(self):
        entry=mock.MagicMock();entry.DescriptorTree.return_value.__enter__.return_value.read.return_value=b'wrong'
        with self.assertRaises(ValueError):r.read_complete_pair(entry,self.d,{}, {})
        entry.decode.assert_not_called()
    def test_read_cleanup_interrupt_preserved(self):
        entry=mock.MagicMock();tree=entry.DescriptorTree.return_value.__enter__.return_value;tree.read.side_effect=KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):r.read_complete_pair(entry,self.d,{}, {})
        entry.DescriptorTree.return_value.__exit__.assert_called_once()
    def main_context(self):
        stack,value,entry,kit=self.context();stack.enter_context(mock.patch.object(r,'load_exporter',return_value=self.d));stack.enter_context(mock.patch.object(r.os,'geteuid',return_value=0));stack.enter_context(mock.patch.object(r.os,'getegid',return_value=0));stack.enter_context(mock.patch.object(r.socket,'gethostname',return_value=self.d.HOST));stack.enter_context(mock.patch.object(self.d,'entry_bytes',return_value=(KIT/'epoch7_recovery_entry.py').read_bytes()));stack.enter_context(mock.patch.object(self.d,'load_entry',return_value=entry));return stack,entry
    def test_main_completes_report_but_returns_hold(self):
        stack,entry=self.main_context();output=io.StringIO()
        with stack,mock.patch('sys.stdout',output):code=r.main()
        result=json.loads(output.getvalue());self.assertEqual(code,2);self.assertTrue(result['reporting_complete']);self.assertEqual(result['stage_a_approval'],'HOLD')
    def test_loader_failure_emits_safe_hold(self):
        output=io.StringIO()
        with mock.patch.object(r,'load_exporter',side_effect=ValueError('private payload q7Z9=unpublished-value')),mock.patch('sys.stdout',output):code=r.main()
        self.assertEqual(code,2);value=json.loads(output.getvalue());self.assertFalse(value['reporting_complete']);self.assertNotIn('private payload q7Z9=unpublished-value',output.getvalue())
    def test_preload_deadline_has_explicit_category(self):
        output=io.StringIO()
        with mock.patch.object(r,'load_exporter',side_effect=r.InitialDeadline()),mock.patch('sys.stdout',output):code=r.main()
        result=json.loads(output.getvalue());self.assertEqual(code,2);self.assertEqual(result['error']['code'],'STAGE_A_DEADLINE')
    def test_full_validator_failure_retains_status(self):
        stack,entry=self.main_context();output=io.StringIO()
        with stack,mock.patch.object(self.d,'validate_saved_observation',side_effect=ValueError('private payload q7Z9=unpublished-value')),mock.patch('sys.stdout',output):code=r.main()
        value=json.loads(output.getvalue());self.assertEqual(code,2);self.assertEqual(value['failed_phase'],'VALIDATE_FULL_SAVED_OBSERVATION');self.assertEqual(len(value['ancillary']),4);self.assertNotIn('private payload q7Z9=unpublished-value',output.getvalue())
    def test_final_recheck_failure_is_hold(self):
        stack,entry=self.main_context();output=io.StringIO();original=entry.verify_kit;entry.verify_kit=mock.Mock(side_effect=[original(),ValueError('private payload q7Z9=unpublished-value')])
        try:
            with stack,mock.patch('sys.stdout',output):r.main()
            value=json.loads(output.getvalue());self.assertEqual(value['failed_phase'],'FINAL_PROTECTED_RECHECKS');self.assertTrue(value['cleanup_unknown'])
        finally:entry.verify_kit=original
    def test_output_failure_is_never_retried(self):
        stack,entry=self.main_context()
        with stack,mock.patch('builtins.print',side_effect=BrokenPipeError('SECRET')) as printer:self.assertEqual(r.main(),2)
        self.assertEqual(printer.call_count,1)
    def test_projection_failure_gets_bounded_fallback(self):
        stack,entry=self.main_context();output=io.StringIO();original=r.public_bytes
        def encode(value):
            if value.get('reporting_complete'):raise ValueError('STAGE_A_PUBLIC_OUTPUT_BOUND')
            return original(value)
        with stack,mock.patch.object(r,'public_bytes',side_effect=encode),mock.patch('sys.stdout',output):self.assertEqual(r.main(),2)
        self.assertFalse(json.loads(output.getvalue())['reporting_complete'])
    def test_deadline_failure_does_not_print_traceback(self):
        stack,entry=self.main_context();output=io.StringIO()
        with stack,mock.patch.object(r,'run_report',side_effect=r.InitialDeadline()),mock.patch('sys.stdout',output):r.main()
        self.assertEqual(json.loads(output.getvalue())['error']['code'],'STAGE_A_DEADLINE')

if __name__=='__main__':unittest.main()
