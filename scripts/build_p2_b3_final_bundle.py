"""Deterministic source bundle; relative checksum filenames; no installation."""
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

PREFIX='evidence/p2-epoch7-access-repair-20261014/runtime'
EXTRA=('production/p2_install/initialize.py','production/p2_install/b3_contracts.py',
       'production/p2_install/b3_ledger.py','production/p2_install/cp08_probe.py',
       'production/p2_install/cp08_evidence.py','scripts/p2_b3_owner_finalize_20261020.py',
       'docs/p2-b3-ledger-20261020/request.json')


def build(repo, request_override=None):
    repo=Path(repo)
    files={str(p.relative_to(repo)):p.read_bytes() for p in (repo/PREFIX).rglob('*') if p.is_file()}
    files.update({p:(repo/p).read_bytes() for p in EXTRA})
    if request_override is not None:
        files[EXTRA[-1]]=json.dumps(request_override,sort_keys=True,separators=(',',':')).encode('ascii')
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as tar:
        for name,raw in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o444;info.mtime=0
            tar.addfile(info,io.BytesIO(raw))
    compressed=io.BytesIO()
    with gzip.GzipFile(fileobj=compressed,mode='wb',mtime=0,filename='') as gz:gz.write(buffer.getvalue())
    archive=compressed.getvalue()
    packet={'schema':1,'tar_bytes':len(archive),'tar_sha256':hashlib.sha256(archive).hexdigest(),
            'tar_b64':base64.b64encode(archive).decode('ascii'),
            'files':{p:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for p,raw in sorted(files.items())}}
    return json.dumps(packet,sort_keys=True,separators=(',',':')).encode('ascii')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    output=Path(args.output);output.mkdir()
    raw=build(Path(__file__).resolve().parents[1]);name='p2-b3-final-bundle.json'
    (output/name).write_bytes(raw)
    wrapper=Path(__file__).resolve().parent/'p2_b3_owner_finalize_20261020.py'
    (output/wrapper.name).write_bytes(wrapper.read_bytes())
    sums=''.join(hashlib.sha256((output/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in (name,wrapper.name))
    (output/'SHA256SUMS').write_text(sums)
