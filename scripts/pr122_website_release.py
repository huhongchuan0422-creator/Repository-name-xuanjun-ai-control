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
FAILURE_RECEIPT_GRACE=0.10

class Hold(RuntimeError): pass
class Unknown(Hold): pass

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
    @contextmanager
    def failure_grace(self):
        """Bound failure reporting after the one-shot overall alarm fired."""
        remaining=max(0.0,self.end-time.monotonic())
        budget=remaining if remaining else FAILURE_RECEIPT_GRACE
        signal.setitimer(signal.ITIMER_REAL,budget)
        try: yield
        finally: signal.setitimer(signal.ITIMER_REAL,0)

@contextmanager
def termination_guard():
    old=signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(Unknown("PROCESS_INTERRUPTED_SIGTERM")))
    try: yield
    finally: signal.signal(signal.SIGTERM,old)

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

def trusted_chain(path,uid):
    """Reject replaceable/symlinked input ancestry; sticky root-owned /tmp is allowed."""
    absolute=path.absolute()
    for current in [absolute,*absolute.parents]:
        try: info=os.lstat(current)
        except OSError as error: raise Hold("TRUSTED_INPUT_PATH_UNAVAILABLE:"+str(current)) from error
        if stat.S_ISLNK(info.st_mode): raise Hold("TRUSTED_INPUT_PATH_LINK:"+str(current))
        if current!=absolute and not stat.S_ISDIR(info.st_mode): raise Hold("TRUSTED_INPUT_PARENT_NOT_DIRECTORY:"+str(current))
        mode=stat.S_IMODE(info.st_mode)
        if info.st_uid not in (0,uid): raise Hold("TRUSTED_INPUT_PATH_OWNER:"+str(current))
        sticky_root=stat.S_ISDIR(info.st_mode) and bool(mode&stat.S_ISVTX) and info.st_uid==0
        if mode&0o022 and not sticky_root: raise Hold("TRUSTED_INPUT_PATH_WRITABLE:"+str(current))

@contextmanager
def open_trusted_file(path,uid,deadline=None):
    path=Path(path).absolute(); trusted_chain(path,uid)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd); live=os.stat(path,follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=uid or stat.S_IMODE(info.st_mode)&0o022:
            raise Hold("TRUSTED_INPUT_FILE_IDENTITY:"+str(path))
        if (info.st_dev,info.st_ino)!=(live.st_dev,live.st_ino): raise Hold("TRUSTED_INPUT_FILE_REPLACED:"+str(path))
        if deadline: deadline.check("TRUSTED_INPUT_OPEN")
        yield fd,info
        live=os.stat(path,follow_symlinks=False)
        if (info.st_dev,info.st_ino)!=(live.st_dev,live.st_ino): raise Hold("TRUSTED_INPUT_FILE_REPLACED:"+str(path))
    finally: os.close(fd)

def read_trusted_bytes(path,uid,deadline=None):
    data=bytearray()
    with open_trusted_file(path,uid,deadline) as (fd,info):
        while True:
            if deadline: deadline.check("TRUSTED_INPUT_READ")
            chunk=os.read(fd,1024*1024)
            if not chunk: break
            data.extend(chunk)
    return bytes(data),{"device":info.st_dev,"inode":info.st_ino,"uid":info.st_uid,"mode":stat.S_IMODE(info.st_mode),"size":info.st_size}

def json_bytes(data,name):
    try: value=json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError) as error: raise Hold("INVALID_JSON:"+name) from error
    if not isinstance(value,dict): raise Hold("JSON_OBJECT_REQUIRED:"+name)
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

