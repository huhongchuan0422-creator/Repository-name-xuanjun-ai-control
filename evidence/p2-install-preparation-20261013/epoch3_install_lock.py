"""Reuse the existing protected install lock; never create a replacement lock."""
import contextlib,fcntl,os,stat
PATH='/run/xuanjun-p2-install.lock'
@contextlib.contextmanager
def held():
 if os.geteuid()!=0 or os.path.realpath(PATH)!=PATH:raise ValueError('INSTALL_LOCK_AUTHORITY')
 fd=os.open(PATH,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  info=os.fstat(fd)
  if (not stat.S_ISREG(info.st_mode) or (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)!=(0,0,0o600,1)):
   raise ValueError('INSTALL_LOCK_IDENTITY')
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  current=os.lstat(PATH)
  if (current.st_dev,current.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('INSTALL_LOCK_REPLACED')
  yield
 finally:os.close(fd)
