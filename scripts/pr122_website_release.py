#!/usr/bin/env python3
"""Receipt-bound, fail-closed PR122 offline release transaction."""
from __future__ import annotations
import argparse, base64, fcntl, hashlib, json, math, os, re, signal, stat, sys, tarfile, time, uuid
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

SOURCE_PREFIX="package/public/"
APPROVED_BASE=Path("/var/www/wenwenwenyiyiyi.work")
ID_RE=re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
MAX_DEADLINE=900.0

class Hold(RuntimeError): pass

def valid_seconds(value,name):
    if not math.isfinite(value) or value <= 0 or value > MAX_DEADLINE: raise Hold("INVALID_"+name.upper())
    return value

def valid_id(value,name):
    if not ID_RE.fullmatch(value): raise Hold("INVALID_"+name.upper())

class Deadline:
    def __init__(self,seconds): self.seconds=valid_seconds(seconds,"deadline_seconds"); self.end=0
    def __enter__(self):
        self.end=time.monotonic()+self.seconds
        if not hasattr(signal,"setitimer") or signal.getsignal(signal.SIGALRM) not in (signal.SIG_DFL,signal.SIG_IGN):
            raise Hold("HARD_DEADLINE_UNAVAILABLE")
        self.old_handler=signal.getsignal(signal.SIGALRM)
        self.old_timer=signal.setitimer(signal.ITIMER_REAL,self.seconds)
        signal.signal(signal.SIGALRM,self.alarm)
        return self
    def alarm(self,*_): raise Hold("OVERALL_DEADLINE_EXCEEDED")
    def check(self,stage):
        if time.monotonic() >= self.end: raise Hold("OVERALL_DEADLINE_EXCEEDED:"+stage)
    def __exit__(self,*_):
        signal.setitimer(signal.ITIMER_REAL,0); signal.signal(signal.SIGALRM,self.old_handler)
        if self.old_timer[0] > 0: signal.setitimer(signal.ITIMER_REAL,*self.old_timer)

def fsync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)

def digest(path,deadline=None):
    h=hashlib.sha256(); fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        while True:
            if deadline: deadline.check("DIGEST")
            chunk=os.read(fd,1024*1024)
            if not chunk: break
            h.update(chunk)
    finally: os.close(fd)
    return h.hexdigest()

def load_json(path,deadline=None):
    if path.is_symlink(): raise Hold("JSON_LINK_REJECTED")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        with os.fdopen(os.dup(fd),"r",encoding="utf-8") as f:
            if deadline: deadline.check("JSON_READ")
            value=json.load(f)
    finally: os.close(fd)
    if not isinstance(value,dict): raise Hold("JSON_OBJECT_REQUIRED")
    return value

def atomic_json(path,value):
    tmp=path.with_name("."+path.name+"."+uuid.uuid4().hex)
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        data=(json.dumps(value,indent=2,sort_keys=True)+"\n").encode()
        while data:
            written=os.write(fd,data); data=data[written:]
        os.fsync(fd)
    finally: os.close(fd)
    os.replace(tmp,path); fsync_dir(path.parent)

def safe_relative(name):
    pure=PurePosixPath(name)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts: raise Hold("UNSAFE_ARCHIVE_MEMBER_PATH")
    return Path(*pure.parts)

def secure_dir(path,mode,uid,create):
    if path.is_symlink(): raise Hold("TRUSTED_DIRECTORY_LINK_REJECTED")
    if not path.exists():
        if not create: raise Hold("TRUSTED_DIRECTORY_MISSING")
        path.mkdir(mode=mode); fsync_dir(path.parent)
    info=path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != mode:
        raise Hold("TRUSTED_DIRECTORY_IDENTITY_MISMATCH:"+str(path))

