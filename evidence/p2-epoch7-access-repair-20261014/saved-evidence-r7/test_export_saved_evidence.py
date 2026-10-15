"""Synthetic metadata only, exact public R7 modules; no host execution."""
import ast,base64,contextlib,copy,hashlib,io,json,os,pathlib,signal,stat,subprocess,sys,types,unittest,zlib
from unittest import mock
import export_saved_evidence as d
import verify_exported_evidence as offline
HERE=pathlib.Path(__file__).resolve().parent
REPAIR=HERE.parent
PREP=REPAIR/'r7-saved-preparation-candidate'
sys.path[:0]=[str(HERE),str(PREP)]
import test_export_schema as fixture_module
import test_epoch7_prepare_data_r7 as cache_fixture
import epoch7_topology_projection as t
import epoch7_prepare_data as data
import export_schema as schema
KIT=cache_fixture.KIT
ARCHIVE=pathlib.Path(os.environ.get('EPOCH7_EXPORT_TEST_ARCHIVE',str(REPAIR/'r7-integration-candidate/selected-artifact-dc18f73e/epoch7-recovery-kit.tar.gz')))


def real_kit():
    return offline.authenticated_kit(ARCHIVE.read_bytes(),d)[1]


def packet_fixture():
    v=fixture_module.fixture();obs=v['observation'];obs['policy_sha256']=d.sha(d.canonical(obs['policy']));raw,meta=fixture_module.bind(v)
    with mock.patch.object(d,'POLICY_SHA',obs['policy_sha256']),mock.patch.object(d,'SNAPSHOT_SHA',obs['snapshot_sha256']):
        packet=d.export_value(obs,raw,meta,v['receipt'],real_kit(),t,schema)
        expected=types.SimpleNamespace(**{key:copy.deepcopy(getattr(d,key)) for key in ('OBS_SHA','RECEIPT_SHA','OBSERVATION_ID','NONCE',
            'POLICY_SHA','SNAPSHOT_SHA','SOURCE_MANIFEST','RECOMPUTED','MANIFEST_SHA','RUNTIME_SHA')})
    return packet,expected,v


