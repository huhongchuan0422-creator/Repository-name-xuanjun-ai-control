"""Finite Owner-approved prerequisite narrowing; no activation or service effects.

Load only through the authenticated new-kit source cache. This module is not a
standalone host command. Acknowledgement records the externally granted scope;
it does not create approval. No file output, journal or retry queue is created.
"""
import contextlib
import errno
import hashlib
import os
import re
import signal
import socket
import stat
import sys
import time

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
HOME = '/home/xuanjun_dev'
OPENCLAW = HOME + '/.openclaw'
TARGETS = (OPENCLAW + '/bin', OPENCLAW + '/tools', OPENCLAW + '/tools/node-v24.21.0')
NODE = TARGETS[2] + '/bin/node'
NODE_SHA = '7fde7b8afa198da66257f42ee2001d874c7355631e6d1579a5fb5ef1f246df4c'
NODE_SIZE = 126595440
PUBLIC_FILES = {
    OPENCLAW+'/bin/openclaw':(188,'b6aff1f40be0d46330c167e44525ef9080d66e40bb36dbb66c3811b4103fe3f2',0o711),
    TARGETS[2]+'/lib/node_modules/openclaw/dist/is-main-DYSvvM1W.mjs':
        (1461,'cedd59a24eadaaf873515fabea73b776a66d40773c8ee5298f4946b9eef10469',None)}
MAX_SECONDS = 240
FIELDS = ('dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns')
XATTRS = ('system.posix_acl_access','system.posix_acl_default','security.capability')
DIRFLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os,'O_CLOEXEC',0)


class PrerequisiteHold(ValueError):
    pass


class PrerequisiteTimeout(KeyboardInterrupt):
    pass


def need(value, code):
    if not value:
        raise PrerequisiteHold(code)


def stamp(info):
    return tuple(getattr(info,'st_'+key) for key in FIELDS)


def metadata(info):
    row = {key:getattr(info,'st_'+key) for key in FIELDS}
    row['mode'] = stat.S_IMODE(info.st_mode)
    return row


def no_attributes(fd):
    for key in XATTRS:
        try:
            os.getxattr(fd,key)
        except OSError as error:
            need(error.errno in (errno.ENODATA,errno.ENOTSUP,errno.EOPNOTSUPP),'PREREQUISITE_XATTR_UNKNOWN')
        else:
            raise PrerequisiteHold('PREREQUISITE_ACL_OR_CAPABILITY')


@contextlib.contextmanager
def bounded():
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'PREREQUISITE_EXISTING_TIMER')
    previous=signal.getsignal(signal.SIGALRM)
    def expire(unused_signum,unused_frame):
        raise PrerequisiteTimeout()
    signal.signal(signal.SIGALRM,expire)
    primary=None
    try:
        signal.setitimer(signal.ITIMER_REAL,MAX_SECONDS,1.0)
        yield
    except BaseException as error:
        primary=error
        raise
    finally:
        failed=False
        try:signal.setitimer(signal.ITIMER_REAL,0)
        except BaseException:failed=True
        try:signal.signal(signal.SIGALRM,previous)
        except BaseException:failed=True
        if failed:
            if primary is not None:primary.prerequisite_cleanup_failed=True
            else:raise PrerequisiteHold('PREREQUISITE_TIMER_CLEANUP')


