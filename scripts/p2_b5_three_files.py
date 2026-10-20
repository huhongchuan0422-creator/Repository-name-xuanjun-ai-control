"""Fixed retained-archive reader. Python3.6, no network/Node/extractall/live-tree walk."""
import hashlib,io,json,os,posixpath,pwd,re,resource,signal,stat,sys,tarfile,time
HOST='iZd7oeikknn1z21sq6ji6zZ'
SOURCE='/var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020/uid1002'
ROOT='home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/'
PINS={'tar_bytes':559237632,'tar_sha256':'e6d3a3cef96ee996eb4b130fb0bd9305438489326b85678a263998602413e485',
 'manifest_bytes':5635704,'manifest_sha256':'cdd3c80360af8b4227d166d8ba643ed534055ea79a75b46dcd345c3e86fb52ba','members':20000,
 'targets':{'package.json':(145276,'214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95'),
 'dist/loader-runtime-load-DpgEqnzx.mjs':(273593,'3c30c5d43fb3cd19525853bb6b756cf45cfd05f5da32a732dc129b85cb309787'),
 'dist/context-DyPstb2Q.mjs':(176,'db7fc7539455da0c564d4ded0d04da1c764a46903d1632489b8bd04641098320')}}
MAX_MANIFEST=8*1024*1024;MAX_TAR=600*1024*1024;MAX_PAYLOAD=512*1024*1024
MAX_MEMBER=128*1024*1024;MAX_MEMBERS=20000;MAX_PAX=65536;MAX_SMALL=1024*1024
OUTPUT_NAME='p2-b5-three-files-gnu-v2-20261020'
class Hold(Exception):pass

