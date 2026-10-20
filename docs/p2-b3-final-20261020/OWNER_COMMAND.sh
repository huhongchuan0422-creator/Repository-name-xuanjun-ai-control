# Pending Owner confirmation. Do not execute as part of source delivery.
sudo -n /usr/bin/python3 -I -B -S - <<'PY'
import os,stat,json,hashlib,fcntl,subprocess,uuid
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
assert os.getuid()==os.geteuid()==0
assert os.uname().nodename.split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
os.umask(0o077)
base=Path('/var/lib/xuanjun-p2-isolated-test')
assert os.path.realpath(str(base))==str(base)
info=os.lstat(str(base))
assert stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700
work=base/'b3-ledger-final-20261020'
lock=os.open(str(base/'state/.formal-cli.lock'),os.O_RDWR|os.O_NOFOLLOW)
try:
    info=os.fstat(lock)
    assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if not os.path.lexists(str(work)):work.mkdir(mode=0o700)
    info=os.lstat(str(work))
    assert stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700
    prefix='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'
    items=[
      ('p2_b3_owner_finalize_20261020.py','701113c7c453ef16cfa39b72dcd0f8c80b088f0b/scripts/p2_b3_owner_finalize_20261020.py','91e77a767752f3714cd670e41ae6eebf6c834707b016b59a9fbe81cab344b753'),
      ('p2-b3-final-bundle.json','5d8eeac0d39e9eb513c3bb0df8abc69fdf074c78/docs/p2-b3-final-20261020/p2-b3-final-bundle.json','acc3befbf0031cdee8bedbf87524c1840d44e8682ba9418f21949963f39c28d5')]
    opener=build_opener(ProxyHandler({}))
    for name,relative,pin in items:
        path=work/name
        if os.path.lexists(str(path)):
            fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600 and info.st_size<=2097152
                raw=stream.read(2097153)
        else:
            with opener.open(prefix+relative,timeout=30) as response:raw=response.read(2097153)
            assert len(raw)<=2097152 and hashlib.sha256(raw).hexdigest()==pin
            fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream:
                os.fchmod(stream.fileno(),0o600)
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
        assert len(raw)<=2097152 and hashlib.sha256(raw).hexdigest()==pin
    fd=os.open(str(work),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
finally:os.close(lock)
token=uuid.uuid4().hex
stdout=work/('bootstrap-'+token+'.stdout')
stderr=work/('bootstrap-'+token+'.stderr')
with stdout.open('xb') as out,stderr.open('xb') as err:
    try:
        result=subprocess.run(['/usr/bin/python3','-I','-B','-S',str(work/items[0][0]),
            '--bundle',str(work/items[1][0]),'--bundle-sha256',items[1][2]],
            stdout=out,stderr=err,timeout=900)
        code=result.returncode
    except subprocess.TimeoutExpired:code=124
print(stdout.read_text(errors='replace')[-50000:])
print(stderr.read_text(errors='replace')[-20000:])
print(json.dumps({'wrapper_exit_code':code,'stdout':str(stdout),'stderr':str(stderr),
 'production_activated':False,'scope':'ISOLATED_TEST_ONLY',
 'timeout_state':'UNKNOWN_RETAINED' if code==124 else 'NOT_TIMED_OUT'},sort_keys=True))
PY
