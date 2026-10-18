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

# Protected rebuild is an internal original-coordinator operation, not a CLI,
# permission verifier, trust store, new transaction, or retry mechanism.
PROTECTED_RUNTIME = Path('/usr/local/lib/xuanjun-customer-runtime')
FIXED_INTERPRETER = Path('/usr/bin/python3')
FIXED_HOST = 'iZvt5t8tlrm8oiZ'
INTERPRETER_SHA256 = 'd9d3833f98fe814c39497d1f05b48474cb214713dd32f3971a5f1877d548ec22'

def _runtime_need(condition, reason):
    if not condition: raise Denied(reason)

def _root_chain(path):
    path=Path(path)
    _runtime_need(path.is_absolute(), 'ABSOLUTE_PATH_REQUIRED')
    for item in reversed((path,*path.parents)):
        s=os.lstat(item)
        _runtime_need(stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and
                      not s.st_mode&0o022, 'UNSAFE_PROTECTED_DIRECTORY')

def _protected_bytes(path, limit=50000000):
    path=Path(path);_root_chain(path.parent)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        _runtime_need(stat.S_ISREG(a.st_mode) and a.st_uid==a.st_gid==0 and
                      a.st_nlink==1 and not a.st_mode&0o6022 and 0<=a.st_size<=limit,
                      'UNSAFE_PROTECTED_INPUT')
        chunks=[];size=0
        while True:
            block=os.read(fd,min(65536,limit+1-size))
            if not block:break
            chunks.append(block);size+=len(block)
            _runtime_need(size<=limit,'PROTECTED_INPUT_LIMIT')
        b=os.fstat(fd);c=os.lstat(path)
        fields=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        _runtime_need(all(getattr(a,k)==getattr(b,k)==getattr(c,k) for k in fields)
                      and size==a.st_size,'PROTECTED_INPUT_DRIFT')
        return b''.join(chunks)
    finally:os.close(fd)

def _relative_runtime_path(name):
    _runtime_need(type(name) is str and name and '\\' not in name and '\x00' not in name,
                  'RUNTIME_MEMBER_PATH')
    p=Path(name)
    _runtime_need(not p.is_absolute() and all(x not in ('','.','..') for x in name.split('/')),
                  'RUNTIME_MEMBER_PATH')
    return p

def _source_identity(contract):
    """Verify externally reviewed *complete* stdlib trees and native file pins.

    The authoritative contract must enumerate native loader/library dependencies;
    this function does not discover or pretend to attest a dynamic dependency set.
    """
    _runtime_need(contract['interpreter_sha256']==INTERPRETER_SHA256,'INTERPRETER_PIN')
    _root_chain(FIXED_INTERPRETER.parent)
    target=Path(os.path.realpath(FIXED_INTERPRETER))
    _runtime_need(target==Path('/usr/bin/python3.11'),'FIXED_INTERPRETER_RESOLUTION')
    # The fixed alias may be regular or a protected relative symlink, never a
    # caller-selected executable or an unexpected intermediate chain.
    s=os.lstat(FIXED_INTERPRETER)
    if stat.S_ISLNK(s.st_mode):
        _runtime_need(s.st_uid==s.st_gid==0 and os.readlink(FIXED_INTERPRETER) in
                      ('python3.11','/usr/bin/python3.11'),'INTERPRETER_ALIAS')
    else:_runtime_need(stat.S_ISREG(s.st_mode),'INTERPRETER_ALIAS')
    _runtime_need(digest(_protected_bytes(target))==INTERPRETER_SHA256,'INTERPRETER_BYTES')
    trees=contract['stdlib_trees'];native=contract['native_files']
    _runtime_need(type(trees) is dict and bool(trees) and type(native) is dict and bool(native),
                  'REVIEWED_SOURCE_CLOSURE_REQUIRED')
    for root,expected in trees.items():
        _runtime_need(root in ('/usr/lib/python3.11','/usr/lib64/python3.11'), 'STDLIB_ROOT')
        _root_chain(root);actual={}
        for base,dirs,files in os.walk(root,followlinks=False):
            for name in dirs:_root_chain(Path(base)/name)
            for name in files:
                p=Path(base)/name
                actual[str(p.relative_to(root))]=digest(_protected_bytes(p))
        _runtime_need(type(expected) is dict and actual==expected,'STDLIB_CLOSURE_DRIFT')
    for path,sha in native.items():
        p=Path(path)
        _runtime_need(p.is_absolute() and '..' not in p.parts and
                      any(str(p).startswith(root) for root in ('/usr/lib/','/usr/lib64/','/lib/','/lib64/')),
                      'NATIVE_SOURCE_PATH')
        _runtime_need(type(sha) is str and len(sha)==64 and digest(_protected_bytes(p))==sha,
                      'NATIVE_SOURCE_DRIFT')
    _runtime_need(contract['abi']=={'python':'3.11','machine':'x86_64','glibc_min':'2.34'},'REVIEWED_ABI')
    import platform
    family,version=platform.libc_ver()
    _runtime_need(os.uname().machine=='x86_64' and family=='glibc' and
                  tuple(int(x) for x in version.split('.')[:2]) >= (2,34),'TARGET_ABI')
    return digest(canonical({'interpreter':INTERPRETER_SHA256,'stdlib':trees,'native':native,'abi':contract['abi']}))

