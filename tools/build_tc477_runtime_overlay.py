#!/usr/bin/env python3
"""Build an immutable delta for the original installer. Never installs/stops."""
import argparse,gzip,hashlib,io,json,os,pathlib,subprocess,tarfile
BASE_MANIFEST='15ecfa38228e106dc9b8528e98f5b32e9f7d92e67284c71cc1ab521f22091ac6'
def digest(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def git(*args):return subprocess.check_output(['git']+list(args)).decode().strip()
def build(base,out):
    base=pathlib.Path(base).resolve();out=pathlib.Path(out).resolve()
    if str(out)==str(base) or str(out).startswith(str(base)+os.sep):raise ValueError('OUTPUT_MUST_NOT_TOUCH_RELEASE')
    if git('status','--porcelain'):raise ValueError('FROZEN_CLEAN_SOURCE_REQUIRED')
    commit=git('rev-parse','HEAD');tree=git('rev-parse','HEAD^{tree}')
    raw=(base/'INSTALL_MANIFEST.json').read_bytes()
    if digest(raw)!=BASE_MANIFEST:raise ValueError('INSTALLED_BASE_MANIFEST_CHANGED')
    entries={e['path']:e for e in json.loads(raw)['entries']}
    lock_path='docs/backup/tc477-dependency-lock-20261124.json'
    lock_raw=pathlib.Path(lock_path).read_bytes();lock=json.loads(lock_raw)
    for row in lock['files']:
        if digest(pathlib.Path(row['path']).read_bytes())!=row['sha256']:raise ValueError('DEPENDENCY_LOCK_MISMATCH')
    paths=git('ls-files','scripts').splitlines()+[lock_path]
    files=[];payload={}
    for name in sorted(paths):
        path=pathlib.PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('INVALID_SOURCE_PATH')
        source=pathlib.Path(name)
        if source.is_symlink() or not source.is_file():raise ValueError('REGULAR_SOURCE_REQUIRED')
        data=source.read_bytes();sha=digest(data);before=entries.get(name)
        if before is not None:
            if before['type']!='file' or digest((base/name).read_bytes())!=before['sha256']:
                raise ValueError('INSTALLED_BEFORE_BYTES_CHANGED')
            if sha==before['sha256']:continue
        elif os.path.lexists(str(base/name)):raise ValueError('ADD_PATH_ALREADY_EXISTS')
        mode=int(before['mode'],8) if before else 0o644
        if mode & 0o022:raise ValueError('WRITABLE_RELEASE_SOURCE_REJECTED')
        payload['payload/'+name]=(data,mode)
        files.append(dict(path=name,before_sha256=before['sha256'] if before else None,
            before_mode=before['mode'] if before else None,result_sha256=sha,size=len(data),mode=oct(mode)))
    manifest=dict(schema=1,kind='INSTALLER_DELTA_CANDIDATE',source_commit=commit,source_tree=tree,
        build_id='tc477-'+commit[:12],before_install_manifest_sha256=BASE_MANIFEST,
        files=files,delete_files=[],preserve_all_unlisted_installed_paths=True,
        dependency_lock_sha256=digest(lock_raw),launch_entry='scripts/task_center_handoff_launch.py',
        config_policy='OWNER_0600_SELECTORS_NO_SECRET_BODY_NO_PLUGIN_LOADER',
        formal_handoff_default='DISABLED_OR_BACKEND_UNAVAILABLE_NO_FAKE_COMPLETE',install_performed=False)
    manifest_raw=encoded(manifest);payload['RESULT-FILES.json']=(manifest_raw,0o644)
    out.mkdir(parents=True,exist_ok=True);archive=out/'tc477-runtime-overlay.tar.gz'
    if archive.exists():raise ValueError('BUILD_OUTPUT_EXISTS_DO_NOT_OVERWRITE')
    with archive.open('wb') as stream:
        with gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as zipped:
            with tarfile.open(fileobj=zipped,mode='w') as tar:
                for name,(data,mode) in sorted(payload.items()):
                    info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode;info.mtime=0;info.uid=0;info.gid=0
                    tar.addfile(info,io.BytesIO(data))
    (out/'RESULT-FILES.json').write_bytes(manifest_raw)
    receipt=dict(SOURCE_COMMIT=commit,SOURCE_TREE=tree,BUILD_ID=manifest['build_id'],VERSION=commit[:12],
        DEPENDENCY_LOCK=manifest['dependency_lock_sha256'],ARTIFACT_HASH=digest(archive.read_bytes()),
        RESULT_MANIFEST_HASH=digest(manifest_raw),RELEASE_STATUS='CANDIDATE_NOT_INSTALLED',
        SECURITY_RESULT='NOT_A_FORMAL_SECURITY_RELEASE',SBOM={'python_stdlib':True,'external_packages':['cryptography'],
            'vendored_sources':lock['files']},TEST_RESULT='SEE_EXACT_VERSION_TEST_RECEIPT',
        file_count=len(files),payload_bytes=sum(len(data) for data,_ in payload.values()))
    (out/'BUILD-RECEIPT.json').write_bytes(encoded(receipt));print(json.dumps(receipt,sort_keys=True))
    return receipt
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base-release',required=True);parser.add_argument('--out-dir',required=True)
    args=parser.parse_args();build(args.base_release,args.out_dir)
