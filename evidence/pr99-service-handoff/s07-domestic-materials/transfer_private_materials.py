"""Transfer the verified preliminary S07 private archive Korea -> domestic staging.
No active runtime replacement, app import, service/unit/proxy/API operation.
Generated payloads and private manifests must stay on the two hosts.
"""
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import shlex
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

KOREA='iZmj7a5kwr75qc1tul4kf9Z'
DOMESTIC='iZvt5t8tlrm8oiZ'
SOURCE=Path('/root/pr99-s07-private-materials-v2')
SOURCE_HELPER=Path('/root/pr99-s07-material-v2-launch.mgOIzkS1/stage.py')
SOURCE_SHA='137a2acea1924b4c62e43abfe6f8689c64450db868c7a216d759a16779c939b4'
ORIGINAL=Path('/root/pr99-s07-install-launch.a5NZU99H/install.py')
ORIGINAL_SHA='745c67d34cf4b0d546aee28c74c11b1586a315a03d970cbebc37508ebc61f8fd'
LOCAL=Path('/root/pr99-s07-domestic-material-transfer-v1')
REMOTE=Path('/var/lib/xuanjun-pr99-s07-private-materials-v1')
MAX_RAW=272*1024*1024
MAX_FILES=10010
HOST_KEY='47.101.152.210 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBF1HeuGyjt1sqB50tPRqy3bhKqukn2ztSk+RlcQix2J+sLAPplEMnmjG2lGQQS49KV1qNjO1itysOwlJFezlEOM=\n'

def need(v,code):
    if not v:raise RuntimeError(code)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def helper(raw,expected,name):
    need(sha(raw)==expected,'HELPER_HASH_CHANGED')
    ns={'__name__':'frozen_functions','__file__':name}
    exec(compile(raw,name,'exec'),ns)
    return ns

def decompress_checked(wire,header):
    need(len(wire)==header['wire_bytes'] and sha(wire)==header['wire_sha256'],'WIRE_DIGEST')
    with gzip.GzipFile(fileobj=io.BytesIO(wire)) as f:raw=f.read(MAX_RAW+1)
    need(len(raw)<=MAX_RAW and len(raw)==header['tar_bytes'] and sha(raw)==header['tar_sha256'],'ARCHIVE_DIGEST')
    return raw

def checked_members(raw,source):
    data={};total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tar:
        for m in tar:
            need(m.type in (tarfile.REGTYPE,tarfile.AREGTYPE) and not m.sparse and source['allowed_name'](m.name)
                 and m.name not in data and 0<=m.size<=source['LIMIT'],'MEMBER_REJECTED')
            total+=m.size;need(total<=MAX_RAW and len(data)<MAX_FILES,'MATERIAL_SIZE_OR_COUNT')
            b=tar.extractfile(m).read();need(len(b)==m.size,'MEMBER_LENGTH');data[m.name]=b
    manifest=json.loads(data.pop('PRIVATE_MANIFEST.json'))
    need(manifest['status']=='S07_PRELIMINARY_PRIVATE_MATERIALS_STAGED'
         and manifest['source_host']==source['TOKYO']
         and manifest['final_cutover_snapshot'] is False,'MANIFEST_SCOPE')
    rows={n:{'bytes':len(b),'sha256':sha(b)} for n,b in data.items()}
    need(rows==manifest['files'],'MATERIAL_MANIFEST')
    need(len(data)==165 and sum(len(b) for b in data.values())==47099890,'OWNER_POINT_CHANGED')
    need('project/'+source['DB'] in data and
         'project/runtime/secure-secrets-portal/credential-store.env' in data,'REQUIRED_MATERIAL_MISSING')
    return manifest,data

def write_new(path,raw,mode=0o400):
    with path.open('xb') as f:f.write(raw)
    path.chmod(mode)

def install_private(root,data):
    need(not os.path.lexists(root),'RECEIVED_DIRECTORY_EXISTS')
    root.mkdir(mode=0o700)
    for name,b in sorted(data.items()):
        p=PurePosixPath(name)
        need(not p.is_absolute() and '..' not in p.parts and str(p)==name and '\\' not in name,'MATERIAL_PATH')
        target=root/name
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        write_new(target,b)
    for name,b in data.items():
        target=root/name
        need(target.is_file() and not target.is_symlink() and sha(target.read_bytes())==sha(b),'INSTALLED_MATERIAL_CHANGED')

