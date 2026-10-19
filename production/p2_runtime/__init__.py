"""Isolated Linux process runtime with durable ownership and recovery evidence."""
import argparse, fcntl, hashlib, json, os, re, signal, subprocess, sys, time
from pathlib import Path

MAX_LOG = 1024 * 1024
MAX_ENV = 64
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
SECRET_KEYS = ("TOKEN", "SECRET", "PASSWORD", "PRIVATE", "KEY")

class Fault(Exception):
    def __init__(self, code, reference=None):
        self.code, self.reference = code, reference
        super().__init__(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def durable(path, value, replace=True):
    payload = canonical(value)
    if not replace and path.exists():
        raise Fault("IMMUTABLE_RECEIPT_EXISTS", str(path))
    temp = path.with_name(path.name + ".tmp." + str(os.getpid()))
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload); out.flush(); os.fsync(out.fileno())
        if not replace and path.exists():
            raise Fault("IMMUTABLE_RECEIPT_EXISTS", str(path))
        os.replace(str(temp), str(path))
        dfd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        try: temp.unlink()
        except FileNotFoundError: pass

def load(path):
    if not path.exists(): return None
    if path.is_symlink() or not path.is_file(): raise Fault("UNSAFE_STATE", str(path))
    return json.loads(path.read_text())

def check_request(req):
    if not isinstance(req, dict) or req.get("schema") != 1 or req.get("scope") != "ISOLATED_TEST_ONLY":
        raise Fault("INVALID_SCOPE")
    for key in ("installation_id","batch_id","attempt_id"):
        if not isinstance(req.get(key), str) or not ID.fullmatch(req[key]): raise Fault("INVALID_ID")
    root = req.get("root")
    if not isinstance(root,str) or not os.path.isabs(root) or os.path.normpath(root)!=root or root=="/":
        raise Fault("INVALID_ROOT")
    if not isinstance(req.get("inputs"),dict): raise Fault("INVALID_INPUT")
    return Path(root)

def safe_root(path):
    cur=Path("/")
    for part in path.parts[1:]:
        cur/=part
        if cur.is_symlink(): raise Fault("SYMLINK_ROOT")
    st=path.stat()
    if not path.is_dir() or st.st_uid!=os.geteuid(): raise Fault("ROOT_UNAVAILABLE")
    if st.st_mode & 0o077: raise Fault("ROOT_NOT_PRIVATE")

def proc(pid):
    try:
        raw=Path("/proc/%d/stat"%pid).read_text()
        fields=raw.rsplit(")",1)[1].split()
        return {"pid":pid,"state":fields[0],"ppid":int(fields[1]),"pgrp":int(fields[2]),"session":int(fields[3]),"start":fields[19]}
    except (OSError,ValueError,IndexError): return None

def scan_group(pgid):
    found=[]
    procdir=Path("/proc")
    try: names=list(procdir.iterdir())
    except OSError: return None
    for p in names:
        if not p.name.isdigit(): continue
        ident=proc(int(p.name))
        if ident and ident["pgrp"]==pgid and ident["state"]!="Z":
            found.append(ident)
    return sorted(found,key=lambda x:x["pid"])

def validate_identity(entry):
    leader=proc(entry.get("pid",-1))
    if leader and leader["state"]!="Z":
        if leader["start"]!=entry.get("start") or leader["pgrp"]!=entry.get("pgid") or leader["session"]!=entry.get("session"):
            return "MISMATCH", []
    group=scan_group(entry.get("pgid",-1))
    if group is None: return "UNKNOWN", []
    if group:
        # A reused process group is unsafe unless session identity still matches the recorded session.
        if any(p["session"]!=entry.get("session") for p in group): return "MISMATCH", group
        return "LIVE", group
    return "GONE", []

