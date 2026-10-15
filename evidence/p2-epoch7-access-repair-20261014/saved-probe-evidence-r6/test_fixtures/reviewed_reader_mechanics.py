"""Test-only source comparison. Never executed on a host."""

def stamp(i):return tuple(getattr(i,'st_'+k) for k in ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'))


@contextlib.contextmanager
def bounded():
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0));previous=signal.getsignal(signal.SIGALRM)
    def expired(*unused):raise Deadline()
    signal.signal(signal.SIGALRM,expired);primary=None
    try:
        signal.setitimer(signal.ITIMER_REAL,60,1);yield
    except BaseException as error:primary=error;raise
    finally:
        failed=False
        try:signal.setitimer(signal.ITIMER_REAL,0)
        except BaseException:failed=True
        try:signal.signal(signal.SIGALRM,previous)
        except BaseException:failed=True
        if failed:
            if primary is not None:primary.diagnostic_cleanup_failed=True
            else:
                failure=ValueError('DIAGNOSTIC_BOUNDARY');failure.diagnostic_cleanup_failed=True;raise failure


def authority(fd,directory):
    i=os.fstat(fd)
    need((stat.S_ISDIR(i.st_mode) if directory else stat.S_ISREG(i.st_mode)) and i.st_uid==i.st_gid==0 and not i.st_mode&0o7022 and (directory or i.st_nlink==1))
    for name in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
        try:os.getxattr(fd,name)
        except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP))
        else:need(False)
    return i


def entry_bytes():
    held=[];rows=[];primary=None
    try:
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);held.append(fd);rows.append((fd,None,None,stamp(authority(fd,True))))
        for name in KIT[1:].split('/'):
            parent=fd;fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);held.append(fd)
            pin=stamp(authority(fd,True));need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==pin);rows.append((fd,parent,name,pin))
        parent=fd;name='epoch7_recovery_entry.py';fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent);held.append(fd)
        before=authority(fd,False);need(0<before.st_size<=1048576);chunks=[];count=0
        while True:
            part=os.read(fd,min(65536,1048577-count))
            if not part:break
            count+=len(part);need(count<=1048576);chunks.append(part)
        raw=b''.join(chunks);need(count==before.st_size and sha(raw)==ENTRY_SHA and stamp(before)==stamp(authority(fd,False))==stamp(os.stat(name,dir_fd=parent,follow_symlinks=False)))
        for fd,parent,name,pin in rows:
            need(stamp(authority(fd,True))==pin)
            if parent is not None:need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==pin)
        return raw
    except BaseException as error:primary=error;raise
    finally:
        failure=None
        for fd in reversed(held):
            try:os.close(fd)
            except BaseException as error:
                if failure is None:failure=error
        if failure is not None:
            if primary is not None:primary.diagnostic_cleanup_failed=True
            else:
                failure.diagnostic_cleanup_failed=True;raise failure