def receive(header,stream):
    need(os.geteuid()==0 and os.uname().nodename==DOMESTIC and sys.version_info[:2]==(3,11),'DOMESTIC_ROOT_PYTHON_REQUIRED')
    os.umask(0o077)
    old=helper(base64.b64decode(header['original'],validate=True),ORIGINAL_SHA,'original_installer.py')
    source=helper(base64.b64decode(header['source_helper'],validate=True),SOURCE_SHA,'material_source.py')
    old['absent'](REMOTE)
    manifest=json.loads(old['stable'](old['BASE']/'source-manifest.json',2*1024*1024))
    need(manifest==header['sources'] and len(manifest)==79,'DOMESTIC_SOURCE_MANIFEST_CHANGED')
    for name,row in manifest.items():
        p=PurePosixPath(name)
        need(not p.is_absolute() and '..' not in p.parts and str(p)==name,'DOMESTIC_SOURCE_PATH')
        need(sha(old['stable'](old['BASE']/'app'/name,row['bytes']))==row['sha256'],'DOMESTIC_SOURCE_CHANGED')
    receipt=json.loads(old['stable'](Path('/var/lib/xuanjun-pr99-s07-wheels-continuation-v1/receipt.json'),100000))
    need(receipt['status']=='DOMESTIC_S07_OFFLINE_DEPENDENCY_CONTINUATION_PASS'
         and receipt['package_sha256']==header['package_sha256'],'DEPENDENCY_RECEIPT_CHANGED')
    need(type(header['wire_bytes']) is int and 0<header['wire_bytes']<=MAX_RAW,'WIRE_SIZE')
    before=old['protected_snapshot']()
    wire=stream.read(header['wire_bytes'])
    raw=decompress_checked(wire,header)
    material,data=checked_members(raw,source)
    need(sha((json.dumps(material,sort_keys=True)+'\n').encode())==header['manifest_sha256'],'SOURCE_MANIFEST_BINDING')
    REMOTE.mkdir(mode=0o700)
    try:
        write_new(REMOTE/'protected.before.json',old['encoded'](before))
        write_new(REMOTE/'received.tar.gz',wire)
        write_new(REMOTE/'PRIVATE_MANIFEST.json',old['encoded'](material))
        install_private(REMOTE/'received',data)
        db=REMOTE/'received'/'project'/source['DB']
        c=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5)
        try:need(c.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'RECEIVED_SQLITE_INTEGRITY')
        finally:c.close()
        for name,b in data.items():need(sha(old['stable'](REMOTE/'received'/name,len(b)))==sha(b),'POSTCHECK_MATERIAL_CHANGED')
        after=old['protected_snapshot']()
        write_new(REMOTE/'protected.after.json',old['encoded'](after))
        need(before==after,'DOMESTIC_PROTECTED_STATE_CHANGED')
        result={'status':'DOMESTIC_S07_PRIVATE_MATERIALS_STAGED_PASS','files':len(data),
          'bytes':sum(len(b) for b in data.values()),'file_hashes':'PASS','database_integrity':'PASS',
          'source_code_79_hashes':'PASS','protected_state_unchanged':True,
          'tar_sha256':header['tar_sha256'],'wire_sha256':header['wire_sha256'],
          'active_runtime_replaced':False,'services_installed':False,'service_actions':0,
          'application_imports':0,'business_api_requests':0,'runtime_configuration_complete':False,
          'final_cutover_snapshot':False,'production_cutover':False,'tokyo_retirement':'HOLD'}
        write_new(REMOTE/'receipt.json',old['encoded'](result))
        print(json.dumps(result,sort_keys=True),flush=True)
    except BaseException:
        write_new(REMOTE/'failure.json',b'{"status":"HOLD_PRESERVE_NO_RETRY"}\n')
        raise

