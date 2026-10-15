"""R7 delivery-only review/input and private-output preservation boundaries."""
import contextlib,hashlib,importlib.util,pathlib,time,types,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r7_delivery_scope',str(ROOT/'epoch7_prepare_delivery.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ARGS=['--observation',m.OBSERVATION_PATH,'--observation-sha256',m.OBSERVATION_SHA256,
      '--topology-review-id','123456789','--retained-renewal-timer','enable-after-reviewed-checks']

def rows():
    return [{'path':m.CAND+'/'+prefix+pin[:16]+'.private.json','sha256':pin,'bytes':n}
        for prefix,pin,n in [('epoch7-approved-plan-','1'*64,100),('epoch7-resume-inputs-','2'*64,200),('epoch7-review-packet-','3'*64,300)]]

def error_with_outputs(count=3):
    error=ValueError('private text');error.preparation_outputs=rows()[:count]
    error.preparation_created_paths=[r['path'] for r in rows()[:count]];return error

class ScopeTests(unittest.TestCase):
    def test_review_and_explicit_timer_required_before_any_effect(self):
        args=[ARGS[:4],ARGS[:4]+['--topology-review-id','123456789'],
              ARGS[:4]+['--retained-renewal-timer','enable-after-reviewed-checks']]
        args.extend(ARGS[:4]+['--topology-review-id',v]+ARGS[-2:] for v in ('0','-1','100000000000000000000','true','unknown'))
        args.append(ARGS[:-1]+['disable'])
        for value in args:
            with self.subTest(value=value),mock.patch.object(m,'PINS_BOUND',True),mock.patch.object(m,'PUBLICATION_COMMIT','a'*40),\
                 mock.patch.object(m.os,'geteuid') as uid,mock.patch.object(m,'fetch_sources') as fetch,mock.patch.object(m,'stage') as stage:
                with self.assertRaises(m.Hold):m.run(value)
                uid.assert_not_called();fetch.assert_not_called();stage.assert_not_called()
    def test_observation_substitution_refuses_before_host(self):
        for index,value in ((1,m.CAND+'/epoch7-observation-'+'0'*16+'.private.json'),(3,'0'*64)):
            args=list(ARGS);args[index]=value
            with mock.patch.object(m,'PINS_BOUND',True),mock.patch.object(m,'PUBLICATION_COMMIT','a'*40),mock.patch.object(m.os,'geteuid') as uid:
                with self.assertRaisesRegex(m.Hold,'OBSERVATION_BINDING'):m.run(args)
                uid.assert_not_called()
    def test_extra_operation_or_probe_install_flags_refuse(self):
        for extra in (['--operation','prepare'],['--probe'],['--resume'],['--install'],['--execute-reviewed-prerequisites']):
            with mock.patch.object(m,'fetch_sources') as fetch,mock.patch.object(m,'stage') as stage:
                with self.assertRaisesRegex(m.Hold,'ARGUMENTS'):m.run(ARGS+extra)
                fetch.assert_not_called();stage.assert_not_called()
    def test_complete_and_partial_output_metadata_preserved(self):
        for count in range(4):
            error=error_with_outputs(count);value=m.retained_outputs(error)
            self.assertEqual(value['completed_outputs'],rows()[:count]);self.assertEqual(value['created_output_paths'],error.preparation_created_paths)
            self.assertNotIn('private text',repr(value))
    def test_partial_created_file_without_completed_hash_is_retained(self):
        error=error_with_outputs(1);error.preparation_created_paths.append(rows()[1]['path'])
        value=m.retained_outputs(error);self.assertEqual(value['completed_outputs'],rows()[:1]);self.assertEqual(len(value['created_output_paths']),2)
    def test_output_unknown_fields_private_paths_hash_size_and_duplicates_reject(self):
        variants=[]
        for key,value in [('path','/private/secret'),('sha256','4'*64),('bytes',True),('bytes',0),('bytes',2*1024*1024+1),('private','secret')]:
            error=error_with_outputs();error.preparation_outputs[0][key]=value;variants.append(error)
        error=error_with_outputs();error.preparation_outputs.append(rows()[0]);variants.append(error)
        error=error_with_outputs();error.preparation_created_paths.append(rows()[0]['path']);variants.append(error)
        for error in variants:
            with self.assertRaises(m.Hold):m.retained_outputs(error)
    def test_output_only_exact_three_prefixes_are_allowed(self):
        for path in (m.CAND+'/epoch7-approved-plan-'+'1'*16+'.private.json/extra',m.CAND+'/arbitrary-'+'1'*16+'.private.json',m.CAND+'/../epoch7-approved-plan-'+'1'*16+'.private.json'):
            error=error_with_outputs(0);error.preparation_created_paths=[path]
            with self.assertRaises(m.Hold):m.retained_outputs(error)
    def test_status_fallback_has_no_raw_output_evidence(self):
        error=error_with_outputs();error.preparation_outputs[0]['private']='secret'
        with mock.patch.object(m,'run',side_effect=error),mock.patch.object(m,'deliver_status') as emit:
            self.assertEqual(m.entrypoint(ARGS),2)
        value=emit.call_args[0][0];self.assertEqual(value['preparation_output_evidence'],'UNKNOWN');self.assertTrue(value['cleanup_unknown']);self.assertNotIn('secret',repr(value))
    def test_initial_unbound_gate_retains_no_output(self):
        with mock.patch.object(m,'fetch_sources') as fetch,mock.patch.object(m,'stage') as stage,mock.patch.object(m,'deliver_status') as emit:
            self.assertEqual(m.entrypoint(ARGS),2)
        fetch.assert_not_called();stage.assert_not_called();self.assertEqual(emit.call_args[0][0]['completed_outputs'],[])

