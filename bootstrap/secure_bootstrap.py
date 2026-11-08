#!/usr/bin/env python3
"""Independent pre-execution verifier. No carrier imports. Candidate, not deployed."""
import argparse, base64, fcntl, hashlib, io, json, os, re, sqlite3, stat, sys, tarfile, time

class Hold(Exception): pass

def require(ok, why):
    if not ok: raise Hold(why)

def stable_read(fd, owner, limit):
    before=os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1, 'REGULAR_SINGLE_LINK_REQUIRED')
    require(before.st_uid==owner and not (before.st_mode & 0o022), 'UNSAFE_OWNER_MODE')
    require(0<=before.st_size<=limit, 'SIZE_LIMIT')
    data=b''; pos=0
    while pos<before.st_size:
        chunk=os.pread(fd,min(1048576,before.st_size-pos),pos)
        require(bool(chunk),'SHORT_READ');data+=chunk;pos+=len(chunk)
    after=os.fstat(fd)
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'FILE_CHANGED')
    return data

def open_relative(dfd, path):
    require(isinstance(path,str) and path and not path.startswith('/'),'UNSAFE_PATH')
    parts=path.split('/');require(all(x not in ('','.','..') for x in parts),'UNSAFE_PATH')
    current=os.dup(dfd)
    try:
        for part in parts[:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
            os.close(current);current=nxt
        return os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=current)
    finally: os.close(current)

def pairs(items):
    out={}
    for k,v in items:
        require(k not in out,'DUPLICATE_JSON_KEY');out[k]=v
    return out

def parse(raw):
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(obj): return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()

def inspect_archive(blob, members):
    require(isinstance(members,dict) and len(members)<=10000,'MANIFEST_MEMBERS')
    seen=set();total=0
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:*') as archive:
        for m in archive:
            p=m.name
            require(p and not p.startswith('/') and all(x not in ('','.','..') for x in p.split('/')),'ARCHIVE_PATH')
            require(p not in seen and (m.isfile() or m.isdir()),'ARCHIVE_TYPE_OR_DUPLICATE');seen.add(p)
            if m.isdir():
                require(p in members and members[p]=={'type':'directory'},'DIRECTORY_MISMATCH');continue
            require(m.size<=64*1024*1024,'MEMBER_SIZE');total+=m.size;require(total<=256*1024*1024,'ARCHIVE_SIZE')
            f=archive.extractfile(m);data=f.read(m.size+1)
            require(len(data)==m.size and members.get(p)=={'type':'file','size':m.size,'sha256':sha(data)},'MEMBER_MISMATCH')
    require(seen==set(members),'MEMBER_SET')

def checked_ledger_path(path, owner):
    from path_guard import Guard
    require(os.path.isabs(path),'LEDGER_ABSOLUTE_REQUIRED')
    with Guard(path,owner) as guard:
        fd=guard.open_file(os.O_RDWR);os.close(fd)

