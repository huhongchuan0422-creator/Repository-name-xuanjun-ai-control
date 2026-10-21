sudo -n /usr/bin/python3 -I -B -S - <<'B5_PAIR_IMPLEMENTATION_CANDIDATE'
import os,sys,json,signal,base64,hashlib
from urllib.request import build_opener,ProxyHandler
try:
    if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or sys.version_info[:3]!=(3,6,8):
        raise RuntimeError('HOLD_FIXED_HOST_ROOT_PYTHON368')
    def deadline(signum,frame):raise RuntimeError('HOLD_SOURCE_FETCH_DEADLINE')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(45)
    url='https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/git/blobs/fbc2e1037c5c688bc3d2b1fb9ec96e5c7d39eb3e'
    with build_opener(ProxyHandler({})).open(url,timeout=30) as response:
        envelope=response.read(131073)
    if len(envelope)>131072:raise RuntimeError('HOLD_SOURCE_RESPONSE_BOUND')
    data=json.loads(envelope.decode('utf8'))
    if data.get('encoding')!='base64' or data.get('sha')!='fbc2e1037c5c688bc3d2b1fb9ec96e5c7d39eb3e' or data.get('size')!=44413:
        raise RuntimeError('HOLD_SOURCE_GIT_BINDING')
    raw=base64.b64decode(''.join(data['content'].splitlines()),validate=True)
    if len(raw)!=44413 or hashlib.sha256(raw).hexdigest()!='5fb267b1a5539d61ea3fe43f28815dd82822fc8b6f18a98a1118a31971bfdf5f':
        raise RuntimeError('HOLD_SOURCE_SHA')
    signal.alarm(0)
except Exception as exc:
    print(json.dumps({'state':'HOLD_SOURCE_NOT_STARTED','error_type':type(exc).__name__,'error':str(exc)[:300],'http_status':getattr(exc,'code',None),'errno':getattr(exc,'errno',None),'sdk':'NOT_EXECUTED'}));raise SystemExit(2)
exec(compile(raw,'<sha256-verified-b5-retained-bootstrap>','exec'),{'__name__':'__main__'})
B5_PAIR_IMPLEMENTATION_CANDIDATE
