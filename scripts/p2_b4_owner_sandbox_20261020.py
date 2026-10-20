"""Python3.6.8 host wrapper: finite B4 only; pending Owner action approval."""
import argparse,base64,fcntl,hashlib,io,json,os,stat,sys,tarfile,traceback,types
from pathlib import Path

HOST='iZd7oeikknn1z21sq6ji6zZ'
BASE=Path('/var/lib/xuanjun-p2-isolated-test')
WORK=BASE/'b4-sandbox-inputs-20261020'
ROOT=BASE/'b4-sandbox'
PRIOR=BASE/'b3-initialize'
IMAGE='sha256:5341f193a5741b64f2acc63a99dc95910289fcc39ff17dacff373a50e233724d'
B3_RECEIPT='34d1530271efaabb4b65c5c44d2e76bd04258247dfc36a9a613aa829ec18dc8b'
B3_PROOF='ef6dba0af499c95d79f83decbd827be94ebfb947c8e16324d7a062dfda7583b2'
TRANSPORT_SHA='91e77a767752f3714cd670e41ae6eebf6c834707b016b59a9fbe81cab344b753'
RUNTIME='evidence/p2-epoch7-access-repair-20261014/runtime/stage1'


def need(ok,code):
    if not ok:raise ValueError(code)


def transport(bundle,pin):
    need(hashlib.sha256(bundle).hexdigest()==pin,'B4_BUNDLE_SHA')
    packet=json.loads(bundle.decode('ascii'));archive=base64.b64decode(packet['tar_b64'].encode('ascii'),validate=True)
    need(len(archive)==packet['tar_bytes'] and hashlib.sha256(archive).hexdigest()==packet['tar_sha256'],'B4_TAR_SHA')
    target='scripts/p2_b3_owner_finalize_20261020.py'
    with tarfile.open(fileobj=io.BytesIO(archive)) as t:
        matches=[m for m in t.getmembers() if m.name==target]
        need(len(matches)==1 and matches[0].isfile() and matches[0].size<=1048576,'B4_TRANSPORT_ENTRY')
        raw=t.extractfile(matches[0]).read(1048577)
    need(hashlib.sha256(raw).hexdigest()==TRANSPORT_SHA,'B4_TRANSPORT_SHA')
    h=types.ModuleType('pinned_b3_transport');h.__file__=str(WORK/'sources'/target)
    exec(compile(raw,target,'exec'),h.__dict__);return h


def private_uid_directory(path):
    if not os.path.lexists(str(path)):
        path.mkdir(mode=0o700);os.chown(str(path),1002,1002)
    s=os.lstat(str(path));need(stat.S_ISDIR(s.st_mode) and (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(1002,1002,0o700),'B4_PRIVATE_UID_DIRECTORY')


def prior_snapshot(h):
    out={}
    for path in [PRIOR]+sorted(PRIOR.rglob('*')):
        info=os.lstat(str(path));need(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),'B4_PRIOR_SPECIAL_OR_LINK')
        row={'metadata':h.meta(path),'kind':'DIRECTORY' if stat.S_ISDIR(info.st_mode) else 'FILE'}
        if row['kind']=='FILE':row['sha256']=h.digest(h.read(path))
        out[str(path)]=row
    return out


def verify_role(h,role,result,request_sha):
    need(result['status']=='CP10_FINITE_COMMITTED' and result['role']==role and result['service_started'] is False,'B4_ROLE_RESULT')
    folder=ROOT/role;path=folder/'CP10-committed.json'
    need(result['receipt']['path']==str(path) and h.digest(h.read(path))==result['receipt']['sha256'],'B4_ROLE_RECEIPT')
    row=json.loads(h.read(path).decode())
    need(row['schema']==1 and row['stage']=='CP10' and row['scope']=='ISOLATED_TEST_ONLY'
         and row['status']=='CP10_FINITE_COMMITTED' and row['role']==role and row['request_sha256']==request_sha
         and row['b3_receipt_sha256']==B3_RECEIPT and row['service_started'] is False and row['database_opened'] is False,'B4_ROLE_IDENTITY')
    for name,pin in row['files'].items():
        need(Path(name).name==name and h.digest(h.read(folder/name))==pin,'B4_ROLE_EVIDENCE_SHA')
    journal=json.loads(h.read(folder/('batch-CP10-'+role+'.json')).decode())
    need(journal['phase']=='STOPPED' and journal['commit_receipt']==row['start_receipt'],'B4_STOPPED_JOURNAL')
    return result['receipt']


