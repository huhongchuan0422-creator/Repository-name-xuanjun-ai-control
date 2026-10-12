"""Read installed SDK sandbox identity and hook contracts; no execution."""
import os,pwd,socket,stat,json,hashlib
def main():
    if socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid:raise SystemExit('HOLD_FIXED_UK_NONROOT')
    root='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/'
    sources=[]
    for name in ('registry-xPfhu4Rv.mjs','shared-BLNeHhmu.mjs','hooks-3uEO1KNL.mjs','agent-scope-config-Dm6T00l4.mjs','setup-registry-2Voi6xC9.mjs'):
        fd=os.open(root+name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            i=os.fstat(fd)
            if not stat.S_ISREG(i.st_mode) or i.st_size>1048576:raise ValueError('HOLD_CODE_BOUND')
            raw=os.read(fd,1048577)
        finally:os.close(fd)
        sources.append({'path':root+name,'sha256':hashlib.sha256(raw).hexdigest(),'source':raw.decode('utf-8')})
    hits=[]
    for name in sorted(os.listdir(root)):
        if not name.endswith('.mjs'):continue
        info=os.lstat(root+name)
        if not stat.S_ISREG(info.st_mode) or info.st_size>1048576:continue
        with open(root+name,'r',encoding='utf-8') as f:source=f.read()
        offset=source.find('runBeforeToolCall(')
        if offset<0:offset=source.find('before_tool_call',source.find('//#region'))
        if offset>=0 and ('runBeforeToolCall(' in source or 'toolCallId' in source):
            hits.append({'path':root+name,'sha256':hashlib.sha256(source.encode()).hexdigest(),'excerpt':source[max(0,offset-500):offset+3500]})
            if len(hits)>=8:break
    print(json.dumps({'state':'READONLY_SDK_CONTRACTS','model_calls':0,'authority_mutation':'NONE','sources':sources,'hook_hits':hits},sort_keys=True))
if __name__=='__main__':main()