def preflight(args,creating):
    valid_id(args.transaction_id,"transaction_id"); valid_id(args.release_id,"release_id")
    valid_seconds(args.deadline_seconds,"deadline_seconds"); valid_seconds(args.lock_wait_seconds,"lock_wait_seconds")
    raw=Path(args.webroot_base)
    if raw.is_symlink() or ".." in raw.parts: raise Hold("UNSAFE_WEBROOT_BASE")
    base=raw.absolute(); uid=os.geteuid()
    if not args.allow_non_root_test and base != APPROVED_BASE: raise Hold("UNAPPROVED_WEBROOT_BASE")
    parent=base.parent
    if parent.is_symlink() or not parent.is_dir(): raise Hold("WEBROOT_PARENT_UNTRUSTED")
    p=parent.stat(follow_symlinks=False)
    if not args.allow_non_root_test and (p.st_uid != 0 or stat.S_IMODE(p.st_mode)&0o022):
        raise Hold("WEBROOT_PARENT_WRITABLE_OR_UNOWNED")
    if base.exists() or base.is_symlink(): secure_dir(base,0o755,uid,False)
    elif not creating: raise Hold("WEBROOT_BASE_MISSING")
    if creating:
        for candidate in (Path(args.bundle).absolute(),Path(args.source_archive).absolute()):
            if candidate.is_symlink() or not candidate.exists(): raise Hold("TRUSTED_INPUT_MISSING_OR_LINK")
            info=candidate.stat(follow_symlinks=False)
            if not args.allow_non_root_test and (info.st_uid != 0 or stat.S_IMODE(info.st_mode)&0o022):
                raise Hold("TRUSTED_INPUT_WRITABLE_OR_UNOWNED")
    return base,uid

@contextmanager
def lock(base,wait_seconds,deadline=None,uid=None):
    valid_seconds(wait_seconds,"lock_wait_seconds"); uid=os.geteuid() if uid is None else uid
    secure_dir(base,0o755,uid,True); path=base/".release.lock"
    if path.is_symlink(): raise Hold("LOCK_LINK_REJECTED")
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); info=os.fstat(fd)
    if info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o600: os.close(fd); raise Hold("LOCK_IDENTITY_MISMATCH")
    until=time.monotonic()+wait_seconds
    try:
        while True:
            if deadline: deadline.check("LOCK")
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); break
            except BlockingIOError:
                if time.monotonic() >= until: raise Hold("LOCK_TIMEOUT")
                time.sleep(.02)
        path_info=os.stat(path,follow_symlinks=False)
        if (path_info.st_dev,path_info.st_ino)!=(info.st_dev,info.st_ino): raise Hold("LOCK_OBJECT_REPLACED")
        yield
    finally:
        try: fcntl.flock(fd,fcntl.LOCK_UN)
        finally: os.close(fd)

def manifest_map(manifest):
    if not isinstance(manifest.get("files"),list): raise Hold("INVALID_CANDIDATE_MANIFEST")
    result={}
    for item in manifest["files"]:
        name=safe_relative(item["path"]).as_posix()
        if name in result or not re.fullmatch(r"[0-9a-f]{64}",item["sha256"]) or item["size"]<0:
            raise Hold("INVALID_CANDIDATE_MANIFEST_ENTRY")
        result[name]=item
    return result

def verify_tree(public,manifest,deadline,uid=None):
    end=deadline.end if isinstance(deadline,Deadline) else deadline
    expected=manifest_map(manifest); actual={}
    if public.is_symlink() or not public.is_dir(): raise Hold("UNSAFE_RELEASE_ROOT")
    root=public.stat(follow_symlinks=False)
    if stat.S_IMODE(root.st_mode)!=0o755 or (uid is not None and root.st_uid!=uid):
        raise Hold("RELEASE_ROOT_MODE_OR_OWNER_MISMATCH")
    for path in public.rglob("*"):
        if time.monotonic()>=end: raise Hold("OVERALL_DEADLINE_EXCEEDED:VERIFY")
        info=path.stat(follow_symlinks=False)
        if path.is_symlink() or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)): raise Hold("UNSAFE_RELEASE_OBJECT")
        if uid is not None and info.st_uid!=uid: raise Hold("RELEASE_OWNER_MISMATCH")
        if stat.S_IMODE(info.st_mode)!=(0o755 if stat.S_ISDIR(info.st_mode) else 0o644): raise Hold("RELEASE_MODE_MISMATCH")
        if stat.S_ISREG(info.st_mode):
            actual[path.relative_to(public).as_posix()]={"size":info.st_size,"sha256":digest(path,deadline if isinstance(deadline,Deadline) else None)}
    if set(actual)!=set(expected): raise Hold("RELEASE_FILE_SET_MISMATCH")
    for name,wanted in expected.items():
        if actual[name]!={"size":wanted["size"],"sha256":wanted["sha256"]}: raise Hold("RELEASE_CONTENT_MISMATCH:"+name)

