"""Stdlib-only root bootstrap: authenticate bytes before importing candidate code.

No CLI test-root/pin override. This source is not an installation permission.
Owner-root must independently pin this script's SHA before first execution.
"""
import argparse
import hashlib
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request

HOST = 'iZmj7a5kwr75qc1tul4kf9Z'
ACTION = 'PR99_PHASE_C_OFFLINE_CANDIDATE_INSTALL_V1'
PIN = Path('/etc/xuanjun-pr99-release/phase-c-offline-install-admission.json')
STAGING = Path('/var/lib')  # Never put trusted imported code below world-writable /tmp.
PREFIX = 'migration-prep/korea/phase_c/'
ENV = {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'}


def require(value, reason):
    if not value: raise ValueError(reason)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(pairs):
        out={}
        for key,value in pairs:
            require(key not in out,'DUPLICATE_JSON_FIELD');out[key]=value
        return out
    return json.loads(raw,object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def trusted_directory(path):
    require(path.is_absolute() and '..' not in path.parts,'ABSOLUTE_PATH')
    for p in reversed((path,)+tuple(path.parents)):
        s=p.lstat()
        require(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'UNTRUSTED_DIRECTORY')


def read(path, modes=(0o400,0o600), limit=2097152):
    path=Path(path);trusted_directory(path.parent)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s=os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and
                stat.S_IMODE(s.st_mode) in modes and 0<s.st_size<=limit,'FILE_IDENTITY')
        chunks=[];size=0
        while True:
            chunk=os.read(fd,min(65536,limit+1-size))
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
            require(size<=limit,'FILE_SIZE')
        after=os.fstat(fd)
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
        require(all(getattr(s,k)==getattr(after,k) for k in fields),'FILE_CHANGED')
        return b''.join(chunks)
    finally:os.close(fd)


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def validate(raw, plan_raw, pin, helper_raw, now):
    require(set(pin)=={'approval_comment_id','approval_body_sha256','approval_body'} and
            type(pin['approval_comment_id']) is int and pin['approval_comment_id']>0 and
            type(pin['approval_body']) is str and sha(pin['approval_body'].encode())==pin['approval_body_sha256'],
            'ROOT_PIN')
    begin='<!-- PR99_PHASE_C_ROOT_APPROVAL_V1\n';end='\nPR99_PHASE_C_ROOT_APPROVAL_V1 -->'
    body=pin['approval_body']
    require(body.count(begin)==body.count(end)==1 and body.index(begin)<body.index(end),'APPROVAL_MARKER')
    approval=parse(body.split(begin)[1].split(end)[0])
    expected=dict(schema_version=1,decision='APPROVED_WITH_EXACT_PRECONDITIONS',host=HOST,action=ACTION,
        max_attempts=1,artifact_sha256=sha(raw),plan_sha256=sha(plan_raw),handoff_sha256=sha(helper_raw),
        create_dedicated_worker_allowed=True,service_start_allowed=False,network_changes_allowed=False,
        credentials_allowed=False,database_export_allowed=False,writer_allowed=False)
    require(set(approval)==set(expected)|{'source_commit','controller_sha256','approval_comment_id','issued_at','expires_at'},
            'APPROVAL_FIELDS')
    for key,value in expected.items():require(type(approval[key]) is type(value) and approval[key]==value,'APPROVAL_SCOPE')
    require(approval['approval_comment_id']==pin['approval_comment_id'] and
            type(approval['approval_comment_id']) is int and
            type(approval['issued_at']) is int and type(approval['expires_at']) is int and
            approval['issued_at']<=now<approval['expires_at'] and
            0<approval['expires_at']-approval['issued_at']<=43200,'APPROVAL_TIME_ID')
    require(re.fullmatch(r'[0-9a-f]{40}',approval['source_commit']),'SOURCE_COMMIT')
    files={}
    require(0<len(raw)<=2097152,'ARCHIVE_SIZE')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
        expanded=compressed.read(16*1024*1024+1)
    require(len(expanded)<=16*1024*1024,'ARCHIVE_EXPANSION_LIMIT')
    with tarfile.open(fileobj=io.BytesIO(expanded),mode='r:') as archive:
        for m in archive:
            p=PurePosixPath(m.name)
            require(len(files)<64 and m.type in (tarfile.REGTYPE,tarfile.AREGTYPE) and p.as_posix()==m.name and not p.is_absolute() and
                    '..' not in p.parts and m.name not in files and 0<m.size<=1048576,'ARCHIVE_MEMBER')
            require(m.name in ('REVIEW_BINDING.json','PHASE_C_RUNTIME_MANIFEST.json') or
                    m.name.startswith('migration-prep/'),'ARCHIVE_SCOPE')
            files[m.name]=archive.extractfile(m).read()
    binding=parse(files['REVIEW_BINDING.json'])
    require(binding['source_commit']==approval['source_commit'] and
            binding['production_authorized'] is False and
            set(files)==set(binding['files'])|{'REVIEW_BINDING.json'},'BINDING')
    for name,digest in binding['files'].items():require(sha(files[name])==digest,'BOUND_FILE_HASH')
    require(files[PREFIX+'root_handoff.py']==helper_raw and
            sha(files[PREFIX+'install_controller.py'])==approval['controller_sha256'],'EXECUTION_CODE_PIN')
    return files,approval


def current_body(comment_id):
    url='https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/issues/comments/'+str(comment_id)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url,timeout=20) as response:raw=response.read(200001)
    require(0<len(raw)<=200000,'CURRENT_APPROVAL_SIZE')
    record=parse(raw)
    require(type(record['id']) is int and record['id']==comment_id,'CURRENT_APPROVAL_ID')
    return record['body']


