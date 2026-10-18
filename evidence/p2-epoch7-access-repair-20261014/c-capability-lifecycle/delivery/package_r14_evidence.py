#!/usr/bin/env python3
"""Package public exact-checkout source and CI evidence; no host effects."""
import argparse
import gzip
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tarfile

PREFIX='evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/'
PATHS=('.github/workflows/p2-capability-lifecycle.yml',
       '.github/workflows/p2-claim-lifecycle-v2-ci.yml')+tuple(PREFIX+name for name in (
           'preparation/epoch7_prepare_successor.py',
           'delivery/epoch7_prepare_successor_delivery.py',
           'delivery/extract_epoch7_successor_kit.py',
           'delivery/render_memory_launcher.py','delivery/run_r14_ci.py',
           'delivery/test_r14_delivery.py','delivery/package_r14_evidence.py',
           'delivery/R14_INTEGRATION.md',
           'published-v2/epoch7-kit-claim-lifecycle-0bd83e6f.tar.gz'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def git(*args):return subprocess.check_output(['git','-c','safe.directory=*']+list(args)).decode('ascii').strip()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-log',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    root=pathlib.Path(__file__).resolve().parents[4]
    files={}
    for relative in PATHS:
        raw=(root/relative).read_bytes()
        exact=subprocess.check_output(['git','-c','safe.directory=*','-C',str(root),'show','HEAD:'+relative])
        if raw!=exact:raise ValueError('SOURCE_DIFFERS_FROM_HEAD')
        files[relative]=raw
    log=pathlib.Path(args.test_log).read_bytes()
    prefix=b'R14_E2E_TERMINAL='
    terminals=[json.loads(line[len(prefix):].decode('ascii')) for line in log.splitlines() if line.startswith(prefix)]
    expected={'schema':1,'state':'PASS','tests':17,'errors':0,'failures':0,'skips':0,
              'production_resume':'NOT_EXECUTED','install_admission':'NOT_GRANTED'}
    if terminals!=[expected]:raise ValueError('EXACT_E2E_RESULT_REQUIRED')
    files['CI_E2E.log']=log
    manifest={'schema':1,'source_commit':git('-C',str(root),'rev-parse','HEAD'),
        'source_tree':git('-C',str(root),'rev-parse','HEAD^{tree}'),'python':sys.version,
        'test_result':expected,'files':{name:{'bytes':len(raw),'sha256':sha(raw)} for name,raw in sorted(files.items())},
        'production_resume':'NOT_EXECUTED','install_admission':'NOT_GRANTED','P2_RELEASE':'HOLD'}
    files['SOURCE_AND_TEST_MANIFEST.json']=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode('ascii')
    expanded=io.BytesIO()
    with tarfile.open(fileobj=expanded,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,raw in sorted(files.items()):
            row=tarfile.TarInfo(name);row.size=len(raw);row.mode=0o444
            archive.addfile(row,io.BytesIO(raw))
    compressed=io.BytesIO()
    with gzip.GzipFile(fileobj=compressed,mode='wb',mtime=0) as stream:stream.write(expanded.getvalue())
    raw=compressed.getvalue();output=pathlib.Path(args.output)
    with open(str(output),'xb') as stream:stream.write(raw)
    with open(str(output)+'.sha256','x') as stream:stream.write(sha(raw)+'  '+output.name+'\n')
    print(json.dumps({'source_commit':manifest['source_commit'],'source_tree':manifest['source_tree'],
                      'bytes':len(raw),'artifact_sha256':sha(raw),'tests':17,'state':'PASS'},sort_keys=True))
    return 0
if __name__=='__main__':sys.exit(main())
