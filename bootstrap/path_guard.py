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
