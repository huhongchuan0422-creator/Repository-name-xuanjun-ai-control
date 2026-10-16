"""Bounded Owner-mediated Tokyo -> Korea private S07 material staging.
No application imports, API calls, service actions, proxy changes or activation.
Contains private credentials/data: never upload the generated archive or manifest.
The live SQLite backup is a preliminary point, not final cutover state.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import signal
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

KOREA='iZmj7a5kwr75qc1tul4kf9Z'
TOKYO='iZ6wee8q9z4t03hvqumwfhZ'
LOCAL=Path('/root/pr99-s07-private-materials-v2')
HOST_KEY='47.245.53.152 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBMfngQ3DTnuC8aP0TZ0fBhcq+8p7Yw0c7VEYKWSpFrtpqWf+shoFTiyrAWj1OlrnoeOlsZq1SS1zOavODbJOnzs=\n'
ROOT=Path('/opt/trading-system')
DIRS=('runtime/secure-secrets-portal',
 'runtime/v8-domestic-operations/operations-secretref-store',
 'runtime/v8-domestic-operations/wecom-customer-contact',
 'runtime/v8-domestic-operations/wecom-customer-service')
EXACT=('knowledge/data/production_knowledge_v1.json','config/model_provider_rate_cards.json')
EXTERNAL=('/home/admin/.openclaw/workspace/xuanjun-agent-coordination/CUSTOMER_REFERRAL_CONFIG.json',
 '/home/openclaw_ops/v8-domestic-operations/config/customer-referral/CUSTOMER_REFERRAL_CONFIG.json')
DB='database/data/trading.db'
UNITS=('secure-secrets-portal.service','xuanjun-wecom-customer-contact.service','xuanjun-wecom-customer-service.service')
LIMIT=256*1024*1024


def need(v,code):
    if not v:raise RuntimeError(code)


def sha(b):return hashlib.sha256(b).hexdigest()


def read_plain_file(p,limit=64*1024*1024):
    for parent in p.parents:
        need(not parent.is_symlink(),'SYMLINK_PARENT')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        a=os.fstat(f.fileno())
        need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_size<=limit,'SOURCE_FILE_TYPE_OR_SIZE')
        b=f.read(limit+1);z=os.fstat(f.fileno())
    c=p.lstat()
    need(len(b)==a.st_size and all(getattr(a,k)==getattr(z,k)==getattr(c,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')),'SOURCE_CHANGED_DURING_READ')
    return b



# One observed alias is permitted ONLY for the exact referral JSON, never a tree.
REFERRAL_ALIAS = Path('/home/admin/.openclaw/workspace')
REFERRAL_TARGET = Path('/mnt/btrfs-workspace/ws-398ab6')
REFERRAL_SUFFIX = Path('xuanjun-agent-coordination/CUSTOMER_REFERRAL_CONFIG.json')

def referral_binding():
    for p in REFERRAL_ALIAS.parents:
        z=p.lstat()
        need(stat.S_ISDIR(z.st_mode) and not stat.S_ISLNK(z.st_mode),'REFERRAL_ALIAS_PARENT_CHANGED')
    a=REFERRAL_ALIAS.lstat()
    need(stat.S_ISLNK(a.st_mode) and
         (a.st_dev,a.st_ino,a.st_uid,a.st_gid,stat.S_IMODE(a.st_mode)) ==
         (64771,654102,1000,1000,0o777),'REFERRAL_LINK_IDENTITY_CHANGED')
    need(os.readlink(REFERRAL_ALIAS)==str(REFERRAL_TARGET),'REFERRAL_LINK_TEXT_CHANGED')
    need(REFERRAL_ALIAS.resolve(strict=True)==REFERRAL_TARGET,'REFERRAL_LINK_TARGET_CHANGED')
    for p in REFERRAL_TARGET.parents:
        z=p.lstat()
        need(stat.S_ISDIR(z.st_mode) and not stat.S_ISLNK(z.st_mode),'REFERRAL_TARGET_PARENT_CHANGED')
    b=REFERRAL_TARGET.lstat()
    need(stat.S_ISDIR(b.st_mode) and
         (b.st_dev,b.st_ino,b.st_uid,b.st_gid,stat.S_IMODE(b.st_mode)) ==
         (37,259,1000,1000,0o755),'REFERRAL_TARGET_IDENTITY_CHANGED')
    return tuple(getattr(v,k) for v in (a,b) for k in
                 ('st_dev','st_ino','st_uid','st_gid','st_mode','st_mtime_ns','st_ctime_ns'))

def read_file(p,limit=64*1024*1024):
    if p == REFERRAL_ALIAS/REFERRAL_SUFFIX:
        before=referral_binding()
        data=read_plain_file(REFERRAL_TARGET/REFERRAL_SUFFIX,limit)
        need(referral_binding()==before,'REFERRAL_BINDING_CHANGED_DURING_READ')
        return data
    return read_plain_file(p,limit)

def require_prior_failure():
    prior=Path('/root/pr99-s07-private-materials-v1')
    need(json.loads(read_plain_file(prior/'failure.json',20000)) ==
         {'status':'HOLD_PRESERVE_NO_RETRY'},'PRIOR_FAILURE_RECORD_CHANGED')
    need(not os.path.lexists(prior/'receipt.json'),'PRIOR_STAGE_ALREADY_SUCCEEDED')
    need(read_plain_file(prior/'materials.tar',1)==b'','PRIOR_PARTIAL_ARCHIVE_NONEMPTY')
    log=read_plain_file(prior/'ssh-private.log',10000)
    need(b'RuntimeError: SYMLINK_PARENT' in log,'PRIOR_FAILURE_CAUSE_CHANGED')


def unit_gate(expected):
    result={}
    for unit in UNITS:
        r=subprocess.run(['/usr/bin/systemctl','show',unit,'--no-pager',
            '--property=FragmentPath,DropInPaths,EnvironmentFiles,User,Group,WorkingDirectory,MainPID'],capture_output=True,timeout=15,check=True)
        props=dict(x.split('=',1) for x in r.stdout.decode().splitlines() if '=' in x)
        path=Path(props['FragmentPath'])
        need(str(path).startswith(('/etc/systemd/system/','/usr/lib/systemd/system/')),'UNIT_FRAGMENT_ROOT')
        need(not props.get('DropInPaths') and not props.get('EnvironmentFiles'),'UNRECEIVED_UNIT_OVERRIDES')
        need(props.get('User')=='admin' and props.get('Group')=='admin' and props.get('WorkingDirectory')==str(ROOT),'SERVICE_IDENTITY_DRIFT')
        need(sha(read_file(path,200000))==expected[unit],'CURRENT_UNIT_CHANGED')
        result[unit]=props
    return result


def enumerate_files():
    found={};absent=[]
    for name in DIRS:
        root=ROOT/name
        if not root.exists():absent.append(name);continue
        need(root.is_dir() and not root.is_symlink(),'RUNTIME_ROOT_TYPE')
        for current,dirs,files in os.walk(root,followlinks=False):
            for n in dirs:
                need(not (Path(current)/n).is_symlink(),'RUNTIME_SYMLINK_DIRECTORY')
            for n in files:
                p=Path(current)/n
                # Socket/device/FIFO/symlink/hardlink objects are not copied or followed.
                st=p.lstat()
                need(stat.S_ISREG(st.st_mode) and st.st_nlink==1,'RUNTIME_NONREGULAR_OBJECT')
                found['project/'+str(p.relative_to(ROOT))]=p
                need(len(found)<=10000,'RUNTIME_FILE_COUNT')
    for name in EXACT:
        p=ROOT/name
        if p.exists():found['project/'+name]=p
        else:absent.append(name)
    for i,name in enumerate(EXTERNAL):
        p=Path(name)
        if p.exists():found['referral/'+str(i)+'.json']=p
        else:absent.append('referral/'+str(i)+'.json')
    return found,absent


def remote_pack(header):
    need(os.geteuid()==0 and os.uname().nodename==TOKYO,'TOKYO_ROOT_REQUIRED')
    os.umask(0o077)
    before=unit_gate(header['unit_hashes'])
    # All selected code must still match the already received S07 source package.
    for name,expected in header['source_hashes'].items():
        p=PurePosixPath(name)
        need(not p.is_absolute() and '..' not in p.parts,'SOURCE_PATH')
        need(sha(read_file(ROOT/name))==expected,'LIVE_SOURCE_DRIFT')
    paths,absent=enumerate_files()
    need(DIRS[0] not in absent and DIRS[1] not in absent,'PORTAL_OR_CHANNEL_STORE_ABSENT')
    payload={};total=0
    for name,p in sorted(paths.items()):
        raw=read_file(p);total+=len(raw);need(total<=LIMIT,'TOTAL_MATERIAL_LIMIT');payload[name]=raw
    # Never emit a credential value. Key presence is checked privately.
    env=payload.get('project/runtime/secure-secrets-portal/credential-store.env',b'')
    need(any(line.strip().startswith(b'TRADING_CREDENTIAL_MASTER_KEY=') for line in env.splitlines()),'MASTER_KEY_FILE_BINDING_UNKNOWN')
    stage=Path(tempfile.mkdtemp(prefix='pr99-s07-private-source-v2-',dir='/root'))
    db=stage/'trading.db'
    started=time.monotonic()
    source_db=ROOT/DB
    for parent in source_db.parents:need(not parent.is_symlink(),'DATABASE_SYMLINK_PARENT')
    db_before=source_db.lstat()
    need(stat.S_ISREG(db_before.st_mode) and db_before.st_nlink==1 and db_before.st_size<=LIMIT,'DATABASE_TYPE_OR_SIZE')
    src=sqlite3.connect(source_db.as_uri()+'?mode=ro',uri=True,timeout=5)
    dest=sqlite3.connect(str(db))
    def progress(status,remaining,total):
        need(time.monotonic()-started<90,'SQLITE_BACKUP_TIMEOUT')
    try:
        src.backup(dest,pages=128,progress=progress,sleep=0.05)
        need(dest.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'SQLITE_INTEGRITY')
    finally:dest.close();src.close()
    db_after=source_db.lstat()
    need(db_before.st_dev==db_after.st_dev and db_before.st_ino==db_after.st_ino and stat.S_ISREG(db_after.st_mode) and db_after.st_nlink==1,'DATABASE_IDENTITY_CHANGED')
    payload['project/'+DB]=read_file(db,LIMIT)
    total+=len(payload['project/'+DB]);need(total<=LIMIT,'TOTAL_MATERIAL_LIMIT')
    again,absent_again=enumerate_files()
    need(set(again)==set(paths) and absent_again==absent,'RUNTIME_FILE_SET_CHANGED')
    for name,p in paths.items():need(sha(read_file(p))==sha(payload[name]),'LIVE_RUNTIME_DRIFT_PRESERVE_NO_RETRY')
    need(unit_gate(header['unit_hashes'])==before,'SERVICE_STATE_CHANGED')
    manifest={'schema_version':1,'status':'S07_PRELIMINARY_PRIVATE_MATERIALS_STAGED',
      'source_host':TOKYO,'source_stage':str(stage),'absent_optional_or_unproven_paths':absent,
      'files':{n:{'bytes':len(b),'sha256':sha(b)} for n,b in payload.items()},
      'database_integrity':'PASS','final_cutover_snapshot':False,
      'live_writer_frozen':False,'runtime_configuration_complete':False,
      'service_actions':0,'api_requests':0,'domestic_install':False}
    payload['PRIVATE_MANIFEST.json']=(json.dumps(manifest,sort_keys=True)+'\n').encode()
    # Private manifest records no credential values; source files remain private on hosts.
    (stage/'PRIVATE_MANIFEST.json').write_bytes(payload['PRIVATE_MANIFEST.json'])
    with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as tar:
        for n,b in sorted(payload.items()):
            info=tarfile.TarInfo(n);info.size=len(b);info.mode=0o400
            tar.addfile(info,io.BytesIO(b))


def allowed_name(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p)!=name:return False
    if name=='PRIVATE_MANIFEST.json' or name in ('referral/0.json','referral/1.json'):return True
    if name in {'project/'+x for x in EXACT+(DB,)}:return True
    return any(name.startswith('project/'+x+'/') for x in DIRS)


def verify_archive(path):
    rows={}
    with tarfile.open(path,'r:') as tar:
        for m in tar:
            need(m.isfile() and allowed_name(m.name) and m.name not in rows and 0<=m.size<=LIMIT,'ARCHIVE_MEMBER_REJECTED')
            need(len(rows)<10010,'ARCHIVE_COUNT_LIMIT')
            b=tar.extractfile(m).read();need(len(b)==m.size,'ARCHIVE_SHORT_MEMBER')
            rows[m.name]=(len(b),sha(b),b if m.name=='PRIVATE_MANIFEST.json' else None)
    need('PRIVATE_MANIFEST.json' in rows,'MANIFEST_MISSING')
    manifest=json.loads(rows.pop('PRIVATE_MANIFEST.json')[2])
    need(manifest['status']=='S07_PRELIMINARY_PRIVATE_MATERIALS_STAGED' and manifest['source_host']==TOKYO,'MANIFEST_SCOPE')
    need({n:{'bytes':r[0],'sha256':r[1]} for n,r in rows.items()}==manifest['files'],'MANIFEST_MISMATCH')
    return manifest


def main():
    need(os.geteuid()==0 and os.uname().nodename==KOREA,'KOREA_ROOT_REQUIRED')
    os.umask(0o077);require_prior_failure();need(not os.path.lexists(LOCAL),'LOCAL_STAGE_EXISTS_NO_RETRY')
    # Reuse the pinned authenticated helper chain; no application code is imported.
    p=Path('/root/pr99-s07-runtime-inventory.8no57zD5/inspect.py')
    raw=read_file(p,100000)
    need(sha(raw)=='295b3e4df882793978042edcb3222c1068c493a9a33e47370ae8558d37095134','INVENTORY_HELPER_CHANGED')
    ns={'__name__':'inventory_functions','__file__':str(p)};exec(compile(raw,str(p),'exec'),ns)
    old=ns['load_pinned'](ns['ORIGINAL'],ns['ORIGINAL_SHA'])
    package=old['stable'](ns['PACKAGE'],64*1024*1024)
    need(sha(package)==ns['PACKAGE_SHA'],'PACKAGE_CHANGED')
    plan,sources=old['unpack'](package,ns['PACKAGE_SHA']);need(len(sources)==79,'SOURCE_COUNT')
    header={'unit_hashes':dict(zip(UNITS,('3023bd5152e1bc26f35cea3ee1cf8196a67c69a736faad7ecf53887882dad0a7','f855698347cc734112d6abd102773eb1a39444a332a90a503f8a4f746ecec5aa','53669b3e6e5646f22b512df5e9dd14feef0796fcd0ac4cb336161c83aa876791'))),
      'source_hashes':{n:sha(b) for n,b in sources.items()}}
    # Current unit arguments must not silently override inventoried storage roots.
    resolver=ns['load_pinned'](ns['RESOLVER'],ns['RESOLVER_SHA'])
    projection,collector=resolver['bootstrap']()
    receipt=json.loads(collector['stable_file'](projection['ROOT']/'receipt.json',20000,private=True))
    files=collector['verify_archive'](collector['stable_file'](projection['ROOT']/'payload.tar.gz',4*1024*1024+65536,private=True),receipt)
    for unit in UNITS:
        unitraw=files['units/'+unit];need(sha(unitraw)==header['unit_hashes'][unit],'UNIT_BINDING')
        fields=resolver['unit_service'](unitraw)
        need(not fields.get('EnvironmentFile') and not fields.get('LoadCredential'),'UNIT_PRIVATE_OVERRIDE_UNKNOWN')
        for line in fields.get('ExecStart',[]):
            args=shlex.split(line)
            need(not any(x.startswith(('--state-root','--runtime-root','--secret-root','--database')) for x in args),'UNIT_STORAGE_OVERRIDE_REQUIRES_PLAN')
    auth=Path(tempfile.mkdtemp(prefix='pr99-s07-material-auth-',dir='/root'))
    (auth/'known_hosts').write_text(HOST_KEY)
    ssh=['/usr/bin/ssh','-T','-S',str(auth/'socket'),'-o','ControlMaster=auto','-o','ControlPersist=900',
      '-o','UserKnownHostsFile='+str(auth/'known_hosts'),'-o','GlobalKnownHostsFile=/dev/null',
      '-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ecdsa-sha2-nistp256','-o','UpdateHostKeys=no',
      '-o','ForwardAgent=no','-o','ForwardX11=no','-o','ClearAllForwardings=yes',
      '-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2']
    remote='root@47.245.53.152'
    try:
        print('请输入东京root密码；仅私有暂存S07材料，不停止或启动服务。',flush=True)
        subprocess.run(ssh+['-n',remote,'test "$(hostname -s)" = '+TOKYO+' && test "$(id -u)" = 0'],check=True,timeout=180)
        LOCAL.mkdir(mode=0o700)
        selfraw=read_file(Path(__file__).absolute(),100000)
        bootstrap='import base64,json; n={"__name__":"private_stage_functions"};exec(base64.b64decode('+repr(base64.b64encode(selfraw).decode())+'),n);n["remote_pack"](json.loads('+repr(json.dumps(header))+'))'
        command='/usr/bin/python3.11 -I -B -u -c '+shlex.quote(bootstrap)
        with (LOCAL/'materials.tar').open('xb') as out,(LOCAL/'ssh-private.log').open('xb') as err:
            proc=subprocess.Popen(ssh+['-n','-o','BatchMode=yes',remote,command],stdin=subprocess.DEVNULL,stdout=out,stderr=err)
            deadline=time.monotonic()+600
            while True:
                try:proc.wait(timeout=15);break
                except subprocess.TimeoutExpired:
                    print('S07_PRIVATE_MATERIAL_STAGE_PROGRESS',flush=True)
                    if time.monotonic()>deadline:
                        proc.terminate();proc.wait(timeout=15);raise RuntimeError('REMOTE_RESULT_UNKNOWN_PRESERVE')
                    if out.tell()>LIMIT+16*1024*1024:
                        proc.terminate();proc.wait(timeout=15);raise RuntimeError('TRANSFER_LIMIT_PRESERVE')
            need(proc.returncode==0,'REMOTE_STAGE_FAILED_PRIVATE_LOG_PRESERVED')
        manifest=verify_archive(LOCAL/'materials.tar')
        (LOCAL/'PRIVATE_MANIFEST.json').write_text(json.dumps(manifest,sort_keys=True)+'\n')
        result={'status':'S07_PRIVATE_MATERIALS_RECEIVED_PRELIMINARY_PASS',
          'files':len(manifest['files']),'bytes':sum(x['bytes'] for x in manifest['files'].values()),
          'database_integrity':'PASS','file_hashes':'PASS','source_code_79_hashes':'PASS',
          'current_three_unit_hashes':'PASS','private_credentials_preserved':True,
          'runtime_configuration_complete':False,'final_cutover_snapshot':False,
          'services_installed':False,'service_actions':0,'api_requests':0,'production_cutover':False,'tokyo_retirement':'HOLD'}
        (LOCAL/'receipt.json').write_text(json.dumps(result,sort_keys=True)+'\n')
        print(json.dumps(result,sort_keys=True),flush=True)
    except BaseException:
        if LOCAL.is_dir():(LOCAL/'failure.json').write_text('{"status":"HOLD_PRESERVE_NO_RETRY"}\n')
        raise
    finally:
        try:subprocess.run(ssh+['-O','exit',remote],capture_output=True,timeout=10)
        except (OSError,subprocess.TimeoutExpired):pass

if __name__=='__main__':
    try:main()
    except BaseException as e:
        reason=str(e) if isinstance(e,RuntimeError) and str(e).replace('_','').isalnum() and len(str(e))<120 else type(e).__name__
        print('S07_PRIVATE_STAGE_HOLD='+reason+' PRESERVE_NO_RETRY',flush=True);raise SystemExit(2)