def need(ok,code):
    if not ok:raise Hold(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf8')
def identity(s):return tuple(getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_size','st_nlink','st_mtime_ns','st_ctime_ns'))
def unique(pairs):
    result={}
    for k,v in pairs:need(k not in result,'DUPLICATE_JSON_KEY');result[k]=v
    return result

def safe_name(name):
    need(isinstance(name,str) and 0<len(name.encode('utf8'))<=4096,'PATH_BOUND')
    need(not name.startswith('/') and '\\' not in name and all(p not in ('','.','..') for p in name.split('/')),'UNSAFE_PATH')
    need(all(ord(c)>=32 and ord(c)!=127 for c in name),'PATH_CONTROL')
    return name

class PinnedFile:
    """Keep parent FDs; root verifies path binding again after the child finishes."""
    def __init__(self,path,allowed_uids):
        need(path.startswith('/') and posixpath.normpath(path)==path,'INPUT_ABSOLUTE_PATH')
        self.fd=None;self.parents=[];self.nodes=[]
        current=os.open('/',os.O_RDONLY|os.O_DIRECTORY);self.parents.append(current)
        try:
            parts=path.strip('/').split('/')
            for index,name in enumerate(parts):
                last=index==len(parts)-1
                flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
                if not last:flags|=os.O_DIRECTORY
                nxt=os.open(name,flags,dir_fd=current);s=os.fstat(nxt)
                need(s.st_uid in allowed_uids and not s.st_mode&0o022,'UNPROTECTED_INPUT')
                need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 if last else stat.S_ISDIR(s.st_mode),'INPUT_TYPE')
                self.nodes.append((current,name,identity(s)))
                if last:self.fd=nxt;self.before=identity(s)
                else:self.parents.append(nxt);current=nxt
        except BaseException:self.close();raise
    def check(self):
        need(identity(os.fstat(self.fd))==self.before,'INPUT_FD_CHANGED')
        for parent,name,before in self.nodes:
            need(identity(os.stat(name,dir_fd=parent,follow_symlinks=False))==before,'INPUT_PATH_CHANGED')
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None
        for fd in self.parents:os.close(fd)
        self.parents=[]

def hash_fd(fd,size):
    need(os.fstat(fd).st_size==size,'INPUT_SIZE')
    os.lseek(fd,0,os.SEEK_SET);h=hashlib.sha256();left=size
    while left:
        block=os.read(fd,min(65536,left));need(block,'INPUT_TRUNCATED');left-=len(block);h.update(block)
    need(not os.read(fd,1),'INPUT_GREW');return h.hexdigest()

def manifest_map(fd,pins):
    size=pins['manifest_bytes'];need(size<=MAX_MANIFEST,'MANIFEST_BOUND')
    need(hash_fd(fd,size)==pins['manifest_sha256'],'MANIFEST_SHA')
    os.lseek(fd,0,os.SEEK_SET);chunks=[];left=size
    while left:
        b=os.read(fd,min(left,65536));need(b,'MANIFEST_TRUNCATED');chunks.append(b);left-=len(b)
    raw=b''.join(chunks);need(sha(raw)==pins['manifest_sha256'],'MANIFEST_CHANGED')
    data=json.loads(raw.decode('utf8'),object_pairs_hook=unique)
    need(data.get('scope')=='ISOLATED_TEST_ONLY_SOURCE_SNAPSHOT','MANIFEST_SCOPE')
    rows=data.get('files');need(isinstance(rows,list) and len(rows)==pins['members']<=MAX_MEMBERS,'MANIFEST_COUNT')
    result={};total=0
    for row in rows:
        need(isinstance(row,dict) and isinstance(row.get('path'),str) and row['path'].startswith('/'),'MANIFEST_PATH')
        name=safe_name(row['path'][1:]);need(name not in result,'DUPLICATE_MANIFEST_PATH')
        need(type(row.get('bytes')) is int and 0<=row['bytes']<=MAX_MEMBER,'MANIFEST_SIZE')
        need(re.fullmatch('[a-f0-9]{64}',row.get('sha256','')) is not None,'MANIFEST_MEMBER_SHA')
        for k in ('uid','gid','mode'):need(type(row.get(k)) is int and 0<=row[k]<=2147483647,'MANIFEST_METADATA')
        need(row['mode']<=0o7777,'MANIFEST_MODE');total+=row['bytes'];result[name]=row
    need(total<=MAX_PAYLOAD and data.get('files_count')==len(rows) and data.get('bytes')==total,'MANIFEST_TOTAL')
    for target,(size,h) in pins['targets'].items():
        row=result.get(ROOT+target);need(row is not None and row['bytes']==size and row['sha256']==h,'TARGET_MANIFEST_BINDING')
    return result

def octal(raw):
    raw=raw.strip(b'\x00 ');need(not raw or re.fullmatch(b'[0-7]+',raw) is not None,'TAR_NUMERIC');return int(raw or b'0',8)
def text(raw):
    value,sep,padding=raw.partition(b'\x00');need(not sep or not padding.strip(b'\x00'),'TAR_TEXT_PADDING');return value.decode('utf8')
def gnu_path(raw):
    need(1<len(raw)<=4097 and raw[-1:]==b'\x00' and b'\x00' not in raw[:-1],'GNU_LONGNAME_PAYLOAD')
    return safe_name(raw[:-1].decode('utf8'))

def pax_path(raw):
    need(0<len(raw)<=MAX_PAX,'PAX_BOUND');offset=0;values={}
    while offset<len(raw):
        space=raw.find(b' ',offset);need(space>offset and space-offset<=6,'PAX_LENGTH')
        digits=raw[offset:space];need(re.fullmatch(b'[1-9][0-9]*',digits) is not None,'PAX_LENGTH')
        length=int(digits);end=offset+length;need(space+1<end<=len(raw) and raw[end-1:end]==b'\n','PAX_RECORD')
        record=raw[space+1:end-1];key,sep,value=record.partition(b'=')
        need(sep and key==b'path' and key not in values,'PAX_KEY_NOT_ALLOWED')
        values[key]=safe_name(value.decode('utf8'));offset=end
    need(set(values)=={b'path'},'PAX_PATH_REQUIRED');return values[b'path']

class TarReader:
    def __init__(self,fd,size):self.fd=fd;self.left=size;os.lseek(fd,0,os.SEEK_SET)
    def read(self,n):
        need(n<=self.left,'TAR_TRUNCATED');parts=[];left=n
        while left:
            b=os.read(self.fd,min(left,65536));need(b,'TAR_TRUNCATED');parts.append(b);left-=len(b);self.left-=len(b)
        return b''.join(parts)

def select_files(tar_fd,manifest_fd,pins,checkpoint=None):
    before=[identity(os.fstat(fd)) for fd in (tar_fd,manifest_fd)]
    need(pins['tar_bytes']<=MAX_TAR and pins['tar_bytes']%512==0,'TAR_BOUND')
    rows=manifest_map(manifest_fd,pins)
    need(hash_fd(tar_fd,pins['tar_bytes'])==pins['tar_sha256'],'TAR_SHA')
    if checkpoint:checkpoint('HASHED')
    reader=TarReader(tar_fd,pins['tar_bytes']);seen=set();selected={};pending=None;pending_format=None;headers=0;total=0;termination='MEMBER_BOUNDARY_EOF'
    while reader.left:
        header=reader.read(512)
        if header==b'\x00'*512:
            need(pending is None and reader.left>=512,'TAR_END_MARKER')
            while reader.left:need(not reader.read(min(reader.left,65536)).strip(b'\x00'),'TAR_TRAILING_DATA')
            termination='ZERO_END_MARKERS';break
        headers+=1;need(headers<=2*MAX_MEMBERS,'TAR_HEADER_BOUND')
        need(octal(header[148:156])==sum(header[:148])+8*32+sum(header[156:]),'TAR_CHECKSUM')
        magic=header[257:265];gnu=magic==b'ustar  \x00'
        need(gnu or magic==b'ustar\x0000','TAR_FORMAT')
        # Old GNU bytes345:512 are extension fields, never a POSIX prefix.
        if gnu:need(not header[345:512].strip(b'\x00'),'GNU_EXTENSION_NOT_ALLOWED')
        name=text(header[:100]) if pending is None else None
        if not gnu:
            prefix=text(header[345:500])
            if name is not None:name=(prefix+'/'+name) if prefix else name
        size=octal(header[124:136]);kind=header[156:157]
        if kind in (b'x',b'L'):
            need(pending is None,'TAR_NESTED_EXTENSION')
            need(not text(header[157:257]) and octal(header[329:337])==octal(header[337:345])==0,'TAR_LINK_OR_DEVICE')
            if kind==b'L':
                need(gnu and name=='././@LongLink' and 101<size<=4097,'GNU_LONGNAME_HEADER')
                need(all(octal(header[a:b])==0 for a,b in ((100,108),(108,116),(116,124),(136,148))) and not header[265:329].strip(b'\x00'),'GNU_LONGNAME_METADATA')
                pending=gnu_path(reader.read(size))
            else:
                need(not gnu and name=='././@PaxHeader' and size<=MAX_PAX,'PAX_HEADER')
                pending=pax_path(reader.read(size))
            pending_format=magic;pad=(-size)%512
            need(not reader.read(pad).strip(b'\x00'),'TAR_PADDING');continue
        need(kind in (b'0',b'\x00'),'TAR_MEMBER_TYPE')
        need(pending is None or pending_format==magic,'TAR_MIXED_EXTENSION')
        # A GNU fallback name may cut a multibyte UTF8 sequence at byte100;
        # bind its exact bytes to the validated full longname instead of decoding.
        if pending is not None:
            expected=pending.encode('utf8')[:100]
            if gnu:need(header[:100]==expected+b'\x00'*(100-len(expected)),'TAR_LONGNAME_FALLBACK')
            name=pending
        safe_name(name);pending=None;pending_format=None
        need(not text(header[157:257]) and octal(header[329:337])==0 and octal(header[337:345])==0,'TAR_LINK_OR_DEVICE')
        need(name not in seen,'DUPLICATE_TAR_MEMBER');need(name in rows,'TAR_MEMBER_NOT_IN_MANIFEST')
        row=rows[name];need(size==row['bytes'] and size<=MAX_MEMBER,'TAR_MEMBER_SIZE')
        need((octal(header[100:108]),octal(header[108:116]),octal(header[116:124]))==(row['mode'],row['uid'],row['gid']),'TAR_METADATA')
        total+=size;need(total<=MAX_PAYLOAD,'TAR_PAYLOAD_BOUND');h=hashlib.sha256();pieces=[];left=size
        target=name[len(ROOT):] if name.startswith(ROOT) else None
        while left:
            b=reader.read(min(left,65536));h.update(b);left-=len(b)
            if target in pins['targets']:pieces.append(b)
        need(h.hexdigest()==row['sha256'],'TAR_MEMBER_CONTENT_SHA')
        need(not reader.read((-size)%512).strip(b'\x00'),'TAR_PADDING');seen.add(name)
        if target in pins['targets']:
            raw=b''.join(pieces);expected=pins['targets'][target]
            need(len(raw)==expected[0] and sha(raw)==expected[1],'TARGET_CONTENT_SHA');selected[target]=raw
        if checkpoint:checkpoint('MEMBER')
    need(pending is None and seen==set(rows),'TAR_MANIFEST_SET_MISMATCH')
    need(set(selected)==set(pins['targets']) and sum(map(len,selected.values()))<=MAX_SMALL,'SELECTED_SET')
    need(all(identity(os.fstat(fd))==s for fd,s in zip((tar_fd,manifest_fd),before)),'SOURCE_CHANGED')
    return selected,{'members_verified':len(seen),'all_members_content_sha_verified':True,'payload_bytes_verified':total,'source_tar_termination':termination}

def small_archive(selected):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for name in sorted(selected):
            raw=selected[name];entry=tarfile.TarInfo(name);entry.size=len(raw);entry.mode=0o600;entry.uid=entry.gid=0;entry.mtime=0
            tar.addfile(entry,io.BytesIO(raw))
    raw=out.getvalue();need(len(raw)<=MAX_SMALL,'SMALL_ARCHIVE_BOUND');return raw

def verify_small(fd,pins):
    size=os.fstat(fd).st_size;need(size<=MAX_SMALL and size%512==0,'SMALL_BOUND')
    reader=TarReader(fd,size);seen=set();total=0
    while reader.left:
        h=reader.read(512)
        if h==b'\x00'*512:
            need(reader.left>=512,'SMALL_END')
            need(not reader.read(reader.left).strip(b'\x00'),'SMALL_TRAILING');break
        need(octal(h[148:156])==sum(h[:148])+256+sum(h[156:]),'SMALL_CHECKSUM')
        need(h[156:157]==b'0' and h[257:265]==b'ustar\x0000' and not text(h[345:500]) and not text(h[157:257]),'SMALL_MEMBER_TYPE')
        name=safe_name(text(h[:100]));need(name in pins['targets'] and name not in seen,'SMALL_MEMBER_SET')
        length=octal(h[124:136]);expected=pins['targets'][name]
        need(length==expected[0] and octal(h[100:108])==0o600 and octal(h[108:116])==octal(h[116:124])==0,'SMALL_METADATA')
        raw=reader.read(length);need(sha(raw)==expected[1],'SMALL_CONTENT_SHA');total+=length
        need(not reader.read((-length)%512).strip(b'\x00'),'SMALL_PADDING');seen.add(name)
    need(seen==set(pins['targets']),'SMALL_MEMBER_SET');return total

def write_new(directory,name,raw):
    need(len(raw)<=MAX_SMALL,'OUTPUT_SIZE_BOUND');fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.fsync(directory)
def run(tar_fd,manifest_fd,out_fd,pins,checkpoint=None):
    s=os.fstat(out_fd);need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'OUTPUT_UID_OR_MODE')
    result={'tool_version':'b5-three-files-gnu-v2','scope':'B5_THREE_FILES_OFFLINE_ANALYSIS_ONLY','state':'HOLD','source_tar_bytes':pins['tar_bytes'],'source_manifest_bytes':pins['manifest_bytes'],'source_tar_sha256':pins['tar_sha256'],'source_manifest_sha256':pins['manifest_sha256'],'dependency_closure':'UNKNOWN','b5_installation':'NOT_EXECUTED'}
    try:
        selected,evidence=select_files(tar_fd,manifest_fd,pins,checkpoint)
        raw=small_archive(selected);write_new(out_fd,'three-files.tar',raw)
        result.update(evidence);result.update(state='CHILD_VERIFIED_AWAIT_PARENT',archive_sha256=sha(raw),archive_bytes=len(raw),selected_bytes=sum(map(len,selected.values())),selected={n:{'bytes':len(b),'sha256':sha(b),'source_member':ROOT+n} for n,b in selected.items()})
        code=0
    except Exception as exc:
        result['error']=str(exc) if isinstance(exc,Hold) else type(exc).__name__;code=2
    write_new(out_fd,'receipt.json',encoded(result));return code

