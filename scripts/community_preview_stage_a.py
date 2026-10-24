"""Fixed stage A manual Owner/sudo adapter. No default execution or servertrust.

Only the original admin SSH controlling terminal may supply an exact-stage
acknowledgement (including a queued line). These local records document that privileged action; they are NOT
OAuth/signatures, independent approval, or a grant from copied chat text.
"""
import fcntl
import hashlib
import json
import math
import os
import pwd
import re
import select
import resource
import subprocess
import stat
import time
import types

HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/opt/xuanjun-community-preview'
INPUT=BASE+'/image-f131-40059478387'
PERMIT='site-prepare-approval.json'
ENTRY='site-prepare-v1.py'
ATTEMPT='stage-a-attempt.json'
SOURCE='3b6be4aa1ff06d088fe26f44f08b9a505c5b5513'
EXPIRES=1793072670
PAYLOAD={
 'community_preview_site_prepare.py':(32470,'48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55'),
 'prepare-site.sh':(3642,'f1af825d4acec6d775956a16a19f5e65b3a58c6aae0e703164f84ee9429ba2c6'),
 'control-oci2330-v1.zip':(111330,'aa8afb5c05240e3c4835680e8cec765fa4199f0b7f230e3adaced8bc489397f9'),
 'artifact12546452389.zip':(57016858,'c902a0663793cb3b99c4c5ab3156d4e9d1054d519d05403347ba20fdebbc061e')}
class Hold(RuntimeError):pass

def need(ok,reason):
    if not ok:raise Hold(reason)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def clock():
    value=time.time();need(type(value) in (int,float) and math.isfinite(value),'CLOCK_UNKNOWN');return value

def owner_context():
    """Existing manual sudo operator context, not a server-signed Owner identity."""
    need(os.getuid()==0 and os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST,'ROOT_HOST_REQUIRED')
    admin=pwd.getpwnam('admin')
    need(admin.pw_uid>0 and os.environ.get('SUDO_USER')=='admin'
        and os.environ.get('SUDO_UID')==str(admin.pw_uid) and os.environ.get('SUDO_GID')==str(admin.pw_gid),'ORIGINAL_ADMIN_SUDO_REQUIRED')
    fd=os.open('/proc/'+str(os.getpid())+'/loginuid',os.O_RDONLY|os.O_NOFOLLOW)
    try:value=os.read(fd,32)
    finally:os.close(fd)
    need(value.strip()==str(admin.pw_uid).encode(),'KERNEL_LOGINUID_UNCONFIRMED')
    return {'sudo_uid':admin.pw_uid,'sudo_gid':admin.pw_gid,'kernel_loginuid':admin.pw_uid}

def check_terminal(fd):
    info=os.fstat(fd)
    # sudo use_pty can initially keep a heredoc command in a background group.
    # Do not preempt the kernel SIGTTIN/sudo foreground handoff or alter it.
    need(stat.S_ISCHR(info.st_mode) and os.isatty(fd),'OWNER_CONTROLLING_TTY_REQUIRED')

def open_terminal():
    fd=os.open('/dev/tty',os.O_RDWR|os.O_NOFOLLOW|os.O_NOCTTY)
    try:check_terminal(fd);return fd
    except BaseException:os.close(fd);raise

def verify_payload(blobs):
    need(type(blobs) is dict and set(blobs)==set(PAYLOAD),'FOUR_EXACT_INPUTS_REQUIRED')
    for name,(size,digest) in PAYLOAD.items():
        need(type(blobs[name]) is bytes and len(blobs[name])==size and sha(blobs[name])==digest,'INPUT_DIGEST_MISMATCH')

def original(blobs):
    verify_payload(blobs)
    module=types.ModuleType('verified_original_site_prepare')
    module.__file__=BASE+'/'+ENTRY
    exec(compile(blobs['community_preview_site_prepare.py'],module.__file__,'exec'),module.__dict__)
    return module

