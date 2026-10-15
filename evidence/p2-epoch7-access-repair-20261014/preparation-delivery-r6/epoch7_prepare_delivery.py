#!/usr/bin/env python3
"""Observation-bound r6 preparation delivery. No installation or approval operation."""
import argparse,contextlib,errno,hashlib,json,os,re,signal,socket,stat,sys,time,types,urllib.request

PINS_BOUND=True
PUBLICATION_COMMIT='e8b9ebb3fb215fa5b1ef0a8dc0b31a77efd0ab67'
RAW_PREFIX='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'
PUBLIC_PREFIX='evidence/p2-epoch7-access-repair-20261014/preparation-source-r6/'
CAND='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
PREP_ROOT=CAND+'/epoch7-preparation-candidate-r6'
OBSERVATION_PATH=CAND+'/epoch7-observation-1311b9e9fa97cfd4.private.json'
OBSERVATION_SHA256='b961df049e2861e4706f28f29fcf994a14fe28e153263a23ec82d4e822b9b246'
HOST='iZd7oeikknn1z21sq6ji6zZ'
SOURCES={
 'epoch7_prepare.py':('83c218fc10d19094446494e10767be58593f09dbc92866cbc8779d9a0e776ebc',41352),
 'epoch7_prepare_data.py':('71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1',13888),
 'epoch7_topology_projection.py':('f8b731a8668a5b5374e18dab9a59657f80fc8d11ea2d9c4588a62942dbf74854',27151)}
STAGE_SECONDS=60
STATUS_SECONDS=5
PHASE='INPUT_VALIDATION'
CODES=frozenset(('UNBOUND','OBSERVATION_BINDING','ARGUMENTS','ROOT_HOST','ISOLATED','SOURCE_SET','SOURCE_PIN','RESPONSE',
 'REDIRECT','ENCODING','LENGTH','DEADLINE','EXISTING_TIMER','ANCESTRY','XATTR','PATH_RACE','PARENT_NAMES',
 'DIRECTORY','INVENTORY','FILE_AUTHORITY','FILE_RACE','FILE_BYTES','SHORT_WRITE','OWNED_PARENT','STATUS_BOUND'))

class Hold(ValueError):pass
class DeadlineError(Exception):pass
class CleanupError(Exception):pass
class StatusDeliveryError(Exception):pass

def need(value,code):
    if not value:raise Hold(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp(info):return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
def check(end):need(time.monotonic()<end,'DEADLINE')
def no_attributes(fd):
    for key in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
        try:os.getxattr(fd,key)
        except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP),'XATTR')
        else:raise Hold('XATTR')
def close_all(fds,primary=None):
    failed=False
    for fd in reversed(fds):
        try:os.close(fd)
        except BaseException:failed=True
    if failed:
        if primary is None:raise CleanupError()
        primary.delivery_cleanup_failed=True

@contextlib.contextmanager
def budget(seconds):
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'EXISTING_TIMER')
    old=signal.getsignal(signal.SIGALRM);end=time.monotonic()+seconds;primary=None
    def expired(unused_signum,unused_frame):raise DeadlineError()
    try:
        signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,seconds,.1)
        yield end;check(end)
    except BaseException as error:primary=error;raise
    finally:
        failed=False
        try:signal.setitimer(signal.ITIMER_REAL,0)
        except BaseException:failed=True
        try:signal.signal(signal.SIGALRM,old)
        except BaseException:failed=True
        if failed:
            if primary is None:raise CleanupError()
            primary.delivery_cleanup_failed=True

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise Hold('REDIRECT')

def bound():
    need(PINS_BOUND is True and type(PUBLICATION_COMMIT) is str and re.fullmatch('[0-9a-f]{40}',PUBLICATION_COMMIT),'UNBOUND')

def validate_sources(cache):
    need(type(cache) is dict and set(cache)==set(SOURCES),'SOURCE_SET')
    for name,(digest,size) in SOURCES.items():
        need(type(cache[name]) is bytes and len(cache[name])==size and sha(cache[name])==digest,'SOURCE_PIN')
    return cache

def fetch_sources(end):
    bound();cache={}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    for name,(digest,size) in sorted(SOURCES.items()):
        check(end);url=RAW_PREFIX+PUBLICATION_COMMIT+'/'+PUBLIC_PREFIX+name
        request=urllib.request.Request(url,headers={'Accept-Encoding':'identity'})
        response=None;primary=None
        try:
            response=opener.open(request,timeout=min(10,max(.001,end-time.monotonic())))
            need(response.status==200 and response.geturl()==url,'RESPONSE')
            need(response.headers.get('Content-Encoding','identity')=='identity','ENCODING')
            length=response.headers.get('Content-Length');need(length is None or length==str(size),'LENGTH')
            raw=response.read(size+1);check(end)
            need(len(raw)==size and sha(raw)==digest,'SOURCE_PIN');cache[name]=raw
        except BaseException as error:primary=error;raise
        finally:
            if response is not None:
                try:response.close()
                except BaseException:
                    if primary is None:raise CleanupError()
                    primary.delivery_cleanup_failed=True
    check(end);return validate_sources(cache)

