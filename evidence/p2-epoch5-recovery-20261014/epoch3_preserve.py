"""Preserve exact failed-transaction evidence before admitted epoch3 recovery.

Production caller must hold the existing install lock, consume the single attempt
and verify fresh approval/exclusion first. No credential generation or deletion;
old receipts stay at original paths except TLS journal/root moved into preservation.
"""
import hashlib,json,os,stat
from inspect_epoch3 import PINS,T,C,TLS,file_data
ARCHIVE=T+'/epoch3-prior-receipts'

def need(value,label):
 if not value:raise ValueError(label)
def sha(data):return hashlib.sha256(data).hexdigest()
def sync(path):
 fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
def authority(path):
 info=os.lstat(path)
 need(os.geteuid()==0 and os.path.realpath(path)==path and stat.S_ISDIR(info.st_mode)
      and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o700),'PRESERVE_AUTHORITY')
def empty_tls():
 authority(TLS)
 need(sorted(os.listdir(TLS))==['config','logs','work'],'PRESERVE_TLS_SCOPE')
 for name in ('config','logs','work'):
  authority(TLS+'/'+name);need(os.listdir(TLS+'/'+name)==[],'PRESERVE_TLS_EFFECTS')
def exclusive_file(path,data):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
 sync(os.path.dirname(path))

def preserve_prior_receipts():
 authority(T);authority(C);empty_tls()
 need(not os.path.lexists(ARCHIVE),'PRESERVE_ALREADY_ATTEMPTED')
 paths=(C+'/install-receipt.json',T+'/runtime-provisioning.json',T+'/recovery-execution.json',
        T+'/bootstrap-files.json',T+'/publisher-bootstrap.json',T+'/tls-lifecycle.json')
 saved={}
 for path in paths:
  data,info=file_data(path)
  need(sha(data)==PINS[path] and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o600,1),
       'PRESERVE_RECEIPT_CHANGED')
  saved[path]=data
 os.mkdir(ARCHIVE,0o700);sync(T)
 # Destination is freshly exclusive root0700. Originals are never overwritten.
 for path in paths:
  exclusive_file(ARCHIVE+'/'+os.path.basename(path),saved[path])
 empty_tls()
 for path,data in saved.items():need(file_data(path)[0]==data,'PRESERVE_RECEIPT_RACE')
 # Both names were proven absent in the freshly-owned archive. Any partial move
 # is retained as an uncertain effect by the caller's durable phase INTENT.
 need(not os.path.lexists(ARCHIVE+'/tls-root'),'PRESERVE_TLS_DESTINATION')
 os.rename(TLS,ARCHIVE+'/tls-root');sync(os.path.dirname(TLS));sync(ARCHIVE)
 tls_journal=T+'/tls-lifecycle.json'
 need(file_data(tls_journal)[0]==saved[tls_journal],'PRESERVE_TLS_JOURNAL_RACE')
 need(not os.path.lexists(ARCHIVE+'/tls-original.json'),'PRESERVE_TLS_JOURNAL_DESTINATION')
 os.rename(tls_journal,ARCHIVE+'/tls-original.json');sync(T);sync(ARCHIVE)
 result={'receipt_hashes':{os.path.basename(p):sha(v) for p,v in saved.items()},
         'tls_root_retained':True,'tls_journal_retained':True,'historical_receipts_deleted':False}
 exclusive_file(ARCHIVE+'/preservation-complete.json',(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode())
 return result