class HeldDirectories(object):
    """All write targets are fixed, opened no-follow, and held through the gate.

    Private fixture overrides exercise genuine fd chmod without host access.
    The production entry never accepts these overrides or arbitrary paths.
    """
    def __init__(self, _root='/', _owner=(1002,1002), _root_owner=(0,0), _root_mode=0o555):
        self.root=_root;self.owner=_owner;self.root_owner=_root_owner;self.root_mode=_root_mode
        self.held=[];self.rows={};self.bindings={};self.names={}

    def _expected(self,path):
        if path=='/':return self.root_owner+(self.root_mode,)
        if path=='/home':return self.root_owner+(0o755,)
        return self.owner+((0o775 if path in TARGETS else 0o700),)

    def _open(self,path,parent=None,name=None):
        fd=os.open(self.root if parent is None else name,DIRFLAGS,**({} if parent is None else {'dir_fd':parent}))
        self.held.append(fd);info=os.fstat(fd)
        need(stat.S_ISDIR(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==self._expected(path),
             'PREREQUISITE_DIRECTORY_AUTHORITY')
        no_attributes(fd)
        source=os.lstat(self.root) if parent is None else os.stat(name,dir_fd=parent,follow_symlinks=False)
        need(stamp(source)==stamp(info),'PREREQUISITE_DIRECTORY_OPEN_RACE')
        self.rows[path]=(fd,info);self.bindings[path]=(parent,name)
        return fd

    def __enter__(self):
        try:
            root=self._open('/');home=self._open('/home',root,'home')
            user=self._open(HOME,home,'xuanjun_dev');base=self._open(OPENCLAW,user,'.openclaw')
            self._open(TARGETS[0],base,'bin');tools=self._open(TARGETS[1],base,'tools')
            self._open(TARGETS[2],tools,'node-v24.21.0')
            for path in TARGETS:self.names[path]=self._names(self.rows[path][0])
            self.check();return self
        except BaseException as error:
            try:self.close()
            except BaseException:error.prerequisite_cleanup_failed=True
            raise

    @staticmethod
    def _names(fd):
        # scandir's iterator bounds allocation before materializing the name set.
        names=[]
        # CPython3.6 does not accept an fd to scandir. This kernel FD view
        # names only our already-open directory; no discovered pathname is used.
        with os.scandir('/proc/self/fd/'+str(fd)) as entries:
            for entry in entries:
                need(len(names)<4096,'PREREQUISITE_DIRECTORY_ENTRY_BOUND')
                names.append(entry.name)
        return tuple(sorted(names))

    def check(self):
        for path,(fd,before) in self.rows.items():
            parent,name=self.bindings[path]
            live=os.lstat(self.root) if parent is None else os.stat(name,dir_fd=parent,follow_symlinks=False)
            need(stamp(os.fstat(fd))==stamp(live)==stamp(before),'PREREQUISITE_DIRECTORY_CHANGED')
            no_attributes(fd)
        for path,names in self.names.items():
            need(self._names(self.rows[path][0])==names,'PREREQUISITE_DIRECTORY_CONTENTS_CHANGED')
        return {path:metadata(self.rows[path][1]) for path in TARGETS}

    def narrow(self,path):
        need(path in TARGETS,'PREREQUISITE_TARGET_SCOPE');self.check()
        fd,before=self.rows[path]
        need(stat.S_IMODE(before.st_mode)==0o775,'PREREQUISITE_ALREADY_CHANGED')
        os.fchmod(fd,0o755)
        after=os.fstat(fd)
        need(stat.S_ISDIR(after.st_mode) and stat.S_IMODE(after.st_mode)==0o755 and
             all(getattr(before,'st_'+key)==getattr(after,'st_'+key)
                 for key in FIELDS if key not in ('mode','ctime_ns')),
             'PREREQUISITE_CHMOD_POSTCONDITION')
        self.rows[path]=(fd,after);self.check()
        return metadata(after)

    def close(self):
        failure=None
        pending,self.held=self.held,[]
        for fd in reversed(pending):
            try:os.close(fd)
            except BaseException as error:
                if failure is None:failure=error
        if failure is not None:raise failure

    def __exit__(self,kind,error,tb):
        try:self.close()
        except BaseException:
            if error is not None:error.prerequisite_cleanup_failed=True
            else:raise
        return False


class HeldPublicFiles(object):
    """Two exact public source leaves stay open across the permission change."""
    def __init__(self,reader,_owner=(1002,1002)):
        self.reader=reader;self.owner=_owner;self.rows={};self.held=[]

    def __enter__(self):
        try:
            for path,(size,digest,mode) in sorted(PUBLIC_FILES.items()):
                with self.reader.parent(path) as (parent,leaf):
                    before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
                    need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==size and
                         (before.st_uid,before.st_gid)==self.owner and not before.st_mode&0o7022 and
                         before.st_mode&0o400 and (mode is None or stat.S_IMODE(before.st_mode)==mode),
                         'PREREQUISITE_PUBLIC_SOURCE_AUTHORITY')
                    fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=parent)
                    self.held.append(fd)
                    need(stamp(os.fstat(fd))==stamp(before),'PREREQUISITE_PUBLIC_OPEN_RACE');no_attributes(fd)
                    chunks=[];count=0
                    while True:
                        part=os.read(fd,min(4096,size+1-count))
                        if not part:break
                        count+=len(part);need(count<=size,'PREREQUISITE_PUBLIC_SOURCE_BOUND');chunks.append(part)
                    raw=b''.join(chunks)
                    need(count==size and hashlib.sha256(raw).hexdigest()==digest,'PREREQUISITE_PUBLIC_SOURCE_HASH')
                    need(stamp(os.fstat(fd))==stamp(before)==stamp(os.stat(leaf,dir_fd=parent,follow_symlinks=False)),
                         'PREREQUISITE_PUBLIC_READ_RACE');no_attributes(fd)
                    self.rows[path]=(fd,before,raw,digest)
            self.check();return self
        except BaseException as error:
            try:self.close()
            except BaseException:error.prerequisite_cleanup_failed=True
            raise

    def check(self):
        result={}
        for path,(fd,before,raw,digest) in sorted(self.rows.items()):
            need(stamp(os.fstat(fd))==stamp(before),'PREREQUISITE_PUBLIC_HELD_FILE_CHANGED');no_attributes(fd)
            fresh,row=self.reader.read(path,maximum=PUBLIC_FILES[path][0])
            need(fresh==raw and all(row[key]==metadata(before)[key] for key in FIELDS) and
                 row['sha256']==digest,'PREREQUISITE_PUBLIC_SOURCE_CHANGED')
            need(stamp(os.fstat(fd))==stamp(before),'PREREQUISITE_PUBLIC_HELD_FILE_CHANGED');no_attributes(fd)
            result[path]=dict(metadata(before),sha256=digest)
        return result

    def close(self):
        pending,self.held=self.held,[];failure=None
        for fd in reversed(pending):
            try:os.close(fd)
            except BaseException as error:
                if failure is None:failure=error
        if failure is not None:raise failure

    def __exit__(self,kind,error,tb):
        try:self.close()
        except BaseException:
            if error is not None:error.prerequisite_cleanup_failed=True
            else:raise
        return False