def bounded_failure_receipt(deadline,path,value,original):
    try:
        with deadline.failure_grace(): atomic_json(path,value)
    except BaseException as receipt_error:
        raise Unknown("FAILURE_RECEIPT_UNAVAILABLE:"+type(receipt_error).__name__) from original

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
        expected_owner=uid
        bundle=Path(args.bundle).absolute(); trusted_chain(bundle,expected_owner)
        bundle_info=bundle.stat(follow_symlinks=False)
        if not stat.S_ISDIR(bundle_info.st_mode) or bundle_info.st_uid!=expected_owner or stat.S_IMODE(bundle_info.st_mode)&0o022:
            raise Hold("TRUSTED_INPUT_DIRECTORY_IDENTITY")
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

def extract_source(source,public,pin,deadline,uid):
    with open_trusted_file(source,uid,deadline) as (fd,info):
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
        live=os.stat(source,follow_symlinks=False)
        if (info.st_dev,info.st_ino)!=(live.st_dev,live.st_ino): raise Hold("SOURCE_ARCHIVE_REPLACED")

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

def identity(path,kind,mode,uid,deadline=None,with_digest=False):
    if path.is_symlink(): raise Hold("RELEASE_ENVELOPE_LINK:"+str(path))
    info=path.stat(follow_symlinks=False)
    expected_type=stat.S_ISDIR if kind=="directory" else stat.S_ISREG
    if not expected_type(info.st_mode) or info.st_uid!=uid or stat.S_IMODE(info.st_mode)!=mode:
        raise Hold("RELEASE_ENVELOPE_IDENTITY:"+str(path))
    value={"kind":kind,"device":info.st_dev,"inode":info.st_ino,"uid":info.st_uid,"mode":mode}
    if with_digest: value.update(size=info.st_size,sha256=digest(path,deadline))
    return value

def capture_release_envelope(base,release,uid,deadline):
    paths={"base":(base,"directory",0o755,False),"releases":(base/"releases","directory",0o755,False),
           "release":(release,"directory",0o755,False),"public":(release/"public","directory",0o755,False),
           "metadata":(release/"release-metadata","directory",0o755,False),
           "csp_conf":(release/"release-metadata/inline-csp.conf","file",0o644,True),
           "csp_json":(release/"release-metadata/inline-csp.json","file",0o644,True)}
    envelope={name:identity(path,kind,mode,uid,deadline,dig) for name,(path,kind,mode,dig) in paths.items()}
    csp=json_bytes((release/"release-metadata/inline-csp.json").read_bytes(),"inline-csp.json")
    expected=('add_header Content-Security-Policy "'+csp["policy"]+'" always;\n').encode()
    if (release/"release-metadata/inline-csp.conf").read_bytes()!=expected: raise Hold("CSP_JSON_CONF_MISMATCH")
    envelope["nginx_include"]="current/release-metadata/inline-csp.conf"
    return envelope

def verify_release_envelope(base,release,receipt,uid,deadline):
    wanted=receipt.get("release_envelope")
    if not isinstance(wanted,dict): raise Hold("RELEASE_ENVELOPE_MISSING")
    actual=capture_release_envelope(base,release,uid,deadline)
    if actual!=wanted: raise Hold("RELEASE_ENVELOPE_DRIFT")
    inventory=receipt.get("csp_inventory",{})
    csp=json_bytes((release/"release-metadata/inline-csp.json").read_bytes(),"inline-csp.json")
    observed={"html_count":csp.get("html_count"),"script_hash_count":len(csp.get("script_hashes",[])),
              "style_hash_count":len(csp.get("style_hashes",[]))}
    if observed!=inventory: raise Hold("CSP_INVENTORY_DRIFT")

