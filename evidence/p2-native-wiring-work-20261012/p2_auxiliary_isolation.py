"""Read-only auxiliary isolation admission and exact masked-unit rollback."""
import os,json,stat,hashlib,subprocess,tempfile
BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
UNIT_ROOT='/etc/systemd/system'
CGROUP_ROOT='/sys/fs/cgroup/systemd/system.slice'
UNITS=frozenset(('xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service'))
def read(path,digest=None):
 if os.path.realpath(path)!=path:raise ValueError('AUX_REFERENCE_SYMLINK')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());raw=f.read(1048577)
  if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=0o600 or len(raw)>1048576:raise ValueError('AUX_REFERENCE_AUTHORITY')
 if digest is not None and hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('AUX_REFERENCE_CHANGED')
 return raw
def verify(ref,masked=True,run=subprocess.run):
 if not isinstance(ref,dict) or set(ref)!={'path','sha256','transaction_id'}:raise ValueError('EXACT_AUX_ISOLATION_REFERENCE')
 tx=ref['transaction_id'];path=ref['path']
 if not isinstance(tx,str) or '/' in tx or not tx or path!=BASE+'/legacy-isolation-'+tx+'/auxiliary-owner/auxiliary-isolation-receipt.json':raise ValueError('AUX_TRANSACTION_SCOPE')
 digest=ref['sha256']
 if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('AUX_DIGEST')
 parent=os.path.dirname(path);s=os.lstat(parent)
 if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o700:raise ValueError('AUX_DIRECTORY_AUTHORITY')
 value=json.loads(read(path,digest).decode())
 if (value.get('state')!='AUTHORIZED_AUXILIARY_OWNER_ISOLATED' or value.get('transaction_id')!=tx
     or value.get('install') is not False or value.get('writer_admission') is not False
     or value.get('fence_mutation') is not False or value.get('database_unchanged') is not True
     or value.get('original_stage1_gateway_journal_unchanged') is not True
     or not isinstance(value.get('unit_hashes'),dict) or set(value['unit_hashes'])!=UNITS):raise ValueError('AUX_RECEIPT_BINDING')
 for unit in sorted(UNITS):
  read(parent+'/'+unit+'.backup',value['unit_hashes'][unit])
  r=run(['/usr/bin/systemctl','show',unit,'--property=ActiveState,SubState,MainPID,UnitFileState'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
  if r.returncode:raise ValueError('AUX_UNIT_STATE_UNAVAILABLE')
  observed=dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
  if observed.get('ActiveState') not in ('inactive','failed') or observed.get('MainPID')!='0':raise ValueError('AUX_UNIT_NOT_QUIESCED')
  target=UNIT_ROOT+'/'+unit
  if masked and (observed.get('UnitFileState')!='masked' or not is_mask(target)):raise ValueError('AUX_MASK_CHANGED')
  root=CGROUP_ROOT+'/'+unit
  for directory,children,files in os.walk(root,followlinks=False):
   if 'cgroup.procs' in files:
    with open(directory+'/cgroup.procs') as f:
     if f.read(65537).strip():raise ValueError('AUX_CGROUP_NOT_EMPTY')
 return value
def scoped(target):
 return isinstance(target,str) and target in {UNIT_ROOT+'/'+u for u in UNITS}
def is_mask(target):
 return scoped(target) and os.path.islink(target) and os.readlink(target)=='/dev/null'
def mask_previous(ref,target,backup,run=subprocess.run):
 if not is_mask(target):raise ValueError('AUX_PREVIOUS_MASK_REQUIRED')
 value=verify(ref,run=run);unit=os.path.basename(target)
 raw=read(os.path.dirname(ref['path'])+'/'+unit+'.backup',value['unit_hashes'][unit])
 fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 return {'backup':backup,'sha256':value['unit_hashes'][unit],'mode':0o644,'uid':0,'gid':0,'masked':True}
def restore_mask(target):
 if not scoped(target):raise ValueError('AUX_RESTORE_TARGET_SCOPE')
 parent=os.path.dirname(target);s=os.lstat(parent)
 if os.path.realpath(parent)!=parent or not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:raise ValueError('AUX_RESTORE_PARENT_AUTHORITY')
 if is_mask(target):return
 if os.path.islink(target):raise ValueError('AUX_RESTORE_UNKNOWN_SYMLINK')
 fd,temporary=tempfile.mkstemp(prefix='.p2-aux-mask-',dir=parent);os.close(fd);os.unlink(temporary)
 try:
  os.symlink('/dev/null',temporary);os.replace(temporary,target)
  fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
 finally:
  if os.path.lexists(temporary):os.unlink(temporary)