def validate_node_transition(before,after,directories_before,directories_after):
    """Only two approved ancestor mode/ctime changes may cross Node proofs."""
    need(before['kind']=='FIXED_NODE_DIRECTORY_ALIAS_MEASUREMENT' and
         after['kind']=='FIXED_NODE_DIRECTORY_ALIAS' and before['admission']=='NOT_GRANTED' and
         before['unsafe_ancestors']==sorted(TARGETS[1:]),'PREREQUISITE_NODE_TRANSITION_KIND')
    need(before['link']==after['link'] and before['final']==after['final'] and
         before['reference_path']==after['reference_path'] and
         set(before['ancestors'])==set(after['ancestors']),'PREREQUISITE_NODE_IDENTITY_CHANGED')
    for path,old in before['ancestors'].items():
        new=after['ancestors'][path]
        if path in TARGETS[1:]:
            need(old['mode']==0o775 and new['mode']==0o755 and
                 {k:v for k,v in old.items() if k not in ('mode','ctime_ns')}==
                 {k:v for k,v in new.items() if k not in ('mode','ctime_ns')},
                 'PREREQUISITE_NODE_ANCESTOR_CHANGED')
            for row,observed in ((old,directories_before[path]),(new,directories_after[path])):
                need(all(row[key]==observed[key] for key in FIELDS),'PREREQUISITE_NODE_TARGET_BINDING')
        else:need(old==new,'PREREQUISITE_NODE_ANCESTOR_CHANGED')
    return True


def cleanup_unknown(error):
    if getattr(error,'prerequisite_cleanup_failed',False) is True:return True
    seen=set();current=error
    for unused in range(8):
        if current is None or id(current) in seen:return False
        seen.add(id(current))
        if type(current) is ValueError and current.args in (
                ('EXISTING_LOCKS_CLEANUP_UNKNOWN',),('NODE_REFERENCE_CLEANUP_UNKNOWN',)):
            return True
        current=current.__cause__
    return False


