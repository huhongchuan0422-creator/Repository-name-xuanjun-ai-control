"""Descriptor-based path validation for controller-owned files.

The caller must keep Guard open while using its directory descriptor. This
module does not make SQLite pathname opens race-free; see README.
"""
import os, stat

class PathHold(ValueError): pass

def guard(condition, code):
    if not condition: raise PathHold(code)

class Guard:
    def __init__(self, path, owner):
        guard(os.path.isabs(path) and path != '/' and not path.endswith('/'),'ABSOLUTE_FILE_PATH_REQUIRED')
        parts=path.split('/')[1:]
        guard(all(p not in ('','.','..') for p in parts),'PATH_COMPONENT')
        self.name=parts[-1];self.owner=owner;self.fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            self.check_dir(self.fd)
            for name in parts[:-1]:
                new=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.fd)
                try:self.check_dir(new)
                except BaseException:os.close(new);raise
                os.close(self.fd);self.fd=new
        except BaseException:
            os.close(self.fd);self.fd=None;raise
    def check_dir(self,fd):
        st=os.fstat(fd)
        guard(stat.S_ISDIR(st.st_mode) and st.st_uid in (0,self.owner) and not st.st_mode & 0o022,'DIRECTORY_TRUST')
    def open_file(self, flags=os.O_RDONLY):
        fd=os.open(self.name,flags|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.fd)
        try:
            st=os.fstat(fd)
            guard(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==self.owner and not st.st_mode&0o077,'FILE_TRUST')
        except BaseException:os.close(fd);raise
        return fd
    def matches(self,fd):
        first=os.fstat(fd);last=os.stat(self.name,dir_fd=self.fd,follow_symlinks=False)
        return (first.st_dev,first.st_ino)==(last.st_dev,last.st_ino) and stat.S_ISREG(last.st_mode) and last.st_nlink==1
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class GuardedLedger:
    """SQLite handle bound to a held private parent dirfd, not the input path."""
    def __init__(self,path,owner):
        import sqlite3
        self.guard=Guard(path,owner); self.file=None; self.db=None
        try:
            st=os.fstat(self.guard.fd)
            guard(st.st_uid==owner and not st.st_mode&0o077,'PRIVATE_LEDGER_DIRECTORY_REQUIRED')
            self.file=self.guard.open_file(os.O_RDWR)
            self.check_sidecars()
            proc='/proc/self/fd/%d/%s' % (self.guard.fd,self.guard.name)
            guard(os.path.exists('/proc/self/fd/%d'%self.guard.fd),'PROC_FD_REQUIRED')
            self.db=sqlite3.connect('file:'+proc+'?mode=rw',uri=True,timeout=5,isolation_level=None)
            self.check()
            guard(self.db.execute('PRAGMA journal_mode').fetchone()[0].lower()=='wal','WAL_REQUIRED')
            self.db.execute('PRAGMA busy_timeout=5000');self.db.execute('PRAGMA synchronous=FULL')
            self.check()
        except BaseException:self.close();raise
    def check_sidecars(self):
        for suffix in ('-wal','-shm','-journal'):
            try: st=os.stat(self.guard.name+suffix,dir_fd=self.guard.fd,follow_symlinks=False)
            except FileNotFoundError:continue
            guard(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==self.guard.owner and not st.st_mode&0o077,'SIDECAR_TRUST')
    def check(self):
        guard(self.guard.matches(self.file),'LEDGER_REPLACED');self.check_sidecars()
    def close(self):
        if self.db is not None:self.db.close();self.db=None
        if self.file is not None:os.close(self.file);self.file=None
        self.guard.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class GuardedAudit:
    def __init__(self,path,owner):
        self.guard=Guard(path,owner);self.file=None
        try:self.file=self.guard.open_file(os.O_WRONLY|os.O_APPEND)
        except BaseException:self.guard.close();raise
    def write(self,data):
        guard(self.guard.matches(self.file),'AUDIT_REPLACED')
        guard(os.write(self.file,data)==len(data),'AUDIT_SHORT_WRITE');os.fsync(self.file)
    def close(self):
        if self.file is not None:os.close(self.file);self.file=None
        self.guard.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
