"""Pinned P2 delivery preparation; never starts installation or a Writer.

Run as root only on the exact UK host. Missing live deployment bindings are
reported after safe staging, never replaced by a new database or synthetic facts.
"""
import datetime
import fcntl
import gzip
import hashlib
import io
import json
import os
import signal
import stat
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

HOST='iZd7oeikknn1z21sq6ji6zZ'
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
COMMIT='6041c7458dce7c83c49c5a9eafa0e20cef52d1c0'
TREE='8e27d077d22af392108568ac06d284df4dd4b35e'
ARTIFACT=12142409951
ZIP_SHA='09f1cb686238290895b395e05cbe9f4fda543d6295e23e0a17e40951d65ecf0b'
MANIFEST_SHA='255009f44680dffd2d928375b2a815f4abe09dc9fb058d4bff196553d41d1fde'
BUNDLE_SHA='05783f3693371840455f7f5e90a54480a7ccf93d33643d416dda16801895f206'
KIT_SHA='2fdc934a336414086361764a4a77894a597a51a53c7693420eaed5cefed3e1d3'
KIT_MANIFEST_SHA='243bc01b1e9c7d2cb302f800556002abcebcfa9f96c298e4275e15d8b1346e1e'
ROOT='/opt/xuanjun-p2-owner-delivery'
LOCAL_ZIP='/var/tmp/p2-12142409951.zip'
LIMIT=32*1024*1024

class Hold(RuntimeError):pass
def need(ok,code):
    if not ok:raise Hold(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode('ascii')
def decode(raw):
    def pairs(items):
        value={}
        for key,item in items:
            need(key not in value,'DUPLICATE_JSON_KEY');value[key]=item
        return value
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,
        parse_constant=lambda unused:need(False,'NONFINITE_JSON'))
def relative(name):
    need(type(name) is str and not name.startswith('/') and
        all(p not in ('','.','..') for p in name.split('/')) and
        '\\' not in name and not any(ord(c)<32 or ord(c)==127 for c in name),
        'ARCHIVE_PATH')
    return name
def read_bound(stream,maximum):
    raw=stream.read(maximum+1)
    need(len(raw)<=maximum,'INPUT_TOO_LARGE')
    return raw
def timeout(signum,frame):raise Hold('NETWORK_TIMEOUT')
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def download():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    endpoint='https://api.github.com/repos/'+REPO+'/actions/artifacts/'+str(ARTIFACT)+'/zip'
    token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    headers={'User-Agent':'xuanjun-p2-pinned-delivery','Accept':'application/vnd.github+json'}
    if token:headers['Authorization']='Bearer '+token
    old=signal.signal(signal.SIGALRM,timeout);signal.alarm(90)
    try:
        try:
            response=opener.open(urllib.request.Request(endpoint,headers=headers),timeout=20)
        except urllib.error.HTTPError as error:
            need(error.code in (301,302,303,307,308),
                'ARTIFACT_DOWNLOAD_AUTH_OR_AVAILABILITY_REQUIRED')
            target=error.headers.get('Location','')
            parsed=urllib.parse.urlsplit(target);host=parsed.hostname or ''
            need(parsed.scheme=='https' and parsed.port in (None,443) and
                 not parsed.username and not parsed.password and len(target)<=16384 and
                 (host.endswith('.blob.core.windows.net') or host.endswith('.actions.githubusercontent.com')),
                 'DOWNLOAD_REDIRECT_REJECTED')
            # Never forward the GitHub token to artifact blob storage.
            response=opener.open(urllib.request.Request(target,
                headers={'User-Agent':'xuanjun-p2-pinned-delivery'}),timeout=20)
        with response:
            need(response.getcode()==200,'ARTIFACT_HTTP_STATUS')
            raw=read_bound(response,8*1024*1024)
        need(sha(raw)==ZIP_SHA,'ZIP_SHA_MISMATCH')
        return raw
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,old)
def acquire():
    try:fd=os.open(LOCAL_ZIP,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except FileNotFoundError:return download()
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
             before.st_size<=8*1024*1024,'LOCAL_ARCHIVE_TYPE')
        raw=os.read(fd,8*1024*1024+1);after=os.fstat(fd)
        stamp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        need(stamp(before)==stamp(after) and len(raw)==before.st_size,'LOCAL_ARCHIVE_RACE')
        need(sha(raw)==ZIP_SHA,'ZIP_SHA_MISMATCH')
        return raw
    finally:os.close(fd)
