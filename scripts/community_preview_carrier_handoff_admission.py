"""Issue76: isolated, one-shot carrier handoff candidate. No CLI or B/C import.

The caller supplies two already authorized directory capabilities (carrier parent and
original update-journal) and the original A ENTRY fd. This module does not acquire
root, grant permissions, delete intents, restart services or call B/C.
"""
import ctypes
import errno
import fcntl
import hashlib
import io
import json
import os
import stat
import zipfile

HOST='iZd7oeikknn1z21sq6ji6zZ'
TARGET='control-stopped-v1'
ENTRY_NAME='site-prepare-v1.py'
JOURNAL_DIR='update-journal'
STAGE='control-stopped-v1.handoff-stage-v1'
RETAINED='control-stopped-v1.handoff-retained-old-v1'
STATE='carrier-handoff-intent-v1.json'
PREINTENT='carrier-handoff-preintent-v1.json'
ROLLBACK_INTENT='carrier-handoff-rollback-intent-v1.json'
ROLLBACK_RESULT='carrier-handoff-rollback-result-v1.json'
LOCK='community-update.lock'
OLD_MANIFEST='e09b7ab9432350cafac0c07e76966d1197056eee02d802c0a2b3be7460c1ac1a'
NEW_MANIFEST='d1d3c92b4059c7e449ed38045be9c1a5bb52ce1795365f01b41d7bd0028019fd'
OLD_ARCHIVE='5107d2f762d018d067c22ca034e41e0e5ee9b8e529cfdfc0a3dbb80a2cc6f4a4'
NEW_ARCHIVE='2418f4421262f509cd84c1c8465c918ea8bbd0c2ee1101d5f692176225bcd7ff'
MAX_ZIP=4*1024*1024
MAX_FILE=131072
MAX_FILES=100

class Hold(RuntimeError):pass

def need(ok,reason):
    if not ok:raise Hold(reason)

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':')).encode('utf-8')
def ident(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,
            st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns]
def parent_ident(st):return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid]
def dirident(st):return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink]
def childstat(fd,name):
    try:return os.stat(name,dir_fd=fd,follow_symlinks=False)
    except FileNotFoundError:return None

def checked_dir(fd,uid):
    st=os.fstat(fd)
    need(stat.S_ISDIR(st.st_mode) and st.st_uid==uid and stat.S_IMODE(st.st_mode)==0o700,
         'UNTRUSTED_DIR')
    return parent_ident(st)

def readfile(fd,name,uid,maxlen=MAX_FILE):
    f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try:
        st=os.fstat(f)
        need(stat.S_ISREG(st.st_mode) and st.st_uid==uid and st.st_nlink==1
             and stat.S_IMODE(st.st_mode)==0o600 and 0<st.st_size<=maxlen,'UNTRUSTED_FILE')
        raw=b''
        while len(raw)<=maxlen:
            part=os.read(f,min(65536,maxlen-len(raw)+1))
            if not part:break
            raw+=part
        need(len(raw)==st.st_size and ident(st)==ident(os.fstat(f))
             and ident(st)==ident(os.stat(name,dir_fd=fd,follow_symlinks=False)),
             'FILE_CHANGED')
        return raw
    finally:os.close(f)