def extract_source(source,public,pin,deadline):
    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd); h=hashlib.sha256()
        while True:
            deadline.check("SOURCE_DIGEST"); chunk=os.read(fd,1024*1024)
            if not chunk: break
            h.update(chunk)
        if info.st_size!=pin["source_archive_size"] or h.hexdigest()!=pin["source_archive_sha256"]:
            raise Hold("SOURCE_ARCHIVE_IDENTITY_MISMATCH")
        os.lseek(fd,0,os.SEEK_SET)
        with os.fdopen(os.dup(fd),"rb") as raw, tarfile.open(fileobj=raw,mode="r:gz") as archive:
            seen=set()
            for member in archive:
                deadline.check("EXTRACT"); safe_relative(member.name)
                if member.name in seen: raise Hold("DUPLICATE_SOURCE_MEMBER")
                seen.add(member.name)
                if not (member.isdir() or member.isfile()): raise Hold("UNSAFE_SOURCE_MEMBER_TYPE")
                if member.isfile() and member.name.startswith(SOURCE_PREFIX):
                    rel=safe_relative(member.name[len(SOURCE_PREFIX):]); target=public/rel
                    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    src=archive.extractfile(member)
                    out=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    try:
                        while True:
                            deadline.check("EXTRACT_COPY"); chunk=src.read(1024*1024)
                            if not chunk: break
                            os.write(out,chunk)
                        os.fsync(out)
                    finally: os.close(out)
    finally: os.close(fd)

def seal_tree(root,uid):
    for path in sorted(root.rglob("*"),key=lambda p:len(p.parts),reverse=True):
        if path.is_symlink(): raise Hold("UNSAFE_RELEASE_OBJECT")
        os.chown(path,uid,0 if uid==0 else os.getegid()); os.chmod(path,0o755 if path.is_dir() else 0o644)
    os.chown(root,uid,0 if uid==0 else os.getegid()); os.chmod(root,0o755)
    for path in sorted([root]+[p for p in root.rglob("*") if p.is_dir()],key=lambda p:len(p.parts),reverse=True): fsync_dir(path)

class InlineCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False); self.kind=None; self.buffer=[]; self.values={"script":[],"style":[]}; self.inline_attributes=[]
    def handle_starttag(self,tag,attrs):
        for name,value in attrs:
            if name.lower().startswith("on") or name.lower()=="style": self.inline_attributes.append({"tag":tag,"attribute":name})
        if tag in self.values and not (tag=="script" and dict(attrs).get("src")): self.kind=tag; self.buffer=[]
    def handle_data(self,data):
        if self.kind: self.buffer.append(data)
    def handle_endtag(self,tag):
        if tag==self.kind:
            self.values[tag].append("".join(self.buffer).encode()); self.kind=None; self.buffer=[]

def write_csp_metadata(public,release_root,deadline):
    hashes={"script":set(),"style":set()}; html_count=0
    for path in sorted(public.rglob("*.html")):
        deadline.check("CSP_SCAN"); parser=InlineCollector(); parser.feed(path.read_text(encoding="utf-8"))
        if parser.inline_attributes: raise Hold("INLINE_ATTRIBUTE_REQUIRES_EXPLICIT_REMEDIATION:"+path.relative_to(public).as_posix())
        html_count+=1
        for kind,values in parser.values.items():
            for value in values:
                if value: hashes[kind].add("'sha256-"+base64.b64encode(hashlib.sha256(value).digest()).decode()+"'")
    policy=("default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; "
            +"script-src 'self' "+" ".join(sorted(hashes["script"]))+"; "
            +"style-src 'self' "+" ".join(sorted(hashes["style"]))+"; "
            +"img-src 'self' data: https:; font-src 'self' data: https:; connect-src 'self' https:")
    metadata=release_root/"release-metadata"; metadata.mkdir(mode=0o700)
    (metadata/"inline-csp.conf").write_text('add_header Content-Security-Policy "'+policy+'" always;\n')
    (metadata/"inline-csp.json").write_text(json.dumps({"schema_version":1,"html_count":html_count,
        "script_hashes":sorted(hashes["script"]),"style_hashes":sorted(hashes["style"]),"policy":policy},indent=2,sort_keys=True)+"\n")
    return {"html_count":html_count,"script_hash_count":len(hashes["script"]),"style_hash_count":len(hashes["style"])}

