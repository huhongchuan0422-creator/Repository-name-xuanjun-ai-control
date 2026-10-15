#!/usr/bin/env python3
"""One manually approved isolated probe. No production recovery authority.

--execute-reviewed-probe acknowledges the operator's external action approval;
it is NOT cryptographic evidence of approval. No token or approval service exists.
Only the manually acknowledged CLI/loader API constructs real effects. Tests
inject a fake backend and never invoke host tools.
"""
import argparse
import copy
import errno
import hashlib
import json
import os
import pwd
import grp
import re
import selectors
import signal
import socket
import stat
import subprocess
import sys
import time
import node_sqlite_probe
import epoch7_python_identity

EXPECTED_HOST='iZd7oeikknn1z21sq6ji6zZ'
PREFIX = 'xj-p2-proof-'
RUNTIME_MANIFEST = '26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa'
CANDIDATE_SOURCES = ('stage1/ledger_service.py','stage1/ledger_server_identity.py','stage1/activation_control.py')
ROLES = ('ledger', 'broker', 'dashboard', 'callback', 'native')
USERS={'ledger':'xuanjun-dispatcher','broker':'root','dashboard':'xuanjun-callback','callback':'xuanjun-callback','native':'xuanjun_dev'}
GROUPS={'ledger':'xuanjun-control-db','broker':'root','dashboard':'xuanjun-control-db','callback':'xuanjun-control-db','native':'xuanjun_dev'}
SUPPLEMENTARY={'ledger':{'xuanjun-dispatcher'},'broker':{'xuanjun-ledger-client'},'dashboard':{'xuanjun-ledger-client'},'callback':{'xuanjun-ledger-client'},'native':{'docker','xuanjun-ledger-client'}}
UIDS = {'ledger': 1003, 'broker': 0, 'dashboard': 1004, 'callback': 1004, 'native': 1002}
CASES = ((1,'native','cold'), (2,'broker','stable'), (3,'dashboard','same_uid_denial'),
         (4,'callback','exact_callback'), (5,'native','restart_between'),
         (6,'broker','restart_during'), (7,'dashboard','recreate_between'),
         (8,'callback','recreate_during'))
LIMITS = {'connections':8, 'frame_bytes':4096, 'connection_seconds':3,
          'command_seconds':2, 'command_bytes':32768, 'overall_seconds':60,
          'cleanup_seconds':15, 'report_bytes':131072}
HEX = re.compile(r'^[0-9a-f]{64}$')


def need(value, code):
    if not value: raise ValueError(code)
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
def digest(raw): return hashlib.sha256(raw).hexdigest()
def same(a,b): return canonical(a)==canonical(b)
def keys(value, wanted, code): need(type(value) is dict and set(value)==set(wanted),code)
def integer(value, minimum=0): need(type(value) is int and value>=minimum,'INTEGER_REQUIRED')
def sha(value): need(type(value) is str and HEX.fullmatch(value),'SHA256_REQUIRED')
def parse(raw):
    def pairs(items):
        value={}
        for key,item in items:
            need(key not in value and key not in ('__proto__','constructor','prototype'),'JSON_DUPLICATE_OR_PROTO')
            value[key]=item
        return value
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('JSON_NONFINITE')))
def path(value):
    need(type(value) is str and re.fullmatch(r'/[A-Za-z0-9_.+/-]+',value) and
         os.path.normpath(value)==value and '..' not in value.split('/'),'CANONICAL_SAFE_PATH')
