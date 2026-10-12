"""Locate installed OpenClaw runtime dependency files by exact code symbols.

Read-only, zero model, Python 3.6.8 compatible. Emits paths and SHA256 only.
"""
from __future__ import print_function
import hashlib,json,os,pwd,socket,stat,sys

HOST='iZd7oeikknn1z21sq6ji6zZ'
USER='xuanjun_dev'
ROOT='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw'
DIST=ROOT+'/dist'
NEEDLES={
 'sandbox_prepare':b'prepareWorkspaceAuthority',
 'sandbox_context':b'resolveSandboxContext',
 'subagent_runtime':b'createGatewaySubagentRuntime',
 'request_scoped_error':b'RequestScopedSubagentRuntimeError',
 'before_tool_hook':b'before_tool_call',
}

def read(path,maximum=8*1024*1024):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum:raise ValueError('SHAPE')
        raw=b''
        while len(raw)<=maximum:
            part=os.read(fd,65536)
            if not part:break
            raw+=part
        if len(raw)>maximum:raise ValueError('LIMIT')
        return raw,info
    finally:os.close(fd)

def main():
    if socket.gethostname().split('.')[0]!=HOST or os.geteuid()!=pwd.getpwnam(USER).pw_uid:
        raise SystemExit('HOLD_FIXED_UK_IDENTITY')
    if sys.version_info[:3]!=(3,6,8):raise SystemExit('HOLD_PYTHON_VERSION')
    found={key:[] for key in NEEDLES}
    scanned=0
    for name in sorted(os.listdir(DIST)):
        if not name.endswith('.mjs'):continue
        path=os.path.join(DIST,name)
        try:raw,info=read(path)
        except (IOError,OSError,ValueError):continue
        scanned+=1
        matched=[key for key,needle in NEEDLES.items() if needle in raw]
        if matched:
            item={'path':path,'sha256':hashlib.sha256(raw).hexdigest(),
                  'uid':info.st_uid,'mode':oct(stat.S_IMODE(info.st_mode))}
            for key in matched:found[key].append(item)
    package,_=read(ROOT+'/package.json',maximum=1048576)
    package_json=json.loads(package.decode('utf-8'))
    print(json.dumps({'state':'P2_UK_OPENCLAW_DEPENDENCIES',
      'python_version':list(sys.version_info[:3]),'scanned_mjs':scanned,
      'openclaw_version':package_json.get('version'),
      'package_json_sha256':hashlib.sha256(package).hexdigest(),
      'symbols':found,'model_calls':0,'authority_mutation':'NONE'},sort_keys=True))
if __name__=='__main__':main()
