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
subprocess.run(['python',str(ROOT/'task23_shared_overlay.py'),str(source)],check=True)
subprocess.run(['python',str(ROOT/'work_review_blockers_overlay.py'),str(source)],check=True)
subprocess.run(['python',str(ROOT/'c2_install_overlay.py'),str(source)],check=True)
subprocess.run(['python',str(ROOT/'service_context_task23_overlay.py'),str(source)],check=True)
env=dict(os.environ,P2_SOURCE_ROOT=str(source))
for name in ('test_native_wiring.py','test_native_ledger.py','test_native_socket.py','test_c2_install_highs.py','test_task23_shared_integration.py','test_work_review_blockers.py','test_service_context_task23.py'):
    subprocess.run(['python',str(ROOT/name)],env=env,check=True)
for name in ('test_controller.mjs','test_host.mjs'):
    subprocess.run(['node',str(ROOT/name)],env=env,check=True)
for item in plugin.glob('*.mjs'):subprocess.run(['node','--check',str(item)],check=True)
# Retain base regressions above, then integrate and test the complete caller package.
repo=ROOT.parents[1]
base_fixture=DEST/'feishu-base'/'xuanjun-p2-package'
base_fixture.parent.mkdir(mode=0o700)
shutil.copytree(str(source),str(base_fixture))
subprocess.run(['python','-B',str(repo/'scripts/owner_feishu_runtime_overlay.py'),str(source)],check=True)
subprocess.run(['python','-B',str(ROOT/'native_snapshot_access_overlay.py'),str(source)],check=True)
subprocess.run(['python','-B',str(ROOT/'sdk_layout_overlay.py'),str(source)],check=True)
subprocess.run(['python','-B',str(ROOT/'socket_access_overlay.py'),str(source)],check=True)
subprocess.run(['python','-B',str(ROOT/'bootstrap_install_overlay.py'),str(source)],check=True)
subprocess.run(['python','-B',str(ROOT/'publisher_install_overlay.py'),str(source)],check=True)
controller_digest=hashlib.sha256((source/'stage1/native_gateway_controller.py').read_bytes()).hexdigest()
service_text=(source/'deploy/xuanjun-development-dispatcher.service').read_text()
if service_text.count('--native-controller-sha256 '+controller_digest)!=3:
    raise ValueError('FINAL_PACKAGE_CONTROLLER_SERVICE_HASH_MISMATCH')
final_env=dict(env,P2_SOURCE_ROOT=str(source))
subprocess.run(['python','-B',str(ROOT/'test_c2_install_highs.py')],env=final_env,check=True)
subprocess.run(['python','-B',str(ROOT/'test_native_snapshot_access.py')],env=final_env,check=True)
subprocess.run(['node',str(ROOT/'test_sdk_layout.mjs')],env=final_env,check=True)
subprocess.run(['python','-B',str(ROOT/'test_socket_access_plan.py')],env=final_env,check=True)
subprocess.run(['sudo','-n','env','P2_SOURCE_ROOT='+str(source),'python3','-B',str(ROOT/'test_bootstrap_files.py')],check=True)
subprocess.run(['sudo','-n','env','P2_SOURCE_ROOT='+str(source),'python3','-B',str(ROOT/'test_publisher_bootstrap.py')],check=True)
print('FINAL_PACKAGE_CONTROLLER_SERVICE_HASH_AND_INSTALL_LIFECYCLE=PASS')
env.update(P2_SOURCE_ROOT=str(base_fixture),P2_FEISHU_INTEGRATION_ROOT=str(source))
subprocess.run(['python','-B','-m','unittest','discover','-s',str(repo/'tests'),'-p','test_owner_feishu_*.py','-v'],env=env,check=True)
subprocess.run(['node',str(repo/'tests/test_owner_feishu_gateway.mjs')],env=env,check=True)
for item in plugin.glob('*.mjs'):subprocess.run(['node','--check',str(item)],check=True)
build_commit=os.environ.get('P2_BUILD_COMMIT')
build_tree=os.environ.get('P2_BUILD_TREE')
if build_commit or build_tree:
    if not build_commit or not build_tree:
        raise ValueError('P2_BUILD_IDENTITY_INCOMPLETE')
    package_archive=DEST/'authoritative-p2-package.tar.gz'
    subprocess.run(['python',str(source/'tools/p2-package-freeze.py'),'build',
        '--source-root',str(source),'--output',str(package_archive),
        '--source-commit',build_commit,'--source-tree',build_tree],check=True)
    subprocess.run(['python',str(source/'tools/p2-package-freeze.py'),'verify',
        '--archive',str(package_archive),'--source-commit',build_commit,
        '--source-tree',build_tree],check=True)
    env['P2_AUTHORITATIVE_PACKAGE']=str(package_archive)

for name in ('p2_install_entrypoint.py','p2_fixed_host_runtime.py'):
    raw=(source/'stage1'/name).read_text();compile(raw,name,'exec')
print(json.dumps({'state':'SOURCE_REGRESSION_PASS','frozen_archive_sha256':SHA,
 'patch_sha256':hashlib.sha256((ROOT/'native-wiring.patch').read_bytes()).hexdigest(),
 'followup_sha256':hashlib.sha256((ROOT/'followup_overlay.py').read_bytes()).hexdigest(),
 'c2_install_overlay_sha256':hashlib.sha256((ROOT/'c2_install_overlay.py').read_bytes()).hexdigest(),
 'task23_shared_overlay_sha256':hashlib.sha256((ROOT/'task23_shared_overlay.py').read_bytes()).hexdigest(),
 'task23_adapter_sha256':hashlib.sha256((ROOT/'task_supervisor_inventory_adapter.py').read_bytes()).hexdigest(),
 'work_review_blockers_overlay_sha256':hashlib.sha256((ROOT/'work_review_blockers_overlay.py').read_bytes()).hexdigest(),
 'service_context_task23_overlay_sha256':hashlib.sha256((ROOT/'service_context_task23_overlay.py').read_bytes()).hexdigest(),
 'authoritative_freeze':bool(build_commit),'model_calls':0,'UK_runtime':'NOT_RUN','install':'NOT_RUN','release_gate':'NOT_GRANTED'}))
