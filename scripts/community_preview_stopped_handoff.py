"""Proposal only: fixed stopped B->C composition; default entry is disabled.
No stop/start/install/load/backup is performed by import or construction.
A record is not freeze proof: fresh source/tree/clone reads are mandatory.
"""
import fcntl
import hashlib
import io
import contextlib
import json
import os
import pwd
import select
import stat
import threading
import time
from scripts import community_preview_site_prepare as s
from scripts import community_preview_update_composition as c
from scripts import community_preview_update_checkpoint as u
from scripts import community_preview_release_plan as p

MODE='STOPPED_HANDOFF_V1'
CONTROL='/opt/xuanjun-community-preview/control-stopped-v1'
B_APPROVAL='/opt/xuanjun-community-preview/bc-b-approval.json'
B_RESUME_APPROVAL='/opt/xuanjun-community-preview/bc-b-resume-approval.json'
RESUME_FREEZE='/opt/xuanjun-community-preview/writer-freeze-resume-reference.json'
B_RESUME_STAGE_PERMIT='/opt/xuanjun-community-preview/site-prepare-resume-approval.json'
C_APPROVAL='/opt/xuanjun-community-preview/bc-c-approval.json'
C_RESUME_APPROVAL='/opt/xuanjun-community-preview/bc-c-resume-approval.json'
C_RESUME_PLAN=s.BACKUP+'/c-preconfirmation-resume-plan.json'
MANIFEST=CONTROL+'/manifest.json'
PROOF=s.BACKUP+'/stopped-handoff-v1.json'
C_ACTIONS=['STOPPED_HANDOFF_RENAME_RUN','KNOWN_FAILURE_SERIAL_RECOVERY','JOURNAL_WRITES']
CORRECTION_KIND='C_SUCCESSOR_INDEPENDENT_CORRECTION_V1'
CORRECTION_REISSUE_KIND='C_SUCCESSOR_INDEPENDENT_CORRECTION_REISSUE_V1'
PREPARED_REOPEN_KIND='C_SUCCESSOR_PREPARED_REOPEN_V1'
PREPARED_REOPEN_REISSUE_KIND='C_SUCCESSOR_PREPARED_REOPEN_REISSUE_V1'
CLONES=('restore-old','verify-f131','verify-downgrade')
A_ENTRY_SHA='48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55'

def need(ok,why):
    if not ok:raise u.Hold(why)
def raw(path,limit=65536):
    # Existing root/nofollow/full parent/identity/mode/nlink/size reader.
    return s.read(path,limit)
def document(path,limit=65536):
    b=raw(path,limit);v=s.exact_json(b)
    need(b==s.canonical(v),'CANONICAL_DOCUMENT_REQUIRED');return v,b
def window(v):
    t=c.now()
    need(type(v['issued_at']) is int and type(v['expires_at']) is int
         and v['issued_at']<=t<=v['expires_at']<=v['issued_at']+600,'APPROVAL_EXPIRED')
def attempt():
    return 'community-update-'+s.PRODUCT[:12]+'-'+s.OLD_ID[:12]+'-stopped-v1'
def paths():
    return {n:s.BACKUP+'/clone-'+n+'.json' for n in CLONES}
def b_records():
    names=['B-intent','snapshot-result','snapshot-permit','validate-clones-result','validate-clones-permit']
    return {name:u.JOURNAL_PARENT+'/'+attempt()+'-'+name+'.json' for name in names}
def resume_record_path():return u.JOURNAL_PARENT+'/'+attempt()+'-B-resume-admission.json'
def resume_probe_names():
    return tuple('xuanjun-community-preview-'+name+'-probe-f131' for name in CLONES)
def resume_reference(path,limit=65536):
    body=raw(path,limit);fd=open_private(path)
    try:
        meta=s.identity(os.fstat(fd))
        need(meta==s.identity(os.stat(path,follow_symlinks=False)) and raw(path,limit)==body,
             'B_RESUME_REFERENCE_REPLACED')
        return body,meta
    finally:os.close(fd)
def probe_names_absent():
    body=s.capture(s.DOCKER+['container','ls','--all','--format','{{.Names}}'])
    try:rows=body.decode('ascii').splitlines()
    except (UnicodeError,AttributeError):raise u.Hold('B_RESUME_PROBE_INVENTORY_UNKNOWN') from None
    need(len(rows)<=4096 and all(row and len(row)<=128 for row in rows),'B_RESUME_PROBE_INVENTORY_UNKNOWN')
    need(not set(resume_probe_names()).intersection(rows),'B_RESUME_PROBE_NAME_CONFLICT')
    return rows
def exists_private(path):
    parent=s.directory(os.path.dirname(path))
    try:
        try:os.stat(os.path.basename(path),dir_fd=parent,follow_symlinks=False);return True
        except FileNotFoundError:return False
    finally:os.close(parent)
