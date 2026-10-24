"""Proposed protected root carrier; verify/load definitions only, never update.

Not installed by this author. Future original root caller must separately bind
real approval/current/backup and explicitly invoke the reviewed composition.
"""
import hashlib
import json
import os
import re
import stat
import sys
import types

INSTALL_ROOT='/opt/xuanjun-community-preview/control-oci2330-v1'
ROOT_ANCHOR='/'
ROOT_UID=0
HOST='iZd7oeikknn1z21sq6ji6zZ'
MODULES=('community_preview_release_plan','community_preview_upgrade','community_preview_version_inspect',
         'community_preview_update_checkpoint','community_preview_update_composition')
PATHS={'loader.py','deploy/community-preview/f131-image-receipt.json'}|{'scripts/'+n+'.py' for n in MODULES}
class Hold(RuntimeError):pass


def identity(value):
    return (value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid,value.st_size,
            value.st_nlink,value.st_mtime_ns,value.st_ctime_ns)  # reads may update atime


def read_file(relative):
    if relative not in PATHS|{'manifest.json'}:raise Hold('FIXED_CARRIER_FILE_ONLY')
    fd=os.open(ROOT_ANCHOR,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        anchor=os.fstat(fd)
        if anchor.st_uid!=ROOT_UID or anchor.st_mode&0o022:raise Hold('PROTECTED_ROOT_ANCHOR_REQUIRED')
        parts=(INSTALL_ROOT+'/'+relative).split('/')[1:]
        for index,part in enumerate(parts[:-1]):
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child;s=os.fstat(fd)
            if s.st_uid!=ROOT_UID or s.st_mode&0o022:raise Hold('PROTECTED_ROOT_PARENT_REQUIRED')
            if index>=len(INSTALL_ROOT.split('/'))-2 and stat.S_IMODE(s.st_mode)!=0o700:raise Hold('PRIVATE_CARRIER_DIRECTORY_REQUIRED')
        before=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)
        f=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(f,'rb') as stream:
            s=os.fstat(stream.fileno())
            if (not stat.S_ISREG(s.st_mode) or s.st_uid!=ROOT_UID or stat.S_IMODE(s.st_mode)!=0o600
                    or s.st_nlink!=1 or s.st_size>131072 or identity(before)!=identity(s)):raise Hold('PROTECTED_CARRIER_FILE_REQUIRED')
            raw=stream.read(131073)
            if len(raw)!=s.st_size or identity(os.fstat(stream.fileno()))!=identity(s):raise Hold('CARRIER_FILE_CHANGED')
        if identity(os.stat(parts[-1],dir_fd=fd,follow_symlinks=False))!=identity(before):raise Hold('CARRIER_PATH_REPLACED')
        return raw
    finally:os.close(fd)


def load(manifest_sha256):
    if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=HOST:raise Hold('EXACT_ROOT_HOST_REQUIRED')
    if type(manifest_sha256) is not str or re.fullmatch('[0-9a-f]{64}',manifest_sha256) is None:raise Hold('REVIEWED_MANIFEST_DIGEST_REQUIRED')
    if 'scripts' in sys.modules:raise Hold('ISOLATED_PROCESS_REQUIRED')
    raw=read_file('manifest.json')
    if hashlib.sha256(raw).hexdigest()!=manifest_sha256:raise Hold('CARRIER_MANIFEST_CHANGED')
    manifest=json.loads(raw)
    if (type(manifest) is not dict or set(manifest)!={'format','install_root','files','updates_enabled'}
            or type(manifest['format']) is not int or manifest['format']!=1 or manifest['install_root']!=INSTALL_ROOT
            or manifest['updates_enabled'] is not False or type(manifest['files']) is not dict or set(manifest['files'])!=PATHS):
        raise Hold('EXACT_CARRIER_MANIFEST_REQUIRED')
    sources={}
    for path,meta in manifest['files'].items():
        if (type(meta) is not dict or set(meta)!={'sha256','bytes','uid','mode'} or meta['uid']!=0 or type(meta['uid']) is not int
                or meta['mode']!='0600' or type(meta['bytes']) is not int or not 0<meta['bytes']<=131072
                or type(meta['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',meta['sha256']) is None):raise Hold('CARRIER_ENTRY_REQUIRED')
        body=read_file(path)
        if len(body)!=meta['bytes'] or hashlib.sha256(body).hexdigest()!=meta['sha256']:raise Hold('CARRIER_SOURCE_CHANGED')
        sources[path]=body
    # All hashes verified before any module definition executes. No sys.path,
    # unprotected cwd, credentials or installed site package may supply code.
    package=types.ModuleType('scripts');package.__path__=[];sys.modules['scripts']=package
    try:
        for name in MODULES:
            full='scripts.'+name;m=types.ModuleType(full);m.__package__='scripts';m.__file__=INSTALL_ROOT+'/scripts/'+name+'.py'
            sys.modules[full]=m;setattr(package,name,m)
            exec(compile(sources['scripts/'+name+'.py'],m.__file__,'exec'),m.__dict__)
        return package.community_preview_update_composition
    except BaseException:
        for name in MODULES:sys.modules.pop('scripts.'+name,None)
        sys.modules.pop('scripts',None);raise


if __name__=='__main__':
    print('{"state":"ROOT_CARRIER_DEFAULT_DISABLED_EXPLICIT_REVIEW_REQUIRED","site_updated":false}')
    raise SystemExit(2)
