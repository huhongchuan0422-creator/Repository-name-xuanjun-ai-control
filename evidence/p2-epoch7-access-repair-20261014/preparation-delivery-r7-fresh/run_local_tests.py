"""Exact portable public delivery tests. No host or network operations."""
import importlib.util,json,pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parent
SUITES=(('test_epoch7_prepare_delivery.py',41),('test_epoch7_prepare_delivery_projection.py',19),('test_epoch7_prepare_bootstrap_binding.py',9),('test_r7_delivery_scope.py',15))
def main():
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode) or sys.argv[1:]:raise ValueError('EXACT_ISOLATED_TEST_SCOPE')
    suite=unittest.TestSuite()
    for index,(name,count) in enumerate(SUITES):
        spec=importlib.util.spec_from_file_location('delivery_contract_'+str(index),str(ROOT/name));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        tests=unittest.defaultTestLoader.loadTestsFromModule(module)
        if tests.countTestCases()!=count:raise ValueError('EXACT_DELIVERY_TEST_COUNT')
        suite.addTests(tests)
    result=unittest.TextTestRunner(verbosity=2,stream=sys.stderr).run(suite)
    passed=result.wasSuccessful() and not result.skipped and result.testsRun==sum(row[1] for row in SUITES)
    print(json.dumps({'schema':1,'state':'PASS' if passed else 'FAIL','tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped),'python':sys.version.split()[0],'host_NOT_RUN':True,'network_NOT_RUN':True,'privateplan_NOT_RUN':True},sort_keys=True))
    return 0 if passed else 1
if __name__=='__main__':sys.exit(main())
