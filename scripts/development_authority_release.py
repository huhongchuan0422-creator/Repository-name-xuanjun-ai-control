"""Signed fail-closed release verification and reversible local lifecycle."""
import argparse, base64, fcntl, hashlib, json, os, shutil, tempfile, time
from development_authority import canonical_bytes, load_private_key, load_public_key
from secure_file_input import read_owned_secret_file

REJECT=69
FIELDS={'schema','artifact','artifact_sha256','source_sha256','commit','tree',
        'created_at','deployment_authorized','signature'}
SIG_FIELDS={'algorithm','anchor_id','canonical_sha256','value'}

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def _unsigned(artifact,commit,tree,source_sha256,created_at=None):
    if not (len(commit)==40 and len(tree)==40 and len(source_sha256)==64):
        raise ValueError('EXACT_SOURCE_BINDING_REQUIRED')
    return {'schema':2,'artifact':os.path.basename(artifact),'artifact_sha256':sha256(artifact),
      'source_sha256':source_sha256,'commit':commit,'tree':tree,
      'created_at':int(time.time() if created_at is None else created_at),
      'deployment_authorized':False}

def manifest(artifact,commit,tree,source_sha256=None,private_key=None,anchor_id=None,created_at=None):
    source_sha256=source_sha256 or sha256(artifact)
    value=_unsigned(artifact,commit,tree,source_sha256,created_at)
    if private_key is None: return value # compatibility helper; CLI always signs
    raw=canonical_bytes(value)
    value['signature']={'algorithm':'Ed25519','anchor_id':anchor_id,
      'canonical_sha256':hashlib.sha256(raw).hexdigest(),
      'value':base64.b64encode(private_key.sign(raw)).decode('ascii')}
    return value

def verify(artifact,data,public_key,anchor_id,commit,tree,source_sha256):
    if not isinstance(data,dict) or set(data)!=FIELDS: raise ValueError('EXACT_MANIFEST_SCHEMA_REQUIRED')
    sig=data['signature']; unsigned={k:v for k,v in data.items() if k!='signature'}
    if (not isinstance(sig,dict) or set(sig)!=SIG_FIELDS or sig['algorithm']!='Ed25519'
        or sig['anchor_id']!=anchor_id): raise ValueError('MANIFEST_SIGNATURE_SCHEMA_REQUIRED')
    raw=canonical_bytes(unsigned)
    if sig['canonical_sha256']!=hashlib.sha256(raw).hexdigest(): raise ValueError('MANIFEST_DIGEST_INVALID')
    try: public_key.verify(base64.b64decode(sig['value'],validate=True),raw)
    except Exception: raise ValueError('MANIFEST_SIGNATURE_INVALID')
    expected={'schema':2,'artifact':os.path.basename(artifact),'artifact_sha256':sha256(artifact),
      'source_sha256':source_sha256,'commit':commit,'tree':tree,'deployment_authorized':False}
    if any(unsigned.get(k)!=v for k,v in expected.items()): raise ValueError('MANIFEST_BINDING_INVALID')
    if not isinstance(unsigned.get('created_at'),int): raise ValueError('MANIFEST_CREATED_AT_INVALID')
    return {'verified':True,'artifact_sha256':expected['artifact_sha256'],'commit':commit,'tree':tree}

def _atomic(path,value):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=os.path.dirname(path)); os.close(fd)
    try:
        with open(tmp,'w') as out: json.dump(value,out,sort_keys=True); out.flush(); os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def lifecycle(root,command,artifact=None,verified=None,operation_id=None,
              expected_generation=None,expected_status=None):
    os.makedirs(root,exist_ok=True)
    lock=open(os.path.join(root,'.lifecycle.lock'),'a+')
    fcntl.flock(lock,fcntl.LOCK_EX)
    try:
        return _lifecycle_locked(root,command,artifact,verified,operation_id,
                                 expected_generation,expected_status)
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN); lock.close()

