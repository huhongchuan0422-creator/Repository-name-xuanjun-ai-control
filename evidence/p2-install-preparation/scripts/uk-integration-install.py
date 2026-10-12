#!/usr/bin/env python3
"""Verify a frozen SOURCE_COMMIT/file manifest and atomically stage a release."""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import secrets


SHA = re.compile(r'^[0-9a-f]{64}$')
RELEASE_DIRECTORY = re.compile(r'^integration-[0-9a-f]{16}$')
PLACEHOLDER = re.compile(r'@@[A-Z0-9_]+@@')
IDENTITY_TOKENS = ('@@RELEASE_DIRECTORY@@', '@@ARTIFACT_SHA256@@')
REQUIRED_RENDERER = 'scripts/uk-owner-workbench-config.py'
IDENTITY_RENDERED_FILES = (
    'deploy/dispatcher.example.json',
    'deploy/uk-owner-workbench/xuanjun-uk-owner-callback.service',
    'deploy/uk-owner-workbench/xuanjun-uk-owner-dashboard.service',
    'deploy/xj-root-broker.service',
    'deploy/xuanjun-development-dispatcher.service',
    'deploy/xuanjun-github-intake.service',
    'deploy/xuanjun-ledger.service',
)


def _raise_release_component_error(parent_fd, component):
    """Classify a component without following it after guarded open failed."""
    try:
        info=os.stat(component,dir_fd=parent_fd,follow_symlinks=False)
    except OSError:
        # The component disappeared or cannot be inspected.  Keep the failure
        # closed without claiming that an unobserved object was a symlink.
        raise ValueError('UNSAFE_RELEASE_ROOT')
    if stat.S_ISLNK(info.st_mode):
        raise ValueError('SYMLINKED')
    raise ValueError('UNSAFE_RELEASE_ROOT')


def open_safe_release_root(path, owner_uid):
    """Open/create an absolute release root without following any symlink."""
    if not os.path.isabs(path) or os.path.normpath(path) != path or path == '/':
        raise ValueError('INVALID_INSTALL_PATH')
    flags=os.O_RDONLY|getattr(os,'O_DIRECTORY',0)|getattr(os,'O_NOFOLLOW',0)
    fd=os.open('/',flags)
    try:
        for component in [part for part in path.split('/') if part]:
            parent_info=os.fstat(fd)
            if (not stat.S_ISDIR(parent_info.st_mode)
                    or parent_info.st_uid not in (0,owner_uid)
                    or parent_info.st_mode & 0o022):
                raise ValueError('UNSAFE_RELEASE_ANCESTRY')
            try:
                child=os.open(component,flags,dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(component,0o750,dir_fd=fd)
                try:
                    child=os.open(component,flags,dir_fd=fd)
                except OSError:
                    _raise_release_component_error(fd,component)
            except OSError:
                _raise_release_component_error(fd,component)
            os.close(fd); fd=child
        info=os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=owner_uid
                or info.st_mode & 0o022):
            raise ValueError('UNSAFE_RELEASE_ROOT')
        return fd
    except BaseException:
        os.close(fd)
        raise


def make_staging(releases_fd,releases):
    for unused in range(100):
        name='.integration-'+secrets.token_hex(8)
        try:
            os.mkdir(name,0o700,dir_fd=releases_fd)
            return name,os.path.join(releases,name)
        except FileExistsError:
            continue
    raise OSError('unable to allocate staging directory')


def digest(path):
    value=hashlib.sha256()
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    info=os.fstat(fd)
    if not stat.S_ISREG(info.st_mode): os.close(fd); raise ValueError('NOT_REGULAR_FILE')
    with os.fdopen(fd,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): value.update(chunk)
    return value.hexdigest()


def release_identity(artifact_sha256):
    """Return the typed immutable directory identity for a full artifact hash."""
    if not isinstance(artifact_sha256,str) or not SHA.fullmatch(artifact_sha256):
        raise ValueError('INVALID_ARTIFACT_SHA256')
    return 'integration-'+artifact_sha256[:16]


