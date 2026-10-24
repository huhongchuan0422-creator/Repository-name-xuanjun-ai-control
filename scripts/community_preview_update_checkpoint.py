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

HOLD_PHASE='HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT'
TRANSITIONS={
    'PREPARED':{'OLD_STOP_INTENT','STOPPED_HANDOFF_ACCEPTED'},
    'STOPPED_HANDOFF_ACCEPTED':{'OLD_RENAME_INTENT'},'OLD_STOP_INTENT':{'OLD_STOPPED'},
    'OLD_STOPPED':{'OLD_RENAME_INTENT'},'OLD_RENAME_INTENT':{'OLD_RETAINED'},
    'OLD_RETAINED':{'NEW_RUN_INTENT'},'NEW_RUN_INTENT':{'NEW_KNOWN'},
    'NEW_KNOWN':{'KNOWN_FAILURE','COMMITTED'},
    'KNOWN_FAILURE':{'RECOVERY_STOP_NEW_INTENT','RECOVERY_RENAME_NEW_INTENT'},
    'RECOVERY_STOP_NEW_INTENT':{'RECOVERY_RENAME_NEW_INTENT'},
    'RECOVERY_RENAME_NEW_INTENT':{'RECOVERY_RESTORE_OLD_INTENT'},
    'RECOVERY_RESTORE_OLD_INTENT':{'RECOVERY_START_OLD_INTENT'},
    'RECOVERY_START_OLD_INTENT':{'ROLLED_BACK_PREVIEW_HOLD'},
    'COMMITTED':set(),'ROLLED_BACK_PREVIEW_HOLD':set(),HOLD_PHASE:set()}
