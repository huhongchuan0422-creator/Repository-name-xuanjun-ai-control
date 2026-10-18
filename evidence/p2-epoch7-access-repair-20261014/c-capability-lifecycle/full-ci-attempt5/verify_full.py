#!/usr/bin/env python3
"""Versioned complete offline acceptance. Historical gates are never patched.

All production root/prepare/install/recovery actions remain forbidden. Tests use
disposable, protected local fixtures and explicit synthetic private boundaries.
"""
import argparse
import ast
import copy
import gzip
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest

HERE=pathlib.Path(__file__).resolve().parent
CANDIDATE=HERE.parent
ROOT=CANDIDATE.parents[2]
PREFIX='evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/'
BASELINE='evidence/p2-epoch7-access-repair-20261014/b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz'
HISTORICAL='0bd83e6fb418ae04d4351b1de7eaf11a0325dd80'
KIT_SOURCE='0bd83e6fb418ae04d4351b1de7eaf11a0325dd80'
KIT_TREE='5d790e58f9f644985fdf063dfc1466eb9b28e66f'
KIT_SHA='42d6d98f0fb1b1436f348a4ab70b2a9d91dd02e1ad085f49ecb2eb5c096d4465'
SUITES=(('collector',26),('preflight',11),('routing',27),('factory',26),
        ('census',12),('transactions',55),('lifecycle',40),('preparation',31),
        ('delivery',47),('builder',50))
NAMES={'collector':'tests/test_predecessor_snapshot.py',
       'preflight':'tests/test_successor_preflight_integration.py',
       'routing':'tests/test_successor_resource_routing.py',
       'factory':'tests/test_successor_approval_factory_entry.py',
       'census':'tests/test_census_race_classification.py',
       'transactions':'tests/test_successor_transactions.py',
       'lifecycle':'tests/test_capability_lifecycle.py',
       'preparation':'preparation/test_prepare_successor.py',
       'delivery':'delivery/test_successor_delivery.py',
       'builder':'build/test_build_claim_successor_kit.py'}

