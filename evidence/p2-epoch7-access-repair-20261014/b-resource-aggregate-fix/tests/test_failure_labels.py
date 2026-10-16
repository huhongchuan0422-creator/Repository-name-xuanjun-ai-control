"""New finite diagnostic regressions only; no delivery or host execution."""
import ast
import hashlib
import importlib.util
import pathlib
import types
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE=ROOT.parent/'b-release-parent-fix-candidate'
path=ROOT/'delivery-overlay/epoch7_prepare_delivery.py'
spec=importlib.util.spec_from_file_location('resource_diagnostic_only',str(path))
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)


class DiagnosticTests(unittest.TestCase):
    def labels(self):
        return delivery.public_labels({
            'delta':(ROOT.parent/'kit/epoch7-recovery-candidate-r7/helpers/epoch7_delta.py').read_bytes(),
            'resources':(ROOT/'kit-overlay/helpers/epoch7_resource_observer.py').read_bytes(),
            'factory':(ROOT/'kit-overlay/helpers/epoch7_host_factory.py').read_bytes()})

    def project(self,error,labels=None):
        preparer=types.SimpleNamespace(CURRENT_PHASE='COMPILE_PRIVATE_BUNDLE',
            PHASES={'COMPILE_PRIVATE_BUNDLE'},CleanupError=type('OtherCleanup',(Exception,),{}))
        return delivery.failure(error,'PREPARE_PRIVATE_PLAN',preparer,
                                self.labels() if labels is None else labels)

    def test_actual_static_failure_is_visible_before_source_labels(self):
        self.assertEqual(self.project(ValueError('PROPOSAL_SIZE_BOUND'),frozenset())['failure_label'],
                         'PROPOSAL_SIZE_BOUND')

    def test_authenticated_new_helper_error_is_visible(self):
        self.assertEqual(self.project(ValueError('EPOCH7_HOST_RESOURCE_BINDING_PATH'))['failure_label'],
                         'EPOCH7_HOST_RESOURCE_BINDING_PATH')

    def test_authenticated_factory_error_is_visible(self):
        code='EPOCH7_HOST_FACTORY_SOURCE_DERIVED_COMPLETE_RESOURCE_VIEWS'
        self.assertEqual(self.project(ValueError(code))['failure_label'],code)

    def test_private_nonliteral_and_multiline_are_never_emitted(self):
        for value in ('private-mixed-Sekret/path123', 'PROPOSAL_SIZE_BOUND\nprivate-secret'):
            report=self.project(ValueError(value))
            self.assertIsNone(report['failure_label'])
            self.assertNotIn(value,str(report))

    def test_no_error_argument_or_multiple_arguments_are_not_emitted(self):
        for error in (ValueError(),ValueError('PROPOSAL_SIZE_BOUND','secret')):
            self.assertIsNone(self.project(error)['failure_label'])

    def test_pending_delivery_overlay_refuses_before_effects(self):
        self.assertIs(delivery.PINS_BOUND,False)
        args=['--observation',delivery.OBSERVATION_PATH,'--observation-sha256',delivery.OBSERVATION_SHA256,
              '--topology-review-id','6207642296','--retained-renewal-timer','enable-after-reviewed-checks']
        with mock.patch.object(delivery,'fetch_sources') as fetch:
            with self.assertRaisesRegex(ValueError,'UNBOUND'):delivery.run(args)
            fetch.assert_not_called()

    def test_label_sources_are_only_post_authenticated_compiler_members(self):
        source=path.read_text();parsed=ast.parse(source)
        run=next(node for node in parsed.body if isinstance(node,ast.FunctionDef) and node.name=='run')
        lines=source.splitlines();block='\n'.join(lines[run.lineno-1:run.body[-1].lineno])
        self.assertLess(block.index('compiler_inputs(archive)'),block.index('compiler_delta=compiler_files'))
        for name in ('epoch7_delta.py','epoch7_resource_observer.py','epoch7_host_factory.py'):
            self.assertIn("compiler_files['helpers/"+name+"']",block)

    def test_failure_output_has_only_existing_fields(self):
        raw=(BASE/'delivery-candidate/epoch7_prepare_delivery.py').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '8bc04315cbe23ee5338ccdc3341f536b15088550ef0d01e655ed4bb4fbb0f7d9')
        before=ast.parse(raw.decode());after=ast.parse(path.read_text())
        for name in ('failure','deliver_status','retained_outputs','code_locations'):
            a=next(node for node in before.body if isinstance(node,ast.FunctionDef) and node.name==name)
            b=next(node for node in after.body if isinstance(node,ast.FunctionDef) and node.name==name)
            self.assertEqual(ast.dump(a),ast.dump(b))


