"""Additive Attempt5 candidate Kit; inherited payload bytes remain unchanged.

No production loader/permission is enabled. The separate manifest records the
new source Commit/Tree and complete candidate closure. Legacy loader + old Kit
stay byte-identical, and the five-attempt runtime has a separate import scope.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent/'published-v2/epoch7-kit-claim-lifecycle-0bd83e6f.tar.gz'
BASE_SHA='42d6d98f0fb1b1436f348a4ab70b2a9d91dd02e1ad085f49ecb2eb5c096d4465'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode('ascii')
def build(commit,tree):
    raw=BASE.read_bytes();assert sha(raw)==BASE_SHA
    files={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        for row in archive.getmembers():
            if row.isdir():continue
            assert row.isfile() and '/' in row.name
            name=row.name.split('/',1)[1]
            assert name not in files and '..' not in name.split('/')
            files['legacy/'+name]=archive.extractfile(row).read()
    assert len(files)==257
    inherited={name:sha(body) for name,body in files.items()}
    for directory in ('runtime','original'):
        for path in sorted((HERE/directory).glob('*.py')):
            name='attempt5/'+directory+'/'+path.name
            assert name not in files;files[name]=path.read_bytes()
    manifest={'schema':1,'kind':'P2_ATTEMPT5_CANDIDATE_V1','source_commit':commit,'source_tree':tree,
              'legacy_kit_sha256':BASE_SHA,'inherited_files':inherited,
              'files':{name:sha(body) for name,body in files.items()},
              'max_attempts':5,'permit_mode':'ONE_PERMIT_MAX_5_ATTEMPTS','cycle_entry':'permit_cycle.PermitCycle',
              'new_approval_per_retry':False,'production_ready':False,'install_permit':'NOT_ISSUED',
              'trusted_provider':'EXTERNAL_PINNED_ISSUER_AND_TRANSPORT_REQUIRED',
              'release':'HOLD'}
    files['attempt5-manifest.json']=canonical(manifest)
    out=io.BytesIO()
    with gzip.GzipFile(fileobj=out,mode='wb',mtime=0,filename='') as compressed:
        with tarfile.open(fileobj=compressed,mode='w',format=tarfile.USTAR_FORMAT) as archive:
            for name,body in sorted(files.items()):
                row=tarfile.TarInfo('epoch7-attempt5-candidate-v1/'+name)
                row.size=len(body);row.mode=0o444;archive.addfile(row,io.BytesIO(body))
    return out.getvalue(),manifest
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    git=lambda value:subprocess.check_output(['git','-c','safe.directory=*','-C',str(ROOT),'rev-parse',value]).decode().strip()
    raw,manifest=build(git('HEAD'),git('HEAD^{tree}'))
    output=Path(args.output);output.mkdir(mode=0o700)
    (output/'kit.tar.gz').write_bytes(raw);(output/'attempt5-manifest.json').write_bytes(canonical(manifest))
    (output/'SHA256SUMS').write_text(sha(raw)+'  kit.tar.gz\n'+sha(canonical(manifest))+'  attempt5-manifest.json\n')
