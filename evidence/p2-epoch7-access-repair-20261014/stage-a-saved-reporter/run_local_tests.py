"""Focused new reconstruction suites only; no host or prior runtime suite."""
import json,pathlib,sys,types,unittest
root=pathlib.Path(__file__).resolve().parent
suite=sys.argv[1] if len(sys.argv)==2 else 'reporter'
if suite not in ('reporter','coverage'):raise ValueError('EXACT_SUITE')
if suite=='reporter':path=root/'test_report_saved_stage_a.py'
else:
    parent=root.parent/'coverage-candidate'
    if not parent.is_dir():parent=root.parent/'stage-a-saved-coverage-candidate'
    path=parent/'test_saved_authority_coverage.py'
sys.path.insert(0,str(root));name='focused_'+suite
module=types.ModuleType(name);module.__file__=str(path);sys.modules[name]=module
exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
tests=unittest.defaultTestLoader.loadTestsFromModule(module)
expected={'reporter':43,'coverage':66}[suite]
if tests.countTestCases()!=expected:raise ValueError('EXACT_TEST_COUNT:'+str(tests.countTestCases()))
result=unittest.TextTestRunner(verbosity=2).run(tests)
ok=result.wasSuccessful() and not result.skipped and result.testsRun==expected
print(json.dumps({'schema':1,'state':'PASS' if ok else 'FAIL','suite':suite,'tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped),'python':sys.version.split()[0],'host_NOT_RUN':True,'network_NOT_RUN':True},sort_keys=True));sys.exit(not ok)