def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--bundle-sha256',required=True);args=p.parse_args()
    need(os.getuid()==os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST,'B4_UK_ROOT_REQUIRED')
    need(os.path.realpath(str(BASE))==str(BASE),'B4_BASE_PATH')
    s=os.lstat(str(BASE));need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,'B4_BASE_PROTECTION')
    os.umask(0o077)
    raw=Path(args.bundle).read_bytes();need(len(raw)<=2097152,'B4_BUNDLE_BOUND')
    h=transport(raw,args.bundle_sha256)
    lock=os.open(str(BASE/'state/.formal-cli.lock'),os.O_RDWR|os.O_NOFOLLOW)
    try:
        s=os.fstat(lock);need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'B4_FORMAL_LOCK')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        h.directory(WORK);h.directory(WORK/'logs');stage=WORK/'sources'
        if not stage.exists() or stat.S_IMODE(os.lstat(str(stage)).st_mode)==0o700:h.unpack(raw,args.bundle_sha256,stage)
        else:
            for path,spec in json.loads(raw.decode())['files'].items():need(h.digest(h.read(stage/path))==spec['sha256'],'B4_STAGED_SOURCE_SHA')
        need(h.read(stage/'scripts/p2_b4_owner_sandbox_20261020.py')==h.read(Path(__file__).absolute()),'B4_PRODUCER_IDENTITY')
        need(h.digest(h.read(PRIOR/'prepared/preparation-receipt.json'))==B3_RECEIPT,'B4_REAL_B3_RECEIPT')
        proof=BASE/'b3-ledger-final-20261020/proof.json';s=os.lstat(str(proof))
        need(s.st_uid==0 and stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode)==0o444
             and h.digest(h.read(proof))==B3_PROOF,'B4_REAL_B3_PROOF')
        before=prior_snapshot(h);h.publish(WORK/'b3-source-snapshot.json',h.canonical(before))
        code,out,err=h.command(['/bin/docker','image','inspect',IMAGE,'--format','{{.Id}}'],WORK/'logs','image')
        need(code==0 and out.decode().strip()==IMAGE,'B4_FIXED_IMAGE_UNAVAILABLE')
        private_uid_directory(ROOT)
        for name in ('workspace','developer','platform-engineer'):private_uid_directory(ROOT/name)
        request=stage/'docs/p2-b4-20261020/request.json';request_raw=h.read(request);req=json.loads(request_raw.decode());request_sha=h.digest(h.canonical(req))
        need(req['root']==str(ROOT) and req['b3_root']==str(PRIOR) and req['b3_receipt_sha256']==B3_RECEIPT,'B4_FIXED_REQUEST')
        producer=h.digest(h.read(Path(__file__).absolute()));receipts={};containers={}
        for role in ('developer','platform-engineer'):
            mounts=[(str(stage),'/tools',True),(str(stage/RUNTIME),'/application/stage1',True),
                    (str(PRIOR),str(PRIOR),True),(str(ROOT),str(ROOT),True),
                    (str(ROOT/role),str(ROOT/role),False),
                    (str(ROOT/'workspace'),str(ROOT/'workspace'),role=='platform-engineer')]
            argv=[req['binary']['path'],'-B','-S','/tools/scripts/p2_b4_container_roundtrip.py',
                  '--request','/tools/docs/p2-b4-20261020/request.json','--role',role]
            result,container,planned=h.run_container('p2-b4-finite-'+role,role,argv,mounts,'1002:1002',IMAGE,b'',WORK/'logs',producer,request_sha)
            need(container['State']['ExitCode']==0,'B4_FINITE_CONTAINER_EXIT')
            receipts[role]=verify_role(h,role,result,request_sha);containers[role]=container['Id']
            need(prior_snapshot(h)==before,'B4_B3_CHANGED')
        need(not os.path.lexists(str(PRIOR/'data/ledger.sqlite3')) and not os.path.lexists(str(PRIOR/'run/ledger.sock')),'B4_UNEXPECTED_B6_EFFECT')
        summary={'schema':1,'scope':'ISOLATED_TEST_ONLY','status':'CP10_FINITE_COMMITTED',
                 'request_sha256':request_sha,'producer_sha256':producer,'b3_receipt_sha256':B3_RECEIPT,
                 'receipts':receipts,'containers':containers,'b3_unchanged':True,'service_started':False,
                 'production_permission':False,'full_original_host_sandbox':'NOT_CLAIMED'}
        h.publish(WORK/'summary.json',h.canonical(summary));print(json.dumps(summary,sort_keys=True));return 0
    finally:os.close(lock)


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        traceback.print_exc();print(json.dumps({'status':'HOLD_RETAINED','reason':str(exc),'service_started':False},sort_keys=True));sys.exit(2)
