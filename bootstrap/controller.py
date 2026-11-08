"""TEST candidate controller: verified bytes -> private staging -> atomic symlink.

No carrier code is imported or executed. Production integration is not provided.
"""
import base64, fcntl, hashlib, io, json, os, re, sqlite3, stat, tarfile, tempfile, time
import secure_bootstrap as verifylib

class ControllerError(Exception): pass

def check(value, reason):
    if not value: raise ControllerError(reason)

def transition(path, owner, nonce, before, after):
    from path_guard import GuardedLedger
    with GuardedLedger(path,owner) as guarded:
        db=guarded.db
        try:
            guarded.check();db.execute('BEGIN IMMEDIATE');guarded.check()
            cur=db.execute('UPDATE operations SET state=? WHERE nonce=? AND state=?',(after,nonce,before))
            check(cur.rowcount==1,'STATE_CONFLICT');guarded.check();db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:db.execute('ROLLBACK')
            raise

def log(fd, event, audit=None):
    blob=(json.dumps(event,sort_keys=True,separators=(',',':'))+'\n').encode()
    if audit is not None:audit.write(blob)
    else:check(os.write(fd,blob)==len(blob),'SHORT_LOG');os.fsync(fd)

def open_dir(parent, name):
    return os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)

def extract(blob, rootfd):
    # All archive entries already passed the bootstrap manifest check. Use the
    # same captured immutable bytes, no pathname reopening and no carrier exec.
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:*') as archive:
        for member in archive:
            parts=member.name.split('/');fd=os.dup(rootfd)
            try:
                for part in parts[:-1]:
                    try:os.mkdir(part,0o700,dir_fd=fd)
                    except FileExistsError:pass
                    nxt=open_dir(fd,part);os.close(fd);fd=nxt
                if member.isdir():
                    try:os.mkdir(parts[-1],0o700,dir_fd=fd)
                    except FileExistsError:pass
                    nxt=open_dir(fd,parts[-1]);os.fsync(nxt);os.close(nxt)
                else:
                    out=os.open(parts[-1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                    try:
                        data=archive.extractfile(member).read(member.size+1)
                        check(len(data)==member.size,'EXTRACTION_SIZE')
                        pos=0
                        while pos<len(data):pos+=os.write(out,data[pos:])
                        os.fsync(out)
                    finally:os.close(out)
                os.fsync(fd)
            finally:os.close(fd)
    os.fsync(rootfd)

def _name(value):
    check(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',value) and value not in ('.','..'),'EVIDENCE_NAME')
    return value

def _file_bytes(dfd, name, owner, limit=4*1024*1024):
    fd=os.open(_name(name),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dfd)
    try:return verifylib.stable_read(fd,owner,limit)
    finally:os.close(fd)

def verified_tree(rootfd,target,owner):
    """Validate every installed entry against its manifest; return tree digest."""
    directory=open_dir(rootfd,_name(target));entries={}
    try:
        rootstat=os.fstat(directory);check(rootstat.st_uid==owner and stat.S_IMODE(rootstat.st_mode)==0o700,'TREE_ROOT_MODE')
        raw=_file_bytes(directory,'.bootstrap-manifest.json',owner)
        manifest=verifylib.parse(raw);check(isinstance(manifest,dict) and isinstance(manifest.get('members'),dict),'TREE_MANIFEST')
        members=manifest['members']
        def walk(fd,prefix=''):
            for name in sorted(os.listdir(fd)):
                if not prefix and name=='.bootstrap-manifest.json':continue
                check(name not in ('','.','..') and '/' not in name,'TREE_PATH')
                path=prefix+name;info=os.stat(name,dir_fd=fd,follow_symlinks=False)
                check(info.st_uid==owner,'TREE_OWNER')
                if stat.S_ISDIR(info.st_mode):
                    check(stat.S_IMODE(info.st_mode)==0o700,'TREE_DIR_MODE')
                    sub=open_dir(fd,name)
                    try:
                        st=os.fstat(sub);check((st.st_dev,st.st_ino)==(info.st_dev,info.st_ino),'TREE_CHANGED')
                        entries[path]={'type':'directory'};walk(sub,path+'/')
                    finally:os.close(sub)
                else:
                    check(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'TREE_FILE_MODE')
                    f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
                    try:
                        st=os.fstat(f);check((st.st_dev,st.st_ino)==(info.st_dev,info.st_ino),'TREE_CHANGED')
                        data=verifylib.stable_read(f,owner,64*1024*1024)
                    finally:os.close(f)
                    entries[path]={'type':'file','size':len(data),'sha256':verifylib.sha(data)}
        walk(directory);check(entries==members,'TREE_MEMBER_MISMATCH')
        return verifylib.sha(verifylib.canonical({'manifest_sha256':verifylib.sha(raw),'members':entries}))
    finally:os.close(directory)

def verify_operation_receipt(raw, trust_raw, operation, attempt, current_tree, prestate_tree):
    """Verify controller-signed receipt, independent from carrier code."""
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    trust=verifylib.parse(trust_raw);receipt=verifylib.parse(raw)
    check(trust.get('mode')=='ED25519' and trust.get('environment') in ('TEST_ONLY','PRODUCTION'),'RECEIPT_TRUST')
    check(isinstance(receipt,dict) and set(receipt)=={'payload','signature'},'RECEIPT_FORMAT')
    expected={'operation':operation,'attempt':attempt,'current_tree_sha256':current_tree,'prestate_tree_sha256':prestate_tree,'controller':trust.get('controller'),'outcome':'SUCCEEDED'}
    check(receipt['payload']==expected,'RECEIPT_BINDING')
    try:
        key=Ed25519PublicKey.from_public_bytes(base64.b64decode(trust['public_key'],validate=True))
        key.verify(base64.b64decode(receipt['signature'],validate=True),verifylib.canonical(expected))
    except Exception:raise ControllerError('RECEIPT_SIGNATURE')
    return expected

def _target_manifest(rootfd, target, owner):
    d=open_dir(rootfd,_name(target))
    try:
        st=os.fstat(d);check(st.st_uid==owner and not st.st_mode&0o077,'TARGET_OWNER_MODE')
        return verifylib.sha(_file_bytes(d,'.bootstrap-manifest.json',owner))
    finally:os.close(d)

def _current(rootfd):
    try:
        st=os.stat('current',dir_fd=rootfd,follow_symlinks=False)
        check(stat.S_ISLNK(st.st_mode),'CURRENT_NOT_LINK')
        return _name(os.readlink('current',dir_fd=rootfd))
    except FileNotFoundError:return None

def _exists(rootfd,name):
    try:os.stat(_name(name),dir_fd=rootfd,follow_symlinks=False);return True
    except FileNotFoundError:return False

def _remove_tree(parent,name,owner):
    """Validate entire tree before deletion; caller holds exclusive controller lock."""
    def walk(parent_fd, item, remove):
        d=open_dir(parent_fd,_name(item));st=os.fstat(d)
        check(st.st_uid==owner and not st.st_mode&0o077,'STAGE_OWNER_MODE')
        try:
            for child in os.listdir(d):
                c=os.stat(child,dir_fd=d,follow_symlinks=False)
                if stat.S_ISDIR(c.st_mode):walk(d,child,remove)
                else:
                    check(stat.S_ISREG(c.st_mode) and c.st_nlink==1 and c.st_uid==owner and not c.st_mode&0o077,'UNSAFE_STAGE_ENTRY')
                    if remove:os.unlink(child,dir_fd=d)
            if remove:os.fsync(d)
        finally:os.close(d)
        current=os.stat(item,dir_fd=parent_fd,follow_symlinks=False)
        check((st.st_dev,st.st_ino)==(current.st_dev,current.st_ino),'STAGE_REPLACED')
        if remove:os.rmdir(item,dir_fd=parent_fd);os.fsync(parent_fd)
    walk(parent,name,False);walk(parent,name,True)

def _reconcile_pending_locked(path, owner, root, log_fd, audit=None, trust_raw=None, receipt_dir_fd=None):
    """Reconcile under the caller-held controller lock; missing evidence holds."""
    from path_guard import GuardedLedger
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        st=os.fstat(rootfd);check(st.st_uid==owner and st.st_gid==os.getegid() and stat.S_IMODE(st.st_mode)==0o700,'ROOT_PERMISSIONS')
        with GuardedLedger(path,owner) as g:
            db=g.db;db.row_factory=sqlite3.Row
            g.check();db.execute('BEGIN IMMEDIATE')
            try:
                columns={r[1] for r in db.execute('PRAGMA table_info(operations)')}
                if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rollbacks'").fetchone():
                    rb_columns={r[1] for r in db.execute('PRAGMA table_info(rollbacks)')}
                    check({'operation_id','request_digest','install_op','attempt','from_target','to_target','from_digest','to_digest','state','receipt_json','receipt_path','key_id'}.issubset(rb_columns),'ROLLBACK_SCHEMA_REQUIRED')
                    for rb in db.execute("SELECT * FROM rollbacks WHERE state IN ('ROLLBACK_PREPARED','SWITCHED','UNKNOWN')").fetchall():
                        old=rb['state'];new='UNKNOWN'
                        try:
                            cur=_current(rootfd)
                            check(verified_tree(rootfd,rb['from_target'],owner)==rb['from_digest'] and verified_tree(rootfd,rb['to_target'],owner)==rb['to_digest'],'ROLLBACK_TREE')
                            if cur==rb['from_target']:
                                name=rb['receipt_path'];check(name=='rollback-'+hashlib.sha256(rb['operation_id'].encode()).hexdigest()+'.json','ROLLBACK_RECEIPT_PATH')
                                check(receipt_dir_fd is not None and not _exists(receipt_dir_fd,name),'ROLLBACK_RECEIPT_CONFLICT');new='FAILED'
                            elif cur==rb['to_target']:
                                check(receipt_dir_fd is not None and trust_raw is not None,'ROLLBACK_RECEIPT_REQUIRED')
                                name=rb['receipt_path'];check(name=='rollback-'+hashlib.sha256(rb['operation_id'].encode()).hexdigest()+'.json','ROLLBACK_RECEIPT_PATH')
                                obj=verifylib.parse(_file_bytes(receipt_dir_fd,name,owner,65536));trust=verifylib.parse(trust_raw);payload=obj['payload']
                                check(set(obj)=={'payload','key_id','signature'} and obj['key_id']==trust['key_id']==rb['key_id'],'ROLLBACK_RECEIPT_KEY')
                                check(payload['install_op']==rb['install_op'] and payload['rollback_op']==rb['operation_id'] and payload['attempt']==rb['attempt'] and payload['request_digest']==rb['request_digest'] and payload['from_tree_digest']==rb['from_digest'] and payload['to_tree_digest']==rb['to_digest'] and payload['controller_identity']==trust['controller'],'ROLLBACK_RECEIPT_BINDING')
                                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                                try:Ed25519PublicKey.from_public_bytes(base64.b64decode(trust['public_key'],validate=True)).verify(base64.b64decode(obj['signature'],validate=True),verifylib.canonical(payload))
                                except Exception:raise ControllerError('ROLLBACK_SIGNATURE')
                                new='SUCCEEDED';db.execute('UPDATE rollbacks SET receipt_json=? WHERE operation_id=?',(verifylib.canonical(obj).decode(),rb['operation_id']))
                        except (OSError,ValueError,TypeError,KeyError,ControllerError):new='UNKNOWN'
                        if new!=old:
                            log(log_fd,{'event':'ROLLBACK_RECONCILE','operation':rb['operation_id'],'from':old,'to':new},audit)
                            db.execute('UPDATE rollbacks SET state=? WHERE operation_id=? AND state=?',(new,rb['operation_id'],old))
                required={'prestate_target','prestate_hash','staging_target','manifest_hash','intended_target','receipt_hash','operation_id','carrier_digest','manifest_digest','tree_digest','prestate_digest','key_id','receipt_path','switch_intent','prestate_dev','prestate_ino'}
                rows=db.execute("SELECT * FROM operations WHERE state IN ('RESERVED','RUNNING','UNKNOWN')").fetchall()
                for row in rows:
                    before=row['state'];outcome='UNKNOWN';reason='EVIDENCE_MISSING'
                    try:
                        check(required.issubset(columns),'EVIDENCE_SCHEMA')
                        pre=_name(row['prestate_target']);stage=_name(row['staging_target']);target=_name(row['intended_target'])
                        prehash=row['prestate_hash'];mh=row['manifest_hash'];rh=row['receipt_hash']
                        check(all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in (prehash,mh)),'EVIDENCE_DIGEST')
                        check(_target_manifest(rootfd,pre,owner)==prehash,'PRESTATE_MISMATCH')
                        check(row['switch_intent'] is not None,'SWITCH_INTENT_REQUIRED')
                        intent=verifylib.parse(row['switch_intent'].encode())
                        check(set(intent)=={'operation_id','fence','from_dev','from_ino','from_tree','to_dev','to_ino','to_tree'} and intent['operation_id']==row['operation_id']=='install:'+row['nonce'] and intent['fence']==row['attempt'] and intent['from_tree']==row['prestate_digest'] and intent['to_tree']==row['tree_digest'] and (intent['from_dev'],intent['from_ino'])==(row['prestate_dev'],row['prestate_ino']),'SWITCH_INTENT_BINDING')
                        pfd=open_dir(rootfd,pre)
                        try:pi=os.fstat(pfd);check((pi.st_dev,pi.st_ino)==(intent['from_dev'],intent['from_ino']) and verified_tree(rootfd,pre,owner)==intent['from_tree'],'SWITCH_PRESTATE_MISMATCH')
                        finally:os.close(pfd)
                        tfd=open_dir(rootfd,target)
                        try:ti=os.fstat(tfd);check((ti.st_dev,ti.st_ino)==(intent['to_dev'],intent['to_ino']) and verified_tree(rootfd,target,owner)==intent['to_tree'],'SWITCH_TARGET_MISMATCH')
                        finally:os.close(tfd)
                        current=_current(rootfd);stage_exists=_exists(rootfd,stage);target_exists=_exists(rootfd,target)
                        if current==target:
                            check(not stage_exists and target_exists,'TARGET_CONFLICT')
                            check(_target_manifest(rootfd,target,owner)==mh,'TARGET_MISMATCH')
                            check(isinstance(rh,str) and re.fullmatch('[0-9a-f]{64}',rh),'RECEIPT_MISSING')
                            raw=_file_bytes(receipt_dir_fd if receipt_dir_fd is not None else rootfd,'receipt-'+row['nonce']+'.json',owner,65536)
                            check(verifylib.sha(raw)==rh,'RECEIPT_MISMATCH')
                            check(trust_raw is not None,'RECEIPT_TRUST_REQUIRED')
                            obj=verifylib.parse(raw);payload=obj['payload'];trust=verifylib.parse(trust_raw)
                            check(set(obj)=={'payload','signature','key_id'} and obj['key_id']==trust.get('key_id'),'RECEIPT_KEY_ID')
                            check(set(payload)=={'operation_id','attempt_id','nonce','carrier_digest','manifest_digest','tree_digest','prestate_digest','current_target','controller_identity','issued_at','switch_intent_digest'},'RECEIPT_FIELDS')
                            check(isinstance(payload['carrier_digest'],str) and re.fullmatch('[0-9a-f]{64}',payload['carrier_digest']) and type(payload['issued_at']) is int,'RECEIPT_FIELDS')
                            check(payload['operation_id']==row['operation_id']=='install:'+row['nonce'] and payload['attempt_id']==row['attempt'] and payload['nonce']==row['nonce'] and payload['carrier_digest']==row['carrier_digest'] and payload['switch_intent_digest']==verifylib.sha(row['switch_intent'].encode()) and payload['manifest_digest']==row['manifest_digest']==mh and payload['tree_digest']==row['tree_digest'] and payload['prestate_digest']==row['prestate_digest'] and obj['key_id']==row['key_id'] and row['receipt_path']=='receipt-'+row['nonce']+'.json' and payload['current_target']==target and payload['controller_identity']==trust.get('controller'),'RECEIPT_BINDING')
                            check(payload['tree_digest']==verified_tree(rootfd,target,owner) and payload['prestate_digest']==verified_tree(rootfd,pre,owner),'RECEIPT_TREE')
                            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                            try:Ed25519PublicKey.from_public_bytes(base64.b64decode(trust['public_key'],validate=True)).verify(base64.b64decode(obj['signature'],validate=True),verifylib.canonical(payload))
                            except Exception:raise ControllerError('RECEIPT_SIGNATURE')
                            outcome='SUCCEEDED';reason='SIGNED_RECEIPT_AND_TREE_MATCH'
                        elif current==pre:
                            check(target_exists,'UNSWITCHED_TARGET_MISSING')
                            if stage_exists:
                                check(_target_manifest(rootfd,stage,owner)==mh,'STAGE_MISMATCH')
                                _remove_tree(rootfd,stage,owner)
                            outcome='FAILED';reason='PRESTATE_UNCHANGED'
                        else:reason='CURRENT_CONFLICT'
                    except (OSError,ValueError,TypeError,KeyError,ControllerError):
                        outcome='UNKNOWN';reason='EVIDENCE_CONFLICT_OR_MISSING'
                    if before!=outcome:
                        log(log_fd,{'event':'RECONCILE','nonce':row['nonce'],'from':before,'to':outcome,'reason':reason},audit)
                        g.check();db.execute('UPDATE operations SET state=? WHERE nonce=? AND state=?',(outcome,row['nonce'],before))
                g.check();db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:db.execute('ROLLBACK')
                raise
            pending=db.execute("SELECT COUNT(*) FROM operations WHERE state IN ('RESERVED','RUNNING','UNKNOWN')").fetchone()[0]
            if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rollbacks'").fetchone():pending+=db.execute("SELECT COUNT(*) FROM rollbacks WHERE state IN ('ROLLBACK_PREPARED','SWITCHED','UNKNOWN')").fetchone()[0]
            return pending
    finally:os.close(rootfd)

def _run_locked(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,root,owner=0,failpoint=None,audit=None,signing_key_fd=None,key_id=None,receipt_dir_fd=None,bound_artifacts=None):
    """Installer for authenticated snapshots; legacy path remains test-only."""
    rootst=os.lstat(root);check(stat.S_ISDIR(rootst.st_mode) and rootst.st_uid==owner and rootst.st_gid==os.getegid() and stat.S_IMODE(rootst.st_mode)==0o700,'ROOT_PERMISSIONS')
    check(signing_key_fd is not None and isinstance(key_id,str) and key_id,'SIGNING_KEY_REQUIRED')
    trust_raw=verifylib.stable_read(trust_fd,owner,65536);trust=verifylib.parse(trust_raw)
    check(trust.get('mode')=='ED25519' and trust.get('key_id')==key_id,'SIGNING_KEY_ID')
    keyinfo=os.fstat(signing_key_fd);check(keyinfo.st_uid==owner and stat.S_IMODE(keyinfo.st_mode)==0o600,'SIGNING_KEY_PERMISSIONS')
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private=Ed25519PrivateKey.from_private_bytes(verifylib.stable_read(signing_key_fd,owner,32))
    public=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    check(base64.b64encode(public).decode()==trust.get('public_key'),'SIGNING_KEY_MISMATCH')
    check(_reconcile_pending_locked(ledger_path,owner,root,log_fd,audit,trust_raw,receipt_dir_fd)==0,'UNKNOWN_RECONCILIATION_REQUIRED')
    # Verify receipt output is writable before reserving or switching current.
    if receipt_dir_fd is not None:
        check(os.access('.',os.W_OK|os.X_OK,dir_fd=receipt_dir_fd,effective_ids=True),'RECEIPT_DIRECTORY_UNWRITABLE')
    # Before effects, verify complete signed input and atomically reserve nonce.
    if audit is not None: audit.write(b'{"event":"STARTING"}\n')
    currentfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        pre=_current(currentfd);check(pre is not None,'PRESTATE_REQUIRED')
        prestate_tree=verified_tree(currentfd,pre,owner)
        pre_fd=open_dir(currentfd,pre)
        try:prestat=os.fstat(pre_fd)
        finally:os.close(pre_fd)
        evidence={'prestate_target':pre,'prestate_hash':_target_manifest(currentfd,pre,owner),'prestate_digest':prestate_tree,'prestate_dev':prestat.st_dev,'prestate_ino':prestat.st_ino,'key_id':key_id}
    finally:os.close(currentfd)
    from path_guard import GuardedLedger
    with GuardedLedger(ledger_path,owner) as schema:
        columns={r[1] for r in schema.db.execute('PRAGMA table_info(operations)')}
        check({'operation_id','carrier_digest','manifest_digest','tree_digest','prestate_digest','key_id','receipt_path','prestate_dev','prestate_ino','switch_intent'}.issubset(columns),'LEDGER_SCHEMA_UPGRADE_REQUIRED')
    blob,p=verifylib.verify(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,owner=owner,audit=audit,evidence=evidence,bound=bound_artifacts)
    nonce=p['nonce']; check(nonce not in ('.','..') and '/' not in nonce,'NONCE_PATH')
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    running=False
    try:
        transition(ledger_path,owner,nonce,'RESERVED','RUNNING');running=True
        log(log_fd,{'event':'RUNNING','nonce':nonce},audit)
        if failpoint=='after_running':raise ControllerError('INJECTED')
        name='stage-'+nonce
        os.mkdir(name,0o700,dir_fd=rootfd);os.fsync(rootfd)
        stage=open_dir(rootfd,name)
        try:
            extract(blob,stage)
            if bound_artifacts is not None:
                signed_manifest=verifylib.parse(bound_artifacts.manifest_raw)
                members={r['path']:({'type':'directory'} if r['type']=='directory' else {'type':'file','size':r['size'],'sha256':r['sha256']}) for r in signed_manifest['members']}
                manifest=verifylib.canonical({'members':members,'source_manifest_sha256':bound_artifacts.manifest_digest,'scope_sha256':bound_artifacts.scope_digest})
                scopefd=os.open('TOOL_SCOPE.json',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=stage)
                try:check(verifylib.sha(verifylib.stable_read(scopefd,owner,1024*1024))==bound_artifacts.scope_digest,'STAGED_SCOPE_MISMATCH')
                finally:os.close(scopefd)
            else:
                manifest=verifylib.stable_read(manifest_fd,owner,4*1024*1024)
                check(verifylib.sha(manifest)==p['manifest_sha256'],'MANIFEST_CHANGED')
            fd=os.open('.bootstrap-manifest.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=stage)
            try:
                check(os.write(fd,manifest)==len(manifest),'SHORT_MANIFEST_WRITE');os.fsync(fd)
            finally:os.close(fd)
            os.fsync(stage)
        finally:os.close(stage)
        stage_tree=verified_tree(rootfd,name,owner)
        if bound_artifacts is not None:
            signed_manifest=verifylib.parse(bound_artifacts.manifest_raw)
            members={r['path']:({'type':'directory'} if r['type']=='directory' else {'type':'file','size':r['size'],'sha256':r['sha256']}) for r in signed_manifest['members']}
            expected_tree=verifylib.sha(verifylib.canonical({'manifest_sha256':verifylib.sha(manifest),'members':members}))
            check(stage_tree==expected_tree,'BOUND_STAGE_TREE_MISMATCH')
        from path_guard import GuardedLedger
        with GuardedLedger(ledger_path,owner) as g:
            g.db.execute('BEGIN IMMEDIATE')
            try:
                g.check();cur=g.db.execute("UPDATE operations SET tree_digest=? WHERE nonce=? AND state='RUNNING'",(stage_tree,nonce));check(cur.rowcount==1,'TREE_STATE');g.db.execute('COMMIT')
            except BaseException:
                if g.db.in_transaction:g.db.execute('ROLLBACK')
                raise
        if failpoint=='after_extract':raise ControllerError('INJECTED')
        target='release-'+nonce
        os.rename(name,target,src_dir_fd=rootfd,dst_dir_fd=rootfd);os.fsync(rootfd)
        if failpoint=='after_release':raise ControllerError('INJECTED')
        # Durable switch intent is committed before the symlink rename.
        prefd=open_dir(rootfd,pre);newfd=open_dir(rootfd,target)
        try:
            before=os.fstat(prefd);after=os.fstat(newfd)
            check((before.st_dev,before.st_ino)==(evidence['prestate_dev'],evidence['prestate_ino']),'SWITCH_PRESTATE_CHANGED')
            check(_current(rootfd)==pre and verified_tree(rootfd,pre,owner)==prestate_tree and verified_tree(rootfd,target,owner)==stage_tree,'SWITCH_TREE_CHANGED')
            intent=verifylib.canonical({'operation_id':'install:'+nonce,'fence':p['attempt'],'from_dev':before.st_dev,'from_ino':before.st_ino,'from_tree':prestate_tree,'to_dev':after.st_dev,'to_ino':after.st_ino,'to_tree':stage_tree}).decode()
        finally:os.close(prefd);os.close(newfd)
        with GuardedLedger(ledger_path,owner) as g:
            g.db.execute('BEGIN IMMEDIATE')
            try:
                g.check();cur=g.db.execute("UPDATE operations SET switch_intent=? WHERE nonce=? AND state='RUNNING'",(intent,nonce));check(cur.rowcount==1,'SWITCH_INTENT_STATE');g.db.execute('COMMIT')
            except BaseException:
                if g.db.in_transaction:g.db.execute('ROLLBACK')
                raise
        log(log_fd,{'event':'SWITCH_INTENT','nonce':nonce,'intent':verifylib.sha(intent.encode())},audit)
        link='.current-'+nonce
        os.symlink(target,link,dir_fd=rootfd)
        if failpoint=='install_crash_before_rename':os._exit(95)
        os.rename(link,'current',src_dir_fd=rootfd,dst_dir_fd=rootfd)
        if failpoint=='install_crash_after_rename':os._exit(94)
        os.fsync(rootfd)
        if failpoint=='install_crash_before_receipt':os._exit(96)
        if failpoint=='after_switch':raise ControllerError('INJECTED')
        check(_current(rootfd)==target and verified_tree(rootfd,target,owner)==stage_tree,'CURRENT_TREE_MISMATCH')
        payload={'operation_id':'install:'+nonce,'attempt_id':p['attempt'],'nonce':nonce,'carrier_digest':p['carrier_sha256'],'manifest_digest':p['manifest_sha256'],'tree_digest':stage_tree,'prestate_digest':prestate_tree,'current_target':target,'controller_identity':p['controller'],'issued_at':int(time.time()),'switch_intent_digest':verifylib.sha(intent.encode())}
        receipt=verifylib.canonical({'payload':payload,'signature':base64.b64encode(private.sign(verifylib.canonical(payload))).decode(),'key_id':key_id})
        temp='.receipt-'+nonce+'.tmp';final='receipt-'+nonce+'.json'
        receiptfd=receipt_dir_fd if receipt_dir_fd is not None else rootfd
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=receiptfd)
        try:check(os.write(fd,receipt)==len(receipt),'SHORT_RECEIPT_WRITE');os.fsync(fd)
        finally:os.close(fd)
        os.link(temp,final,src_dir_fd=receiptfd,dst_dir_fd=receiptfd,follow_symlinks=False);os.unlink(temp,dir_fd=receiptfd);os.fsync(receiptfd)
        check(_current(rootfd)==target and verified_tree(rootfd,target,owner)==stage_tree,'CURRENT_TREE_MISMATCH')
        from path_guard import GuardedLedger
        with GuardedLedger(ledger_path,owner) as g:
            g.db.execute('BEGIN IMMEDIATE')
            try:
                g.check();cur=g.db.execute("UPDATE operations SET receipt_hash=? WHERE nonce=? AND state='RUNNING'",(verifylib.sha(receipt),nonce));check(cur.rowcount==1,'RECEIPT_STATE');g.db.execute('COMMIT')
            except BaseException:
                if g.db.in_transaction:g.db.execute('ROLLBACK')
                raise
        log(log_fd,{'event':'SUCCEEDED','nonce':nonce,'target':target},audit)
        transition(ledger_path,owner,nonce,'RUNNING','SUCCEEDED');running=False
        return target
    except BaseException:
        if running:
            try:transition(ledger_path,owner,nonce,'RUNNING','UNKNOWN')
            except Exception:pass
        raise
    finally:os.close(rootfd)

def recover(path, owner):
    """Do not replay after a process crash. No automatic reconciliation."""
    from path_guard import GuardedLedger
    with GuardedLedger(path,owner) as guarded:
        db=guarded.db
        try:
            guarded.check();db.execute('BEGIN IMMEDIATE');guarded.check()
            db.execute("UPDATE operations SET state='UNKNOWN' WHERE state='RUNNING'");guarded.check();db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:db.execute('ROLLBACK')
            raise


def run(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,root,owner=0,failpoint=None,audit=None,signing_key_fd=None,key_id=None,receipt_dir_fd=None,bound_artifacts=None):
    if bound_artifacts is not None:check(isinstance(bound_artifacts,verifylib.VerifiedBoundArtifacts),'VERIFIED_BOUND_ARTIFACT_REQUIRED')
    else:check(verifylib.parse(verifylib.stable_read(trust_fd,owner,65536)).get('environment')=='TEST_ONLY','LEGACY_INSTALL_FORBIDDEN')
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        st=os.fstat(rootfd);check(st.st_uid==owner and st.st_gid==os.getegid() and stat.S_IMODE(st.st_mode)==0o700,'ROOT_PERMISSIONS')
        lock=os.open('.bootstrap.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=rootfd)
        try:
            st=os.fstat(lock);check(stat.S_ISREG(st.st_mode) and st.st_uid==owner and st.st_nlink==1 and not st.st_mode&0o077,'LOCK_PERMISSIONS')
            fcntl.flock(lock,fcntl.LOCK_EX)
            return _run_locked(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,root,owner,failpoint,audit,signing_key_fd,key_id,receipt_dir_fd,bound_artifacts)
        finally:os.close(lock)
    finally:os.close(rootfd)


def reconcile_pending(path, owner, root, log_fd, audit=None, trust_raw=None,receipt_dir_fd=None):
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        st=os.fstat(rootfd);check(st.st_uid==owner and st.st_gid==os.getegid() and stat.S_IMODE(st.st_mode)==0o700,'ROOT_PERMISSIONS')
        lock=os.open('.bootstrap.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=rootfd)
        try:
            st=os.fstat(lock);check(stat.S_ISREG(st.st_mode) and st.st_uid==owner and st.st_nlink==1 and not st.st_mode&0o077,'LOCK_PERMISSIONS')
            fcntl.flock(lock,fcntl.LOCK_EX)
            return _reconcile_pending_locked(path,owner,root,log_fd,audit,trust_raw,receipt_dir_fd)
        finally:os.close(lock)
    finally:os.close(rootfd)

def rollback(ledger_path,root,owner,log_fd,trust_fd,signing_key_fd,key_id,receipt_dir_fd,install_op,rollback_op,request_digest,audit=None,failpoint=None,authorized_prestate_digest=None):
    """Experimental rollback. Caller must provide independent authorization."""
    from path_guard import GuardedLedger
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    check(re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',rollback_op or '') and re.fullmatch('[0-9a-f]{64}',request_digest or ''),'ROLLBACK_ID')
    check(os.access('.',os.W_OK|os.X_OK,dir_fd=receipt_dir_fd,effective_ids=True),'RECEIPT_DIRECTORY_UNWRITABLE')
    trust=verifylib.parse(verifylib.stable_read(trust_fd,owner,65536));check(trust.get('mode')=='ED25519' and trust.get('key_id')==key_id,'SIGNING_KEY_ID')
    keyinfo=os.fstat(signing_key_fd);check(keyinfo.st_uid==owner and stat.S_IMODE(keyinfo.st_mode)==0o600,'SIGNING_KEY_PERMISSIONS')
    private=Ed25519PrivateKey.from_private_bytes(verifylib.stable_read(signing_key_fd,owner,32))
    pub=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    check(base64.b64encode(pub).decode()==trust.get('public_key'),'SIGNING_KEY_MISMATCH')
    rootfd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    lock=None;reserved=False
    try:
        st=os.fstat(rootfd);check(st.st_uid==owner and st.st_gid==os.getegid() and stat.S_IMODE(st.st_mode)==0o700,'ROOT_PERMISSIONS')
        lock=os.open('.bootstrap.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=rootfd);fcntl.flock(lock,fcntl.LOCK_EX)
        check(_reconcile_pending_locked(ledger_path,owner,root,log_fd,audit,verifylib.canonical(trust),receipt_dir_fd)==0,'PENDING_INSTALL')
        with GuardedLedger(ledger_path,owner) as g:
            db=g.db;db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
            try:
                old=db.execute('SELECT * FROM rollbacks WHERE operation_id=?',(rollback_op,)).fetchone()
                if old:
                    check(old['request_digest']==request_digest and old['install_op']==install_op,'ROLLBACK_REQUEST_CONFLICT')
                    check(old['state']=='SUCCEEDED' and old['receipt_json'],'ROLLBACK_NOT_SUCCEEDED')
                    name='rollback-'+hashlib.sha256(rollback_op.encode()).hexdigest()+'.json'
                    raw=_file_bytes(receipt_dir_fd,name,owner,65536);check(raw.decode()==old['receipt_json'],'ROLLBACK_RECEIPT_CONFLICT')
                    obj=verifylib.parse(raw);payload=obj['payload'];check(obj['key_id']==key_id and payload['rollback_op']==rollback_op and payload['request_digest']==request_digest and payload['install_op']==install_op,'ROLLBACK_RECEIPT_BINDING')
                    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                    try:Ed25519PublicKey.from_public_bytes(pub).verify(base64.b64decode(obj['signature'],validate=True),verifylib.canonical(payload))
                    except Exception:raise ControllerError('ROLLBACK_SIGNATURE')
                    check(_current(rootfd)==old['to_target'] and verified_tree(rootfd,old['to_target'],owner)==old['to_digest'],'ROLLBACK_POSTSTATE')
                    result={'state':old['state'],'receipt':old['receipt_json']};db.execute('COMMIT');return result
                check(db.execute("SELECT 1 FROM rollbacks WHERE state IN ('ROLLBACK_PREPARED','SWITCHED','UNKNOWN')").fetchone() is None,'ROLLBACK_UNKNOWN_HOLD')
                installed=db.execute("SELECT * FROM operations WHERE operation_id=? AND state='SUCCEEDED'",(install_op,)).fetchone();check(installed is not None,'INSTALL_OPERATION_REQUIRED');check(authorized_prestate_digest is None or installed['prestate_digest']==authorized_prestate_digest,'AUTHORIZATION_PRESTATE_MISMATCH')
                from_target=_name(installed['intended_target']);to_target=_name(installed['prestate_target'])
                check(_current(rootfd)==from_target,'ROLLBACK_CURRENT_MISMATCH')
                fd=open_dir(rootfd,to_target)
                try:st=os.fstat(fd);check((st.st_dev,st.st_ino)==(installed['prestate_dev'],installed['prestate_ino']),'PRESTATE_INODE_MISMATCH')
                finally:os.close(fd)
                check(verified_tree(rootfd,from_target,owner)==installed['tree_digest'] and verified_tree(rootfd,to_target,owner)==installed['prestate_digest'],'ROLLBACK_TREE_MISMATCH')
                db.execute('INSERT INTO rollbacks(operation_id,request_digest,install_op,attempt,from_target,to_target,from_digest,to_digest,state,receipt_json,receipt_path,key_id) VALUES(?,?,?,?,?,?,?,?,?,NULL,?,?)',(rollback_op,request_digest,install_op,installed['attempt'],from_target,to_target,installed['tree_digest'],installed['prestate_digest'],'ROLLBACK_PREPARED','rollback-'+hashlib.sha256(rollback_op.encode()).hexdigest()+'.json',key_id))
                log(log_fd,{'event':'ROLLBACK_PREPARED','operation':rollback_op},audit);g.check();db.execute('COMMIT');reserved=True
            except BaseException:
                if db.in_transaction:db.execute('ROLLBACK')
                raise
        if failpoint=='before_rename':raise ControllerError('INJECTED_BEFORE_RENAME')
        if failpoint=='crash_before_rename':os._exit(91)
        link='.rollback-'+hashlib.sha256(rollback_op.encode()).hexdigest();os.symlink(to_target,link,dir_fd=rootfd);os.rename(link,'current',src_dir_fd=rootfd,dst_dir_fd=rootfd)
        log(log_fd,{'event':'ROLLBACK_SWITCH','operation':rollback_op,'target':to_target},audit)
        if failpoint=='after_rename':raise ControllerError('INJECTED_AFTER_RENAME')
        if failpoint=='crash_after_rename':os._exit(92)
        os.fsync(rootfd)
        with GuardedLedger(ledger_path,owner) as g:
            g.db.execute('BEGIN IMMEDIATE');g.db.execute("UPDATE rollbacks SET state='SWITCHED' WHERE operation_id=? AND state='ROLLBACK_PREPARED'",(rollback_op,));g.db.execute('COMMIT')
        if failpoint=='before_receipt':raise ControllerError('INJECTED_BEFORE_RECEIPT')
        if failpoint=='crash_before_receipt':os._exit(93)
        check(_current(rootfd)==to_target and verified_tree(rootfd,to_target,owner)==installed['prestate_digest'],'ROLLBACK_POSTSTATE')
        payload={'install_op':install_op,'rollback_op':rollback_op,'attempt':installed['attempt'],'request_digest':request_digest,'from_tree_digest':installed['tree_digest'],'to_tree_digest':installed['prestate_digest'],'controller_identity':trust['controller'],'issued_at':int(time.time())}
        receipt=verifylib.canonical({'payload':payload,'key_id':key_id,'signature':base64.b64encode(private.sign(verifylib.canonical(payload))).decode()})
        name='rollback-'+hashlib.sha256(rollback_op.encode()).hexdigest()+'.json';fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=receipt_dir_fd)
        try:check(os.write(fd,receipt)==len(receipt),'RECEIPT_SHORT');os.fsync(fd)
        finally:os.close(fd)
        os.fsync(receipt_dir_fd);log(log_fd,{'event':'ROLLBACK_SUCCEEDED','operation':rollback_op},audit)
        with GuardedLedger(ledger_path,owner) as g:
            g.db.execute('BEGIN IMMEDIATE');g.db.execute("UPDATE rollbacks SET state='SUCCEEDED',receipt_json=? WHERE operation_id=? AND state='SWITCHED'",(receipt.decode(),rollback_op));g.db.execute('COMMIT')
        return {'state':'SUCCEEDED','receipt':receipt.decode()}
    except BaseException:
        if reserved:
            try:
                with GuardedLedger(ledger_path,owner) as g:
                    g.db.execute('BEGIN IMMEDIATE');g.db.execute("UPDATE rollbacks SET state='UNKNOWN' WHERE operation_id=? AND state IN ('ROLLBACK_PREPARED','SWITCHED')",(rollback_op,));g.db.execute('COMMIT')
            except Exception:pass
        raise
    finally:
        if lock is not None:os.close(lock)
        os.close(rootfd)
