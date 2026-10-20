#!/bin/sh
# CANDIDATE ONLY: onsite execution requires separate Owner confirmation.
sudo -n /usr/bin/python3 -I -B -S - <<'SHOWCASE_READONLY'
"""Fixed diagnostic only, no enrollment/build API. Python >=3.6, stdlib only.

Reuse PR122 readonly_probe.identity FD/hash/drift pattern and showcase
private_bytes root/0600/single-link policy; add dir-FD ancestor/path rechecks.
No imports of production builder, trust verifier, credentials or executable code.
"""
import errno,hashlib,json,os,re,signal,stat,sys,time
HOST='iZvt5t8tlrm8oiZ'
TARGETS=('/etc/xuanjun-showcase/INDEPENDENT_REVIEW_TRUST.json','/etc/xuanjun-showcase/BUILDER_POLICY.json')
ANCHOR='6214465866'
BODY='156711523974f62e2f9df7753af9af3d1879c5f45678ace617b0ed2471aa181c'
MAX_BYTES=1000000
MAX_OUTPUT=16384
class Unknown(Exception):pass
def require(ok,code):
    if not ok:raise Unknown(code)
def ident(s):return tuple(getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
def metadata(s):
    return dict(size=s.st_size,uid=s.st_uid,gid=s.st_gid,mode=format(stat.S_IMODE(s.st_mode),'04o'),nlink=s.st_nlink,type='REGULAR' if stat.S_ISREG(s.st_mode) else 'DIRECTORY' if stat.S_ISDIR(s.st_mode) else 'OTHER')
def bounded_json(raw):
    # Bound nesting before json decoding (also works on Python3.6).
    depth=0;quoted=False;escape=False
    for c in raw.decode('utf8'):
        if quoted:
            if escape:escape=False
            elif c=='\\':escape=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c in '[{':
            depth+=1;require(depth<=12,'JSON_DEPTH')
        elif c in ']}':depth-=1
    total=[0]
    def pairs(items):
        total[0]+=len(items);require(total[0]<=12000 and len(items)<=1000,'JSON_FIELDS')
        out={}
        for k,v in items:
            require(k not in out and len(k)<=128,'JSON_KEYS');out[k]=v
        return out
    def integer(s):require(len(s)<=20,'JSON_NUMBER');return int(s)
    def forbidden(s):raise Unknown('JSON_NUMBER_TYPE')
    value=json.loads(raw.decode('utf8'),object_pairs_hook=pairs,parse_int=integer,parse_float=forbidden,parse_constant=forbidden)
    stack=[value];nodes=0
    while stack:
        x=stack.pop();nodes+=1;require(nodes<=20000,'JSON_NODES')
        if type(x) is dict:stack.extend(x.values())
        elif type(x) is list:require(len(x)<=1000,'JSON_ARRAY');stack.extend(x)
        elif type(x) is str:require(len(x)<=4096,'JSON_STRING')
    return value
def digest_field(x):return type(x) is str and re.fullmatch('[0-9a-f]{64}',x) is not None
def principal(x):return type(x) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}',x) is not None
def selected(raw,trust,now):
    v=bounded_json(raw);require(type(v) is dict,'JSON_SCHEMA')
    if not trust:
        keys={'schema','mechanism_manifest_sha256','shell_tar_sha256','legacy_pages_sha256','reviewer_logins'}
        require(set(v)==keys and type(v['schema']) is int and v['schema']==1,'POLICY_SCHEMA')
        require(all(digest_field(v[k]) for k in keys-{'schema','reviewer_logins'}),'POLICY_DIGEST')
        logins=v['reviewer_logins'];require(type(logins) is list and 0<len(logins)<=100 and all(type(x) is str and re.fullmatch('[A-Za-z0-9-]{1,100}',x) for x in logins),'POLICY_REVIEWERS')
        return dict(schema=1,mechanism_manifest_sha256=v['mechanism_manifest_sha256'],shell_tar_sha256=v['shell_tar_sha256'],legacy_pages_sha256=v['legacy_pages_sha256'],reviewer_logins_count=len(logins),reviewer_logins_sha256=hashlib.sha256(json.dumps(logins,separators=(',',':')).encode('utf8')).hexdigest())
    require(set(v)=={'schema','source_writer_principal','reviewers','revoked_review_ids','anchors'} and type(v['schema']) is int and v['schema']==1,'TRUST_SCHEMA')
    require(principal(v['source_writer_principal']) and type(v['reviewers']) is dict and type(v['anchors']) is dict,'TRUST_FIELDS')
    revoked=v['revoked_review_ids'];require(type(revoked) is list and all(type(x) is int and x>0 for x in revoked),'TRUST_REVOKED')
    out=dict(schema=1,source_writer_principal=v['source_writer_principal'],target_comment_id=int(ANCHOR),independence='UNKNOWN_NOT_ATTESTED',custody_provenance='UNKNOWN_NOT_ATTESTED')
    if ANCHOR not in v['anchors']:out['target_anchor']='NOT_PRESENT_IN_OBSERVED_DOCUMENT';return out
    a=v['anchors'][ANCHOR]
    require(type(a) is dict and set(a)=={'body_sha256','scope','reviewer_principal','custody_evidence_sha256','issued_unix','expires_unix'},'ANCHOR_SCHEMA')
    require(principal(a['reviewer_principal']) and digest_field(a['body_sha256']) and digest_field(a['custody_evidence_sha256']) and a['scope'] in ('CONTENT','MECHANISM','PUBLICATION'),'ANCHOR_FIELDS')
    start,end=a['issued_unix'],a['expires_unix'];require(type(start) is int and type(end) is int and 0<=start<end and end-start<=7*86400,'ANCHOR_TIME')
    r=v['reviewers'].get(a['reviewer_principal']);require(type(r) is dict and set(r)=={'status','custody_evidence_sha256'} and r['status'] in ('ACTIVE','REVOKED') and digest_field(r['custody_evidence_sha256']),'REVIEWER_SCHEMA')
    out.update(target_anchor='OBSERVED',reviewer_principal=a['reviewer_principal'],custody_evidence_sha256=a['custody_evidence_sha256'],body_sha256=a['body_sha256'],scope=a['scope'],issued_unix=start,expires_unix=end,target_review_revoked=int(ANCHOR) in revoked,reviewer_status=r['status'],custody_digest_matches=r['custody_evidence_sha256']==a['custody_evidence_sha256'],writer_reviewer_distinct=v['source_writer_principal']!=a['reviewer_principal'],expected_content_binding=a['body_sha256']==BODY and a['scope']=='CONTENT',time_window='CURRENT_AT_OBSERVATION' if start<=now<end else 'NOT_YET_VALID' if now<start else 'EXPIRED')
    return out