def authority(fd,mode=None):
    info=os.fstat(fd)
    need(stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==0 and not info.st_mode&0o7022 and
         (mode is None or stat.S_IMODE(info.st_mode)==mode),'ANCESTRY')
    no_attributes(fd);return stamp(info)

def names(fd,maximum):
    row=os.listdir(fd);need(len(row)<=maximum and len(row)==len(set(row)) and all(type(v) is str and 0<len(v)<=255 and '/' not in v and '\x00' not in v for v in row),'PARENT_NAMES')
    return tuple(sorted(row))

def parent_walk(held,end):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);held.append(fd)
    rows=[(fd,None,None,'/',authority(fd))];path=''
    for name in CAND[1:].split('/'):
        check(end);parent=fd;path+='/'+name
        fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);held.append(fd)
        row=authority(fd);need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==row,'PATH_RACE')
        rows.append((fd,parent,name,path,row))
    return rows

def recheck_parents(rows,parent_after):
    for fd,parent,name,path,before in rows:
        actual=authority(fd);wanted=parent_after if path==CAND else before
        need(actual==wanted,'PATH_RACE')
        if parent is not None:need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==actual,'PATH_RACE')

def read_file(directory,name,raw,end):
    check(end);before=os.stat(name,dir_fd=directory,follow_symlinks=False);fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory);primary=None
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink,info.st_size)==(0,0,0o600,1,len(raw)),'FILE_AUTHORITY')
        need(stamp(before)==stamp(info),'FILE_RACE');no_attributes(fd);parts=[];count=0
        while True:
            check(end);part=os.read(fd,min(16384,len(raw)+1-count))
            if not part:break
            count+=len(part);need(count<=len(raw),'FILE_BYTES');parts.append(part)
        need(b''.join(parts)==raw,'FILE_BYTES');no_attributes(fd)
        need(stamp(os.fstat(fd))==stamp(info)==stamp(os.stat(name,dir_fd=directory,follow_symlinks=False)),'FILE_RACE')
        check(end);return stamp(info)
    except BaseException as error:primary=error;raise
    finally:close_all([fd],primary)

