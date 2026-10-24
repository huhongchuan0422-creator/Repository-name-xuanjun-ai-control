"""Default-disabled host-only coordinator over the ORIGINAL UK Docker transport.

No CLI/listener/grant. Parent fd and live protected-reference/health readers must
come from a separately reviewed original root composition. No site calls at import.
"""
import fcntl
import hashlib
import json
import math
import os
import stat
import time
import threading
from scripts import community_preview_release_plan as plan
from scripts import community_preview_upgrade as original


OWNER_UID=0  # fixed root journal policy; no request/config override
JOURNAL_PARENT='/opt/xuanjun-community-preview/update-journal'  # proposed; NOT created at import

class Hold(RuntimeError):pass


def protected(fd,directory=False):
    s=os.fstat(fd)
    if (not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode))
            or s.st_uid!=OWNER_UID or stat.S_IMODE(s.st_mode)!=(0o700 if directory else 0o600)
            or not directory and s.st_nlink!=1):raise Hold('PROTECTED_JOURNAL_REQUIRED')


class Journal:
    """Real exclusive lock, bounded no-follow read and fsynced atomic checkpoint.

    parent_fd is an original protected directory capability, NOT a request path.
    The future composition must open its fixed parent through verified parent chains.
    """
    def __init__(self,parent_fd,candidate):
        protected(parent_fd,True)
        if os.readlink('/proc/self/fd/'+str(parent_fd))!=JOURNAL_PARENT:raise Hold('FIXED_ORIGINAL_JOURNAL_PARENT_REQUIRED')
        if candidate.get('state')!='REVIEW_CANDIDATE_NOT_AUTHORIZED':raise Hold('COMPLETE_REVIEWED_BINDINGS_REQUIRED')
        rebuilt=plan.prepare(candidate['source'],candidate['current'],candidate['image'])
        if candidate!=rebuilt:raise Hold('EXACT_COMPILED_PLAN_REQUIRED')
        self.plan=candidate;self.parent=os.dup(parent_fd);self.fd=None;self.lock=None;self.poisoned=False;self.owner=threading.get_ident()
        try:
            self.lock=os.open('community-update.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=self.parent)
            protected(self.lock);fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            name=candidate['attempt']
            active=json.dumps({'attempt':name,'plan_sha256':candidate['plan_sha256']},sort_keys=True).encode()
            try:
                fd=os.open('active-attempt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.parent)
                with os.fdopen(fd,'wb') as stream:stream.write(active);stream.flush();os.fsync(stream.fileno())
                os.fsync(self.parent)
            except FileExistsError:
                fd=os.open('active-attempt.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.parent)
                with os.fdopen(fd,'rb') as stream:
                    protected(stream.fileno());prior=stream.read(65537)
                if prior!=active:raise Hold('OTHER_ATTEMPT_OR_PARTIAL_ACTIVE_RECORD_INSPECT_ONLY')
            try:os.mkdir(name,0o700,dir_fd=self.parent);os.fsync(self.parent)
            except FileExistsError:pass
            self.fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.parent);protected(self.fd,True)
            try:os.stat('checkpoint.tmp',dir_fd=self.fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise Hold('PARTIAL_CHECKPOINT_INSPECT_ONLY')
            self.state=self.read()
            if self.state is None:self.write('PREPARED')
            elif self.state.get('plan_sha256')!=candidate['plan_sha256']:raise Hold('CHECKPOINT_PLAN_CHANGED')
            events=sorted(n for n in os.listdir(self.fd) if n.startswith('event-'))
            if len(events)!=self.state['sequence'] or events[-1:]!=['event-%06d.json'%self.state['sequence']]:
                raise Hold('PARTIAL_EVENT_HISTORY_INSPECT_ONLY')
        except BaseException:self.close();raise
    @classmethod
    def from_original_parent(cls,candidate):
        # Future approved host composition only. Do not create/chmod the parent.
        original.secure_directory(JOURNAL_PARENT)
        fd=os.open(JOURNAL_PARENT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:return cls(fd,candidate)
        finally:os.close(fd)
    def read(self):
        try:fd=os.open('checkpoint.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.fd)
        except FileNotFoundError:return None
        with os.fdopen(fd,'rb') as stream:
            protected(stream.fileno());raw=stream.read(65537)
        if len(raw)>65536:raise Hold('CHECKPOINT_SIZE')
        value=json.loads(raw)
        if type(value) is not dict or set(value)-{'plan_sha256','phase','new_id','sequence'}:raise Hold('CHECKPOINT_SHAPE')
        if value.get('new_id') is not None and not plan.exact_hex(value['new_id'],64):raise Hold('CHECKPOINT_ID')
        if type(value.get('sequence')) is not int or not 1<=value['sequence']<=64:raise Hold('CHECKPOINT_SEQUENCE')
        return value
    def write(self,phase,new_id=None):
        if self.poisoned or threading.get_ident()!=self.owner:raise Hold('JOURNAL_OWNER_OR_IO_HOLD')
        sequence=(self.state['sequence'] if self.state else 0)+1
        if sequence>64:raise Hold('CHECKPOINT_LIMIT')
        value=dict(plan_sha256=self.plan['plan_sha256'],phase=phase,new_id=new_id,sequence=sequence)
        raw=json.dumps(value,sort_keys=True).encode()
        try:
            # Append-only history is durable BEFORE replacing the current pointer.
            for name in ('event-%06d.json'%sequence,'checkpoint.tmp'):
                fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
                with os.fdopen(fd,'wb') as stream:protected(stream.fileno());stream.write(raw);stream.flush();os.fsync(stream.fileno())
                os.fsync(self.fd)
            os.replace('checkpoint.tmp','checkpoint.json',src_dir_fd=self.fd,dst_dir_fd=self.fd);os.fsync(self.fd)
            self.state=value
        except BaseException:self.poisoned=True;raise
    def close(self):
        for name in ('fd','lock','parent'):
            value=getattr(self,name,None)
            if value is not None:os.close(value);setattr(self,name,None)


class OriginalTransport:
    def __init__(self,protected_bindings,health_reader):
        if not callable(protected_bindings) or not callable(health_reader):raise Hold('ORIGINAL_LIVE_READERS_REQUIRED')
        self.bindings=protected_bindings;self.health=health_reader
    def inspect(self,cid,image,running):
        value=original.inspect(cid);original.validate(value,image,cid,running=running);return value
    def mutate(self,argv):return original.mutate(argv,20).strip()
    def image_and_names_ready(self,candidate):
        fmt='{{json .Id}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}'
        rows=original.command(plan.DOCKER+['image','inspect','--format',fmt,candidate['image']['image_id']]).splitlines()
        if len(rows)!=3 or [json.loads(v) for v in rows]!=[candidate['image']['image_id'],candidate['source']['source_sha'],'10001:1008']:
            raise Hold('EXACT_LOADED_IMAGE_REQUIRED')
        names=original.command(plan.DOCKER+['container','ls','--all','--format','{{.Names}}','--filter','name=^/xuanjun-community-preview']).splitlines()
        if candidate['rollback_name'] in names or candidate['failed_name'] in names:raise Hold('EXISTING_RECOVERY_NAME_INSPECT_ONLY')
    def socket_absent(self):
        if os.path.lexists(plan.RUN+'/preview.sock'):raise Hold('SOCKET_REMAINS')


class Update:
    def __init__(self,journal,transport,*,execution_enabled=False,clock=time.time):
        if type(transport) is not OriginalTransport:raise Hold('ORIGINAL_TRANSPORT_REQUIRED')
        self.journal=journal;self.t=transport;self.enabled=execution_enabled;self.clock=clock;self.last=None
    def guard(self):
        if self.journal.poisoned or threading.get_ident()!=self.journal.owner:raise Hold('JOURNAL_OWNER_OR_IO_HOLD')
        if self.enabled is not True:raise Hold('UPDATE_EXECUTION_DISABLED')
        if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=plan.HOST:raise Hold('EXACT_ROOT_HOST_REQUIRED')
        now=self.clock()
        if type(now) not in (int,float) or not math.isfinite(now) or self.last is not None and now<self.last:raise Hold('CLOCK_INVALID')
        self.last=now
        c=self.journal.plan['current']
        # A live recheck may refresh observed_at, never any protected identity.
        raw=self.t.bindings()
        if type(raw) is not dict or type(raw.get('running')) is not bool:raise Hold('LIVE_BINDING_SHAPE')
        live=plan.current_identity(dict(raw,running=True))
        if any(live[k]!=c[k] for k in c if k not in ('observed_at','running')):raise Hold('PROTECTED_BINDING_CHANGED')
        if not now-600<=live['observed_at']<=now+30:raise Hold('CURRENT_OBSERVATION_EXPIRED')
        return int(now)
    def action(self,intent,argv,*,new_id=None):
        self.guard();self.journal.write(intent,new_id)
        # Recheck time/binding after durable I/O, immediately before the mutation.
        self.guard()
        try:return self.t.mutate(argv)
        except BaseException:
            self.journal.write('HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT',new_id)
            raise Hold('MUTATION_UNKNOWN_NO_RETRY') from None
    def run(self):
        self.guard();j=self.journal;p=j.plan;c=p['current'];image=p['image']['image_id']
        if j.state['phase']!='PREPARED':raise Hold('EXISTING_ATTEMPT_RECOVER_OR_INSPECT_ONLY')
        self.t.image_and_names_ready(p)
        self.t.inspect(c['container_id'],c['image_id'],True)
        self.action('OLD_STOP_INTENT',p['actions'][1]['argv']);self.t.inspect(c['container_id'],c['image_id'],False);self.t.socket_absent()
        j.write('OLD_STOPPED')
        self.action('OLD_RENAME_INTENT',p['actions'][2]['argv']);j.write('OLD_RETAINED')
        new_id=self.action('NEW_RUN_INTENT',p['actions'][3]['argv'])
        if not plan.exact_hex(new_id,64):j.write('HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT');raise Hold('NEW_ID_UNKNOWN')
        j.write('NEW_KNOWN',new_id)
        # Unknown inspection/clock/binding/transport failures never become a
        # rollback permit. A concrete completed nonmatching health report is the
        # only recoverable verification failure here; recovery still rechecks all.
        try:
            self.guard();self.t.inspect(new_id,image,True)
            health=self.t.health();now=self.guard()
            self.t.inspect(c['container_id'],c['image_id'],False);self.guard()
        except Exception:
            j.write('HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT',new_id);raise Hold('VERIFY_UNKNOWN') from None
        if not plan.exact_health(health,p['source']['source_sha'],p['image']['oci_revision'],now):
            j.write('KNOWN_FAILURE',new_id);raise Hold('KNOWN_FAILURE_RECOVERY_REQUIRED')
        j.write('COMMITTED',new_id);return dict(j.state)
    def recover(self):
        self.guard();j=self.journal;p=j.plan;c=p['current'];new_id=j.state.get('new_id')
        if j.state['phase']!='KNOWN_FAILURE' or not plan.exact_hex(new_id,64):raise Hold('KNOWN_NEW_RECEIPT_REQUIRED')
        value=original.inspect(new_id);original.validate(value,p['image']['image_id'],new_id,running=value['running'])
        if value['running']:self.action('RECOVERY_STOP_NEW_INTENT',plan.DOCKER+['stop','--time','10',new_id],new_id=new_id)
        self.t.inspect(new_id,p['image']['image_id'],False);self.t.socket_absent()
        self.action('RECOVERY_RENAME_NEW_INTENT',plan.DOCKER+['rename',new_id,p['failed_name']],new_id=new_id)
        self.t.inspect(c['container_id'],c['image_id'],False)
        self.action('RECOVERY_RESTORE_OLD_INTENT',p['rollback']['old_rename_argv'],new_id=new_id)
        self.action('RECOVERY_START_OLD_INTENT',p['rollback']['old_start_argv'],new_id=new_id)
        self.t.inspect(c['container_id'],c['image_id'],True);self.guard()
        old_health=self.t.health()
        if (old_health.get('http_status')!=200 or old_health.get('url')!=plan.URL or old_health.get('status')!='READY'
                or old_health.get('scope')!='PROCESS_AND_DATABASE_CONNECTIVITY' or old_health.get('production_acceptance') is not False):raise Hold('ROLLBACK_HEALTH_UNKNOWN')
        j.write('ROLLED_BACK_PREVIEW_HOLD',new_id);return dict(j.state)