def tar_rows(raw,prefix=''):
    plain=read_bound(gzip.GzipFile(fileobj=io.BytesIO(raw)),LIMIT)
    result={}
    with tarfile.open(fileobj=io.BytesIO(plain),mode='r:') as archive:
        for item in archive:
            need(len(result)<1024 and item.isfile() and
                 0<=item.size<=4*1024*1024,'TAR_MEMBER_TYPE_OR_BOUND')
            name=relative(item.name)
            if prefix:
                need(name.startswith(prefix),'KIT_PREFIX')
                name=relative(name[len(prefix):])
            need(name not in result,'DUPLICATE_TAR_MEMBER')
            result[name]=archive.extractfile(item).read()
    return result
def verify(raw):
    need(sha(raw)==ZIP_SHA,'ZIP_SHA_MISMATCH')
    expected={'MANIFEST.json','production-assembly.tar.gz','attempt5-kit.tar.gz',
        'attempt5-manifest.json','SHA256SUMS'}|{'tests-%d.log'%i for i in range(7)}
    rows={}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for item in archive.infolist():
            relative(item.filename)
            need(item.filename in expected and item.filename not in rows and
                 item.file_size<=4*1024*1024 and
                 stat.S_IFMT(item.external_attr>>16) in (0,stat.S_IFREG),
                 'ZIP_MEMBER_TYPE_OR_BOUND')
            rows[item.filename]=archive.read(item)
    need(set(rows)==expected,'ZIP_INVENTORY')
    for name,pin in [('MANIFEST.json',MANIFEST_SHA),('production-assembly.tar.gz',BUNDLE_SHA),
        ('attempt5-kit.tar.gz',KIT_SHA),('attempt5-manifest.json',KIT_MANIFEST_SHA)]:
        need(sha(rows[name])==pin,'ARTIFACT_MEMBER_SHA')
    sums=rows['SHA256SUMS'].decode('ascii').splitlines()
    need(set(sums)=={MANIFEST_SHA+'  MANIFEST.json',BUNDLE_SHA+'  production-assembly.tar.gz',
        KIT_SHA+'  attempt5-kit.tar.gz',KIT_MANIFEST_SHA+'  attempt5-manifest.json'} and len(sums)==4,
        'SHA256SUMS_BINDING')
    manifest=decode(rows['MANIFEST.json'])
    need(manifest['source_commit']==COMMIT and manifest['source_tree']==TREE and
         manifest['runtime_kit_sha256']==KIT_SHA and manifest['runtime_manifest_sha256']==KIT_MANIFEST_SHA,
         'SOURCE_BINDING')
    bundle=tar_rows(rows['production-assembly.tar.gz'])
    need(set(bundle)==set(manifest['files'])|{'MANIFEST.json'}|
         {'tests-%d.log'%i for i in range(7)},'BUNDLE_INVENTORY')
    need(bundle['MANIFEST.json']==rows['MANIFEST.json'],'BUNDLE_MANIFEST')
    for name,pin in manifest['files'].items():
        relative(name);need(sha(bundle[name])==pin,'SOURCE_FILE_SHA')
    for i,group in enumerate(manifest['groups']):
        name='tests-%d.log'%i
        need(bundle[name]==rows[name] and sha(rows[name])==group['log_sha256'],'TEST_LOG_SHA')
    kit=tar_rows(rows['attempt5-kit.tar.gz'],'epoch7-attempt5-candidate-v1/')
    km=decode(rows['attempt5-manifest.json'])
    need(kit['attempt5-manifest.json']==rows['attempt5-manifest.json'] and
         km['source_commit']==COMMIT and km['source_tree']==TREE and
         set(kit)==set(km['files'])|{'attempt5-manifest.json'} and
         len(km['inherited_files'])==257,'KIT_BINDING')
    for name,pin in km['files'].items():
        relative(name);need(sha(kit[name])==pin,'KIT_FILE_SHA')
    need(all(name.startswith('legacy/') and km['files'].get(name)==pin
        for name,pin in km['inherited_files'].items()),'LEGACY_INHERITANCE')
    return rows,bundle,kit
