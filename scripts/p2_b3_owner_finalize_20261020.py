"""Python3.6.8 host producer. PREPARATION ONLY; run only after Owner approval."""
import argparse
import base64
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import uuid

HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE='/var/lib/xuanjun-p2-isolated-test'
ROOT=BASE+'/b3-initialize'
INPUT=BASE+'/b3-ledger-final-20261020'
IMAGE='sha256:5341f193a5741b64f2acc63a99dc95910289fcc39ff17dacff373a50e233724d'
REQUEST_SHA='199938d73d46f5a841cd56f5f51f814256b28bdc5c7cc88d43e3ff07226ee5b9'
CP03_SHA='bede2ebc9f9c5458c92307c974358eb61947e7ec80a9611cc76735891ffae433'
PROBE_SHA='3bd3db756c5ad10711083682009247f25014088ce694523a55d0eb4742096081'
RUNTIME='evidence/p2-epoch7-access-repair-20261014/runtime/stage1'


def need(ok,code):
    if not ok:raise ValueError(code)


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode('ascii')
def digest(raw):return hashlib.sha256(raw).hexdigest()


def read(path,limit=4194304):
    p=Path(path);need(p.is_absolute() and '..' not in p.parts,'ABSOLUTE_PATH')
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            os.close(parent);parent=child
        fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as f:
            a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_size<=limit,'REGULAR_BOUND')
            raw=f.read(limit+1);b=os.fstat(f.fileno())
            fields=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
            need(all(getattr(a,k)==getattr(b,k) for k in fields) and len(raw)==a.st_size,'READ_CHANGED')
            return raw
    finally:os.close(parent)