def private_home(path,uid):
    need(path.startswith('/') and posixpath.normpath(path)==path,'ADMIN_HOME_PATH')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for name in path.strip('/').split('/'):
            nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
            s=os.fstat(fd);need(s.st_uid in (0,uid) and not s.st_mode&0o022,'ADMIN_HOME_PARENT')
        need(os.fstat(fd).st_uid==uid,'ADMIN_HOME_OWNER');return fd
    except BaseException:os.close(fd);raise

def prior_failure(home,uid):
    old=os.open('p2-b5-three-files-20261020',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=home)
    try:
        st=os.fstat(old);need(st.st_uid==uid and stat.S_IMODE(st.st_mode)==0o700,'PRIOR_DIRECTORY_IDENTITY')
        evidence={}
        for name in ('host-result.json','receipt.json'):
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=old)
            try:
                st=os.fstat(fd);need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==uid and stat.S_IMODE(st.st_mode)==0o600 and st.st_size<=65536,'PRIOR_RECEIPT_IDENTITY')
                raw=os.read(fd,65537);need(len(raw)==st.st_size,'PRIOR_RECEIPT_SIZE')
                value=json.loads(raw.decode('utf8'),object_pairs_hook=unique)
                if name=='host-result.json':need(sha(raw)=='e40abcd5304e4ab0e29c83a4865528272aca2b0ddb97e6d3df8d9941544c3bd6' and value.get('state')=='HOLD','PRIOR_HOST_RESULT_BINDING')
                error=value.get('error');evidence[name]={'sha256':sha(raw),'bytes':len(raw),'state':value.get('state'),'error':error if isinstance(error,str) and re.fullmatch('[A-Z][A-Z0-9_]{0,160}',error) else 'UNKNOWN'}
            finally:os.close(fd)
        return evidence
    finally:os.close(old)