def config_payload(inputs):
    argv=inputs.get("argv")
    if not isinstance(argv,list) or not argv or len(argv)>64 or any(not isinstance(x,str) or not x or "\x00" in x for x in argv):
        raise Fault("INVALID_ARGV")
    if argv[0] in ("/bin/sh","/bin/bash","sh","bash"): raise Fault("SHELL_FORBIDDEN")
    if not os.path.isabs(argv[0]) or not Path(argv[0]).is_file() or not os.access(argv[0],os.X_OK):
        raise Fault("INVALID_EXECUTABLE")
    cwd=inputs.get("cwd")
    if not isinstance(cwd,str) or not os.path.isabs(cwd) or not Path(cwd).is_dir(): raise Fault("INVALID_CWD")
    env=inputs.get("env",{})
    if not isinstance(env,dict) or len(env)>MAX_ENV: raise Fault("INVALID_ENV")
    for k,v in env.items():
        if not isinstance(k,str) or not ID.fullmatch(k) or not isinstance(v,str) or "\x00" in v: raise Fault("INVALID_ENV")
        if any(mark in k.upper() for mark in SECRET_KEYS): raise Fault("SECRET_ENV_FORBIDDEN")
    health=inputs.get("health",{"type":"process"})
    if not isinstance(health,dict) or health.get("type")!="process": raise Fault("INVALID_HEALTH")
    return {"argv":argv,"cwd":cwd,"env":env,"health":health}

def base(req,status,error=None,receipt=None):
    r={k:req[k] for k in ("schema","scope","installation_id","batch_id","attempt_id")}
    r.update({"status":status,"receipt":receipt,"error":error})
    return r

