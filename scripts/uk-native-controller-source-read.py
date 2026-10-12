"""Read fixed installed controller code as data; no inference or mutation."""
import os,pwd,socket,stat,json,hashlib,re
def main():
    if socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid:
        raise SystemExit('HOLD_FIXED_UK_NONROOT')
    paths=['/home/xuanjun_dev/.openclaw/workspace/scripts/p2_supervisor.py','/home/xuanjun_dev/.openclaw/bin/openclaw']
    records=[]
    for requested in paths:
        path=os.path.realpath(requested)
        if not path.startswith('/home/xuanjun_dev/.openclaw/'):
            records.append({'path':requested,'state':'OUTSIDE_CODE_ROOT'});continue
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size>131072:
                records.append({'path':requested,'state':'NONREGULAR_OR_OVERSIZE'});continue
            raw=os.read(fd,131073)
        finally:os.close(fd)
        try:source=raw.decode('utf-8')
        except UnicodeDecodeError:
            records.append({'path':requested,'state':'BINARY_METADATA_ONLY','resolved':path});continue
        if re.search(r'-----BEGIN .*PRIVATE KEY|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{30,}|[0-9]{6,}:[A-Za-z0-9_-]{25,}|sk-[A-Za-z0-9]{32,}',source):
            records.append({'path':requested,'state':'SECRET_PATTERN_BLOCKED'});continue
        records.append({'path':requested,'resolved':path,'sha256':hashlib.sha256(raw).hexdigest(),'uid':info.st_uid,'mode':oct(stat.S_IMODE(info.st_mode)),'source':source})
    root='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist'
    selected=[];scanned=0
    code_paths=[]
    for directory,folders,files in os.walk(root,followlinks=False):
        depth=os.path.relpath(directory,root).count(os.sep)
        folders[:]=[f for f in sorted(folders) if depth<5 and f not in ('node_modules','__pycache__')]
        for name in sorted(files):
            path=os.path.join(directory,name)
            if name.endswith(('.js','.mjs')) and any(w in path[len(root):] for w in ('gateway','agent','automation','schema','protocol')):code_paths.append(path)
        if len(code_paths)>3000:break
    for path in code_paths:
        info=os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size>4000000:continue
        if scanned+info.st_size>48000000:break
        scanned+=info.st_size
        with open(path,'r',encoding='utf-8') as f:body=f.read()
        if re.search(r'-----BEGIN .*PRIVATE KEY|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{30,}|[0-9]{6,}:[A-Za-z0-9_-]{25,}|sk-[A-Za-z0-9]{32,}',body):continue
        snippets=[]
        for word in ('AgentParamsSchema','AgentWaitParamsSchema','runEmbeddedPiAgent','expectedRevision','automations.scratch','agentHandlers','registerGatewayMethod'):
            start=body.find(word)
            if start>=0:snippets.append({'symbol':word,'source':body[max(0,start-1000):start+5000]})
        if snippets:selected.append({'path':path,'sha256':hashlib.sha256(body.encode()).hexdigest(),'snippets':snippets})
        if len(selected)>=14:break
    records.append({'gateway_code_snippets':selected,'bytes_scanned':scanned,'code_candidates':len(code_paths),'directory_names':sorted(os.listdir(root))[:30]})
    print(json.dumps({'state':'READONLY_CODE_EXPORT','model_calls':0,'authority_mutation':'NONE','sources':records},sort_keys=True))
if __name__=='__main__':main()
