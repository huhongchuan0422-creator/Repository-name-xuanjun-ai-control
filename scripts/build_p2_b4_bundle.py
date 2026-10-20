"""Fixed B4 source package, including untouched B3 application/transport assets."""
import base64,gzip,hashlib,io,json,tarfile
from pathlib import Path
PREFIX='evidence/p2-epoch7-access-repair-20261014/runtime'
EXTRA=('production/p2_runtime/__init__.py','production/p2_install/initialize.py',
 'production/p2_install/b4_sandbox.py','scripts/p2_b3_owner_finalize_20261020.py',
 'scripts/p2_b4_owner_sandbox_20261020.py','scripts/p2_b4_container_roundtrip.py','docs/p2-b4-20261020/request.json')
def build(repo,request_override=None):
    repo=Path(repo);files={str(p.relative_to(repo)):p.read_bytes() for p in (repo/PREFIX).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    files.update({p:(repo/p).read_bytes() for p in EXTRA})
    if request_override is not None:files[EXTRA[-1]]=json.dumps(request_override,sort_keys=True,separators=(',',':')).encode('ascii')
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as archive:
        for name,raw in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o444;info.mtime=0;archive.addfile(info,io.BytesIO(raw))
    compressed=io.BytesIO()
    with gzip.GzipFile(fileobj=compressed,mode='wb',mtime=0,filename='') as gz:gz.write(buffer.getvalue())
    raw=compressed.getvalue()
    return json.dumps({'schema':1,'tar_bytes':len(raw),'tar_sha256':hashlib.sha256(raw).hexdigest(),
      'tar_b64':base64.b64encode(raw).decode('ascii'),'files':{p:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for p,v in sorted(files.items())}},sort_keys=True,separators=(',',':')).encode('ascii')
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args();repo=Path(__file__).resolve().parents[1];out=Path(args.output);out.mkdir()
    names=('p2-b4-bundle.json','p2_b4_owner_sandbox_20261020.py')
    (out/names[0]).write_bytes(build(repo));(out/names[1]).write_bytes((repo/'scripts'/names[1]).read_bytes())
    (out/'SHA256SUMS').write_text(''.join(hashlib.sha256((out/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in names))