def observe(path,trust,now=None,checkpoint=None):
    """Path is constant in main; fixtures alone may pass an isolated path."""
    result=dict(path=path,existence='UNKNOWN',observation='UNKNOWN',registration='UNKNOWN',ancestors=[])
    fds=[];nodes=[];fd=None
    def stable():
        for parent,name,before in nodes:
            require(ident(os.stat(name,dir_fd=parent,follow_symlinks=False))==before,'PATH_CHANGED')
    try:
        current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);fds.append(current)
        root=os.fstat(current);result['ancestors'].append(dict(path='/',protected=root.st_uid==root.st_gid==0 and not root.st_mode&0o022,**metadata(root)))
        require(root.st_uid==root.st_gid==0 and not root.st_mode&0o022,'UNPROTECTED_ANCESTOR')
        parts=path.strip('/').split('/');prefix=''
        for i,name in enumerate(parts):
            final=i==len(parts)-1;prefix+='/'+name
            try:s=os.stat(name,dir_fd=current,follow_symlinks=False)
            except FileNotFoundError:
                stable()
                try:os.stat(name,dir_fd=current,follow_symlinks=False)
                except FileNotFoundError:pass
                else:raise Unknown('MISSING_PATH_CHANGED')
                result.update(existence='ABSENT',observation='ABSENT_AT_OBSERVATION',missing_component=prefix);return result
            nodes.append((current,name,ident(s)))
            if final:
                result.update(existence='PRESENT',metadata=metadata(s),protected=stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1)
                require(stat.S_ISREG(s.st_mode),'TYPE_MISMATCH')
                # Never read a file failing the original root-private input policy.
                require(result['protected'],'UNPROTECTED_FILE');require(s.st_size<=MAX_BYTES,'FILE_BOUND')
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=current)
                require(ident(os.fstat(fd))==ident(s),'OPEN_CHANGED');before=ident(s)
            else:
                protected=stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and not s.st_mode&0o022
                result['ancestors'].append(dict(path=prefix,protected=bool(protected),**metadata(s)))
                require(protected,'UNPROTECTED_ANCESTOR')
                nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current);fds.append(nxt)
                require(ident(os.fstat(nxt))==ident(s),'OPEN_CHANGED');current=nxt
        h=hashlib.sha256();chunks=[];total=0
        while True:
            b=os.read(fd,min(65536,MAX_BYTES+1-total))
            if not b:break
            total+=len(b);require(total<=MAX_BYTES,'FILE_BOUND');h.update(b);chunks.append(b)
        if checkpoint:checkpoint()
        require(ident(os.fstat(fd))==before and total==before[6],'FILE_CHANGED');stable()
        result.update(observation='STABLE_BYTES_OBSERVED',sha256=h.hexdigest())
        try:result['selected']=selected(b''.join(chunks),trust,time.time() if now is None else now)
        except Exception as e:result.update(fields='UNKNOWN',field_reason=str(e) if isinstance(e,Unknown) else 'INVALID_JSON')
        stable();require(ident(os.fstat(fd))==before,'FILE_CHANGED')
    except OSError as e:
        result.pop('sha256',None);result.pop('selected',None)
        result.update(observation='ACCESS_DENIED' if e.errno in (errno.EACCES,errno.EPERM) else 'UNKNOWN',reason='ACCESS_DENIED' if e.errno in (errno.EACCES,errno.EPERM) else 'PATH_OR_IO_ERROR')
    except Unknown as e:
        if str(e)=='TIME_BOUND':raise
        result.pop('sha256',None);result.pop('selected',None);result.update(observation='UNKNOWN',reason=str(e))
    finally:
        if fd is not None:os.close(fd)
        for d in reversed(fds):os.close(d)
    return result
def main():
    if sys.version_info<(3,6) or os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=HOST:
        print('{"state":"UNKNOWN","reason":"FIXED_HOST_ROOT_REQUIRED"}');return 2
    def timeout(signum,frame):raise Unknown('TIME_BOUND')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(15)
    try:
        result=dict(schema=1,state='READONLY_OBSERVATION_NOT_AUTHORIZATION',host=HOST,python_version=list(sys.version_info[:3]),observed_unix=int(time.time()),results=[observe(TARGETS[0],True),observe(TARGETS[1],False)],independence='UNKNOWN_NOT_ATTESTED',target_content_mutations=0)
        raw=json.dumps(result,sort_keys=True,separators=(',',':'));require(len(raw.encode('utf8'))<=MAX_OUTPUT,'OUTPUT_BOUND');print(raw);return 0
    except Exception:
        print('{"state":"UNKNOWN","reason":"QUERY_INCOMPLETE"}');return 2
    finally:signal.alarm(0)
if __name__=='__main__':sys.exit(main())
SHOWCASE_READONLY