class PostReturnTests(unittest.TestCase):
    def invoke(self,mode):
        result={'state':'PREPARED_NOT_ADMITTED','outputs':rows(),'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
        if mode=='bad_result':result['state']='TOPOLOGY_REVIEW_REQUIRED'
        primary=KeyboardInterrupt() if mode=='interrupt' else m.Hold('FILE_BYTES')
        @contextlib.contextmanager
        def plain(*args):yield time.monotonic()+10
        @contextlib.contextmanager
        def inner(*args):
            yield time.monotonic()+10
            if mode=='deadline':raise m.DeadlineError()
            if mode=='cleanup':raise m.CleanupError()
        module=types.SimpleNamespace(budget=inner,run_preparation=mock.Mock(return_value=result),CleanupError=m.CleanupError,CURRENT_PHASE='FINALIZE_BUDGET',PHASES={'FINALIZE_BUDGET'})
        def stage(cache,end,allow_create=True):
            if not allow_create and mode in ('recheck','interrupt'):raise primary
            return {'state':'REUSED_EXACT','path':m.PREP_ROOT,'files':{name:{'sha256':pin,'bytes':size} for name,(pin,size) in m.SOURCES.items()},'created_paths':[]}
        with mock.patch.object(m,'PINS_BOUND',True),mock.patch.object(m,'PUBLICATION_COMMIT','a'*40),\
             mock.patch.object(m.os,'geteuid',return_value=0),mock.patch.object(m.os,'getegid',return_value=0),mock.patch.object(m.socket,'gethostname',return_value=m.HOST),\
             mock.patch.object(m,'budget',plain),mock.patch.object(m,'fetch_sources',return_value={}),mock.patch.object(m,'public_labels',return_value=frozenset(m.CODES)),\
             mock.patch.object(m,'preparer',return_value=module),mock.patch.object(m,'stage',side_effect=stage),mock.patch.object(m,'deliver_status') as emit:
            code=m.entrypoint(ARGS)
        self.assertEqual(module.run_preparation.call_count,1)
        args=module.run_preparation.call_args[0][0];self.assertEqual((args.operation,args.topology_review_id,args.retained_renewal_timer),('prepare',123456789,'enable-after-reviewed-checks'))
        return code,emit.call_args[0][0]
    def test_nonpreparation_result_never_claims_success(self):
        code,value=self.invoke('bad_result');self.assertEqual(code,2);self.assertEqual(value['failure_label'],'PREPARATION_RESULT_SCOPE');self.assertEqual(value['completed_outputs'],rows())
    def test_success_keeps_private_preparation_summary(self):
        code,value=self.invoke('pass');self.assertEqual(code,0);self.assertEqual(value['preparation']['outputs'],rows());self.assertEqual(value['install_admission'],'NOT_GRANTED')
    def test_post_return_source_recheck_failure_keeps_output_hashes(self):
        code,value=self.invoke('recheck');self.assertEqual(code,2);self.assertEqual(value['completed_outputs'],rows());self.assertEqual(value['failure_label'],'FILE_BYTES')
    def test_post_return_deadline_keeps_output_hashes(self):
        code,value=self.invoke('deadline');self.assertEqual(code,2);self.assertEqual(value['completed_outputs'],rows());self.assertEqual(value['failure_code'],'DeadlineError')
    def test_post_return_cleanup_keeps_output_hashes(self):
        code,value=self.invoke('cleanup');self.assertEqual(code,2);self.assertEqual(value['completed_outputs'],rows());self.assertTrue(value['cleanup_unknown'])
    def test_post_return_interrupt_keeps_output_hashes(self):
        code,value=self.invoke('interrupt');self.assertEqual(code,2);self.assertEqual(value['completed_outputs'],rows());self.assertEqual(value['failure_code'],'KeyboardInterrupt')

if __name__=='__main__':unittest.main(verbosity=2)
