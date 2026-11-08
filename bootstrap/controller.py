"""TEST candidate controller: verified bytes -> private staging -> atomic symlink.

No carrier code is imported or executed. Production integration is not provided.
"""
import fcntl, hashlib, io, json, os, re, sqlite3, stat, tarfile, tempfile
import secure_bootstrap as verifylib

class ControllerError(Exception): pass

def check(value, reason):
    if not value: raise ControllerError(reason)

def transition(path, owner, nonce, before, after):
    from path_guard import GuardedLedger
    with GuardedLedger(path,owner) as guarded:
        db=guarded.db
        try:
            guarded.check();db.execute('BEGIN IMMEDIATE');guarded.check()
            cur=db.execute('UPDATE operations SET state=? WHERE nonce=? AND state=?',(after,nonce,before))
            check(cur.rowcount==1,'STATE_CONFLICT');guarded.check();db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:db.execute('ROLLBACK')
            raise

def log(fd, event, audit=None):
    blob=(json.dumps(event,sort_keys=True,separators=(',',':'))+'\n').encode()
    if audit is not None:audit.write(blob)
    else:check(os.write(fd,blob)==len(blob),'SHORT_LOG');os.fsync(fd)

def open_dir(parent, name):
    return os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)

def extract(blob, rootfd):
    # All archive entries already passed the bootstrap manifest check. Use the
    # same captured immutable bytes, no pathname reopening and no carrier exec.
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:*') as archive:
        for member in archive:
            parts=member.name.split('/');fd=os.dup(rootfd)
            try:
                for part in parts[:-1]:
                    try:os.mkdir(part,0o700,dir_fd=fd)
                    except FileExistsError:pass
                    nxt=open_dir(fd,part);os.close(fd);fd=nxt
                if member.isdir():
                    try:os.mkdir(parts[-1],0o700,dir_fd=fd)
                    except FileExistsError:pass
                    nxt=open_dir(fd,parts[-1]);os.fsync(nxt);os.close(nxt)
                else:
                    out=os.open(parts[-1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                    try:
                        data=archive.extractfile(member).read(member.size+1)
                        check(len(data)==member.size,'EXTRACTION_SIZE')
                        pos=0
                        while pos<len(data):pos+=os.write(out,data[pos:])
                        os.fsync(out)
                    finally:os.close(out)
                os.fsync(fd)
            finally:os.close(fd)
    os.fsync(rootfd)

def _name(value):
    check(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',value) and value not in ('.','..'),'EVIDENCE_NAME')
    return value

def _file_bytes(dfd, name, owner, limit=4*1024*1024):
    fd=os.open(_name(name),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dfd)
    try:return verifylib.stable_read(fd,owner,limit)
    finally:os.close(fd)

def verified_tree(rootfd,target,owner):
    """Validate every installed entry against its manifest; return tree digest."""
    directory=open_dir(rootfd,_name(target));entries={}
    try:
        rootstat=os.fstat(directory);check(rootstat.st_uid==owner and stat.S_IMODE(rootstat.st_mode)==0o700,'TREE_ROOT_MODE')
        raw=_file_bytes(directory,'.bootstrap-manifest.json',owner)
        manifest=verifylib.parse(raw);check(isinstance(manifest,dict) and isinstance(manifest.get('members'),dict),'TREE_MANIFEST')
        members=manifest['members']
        def walk(fd,prefix=''):
            for name in sorted(os.listdir(fd)):
                if not prefix and name=='.bootstrap-manifest.json':continue
                check(name not in ('','.','..') and '/' not in name,'TREE_PATH')
                path=prefix+name;info=os.stat(name,dir_fd=fd,follow_symlinks=False)
                check(info.st_uid==owner,'TREE_OWNER')
                if stat.S_ISDIR(info.st_mode):
                    check(stat.S_IMODE(info.st_mode)==0o700,'TREE_DIR_MODE')
                    sub=open_dir(fd,name)
                    try:
                        st=os.fstat(sub);check((st.st_dev,st.st_ino)==(info.st_dev,info.st_ino),'TREE_CHANGED')
                        entries[path]={'type':'directory'};walk(sub,path+'/')
                    finally:os.close(sub)
                else:
                    check(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'TREE_FILE_MODE')
                    f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
                    try:
                        st=os.fstat(f);check((st.st_dev,st.st_ino)==(info.st_dev,info.st_ino),'TREE_CHANGED')
                        data=verifylib.stable_read(f,owner,64*1024*1024)
                    finally:os.close(f)
                    entries[path]={'type':'file','size':len(data),'sha256':verifylib.sha(data)}
        walk(directory);check(entries==members,'TREE_MEMBER_MISMATCH')
        return verifylib.sha(verifylib.canonical({'manifest_sha256':verifylib.sha(raw),'members':entries}))
    finally:os.close(directory)

def verify_operation_receipt(raw, trust_raw, operation, attempt, current_tree, prestate_tree):
    """Verify controller-signed receipt, independent from carrier code."""
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    trust=verifylib.parse(trust_raw);receipt=verifylib.parse(raw)
    check(trust.get('mode')=='ED25519' and trust.get('environment') in ('TEST_ONLY','PRODUCTION'),'RECEIPT_TRUST')
    check(isinstance(receipt,dict) and set(receipt)=={'payload','signature'},'RECEIPT_FORMAT')
    expected={'operation':operation,'attempt':attempt,'current_tree_sha256':current_tree,'prestate_tree_sha256':prestate_tree,'controller':trust.get('controller'),'outcome':'SUCCEEDED'}
    check(receipt['payload']==expected,'RECEIPT_BINDING')
    try:
        key=Ed25519PublicKey.from_public_bytes(base64.b64decode(trust['public_key'],validate=True))
        key.verify(base64.b64decode(receipt['signature'],validate=True),verifylib.canonical(expected))
    except Exception:raise ControllerError('RECEIPT_SIGNATURE')
    return expected

def _target_manifest(rootfd, target, owner):
    d=open_dir(rootfd,_name(target))
    try:
        st=os.fstat(d);check(st.st_uid==owner and not st.st_mode&0o077,'TARGET_OWNER_MODE')
        return verifylib.sha(_file_bytes(d,'.bootstrap-manifest.json',owner))
    finally:os.close(d)

def _current(rootfd):
    try:
        st=os.stat('current',dir_fd=rootfd,follow_symlinks=False)
        check(stat.S_ISLNK(st.st_mode),'CURRENT_NOT_LINK')
        return _name(os.readlink('current',dir_fd=rootfd))
    except FileNotFoundError:return None

def _exists(rootfd,name):
    try:os.stat(_name(name),dir_fd=rootfd,follow_symlinks=False);return True
    except FileNotFoundError:return False

def _remove_tree(parent,name,owner):
    """Validate entire tree before deletion; caller holds exclusive controller lock."""
    def walk(parent_fd, item, remove):
        d=open_dir(parent_fd,_name(item));st=os.fstat(d)
        check(st.st_uid==owner and not st.st_mode&0o077,'STAGE_OWNER_MODE')
        try:
            for child in os.listdir(d):
                c=os.stat(child,dir_fd=d,follow_symlinks=False)
                if stat.S_ISDIR(c.st_mode):walk(d,child,remove)
                else:
                    check(stat.S_ISREG(c.st_mode) and c.st_nlink==1 and c.st_uid==owner and not c.st_mode&0o077,'UNSAFE_STAGE_ENTRY')
                    if remove:os.unlink(child,dir_fd=d)
            if remove:os.fsync(d)
        finally:os.close(d)
        current=os.stat(item,dir_fd=parent_fd,follow_symlinks=False)
        check((st.st_dev,st.st_ino)==(current.st_dev,current.st_ino),'STAGE_REPLACED')
        if remove:os.rmdir(item,dir_fd=parent_fd);os.fsync(parent_fd)
    walk(parent,name,False);walk(parent,name,True)

def _reconcile_pending_locked(path, owner, root, log_fd, audit=None):
    """Reconcile under the caller-held controller lock; missing evidence holds."""
    from path_guard import GuardedLedger
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        st=os.fstat(rootfd);check(st.st_uid==owner and not st.st_mode&0o077,'ROOT_PERMISSIONS')
        with GuardedLedger(path,owner) as g:
            db=g.db;db.row_factory=sqlite3.Row
            g.check();db.execute('BEGIN IMMEDIATE')
            try:
                columns={r[1] for r in db.execute('PRAGMA table_info(operations)')}
                required={'prestate_target','prestate_hash','staging_target','manifest_hash','intended_target','receipt_hash'}
                rows=db.execute("SELECT * FROM operations WHERE state IN ('RESERVED','RUNNING','UNKNOWN')").fetchall()
                for row in rows:
                    before=row['state'];outcome='UNKNOWN';reason='EVIDENCE_MISSING'
                    try:
                        check(required.issubset(columns),'EVIDENCE_SCHEMA')
                        pre=_name(row['prestate_target']);stage=_name(row['staging_target']);target=_name(row['intended_target'])
                        prehash=row['prestate_hash'];mh=row['manifest_hash'];rh=row['receipt_hash']
                        check(all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in (prehash,mh)),'EVIDENCE_DIGEST')
                        check(_target_manifest(rootfd,pre,owner)==prehash,'PRESTATE_MISMATCH')
                        current=_current(rootfd);stage_exists=_exists(rootfd,stage);target_exists=_exists(rootfd,target)
                        if current==target:
                            check(not stage_exists and target_exists,'TARGET_CONFLICT')
                            check(_target_manifest(rootfd,target,owner)==mh,'TARGET_MISMATCH')
                            check(isinstance(rh,str) and re.fullmatch('[0-9a-f]{64}',rh),'RECEIPT_MISSING')
                            raw=_file_bytes(rootfd,'receipt-'+row['nonce']+'.json',owner,65536)
                            check(verifylib.sha(raw)==rh,'RECEIPT_MISMATCH')
                            # Legacy local receipts carry no controller signature.
                            # Never promote them to SUCCEEDED.
                            raise ControllerError('SIGNED_OPERATION_RECEIPT_REQUIRED')
                        elif current==pre:
                            check(not target_exists,'UNSWITCHED_TARGET_CONFLICT')
                            if stage_exists:
                                check(_target_manifest(rootfd,stage,owner)==mh,'STAGE_MISMATCH')
                                _remove_tree(rootfd,stage,owner)
                            outcome='FAILED';reason='PRESTATE_UNCHANGED'
                        else:reason='CURRENT_CONFLICT'
                    except (OSError,ValueError,TypeError,KeyError,ControllerError):
                        outcome='UNKNOWN';reason='EVIDENCE_CONFLICT_OR_MISSING'
                    if before!=outcome:
                        log(log_fd,{'event':'RECONCILE','nonce':row['nonce'],'from':before,'to':outcome,'reason':reason},audit)
                        g.check();db.execute('UPDATE operations SET state=? WHERE nonce=? AND state=?',(outcome,row['nonce'],before))
                g.check();db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:db.execute('ROLLBACK')
                raise
            return db.execute("SELECT COUNT(*) FROM operations WHERE state IN ('RESERVED','RUNNING','UNKNOWN')").fetchone()[0]
    finally:os.close(rootfd)

def _run_locked(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,root,owner=0,failpoint=None,audit=None):
    """Fixture implementation only; caller must exclusively control root and ledger."""
    rootst=os.lstat(root);check(stat.S_ISDIR(rootst.st_mode) and rootst.st_uid==owner and not rootst.st_mode&0o077,'ROOT_PERMISSIONS')
    check(_reconcile_pending_locked(ledger_path,owner,root,log_fd,audit)==0,'UNKNOWN_RECONCILIATION_REQUIRED')
    # Before effects, verify complete signed input and atomically reserve nonce.
    if audit is not None: audit.write(b'{"event":"STARTING"}\n')
    currentfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        pre=_current(currentfd);check(pre is not None,'PRESTATE_REQUIRED')
        evidence={'prestate_target':pre,'prestate_hash':_target_manifest(currentfd,pre,owner)}
    finally:os.close(currentfd)
    blob,p=verifylib.verify(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,owner=owner,audit=audit,evidence=evidence)
    nonce=p['nonce']; check(nonce not in ('.','..') and '/' not in nonce,'NONCE_PATH')
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    running=False
    try:
        transition(ledger_path,owner,nonce,'RESERVED','RUNNING');running=True
        log(log_fd,{'event':'RUNNING','nonce':nonce},audit)
        if failpoint=='after_running':raise ControllerError('INJECTED')
        name='stage-'+nonce
        os.mkdir(name,0o700,dir_fd=rootfd);os.fsync(rootfd)
        stage=open_dir(rootfd,name)
        try:
            extract(blob,stage)
            manifest=verifylib.stable_read(manifest_fd,owner,4*1024*1024)
            check(verifylib.sha(manifest)==p['manifest_sha256'],'MANIFEST_CHANGED')
            fd=os.open('.bootstrap-manifest.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=stage)
            try:
                check(os.write(fd,manifest)==len(manifest),'SHORT_MANIFEST_WRITE');os.fsync(fd)
            finally:os.close(fd)
            os.fsync(stage)
        finally:os.close(stage)
        if failpoint=='after_extract':raise ControllerError('INJECTED')
        target='release-'+nonce
        os.rename(name,target,src_dir_fd=rootfd,dst_dir_fd=rootfd);os.fsync(rootfd)
        if failpoint=='after_release':raise ControllerError('INJECTED')
        link='.current-'+nonce
        os.symlink(target,link,dir_fd=rootfd)
        os.rename(link,'current',src_dir_fd=rootfd,dst_dir_fd=rootfd);os.fsync(rootfd)
        if failpoint=='after_switch':raise ControllerError('INJECTED')
        receipt=verifylib.canonical({'nonce':nonce,'target':target,'manifest_sha256':p['manifest_sha256'],'outcome':'SUCCEEDED'})
        fd=os.open('receipt-'+nonce+'.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=rootfd)
        try:check(os.write(fd,receipt)==len(receipt),'SHORT_RECEIPT_WRITE');os.fsync(fd)
        finally:os.close(fd)
        os.fsync(rootfd)
        from path_guard import GuardedLedger
        with GuardedLedger(ledger_path,owner) as g:
            g.db.execute('BEGIN IMMEDIATE')
            try:
                g.check();cur=g.db.execute("UPDATE operations SET receipt_hash=? WHERE nonce=? AND state='RUNNING'",(verifylib.sha(receipt),nonce));check(cur.rowcount==1,'RECEIPT_STATE');g.db.execute('COMMIT')
            except BaseException:
                if g.db.in_transaction:g.db.execute('ROLLBACK')
                raise
        log(log_fd,{'event':'SUCCEEDED','nonce':nonce,'target':target},audit)
        transition(ledger_path,owner,nonce,'RUNNING','SUCCEEDED');running=False
        return target
    except BaseException:
        if running:
            try:transition(ledger_path,owner,nonce,'RUNNING','UNKNOWN')
            except Exception:pass
        raise
    finally:os.close(rootfd)

def recover(path, owner):
    """Do not replay after a process crash. No automatic reconciliation."""
    from path_guard import GuardedLedger
    with GuardedLedger(path,owner) as guarded:
        db=guarded.db
        try:
            guarded.check();db.execute('BEGIN IMMEDIATE');guarded.check()
            db.execute("UPDATE operations SET state='UNKNOWN' WHERE state='RUNNING'");guarded.check();db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:db.execute('ROLLBACK')
            raise


def run(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,root,owner=0,failpoint=None,audit=None):
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        st=os.fstat(rootfd);check(st.st_uid==owner and not st.st_mode&0o077,'ROOT_PERMISSIONS')
        lock=os.open('.bootstrap.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=rootfd)
        try:
            st=os.fstat(lock);check(stat.S_ISREG(st.st_mode) and st.st_uid==owner and st.st_nlink==1 and not st.st_mode&0o077,'LOCK_PERMISSIONS')
            fcntl.flock(lock,fcntl.LOCK_EX)
            return _run_locked(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,root,owner,failpoint,audit)
        finally:os.close(lock)
    finally:os.close(rootfd)


def reconcile_pending(path, owner, root, log_fd, audit=None):
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        st=os.fstat(rootfd);check(st.st_uid==owner and not st.st_mode&0o077,'ROOT_PERMISSIONS')
        lock=os.open('.bootstrap.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=rootfd)
        try:
            st=os.fstat(lock);check(stat.S_ISREG(st.st_mode) and st.st_uid==owner and st.st_nlink==1 and not st.st_mode&0o077,'LOCK_PERMISSIONS')
            fcntl.flock(lock,fcntl.LOCK_EX)
            return _reconcile_pending_locked(path,owner,root,log_fd,audit)
        finally:os.close(lock)
    finally:os.close(rootfd)
