"""Test-only harness; private suite is never selected by --portable."""
import argparse,importlib,json,os,pathlib,sys,unittest
parser=argparse.ArgumentParser();parser.add_argument('--portable',action='store_true');parser.add_argument('--kit-root');parser.add_argument('tests',nargs='*')
args=parser.parse_args();folder=pathlib.Path(__file__).resolve().parent;root=folder.parent
kit=pathlib.Path(args.kit_root).resolve() if args.kit_root else root/'kit-candidate/build-9c40fc81-python368-a/epoch7-recovery-candidate-r5'
os.environ['EPOCH7_PREP_TEST_KIT_ROOT']=str(kit)
sys.path.insert(0,str((kit/'xuanjun-p2-package/stage1') if args.portable else root/'runtime-build-101b465c/xuanjun-p2-package/stage1'))
import activation_control
paths=[str(folder)]
if not args.portable:paths += [str(root/'host-driver-candidate'),str(root/'snapshot-candidate/tests')]+[str(p) for p in root.glob('*-candidate') if p.is_dir()]
paths += [str(kit/'helpers')]+[str(p) for p in sorted((kit/'tests').iterdir()) if p.is_dir()]
sys.path[:0]=paths
names=args.tests or ['test_epoch7_prepare','test_epoch7_topology_projection']
if args.portable and (len(names)!=2 or set(names)!={'test_epoch7_prepare','test_epoch7_topology_projection'}):raise ValueError('PORTABLE_EXACT_PUBLIC_SUITES')
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in names)
result=unittest.TextTestRunner(verbosity=2).run(suite)
passed=result.wasSuccessful() and (not args.portable or not result.skipped)
print(json.dumps({'schema':1,'state':'PASS' if passed else 'FAIL','tests':result.testsRun,
 'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped),
 'python':sys.version.split()[0],'host_NOT_RUN':True,
 'privateplan_NOT_RUN':args.portable or 'test_epoch7_prepare_private' not in names},sort_keys=True))
sys.exit(not passed)