def members(raw,manifest_sha,archive_sha):
    need(sha(raw)==archive_sha and 0<len(raw)<=MAX_ZIP,'CANDIDATE_ARCHIVE_SHA')
    try:archive=zipfile.ZipFile(io.BytesIO(raw))
    except (ValueError,zipfile.BadZipFile):raise Hold('CANDIDATE_ZIP_INVALID')
    with archive:
        rows=archive.infolist()
        names=[r.filename for r in rows]
        need(0<len(rows)<=MAX_FILES and len(names)==len(set(names))
             and 'manifest.json' in names,'CANDIDATE_ZIP_MEMBERS')
        contents={}
        for row in rows:
            path=row.filename
            need(path and not path.startswith('/') and not path.endswith('/')
                 and '\\' not in path and all(x not in ('','.','..') for x in path.split('/'))
                 and row.compress_type==zipfile.ZIP_DEFLATED
                 and stat.S_IFMT(row.external_attr>>16)==stat.S_IFREG
                 and stat.S_IMODE(row.external_attr>>16)==0o600
                 and 0<row.file_size<=MAX_FILE,'CANDIDATE_UNSAFE_MEMBER')
            data=archive.read(row)
            need(len(data)==row.file_size,'CANDIDATE_TRUNCATED')
            contents[path]=data
        manifest_raw=contents['manifest.json']
        need(sha(manifest_raw)==manifest_sha,'CANDIDATE_MANIFEST_SHA')
        try:m=json.loads(manifest_raw.decode('utf8'))
        except (ValueError,UnicodeError):raise Hold('CANDIDATE_MANIFEST_JSON')
        need(manifest_raw==canonical(m) and type(m) is dict
             and set(m)=={'format','mode','install_root','updates_enabled','files'}
             and type(m['format']) is int and m['format']==1
             and m['mode']=='STOPPED_HANDOFF_V1' and m['updates_enabled'] is False
             and m['install_root']=='/opt/xuanjun-community-preview/control-stopped-v1'
             and type(m['files']) is dict and set(m['files'])==set(contents)-{'manifest.json'},
             'CANDIDATE_MANIFEST_SCOPE')
        for name,meta in m['files'].items():
            need(type(meta) is dict and set(meta)=={'bytes','sha256','uid','mode'}
                 and meta['bytes']==len(contents[name]) and meta['sha256']==sha(contents[name])
                 and meta['uid']==0 and meta['mode']=='0600','CANDIDATE_MEMBER_SHA')
        return contents

def capture_history(refs,uid):
    need(type(refs) is dict and set(refs)=={'b_intent','b_approval','freeze','old_stage_permit'},
         'HISTORICAL_BINDINGS_REQUIRED')
    result={}
    for key in sorted(refs):
        ref=refs[key]
        need(type(ref) in (tuple,list) and len(ref)==5,'HISTORY_REFERENCE_SCHEMA')
        pfd,name,expected_parent,expected_file,expected_sha=ref
        pst=os.fstat(pfd)
        need(stat.S_ISDIR(pst.st_mode) and pst.st_uid==uid
             and not(stat.S_IMODE(pst.st_mode)&0o022)
             and parent_ident(pst)==expected_parent,'HISTORY_PARENT_CHANGED')
        need(type(name) is str and name and '/' not in name and name not in ('.','..'),
             'HISTORY_NAME_INVALID')
        st=childstat(pfd,name)
        if expected_file is None:
            need(expected_sha is None and st is None,'HISTORY_ABSENCE_CHANGED')
            result[key]={'name':name,'parent_identity':expected_parent,'file_identity':None,'sha256':None}
            continue
        need(st is not None and ident(st)==expected_file,'HISTORY_FILE_IDENTITY_CHANGED')
        raw=readfile(pfd,name,uid,8*1024*1024)
        after=childstat(pfd,name)
        need(after is not None and ident(after)==expected_file and sha(raw)==expected_sha,
             'HISTORY_FILE_CONTENT_CHANGED')
        result[key]={'name':name,'parent_identity':expected_parent,
                     'file_identity':expected_file,'sha256':expected_sha}
    return result

def verified_old_inventory(expected):
    need(type(expected) is dict and 'manifest.json' in expected,
         'OLD_INVENTORY_REQUIRED')
    manifest_raw=expected['manifest.json']
    need(sha(manifest_raw)==OLD_MANIFEST,'OLD_MANIFEST_CHANGED')
    try:m=json.loads(manifest_raw.decode('utf8'))
    except (ValueError,UnicodeError):raise Hold('OLD_MANIFEST_INVALID')
    need(manifest_raw==canonical(m) and type(m) is dict
         and set(m)=={'format','mode','install_root','files','updates_enabled'}
         and m['format']==1 and type(m['format']) is int
         and m['mode']=='STOPPED_HANDOFF_V1'
         and m['install_root']=='/opt/xuanjun-community-preview/control-stopped-v1'
         and m['updates_enabled'] is False
         and type(m['files']) is dict and set(expected)==set(m['files'])|{'manifest.json'},
         'OLD_INVENTORY_SCOPE')
    for name,meta in m['files'].items():
        need(type(meta) is dict and set(meta)=={'bytes','sha256','uid','mode'}
             and type(meta['bytes']) is int and meta['bytes']==len(expected[name])
             and meta['sha256']==sha(expected[name])
             and meta['uid']==0 and meta['mode']=='0600','OLD_MEMBER_MANIFEST_BINDING')
    return True

