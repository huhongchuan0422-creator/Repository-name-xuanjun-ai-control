import ast,base64,contextlib,copy,hashlib,io,json,os,pathlib,signal,stat,sys,types,unittest,zlib
from unittest import mock
import export_saved_evidence as d
import verify_exported_evidence as offline
HERE=pathlib.Path(__file__).resolve().parent
REPAIR=HERE.parent
KIT=REPAIR/'r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6'
PREP=REPAIR/'r6-preparation-contract-fix-candidate'

@contextlib.contextmanager
def frozen_fixture():
    raw=(KIT/'epoch7_recovery_entry.py').read_bytes();assert d.sha(raw)==d.ENTRY_SHA
    entry=types.ModuleType('fixture_verified_entry');entry.__file__=str(KIT/'epoch7_recovery_entry.py')
    exec(compile(raw,entry.__file__,'exec'),entry.__dict__)
    manifest_raw=(KIT/entry.MANIFEST).read_bytes();assert d.sha(manifest_raw)==d.MANIFEST_SHA
    manifest=entry.validate_manifest(entry.decode(manifest_raw))
    cache={name:(KIT/name).read_bytes() for name in manifest['files']}
    assert len(cache)==249
    for name,body in cache.items():assert d.sha(body)==manifest['files'][name]
    entry.validate_runtime(manifest,cache)
    kit=entry.VerifiedKit(str(KIT),manifest,cache,d.MANIFEST_SHA,raw_manifest=manifest_raw)
    extra={'test_probe_driver':'tests/probe/test_probe_driver.py','test_node_sqlite_probe':'tests/probe/test_node_sqlite_probe.py'}
    previous={name:sys.modules.get(name) for name in ('epoch7_topology_projection','test_epoch7_topology_projection')}
    try:
        with kit.imports(extra):
            topology=types.ModuleType('epoch7_topology_projection');topology.__file__=str(PREP/'epoch7_topology_projection.py')
            raw=(PREP/'epoch7_topology_projection.py').read_bytes();assert d.sha(raw)==d.SOURCE_MANIFEST['files']['epoch7_topology_projection.py']
            sys.modules[topology.__name__]=topology;exec(compile(raw,topology.__file__,'exec'),topology.__dict__)
            fixture=types.ModuleType('test_epoch7_topology_projection');fixture.__file__=str(PREP/'test_epoch7_topology_projection.py')
            sys.modules[fixture.__name__]=fixture;exec(compile((PREP/'test_epoch7_topology_projection.py').read_bytes(),fixture.__file__,'exec'),fixture.__dict__)
            yield entry,kit,topology,fixture
    finally:
        for name,module in previous.items():
            if module is None:sys.modules.pop(name,None)
            else:sys.modules[name]=module