def _validate_install_contract(manifest):
    rendering=manifest.get('rendering')
    if not isinstance(rendering,dict):
        raise ValueError('INVALID_RENDERING_CONTRACT')
    identity_files=rendering.get('identity_files')
    if (identity_files!=list(IDENTITY_RENDERED_FILES)
            or len(set(identity_files or ()))!=len(IDENTITY_RENDERED_FILES)):
        raise ValueError('INVALID_IDENTITY_RENDER_SET')
    allowed=rendering.get('allowed_remaining_placeholders')
    if not isinstance(allowed,dict) or set(allowed)!=set(IDENTITY_RENDERED_FILES):
        raise ValueError('INVALID_PLACEHOLDER_ALLOWLIST')
    for name,tokens in allowed.items():
        if (not isinstance(tokens,list) or len(tokens)!=len(set(tokens))
                or any(not PLACEHOLDER.fullmatch(token) or token in IDENTITY_TOKENS
                       for token in tokens)):
            raise ValueError('INVALID_PLACEHOLDER_ALLOWLIST:'+name)

    renderers=manifest.get('required_renderers')
    if not isinstance(renderers,list) or len(renderers)!=1:
        raise ValueError('INVALID_REQUIRED_RENDERERS')
    renderer=renderers[0]
    expected_target='/opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/'+REQUIRED_RENDERER
    if (not isinstance(renderer,dict) or renderer.get('path')!=REQUIRED_RENDERER
            or renderer.get('sha256')!=manifest.get('files',{}).get(REQUIRED_RENDERER)
            or renderer.get('target')!=expected_target
            or renderer.get('owner')!='root' or renderer.get('group')!='root'
            or renderer.get('mode')!='0555'
            or renderer.get('invocation')!=[expected_target,'--owner-host','<fqdn>',
                                             '--tls-cert','<absolute-path>',
                                             '--tls-key','<absolute-path>','--verify-files']):
        raise ValueError('INVALID_REQUIRED_RENDERER_BINDING')


def render_identity_bytes(name,data,artifact_sha256,manifest):
    """Render typed identities and reject unclassified placeholders."""
    if name not in IDENTITY_RENDERED_FILES:
        return data
    try:
        value=data.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError('NON_UTF8_RENDER_INPUT:'+name)
    allowed=set(manifest['rendering']['allowed_remaining_placeholders'][name])
    observed=PLACEHOLDER.findall(value)
    if set(observed)-set(IDENTITY_TOKENS)-allowed:
        raise ValueError('UNKNOWN_PLACEHOLDER:'+name)
    directory=release_identity(artifact_sha256)
    value=value.replace('@@RELEASE_DIRECTORY@@',directory)
    value=value.replace('@@ARTIFACT_SHA256@@',artifact_sha256)
    remaining=PLACEHOLDER.findall(value)
    if set(remaining)-allowed or any(token in IDENTITY_TOKENS for token in remaining):
        raise ValueError('UNRESOLVED_PLACEHOLDER:'+name)
    return value.encode('utf-8')