def main():
    need(os.getuid()==os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST,'FIXED_HOST_ROOT_REQUIRED')
    need(sys.version_info[:3]==(3,6,8),'HOST_PYTHON368_REQUIRED')
    admin=pwd.getpwnam('admin');need(admin.pw_uid not in (0,1002) and admin.pw_gid>0,'ADMIN_IDENTITY')
    a=PinnedFile(SOURCE+'/source-tree.tar.pending',(0,1002));m=PinnedFile(SOURCE+'/manifest.json',(0,1002))
    home=None;out=None
    try:
        a.check();m.check()
        need(os.fstat(a.fd).st_size==PINS['tar_bytes'] and os.fstat(m.fd).st_size==PINS['manifest_bytes'],'FIXED_INPUT_SIZE')
        # Open only pwd's real home; no caller-selected output path or runtime-tree traversal.
        home_path=admin.pw_dir;home=private_home(home_path,admin.pw_uid)
        hs=os.fstat(home);need(hs.st_uid==admin.pw_uid and not hs.st_mode&0o022,'ADMIN_HOME_OWNER')
        prior=prior_failure(home,admin.pw_uid);print(json.dumps({'prior_failure_readback':prior},sort_keys=True),flush=True)
        os.umask(0o077);os.mkdir(OUTPUT_NAME,0o700,dir_fd=home)
        out=os.open(OUTPUT_NAME,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=home);os.fchown(out,admin.pw_uid,admin.pw_gid);os.fsync(home)
        pid=os.fork()
        if pid==0:
            try:
                os.setsid();os.close(home)
                for fd in a.parents+m.parents:os.close(fd)
                resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(180,180));resource.setrlimit(resource.RLIMIT_AS,(384*1024*1024,384*1024*1024));resource.setrlimit(resource.RLIMIT_FSIZE,(2*MAX_SMALL,2*MAX_SMALL));resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
                def deadline(signum,frame):raise Hold('WALL_TIME_BOUND')
                signal.signal(signal.SIGALRM,deadline);signal.alarm(240)
                os.setgroups([]);os.setgid(admin.pw_gid);os.setuid(admin.pw_uid)
                code=run(a.fd,m.fd,out,PINS);os._exit(code)
            except BaseException:os._exit(2)
        start=time.monotonic();status=None
        while status is None:
            got,value=os.waitpid(pid,os.WNOHANG)
            if got:status=value;break
            if time.monotonic()-start>=270:
                os.killpg(pid,signal.SIGKILL);_,status=os.waitpid(pid,0);break
            time.sleep(.1)
        report={'scope':'B5_THREE_FILES_OFFLINE_ANALYSIS_ONLY','state':'HOLD','child_wait_status':status,'dependency_closure':'UNKNOWN','b5_installation':'NOT_EXECUTED'}
        try:
            a.check();m.check();need(os.WIFEXITED(status) and os.WEXITSTATUS(status)==0,'CHILD_FAILED_RETAIN_OUTPUT')
            fd=os.open('receipt.json',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=out)
            with os.fdopen(fd,'rb') as f:
                rs=os.fstat(f.fileno());need(stat.S_ISREG(rs.st_mode) and rs.st_uid==admin.pw_uid and stat.S_IMODE(rs.st_mode)==0o600 and rs.st_nlink==1,'RECEIPT_IDENTITY');raw=f.read(65537)
            need(len(raw)<=65536,'RECEIPT_BOUND');value=json.loads(raw.decode('utf8'),object_pairs_hook=unique)
            need(value.get('state')=='CHILD_VERIFIED_AWAIT_PARENT' and value.get('members_verified')==PINS['members'] and value.get('all_members_content_sha_verified') is True and value.get('source_tar_sha256')==PINS['tar_sha256'] and value.get('source_manifest_sha256')==PINS['manifest_sha256'],'CHILD_RECEIPT')
            fd=os.open('three-files.tar',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=out)
            try:
                ss=os.fstat(fd);need(stat.S_ISREG(ss.st_mode) and ss.st_uid==admin.pw_uid and stat.S_IMODE(ss.st_mode)==0o600 and ss.st_nlink==1 and ss.st_size<=MAX_SMALL and hash_fd(fd,value['archive_bytes'])==value['archive_sha256'],'SMALL_ARCHIVE_READBACK')
                need(verify_small(fd,PINS)==value['selected_bytes']==sum(v[0] for v in PINS['targets'].values()),'SMALL_SELECTED_BYTES')
            finally:os.close(fd)
            report.update(state='THREE_FILES_READY_OFFLINE_ONLY',receipt_sha256=sha(raw),archive_sha256=value['archive_sha256'],archive_bytes=value['archive_bytes'],selected_bytes=value['selected_bytes'])
        except Exception as exc:report['error']=str(exc) if isinstance(exc,Hold) else type(exc).__name__
        # Parent writes one new admin-owned summary; no alteration of child/source artifacts.
        fd=os.open('host-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=out)
        with os.fdopen(fd,'wb') as f:os.fchown(f.fileno(),admin.pw_uid,admin.pw_gid);raw=encoded(report);f.write(raw);f.flush();os.fsync(f.fileno())
        os.fsync(out);print(json.dumps({'output_directory':home_path+'/'+OUTPUT_NAME,'host_result':report,'host_result_sha256':sha(raw)},sort_keys=True))
        return 0 if report['state']=='THREE_FILES_READY_OFFLINE_ONLY' else 2
    finally:
        a.close();m.close()
        if out is not None:os.close(out)
        if home is not None:os.close(home)
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'state':'HOLD','error':str(exc) if isinstance(exc,Hold) else type(exc).__name__,'b5_installation':'NOT_EXECUTED'},sort_keys=True));sys.exit(2)
