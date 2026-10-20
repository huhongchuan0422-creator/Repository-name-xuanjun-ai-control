"""Proposed fixed UK UID1002 SDK metadata read. No Node/loader execution or writes."""
import hashlib,json,os,pwd,re,socket,stat,sys
HOME='/home/xuanjun_dev'
NODE=HOME+'/.openclaw/tools/node-v24.21.0/bin/node'
ROOT=HOME+'/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw'
LOADER=ROOT+'/dist/loader-runtime-load-DpgEqnzx.mjs'
PINS={ROOT+'/package.json':'214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95',
 LOADER:'3c30c5d43fb3cd19525853bb6b756cf45cfd05f5da32a732dc129b85cb309787',
 ROOT+'/dist/context-DyPstb2Q.mjs':'db7fc7539455da0c564d4ded0d04da1c764a46903d1632489b8bd04641098320'}


def check(ok,reason):
    if not ok:raise ValueError(reason)


def read_metadata(path,maximum,retain=False):
    check(os.path.realpath(path)==path,'SDK_PATH_ALIAS')
    parents=[];parent=os.path.dirname(path)
    while True:
        s=os.lstat(parent);within=parent==HOME or parent.startswith(HOME+'/')
        check(stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022 and
              (s.st_uid==0 or (within and s.st_uid==1002)),'SDK_PARENT')
        if parent in (HOME,HOME+'/.openclaw'):check(s.st_uid==1002,'SDK_HOME_IDENTITY')
        parents.append((parent,s))
        if parent=='/':break
        parent=os.path.dirname(parent)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        a=os.fstat(stream.fileno())
        check(stat.S_ISREG(a.st_mode) and a.st_uid in (0,1002) and a.st_nlink==1
              and not a.st_mode&0o022 and a.st_size<=maximum,'SDK_FILE')
        h=hashlib.sha256();chunks=[];total=0
        while True:
            raw=stream.read(min(65536,maximum+1-total))
            if not raw:break
            total+=len(raw);check(total<=maximum,'SDK_SIZE_BOUND');h.update(raw)
            if retain:chunks.append(raw)
        b=os.fstat(stream.fileno());fields=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        check(total==a.st_size and all(getattr(a,k)==getattr(b,k) for k in fields),'SDK_CHANGED')
    s=os.lstat(path);check(all(getattr(s,k)==getattr(b,k) for k in fields) and os.path.realpath(path)==path,'SDK_PATH_CHANGED')
    for parent,old in parents:
        current=os.lstat(parent)
        check(all(getattr(current,k)==getattr(old,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode')),'SDK_PARENT_CHANGED')
    return {'path':path,'bytes':total,'sha256':h.hexdigest(),'uid':a.st_uid,'gid':a.st_gid,
            'mode':oct(stat.S_IMODE(a.st_mode))},b''.join(chunks)


def loader_exports(raw):
    result={}
    for block in re.findall(rb'export\s*\{([^}]{0,32768})\}',raw):
        for item in block.decode('ascii','ignore').split(','):
            match=re.fullmatch(r'\s*([A-Za-z_$][A-Za-z0-9_$]*)(?:\s+as\s+([A-Za-z_$][A-Za-z0-9_$]*))?\s*',item)
            if match and match.group(1) in ('loadOpenClawPlugins','loadPluginRegistryHandle','loadAndActivateRootPluginRegistry'):
                result[match.group(1)]=match.group(2) or match.group(1)
    return result


def main():
    check(socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
          and os.getuid()==os.geteuid()==1002 and pwd.getpwuid(1002).pw_name=='xuanjun_dev','FIXED_UK_UID1002_REQUIRED')
    check(sys.version_info[:3]==(3,6,8),'HOST_PYTHON368_REQUIRED')
    rows=[];exports={};package=None
    for path in [NODE]+sorted(PINS):
        try:
            info,raw=read_metadata(path,512*1024*1024 if path==NODE else 8*1024*1024,retain=path!=NODE)
            if path in PINS:check(info['sha256']==PINS[path],'SDK_HISTORICAL_PIN_CHANGED')
            info['state']='READ_ONLY_MEASURED';rows.append(info)
            if path==LOADER:exports=loader_exports(raw)
            if path==ROOT+'/package.json':
                value=json.loads(raw.decode('utf8'));package={'version':value.get('version'),'engines':value.get('engines'),
                       'dependencies':sorted(value.get('dependencies',{}))}
        except Exception as exc:rows.append({'path':path,'state':'UNKNOWN','error_type':type(exc).__name__,
                                            'reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__})
    print(json.dumps({'scope':'ISOLATED_TEST_ONLY_DEPENDENCY_METADATA','files':rows,'loader_exports':exports,
       'openclaw_package':package,'node_version_execution':'NOT_EXECUTED','transitive_closure':'UNKNOWN',
       'loader_execution':'NOT_EXECUTED','cp11':'NOT_EXECUTED','model_calls':0,'writes':'NONE_BY_SCRIPT',
       'limit':'reads may update filesystem atime; no current SDK source is printed'},sort_keys=True))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'state':'HOLD','reason':str(exc),'loader_execution':'NOT_EXECUTED'},sort_keys=True));sys.exit(2)