def tree(fd,name,uid,expected,expected_id=None):
    root=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
    try:
        st=os.fstat(root)
        need(stat.S_ISDIR(st.st_mode) and st.st_uid==uid and stat.S_IMODE(st.st_mode)==0o700
             and (expected_id is None or dirident(st)==expected_id)
             and dirident(st)==dirident(os.stat(name,dir_fd=fd,follow_symlinks=False)),
             'TREE_IDENTITY_CHANGED')
        dirs={'':set()}
        for rel in expected:
            chunks=rel.split('/')
            for j in range(len(chunks)-1):
                prefix='/'.join(chunks[:j])
                child=chunks[j]
                dirs.setdefault(prefix,set()).add(child)
                dirs.setdefault('/'.join(chunks[:j+1]),set())
            dirs.setdefault('/'.join(chunks[:-1]),set()).add(chunks[-1])
        need(len(expected)<=MAX_FILES and len(dirs)<=MAX_FILES,'TREE_BUDGET_EXCEEDED')
        dir_ids={}
        for rel,names in dirs.items():
            current=root;opened=[]
            try:
                for part in rel.split('/') if rel else ():
                    nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
                    opened.append(nxt);current=nxt
                    checked_dir(current,uid)
                before=dirident(os.fstat(current))
                first=set(os.listdir(current));after=dirident(os.fstat(current));second=set(os.listdir(current))
                need(first==names and second==names and before==after,'TREE_EXTRA_OR_MISSING_MEMBER')
                dir_ids[rel]=before
            finally:
                for n in reversed(opened):os.close(n)
        for rel,want in expected.items():
            parts=rel.split('/')
            current=root;opened=[]
            try:
                for part in parts[:-1]:
                    nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
                    opened.append(nxt);current=nxt;checked_dir(current,uid)
                need(readfile(current,parts[-1],uid)==want,'TREE_BYTES_CHANGED')
            finally:
                for n in reversed(opened):os.close(n)
        for rel,names in dirs.items():
            cur=root;opened=[]
            try:
                for part in rel.split('/') if rel else ():
                    nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=cur)
                    opened.append(nxt);cur=nxt;checked_dir(cur,uid)
                need(dirident(os.fstat(cur))==dir_ids[rel]
                     and set(os.listdir(cur))==names,'TREE_CHANGED_DURING_READ')
            finally:
                for n in reversed(opened):os.close(n)
        need(dirident(st)==dirident(os.fstat(root))
             and dirident(st)==dirident(os.stat(name,dir_fd=fd,follow_symlinks=False)),
             'TREE_REPLACED_DURING_READ')
        return dirident(st)
    finally:os.close(root)

def writefile(fd,name,body,uid):
    f=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
    try:
        os.fchown(f,uid,-1);os.fchmod(f,0o600)
        pos=0
        while pos<len(body):
            n=os.write(f,body[pos:]);need(n>0,'WRITE_NO_PROGRESS');pos+=n
        os.fsync(f)
    finally:os.close(f)
    os.fsync(fd)