def trusted_bundle(args,deadline):
    bundle=Path(args.bundle).absolute(); mp=bundle/"candidate-manifest.json"; sp=bundle/"source-pin.json"; pp=bundle/"PACKAGE_MANIFEST.json"
    manifest=load_json(mp,deadline); pin=load_json(sp,deadline); package=load_json(pp,deadline); manifest_map(manifest)
    files={x["path"]:x for x in package.get("files",[])}
    for name,path in (("candidate-manifest.json",mp),("source-pin.json",sp)):
        item=files.get(name)
        if not item or item["size"]!=path.stat().st_size or item["sha256"]!=digest(path,deadline):
            raise Hold("PACKAGE_MANIFEST_IDENTITY_MISMATCH:"+name)
    ids={"candidate_manifest_sha256":digest(mp,deadline),"source_pin_sha256":digest(sp,deadline),
         "package_manifest_sha256":digest(pp,deadline),"source_archive_sha256":pin["source_archive_sha256"],
         "source_archive_size":pin["source_archive_size"]}
    return manifest,pin,ids

def prepare(args,deadline=None):
    own=deadline is None; ctx=Deadline(args.deadline_seconds) if own else None
    if ctx: deadline=ctx.__enter__()
    try:
        base,uid=preflight(args,True); secure_dir(base,0o755,uid,True)
        releases,transactions=base/"releases",base/"transactions"
        secure_dir(releases,0o755,uid,True); secure_dir(transactions,0o700,uid,True)
        release=releases/args.release_id; receipt_path=transactions/(args.transaction_id+".json"); staging=base/(".staging-"+args.transaction_id)
        if any(x.exists() or x.is_symlink() for x in (release,receipt_path,staging)): raise Hold("TARGET_OR_TRANSACTION_ALREADY_EXISTS")
        manifest,pin,ids=trusted_bundle(args,deadline); source=Path(args.source_archive).absolute()
        if source.stat().st_size!=ids["source_archive_size"] or digest(source,deadline)!=ids["source_archive_sha256"]: raise Hold("SOURCE_ARCHIVE_IDENTITY_MISMATCH")
        receipt={"schema_version":2,"transaction_id":args.transaction_id,"release_id":args.release_id,"state":"PREPARE_INTENT",
                 "last_stage":"PREPARE_INTENT","release":str(release),"trusted_manifest":manifest,**ids,"residuals":[]}
        atomic_json(receipt_path,receipt)
        try:
            staging.mkdir(mode=0o700); receipt.update(last_stage="STAGING_CREATED",residuals=[str(staging)]); atomic_json(receipt_path,receipt)
            public=staging/"public"; public.mkdir(mode=0o700); extract_source(source,public,pin,deadline)
            for name,baseline in pin["overlay_baselines"].items():
                target=public/safe_relative(name); overlay=Path(args.bundle).absolute()/"overlay/public"/safe_relative(name)
                if target.is_symlink() or not target.is_file() or digest(target,deadline)!=baseline: raise Hold("OVERLAY_BASELINE_DRIFT:"+name)
                if overlay.is_symlink() or not overlay.is_file(): raise Hold("OVERLAY_MISSING:"+name)
                data_fd=os.open(overlay,os.O_RDONLY|os.O_NOFOLLOW); out=os.open(target,os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW)
                try:
                    while True:
                        deadline.check("OVERLAY_COPY"); chunk=os.read(data_fd,1024*1024)
                        if not chunk: break
                        os.write(out,chunk)
                    os.fsync(out)
                finally: os.close(data_fd); os.close(out)
            csp=write_csp_metadata(public,staging,deadline)
            seal_tree(staging,uid); verify_tree(public,manifest,deadline,uid)
            receipt.update(last_stage="SEALED_VERIFIED",csp_inventory=csp,
                           csp_include_sha256=digest(staging/"release-metadata/inline-csp.conf",deadline)); atomic_json(receipt_path,receipt)
            os.replace(staging,release); fsync_dir(releases); verify_tree(release/"public",manifest,deadline,uid)
            receipt.update(state="PREPARED",last_stage="PREPARED_COMMIT",residuals=[str(release)]); atomic_json(receipt_path,receipt); return receipt
        except BaseException as error:
            receipt.update(state="HOLD_PARTIAL",failure=type(error).__name__+":"+str(error)); atomic_json(receipt_path,receipt); raise
    finally:
        if ctx: ctx.__exit__(None,None,None)

