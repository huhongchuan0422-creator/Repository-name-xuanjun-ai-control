"""Read public static baseline and configuration hashes only; no root operations."""
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tarfile
from scripts.pr122_site_hub_host_preflight import nginx_source

ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/var/www/wenwenwenyiyiyi.work')
EXPECTED=BASE/'releases/pr122-hub-experience-ca7ab933-r2'
SHA='b66eba8c958b10925064053f41dc575a6eb301616bc414d139cdddd98a2e7cb3'
def sha(b):return hashlib.sha256(b).hexdigest()
def need(ok,why):
    if not ok:raise ValueError(why)
def main():
    signal.alarm(60);need(os.uname().nodename=='iZvt5t8tlrm8oiZ','WRONG_HOST')
    need(os.geteuid()!=0,'UNPRIVILEGED_OBSERVATION_ONLY')
    raw=(ROOT/'evidence/pr122-site-hub-experience/PR122_SITE_HUB_REVIEW_ONLY.tar.gz').read_bytes();need(sha(raw)==SHA,'BASE_PACKAGE_HASH')
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as a:expected=json.loads(a.extractfile('pr122-site-hub/candidate-manifest.json').read())
    wanted={x['path']:{'size':x['size'],'sha256':x['sha256']} for x in expected['files']}
    pointer=BASE/'current';start=pointer.lstat();need(pointer.is_symlink() and os.readlink(pointer)==str(EXPECTED),'CURRENT_DRIFT')
    public=EXPECTED/'public';identity=public.stat();found={};total=0
    for directory,dirs,names in os.walk(public,followlinks=False):
        for name in dirs:need(not (Path(directory)/name).is_symlink(),'PUBLIC_DIR_SYMLINK')
        for name in names:
            path=Path(directory)/name;before=path.lstat()
            need(stat.S_ISREG(before.st_mode) and before.st_size<=8388608 and before.st_uid==0 and not stat.S_IMODE(before.st_mode)&0o022,'PUBLIC_OBJECT')
            with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as f:payload=f.read(8388609)
            after=path.lstat();need((before.st_ino,before.st_dev,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_dev,after.st_size,after.st_mtime_ns),'FILE_CHANGED')
            total+=len(payload);need(total<=33554432 and len(found)<2000,'PUBLIC_LIMIT')
            found[path.relative_to(public).as_posix()]={'size':len(payload),'sha256':sha(payload)}
    end=pointer.lstat();need((start.st_dev,start.st_ino,start.st_mtime_ns)==(end.st_dev,end.st_ino,end.st_mtime_ns) and os.readlink(pointer)==str(EXPECTED) and public.stat().st_ino==identity.st_ino,'POINTER_CHANGED')
    need(found==wanted and len(found)==1279,'PUBLIC_MANIFEST_DRIFT')
    inventory=nginx_source();need(inventory['status']=='SOURCE_INVENTORY_COMPLETE' and inventory['disk_config_trust'],'NGINX_SOURCE_UNTRUSTED')
    result={'state':'PUBLIC_BASELINE_MATCH_ROOT_EVIDENCE_PENDING','host':os.uname().nodename,'uid':os.geteuid(),'current':str(EXPECTED),
      'public_file_count':len(found),'public_manifest_digest':sha(json.dumps(found,sort_keys=True,separators=(',',':')).encode()),
      'nginx_files':{p:r['sha256'] for p,r in inventory['files'].items()},'nginx_loaded_validation':'REQUIRES_PROTECTED_ROOT',
      'protected_previous_receipt':'REQUIRES_OWNER_ROOT_SHA256','runtime_kernel_isolation':'REQUIRES_PROTECTED_ROOT',
      'production_changes':0,'private_keys_read':False,'raw_configuration_exported':False}
    p=subprocess.run(['systemctl','show','xuanjun-site-hub-preview.service','-p','LoadState','-p','ActiveState','-p','MainPID','-p','User'],capture_output=True,text=True,timeout=15)
    need(p.returncode==0,'UNIT_METADATA_UNAVAILABLE');result['runtime_metadata']=dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)
    need(result['runtime_metadata'].get('ActiveState')=='active','RUNTIME_NOT_ACTIVE')
    print(json.dumps(result,sort_keys=True,indent=2))
if __name__=='__main__':main()