def directory(path,create=False):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.strip('/').split('/'):
            if create:
                try:os.mkdir(part,0o700,dir_fd=fd);os.fsync(fd)
                except FileExistsError:pass
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child;info=os.fstat(fd)
            need(info.st_uid==0 and not info.st_mode&0o022,'OUTPUT_PARENT_PROTECTION')
            for name in ('system.posix_acl_access','system.posix_acl_default'):
                try:acl=os.getxattr(fd,name)
                except OSError as e:
                    if e.errno not in (61,95):raise
                else:need(acl is None,'OUTPUT_PARENT_ACL')
        return fd
    except BaseException:os.close(fd);raise
def write(root,name,raw):
    relative(name)
    parent=os.path.dirname(name)
    fd=directory(root+('/'+parent if parent else ''),create=True)
    try:
        out=os.open(name.rsplit('/',1)[-1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:
            view=memoryview(raw)
            while view:
                count=os.write(out,view);need(count>0,'SHORT_WRITE');view=view[count:]
            os.fsync(out)
        finally:os.close(out)
        os.fsync(fd)
    finally:os.close(fd)
def stage(raw,root):
    rows,bundle,kit=verify(raw)
    base=directory(root,create=True)
    lock=os.open('.delivery.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=base)
    try:
        info=os.fstat(lock)
        need(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and
             stat.S_IMODE(info.st_mode)==0o600,'DELIVERY_LOCK_IDENTITY')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:os.mkdir(COMMIT,0o700,dir_fd=base);os.fsync(base)
        except FileExistsError:raise Hold('VERSION_DIRECTORY_EXISTS_RETAINED_NO_OVERWRITE')
        version=root+'/'+COMMIT
        write(version,'artifact.zip',raw)
        for name,body in rows.items():write(version,'artifact/'+name,body)
        for name,body in bundle.items():write(version,'assembly/'+name,body)
        for name,body in kit.items():write(version,'kit/'+name,body)
        receipt={'schema':1,'state':'PREPARED_NOT_INSTALLED','source_commit':COMMIT,
            'source_tree':TREE,'artifact':ARTIFACT,'zip_sha256':ZIP_SHA,'kit_sha256':KIT_SHA,
            'kit_manifest_sha256':KIT_MANIFEST_SHA,'assembly_root':version+'/assembly',
            'kit_root':version+'/kit','install_executed':False,'writer_started':False,
            'authority_store_opened':False,'grant_registered':False}
        write(version,'PREPARATION_RECEIPT.json',canonical(receipt))
        return receipt
    finally:os.close(lock);os.close(base)
def observe():
    # Fixed new-component metadata only; never opens private config or database.
    result={}
    for path in ('/etc/xuanjun-p2/registry','/etc/xuanjun-p2/registry/.registry-commits.sqlite3'):
        try:
            info=os.lstat(path)
            result[path]={'present':True,'symlink':stat.S_ISLNK(info.st_mode),
                'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}
        except FileNotFoundError:result[path]={'present':False}
        except OSError:result[path]={'state':'UNKNOWN_METADATA_ERROR'}
    return result
def main():
    need(os.getuid()==os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST,'FIXED_UK_ROOT_REQUIRED')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'ISOLATED_PYTHON_REQUIRED')
    os.umask(0o077)
    logroot='/var/log/xuanjun-p2-owner-delivery'
    fd=directory(logroot,create=True);os.close(fd)
    ident=datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')+'-'+str(os.getpid())
    name=ident+'.json'
    started=time.time()
    try:
        result=stage(acquire(),ROOT)
        result.update(component_metadata=observe(),status='HOLD_INSTALL_BINDINGS_NOT_AVAILABLE',
            next_action='USE_REAL_EXISTING_AUTHORITY_STORE_AND_SIGNER_CONFIG_NO_INITIALIZATION')
        code=2
    except Exception as error:
        reason=str(error) if isinstance(error,Hold) else type(error).__name__
        result={'status':'HOLD','reason':reason,'install_executed':False,
            'preserve_outputs':True,'next_action':(
                'UPLOAD_EXACT_ARTIFACT_TO_'+LOCAL_ZIP if
                reason=='ARTIFACT_DOWNLOAD_AUTH_OR_AVAILABILITY_REQUIRED' else
                'RETAIN_THIS_RECEIPT_AND_EXISTING_OUTPUTS_DO_NOT_RESET_OR_RETRY_UNKNOWN_INSTALL')}
        code=2
    result.update(source_commit=COMMIT,elapsed_seconds=round(time.time()-started,3),
        receipt_path=logroot+'/'+name)
    write(logroot,name,canonical(result))
    print(json.dumps(result,sort_keys=True))
    return code
if __name__=='__main__':
    sys.exit(main())