def receipt_for(args,states,deadline,verify_release=True):
    base,uid=preflight(args,False); transactions=base/"transactions"; secure_dir(transactions,0o700,uid,False)
    path=transactions/(args.transaction_id+".json"); receipt=load_json(path,deadline)
    if receipt.get("schema_version")!=2 or receipt.get("transaction_id")!=args.transaction_id or receipt.get("release_id")!=args.release_id:
        raise Hold("RECEIPT_IDENTITY_MISMATCH")
    if receipt.get("state") not in states: raise Hold("TRANSACTION_STATE_NOT_ELIGIBLE")
    release=base/"releases"/args.release_id
    if release.is_symlink() or str(release)!=receipt.get("release") or not release.is_dir(): raise Hold("PREPARED_RELEASE_IDENTITY_DRIFT")
    if verify_release: verify_tree(release/"public",receipt["trusted_manifest"],deadline,uid)
    if args.bundle and digest(Path(args.bundle).absolute()/"candidate-manifest.json",deadline)!=receipt["candidate_manifest_sha256"]:
        raise Hold("CALLER_BUNDLE_DOES_NOT_MATCH_RECEIPT")
    return base,receipt,path,uid

def snapshot(public,deadline):
    files=[]
    for path in sorted(public.rglob("*")):
        if path.is_file() and not path.is_symlink(): files.append({"path":path.relative_to(public).as_posix(),"size":path.stat().st_size,"sha256":digest(path,deadline)})
    return {"schema_version":2,"files":files}

def activate(args,deadline=None):
    own=deadline is None; ctx=Deadline(args.deadline_seconds) if own else None
    if ctx: deadline=ctx.__enter__()
    try:
        base,r,path,uid=receipt_for(args,{"PREPARED"},deadline); target=base/"releases"/args.release_id; current=base/"current"
        if current.exists() and not current.is_symlink(): raise Hold("CURRENT_NOT_SYMLINK")
        previous=None
        if current.is_symlink():
            link=os.readlink(current); old=(base/link).resolve() if not Path(link).is_absolute() else Path(link).resolve()
            if old.parent!=(base/"releases").resolve() or old.is_symlink() or not old.is_dir(): raise Hold("PREVIOUS_POINTER_OUTSIDE_RELEASE_NAMESPACE")
            old_manifest=snapshot(old/"public",deadline); verify_tree(old/"public",old_manifest,deadline,uid)
            previous={"link":link,"release":str(old),"manifest":old_manifest}
        r.update(state="ACTIVATION_INTENT",last_stage="ACTIVATION_INTENT_DURABLE",previous_current=previous,target_current=str(target)); atomic_json(path,r)
        tmp=base/(".current-"+args.transaction_id)
        if tmp.exists() or tmp.is_symlink(): raise Hold("TEMPORARY_POINTER_EXISTS")
        os.symlink(str(target),tmp); fsync_dir(base); os.replace(tmp,current); fsync_dir(base)
        if not current.is_symlink() or current.resolve()!=target.resolve():
            r.update(state="UNKNOWN_AFTER_ACTIVATE",last_stage="POINTER_RESULT_UNKNOWN"); atomic_json(path,r); raise Hold("ACTIVATION_RESULT_UNKNOWN")
        verify_tree(target/"public",r["trusted_manifest"],deadline,uid)
        r.update(state="ACTIVATED",last_stage="ACTIVATION_COMMITTED"); atomic_json(path,r); return r
    finally:
        if ctx: ctx.__exit__(None,None,None)

def reconcile(args,deadline=None):
    own=deadline is None; ctx=Deadline(args.deadline_seconds) if own else None
    if ctx: deadline=ctx.__enter__()
    try:
        base,r,path,uid=receipt_for(args,{"ACTIVATION_INTENT","UNKNOWN_AFTER_ACTIVATE"},deadline); current=base/"current"; target=base/"releases"/args.release_id
        if current.is_symlink() and current.resolve()==target.resolve():
            r.update(state="ACTIVATED",last_stage="RECONCILED_SWITCH_COMMITTED",reconciliation="TARGET_PRESENT")
        else:
            observed=os.readlink(current) if current.is_symlink() else (None if not current.exists() else "NON_SYMLINK")
            expected=None if r.get("previous_current") is None else r["previous_current"]["link"]
            if observed!=expected:
                r.update(state="UNKNOWN_AFTER_RECONCILE",observed_current=observed); atomic_json(path,r); raise Hold("RECONCILIATION_AMBIGUOUS")
            r.update(state="PREPARED",last_stage="RECONCILED_NO_SWITCH",reconciliation="PREVIOUS_OR_ABSENT")
        atomic_json(path,r); return r
    finally:
        if ctx: ctx.__exit__(None,None,None)