def validate_rollback_map(value,active_epoch):
    """Validate an immutable direct-path rollback receipt without side effects."""
    required={'schema','previous_release_directory','previous_manifest_sha256',
              'previous_artifact_sha256','previous_epoch','stopped_epoch',
              'cgroup_empty','restoration_order','rendered_files'}
    if not isinstance(value,dict) or set(value)!=required or value.get('schema')!=2:
        raise ValueError('INVALID_ROLLBACK_MAP')
    if (not RELEASE_DIRECTORY.fullmatch(value.get('previous_release_directory',''))
            or not SHA.fullmatch(value.get('previous_manifest_sha256',''))
            or not SHA.fullmatch(value.get('previous_artifact_sha256',''))
            or value['previous_release_directory']!=release_identity(value['previous_artifact_sha256'])
            or not isinstance(active_epoch,int) or active_epoch<1
            or value.get('stopped_epoch')!=active_epoch
            or not isinstance(value.get('previous_epoch'),int)
            or value['previous_epoch']>=active_epoch
            or value.get('cgroup_empty') is not True):
        raise ValueError('ROLLBACK_IDENTITY_MISMATCH')
    rendered=value.get('rendered_files')
    if not isinstance(rendered,dict) or not rendered:
        raise ValueError('INVALID_ROLLBACK_FILES')
    restoration=value.get('restoration_order')
    if (not isinstance(restoration,dict) or set(restoration)!= {'schema','targets'}
            or restoration.get('schema')!=1
            or not isinstance(restoration.get('targets'),list)
            or not restoration['targets']):
        raise ValueError('INVALID_ROLLBACK_RESTORATION_ORDER')
    targets=restoration['targets']
    if (any(not isinstance(target,str) for target in targets)
            or len(targets)!=len(set(targets))
            or len(targets)!=len(rendered)
            or set(targets)!=set(rendered)):
        raise ValueError('ROLLBACK_TARGET_SET_MISMATCH')
    release_root='/opt/xuanjun-control-releases/'+value['previous_release_directory']+'/'
    seen_backups=set()
    seen_targets=set()
    for target in targets:
        binding=rendered[target]
        canonical_target=os.path.normpath(target) if target.startswith('/') else None
        if (not isinstance(target,str) or not target.startswith('/')
                or canonical_target!=target or canonical_target in seen_targets
                or target.startswith('/opt/xuanjun-control-releases/')
                or not isinstance(binding,dict) or set(binding)!= {'sha256','backup_path'}
                or not SHA.fullmatch(binding.get('sha256',''))):
            raise ValueError('INVALID_ROLLBACK_FILE_BINDING')
        seen_targets.add(canonical_target)
        backup=binding.get('backup_path')
        canonical_backup=(os.path.normpath(backup)
                          if isinstance(backup,str) and backup.startswith('/') else None)
        if (not isinstance(backup,str) or not backup.startswith(release_root)
                or canonical_backup!=backup or canonical_backup in seen_backups):
            raise ValueError('INVALID_ROLLBACK_BACKUP_PATH')
        seen_backups.add(canonical_backup)
    return True


def restore_rollback_files(value,active_epoch,restore):
    """Invoke a restoration primitive in the receipt's validated exact order.

    The immutable tuple is captured before the first callback so a restoration
    primitive cannot alter the receipt to change later targets or bindings.
    Filesystem mutation and privilege checks remain the caller's responsibility.
    """
    validate_rollback_map(value,active_epoch)
    if not callable(restore):
        raise ValueError('INVALID_ROLLBACK_RESTORER')
    ordered=tuple(
        (target,value['rendered_files'][target]['backup_path'],
         value['rendered_files'][target]['sha256'])
        for target in value['restoration_order']['targets'])
    for target,backup_path,expected_sha256 in ordered:
        restore(target,backup_path,expected_sha256)
    return tuple(item[0] for item in ordered)


def read_manifest(path, expected_sha):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>1024*1024:
            raise ValueError('INVALID_MANIFEST_FILE')
        chunks=[]; value=hashlib.sha256()
        while True:
            chunk=os.read(fd,65536)
            if not chunk: break
            chunks.append(chunk); value.update(chunk)
        data=b''.join(chunks)
        if not SHA.fullmatch(expected_sha) or value.hexdigest()!=expected_sha:
            raise ValueError('MANIFEST_SHA256_MISMATCH')
        return json.loads(data.decode('utf-8')),data
    finally:
        os.close(fd)


def _git_identity(root):
    result=subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','rev-parse',
                           'HEAD','HEAD^{tree}','HEAD^'],cwd=root,
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                          timeout=10,check=False,
                          env={'HOME':'/nonexistent','PATH':'/usr/bin:/bin',
                               'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'})
    values=result.stdout.decode('ascii','replace').splitlines()
    if result.returncode or len(values)!=3:
        raise ValueError('GIT_ARTIFACT_IDENTITY_UNAVAILABLE')
    return tuple(values)