def execute(backend,acknowledged):
    """One finite injected sequence. Production supplies only FixedBackend."""
    result={'schema':1,'kind':'EPOCH7_OWNER_PREREQUISITE','stage':'HOLD',
        'authorized_targets':list(TARGETS),'attempted':[],'completed':[],
        'automatic_retry':False,'permission_widening_rollback':False,
        'production_admission':'NOT_GRANTED','service_actions':0,'database_writes':0}
    try:
        need(acknowledged is True,'PREREQUISITE_SCOPE_ACK_REQUIRED')
        with backend as active:
            result['before']=active.directories.check()
            result['entry_before']=active.entry_evidence()
            first=active.guard();result['guard_before']=first
            proof=active.node_measurement();result['node_before']=proof
            need(proof['kind']=='FIXED_NODE_DIRECTORY_ALIAS_MEASUREMENT' and proof['admission']=='NOT_GRANTED' and
                 proof['final']['path']==NODE and proof['final']['sha256']==NODE_SHA and
                 proof['final']['metadata']['size']==NODE_SIZE,'PREREQUISITE_NODE_PROOF')
            active.guard();active.directories.check()
            for path in TARGETS:
                active.guard();active.directories.check()
                result['attempted'].append(path)
                active.directories.narrow(path)
                result['completed'].append(path)
            active.guard();result['after']=active.directories.check()
            result['node_after']=active.node_admission()
            result['guard_after']=active.guard()
            result['after']=active.directories.check()
            validate_node_transition(proof,result['node_after'],result['before'],result['after'])
            result['entry_after']=active.entry_evidence()
            need(result['entry_after']==result['entry_before'],'PREREQUISITE_PUBLIC_SOURCE_CHANGED')
            result['after']=active.directories.check()
            result['stage']='COMPLETE_PREREQUISITES_ONLY'
    except BaseException as error:
        result['stage']='PARTIAL_HOLD' if result['attempted'] else 'HOLD'
        if isinstance(error,(KeyboardInterrupt,SystemExit)):
            result['failure_code']='PREREQUISITE_INTERRUPTED'
        elif isinstance(error,ValueError) and re.fullmatch(r'[A-Z0-9_]{1,128}',str(error)):
            result['failure_code']=str(error)
        else:result['failure_code']='PREREQUISITE_BOUNDARY_OR_IO_FAILED'
        result['cleanup_failed']=cleanup_unknown(error)
    return result