def trusted_bundle(args,deadline,uid):
    bundle=Path(args.bundle).absolute(); mp=bundle/"candidate-manifest.json"; sp=bundle/"source-pin.json"; pp=bundle/"PACKAGE_MANIFEST.json"
    blobs={}; identities={}
    for name,path in (("candidate-manifest.json",mp),("source-pin.json",sp),("PACKAGE_MANIFEST.json",pp)):
        blobs[name],identities[name]=read_trusted_bytes(path,uid,deadline)
    approved=getattr(args,"approved_package_manifest_sha256",None)
    if not approved or not re.fullmatch(r"[0-9a-f]{64}",approved): raise Hold("APPROVED_PACKAGE_MANIFEST_SHA256_REQUIRED")
    if hashlib.sha256(blobs["PACKAGE_MANIFEST.json"]).hexdigest()!=approved:
        raise Hold("APPROVED_PACKAGE_MANIFEST_IDENTITY_MISMATCH")
    manifest=json_bytes(blobs["candidate-manifest.json"],"candidate-manifest.json")
    pin=json_bytes(blobs["source-pin.json"],"source-pin.json")
    package=json_bytes(blobs["PACKAGE_MANIFEST.json"],"PACKAGE_MANIFEST.json"); manifest_map(manifest)
    files={x["path"]:x for x in package.get("files",[])}
    for name in ("candidate-manifest.json","source-pin.json"):
        item=files.get(name)
        if not item or item["size"]!=len(blobs[name]) or item["sha256"]!=hashlib.sha256(blobs[name]).hexdigest():
            raise Hold("PACKAGE_MANIFEST_IDENTITY_MISMATCH:"+name)
    ids={"candidate_manifest_sha256":hashlib.sha256(blobs["candidate-manifest.json"]).hexdigest(),
         "source_pin_sha256":hashlib.sha256(blobs["source-pin.json"]).hexdigest(),
         "package_manifest_sha256":approved,"trusted_input_identities":identities,
         "source_archive_sha256":pin["source_archive_sha256"],"source_archive_size":pin["source_archive_size"]}
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
        manifest,pin,ids=trusted_bundle(args,deadline,uid); source=Path(args.source_archive).absolute()
        receipt={"schema_version":2,"transaction_id":args.transaction_id,"release_id":args.release_id,"state":"PREPARE_INTENT",
                 "last_stage":"PREPARE_INTENT","release":str(release),"trusted_manifest":manifest,**ids,"residuals":[]}
        atomic_json(receipt_path,receipt)
        try:
            staging.mkdir(mode=0o700); receipt.update(last_stage="STAGING_CREATED",residuals=[str(staging)]); atomic_json(receipt_path,receipt)
            public=staging/"public"; public.mkdir(mode=0o700); extract_source(source,public,pin,deadline,uid)
            for name,baseline in pin["overlay_baselines"].items():
                target=public/safe_relative(name); overlay=Path(args.bundle).absolute()/"overlay/public"/safe_relative(name)
                if target.is_symlink() or not target.is_file() or digest(target,deadline)!=baseline: raise Hold("OVERLAY_BASELINE_DRIFT:"+name)
                if overlay.is_symlink() or not overlay.is_file(): raise Hold("OVERLAY_MISSING:"+name)
                with open_trusted_file(overlay,uid,deadline) as (data_fd,_):
                    out=os.open(target,os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW)
                    try:
                        while True:
                            deadline.check("OVERLAY_COPY"); chunk=os.read(data_fd,1024*1024)
                            if not chunk: break
                            os.write(out,chunk)
                        os.fsync(out)
                    finally: os.close(out)
            csp=write_csp_metadata(public,staging,deadline)
            seal_tree(staging,uid); verify_tree(public,manifest,deadline,uid)
            receipt.update(last_stage="SEALED_VERIFIED",csp_inventory=csp); atomic_json(receipt_path,receipt)
            os.replace(staging,release); fsync_dir(releases); verify_tree(release/"public",manifest,deadline,uid)
            receipt.update(state="PREPARED",last_stage="PREPARED_COMMIT",residuals=[str(release)],
                           release_envelope=capture_release_envelope(base,release,uid,deadline)); atomic_json(receipt_path,receipt); return receipt
        except BaseException as error:
            receipt.update(state="HOLD_PARTIAL",failure=type(error).__name__+":"+str(error))
            bounded_failure_receipt(deadline,receipt_path,receipt,error)
            raise
    finally:
        if ctx: ctx.__exit__(None,None,None)