def need(value,code):
    if not value:raise ValueError('P2_FULL_V2_'+code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def packed(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode('ascii')
def path_name(value):
    need(type(value) is str and re.fullmatch(r'[A-Za-z0-9_.\-/]+',value) and not value.startswith('/') and
         all(p not in ('','.','..','__pycache__') for p in value.split('/')),'PATH')
    return value
def file_record(raw,row):
    need(type(row) is dict and set(row)=={'bytes','sha256'},'FILE_SCHEMA')
    need(type(row['bytes']) is int and 0<row['bytes']<=33554432 and type(row['sha256']) is str and
         re.fullmatch('[0-9a-f]{64}',row['sha256']),'FILE_PIN')
    need(type(raw) is bytes and len(raw)==row['bytes'] and sha(raw)==row['sha256'],'FILE_BYTES')
def identity(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{40}',value) and value!='0'*40,'IDENTITY')
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def git(*args):
    return subprocess.check_output(['git','-c','safe.directory=*','-C',str(ROOT)]+list(args))
def exact_terminal(value,count):
    need(type(value) is dict and value.get('state')=='PASS' and type(value.get('tests')) is int and
         value['tests']==count and all(type(value.get(k)) is int and value[k]==0
                                     for k in ('errors','failures','skips')),'TEST_TERMINAL')

def inventory(root,records):
    expected=set(records)
    found=set()
    candidate=root/PREFIX
    for path in candidate.rglob('*'):
        relative=path.relative_to(root).as_posix();info=path.lstat()
        need(not stat.S_ISLNK(info.st_mode),'SOURCE_SYMLINK')
        if stat.S_ISDIR(info.st_mode):continue
        need(stat.S_ISREG(info.st_mode) and info.st_nlink==1,'SOURCE_TYPE')
        if relative==PREFIX+'full-ci-attempt5/INPUTS.json':continue
        found.add(relative)
    need(found=={p for p in expected if p.startswith(PREFIX)},'SOURCE_ALLOWLIST')
    for relative,row in records.items():
        path=root/path_name(relative);info=path.lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and not info.st_mode&0o022,'SOURCE_AUTHORITY')
        file_record(path.read_bytes(),row)

def verify_inputs():
    raw=(HERE/'INPUTS.json').read_bytes();manifest=json.loads(raw.decode('ascii'))
    need(type(manifest) is dict and set(manifest)=={'schema','base_commit','files','historical_files','suite_counts'},'INPUT_SCHEMA')
    need(type(manifest['schema']) is int and manifest['schema']==2,'INPUT_SCHEMA')
    identity(manifest['base_commit']);need(manifest['suite_counts']==dict(SUITES),'SUITE_COUNTS')
    need(manifest['base_commit']=='15064657c443a42ab705be165e8757fc08c383cc','BASE_VERSION')
    external={BASELINE,'docs/development/P2_RETAINED_RECOVERY.md',
        'docs/DEVELOPMENT_EXECUTION_AND_FEEDBACK_RULES_20261012.md','.github/workflows/p2-attempt5-full-ci.yml','.github/workflows/p2-r14-versioned-full-ci.yml',
        '.github/workflows/p2-capability-lifecycle.yml','.github/workflows/p2-claim-lifecycle-v2-ci.yml',
        'tests/test_p2_capability_lifecycle.py','tests/test_p2_capability_lifecycle_contract.py',
        'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tests/approval/test_epoch7_approval.py'}
    need({path for path in manifest['files'] if not path.startswith(PREFIX)}==external,'EXTERNAL_DEPENDENCY_CLOSURE')
    historical=set(git('ls-tree','-r','--name-only',HISTORICAL,'--',PREFIX).decode('ascii').splitlines())
    need(set(manifest['historical_files'])==historical,'HISTORICAL_SOURCE_CLOSURE')
    for path in ('tests/test_p2_capability_lifecycle.py','tests/test_p2_capability_lifecycle_contract.py',
                 '.github/workflows/p2-capability-lifecycle.yml',
                 PREFIX+'preparation/test_prepare_successor.py',PREFIX+'delivery/test_successor_delivery.py'):
        need((ROOT/path).read_bytes()==git('show',HISTORICAL+':'+path),'HISTORICAL_ASSERTION_CHANGED')
    head=git('rev-parse','HEAD').decode().strip();tree=git('rev-parse','HEAD^{tree}').decode().strip()
    identity(head);identity(tree)
    expected=os.environ.get('GITHUB_SHA')
    if expected is not None:need(head==expected,'EVENT_HEAD')
    need(git('show','HEAD:'+PREFIX+'full-ci-attempt5/INPUTS.json')==raw,'MANIFEST_NOT_HEAD')
    inventory(ROOT,manifest['files'])
    for path,row in manifest['files'].items():file_record(git('show','HEAD:'+path),row)
    # Historical assertions and both original source files are independently pinned.
    for path,row in manifest['historical_files'].items():file_record(git('show',HISTORICAL+':'+path),row)
    return manifest,head,tree,sha(raw)

def verify_dependencies(candidate,baseline_raw,expected):
    builder=load(candidate/'build/build_claim_successor_kit.py','full_v2_builder')
    old_files,old_manifest=builder.authenticate_archive(baseline_raw)
    delivery=load(candidate/'delivery/epoch7_prepare_successor_delivery.py','full_v2_delivery')
    prep=(candidate/'preparation/epoch7_prepare_successor.py').read_bytes()
    delivery.preparer({'epoch7_prepare_successor.py':prep})
    need(git('show',delivery.PUBLICATION_COMMIT+':'+PREFIX+'preparation/epoch7_prepare_successor.py')==prep,'PREPARER_PUBLICATION')
    raw=(candidate/'published-v2/epoch7-kit-claim-lifecycle-0bd83e6f.tar.gz').read_bytes()
    need(len(raw)==1074452 and sha(raw)==KIT_SHA,'PUBLISHED_KIT')
    extractor,entry,files=delivery.compiler_inputs(raw)
    manifest=json.loads(files['recovery-kit-manifest.json'].decode('ascii'))
    need(manifest['kit_source_commit']==KIT_SOURCE and manifest['kit_source_tree']==KIT_TREE,'KIT_IDENTITY')
    builder.validate_module_closure(manifest,files)
    builder.validate_test_suites(manifest,files)
    builder.validate_business_invariants(old_files,files)
    mapping=(candidate/'build/OVERLAY_INPUTS.json').read_bytes()
    sources={row['source']:(candidate/row['source']).read_bytes() for row in json.loads(mapping.decode('ascii'))['files']}
    # Check every compiler input against its actual immutable source Git object.
    for name,body in sources.items():need(git('show',KIT_SOURCE+':'+PREFIX+name)==body,'KIT_SOURCE_OBJECT')
    need(git('rev-parse',KIT_SOURCE+'^{tree}').decode().strip()==KIT_TREE,'KIT_SOURCE_TREE')
    one,metadata=builder.compile_artifact(baseline_raw,mapping,sources,KIT_SOURCE,KIT_TREE)
    two,second=builder.compile_artifact(baseline_raw,mapping,sources,KIT_SOURCE,KIT_TREE)
    need(one==two and metadata==second,'DETERMINISM')
    rebuilt,_=extractor.inspect_archive(one,sha(one),delivery.COMPILER_ENTRY_SHA,delivery.COMPILER_MANIFEST_SHA)
    need(rebuilt==files and metadata['output']['files']=={name:sha(body) for name,body in files.items()},'EXACT_257_FILE_CLOSURE')
    normalized=copy.deepcopy(metadata)
    for field in ('archive_bytes','archive_sha256'):normalized['output'][field]=expected['output'][field]
    need(normalized==expected,'COMPLETE_BUILD_METADATA')
    need(expected['output']['archive_bytes']==len(raw) and expected['output']['archive_sha256']==sha(raw),'PUBLISHED_BUILD_RESULT')
    return old_files,{'archive_sha256':KIT_SHA,'rebuilt_archive_sha256':sha(one),
        'source_commit':KIT_SOURCE,'source_tree':KIT_TREE,'manifest_sha256':delivery.COMPILER_MANIFEST_SHA,
        'files':len(files),'pins':len(manifest['files']),'runtime_payloads':107,'business_phases':16,
        'modules':len(manifest['modules']),'metadata_sha256':sha(packed(expected))}

def write_fixture(path,raw):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with open(str(path),'xb') as stream:stream.write(raw)
    # Public test-source copies match the historical harness's0644 layout;
    # isolated routing suites overlay their own copies. Real Kit extraction
    # and E2E readers continue to enforce the original0444 files.
    path.chmod(0o644)

def _suite(root,name,kind):
    need(kind in ('current','historical') and name in NAMES,'SUITE')
    import ctypes,uuid
    need(ctypes.CDLL(None).getpid()==os.getpid() and len(uuid.uuid4().bytes)==16,'NATIVE_IMPORT')
    kit=root/'baseline'
    os.environ['CLAIM_SUCCESSOR_BASELINE_ARCHIVE']=str(root/'baseline.tar.gz')
    os.environ['EPOCH7_SUCCESSOR_PREPARATION']=str(root/'preparation')
    paths=[root/'tests',root/'kit-overlay/helpers',kit/'helpers',kit/'xuanjun-p2-package/stage1',kit/'xuanjun-p2-package/scripts']
    paths.extend(sorted(p for p in (kit/'tests').iterdir() if p.is_dir()))
    sys.path[:0]=[str(path) for path in paths]
    relative=NAMES[name]
    if kind=='current' and name in ('preparation','delivery'):relative=relative[:-3]+'_v2.py'
    path=root/relative;module=types.ModuleType('full_v2_'+kind+'_'+name);module.__file__=str(path)
    sys.modules[module.__name__]=module;exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
    wanted=dict(SUITES)[name]
    if name in ('routing','transactions','lifecycle'):
        original=unittest.TextTestRunner;results=[]
        class RecordingRunner(original):
            def run(self,suite):
                need(suite.countTestCases()==wanted,'TEST_COUNT');result=super(RecordingRunner,self).run(suite);results.append(result);return result
        unittest.TextTestRunner=RecordingRunner
        try:code=(module.original.run_isolated(extra_suite_factory=module.lifecycle_suite,include_existing=False)
                  if name=='lifecycle' else module.run_isolated())
        finally:unittest.TextTestRunner=original
        need(code==0 and len(results)==1,'ISOLATED_SUITE');result=results[0]
    else:
        suite=unittest.defaultTestLoader.loadTestsFromModule(module)
        need(suite.countTestCases()==wanted,'TEST_COUNT');result=unittest.TextTestRunner(verbosity=2).run(suite)
    row={'state':'PASS' if result.wasSuccessful() else 'HOLD','tests':result.testsRun,
         'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped),'suite':name,'version':kind}
    exact_terminal(row,wanted);print('FULL_V2_SUITE='+json.dumps(row,sort_keys=True))

def run(output):
    manifest,head,tree,manifest_sha=verify_inputs()
    output.mkdir(mode=0o700)
    legacy=load(ROOT/'tests/test_p2_capability_lifecycle.py','historical_gate_utilities')
    baseline_raw=(ROOT/BASELINE).read_bytes()
    expected=json.loads((HERE/'EXPECTED_BUILD_RESULT.json').read_text())
    old_files,dependencies=verify_dependencies(CANDIDATE,baseline_raw,expected)
    results=[];logs={}
    def invoke(label,argv,cwd,count,prefix=None,limit=legacy.MAX_ARTIFACT_FILE):
        code,raw=legacy.run_child(argv,cwd,300,file_limit=limit)
        need(len(raw)<=2097152,'LOG_BOUND')
        with open(str(output/(label+'.log')),'xb') as stream:stream.write(raw)
        logs[label]={'bytes':len(raw),'sha256':sha(raw)}
        print(raw.decode('utf-8','replace'),flush=True)
        need(code==0,'CHILD_'+label.upper())
        if prefix:
            rows=[json.loads(line[len(prefix):].decode('ascii')) for line in raw.splitlines() if line.startswith(prefix)]
            need(len(rows)==1,'TERMINAL_COUNT');exact_terminal(rows[0],count)
            row=dict(rows[0]);row.setdefault('suite',label);results.append(row)
        else:
            need(re.search(rb'Ran '+str(count).encode()+rb' tests? in ',raw) is not None and b'\nOK\n' in raw,'UNIT_RESULT')
            need(b'skipped=' not in raw and b'FAILED' not in raw,'UNIT_SKIP_OR_FAILURE')
            results.append({'suite':label,'state':'PASS','tests':count,'errors':0,'failures':0,'skips':0})
    with tempfile.TemporaryDirectory(prefix='p2-versioned-full-',dir='/') as folder:
        temp=pathlib.Path(folder);scratch=temp/'tmp';scratch.mkdir(mode=0o700)
        write_fixture(temp/'b-resource-aggregate-fix/artifact/epoch7-kit-resourcebind.tar.gz',baseline_raw)
        write_fixture(temp/'b-resource-aggregate-fix-candidate/artifact/epoch7-kit-resourcebind.tar.gz',baseline_raw)
        os.environ['TMPDIR']=str(scratch);os.environ['RUNNER_TEMP']=str(scratch)
        for kind in ('current','historical'):
            candidate=temp/kind
            shutil.copytree(str(CANDIDATE),str(candidate),ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            write_fixture(candidate/'baseline.tar.gz',baseline_raw)
            for name,raw in old_files.items():write_fixture(candidate/'baseline'/name,raw)
            if kind=='historical':
                for path,row in manifest['historical_files'].items():
                    if path.startswith(PREFIX):
                        target=candidate/path[len(PREFIX):]
                        # The historical fixture is a separate namespace, not a repair.
                        target.unlink();write_fixture(target,git('show',HISTORICAL+':'+path))
            for name,count in SUITES:
                invoke(kind+'-'+name,[sys.executable,'-I','-B','-S',str(HERE/'verify_full.py'),'--suite',str(candidate),name,kind],
                       candidate,count,b'FULL_V2_SUITE=')
        invoke('historical-adapter-contract',[sys.executable,'-I','-B','-S',str(ROOT/'tests/test_p2_capability_lifecycle_contract.py'),'-v'],ROOT,55)
        approval=temp/'current/baseline/tests/approval/test_epoch7_approval.py'
        # Preserve all18 original archived assertions, then separately exercise
        # the20 current assertions against the actual new approval helper.
        code="import sys,runpy;sys.path.insert(0,"+repr(str(temp/'current/baseline/helpers'))+");runpy.run_path("+repr(str(approval))+",run_name='__main__')"
        invoke('historical-approval',[sys.executable,'-I','-B','-S','-c',code],ROOT,18)
        approval=ROOT/'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/tests/approval/test_epoch7_approval.py'
        code=("import sys,runpy,hashlib;sys.path[:0]="+
              repr([str(temp/'current/kit-overlay/helpers'),str(temp/'current/baseline/helpers')])+
              ";import epoch7_approval;assert hashlib.sha256(open(epoch7_approval.__file__,'rb').read()).hexdigest()=="+
              repr('0587f0e1f81e7f70ab098a13b1e0a3b47cad40344e4237128716953f2ad34f55')+
              ";runpy.run_path("+repr(str(approval))+",run_name='__main__')")
        invoke('current-approval-authors',[sys.executable,'-I','-B','-S','-c',code],ROOT,20)
        invoke('gate-contract',[sys.executable,'-I','-B','-S',str(HERE/'test_full_gate.py'),'-v'],ROOT,15,b'FULL_V2_CONTRACT=')
        invoke('delivery-e2e',[sys.executable,'-I','-B','-S',str(temp/'current/delivery/run_r14_ci.py')],ROOT,17,b'R14_E2E_TERMINAL=')
        argv=[sys.executable,'-I','-B','-S','-c',"import sys,unittest;sys.path.insert(0,"+repr(str(CANDIDATE/'attempt5/original'))+");r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover("+repr(str(CANDIDATE/'attempt5/original'))+"));sys.exit(not r.wasSuccessful())"]
        invoke('attempt5-original',argv,ROOT,29)
        for filename,count in (('test_receipt_provider.py',10),('test_authority_store.py',21),('test_versioned_kit.py',6),('test_issuer_service.py',18),('test_authorization.py',9),('test_approved_config.py',9)):
            invoke('attempt5-'+filename,[sys.executable,'-I','-B','-S',str(CANDIDATE/'attempt5'/filename),'-v'],ROOT,count)
        invoke('attempt5-native',[sys.executable,'-I','-B','-S',str(CANDIDATE/'attempt5/test_native_recovery.py'),str(temp/'current')],ROOT,44)
        builder=load(CANDIDATE/'attempt5/build_kit.py','attempt5_kit_builder')
        kit,kit_manifest=builder.build(head,tree)
        kit2,manifest2=builder.build(head,tree)
        need(kit==kit2 and kit_manifest==manifest2,'ATTEMPT5_KIT_DETERMINISM')
        (output/'attempt5-kit.tar.gz').write_bytes(kit)
        (output/'attempt5-manifest.json').write_bytes(builder.canonical(kit_manifest))
        dependencies['attempt5']={'kit_sha256':sha(kit),'manifest_sha256':sha(builder.canonical(kit_manifest)),
                                 'files':len(kit_manifest['files'])+1,'source_commit':head,'source_tree':tree}
    inventory(ROOT,manifest['files'])
    need(git('rev-parse','HEAD').decode().strip()==head,'HEAD_DRIFT')
    for path,row in manifest['files'].items():file_record(git('show','HEAD:'+path),row)
    need(git('show','HEAD:'+PREFIX+'full-ci-attempt5/INPUTS.json')==(HERE/'INPUTS.json').read_bytes(),'MANIFEST_DRIFT')
    total=sum(row['tests'] for row in results);need(total==921,'TOTAL_TESTS')
    report={'schema':2,'state':'PASS','source_commit':head,'source_tree':tree,'python':sys.version,
        'input_manifest_sha256':manifest_sha,'files':manifest['files'],'dependencies':dependencies,
        'tests':total,'errors':0,'failures':0,'skips':0,'suites':results,'logs':logs,
        'historical_outer_ci':'PRESERVED_FAILURE_NOT_RECLASSIFIED','historical_fixed_commit':HISTORICAL,
        'production_resume':'NOT_EXECUTED','install_admission':'NOT_GRANTED','P2_RELEASE':'HOLD'}
    with open(str(output/'FULL_RESULT.json'),'xb') as stream:stream.write(packed(report))
    contents={path:str(path.relative_to(output)) for path in output.iterdir() if path.is_file()}
    expanded=io.BytesIO()
    with tarfile.open(fileobj=expanded,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        selected={'evidence/'+name:path.read_bytes() for path,name in contents.items()}
        selected.update({'source/'+name:(ROOT/name).read_bytes() for name in manifest['files']})
        selected['source/'+PREFIX+'full-ci-attempt5/INPUTS.json']=(HERE/'INPUTS.json').read_bytes()
        for name,raw in sorted(selected.items()):
            row=tarfile.TarInfo(name);row.size=len(raw);row.mode=0o444;archive.addfile(row,io.BytesIO(raw))
    compressed=io.BytesIO()
    with gzip.GzipFile(fileobj=compressed,mode='wb',mtime=0) as stream:stream.write(expanded.getvalue())
    raw=compressed.getvalue()
    with open(str(output/'full-evidence.tar.gz'),'xb') as stream:stream.write(raw)
    with open(str(output/'full-evidence.tar.gz.sha256'),'x') as stream:stream.write(sha(raw)+'  full-evidence.tar.gz\n')
    print('VERSIONED_FULL_CI='+json.dumps({'state':'PASS','tests':921,'errors':0,'failures':0,'skips':0,
          'source_commit':head,'source_tree':tree,'artifact_sha256':sha(raw),'input_manifest_sha256':manifest_sha},sort_keys=True))

def main():
    if len(sys.argv)==5 and sys.argv[1]=='--suite':
        _suite(pathlib.Path(sys.argv[2]),sys.argv[3],sys.argv[4]);return 0
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    run(pathlib.Path(args.output).resolve());return 0
if __name__=='__main__':sys.exit(main())
