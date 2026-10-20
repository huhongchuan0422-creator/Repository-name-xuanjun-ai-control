"""B5 bounded SOURCE snapshot candidate. Host Python3.6; no Node/SDK execution.
No closure/export acceptance. Production paths and credentials are not inputs.
"""
import hashlib,json,os,pwd,re,socket,stat,struct,sys,tarfile,time
HOST='iZd7oeikknn1z21sq6ji6zZ'
INSTALL='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0'
SDK=INSTALL+'/lib/node_modules/openclaw'
NODE=INSTALL+'/bin/node'
OUTPUT='/var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020/uid1002'
MAX_FILES=20000;MAX_BYTES=512*1024*1024;MAX_FILE=128*1024*1024;MAX_SECONDS=90;MAX_DEPTH=40
PACKAGE_SHA='214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95'
PINS={SDK+'/package.json':PACKAGE_SHA,
 SDK+'/dist/loader-runtime-load-DpgEqnzx.mjs':'3c30c5d43fb3cd19525853bb6b756cf45cfd05f5da32a732dc129b85cb309787',
 SDK+'/dist/context-DyPstb2Q.mjs':'db7fc7539455da0c564d4ded0d04da1c764a46903d1632489b8bd04641098320'}
SECRET=re.compile(r'(^|[._-])(auth|credentials?|secrets?|tokens?|sessions?|ledger|customers?|config|passwords?|private|api[_-]?key)([._-]|$)',re.I)
# Runtime source filenames containing config/auth are legitimate CODE, not user data.
SOURCE_EXT=('.js','.mjs','.cjs','.ts','.map','.wasm','.node','.d.ts')

def require(ok,reason):
    if not ok:raise ValueError(reason)

def canon(raw):return json.dumps(raw,sort_keys=True,separators=(',',':')).encode('utf8')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def fingerprint(s):return tuple(getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))

def open_absolute(path,directory=False):
    require(path.startswith('/') and os.path.normpath(path)==path,'ABSOLUTE_CANONICAL_PATH_REQUIRED')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        parts=path.strip('/').split('/')
        for i,part in enumerate(parts):
            last=i==len(parts)-1
            flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
            if not last or directory:flags|=os.O_DIRECTORY
            nxt=os.open(part,flags,dir_fd=fd);os.close(fd);fd=nxt
            s=os.fstat(fd)
            require(s.st_uid in (0,1002) and not s.st_mode&0o022,'UNPROTECTED_SOURCE_PATH')
        return fd
    except BaseException:
        os.close(fd);raise

def permitted(relative):
    parts=relative.split('/')
    if any(p in ('.git','.env','auth-profiles','credentials','sessions','ledger','customer-data') for p in parts):return False
    name=parts[-1]
    # Never read databases, private keys, environment files or customer/config data.
    if name.endswith(('.sqlite','.sqlite3','.db','-wal','-shm','.pem','.key','.p12','.pfx')) or name.startswith('.env'):return False
    if name.endswith(SOURCE_EXT):return True
    if SECRET.search(name) or any(SECRET.search(part) for part in parts[:-1]):return False
    return name in ('package.json','package-lock.json','npm-shrinkwrap.json','LICENSE','LICENSE.md','README.md') or name.endswith(('.json','.txt','.md','.html','.css','.svg','.png','.jpg','.webp','.gif','.woff','.woff2','.ttf','.otf'))

def elf_needs(raw):
    """Static ELF64 little-endian PT_INTERP/DT_NEEDED only; never ldd/execute."""
    require(raw[:4]==b'\x7fELF' and raw[4:6]==b'\x02\x01','ELF64_LE_REQUIRED')
    require(len(raw)>=64,'ELF_TRUNCATED')
    off=struct.unpack_from('<Q',raw,32)[0];size,num=struct.unpack_from('<HH',raw,54)
    require(size>=56 and num<=1024 and off+size*num<=len(raw),'ELF_HEADERS')
    loads=[];dynamic=None;interp=None
    for i in range(num):
        typ,flags,po,va,pa,fs,ms,al=struct.unpack_from('<IIQQQQQQ',raw,off+i*size)
        require(po+fs<=len(raw),'ELF_SEGMENT')
        if typ==1:loads.append((va,fs,po))
        if typ==2:dynamic=(po,fs)
        if typ==3:interp=raw[po:po+fs].rstrip(b'\x00').decode('ascii')
    needed=[];straddr=None;strsize=None
    if dynamic:
        require(dynamic[1]%16==0,'ELF_DYNAMIC')
        for p in range(dynamic[0],dynamic[0]+dynamic[1],16):
            tag,value=struct.unpack_from('<qQ',raw,p)
            if tag==0:break
            if tag==1:needed.append(value)
            if tag==5:straddr=value
            if tag==10:strsize=value
            # RPATH/RUNPATH resolution must not be guessed from host search order.
            if tag in (15,29):raise ValueError('ELF_CUSTOM_SEARCH_PATH_HOLD')
        if needed:
            require(straddr is not None and strsize is not None and strsize<=16*1024*1024,'ELF_STRTAB')
            offsets=[po+straddr-va for va,fs,po in loads if va<=straddr and straddr+strsize<=va+fs]
            require(len(offsets)==1,'ELF_STRTAB_MAPPING')
            table=raw[offsets[0]:offsets[0]+strsize];names=[]
            for n in needed:
                require(n<len(table) and b'\x00' in table[n:],'ELF_NEEDED_STRING')
                name=table[n:table.index(b'\x00',n)].decode('ascii')
                require(re.fullmatch(r'[A-Za-z0-9_+.-]+',name) is not None,'ELF_NEEDED_NAME')
                names.append(name)
            needed=names
    return {'interpreter':interp,'needed':needed}

