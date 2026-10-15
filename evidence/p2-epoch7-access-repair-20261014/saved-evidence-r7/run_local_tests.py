"""Public synthetic tests only; exporter and host actions are never invoked."""
import json,pathlib,sys,types,unittest
root=pathlib.Path(__file__).resolve().parent
name=sys.argv[1] if len(sys.argv)==2 else 'orchestration'
if name not in ('orchestration','schema','bootstrap'):raise ValueError('EXACT_SUITE')
modules={'orchestration':('export_saved_evidence','verify_exported_evidence','export_schema','test_export_saved_evidence'),
         'schema':('export_schema','test_export_schema'),'bootstrap':('bootstrap/test_owner_bootstrap',)}[name]
for relative in modules:
    path=root/(relative+'.py');module_name=relative.rsplit('/',1)[-1];module=types.ModuleType(module_name);module.__file__=str(path);sys.modules[module_name]=module
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
suite=unittest.defaultTestLoader.loadTestsFromModule(module)
expected={'orchestration':35,'schema':16,'bootstrap':23}[name]
if suite.countTestCases()!=expected:raise ValueError('EXACT_TEST_COUNT:'+str(suite.countTestCases()))
result=unittest.TextTestRunner(verbosity=2).run(suite)
ok=result.wasSuccessful() and not result.skipped and result.testsRun==expected
print(json.dumps({'schema':1,'state':'PASS' if ok else 'FAIL','suite':name,'tests':result.testsRun,
    'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped),'python':sys.version.split()[0],
    'host_NOT_RUN':True,'network_NOT_RUN':True},sort_keys=True));sys.exit(not ok)