def consume(db_path, receipt, owner=0, evidence=None):
    from path_guard import GuardedLedger
    with GuardedLedger(db_path,owner) as guarded:
        db=guarded.db
        try:
            guarded.check();db.execute('BEGIN IMMEDIATE');guarded.check()
            require(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='operations'").fetchone() is not None,'LEDGER_SCHEMA')
            require(db.execute("SELECT 1 FROM operations WHERE state IN ('RESERVED','RUNNING','UNKNOWN') LIMIT 1").fetchone() is None,'UNRESOLVED_OPERATION')
            require(db.execute("SELECT 1 FROM operations WHERE task=? AND attempt=?",(receipt['task'],receipt['attempt'])).fetchone() is None,'ATTEMPT_IN_FLIGHT')
            if evidence is None:
                db.execute('INSERT INTO operations(nonce,task,attempt,state) VALUES(?,?,?,?)',(receipt['nonce'],receipt['task'],receipt['attempt'],'RESERVED'))
            else:
                db.execute('INSERT INTO operations(nonce,task,attempt,state,prestate_target,prestate_hash,staging_target,manifest_hash,intended_target,receipt_hash,operation_id,carrier_digest,manifest_digest,prestate_digest,key_id,receipt_path,prestate_dev,prestate_ino) VALUES(?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?)',(receipt['nonce'],receipt['task'],receipt['attempt'],'RESERVED',evidence['prestate_target'],evidence['prestate_hash'],'stage-'+receipt['nonce'],receipt['manifest_sha256'],'release-'+receipt['nonce'],'install:'+receipt['nonce'],receipt['carrier_sha256'],receipt['manifest_sha256'],evidence['prestate_digest'],evidence['key_id'],'receipt-'+receipt['nonce']+'.json',evidence['prestate_dev'],evidence['prestate_ino']))
            guarded.check();db.execute('COMMIT')
        except Exception:
            if db.in_transaction:db.execute('ROLLBACK')
            raise

def verify(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,owner=0,now=None,audit=None,evidence=None):
    # Check the supplied evidence sink before reserving a nonce or reading carrier.
    ls=os.fstat(log_fd);require(stat.S_ISREG(ls.st_mode) and ls.st_nlink==1 and ls.st_uid==owner and not ls.st_mode&0o022 and fcntl.fcntl(log_fd,fcntl.F_GETFL)&os.O_APPEND,'LOG_REQUIRED')
    trust=parse(stable_read(trust_fd,owner,65536));require(trust.get('mode') in ('ED25519','DIGEST_ALLOWLIST'),'TRUST_ANCHOR_REQUIRED')
    require(trust.get('environment') in ('PRODUCTION','TEST_ONLY'),'TRUST_ENVIRONMENT_REQUIRED')
    receipt=parse(stable_read(receipt_fd,owner,65536));require(set(receipt)=={'payload','signature'},'RECEIPT_FORMAT')
    p=receipt['payload'];keys={'carrier_sha256','manifest_sha256','task','attempt','nonce','expiry','controller','tool_scope'}
    require(isinstance(p,dict) and set(p)==keys,'RECEIPT_FIELDS')
    require(all(isinstance(p[x],str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',p[x]) for x in ('task','attempt','nonce','controller')),'RECEIPT_ID')
    require(type(p['expiry']) is int and p['expiry']>int(time.time() if now is None else now),'RECEIPT_EXPIRED')
    require(p['task']==scope['task'] and p['attempt']==scope['attempt'] and p['controller']==trust.get('controller'),'RECEIPT_SCOPE')
    if trust['mode']=='ED25519':
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try: Ed25519PublicKey.from_public_bytes(base64.b64decode(trust['public_key'],validate=True)).verify(base64.b64decode(receipt['signature'],validate=True),canonical(p))
        except Exception as e: raise Hold('SIGNATURE_INVALID') from e
    else:
        require(trust.get('environment')=='PRODUCTION' and os.fstat(trust_fd).st_uid==0,'ALLOWLIST_ROOT_REQUIRED')
        require(sha(canonical(p)) in trust.get('receipt_sha256_allowlist',[]),'RECEIPT_NOT_ALLOWLISTED')
    manifest_raw=stable_read(manifest_fd,owner,4*1024*1024);carrier=stable_read(carrier_fd,owner,128*1024*1024)
    require(sha(manifest_raw)==p['manifest_sha256'] and sha(carrier)==p['carrier_sha256'],'DIGEST_MISMATCH')
    manifest=parse(manifest_raw);require(set(manifest)=={'members','tool_scope','minimum_sqlite'},'MANIFEST_FIELDS')
    require(manifest['minimum_sqlite']==[3,35,0] and sqlite3.sqlite_version_info >= tuple(manifest['minimum_sqlite']),'SQLITE_VERSION_UNSUPPORTED')
    tool_scope=p['tool_scope'];require(isinstance(tool_scope,dict) and set(tool_scope)=={'mode','tools'},'TOOL_SCOPE_REQUIRED')
    require(tool_scope['mode'] in ('READ_ONLY','WRITE_ALLOWED') and isinstance(tool_scope['tools'],dict),'TOOL_SCOPE_INVALID')
    require(isinstance(manifest['tool_scope'],dict),'MANIFEST_SCOPE_INVALID')
    # Exact known names only; a signed receipt cannot grant an unknown dynamic tool.
    known_read={'task_list','task_read_context','task_query_result','task_dispatch_contract','task_capabilities','task_get','task_dispatch_status','task_candidate_status','task_development_status','task_development_gateway_readback','task_result_recovery_status'}
    known_write={'task_claim','task_report_progress','task_save_checkpoint','task_submit_artifact','task_request_review','task_submit','task_assign_role','task_dispatch','task_cancel_dispatch','task_submit_candidate','task_review_candidate','task_accept_candidate','task_development_gateway_candidate','task_development_gateway_test_event','task_development_gateway','task_development_continue_review','task_development_verify_tests','task_development_apply','task_development_review','task_development_finalize','task_prepare_result_recovery','task_review_result_recovery','task_accept_result_recovery'}
    require(not(set(tool_scope['tools'])-(known_read|known_write)),'UNKNOWN_TOOL_DENIED')
    for name,resource in manifest['tool_scope'].items():
        require(name in known_read or name in known_write,'UNKNOWN_TOOL_DENIED')
        require(name in tool_scope['tools'] and tool_scope['tools'][name]==resource and isinstance(resource,str) and bool(resource),'TOOL_SCOPE_DENIED')
        if tool_scope['mode']=='READ_ONLY':require(name in known_read,'WRITE_TOOL_DENIED')
    inspect_archive(carrier,manifest['members'])
    consume(ledger_path,p,owner,evidence)
    record=(json.dumps({'event':'VERIFIED_RESERVED','nonce':p['nonce'],'carrier_sha256':p['carrier_sha256']},sort_keys=True)+'\n').encode()
    if audit is None:os.write(log_fd,record);os.fsync(log_fd)
    else:audit.write(record)
    return carrier,p

def verify_binding(binding_raw, trust, owner):
    """Verify signed binding before loading third-party vendor modules."""
    binding=parse(binding_raw)
    require(isinstance(binding,dict) and set(binding)=={'payload','signature','key_id'},'BINDING_FORMAT')
    payload=binding['payload'];require(isinstance(payload,dict) and binding['key_id']==trust.get('binding_key_id'),'BINDING_KEY_ID')
    require(payload.get('schema')==1 and payload.get('production_trust_anchor')=='REQUIRED' and type(payload.get('expiry')) is int and payload['expiry']>int(time.time()),'BINDING_SCOPE')
    require(payload.get('dependency_lock_sha256')==trust.get('dependency_lock_sha256'),'BINDING_LOCK_DIGEST')
    try:
        public=base64.b64decode(trust['binding_public_key'],validate=True)
        signature=base64.b64decode(binding['signature'],validate=True)
    except Exception:raise Hold('BINDING_KEY_FORMAT')
    require(len(public)==32 and len(signature)==64,'BINDING_KEY_FORMAT')
    # python -I removes the script directory; insert only this trusted bootstrap.
    bootstrap=os.path.dirname(os.path.realpath(__file__));sys.path.insert(0,bootstrap)
    from ed25519_verify import verify
    require(verify(public,canonical(payload),signature),'BINDING_SIGNATURE_INVALID')
    return payload

def verify_dependency_lock(lock_raw, trust, *, _test_expected_uid=None):
    """Authenticate the isolated vendored dependency tree before importing it."""
    import sysconfig
    require(_test_expected_uid is None or (trust.get('environment')=='TEST_ONLY' and _test_expected_uid==os.getuid()),'TEST_OWNER_POLICY')
    expected_uid=0 if _test_expected_uid is None else _test_expected_uid
    expected_gid=0 if _test_expected_uid is None else os.getgid()
    require(sys.flags.isolated==1,'PYTHON_ISOLATED_MODE_REQUIRED')
    require(sha(lock_raw)==trust.get('dependency_lock_sha256'),'DEPENDENCY_LOCK_DIGEST')
    lock=parse(lock_raw);require(lock.get('schema')==1 and lock.get('soabi')==sysconfig.get_config_var('SOABI'),'DEPENDENCY_ABI')
    require(lock.get('platform')=='linux-x86_64-glibc' and sys.platform=='linux' and __import__('platform').machine()=='x86_64','DEPENDENCY_PLATFORM')
    vendor=os.path.realpath(os.path.join(os.path.dirname(__file__),'vendor'))
    require(os.path.isdir(vendor) and not os.path.islink(os.path.join(os.path.dirname(__file__),'vendor')),'VENDOR_DIRECTORY_REQUIRED')
    for directory in (os.path.dirname(vendor),vendor):
        info=os.stat(directory,follow_symlinks=False)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==expected_uid and info.st_gid==expected_gid and not info.st_mode&0o022 and (_test_expected_uid is not None or not info.st_mode&0o222),'VENDOR_DIRECTORY_POLICY')
    files=lock.get('files');require(isinstance(files,list) and files,'DEPENDENCY_LOCK_FILES')
    expected={}
    for row in files:
        require(isinstance(row,dict) and set(row)=={'path','sha256','size','mode'},'DEPENDENCY_LOCK_FIELDS')
        name=row['path'];require(isinstance(name,str) and name and not name.startswith('/') and all(x not in ('','.','..') for x in name.split('/')) and name not in expected,'DEPENDENCY_PATH')
        path=os.path.join(vendor,name);require(os.path.realpath(path)==path,'DEPENDENCY_PATH_LINK')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==expected_uid and st.st_gid==expected_gid and not st.st_mode&0o022 and (_test_expected_uid is not None or not st.st_mode&0o222) and st.st_size==row['size'] and format(stat.S_IMODE(st.st_mode),'04o')==row['mode'],'DEPENDENCY_FILE_POLICY')
            h=hashlib.sha256();offset=0
            while offset<st.st_size:
                chunk=os.pread(fd,min(1048576,st.st_size-offset),offset);require(bool(chunk),'DEPENDENCY_SHORT_READ');h.update(chunk);offset+=len(chunk)
            end=os.fstat(fd);require((st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==(end.st_dev,end.st_ino,end.st_size,end.st_mtime_ns,end.st_ctime_ns),'DEPENDENCY_CHANGED')
            require(h.hexdigest()==row['sha256'],'DEPENDENCY_DIGEST');expected[name]=row['sha256']
        finally:os.close(fd)
    actual=set()
    for directory,dirs,names in os.walk(vendor,followlinks=False):
        info=os.stat(directory,follow_symlinks=False);require(info.st_uid==expected_uid and info.st_gid==expected_gid and not info.st_mode&0o022 and (_test_expected_uid is not None or not info.st_mode&0o222),'VENDOR_DIRECTORY_POLICY')
        require(not any(os.path.islink(os.path.join(directory,x)) for x in dirs),'DEPENDENCY_PATH_LINK')
        for name in names:actual.add(os.path.relpath(os.path.join(directory,name),vendor))
    require(actual==set(expected),'DEPENDENCY_FILE_SET')
    sys.path[:]=[vendor,os.path.dirname(os.path.realpath(__file__))]+[p for p in sys.path if p and 'site-packages' not in p and 'dist-packages' not in p and os.path.realpath(p)!=vendor]
    sys.dont_write_bytecode=True
    import cryptography,cffi,_cffi_backend
    import cryptography.hazmat.bindings._rust as rust
    import importlib.metadata as metadata
    for module in (cryptography,cffi,_cffi_backend,rust):
        path=os.path.realpath(module.__file__);require(path.startswith(vendor+os.sep) and os.path.relpath(path,vendor) in expected,'DEPENDENCY_IMPORT_ORIGIN')
    dist={d.metadata['Name'].lower():d.version for d in metadata.distributions(path=[vendor])}
    require(all(dist.get(k)==v for k,v in lock.get('distributions',{}).items()),'DEPENDENCY_VERSION')


def main():
    # Reject unsupported runtime before opening or mutating any controller path.
    if sqlite3.sqlite_version_info < (3,35,0):
        print('HOLD SQLITE_VERSION_UNSUPPORTED',file=sys.stderr);return 1
    a=argparse.ArgumentParser()
    a.add_argument('--reconcile',action='store_true')
    a.add_argument('--rollback',action='store_true')
    a.add_argument('--rollback-authorization-fd',type=int)
    a.add_argument('--test-only-crash-hook',choices=('crash_before_rename','crash_after_rename','crash_before_receipt','install_crash_after_rename','install_crash_before_rename','install_crash_before_receipt'))
    for n in ('carrier-fd','manifest-fd','receipt-fd','receipt-signing-key-fd'):a.add_argument('--'+n,type=int)
    a.add_argument('--trust-fd',type=int,required=True)
    a.add_argument('--dependency-lock-fd',type=int,required=True)
    a.add_argument('--binding-fd',type=int,required=True)
    a.add_argument('--receipt-dir-fd',type=int,required=True)
    a.add_argument('--expected-controller-uid',type=int,default=0)
    a.add_argument('--expected-controller-gid',type=int,default=0)
    a.add_argument('--expected-receipt-owner',type=int,default=0)
    a.add_argument('--expected-receipt-mode',type=lambda v:int(v,8),default=0o700)
    for n in ('ledger','audit','root'):a.add_argument('--'+n,required=True)
    for n in ('task','attempt','receipt-key-id'):a.add_argument('--'+n)
    x=a.parse_args()
    try:
        require(os.geteuid()==x.expected_controller_uid and os.getegid()==x.expected_controller_gid,'CONTROLLER_IDENTITY_MISMATCH')
        trust=parse(stable_read(x.trust_fd,x.expected_controller_uid,65536))
        binding=verify_binding(stable_read(x.binding_fd,x.expected_controller_uid,65536),trust,x.expected_controller_uid)
        require(binding.get('environment')==trust.get('environment'),'BINDING_ENVIRONMENT')
        verify_dependency_lock(stable_read(x.dependency_lock_fd,x.expected_controller_uid,8*1024*1024),trust)
        from controller import run,reconcile_pending,rollback
        from path_guard import GuardedAudit
        require(trust.get('expected_controller_uid',0)==x.expected_controller_uid and trust.get('expected_controller_gid',0)==x.expected_controller_gid,'CONTROLLER_TRUST_MISMATCH')
        require(trust.get('expected_receipt_owner',0)==x.expected_receipt_owner and trust.get('expected_receipt_mode',448)==x.expected_receipt_mode,'RECEIPT_TRUST_MISMATCH')
        rd=os.fstat(x.receipt_dir_fd)
        require(stat.S_ISDIR(rd.st_mode) and rd.st_uid==x.expected_receipt_owner and stat.S_IMODE(rd.st_mode)==x.expected_receipt_mode,'RECEIPT_DIRECTORY_REQUIRED')
        with GuardedAudit(x.audit,x.expected_controller_uid) as audit:
            if x.reconcile:
                pending=reconcile_pending(x.ledger,x.expected_controller_uid,x.root,audit.file,audit,stable_read(x.trust_fd,x.expected_controller_uid,65536),receipt_dir_fd=x.receipt_dir_fd)
                require(pending==0,'UNKNOWN_RECONCILIATION_REQUIRED')
                print('RECONCILED')
            elif x.rollback:
                require(x.rollback_authorization_fd is not None and x.receipt_signing_key_fd is not None and x.receipt_key_id,'ROLLBACK_ARGUMENTS_REQUIRED')
                auth_raw=stable_read(x.rollback_authorization_fd,x.expected_controller_uid,65536);auth=parse(auth_raw)
                require(isinstance(auth,dict) and set(auth)=={'payload','signature','key_id'} and auth['key_id']==trust.get('key_id'),'ROLLBACK_AUTH_FORMAT')
                p=auth['payload'];require(isinstance(p,dict) and set(p)=={'install_op','prestate_digest','rollback_op','nonce','expiry','controller'},'ROLLBACK_AUTH_FIELDS')
                require(all(isinstance(p[k],str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',p[k]) for k in ('install_op','rollback_op','nonce')) and isinstance(p['prestate_digest'],str) and re.fullmatch('[0-9a-f]{64}',p['prestate_digest']),'ROLLBACK_AUTH_FIELDS')
                require(type(p['expiry']) is int and p['expiry']>int(time.time()) and p['controller']==trust.get('controller'),'ROLLBACK_AUTH_SCOPE')
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                try:Ed25519PublicKey.from_public_bytes(base64.b64decode(trust['public_key'],validate=True)).verify(base64.b64decode(auth['signature'],validate=True),canonical(p))
                except Exception:raise Hold('ROLLBACK_AUTH_SIGNATURE')
                require(x.test_only_crash_hook is None or trust.get('environment')=='TEST_ONLY','TEST_HOOK_FORBIDDEN')
                result=rollback(x.ledger,x.root,x.expected_controller_uid,audit.file,x.trust_fd,x.receipt_signing_key_fd,x.receipt_key_id,x.receipt_dir_fd,p['install_op'],p['rollback_op'],sha(canonical(p)),audit=audit,authorized_prestate_digest=p['prestate_digest'],failpoint=x.test_only_crash_hook)
                require(result['state']=='SUCCEEDED','ROLLBACK_NOT_SUCCEEDED');print(json.dumps(result,sort_keys=True))
            else:
                require(all(getattr(x,n) is not None for n in ('carrier_fd','manifest_fd','receipt_fd','receipt_signing_key_fd','task','attempt','receipt_key_id')),'INSTALL_ARGUMENTS_REQUIRED')
                require(x.test_only_crash_hook is None or (trust.get('environment')=='TEST_ONLY' and x.test_only_crash_hook in ('install_crash_after_rename','install_crash_before_rename','install_crash_before_receipt')),'TEST_HOOK_FORBIDDEN')
                target=run(x.carrier_fd,x.manifest_fd,x.receipt_fd,x.trust_fd,x.ledger,audit.file,{'task':x.task,'attempt':x.attempt},x.root,owner=x.expected_controller_uid,audit=audit,signing_key_fd=x.receipt_signing_key_fd,key_id=x.receipt_key_id,receipt_dir_fd=x.receipt_dir_fd,failpoint=x.test_only_crash_hook);print('INSTALLED '+target)
    except Exception as e: print('HOLD '+type(e).__name__+': '+str(e),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