def receipt_for(args,states,deadline,verify_release=True,verify_envelope=True,verify_target_identity=True):
    base,uid=preflight(args,False); transactions=base/"transactions"; secure_dir(transactions,0o700,uid,False)
    path=transactions/(args.transaction_id+".json"); receipt=load_json(path,deadline)
    if receipt.get("schema_version")!=2 or receipt.get("transaction_id")!=args.transaction_id or receipt.get("release_id")!=args.release_id:
        raise Hold("RECEIPT_IDENTITY_MISMATCH")
    if receipt.get("state") not in states: raise Hold("TRANSACTION_STATE_NOT_ELIGIBLE")
    release=base/"releases"/args.release_id
    if str(release)!=receipt.get("release"): raise Hold("PREPARED_RELEASE_IDENTITY_DRIFT")
    if verify_target_identity and (release.is_symlink() or not release.is_dir()): raise Hold("PREPARED_RELEASE_IDENTITY_DRIFT")
    if verify_envelope: verify_release_envelope(base,release,receipt,uid,deadline)
    if verify_release: verify_tree(release/"public",receipt["trusted_manifest"],deadline,uid)
    if args.bundle:
        try: _,_,caller_ids=trusted_bundle(args,deadline,uid)
        except Hold as error: raise Hold("CALLER_BUNDLE_DOES_NOT_MATCH_RECEIPT:"+str(error)) from error
        for key in ("candidate_manifest_sha256","source_pin_sha256","package_manifest_sha256"):
            if caller_ids[key]!=receipt[key]: raise Hold("CALLER_BUNDLE_DOES_NOT_MATCH_RECEIPT:"+key)
    return base,receipt,path,uid

def snapshot(public,deadline):
    files=[]
    for path in sorted(public.rglob("*")):
        if path.is_file() and not path.is_symlink(): files.append({"path":path.relative_to(public).as_posix(),"size":path.stat().st_size,"sha256":digest(path,deadline)})
    return {"schema_version":2,"files":files}

def capture_previous_envelope(base,release,uid,deadline):
    metadata=release/"release-metadata"
    if metadata.exists() or metadata.is_symlink():
        return {"metadata_state":"PRESENT","objects":capture_release_envelope(base,release,uid,deadline)}
    paths={"base":base,"releases":base/"releases","release":release,"public":release/"public"}
    return {"metadata_state":"ABSENT","objects":{
        name:identity(path,"directory",0o755,uid,deadline) for name,path in paths.items()
    }}

def direct_previous_release(base,link):
    """Return only a direct releases/<id> target; aliases and path jumps fail closed."""
    if not isinstance(link,str) or not link: raise Hold("PREVIOUS_POINTER_LINK_INVALID")
    raw=Path(link); releases=base/"releases"
    if raw.is_absolute():
        old=raw
        if old.parent!=releases: raise Hold("PREVIOUS_POINTER_NOT_DIRECT_RELEASE")
    else:
        if len(raw.parts)!=2 or raw.parts[0]!="releases":
            raise Hold("PREVIOUS_POINTER_NOT_DIRECT_RELEASE")
        old=base/raw
    try: valid_id(old.name,"previous_release_id")
    except Hold as error: raise Hold("PREVIOUS_POINTER_NOT_DIRECT_RELEASE") from error
    if old.parent!=releases: raise Hold("PREVIOUS_POINTER_NOT_DIRECT_RELEASE")
    return old

