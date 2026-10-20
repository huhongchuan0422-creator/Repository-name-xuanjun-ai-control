sudo -n /usr/bin/python3 -I -B -S - <<'B5_RETAINED_CANDIDATE'
import os,sys,json,signal,base64,hashlib
from urllib.request import build_opener,ProxyHandler
try:
    if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or sys.version_info[:3]!=(3,6,8):
        raise RuntimeError('HOLD_FIXED_HOST_ROOT_PYTHON368')
    def deadline(signum,frame):raise RuntimeError('HOLD_SOURCE_FETCH_DEADLINE')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(45)
    url='https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/git/blobs/897a47af10c63d446306aca726f5fbdd303ff7a6'
    with build_opener(ProxyHandler({})).open(url,timeout=30) as response:
        envelope=response.read(131073)
    if len(envelope)>131072:raise RuntimeError('HOLD_SOURCE_RESPONSE_BOUND')
    data=json.loads(envelope.decode('utf8'))
    if data.get('encoding')!='base64' or data.get('sha')!='897a47af10c63d446306aca726f5fbdd303ff7a6' or data.get('size')!=42663:
        raise RuntimeError('HOLD_SOURCE_GIT_BINDING')
    raw=base64.b64decode(''.join(data['content'].splitlines()),validate=True)
    if len(raw)!=42663 or hashlib.sha256(raw).hexdigest()!='8d76be9bbf136ffec7ad9c98d141b6fd904d24458e4e68219e19dc6aa7220770':
        raise RuntimeError('HOLD_SOURCE_SHA')
    signal.alarm(0)
except Exception as exc:
    print(json.dumps({'state':'HOLD_SOURCE_NOT_STARTED','error':type(exc).__name__,'sdk':'NOT_EXECUTED'}));raise SystemExit(2)
exec(compile(raw,'<sha256-verified-b5-retained-bootstrap>','exec'),{'__name__':'__main__'})
B5_RETAINED_CANDIDATE