def sync(path):
    fd=os.open(str(path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def directory(path,mode=0o700):
    path=Path(path)
    if not os.path.lexists(str(path)):path.mkdir(mode=mode);sync(path.parent)
    s=os.lstat(str(path))
    need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==mode,'DIRECTORY_PROTECTION')


def publish(path,raw,mode=0o444):
    path=Path(path)
    if os.path.lexists(str(path)):
        s=os.lstat(str(path));need(stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid()
             and stat.S_IMODE(s.st_mode)==mode and read(path)==raw,'IMMUTABLE_CONFLICT');return
    pending=path.parent/('.'+path.name+'.pending-'+uuid.uuid4().hex)
    fd=os.open(str(pending),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.link(str(pending),str(path));sync(path.parent)


def unpack(raw,expected_sha,stage):
    need(digest(raw)==expected_sha,'BUNDLE_SHA')
    packet=json.loads(raw.decode('ascii'))
    need(set(packet)=={'schema','tar_sha256','tar_bytes','files','tar_b64'} and packet['schema']==1,'BUNDLE_FIELDS')
    archive=base64.b64decode(packet['tar_b64'].encode('ascii'),validate=True)
    need(len(archive)==packet['tar_bytes'] and digest(archive)==packet['tar_sha256'],'TAR_SHA')
    manifest=packet['files'];need(isinstance(manifest,dict) and len(manifest)<=256,'MANIFEST_BOUND')
    total=0;seen=set();directory(stage)
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as t:
        members=t.getmembers();need(len(members)<=512,'TAR_MEMBER_BOUND')
        for item in members:
            p=PurePosixPath(item.name)
            need(not p.is_absolute() and '..' not in p.parts and str(p)==item.name.rstrip('/'),'TAR_PATH')
            need(item.isdir() or item.isfile(),'TAR_SPECIAL_FILE')
            if item.isdir():continue
            need(item.name not in seen and item.name in manifest and item.size<=4194304,'TAR_FILE')
            seen.add(item.name);total+=item.size;need(total<=33554432,'TAR_TOTAL_BOUND')
            content=t.extractfile(item).read(4194305);spec=manifest[item.name]
            need(set(spec)=={'bytes','sha256'} and len(content)==spec['bytes']==item.size
                 and digest(content)==spec['sha256'],'MANIFEST_FILE_SHA')
            target=Path(stage).joinpath(*p.parts)
            cursor=Path(stage)
            for part in p.parts[:-1]:
                cursor=cursor/part
                if not os.path.lexists(str(cursor)):directory(cursor)
                else:
                    s=os.lstat(str(cursor));need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid()
                         and stat.S_IMODE(s.st_mode) in (0o700,0o555),'STAGED_DIRECTORY')
            publish(target,content)
    need(seen==set(manifest),'MANIFEST_MISSING')
    # Only this new exact staging tree is changed; no existing application path.
    folders=[Path(stage)]+[p for p in Path(stage).rglob('*') if p.is_dir()]
    for p in sorted(folders,key=lambda x:len(x.parts),reverse=True):os.chmod(str(p),0o555)
    return manifest


def meta(path):
    s=os.lstat(str(path))
    return {k:getattr(s,'st_'+k) for k in ('dev','ino','uid','gid','mode','mtime_ns','ctime_ns')}


def snapshot(target):
    files={}
    for name in ('CP07-committed.json','ledger-config.json','profile.json','runtime-invocation.json','expected-identity.json'):
        p=Path(target)/name;files[name]={'sha256':digest(read(p)),'metadata':meta(p)}
    return {'target':meta(target),'files':files}


def prior_snapshot(root):
    result={}
    for p in sorted(Path(root).iterdir()):
        if p.name=='prepared':continue
        if p.name=='activation':
            need(p.is_dir() and not p.is_symlink(),'CP03_ACTIVATION_DIRECTORY')
            for f in sorted(p.iterdir()):result[str(f)]=(digest(read(f)),meta(f))
        else:result[str(p)]=(digest(read(p)),meta(p))
    need(len(result)==(6 if str(root).startswith('/tmp/p2-b3-test-host-') else 10),'CP03_ORIGINAL_FILE_COUNT')
    return result


def command(argv,logs,label,input_bytes=None,timeout=120):
    token=uuid.uuid4().hex
    out=Path(logs)/(label+'-'+token+'.stdout');err=Path(logs)/(label+'-'+token+'.stderr')
    with out.open('xb') as o,err.open('xb') as e:
        try:p=subprocess.run(argv,input=input_bytes,stdout=o,stderr=e,timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ValueError('COMMAND_TIMEOUT_RETAIN_LOGS:'+label)
    a=read(out,1048576);b=read(err,1048576)
    return p.returncode,a,b


def inspect_container(name,logs):
    code,out,err=command(['/bin/docker','inspect',name],logs,'inspect-'+name)
    if code:
        need(b'No such object' in err or b'No such container' in err,'DOCKER_INSPECT_FAILED')
        return None
    rows=json.loads(out.decode());need(len(rows)==1,'INSPECT_COUNT');return rows[0]


def options(user):
    return ['--hostname='+HOST,'--user='+user,'--network=none','--cap-drop=ALL',
            '--security-opt=no-new-privileges','--read-only','--pids-limit=96',
            '--memory=512m','--memory-swap=1g',
            '--tmpfs=/root:rw,nosuid,nodev,size=128m,mode=0700',
            '--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777']


def run_container(name,step,argv,mounts,user,image,stdin,logs,producer_sha,request_sha=REQUEST_SHA):
    labels={'xuanjun.b3.request':request_sha,'xuanjun.b3.producer':producer_sha,
            'xuanjun.b3.step':step,'xuanjun.b3.stdin':digest(stdin)}
    create=['/bin/docker','create','--name='+name,'--interactive']+options(user)
    for key,value in sorted(labels.items()):create+=['--label='+key+'='+value]
    if user=='1002:1002':create+=['--env=PYTHONPATH=/tools','--workdir=/tools']
    for source,dest,readonly in mounts:
        create+=['--mount=type=bind,src='+source+',dst='+dest+(',readonly' if readonly else '')]
    create+=[image]+argv
    planned=digest(canonical(create))
    publish(Path(logs)/(step+'-intent.json'),canonical({'command_sha256':planned,'stdin_sha256':digest(stdin),'argv':create}))
    current=inspect_container(name,logs)
    if current is None:
        code,out,err=command(create,logs,'create-'+step);need(code==0,'CREATE_FAILED_RETAIN_LOGS')
        current=inspect_container(name,logs)
    need(current is not None and current['Image']==image and current['Config']['Cmd']==argv
         and current['Config']['User']==user and all(current['Config']['Labels'].get(k)==v for k,v in labels.items()),'CONTAINER_IDENTITY')
    h=current['HostConfig']
    need(h['NetworkMode']=='none' and h['ReadonlyRootfs'] is True and h['CapDrop']==['ALL']
         and h['SecurityOpt']==['no-new-privileges'] and h['Memory']==536870912
         and h['PidsLimit']==96,'CONTAINER_ISOLATION')
    observed={(m['Source'],m['Destination'],not m['RW']) for m in current['Mounts'] if m['Type']=='bind'}
    need(observed==set(mounts) and all(m['Type'] in ('bind','tmpfs') for m in current['Mounts']), 'CONTAINER_MOUNTS')
    try:
        if current['State']['Status']=='created':
            command(['/bin/docker','start','--attach','--interactive',current['Id']],logs,'start-'+step,stdin)
        elif current['State']['Running']:
            command(['/bin/docker','wait',current['Id']],logs,'wait-'+step)
    except ValueError:
        # Only the previously verified owned container is stopped on timeout.
        command(['/bin/docker','stop','--time','5',current['Id']],logs,'stop-owned-'+step,timeout=15)
        raise
    current=inspect_container(name,logs)
    need(current['State']['Running'] is False and current['State']['Status']=='exited','CONTAINER_NOT_TERMINAL')
    unused,out,err=command(['/bin/docker','logs',current['Id']],logs,'logs-'+step)
    lines=[line for line in out.splitlines() if line.strip()]
    need(bool(lines),'CONTAINER_RESULT_MISSING')
    result=json.loads(lines[-1].decode('utf-8'))
    return result,current,planned


def install(stage,work,logs,root,image,python,producer_sha,fixture=False):
    # fixture is Python-test-only and unavailable from the host CLI.
    if fixture:need(str(root).startswith('/tmp/p2-b3-test-host-'),'FIXTURE_SCOPE')
    else:need((str(root),str(work),image,python)==(ROOT,INPUT,IMAGE,'/usr/bin/python3.11'),'FIXED_SCOPE')
    req=read(Path(stage)/'docs/p2-b3-ledger-20261020/request.json',65536)
    request=json.loads(req.decode());request_sha=digest(canonical(request))
    if not fixture:need(request_sha==REQUEST_SHA and digest(read(Path(root)/'commit-receipt.json'))==CP03_SHA,'FIXED_REQUEST_CP03')
    original=prior_snapshot(root);proof=Path(work)/'proof.json';target=Path(root)/'prepared'
    shared=[(str(stage),'/tools',True),(str(Path(stage)/RUNTIME),'/application/stage1',True),
            (str(root),str(root),False),(str(Path(root)/'activation'),str(Path(root)/'activation'),True),
            (str(Path(root)/'binding-config.json'),str(Path(root)/'binding-config.json'),True),
            (str(Path(root)/'commit-receipt.json'),str(Path(root)/'commit-receipt.json'),True)]
    records=[]
    def worker(action,suffix,include_proof=True):
        mounts=list(shared)
        if include_proof and proof.exists():mounts.append((str(proof),'/observer/proof.json',True))
        argv=[python,'-B','-S','-m','production.p2_install.b3_ledger',action,'--request-sha256',request_sha]
        r,c,unused=run_container('p2-b3-final-'+suffix,suffix,argv,mounts,'1002:1002',image,req,logs,producer_sha,request_sha)
        need(prior_snapshot(root)==original,'CP03_CHANGED')
        records.append({'action':action,'container_id':c['Id'],'exit_code':c['State']['ExitCode'],'result':r})
        return r
    result=worker('execute','execute',False)
    if result['status']!='PREPARATION_COMMITTED' and not proof.exists():
        need(result['status']=='HOLD' and result.get('stage')=='CP08'
             and result['completed']==['CP04','CP05','CP06','CP07'] and not result.get('error'), 'INITIAL_EXECUTE_HOLD')
        before=snapshot(target)
        cp07=json.loads(read(target/'CP07-committed.json').decode())
        need(cp07['request_sha256']==request_sha and cp07['stage']=='CP07'
             and cp07['status']=='PREPARATION_CHECKPOINT_COMMITTED','CP07_RECEIPT')
        context={'request_sha256':request_sha,'cp03_sha256':digest(read(Path(root)/'commit-receipt.json')),
                 'cp07_sha256':before['files']['CP07-committed.json']['sha256'],'host_path':str(target)}
        probe=Path(stage)/'production/p2_install/cp08_probe.py'
        need(digest(read(probe))==PROBE_SHA,'PROBE_SOURCE_SHA')
        argv=[python,'-I','-B','-S','/probe/probe.py']
        mounts=[(str(target),'/target',True),(str(probe),'/probe/probe.py',True)]
        observed,c,planned=run_container('p2-b3-final-observe','observe',argv,mounts,'65534:65534',image,
            canonical(dict(context,metadata=before['target'])),logs,producer_sha,request_sha)
        after=snapshot(target);need(before==after and prior_snapshot(root)==original,'OBSERVER_CHANGED_STATE')
        h=c['HostConfig']
        packet={'schema':1,'producer_sha256':producer_sha,'probe_sha256':PROBE_SHA,'context':context,
                'before':before,'after':after,'probe':observed,'command_sha256':planned,
                'container':{'id':c['Id'],'image':image,'user':c['Config']['User'],'network':h['NetworkMode'],
                   'readonly_root':h['ReadonlyRootfs'],'cap_drop':h['CapDrop'],'security_opt':h['SecurityOpt'],
                   'running':c['State']['Running'],'exit_code':c['State']['ExitCode'],'command_sha256':planned,
                   'mounts':{'/target':{'source':str(target),'readonly':True},
                             '/probe/probe.py':{'readonly':True,'sha256':PROBE_SHA}}}}
        # Validate using the same pinned verifier without granting UID1002 the
        # ability to produce or replace the host-owned proof transport.
        import types
        verifier=types.ModuleType('cp08_host_verifier')
        exec(compile(read(Path(stage)/'production/p2_install/cp08_evidence.py'),'<pinned-cp08-verifier>','exec'),verifier.__dict__)
        verifier.validate(packet,context,after,image=image)
        publish(proof,canonical(packet))
    first=worker('recover','recover-1');need(first['status']=='PREPARATION_COMMITTED','RECOVER_NOT_COMMITTED')
    inspected=worker('inspect','inspect');again=worker('recover','recover-2')
    need(inspected['status']==again['status']=='PREPARATION_COMMITTED'
         and first['receipt']==inspected['receipt']==again['receipt'],'RESTART_RECEIPT_CONFLICT')
    summary={'schema':1,'scope':'ISOLATED_TEST_ONLY','status':'PREPARATION_COMMITTED',
             'request_sha256':request_sha,'producer_sha256':producer_sha,'records':records,
             'receipt':first['receipt'],'proof_sha256':digest(read(proof)),
             'cp03_unchanged':True,'full_b3_complete':False,'service_started':False,'production_permission':False}
    publish(Path(work)/'summary.json',canonical(summary))
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--bundle-sha256',required=True)
    args=p.parse_args()
    need(os.getuid()==os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST,'UK_ROOT_REQUIRED')
    os.umask(0o077)
    lock=os.open(BASE+'/state/.formal-cli.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        s=os.fstat(lock);need(s.st_uid==0 and stat.S_ISREG(s.st_mode)
             and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'FORMAL_LOCK')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        directory(INPUT);directory(INPUT+'/logs')
        stage=Path(INPUT)/'sources'
        if not stage.exists() or stat.S_IMODE(os.lstat(str(stage)).st_mode)==0o700:unpack(read(args.bundle,2097152),args.bundle_sha256,stage)
        else:
            # Verification-only reuse of a completely sealed staging tree.
            packet=json.loads(read(args.bundle,2097152).decode());need(digest(read(args.bundle,2097152))==args.bundle_sha256,'BUNDLE_SHA')
            for path,spec in packet['files'].items():need(digest(read(stage/path))==spec['sha256'],'STAGED_FILE_SHA')
        producer=digest(read(Path(__file__).absolute()))
        need(read(stage/'scripts/p2_b3_owner_finalize_20261020.py')==read(Path(__file__).absolute()),'PRODUCER_SOURCE_IDENTITY')
        code,out,err=command(['/bin/docker','image','inspect',IMAGE,'--format','{{.Id}}'],INPUT+'/logs','image')
        need(code==0 and out.decode().strip()==IMAGE,'FIXED_IMAGE_UNAVAILABLE')
        summary=install(stage,INPUT,INPUT+'/logs',ROOT,IMAGE,'/usr/bin/python3.11',producer)
        print(json.dumps(summary,sort_keys=True));return 0
    finally:os.close(lock)


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'status':'HOLD_RETAINED','error_type':type(exc).__name__,
              'reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,
              'full_b3_complete':False,'service_started':False},sort_keys=True));sys.exit(2)