def main():
    need(os.geteuid()==0 and os.uname().nodename==KOREA,'KOREA_ROOT_REQUIRED')
    os.umask(0o077);need(not os.path.lexists(LOCAL),'LOCAL_ATTEMPT_EXISTS_NO_RETRY')
    # Load frozen helper bytes; their application/production main functions never run.
    sr=SOURCE_HELPER.read_bytes()
    source=helper(sr,SOURCE_SHA,str(SOURCE_HELPER))
    original=source['read_plain_file'](ORIGINAL,100000)
    old=helper(original,ORIGINAL_SHA,str(ORIGINAL))
    previous=json.loads(old['stable'](SOURCE/'receipt.json',100000))
    need(previous['status']=='S07_PRIVATE_MATERIALS_RECEIVED_PRELIMINARY_PASS'
         and previous['files']==165 and previous['bytes']==47099890,'SOURCE_RECEIPT_CHANGED')
    raw=old['stable'](SOURCE/'materials.tar',MAX_RAW)
    material,data=checked_members(raw,source)
    need(json.loads(old['stable'](SOURCE/'PRIVATE_MANIFEST.json',4*1024*1024))==material,'PRIVATE_SOURCE_MANIFEST_CHANGED')
    package=old['stable'](old['LOCAL_ATTEMPT']/'package.json',64*1024*1024)
    plan,files=old['unpack'](package,sha(package))
    need(len(files)==79,'SOURCE_CODE_COUNT')
    wire=gzip.compress(raw,compresslevel=6,mtime=0)
    selfraw=source['read_plain_file'](Path(__file__).absolute(),100000)
    header={'source_helper':base64.b64encode(sr).decode(),'original':base64.b64encode(original).decode(),
      'receiver':base64.b64encode(selfraw).decode(),'sources':{n:{'bytes':len(b),'sha256':sha(b)} for n,b in files.items()},
      'package_sha256':sha(package),'manifest_sha256':sha((json.dumps(material,sort_keys=True)+'\n').encode()),
      'wire_bytes':len(wire),'wire_sha256':sha(wire),'tar_bytes':len(raw),'tar_sha256':sha(raw)}
    auth=Path(tempfile.mkdtemp(prefix='pr99-s07-domestic-data-auth-',dir='/root'))
    (auth/'known_hosts').write_text(HOST_KEY)
    ssh=['/usr/bin/ssh','-T','-S',str(auth/'socket'),'-o','ControlMaster=auto','-o','ControlPersist=1200',
      '-o','UserKnownHostsFile='+str(auth/'known_hosts'),'-o','GlobalKnownHostsFile=/dev/null',
      '-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ecdsa-sha2-nistp256','-o','UpdateHostKeys=no',
      '-o','ForwardAgent=no','-o','ForwardX11=no','-o','ClearAllForwardings=yes',
      '-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2']
    remote='root@47.101.152.210'
    try:
        print('请输入国内root密码；只接收私有材料，不启动服务或切换入口。',flush=True)
        subprocess.run(ssh+['-n',remote,'test "$(hostname -s)" = '+DOMESTIC+' && test "$(id -u)" = 0'],check=True,timeout=180)
        LOCAL.mkdir(mode=0o700)
        write_new(LOCAL/'wire.bin',json.dumps(header).encode()+b'\n'+wire)
        bootstrap='import sys,json,base64;h=json.loads(sys.stdin.buffer.readline(250000));n={"__name__":"receiver_functions"};exec(base64.b64decode(h["receiver"]),n);n["receive"](h,sys.stdin.buffer)'
        command='/usr/bin/python3 -I -B -u -c '+shlex.quote(bootstrap)
        print('DOMESTIC_MATERIAL_TRANSFER_STARTED compressed_bytes='+str(len(wire)),flush=True)
        with (LOCAL/'wire.bin').open('rb') as inp,(LOCAL/'result.log').open('xb') as out,(LOCAL/'ssh-private.log').open('xb') as err:
            proc=subprocess.Popen(ssh+['-o','BatchMode=yes',remote,command],stdin=inp,stdout=out,stderr=err)
            end=time.monotonic()+600
            while True:
                try:proc.wait(timeout=15);break
                except subprocess.TimeoutExpired:
                    print('DOMESTIC_MATERIAL_TRANSFER_PROGRESS',flush=True)
                    if time.monotonic()>end:
                        proc.terminate();proc.wait(timeout=15);raise RuntimeError('REMOTE_RESULT_UNKNOWN_PRESERVE')
            need(proc.returncode==0,'REMOTE_RECEIVE_FAILED_PRESERVE_PRIVATE_LOG')
        result=old['stable'](LOCAL/'result.log',100000).decode()
        rows=[json.loads(x) for x in result.splitlines() if x.startswith('{')]
        need(rows and rows[-1]['status']=='DOMESTIC_S07_PRIVATE_MATERIALS_STAGED_PASS'
             and rows[-1]['tar_sha256']==header['tar_sha256'],'REMOTE_SUCCESS_RECEIPT_MISSING')
        write_new(LOCAL/'receipt.json',(json.dumps(rows[-1],sort_keys=True)+'\n').encode())
        print(json.dumps(rows[-1],sort_keys=True),flush=True)
    except BaseException:
        if LOCAL.is_dir():write_new(LOCAL/'failure.json',b'{"status":"HOLD_PRESERVE_NO_RETRY"}\n')
        raise
    finally:
        try:subprocess.run(ssh+['-O','exit',remote],capture_output=True,timeout=10)
        except (OSError,subprocess.TimeoutExpired):pass

if __name__=='__main__':
    try:main()
    except BaseException as e:
        reason=str(e) if isinstance(e,RuntimeError) and str(e).replace('_','').isalnum() and len(str(e))<120 else type(e).__name__
        print('S07_DOMESTIC_MATERIAL_HOLD='+reason+' PRESERVE_NO_RETRY',flush=True)
        raise SystemExit(2)