class FixedBackend(object):
    def __enter__(self):
        import epoch7_delta as d
        import epoch7_snapshot as c
        import snapshot_io as concrete
        import observe_epoch7 as observed
        self.d,self.c,self.concrete,self.observed=d,c,concrete,observed
        self.stack=contextlib.ExitStack();self.deadline=time.monotonic()+MAX_SECONDS
        try:
            reader=observed.ObservationReader({});pins={}
            for name,mode in ((c.INSTALL_LOCK,0o600),(c.ACTIVATION_LOCK,0o644)):
                raw,row=reader.read(name)
                need((row['uid'],row['gid'],row['mode'])==(0,0,mode),'PREREQUISITE_LOCK_AUTHORITY')
                pins[name]={key:row[key] for key in ('sha256','uid','gid','mode')}
            self.locks=self.stack.enter_context(concrete.existing_locks(reader,{'files':pins}))
            # Measurement authority applies only to these three directories and
            # never escapes into a recovery policy or normal executable reader.
            class MeasurementIO(observed.ObservationIO):
                def _authority(inner,fd,path):
                    if path not in TARGETS:return super(MeasurementIO,inner)._authority(fd,path)
                    info=os.fstat(fd);mode=stat.S_IMODE(info.st_mode)
                    need(stat.S_ISDIR(info.st_mode) and (info.st_uid,info.st_gid)==(1002,1002) and mode in (0o775,0o755),
                         'PREREQUISITE_MEASUREMENT_AUTHORITY')
                    no_attributes(fd)
                    # Staged permission changes invalidate old measurement pins;
                    # this private IO never exports those pins as approved policy.
                    inner.pins[path]={'uid':1002,'gid':1002,'mode':mode}
                    return info
            self.io=MeasurementIO({},self.locks);self.io.deadline=self.deadline
            self.directories=self.stack.enter_context(HeldDirectories())
            self.policy=self._writer_policy();self.io.policy=self.policy
            self.state=None;self.stable_writer=None
            self.public_files=self.stack.enter_context(HeldPublicFiles(self.io))
            return self
        except BaseException as error:
            try:self.stack.__exit__(*sys.exc_info())
            except BaseException:error.prerequisite_cleanup_failed=True
            raise

    def _writer_policy(self):
        c,d,io=self.c,self.d,self.io
        raw,row=io.read(self.observed.READINESS)
        need(row['sha256']==self.observed.READINESS_SHA and
             (row['uid'],row['gid'],row['mode'],row['nlink'])==(0,0,0o600,1),'PREREQUISITE_READINESS_PIN')
        baseline=c.decode(raw)['sections']['remaining_control_entry_inventory']
        executables={};files={}
        for label,name in (('systemctl','/usr/bin/systemctl'),('systemd','/usr/lib/systemd/systemd')):
            unused,meta=io.read(name,maximum=33554432)
            need(meta['uid']==meta['gid']==0 and meta['mode']&0o111,'PREREQUISITE_TOOL_AUTHORITY')
            executables[label]={'path':name,'sha256':meta['sha256']}
            files[name]={key:meta[key] for key in ('sha256','uid','gid','mode')}
        policy={'executables':executables,'files':files,'scheduler_files':{},'control_units':{}}
        io.policy=policy
        scheduler={}
        for root in sorted(c.SCHEDULER_ROOTS):scheduler.update(io.scheduler_inventory(root))
        need(scheduler=={r['path']:r['sha256'] for r in baseline['scheduler_metadata']},'PREREQUISITE_SCHEDULER_BASELINE')
        policy['scheduler_files']=scheduler
        old=baseline['registered_control_units'];expected=set(old)|{n for n in c.WRITER_UNITS if n.startswith(('xj-','xuanjun-'))}
        listing=io.command('systemctl',['list-unit-files','--no-legend','--no-pager']).decode('utf-8','strict')
        actual={line.split()[0] for line in listing.splitlines() if line.split() and line.split()[0].startswith(('xj-','xuanjun-'))}
        need(actual==expected,'PREREQUISITE_CONTROL_UNIT_SET')
        for unit in sorted(actual):
            rows={};paths={'/etc/systemd/system/'+unit}
            for script in old.get(unit,{}).get('script_metadata',[]):
                path=script['path'];c.path(path)
                need(path.startswith(('/home/xuanjun_dev/','/usr/local/bin/','/opt/','/etc/')),'PREREQUISITE_SCRIPT_SCOPE')
                data,unused=io.read(path)
                need(c.sha(data)==script['sha256'],'PREREQUISITE_SCRIPT_PIN');paths.add(path)
            for path in paths:
                if path in c.LEGACY_MASKS:io.mask(path);rows[path]=c.sha(b'/dev/null')
                else:rows[path]=io.read(path)[1]['sha256']
            policy['control_units'][unit]=rows
        return policy

    def entry_evidence(self):
        return self.public_files.check()

    def guard(self):
        c,d,io=self.c,self.d,self.io;io.check_locks()
        if hasattr(self,'public_files'):self.public_files.check()
        current,current_meta=io.read(c.ACTIVE);epochs,epochs_meta=io.read(c.EPOCHS)
        need(all((row['uid'],row['gid'],row['mode'],row['nlink'])==(0,0,0o644,1)
                 for row in (current_meta,epochs_meta)),'PREREQUISITE_ACTIVATION_AUTHORITY')
        active=c.decode(current);d.validate_activation(active,7,d.OLD_MANIFEST);chain=c.activation_chain(epochs,active)
        state=(current,current_meta,epochs,epochs_meta)
        if self.state is None:self.state=state
        need(state==self.state,'PREREQUISITE_ACTIVATION_CHANGED')
        writers=c.validate_writers(io.writers(self.policy,c.DATABASES))
        stable={key:value for key,value in writers.items() if key!='processes'}
        if self.stable_writer is None:self.stable_writer=stable
        need(stable==self.stable_writer,'PREREQUISITE_WRITER_BASELINE_CHANGED')
        # Every census must pass independently; unrelated root process churn is
        # not mistaken for a changed persistent controller configuration.
        return {'activation_sha256':c.sha(current),'epochs_sha256':c.sha(epochs),
                'writer_evidence_sha256':d.digest(writers),'epoch':7,'state':'PREPARED'}

    def node_measurement(self):
        import unit_metadata
        raw,row=self.io.read(self.c.NATIVE)
        need(row['sha256']==self.c.NATIVE_CURRENT_SHA and
             (row['uid'],row['gid'],row['mode'],row['nlink'])==(0,0,0o644,1),'PREREQUISITE_NATIVE_PIN')
        native=self.c.decode(raw)['gatewayIdentity']
        need(native['exe']==NODE and native['sha256']==NODE_SHA,'PREREQUISITE_NATIVE_NODE_SCOPE')
        proof=self.io.measure_node_directory_reference(NODE,NODE_SHA)
        return unit_metadata.validate_node_reference_measurement(proof,NODE,NODE_SHA)

    def node_admission(self):
        import unit_metadata
        fresh=self.observed.ObservationIO({},self.locks);fresh.deadline=self.deadline
        proof=fresh.node_directory_reference(NODE,NODE_SHA)
        return unit_metadata.validate_node_reference(proof,NODE,NODE_SHA)

    def __exit__(self,kind,error,tb):
        try:return self.stack.__exit__(kind,error,tb)
        except BaseException:
            if error is not None:error.prerequisite_cleanup_failed=True;return False
            raise


def apply_reviewed_prerequisites(operator_acknowledged=False):
    """Fixed-host production interface. Caller keeps authenticated imports alive."""
    need(os.geteuid()==os.getegid()==0 and socket.gethostname().split('.')[0]==HOST,'PREREQUISITE_FIXED_ROOT_HOST')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'PREREQUISITE_ISOLATED_INTERPRETER')
    with bounded():
        return execute(FixedBackend(),operator_acknowledged)