def verify_previous_release(base,previous,uid,deadline):
    if not isinstance(previous,dict) or not isinstance(previous.get("link"),str):
        raise Hold("PREVIOUS_RELEASE_EVIDENCE_MISSING")
    raw=previous.get("release")
    if not isinstance(raw,str): raise Hold("PREVIOUS_RELEASE_EVIDENCE_MISSING")
    old=direct_previous_release(base,previous["link"])
    if raw!=str(old):
        raise Hold("PREVIOUS_RELEASE_PATH_INVALID")
    if old.is_symlink() or not old.is_dir(): raise Hold("PREVIOUS_RELEASE_MISSING")
    wanted=previous.get("release_envelope")
    if not isinstance(wanted,dict) or wanted.get("metadata_state") not in {"PRESENT","ABSENT"}:
        raise Hold("PREVIOUS_RELEASE_ENVELOPE_MISSING")
    try: actual=capture_previous_envelope(base,old,uid,deadline)
    except Hold as error:
        if str(error).startswith("OVERALL_DEADLINE_EXCEEDED"): raise
        raise Hold("PREVIOUS_RELEASE_ENVELOPE_DRIFT:"+str(error)) from error
    if actual!=wanted: raise Hold("PREVIOUS_RELEASE_ENVELOPE_DRIFT")
    manifest=previous.get("manifest")
    if not isinstance(manifest,dict): raise Hold("PREVIOUS_RELEASE_MANIFEST_MISSING")
    verify_tree(old/"public",manifest,deadline,uid)
    return old

def verify_previous_pointer_target(base,current,previous,pointer_identity,uid,deadline):
    verify_symlink_identity(current,pointer_identity,uid)
    old=verify_previous_release(base,previous,uid,deadline)
    try:
        resolved=current.resolve(strict=True)
        same=os.path.samefile(current,old)
    except OSError as error:
        raise Hold("ROLLBACK_POINTER_TARGET_UNAVAILABLE") from error
    if resolved!=old or not same:
        raise Hold("ROLLBACK_POINTER_TARGET_MISMATCH")
    return old

def target_residual_failure(base,r,uid,deadline):
    target=base/"releases"/r["release_id"]
    try:
        if str(target)!=r.get("release") or target.is_symlink() or not target.is_dir():
            raise Hold("PREPARED_RELEASE_IDENTITY_DRIFT")
        verify_release_envelope(base,target,r,uid,deadline)
        verify_tree(target/"public",r["trusted_manifest"],deadline,uid)
    except Hold as error:
        if str(error).startswith("OVERALL_DEADLINE_EXCEEDED"): raise
        return str(error)
    return None

def activate(args,deadline=None):
    own=deadline is None; ctx=Deadline(args.deadline_seconds) if own else None
    if ctx: deadline=ctx.__enter__()
    try:
        base,r,path,uid=receipt_for(args,{"PREPARED"},deadline); target=base/"releases"/args.release_id; current=base/"current"
        if current.exists() and not current.is_symlink(): raise Hold("CURRENT_NOT_SYMLINK")
        previous=None
        if current.is_symlink():
            if current.lstat().st_uid!=uid: raise Hold("PREVIOUS_POINTER_OWNER_MISMATCH")
            link=os.readlink(current); old=direct_previous_release(base,link)
            if old.is_symlink() or not old.is_dir(): raise Hold("PREVIOUS_POINTER_OUTSIDE_RELEASE_NAMESPACE")
            old_manifest=snapshot(old/"public",deadline); verify_tree(old/"public",old_manifest,deadline,uid)
            previous={"link":link,"release":str(old),"manifest":old_manifest,
                      "release_envelope":capture_previous_envelope(base,old,uid,deadline)}
        tmp=base/(".current-"+args.transaction_id)
        r.update(state="ACTIVATION_INTENT",last_stage="ACTIVATION_INTENT_DURABLE",previous_current=previous,
                 target_current=str(target),activation_temp=str(tmp)); atomic_json(path,r)
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
        base,r,path,uid=receipt_for(args,{"ACTIVATION_INTENT","UNKNOWN_AFTER_ACTIVATE","ROLLBACK_INTENT","ROLLBACK_PENDING","UNKNOWN_AFTER_ROLLBACK"},deadline,
                                    verify_release=False,verify_envelope=False,verify_target_identity=False)
        current=base/"current"; target=base/"releases"/args.release_id
        if r["state"] in {"ROLLBACK_INTENT","ROLLBACK_PENDING","UNKNOWN_AFTER_ROLLBACK"}:
            return reconcile_rollback(base,r,path,uid,deadline)
        if target.is_symlink() or not target.is_dir(): raise Hold("PREPARED_RELEASE_IDENTITY_DRIFT")
        verify_release_envelope(base,target,r,uid,deadline)
        verify_tree(target/"public",r["trusted_manifest"],deadline,uid)
        tmp=Path(r.get("activation_temp",base/(".current-"+args.transaction_id)))
        if tmp.exists() or tmp.is_symlink():
            if not tmp.is_symlink() or tmp.resolve()!=target.resolve():
                r.update(state="UNKNOWN_AFTER_RECONCILE",last_stage="ACTIVATION_TEMP_UNKNOWN"); atomic_json(path,r); raise Hold("RECONCILIATION_AMBIGUOUS")
        if current.is_symlink() and current.resolve()==target.resolve():
            if tmp.is_symlink(): tmp.unlink(); fsync_dir(base)
            r.update(state="ACTIVATED",last_stage="RECONCILED_SWITCH_COMMITTED",reconciliation="TARGET_PRESENT")
        else:
            observed=os.readlink(current) if current.is_symlink() else (None if not current.exists() else "NON_SYMLINK")
            expected=None if r.get("previous_current") is None else r["previous_current"]["link"]
            if observed!=expected:
                r.update(state="UNKNOWN_AFTER_RECONCILE",observed_current=observed); atomic_json(path,r); raise Hold("RECONCILIATION_AMBIGUOUS")
            if tmp.is_symlink(): tmp.unlink(); fsync_dir(base)
            r.update(state="PREPARED",last_stage="RECONCILED_NO_SWITCH",reconciliation="PREVIOUS_OR_ABSENT")
        atomic_json(path,r); return r
    finally:
        if ctx: ctx.__exit__(None,None,None)