class StageA:
    def __init__(self,blobs,manifest_sha256):
        need(type(manifest_sha256) is str and re.fullmatch('[0-9a-f]{64}',manifest_sha256),'VERIFIED_DELIVERY_BINDING_REQUIRED')
        self.blobs=blobs;self.s=original(blobs);self.parent=None;self.input=None;self.tty=None
        self.manifest_sha256=manifest_sha256
        self.permit_identity=None
        self.phase=None;self.issued=None;self.deadline=None;self.operator=None;self.scope=sha(canonical({
            'format':1,'host':HOST,'delivery_manifest_sha256':manifest_sha256,'original_source':SOURCE,'payload':PAYLOAD,'stages':['install','image-load'],
            'site_update':False,'private_data':False,'servertrust':False}))
    def close(self):
        failed=False
        for attr in ('input','tty','parent'):
            value=getattr(self,attr);setattr(self,attr,None)
            if value is not None:
                try:os.close(value)
                except BaseException:failed=True
        if failed:raise Hold('STAGE_A_CLEANUP_UNKNOWN')
    def absent(self,name):
        try:os.stat(name,dir_fd=self.parent,follow_symlinks=False)
        except FileNotFoundError:return
        raise Hold('EXISTING_OR_PARTIAL_ATTEMPT_HOLD')
    def preflight(self):
        self.operator=owner_context();self.parent=self.s.private_parent(BASE)
        fcntl.flock(self.parent,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for name in (ENTRY,PERMIT,ATTEMPT,'control-oci2330-v1','update-journal',
                     'stage-a-install-result.json','stage-a-image-load-result.json',
                     'site-prepare-approval.install.json','site-prepare-approval.image-load.json'):
            self.absent(name)
        # Exact public prestaging is reusable; anything else is an unknown attempt.
        try:self.input=self.s.private_parent(INPUT)
        except FileNotFoundError:self.input=None
        if self.input is not None:
            need(set(os.listdir(self.input))==set(PAYLOAD),'PRESTAGED_INPUT_SET_CONFLICT')
            for name,(size,digest) in PAYLOAD.items():
                need(sha(self.s.read(INPUT+'/'+name,size))==digest,'PRESTAGED_INPUT_CHANGED')
        self.s.space(self.parent,sum(v[0] for v in PAYLOAD.values())+2*57365044+2*111330,64)  # +128 = 192 free inodes
        need(clock()<EXPIRES,'ORIGINAL_ARTIFACT_EXPIRED')
        self.tty=open_terminal()
    def confirm(self,phase):
        need(phase in ('install','image-load'),'STAGE_A_ONLY')
        need(owner_context()==self.operator,'OPERATOR_CHANGED')
        check_terminal(self.tty)
        expected=('APPROVE_'+phase.upper().replace('-','_')+' '+self.scope).encode()
        message=(b'REVIEWED STAGE A ONLY. No service stop/update/private data.\n'
            +b'Type the exact stage confirmation on this controlling terminal:\n'+expected+b'\n')
        os.write(self.tty,message)
        need(select.select([self.tty],[],[],120)[0]==[self.tty],'OWNER_CONFIRMATION_TIMEOUT')
        answer=os.read(self.tty,257)
        need(len(answer)<=256 and answer in (expected+b'\n',expected+b'\r\n'),'NO_EXACT_OPERATOR_CONFIRMATION')
        # Time is line CONSUMPTION time, not evidence it was typed after prompt.
        # No independent Owner authentication or servertrust is established.
        issued=int(clock());self.phase=phase;self.issued=issued;self.deadline=issued+600
        self.gate()
    def gate(self):
        need(self.phase in ('install','image-load') and self.issued is not None,'ACTUAL_STAGE_CONFIRMATION_REQUIRED')
        need(owner_context()==self.operator,'OPERATOR_CHANGED')
        check_terminal(self.tty)
        now=clock();need(self.issued<=now<=self.deadline and now<EXPIRES,'STAGE_APPROVAL_EXPIRED')
    def write(self,fd,name,body):
        self.gate();out=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:
            self.gate();os.fchown(out,0,0)
            self.gate();os.fchmod(out,0o600)
            view=memoryview(body)
            while view:
                self.gate();count=os.write(out,view);need(count>0,'WRITE_FAILED');view=view[count:]
            self.gate();os.fsync(out)
        finally:os.close(out)
        self.gate();os.fsync(fd)
    def stage_inputs(self):
        self.s.space(self.parent,sum(v[0] for v in PAYLOAD.values())+2*57365044+2*111330,64)
        self.gate()
        if self.input is None:
            self.gate();os.mkdir('image-f131-40059478387',0o700,dir_fd=self.parent)
            fd=os.open('image-f131-40059478387',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.parent)
            try:
                self.gate();os.fchown(fd,0,0)
                self.gate();os.fchmod(fd,0o700)
                self.gate();os.fsync(fd)
            finally:os.close(fd)
            self.input=self.s.private_parent(INPUT)
            self.gate();os.fsync(self.parent)
            for name in sorted(PAYLOAD):self.write(self.input,name,self.blobs[name])
        for name,(size,digest) in PAYLOAD.items():
            need(sha(self.s.read(INPUT+'/'+name,size))==digest,'STAGED_READBACK_MISMATCH')
        self.gate()
    def permit(self):
        value={'format':1,'host':HOST,'stage':self.phase,'entry_sha256':PAYLOAD['community_preview_site_prepare.py'][1],
            'issued_at':self.issued,'expires_at':self.deadline,
            'all_writers_frozen_evidence_sha256':None,'snapshot_manifest_sha256':None}
        raw=canonical(value);self.write(self.parent,PERMIT,raw)
        need(self.s.read(BASE+'/'+PERMIT,16384)==raw,'PERMIT_READBACK_CHANGED')
        self.permit_identity=self.s.identity(os.stat(PERMIT,dir_fd=self.parent,follow_symlinks=False))
        self.gate();return raw
    def capture_bootstrap(self,args,timeout=300):
        # Adaptation only: the frozen caller's 16KiB RLIMIT is for its log
        # children, not for a Python which writes 32470B ENTRY / 57365044B tar.
        # stdout is a bounded PIPE; regular file writes get a phase-fixed cap.
        need(self.phase in ('install','image-load'),'STAGE_A_ONLY')
        file_limit=131072 if self.phase=='install' else 64*1024**2
        def limits():
            hard=resource.getrlimit(resource.RLIMIT_FSIZE)[1]
            need(hard==resource.RLIM_INFINITY or hard>=file_limit,'INHERITED_FILE_LIMIT_TOO_SMALL')
            resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit,file_limit))
            resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            need(owner_context()==self.operator,'OPERATOR_CHANGED')
            now=clock();need(self.issued<=now<=self.deadline and now<EXPIRES,'STAGE_APPROVAL_EXPIRED')
        self.gate()
        proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            start_new_session=True,preexec_fn=limits,env=dict({'PATH':'/usr/bin:/bin'},
                **{k:os.environ.get(k,'') for k in ('SUDO_USER','SUDO_UID','SUDO_GID')}))
        try:
            end=time.monotonic()+timeout;out=bytearray();eof=False;status=None
            fd=proc.stdout.fileno()
            while True:
                need(time.monotonic()<=end,'BOOTSTRAP_TIMEOUT_UNKNOWN')
                ready=select.select([] if eof else [fd],[],[],.025)[0]
                if ready:
                    data=os.read(fd,min(4096,16385-len(out)))
                    if data:out.extend(data);need(len(out)<=16384,'BOOTSTRAP_OUTPUT_LIMIT')
                    else:eof=True
                status=self.s.child_status(proc)  # original WNOWAIT PID binding
                if status is not None and eof:break
            need(status.si_code==os.CLD_EXITED and status.si_status==0,'BOOTSTRAP_CHILD_FAILED')
            return bytes(out)
        finally:
            try:self.s.finish_child(proc)  # original bounded owned-group cleanup
            finally:proc.stdout.close()
    def call(self,raw):
        self.gate()
        reply=self.s.exact_json(self.capture_bootstrap(['/bin/sh',INPUT+'/prepare-site.sh',self.phase,sha(raw)],timeout=300))
        self.gate()
        if self.phase=='install':
            need(reply=={'stage':'install','carrier_manifest_sha256':self.s.CARRIER_MANIFEST,'update_executed':False},'INSTALL_RESULT_UNKNOWN')
        else:
            expected={'stage':'image-load','image':self.s.NEW_IMAGE,'service_changed':False}
            need(reply==expected or reply==dict(expected,existing_exact_image_reused=True),'IMAGE_RESULT_UNKNOWN')
        return reply
    def archive_permit(self,raw):
        need(self.s.read(BASE+'/'+PERMIT,16384)==raw,'PERMIT_CHANGED')
        self.write(self.parent,'site-prepare-approval.'+self.phase+'.json',raw)
        # Only our exact completed phase record may be retired. Never replace an
        # unknown active permit or erase a failed/partial attempt.
        need(self.s.read(BASE+'/'+PERMIT,16384)==raw,'PERMIT_CHANGED');self.gate()
        need(self.s.identity(os.stat(PERMIT,dir_fd=self.parent,follow_symlinks=False))==self.permit_identity,'PERMIT_IDENTITY_CHANGED')
        now=clock();need(self.issued<=now<=self.deadline and now<EXPIRES,'STAGE_APPROVAL_EXPIRED')
        os.unlink(PERMIT,dir_fd=self.parent);self.gate();os.fsync(self.parent)
    def run(self):
        try:
            self.preflight();self.confirm('install')
            self.write(self.parent,ATTEMPT,canonical({'format':1,'scope_sha256':self.scope,'operator':self.operator,
                'kind':'MANUAL_SUDO_ACTION_RECORD_NOT_SERVERTRUST','delivery_manifest_sha256':self.manifest_sha256,'original_source':SOURCE,'started_at':self.issued}))
            self.stage_inputs();raw=self.permit();reply=self.call(raw)
            self.write(self.parent,'stage-a-install-result.json',canonical(reply));self.archive_permit(raw)
            self.confirm('image-load');raw=self.permit();reply=self.call(raw)
            self.write(self.parent,'stage-a-image-load-result.json',canonical(reply));self.archive_permit(raw)
            return {'state':'STAGE_A_ORIGINAL_CALLER_COMPLETED','image':self.s.NEW_IMAGE,
                'site_update':False,'private_data':False,'ocr_enabled':False,'servertrust':False}
        finally:self.close()

def run(blobs,manifest_sha256):
    # Verified wrapper calls this only after exact full-package/input checks.
    try:
        result=StageA(blobs,manifest_sha256).run();print(json.dumps(result,sort_keys=True));return 0
    except BaseException:
        print('{"state":"HOLD_STAGE_A_PRESERVE_NO_RETRY","site_update":false,"servertrust":false}');return 2

if __name__=='__main__':
    print('{"state":"STAGE_A_DEFAULT_DISABLED","site_executed":false}');raise SystemExit(2)
