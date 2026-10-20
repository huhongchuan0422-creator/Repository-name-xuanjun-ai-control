"""Thin ISOLATED_NEW epoch1 adapter over the unchanged ActivationStore.
No database, socket, service, production path or old epoch recovery operation.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import uuid

STORE_SOURCE = 'evidence/p2-epoch7-access-repair-20261014/runtime/stage1/activation_control.py'
STORE_SHA = '169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4'
ROOT = '/var/lib/xuanjun-p2-isolated-test/b3-initialize'
MANIFEST_SHA = '591855b35c820c486ae07bbb91e681b983a3a2310feaedb57ae7c87fc9b66592'
B1_RECEIPT_SHA = '2aa0616f8d9cc57e4dc367198fcb40b1d9cfe88ffa46221273c62cf4ad6e069a'


def need(ok, reason):
    if not ok: raise ValueError(reason)


def encode(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def stamp(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def read(path, limit=1048576):
    path=Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'ABSOLUTE_PATH')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=nxt
        item=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(item,'rb') as stream:
            before=os.fstat(stream.fileno())
            need(stat.S_ISREG(before.st_mode) and not before.st_mode & 0o022 and before.st_size<=limit,'FILE_PROTECTION:'+str(path))
            raw=stream.read(limit+1)
            need(stamp(before)==stamp(os.fstat(stream.fileno())) and len(raw)==before.st_size,'FILE_CHANGED')
            return raw
    finally:os.close(fd)


def sync(path):
    fd=os.open(str(path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def publish(path, raw):
    if os.path.lexists(str(path)):
        need(read(path)==raw,'IMMUTABLE_CONFLICT');return
    pending=path.parent/('.'+path.name+'.pending-'+uuid.uuid4().hex)
    fd=os.open(str(pending),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as out:
        out.write(raw);out.flush();os.fsync(out.fileno())
    # Both names intentionally retained, including on interruption.
    try:os.link(str(pending),str(path))
    except FileExistsError:need(read(path)==raw,'PUBLICATION_CONFLICT')
    sync(path.parent)


def directory(path):
    if not os.path.lexists(str(path)):
        path.mkdir(mode=0o700);sync(path.parent)
    s=os.lstat(str(path))
    need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o700,'PRIVATE_DIRECTORY')


def store_module():
    path=Path(__file__).resolve().parents[2]/STORE_SOURCE
    raw=read(path)
    need(sha(raw)==STORE_SHA,'STORE_SOURCE_CHANGED')
    module=importlib.util.module_from_spec(importlib.util.spec_from_file_location('b3_original_store',str(path)))
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def _checkpoint(_name): pass  # test injection only; never selected by a request


def validate(req):
    need(isinstance(req,dict) and set(req)=={'schema','scope','origin','installation_id','batch_id','attempt_id',
         'root','source_root','config','config_sha256','binary','descriptor'},'REQUEST_FIELDS')
    need(req['schema']==1 and req['scope']=='ISOLATED_TEST_ONLY' and req['origin']=='ISOLATED_NEW','SCOPE')
    need((req['installation_id'],req['batch_id'],req['attempt_id'])==
         ('p2-uk-isolated-20261020','b3-initialize','b3-initialize-a1'),'FIXED_IDENTITY')
    root=Path(req['root'])
    fixture=str(root).startswith('/tmp/p2-b3-test-') and root.name=='b3-initialize'
    need(str(root)==ROOT or fixture,'ROOT_SCOPE')
    need(str(root.resolve())==str(root),'ROOT_LINK')
    directory_existing=os.lstat(str(root))
    need(stat.S_ISDIR(directory_existing.st_mode) and directory_existing.st_uid==os.geteuid()
         and stat.S_IMODE(directory_existing.st_mode)==0o700,'ROOT_PRIVATE')
    source=Path(req['source_root'])
    need(str(source)==('/input/sources' if not fixture else str(root.parent/'sources')),'SOURCE_SCOPE')
    need(sha(read(source/'MANIFEST.json'))==MANIFEST_SHA and
         sha(read(source/'b1-receipt.json'))==B1_RECEIPT_SHA,'B1_SOURCE_BINDING')
    cfg=req['config'];need(sha(encode(cfg))==req['config_sha256'],'CONFIG_SHA')
    need(cfg['origin']=='ISOLATED_NEW' and cfg['scope']=='ISOLATED_TEST_ONLY' and
         all(cfg[k]==req[k] for k in ('installation_id','batch_id','attempt_id')),'CONFIG_IDENTITY')
    need(cfg['release_manifest_sha256']==MANIFEST_SHA and cfg['initial_epoch']==1 and cfg['initial_state']=='PREPARED'
         and cfg['generation']==1 and all(cfg[k] is False for k in ('start_services','create_database','bind_socket')),'PREPARED_ONLY')
    need(cfg['db_path']==str(root/'data/ledger.sqlite3') and cfg['ledger_socket']==str(root/'run/ledger.sock'),'RESERVED_PATHS')
    binary=req['binary']
    need(isinstance(binary,dict) and set(binary)=={'path','bytes','sha256'} and binary['sha256']
         and len(binary['sha256'])==64,'BINARY_PIN_REQUIRED')
    path=os.path.realpath(sys.executable)
    need(path==binary['path'],'BINARY_PATH')
    raw=read(Path(path),32*1024*1024)
    need(len(raw)==binary['bytes'] and sha(raw)==binary['sha256'],'BINARY_CHANGED')
    module=store_module();Store=module.ActivationStore
    expected={'schema':1,'state':'PREPARED','epoch':1,'release_sha256':MANIFEST_SHA,
        'config_sha256':req['config_sha256'],'binary_sha256':binary['sha256'],
        'ledger_uuid':cfg['ledger_uuid'],'generation':1,'instance':cfg['instance'],
        'db_path':cfg['db_path'],'ledger_socket':cfg['ledger_socket']}
    need(Store.validate(req['descriptor'])==expected,'DESCRIPTOR_IDENTITY')
    return root,module,expected


def dispatch(req, action, request_sha256):
    result={'schema':1,'scope':'ISOLATED_TEST_ONLY','origin':'ISOLATED_NEW',
        'installation_id':req.get('installation_id') if isinstance(req,dict) else None,
        'batch_id':'b3-initialize','attempt_id':'b3-initialize-a1','status':'HOLD',
        'receipt':None,'production_permission':False,'full_b3_complete':False}
    lock=None
    try:
        need(action in ('execute','inspect','recover'),'ACTION')
        need(sha(encode(req))==request_sha256,'REQUEST_SHA')
        root,module,expected=validate(req)
        need(not os.path.lexists(str(root/'data/ledger.sqlite3')) and not os.path.lexists(str(root/'run/ledger.sock')),'UNEXPECTED_DB_OR_SOCKET')
        lock=os.open(str(root/'.initialize.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        info=os.fstat(lock)
        need(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1
             and stat.S_IMODE(info.st_mode)==0o600,'LOCK_IDENTITY')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        intent=root/'intent.json';config=root/'binding-config.json';receipt=root/'commit-receipt.json'
        activation=root/'activation'
        existed=os.path.lexists(str(intent))
        if not existed:
            need(not any(os.path.lexists(str(p)) for p in (config,receipt,activation)),'UNOWNED_PARTIAL_STATE')
            if action=='inspect':result['status']='NO_EFFECT';return result
            publish(intent,encode({'schema':1,'origin':'ISOLATED_NEW','request_sha256':request_sha256,'request':req}))
            _checkpoint('after_intent')
        else:
            need(read(intent)==encode({'schema':1,'origin':'ISOLATED_NEW','request_sha256':request_sha256,'request':req}),'REQUEST_CONFLICT')
        repairing=action=='recover' or (action=='execute' and not existed)
        if repairing:
            publish(config,encode(req['config']));_checkpoint('after_config')
            directory(activation)
        else:
            need(read(config)==encode(req['config']),'CONFIG_CONFLICT')
            need(activation.is_dir(),'ACTIVATION_MISSING_RECOVER_REQUIRED')
        directory(activation)
        for name in ('active.json','epochs.jsonl','activation.lock'):
            path=activation/name
            if os.path.lexists(str(path)):
                read(path,16*1024*1024)
                s=os.lstat(str(path))
                need(s.st_uid==os.geteuid() and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o644,'ACTIVATION_FILE_IDENTITY')
        store=module.ActivationStore(str(activation/'active.json'),str(activation/'epochs.jsonl'),
                                    str(activation/'activation.lock'),owner_uid=os.geteuid())
        rows=store._journal()
        if not rows:
            need(not os.path.lexists(str(activation/'epochs.jsonl')) and
                 not os.path.lexists(str(activation/'active.json')) and repairing,'MISSING_OR_PARTIAL_HISTORY_HOLD')
            args={k:expected[k] for k in ('release_sha256','config_sha256','binary_sha256','ledger_uuid','generation','instance','db_path','ledger_socket')}
            # Only the unchanged original Store performs append/descriptor writes.
            store.prepare(expected_epoch=0,**args)
            rows=store._journal()
        need(len(rows)==1 and rows[0][0]['descriptor']==expected and rows[0][0]['proof']=={},'NEW_EPOCH1_IDENTITY')
        journal=activation/'epochs.jsonl';descriptor=activation/'active.json'
        need(read(journal)==encode(rows[0][0])+b'\n','JOURNAL_CANONICAL')
        if not os.path.lexists(str(descriptor)):
            need(repairing,'DESCRIPTOR_MISSING_RECOVER_REQUIRED')
            store.reconcile()
        need(store.read(require_active=False)==expected and read(descriptor)==encode(expected)+b'\n','DESCRIPTOR_CONFLICT')
        _checkpoint('before_receipt')
        payload={'schema':1,'scope':'ISOLATED_TEST_ONLY','origin':'ISOLATED_NEW','status':'COMMITTED',
            'installation_id':req['installation_id'],'batch_id':req['batch_id'],'attempt_id':req['attempt_id'],
            'request_sha256':request_sha256,'config_sha256':req['config_sha256'],
            'descriptor_head_sha256':store.head(expected),'journal_sha256':sha(read(journal)),
            'descriptor_file_sha256':sha(read(descriptor)),'binary_sha256':req['binary']['sha256'],
            'full_b3_complete':False,'database':'RESERVED_NOT_CREATED','socket':'RESERVED_NOT_BOUND'}
        if repairing:publish(receipt,encode(payload))
        need(read(receipt)==encode(payload),'RECEIPT_CONFLICT')
        need(not os.path.lexists(str(root/'data/ledger.sqlite3')) and
             not os.path.lexists(str(root/'run/ledger.sock')),'UNEXPECTED_DB_OR_SOCKET')
        result.update(status='COMMITTED',receipt={'path':str(receipt),'sha256':sha(read(receipt))},
                      descriptor_head_sha256=store.head(expected))
    except Exception as exc:
        result['error']={'type':type(exc).__name__,'code':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
    finally:
        if lock is not None:os.close(lock)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('execute','inspect','recover'))
    parser.add_argument('--request-sha256',required=True);args=parser.parse_args()
    req=json.loads(sys.stdin.buffer.read(1048577))
    result=dispatch(req,args.action,args.request_sha256)
    print(json.dumps(result,sort_keys=True));return 0 if result['status'] in ('COMMITTED','NO_EFFECT') else 2

if __name__=='__main__':sys.exit(main())