def check(args,deadline=None):
    own=deadline is None; ctx=Deadline(args.deadline_seconds) if own else None
    if ctx: deadline=ctx.__enter__()
    try:
        base,r,path,uid=receipt_for(args,{"ACTIVATED","CHECKED"},deadline); current=base/"current"; target=base/"releases"/args.release_id
        if not current.is_symlink() or current.resolve()!=target.resolve():
            r.update(state="UNKNOWN_AFTER_CHECK",last_stage="CURRENT_RELEASE_MISMATCH"); atomic_json(path,r); raise Hold("CURRENT_RELEASE_MISMATCH")
        verify_tree(target/"public",r["trusted_manifest"],deadline,uid)
        repeat=r["state"]=="CHECKED"
        if not repeat:
            r.update(state="CHECKED",last_stage="CHECK_COMMITTED"); atomic_json(path,r)
        return {"state":"PASS","release_id":args.release_id,"candidate_manifest_sha256":r["candidate_manifest_sha256"]}
    except Hold as error:
        if "r" in locals() and r.get("state") in {"ACTIVATED","CHECKED"}:
            r.update(state="CHECK_FAILED",failure=str(error)); bounded_failure_receipt(deadline,path,r,error)
        raise
    finally:
        if ctx: ctx.__exit__(None,None,None)

def expected_rollback_observation(base,r):
    previous=r.get("previous_current")
    if previous is None: return None
    return previous["link"]

def symlink_identity(path,uid):
    if not path.is_symlink(): raise Hold("POINTER_NOT_SYMLINK")
    info=path.lstat()
    if info.st_uid!=uid: raise Hold("POINTER_OWNER_MISMATCH")
    return {"device":info.st_dev,"inode":info.st_ino,"ctime_ns":info.st_ctime_ns,"uid":info.st_uid,"link":os.readlink(path)}

def verify_symlink_identity(path,wanted,uid):
    if not isinstance(wanted,dict) or symlink_identity(path,uid)!=wanted:
        raise Hold("ROLLBACK_POINTER_IDENTITY_DRIFT")

