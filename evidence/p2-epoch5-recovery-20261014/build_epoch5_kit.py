"""Offline deterministic packaging. No host installation or review authority."""
import gzip,hashlib,io,json,os,pathlib,shutil,tarfile
from epoch5_recovery_entry import HELPERS,MANIFEST

def sha(raw):return hashlib.sha256(raw).hexdigest()
def build(source,reviewed,runtime,output):
 source,reviewed,runtime,output=map(pathlib.Path,(source,reviewed,runtime,output))
 if output.exists():raise ValueError('KIT_OUTPUT_EXISTS')
 output.mkdir(mode=0o700)
 root=output/'epoch5-recovery-candidate';root.mkdir(mode=0o700)
 for name in ('helpers','tests'):(root/name).mkdir(mode=0o700)
 helpers={};tests={}
 for name in sorted(HELPERS):
  path=source/name if (source/name).exists() else reviewed/name
  raw=path.read_bytes();compile(raw,name,'exec');helpers[name]=sha(raw)
  (root/'helpers'/name).write_bytes(raw)
 for path in sorted(source.glob('test_*.py')):
  raw=path.read_bytes();compile(raw,path.name,'exec');tests[path.name]=sha(raw)
  (root/'tests'/path.name).write_bytes(raw)
 shutil.copytree(str(runtime),str(root/'xuanjun-p2-package'))
 manifest_raw=(runtime/'deploy/integration-manifest.json').read_bytes()
 if sha(manifest_raw)!=MANIFEST:raise ValueError('KIT_RUNTIME_MANIFEST')
 manifest=json.loads(manifest_raw.decode())
 for name,wanted in manifest['files'].items():
  if sha((root/'xuanjun-p2-package'/name).read_bytes())!=wanted:raise ValueError('KIT_RUNTIME_FILE')
 entry=(source/'epoch5_recovery_entry.py').read_bytes();(root/'epoch5_recovery_entry.py').write_bytes(entry)
 value={'schema':1,'runtime_manifest_sha256':MANIFEST,'helper_files':helpers,'test_files':tests,'entry_sha256':sha(entry)}
 raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode();(root/'recovery-kit-manifest.json').write_bytes(raw)
 archive=output/'epoch5-recovery-kit.tar.gz'
 with archive.open('xb') as stream:
  with gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as gz:
   with tarfile.open(fileobj=gz,mode='w',format=tarfile.PAX_FORMAT) as tar:
    for path in [root]+sorted(root.rglob('*')):
     name=path.relative_to(output).as_posix();info=tarfile.TarInfo(name)
     info.uid=info.gid=0;info.uname=info.gname='root';info.mtime=0
     if path.is_symlink():raise ValueError('KIT_SYMLINK')
     if path.is_dir():info.type=tarfile.DIRTYPE;info.mode=0o700 if path in (root,root/'helpers',root/'tests') else 0o755;tar.addfile(info)
     else:
      data=path.read_bytes();info.size=len(data);info.mode=0o444;tar.addfile(info,io.BytesIO(data))
 receipt={'schema':1,'archive_sha256':sha(archive.read_bytes()),'entry_sha256':sha(entry),
          'kit_manifest_sha256':sha(raw),'runtime_manifest_sha256':MANIFEST,
          'helpers':len(helpers),'test_modules':len(tests),'production_execution':'NOT_RUN',
          'independent_review':'PENDING'}
 (output/'kit-receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
 return receipt