def verify(root, manifest_path, expected_source, expected_manifest_sha,
           expected_tree=None):
    if any(os.path.realpath(value)!=value for value in (root,manifest_path)):
        raise ValueError('CANONICAL_PATH_REQUIRED')
    # Hash and parse exactly the same bytes from one O_NOFOLLOW descriptor.
    manifest,manifest_bytes=read_manifest(manifest_path,expected_manifest_sha)
    if not re.fullmatch(r'[0-9a-f]{40}',expected_source):
        raise ValueError('SOURCE_COMMIT_MISMATCH')
    if manifest.get('schema')==1:
        if manifest.get('source_commit')!=expected_source:
            raise ValueError('SOURCE_COMMIT_MISMATCH')
    elif manifest.get('schema')==2:
        if (manifest.get('source_commit_policy')!='EXTERNAL_FROZEN_COMMIT'
                or not re.fullmatch(r'[0-9a-f]{40}',manifest.get('source_parent',''))
                or not re.fullmatch(r'[0-9a-f]{64}',manifest.get('contract_sha256',''))
                or not re.fullmatch(r'[0-9a-f]{40}',expected_tree or '')):
            raise ValueError('INVALID_EXTERNAL_COMMIT_BINDING')
        commit,tree,parent=_git_identity(root)
        if (commit!=expected_source or tree!=expected_tree
                or parent!=manifest['source_parent']):
            raise ValueError('FROZEN_GIT_IDENTITY_MISMATCH')
    else:
        raise ValueError('INVALID_MANIFEST_SCHEMA')
    files=manifest.get('files')
    if not isinstance(files,dict) or not files: raise ValueError('EMPTY_MANIFEST')
    for name,expected in files.items():
        if (not isinstance(name,str) or name.startswith('/') or '..' in name.split('/')
                or not SHA.fullmatch(expected)):
            raise ValueError('INVALID_MANIFEST_ENTRY')
        path=os.path.join(root,name)
        if os.path.islink(path) or not os.path.isfile(path) or digest(path)!=expected:
            raise ValueError('ARTIFACT_MISMATCH:'+name)
    if manifest.get('schema')==2:
        _validate_install_contract(manifest)
    return manifest,manifest_bytes


def smoke(root):
    for relative in ('stage1/development_service.py','stage1/owner_callback_server.py',
                     'stage1/owner_dashboard.py','stage1/root_broker.py',
                     'stage1/github_issue_consumer.py','stage1/ledger_service.py'):
        result=subprocess.run([sys.executable,os.path.join(root,relative),'--help'],
                              cwd=os.path.join(root,'stage1'),stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE,timeout=10,check=False)
        if result.returncode: raise ValueError('RUNTIME_CLOSURE_SMOKE_FAILED:'+relative)


