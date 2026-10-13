"""Hash-bound private bootstrap files; durable no-overwrite publication and rollback."""
import hashlib,json,os,stat,tempfile
from ledger_cutover_transaction import _atomic_receipt
CALLBACK='/etc/xuanjun-owner-callback/'
TARGETS={CALLBACK+n:(1004,1006,0o600) for n in ('owner-user-id','owner-chat-id','owner-callback-auth','owner-callback-hmac','owner-dashboard-token')}
TARGETS.update({'/etc/xuanjun-development/github-intake-token':(1003,1003,0o600),'/etc/xuanjun-development/p2-native-binding.json':(0,0,0o644)})
def hash_bytes(raw):return hashlib.sha256(raw).hexdigest()
def private_read(path):
    if os.path.realpath(path)!=path:raise ValueError('BOOTSTRAP_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno());raw=f.read(1048577);end=os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o600 or s.st_nlink!=1 or len(raw)>1048576 or (s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(end.st_size,end.st_mtime_ns,end.st_ctime_ns):raise ValueError('BOOTSTRAP_PRIVATE_SOURCE')
    return raw
class BootstrapFiles:
    def __init__(self,directory):self.directory=directory;self.journal=directory+'/bootstrap-files.json'
    def authority(self):
        s=os.lstat(self.directory)
        if os.geteuid()!=0 or not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o700 or os.path.realpath(self.directory)!=self.directory:raise ValueError('BOOTSTRAP_ROOT_AUTHORITY')
    def prepare(self,reference,release_directory):
        self.authority()
        if not isinstance(reference,dict) or set(reference)!={'path','sha256'} or not reference['path'].startswith('/var/lib/xuanjun-p2-preparation/'):raise ValueError('BOOTSTRAP_EXACT_REFERENCE')
        raw=private_read(reference['path'])
        if hash_bytes(raw)!=reference['sha256']:raise ValueError('BOOTSTRAP_RECEIPT_HASH')
        value=json.loads(raw.decode());items=value.get('files')
        if not isinstance(items,list) or len(items)!=7:raise ValueError('BOOTSTRAP_SEVEN_FILES')
        rows=[];seen=set()
        for item in items:
            target=item['target'];source=item['source']
            if target not in TARGETS or target in seen or tuple(item[k] for k in ('owner_uid','group_gid','mode'))!=TARGETS[target] or item.get('applied') is not False or item.get('requires_approved_bootstrap') is not True:raise ValueError('BOOTSTRAP_EXACT_TARGET')
            if os.path.dirname(source)!=os.path.dirname(reference['path'])+'/private-bootstrap':raise ValueError('BOOTSTRAP_SOURCE_SCOPE')
            data=private_read(source)
            if hash_bytes(data)!=item['sha256']:raise ValueError('BOOTSTRAP_BYTES')
            if target.endswith('/p2-native-binding.json'):
                binding=json.loads(data.decode())
                if binding['ledger']['bridge']!='/opt/xuanjun-control-releases/'+release_directory+'/stage1/native_ledger_bridge.py':raise ValueError('BOOTSTRAP_RELEASE_BINDING')
            if os.path.lexists(target):raise ValueError('HOLD_BOOTSTRAP_TARGET_PRESENT')
            seen.add(target);rows.append(dict(item,data=data))
        return rows
    def apply(self,reference,release_directory):
        if os.path.lexists(self.journal):raise ValueError('HOLD_BOOTSTRAP_JOURNAL_PRESENT')
        prepared=self.prepare(reference,release_directory);rows=[]
        for item in prepared:
            target=item['target'];parent=os.path.dirname(target);s=os.lstat(parent)
            if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022 or os.path.realpath(parent)!=parent:raise ValueError('BOOTSTRAP_PARENT')
            # Stage in target's filesystem so no-overwrite hardlink is atomic.
            fd,temp=tempfile.mkstemp(prefix='.p2-bootstrap-',dir=parent)
            with os.fdopen(fd,'wb') as f:
                f.write(item['data']);f.flush();os.fchown(f.fileno(),item['owner_uid'],item['group_gid']);os.fchmod(f.fileno(),item['mode']);os.fsync(f.fileno());s=os.fstat(f.fileno())
            row={k:item[k] for k in ('target','sha256','owner_uid','group_gid','mode')}
            row.update(temp=temp,dev=s.st_dev,ino=s.st_ino,state='PUBLISH_INTENT');rows.append(row)
            _atomic_receipt(self.journal,{'schema':1,'files':rows})
            os.link(temp,target,follow_symlinks=False);self.sync(parent)
            os.unlink(temp);row['state']='PUBLISHED';_atomic_receipt(self.journal,{'schema':1,'files':rows});self.sync(parent)
    @staticmethod
    def sync(parent):
        fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    def rollback_rows(self):
        if not os.path.lexists(self.journal):return []
        self.authority()
        value=json.loads(private_read(self.journal).decode());rows=value['files'];seen=set()
        if value.get('schema')!=1 or not isinstance(rows,list) or len(rows)>7:raise ValueError('BOOTSTRAP_ROLLBACK_SCHEMA')
        for row in rows:
            target=row['target'];temp=row['temp']
            if target not in TARGETS or target in seen or tuple(row[k] for k in ('owner_uid','group_gid','mode'))!=TARGETS[target] or os.path.dirname(temp)!=os.path.dirname(target) or not os.path.basename(temp).startswith('.p2-bootstrap-'):raise ValueError('BOOTSTRAP_ROLLBACK_SCOPE')
            seen.add(target)
            for path in (target,temp):
                if not os.path.lexists(path):continue
                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                with os.fdopen(fd,'rb') as f:
                    s=os.fstat(f.fileno());raw=f.read(1048577);end=os.fstat(f.fileno())
                    links=sum(int(os.path.lexists(p)) for p in (target,temp))
                    if not stat.S_ISREG(s.st_mode) or s.st_nlink!=links or (s.st_dev,s.st_ino,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=(row['dev'],row['ino'],row['owner_uid'],row['group_gid'],row['mode']) or hash_bytes(raw)!=row['sha256'] or (s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(end.st_size,end.st_mtime_ns,end.st_ctime_ns):raise ValueError('HOLD_BOOTSTRAP_TARGET_CHANGED')
        return rows
    def rollback(self):
        rows=self.rollback_rows()
        for row in reversed(rows):
            for path in (row['target'],row['temp']):
                if os.path.lexists(path):os.unlink(path)
            self.sync(os.path.dirname(row['target']));row['state']='RESTORED_ABSENT'
            _atomic_receipt(self.journal,{'schema':1,'files':rows})
