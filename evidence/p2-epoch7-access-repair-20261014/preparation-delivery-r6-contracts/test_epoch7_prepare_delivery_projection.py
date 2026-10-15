"""Safe public projection regressions; no real host or network operations."""
import ast,contextlib,hashlib,importlib.util,json,pathlib,time,types,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('projection_delivery',str(ROOT/'epoch7_prepare_delivery.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
PREPARATION_ROOT=ROOT/'fixtures/preparation-source'
def sources():return {name:(PREPARATION_ROOT/name).read_bytes() for name in m.SOURCES}
@contextlib.contextmanager
def scope(*args):yield time.monotonic()+30

def caught(source,filename):
    namespace={};exec(compile(source,filename,'exec'),namespace)
    try:namespace['f']()
    except BaseException as error:return error
    raise AssertionError('fixture must raise')

class SourceProjectionTests(unittest.TestCase):
    def test_ast_label_derivation_is_exact_frozen_diagnostic_logic(self):
        raw=(ROOT/'fixtures/diagnose_preparation.py').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'9cd065c6fb7d7f756314420d0867d4f639fcef090d82b449fdc3a20570eeed25')
        def function(raw,name):
            node=next(n for n in ast.parse(raw.decode('utf-8')).body if isinstance(n,ast.FunctionDef) and n.name==name)
            return ast.dump(node)
        self.assertEqual(function(raw,'public_labels'),function((ROOT/'epoch7_prepare_delivery.py').read_bytes(),'public_labels'))
        prior=function(raw,'code_locations').replace("'diagnostic'","'delivery/epoch7_prepare_delivery.py'")
        self.assertEqual(prior,function((ROOT/'epoch7_prepare_delivery.py').read_bytes(),'code_locations'))
    def test_static_code_paths_match_frozen_public_kit_manifest(self):
        manifest=ROOT/'fixtures/recovery-kit-manifest.json'
        raw=manifest.read_bytes();self.assertEqual(m.sha(raw),'70c76e30ae8390963f345813f87267bf1d2f024bc01031c8023733c84aa571cc')
        value=json.loads(raw.decode('utf-8'));self.assertEqual(m.PUBLIC_CODE_PATHS,set(value['modules'].values())|{'epoch7_recovery_entry.py'})
    def test_public_static_labels_include_native_guard_and_topology_guard(self):
        labels=m.public_labels(sources())
        self.assertIn('EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY',labels)
        self.assertIn('TOPOLOGY_KERNEL_PEER_IDENTITY',labels)
        self.assertNotIn('secret runtime configuration',labels)
    def test_label_source_type_and_size_are_bounded(self):
        for raw in ('not bytes',b'x'*1048577):
            with self.assertRaisesRegex(m.Hold,'LABEL_SOURCE_BOUND'):m.public_labels({'fixture.py':raw})
    def test_unknown_zero_multiarg_and_private_errors_are_not_echoed(self):
        labels=m.public_labels(sources())
        for error in (ValueError(),ValueError('secret runtime configuration'),ValueError('EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY','secret'),KeyError('EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY'),m.Hold('secret')):
            row=m.failure(error,'PROPOSE_TOPOLOGY',None,labels)
            self.assertIsNone(row['failure_label']);self.assertNotIn('secret',repr(row))
    def test_unknown_class_name_is_not_echoed(self):
        error=type('PrivateRuntimeValue',(Exception,),{})('secret')
        row=m.failure(error,'PROPOSE_TOPOLOGY',None,frozenset())
        self.assertEqual(row['failure_code'],'DEPENDENCY_ERROR');self.assertNotIn('PrivateRuntimeValue',repr(row))
    def test_unknown_phase_and_filename_are_not_echoed(self):
        p=types.SimpleNamespace(CURRENT_PHASE=['secret'],PHASES={'COLLECT_INPUTS'},CleanupError=type('C',(Exception,),{}))
        error=caught("def f(): raise ValueError('secret')",'/private/configuration')
        row=m.failure(error,'secret',p,frozenset())
        self.assertEqual(row['phase'],'INPUT_VALIDATION');self.assertEqual(row['preparation_phase'],'UNAVAILABLE')
        self.assertEqual(row['code_locations'],[]);self.assertNotIn('secret',repr(row));self.assertNotIn('/private',repr(row))
    def test_only_exact_allowlisted_paths_become_static_locations(self):
        rows=((m.PREP_ROOT+'/epoch7_prepare.py','preparation/epoch7_prepare.py'),
              (m.KIT_ROOT+'/helpers/epoch7_protected_fs.py','kit/helpers/epoch7_protected_fs.py'),
              ('<hash-pinned-build_epoch5_runtime>','historical/hash-pinned-build_epoch5_runtime'),
              (m.KIT_ROOT+'/private.py',None),(m.PREP_ROOT+'/private.py',None),
              (m.KIT_ROOT+'/../private.py',None))
        for path,wanted in rows:
            error=caught("def f(): raise ValueError('secret')",path);locations=m.code_locations(error)
            self.assertEqual(locations,[] if wanted is None else [{'source':wanted,'line':1}])
    def test_location_rows_are_bounded_without_locals(self):
        source="def f(n=20):\n    private_buffer='secret'\n    if n: return f(n-1)\n    raise ValueError(private_buffer)\n"
        error=caught(source,m.PREP_ROOT+'/epoch7_prepare.py');locations=m.code_locations(error)
        self.assertEqual(len(locations),8)
        self.assertTrue(all(set(row)=={'source','line'} and 0<row['line']<=100000 for row in locations))
        self.assertNotIn('secret',repr(locations))
    def test_cleanup_flags_and_distinct_verified_preparer_class_survive(self):
        p=m.preparer(sources())
        for error in (m.CleanupError(),p.CleanupError(),ValueError('secret')):
            if type(error) is ValueError:error.preparation_cleanup_failed=True
            row=m.failure(error,'PROPOSE_TOPOLOGY',p,frozenset())
            self.assertTrue(row['cleanup_unknown'])
    def test_only_fixed_staging_paths_are_projected(self):
        error=ValueError('secret');error.delivery_created_paths=[m.PREP_ROOT,'/private/file']
        error.delivery_staging={'state':'STAGED_EXACT','path':'/private/file','secret':'secret'}
        row=m.retained_staging(error)
        self.assertEqual(row,{'created_paths':[m.PREP_ROOT],'staging':None})
        self.assertNotIn('/private',repr(row));self.assertNotIn('secret',repr(row))

class IntegratedProjectionTests(unittest.TestCase):
    def invoke(self,where='proposal',error=None,projector_failure=False):
        p=m.preparer(sources());events=[]
        staged={'state':'STAGED_EXACT','path':m.PREP_ROOT,
            'files':{name:{'sha256':digest,'bytes':size} for name,(digest,size) in m.SOURCES.items()},
            'created_paths':[m.PREP_ROOT]+[m.PREP_ROOT+'/'+name for name in sorted(m.SOURCES)]}
        p.budget=scope
        def fetch(end):
            events.append('fetch')
            if where=='fetch':raise error
            return sources()
        def load(cache):
            events.append('load')
            if where=='load':raise error
            return p
        def stage(cache,end,allow_create=True):
            events.append('create' if allow_create else 'verify')
            if where=='stage' and allow_create:
                error.delivery_created_paths=staged['created_paths'][:2];raise error
            if where=='verify' and not allow_create:raise error
            return staged
        def propose(args,end):
            events.append('propose')
            self.assertEqual(vars(args),{'operation':'propose-topology','observation':m.OBSERVATION_PATH,
                'observation_sha256':m.OBSERVATION_SHA256,'topology_review_id':None,'retained_renewal_timer':None})
            p.phase('COLLECT_INPUTS')
            if where=='native':p.need(False,'NATIVE_EXPECTED_AUTHORITY')
            if where=='proposal':raise error
            return {'state':'TOPOLOGY_REVIEW_REQUIRED'}
        p.run_preparation=propose
        original_failure=m.failure
        with mock.patch.object(m,'PINS_BOUND',True),mock.patch.object(m,'PUBLICATION_COMMIT','a'*40),\
             mock.patch.object(m.os,'geteuid',return_value=0),mock.patch.object(m.os,'getegid',return_value=0),\
             mock.patch.object(m.socket,'gethostname',return_value=m.HOST),mock.patch.object(m.sys,'flags',types.SimpleNamespace(isolated=1,no_site=1)),\
             mock.patch.object(m.sys,'dont_write_bytecode',True),mock.patch.object(m,'budget',scope),\
             mock.patch.object(m,'fetch_sources',fetch),mock.patch.object(m,'preparer',load),mock.patch.object(m,'stage',stage),\
             mock.patch.object(m,'failure',side_effect=ValueError('private projection') if projector_failure else original_failure),\
             mock.patch.object(m,'deliver_status') as output:
            code=m.entrypoint(['--observation',m.OBSERVATION_PATH,'--observation-sha256',m.OBSERVATION_SHA256])
        self.assertEqual(output.call_count,1)
        return code,events,output.call_args[0][0],staged
    def test_actual_frozen_guard_reports_inner_phase_literal_label_and_static_location(self):
        code,events,row,staged=self.invoke(where='native')
        self.assertEqual(code,2);self.assertEqual(row['preparation_phase'],'COLLECT_INPUTS')
        self.assertEqual(row['failure_label'],'EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY')
        self.assertIn('preparation/epoch7_prepare.py',[r['source'] for r in row['code_locations']])
        self.assertEqual(row['created_paths'],staged['created_paths']);self.assertEqual(row['staging'],staged)
        self.assertFalse(row['cleanup_unknown']);self.assertNotIn('proposal',row)
    def test_before_load_failure_reports_outer_phase_and_no_private_text(self):
        for where,wanted in (('fetch','DOWNLOAD_ALL'),('load','LOAD_VERIFIED_PREPARER')):
            code,events,row,staged=self.invoke(where=where,error=ValueError('secret'))
            self.assertEqual(row['phase'],wanted);self.assertEqual(row['preparation_phase'],'UNAVAILABLE')
            self.assertEqual(row['created_paths'],[]);self.assertTrue(row['code_locations']);self.assertNotIn('secret',repr(row))
    def test_post_proposal_verification_keeps_exact_phase_and_all_created_paths(self):
        code,events,row,staged=self.invoke(where='verify',error=m.Hold('FILE_BYTES'))
        self.assertEqual(row['phase'],'VERIFY_STAGING_AFTER_PROPOSAL');self.assertEqual(row['failure_label'],'FILE_BYTES')
        self.assertEqual(row['created_paths'],staged['created_paths']);self.assertNotIn('proposal',row)
    def test_zero_multiarg_error_does_not_replace_primary_class_with_projection_error(self):
        for error in (ValueError(),ValueError('EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY','secret')):
            code,events,row,staged=self.invoke(error=error)
            self.assertEqual(row['failure_code'],'ValueError');self.assertIsNone(row['failure_label'])
            self.assertEqual(row['preparation_phase'],'COLLECT_INPUTS');self.assertEqual(row['created_paths'],staged['created_paths'])
    def test_projection_fallback_preserves_complete_staging_and_sets_uncertainty(self):
        code,events,row,staged=self.invoke(error=ValueError('secret'),projector_failure=True)
        self.assertEqual(row['failure_code'],'DIAGNOSTIC_PROJECTION_FAILED');self.assertTrue(row['cleanup_unknown'])
        self.assertEqual(row['created_paths'],staged['created_paths']);self.assertEqual(row['staging'],staged)
        self.assertEqual(row['code_locations'],[]);self.assertNotIn('secret',repr(row));self.assertNotIn('private projection',repr(row))
    def test_projection_fallback_preserves_partial_created_paths(self):
        code,events,row,staged=self.invoke(where='stage',error=OSError('secret'),projector_failure=True)
        self.assertEqual(row['created_paths'],staged['created_paths'][:2]);self.assertIsNone(row['staging'])
        self.assertTrue(row['cleanup_unknown']);self.assertEqual(row['phase'],'STAGE_EXACT')
    def test_status_failure_is_not_retried(self):
        with mock.patch.object(m,'deliver_status',side_effect=m.StatusDeliveryError()) as output:
            self.assertEqual(m.entrypoint(['--forbidden']),2)
        self.assertEqual(output.call_count,1)
    def test_status_size_cap_refuses_before_write(self):
        with mock.patch.object(m.os,'write') as write:
            with self.assertRaises(m.StatusDeliveryError):m.deliver_status({'data':'x'*131072})
        write.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