def build_tree(parent,entries,uid,name=STAGE):
    need(childstat(parent,name) is None,'STAGE_ALREADY_EXISTS')
    os.mkdir(name,0o700,dir_fd=parent)
    os.fsync(parent)
    root=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    try:
        os.fchown(root,uid,-1);os.fchmod(root,0o700)
        dirs=set()
        for path in entries:
            parts=path.split('/')
            for n in range(1,len(parts)):
                dirs.add('/'.join(parts[:n]))
        for d in sorted(dirs,key=lambda x:(x.count('/'),x)):
            chunks=d.split('/')
            fd=root;opened=[]
            try:
                for part in chunks[:-1]:
                    new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                    opened.append(new);fd=new
                os.mkdir(chunks[-1],0o700,dir_fd=fd)
                os.fsync(fd)
                f=os.open(chunks[-1],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                try:os.fchown(f,uid,-1);os.fchmod(f,0o700);os.fsync(f)
                finally:os.close(f)
            finally:
                for n in reversed(opened):os.close(n)
        for path,body in sorted(entries.items()):
            parts=path.split('/');fd=root;opened=[]
            try:
                for part in parts[:-1]:
                    new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                    opened.append(new);fd=new
                writefile(fd,parts[-1],body,uid)
            finally:
                for n in reversed(opened):os.close(n)
        os.fsync(root)
    finally:os.close(root)
    os.fsync(parent)

def exchange(parent,a,b):
    lib=ctypes.CDLL(None,use_errno=True)
    fn=getattr(lib,'renameat2',None)
    need(fn is not None,'ATOMIC_EXCHANGE_UNAVAILABLE')
    fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    fn.restype=ctypes.c_int
    if fn(parent,a.encode('ascii'),parent,b.encode('ascii'),2)!=0:
        raise Hold('ATOMIC_EXCHANGE_UNKNOWN_'+str(ctypes.get_errno()))

def journal(jfd,uid):
    b=readfile(jfd,STATE,uid,8192)
    try:v=json.loads(b.decode('utf8'))
    except (UnicodeError,ValueError):raise Hold('JOURNAL_JSON_UNKNOWN')
    fields={'format','attempt','old_manifest','new_manifest','old_identity','stage_identity',
            'old_tree_sha','new_tree_sha','history','entry_identity','journal_parent_identity','lock_identity','preintent_sha256'}
    need(type(v) is dict and set(v)==fields and type(v['format']) is int
         and v['format']==1 and type(v['attempt']) is str
         and v['old_manifest']==OLD_MANIFEST and v['new_manifest']==NEW_MANIFEST
         and b==canonical(v),'JOURNAL_SCHEMA_OR_BINDING')
    return v

def _check_paths(parent,jfd,entryfd,leasefd,uid,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity):
    checked_dir(parent,uid)
    need(parent_ident(os.fstat(parent))==expected_parent_identity,'PARENT_IDENTITY_CHANGED')
    need(dirident(os.fstat(jfd))==expected_journal_identity
         and dirident(os.stat(JOURNAL_DIR,dir_fd=parent,follow_symlinks=False))==expected_journal_identity,
         'JOURNAL_PARENT_PATH_CHANGED')
    st=os.fstat(entryfd)
    need(stat.S_ISREG(st.st_mode) and st.st_uid==uid and stat.S_IMODE(st.st_mode)==0o600
         and st.st_nlink==1 and ident(st)==expected_entry_identity
         and ident(os.stat(ENTRY_NAME,dir_fd=parent,follow_symlinks=False))==expected_entry_identity,
         'ORIGINAL_ENTRY_FD_PATH_CHANGED')
    lockst=os.fstat(leasefd)
    need(stat.S_ISREG(lockst.st_mode) and lockst.st_uid==uid
         and stat.S_IMODE(lockst.st_mode)==0o600 and lockst.st_nlink==1
         and ident(lockst)==expected_lock_identity
         and ident(os.stat(LOCK,dir_fd=jfd,follow_symlinks=False))==expected_lock_identity,
         'ORIGINAL_LOCK_FD_PATH_CHANGED')

def _locks(parent,jfd,entryfd,leasefd,uid,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity):
    _check_paths(parent,jfd,entryfd,leasefd,uid,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity)
    checked_dir(jfd,uid)
    entry_stat=os.fstat(entryfd)
    need(stat.S_ISREG(entry_stat.st_mode) and entry_stat.st_uid==uid
         and stat.S_IMODE(entry_stat.st_mode)==0o600 and entry_stat.st_nlink==1,
         'ORIGINAL_ENTRY_UNTRUSTED')
    need(ident(os.fstat(entryfd))==expected_entry_identity,'ORIGINAL_ENTRY_IDENTITY_UNKNOWN')
    fcntl.flock(leasefd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    fcntl.flock(entryfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    # Duplicate the same open-file description; do not create or reopen a lock.
    return os.dup(leasefd)

def status(parent,jfd,entryfd,leasefd,uid,old_entries,new_entries,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity,history_refs=None):
    _check_paths(parent,jfd,entryfd,leasefd,uid,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity)
    if childstat(jfd,STATE) is None:
        if childstat(jfd,PREINTENT) is not None:
            pre_raw=readfile(jfd,PREINTENT,uid,8192)
            try:pre=json.loads(pre_raw.decode('utf8'))
            except (ValueError,UnicodeError):raise Hold('PREINTENT_UNKNOWN')
            need(pre_raw==canonical(pre) and pre.get('format')==1
                 and pre.get('old_manifest')==OLD_MANIFEST and pre.get('new_manifest')==NEW_MANIFEST
                 and pre.get('parent_identity')==expected_parent_identity
                 and pre.get('journal_parent_identity')==expected_journal_identity
                 and pre.get('entry_identity')==expected_entry_identity,
                 'PREINTENT_BINDING_UNKNOWN')
            need(history_refs is not None and pre.get('history')==capture_history(history_refs,uid),
                 'PREINTENT_HISTORY_CHANGED')
        return {'state':'UNKNOWN_INSPECT_ONLY','retry_safe':False}
    verified_old_inventory(old_entries)
    need(history_refs is not None,'HISTORICAL_BINDINGS_REQUIRED')
    current_history=capture_history(history_refs,uid)
    j=journal(jfd,uid)
    need(j['journal_parent_identity']==expected_journal_identity
         and j['entry_identity']==expected_entry_identity
         and j['lock_identity']==expected_lock_identity,'JOURNAL_OWNER_BINDING_CHANGED')
    pre_raw=readfile(jfd,PREINTENT,uid,8192)
    try:pre=json.loads(pre_raw.decode('utf8'))
    except (ValueError,UnicodeError):raise Hold('PREINTENT_UNKNOWN')
    need(pre_raw==canonical(pre) and pre['attempt']==j['attempt']
         and pre['old_identity']==j['old_identity']
         and pre['old_manifest']==OLD_MANIFEST
         and pre['new_manifest']==NEW_MANIFEST
         and pre.get('history')==current_history
         and pre.get('parent_identity')==expected_parent_identity
         and pre.get('journal_parent_identity')==expected_journal_identity
         and pre.get('entry_identity')==expected_entry_identity
         and pre.get('old_tree_sha')==j['old_tree_sha']
         and pre.get('new_tree_sha')==j['new_tree_sha']
         and j['preintent_sha256']==sha(pre_raw),'PREINTENT_CHAIN_CHANGED')
    current=childstat(parent,TARGET)
    stage=childstat(parent,STAGE)
    retained=childstat(parent,RETAINED)
    if current is None or stage is None:
        return {'state':'UNKNOWN_INSPECT_ONLY','retry_safe':False}
    need(j.get('history')==current_history,'HISTORY_CHANGED_SINCE_INTENT')
    need(j['old_tree_sha']==sha(canonical({x:sha(y) for x,y in old_entries.items()}))
         and j['new_tree_sha']==sha(canonical({x:sha(y) for x,y in new_entries.items()}))
         and sha(old_entries['manifest.json'])==OLD_MANIFEST
         and sha(new_entries['manifest.json'])==NEW_MANIFEST,
         'JOURNAL_TREE_DIGEST_MISMATCH')
    old_id=j['old_identity'];new_id=j['stage_identity']
    rb_intent=childstat(jfd,ROLLBACK_INTENT)
    rb_result=childstat(jfd,ROLLBACK_RESULT)
    if dirident(current)==new_id and dirident(stage)==old_id:
        state='SWAPPED_OLD_RETAINED_IN_STAGE'
        if rb_intent is not None:state='ROLLBACK_NOT_APPLIED_RESULT_UNKNOWN'
        tree(parent,TARGET,uid,new_entries,new_id)
        tree(parent,STAGE,uid,old_entries,old_id)
    elif dirident(current)==old_id and dirident(stage)==new_id and retained is None:
        state='PREPARED_OR_REVERTED'
        if rb_intent is not None:
            intent_raw=readfile(jfd,ROLLBACK_INTENT,uid,8192)
            intent=json.loads(intent_raw.decode('utf8'))
            need(intent_raw==canonical(intent) and set(intent)=={'format','attempt','history_sha256','old_identity','new_identity','old_tree_sha','new_tree_sha'}
                 and intent['format']==1 and intent['attempt']==j['attempt']
                 and intent['old_identity']==old_id and intent['new_identity']==new_id
                 and intent['old_tree_sha']==j['old_tree_sha'] and intent['new_tree_sha']==j['new_tree_sha']
                 and intent['history_sha256']==sha(canonical(current_history)),
                 'ROLLBACK_INTENT_BINDING')
            if rb_result is None:state='ROLLBACK_APPLIED_RESULT_UNKNOWN'
            else:
                result_raw=readfile(jfd,ROLLBACK_RESULT,uid,8192)
                result=json.loads(result_raw.decode('utf8'))
                need(result_raw==canonical(result) and set(result)=={'format','attempt','result','rollback_intent_sha256'}
                     and result['format']==1 and result['attempt']==j['attempt']
                     and result['result']=='OLD_RESTORED_NEW_RETAINED'
                     and result['rollback_intent_sha256']==sha(intent_raw),
                     'ROLLBACK_RESULT_BINDING')
                state='ROLLED_BACK_OLD_TARGET_RESTORED_NEW_RETAINED'
        tree(parent,TARGET,uid,old_entries,old_id)
        tree(parent,STAGE,uid,new_entries,new_id)
    else:
        return {'state':'UNKNOWN_INSPECT_ONLY','retry_safe':False}
    return {'state':state,'retry_safe':False,'attempt':j['attempt']}

def execute(parent,jfd,entryfd,leasefd,old_entries,new_archive,uid,expected_parent_identity,
            expected_journal_identity,expected_entry_identity,expected_lock_identity,attempt,history_refs=None,fault=None):
    """One-shot isolated transaction; caller supplies immutable old inventory and fd witnesses."""
    need(type(attempt) is str and 8<=len(attempt)<=80 and
         all(c.isalnum() or c in '-_' for c in attempt),'ATTEMPT_REQUIRED')
    _check_paths(parent,jfd,entryfd,leasefd,uid,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity)
    lease=_locks(parent,jfd,entryfd,leasefd,uid,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity)
    try:
        need(childstat(jfd,STATE) is None and childstat(jfd,PREINTENT) is None and childstat(parent,STAGE) is None
             and childstat(parent,RETAINED) is None,'EXISTING_TRANSACTION_INSPECT_ONLY')
        need(childstat(jfd,'active-attempt.json') is None,'ACTIVE_BUSINESS_ATTEMPT')
        verified_old_inventory(old_entries)
        old_id=tree(parent,TARGET,uid,old_entries)
        need(sha(old_entries['manifest.json'])==OLD_MANIFEST,'OLD_MANIFEST_CHANGED')
        new_entries=members(new_archive,NEW_MANIFEST,NEW_ARCHIVE)
        need(history_refs is not None,'HISTORICAL_BINDINGS_REQUIRED')
        history=capture_history(history_refs,uid)
        pre=dict(format=1,attempt=attempt,old_identity=old_id,
                 old_manifest=OLD_MANIFEST,new_manifest=NEW_MANIFEST,
                 entry_identity=expected_entry_identity,
                 parent_identity=expected_parent_identity,
                 journal_parent_identity=dirident(os.fstat(jfd)),lock_identity=expected_lock_identity,history=history,
                 old_tree_sha=sha(canonical({x:sha(y) for x,y in old_entries.items()})),
                 new_tree_sha=sha(canonical({x:sha(y) for x,y in new_entries.items()})))
        writefile(jfd,PREINTENT,canonical(pre),uid)
        if fault:fault('preintent_fsynced')
        build_tree(parent,new_entries,uid)
        stage_id=tree(parent,STAGE,uid,new_entries)
        if fault:fault('staged')
        j={'format':1,'attempt':attempt,'old_manifest':OLD_MANIFEST,
           'new_manifest':NEW_MANIFEST,'old_identity':old_id,'stage_identity':stage_id,
           'old_tree_sha':sha(canonical({x:sha(y) for x,y in old_entries.items()})),
           'new_tree_sha':sha(canonical({x:sha(y) for x,y in new_entries.items()})),
           'history':history,'entry_identity':expected_entry_identity,
           'journal_parent_identity':dirident(os.fstat(jfd)),
           'lock_identity':expected_lock_identity,'preintent_sha256':sha(canonical(pre))}
        writefile(jfd,STATE,canonical(j),uid)
        if fault:fault('intent_fsynced')
        need(parent_ident(os.fstat(parent))==expected_parent_identity
             and dirident(os.fstat(jfd))==j['journal_parent_identity']
             and dirident(os.stat(JOURNAL_DIR,dir_fd=parent,follow_symlinks=False))==j['journal_parent_identity']
             and ident(os.fstat(entryfd))==expected_entry_identity
             and ident(os.fstat(leasefd))==expected_lock_identity
             and ident(os.stat(LOCK,dir_fd=jfd,follow_symlinks=False))==expected_lock_identity,
             'FINAL_LEASE_OR_PARENT_CHANGED')
        tree(parent,TARGET,uid,old_entries,old_id)
        tree(parent,STAGE,uid,new_entries,stage_id)
        need(journal(jfd,uid)==j,'INTENT_CHANGED')
        if fault:fault('before_switch')
        switch_attempted=True
        try:exchange(parent,TARGET,STAGE)
        except BaseException:raise Hold('EXCHANGE_RESULT_UNKNOWN_INSPECT_ONLY') from None
        # From this point a failure is always UNKNOWN, and cannot be retried.
        try:
            if fault:fault('after_exchange')
            os.fsync(parent)
            result=status(parent,jfd,entryfd,leasefd,uid,old_entries,new_entries,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity,history_refs)
            need(result['state']=='SWAPPED_OLD_RETAINED_IN_STAGE','SWITCH_STATUS_UNKNOWN')
            return result
        except BaseException:raise Hold('POST_SWITCH_UNKNOWN_INSPECT_ONLY')
    finally:
        try:_close_lease(lease)
        except BaseException:
            if 'switch_attempted' in locals() and switch_attempted:
                raise Hold('POST_SWITCH_CLOSE_UNKNOWN_INSPECT_ONLY') from None
            raise

def _close_lease(fd):
    os.close(fd)

def rollback(parent,jfd,entryfd,leasefd,old_entries,new_entries,uid,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity,history_refs=None):
    _check_paths(parent,jfd,entryfd,leasefd,uid,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity)
    need(history_refs is not None,'HISTORICAL_BINDINGS_REQUIRED')
    lease=_locks(parent,jfd,entryfd,leasefd,uid,expected_parent_identity,expected_journal_identity,expected_entry_identity,expected_lock_identity)
    try:
        need(childstat(jfd,'active-attempt.json') is None and childstat(parent,RETAINED) is None,'ROLLBACK_CONFLICT')
        capture_history(history_refs,uid)
        need(childstat(jfd,ROLLBACK_INTENT) is None
             and childstat(jfd,ROLLBACK_RESULT) is None,'ROLLBACK_ALREADY_ATTEMPTED')
        result=status(parent,jfd,uid,old_entries,new_entries,history_refs)
        need(result['state']=='SWAPPED_OLD_RETAINED_IN_STAGE','ROLLBACK_NOT_OWNED')
        binding=journal(jfd,uid)
        history=capture_history(history_refs,uid)
        intent={'format':1,'attempt':binding['attempt'],
                'history_sha256':sha(canonical(history)),
                'old_identity':binding['old_identity'],
                'new_identity':binding['stage_identity'],
                'old_tree_sha':binding['old_tree_sha'],
                'new_tree_sha':binding['new_tree_sha']}
        writefile(jfd,ROLLBACK_INTENT,canonical(intent),uid)
        need(childstat(jfd,'active-attempt.json') is None
             and childstat(parent,RETAINED) is None
             and ident(os.fstat(entryfd))==expected_entry_identity
             and sha(canonical(capture_history(history_refs,uid)))==intent['history_sha256'],
             'ROLLBACK_BOUNDARY_CHANGED')
        result=status(parent,jfd,entryfd,uid,old_entries,new_entries,expected_parent_identity,expected_journal_identity,expected_entry_identity,history_refs)
        need(result['state']=='SWAPPED_OLD_RETAINED_IN_STAGE','ROLLBACK_BOUNDARY_CHANGED')
        rollback_attempted=True
        try:exchange(parent,TARGET,STAGE)
        except BaseException:raise Hold('ROLLBACK_EXCHANGE_UNKNOWN_INSPECT_ONLY') from None
        try:
            os.fsync(parent)
            result=status(parent,jfd,entryfd,uid,old_entries,new_entries,expected_parent_identity,expected_journal_identity,expected_entry_identity,history_refs)
            need(result['state'] in ('PREPARED_OR_REVERTED','ROLLBACK_APPLIED_RESULT_UNKNOWN'),'ROLLBACK_UNKNOWN')
            writefile(jfd,ROLLBACK_RESULT,canonical({'format':1,'attempt':intent['attempt'],
                     'result':'OLD_RESTORED_NEW_RETAINED','rollback_intent_sha256':sha(canonical(intent))}),uid)
            return {'state':'ROLLED_BACK_OLD_TARGET_RESTORED_NEW_STAGE_RETAINED',
                    'retry_safe':False}
        except BaseException:raise Hold('ROLLBACK_UNKNOWN_INSPECT_ONLY')
    finally:
        try:_close_lease(lease)
        except BaseException:
            if 'rollback_attempted' in locals() and rollback_attempted:
                raise Hold('ROLLBACK_CLOSE_UNKNOWN_INSPECT_ONLY') from None
            raise
