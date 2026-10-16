"""Offline, unprivileged runtime staging. Never installs global Python packages.
Pinned vendor wheel bytes were downloaded from the reviewed CI artifact.
The staged directory is evidence, NOT a trusted production installation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import zipfile
class Denied(PermissionError):pass
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(value).hexdigest()

WHEELS={
 'cffi-2.0.0-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl':'8941aaadaf67246224cee8c3803777eed332a19d909b47e29c9842ef1e79ac26',
 'cryptography-46.0.3-cp311-abi3-manylinux_2_34_x86_64.whl':'10b01676fc208c3e6feeb25a8b83d81767e8059e1fe86e1dc62d10a3018fa926',
 'pycparser-2.23-py3-none-any.whl':'e5c6e8d3fbad53479cab09ac03729e0a9faf2bee3db8208a550daf5af81a5934',
}

def wheel_files(folder):
    folder=Path(folder)
    if folder.is_symlink() or {p.name for p in folder.iterdir()}!=set(WHEELS):raise Denied('EXACT_VENDOR_WHEEL_SET_REQUIRED')
    files={};total=0
    for name,sha in WHEELS.items():
        path=folder/name
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as f:
            st=os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or not 0<st.st_size<15000000:raise Denied('WHEEL_TYPE_SIZE')
            raw=f.read(15000001)
        if digest(raw)!=sha:raise Denied('PINNED_VENDOR_WHEEL_HASH')
        import io
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            seen=set()
            for member in z.infolist():
                p=Path(member.filename)
                if p.is_absolute() or '..' in p.parts or '\\' in member.filename or member.filename in seen or stat.S_ISLNK(member.external_attr>>16):raise Denied('WHEEL_MEMBER_PATH_TYPE')
                seen.add(member.filename)
                if member.is_dir():continue
                if p.suffix=='.pth' or any(x.endswith('.data') for x in p.parts) or member.file_size>20000000:raise Denied('WHEEL_INSTALL_HOOK_OR_SIZE')
                total+=member.file_size
                if total>60000000 or len(files)>10000 or member.filename in files:raise Denied('WHEEL_CLOSURE_LIMIT')
                b=z.read(member);files[member.filename]=b
    return files

VERIFY="""import json,cryptography,cffi,pycparser
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
key=bytes(range(32));nonce=bytes(range(12));cipher=AESGCM(key).encrypt(nonce,b'isolated runtime',b'PR122')
assert AESGCM(key).decrypt(nonce,cipher,b'PR122')==b'isolated runtime'
p=Ed25519PrivateKey.generate();p.public_key().verify(p.sign(b'fixture'),b'fixture')
assert (cryptography.__version__,cffi.__version__,pycparser.__version__)==('46.0.3','2.0.0','2.23')
print(json.dumps({'cryptography':cryptography.__version__,'cffi':cffi.__version__,'pycparser':pycparser.__version__,'aes_gcm':'PASS','ed25519':'PASS'}))
"""

def build(folder,output):
    if os.geteuid()==0:raise Denied('UNPRIVILEGED_STAGING_ONLY')
    if sys.version_info[:2]!=(3,11):raise Denied('TARGET_PYTHON_3_11_REQUIRED')
    output=Path(output)
    if not output.is_absolute() or os.path.lexists(output):raise Denied('NEW_ISOLATED_OUTPUT_REQUIRED')
    files=wheel_files(folder)
    output.mkdir(mode=0o700)
    env={'PATH':'/usr/bin:/bin','LANG':'C','PYTHONDONTWRITEBYTECODE':'1'}
    try:
        subprocess.run([sys.executable,'-I','-B','-m','venv','--copies','--without-pip',str(output/'venv')],check=True,timeout=45,env=env,capture_output=True)
        site=output/'venv/lib/python3.11/site-packages'
        for relative,raw in files.items():
            p=site/relative;p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('xb') as f:f.write(raw)
            p.chmod(0o644)
        result=subprocess.run([str(output/'venv/bin/python'),'-I','-B','-c',VERIFY],check=True,timeout=30,env=env,capture_output=True,text=True)
        versions=json.loads(result.stdout)
        report={'state':'ISOLATED_TARGET_RUNTIME_PASS','host':os.uname().nodename,'python':sys.version,'versions':versions,'wheel_sha256':WHEELS,'installed_file_count':len(files),'file_scope_sha256':digest(canonical({p:digest(b) for p,b in sorted(files.items())})),'root_called':False,'global_package_changes':0,'production_install':'NOT_EXECUTED','owner_protected_rebuild_required':True}
        (output/'RUNTIME_REPORT.json').write_bytes(canonical(report));return report
    except BaseException:
        (output/'HOLD.json').write_bytes(canonical({'state':'HOLD','retry_allowed':False,'production_install':'NOT_EXECUTED'}));raise

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--wheels',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    if os.uname().nodename!='iZvt5t8tlrm8oiZ' or os.getuid()!=1002:raise Denied('FIXED_UNPRIVILEGED_TARGET_RUNNER_REQUIRED')
    print(json.dumps(build(a.wheels,a.output),sort_keys=True))
if __name__=='__main__':main()