def write_receipt(req,root,kind,status,error=None):
    # Commit receipts are immutable; observations are append-only and cannot invalidate an earlier hash.
    stamp=time.time_ns()
    name=("commit" if kind=="commit" else "observe") + "-%s-%s-%d.json"%(req["batch_id"],req["attempt_id"],stamp)
    path=root/name
    body=base(req,status,error,None)
    durable(path,body,replace=False)
    return {"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}

def finish(req,root,status,code=None,reference=None,kind="observe"):
    err=None if code is None else {"code":code,"log":reference}
    rec=write_receipt(req,root,kind,status,err)
    return base(req,status,err,rec)

def log_size(path):
    try: return path.stat().st_size
    except OSError: return None

def terminate_owned(entry, timeout):
    state,group=validate_identity(entry)
    if state=="MISMATCH": return "PID_IDENTITY_MISMATCH"
    if state=="UNKNOWN": return "PROCESS_SET_UNKNOWN"
    if state=="GONE": return None
    try: os.killpg(entry["pgid"],signal.SIGTERM)
    except ProcessLookupError: pass
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        state,_=validate_identity(entry)
        if state=="GONE": return None
        if state=="MISMATCH": return "PID_IDENTITY_MISMATCH"
        if state=="UNKNOWN": return "PROCESS_SET_UNKNOWN"
        time.sleep(0.03)
    return "STOP_TIMEOUT"

def monitor(entry, logfile, timeout):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        state,group=validate_identity(entry)
        if state!="LIVE": return "HEALTH_FAILED" if state=="GONE" else ("PID_IDENTITY_MISMATCH" if state=="MISMATCH" else "PROCESS_SET_UNKNOWN")
        size=log_size(logfile)
        if size is None: return "LOG_STATE_UNKNOWN"
        if size>MAX_LOG: return "LOG_LIMIT"
        entry["members"]=[{"pid":p["pid"],"start":p["start"]} for p in group]
        time.sleep(0.03)
    return None

def execute(request): return _operate(request,"execute")
def inspect(request): return _operate(request,"inspect")
def recover(request): return _operate(request,"recover")

def _operate(req,method):
    root=check_request(req); safe_root(root)
    lock=root/".runtime.lock"
    fd=os.open(str(lock),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        return _locked(req,root,method)
    except Fault as e:
        return finish(req,root,"HOLD",e.code,e.reference) if root.exists() else base(req,"HOLD",{"code":e.code,"log":e.reference},None)
    finally: os.close(fd)

def _locked(req,root,method):
    inputs=req["inputs"]; op=inputs.get("operation","start")
    journal=root/("batch-"+req["batch_id"]+".json")
    entry=load(journal)
    if entry and entry["installation_id"]!=req["installation_id"]: return finish(req,root,"HOLD","BATCH_CONFLICT",entry.get("log"))
    if entry and entry["attempt_id"]!=req["attempt_id"]: return finish(req,root,"HOLD","ATTEMPT_CONFLICT",entry.get("log"))

    expected=None
    if op=="start":
        cfg=config_payload(inputs); expected=sha(cfg)
        if entry and entry.get("config_sha256")!=expected: return finish(req,root,"HOLD","CONFIG_CONFLICT",entry.get("log"))
    if method!="execute":
        if entry is None: return finish(req,root,"NO_EFFECT")
        state,group=validate_identity(entry) if "pid" in entry else ("GONE",[])
        if state=="MISMATCH": return finish(req,root,"HOLD","PID_IDENTITY_MISMATCH",entry.get("log"))
        if state=="UNKNOWN": return finish(req,root,"HOLD","PROCESS_SET_UNKNOWN",entry.get("log"))
        if entry["phase"]=="PREPARED":
            return finish(req,root,"HOLD","START_OUTCOME_UNKNOWN",entry.get("log"))
        if entry["phase"]=="STOPPING":
            if state=="GONE":
                entry["phase"]="STOPPED"; entry["members"]=[]; durable(journal,entry)
                return finish(req,root,"COMMITTED",kind="commit")
            return finish(req,root,"HOLD","STOP_OUTCOME_UNKNOWN",entry.get("log"))
        if entry["phase"]=="RUNNING":
            if state!="LIVE": return finish(req,root,"HOLD","RUNNING_PROCESS_MISSING",entry.get("log"))
            size=log_size(Path(entry["log"]))
            if size is None: return finish(req,root,"HOLD","LOG_STATE_UNKNOWN",entry.get("log"))
            if size>MAX_LOG:
                entry["phase"]="STOPPING"; durable(journal,entry)
                err=terminate_owned(entry,1.0)
                if err: return finish(req,root,"HOLD",err,entry.get("log"))
                entry["phase"]="STOPPED"; entry["members"]=[]; durable(journal,entry)
                return finish(req,root,"HOLD","LOG_LIMIT",entry.get("log"))
            entry["members"]=[{"pid":p["pid"],"start":p["start"]} for p in group]; durable(journal,entry)
            return finish(req,root,"COMMITTED")
        if state=="LIVE": return finish(req,root,"HOLD","UNEXPECTED_LIVE_PROCESS",entry.get("log"))
        return finish(req,root,"NO_EFFECT")

    if op not in ("start","stop"): raise Fault("INVALID_OPERATION")
    if op=="stop":
        if entry is None: return finish(req,root,"NO_EFFECT")
        if entry["phase"] not in ("RUNNING","STOPPING"): return finish(req,root,"HOLD","UNCERTAIN_JOURNAL",entry.get("log"))
        state,_=validate_identity(entry)
        if state=="MISMATCH": return finish(req,root,"HOLD","PID_IDENTITY_MISMATCH",entry.get("log"))
        if state=="UNKNOWN": return finish(req,root,"HOLD","PROCESS_SET_UNKNOWN",entry.get("log"))
        if state=="GONE":
            entry["phase"]="STOPPED"; entry["members"]=[]; durable(journal,entry)
            return finish(req,root,"COMMITTED",kind="commit")
        entry["phase"]="STOPPING"; durable(journal,entry)
        timeout=min(10.0,max(0.05,float(inputs.get("timeout",3))))
        err=terminate_owned(entry,timeout)
        if err: return finish(req,root,"HOLD",err,entry.get("log"))
        entry["phase"]="STOPPED"; entry["members"]=[]; durable(journal,entry)
        return finish(req,root,"COMMITTED",kind="commit")

    if entry:
        state,_=validate_identity(entry) if "pid" in entry else ("GONE",[])
        if entry["phase"]=="RUNNING" and state=="LIVE":
            size=log_size(Path(entry["log"]))
            if size is None: return finish(req,root,"HOLD","LOG_STATE_UNKNOWN",entry.get("log"))
            if size>MAX_LOG:
                entry["phase"]="STOPPING"; durable(journal,entry)
                err=terminate_owned(entry,1.0)
                if err: return finish(req,root,"HOLD",err,entry.get("log"))
                entry["phase"]="STOPPED"; entry["members"]=[]; durable(journal,entry)
                return finish(req,root,"HOLD","LOG_LIMIT",entry.get("log"))
            return finish(req,root,"COMMITTED")
        if entry["phase"]=="PREPARED": return finish(req,root,"HOLD","START_OUTCOME_UNKNOWN",entry.get("log"))
        if entry["phase"]=="STOPPED" and state=="GONE": return finish(req,root,"HOLD","ATTEMPT_ALREADY_USED",entry.get("log"))
        return finish(req,root,"HOLD","UNCERTAIN_PRIOR_START",entry.get("log"))

    cfg=config_payload(inputs)
    logfile=root/("run-"+req["batch_id"]+".log")
    entry={"installation_id":req["installation_id"],"batch_id":req["batch_id"],"attempt_id":req["attempt_id"],
           "phase":"PREPARED","config_sha256":sha(cfg),"argv":cfg["argv"],"cwd":cfg["cwd"],
           "env_sha256":sha(cfg["env"]),"health_sha256":sha(cfg["health"]),"log":str(logfile),"members":[]}
    durable(journal,entry)
    if logfile.exists(): return finish(req,root,"HOLD","LOG_EXISTS",str(logfile))
    fd=os.open(str(logfile),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"wb") as out:
            p=subprocess.Popen(cfg["argv"],cwd=cfg["cwd"],env=cfg["env"],stdin=subprocess.DEVNULL,
                               stdout=out,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        ident=proc(p.pid)
        if ident is None or ident["pgrp"]!=p.pid or ident["session"]!=p.pid:
            return finish(req,root,"HOLD","PROCESS_IDENTITY_UNKNOWN",str(logfile))
        entry.update({"pid":p.pid,"start":ident["start"],"pgid":ident["pgrp"],"session":ident["session"],"phase":"RUNNING"})
        durable(journal,entry)
        err=monitor(entry,logfile,min(10.0,max(0.05,float(inputs.get("timeout",2)))))
        if err:
            entry["phase"]="STOPPING"; durable(journal,entry)
            cleanup=terminate_owned(entry,1.0)
            if cleanup:
                return finish(req,root,"HOLD",cleanup,str(logfile))
            entry["phase"]="STOPPED"; entry["members"]=[]; durable(journal,entry)
            return finish(req,root,"HOLD",err,str(logfile))
        durable(journal,entry)
        return finish(req,root,"COMMITTED",kind="commit")
    except (OSError,ValueError,subprocess.SubprocessError):
        # PREPARED is intentionally retained: launch outcome cannot be inferred safely.
        return finish(req,root,"HOLD","LAUNCH_UNKNOWN",str(logfile))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("method",choices=("execute","inspect","recover"))
    parser.add_argument("--request")
    args=parser.parse_args()
    try:
        req=json.load(open(args.request)) if args.request else json.load(sys.stdin)
        value=globals()[args.method](req)
    except (Fault,OSError,ValueError,KeyError,json.JSONDecodeError) as e:
        value={"schema":1,"scope":"ISOLATED_TEST_ONLY","installation_id":None,"batch_id":None,"attempt_id":None,
               "status":"HOLD","receipt":None,"error":{"code":getattr(e,"code","INVALID_OR_UNAVAILABLE"),"log":getattr(e,"reference",None)}}
    print(json.dumps(value,sort_keys=True))
    return 0 if value["status"]!="HOLD" else 2
if __name__=="__main__": sys.exit(main())