def copy_verified(source,destination,expected,transform=None):
    source_fd=os.open(source,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    source_info=os.fstat(source_fd)
    if not stat.S_ISREG(source_info.st_mode):
        os.close(source_fd); raise ValueError('NOT_REGULAR_FILE')
    with os.fdopen(source_fd,'rb') as src:
        source_bytes=src.read()
    observed=hashlib.sha256(source_bytes)
    if observed.hexdigest()!=expected:
        raise ValueError('ARTIFACT_CHANGED_DURING_COPY')
    output=transform(source_bytes) if transform else source_bytes
    destination_fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
    with os.fdopen(destination_fd,'wb') as dst:
        dst.write(output); dst.flush(); os.fsync(dst.fileno())
    return hashlib.sha256(output).hexdigest()


def verify_rendered_release(staging,manifest,artifact_sha256,rendered_hashes):
    directory=release_identity(artifact_sha256)
    if set(rendered_hashes)!=set(manifest['files']):
        raise ValueError('INCOMPLETE_RENDERED_FILE_SET')
    for name,expected in rendered_hashes.items():
        if digest(os.path.join(staging,name))!=expected:
            raise ValueError('RENDERED_ARTIFACT_MISMATCH:'+name)
    for name in IDENTITY_RENDERED_FILES:
        with open(os.path.join(staging,name),'rb') as stream:
            data=stream.read()
        if any(token.encode() in data for token in IDENTITY_TOKENS):
            raise ValueError('UNRESOLVED_IDENTITY_PLACEHOLDER:'+name)
        if (name.endswith('.service')
                and ('/opt/xuanjun-control-releases/'+directory+'/').encode() not in data):
            raise ValueError('RELEASE_PATH_BINDING_MISMATCH:'+name)
    with open(os.path.join(staging,'deploy','dispatcher.example.json')) as stream:
        config=json.load(stream)
    if (config.get('release_sha256')!=artifact_sha256
            or config.get('broker_client')!='/opt/xuanjun-control-releases/'+directory+'/scripts/xj-root-broker-client'):
        raise ValueError('RUNTIME_ARTIFACT_BINDING_MISMATCH')
    renderer=manifest['required_renderers'][0]
    renderer_path=os.path.join(staging,renderer['path'])
    if (stat.S_IMODE(os.stat(renderer_path,follow_symlinks=False).st_mode)!=int(renderer['mode'],8)
            or digest(renderer_path)!=renderer['sha256']
            or renderer['target'].replace('@@RELEASE_DIRECTORY@@',directory)
               !='/opt/xuanjun-control-releases/'+directory+'/'+renderer['path']
            or renderer['invocation'][0].replace('@@RELEASE_DIRECTORY@@',directory)
               !='/opt/xuanjun-control-releases/'+directory+'/'+renderer['path']):
        raise ValueError('REQUIRED_RENDERER_INSTALL_MISMATCH')


def install(root,manifest_path,expected_source,expected_manifest_sha,releases,
            enforce_root=True,expected_tree=None):
    if enforce_root and os.geteuid()!=0: raise PermissionError('ROOT_INSTALL_REQUIRED')
    manifest,manifest_bytes=verify(root,manifest_path,expected_source,
                                   expected_manifest_sha,expected_tree)
    owner_uid=0 if enforce_root else os.geteuid()
    releases_fd=open_safe_release_root(releases,owner_uid)
    manifest_hash=digest(manifest_path)
    target_name=release_identity(manifest_hash)
    target=os.path.join(releases,target_name)
    try:
        os.stat(target_name,dir_fd=releases_fd,follow_symlinks=False)
        raise ValueError('RELEASE_ALREADY_EXISTS')
    except FileNotFoundError:
        pass
    staging_name,staging=make_staging(releases_fd,releases)
    try:
        rendered_hashes={}
        for name in sorted(manifest['files']):
            destination=os.path.join(staging,name)
            os.makedirs(os.path.dirname(destination),mode=0o750,exist_ok=True)
            source=os.path.join(root,name)
            transform=lambda data,n=name: render_identity_bytes(n,data,manifest_hash,manifest)
            try: rendered_hashes[name]=copy_verified(source,destination,manifest['files'][name],transform)
            except ValueError as error: raise ValueError(str(error)+':'+name)
        manifest_destination=os.path.join(staging,'INTEGRATION_MANIFEST.json')
        manifest_fd=os.open(manifest_destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
        with os.fdopen(manifest_fd,'wb') as output:
            output.write(manifest_bytes); output.flush(); os.fsync(output.fileno())
        executables=[os.path.join(staging,'scripts','xj-root-broker-client'),
                     os.path.join(staging,REQUIRED_RENDERER)]
        for executable in executables:
            os.chmod(executable,0o555)
            if os.stat(executable).st_mode & 0o022: raise ValueError('UNSAFE_HELPER_MODE')
        verify_rendered_release(staging,manifest,manifest_hash,rendered_hashes)
        smoke(staging)
        if enforce_root:
            for directory,dirs,files in os.walk(staging):
                os.chown(directory,0,0); os.chmod(directory,0o555)
                for name in files:
                    path=os.path.join(directory,name); os.chown(path,0,0)
                    os.chmod(path,0o555 if path in executables else 0o444)
        path_info=os.stat(releases,follow_symlinks=False)
        fd_info=os.fstat(releases_fd)
        if (path_info.st_dev,path_info.st_ino)!=(fd_info.st_dev,fd_info.st_ino):
            raise ValueError('RELEASE_ROOT_CHANGED')
        os.rename(staging_name,target_name,src_dir_fd=releases_fd,
                  dst_dir_fd=releases_fd)
        os.fsync(releases_fd)
    finally:
        if os.path.isdir(staging): shutil.rmtree(staging)
        os.close(releases_fd)
    return target


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True); parser.add_argument('--manifest',required=True)
    parser.add_argument('--source-commit',required=True); parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--source-tree')
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--releases')
    args=parser.parse_args(argv)
    if args.verify_only:
        verify(args.root,args.manifest,args.source_commit,args.manifest_sha256,args.source_tree); print('MANIFEST_OK'); return 0
    if not args.releases: parser.error('install requires --releases')
    print(install(args.root,args.manifest,args.source_commit,args.manifest_sha256,args.releases,
                  expected_tree=args.source_tree)); return 0


if __name__=='__main__': sys.exit(main())