class ReaderContracts(unittest.TestCase):
    def test_reviewed_descriptor_mechanics_source_identical(self):
        def functions(raw):return {n.name:ast.dump(n) for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)}
        old=functions((HERE/'test_fixtures/reviewed_reader_mechanics.py').read_text());new=functions((HERE/'export_saved_evidence.py').read_text())
        for name in ('bounded','authority','entry_bytes','stamp'):self.assertEqual(old[name],new[name])
    def test_new_known_pins_no_old_expected_body(self):
        self.assertEqual(d.OBSERVATION_ID,'8df3b22b3762070f');self.assertEqual(d.NONCE,'cee45858d9d19863e977e2648bc2196a')
        self.assertTrue(d.KIT.endswith('-r7'));self.assertFalse(hasattr(d,'EXPECTED_BODY'));self.assertFalse(hasattr(d,'DROPINS'));self.assertFalse(hasattr(d,'PROBE_SHA'))
    def pair(self,kind='OWNER_R7_RECEIPT_BOUND_CONTINUATION'):
        value={'schema':1,'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED','install_admission':'NOT_GRANTED',
            'policy_sha256':d.POLICY_SHA,'snapshot_sha256':d.SNAPSHOT_SHA,'finite_probe':{'nonce':d.NONCE}}
        raw=d.canonical(value)+b'\n';pin=d.sha(raw)
        receipt={'schema':1,'kind':kind,'kit_source_commit':d.SOURCE,'kit_manifest_sha256':d.MANIFEST_SHA,'success':True,
            'observation':{'private_file_sha256':pin,'kit_manifest_sha256':d.MANIFEST_SHA,'probe_observations_complete':True}}
        rr=d.canonical(receipt)+b'\n';entry=mock.MagicMock();entry.decode.side_effect=lambda b:json.loads(b.decode())
        entry.DescriptorTree.return_value.__enter__.return_value.read.side_effect=[raw,rr]
        return entry,value,receipt,pin,d.sha(rr)
    def test_exact_saved_pair_success_link(self):
        entry,value,receipt,pin,rpin=self.pair()
        with mock.patch.object(d,'OBS_SHA',pin),mock.patch.object(d,'RECEIPT_SHA',rpin):self.assertEqual(d.read_pair(entry),(value,receipt))
    def test_r6_receipt_kind_rejected_even_with_matching_bytes(self):
        entry,value,receipt,pin,rpin=self.pair('OWNER_R6_RECEIPT_BOUND_CONTINUATION')
        with mock.patch.object(d,'OBS_SHA',pin),mock.patch.object(d,'RECEIPT_SHA',rpin),self.assertRaises(ValueError):d.read_pair(entry)
    def test_pair_hash_mismatch_before_decode(self):
        entry=mock.MagicMock();entry.DescriptorTree.return_value.__enter__.return_value.read.return_value=b'wrong'
        with self.assertRaises(ValueError):d.read_pair(entry)
        entry.decode.assert_not_called()
    def test_probe_scope_rejected_before_read(self):
        entry=mock.MagicMock();obs={'finite_probe':{'result':{'created_receipt':{'path':'/private/other','sha256':'a'*64}}}}
        with self.assertRaises(ValueError):d.read_probe(entry,obs)
        entry.DescriptorTree.assert_not_called()
    def test_probe_digest_derived_from_exact_binding_and_metadata(self):
        receipt={'public':1};raw=d.canonical(receipt)+b'\n'
        info=types.SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o600,st_uid=0,st_gid=0,st_nlink=1,st_size=len(raw),st_mtime_ns=1790000000123456789,st_ctime_ns=1790000000123456789)
        meta={key:getattr(info,'st_'+key) for key in ('dev','ino','uid','gid','nlink','size','mtime_ns','ctime_ns')};meta['mode']=0o600
        binding={'path':d.PROBE_ROOT+'/created-receipt.json','sha256':d.sha(raw),'metadata':meta}
        entry=mock.MagicMock();entry.decode.side_effect=lambda b:json.loads(b.decode());entry.DescriptorTree.return_value.__enter__.return_value.read.return_value=raw
        with mock.patch.object(d.os,'stat',return_value=info):self.assertEqual(d.read_probe(entry,{'finite_probe':{'result':{'created_receipt':binding}}}),(raw,meta,receipt))
    def test_missing_or_corrupt_probe_fails(self):
        entry=mock.MagicMock();entry.DescriptorTree.side_effect=FileNotFoundError()
        obs={'finite_probe':{'result':{'created_receipt':{'path':d.PROBE_ROOT+'/created-receipt.json','sha256':'a'*64}}}}
        with self.assertRaises(FileNotFoundError):d.read_probe(entry,obs)
    def test_embedded_sources_exact_three_no_filesystem(self):
        with mock.patch('builtins.open',side_effect=AssertionError('IO_FORBIDDEN')):sources=d.embedded_sources()
        self.assertEqual(set(sources),{'epoch7_prepare_data.py','epoch7_topology_projection.py','export_schema.py'})
        for name,raw in sources.items():self.assertEqual(d.sha(raw),d.SOURCE_MANIFEST['files'][name])
    def test_embedded_source_tamper_and_trailing_data_rejected(self):
        for field,value in (('sha256','0'*64),('bytes',1)):
            rows=copy.deepcopy(d.EMBEDDED_SOURCES);rows['export_schema.py'][field]=value
            with mock.patch.object(d,'EMBEDDED_SOURCES',rows),self.assertRaises(ValueError):d.embedded_sources()
        rows=copy.deepcopy(d.EMBEDDED_SOURCES);row=rows['export_schema.py'];row['zlib_base64']=base64.b64encode(base64.b64decode(row['zlib_base64'])+b'trailing').decode()
        with mock.patch.object(d,'EMBEDDED_SOURCES',rows),self.assertRaises(ValueError):d.embedded_sources()
    def test_no_host_action_functions_in_exporter(self):
        tree=ast.parse((HERE/'export_saved_evidence.py').read_text())
        forbidden={'collect','observe','observe_host','execute_reviewed_probe','run_preparation','fetch','chmod','fchmod','unlink','mkdir','write'}
        calls={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
        self.assertFalse(calls&forbidden)
    def test_bounded_refuses_existing_alarm(self):
        with mock.patch.object(d.signal,'getitimer',return_value=(1.0,0.0)),self.assertRaises(ValueError):
            with d.bounded():pass
    def test_bounded_cleanup_preserves_primary(self):
        error=KeyboardInterrupt()
        with mock.patch.object(d.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(d.signal,'signal'),mock.patch.object(d.signal,'setitimer',side_effect=[None,OSError('SECRET')]):
            with self.assertRaises(KeyboardInterrupt) as got:
                with d.bounded():raise error
        self.assertIs(got.exception,error);self.assertTrue(error.diagnostic_cleanup_failed)
    def test_bounded_cleanup_without_primary_marked(self):
        with mock.patch.object(d.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(d.signal,'signal'),mock.patch.object(d.signal,'setitimer',side_effect=[None,OSError()]):
            with self.assertRaises(ValueError) as got:
                with d.bounded():pass
        self.assertTrue(got.exception.diagnostic_cleanup_failed)
    def test_failure_text_never_echoed(self):
        result=d.error_summary(ValueError('SECRET_ENV=private'));self.assertNotIn('SECRET',json.dumps(result));self.assertEqual(result['code'],'UNLISTED_CODE')
    def test_static_failure_code_and_frame(self):
        d.remember_source('TEST_PUBLIC','<public>',b"raise ValueError('FIXED_TEST_CODE')")
        try:exec(compile("raise ValueError('FIXED_TEST_CODE')",'<public>','exec'))
        except ValueError as error:result=d.error_summary(error)
        self.assertEqual(result['code'],'FIXED_TEST_CODE');self.assertEqual(result['public_source_frames'],[{'source':'TEST_PUBLIC','line':1}])


class CompleteExportContracts(unittest.TestCase):
    def test_real_r7_archive_and_embedded_modules_import(self):
        code="import pathlib,sys,types; p=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(p)); import export_saved_evidence as d, verify_exported_evidence as v; e,k=v.authenticated_kit(pathlib.Path(sys.argv[2]).read_bytes(),d); assert len(k.cache)==252;\nwith k.imports():\n m=d.pure_modules(d.embedded_sources()); assert callable(m['epoch7_prepare_data.py'].validate_observation); assert len(m['epoch7_topology_projection.py'].DROPIN_UNITS)==11\nprint('CORE_CACHE_PASS')"
        result=subprocess.run([sys.executable,'-I','-B','-S','-c',code,str(HERE),str(ARCHIVE)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr.decode());self.assertEqual(result.stdout,b'CORE_CACHE_PASS\n')
    def test_complete_actual_cache_projection_and_seven_hashes(self):
        packet,expected,v=packet_fixture();offline.validate_packet_pins(packet,expected,t)
        original=t.project_topology(v['observation'],*fixture_module.bind(v),d.MANIFEST_SHA,v['sources'],t.project_saved_unit_dropins(v['observation']),d.sha(d.canonical(d.SOURCE_MANIFEST)))
        self.assertEqual(packet['topology_raw_utf8'].encode(),original['topology_raw'])
        self.assertEqual(packet['unsigned_expected_review_body']['schema'],2)
        self.assertLess(len(d.canonical(packet)),d.MAX_OUTPUT)
        verified=offline.verify_packet(packet,t,schema)
        self.assertEqual(verified['computed']['topology_sha256'],original['topology_sha256']);self.assertEqual(len(verified['computed']),7)
        self.assertFalse(verified['whole_observation_recomputed'])
    def test_full_saved_observation_validator_is_genuine_data_function(self):
        seed=copy.deepcopy(cache_fixture.R7DataContractTests.seed if hasattr(cache_fixture.R7DataContractTests,'seed') else cache_fixture.make_seed())
        self.assertIs(d.validate_saved_observation(seed['observation'],data),seed['observation'])
    def test_unknown_receipt_key_blocks_export_before_output(self):
        v=fixture_module.fixture();v['receipt']['private_environment']='SECRET';obs=v['observation'];obs['policy_sha256']=d.sha(d.canonical(obs['policy']));raw,meta=fixture_module.bind(v)
        with mock.patch.object(d,'POLICY_SHA',obs['policy_sha256']),mock.patch.object(d,'SNAPSHOT_SHA',obs['snapshot_sha256']),self.assertRaises(ValueError):
            d.export_value(obs,raw,meta,v['receipt'],real_kit(),t,schema)
    def test_old_inventory_is_rejected(self):
        packet,expected,v=packet_fixture();packet['saved_unit_dropins']={'schema':1,'reread':'EXACT_PRE_POST'}
        with self.assertRaises(ValueError):offline.verify_packet(packet,t,schema)
    def test_missing_socket_or_extra_inventory_rejected(self):
        packet,expected,v=packet_fixture()
        for mutation in ('missing','extra'):
            bad=copy.deepcopy(packet);units=bad['saved_unit_dropins']['dropins_section']['evidence']['units']
            if mutation=='missing':units.pop('xuanjun-ledger.socket')
            else:units['private.socket']={}
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):offline.verify_packet(bad,t,schema)
    def test_known_packet_binding_and_scope_tamper_rejected(self):
        packet,expected,v=packet_fixture()
        for key,value in (('observation_file_sha256','0'*64),('diagnostic_receipt_sha256','0'*64),('core_policy_sha256','0'*64),('snapshot_sha256','0'*64),('nonce','0'*32),('approval_granted',True),('collection','COMPLETE')):
            bad=copy.deepcopy(packet);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):offline.validate_packet_pins(bad,expected,t)
    def test_changed_unsigned_body_cannot_be_accepted(self):
        packet,expected,v=packet_fixture();packet['unsigned_expected_review_body']['production_resume_authorized']=True
        packet['expected_review_body_sha256']=d.sha(d.canonical(packet['unsigned_expected_review_body']))
        with self.assertRaises(ValueError):offline.validate_packet_pins(packet,expected,t)
    def test_delivery_digest_is_external_and_rejects_consistent_packet_tamper(self):
        packet,expected,v=packet_fixture();raw=d.canonical(packet)+b'\n';entry=types.SimpleNamespace(decode=lambda x:json.loads(x.decode()))
        self.assertEqual(offline.decode_packet(raw,d.sha(raw),entry),packet)
        packet['observation_full_canonical_sha256']='0'*64;packet['bindings']['observation_sha256']='0'*64
        packet['unsigned_expected_review_body']=t.expected_review_body(packet['topology_sha256'],packet['bindings'])
        packet['expected_review_body_sha256']=d.sha(d.canonical(packet['unsigned_expected_review_body']))
        with self.assertRaises(ValueError):offline.decode_packet(d.canonical(packet)+b'\n',d.sha(raw),entry)
    def test_raw_receipt_or_topology_mutation_rejected(self):
        packet,expected,v=packet_fixture()
        for key,value in (('probe_receipt_raw_base64',base64.b64encode(b'{}\n').decode()),('topology_raw_utf8','{}\n')):
            bad=copy.deepcopy(packet);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):offline.verify_packet(bad,t,schema)


class MainFlowContracts(unittest.TestCase):
    @contextlib.contextmanager
    def effects(self):
        entry=mock.MagicMock();kit=mock.MagicMock();kit.manifest={'kit_source_commit':d.SOURCE};kit.cache={};entry.verify_kit.return_value=kit
        modules={name:mock.MagicMock() for name in ('epoch7_prepare_data.py','epoch7_topology_projection.py','export_schema.py')}
        patches=[mock.patch.object(d.os,'geteuid',return_value=0),mock.patch.object(d.os,'getegid',return_value=0),
            mock.patch.object(d.socket,'gethostname',return_value=d.HOST),mock.patch.object(d,'entry_bytes',return_value=b'# synthetic test seam\n'),
            mock.patch.object(d,'load_entry',return_value=entry),mock.patch.object(d,'read_pair',return_value=({},{})),
            mock.patch.object(d,'embedded_sources',return_value={}),mock.patch.object(d,'read_probe',return_value=(b'{}\n',{},{})),
            mock.patch.object(d,'pure_modules',return_value=modules),mock.patch.object(d,'validate_saved_observation'),
            mock.patch.object(d,'export_value',return_value={'state':'COMPLETE_SAVED_DATA_EXPORT'}),mock.patch('builtins.print')]
        with contextlib.ExitStack() as stack:
            values=[stack.enter_context(x) for x in patches];yield entry,values[-3],values[-2],values[-1]
    def test_one_export_then_same_fixed_rechecks(self):
        with self.effects() as (entry,validate,project,output):
            self.assertEqual(d.main(),0);validate.assert_called_once();project.assert_called_once();self.assertEqual(entry.verify_kit.call_count,2)
            self.assertEqual(json.loads(output.call_args[0][0])['state'],'COMPLETE_SAVED_DATA_EXPORT')
    def test_schema_rejection_outputs_hold_only(self):
        with self.effects() as (entry,validate,project,output):
            project.side_effect=ValueError('PRIVATE_CREDENTIAL');self.assertEqual(d.main(),2);raw=output.call_args[0][0]
            self.assertNotIn('PRIVATE_CREDENTIAL',raw);self.assertEqual(json.loads(raw)['state'],'HOLD');self.assertEqual(json.loads(raw)['failed_phase'],'PURE_PROJECTION_AND_STRICT_EXPORT_SCHEMA')
    def test_ancillary_validation_failure_stops_projection(self):
        with self.effects() as (entry,validate,project,output):
            validate.side_effect=ValueError('PRIVATE');self.assertEqual(d.main(),2);project.assert_not_called()
            self.assertEqual(json.loads(output.call_args[0][0])['failed_phase'],'VALIDATE_COMPLETE_SAVED_OBSERVATION')
    def test_final_reverification_failure_never_prints_complete(self):
        with self.effects() as (entry,validate,project,output):
            entry.verify_kit.side_effect=[entry.verify_kit.return_value,ValueError('PRIVATE')];self.assertEqual(d.main(),2)
            result=json.loads(output.call_args[0][0]);self.assertEqual(result['state'],'HOLD');self.assertTrue(result['cleanup_unknown'])
    def test_import_cleanup_interrupt_preserves_failure(self):
        with self.effects() as (entry,validate,project,output):
            entry.verify_kit.return_value.imports.return_value.__exit__.side_effect=KeyboardInterrupt();self.assertEqual(d.main(),2)
            result=json.loads(output.call_args[0][0]);self.assertEqual(result['error']['exception_class'],'KeyboardInterrupt');self.assertTrue(result['cleanup_unknown'])
    def test_reader_deadline_no_projection(self):
        with self.effects() as (entry,validate,project,output),mock.patch.object(d,'read_pair',side_effect=d.Deadline()):
            self.assertEqual(d.main(),2);project.assert_not_called();self.assertEqual(json.loads(output.call_args[0][0])['failure_code'],'EXPORT_DEADLINE')
    def test_output_failure_never_retried(self):
        with self.effects() as (entry,validate,project,output):output.side_effect=BrokenPipeError();self.assertEqual(d.main(),2);self.assertEqual(output.call_count,1)
    def test_output_bound_fails_closed(self):
        with self.effects() as (entry,validate,project,output),mock.patch.object(d,'MAX_OUTPUT',8):self.assertEqual(d.main(),2);self.assertEqual(json.loads(output.call_args[0][0])['state'],'HOLD')
    def test_wrong_host_stops_before_any_read(self):
        with self.effects() as (entry,validate,project,output),mock.patch.object(d.socket,'gethostname',return_value='wrong'),mock.patch.object(d,'entry_bytes') as reader:
            self.assertEqual(d.main(),2);reader.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
