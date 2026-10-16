"""Deterministic snapshot package for the existing immutable static publisher."""
import argparse
import gzip
import io
import json
from pathlib import Path
import tarfile
from scripts.pr122_showcase import need,canonical,sha

def tar_bytes(files,prefix=''):
    stream=io.BytesIO()
    with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as gz,tarfile.open(fileobj=gz,mode='w') as archive:
        for name,raw in sorted(files.items()):
            m=tarfile.TarInfo(prefix+name);m.size=len(raw);m.mode=0o644;archive.addfile(m,io.BytesIO(raw))
    return stream.getvalue()

def build(public,output,preview=False):
    public=Path(public);declared=json.loads((public/'SHOWCASE_MANIFEST.json').read_text())
    need(declared['preview_only'] is preview,'PREVIEW_SCOPE_MISMATCH')
    files={}
    for row in declared['files']:
        path=Path(row['path']);need(not path.is_absolute() and '..' not in path.parts and path.parts[0]=='showcase','PUBLIC_PATH')
        target=public/path;need(not target.is_symlink(),'PUBLIC_SYMLINK');raw=target.read_bytes()
        need(len(raw)==row['size'] and sha(raw)==row['sha256'],'PUBLIC_FILE_CHANGED');files[row['path']]=raw
    need(0<len(files)<=5000 and sum(map(len,files.values()))<=100000000,'PUBLIC_SIZE_LIMIT')
    source=tar_bytes(files,'package/public/')
    candidate={'schema_version':2,'files':[{'path':name,'size':len(raw),'sha256':sha(raw),'mode':420,'uid':0,'gid':0} for name,raw in sorted(files.items())]}
    pin={'schema_version':2,'source_archive_sha256':sha(source),'source_archive_size':len(source),'overlay_baselines':{}}
    bundle={'bundle/candidate-manifest.json':canonical(candidate),'bundle/source-pin.json':canonical(pin),'source.tar.gz':source,
            'PUBLICATION.json':canonical({'schema':1,'preview_only':preview,'scope':'SHOWCASE_STATIC_ONLY','public_file_count':len(files)})}
    manifest={'schema_version':2,'files':[{'path':name.removeprefix('bundle/'),'size':len(raw),'sha256':sha(raw)} for name,raw in sorted(bundle.items()) if name.startswith('bundle/')]}
    bundle['bundle/PACKAGE_MANIFEST.json']=canonical(manifest)
    package=tar_bytes(bundle,'showcase-release/');need(len(package)<=16000000,'PACKAGE_SIZE_LIMIT')
    Path(output).write_bytes(package)
    return {'tar_sha256':sha(package),'package_manifest_sha256':sha(bundle['bundle/PACKAGE_MANIFEST.json']),'preview_only':preview,'file_count':len(files),'production_changes':0}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--public',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--preview',action='store_true')
    a=p.parse_args();print(json.dumps(build(a.public,a.output,a.preview),sort_keys=True))