class Collector:
    def __init__(self,archive):
        self.archive=archive;self.start=time.monotonic();self.rows=[];self.holds=[];self.total=0;self.files=0;self.elf=[]
    def bound(self):require(time.monotonic()-self.start<=MAX_SECONDS,'TIME_BOUND')
    def hold(self,reason,path=None):
        require(len(self.holds)<2048,'HOLD_REPORT_BOUND')
        self.holds.append({'reason':reason,'path':path} if path else {'reason':reason})
    def file(self,path,kind):
        if any(r['path']==path for r in self.rows):return None
        self.bound();fd=open_absolute(path)
        with os.fdopen(fd,'rb') as f:
            before=os.fstat(f.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=MAX_FILE,'SOURCE_FILE_BOUND_OR_TYPE')
            self.files+=1;self.total+=before.st_size
            require(self.files<=MAX_FILES and self.total<=MAX_BYTES,'TOTAL_BOUND')
            # Bound memory per file; no unbounded copytree or special-file opening.
            raw=f.read(MAX_FILE+1);after=os.fstat(f.fileno())
            require(len(raw)==before.st_size and fingerprint(before)==fingerprint(after),'SOURCE_CHANGED')
        fd=open_absolute(path)
        try:require(fingerprint(os.fstat(fd))==fingerprint(before),'SOURCE_REPLACED')
        finally:os.close(fd)
        h=sha(raw)
        if path in PINS:require(h==PINS[path],'HISTORICAL_PIN_CHANGED')
        import io
        info=tarfile.TarInfo(path.lstrip('/'));info.size=len(raw);info.mode=stat.S_IMODE(before.st_mode);info.uid=before.st_uid;info.gid=before.st_gid;info.mtime=0
        self.archive.addfile(info,io.BytesIO(raw))
        row={'path':path,'sha256':h,'bytes':len(raw),'uid':before.st_uid,'gid':before.st_gid,'mode':info.mode,'kind':kind}
        self.rows.append(row)
        if path==NODE or path.endswith('.node') or kind=='elf-library':
            try:self.elf.append({'path':path,'dependencies':elf_needs(raw)})
            except ValueError as exc:self.hold(str(exc),path)
        return raw
    def tree(self,root,relative='',depth=0):
        self.bound();require(depth<=MAX_DEPTH,'DEPTH_BOUND')
        full=root+('/'+relative if relative else '')
        fd=open_absolute(full,True)
        try:
            before=os.fstat(fd);names=sorted(os.listdir(fd))
            require(len(names)<=MAX_FILES,'DIRECTORY_ENTRY_BOUND')
            for name in names:
                self.bound();rel=relative+'/'+name if relative else name;p=root+'/'+rel
                s=os.stat(name,dir_fd=fd,follow_symlinks=False)
                if stat.S_ISLNK(s.st_mode):
                    # Capture metadata only; do not follow a link into credentials/other roots.
                    self.hold('LINK_REQUIRES_EXPLICIT_MATERIALIZATION',p);continue
                if stat.S_ISDIR(s.st_mode):
                    if name in ('.git','auth-profiles','credentials','sessions','ledger','customer-data'):
                        self.hold('EXCLUDED_DIRECTORY',sha(rel.encode()));continue
                    self.tree(root,rel,depth+1)
                elif not stat.S_ISREG(s.st_mode):self.hold('SPECIAL_FILE_REJECTED',p)
                elif permitted(rel):self.file(p,'sdk-source')
                else:self.hold('EXCLUDED_MEMBER',sha(rel.encode()))
            require(fingerprint(os.fstat(fd))==fingerprint(before),'SOURCE_DIRECTORY_CHANGED')
        finally:os.close(fd)