def _runtime_tree(root):
    """Full root-owned closure, including directories and explicitly safe aliases."""
    _root_chain(root);out={}
    for base,dirs,files in os.walk(root,followlinks=False):
        for name in sorted(dirs+files):
            p=Path(base)/name;s=os.lstat(p);rel=str(p.relative_to(root))
            _runtime_need(s.st_uid==s.st_gid==0 and (stat.S_ISLNK(s.st_mode) or not s.st_mode&0o7022),'RUNTIME_OWNERSHIP_MODE')
            if stat.S_ISDIR(s.st_mode):out[rel]={'kind':'directory','mode':stat.S_IMODE(s.st_mode)}
            elif stat.S_ISREG(s.st_mode):
                out[rel]={'kind':'file','mode':stat.S_IMODE(s.st_mode),'sha256':digest(_protected_bytes(p))}
            else:
                aliases={'venv/bin/python3':'python','venv/bin/python3.11':'python','venv/lib64':'lib'}
                _runtime_need(stat.S_ISLNK(s.st_mode) and rel in aliases and
                              os.readlink(p)==aliases[rel],'UNAPPROVED_RUNTIME_LINK')
                out[rel]={'kind':'symlink','target':aliases[rel]}
    return out

def _sync_runtime(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def _durable_runtime(root):
    for base,dirs,files in os.walk(root,followlinks=False):
        for name in files:
            p=Path(base)/name
            if p.is_symlink():continue
            fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
        _sync_runtime(base)
    _sync_runtime(root.parent)

def _create_runtime_member(root,name,raw):
    relative=_relative_runtime_path(name);p=root/relative
    _root_chain(root)
    parent=root
    for component in relative.parts[:-1]:
        parent=parent/component
        try:parent.mkdir(mode=0o755)
        except FileExistsError:pass
        _root_chain(parent)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
    with os.fdopen(fd,'wb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    _sync_runtime(p.parent)

def _bounded_runtime_verify(argv,uid,gid,env):
    import selectors,time
    output=bytearray();process=None;selector=selectors.DefaultSelector()
    try:
        process=subprocess.Popen(argv,user=uid,group=gid,extra_groups=(),cwd='/',env=env,
                                 stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        selector.register(process.stdout,selectors.EVENT_READ)
        end=time.monotonic()+30
        while selector.get_map():
            remaining=end-time.monotonic()
            _runtime_need(remaining>0,'RUNTIME_VERIFY_TIMEOUT')
            for key,_ in selector.select(remaining):
                block=os.read(key.fileobj.fileno(),4097-len(output))
                if not block:selector.unregister(key.fileobj);continue
                output.extend(block)
                _runtime_need(len(output)<=4096,'RUNTIME_VERIFY_OUTPUT')
        remaining=end-time.monotonic()
        _runtime_need(remaining>0 and process.wait(timeout=remaining)==0,'RUNTIME_VERIFY_FAILED')
        return json.loads(output.decode('utf-8'))
    finally:
        selector.close()
        if process is not None:
            if process.poll() is None:
                process.kill();process.wait(timeout=5)
            if process.stdout is not None:process.stdout.close()

def protected_rebuild(contract, coordinator):
    """Real fixed-path rebuild; NEVER called by the existing staging CLI.

    coordinator.authorize_runtime(contract) must verify existing actual authority,
    not a boolean from this module. assert_locked() and record_runtime() belong to
    the original preparation transaction. Missing implementations fail closed.
    No retry/resume, cleanup, overwrite, key generation, or permission is supplied.
    """
    fields={'schema','host','source_commit','runtime_module_sha256','wheel_directory',
            'interpreter_sha256','stdlib_trees','native_files','abi','expected_venv_tree','account_uid','account_gid'}
    _runtime_need(type(contract) is dict and set(contract)==fields and type(contract['schema']) is int and contract['schema']==1,
                  'RUNTIME_CONTRACT_SCHEMA')
    _runtime_need(contract['host']==FIXED_HOST and os.uname().nodename==FIXED_HOST and
                  os.getuid()==os.geteuid()==0 and os.getgid()==os.getegid()==0,'RUNTIME_OWNER_HOST')
    _runtime_need(type(contract['source_commit']) is str and len(contract['source_commit'])==40,
                  'RUNTIME_SOURCE_COMMIT')
    # The verifier must bind this module's exact bytes as part of the original
    # package. No self-asserted approval dictionary or generated permit is used.
    coordinator.authorize_runtime(contract)
    coordinator.assert_locked()
    _runtime_need(digest(_protected_bytes(Path(__file__).absolute()))==contract['runtime_module_sha256'],
                  'RUNTIME_MODULE_BINDING')
    import pwd,grp
    account=pwd.getpwnam('xuanjun-customer');group=grp.getgrnam('xuanjun-customer')
    _runtime_need(type(contract['account_uid']) is int and type(contract['account_gid']) is int and
                  account.pw_uid==contract['account_uid']>0 and account.pw_gid==group.gr_gid==contract['account_gid']>0 and
                  account.pw_dir=='/nonexistent' and account.pw_shell=='/usr/sbin/nologin' and
                  not any(account.pw_name in g.gr_mem for g in grp.getgrall()),'RUNTIME_ACCOUNT')
    _root_chain(PROTECTED_RUNTIME.parent)
    _runtime_need(not os.path.lexists(PROTECTED_RUNTIME),'RUNTIME_EXISTS_PRESERVE')
    source_identity=_source_identity(contract)
    wheels=Path(contract['wheel_directory']);_root_chain(wheels)
    # Root-protected individual byte validation precedes existing bounded ZIP
    # parsing. Its exact three vendor pins stay unchanged.
    for name,sha in WHEELS.items():
        _runtime_need(digest(_protected_bytes(wheels/name,15000000))==sha,'VENDOR_WHEEL_BYTES')
    files=wheel_files(wheels)
    expected=contract['expected_venv_tree']
    _runtime_need(type(expected) is dict and bool(expected),'REVIEWED_VENV_CLOSURE_REQUIRED')
    for name in expected:
        _relative_runtime_path(name)
        _runtime_need(not name.startswith('venv/lib/python3.11/site-packages/') and not name.endswith('.pth') and Path(name).name not in ('sitecustomize.py','usercustomize.py'),
                      'GENERATED_RUNTIME_STARTUP_HOOK')
    _runtime_need(expected.get('venv/bin/python',{}).get('kind')=='file' and
                  expected.get('venv/pyvenv.cfg',{}).get('kind')=='file' and
                  expected['venv/bin/python'].get('sha256')==INTERPRETER_SHA256, 'REGULAR_RUNTIME_REQUIRED')
    coordinator.assert_locked();coordinator.authorize_runtime(contract)
    _runtime_need(_source_identity(contract)==source_identity,'SOURCE_CHANGED_BEFORE_WRITE')
    coordinator.record_runtime('RUNTIME_CREATE_INTENT',{'contract_sha256':digest(canonical(contract))})
    old_umask=os.umask(0o022)
    try:
        coordinator.assert_locked();coordinator.authorize_runtime(contract)
        PROTECTED_RUNTIME.mkdir(mode=0o755);_sync_runtime(PROTECTED_RUNTIME.parent)
        env={'PATH':'/usr/bin:/bin','LANG':'C','PYTHONDONTWRITEBYTECODE':'1'}
        coordinator.assert_locked();coordinator.authorize_runtime(contract)
        subprocess.run([str(FIXED_INTERPRETER),'-I','-B','-S','-m','venv','--copies','--without-pip',
                        str(PROTECTED_RUNTIME/'venv')],check=True,timeout=45,env=env,cwd='/',
                        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        _runtime_need(_runtime_tree(PROTECTED_RUNTIME)==expected,'GENERATED_VENV_CLOSURE_MISMATCH')
        cfg=_protected_bytes(PROTECTED_RUNTIME/'venv/pyvenv.cfg').decode('utf-8')
        _runtime_need('include-system-site-packages = false' in cfg,'SYSTEM_SITE_PACKAGES_FORBIDDEN')
        site=PROTECTED_RUNTIME/'venv/lib/python3.11/site-packages';_root_chain(site)
        for name,raw in sorted(files.items()):
            coordinator.assert_locked();coordinator.authorize_runtime(contract)
            _create_runtime_member(site,name,raw)
        final_expected=dict(expected)
        for name,raw in files.items():
            p=Path('venv/lib/python3.11/site-packages')/_relative_runtime_path(name)
            for parent in p.parents:
                if str(parent)=='.':break
                final_expected.setdefault(str(parent),{'kind':'directory','mode':0o755})
            _runtime_need(str(p) not in final_expected,'WHEEL_OVERLAPS_VENV')
            final_expected[str(p)]={'kind':'file','mode':0o644,'sha256':digest(raw)}
        _runtime_need(_runtime_tree(PROTECTED_RUNTIME)==final_expected,'INSTALLED_RUNTIME_CLOSURE')
        coordinator.assert_locked()
        _runtime_need(_source_identity(contract)==source_identity,'SOURCE_CHANGED_AFTER_WRITE')
        live_account=pwd.getpwnam('xuanjun-customer');live_group=grp.getgrnam('xuanjun-customer')
        _runtime_need((live_account.pw_uid,live_account.pw_gid,live_account.pw_dir,live_account.pw_shell,live_group.gr_gid)==
                      (account.pw_uid,account.pw_gid,account.pw_dir,account.pw_shell,group.gr_gid),'RUNTIME_ACCOUNT_DRIFT')
        versions=_bounded_runtime_verify([str(PROTECTED_RUNTIME/'venv/bin/python'),'-I','-B','-c',VERIFY],
                                         account.pw_uid,group.gr_gid,env)
        _runtime_need(versions=={'cryptography':'46.0.3','cffi':'2.0.0','pycparser':'2.23',
                                'aes_gcm':'PASS','ed25519':'PASS'},'RUNTIME_VERIFY_RESULT')
        _runtime_need(_runtime_tree(PROTECTED_RUNTIME)==final_expected,'POST_VERIFY_CLOSURE_DRIFT')
        _durable_runtime(PROTECTED_RUNTIME)
        root_identity=os.lstat(PROTECTED_RUNTIME)
        report={'state':'PROTECTED_RUNTIME_REBUILT_VERIFIED',
                'runtime_root_identity':{'dev':root_identity.st_dev,'ino':root_identity.st_ino,'uid':root_identity.st_uid,'gid':root_identity.st_gid,'mode':stat.S_IMODE(root_identity.st_mode)},'source_closure_sha256':source_identity,
                'runtime_closure_sha256':digest(canonical(final_expected)),'account_uid':account.pw_uid,
                'account_gid':group.gr_gid,'versions':versions,'service_started':False,'retry_allowed':False}
        coordinator.record_runtime('RUNTIME_VERIFIED',report)
        return report
    except BaseException:
        # No captured vendor stderr or secrets enter the original receipt.
        coordinator.record_runtime('RUNTIME_UNKNOWN_PRESERVE',{'retry_allowed':False})
        raise
    finally:os.umask(old_umask)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--wheels',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    if os.uname().nodename!='iZvt5t8tlrm8oiZ' or os.getuid()!=1002:raise Denied('FIXED_UNPRIVILEGED_TARGET_RUNNER_REQUIRED')
    print(json.dumps(build(a.wheels,a.output),sort_keys=True))
if __name__=='__main__':main()