def stage(cache,end,allow_create=True):
    """Exclusive fixed directory; a partial attempt is retained and reported."""
    validate_sources(cache);need(os.geteuid()==os.getegid()==0,'ROOT_HOST')
    held=[];created=[];primary=None;result=None
    try:
        rows=parent_walk(held,end);parent=rows[-1][0];parent_before=rows[-1][4];before_names=names(parent,1024)
        need(authority(parent)==parent_before,'PATH_RACE');leaf='epoch7-preparation-candidate-r6'
        try:before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:
            need(allow_create is True,'DIRECTORY')
            check(end);os.mkdir(leaf,0o700,dir_fd=parent);created.append(PREP_ROOT);before=os.stat(leaf,dir_fd=parent,follow_symlinks=False);new=True
        else:new=False
        need(stat.S_ISDIR(before.st_mode),'DIRECTORY')
        directory=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);held.append(directory)
        start=authority(directory,0o700);need(stamp(before)==start,'PATH_RACE')
        need(names(directory,3)==(() if new else tuple(sorted(SOURCES))),'INVENTORY')
        if new:
            for name in sorted(SOURCES):
                check(end);raw=cache[name];fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory);created.append(PREP_ROOT+'/'+name);file_primary=None
                try:
                    info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o600,1),'FILE_AUTHORITY');no_attributes(fd)
                    offset=0
                    while offset<len(raw):
                        check(end);count=os.write(fd,raw[offset:offset+16384]);need(type(count) is int and 0<count<=min(16384,len(raw)-offset),'SHORT_WRITE');offset+=count
                    os.fsync(fd);check(end)
                except BaseException as error:file_primary=error;raise
                finally:close_all([fd],file_primary)
            os.fsync(directory);os.fsync(parent);check(end)
        current=authority(directory,0o700)
        need(current[:6]==start[:6] and (new or current==start),'DIRECTORY')
        expected_names=tuple(sorted(SOURCES));need(names(directory,3)==expected_names,'INVENTORY')
        observed={name:read_file(directory,name,cache[name],end) for name in sorted(SOURCES)}
        for name in sorted(SOURCES):need(stamp(os.stat(name,dir_fd=directory,follow_symlinks=False))==observed[name],'FILE_RACE')
        need(authority(directory,0o700)==current and names(directory,3)==expected_names and
             stamp(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==current,'PATH_RACE')
        parent_after=authority(parent)
        if new:
            need(parent_after[:5]==parent_before[:5] and parent_after[5]==parent_before[5]+1 and names(parent,1024)==tuple(sorted(before_names+(leaf,))),'OWNED_PARENT')
        else:need(parent_after==parent_before and names(parent,1024)==before_names,'OWNED_PARENT')
        recheck_parents(rows,parent_after);check(end)
        result={'state':'STAGED_EXACT' if new else 'REUSED_EXACT','path':PREP_ROOT,
                'files':{name:{'sha256':SOURCES[name][0],'bytes':SOURCES[name][1]} for name in sorted(SOURCES)},'created_paths':list(created)}
        return result
    except BaseException as error:primary=error;error.delivery_created_paths=list(created);raise
    finally:
        try:close_all(held,primary)
        except BaseException as error:error.delivery_created_paths=list(created);raise

def preparer(cache):
    validate_sources(cache);module=types.ModuleType('verified_epoch7_preparer');module.__file__=PREP_ROOT+'/epoch7_prepare.py'
    exec(compile(cache['epoch7_prepare.py'],module.__file__,'exec'),module.__dict__);return module

def deliver_status(value):
    try:
        with budget(STATUS_SECONDS) as end:
            raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
            need(len(raw)<=131072,'STATUS_BOUND');offset=0
            while offset<len(raw):
                check(end);count=os.write(1,raw[offset:offset+16384]);need(type(count) is int and 0<count<=min(16384,len(raw)-offset),'SHORT_WRITE');offset+=count
            check(end)
    except BaseException:raise StatusDeliveryError() from None

def run(argv=None):
    global PHASE
    PHASE='INPUT_VALIDATION'
    class Parser(argparse.ArgumentParser):
        def error(self,unused):raise Hold('ARGUMENTS')
    parser=Parser(add_help=False);parser.add_argument('--observation',required=True);parser.add_argument('--observation-sha256',required=True);args=parser.parse_args(argv)
    bound()
    need(type(args.observation) is str and os.path.dirname(args.observation)==CAND and re.fullmatch('epoch7-observation-[0-9a-f]{16}\\.private\\.json',os.path.basename(args.observation)) and re.fullmatch('[0-9a-f]{64}',args.observation_sha256),'ARGUMENTS')
    need(args.observation==OBSERVATION_PATH and args.observation_sha256==OBSERVATION_SHA256,'OBSERVATION_BINDING')
    need(os.geteuid()==os.getegid()==0 and socket.gethostname()==HOST,'ROOT_HOST')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'ISOLATED')
    staged=None;module=None
    try:
        with budget(STAGE_SECONDS) as end:
            PHASE='DOWNLOAD_ALL';cache=fetch_sources(end)
            PHASE='LOAD_VERIFIED_PREPARER';module=preparer(cache);check(end)
            PHASE='STAGE_EXACT';staged=stage(cache,end)
        PHASE='PROPOSE_TOPOLOGY'
        proposal_args=types.SimpleNamespace(operation='propose-topology',observation=args.observation,
            observation_sha256=args.observation_sha256,topology_review_id=None,retained_renewal_timer=None)
        with module.budget() as end:
            proposal=module.run_preparation(proposal_args,end)
            # The proposal is returned only while the complete fixed staging
            # inventory still equals the originally downloaded source bytes.
            stage(cache,end,allow_create=False)
        result={'schema':1,'state':'TOPOLOGY_REVIEW_REQUIRED','staging':staged,'proposal':proposal,
                'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
    except BaseException as error:
        if module is not None and isinstance(error,module.CleanupError):error.delivery_cleanup_failed=True
        if staged is not None:error.delivery_created_paths=staged['created_paths'];error.delivery_staging=staged
        raise
    PHASE='DELIVER_STATUS';deliver_status(result);return 0

def entrypoint(argv=None):
    try:return run(argv)
    except StatusDeliveryError:return 2
    except BaseException as error:
        label=error.args[0] if type(error) is Hold and len(error.args)==1 and type(error.args[0]) is str and error.args[0] in CODES else None
        status={'state':'HOLD','phase':PHASE,'failure_code':type(error).__name__,'failure_label':label,
            'created_paths':getattr(error,'delivery_created_paths',[]),'staging':getattr(error,'delivery_staging',None),
            'cleanup_unknown':isinstance(error,CleanupError) or bool(getattr(error,'delivery_cleanup_failed',False)) or bool(getattr(error,'preparation_cleanup_failed',False)),
            'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
        try:deliver_status(status)
        except StatusDeliveryError:pass
        return 2

if __name__=='__main__':sys.exit(entrypoint())