def extract_new(files, stage):
    for name,raw in files.items():
        p=PurePosixPath(name)
        require(type(raw) is bytes and p.as_posix()==name and not p.is_absolute() and '..' not in p.parts,
                'EXTRACTION_PATH')
    trusted_directory(stage.parent)
    stage.mkdir(mode=0o700);os.chmod(stage,0o700);sync(stage.parent)
    for name,raw in sorted(files.items()):
        target=stage/name
        target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        trusted_directory(target.parent)
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as out:
            out.write(raw);out.flush();os.fchmod(out.fileno(),0o400);os.fsync(out.fileno())
    for folder in sorted((p for p in stage.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):sync(folder)
    sync(stage)


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--plan',required=True)
    args=p.parse_args(argv)
    require(os.geteuid()==0 and os.uname().nodename==HOST and sys.version_info[:2]==(3,11),'ROOT_HOST_PYTHON')
    require(set(os.environ)<={'PATH','LANG','LC_ALL','LC_CTYPE'} and all(os.environ.get(k)==v for k,v in ENV.items()) and
            all(os.environ.get(k,'C') in ('C','C.UTF-8','C.utf8') for k in ('LC_ALL','LC_CTYPE')),'CLEAN_ENV')
    os.umask(0o077)
    helper=read(Path(__file__),modes=(0o400,0o600,0o644))
    trusted_directory(PIN.parent);require(stat.S_IMODE(PIN.parent.stat().st_mode)==0o700,'PIN_DIRECTORY_MODE')
    pin=parse(read(PIN,modes=(0o600,),limit=110000))
    raw=read(Path(args.archive));plan_raw=read(Path(args.plan),limit=65536)
    files,approval=validate(raw,plan_raw,pin,helper,time.time())
    require(current_body(approval['approval_comment_id'])==pin['approval_body'],'CURRENT_APPROVAL_CHANGED')
    stage=STAGING/('pr99-c-root-handoff-'+str(approval['approval_comment_id']))
    require(time.time()<approval['expires_at'],'APPROVAL_EXPIRED_BEFORE_STAGE')
    extract_new(files,stage)  # no candidate import before immutable exact extraction
    code="import sys;sys.path.insert(0,sys.argv[1]);from korea.phase_c.install_controller import main;raise SystemExit(main(sys.argv[2:]))"
    with (stage/'install.log').open('xb') as log:
        result=subprocess.run([sys.executable,'-I','-B','-u','-c',code,str(stage/'migration-prep'),
            '--archive',args.archive,'--plan',args.plan],stdout=log,stderr=log,env=ENV,timeout=240)
    print(json.dumps({'install_exit':result.returncode,'logs':str(stage/'install.log'),
                      'service_started':False,'retry_allowed':False},sort_keys=True))
    return result.returncode


if __name__=='__main__':
    try:status=main()
    except BaseException as error:
        print(json.dumps({'status':'HOLD_PRESERVE_EVIDENCE','error_type':type(error).__name__,'retry_allowed':False}),flush=True)
        sys.exit(2)
    else:sys.exit(status)
