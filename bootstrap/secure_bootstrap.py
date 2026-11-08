#!/usr/bin/env python3
"""Independent pre-execution verifier. No carrier imports. Candidate, not deployed."""
import argparse, base64, hashlib, io, json, os, re, sqlite3, stat, sys, tarfile, time

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

def consume(db_path, receipt, owner=0):
    # The controller provisions the DB and WAL mode. Do not create missing DB/schema.
    require(os.path.isabs(db_path) and os.path.isfile(db_path) and not os.path.islink(db_path),'LEDGER_REQUIRED')
    st=os.stat(db_path);require(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==owner and not st.st_mode&0o077,'LEDGER_PERMISSIONS')
    db=sqlite3.connect('file:'+db_path+'?mode=rw',uri=True,timeout=5,isolation_level=None)
    try:
        require(db.execute('PRAGMA journal_mode').fetchone()[0].lower()=='wal','WAL_REQUIRED')
        db.execute('BEGIN IMMEDIATE')
        require(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='operations'").fetchone() is not None,'LEDGER_SCHEMA')
        require(db.execute("SELECT 1 FROM operations WHERE task=? AND attempt=?",(receipt['task'],receipt['attempt'])).fetchone() is None,'ATTEMPT_IN_FLIGHT')
        db.execute('INSERT INTO operations(nonce,task,attempt,state) VALUES(?,?,?,?)',(receipt['nonce'],receipt['task'],receipt['attempt'],'RESERVED'))
        db.execute('COMMIT')
    except Exception:
        if db.in_transaction: db.execute('ROLLBACK')
        raise
    finally: db.close()

def verify(carrier_fd,manifest_fd,receipt_fd,trust_fd,ledger_path,log_fd,scope,owner=0,now=None):
    # Check the supplied evidence sink before reserving a nonce or reading carrier.
    ls=os.fstat(log_fd);require(stat.S_ISREG(ls.st_mode) and ls.st_nlink==1 and ls.st_uid==owner and not ls.st_mode&0o022,'LOG_REQUIRED')
    trust=parse(stable_read(trust_fd,owner,65536));require(trust.get('mode') in ('ED25519','DIGEST_ALLOWLIST'),'TRUST_ANCHOR_REQUIRED')
    require(trust.get('environment') in ('PRODUCTION','TEST_ONLY'),'TRUST_ENVIRONMENT_REQUIRED')
    receipt=parse(stable_read(receipt_fd,owner,65536));require(set(receipt)=={'payload','signature'},'RECEIPT_FORMAT')
    p=receipt['payload'];keys={'carrier_sha256','manifest_sha256','task','attempt','nonce','expiry','controller'}
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
    manifest=parse(manifest_raw);require(set(manifest)=={'members'},'MANIFEST_FIELDS');inspect_archive(carrier,manifest['members'])
    consume(ledger_path,p,owner)
    os.write(log_fd,(json.dumps({'event':'VERIFIED_RESERVED','nonce':p['nonce'],'carrier_sha256':p['carrier_sha256']},sort_keys=True)+'\n').encode());os.fsync(log_fd)
    return carrier,p

def main():
    a=argparse.ArgumentParser();
    for n in ('carrier-fd','manifest-fd','receipt-fd','trust-fd','log-fd'): a.add_argument('--'+n,type=int,required=True)
    for n in ('ledger','task','attempt','root'):a.add_argument('--'+n,required=True)
    x=a.parse_args()
    try:
        from controller import run
        target=run(x.carrier_fd,x.manifest_fd,x.receipt_fd,x.trust_fd,x.ledger,x.log_fd,{'task':x.task,'attempt':x.attempt},x.root);print('INSTALLED '+target)
    except Exception as e: print('HOLD '+type(e).__name__+': '+str(e),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
