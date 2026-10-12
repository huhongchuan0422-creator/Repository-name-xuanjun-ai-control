"""Replay pinned frozen source and execute local-only controller regressions."""
import hashlib, json, os, pathlib, shutil, subprocess, tarfile, zipfile
ROOT=pathlib.Path(__file__).resolve().parent
DEST=pathlib.Path('/tmp/xuanjun-p2-native-ci')
SHA='456ae23aa52e300021c9fb889df84d8eba34965769ce868e5ee6e43c29911a13'
with zipfile.ZipFile(os.environ['P2_FROZEN_ZIP']) as archive:
    candidates=[n for n in archive.namelist() if n.split('/')[-1]=='candidate.tar.gz']
    if len(candidates)!=1:raise ValueError('frozen artifact identity')
    info=archive.getinfo(candidates[0])
    if info.file_size>2097152:raise ValueError('archive limit')
    raw=archive.read(candidates[0])
if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('frozen source digest')
DEST.mkdir(mode=0o700,exist_ok=False)
archive_path=DEST/'candidate.tar.gz';archive_path.write_bytes(raw)
with tarfile.open(archive_path) as archive:
    names=set();total=0
    for item in archive.getmembers():
        parts=pathlib.PurePosixPath(item.name).parts
        if (not parts or parts[0]!='xuanjun-p2-package' or item.name.startswith('/')
                or any(p in ('.','..') for p in parts) or item.name in names
                or not (item.isfile() or item.isdir())):raise ValueError('unsafe frozen archive')
        names.add(item.name);total+=item.size
        if total>67108864:raise ValueError('source limit')
    archive.extractall(DEST)
source=DEST/'xuanjun-p2-package'
for item in source.rglob('*'):
    if item.is_file():item.chmod(item.stat().st_mode|0o200)
subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(ROOT/'native-wiring.patch')],cwd=source,check=True)
shutil.copy2(ROOT/'native_peer_identity.py',source/'stage1'/'native_peer_identity.py')
subprocess.run(['python',str(ROOT/'followup_overlay.py'),str(source)],check=True)
plugin=source/'plugins/p2-native-controller'
shutil.copytree(ROOT/'controller',plugin)
subprocess.run(['python',str(ROOT/'c2_install_overlay.py'),str(source)],check=True)
env=dict(os.environ,P2_SOURCE_ROOT=str(source))
for name in ('test_native_wiring.py','test_native_ledger.py','test_native_socket.py'):
    subprocess.run(['python',str(ROOT/name)],env=env,check=True)
for name in ('test_controller.mjs','test_host.mjs'):
    subprocess.run(['node',str(ROOT/name)],env=env,check=True)
for item in plugin.glob('*.mjs'):subprocess.run(['node','--check',str(item)],check=True)
for name in ('p2_install_entrypoint.py','p2_fixed_host_runtime.py'):
    raw=(source/'stage1'/name).read_text();compile(raw,name,'exec')
print(json.dumps({'state':'SOURCE_REGRESSION_PASS','frozen_archive_sha256':SHA,
 'patch_sha256':hashlib.sha256((ROOT/'native-wiring.patch').read_bytes()).hexdigest(),
 'followup_sha256':hashlib.sha256((ROOT/'followup_overlay.py').read_bytes()).hexdigest(),
 'c2_install_overlay_sha256':hashlib.sha256((ROOT/'c2_install_overlay.py').read_bytes()).hexdigest(),
 'model_calls':0,'UK_runtime':'NOT_RUN','install':'NOT_RUN','release_gate':'NOT_GRANTED'}))
