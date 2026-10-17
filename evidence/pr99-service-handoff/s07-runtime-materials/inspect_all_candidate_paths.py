"""Locate S07 path links using only bounded metadata; no data/config/key reads."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

STAGE=Path('/root/pr99-s07-material-launch.Fwej5Q9b/stage.py')
STAGE_SHA='0076b30aec052366ac2f7ec6adfa5ff13b9c54f21fa50221c72d9415ddfc6c7f'

def scan(paths,roots):
    links={};errors={};seen=set();visited=0
    def inspect(name):
        nonlocal visited
        p=Path(name)
        for part in list(reversed(p.parents))+[p]:
            if str(part) in links:return False
            if str(part) in errors:return False
            if str(part) in seen:continue
            seen.add(str(part));visited+=1
            if visited>20000:raise RuntimeError('METADATA_LIMIT')
            try:
                s=part.lstat()
                if stat.S_ISLNK(s.st_mode):
                    row={'path':str(part),'target':os.readlink(part),'link_device':s.st_dev,
                         'link_inode':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':oct(stat.S_IMODE(s.st_mode))}
                    try:
                        resolved=part.resolve(strict=True);t=resolved.stat()
                        row.update(resolved_target=str(resolved),target_device=t.st_dev,target_inode=t.st_ino,
                                   target_uid=t.st_uid,target_gid=t.st_gid,target_mode=oct(stat.S_IMODE(t.st_mode)))
                    except OSError as e:row['target_error']=type(e).__name__
                    links[str(part)]=row
                    return False
            except OSError as e:errors[str(part)]={'path':str(part),'error':type(e).__name__};return False
        return True
    for name in paths:inspect(name)
    for name in roots:
        if not inspect(name):continue
        for current,dirs,files in os.walk(name,followlinks=False):
            dirs[:]=[d for d in dirs if inspect(str(Path(current)/d))]
            for f in files:inspect(str(Path(current)/f))
    return {'status':'S07_BOUNDED_PATH_METADATA_COMPLETE','links':list(links.values()),
            'missing_or_denied':list(errors.values()),'metadata_entries':visited,
            'business_file_contents_read':False,'database_opened':False,'service_actions':0}

def main():
    assert os.geteuid()==0 and os.uname().nodename=='iZmj7a5kwr75qc1tul4kf9Z'
    log=Path('/root/pr99-s07-private-materials-v1/ssh-private.log')
    if log.is_file():
        for line in log.read_bytes()[-32768:].decode('utf-8','replace').splitlines():
            m=re.match(r'^\s*File "([^"]+)", line ([0-9]+), in ([A-Za-z0-9_<>]+)$',line)
            if m:
                print(json.dumps({'private_log_frame_line':int(m.group(2)),'function':m.group(3)}),flush=True)
    raw=STAGE.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==STAGE_SHA
    stage={'__name__':'staging_functions','__file__':str(STAGE)}
    exec(compile(raw,str(STAGE),'exec'),stage)
    helper=Path('/root/pr99-s07-runtime-inventory.8no57zD5/inspect.py')
    raw=stage['read_file'](helper,100000)
    assert hashlib.sha256(raw).hexdigest()=='295b3e4df882793978042edcb3222c1068c493a9a33e47370ae8558d37095134'
    ns={'__name__':'inventory_functions','__file__':str(helper)}
    exec(compile(raw,str(helper),'exec'),ns)
    old=ns['load_pinned'](ns['ORIGINAL'],ns['ORIGINAL_SHA'])
    package=old['stable'](ns['PACKAGE'],64*1024*1024)
    assert ns['digest'](package)==ns['PACKAGE_SHA']
    plan,sources=old['unpack'](package,ns['PACKAGE_SHA'])
    assert len(sources)==79
    root=stage['ROOT']
    paths=[str(root/n) for n in sources]+[str(root/n) for n in stage['EXACT']+(stage['DB'],)]
    paths+=list(stage['EXTERNAL'])+['/root']+['/etc/systemd/system/'+u for u in stage['UNITS']]
    roots=[str(root/n) for n in stage['DIRS']]
    remote_code='import os,json,stat\nfrom pathlib import Path\n'+__import__('inspect').getsource(scan)
    remote_code+='\nassert os.geteuid()==0 and os.uname().nodename=='+repr(stage['TOKYO'])+'\n'
    remote_code+='print(json.dumps(scan('+repr(paths)+','+repr(roots)+'),sort_keys=True),flush=True)\n'
    auth=Path(tempfile.mkdtemp(prefix='pr99-s07-all-path-check-',dir='/root'))
    (auth/'known_hosts').write_text(stage['HOST_KEY'])
    ssh=['/usr/bin/ssh','-T','-o','UserKnownHostsFile='+str(auth/'known_hosts'),
         '-o','GlobalKnownHostsFile=/dev/null','-o','StrictHostKeyChecking=yes',
         '-o','HostKeyAlgorithms=ecdsa-sha2-nistp256','-o','UpdateHostKeys=no',
         '-o','ForwardAgent=no','-o','ForwardX11=no','-o','ClearAllForwardings=yes',
         '-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2',
         'root@47.245.53.152','/usr/bin/python3.11 -I -B -']
    print('请输入东京root密码；本次仅目录/文件身份与符号链接元数据，不复制业务材料。',flush=True)
    subprocess.run(ssh,input=remote_code.encode(),check=True,timeout=180)

if __name__=='__main__':main()
