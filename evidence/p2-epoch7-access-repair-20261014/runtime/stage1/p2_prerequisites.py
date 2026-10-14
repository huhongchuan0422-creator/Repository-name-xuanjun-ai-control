"""Fixed UK identity/directory/binary bootstrap with an intent journal.

No credential copying, package downloads, service start or legacy mutation.
Existing objects must match the reviewed plan; unknown partial effects HOLD.
"""
import grp
import hashlib
import json
import os
import pwd
import socket
import stat
import subprocess

from ledger_cutover_transaction import _atomic_receipt

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
USERS = {'xuanjun-dispatcher', 'xuanjun-callback', 'xj_codex_worker'}
GROUPS = USERS | {'xuanjun-control-db', 'xuanjun-ledger-client'}
ROOTS = ('/etc/xuanjun-development', '/etc/xuanjun-owner-callback',
         '/var/lib/xuanjun-development', '/opt/xuanjun-runtime')
BINARIES = {'/opt/xuanjun-runtime/codex-0.160.0/codex',
            '/opt/xuanjun-runtime/gh/gh'}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',', ':'),
        allow_nan=False).encode('utf-8')).hexdigest()


def file_hash(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>536870912:
            raise ValueError('UNSAFE_PREREQUISITE_BINARY')
        value=hashlib.sha256()
        while True:
            chunk=os.read(fd,1048576)
            if not chunk:break
            value.update(chunk)
        end=os.fstat(fd)
        if (info.st_size,info.st_mtime_ns)!=(end.st_size,end.st_mtime_ns):
            raise ValueError('PREREQUISITE_BINARY_CHANGED')
        return value.hexdigest(),info
    finally:os.close(fd)


def validate(plan):
    if (not isinstance(plan,dict) or set(plan)!={'schema','groups','users','directories','binaries'}
            or type(plan.get('schema')) is not int or plan['schema']!=1
            or not isinstance(plan['groups'],dict) or set(plan['groups']) not in (GROUPS,GROUPS|{'nginx'})
            or not isinstance(plan['users'],dict) or set(plan['users']) not in (USERS,USERS|{'nginx'})
            or ('nginx' in plan['groups'])!=('nginx' in plan['users'])
            or not isinstance(plan['directories'],list) or not plan['directories']
            or not isinstance(plan['binaries'],list)):
        raise ValueError('EXACT_PREREQUISITE_PLAN_REQUIRED')
    gids=list(plan['groups'].values())
    if any(type(x) is not int or not 1003<=x<=60000 for x in gids) or len(set(gids))!=len(gids):
        raise ValueError('DEDICATED_NONPRIVILEGED_GIDS_REQUIRED')
    uids=[]
    for name,item in plan['users'].items():
        if (not isinstance(item,dict) or set(item)!={'uid','gid','home','groups'}
                or type(item['uid']) is not int or not 1003<=item['uid']<=60000
                or item['gid']!=plan['groups'][name]
                or not isinstance(item['home'],str)
                or not item['home'].startswith('/var/lib/xuanjun-development/')
                or os.path.realpath(item['home'])!=item['home']
                or item['groups']!= ([] if name in ('xj_codex_worker','nginx') else ['xuanjun-control-db'])):
            raise ValueError('ISOLATED_ACCOUNT_BINDING_REQUIRED')
        if name=='nginx' and (item['uid'],item['gid'],item['home'])!=(1008,1008,'/var/lib/xuanjun-development/nginx-home'):
            raise ValueError('FIXED_NGINX_IDENTITY_REQUIRED')
        uids.append(item['uid'])
    if len(set(uids))!=len(uids):raise ValueError('DISTINCT_WORKER_UIDS_REQUIRED')
    targets=set()
    for item in plan['directories']:
        if (not isinstance(item,dict) or set(item)!={'path','uid','gid','mode'}
                or not isinstance(item['path'],str)
                or not any(item['path']==r or item['path'].startswith(r+'/') for r in ROOTS)
                or os.path.realpath(item['path'])!=item['path']
                or item['path'] in targets or type(item['uid']) is not int
                or type(item['gid']) is not int or item['uid'] not in [0]+uids
                or item['gid'] not in [0]+gids or type(item['mode']) is not int
                or not 0o700<=item['mode']<=0o755 or item['mode']&0o022):
            raise ValueError('PROTECTED_PREREQUISITE_DIRECTORY_REQUIRED')
        if (item['path'].startswith(('/etc/','/opt/'))
                or item['path']=='/var/lib/xuanjun-development'
                or item['path'].startswith('/var/lib/xuanjun-development/activation')) and item['uid']!=0:
            raise ValueError('AUTHORITY_DIRECTORY_MUST_BE_ROOT_OWNED')
        targets.add(item['path'])
    for item in plan['binaries']:
        if (not isinstance(item,dict) or set(item)!={'source','target','sha256'}
                or item['target'] not in BINARIES or item['target'] in targets
                or not isinstance(item['source'],str) or not os.path.isabs(item['source'])
                or os.path.realpath(item['source'])!=item['source']
                or os.path.basename(item['source'])!=os.path.basename(item['target'])
                or not isinstance(item['sha256'],str) or len(item['sha256'])!=64
                or any(c not in '0123456789abcdef' for c in item['sha256'])):
            raise ValueError('PINNED_CODE_BINARY_REQUIRED')
        targets.add(item['target'])
    return True


class Prerequisites(object):
    def __init__(self,directory,run=subprocess.run):
        self.directory=directory
        self.path=os.path.join(directory,'prerequisites.json')
        self.run=run

    def authority(self):
        if (os.geteuid()!=0 or socket.gethostname().split('.')[0]!=HOST
                or os.path.realpath(self.directory)!=self.directory):
            raise ValueError('FIXED_UK_ROOT_PREREQUISITES_REQUIRED')
        info=os.lstat(self.directory)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700:
            raise ValueError('PROTECTED_PREREQUISITE_JOURNAL_REQUIRED')

    def command(self,args):
        result=self.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                        timeout=30,check=False)
        if result.returncode:raise RuntimeError('PREREQUISITE_COMMAND_FAILED')

    @staticmethod
    def directory_matches(item):
        s=os.lstat(item['path'])
        if (not stat.S_ISDIR(s.st_mode) or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))
                !=(item['uid'],item['gid'],item['mode'])):
            raise ValueError('EXISTING_DIRECTORY_IDENTITY_MISMATCH')

    def preflight(self,plan):
        self.authority();validate(plan)
        if os.path.lexists(self.path):raise ValueError('HOLD_EXISTING_PREREQUISITE_JOURNAL')
        for name,gid in plan['groups'].items():
            try:g=grp.getgrnam(name)
            except KeyError:
                try:grp.getgrgid(gid)
                except KeyError:continue
                raise ValueError('PLANNED_GID_ALREADY_ALLOCATED')
            if g.gr_gid!=gid:raise ValueError('EXISTING_GROUP_IDENTITY_MISMATCH')
            allowed=({'xuanjun-dispatcher','xuanjun-callback'} if name=='xuanjun-control-db'
                     else set() if name=='xuanjun-ledger-client' else {name})
            if not set(g.gr_mem).issubset(allowed):raise ValueError('UNREVIEWED_GROUP_MEMBERS')
        for name,item in plan['users'].items():
            try:u=pwd.getpwnam(name)
            except KeyError:
                try:pwd.getpwuid(item['uid'])
                except KeyError:continue
                raise ValueError('PLANNED_UID_ALREADY_ALLOCATED')
            if (u.pw_uid,u.pw_gid,u.pw_dir,u.pw_shell)!=(item['uid'],item['gid'],item['home'],'/sbin/nologin'):
                raise ValueError('EXISTING_USER_IDENTITY_MISMATCH')
            expected={item['gid']}|{plan['groups'][n] for n in item['groups']}
            if set(os.getgrouplist(name,item['gid']))!=expected:
                raise ValueError('UNREVIEWED_SUPPLEMENTARY_GROUPS')
        declared={x['path'] for x in plan['directories']}
        for item in plan['directories']:
            if os.path.lexists(item['path']):self.directory_matches(item)
            parent=os.path.dirname(item['path'])
            if parent not in declared:
                s=os.lstat(parent)
                if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:
                    raise ValueError('UNSAFE_UNDECLARED_DIRECTORY_PARENT')
        for item in plan['binaries']:
            h,unused=file_hash(item['source'])
            if h!=item['sha256']:raise ValueError('BINARY_SOURCE_HASH_MISMATCH')
            if os.path.dirname(item['target']) not in declared:
                raise ValueError('BINARY_PARENT_MUST_BE_DECLARED')
            if os.path.lexists(item['target']):
                h,s=file_hash(item['target'])
                if h!=item['sha256'] or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=(0,0,0o555):
                    raise ValueError('EXISTING_BINARY_IDENTITY_MISMATCH')
        return True

    def apply(self,plan):
        if os.path.lexists(self.path):raise ValueError('HOLD_EXISTING_PREREQUISITE_TRANSACTION')
        self.preflight(plan)
        receipt={'schema':1,'plan_sha256':digest(plan),'actions':[]}
        _atomic_receipt(self.path,receipt)
        def effect(kind,value,callback):
            action={'kind':kind,'value':value,'state':'INTENT'}
            receipt['actions'].append(action);_atomic_receipt(self.path,receipt)
            callback();action['state']='DONE';_atomic_receipt(self.path,receipt)
        for name,gid in sorted(plan['groups'].items()):
            try:grp.getgrnam(name)
            except KeyError:effect('group',{'name':name,'gid':gid},
                lambda n=name,g=gid:self.command(['/usr/sbin/groupadd','--gid',str(g),n]))
        for name,item in sorted(plan['users'].items()):
            try:pwd.getpwnam(name)
            except KeyError:
                args=['/usr/sbin/useradd','--uid',str(item['uid']),'--gid',str(item['gid']),
                      '--no-create-home','--home-dir',item['home'],'--shell','/sbin/nologin']
                if item['groups']:args+=['--groups',','.join(item['groups'])]
                effect('user',dict(item,name=name),lambda a=args,n=name:self.command(a+[n]))
        for item in sorted(plan['directories'],key=lambda x:(x['path'].count('/'),x['path'])):
            if not os.path.lexists(item['path']):
                def create(i=item):
                    os.mkdir(i['path'],i['mode']);os.chown(i['path'],i['uid'],i['gid']);os.chmod(i['path'],i['mode'])
                effect('directory',item,create)
        for item in plan['binaries']:
            if not os.path.lexists(item['target']):
                def copy(i=item):
                    src=os.open(i['source'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                    dst=None
                    try:
                        s=os.fstat(src)
                        if not stat.S_ISREG(s.st_mode):raise ValueError('UNSAFE_BINARY_SOURCE')
                        dst=os.open(i['target'],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o500)
                        h=hashlib.sha256()
                        while True:
                            chunk=os.read(src,1048576)
                            if not chunk:break
                            h.update(chunk)
                            position=0
                            while position<len(chunk):position+=os.write(dst,chunk[position:])
                        if h.hexdigest()!=i['sha256']:raise ValueError('BINARY_CHANGED_DURING_COPY')
                        os.fchown(dst,0,0);os.fchmod(dst,0o555);os.fsync(dst)
                    finally:
                        os.close(src)
                        if dst is not None:os.close(dst)
                effect('binary',item,copy)
        return {'plan_sha256':digest(plan)}

    def rollback(self,plan):
        self.authority();validate(plan)
        if not os.path.lexists(self.path):return {'restored':True,'effects':0}
        fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd) as f:receipt=json.load(f)
        if receipt.get('plan_sha256')==digest(plan) and receipt.get('restored') is True:return {'restored':True,'effects':0}
        if receipt.get('plan_sha256')!=digest(plan) or any(a.get('state')!='DONE' for a in receipt.get('actions',[])):
            raise ValueError('HOLD_UNKNOWN_PREREQUISITE_EFFECT')
        actions=list(reversed(receipt['actions']))
        owned={a['value']['path'] for a in actions if a['kind']=='directory'}
        owned|={a['value']['target'] for a in actions if a['kind']=='binary'}
        # Validate all current objects before deleting any. Retained evidence
        # or a new process is not silently destroyed to make rollback PASS.
        for action in actions:
            i=action['value'];kind=action['kind']
            if kind=='directory':
                self.directory_matches(i)
                if any(os.path.join(i['path'],n) not in owned for n in os.listdir(i['path'])):
                    raise ValueError('HOLD_PREREQUISITE_DIRECTORY_HAS_RETAINED_DATA')
            elif kind=='binary':
                h,s=file_hash(i['target'])
                if h!=i['sha256'] or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=(0,0,0o555):
                    raise ValueError('HOLD_PREREQUISITE_BINARY_CHANGED')
            elif kind=='user':
                u=pwd.getpwnam(i['name'])
                if (u.pw_uid,u.pw_gid,u.pw_dir,u.pw_shell)!=(i['uid'],i['gid'],i['home'],'/sbin/nologin'):
                    raise ValueError('HOLD_CREATED_USER_CHANGED')
                if any(os.stat('/proc/'+p).st_uid==i['uid'] for p in os.listdir('/proc') if p.isdigit() and os.path.exists('/proc/'+p)):
                    raise ValueError('HOLD_CREATED_USER_HAS_PROCESSES')
            elif kind=='group':
                if grp.getgrnam(i['name']).gr_gid!=i['gid']:raise ValueError('HOLD_CREATED_GROUP_CHANGED')
            else:raise ValueError('INVALID_PREREQUISITE_ACTION')
        for action in actions:
            i=action['value'];kind=action['kind']
            if kind=='binary':os.unlink(i['target'])
            elif kind=='directory':os.rmdir(i['path'])
            elif kind=='user':self.command(['/usr/sbin/userdel',i['name']])
            elif kind=='group':
                try:g=grp.getgrnam(i['name'])
                except KeyError:continue # userdel can already remove its matching private group.
                if g.gr_gid!=i['gid']:raise ValueError('HOLD_CREATED_GROUP_CHANGED')
                self.command(['/usr/sbin/groupdel',i['name']])
        receipt['restored']=True;_atomic_receipt(self.path,receipt)
        return {'restored':True,'effects':len(actions)}