def same_symlink_object(observed,wanted):
    keys=("device","inode","uid","link")
    return isinstance(wanted,dict) and all(observed.get(key)==wanted.get(key) for key in keys)

def observe_pointer(current,target,uid=None):
    if current.is_symlink():
        if uid is not None and current.lstat().st_uid!=uid: return "SYMLINK_OWNER_MISMATCH"
        link=os.readlink(current)
        if link==str(target): return "TARGET"
        return link
    return None if not current.exists() else "NON_SYMLINK"

def reconcile_rollback(base,r,path,uid,deadline):
    current=base/"current"; target=base/"releases"/r["release_id"]
    observed=observe_pointer(current,target,uid); expected=expected_rollback_observation(base,r)
    tmp=Path(r.get("rollback_temp",base/(".rollback-"+r["transaction_id"])))
    if tmp.exists() or tmp.is_symlink():
        previous=r.get("previous_current")
        if not previous or not tmp.is_symlink() or tmp.lstat().st_uid!=uid or os.readlink(tmp)!=previous["link"]:
            r.update(state="UNKNOWN_AFTER_ROLLBACK",last_stage="ROLLBACK_TEMP_UNKNOWN",observed_current=observed); atomic_json(path,r)
            raise Hold("ROLLBACK_RECONCILIATION_AMBIGUOUS")
    if observed==expected:
        try:
            if r.get("previous_current") is not None:
                verify_previous_pointer_target(base,current,r["previous_current"],r.get("rollback_pointer_identity"),uid,deadline)
        except Hold as error:
            r.update(state="UNKNOWN_AFTER_ROLLBACK",last_stage="ROLLBACK_FINAL_VALIDATION_FAILED",
                     observed_current=observed,rollback_final_validation_failure=str(error)); atomic_json(path,r)
            raise Hold("ROLLBACK_FINAL_STATE_UNPROVEN:"+str(error)) from error
        residual=target_residual_failure(base,r,uid,deadline)
        if tmp.is_symlink(): tmp.unlink(); fsync_dir(base)
        r.update(state="ROLLED_BACK",last_stage="ROLLBACK_RECONCILED_COMMITTED",reconciliation="EXPECTED_FINAL_PRESENT",
                 target_residual_failure=residual)
        atomic_json(path,r); return r
    if observed=="TARGET":
        r.update(state="ROLLBACK_PENDING",last_stage="ROLLBACK_RECONCILED_NOT_APPLIED",reconciliation="TARGET_STILL_PRESENT")
        atomic_json(path,r); return r
    r.update(state="UNKNOWN_AFTER_ROLLBACK",last_stage="ROLLBACK_RESULT_UNKNOWN",observed_current=observed); atomic_json(path,r)
    raise Hold("ROLLBACK_RECONCILIATION_AMBIGUOUS")

