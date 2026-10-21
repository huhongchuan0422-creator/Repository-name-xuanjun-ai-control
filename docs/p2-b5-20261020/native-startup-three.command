sudo -n /usr/bin/python3 -I -B -S - <<'B5_NATIVE_STARTUP_THREE_CANDIDATE'
import os,sys,json,signal,base64,hashlib
from urllib.request import build_opener,ProxyHandler
try:
    if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or sys.version_info[:3]!=(3,6,8):
        raise RuntimeError('HOLD_FIXED_HOST_ROOT_PYTHON368')
    def deadline(signum,frame):raise RuntimeError('HOLD_SOURCE_FETCH_DEADLINE')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(45)
    url='https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/git/blobs/e44f0e6e34eadfe2ccb2da0ef50af4ae04d9b1a3'
    with build_opener(ProxyHandler({})).open(url,timeout=30) as response:
        envelope=response.read(131073)
    if len(envelope)>131072:raise RuntimeError('HOLD_SOURCE_RESPONSE_BOUND')
    data=json.loads(envelope.decode('utf8'))
    if data.get('encoding')!='base64' or data.get('sha')!='e44f0e6e34eadfe2ccb2da0ef50af4ae04d9b1a3' or data.get('size')!=44630:
        raise RuntimeError('HOLD_SOURCE_GIT_BINDING')
    raw=base64.b64decode(''.join(data['content'].splitlines()),validate=True)
    if len(raw)!=44630 or hashlib.sha256(raw).hexdigest()!='30c6caa8e30dfe91e03dd80eb51b1d4c25931dbcb1374e08f87def3d56dd8b3c':
        raise RuntimeError('HOLD_SOURCE_SHA')
    signal.alarm(0)
except Exception as exc:
    print(json.dumps({'state':'HOLD_SOURCE_NOT_STARTED','error_type':type(exc).__name__,'error':str(exc)[:300],'http_status':getattr(exc,'code',None),'errno':getattr(exc,'errno',None),'sdk':'NOT_EXECUTED'}));raise SystemExit(2)
exec(compile(raw,'<sha256-verified-b5-retained-bootstrap>','exec'),{'__name__':'__main__'})
B5_NATIVE_STARTUP_THREE_CANDIDATE
