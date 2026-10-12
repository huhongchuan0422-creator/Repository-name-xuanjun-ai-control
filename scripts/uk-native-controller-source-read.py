"""Read fixed installed controller code as data; no inference or mutation."""
import os,pwd,socket,stat,json,hashlib,re
def main():
    if socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid:
        raise SystemExit('HOLD_FIXED_UK_NONROOT')
    paths=['/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/context-Dt2Gy7El.mjs']
    records=[]
    for requested in paths:
        path=os.path.realpath(requested)
        if not path.startswith('/home/xuanjun_dev/.openclaw/'):
            records.append({'path':requested,'state':'OUTSIDE_CODE_ROOT'});continue
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size>1048576:
                records.append({'path':requested,'state':'NONREGULAR_OR_OVERSIZE'});continue
            raw=os.read(fd,1048577)
        finally:os.close(fd)
        try:source=raw.decode('utf-8')
        except UnicodeDecodeError:
            records.append({'path':requested,'state':'BINARY_METADATA_ONLY','resolved':path});continue
        if re.search(r'-----BEGIN .*PRIVATE KEY|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{30,}|[0-9]{6,}:[A-Za-z0-9_-]{25,}|sk-[A-Za-z0-9]{32,}',source):
            records.append({'path':requested,'state':'SECRET_PATTERN_BLOCKED'});continue
        records.append({'path':requested,'resolved':path,'sha256':hashlib.sha256(raw).hexdigest(),'uid':info.st_uid,'mode':oct(stat.S_IMODE(info.st_mode)),'source':source})
    print(json.dumps({'state':'READONLY_CODE_EXPORT','model_calls':0,'authority_mutation':'NONE','sources':records},sort_keys=True))
if __name__=='__main__':main()