def check(args,deadline=None):
    own=deadline is None; ctx=Deadline(args.deadline_seconds) if own else None
    if ctx: deadline=ctx.__enter__()
    try:
        base,r,path,uid=receipt_for(args,{"ACTIVATED"},deadline); current=base/"current"; target=base/"releases"/args.release_id
        if not current.is_symlink() or current.resolve()!=target.resolve():
            r.update(state="UNKNOWN_AFTER_CHECK",last_stage="CURRENT_RELEASE_MISMATCH"); atomic_json(path,r); raise Hold("CURRENT_RELEASE_MISMATCH")
        verify_tree(target/"public",r["trusted_manifest"],deadline,uid)
        r.update(state="CHECKED",last_stage="CHECK_COMMITTED"); atomic_json(path,r)
        return {"state":"PASS","release_id":args.release_id,"candidate_manifest_sha256":r["candidate_manifest_sha256"]}
    except Hold as error:
        if "r" in locals() and r.get("state")=="ACTIVATED":
            r.update(state="CHECK_FAILED",failure=str(error)); atomic_json(path,r)
        raise
    finally:
        if ctx: ctx.__exit__(None,None,None)

def rollback(args,deadline=None):
    own=deadline is None; ctx=Deadline(args.deadline_seconds) if own else None
    if ctx: deadline=ctx.__enter__()
    try:
        states={"ACTIVATED","CHECKED","CHECK_FAILED","UNKNOWN_AFTER_CHECK","ACTIVATION_INTENT","UNKNOWN_AFTER_ACTIVATE"}
        base,r,path,uid=receipt_for(args,states,deadline,verify_release=False); current=base/"current"; target=base/"releases"/args.release_id
        if not current.is_symlink() or current.resolve()!=target.resolve(): raise Hold("CURRENT_IDENTITY_UNKNOWN_NO_ROLLBACK")
        previous=r.get("previous_current"); r.update(state="ROLLBACK_INTENT",last_stage="ROLLBACK_INTENT_DURABLE"); atomic_json(path,r)
        if previous is None:
            current.unlink(); fsync_dir(base)
            if current.exists() or current.is_symlink(): raise Hold("ROLLBACK_RESULT_UNKNOWN")
        else:
            old=Path(previous["release"])
            if old.parent!=(base/"releases").resolve() or not old.is_dir(): raise Hold("PREVIOUS_RELEASE_MISSING")
            verify_tree(old/"public",previous["manifest"],deadline,uid); tmp=base/(".rollback-"+args.transaction_id)
            if tmp.exists() or tmp.is_symlink(): raise Hold("TEMPORARY_POINTER_EXISTS")
            os.symlink(previous["link"],tmp); fsync_dir(base); os.replace(tmp,current); fsync_dir(base)
            if not current.is_symlink() or current.resolve()!=old.resolve(): raise Hold("ROLLBACK_RESULT_UNKNOWN")
            verify_tree(old/"public",previous["manifest"],deadline,uid)
        r.update(state="ROLLED_BACK",last_stage="ROLLBACK_COMMITTED"); atomic_json(path,r); return r
    finally:
        if ctx: ctx.__exit__(None,None,None)

def parser():
    p=argparse.ArgumentParser(); p.add_argument("command",choices=("prepare","activate","reconcile","check","rollback"))
    p.add_argument("--webroot-base",type=Path,required=True); p.add_argument("--bundle",type=Path); p.add_argument("--source-archive",type=Path)
    p.add_argument("--transaction-id",required=True); p.add_argument("--release-id",required=True)
    p.add_argument("--lock-wait-seconds",type=float,default=5); p.add_argument("--deadline-seconds",type=float,default=120)
    p.add_argument("--allow-non-root-test",action="store_true",help=argparse.SUPPRESS); return p

def main():
    args=parser().parse_args()
    if os.geteuid()!=0 and not args.allow_non_root_test:
        print(json.dumps({"state":"HOLD","reason":"ROOT_REQUIRED"}),file=sys.stderr); return 77
    try:
        creating=args.command=="prepare"
        if creating and (not args.bundle or not args.source_archive): raise Hold("PREPARE_INPUT_REQUIRED")
        if args.command=="check" and not args.bundle: raise Hold("CHECK_BUNDLE_REQUIRED")
        base,uid=preflight(args,creating)
        with Deadline(args.deadline_seconds) as deadline:
            with lock(base,min(args.lock_wait_seconds,args.deadline_seconds),deadline,uid):
                result={"prepare":prepare,"activate":activate,"reconcile":reconcile,"check":check,"rollback":rollback}[args.command](args,deadline)
        print(json.dumps(result,sort_keys=True)); return 0
    except (Hold,OSError,ValueError,KeyError,json.JSONDecodeError) as error:
        print(json.dumps({"state":"HOLD","reason":str(error)}),file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