SYSROOTS=('/usr/lib64','/lib64','/usr/lib/x86_64-linux-gnu','/lib/x86_64-linux-gnu')
def capture_libraries(collector):
    """Capture only names derived from actual ELF, not an entire system directory.
    Unique canonical candidates are source evidence; never a claim about ld.so resolution.
    """
    done=set(r['path'] for r in collector.rows);index=0;edges=[]
    while index<len(collector.elf):
        require(index<512,'ELF_CLOSURE_BOUND');item=collector.elf[index];index+=1
        deps=item['dependencies'];requests=[]
        if deps['interpreter']:requests.append(('interpreter',deps['interpreter']))
        requests.extend(('needed',name) for name in deps['needed'])
        for typ,name in requests:
            candidates=[name] if typ=='interpreter' else [root+'/'+name for root in SYSROOTS]
            resolved={}
            for p in candidates:
                if not os.path.lexists(p):continue
                canonical=os.path.realpath(p)
                require(any(canonical.startswith(root+'/') for root in SYSROOTS),'ELF_LIBRARY_OUTSIDE_SCOPE')
                resolved.setdefault(canonical,[]).append(p)
            if len(resolved)!=1:
                collector.hold('ELF_LIBRARY_MISSING_OR_AMBIGUOUS',name);continue
            canonical=list(resolved)[0];s=os.stat(canonical)
            require(s.st_uid==0,'ELF_LIBRARY_ROOT_OWNER')
            edges.append({'from':item['path'],'kind':typ,'name':name,'canonical':canonical,'aliases':resolved[canonical]})
            if canonical not in done:
                collector.file(canonical,'elf-library');done.add(canonical)
    return edges

def write_new(path,raw,dir_fd=None):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=dir_fd)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    except BaseException:raise

def collect(output):
    # Output is always a new operation directory. Existing/partial artifacts are retained.
    directory=os.dup(output) if isinstance(output,int) else open_absolute(output,True)
    s=os.fstat(directory);require(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'PRIVATE_OUTPUT_REQUIRED')
    result={'scope':'ISOLATED_TEST_ONLY_SOURCE_SNAPSHOT','state':'HOLD','node_execution':'NOT_EXECUTED','dependency_closure':'UNKNOWN','compiled_export':'UNKNOWN','cp11':'NOT_EXECUTED'}
    target='source-tree.tar.pending';collector=None
    try:
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        with os.fdopen(fd,'wb') as stream:
            with tarfile.open(fileobj=stream,mode='w|') as archive:
                collector=Collector(archive)
                for pinned in sorted(PINS):collector.file(pinned,'pinned-sdk-source')
                collector.file(NODE,'node-executable');collector.tree(SDK)
                result['elf_source_edges']=capture_libraries(collector)
            stream.flush();os.fsync(stream.fileno())
        measured={r['path'] for r in collector.rows}
        require(set(PINS)<=measured,'PINNED_MEMBERS_MISSING')
        result['capture']='BOUNDED_SOURCE_CAPTURED';result['holds']=collector.holds
        # Static ELF names are evidence, not host linker resolution or shared-library closure.
        result['elf_requirements']=collector.elf
        result['required_next']='Bind recursive ELF interpreter/libraries and JS resolution graph using the captured source; export must be verified against the exact compiled module in the separately approved isolated runtime.'
    except Exception as exc:
        result['capture']='STOPPED_RETAINED';result['error']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
        if collector:result['holds']=collector.holds
    if collector:
        manifest={'scope':result['scope'],'files':collector.rows,'files_count':collector.files,'bytes':collector.total}
        raw=canon(manifest);write_new('manifest.json',raw,dir_fd=directory);result['manifest_sha256']=sha(raw)
    # Pending tar is never published as a closed runtime or executable test artifact.
    if 'fd' in locals():
        h=hashlib.sha256()
        archive_fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
        archive_stat=os.fstat(archive_fd)
        with os.fdopen(archive_fd,'rb') as f:
            for block in iter(lambda:f.read(65536),b''):h.update(block)
        result['archive_sha256']=h.hexdigest();result['archive_bytes']=archive_stat.st_size
    write_new('result.json',canon(result),dir_fd=directory)
    try:os.fsync(directory)
    finally:os.close(directory)
    print(json.dumps(result,sort_keys=True));return 2

def main():
    require(socket.gethostname().split('.')[0]==HOST and os.getuid()==os.geteuid()==1002 and pwd.getpwuid(1002).pw_name=='xuanjun_dev','FIXED_HOST_UID_REQUIRED')
    require(sys.version_info[:3]==(3,6,8),'HOST_PYTHON368_REQUIRED')
    output_fd=int(os.environ['P2_B5_OUTPUT_FD'])
    require(os.readlink('/proc/self/fd/'+str(output_fd))==OUTPUT,'FIXED_OUTPUT_FD_REQUIRED')
    return collect(output_fd)
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'state':'HOLD','error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,'cp11':'NOT_EXECUTED'}));sys.exit(2)