def _lifecycle_locked(root,command,artifact=None,verified=None,operation_id=None,
                      expected_generation=None,expected_status=None):
    state_path=os.path.join(root,'state.json'); receipts=os.path.join(root,'receipts')
    state=json.load(open(state_path)) if os.path.exists(state_path) else {'generation':0,'status':'EMPTY','active':None,'backup':None,'pending':None}
    if command=='inspect':
        active=state.get('active'); path=os.path.join(root,'artifacts',active) if active else None
        return {'state':state,'state_sha256':sha256(state_path) if os.path.exists(state_path) else None,
          'active_observed':sha256(path) if path and os.path.isfile(path) else None}
    if command=='query': return {'state':state,'receipt_files':sorted(os.listdir(receipts)) if os.path.isdir(receipts) else []}
    if command=='apply':
        if not verified or verified.get('verified') is not True: raise ValueError('VERIFIED_MANIFEST_REQUIRED')
        os.makedirs(os.path.join(root,'artifacts'),exist_ok=True); digest=sha256(artifact)
        pending={'generation':state['generation']+1,'status':'APPLYING','active':state.get('active'),
          'backup':state.get('backup'),'pending':digest}; _atomic(state_path,pending)
        target=os.path.join(root,'artifacts',digest)
        try: shutil.copyfile(artifact,target)
        except Exception:
            pending['status']='UNKNOWN'; _atomic(state_path,pending); raise
        if sha256(target)!=digest:
            pending['status']='UNKNOWN'; _atomic(state_path,pending); raise ValueError('APPLY_COPY_UNKNOWN')
        state={'generation':pending['generation'],'status':'ACTIVE','active':digest,
          'backup':pending.get('active'),'pending':None}
    elif command=='recover':
        if not isinstance(operation_id,str) or not operation_id: raise ValueError('RECOVERY_OPERATION_ID_REQUIRED')
        operation_path=os.path.join(receipts,'recover-'+hashlib.sha256(operation_id.encode()).hexdigest()+'.json')
        request={'operation_id':operation_id,'expected_generation':expected_generation,
                 'expected_status':expected_status}
        request_digest=hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if os.path.isfile(operation_path):
            operation=json.load(open(operation_path))
            if operation.get('request_digest')!=request_digest:
                raise ValueError('RECOVERY_OPERATION_REQUEST_MISMATCH')
            if operation.get('status')=='COMPLETED': return operation['receipt']
            receipt=operation['receipt']
            if state==receipt['state']:
                operation['status']='COMPLETED'; _atomic(operation_path,operation)
                return receipt
            raise ValueError('RECOVERY_OPERATION_UNKNOWN_REQUIRES_RECONCILIATION')
        if state.get('generation')!=expected_generation or state.get('status')!=expected_status:
            raise ValueError('RECOVERY_EXPECTED_STATE_CAS_FAILED')
        if state.get('status')=='UNKNOWN' and state.get('pending'):
            target=os.path.join(root,'artifacts',state['pending'])
            if os.path.isfile(target) and sha256(target)==state['pending']:
                state={'generation':state['generation']+1,'status':'ACTIVE','active':state['pending'],
                  'backup':state.get('active'),'pending':None}
            elif state.get('active'):
                state={'generation':state['generation']+1,'status':'ACTIVE','active':state['active'],
                  'backup':state.get('backup'),'pending':None}
            else: raise ValueError('UNKNOWN_RECOVERY_EVIDENCE_REQUIRED')
        else:
            if not state.get('backup'): raise ValueError('RECOVERABLE_BACKUP_REQUIRED')
            state={'generation':state['generation']+1,'status':'ACTIVE','active':state['backup'],
              'backup':state['active'],'pending':None}
    else: raise ValueError('LIFECYCLE_COMMAND_REQUIRED')
    receipt={'command':command,'state':state,'observed_at':int(time.time())}
    if command=='recover':
        receipt['operation_id']=operation_id; receipt['request_digest']=request_digest
        _atomic(operation_path,{'status':'PREPARED','request_digest':request_digest,
                                'receipt':receipt})
    _atomic(state_path,state)
    _atomic(os.path.join(receipts,'%08d-%s.json'%(state['generation'],command)),receipt)
    if command=='recover': _atomic(operation_path,{'status':'COMPLETED',
      'request_digest':request_digest,'receipt':receipt})
    return receipt

def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command')
    m=sub.add_parser('manifest'); v=sub.add_parser('verify')
    for x in (m,v):
        x.add_argument('--artifact',required=True); x.add_argument('--commit',required=True); x.add_argument('--tree',required=True); x.add_argument('--source-sha256',required=True); x.add_argument('--anchor-id',required=True)
    m.add_argument('--private-key-file',required=True); v.add_argument('--manifest',required=True); v.add_argument('--public-key-file',required=True)
    for name in ('inspect','query'):
        q=sub.add_parser(name); q.add_argument('--root',required=True)
    q=sub.add_parser('recover'); q.add_argument('--root',required=True)
    q.add_argument('--operation-id',required=True)
    q.add_argument('--expected-generation',required=True,type=int)
    q.add_argument('--expected-status',required=True)
    a=sub.add_parser('apply'); a.add_argument('--root',required=True); a.add_argument('--artifact',required=True); a.add_argument('--verified-receipt',required=True)
    a=p.parse_args(argv)
    if a.command is None: p.error('a command is required')
    try:
        if a.command=='manifest':
            key=load_private_key(read_owned_secret_file(a.private_key_file,'RELEASE_PRIVATE_KEY').encode()); print(json.dumps(manifest(a.artifact,a.commit,a.tree,a.source_sha256,key,a.anchor_id),sort_keys=True)); return 0
        if a.command=='verify':
            key=load_public_key(read_owned_secret_file(a.public_key_file,'RELEASE_PUBLIC_KEY').encode()); result=verify(a.artifact,json.load(open(a.manifest)),key,a.anchor_id,a.commit,a.tree,a.source_sha256); print(json.dumps(result,sort_keys=True)); return 0
        if a.command=='apply': result=lifecycle(a.root,'apply',a.artifact,json.load(open(a.verified_receipt)))
        elif a.command=='recover': result=lifecycle(a.root,a.command,
          operation_id=a.operation_id,expected_generation=a.expected_generation,
          expected_status=a.expected_status)
        else: result=lifecycle(a.root,a.command)
        print(json.dumps(result,sort_keys=True)); return 0
    except Exception as exc: print(json.dumps({'verified':False,'error':str(exc)},sort_keys=True)); return REJECT

if __name__=='__main__': raise SystemExit(main())