def open_private(path):
    parent=s.directory(os.path.dirname(path))
    try:
        fd=os.open(os.path.basename(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        try:u.protected(fd);return fd
        except BaseException:os.close(fd);raise
    finally:os.close(parent)
def write_private(parent,name,value):
    # Original EXCL/checkpoint/fchown/fchmod/fsync implementation.
    s.create_file(parent,name,s.canonical(value))
def operator():
    c.root_host();a=pwd.getpwnam('admin')
    need(a.pw_uid>0 and os.environ.get('SUDO_USER')=='admin'
         and os.environ.get('SUDO_UID')==str(a.pw_uid)
         and os.environ.get('SUDO_GID')==str(a.pw_gid),'ORIGINAL_ADMIN_REQUIRED')
    f=os.open('/proc/'+str(os.getpid())+'/loginuid',os.O_RDONLY|os.O_NOFOLLOW)
    try:need(os.read(f,32).strip()==str(a.pw_uid).encode(),'KERNEL_LOGINUID_REQUIRED')
    finally:os.close(f)
    return a.pw_uid,a.pw_gid
def acknowledge(action,digest):
    fd=os.open('/dev/tty',os.O_RDWR|os.O_NOFOLLOW|os.O_NOCTTY)
    try:
        need(os.isatty(0) and os.isatty(1) and os.isatty(fd),'DIRECT_TTY_REQUIRED')
        line=('APPROVE_'+action+' '+digest).encode()
        os.write(fd,b'Exact separately approved action only; no automatic retry.\nType '+line+b' to continue: ')
        need(select.select([fd],[],[],120)[0]==[fd],'OWNER_CONFIRMATION_TIMEOUT')
        need(os.read(fd,257) in (line+b'\n',line+b'\r\n'),'EXACT_CONFIRMATION_REQUIRED')
    finally:os.close(fd)

def authorize_v2(session,stage,digest):
    """Exact A stage authority, rebound to the pinned V2 carrier source.

    The installed A entry remains immutable authority evidence; unlike A's own
    entrypoint, this function never pretends the V2 module __file__ is ENTRY.
    """
    c.root_host();need(stage in s.STAGES and p.exact_hex(digest,64),'STAGE_APPROVAL_REQUIRED')
    need(os.path.abspath(s.__file__)==CONTROL+'/scripts/community_preview_site_prepare.py','V2_SITE_PREPARE_SOURCE_REQUIRED')
    need(session.pins()==session.approved_stamp,'CARRIER_STAMP_CHANGED')
    need(s.sha(raw(s.ENTRY,131072))==A_ENTRY_SHA,'A_INSTALLED_ENTRY_CHANGED')
    permit_path=session.stage_permit_path
    permit_raw=raw(permit_path,16384);need(s.sha(permit_raw)==digest,'APPROVAL_CHANGED');v=s.exact_json(permit_raw)
    fields={'format','host','stage','entry_sha256','issued_at','expires_at','all_writers_frozen_evidence_sha256','snapshot_manifest_sha256'}
    need(type(v) is dict and set(v)==fields and type(v['format']) is int and v['format']==1
         and v['host']==p.HOST and v['stage']==stage and v['entry_sha256']==A_ENTRY_SHA,'EXACT_STAGE_SCOPE')
    for key in ('all_writers_frozen_evidence_sha256','snapshot_manifest_sha256'):
        need(v[key] is None or p.exact_hex(v[key],64),'EXACT_EVIDENCE_REFERENCE')
    if stage in ('install','image-load'):
        need(v['all_writers_frozen_evidence_sha256'] is None and v['snapshot_manifest_sha256'] is None,'UNRELATED_EVIDENCE_DENIED')
    if stage=='snapshot':
        need(v['snapshot_manifest_sha256'] is None and v['all_writers_frozen_evidence_sha256']==s.sha(session.freeze),
             'EXCLUSIVE_WRITER_FREEZE_PROOF_REQUIRED')
        session.freeze_live()
    if stage=='validate-clones':need(v['snapshot_manifest_sha256'] is not None,'REVIEWED_SNAPSHOT_DIGEST_REQUIRED')
    need(permit_raw==s.canonical(v) and raw(permit_path,16384)==permit_raw,'APPROVAL_CHANGED')
    need(s.sha(raw(s.ENTRY,131072))==A_ENTRY_SHA,'A_INSTALLED_ENTRY_CHANGED')
    now=c.now();need(type(v['issued_at']) is int and type(v['expires_at']) is int
        and v['issued_at']<=now<=v['expires_at']<=v['issued_at']+600,'STAGE_APPROVAL_EXPIRED')
    if stage=='snapshot':session.freeze_live()
    return v

def retire_permit(parent,name,identity,digest,path):
    try:
        current=os.stat(name,dir_fd=parent,follow_symlinks=False)
        need(s.identity(current)==identity,'ACTIVE_PERMIT_REPLACED')
        body=raw(path,16384);need(s.sha(body)==digest,'ACTIVE_PERMIT_CHANGED')
        os.unlink(name,dir_fd=parent);os.fsync(parent)
    except FileNotFoundError:return

class Session:
    """One process/thread and the SAME flock description spans B and C."""
    def __init__(self):
        self.parent=None;self.lease=None;self.entry=None;self.backup=None
        self.journal=None;self.old_checkpoint=None;self.old_clone=None;self.old_component=None
        self.owner=None;self.thread=threading.get_ident();self.last=None
        self.braw=None;self.craw=None;self.freeze=None;self.bdone=False;self.approved_stamp=None
        self.b_path=B_APPROVAL;self.freeze_path=s.FREEZE;self.stage_permit_path=s.PERMIT;self.resume_raw=None;self.resume_mode=False
        self.c_resume_plan_path=C_RESUME_PLAN;self.c_resume_approval_path=C_RESUME_APPROVAL
        self.successor_approval_sha256=None;self.successor_renewal_sha256=None;self.successor_recovery_sha256=None;self.successor_correction_sha256=None
        self.resume_history={};self.resume_absent=();self.resume_old_permit_absent=False
        self.prepared_reopen_path=None;self.prepared_reopen_raw=None
        self.started=time.monotonic();self.captured={};self.recovering=False;self.cleanup_unproven=False
    def acquire(self,recover=False):
        self.owner=operator();self.recovering=recover
        # Parent was installed by A; never mkdir/chmod it.
        self.parent=s.private_parent(u.JOURNAL_PARENT)
        self.lease=os.open('community-update.lock',os.O_RDWR|os.O_NOFOLLOW|(0 if recover else os.O_CREAT),0o600,dir_fd=self.parent)
        u.protected(self.lease);fcntl.flock(self.lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.entry=open_private(s.ENTRY);fcntl.flock(self.entry,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.old_checkpoint=s.checkpoint;self.old_clone=s.clone_run
        self.old_component=s._COMPONENT
        s._COMPONENT=c  # Exact same manifest-verified original readers, no fake Reader.
        def checkpoint():
            self.boundary()
            if s._ACTIVE is not None:authorize_v2(self,*s._ACTIVE)
        s.checkpoint=checkpoint
        def clone(name,image):
            self.stopped();v=self.old_clone(name,image);self.stopped()
            need(name in CLONES and name not in self.captured,'EXACT_SINGLE_CLONE_REQUIRED')
            row=dict(format=1,attempt=attempt(),name=name,image=image,
                     code_sha256=s.sha(s.CLONE_CODE.encode()),result=v)
            fd=s.private_parent(s.BACKUP)
            try:write_private(fd,'clone-'+name+'.json',row)
            finally:os.close(fd)
            self.captured[name]=row
            return v
        s.clone_run=clone
    def bind_resume_reference(self,path,limit=65536):
        body,meta=resume_reference(path,limit);self.resume_history[path]=(body,meta,limit);return body
    def resume_guard(self):
        if not self.resume_mode:return
        for path,(body,meta,limit) in self.resume_history.items():
            current,current_meta=resume_reference(path,limit)
            need(current==body and current_meta==meta,'B_RESUME_REFERENCE_REPLACED')
        for path in self.resume_absent:
            need(not exists_private(path),'B_PARTIAL_STATE_CONFLICT')
        if self.resume_old_permit_absent:
            need(not exists_private(s.PERMIT),'B_PARTIAL_STATE_CONFLICT')
    def resume_require_absent(self,paths):
        self.resume_guard()
        for path in paths:need(not exists_private(path),'B_PARTIAL_STATE_CONFLICT')
    def resume_stage_preflight(self,stage):
        if not self.resume_mode:return
        records=b_records()
        common=[C_APPROVAL,u.JOURNAL_PARENT+'/active-attempt.json',u.JOURNAL_PARENT+'/'+attempt()]
        if stage=='snapshot':
            paths=[records['snapshot-result'],records['snapshot-permit'],records['validate-clones-result'],
                   records['validate-clones-permit'],s.BACKUP,self.stage_permit_path]+common
        else:
            paths=[records['validate-clones-result'],records['validate-clones-permit'],self.stage_permit_path]+common
            paths += list(globals()['paths']().values())
            paths += [s.BACKUP+'/'+name for name in CLONES]
        self.resume_require_absent(paths)
        self.resume_absent=tuple(paths)
    def strict_prior_stage_permit(self,old_b,old_freeze,old_freeze_raw):
        if not exists_private(s.PERMIT):return None
        old_permit_raw=self.bind_resume_reference(s.PERMIT,16384)
        old_permit=s.exact_json(old_permit_raw)
        need(old_permit_raw==s.canonical(old_permit),'EXACT_PRIOR_STAGE_PERMIT_REQUIRED')
        fields={'format','host','stage','entry_sha256','issued_at','expires_at',
                'all_writers_frozen_evidence_sha256','snapshot_manifest_sha256'}
        valid=(set(old_permit)==fields and type(old_permit.get('format')) is int and old_permit.get('format')==1
            and old_permit.get('host')==p.HOST and old_permit.get('stage')=='snapshot'
            and old_permit.get('entry_sha256')==A_ENTRY_SHA
            and old_permit.get('all_writers_frozen_evidence_sha256')==s.sha(old_freeze_raw)
            and old_permit.get('snapshot_manifest_sha256') is None
            and type(old_permit.get('issued_at')) is int and type(old_permit.get('expires_at')) is int
            and old_b['issued_at']<=old_permit['issued_at']<=old_permit['expires_at']
            and old_permit['expires_at']<=old_permit['issued_at']+600
            and old_permit['expires_at']<=old_b['expires_at'] and old_permit['expires_at']<=old_freeze['expires_at'])
        need(valid,'EXACT_PRIOR_STAGE_PERMIT_REQUIRED')
        self.resume_guard()
        return s.sha(old_permit_raw)
    def configure_resumed_recovery(self,proof):
        evidence=proof.get('evidence') if type(proof) is dict else None
        rows=evidence.get('b_records') if type(evidence) is dict else None
        if type(rows) is not dict or 'B-resume-admission' not in rows:return False
        self.resume_mode=True;self.c_preconfirm_mode=(proof.get('approval_kind')=='C_RESUME_APPROVAL');self.b_path=B_RESUME_APPROVAL;self.freeze_path=RESUME_FREEZE;self.stage_permit_path=B_RESUME_STAGE_PERMIT
        self.resume_raw=self.bind_resume_reference(resume_record_path())
        need(s.sha(self.resume_raw)==rows['B-resume-admission'],'B_RESUME_PROOF_BINDING_CHANGED')
        resume=s.exact_json(self.resume_raw)
        need(type(resume) is dict and resume.get('attempt')==attempt() and resume.get('mode')==MODE,
             'B_RESUME_PROOF_BINDING_CHANGED')
        intent_raw=self.bind_resume_reference(b_records()['B-intent'])
        old_braw=self.bind_resume_reference(B_APPROVAL);old_freeze_raw=self.bind_resume_reference(s.FREEZE,16384)
        self.b,self.braw=document(self.b_path);self.bind_resume_reference(self.b_path)
        self.freeze=self.bind_resume_reference(self.freeze_path,16384)
        self.resume_old_permit_absent=resume.get('old_stage_permit_sha256') is None
        if not self.resume_old_permit_absent:self.bind_resume_reference(s.PERMIT,16384)
        self.resume_guard()
        need(resume.get('old_b_intent_sha256')==s.sha(intent_raw)
             and resume.get('old_b_approval_sha256')==s.sha(old_braw)
             and resume.get('old_freeze_sha256')==s.sha(old_freeze_raw)
             and resume.get('resume_approval_sha256')==s.sha(self.braw)
             and resume.get('resume_freeze_sha256')==s.sha(self.freeze),
             'B_RESUME_PROOF_BINDING_CHANGED')
        if resume.get('old_stage_permit_sha256') is not None:
            need(resume['old_stage_permit_sha256']==s.sha(raw(s.PERMIT,16384)),'B_RESUME_PROOF_BINDING_CHANGED')
        historical_carrier=self.b['carrier_manifest_sha256']
        need(historical_carrier==resume.get('carrier_manifest_sha256'),'B_HISTORICAL_CARRIER_BINDING_CHANGED')
        if self.c_preconfirm_mode:
            self._restore_c_resume_paths(proof)
            self.approved_stamp=self.pins()
        else:
            self.approved_stamp=historical_carrier
            need(self.approved_stamp==self.pins(),'B_SOURCE_BINDING_CHANGED')
        self.resume_guard()
        return True
    def configure_resumed_b_context(self):
        """Bind the existing completed B evidence without running either B stage."""
        self.resume_mode=True
        self.c_preconfirm_mode=True
        self.b_path=B_RESUME_APPROVAL;self.freeze_path=RESUME_FREEZE
        self.stage_permit_path=B_RESUME_STAGE_PERMIT
        self.resume_raw=self.bind_resume_reference(resume_record_path())
        resume=s.exact_json(self.resume_raw)
        need(self.resume_raw==s.canonical(resume)
             and set(resume)=={'format','mode','attempt','carrier_manifest_sha256',
                'old_b_intent_sha256','old_b_approval_sha256','old_freeze_sha256',
                'old_stage_permit_sha256','resume_approval_sha256','resume_freeze_sha256','actions'}
             and type(resume['format']) is int and resume['format']==1
             and resume['mode']==MODE and resume['attempt']==attempt()
             and resume['actions']==['RESUME_SNAPSHOT','THREE_ISOLATED_CLONES'],
             'B_RESUME_RECORD_INVALID')
        intent_raw=self.bind_resume_reference(b_records()['B-intent'])
        old_braw=self.bind_resume_reference(B_APPROVAL)
        old_freeze_raw=self.bind_resume_reference(s.FREEZE,16384)
        old_b=s.exact_json(old_braw);old_freeze=s.exact_json(old_freeze_raw)
        need(old_freeze_raw==s.canonical(old_freeze)
             and set(old_freeze)=={'format','host','old_id','old_image','roots','issued_at','expires_at',
                 'all_writers_frozen','owner_review_reference_sha256'}
             and type(old_freeze['format']) is int and old_freeze['format']==1
             and old_freeze['host']==p.HOST and old_freeze['old_id']==s.OLD_ID
             and old_freeze['old_image']==s.OLD_IMAGE
             and old_freeze['roots']==[s.DATA+'/data',s.DATA+'/config']
             and old_freeze['all_writers_frozen'] is True
             and p.exact_hex(old_freeze['owner_review_reference_sha256'],64)
             and type(old_freeze['issued_at']) is int and type(old_freeze['expires_at']) is int
             and old_freeze['issued_at']<=old_freeze['expires_at']<=old_freeze['issued_at']+600,
             'EXACT_PRIOR_FREEZE_REQUIRED')
        need(resume['old_b_intent_sha256']==s.sha(intent_raw)
             and resume['old_b_approval_sha256']==s.sha(old_braw)
             and resume['old_freeze_sha256']==s.sha(old_freeze_raw),
             'B_RESUME_PROOF_BINDING_CHANGED')
        need(old_braw==s.canonical(old_b)
             and set(old_b)=={'format','host','mode','attempt','carrier_manifest_sha256',
                'issued_at','expires_at','freeze_sha256','actions'}
             and old_b['host']==p.HOST and old_b['mode']==MODE
             and old_b['attempt']==attempt()
             and old_b['actions']==['SNAPSHOT','THREE_ISOLATED_CLONES']
             and old_b['freeze_sha256']==s.sha(old_freeze_raw)
             and p.exact_hex(old_b['carrier_manifest_sha256'],64)
             and type(old_b['issued_at']) is int and type(old_b['expires_at']) is int
             and old_b['issued_at']<=old_b['expires_at']<=old_b['issued_at']+600
             and intent_raw==s.canonical(s.exact_json(intent_raw))
             and s.exact_json(intent_raw)==dict(format=1,mode=MODE,attempt=attempt(),
                 approval_sha256=s.sha(old_braw),freeze_sha256=s.sha(old_freeze_raw)),
             'PRIOR_B_EVIDENCE_MISMATCH')
        self.braw=self.bind_resume_reference(self.b_path)
        self.b=s.exact_json(self.braw)
        # Historical B-resume authority is evidence only; preserve its original
        # bounded lifetime, but do not reuse it as current C permission.
        need(type(self.b.get('issued_at')) is int and type(self.b.get('expires_at')) is int
             and self.b['issued_at']<=self.b['expires_at']<=self.b['issued_at']+600,
             'HISTORICAL_B_RESUME_AUTHORITY_INVALID')
        need(self.braw==s.canonical(self.b)
             and set(self.b)=={'format','host','mode','attempt','carrier_manifest_sha256',
                'issued_at','expires_at','old_b_intent_sha256','old_b_approval_sha256',
                'old_freeze_sha256','old_stage_permit_sha256','resume_freeze_sha256','actions'}
             and type(self.b['format']) is int and self.b['format']==1
             and self.b['host']==p.HOST and self.b['mode']==MODE and self.b['attempt']==attempt()
             and self.b['actions']==['RESUME_SNAPSHOT','THREE_ISOLATED_CLONES']
             and self.b['old_b_intent_sha256']==s.sha(intent_raw)
             and self.b['old_b_approval_sha256']==s.sha(old_braw)
             and self.b['old_freeze_sha256']==s.sha(old_freeze_raw)
             and self.b['old_stage_permit_sha256']==resume['old_stage_permit_sha256'],
             'EXACT_B_RESUME_APPROVAL_REQUIRED')
        self.freeze=self.bind_resume_reference(self.freeze_path,16384)
        need(self.b['resume_freeze_sha256']==s.sha(self.freeze)
             and resume['resume_approval_sha256']==s.sha(self.braw)
             and resume['resume_freeze_sha256']==s.sha(self.freeze),
             'B_RESUME_EVIDENCE_BINDING_CHANGED')
        self.resume_old_permit_absent=resume['old_stage_permit_sha256'] is None
        prior_permit_sha=self.strict_prior_stage_permit(old_b,old_freeze,old_freeze_raw)
        need(prior_permit_sha==resume['old_stage_permit_sha256'],
             'B_RESUME_PROOF_BINDING_CHANGED')
        historical_carrier=self.b['carrier_manifest_sha256']
        need(historical_carrier==resume['carrier_manifest_sha256'],
             'B_HISTORICAL_CARRIER_BINDING_CHANGED')
        # B's completed results stay bound to the historical carrier. The
        # current caller/modules are separately verified by pins() for C.
        self.approved_stamp=self.pins()
        self.resume_absent=(u.JOURNAL_PARENT+'/active-attempt.json',u.JOURNAL_PARENT+'/'+attempt())
        # The existing C approval is expected input for this recovery, not an
        # absence constraint. All C side-effect/journal markers remain absent.
        self.resume_absent=tuple(path for path in self.resume_absent if path!=C_APPROVAL)
        self.freeze_live()
        self.resume_guard()
        return resume

    def _c_resume_approval(self,candidate):
        approval_path=self.c_resume_approval_path
        if approval_path in self.resume_history:
            self.resume_guard()
            bound,meta,limit=self.resume_history[approval_path]
        else:
            bound=self.bind_resume_reference(approval_path,16384)
        a,b=document(approval_path)
        need(bound==b,'C_RESUME_APPROVAL_REPLACED')
        successor='predecessor_plan_sha256' in candidate
        renewal='successor-renewal-' in os.path.basename(approval_path)
        recovery='successor-recovery-' in os.path.basename(approval_path)
        reissue='successor-independent-correction-reissue-' in os.path.basename(approval_path)
        correction='successor-independent-correction-' in os.path.basename(approval_path) and not reissue
        if reissue:
            expected={'format','kind','host','mode','attempt','carrier_manifest_sha256',
                'plan_sha256','predecessor_plan_sha256','predecessor_plan_record_sha256',
                'predecessor_approval_sha256','successor_plan_record_sha256',
                'successor_approval_sha256','successor_renewal_sha256',
                'successor_recovery_sha256','successor_correction_sha256',
                'issued_at','expires_at','actions'}
            need(set(a)==expected and type(a['format']) is int and a['format']==1
                 and a['kind']==CORRECTION_REISSUE_KIND and a['host']==p.HOST and a['mode']==MODE
                 and a['attempt']==attempt() and a['carrier_manifest_sha256']==self.approved_stamp==self.pins()
                 and a['plan_sha256']==candidate['plan_sha256']
                 and a['predecessor_plan_sha256']==candidate['predecessor_plan_sha256']
                 and a['predecessor_plan_record_sha256']==candidate['predecessor_plan_record_sha256']
                 and a['predecessor_approval_sha256']==candidate['predecessor_approval_sha256']
                 and a['successor_plan_record_sha256']==s.sha(raw(self.c_resume_plan_path,4*1024*1024))
                 and a['successor_approval_sha256']==self.successor_approval_sha256
                 and a['successor_renewal_sha256']==self.successor_renewal_sha256
                 and a['successor_recovery_sha256']==self.successor_recovery_sha256
                 and a['successor_correction_sha256']==self.successor_correction_sha256
                 and a['actions']==C_ACTIONS,'EXACT_C_INDEPENDENT_CORRECTION_REISSUE_REQUIRED')
            window(a);self.craw=b;return a
        if correction:
            expected={'format','kind','host','mode','attempt','carrier_manifest_sha256',
                'plan_sha256','predecessor_plan_sha256','predecessor_plan_record_sha256',
                'predecessor_approval_sha256','successor_plan_record_sha256',
                'successor_approval_sha256','successor_renewal_sha256',
                'successor_recovery_sha256','issued_at','expires_at','actions'}
            need(set(a)==expected and type(a['format']) is int and a['format']==1
                 and a['kind']==CORRECTION_KIND and a['host']==p.HOST and a['mode']==MODE
                 and a['attempt']==attempt() and a['carrier_manifest_sha256']==self.approved_stamp==self.pins()
                 and a['plan_sha256']==candidate['plan_sha256']
                 and a['predecessor_plan_sha256']==candidate['predecessor_plan_sha256']
                 and a['predecessor_plan_record_sha256']==candidate['predecessor_plan_record_sha256']
                 and a['predecessor_approval_sha256']==candidate['predecessor_approval_sha256']
                 and a['successor_plan_record_sha256']==s.sha(raw(self.c_resume_plan_path,4*1024*1024))
                 and a['successor_approval_sha256']==self.successor_approval_sha256
                 and a['successor_renewal_sha256']==self.successor_renewal_sha256
                 and a['successor_recovery_sha256']==self.successor_recovery_sha256
                 and a['actions']==C_ACTIONS,'EXACT_C_INDEPENDENT_CORRECTION_REQUIRED')
            window(a);self.craw=b;return a
        expected={'format','host','mode','attempt','carrier_manifest_sha256',
                  'plan_sha256','issued_at','expires_at','actions'}
        if successor:expected|={'predecessor_plan_sha256','predecessor_approval_sha256'}
        if renewal or recovery:expected|={'successor_plan_record_sha256','successor_approval_sha256'}
        need(set(a)==expected
             and type(a['format']) is int and a['format']==(4 if recovery else (3 if renewal else (2 if successor else 1)))
             and a['host']==p.HOST and a['mode']==MODE and a['attempt']==attempt()
             and a['carrier_manifest_sha256']==self.approved_stamp==self.pins()
             and a['plan_sha256']==candidate['plan_sha256']
             and (not successor or (a['predecessor_plan_sha256']==candidate['predecessor_plan_sha256']
                  and a['predecessor_approval_sha256']==candidate['predecessor_approval_sha256']))
             and (not (renewal or recovery) or (a['successor_plan_record_sha256']==s.sha(raw(self.c_resume_plan_path,4*1024*1024))
                  and a['successor_approval_sha256']==self.successor_approval_sha256))
             and a['actions']==C_ACTIONS,'EXACT_C_RESUME_APPROVAL_REQUIRED')
        window(a);self.craw=b;return a

    @staticmethod
    def _without_observed_at(value):
        if type(value) is dict:
            return {k:Session._without_observed_at(v) for k,v in value.items() if k not in ('observed_at','plan_sha256')}
        if type(value) is list:return [Session._without_observed_at(v) for v in value]
        return value

    # Expired authority renewal stays on the original B-resume/C-preconfirmation lane.
    def _successor_paths(self,predecessor_plan_sha):
        need(p.exact_hex(predecessor_plan_sha,64),'PREDECESSOR_PLAN_SHA_REQUIRED')
        suffix=predecessor_plan_sha[:16]
        return (s.BACKUP+'/c-preconfirmation-resume-plan-successor-'+suffix+'.json',
                s.BASE+'/bc-c-resume-approval-successor-'+suffix+'.json')

    def _successor_renewal_path(self,successor_plan_sha):
        need(p.exact_hex(successor_plan_sha,64),'SUCCESSOR_PLAN_SHA_REQUIRED')
        return s.BASE+'/bc-c-resume-approval-successor-renewal-'+successor_plan_sha[:16]+'.json'

    def _successor_recovery_path(self,renewal_sha):
        need(p.exact_hex(renewal_sha,64),'SUCCESSOR_RENEWAL_SHA_REQUIRED')
        return s.BASE+'/bc-c-resume-approval-successor-recovery-'+renewal_sha[:16]+'.json'

    def _successor_correction_path(self,recovery_sha):
        need(p.exact_hex(recovery_sha,64),'SUCCESSOR_RECOVERY_SHA_REQUIRED')
        return s.BASE+'/bc-c-resume-approval-successor-independent-correction-'+recovery_sha[:16]+'.json'

    def _successor_correction_reissue_path(self,correction_sha):
        need(p.exact_hex(correction_sha,64),'SUCCESSOR_CORRECTION_SHA_REQUIRED')
        return s.BASE+'/bc-c-resume-approval-successor-independent-correction-reissue-'+correction_sha[:16]+'.json'

    def _prepared_reopen_path(self,proof_sha):
        need(p.exact_hex(proof_sha,64),'PREPARED_PROOF_SHA_REQUIRED')
        return s.BASE+'/bc-c-resume-approval-successor-prepared-reopen-'+proof_sha[:16]+'.json'

    def _prepared_reopen_reissue_path(self,prior_sha):
        need(p.exact_hex(prior_sha,64),'PREPARED_REOPEN_SHA_REQUIRED')
        return s.BASE+'/bc-c-resume-approval-successor-prepared-reopen-reissue-'+prior_sha[:16]+'.json'

    def _prepared_reopen_approval(self,proof,phase='PREPARED'):
        proof_raw=raw(PROOF,4*1024*1024);proof_sha=s.sha(proof_raw)
        need(s.exact_json(proof_raw)==proof,'PREPARED_PROOF_CHANGED')
        active_path=u.JOURNAL_PARENT+'/active-attempt.json'
        attempt_path=u.JOURNAL_PARENT+'/'+proof['plan']['attempt']
        checkpoint_path=attempt_path+'/checkpoint.json';event_path=attempt_path+'/event-000001.json'
        active=raw(active_path,16384);checkpoint=raw(checkpoint_path,16384);event=raw(event_path,16384)
        prepared=s.exact_json(event);state=s.exact_json(checkpoint)
        need(prepared==dict(approval_sha256=proof['approval_sha256'],
             handoff_sha256=prepared.get('handoff_sha256'),new_id=None,
             phase='PREPARED',plan_sha256=proof['plan']['plan_sha256'],sequence=1),
             'EXACT_PREPARED_CHECKPOINT_REQUIRED')
        need(phase in ('PREPARED','KNOWN_FAILURE') and state.get('phase')==phase,
             'EXACT_PREPARED_REOPEN_PHASE_REQUIRED')
        path=self._prepared_reopen_path(proof_sha);approval,body=document(path,16384)
        expected={'format','kind','host','mode','attempt','carrier_manifest_sha256','plan_sha256',
            'proof_sha256','prior_approval_sha256','active_attempt_sha256','prepared_event_sha256',
            'issued_at','expires_at','actions'}
        need(set(approval)==expected and type(approval['format']) is int and approval['format']==1
             and approval['kind']==PREPARED_REOPEN_KIND and approval['host']==p.HOST
             and approval['mode']==MODE and approval['attempt']==attempt()
             and p.exact_hex(approval['carrier_manifest_sha256'],64)
             and approval['plan_sha256']==proof['plan']['plan_sha256']
             and approval['proof_sha256']==proof_sha
             and approval['prior_approval_sha256']==proof['approval_sha256']
             and approval['active_attempt_sha256']==s.sha(active)
             and approval['prepared_event_sha256']==s.sha(event)
             and approval['actions']==['REOPEN_EXACT_PREPARED_SAME_ATTEMPT','KNOWN_FAILURE_SERIAL_RECOVERY'],
             'EXACT_C_PREPARED_REOPEN_APPROVAL_REQUIRED')
        # These preserved files are immutable scope evidence, not a renewed
        # execution permit.  Live execution authority is the exact TTY gate in
        # reopen_prepared(); therefore elapsed time must not force another
        # permit file for this already-PREPARED same attempt.  Expiry remains
        # recorded and checked as history; it is never rewritten or extended.
        now=c.now();current=self.approved_stamp==self.pins()
        if approval['carrier_manifest_sha256']==self.approved_stamp:
            need(type(approval['issued_at']) is int and type(approval['expires_at']) is int
                 and approval['issued_at']<=approval['expires_at']<=approval['issued_at']+600
                 and now>approval['expires_at'],'PREPARED_REOPEN_EVIDENCE_NOT_HISTORICAL')
        else:
            need(type(approval['issued_at']) is int and type(approval['expires_at']) is int
                 and approval['issued_at']<=approval['expires_at']<=approval['issued_at']+600
                 and now>approval['expires_at'],'PREPARED_REOPEN_NOT_EXPIRED')
            prior_sha=s.sha(body);path=self._prepared_reopen_reissue_path(prior_sha)
            approval,body=document(path,16384)
            expected=expected|{'prior_prepared_reopen_sha256'}
            need(set(approval)==expected and type(approval['format']) is int and approval['format']==1
                 and approval['kind']==PREPARED_REOPEN_REISSUE_KIND and approval['host']==p.HOST
                 and approval['mode']==MODE and approval['attempt']==attempt()
                 # A preserved reissue records the carrier that was current
                 # when it was issued.  A later, integrity-checked carrier
                 # update must not rewrite that history or turn its elapsed
                 # window into a new execution gate.  pins()/boundary() bind
                 # the live carrier independently at every action boundary.
                 and p.exact_hex(approval['carrier_manifest_sha256'],64)
                 and approval['plan_sha256']==proof['plan']['plan_sha256']
                 and approval['proof_sha256']==proof_sha
                 and approval['prior_approval_sha256']==proof['approval_sha256']
                 and approval['prior_prepared_reopen_sha256']==prior_sha
                 and approval['active_attempt_sha256']==s.sha(active)
                 and approval['prepared_event_sha256']==s.sha(event)
                 and approval['actions']==['REOPEN_EXACT_PREPARED_SAME_ATTEMPT','KNOWN_FAILURE_SERIAL_RECOVERY'],
                 'EXACT_C_PREPARED_REOPEN_REISSUE_REQUIRED')
            need(type(approval['issued_at']) is int and type(approval['expires_at']) is int
                 and approval['issued_at']<=approval['expires_at']<=approval['issued_at']+600
                 and now>approval['expires_at'],'PREPARED_REOPEN_REISSUE_NOT_HISTORICAL')
        need(current,'CARRIER_STAMP_CHANGED')
        self.prepared_reopen_path=path;self.prepared_reopen_raw=body
        return approval

    def _restore_c_resume_paths(self,proof):
        """Rebuild the exact dynamic plan/approval lane from durable proof."""
        candidate=proof.get('plan') if type(proof) is dict else None
        approval_path=proof.get('approval_path') if type(proof) is dict else None
        need(type(candidate) is dict and type(approval_path) is str,
             'C_RESUME_PROOF_APPROVAL_PATH_REQUIRED')
        if 'predecessor_plan_sha256' not in candidate:
            need(approval_path==C_RESUME_APPROVAL,'C_RESUME_PROOF_APPROVAL_PATH_INVALID')
            self.c_resume_plan_path=C_RESUME_PLAN
            self.c_resume_approval_path=C_RESUME_APPROVAL
            return
        plan_path,successor_path=self._successor_paths(candidate['predecessor_plan_sha256'])
        need(exists_private(plan_path),'C_SUCCESSOR_PLAN_REQUIRED_FOR_RECOVERY')
        plan_record,plan_raw=document(plan_path,4*1024*1024)
        need(plan_record.get('plan')==candidate
             and plan_record.get('plan_sha256')==candidate.get('plan_sha256'),
             'C_SUCCESSOR_PLAN_CHANGED_FOR_RECOVERY')
        allowed=[successor_path];renewal_path=None;recovery_path=None
        if exists_private(successor_path):
            successor_raw=raw(successor_path,16384)
            renewal_path=self._successor_renewal_path(candidate['plan_sha256'])
            allowed.append(renewal_path)
            if exists_private(renewal_path):
                renewal_raw=raw(renewal_path,16384)
                recovery_path=self._successor_recovery_path(s.sha(renewal_raw));allowed.append(recovery_path)
                if exists_private(recovery_path):
                    recovery_raw=raw(recovery_path,16384)
                    correction_path=self._successor_correction_path(s.sha(recovery_raw));allowed.append(correction_path)
                    if exists_private(correction_path):
                        correction_raw=raw(correction_path,16384)
                        allowed.append(self._successor_correction_reissue_path(s.sha(correction_raw)))
        need(approval_path in allowed,'C_RESUME_PROOF_APPROVAL_PATH_INVALID')
        need(exists_private(approval_path)
             and s.sha(raw(approval_path,16384))==proof.get('approval_sha256'),
             'C_RESUME_PROOF_APPROVAL_REPLACED')
        self.c_resume_plan_path=plan_path
        self.c_resume_approval_path=approval_path
        self.successor_approval_sha256=s.sha(successor_raw)
        if approval_path==renewal_path:self.successor_approval_sha256=s.sha(successor_raw)
        elif approval_path==recovery_path:
            self.successor_approval_sha256=s.sha(renewal_raw)
        elif approval_path not in (successor_path,renewal_path):
            self.successor_approval_sha256=s.sha(successor_raw)
            self.successor_renewal_sha256=s.sha(renewal_raw)
            self.successor_recovery_sha256=s.sha(recovery_raw)
            if approval_path!=correction_path:
                self.successor_correction_sha256=s.sha(correction_raw)

    @staticmethod
    def _successor_base(value):
        value=Session._without_observed_at(value)
        return {k:v for k,v in value.items() if k not in (
            'carrier_manifest_sha256','predecessor_plan_sha256','predecessor_plan_record_sha256',
            'predecessor_approval_sha256')}

    def _expired_successor_approval(self,path,successor,successor_raw,now):
        approval,approval_raw=document(path,16384)
        expected={'format','host','mode','attempt','carrier_manifest_sha256','plan_sha256',
                  'predecessor_plan_sha256','predecessor_approval_sha256','issued_at','expires_at','actions'}
        need(set(approval)==expected and type(approval['format']) is int and approval['format']==2
             and approval['host']==p.HOST and approval['mode']==MODE and approval['attempt']==attempt()
             and approval['carrier_manifest_sha256']==successor['carrier_manifest_sha256']
             and approval['plan_sha256']==successor['plan_sha256']
             and approval['predecessor_plan_sha256']==successor['predecessor_plan_sha256']
             and approval['predecessor_approval_sha256']==successor['predecessor_approval_sha256']
             and approval['actions']==C_ACTIONS
             and type(approval['issued_at']) is int and type(approval['expires_at']) is int
             and approval['issued_at']<=approval['expires_at']<=approval['issued_at']+600
             and now>approval['expires_at'] and successor_raw==raw(self.c_resume_plan_path,4*1024*1024),
             'C_SUCCESSOR_RENEWAL_PREDECESSOR_INVALID')
        return approval_raw

    def _expired_successor_renewal(self,path,successor,successor_raw,prior_sha,now):
        approval,approval_raw=document(path,16384)
        expected={'format','host','mode','attempt','carrier_manifest_sha256','plan_sha256',
                  'predecessor_plan_sha256','predecessor_approval_sha256','issued_at','expires_at',
                  'actions','successor_plan_record_sha256','successor_approval_sha256'}
        need(set(approval)==expected and type(approval['format']) is int and approval['format']==3
             and approval['host']==p.HOST and approval['mode']==MODE and approval['attempt']==attempt()
             and approval['plan_sha256']==successor['plan_sha256']
             and approval['predecessor_plan_sha256']==successor['predecessor_plan_sha256']
             and approval['predecessor_approval_sha256']==successor['predecessor_approval_sha256']
             and approval['successor_plan_record_sha256']==s.sha(successor_raw)
             and approval['successor_approval_sha256']==prior_sha
             and approval['actions']==C_ACTIONS
             and type(approval['issued_at']) is int and type(approval['expires_at']) is int
             and approval['issued_at']<=approval['expires_at']<=approval['issued_at']+600
             and now>approval['expires_at'],'C_SUCCESSOR_RECOVERY_PREDECESSOR_INVALID')
        return approval_raw

    def _expired_successor_recovery(self,path,successor,successor_raw,successor_sha,renewal_sha,now):
        approval,approval_raw=document(path,16384)
        expected={'format','host','mode','attempt','carrier_manifest_sha256','plan_sha256',
                  'predecessor_plan_sha256','predecessor_approval_sha256','issued_at','expires_at',
                  'actions','successor_plan_record_sha256','successor_approval_sha256'}
        need(set(approval)==expected and type(approval['format']) is int and approval['format']==4
             and approval['host']==p.HOST and approval['mode']==MODE and approval['attempt']==attempt()
             and approval['plan_sha256']==successor['plan_sha256']
             and approval['predecessor_plan_sha256']==successor['predecessor_plan_sha256']
             and approval['predecessor_approval_sha256']==successor['predecessor_approval_sha256']
             and approval['successor_plan_record_sha256']==s.sha(successor_raw)
             and approval['successor_approval_sha256']==renewal_sha and successor_sha==self.successor_approval_sha256
             and approval['actions']==C_ACTIONS
             and type(approval['issued_at']) is int and type(approval['expires_at']) is int
             and approval['issued_at']<=approval['expires_at']<=approval['issued_at']+600
             and now>approval['expires_at'],'C_INDEPENDENT_CORRECTION_PREDECESSOR_INVALID')
        return approval_raw

    def _expired_successor_correction(self,path,successor,successor_raw,successor_sha,
                                      renewal_sha,recovery_sha,now):
        approval,approval_raw=document(path,16384)
        expected={'format','kind','host','mode','attempt','carrier_manifest_sha256',
                  'plan_sha256','predecessor_plan_sha256','predecessor_plan_record_sha256',
                  'predecessor_approval_sha256','successor_plan_record_sha256',
                  'successor_approval_sha256','successor_renewal_sha256',
                  'successor_recovery_sha256','issued_at','expires_at','actions'}
        need(set(approval)==expected and type(approval['format']) is int and approval['format']==1
             and approval['kind']==CORRECTION_KIND and approval['host']==p.HOST
             and approval['mode']==MODE and approval['attempt']==attempt()
             and approval['plan_sha256']==successor['plan_sha256']
             and approval['predecessor_plan_sha256']==successor['predecessor_plan_sha256']
             and approval['predecessor_plan_record_sha256']==successor['predecessor_plan_record_sha256']
             and approval['predecessor_approval_sha256']==successor['predecessor_approval_sha256']
             and approval['successor_plan_record_sha256']==s.sha(successor_raw)
             and approval['successor_approval_sha256']==successor_sha
             and approval['successor_renewal_sha256']==renewal_sha
             and approval['successor_recovery_sha256']==recovery_sha
             and approval['actions']==C_ACTIONS
             and type(approval['issued_at']) is int and type(approval['expires_at']) is int
             and approval['issued_at']<=approval['expires_at']<=approval['issued_at']+600
             and now>approval['expires_at'],'C_INDEPENDENT_CORRECTION_REISSUE_PREDECESSOR_INVALID')
        return approval_raw

    def _fixed_c_resume_plan(self,candidate,semantic):
        stable_semantic=self._without_observed_at(semantic)
        evidence_sha=s.sha(s.canonical(stable_semantic))
        now=c.now()
        if exists_private(C_RESUME_PLAN):
            saved,saved_raw=document(C_RESUME_PLAN,4*1024*1024)
            base_ok=(set(saved)=={'format','host','mode','attempt','carrier_manifest_sha256',
                    'evidence_sha256','plan','plan_sha256','plan_document_sha256','issued_at','expires_at'}
                 and type(saved['format']) is int and saved['format']==1
                 and saved['host']==p.HOST and saved['mode']==MODE and saved['attempt']==attempt()
                 and p.exact_hex(saved['carrier_manifest_sha256'],64)
                 and type(saved['plan']) is dict and saved['plan'].get('attempt')==attempt()
                 and saved['plan_sha256']==saved['plan'].get('plan_sha256')
                 and saved['plan_document_sha256']==s.sha(s.canonical(saved['plan']))
                 and type(saved['issued_at']) is int and type(saved['expires_at']) is int
                 and saved['issued_at']<=saved['expires_at']<=saved['issued_at']+600)
            need(base_ok,'C_RESUME_PLAN_RECORD_INVALID')
            if now<=saved['expires_at']:
                need(saved['carrier_manifest_sha256']==self.approved_stamp==self.pins(),
                     'C_RESUME_PLAN_CARRIER_CHANGED')
                need(saved['evidence_sha256']==evidence_sha,'C_RESUME_PLAN_EVIDENCE_CHANGED')
                need(self._without_observed_at(saved['plan'])==
                     self._without_observed_at(candidate),'C_RESUME_PLAN_EVIDENCE_CHANGED')
                candidate=saved['plan']
                self.c_resume_plan_path=C_RESUME_PLAN
                self.c_resume_approval_path=C_RESUME_APPROVAL
            else:
                # Expired successor is allowed only before any C execution trace; predecessor carrier remains historical.
                proof_path=PROOF;active_path=u.JOURNAL_PARENT+'/active-attempt.json'
                attempt_path=u.JOURNAL_PARENT+'/'+attempt()
                # The fixed attempt path is a whole-tree fence: if it exists at all,
                # empty or not, checkpoint/event/unknown contents are already forbidden.
                for path in (proof_path,active_path,attempt_path):
                    need(not exists_private(path),'C_SUCCESSOR_EXECUTION_TRACE_PRESENT')
                need(exists_private(C_RESUME_APPROVAL),'C_SUCCESSOR_PREDECESSOR_APPROVAL_REQUIRED')
                old_approval,old_approval_raw=document(C_RESUME_APPROVAL,16384)
                need(set(old_approval)=={'format','host','mode','attempt','carrier_manifest_sha256',
                        'plan_sha256','issued_at','expires_at','actions'}
                     and old_approval['host']==p.HOST and old_approval['mode']==MODE
                     and old_approval['attempt']==attempt()
                     and old_approval['carrier_manifest_sha256']==saved['carrier_manifest_sha256']
                     and old_approval['plan_sha256']==saved['plan_sha256']
                     and old_approval['actions']==C_ACTIONS
                     and type(old_approval['issued_at']) is int and type(old_approval['expires_at']) is int
                     and old_approval['issued_at']<=old_approval['expires_at']<=old_approval['issued_at']+600
                     and now>old_approval['expires_at'],'C_SUCCESSOR_PREDECESSOR_APPROVAL_INVALID')
                plan_path,approval_path=self._successor_paths(saved['plan_sha256'])
                successor=dict(candidate)
                successor.pop('plan_sha256',None)
                successor['predecessor_plan_sha256']=saved['plan_sha256']
                successor['predecessor_plan_record_sha256']=s.sha(saved_raw)
                successor['predecessor_approval_sha256']=s.sha(old_approval_raw)
                successor['carrier_manifest_sha256']=self.approved_stamp
                successor['plan_sha256']=s.sha(s.canonical(successor))
                # Recompute once with the final self-contained hash convention.
                successor['plan_sha256']=s.sha(s.canonical({k:v for k,v in successor.items() if k!='plan_sha256'}))
                record=dict(format=2,host=p.HOST,mode=MODE,attempt=attempt(),
                    carrier_manifest_sha256=self.approved_stamp,evidence_sha256=evidence_sha,
                    predecessor_plan_sha256=saved['plan_sha256'],
                    predecessor_plan_record_sha256=s.sha(saved_raw),
                    predecessor_approval_sha256=s.sha(old_approval_raw),
                    plan=successor,plan_sha256=successor['plan_sha256'],
                    plan_document_sha256=s.sha(s.canonical(successor)),
                    issued_at=now,expires_at=now+600)
                if exists_private(plan_path):
                    existing,existing_raw=document(plan_path,4*1024*1024)
                    need(set(existing)=={'format','host','mode','attempt','carrier_manifest_sha256','evidence_sha256',
                         'predecessor_plan_sha256','predecessor_plan_record_sha256','predecessor_approval_sha256',
                         'plan','plan_sha256','plan_document_sha256','issued_at','expires_at'}
                         and existing_raw==s.canonical(existing) and existing['format']==2
                         and existing['host']==p.HOST and existing['mode']==MODE and existing['attempt']==attempt()
                         and existing.get('predecessor_plan_record_sha256')==s.sha(saved_raw)
                         and existing.get('predecessor_approval_sha256')==s.sha(old_approval_raw)
                         and existing.get('plan_sha256')==existing.get('plan',{}).get('plan_sha256'),
                         'C_SUCCESSOR_ALREADY_EXISTS_CONFLICT')
                    successor=existing['plan']
                    need(existing['evidence_sha256']==evidence_sha,'C_SUCCESSOR_STABLE_EVIDENCE_CHANGED')
                    need(self._successor_base(successor)==self._successor_base(candidate),
                         'C_SUCCESSOR_STABLE_PLAN_CHANGED')
                    if now>existing.get('expires_at',0):
                        need(exists_private(approval_path),'C_SUCCESSOR_RENEWAL_PREDECESSOR_REQUIRED')
                        self.c_resume_plan_path=plan_path
                        prior_successor_approval=self._expired_successor_approval(
                            approval_path,successor,existing_raw,now)
                        self.successor_approval_sha256=s.sha(prior_successor_approval)
                        approval_path=self._successor_renewal_path(successor['plan_sha256'])
                        if exists_private(approval_path):
                            renewal_raw=self._expired_successor_renewal(
                                approval_path,successor,existing_raw,self.successor_approval_sha256,now)
                            self.successor_renewal_sha256=s.sha(renewal_raw)
                            approval_path=self._successor_recovery_path(self.successor_renewal_sha256)
                            if exists_private(approval_path):
                                recovery_raw=self._expired_successor_recovery(
                                    approval_path,successor,existing_raw,self.successor_approval_sha256,
                                    self.successor_renewal_sha256,now)
                                self.successor_recovery_sha256=s.sha(recovery_raw)
                                approval_path=self._successor_correction_path(self.successor_recovery_sha256)
                                if exists_private(approval_path):
                                    correction_raw=self._expired_successor_correction(
                                        approval_path,successor,existing_raw,self.successor_approval_sha256,
                                        self.successor_renewal_sha256,self.successor_recovery_sha256,now)
                                    self.successor_correction_sha256=s.sha(correction_raw)
                                    approval_path=self._successor_correction_reissue_path(
                                        self.successor_correction_sha256)
                else:
                    need(saved['evidence_sha256']==evidence_sha,'C_SUCCESSOR_STABLE_EVIDENCE_CHANGED')
                    need(self._without_observed_at(saved['plan'])==
                         self._without_observed_at(candidate),'C_SUCCESSOR_STABLE_PLAN_CHANGED')
                    # Recheck predecessor bytes and execution absence immediately before EXCL publish.
                    need(raw(C_RESUME_PLAN,4*1024*1024)==saved_raw
                         and raw(C_RESUME_APPROVAL,16384)==old_approval_raw,
                         'C_SUCCESSOR_PREDECESSOR_REPLACED')
                    for path in (proof_path,active_path,attempt_path):
                        need(not exists_private(path),'C_SUCCESSOR_EXECUTION_TRACE_PRESENT')
                    fd=s.private_parent(s.BACKUP)
                    try:write_private(fd,os.path.basename(plan_path),record)
                    finally:os.close(fd)
                self.c_resume_plan_path=plan_path
                self.c_resume_approval_path=approval_path
                candidate=successor
        else:
            need(not exists_private(C_RESUME_APPROVAL),'C_RESUME_APPROVAL_PREEXISTS_WITHOUT_PLAN')
            record=dict(format=1,host=p.HOST,mode=MODE,attempt=attempt(),
                carrier_manifest_sha256=self.approved_stamp,evidence_sha256=evidence_sha,
                plan=candidate,plan_sha256=candidate['plan_sha256'],
                plan_document_sha256=s.sha(s.canonical(candidate)),
                issued_at=now,expires_at=now+600)
            fd=s.private_parent(s.BACKUP)
            try:write_private(fd,os.path.basename(C_RESUME_PLAN),record)
            finally:os.close(fd)
            self.c_resume_plan_path=C_RESUME_PLAN
            self.c_resume_approval_path=C_RESUME_APPROVAL
        bound_plan=self.bind_resume_reference(self.c_resume_plan_path,4*1024*1024)
        self.resume_guard()
        print(json.dumps(dict(state='C_RESUME_PLAN_REQUIRES_FRESH_APPROVAL',
            attempt=attempt(),plan_sha256=candidate['plan_sha256'],
            plan=candidate,approval_path=self.c_resume_approval_path,expires_in_seconds=600,
            site_update=False),sort_keys=True,separators=(',',':')),flush=True)
        return candidate

    def resume_c_before_confirmation(self):
        """Resume same attempt after B completion, before any C proof or journal."""
        need(self.journal is None,'C_PRECONFIRMATION_RECOVERY_STATE_INVALID')
        proof_path=PROOF
        active_path=u.JOURNAL_PARENT+'/active-attempt.json'
        attempt_path=u.JOURNAL_PARENT+'/'+attempt()
        for path in (proof_path,active_path,attempt_path):
            need(not exists_private(path),'C_ALREADY_STARTED_INSPECT_ORIGINAL_RECOVERY')
        self.configure_resumed_b_context()
        self.boundary();self.stopped()
        semantic=self.evidence(True)
        self.boundary();self.stopped()
        self.backup=open_private(s.BACKUP+'/clone-results.json')
        computed=self.candidate(semantic)
        need(computed['attempt']==attempt(),'C_RESUME_ATTEMPT_CHANGED')
        c.exact_stopped_names(computed,'PREPARED',None)
        for path in (proof_path,active_path,attempt_path):
            need(not exists_private(path),'C_ALREADY_STARTED_INSPECT_ORIGINAL_RECOVERY')
        candidate=self._fixed_c_resume_plan(computed,semantic)
        deadline=time.monotonic()+120
        while True:
            self.boundary();self.stopped()
            for path in (proof_path,active_path,attempt_path):
                need(not exists_private(path),'C_ALREADY_STARTED_INSPECT_ORIGINAL_RECOVERY')
            c.exact_stopped_names(candidate,'PREPARED',None)
            try:
                self._c_resume_approval(candidate)
                break
            except FileNotFoundError:
                need(time.monotonic()<deadline,'C_RESUME_APPROVAL_NOT_RECEIVED')
                time.sleep(.1)
        # Approval is operation-specific and bound to the complete, printed,
        # persisted plan. Recheck it after the exact TTY confirmation.
        self.boundary();self.stopped()
        acknowledge('STOPPED_UPDATE',candidate['plan_sha256'])
        self.boundary();self.stopped()
        c.exact_stopped_names(candidate,'PREPARED',None)
        for path in (proof_path,active_path,attempt_path):
            need(not exists_private(path),'C_ALREADY_STARTED_INSPECT_ORIGINAL_RECOVERY')
        self._c_resume_approval(candidate)
        proof=dict(format=1,mode=MODE,host=p.HOST,attempt=attempt(),
             plan=candidate,approval_sha256=s.sha(self.craw),evidence=semantic,
             approval_kind='C_RESUME_APPROVAL',approval_path=self.c_resume_approval_path)
        fd=s.private_parent(s.BACKUP)
        try:write_private(fd,os.path.basename(PROOF),proof)
        finally:os.close(fd)
        self.boundary()
        # The pre-C absence fence is discharged only after the bound proof is
        # durably written and rechecked; the original C transaction may now
        # create its own active-attempt/checkpoint under its existing guards.
        self.resume_absent=tuple(path for path in self.resume_absent
            if path not in (active_path,attempt_path))
        return self.consume(proof,False)

    def pins(self):
        m,b=document(MANIFEST)
        need(set(m)=={'format','mode','install_root','files','updates_enabled'}
             and type(m['format']) is int and m['format']==1 and m['mode']==MODE
             and m['install_root']==CONTROL and m['updates_enabled'] is False,'EXACT_V2_MANIFEST_REQUIRED')
        need(type(m['files']) is dict and set(m['files'])==SOURCE_FILES,'EXACT_V2_FILES_REQUIRED')
        need(s.sha(raw(CONTROL+'/deploy/community-preview/f131-image-receipt.json'))==c.RECEIPT_SHA,'FROZEN_F131_RECEIPT_REQUIRED')
        for name,meta in m['files'].items():
            body=raw(CONTROL+'/'+name,131072)
            need(meta==dict(bytes=len(body),sha256=s.sha(body),uid=0,mode='0600'),'V2_SOURCE_CHANGED')
        return s.sha(b)
    def frozen_image_boundary(self,clock):
        if clock<s.EXPIRES:return
        # The original artifact window governs acquiring/loading the image.  A
        # persisted same-attempt PREPARED reopen may outlive that window only
        # when its immutable authority history is bound and the exact reviewed
        # image is already present in Docker.  This is read-only and is repeated
        # at every boundary; it never authorizes another image or a new attempt.
        need(self.recovering and self.prepared_reopen_raw is not None,
             'FROZEN_IMAGE_ARTIFACT_EXPIRED')
        fmt='{{json .Id}}\n{{json (index .Config.Labels "org.opencontainers.image.revision")}}\n{{json .Config.User}}'
        rows=c.observation.capture(p.DOCKER+['image','inspect','--format',fmt,s.NEW_IMAGE],
                                   timeout=8,budget=4096).splitlines()
        need(len(rows)==3 and [s.exact_json(v) for v in rows]==
             [s.NEW_IMAGE,s.PRODUCT,'10001:1008'],'EXACT_LOADED_IMAGE_REQUIRED')
    def boundary(self):
        need(threading.get_ident()==self.thread and operator()==self.owner,'OWNER_THREAD_CHANGED')
        need(time.monotonic()-self.started<=600,'WHOLE_ENTRY_TIME_BUDGET')
        st=os.stat('community-update.lock',dir_fd=self.parent,follow_symlinks=False)
        held=os.fstat(self.lease);u.protected(self.lease)
        need((st.st_dev,st.st_ino)==(held.st_dev,held.st_ino),'CONTINUOUS_LOCK_REPLACED')
        need(s.identity(os.fstat(self.entry))==s.identity(os.stat(s.ENTRY,follow_symlinks=False)),
             'CONTINUOUS_ENTRY_LOCK_REPLACED')
        need(s.sha(raw(s.ENTRY,131072))=='48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55',
             'A_INSTALLED_ENTRY_CHANGED')
        stamp=self.pins();t=c.now();self.frozen_image_boundary(t)
        need(self.last is None or t>=self.last,'CLOCK_BACKWARDS');self.last=t
        if self.resume_mode and self.resume_history:self.resume_guard()
        if self.approved_stamp is not None:need(stamp==self.approved_stamp,'CARRIER_STAMP_CHANGED')
        if self.braw is not None:need(raw(self.b_path)==self.braw,'B_REFERENCE_REPLACED')
        if self.resume_raw is not None:need(raw(resume_record_path())==self.resume_raw,'B_RESUME_RECORD_REPLACED')
        if self.prepared_reopen_raw is not None:
            v,b=document(self.prepared_reopen_path,16384)
            need(b==self.prepared_reopen_raw
                 and v.get('kind') in (PREPARED_REOPEN_KIND,PREPARED_REOPEN_REISSUE_KIND),
                 'C_PREPARED_REOPEN_EVIDENCE_CHANGED')
        elif self.craw is not None:
            approval_path=self.c_resume_approval_path if getattr(self,'c_preconfirm_mode',False) else C_APPROVAL
            v,b=document(approval_path);need(b==self.craw,'C_APPROVAL_REVOKED');window(v)
        elif self.braw is not None and not getattr(self,'c_preconfirm_mode',False):
            v,b=document(self.b_path);need(b==self.braw,'B_APPROVAL_REVOKED');window(v)
            need(v['carrier_manifest_sha256']==stamp,'B_SOURCE_BINDING_CHANGED')
        if self.freeze is not None:
            need(raw(self.freeze_path,16384)==self.freeze,'FREEZE_REPLACED')
            pre=self.journal is None or self.journal.state['phase'] in ('PREPARED','STOPPED_HANDOFF_ACCEPTED',
                'OLD_RENAME_INTENT','OLD_RETAINED','NEW_RUN_INTENT')
            if not self.recovering and pre and not getattr(self,'c_preconfirm_mode',False):window(s.exact_json(self.freeze))
    def freeze_live(self):
        f,b=document(self.freeze_path,16384)
        need(b==self.freeze and set(f)=={'format','host','old_id','old_image','roots','issued_at','expires_at',
             'all_writers_frozen','owner_review_reference_sha256'} and type(f['format']) is int
             and f['format']==1 and f['host']==p.HOST and f['old_id']==s.OLD_ID and f['old_image']==s.OLD_IMAGE
             and f['roots']==[s.DATA+'/data',s.DATA+'/config'] and f['all_writers_frozen'] is True
             and p.exact_hex(f['owner_review_reference_sha256'],64),'ORIGINAL_FREEZE_EVIDENCE_REQUIRED')
        if not getattr(self,'c_preconfirm_mode',False):window(f)
    def stopped(self):
        self.boundary();self.freeze_live();s.stopped();self.boundary()
    def b_stage(self,stage,snapshot_sha=None):
        self.resume_stage_preflight(stage)
        self.stopped();acknowledge(stage.upper().replace('-','_'),s.sha(self.braw));self.stopped()
        # No overwrite/reuse of an active or unknown stage permission.
        permit=dict(format=1,host=p.HOST,stage=stage,
            entry_sha256='48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55',
            issued_at=c.now(),expires_at=min(c.now()+600,self.b['expires_at'],s.exact_json(self.freeze)['expires_at']),
            all_writers_frozen_evidence_sha256=s.sha(self.freeze),snapshot_manifest_sha256=snapshot_sha)
        fd=s.private_parent(s.BASE);name=os.path.basename(self.stage_permit_path);identity=None;digest=s.sha(s.canonical(permit))
        if self.resume_mode:
            self.resume_guard();need(not exists_private(self.stage_permit_path),'B_PARTIAL_STATE_CONFLICT')
            self.resume_absent=tuple(path for path in self.resume_absent if path!=self.stage_permit_path)
        try:
            write_private(fd,name,permit)
            identity=s.identity(os.stat(name,dir_fd=fd,follow_symlinks=False))
            authorize_v2(self,stage,digest);s._ACTIVE=(stage,digest)
            self.stopped()
            if self.resume_mode:
                self.resume_guard()
                becoming=[s.BACKUP] if stage=='snapshot' else list(globals()['paths']().values())+[s.BACKUP+'/'+name for name in CLONES]
                self.resume_require_absent(becoming)
                self.resume_absent=tuple(path for path in self.resume_absent if path not in becoming)
            value=s.snapshot(permit) if stage=='snapshot' else s.validate_clones(permit)
            self.stopped();authorize_v2(self,stage,digest)
            if self.resume_mode:
                self.resume_guard();self.resume_absent=tuple(path for path in self.resume_absent if path!=b_records()[stage+'-result'])
            write_private(self.parent,attempt()+'-'+stage+'-result.json',dict(
                format=1,attempt=attempt(),stage=stage,approval_sha256=s.sha(self.braw),permit_sha256=digest,result=value))
            if self.resume_mode:
                self.resume_guard();self.resume_absent=tuple(path for path in self.resume_absent if path!=b_records()[stage+'-permit'])
            write_private(self.parent,attempt()+'-'+stage+'-permit.json',permit)
            need(raw(self.stage_permit_path,16384)==s.canonical(permit),'ACTIVE_PERMIT_CHANGED')
            self.stopped();authorize_v2(self,stage,digest)
            need(identity==s.identity(os.stat(name,dir_fd=fd,follow_symlinks=False)),'ACTIVE_PERMIT_REPLACED')
            self.boundary();authorize_v2(self,stage,digest)
            retire_permit(fd,name,identity,digest,self.stage_permit_path);identity=None;self.boundary()
            return value
        except BaseException:
            if identity is not None:
                try:retire_permit(fd,name,identity,digest,self.stage_permit_path);identity=None
                except BaseException:raise u.Hold('B_PERMISSION_CLEANUP_UNKNOWN') from None
            raise
        finally:s._ACTIVE=None;os.close(fd)
    def run_b(self):
        self.b_path=B_APPROVAL;self.freeze_path=s.FREEZE;self.stage_permit_path=s.PERMIT;self.resume_mode=False
        self.b,self.braw=document(self.b_path)
        need(set(self.b)=={'format','host','mode','attempt','carrier_manifest_sha256','issued_at','expires_at','freeze_sha256','actions'}
             and type(self.b['format']) is int and self.b['format']==1 and self.b['host']==p.HOST
             and self.b['mode']==MODE and self.b['attempt']==attempt()
             and self.b['actions']==['SNAPSHOT','THREE_ISOLATED_CLONES'],'EXACT_B_APPROVAL_REQUIRED')
        window(self.b);self.freeze=raw(self.freeze_path,16384)
        self.approved_stamp=self.b['carrier_manifest_sha256']
        need(self.pins()==self.approved_stamp,'B_SOURCE_BINDING_CHANGED')
        need(s.sha(self.freeze)==self.b['freeze_sha256'],'FREEZE_APPROVAL_MISMATCH')
        self.stopped()
        write_private(self.parent,attempt()+'-B-intent.json',
             dict(format=1,mode=MODE,attempt=attempt(),approval_sha256=s.sha(self.braw),freeze_sha256=s.sha(self.freeze)))
        snap=self.b_stage('snapshot')
        self.b_stage('validate-clones',snap['manifest_sha256'])
        need(set(self.captured)==set(CLONES),'REAL_THREE_CLONE_RESULTS_REQUIRED')
        self.bdone=True
    def resume_admission(self):
        self.resume_mode=True;self.b_path=B_RESUME_APPROVAL;self.freeze_path=RESUME_FREEZE;self.stage_permit_path=B_RESUME_STAGE_PERMIT
        records=b_records()
        intent_raw=self.bind_resume_reference(records['B-intent']);intent=s.exact_json(intent_raw)
        need(intent_raw==s.canonical(intent) and set(intent)=={'format','mode','attempt','approval_sha256','freeze_sha256'}
             and type(intent['format']) is int and intent['format']==1 and intent['mode']==MODE
             and intent['attempt']==attempt(),'EXACT_PRIOR_B_INTENT_REQUIRED')
        old_braw=self.bind_resume_reference(B_APPROVAL);old_b=s.exact_json(old_braw)
        old_freeze_raw=self.bind_resume_reference(s.FREEZE,16384);old_freeze=s.exact_json(old_freeze_raw)
        need(old_braw==s.canonical(old_b) and set(old_b)=={'format','host','mode','attempt','carrier_manifest_sha256','issued_at','expires_at','freeze_sha256','actions'}
             and type(old_b['format']) is int and old_b['format']==1 and old_b['host']==p.HOST and old_b['mode']==MODE
             and old_b['attempt']==attempt() and old_b['actions']==['SNAPSHOT','THREE_ISOLATED_CLONES']
             and type(old_b['issued_at']) is int and type(old_b['expires_at']) is int
             and old_b['issued_at']<=old_b['expires_at']<=old_b['issued_at']+600,
             'EXACT_PRIOR_B_APPROVAL_REQUIRED')
        need(intent['approval_sha256']==s.sha(old_braw) and intent['freeze_sha256']==s.sha(old_freeze_raw)
             and old_b['freeze_sha256']==s.sha(old_freeze_raw),'PRIOR_B_EVIDENCE_MISMATCH')
        need(old_freeze_raw==s.canonical(old_freeze)
             and set(old_freeze)=={'format','host','old_id','old_image','roots','issued_at','expires_at','all_writers_frozen','owner_review_reference_sha256'}
             and type(old_freeze['format']) is int and old_freeze['format']==1 and old_freeze['host']==p.HOST
             and old_freeze['old_id']==s.OLD_ID and old_freeze['old_image']==s.OLD_IMAGE
             and old_freeze['roots']==[s.DATA+'/data',s.DATA+'/config'] and old_freeze['all_writers_frozen'] is True
             and p.exact_hex(old_freeze['owner_review_reference_sha256'],64)
             and type(old_freeze['issued_at']) is int and type(old_freeze['expires_at']) is int
             and old_freeze['issued_at']<=old_freeze['expires_at']<=old_freeze['issued_at']+600,
             'EXACT_PRIOR_FREEZE_REQUIRED')
        pre_outputs=[records['snapshot-result'],records['snapshot-permit'],records['validate-clones-result'],records['validate-clones-permit']]
        pre_state=[s.BACKUP,C_APPROVAL,B_RESUME_STAGE_PERMIT,u.JOURNAL_PARENT+'/active-attempt.json',
                   u.JOURNAL_PARENT+'/'+attempt(),resume_record_path()]
        self.resume_require_absent(pre_outputs+pre_state)
        old_stage_permit_sha=self.strict_prior_stage_permit(old_b,old_freeze,old_freeze_raw)
        self.resume_old_permit_absent=old_stage_permit_sha is None
        self.braw=self.bind_resume_reference(self.b_path);self.b=s.exact_json(self.braw);window(self.b)
        fields={'format','host','mode','attempt','carrier_manifest_sha256','issued_at','expires_at',
                'old_b_intent_sha256','old_b_approval_sha256','old_freeze_sha256','old_stage_permit_sha256',
                'resume_freeze_sha256','actions'}
        need(self.braw==s.canonical(self.b) and set(self.b)==fields and type(self.b['format']) is int and self.b['format']==1
             and self.b['host']==p.HOST and self.b['mode']==MODE and self.b['attempt']==attempt()
             and self.b['actions']==['RESUME_SNAPSHOT','THREE_ISOLATED_CLONES'],'EXACT_B_RESUME_APPROVAL_REQUIRED')
        self.freeze=self.bind_resume_reference(self.freeze_path,16384);self.approved_stamp=self.b['carrier_manifest_sha256']
        need(self.pins()==self.approved_stamp and p.exact_hex(old_b['carrier_manifest_sha256'],64),'B_SOURCE_BINDING_CHANGED')
        need(self.b['old_b_intent_sha256']==s.sha(intent_raw) and self.b['old_b_approval_sha256']==s.sha(old_braw)
             and self.b['old_freeze_sha256']==s.sha(old_freeze_raw) and self.b['old_stage_permit_sha256']==old_stage_permit_sha
             and self.b['resume_freeze_sha256']==s.sha(self.freeze),'B_RESUME_EVIDENCE_BINDING_CHANGED')
        self.freeze_live();self.stopped();probe_names_absent()
        # Recheck every historical byte+identity and all pre-backup absences immediately before the first write.
        self.resume_require_absent(pre_outputs+pre_state)
        self.resume_absent=tuple(pre_outputs+pre_state[:-1])
        record=dict(format=1,mode=MODE,attempt=attempt(),carrier_manifest_sha256=self.approved_stamp,
            old_b_intent_sha256=s.sha(intent_raw),old_b_approval_sha256=s.sha(old_braw),old_freeze_sha256=s.sha(old_freeze_raw),
            old_stage_permit_sha256=old_stage_permit_sha,resume_approval_sha256=s.sha(self.braw),
            resume_freeze_sha256=s.sha(self.freeze),actions=self.b['actions'])
        write_private(self.parent,os.path.basename(resume_record_path()),record)
        self.resume_raw=self.bind_resume_reference(resume_record_path())
        need(self.resume_raw==s.canonical(record),'B_RESUME_RECORD_CHANGED')
        return record
    def resume_b_partial(self):
        self.resume_admission()
        snap=self.b_stage('snapshot')
        self.b_stage('validate-clones',snap['manifest_sha256'])
        need(set(self.captured)==set(CLONES),'REAL_THREE_CLONE_RESULTS_REQUIRED')
        self.bdone=True
    def evidence(self,active):
        self.boundary()
        m,mb=document(s.BACKUP+'/private-manifest.json',8*1024*1024)
        need(set(m)=={'format','old_id','old_image','product_image','all_writers_frozen_evidence_sha256','trees'}
             and type(m['format']) is int and m['format']==1 and m['old_id']==s.OLD_ID
             and m['old_image']==s.OLD_IMAGE and m['product_image']==s.NEW_IMAGE
             and m['all_writers_frozen_evidence_sha256']==s.sha(self.freeze),'SNAPSHOT_BINDING_CHANGED')
        need(set(m['trees'])=={'data','config'} and s.copy_roots(s.BACKUP+'/snapshot',None)==m['trees'],'IMMUTABLE_BACKUP_CHANGED')
        if active:
            self.boundary();self.freeze_live()
            need(s.copy_roots(s.DATA,None)==m['trees'],'CURRENT_TREE_DRIFT')
            self.freeze_live();self.boundary()
        result,rb=document(s.BACKUP+'/clone-results.json')
        need(set(result)=={'stage','snapshot_manifest_sha256','logical_evidence_sha256','tested_at','restore_original_host',
             'downgrade_logical_equality','production_acceptance','rollback_health_acceptance'}
             and result['stage']=='validate-clones' and result['snapshot_manifest_sha256']==s.sha(mb)
             and result['restore_original_host'] is True and result['downgrade_logical_equality'] is True
             and result['production_acceptance'] is False and result['rollback_health_acceptance'] is False
             and type(result['tested_at']) is int,'REAL_CLONE_RESULT_REQUIRED')
        rows=[];hashes={}
        for name,path in paths().items():
            row,b=document(path)
            image=s.NEW_IMAGE if name=='verify-f131' else s.OLD_IMAGE
            need(set(row)=={'format','attempt','name','image','code_sha256','result'}
                 and type(row['format']) is int and row['format']==1 and row['attempt']==attempt()
                 and row['name']==name and row['image']==image and row['code_sha256']==s.sha(s.CLONE_CODE.encode()),
                 'CLONE_SOURCE_OR_IMAGE_CHANGED')
            rows.append(row['result']);hashes[name]=s.sha(b)
        need(rows[0]==rows[1]==rows[2] and set(rows[0])=={'format','original_host_open','center_integrity','stores'}
             and rows[0]['format']==1 and type(rows[0]['format']) is int
             and rows[0]['original_host_open'] is True and rows[0]['center_integrity'] is True
             and type(rows[0]['stores']) is list and rows[0]['stores']
             and s.sha(s.canonical(rows[0]))==result['logical_evidence_sha256'],'CLONE_BODY_MISMATCH')
        if active and not getattr(self,'c_preconfirm_mode',False):
            f=s.exact_json(self.freeze)
            need(f['issued_at']<=result['tested_at']<=c.now() and c.now()-600<=result['tested_at'],
                 'RESTORE_PROOF_STALE')
        elif active:
            # Completed B clone timestamps are immutable historical evidence.
            # Current stopped/container identity is independently rechecked;
            # do not rewrite timestamps or rerun B/clone work.
            need(result['tested_at']<=c.now(),'CLONE_RESULT_FROM_FUTURE')
        records={}
        intent,ib=document(b_records()['B-intent'])
        if self.resume_mode:
            resume,_=document(resume_record_path())
            need(type(intent.get('format')) is int and intent==dict(format=1,mode=MODE,attempt=attempt(),
                 approval_sha256=resume['old_b_approval_sha256'],freeze_sha256=resume['old_freeze_sha256']),
                 'B_INTENT_CHANGED')
            records['B-resume-admission']=s.sha(self.resume_raw)
        else:
            need(type(intent.get('format')) is int and intent==dict(format=1,mode=MODE,attempt=attempt(),approval_sha256=s.sha(self.braw),
                 freeze_sha256=s.sha(self.freeze)),'B_INTENT_CHANGED')
        records['B-intent']=s.sha(ib)
        for stage in ('snapshot','validate-clones'):
            event,eb=document(b_records()[stage+'-result'])
            permit,pb=document(b_records()[stage+'-permit'])
            need(set(event)=={'format','attempt','stage','approval_sha256','permit_sha256','result'}
                 and type(event['format']) is int and event['format']==1 and event['attempt']==attempt()
                 and event['stage']==stage and event['approval_sha256']==s.sha(self.braw)
                 and event['permit_sha256']==s.sha(pb),'B_RESULT_BINDING_CHANGED')
            need(set(permit)=={'format','host','stage','entry_sha256','issued_at','expires_at',
                 'all_writers_frozen_evidence_sha256','snapshot_manifest_sha256'}
                 and type(permit['format']) is int and permit['format']==1 and permit['host']==p.HOST
                 and permit['stage']==stage and permit['entry_sha256']=='48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55'
                 and type(permit['issued_at']) is int and type(permit['expires_at']) is int
                 and permit['issued_at']<=permit['expires_at']<=permit['issued_at']+600
                 and permit['all_writers_frozen_evidence_sha256']==s.sha(self.freeze)
                 and permit['snapshot_manifest_sha256']==(None if stage=='snapshot' else s.sha(mb)),
                 'B_PERMISSION_BINDING_CHANGED')
            expected=dict(stage='snapshot',manifest_sha256=s.sha(mb),
                bytes=sum(t['bytes'] for t in m['trees'].values()),recovery_verified=False,downgrade_verified=False)
            need(event['result']==(expected if stage=='snapshot' else result),'B_RESULT_BODY_CHANGED')
            if stage=='snapshot':
                need(type(event['result']['bytes']) is int and event['result']['recovery_verified'] is False
                     and event['result']['downgrade_verified'] is False,'B_RESULT_TYPE_CHANGED')
            records[stage+'-result']=s.sha(eb);records[stage+'-permit']=s.sha(pb)
        self.boundary()
        value=dict(snapshot_sha256=s.sha(mb),clone_results_sha256=s.sha(rb),clones=hashes,
                   freeze_sha256=s.sha(self.freeze),b_approval_sha256=s.sha(self.braw),b_records=records)
        if self.resume_mode:
            value['b_resume_record_sha256']=s.sha(self.resume_raw)
            value['prior_b_approval_sha256']=s.exact_json(self.resume_raw)['old_b_approval_sha256']
            value['prior_freeze_sha256']=s.exact_json(self.resume_raw)['old_freeze_sha256']
        return value
    def current(self,semantic):
        value=c.read_current(s.OLD_ID,s.OLD_IMAGE,self.backup)
        value['backup_reference_sha256']=c.digest(semantic)
        return value
    def candidate(self,semantic):
        receipt=s.exact_json(raw(CONTROL+'/deploy/community-preview/f131-image-receipt.json'))
        source=dict(source_sha=s.PRODUCT,tree_sha=receipt['product_tree'],
            source_zip_sha256=receipt['source_artifact']['inner_zip_sha256'],artifact_id=receipt['source_artifact']['id'],
            artifact_sha256=receipt['source_artifact']['outer_sha256'],run_id=receipt['build_run_id'],ocr_source_sha=p.OCR_SHA,
            push_evidence_run_id=receipt['push_evidence_run_id'])
        image=dict(source_sha=s.PRODUCT,tree_sha=source['tree_sha'],source_zip_sha256=source['source_zip_sha256'],
            oci_revision=s.PRODUCT,image_id=s.NEW_IMAGE,repo_digest=None,image_archive_sha256=receipt['image_artifact']['inner_tar_sha256'],
            artifact_sha256=receipt['image_artifact']['outer_sha256'],artifact_id=receipt['image_artifact']['id'],run_id=receipt['build_run_id'])
        return p.prepare_stopped(source,self.current(semantic),image)
    def c_approval(self,candidate):
        a,b=document(C_APPROVAL)
        need(set(a)=={'format','host','mode','attempt','carrier_manifest_sha256','plan_sha256','issued_at','expires_at','actions'}
             and type(a['format']) is int and a['format']==1 and a['host']==p.HOST and a['mode']==MODE
             and a['attempt']==candidate['attempt'] and a['plan_sha256']==candidate['plan_sha256']
             and self.approved_stamp is not None and a['carrier_manifest_sha256']==self.approved_stamp==self.pins()
             and a['actions']==C_ACTIONS,'EXACT_C_APPROVAL_REQUIRED')
        window(a);self.craw=b;return a
    def update(self):
        need(self.bdone,'SAME_PROCESS_CONTINUOUS_B_REQUIRED')
        need(self.journal is None and not os.path.lexists(PROOF),'EXISTING_ATTEMPT_INSPECT_OR_RECOVER_ONLY')
        self.stopped();semantic=self.evidence(True);self.stopped()
        self.backup=open_private(s.BACKUP+'/clone-results.json')
        candidate=self.candidate(semantic)
        if self.resume_mode:
            self.resume_absent=(u.JOURNAL_PARENT+'/active-attempt.json',u.JOURNAL_PARENT+'/'+attempt())
            self.resume_guard()
        print(json.dumps(dict(state='STOPPED_PLAN_REQUIRES_SEPARATE_C_APPROVAL',plan_sha256=candidate['plan_sha256'],
                              attempt=candidate['attempt'],site_update=False)),flush=True)
        deadline=time.monotonic()+120
        while True:
            self.boundary()
            try:self.c_approval(candidate);break
            except FileNotFoundError:
                need(time.monotonic()<deadline,'C_APPROVAL_NOT_RECEIVED')
                time.sleep(.1)  # Missing exact file only; malformed/denied never retried.
        acknowledge('STOPPED_UPDATE',candidate['plan_sha256']);self.stopped()
        proof=dict(format=1,mode=MODE,host=p.HOST,attempt=candidate['attempt'],
             plan=candidate,approval_sha256=s.sha(self.craw),evidence=semantic)
        fd=s.private_parent(s.BACKUP)
        try:write_private(fd,os.path.basename(PROOF),proof)
        finally:os.close(fd)
        return self.consume(proof,False)
    def reference_digest(self):
        rows=[]
        base=[PROOF,C_APPROVAL,self.b_path,self.freeze_path,s.BACKUP+'/private-manifest.json',s.BACKUP+'/clone-results.json']
        if getattr(self,'c_preconfirm_mode',False):
            base += [self.c_resume_approval_path,self.c_resume_plan_path]
        if self.resume_mode:
            base += [B_APPROVAL,s.FREEZE,resume_record_path()]
            resume=s.exact_json(self.resume_raw)
            if resume.get('old_stage_permit_sha256') is not None:base.append(s.PERMIT)
        for path in base+list(paths().values())+list(b_records().values()):
            limit=8*1024*1024 if path.endswith('/private-manifest.json') else 65536
            body=raw(path,limit);fd=open_private(path)
            try:
                meta=s.identity(os.fstat(fd))
                need(meta==s.identity(os.stat(path,follow_symlinks=False)) and raw(path,limit)==body,
                     'REFERENCE_REPLACED_DURING_BIND')
                rows.append([path,s.sha(body),meta])
            finally:os.close(fd)
        return c.digest(rows)
    def consume(self,proof,recover,prepared_reopen=False):
        need(type(proof) is dict and set(proof) in ({'format','mode','host','attempt','plan','approval_sha256','evidence'},
             {'format','mode','host','attempt','plan','approval_sha256','evidence','approval_kind','approval_path'}),
             'EXACT_HANDOFF_DOCUMENT_REQUIRED')
        need(proof['mode']==MODE and proof['host']==p.HOST and proof['attempt']==attempt()
             and type(proof['format']) is int and proof['format']==1,'EXACT_PROOF_SCOPE_REQUIRED')
        candidate=proof['plan']
        if proof.get('approval_kind')=='C_RESUME_APPROVAL':
            self.c_preconfirm_mode=True
            if self.c_resume_approval_path==C_RESUME_APPROVAL:
                self._restore_c_resume_paths(proof)
            if not prepared_reopen:self._c_resume_approval(candidate)
            else:
                bound=self.bind_resume_reference(self.c_resume_approval_path,16384)
                need(bound==raw(self.c_resume_approval_path,16384)
                     and s.sha(bound)==proof['approval_sha256'],'PROOF_APPROVAL_CHANGED')
                self.craw=bound
        else:self.c_approval(candidate)
        need(proof['approval_sha256']==s.sha(self.craw),'PROOF_APPROVAL_CHANGED')
        binding=dict(approval_sha256=s.sha(self.craw),handoff_sha256=self.reference_digest())
        if recover or prepared_reopen:
            active=raw(u.JOURNAL_PARENT+'/active-attempt.json')
            need(active==json.dumps(dict(attempt=candidate['attempt'],plan_sha256=candidate['plan_sha256']),sort_keys=True).encode(),
                 'EXISTING_SAME_ATTEMPT_REQUIRED')
            raw(u.JOURNAL_PARENT+'/'+candidate['attempt']+'/checkpoint.json')
        if self.resume_mode:
            self.resume_absent=()
            self.resume_guard()
        self.journal=u.Journal(self.parent,candidate,lease_fd=self.lease,handoff_binding=binding)
        h=VerifiedHandoff(self,proof,self.journal)
        transport=u.OriginalTransport(h.bindings,c.BoundHttpsHealth(self.journal,h.bindings),
            route_transition=c.stopped_route_transition)
        update=u.Update(self.journal,transport,execution_enabled=True,clock=c.now,handoff=h)
        if recover:
            c.recovery_admission(self.journal,transport,h.bindings)
            return update.recover()
        if prepared_reopen:return update.reopen_prepared_stopped()
        return update.run_stopped()

    def reopen_prepared(self):
        proof,_=document(PROOF)
        need(type(proof) is dict and 'plan' in proof,'PROOF_REQUIRED')
        need(self.configure_resumed_recovery(proof),'PREPARED_RESUME_CONTEXT_REQUIRED')
        # Restore and bind the original proof authority without treating its
        # expired window as new execution authority.  The journal continues to
        # carry that immutable hash; the separate permit below authorizes only
        # reopening this exact PREPARED checkpoint.
        self._restore_c_resume_paths(proof);self.approved_stamp=self.pins()
        self.backup=open_private(s.BACKUP+'/clone-results.json')
        self._prepared_reopen_approval(proof)
        acknowledge('PREPARED_REOPEN',proof['plan']['plan_sha256'])
        return self.consume(proof,False,prepared_reopen=True)
    def recover(self):
        proof,proof_raw=document(PROOF)
        need(type(proof) is dict and 'plan' in proof,'PROOF_REQUIRED')
        if not self.configure_resumed_recovery(proof):
            self.b_path=B_APPROVAL;self.freeze_path=s.FREEZE;self.stage_permit_path=s.PERMIT;self.resume_mode=False
            self.b,self.braw=document(self.b_path);self.approved_stamp=self.b['carrier_manifest_sha256'];self.freeze=raw(self.freeze_path,16384)
        self.backup=open_private(s.BACKUP+'/clone-results.json')
        # No B rerun, no new plan, no automatic recovery of intents/UNKNOWN.
        if proof.get('approval_kind')=='C_RESUME_APPROVAL':
            self.c_preconfirm_mode=True
            prepared_path=self._prepared_reopen_path(s.sha(proof_raw))
            if exists_private(prepared_path):
                self._restore_c_resume_paths(proof);self.approved_stamp=self.pins()
                self._prepared_reopen_approval(proof,'KNOWN_FAILURE')
                bound=self.bind_resume_reference(self.c_resume_approval_path,16384)
                need(s.sha(bound)==proof['approval_sha256'],'PROOF_APPROVAL_CHANGED');self.craw=bound
            else:self._c_resume_approval(proof['plan'])
        else:self.c_approval(proof['plan'])
        if self.prepared_reopen_raw is not None:
            return self.consume(proof,True,prepared_reopen=True)
        acknowledge('KNOWN_FAILURE_RECOVER',proof['plan']['plan_sha256'])
        return self.consume(proof,True)
    def close(self):
        if self.cleanup_unproven:raise u.Hold('BC_CLEANUP_UNKNOWN')
        unproven_close=False
        s._ACTIVE=None
        if self.old_checkpoint is not None:s.checkpoint=self.old_checkpoint
        if self.old_clone is not None:s.clone_run=self.old_clone
        if self.old_checkpoint is not None:s._COMPONENT=self.old_component
        journal=self.journal;self.journal=None
        if journal is not None:
            try:journal.close()
            except BaseException:unproven_close=True
        for name in ('backup','entry','lease','parent'):
            fd=getattr(self,name)
            if fd is None:continue
            # Drop ownership before invoking close. Never retry a possibly
            # consumed/recycled descriptor number after an exceptional close.
            setattr(self,name,None)
            try:os.close(fd)
            except BaseException:unproven_close=True
        if unproven_close:
            self.cleanup_unproven=True
            raise u.Hold('BC_CLEANUP_UNKNOWN')

class VerifiedHandoff:
    def __init__(self,session,proof,journal):
        self.session=session;self.proof=proof;self.journal=journal
        need(journal.plan==proof['plan'],'HANDOFF_PLAN_CHANGED')
    def before_new(self):
        return self.journal.state['phase'] in ('PREPARED','STOPPED_HANDOFF_ACCEPTED',
            'OLD_RENAME_INTENT','OLD_RETAINED','NEW_RUN_INTENT')
    def bindings(self):
        self.session.boundary()
        c.exact_stopped_names(self.journal.plan,self.journal.state['phase'],self.journal.state.get('new_id'))
        return self.session.current(self.proof['evidence'])
    def pre_action(self,intent,new_id):
        need(self.journal.state['phase']==intent,'HANDOFF_ACTION_PHASE_CHANGED')
        need(c.exact_stopped_names(self.journal.plan,intent,new_id,pre_action=True),'HANDOFF_PRE_ACTION_NAMES_CHANGED')
    def check(self):
        q=self.session;j=self.journal;q.boundary();j.validate_history()
        proof,b=document(PROOF)
        need(proof==self.proof and q.reference_digest()==j.handoff_binding['handoff_sha256']
             and s.sha(q.craw)==j.handoff_binding['approval_sha256'],'HANDOFF_REFERENCE_REPLACED')
        before=self.before_new()
        need(q.evidence(before)==proof['evidence'],'HANDOFF_EVIDENCE_CHANGED')
        live=self.bindings();base=j.plan['current']
        changed={k for k in base if k not in ('running','observed_at')
                 and (type(live[k]) is not type(base[k]) or live[k]!=base[k])}
        compatible=(changed=={'routing_sha256'}
                    and c.stopped_route_transition(base,live) is True)
        need(not changed or compatible,'LIVE_HANDOFF_BINDING_CHANGED')
        need(c.now()-600<=live['observed_at']<=c.now()+30,'CURRENT_STALE')
        if before:
            need(live['running'] is False,'OLD_REVIVED');q.freeze_live();q.boundary()
        need(c.exact_stopped_names(j.plan,j.state['phase'],j.state.get('new_id')),'STOPPED_NAME_CHANGED')
        if before:q.freeze_live();q.boundary()
        q.boundary()

SOURCE_FILES={'loader.py','scripts/community_preview_release_plan.py','scripts/community_preview_upgrade.py',
 'scripts/community_preview_version_inspect.py','scripts/community_preview_update_checkpoint.py',
 'scripts/community_preview_update_composition.py','scripts/community_preview_site_prepare.py',
 'scripts/community_preview_stopped_handoff.py','deploy/community-preview/f131-image-receipt.json'}

def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--owner-bc',action='store_true')
    group.add_argument('--resume-b-partial',action='store_true')
    group.add_argument('--resume-c-before-confirmation',action='store_true')
    group.add_argument('--recover-known-failure',action='store_true')
    group.add_argument('--reopen-prepared',action='store_true')
    args=parser.parse_args(argv)
    if not args.owner_bc and not args.resume_b_partial and not args.recover_known_failure and not args.resume_c_before_confirmation and not args.reopen_prepared:
        print('{"state":"BC_DEFAULT_HOLD","site_executed":false}');return 2
    session=Session();result=None;code=2
    try:
        session.acquire(recover=args.recover_known_failure or args.reopen_prepared)
        if args.owner_bc:
            session.run_b();result=session.update()
        elif args.resume_b_partial:
            session.resume_b_partial();result=session.update()
        elif args.resume_c_before_confirmation:
            result=session.resume_c_before_confirmation()
        elif args.reopen_prepared:result=session.reopen_prepared()
        else:result=session.recover()
        need(result['phase'] in ('COMMITTED','ROLLED_BACK_PREVIEW_HOLD'),'NONTERMINAL_NOT_SUCCESS')
        code=0
    except BaseException as error:
        import re,traceback
        reason=str(error) if type(error) in (u.Hold,s.Hold,c.original.Rejected) and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',str(error)) else 'BC_BOUNDARY_UNKNOWN'
        # Safe diagnostics only: never emit exception text, argv, paths or secrets.
        frames=traceback.extract_tb(error.__traceback__)
        trail=[f.name for f in frames[-4:] if re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}',f.name)]
        result=dict(phase='HOLD_UNKNOWN_INSPECT_SAME_ATTEMPT',reason=reason,
                    error_type=type(error).__name__,safe_call_trail=trail)
    finally:
        try:session.close()
        except BaseException:code=2;result=dict(phase='HOLD_CLEANUP_UNKNOWN')
    print(json.dumps(dict(state='BC_RESULT',child_exit=code,result=result,
        production_acceptance=False,ocr_enabled=False,servertrust=False,image=s.NEW_IMAGE,control_mode=MODE),sort_keys=True),flush=True)
    return code

if __name__=='__main__':raise SystemExit(main())