def rollback(args,deadline=None):
    own=deadline is None; ctx=Deadline(args.deadline_seconds) if own else None
    if ctx: deadline=ctx.__enter__()
    try:
        states={"ACTIVATED","CHECKED","CHECK_FAILED","UNKNOWN_AFTER_CHECK","ACTIVATION_INTENT","UNKNOWN_AFTER_ACTIVATE","ROLLBACK_INTENT","ROLLBACK_PENDING"}
        base,r,path,uid=receipt_for(args,states,deadline,verify_release=False,verify_envelope=False,verify_target_identity=False); current=base/"current"; target=base/"releases"/args.release_id
        envelope_failure=None
        try:
            if target.is_symlink() or not target.is_dir(): raise Hold("PREPARED_RELEASE_IDENTITY_DRIFT")
            verify_release_envelope(base,target,r,uid,deadline)
            verify_tree(target/"public",r["trusted_manifest"],deadline,uid)
        except Hold as error: envelope_failure=str(error)
        observed=observe_pointer(current,target,uid); expected=expected_rollback_observation(base,r)
        if r["state"] in {"ROLLBACK_INTENT","ROLLBACK_PENDING"} and observed==expected:
            return reconcile_rollback(base,r,path,uid,deadline)
        if observed!="TARGET": raise Hold("CURRENT_IDENTITY_UNKNOWN_NO_ROLLBACK")
        previous=r.get("previous_current"); tmp=base/(".rollback-"+args.transaction_id)
        if previous is not None: verify_previous_release(base,previous,uid,deadline)
        if r["state"] not in {"ROLLBACK_INTENT","ROLLBACK_PENDING"}:
            r.update(state="ROLLBACK_INTENT",last_stage="ROLLBACK_INTENT_DURABLE",rollback_temp=str(tmp),target_envelope_failure=envelope_failure); atomic_json(path,r)
        if previous is None:
            current.unlink(); fsync_dir(base)
            if current.exists() or current.is_symlink(): raise Hold("ROLLBACK_RESULT_UNKNOWN")
        else:
            old=verify_previous_release(base,previous,uid,deadline)
            if tmp.exists() or tmp.is_symlink():
                if not tmp.is_symlink() or tmp.lstat().st_uid!=uid or os.readlink(tmp)!=previous["link"]: raise Hold("TEMPORARY_POINTER_EXISTS")
            else: os.symlink(previous["link"],tmp); fsync_dir(base)
            prepared_pointer_identity=symlink_identity(tmp,uid)
            existing_identity=r.get("rollback_prepared_pointer_identity")
            if existing_identity is not None and not same_symlink_object(prepared_pointer_identity,existing_identity):
                raise Hold("ROLLBACK_POINTER_IDENTITY_DRIFT")
            r.update(last_stage="ROLLBACK_POINTER_PREPARED",rollback_prepared_pointer_identity=prepared_pointer_identity); atomic_json(path,r)
            os.replace(tmp,current); fsync_dir(base)
            if observe_pointer(current,target,uid)!=expected: raise Hold("ROLLBACK_RESULT_UNKNOWN")
            pointer_identity=symlink_identity(current,uid)
            if not same_symlink_object(pointer_identity,prepared_pointer_identity): raise Hold("ROLLBACK_POINTER_IDENTITY_DRIFT")
            r.update(last_stage="ROLLBACK_POINTER_SWITCHED",rollback_pointer_identity=pointer_identity); atomic_json(path,r)
            verify_previous_pointer_target(base,current,previous,pointer_identity,uid,deadline)
        r.update(state="ROLLED_BACK",last_stage="ROLLBACK_COMMITTED"); atomic_json(path,r); return r
    finally:
        if ctx: ctx.__exit__(None,None,None)

def parser():
    p=argparse.ArgumentParser(); p.add_argument("command",choices=("prepare","activate","reconcile","check","rollback"))
    p.add_argument("--webroot-base",type=Path,required=True); p.add_argument("--bundle",type=Path); p.add_argument("--source-archive",type=Path)
    p.add_argument("--transaction-id",required=True); p.add_argument("--release-id",required=True)
    p.add_argument("--approved-package-manifest-sha256",help="Externally approved SHA-256 of PACKAGE_MANIFEST.json")
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
        with termination_guard():
            base,uid=preflight(args,creating)
            with Deadline(args.deadline_seconds) as deadline:
                with lock(base,min(args.lock_wait_seconds,args.deadline_seconds),deadline,uid):
                    result={"prepare":prepare,"activate":activate,"reconcile":reconcile,"check":check,"rollback":rollback}[args.command](args,deadline)
        print(json.dumps(result,sort_keys=True)); return 0
    except Unknown as error:
        print(json.dumps({"state":"UNKNOWN","reason":str(error)}),file=sys.stderr); return 2
    except KeyboardInterrupt:
        print(json.dumps({"state":"UNKNOWN","reason":"PROCESS_INTERRUPTED_SIGINT"}),file=sys.stderr); return 130
    except (Hold,OSError,ValueError,KeyError,json.JSONDecodeError) as error:
        print(json.dumps({"state":"HOLD","reason":str(error)}),file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