ID_PHASES={'NEW_KNOWN','KNOWN_FAILURE','COMMITTED','RECOVERY_STOP_NEW_INTENT',
           'RECOVERY_RENAME_NEW_INTENT','RECOVERY_RESTORE_OLD_INTENT',
           'RECOVERY_START_OLD_INTENT','ROLLED_BACK_PREVIEW_HOLD'}


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
    def __init__(self,parent_fd,candidate,*,lease_fd=None,handoff_binding=None):
        protected(parent_fd,True)
        if os.readlink('/proc/self/fd/'+str(parent_fd))!=JOURNAL_PARENT:raise Hold('FIXED_ORIGINAL_JOURNAL_PARENT_REQUIRED')
        if candidate.get('state')!='REVIEW_CANDIDATE_NOT_AUTHORIZED':raise Hold('COMPLETE_REVIEWED_BINDINGS_REQUIRED')
        stopped=candidate.get('handoff_mode')=='STOPPED_HANDOFF_V1'
        rebuilt=(plan.prepare_stopped if stopped else plan.prepare)(candidate['source'],candidate['current'],candidate['image'])
        self.handoff_binding=handoff_binding
        if stopped:
            if lease_fd is None:raise Hold('STOPPED_HANDOFF_CONTINUOUS_LEASE_REQUIRED')
            if type(handoff_binding) is not dict or set(handoff_binding)!={'approval_sha256','handoff_sha256'} or not all(plan.exact_hex(v,64) for v in handoff_binding.values()):raise Hold('EXACT_HANDOFF_BINDING_REQUIRED')
        elif handoff_binding is not None or lease_fd is not None:raise Hold('LEGACY_JOURNAL_NO_HANDOFF_ARGUMENTS')
        if candidate!=rebuilt:raise Hold('EXACT_COMPILED_PLAN_REQUIRED')
        self.plan=candidate;self.parent=os.dup(parent_fd);self.fd=None;self.lock=None;self.poisoned=False;self.owner=threading.get_ident();self.cleanup_unproven=False
        try:
            if lease_fd is None:
                self.lock=os.open('community-update.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=self.parent)
            else:
                if type(lease_fd) is not int:raise Hold('EXACT_LEASE_DESCRIPTOR_REQUIRED')
                protected(lease_fd)
                bound=os.stat('community-update.lock',dir_fd=self.parent,follow_symlinks=False);held=os.fstat(lease_fd)
                if (bound.st_dev,bound.st_ino)!=(held.st_dev,held.st_ino):raise Hold('SAME_CONTINUOUS_LOCK_REQUIRED')
                self.lock=os.dup(lease_fd)
            protected(self.lock);fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            name=candidate['attempt']
            active=json.dumps({'attempt':name,'plan_sha256':candidate['plan_sha256']},sort_keys=True).encode()
            active_created=False
            try:os.stat('active-attempt.json',dir_fd=self.parent,follow_symlinks=False)
            except FileNotFoundError:
                try:os.stat(name,dir_fd=self.parent,follow_symlinks=False)
                except FileNotFoundError:pass
                else:raise Hold('MISSING_ACTIVE_RECORD_INSPECT_ONLY')
            try:
                fd=os.open('active-attempt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.parent)
                with os.fdopen(fd,'wb') as stream:stream.write(active);stream.flush();os.fsync(stream.fileno())
                os.fsync(self.parent);active_created=True
            except FileExistsError:
                fd=os.open('active-attempt.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.parent)
                with os.fdopen(fd,'rb') as stream:
                    protected(stream.fileno());prior=stream.read(65537)
                if prior!=active:raise Hold('OTHER_ATTEMPT_OR_PARTIAL_ACTIVE_RECORD_INSPECT_ONLY')
            try:
                os.stat(name,dir_fd=self.parent,follow_symlinks=False);directory_created=False
            except FileNotFoundError:
                if not active_created:raise Hold('MISSING_ATTEMPT_DIRECTORY_INSPECT_ONLY')
                os.mkdir(name,0o700,dir_fd=self.parent);os.fsync(self.parent);directory_created=True
            self.fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.parent);protected(self.fd,True)
            try:os.stat('checkpoint.tmp',dir_fd=self.fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise Hold('PARTIAL_CHECKPOINT_INSPECT_ONLY')
            self.state=self.read()
            entries=os.listdir(self.fd)
            if self.state is None:
                if not active_created or not directory_created or entries:raise Hold('MISSING_CHECKPOINT_INSPECT_ONLY')
                self.write('PREPARED')
            self.validate_history()
        except BaseException:self.close();raise
    @classmethod
    def from_original_parent(cls,candidate):
        # Future approved host composition only. Do not create/chmod the parent.
        original.secure_directory(JOURNAL_PARENT)
        fd=os.open(JOURNAL_PARENT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        journal=None;error=None;temp_close_unproven=False
        try:journal=cls(fd,candidate)
        except BaseException as exc:error=exc
        temp=fd;fd=None
        try:os.close(temp)
        except BaseException:temp_close_unproven=True
        if temp_close_unproven:
            if journal is not None:
                try:journal.close()
                except BaseException:pass
            raise Hold('JOURNAL_PARENT_CLEANUP_UNKNOWN') from error
        if error is not None:raise error
        return journal
    def validate_record(self,value):
        keys={'plan_sha256','phase','new_id','sequence'}
        if self.handoff_binding is not None:keys|={'approval_sha256','handoff_sha256'}
        if type(value) is not dict or set(value)!=keys:raise Hold('CHECKPOINT_SHAPE')
        if self.handoff_binding is not None and any(value[k]!=v for k,v in self.handoff_binding.items()):raise Hold('JOURNAL_HANDOFF_BINDING_CHANGED')
        if value.get('phase')=='STOPPED_HANDOFF_ACCEPTED' and self.handoff_binding is None:raise Hold('LEGACY_RUNNING_PATH_REQUIRED')
        if value['plan_sha256']!=self.plan['plan_sha256']:raise Hold('CHECKPOINT_PLAN_CHANGED')
        if type(value['phase']) is not str or value['phase'] not in TRANSITIONS:raise Hold('CHECKPOINT_PHASE')
        if type(value['sequence']) is not int or not 1<=value['sequence']<=64:raise Hold('CHECKPOINT_SEQUENCE')
        if value['new_id'] is not None and not plan.exact_hex(value['new_id'],64):raise Hold('CHECKPOINT_ID')
        if value['phase'] in ID_PHASES and value['new_id'] is None:raise Hold('CHECKPOINT_ID_REQUIRED')
        if value['phase'] not in ID_PHASES|{HOLD_PHASE} and value['new_id'] is not None:raise Hold('CHECKPOINT_UNEXPECTED_ID')
    def read_record(self,name,missing=False):
        try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.fd)
        except FileNotFoundError:
            if missing:return None
            raise Hold('MISSING_EVENT_INSPECT_ONLY') from None
        with os.fdopen(fd,'rb') as stream:
            protected(stream.fileno());raw=stream.read(65537)
        if len(raw)>65536:raise Hold('CHECKPOINT_SIZE')
        try:value=json.loads(raw)
        except (ValueError,UnicodeError):raise Hold('CORRUPT_EVENT_INSPECT_ONLY') from None
        self.validate_record(value)
        if raw!=json.dumps(value,sort_keys=True).encode():raise Hold('NONCANONICAL_EVENT_INSPECT_ONLY')
        return value
    def read(self):return self.read_record('checkpoint.json',missing=True)
    def validate_transition(self,previous,current):
        self.validate_record(current)
        if previous is None:
            if current['sequence']!=1 or current['phase']!='PREPARED':raise Hold('EVENT_INITIAL_STATE')
            return
        if current['sequence']!=previous['sequence']+1:raise Hold('EVENT_SEQUENCE_GAP')
        allowed=TRANSITIONS[previous['phase']]|({HOLD_PHASE} if previous['phase']!=HOLD_PHASE else set())
        if current['phase'] not in allowed:raise Hold('EVENT_PHASE_TRANSITION')
        if previous['new_id'] is not None and current['new_id']!=previous['new_id']:raise Hold('EVENT_ID_CHANGED')
    def validate_history(self):
        expected=['event-%06d.json'%i for i in range(1,self.state['sequence']+1)]
        if set(os.listdir(self.fd))!=set(expected)|{'checkpoint.json'}:raise Hold('PARTIAL_EVENT_HISTORY_INSPECT_ONLY')
        previous=None
        for i,name in enumerate(expected,1):
            value=self.read_record(name)
            if value['sequence']!=i:raise Hold('EVENT_SEQUENCE_GAP')
            self.validate_transition(previous,value);previous=value
        if previous!=self.state:raise Hold('EVENT_CHECKPOINT_MISMATCH')
    def write(self,phase,new_id=None):
        if self.poisoned or threading.get_ident()!=self.owner:raise Hold('JOURNAL_OWNER_OR_IO_HOLD')
        sequence=(self.state['sequence'] if self.state else 0)+1
        if sequence>64:raise Hold('CHECKPOINT_LIMIT')
        value=dict(plan_sha256=self.plan['plan_sha256'],phase=phase,new_id=new_id,sequence=sequence)
        if self.handoff_binding is not None:value.update(self.handoff_binding)
        self.validate_transition(self.state,value)
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
        if self.cleanup_unproven:raise Hold('JOURNAL_CLEANUP_UNKNOWN')
        unproven_close=False
        for name in ('fd','lock','parent'):
            value=getattr(self,name,None)
            if value is None:continue
            # Transfer ownership away BEFORE close(). A close error does not
            # prove the integer still denotes our resource; it may already have
            # been consumed and recycled to an unrelated fd. Never retain or
            # retry the number after invoking close once.
            setattr(self,name,None)
            try:os.close(value)
            except BaseException:unproven_close=True
        if unproven_close:
            self.cleanup_unproven=True
            raise Hold('JOURNAL_CLEANUP_UNKNOWN')


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
    def __init__(self,journal,transport,*,execution_enabled=False,clock=time.time,handoff=None):
        if type(transport) is not OriginalTransport:raise Hold('ORIGINAL_TRANSPORT_REQUIRED')
        self.journal=journal;self.t=transport;self.enabled=execution_enabled;self.clock=clock;self.last=None
        self.handoff=handoff
        if journal.plan.get('handoff_mode')=='STOPPED_HANDOFF_V1':
            from scripts.community_preview_stopped_handoff import VerifiedHandoff
            if type(handoff) is not VerifiedHandoff or handoff.journal is not journal:raise Hold('VERIFIED_HANDOFF_OBJECT_REQUIRED')
        elif handoff is not None:raise Hold('LEGACY_RUNNING_PATH_REQUIRED')
    def guard(self,old_running=None):
        if self.journal.poisoned or threading.get_ident()!=self.journal.owner:raise Hold('JOURNAL_OWNER_OR_IO_HOLD')
        if self.enabled is not True:raise Hold('UPDATE_EXECUTION_DISABLED')
        if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=plan.HOST:raise Hold('EXACT_ROOT_HOST_REQUIRED')
        now=self.clock()
        if type(now) not in (int,float) or not math.isfinite(now) or self.last is not None and now<self.last:raise Hold('CLOCK_INVALID')
        self.last=now
        c=self.journal.plan['current']
        # A live recheck may refresh observed_at, never any protected identity.
        live=self.t.bindings()
        if type(live) is not dict or set(live)!=set(c):raise Hold('LIVE_BINDING_SHAPE')
        if any(type(live[k]) is not type(c[k]) for k in c):raise Hold('LIVE_BINDING_SHAPE')
        if any(live[k]!=c[k] for k in c if k not in ('observed_at','running')):raise Hold('PROTECTED_BINDING_CHANGED')
        if old_running is not None and live['running'] is not old_running:raise Hold('OLD_WRITER_PHASE_CHANGED')
        if not now-600<=live['observed_at']<=now+30:raise Hold('CURRENT_OBSERVATION_EXPIRED')
        if self.handoff is not None:self.handoff.check()
        return int(now)
    def hold(self,code,new_id=None):
        self.journal.write(HOLD_PHASE,new_id);raise Hold(code)
    def phase_check(self,intent,new_id):
        p=self.journal.plan;c=p['current'];old_running=intent=='OLD_STOP_INTENT'
        self.guard(old_running)
        if self.handoff is not None:self.handoff.pre_action(intent,new_id)
        self.t.inspect(c['container_id'],c['image_id'],old_running)
        if intent.startswith('RECOVERY_'):
            if not plan.exact_hex(new_id,64) or new_id!=self.journal.state['new_id']:raise Hold('EXACT_NEW_ID_REQUIRED')
            if intent=='RECOVERY_STOP_NEW_INTENT':
                v=original.inspect(new_id)
                if type(v.get('running')) is not bool:raise Hold('NEW_WRITER_UNKNOWN')
                original.validate(v,p['image']['image_id'],new_id,running=v['running'])
            else:self.t.inspect(new_id,p['image']['image_id'],False)
        if intent!='OLD_STOP_INTENT' and intent!='RECOVERY_STOP_NEW_INTENT':self.t.socket_absent()
        # The binding reader is live and phase-sensitive too; it cannot hide a
        # resurrected old writer behind the initial running=True snapshot.
        self.guard(old_running)
        self.t.inspect(c['container_id'],c['image_id'],old_running)
        if intent.startswith('RECOVERY_') and intent!='RECOVERY_STOP_NEW_INTENT':
            self.t.inspect(new_id,p['image']['image_id'],False)
    def action(self,intent,argv,*,new_id=None):
        p=self.journal.plan
        allowed={'OLD_STOP_INTENT':p['actions'][1]['argv'],'OLD_RENAME_INTENT':p['actions'][2]['argv'],
            'NEW_RUN_INTENT':p['actions'][3]['argv'],
            'RECOVERY_STOP_NEW_INTENT':plan.DOCKER+['stop','--time','10',new_id],
            'RECOVERY_RENAME_NEW_INTENT':plan.DOCKER+['rename',new_id,p['failed_name']],
            'RECOVERY_RESTORE_OLD_INTENT':p['rollback']['old_rename_argv'],
            'RECOVERY_START_OLD_INTENT':p['rollback']['old_start_argv']}
        if intent not in allowed or argv!=allowed[intent]:raise Hold('EXACT_STAGE_ACTION_REQUIRED')
        self.guard(intent=='OLD_STOP_INTENT');self.journal.write(intent,new_id)
        try:
            # Durable intent is not a permit: inspect the exact writer pair and
            # socket AFTER publishing it, immediately before original mutate.
            self.phase_check(intent,new_id)
            return self.t.mutate(argv)
        except BaseException:
            self.hold('STAGE_CHANGED_OR_MUTATION_UNKNOWN_NO_RETRY',new_id)
    def writer_pair(self,new_id,old_running,new_running):
        p=self.journal.plan;c=p['current']
        self.guard(old_running);self.t.inspect(c['container_id'],c['image_id'],old_running)
        self.t.inspect(new_id,p['image']['image_id'],new_running)
        self.guard(old_running);self.t.inspect(new_id,p['image']['image_id'],new_running)
    def run(self):
        self.guard(True);j=self.journal;p=j.plan;c=p['current'];image=p['image']['image_id']
        if j.state['phase']!='PREPARED':raise Hold('EXISTING_ATTEMPT_RECOVER_OR_INSPECT_ONLY')
        self.t.image_and_names_ready(p)
        self.t.inspect(c['container_id'],c['image_id'],True)
        self.action('OLD_STOP_INTENT',p['actions'][1]['argv']);self.t.inspect(c['container_id'],c['image_id'],False);self.t.socket_absent()
        j.write('OLD_STOPPED')
        return self.replace_and_verify()
    def run_stopped(self):
        if self.handoff is None:raise Hold('STOPPED_MODE_DEFAULT_OFF')
        self.guard(False);j=self.journal;p=j.plan;c=p['current']
        if j.state['phase']!='PREPARED':raise Hold('EXISTING_ATTEMPT_INSPECT_OR_RECOVER_ONLY')
        self.t.image_and_names_ready(p);self.t.inspect(c['container_id'],c['image_id'],False);self.t.socket_absent()
        self.handoff.check();j.write('STOPPED_HANDOFF_ACCEPTED')
        try:self.handoff.check()
        except BaseException:self.hold('HANDOFF_CHANGED_AFTER_ACCEPTANCE')
        return self.replace_and_verify()
    def replace_and_verify(self):
        j=self.journal;p=j.plan;c=p['current']
        self.action('OLD_RENAME_INTENT',p['actions'][2]['argv']);j.write('OLD_RETAINED')
        new_id=self.action('NEW_RUN_INTENT',p['actions'][3]['argv'])
        if not plan.exact_hex(new_id,64):j.write('HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT');raise Hold('NEW_ID_UNKNOWN')
        j.write('NEW_KNOWN',new_id)
        # Unknown inspection/clock/binding/transport failures never become a
        # rollback permit. A concrete completed nonmatching health report is the
        # only recoverable verification failure here; recovery still rechecks all.
        try:
            self.writer_pair(new_id,False,True)
            health=self.t.health();now=self.guard(False)
            self.writer_pair(new_id,False,True)
        except Exception:
            j.write('HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT',new_id);raise Hold('VERIFY_UNKNOWN') from None
        completed=(type(health) is dict and type(health.get('http_status')) is int
                   and health.get('url')==plan.URL and type(health.get('status')) is str
                   and health.get('scope')=='PROCESS_AND_DATABASE_CONNECTIVITY'
                   and health.get('production_acceptance') is False)
        stamped=(completed and type(health.get('runtime_source_sha')) is str
                 and plan.exact_hex(health['runtime_source_sha'],40)
                 and health.get('version_source')=='IMAGE_BUILD_STAMP'
                 and type(health.get('observed_at')) is int and now-600<=health['observed_at']<=now+30)
        if not completed or not stamped:
            j.write('HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT',new_id);raise Hold('HEALTH_EVIDENCE_UNKNOWN')
        if not plan.exact_health(health,p['source']['source_sha'],p['image']['oci_revision'],now):
            j.write('KNOWN_FAILURE',new_id);raise Hold('KNOWN_FAILURE_RECOVERY_REQUIRED')
        j.write('COMMITTED',new_id)
        try:self.writer_pair(new_id,False,True)
        except Exception:self.hold('COMMIT_PAIR_CHANGED',new_id)
        return dict(j.state)
    def recover(self):
        self.guard(False);j=self.journal;p=j.plan;c=p['current'];new_id=j.state.get('new_id')
        if j.state['phase']!='KNOWN_FAILURE' or not plan.exact_hex(new_id,64):raise Hold('KNOWN_NEW_RECEIPT_REQUIRED')
        value=original.inspect(new_id)
        if type(value.get('running')) is not bool:raise Hold('NEW_WRITER_UNKNOWN')
        original.validate(value,p['image']['image_id'],new_id,running=value['running'])
        if value['running']:self.action('RECOVERY_STOP_NEW_INTENT',plan.DOCKER+['stop','--time','10',new_id],new_id=new_id)
        self.t.inspect(new_id,p['image']['image_id'],False);self.t.socket_absent()
        self.action('RECOVERY_RENAME_NEW_INTENT',plan.DOCKER+['rename',new_id,p['failed_name']],new_id=new_id)
        self.action('RECOVERY_RESTORE_OLD_INTENT',p['rollback']['old_rename_argv'],new_id=new_id)
        self.action('RECOVERY_START_OLD_INTENT',p['rollback']['old_start_argv'],new_id=new_id)
        try:
            self.writer_pair(new_id,True,False)
            old_health=self.t.health();now=self.guard(True)  # time/identity AFTER the response
            if (type(old_health) is not dict or type(old_health.get('http_status')) is not int
                    or old_health['http_status']!=200 or old_health.get('url')!=plan.URL
                    or old_health.get('status')!='READY' or old_health.get('scope')!='PROCESS_AND_DATABASE_CONNECTIVITY'
                    or old_health.get('production_acceptance') is not False
                    or type(old_health.get('observed_at')) is not int
                    or not now-600<=old_health['observed_at']<=now+30):raise Hold('ROLLBACK_HEALTH_UNKNOWN')
            # Legacy rollback needs no new-source stamp; it DOES need a fresh
            # fixed response and another proof that the new writer remains off.
            self.writer_pair(new_id,True,False)
        except Exception:self.hold('ROLLBACK_HEALTH_OR_PAIR_UNKNOWN',new_id)
        j.write('ROLLED_BACK_PREVIEW_HOLD',new_id)
        try:self.writer_pair(new_id,True,False)
        except Exception:self.hold('ROLLBACK_FINAL_PAIR_CHANGED',new_id)
        return dict(j.state)