def identity(info):
    return {'dev':info.st_dev,'ino':info.st_ino,'mode':stat.S_IMODE(info.st_mode),
        'uid':info.st_uid,'gid':info.st_gid,'nlink':info.st_nlink,'size':info.st_size,
        'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns}


def validate_policy(policy):
    keys(policy,('schema','purpose','nonce','hostname','machine_id_sha256','runtime_manifest_sha256',
        'driver_sha256','helper_sha256','python','systemctl','profiles','sdk_bindings','public_files',
        'ledger_capability_reviewed','cleanup_reviewed','limits','candidate_sources',
        'node_sqlite_reviewed','node_sqlite'),'POLICY_KEYS')
    need(type(policy['schema']) is int and policy['schema']==2 and
         policy['purpose']=='ISOLATED_ROOT_MANAGER_ACCESS_PROBE','POLICY_PURPOSE')
    need(type(policy['nonce']) is str and re.fullmatch(r'[0-9a-f]{32}',policy['nonce']),'NONCE_REQUIRED')
    need(type(policy['hostname']) is str and re.fullmatch(r'[A-Za-z0-9.-]{1,253}',policy['hostname']),'HOST_REQUIRED')
    need(policy['hostname'].split('.')[0]==EXPECTED_HOST,'EXACT_UK_HOST_POLICY')
    for key in ('machine_id_sha256','runtime_manifest_sha256','driver_sha256','helper_sha256'): sha(policy[key])
    need(policy['runtime_manifest_sha256']==RUNTIME_MANIFEST,'EXACT_RUNTIME_SOURCE_REQUIRED')
    need(policy['ledger_capability_reviewed'] is True and policy['cleanup_reviewed'] is True and
         same(policy['limits'],LIMITS),'EXACT_CAPABILITY_CLEANUP_LIMITS')
    need(policy['node_sqlite_reviewed'] is True,'EXPLICIT_NODE_SQLITE_SCOPE')
    binding=policy['node_sqlite'];keys(binding,('node','probe_input_sha256','diagnostic_sha256'),'NODE_SQLITE_BINDING')
    node_sqlite_probe.validate_node(binding['node']);sha(binding['probe_input_sha256'])
    need(binding['diagnostic_sha256']==digest(node_sqlite_probe.SOURCE),'EXACT_NODE_DIAGNOSTIC')
    for tool in ('python','systemctl'):
        wanted=('path','sha256','python_identity') if tool=='python' and type(policy[tool]) is dict and 'python_identity' in policy[tool] else ('path','sha256')
        keys(policy[tool],wanted,'TOOL_KEYS');path(policy[tool]['path']);sha(policy[tool]['sha256'])
    if 'python_identity' in policy['python']:
        epoch7_python_identity.validate_pair_proof(policy['python']['python_identity'])
        need(policy['python']['path']==epoch7_python_identity.PYTHON_PATHS[0] and
             policy['python']['sha256']==epoch7_python_identity.RETAINED_SHA256,'EXACT_PYTHON_PAIR_BINDING')
    need(policy['systemctl']['path']=='/usr/bin/systemctl','FIXED_SYSTEMCTL')
    need(re.fullmatch(r'/usr/(?:bin/python3(?:\.6)?|libexec/platform-python(?:3\.6)?)',policy['python']['path']),
         'CANONICAL_PYTHON_SCOPE')
    keys(policy['profiles'],ROLES,'EXACT_PROFILES')
    for role,row in policy['profiles'].items():
        keys(row,('user','uid','group','gid','supplementary_groups','protect_home'),'PROFILE_KEYS')
        need(type(row['user']) is str and re.fullmatch(r'[a-z_][a-z0-9_-]*',row['user']),'PROFILE_USER')
        need(type(row['group']) is str and re.fullmatch(r'[a-z_][a-z0-9_-]*',row['group']),'PROFILE_GROUP')
        need(type(row['uid']) is int and row['uid']==UIDS[role],'EXISTING_UID_REQUIRED');integer(row['gid'])
        need(type(row['supplementary_groups']) is dict and len(row['supplementary_groups'])<=4,'GROUP_BOUND')
        for name,gid in row['supplementary_groups'].items():
            need(re.fullmatch(r'[a-z_][a-z0-9_-]*',name),'GROUP_NAME');integer(gid)
        need(row['protect_home']==('read-only' if role=='native' else 'yes'),'PROTECT_HOME_REQUIRED')
        need(row['user']==USERS[role] and row['group']==GROUPS[role] and
             set(row['supplementary_groups'])==SUPPLEMENTARY[role],'EXACT_EXISTING_ROLE_SCOPE')
    need(type(policy['sdk_bindings']) is list and 1<=len(policy['sdk_bindings'])<=5,'SDK_FIXED_BINDINGS')
    for row in policy['sdk_bindings']:
        keys(row,('path','sha256','uid','gid','size'),'SDK_KEYS');path(row['path']);sha(row['sha256'])
        need(row['path'].startswith('/home/xuanjun_dev/.openclaw/tools/') and row['uid']==1002,'SDK_SCOPE')
        integer(row['gid']);integer(row['size']);need(row['size']<=8*1024*1024,'SDK_BOUND')
    keys(policy['candidate_sources'],CANDIDATE_SOURCES,'EXACT_CANDIDATE_SOURCES')
    for value in policy['candidate_sources'].values():sha(value)
    need(type(policy['public_files']) is list and len(policy['public_files'])<=20,'PUBLIC_FILE_BOUND')
    need(len(policy['public_files'])==2 and {x.get('path') for x in policy['public_files']} in (
        {'/usr/bin/systemctl','/usr/lib/systemd/systemd'}, {'/usr/bin/systemctl','/lib/systemd/systemd'}),
        'EXACT_MANAGER_AND_SYSTEMCTL_PINS')
    for row in policy['public_files']:
        keys(row,('path','sha256','maximum'),'PUBLIC_FILE_KEYS');path(row['path']);sha(row['sha256'])
        need(row['path'] in ('/usr/lib/systemd/systemd','/lib/systemd/systemd','/usr/bin/systemctl'),
             'PUBLIC_SOURCE_SCOPE')
        need(type(row['maximum']) is int and 0<row['maximum']<=32*1024*1024,'PUBLIC_FILE_MAXIMUM')
    need(next(x['sha256'] for x in policy['public_files'] if x['path']=='/usr/bin/systemctl')==policy['systemctl']['sha256'],
         'CONSISTENT_SYSTEMCTL_PIN')
    return copy.deepcopy(policy)


def compile_policy(ingredients,offline,observation):
    """Pure bounded derivation for a single collect-then-probe invocation.

    Metadata consistency is not Owner approval. The manually reviewed command
    owns observation provenance and the external action-time consent boundary.
    """
    keys(ingredients,('hostname','machine_id_sha256','python','systemctl','profiles','sdk_bindings','manager'),
         'PROBE_INGREDIENT_KEYS')
    keys(offline,('nonce','driver_sha256','helper_sha256','candidate_sources',
                  'ledger_capability_reviewed','cleanup_reviewed','node_sqlite_reviewed'),'PROBE_OFFLINE_KEYS')
    profiles=copy.deepcopy(ingredients['profiles']);keys(profiles,ROLES,'EXACT_PROFILES')
    for role,row in profiles.items():
        keys(row,('user','uid','group','gid','supplementary_groups'),'OBSERVED_ROLE_KEYS')
        row['protect_home']='read-only' if role=='native' else 'yes'
    manager=ingredients['manager'];keys(manager,('path','sha256'),'MANAGER_INGREDIENT_KEYS')
    result=dict(copy.deepcopy(offline),schema=2,purpose='ISOLATED_ROOT_MANAGER_ACCESS_PROBE',
        hostname=ingredients['hostname'],machine_id_sha256=ingredients['machine_id_sha256'],
        runtime_manifest_sha256=RUNTIME_MANIFEST,python=copy.deepcopy(ingredients['python']),
        systemctl=copy.deepcopy(ingredients['systemctl']),profiles=profiles,
        sdk_bindings=copy.deepcopy(ingredients['sdk_bindings']),limits=dict(LIMITS),
        node_sqlite=node_sqlite_probe.binding_from_observation(observation),
        public_files=[dict(manager,maximum=33554432),dict(ingredients['systemctl'],maximum=33554432)])
    return validate_policy(result)


def scope(policy):
    nonce=policy['nonce'];stem=PREFIX+nonce;root='/run/'+stem
    return {'root':root,'receipt':root+'/created-receipt.json','socket':root+'/ledger.sock',
        'socket_unit':stem+'.socket','service_unit':stem+'.service',
        'client_units':{role:stem+'-'+role+'.service' for role in ROLES if role!='ledger'}}


def render_unit(policy,role,case=1):
    p=scope(policy);row=policy['profiles'][role];unit= p['service_unit'] if role=='ledger' else p['client_units'][role]
    mode='server' if role=='ledger' else 'client'
    config=p['root']+'/helper-'+role+'-'+mode+'.json'
    lines=['[Unit]','Description=Isolated P2 proof '+policy['nonce'], '[Service]','Type=simple',
        'User='+row['user'],'Group='+row['group'],
        'SupplementaryGroups='+' '.join(sorted(row['supplementary_groups'])),
        'ExecStart='+policy['python']['path']+' -B '+p['root']+'/probe_helpers.py --config '+config+' --mode '+mode,
        'Restart=no','RuntimeMaxSec=20','TimeoutStopSec=1','KillMode=control-group','LimitCORE=0',
        'NoNewPrivileges=yes','PrivateTmp=yes','PrivateDevices=yes','ProtectSystem=strict',
        'ProtectHome='+row['protect_home'],'ProtectControlGroups=yes','RestrictSUIDSGID=yes',
        'RestrictAddressFamilies=AF_UNIX','SystemCallArchitectures=native',
        'ReadOnlyPaths='+p['root'],'UMask=0077','WorkingDirectory='+p['root'],
        'StandardOutput=file:'+p['root']+'/output-'+role+'.jsonl',
        'StandardError=file:'+p['root']+'/error-'+role+'.txt']
    if role=='ledger':
        lines=[line for line in lines if not line.startswith(('StandardOutput=','StandardError='))]
        lines += ['StandardInput=file:'+p['root']+'/connection-budget.json',
                  'StandardOutput=file:'+p['root']+'/connection-budget.json',
                  'StandardError=file:'+p['root']+'/output-ledger.jsonl']
        lines += ['CapabilityBoundingSet=CAP_SYS_PTRACE','AmbientCapabilities=CAP_SYS_PTRACE',
                  'SystemCallFilter=~ptrace process_vm_readv process_vm_writev']
    else: lines += ['CapabilityBoundingSet=','AmbientCapabilities=']
    return unit, ('\n'.join(lines)+'\n').encode('utf-8')


def render_socket(policy):
    p=scope(policy);ledger=policy['profiles']['ledger']
    # RemoveOnStop means stop/recreation intentionally removes the OLD inode.
    return ('[Unit]\nDescription=Isolated P2 inherited listener\n[Socket]\nListenStream='+p['socket']+
        '\nAccept=no\nService='+p['service_unit']+'\nSocketUser='+ledger['user']+
        '\nSocketGroup=xuanjun-ledger-client\nSocketMode=0660\nDirectoryMode=0755\nRemoveOnStop=yes\n').encode()


class Deadline(object):
    def __init__(self,seconds,clock=time.monotonic):self.clock=clock;self.end=clock()+seconds
    def remaining(self):
        left=self.end-self.clock()
        if left<=0:raise TimeoutError('PROBE_DEADLINE')
        return left

def wait_owned_child(process,end):
    # Observe exit without reaping: keep this PID/group identity owned until
    # cleanup has signalled the group, closed streams and reaped independently.
    while True:
        need(time.monotonic()<end,'MANAGER_DEADLINE')
        row=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        if row is not None:
            need(row.si_pid==process.pid,'OWNED_CHILD_IDENTITY')
            return row.si_status if row.si_code==os.CLD_EXITED else -row.si_status
        time.sleep(.005)

def cleanup_owned_child(process):
    errors=[];lock=getattr(process,"_waitpid_lock",None);held=False
    try:
        need(lock is not None and lock.acquire(False),'CHILD_WAIT_LOCK_REQUIRED');held=True
        need(process.returncode is None,'CHILD_ALREADY_REAPED')
        row=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        need(row is None or row.si_pid==process.pid,'OWNED_CHILD_IDENTITY')
        need(os.getpgid(process.pid)==process.pid and os.getsid(process.pid)==process.pid,'OWNED_CHILD_GROUP_SESSION')
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        except BaseException:errors.append('CHILD_SIGNAL_UNCONFIRMED')
    except BaseException:errors.append('CHILD_OWNERSHIP_UNCONFIRMED')
    finally:
        if held:lock.release()
    for name in ('stdout','stderr'):
        try:
            stream=getattr(process,name,None)
            if stream is not None:stream.close()
        except BaseException:errors.append(name.upper()+'_CLOSE_UNCONFIRMED')
    try:process.wait(timeout=.2)
    except BaseException:errors.append('CHILD_REAP_UNCONFIRMED')
    return errors


class HostOps(object):
    """Real effects are reachable only from manually acknowledged apply/cleanup."""
    def __init__(self,policy,policy_sha,runtime_source=None):
        self.policy=policy;self.policy_sha=policy_sha;self.paths=scope(policy)
        self.runtime_source=runtime_source;self.operator_acknowledged=False;self.watchdog_armed=False
        self.created=[];self.receipt=None;self.deadline=Deadline(LIMITS['overall_seconds'])
    def check_host(self):
        need(os.geteuid()==0 and os.getegid()==0,'ROOT_REQUIRED')
        need(socket.gethostname()==self.policy['hostname'],'EXACT_HOST_REQUIRED')
        raw=self.read_file('/etc/machine-id',4096,protected=True)[0]
        need(digest(raw)==self.policy['machine_id_sha256'],'EXACT_MACHINE_ID_REQUIRED')
        raw,unused=self.read_python()
        need(digest(raw)==self.policy['python']['sha256'],'TOOL_SOURCE_CHANGED')
        raw,unused=self.read_file(self.policy['systemctl']['path'],32*1024*1024,protected=True)
        need(digest(raw)==self.policy['systemctl']['sha256'],'TOOL_SOURCE_CHANGED')
        for role,row in self.policy['profiles'].items():
            account=pwd.getpwnam(row['user']); group=grp.getgrnam(row['group'])
            need((account.pw_uid,group.gr_gid)==(row['uid'],row['gid']),'NSS_IDENTITY_CHANGED')
            for name,gid in row['supplementary_groups'].items():need(grp.getgrnam(name).gr_gid==gid,'NSS_GROUP_CHANGED')
        result=self.command(['--version'],mutating=False)
        need(re.match(br'systemd 239(?:\s|$)',result['stdout']),'SYSTEMD239_REQUIRED')
        manager=next(row for row in self.policy['public_files'] if row['path']!='/usr/bin/systemctl')
        before=os.readlink('/proc/1/exe')
        need(before==manager['path'],'ACTUAL_INIT_MANAGER_EXECUTABLE_REQUIRED')
        raw,unused=self.read_file(before,manager['maximum'])
        need(digest(raw)==manager['sha256'] and os.readlink('/proc/1/exe')==before,'INIT_MANAGER_EXECUTABLE_CHANGED')
        namespace=os.readlink('/proc/1/ns/pid')
        need(namespace==os.readlink('/proc/self/ns/pid'),'ROOT_DRIVER_INIT_NAMESPACE_MISMATCH')
        return {'host_match':True,'systemd':239,'root':True,
                'manager_exe':before,'manager_sha256':digest(raw),'manager_pid_namespace':namespace}
    @staticmethod
    def protected_parent(target):
        path(target); parent=os.path.dirname(target)
        while True:
            info=os.lstat(parent)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022 and
                 os.path.realpath(parent)==parent,'UNSAFE_PARENT')
            if parent=='/':break
            parent=os.path.dirname(parent)
    def read_file(self,target,maximum,protected=True):
        if protected:self.protected_parent(target)
        before=os.lstat(target);fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<=info.st_size<=maximum and
                 identity(before)==identity(info),'FILE_TYPE_OR_RACE')
            if protected:need(info.st_uid==0 and not info.st_mode&0o022,'PROTECTED_FILE_REQUIRED')
            raw=b''
            while len(raw)<=maximum:
                self.deadline.remaining();part=os.read(fd,min(65536,maximum+1-len(raw)))
                if not part:break
                raw+=part
            need(len(raw)<=maximum and identity(info)==identity(os.fstat(fd)) and
                 identity(info)==identity(os.lstat(target)),'FILE_CHANGED_OR_BOUND')
            return raw,identity(info)
        finally:os.close(fd)
    def _python_pair_sample(self):
        # This bounded exception belongs only to the measured fixed Python pair.
        # Generic reads (including executable/systemctl reads) remain nlink == 1.
        sample={'files':{},'ancestors':{}};contents={}
        for target in ('/','/usr','/usr/libexec')+tuple(epoch7_python_identity.PYTHON_PATHS):
            directory=target in ('/','/usr','/usr/libexec')
            before=os.lstat(target)
            flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
            if directory:flags|=os.O_DIRECTORY
            fd=os.open(target,flags)
            try:
                info=os.fstat(fd)
                need(identity(before)==identity(info) and before.st_mode==info.st_mode,
                     'PYTHON_PAIR_OPEN_RACE')
                need((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)),
                     'PYTHON_PAIR_TYPE')
                need(info.st_uid==0 and info.st_gid==0 and not info.st_mode&0o022,
                     'PYTHON_PAIR_PROTECTED')
                attributes=set(os.listxattr(fd))
                row=identity(info)
                row.update(kind='DIRECTORY' if directory else 'FILE',
                    access_acl='system.posix_acl_access' in attributes,
                    default_acl='system.posix_acl_default' in attributes,
                    capability='security.capability' in attributes)
                need(not (row['access_acl'] or row['default_acl'] or row['capability']),
                     'PYTHON_PAIR_ACL_OR_CAPABILITY')
                if not directory:
                    need(info.st_nlink==2 and info.st_mode==(stat.S_IFREG|0o755) and
                         0<info.st_size<=32*1024*1024,'PYTHON_PAIR_FILE_SCOPE')
                    raw=b''
                    while len(raw)<=32*1024*1024:
                        self.deadline.remaining()
                        part=os.read(fd,min(65536,32*1024*1024+1-len(raw)))
                        if not part:break
                        raw+=part
                    need(len(raw)==info.st_size,'PYTHON_PAIR_READ_BOUND')
                    row.update(sha256=digest(raw),elf_header=raw.startswith(b'\x7fELF'))
                    contents[target]=raw
                final_attributes=set(os.listxattr(fd))
                after=os.fstat(fd);named=os.lstat(target)
                need(identity(info)==identity(after)==identity(named) and
                     info.st_mode==after.st_mode==named.st_mode and
                     attributes==final_attributes, 'PYTHON_PAIR_CHANGED')
                sample['ancestors' if directory else 'files'][target]=row
            finally:os.close(fd)
        epoch7_python_identity.validate_pair_sample(sample)
        return sample,contents
    def read_python(self):
        binding=self.policy['python']
        if 'python_identity' not in binding:
            return self.read_file(binding['path'],32*1024*1024,protected=True)
        proof=binding['python_identity']
        epoch7_python_identity.validate_pair_proof(proof)
        need(binding['path']==epoch7_python_identity.PYTHON_PATHS[0] and
             binding['sha256']==epoch7_python_identity.RETAINED_SHA256,'EXACT_PYTHON_PAIR_BINDING')
        before,unused=self._python_pair_sample()
        after,contents=self._python_pair_sample()
        epoch7_python_identity.validate_pair_reread(proof,before,after)
        return contents[binding['path']], {key:after['files'][binding['path']][key]
                                         for key in epoch7_python_identity.METADATA_FIELDS}
    def command(self,args,mutating=True,timeout=2):
        allowed=('start','stop','restart','show','daemon-reload','--version')
        need(args and args[0] in allowed,'MANAGER_ACTION_SCOPE')
        units=set([self.paths['socket_unit'],self.paths['service_unit']]+list(self.paths['client_units'].values()))
        if args[0] in ('start','stop','restart'):need(len(args)==2 and args[1] in units,'EXACT_NONCE_UNIT')
        if args[0]=='show':need(len(args)==4 and args[1] in units and args[2]=='--no-pager' and
            args[3].startswith('--property=') and len(args[3])<=256,'EXACT_NONCE_SHOW')
        if args[0] in ('daemon-reload','--version'):need(len(args)==1,'EXACT_MANAGER_ACTION')
        if args[0] in ('start','stop','restart','daemon-reload'):
            need(self.operator_acknowledged is True and self.receipt is not None,'OPERATOR_ACK_AND_ATTEMPT_REQUIRED')
        return self.capture([self.policy['systemctl']['path']]+args,
            {'PATH':'/usr/bin:/bin','LC_ALL':'C','SYSTEMD_COLORS':'0'},timeout,LIMITS['command_bytes'])
    def capture(self,argv,env,timeout,maximum,**options):
        need(type(timeout) in (int,float) and 0<timeout<=5 and type(maximum) is int and
             0<maximum<=LIMITS['command_bytes'],'CAPTURE_BOUND')
        need(set(options)<=set(('executable','pass_fds','preexec_fn','cwd')),'CAPTURE_OPTIONS')
        self.last_capture_cleanup=None
        deadline=min(timeout,self.deadline.remaining());until=time.monotonic()+deadline
        proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,
            close_fds=True,start_new_session=True,**options)
        selector=None;data={'stdout':b'','stderr':b''};completed=False
        try:
            selector=selectors.DefaultSelector();selector.register(proc.stdout,selectors.EVENT_READ,'stdout');selector.register(proc.stderr,selectors.EVENT_READ,'stderr')
            while selector.get_map():
                remaining=until-time.monotonic()
                if remaining<=0:raise TimeoutError('MANAGER_DEADLINE')
                for key,unused in selector.select(remaining):
                    chunk=os.read(key.fd,4096)
                    if not chunk:selector.unregister(key.fileobj);continue
                    data[key.data]+=chunk
                    need(sum(len(x) for x in data.values())<=maximum,'MANAGER_OUTPUT_BOUND')
            code=wait_owned_child(proc,until)
            need(code==0,'MANAGER_COMMAND_FAILED')
            completed=True
            return dict(data,returncode=code)
        finally:
            errors=[]
            try:
                if selector is not None:selector.close()
            except BaseException:errors.append('SELECTOR_CLOSE_UNCONFIRMED')
            errors+=cleanup_owned_child(proc)
            self.last_capture_cleanup=list(errors)
            self.last_command_cleanup=(getattr(self,'last_command_cleanup',[])+errors)[:32]
            if completed and errors:raise RuntimeError('MANAGER_CHILD_CLEANUP_UNCONFIRMED')
    def assert_absent(self):
        need(not os.path.lexists(self.paths['root']),'NONCE_ALREADY_USED')
        for name in [self.paths['socket_unit'],self.paths['service_unit']]+list(self.paths['client_units'].values()):
            need(not os.path.lexists('/run/systemd/system/'+name),'NONCE_UNIT_EXISTS')
            result=self.command(['show',name,'--no-pager','--property=LoadState,ActiveState,FragmentPath'],False)
            values=dict(line.split('=',1) for line in result['stdout'].decode().splitlines() if '=' in line)
            need(values.get('LoadState')=='not-found' and values.get('ActiveState')=='inactive' and
                 values.get('FragmentPath','')=='','LOADED_NONCE_UNIT_EXISTS')
    @staticmethod
    def write_all(fd,raw):
        offset=0
        while offset<len(raw):
            count=os.write(fd,raw[offset:]);need(type(count) is int and count>0,'SHORT_WRITE')
            offset+=count
    def _write(self,target,raw,mode=0o644):
        self.protected_parent(target);fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
        try:
            os.fchmod(fd,mode);self.write_all(fd,raw)
            os.fsync(fd);info=identity(os.fstat(fd))
        finally:os.close(fd)
        parent=os.open(os.path.dirname(target),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(parent)
        finally:os.close(parent)
        self.created.append({'path':target,'identity':info,'sha256':digest(raw),'kind':'FILE'})
        return info
    def begin(self):
        need(self.operator_acknowledged is True,'OPERATOR_ACK_REQUIRED')
        self.assert_absent();os.mkdir(self.paths['root'],0o700)
        fd=os.open(self.paths['root'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            # mkdir is umask-sensitive; the nonsecret fixture directory must
            # really be searchable after the exact nonroot identity drop.
            os.fchmod(fd,0o755);os.fsync(fd)
            need(stat.S_IMODE(os.fstat(fd).st_mode)==0o755,'NONCE_DIRECTORY_SEARCH_MODE')
        finally:os.close(fd)
        self.created.append({'path':self.paths['root'],'identity':identity(os.lstat(self.paths['root'])),'kind':'DIRECTORY'})
        self.receipt={'schema':1,'purpose':'ISOLATED_PROBE_CREATION_RECEIPT','nonce':self.policy['nonce'],
            'policy_sha256':self.policy_sha,'operator_acknowledged':True,'external_approval_authenticated':False,
            'attempt_consumed':True,'connections_reserved':0,'stage':'CREATED','resources':self.created,'events':[]}
        self.save_receipt()
    def save_receipt(self):
        raw=canonical(self.receipt)+b'\n';need(len(raw)<=LIMITS['report_bytes'],'RECEIPT_BOUND')
        target=self.paths['receipt'];temporary=target+'.next'
        self.protected_parent(target)
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:self.write_all(fd,raw);os.fsync(fd)
        finally:os.close(fd)
        os.replace(temporary,target)
        parent=os.open(self.paths['root'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(parent)
        finally:os.close(parent)
    def event(self,name,detail=None):
        self.receipt['events'].append({'event':name,'detail':detail});self.save_receipt()
    def publish(self,target,raw):
        need(self.operator_acknowledged is True and self.receipt is not None,'OPERATOR_ACK_AND_ATTEMPT_REQUIRED')
        allowed=(target.startswith(self.paths['root']+'/') or target in ['/run/systemd/system/'+x for x in
            [self.paths['socket_unit'],self.paths['service_unit']]+list(self.paths['client_units'].values())])
        need(allowed,'PUBLICATION_SCOPE');self.event('CREATE_INTENT',{'path':target,'sha256':digest(raw)})
        self._write(target,raw,0o600 if target.endswith('/connection-budget.json') else 0o644);self.save_receipt()
    def preflight_sources(self,helper_raw=None):
        if helper_raw is not None:need(digest(helper_raw)==self.policy['helper_sha256'],'HELPER_HASH')
        need(self.runtime_source is not None,'REVIEWED_STAGED_RUNTIME_SOURCE_REQUIRED')
        manifest,unused=self.read_file(self.runtime_source+'/deploy/integration-manifest.json',1048576)
        need(digest(manifest)==RUNTIME_MANIFEST,'EXACT_STAGED_RUNTIME_MANIFEST')
        value=parse(manifest)
        for relative in CANDIDATE_SOURCES:
            raw,unused=self.read_file(self.runtime_source+'/'+relative,262144)
            need(digest(raw)==self.policy['candidate_sources'][relative]==value['files'][relative],'STAGED_SOURCE_HASH')
        return {'manifest_sha256':RUNTIME_MANIFEST,'candidate_sources':3,'installed_release_required':False}
    def run_node_sqlite(self):
        return node_sqlite_probe.run(self)
    def receipt_binding(self):
        raw,info=self.read_file(self.paths['receipt'],LIMITS['report_bytes'])
        need((info['uid'],info['gid'],info['mode'],info['nlink'])==(0,0,0o600,1),
             'PRIVATE_CREATED_RECEIPT_AUTHORITY')
        value=parse(raw);need(same(value,self.receipt),'CREATED_RECEIPT_READBACK')
        events=[row['detail'] for row in value['events'] if row.get('event')=='NODE_SQLITE_OBSERVED']
        need(len(events)==1,'ONE_NODE_SQLITE_RECEIPT_EVENT')
        return {'path':self.paths['receipt'],'sha256':digest(raw),'metadata':info,
            'node_sqlite_event_sha256':digest(canonical(events[0]))}
    def install(self,helper_raw):
        self.preflight_sources(helper_raw)
        self.publish(self.paths['root']+'/probe_helpers.py',helper_raw)
        need(self.runtime_source is not None,'REVIEWED_STAGED_RUNTIME_SOURCE_REQUIRED')
        manifest,unused=self.read_file(self.runtime_source+'/deploy/integration-manifest.json',1048576)
        need(digest(manifest)==RUNTIME_MANIFEST,'EXACT_STAGED_RUNTIME_MANIFEST')
        manifest_value=parse(manifest)
        for relative in CANDIDATE_SOURCES:
            raw,unused=self.read_file(self.runtime_source+'/'+relative,262144)
            need(digest(raw)==self.policy['candidate_sources'][relative]==manifest_value['files'][relative],'STAGED_SOURCE_HASH')
            self.publish(self.paths['root']+'/candidate-'+os.path.basename(relative),raw)
        self.publish(self.paths['root']+'/connection-budget.json',canonical({'schema':1,'nonce':self.policy['nonce'],'accepted':0})+b'\n')
        self.publish(self.paths['root']+'/probe-policy.json',canonical(self.policy)+b'\n')
        self.publish(self.paths['root']+'/fixture-activation.json',canonical({'schema':1,'fixture_only':True,'nonce':self.policy['nonce']})+b'\n')
        self.publish(self.paths['root']+'/fixture-epochs.jsonl',canonical({'schema':1,'fixture_only':True,'epoch':8})+b'\n')
        self.publish(self.paths['root']+'/fixture-activation.lock',b'')
        self.publish(self.paths['root']+'/fixture-dispatcher.json',b'{"fixture_only":true}\n')
        self.publish('/run/systemd/system/'+self.paths['socket_unit'],render_socket(self.policy))
        for role in ROLES:
            mode='server' if role=='ledger' else 'client'
            self.publish(self.paths['root']+'/helper-'+role+'-'+mode+'.json',canonical(self.helper_config(role,1))+b'\n')
            self.publish(self.paths['root']+'/output-'+role+'.jsonl',b'')
            self.publish(self.paths['root']+'/error-'+role+'.txt',b'')
            name,raw=render_unit(self.policy,role,1)
            self.publish('/run/systemd/system/'+name,raw)
        self.command(['daemon-reload']);self.event('UNITS_LOADED')
    def helper_config(self,role,case):
        row=self.policy['profiles'][role]
        result={'schema':1,'purpose':'ISOLATED_P2_PROBE_HELPER','nonce':self.policy['nonce'],
            'case':case,'role':role,'mode':'server' if role=='ledger' else 'client',
            'policy_sha256':self.policy_sha,'operator_acknowledged':True,
            'expected_uid':row['uid'],'expected_gid':row['gid'],
            'sdk_bindings':self.policy['sdk_bindings'] if role=='native' else [],
            'public_files':self.policy['public_files']+[{'path':self.paths['root']+'/candidate-'+os.path.basename(relative),
                'sha256':self.policy['candidate_sources'][relative],'maximum':262144} for relative in CANDIDATE_SOURCES],'systemctl':self.policy['systemctl']['path'],
            'allowed_pids':{},'python':self.policy['python']}
        result['public_files'] += [{'path':self.paths['root']+'/'+leaf,'sha256':digest(raw),'maximum':65536}
            for leaf,raw in [('probe-policy.json',canonical(self.policy)+b'\n'),
             ('fixture-activation.json',canonical({'schema':1,'fixture_only':True,'nonce':self.policy['nonce']})+b'\n'),
             ('fixture-epochs.jsonl',canonical({'schema':1,'fixture_only':True,'epoch':8})+b'\n')]]
        result['public_files'] += [{'path':'/run/systemd/system/'+self.paths['socket_unit'],
             'sha256':digest(render_socket(self.policy)),'maximum':65536},
            {'path':'/run/systemd/system/'+self.paths['service_unit'],
             'sha256':digest(render_unit(self.policy,'ledger')[1]),'maximum':65536}]
        return result
    def replace_created(self,target,raw):
        matched=[row for row in self.created if row['path']==target]
        need(len(matched)==1 and matched[0]['kind']=='FILE','EXACT_CREATED_REPLACEMENT')
        row=matched[0];old,info=self.read_file(target,1048576)
        need(same(info,row['identity']) and digest(old)==row['sha256'],'CREATED_FILE_CAS')
        self.event('REPLACE_INTENT',{'path':target,'before_sha256':row['sha256'],'after_sha256':digest(raw)})
        temporary=target+'.next';self.protected_parent(temporary)
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
        try:
            self.write_all(fd,raw)
            os.fsync(fd)
        finally:os.close(fd)
        current,info=self.read_file(target,1048576)
        need(same(info,row['identity']) and digest(current)==row['sha256'],'CREATED_FILE_CAS')
        os.replace(temporary,target)
        parent=os.open(os.path.dirname(target),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(parent)
        finally:os.close(parent)
        row.update(identity=identity(os.lstat(target)),sha256=digest(raw));self.save_receipt()
    def unit_state(self,unit):
        allowed=set([self.paths['socket_unit'],self.paths['service_unit']]+list(self.paths['client_units'].values()))
        need(unit in allowed,'EXACT_NONCE_UNIT')
        result=self.command(['show',unit,'--no-pager','--property=MainPID,ActiveState,SubState,ControlGroup,FragmentPath,LoadState'],False)
        return dict(line.split('=',1) for line in result['stdout'].decode().splitlines() if '=' in line)
    def output(self,role):
        target=self.paths['root']+'/output-'+role+'.jsonl'
        try:raw,unused=self.read_file(target,65536)
        except FileNotFoundError:return []
        return [parse(line) for line in raw.splitlines() if line.startswith(b'{')]
    def wait_output(self,role,case,event,seconds):
        end=time.monotonic()+min(seconds,self.deadline.remaining())
        while time.monotonic()<end:
            for row in self.output(role):
                value=row.get('result',row)
                if row.get('event')==event and value.get('case')==case:return row
            time.sleep(.02)
        raise TimeoutError('HELPER_RESULT_DEADLINE')
    def socket_identity(self):
        info=os.lstat(self.paths['socket']);need(stat.S_ISSOCK(info.st_mode),'NONCE_SOCKET_TYPE')
        result={'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}
        self.receipt['socket_identity']=result;self.save_receipt();return result
    def wait_accepted(self,case):
        end=time.monotonic()+min(1,self.deadline.remaining())
        while time.monotonic()<end:
            count=self.capture_budget()
            need(type(count) is int and count<=case,'UNEXPECTED_CONNECTION_BEFORE_RACE')
            if count==case:return
            time.sleep(.01)
        raise TimeoutError('ACCEPTED_CONNECTION_NOT_OBSERVED_BEFORE_RACE')
    def capture_budget(self):
        target=self.paths['root']+'/connection-budget.json'
        rows=[row for row in self.created if row['path']==target]
        if not rows:return None
        raw,info=self.read_file(target,4096);row=rows[0]
        need(all(info[k]==row['identity'][k] for k in ('dev','ino','uid','gid','mode','nlink')),'BUDGET_INODE_CHANGED')
        value=parse(raw);keys(value,('schema','nonce','accepted'),'BUDGET_SCHEMA')
        need(value['schema']==1 and value['nonce']==self.policy['nonce'] and type(value['accepted']) is int and
             0<=value['accepted']<=8,'EXACT_GLOBAL_CONNECTION_BUDGET')
        row.update(identity=info,sha256=digest(raw));self.receipt['accepted_connections']=value['accepted'];self.save_receipt()
        return value['accepted']
    def capture_output(self,role):
        for leaf in ('output-'+role+'.jsonl','error-'+role+'.txt'):
            target=self.paths['root']+'/'+leaf
            matched=[x for x in self.created if x['path']==target]
            need(len(matched)==1,'EXACT_CREATED_OUTPUT')
            raw,info=self.read_file(target,65536);row=matched[0]
            need(all(info[k]==row['identity'][k] for k in ('dev','ino','uid','gid','mode','nlink')),'OUTPUT_INODE_CHANGED')
            row.update(identity=info,sha256=digest(raw))
            detail={'path':target,'sha256':digest(raw),'bytes':len(raw)}
            if role=='ledger' and leaf.endswith('.jsonl'):
                detail['observations']=[parse(line) for line in raw.splitlines() if line.startswith(b'{')]
            self.event('OUTPUT_CAPTURED',detail)
    def restart_service(self):
        self.command(['stop',self.paths['service_unit']],timeout=1);self.capture_output('ledger')
        self.replace_created(self.paths['root']+'/output-ledger.jsonl',b'')
        self.replace_created(self.paths['root']+'/error-ledger.txt',b'')
        self.command(['start',self.paths['service_unit']],timeout=1)
    def namespace_proof(self,unit):
        state=self.unit_state(unit);pid=int(state.get('MainPID','0'));need(pid>1,'LIVE_NONCE_HELPER_REQUIRED')
        need(state.get('FragmentPath')=='/run/systemd/system/'+unit and
             state.get('ControlGroup','').endswith('/'+unit),'EXACT_NONCE_HELPER_UNIT')
        before=os.stat('/proc/'+str(pid));own=os.readlink('/proc/'+str(pid)+'/ns/pid')
        manager=os.readlink('/proc/1/ns/pid')
        view=os.readlink('/proc/'+str(pid)+'/root/proc/1/ns/pid');after=os.stat('/proc/'+str(pid))
        need(before.st_ino==after.st_ino and own==manager==view and
             self.unit_state(unit).get('MainPID')==str(pid),'SHARED_INIT_NAMESPACE_UNPROVEN')
        return {'pid':pid,'namespace':own,'manager_namespace':manager,'helper_proc_view':view,
                'same_pid_namespace':True,'same_proc_namespace':True}
    def run_case(self,case,role,kind):
        unit=self.paths['client_units'][role]
        self.command(['stop',unit])
        self.capture_output(role)
        self.replace_created(self.paths['root']+'/output-'+role+'.jsonl',b'')
        self.replace_created(self.paths['root']+'/error-'+role+'.txt',b'')
        self.replace_created(self.paths['root']+'/helper-'+role+'-client.json',canonical(self.helper_config(role,case))+b'\n')
        if case==1:self.command(['start',self.paths['socket_unit']]);self.socket_identity()
        if kind=='restart_between':
            old=self.socket_identity();self.restart_service()
            need(self.socket_identity()==old,'LISTENER_CHANGED_DURING_SERVICE_RESTART')
        if kind=='recreate_between':
            old=self.socket_identity();self.command(['stop',self.paths['service_unit']]);self.command(['stop',self.paths['socket_unit']])
            need(not os.path.lexists(self.paths['socket']),'REMOVE_ON_STOP_NOT_OBSERVED')
            self.capture_output('ledger')
            self.replace_created(self.paths['root']+'/output-ledger.jsonl',b'')
            self.replace_created(self.paths['root']+'/error-ledger.txt',b'')
            self.command(['start',self.paths['socket_unit']]);new=self.socket_identity()
            self.event('SOCKET_RECREATED',{'before':old,'after':new})
        self.event('CLIENT_START_INTENT',{'case':case,'unit':unit});self.command(['start',unit])
        try:namespace=self.namespace_proof(unit)
        except BaseException as exc:namespace={'status':'NOT_VERIFIED','reason':type(exc).__name__}
        if kind in ('restart_during','recreate_during'):
            self.wait_output(role,case,'BOUND_PAUSED',2)
            # Connect() alone can leave a pending connection in the manager's
            # queue. Only interrupt a connection the old service has accepted.
            self.wait_accepted(case)
            if kind=='restart_during':self.restart_service()
            else:
                old=self.socket_identity();self.command(['stop',self.paths['service_unit']],timeout=1)
                self.command(['stop',self.paths['socket_unit']],timeout=1)
                need(not os.path.lexists(self.paths['socket']),'REMOVE_ON_STOP_NOT_OBSERVED')
                self.capture_output('ledger')
                self.replace_created(self.paths['root']+'/output-ledger.jsonl',b'')
                self.replace_created(self.paths['root']+'/error-ledger.txt',b'')
                self.command(['start',self.paths['socket_unit']],timeout=1)
                self.event('SOCKET_RECREATED_DURING',{'before':old,'after':self.socket_identity()})
            release={'schema':1,'nonce':self.policy['nonce'],'case':case,'policy_sha256':self.policy_sha}
            self.publish(self.paths['root']+'/release-%02d.json'%case,canonical(release)+b'\n')
        observed=self.wait_output(role,case,'RESULT',10)['result']
        observed['namespace_proof']=namespace
        if kind in ('restart_during','recreate_during'):
            observed['expected_rejection_observed']=observed.get('bound_before_failure') is True and observed.get('status')=='FAIL_OBSERVED'
        self.command(['stop',unit])
        need(self.capture_budget()==case,'UNEXPECTED_OR_MISSING_CONNECTION')
        return observed
    def validate_created_scope(self):
        root=self.paths['root'];units=set([self.paths['socket_unit'],self.paths['service_unit']]+list(self.paths['client_units'].values()))
        seen=set()
        for row in self.created:
            need(type(row) is dict and row.get('kind') in ('FILE','DIRECTORY'),'RECEIPT_RESOURCE_SCHEMA')
            target=row.get('path');need(type(target) is str and target not in seen,'RECEIPT_DUPLICATE_PATH');seen.add(target)
            allowed=target==root or target in ['/run/systemd/system/'+unit for unit in units] or (
                target.startswith(root+'/') and '/' not in target[len(root)+1:] and
                re.fullmatch(r'(?:probe_helpers\.py|node-sqlite-probe\.cjs|connection-budget\.json|probe-policy\.json|fixture-(?:activation\.json|epochs\.jsonl|activation\.lock|dispatcher\.json)|candidate-[a-z_]+\.py|helper-(?:ledger|broker|dashboard|callback|native)-(?:server|client)\.json|(?:output|error)-(?:ledger|broker|dashboard|callback|native)\.(?:jsonl|txt)|release-0[68]\.json)',target[len(root)+1:]))
            need(allowed and target!=self.paths['receipt'],'RECEIPT_RESOURCE_SCOPE')
            need(row['kind']==('DIRECTORY' if target==root else 'FILE'),'RECEIPT_RESOURCE_KIND')
            keys(row['identity'],('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'),'RECEIPT_IDENTITY')
            for value in row['identity'].values():integer(value)
            need(row['identity']['uid']==row['identity']['gid']==0 and row['identity']['nlink']>=1,'RECEIPT_ROOT_IDENTITY')
            if row['kind']=='FILE':sha(row['sha256'])
    def stopped_exact(self,unit):
        state=self.unit_state(unit)
        need(state.get('ActiveState') in ('inactive','failed') and state.get('MainPID','0') in ('','0'),'UNIT_NOT_STOPPED')
        control=state.get('ControlGroup','')
        if control:
            need(control=='/system.slice/'+unit,'EXACT_NONCE_CGROUP')
            target='/sys/fs/cgroup/systemd'+control+'/cgroup.procs'
            try:
                fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
                try:raw=os.read(fd,4097);need(not raw.strip(),'CGROUP_NOT_EMPTY')
                finally:os.close(fd)
            except FileNotFoundError:pass
        return True
    def cleanup(self):
        self.deadline=Deadline(LIMITS['cleanup_seconds'])
        if self.watchdog_armed:signal.setitimer(signal.ITIMER_REAL,LIMITS['cleanup_seconds'])
        results=[];self.validate_created_scope()
        units=list(self.paths['client_units'].values())+[self.paths['service_unit'],self.paths['socket_unit']]
        all_stopped=True
        for unit in units:
            rows=[row for row in self.created if row['path']=='/run/systemd/system/'+unit]
            if not rows:continue
            try:
                row=rows[0];raw,info=self.read_file(row['path'],65536)
                need(same(info,row['identity']) and digest(raw)==row['sha256'],'CLEANUP_UNIT_CHANGED')
                self.command(['stop',unit],timeout=1);self.stopped_exact(unit)
                results.append({'unit':unit,'status':'STOPPED_AND_EMPTY'})
            except FileNotFoundError:
                try:self.stopped_exact(unit);results.append({'unit':unit,'status':'ALREADY_ABSENT_STOPPED'})
                except BaseException as exc:all_stopped=False;results.append({'unit':unit,'status':'UNKNOWN','reason':type(exc).__name__})
            except BaseException as exc:
                all_stopped=False;results.append({'unit':unit,'status':'UNKNOWN','reason':type(exc).__name__})
        if all_stopped:
            try:self.capture_budget()
            except BaseException as exc:results.append({'budget':'RETAINED','reason':type(exc).__name__})
            for role in ROLES:
                if any(row['path']==self.paths['root']+'/output-'+role+'.jsonl' for row in self.created):
                    try:self.capture_output(role)
                    except BaseException as exc:results.append({'output':role,'status':'RETAINED','reason':type(exc).__name__})
            for row in reversed(self.created):
                target=row['path']
                if row['kind']=='DIRECTORY':continue
                try:
                    raw,info=self.read_file(target,1048576)
                    need(same(info,row['identity']) and digest(raw)==row['sha256'],'CLEANUP_RESOURCE_CHANGED')
                    os.unlink(target);results.append({'path':target,'status':'REMOVED'})
                except FileNotFoundError:results.append({'path':target,'status':'ABSENT'})
                except BaseException as exc:results.append({'path':target,'status':'RETAINED','reason':type(exc).__name__})
            try:self.command(['daemon-reload'],timeout=1)
            except BaseException as exc:results.append({'manager_reload':'UNKNOWN','reason':type(exc).__name__})
        else:results.append({'files':'RETAINED_BECAUSE_UNIT_STOP_UNCONFIRMED'})
        if os.path.lexists(self.paths['socket']):results.append({'socket':'RETAINED_REMOVE_ON_STOP_NOT_CONFIRMED'})
        self.receipt['stage']='CLEANUP_OBSERVED';self.receipt['cleanup']=results
        try:self.save_receipt()
        except BaseException:results.append({'receipt':'UNKNOWN'})
        return results


class Probe(object):
    def __init__(self,policy,policy_sha,ops):
        self.policy=validate_policy(policy)
        need(digest(canonical(self.policy)+b'\n')==policy_sha,'CANONICAL_POLICY_HASH')
        self.policy_sha=policy_sha;self.ops=ops
    def inspect(self):
        return {'schema':1,'effect_count':0,'scope':scope(self.policy),'host':self.ops.check_host(),
            'staged_sources':self.ops.preflight_sources(),
            'approval':'NOT_ESTABLISHED_BY_FLAG','production_acceptance':'NOT_VERIFIED'}
    def apply(self,helper_raw,operator_acknowledged):
        need(operator_acknowledged is True,'EXPLICIT_OPERATOR_ACKNOWLEDGEMENT_REQUIRED')
        self.ops.operator_acknowledged=True
        self.ops.check_host();self.ops.preflight_sources(helper_raw);cases=[];failure=None;cleanup=[];node_proof=None
        try:
            self.ops.begin()
            self.ops.install(helper_raw)
            node_proof=self.ops.run_node_sqlite()
            node_sqlite_probe.validate_node_sqlite_proof(node_proof,self.policy['node_sqlite']['node'],
                self.policy_sha,self.policy['node_sqlite']['probe_input_sha256'])
            for case,role,kind in CASES:
                self.ops.receipt['connections_reserved']+=1
                need(self.ops.receipt['connections_reserved']<=8,'CONNECTION_BUDGET')
                self.ops.event('CASE_INTENT',{'case':case,'role':role,'kind':kind})
                result=self.ops.run_case(case,role,kind);cases.append(result)
                self.ops.event('CASE_OBSERVED',result)
                if kind in ('restart_during','recreate_during'):
                    need(result.get('expected_rejection_observed') is True,'EXPECTED_RACE_REJECTION_NOT_OBSERVED')
                else:need(result.get('status')=='PASS_OBSERVED','UNEXPECTED_CASE_RESULT')
        except BaseException as exc:failure=type(exc).__name__+':'+str(exc)[:160]
        finally:
            if self.ops.receipt is not None:
                try:cleanup=self.ops.cleanup()
                except BaseException as exc:cleanup=[{'status':'UNKNOWN','reason':type(exc).__name__}]
        receipt_binding=None
        if self.ops.receipt is not None:
            try:receipt_binding=self.ops.receipt_binding()
            except BaseException as exc:
                cleanup.append({'receipt':'UNKNOWN','reason':type(exc).__name__})
                if failure is None:failure='CREATED_RECEIPT_NOT_VERIFIED'
        observations=[]
        for event in self.ops.receipt.get('events',[]) if self.ops.receipt else []:
            if event.get('event')=='OUTPUT_CAPTURED':observations.extend((event.get('detail') or {}).get('observations',[]))
        return {'schema':1,'cases':cases,'node_sqlite':node_proof,'created_receipt':receipt_binding,
            'server_observations':observations,'failure':failure,'cleanup':cleanup,
            'last_command_cleanup':getattr(self.ops,'last_command_cleanup',[]),
            'intentionally_retained':[scope(self.policy)['root'],scope(self.policy)['receipt']],
            'production_acceptance':'NOT_VERIFIED','resume_authority':False,
            'operator_acknowledgement_is_external_approval_proof':False}


def execute_reviewed_probe(policy,policy_sha256,runtime_source,helper_raw,operator_acknowledged):
    """Authenticated outer loader API; operator consent remains external.

    Caller must authenticate/cache these source files before importing this
    module. This wrapper preserves the same signal watchdog as the standalone
    CLI; it offers no fake backend or bypass argument.
    """
    need(operator_acknowledged is True,'EXPLICIT_OPERATOR_ACKNOWLEDGEMENT_REQUIRED')
    need(digest(helper_raw)==policy.get('helper_sha256'),'EXACT_HELPER_HASH')
    ops=HostOps(policy,policy_sha256,runtime_source);probe=Probe(policy,policy_sha256,ops)
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'UNEXPECTED_EXISTING_ALARM')
    def interrupted(signum,unused):raise RuntimeError('PROBE_SIGNAL_'+str(signum))
    previous={sig:signal.getsignal(sig) for sig in (signal.SIGALRM,signal.SIGTERM,signal.SIGINT)}
    for sig in previous:signal.signal(sig,interrupted)
    ops.watchdog_armed=True;signal.setitimer(signal.ITIMER_REAL,LIMITS['overall_seconds'])
    try:
        result=probe.apply(helper_raw,True)
        need(len(canonical(result))<=LIMITS['report_bytes'],'REPORT_BOUND')
        return result
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        for sig,value in previous.items():signal.signal(sig,value)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('inspect','apply','cleanup'))
    parser.add_argument('--policy',required=True);parser.add_argument('--policy-sha256',required=True)
    parser.add_argument('--driver-sha256',required=True);parser.add_argument('--helper',required=True)
    parser.add_argument('--runtime-source',required=True)
    parser.add_argument('--execute-reviewed-probe',action='store_true')
    args=parser.parse_args(argv)
    need(os.geteuid()==0,'ROOT_REQUIRED')
    # Bootstrap reads use the same no-follow/protected reader, without host effects.
    shell=object.__new__(HostOps);shell.deadline=Deadline(5)
    raw,unused=shell.read_file(args.policy,131072);sha(args.policy_sha256)
    need(digest(raw)==args.policy_sha256,'EXACT_POLICY_HASH')
    policy=validate_policy(parse(raw));need(raw==canonical(policy)+b'\n','CANONICAL_POLICY_FILE_REQUIRED')
    driver,unused=shell.read_file(os.path.realpath(__file__),1048576)
    need(digest(driver)==args.driver_sha256==policy['driver_sha256'],'EXACT_DRIVER_HASH')
    helper,unused=shell.read_file(args.helper,1048576);need(digest(helper)==policy['helper_sha256'],'EXACT_HELPER_HASH')
    ops=HostOps(policy,args.policy_sha256,args.runtime_source);probe=Probe(policy,args.policy_sha256,ops)
    if args.action=='inspect':result=probe.inspect()
    elif args.action=='apply':
        result=execute_reviewed_probe(policy,args.policy_sha256,args.runtime_source,helper,args.execute_reviewed_probe)
    else:
        need(args.execute_reviewed_probe,'EXPLICIT_OPERATOR_ACKNOWLEDGEMENT_REQUIRED');ops.operator_acknowledged=True;ops.check_host()
        saved,unused=ops.read_file(ops.paths['receipt'],131072);ops.receipt=parse(saved)
        need(ops.receipt.get('nonce')==policy['nonce'] and ops.receipt.get('policy_sha256')==args.policy_sha256,
             'EXACT_CLEANUP_RECEIPT')
        ops.created=ops.receipt['resources'];result={'cleanup':ops.cleanup(),'resume_authority':False}
    raw=canonical(result);need(len(raw)<=LIMITS['report_bytes'],'REPORT_BOUND');sys.stdout.write(raw.decode()+'\n')

if __name__=='__main__':main()
