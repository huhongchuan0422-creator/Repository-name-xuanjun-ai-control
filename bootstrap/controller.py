"""TEST candidate controller: verified bytes -> private staging -> atomic symlink.

No carrier code is imported or executed. Production integration is not provided.
"""
import io, json, os, sqlite3, stat, tarfile, tempfile
import secure_bootstrap as verifylib

class ControllerError(Exception): pass

def check(value, reason):
    if not value: raise ControllerError(reason)

def ledger(path, owner):
    verifylib.checked_ledger_path(path,owner)
    db=sqlite3.connect('file:'+path+'?mode=rw',uri=True,timeout=5,isolation_level=None)
    check(db.execute('pragma journal_mode').fetchone()[0].lower()=='wal','WAL_REQUIRED')
    db.execute('pragma busy_timeout=5000');db.execute('pragma synchronous=FULL')
    return db

def transition(path, owner, nonce, before, after):
    db=ledger(path,owner)
    try:
        db.execute('BEGIN IMMEDIATE')
        cur=db.execute('UPDATE operations SET state=? WHERE nonce=? AND state=?',(after,nonce,before))
        check(cur.rowcount==1,'STATE_CONFLICT')
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:db.execute('ROLLBACK')
        raise
    finally:db.close()

def log(fd, event):
    blob=(json.dumps(event,sort_keys=True,separators=(',',':'))+'\n').encode()
    check(os.write(fd,blob)==len(blob),'SHORT_LOG');os.fsync(fd)

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

def run(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,root,owner=0,failpoint=None):
    """Fixture implementation only; caller must exclusively control root and ledger."""
    rootst=os.lstat(root);check(stat.S_ISDIR(rootst.st_mode) and rootst.st_uid==owner and not rootst.st_mode&0o077,'ROOT_PERMISSIONS')
    # Before effects, verify complete signed input and atomically reserve nonce.
    blob,p=verifylib.verify(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,owner=owner)
    nonce=p['nonce']; check(nonce not in ('.','..') and '/' not in nonce,'NONCE_PATH')
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    running=False
    try:
        transition(ledger_path,owner,nonce,'RESERVED','RUNNING');running=True
        log(log_fd,{'event':'RUNNING','nonce':nonce})
        if failpoint=='after_running':raise ControllerError('INJECTED')
        name='stage-'+nonce
        os.mkdir(name,0o700,dir_fd=rootfd);os.fsync(rootfd)
        stage=open_dir(rootfd,name)
        try:extract(blob,stage)
        finally:os.close(stage)
        if failpoint=='after_extract':raise ControllerError('INJECTED')
        target='release-'+nonce
        os.rename(name,target,src_dir_fd=rootfd,dst_dir_fd=rootfd);os.fsync(rootfd)
        if failpoint=='after_release':raise ControllerError('INJECTED')
        link='.current-'+nonce
        os.symlink(target,link,dir_fd=rootfd)
        os.rename(link,'current',src_dir_fd=rootfd,dst_dir_fd=rootfd);os.fsync(rootfd)
        if failpoint=='after_switch':raise ControllerError('INJECTED')
        log(log_fd,{'event':'SUCCEEDED','nonce':nonce,'target':target})
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
    db=ledger(path,owner)
    try:
        db.execute('BEGIN IMMEDIATE');db.execute("UPDATE operations SET state='UNKNOWN' WHERE state='RUNNING'");db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:db.execute('ROLLBACK')
        raise
    finally:db.close()