class ReaderContracts(unittest.TestCase):
    def test_reviewed_descriptor_mechanics_source_identical(self):
        old=(HERE/'test_fixtures/reviewed_reader_mechanics.py').read_text()
        new=(HERE/'export_saved_evidence.py').read_text()
        def functions(raw):return {n.name:ast.dump(n) for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)}
        for name in ('bounded','authority','entry_bytes','stamp'):
            self.assertEqual(functions(old)[name],functions(new)[name])
    def test_original_dropins_exact_integer_hash(self):
        self.assertEqual(d.sha(d.canonical(d.DROPINS)),d.EXPECTED_BODY['socket_dropins_sha256'])
        self.assertEqual(d.DROPINS['roots']['/etc/systemd/system/xuanjun-ledger.socket.d']['parent_metadata']['ctime_ns'],1791988264717936099)
    def test_embedded_unsigned_body_has_exact_recorded_hash(self):
        self.assertEqual(d.sha(d.canonical(d.EXPECTED_BODY)),'cc4764bdab37c3bedad9171e72aafd86b59812e82b6acdf196a39a1257a6df36')
        self.assertEqual(d.sha(d.canonical(d.DROPINS)),'7412f8e70c998cf6fd8cedcbc444c0715747ff7421e49910c08d66cec43df7b7')
        self.assertEqual(d.sha(d.canonical(d.SOURCE_MANIFEST)),'c169a9885c190660b449c3a8358f585bed56d0da064a570670115ba0f872563c')
    def test_fixed_normal_receipt_scope_and_success_link(self):
        value={'schema':1,'kind':'EPOCH7_OBSERVATION_ONLY_UNREVIEWED','install_admission':'NOT_GRANTED','finite_probe':{'nonce':d.NONCE}}
        raw=d.canonical(value)+b'\n';observation_sha=d.sha(raw)
        receipt={'schema':1,'kind':'OWNER_R6_RECEIPT_BOUND_CONTINUATION','kit_source_commit':d.SOURCE,
            'kit_manifest_sha256':d.MANIFEST_SHA,'success':True,'observation':{'private_file_sha256':observation_sha,
            'kit_manifest_sha256':d.MANIFEST_SHA,'probe_observations_complete':True}}
        rr=d.canonical(receipt)+b'\n';entry=mock.MagicMock();entry.decode.side_effect=lambda b:json.loads(b.decode())
        entry.DescriptorTree.return_value.__enter__.return_value.read.side_effect=[raw,rr]
        with mock.patch.object(d,'OBS_SHA',observation_sha),mock.patch.object(d,'RECEIPT_SHA',d.sha(rr)),mock.patch.object(d,'OBS_CANONICAL_SHA',d.sha(d.canonical(value))):
            self.assertEqual(d.read_pair(entry),(value,receipt))
    def test_frozen_cache_and_pure_fixture(self):
        with frozen_fixture() as (entry,kit,t,f):
            value=f.fixture();proposal=f.project(value)
            self.assertEqual(proposal['topology']['systemd_version'],239)
            self.assertFalse(proposal['expected_review_body']['production_resume_authorized'])
    def test_bounded_refuses_existing_alarm(self):
        with mock.patch.object(d.signal,'getitimer',return_value=(1.0,0.0)):
            with self.assertRaises(ValueError):
                with d.bounded():pass
    def test_bounded_cleanup_preserves_primary(self):
        error=KeyboardInterrupt();calls=[None,OSError('SECRET')]
        with mock.patch.object(d.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(d.signal,'signal'),mock.patch.object(d.signal,'setitimer',side_effect=calls):
            with self.assertRaises(KeyboardInterrupt) as got:
                with d.bounded():raise error
        self.assertIs(got.exception,error);self.assertTrue(error.diagnostic_cleanup_failed)
    def test_bounded_cleanup_without_primary_marked(self):
        with mock.patch.object(d.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(d.signal,'signal'),mock.patch.object(d.signal,'setitimer',side_effect=[None,OSError()]):
            with self.assertRaises(ValueError) as got:
                with d.bounded():pass
        self.assertTrue(got.exception.diagnostic_cleanup_failed)
    def test_failure_text_never_echoed(self):
        result=d.error_summary(ValueError('SECRET_ENV=private'))
        self.assertNotIn('SECRET',json.dumps(result));self.assertEqual(result['code'],'UNLISTED_CODE')
    def test_static_failure_code_and_frame(self):
        d.remember_source('TEST_PUBLIC','<public>',b"raise ValueError('FIXED_TEST_CODE')")
        try:exec(compile("raise ValueError('FIXED_TEST_CODE')",'<public>','exec'))
        except ValueError as error:result=d.error_summary(error)
        self.assertEqual(result['code'],'FIXED_TEST_CODE');self.assertEqual(result['public_source_frames'],[{'source':'TEST_PUBLIC','line':1}])
    def test_sources_exact_three_no_execution(self):
        entry=mock.MagicMock();tree=entry.DescriptorTree.return_value.__enter__.return_value
        tree.read.side_effect=lambda name,maximum:(PREP/name).read_bytes()
        result=d.read_sources(entry)
        self.assertEqual(set(result),set(d.SOURCE_MANIFEST['files']));self.assertEqual(tree.read.call_count,3)
        entry.DescriptorTree.assert_called_once_with(d.PREP)
    def test_changed_source_rejected(self):
        entry=mock.MagicMock();entry.DescriptorTree.return_value.__enter__.return_value.read.return_value=b'CHANGED'
        with self.assertRaises(ValueError):d.read_sources(entry)
    def test_probe_scope_rejected_before_read(self):
        entry=mock.MagicMock();observation={'finite_probe':{'result':{'created_receipt':{'path':'/private/other','sha256':d.PROBE_SHA}}}}
        with self.assertRaises(ValueError):d.read_probe(entry,observation)
        entry.DescriptorTree.assert_not_called()
    def test_pair_hash_mismatch_rejects_before_decode(self):
        entry=mock.MagicMock();entry.DescriptorTree.return_value.__enter__.return_value.read.return_value=b'wrong'
        with self.assertRaises(ValueError):d.read_pair(entry)
        entry.decode.assert_not_called()
    def test_no_host_action_functions_in_main_source(self):
        source=(HERE/'export_saved_evidence.py').read_text();tree=ast.parse(source)
        forbidden={'collect','observe','observe_host','execute_reviewed_probe','run_preparation','fetch','chmod','fchmod','unlink','mkdir','write'}
        calls={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
        self.assertFalse(calls&forbidden)
    def test_embedded_schema_exact_source_hash_and_loading(self):
        raw=(HERE/'export_schema.py').read_bytes()
        self.assertEqual(d.sha(raw),d.SCHEMA_SHA);self.assertEqual(len(raw),d.SCHEMA_BYTES)
        self.assertTrue(callable(d.load_schema().validate_export))
    def test_schema_bad_size_or_hash_refused(self):
        with mock.patch.object(d,'SCHEMA_BYTES',1),mock.patch.object(d,'SCHEMA_SHA','0'*64),mock.patch.object(d,'SCHEMA_ZLIB_BASE64',base64.b64encode(zlib.compress(b'x')).decode()):
            with self.assertRaises(ValueError):d.load_schema()
    def test_schema_trailing_compressed_content_refused(self):
        raw=b'pass\n'
        with mock.patch.object(d,'SCHEMA_BYTES',len(raw)),mock.patch.object(d,'SCHEMA_SHA',d.sha(raw)),mock.patch.object(d,'SCHEMA_ZLIB_BASE64',base64.b64encode(zlib.compress(raw)+b'trailing').decode()):
            with self.assertRaises(ValueError):d.load_schema()
    def test_main_wrong_host_stops_before_read(self):
        with mock.patch.object(d.os,'geteuid',return_value=0),mock.patch.object(d.os,'getegid',return_value=0),mock.patch.object(d.socket,'gethostname',return_value='wrong'),mock.patch.object(d,'entry_bytes') as reader,mock.patch('builtins.print') as output:
            self.assertEqual(d.main(),2)
        reader.assert_not_called();self.assertEqual(json.loads(output.call_args[0][0])['state'],'HOLD')

class CompleteExportContracts(unittest.TestCase):
    def fixture(self):
        name='test_export_schema';path=HERE/(name+'.py');module=types.ModuleType(name);module.__file__=str(path)
        old_path=list(sys.path)
        try:exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
        finally:sys.path[:]=old_path
        return module.fixture()
    def test_complete_actual_cache_projection_export_and_offline_hashes(self):
        import export_schema
        with frozen_fixture() as (entry,kit,t,f):
            v=self.fixture();raw,meta=f.bind(v)
            original=t.project_topology(v['observation'],raw,meta,d.MANIFEST_SHA,v['sources'],v['dropins'],d.EXPECTED_BODY['preparation_source_manifest_sha256'])
            with mock.patch.object(d,'DROPINS',v['dropins']),mock.patch.object(d,'EXPECTED_BODY',original['expected_review_body']),mock.patch.object(d,'EXPECTED_BODY_SHA',d.sha(d.canonical(original['expected_review_body']))),mock.patch.object(d,'OBS_CANONICAL_SHA',d.sha(d.canonical(v['observation']))):
                result=d.export_value(v['observation'],raw,meta,v['receipt'],kit,t,export_schema)
            self.assertEqual(result['topology_raw_utf8'].encode(),original['topology_raw'])
            self.assertLess(len(d.canonical(result)),d.MAX_OUTPUT)
            verified=offline.verify_packet(result,t,export_schema)
            self.assertEqual(verified['computed']['evidence_records_sha256'],original['bindings']['evidence_records_sha256'])
            self.assertEqual(verified['computed']['topology_sha256'],original['topology_sha256'])
            self.assertFalse(verified['whole_observation_recomputed'])
    def test_unknown_schema_blocks_export(self):
        import export_schema
        with frozen_fixture() as (entry,kit,t,f):
            v=self.fixture();v['receipt']['private_environment']='SECRET'
            raw,meta=f.bind(v)
            original=t.project_topology(v['observation'],raw,meta,d.MANIFEST_SHA,v['sources'],v['dropins'],d.EXPECTED_BODY['preparation_source_manifest_sha256'])
            with mock.patch.object(d,'DROPINS',v['dropins']),mock.patch.object(d,'EXPECTED_BODY',original['expected_review_body']),mock.patch.object(d,'EXPECTED_BODY_SHA',d.sha(d.canonical(original['expected_review_body']))):
                with self.assertRaises(ValueError):d.export_value(v['observation'],raw,meta,v['receipt'],kit,t,export_schema)


class OfflinePinContracts(unittest.TestCase):
    def packet(self):
        import export_schema
        with frozen_fixture() as (entry,kit,t,f):
            v=CompleteExportContracts().fixture();raw,meta=f.bind(v)
            original=t.project_topology(v['observation'],raw,meta,d.MANIFEST_SHA,v['sources'],v['dropins'],d.EXPECTED_BODY['preparation_source_manifest_sha256'])
            with mock.patch.object(d,'DROPINS',v['dropins']),mock.patch.object(d,'EXPECTED_BODY',original['expected_review_body']),mock.patch.object(d,'EXPECTED_BODY_SHA',d.sha(d.canonical(original['expected_review_body']))),mock.patch.object(d,'OBS_CANONICAL_SHA',d.sha(d.canonical(v['observation']))):
                packet=d.export_value(v['observation'],raw,meta,v['receipt'],kit,t,export_schema)
                expected=types.SimpleNamespace(**{name:copy.deepcopy(getattr(d,name)) for name in
                    ('EXPECTED_BODY','EXPECTED_BODY_SHA','OBS_SHA','RECEIPT_SHA','OBS_CANONICAL_SHA','NONCE','SCHEMA_SHA','DROPINS','SOURCE_MANIFEST')})
            return packet,expected
    def test_all_packet_pins_pass(self):
        packet,expected=self.packet();offline.validate_packet_pins(packet,expected)
    def test_observation_file_and_receipt_pin_change_rejected(self):
        packet,expected=self.packet()
        for key in ('observation_file_sha256','diagnostic_receipt_sha256','observation_full_canonical_sha256'):
            bad=copy.deepcopy(packet);bad[key]='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):offline.validate_packet_pins(bad,expected)
    def test_self_consistent_changed_whole_observation_binding_rejected(self):
        packet,expected=self.packet();packet['observation_full_canonical_sha256']='0'*64
        packet['bindings']['observation_sha256']='0'*64;packet['unsigned_expected_review_body']['observation_sha256']='0'*64
        packet['expected_review_body_sha256']=d.sha(d.canonical(packet['unsigned_expected_review_body']))
        with self.assertRaises(ValueError):offline.validate_packet_pins(packet,expected)
    def test_extra_approval_claim_or_changed_labels_rejected(self):
        packet,expected=self.packet()
        for key,value in (('approval_granted',True),('collection','COMPLETE'),('whole_observation_validation','INDEPENDENTLY_RECOMPUTED')):
            bad=copy.deepcopy(packet);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):offline.validate_packet_pins(bad,expected)
    def test_unknown_dropin_metadata_rejected(self):
        packet,expected=self.packet();packet['socket_dropins']['private']='SECRET'
        with self.assertRaises(ValueError):offline.validate_packet_pins(packet,expected)


class MainFlowContracts(unittest.TestCase):
    @contextlib.contextmanager
    def effects(self):
        entry=mock.MagicMock();kit=mock.MagicMock();kit.manifest={'kit_source_commit':d.SOURCE};kit.cache={}
        entry.verify_kit.return_value=kit
        observation={'finite_probe':{}};diagnostic={};receipt={};metadata={};raw=b'{}\n'
        patches=[mock.patch.object(d.os,'geteuid',return_value=0),mock.patch.object(d.os,'getegid',return_value=0),
            mock.patch.object(d.socket,'gethostname',return_value=d.HOST),mock.patch.object(d,'entry_bytes',return_value=b'# synthetic test seam\n'),
            mock.patch.object(d,'load_entry',return_value=entry),mock.patch.object(d,'read_pair',return_value=(observation,diagnostic)),
            mock.patch.object(d,'read_sources',return_value={'epoch7_topology_projection.py':b'# pure test seam\n'}),
            mock.patch.object(d,'read_probe',return_value=(raw,metadata,receipt)),mock.patch.object(d,'load_schema'),
            mock.patch.object(d,'export_value',return_value={'state':'COMPLETE_SAVED_DATA_EXPORT'}),mock.patch('builtins.print')]
        with contextlib.ExitStack() as stack:
            values=[stack.enter_context(x) for x in patches]
            yield entry,values[-2],values[-1]
    def test_one_export_then_fixed_rechecks(self):
        with self.effects() as (entry,project,output):
            self.assertEqual(d.main(),0);self.assertEqual(project.call_count,1);self.assertEqual(entry.verify_kit.call_count,2)
            self.assertEqual(json.loads(output.call_args[0][0])['state'],'COMPLETE_SAVED_DATA_EXPORT')
    def test_schema_rejection_outputs_hold_only(self):
        with self.effects() as (entry,project,output):
            project.side_effect=ValueError('PRIVATE_CREDENTIAL')
            self.assertEqual(d.main(),2);raw=output.call_args[0][0]
            self.assertNotIn('PRIVATE_CREDENTIAL',raw);self.assertEqual(json.loads(raw)['state'],'HOLD')
            self.assertEqual(json.loads(raw)['failed_phase'],'PURE_PROJECTION_AND_STRICT_EXPORT_SCHEMA')
    def test_final_reverification_failure_never_prints_complete(self):
        with self.effects() as (entry,project,output):
            entry.verify_kit.side_effect=[entry.verify_kit.return_value,ValueError('PRIVATE')]
            self.assertEqual(d.main(),2);result=json.loads(output.call_args[0][0]);self.assertEqual(result['state'],'HOLD');self.assertTrue(result['cleanup_unknown'])
    def test_import_cleanup_interrupt_preserved_without_complete(self):
        with self.effects() as (entry,project,output):
            entry.verify_kit.return_value.imports.return_value.__exit__.side_effect=KeyboardInterrupt()
            self.assertEqual(d.main(),2);result=json.loads(output.call_args[0][0]);self.assertEqual(result['error']['exception_class'],'KeyboardInterrupt');self.assertTrue(result['cleanup_unknown'])
    def test_reader_interrupt_no_probe_or_schema(self):
        with self.effects() as (entry,project,output),mock.patch.object(d,'read_pair',side_effect=d.Deadline()):
            self.assertEqual(d.main(),2);project.assert_not_called();self.assertEqual(json.loads(output.call_args[0][0])['failure_code'],'EXPORT_DEADLINE')
    def test_output_failure_never_retried(self):
        with self.effects() as (entry,project,output):
            output.side_effect=BrokenPipeError();self.assertEqual(d.main(),2);self.assertEqual(output.call_count,1)
    def test_output_bound_is_fail_closed(self):
        with self.effects() as (entry,project,output),mock.patch.object(d,'MAX_OUTPUT',8):
            self.assertEqual(d.main(),2);self.assertEqual(json.loads(output.call_args[0][0])['state'],'HOLD')

if __name__=='__main__':unittest.main(verbosity=2)