class VersionBoundaryTests(unittest.TestCase):
    def entry(self):
        path=ROOT/'kit-overlay/epoch7_recovery_entry.py'
        spec=importlib.util.spec_from_file_location('resourcebind_entry_test',str(path))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def kit(self,entry,leaf):
        value=object.__new__(entry.VerifiedKit)
        value.root=entry.CANDIDATE_PARENT+'/'+leaf
        value.manifest={'production_resume':entry.RESUME_COMPOSED};value.digest='d'*64
        return value

    def test_both_old_roots_refuse_before_private_reads(self):
        entry=self.entry()
        for leaf in ('epoch7-recovery-candidate-r7','epoch7-recovery-candidate-r7-parentfix'):
            kit=self.kit(entry,leaf)
            with mock.patch.object(entry.os,'geteuid',return_value=0),mock.patch.object(entry.os,'uname',return_value=types.SimpleNamespace(nodename=entry.FIXED_HOST)),mock.patch.object(kit,'_private_resume_inputs') as read:
                with self.assertRaisesRegex(ValueError,'RESUME_FIXED_HOST_ROOT'):
                    kit.resume('plan','a'*64,'seed','b'*64,1,'c'*64)
                read.assert_not_called()

    def test_new_root_still_refuses_missing_complete_review(self):
        entry=self.entry();kit=self.kit(entry,'epoch7-recovery-candidate-r7-resourcebind')
        with mock.patch.object(entry.os,'geteuid',return_value=0),mock.patch.object(entry.os,'uname',return_value=types.SimpleNamespace(nodename=entry.FIXED_HOST)),mock.patch.object(kit,'_private_resume_inputs') as read:
            for review in (None,True,0,-1):
                with self.assertRaisesRegex(ValueError,'FRESH_REVIEW_ARGUMENTS_REQUIRED'):
                    kit.resume('plan','a'*64,'seed','b'*64,review,'c'*64)
            read.assert_not_called()

    def test_new_root_protected_input_stop_remains_not_admitted(self):
        entry=self.entry();kit=self.kit(entry,'epoch7-recovery-candidate-r7-resourcebind')
        with mock.patch.object(entry.os,'geteuid',return_value=0),mock.patch.object(entry.os,'uname',return_value=types.SimpleNamespace(nodename=entry.FIXED_HOST)),mock.patch.object(kit,'_private_resume_inputs',side_effect=ValueError('SYNTHETIC_STOP')) as read:
            result=kit.resume('plan','a'*64,'seed','b'*64,1,'c'*64)
            self.assertFalse(result['success']);self.assertEqual(result['install_admission'],'NOT_GRANTED')
            self.assertEqual(result['production_resume'],'NOT_EXECUTED');read.assert_called_once()

    def test_new_wrapper_is_unbound_and_old_evidence_pins_are_exact(self):
        def constants(raw):
            result={}
            for node in ast.parse(raw.decode()).body:
                if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                    try:result[node.targets[0].id]=ast.literal_eval(node.value)
                    except (TypeError,ValueError):pass
            return result
        old=constants((BASE/'preparation-bound/epoch7_prepare.py').read_bytes())
        new=constants((ROOT/'preparation-overlay/epoch7_prepare.py').read_bytes())
        for key in ('KIT_SHA','ENTRY_SHA','OBSERVATION_SHA','EXPECTED_REVIEW_BODY_SHA','SAVED_PROJECTION_MANIFEST_SHA'):
            self.assertEqual(old[key],new[key])
        self.assertIsNone(new['COMPILER_KIT_SHA']);self.assertIsNone(new['COMPILER_ENTRY_SHA'])


if __name__=='__main__':unittest.main(verbosity=2)
