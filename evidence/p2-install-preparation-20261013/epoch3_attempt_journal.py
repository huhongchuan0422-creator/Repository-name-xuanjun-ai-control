"""One durable attempt file inside the existing P2 transaction, not a task queue."""
import hashlib,json,os,stat,tempfile
DIRECTORY=('/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/'
           'legacy-isolation-c529c379-9341-4510-8384-fc6be1e412e5')
NAME='epoch3-recovery-execution.json'

def require(value,label):
 if not value:raise ValueError(label)

def packed(value):
 raw=(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
 require(len(raw)<=1048576,'ATTEMPT_SIZE_BOUND');return raw

class AttemptJournal:
 def __init__(self,directory):
  require(directory==DIRECTORY and os.path.realpath(directory)==directory,'ATTEMPT_EXACT_DIRECTORY')
  self.directory=directory;self.path=directory+'/'+NAME;self.last_sha=None
 def authority(self):
  info=os.lstat(self.directory)
  require(os.geteuid()==0 and stat.S_ISDIR(info.st_mode) and info.st_uid==0 and
          info.st_gid==0 and stat.S_IMODE(info.st_mode)==0o700 and
          os.path.realpath(self.directory)==self.directory,'ATTEMPT_AUTHORITY')
 def sync(self):
  fd=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:os.fsync(fd)
  finally:os.close(fd)
 @staticmethod
 def write(fd,raw):
  with os.fdopen(fd,'wb') as stream:
   stream.write(raw);stream.flush();os.fsync(stream.fileno())
 def read(self):
  fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
  with os.fdopen(fd,'rb') as stream:
   info=os.fstat(stream.fileno())
   require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_gid==0 and
           stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,'ATTEMPT_FILE_IDENTITY')
   raw=stream.read(1048577);end=os.fstat(stream.fileno())
  require(len(raw)<=1048576 and (info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)==
          (end.st_ino,end.st_size,end.st_mtime_ns,end.st_ctime_ns),'ATTEMPT_CHANGED')
  return raw
 def create(self,value):
  self.authority();raw=packed(value)
  fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  # Any failure leaves an existing file/uncertain attempt; no automatic removal.
  self.write(fd,raw);self.sync();self.last_sha=hashlib.sha256(raw).hexdigest()
 def save(self,value):
  self.authority();raw=packed(value)
  require(self.last_sha is not None and hashlib.sha256(self.read()).hexdigest()==self.last_sha,
          'ATTEMPT_STALE_OR_UNCLAIMED')
  fd,temporary=tempfile.mkstemp(prefix='.epoch3-attempt-',dir=self.directory)
  try:
   os.fchmod(fd,0o600);self.write(fd,raw);fd=-1
   require(hashlib.sha256(self.read()).hexdigest()==self.last_sha,'ATTEMPT_CHANGED_BEFORE_PUBLISH')
   os.replace(temporary,self.path);self.sync();self.last_sha=hashlib.sha256(raw).hexdigest()
  finally:
   if fd>=0:
    try:os.close(fd)
    except OSError:pass
   if os.path.lexists(temporary):os.unlink(temporary)
