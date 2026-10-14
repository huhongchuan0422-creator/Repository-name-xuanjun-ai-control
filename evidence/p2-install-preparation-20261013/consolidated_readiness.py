"""Fixed UK P2 preparation audit. Canonical DB and all services read-only.

Only writes new private preparation evidence and a disposable DB fixture.
Never installs, fences canonical tasks, sends messages or changes units.
"""
import ast
import datetime
import grp
import hashlib
import importlib.util
import json
import os
import pwd
import shlex
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile

BASE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
TX='c529c379-9341-4510-8384-fc6be1e412e5'
OLD=BASE+'/legacy-isolation-'+TX
DB='/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
DB_SHA='a6b3847009ca7ee394772b7cf0144b90f82d1c68a3e9b4d3e9c4656f50c28d60'
PLAN=BASE+'/adopted-core-plan-38439161110/protected-core-install-plan.json'
PLAN_SHA='4d16f2f68016afa5c869373e59e01ffeae581eb54db3c69cdc6b686cfc4f05e8'
NOTIFIER_SHA='a43d2188c7f2528e6a061898ccf435958fe99d9d26cf3a4c8cddcd1670522a55'
UNITS=['xuanjun-uk-stage1-minimal.service','xuanjun-uk-openclaw.service',
       'xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service',
       'xj-uk-owner-notify.timer','xj-uk-owner-notify.service']


def require(value, code):
    if not value:raise ValueError(code)


def raw(path, maximum=1048576, private=False):
    require(os.path.realpath(path)==path, 'PATH_ALIAS')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        i=os.fstat(f.fileno())
        require(stat.S_ISREG(i.st_mode) and i.st_nlink==1 and i.st_size<=maximum,'FILE_IDENTITY_BOUND')
        if private:require(i.st_uid==0 and i.st_gid==0 and stat.S_IMODE(i.st_mode)==0o600,'ROOT_PRIVATE_REQUIRED')
        b=f.read(maximum+1)
    require(len(b)<=maximum,'FILE_BOUND')
    return b


def digest(path, maximum=536870912):
    require(os.path.realpath(path)==path,'HASH_PATH_ALIAS')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        i=os.fstat(f.fileno());require(stat.S_ISREG(i.st_mode) and i.st_size<=maximum,'HASH_FILE_BOUND')
        h=hashlib.sha256();size=0
        for b in iter(lambda:f.read(65536),b''):
            size+=len(b);require(size<=maximum,'HASH_READ_BOUND');h.update(b)
    return h.hexdigest()


def command(args, maximum=2097152):
    r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
    require(r.returncode==0 and len(r.stdout)<=maximum,'READ_COMMAND_FAILED')
    return r.stdout


def execute():
    require(os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ','FIXED_UK_ROOT')
    run=sys.argv[1];require(run.isdigit(),'NUMERIC_RUN_REQUIRED')
    result={'schema':1,'transaction_id':TX,'observed_utc':datetime.datetime.utcnow().isoformat()+'Z',
            'sections':{},'errors':{},'production_effects':0,'release':'HOLD','install':False,
            'canonical_db_mutation':False,'other_writers_outside_control_realm':'UNKNOWN'}
    def section(name, fn):
        try:result['sections'][name]=fn()
        except Exception as error:result['errors'][name]={'type':type(error).__name__,'code':str(error) if isinstance(error,ValueError) else 'READ_OR_FIXTURE_FAILED'}
    p=raw(PLAN,private=True);require(hashlib.sha256(p).hexdigest()==PLAN_SHA,'CORE_PLAN_DRIFT')
    plan=json.loads(p.decode());root=plan['artifact']['root']
    require(digest(DB)==DB_SHA,'CANONICAL_DB_DRIFT')
    for suffix in ['-wal','-journal']:
        require(not os.path.lexists(DB+suffix) or os.lstat(DB+suffix).st_size==0,'NONEMPTY_DB_JOURNAL')
    sys.path.insert(0,root+'/stage1')

    def artifact():
        manifest=raw(plan['artifact']['manifest'])
        require(hashlib.sha256(manifest).hexdigest()==plan['artifact']['manifest_sha256'],'MANIFEST_DRIFT')
        files=json.loads(manifest.decode())['files'];require(len(files)==95,'EXACT95_REQUIRED')
        for rel,h in files.items():
            require(rel and not rel.startswith('/') and '..' not in rel.split('/'),'MANIFEST_PATH')
            require(digest(root+'/'+rel)==h,'RUNTIME_FILE_DRIFT')
        from p2_install_entrypoint import validate_plan
        validate_plan(plan)
        return {'files_verified':95,'plan_sha256':PLAN_SHA,'source':plan['artifact']['source_commit'],
                'manifest_sha256':plan['artifact']['manifest_sha256'],'schema_valid':True}
    section('artifact_and_plan',artifact)

    def isolation():
        script=os.path.join(os.path.dirname(os.path.abspath(__file__)),'notifier_isolation_candidate.py')
        b=raw(script);require(hashlib.sha256(b).hexdigest()=='af0555ef8382213889c4d2b3390a202ab0d5218842d8b563456cad20720a8d56','EXACT_ISOLATION_AUDITOR_REQUIRED')
        ns={'__name__':'isolation_readonly','__file__':script};exec(compile(b,script,'exec'),ns)
        adapter=ns['FixedHost']();adapter.evidence()
        receipt=raw(OLD+'/notifier/notifier-isolation-receipt.json',private=True)
        require(hashlib.sha256(receipt).hexdigest()==NOTIFIER_SHA,'NOTIFIER_RECEIPT_DRIFT')
        value=json.loads(receipt.decode());require(value['state']=='AUTHORIZED_NOTIFIER_ISOLATED' and value['transaction_id']==TX,'NOTIFIER_RECEIPT_STATE')
        states={}
        for unit in UNITS:
            x=adapter.quiet(unit)
            path='/etc/systemd/system/'+unit
            require(os.path.islink(path) and os.readlink(path)=='/dev/null' and x['UnitFileState']=='masked','SIX_UNIT_MASK_DRIFT')
            states[unit]=x
        for unit,h in ns['UNIT_HASHES'].items():
            require(digest(OLD+'/notifier/'+unit+'.backup')==h,'NOTIFIER_BACKUP_DRIFT')
        return {'six_units':states,'notifier_receipt_sha256':NOTIFIER_SHA,'original_evidence_unchanged':True}
    section('six_unit_isolation',isolation)

    def authority_fixture():
        require('artifact_and_plan' in result['sections'],'VERIFIED_RUNTIME_REQUIRED_FOR_FIXTURE')
        # Only the fixture is writable; original is query_only immutable with no WAL.
        with tempfile.TemporaryDirectory(prefix='p2-authority-fixture-') as tmp:
            # Python3.6 has no Connection.backup. Read the exact hash-bound main
            # file only with absent WAL/journal; no canonical SQLite connection writes.
            snapshot=raw(DB);require(hashlib.sha256(snapshot).hexdigest()==DB_SHA,'FIXTURE_SOURCE_DRIFT')
            with open(tmp+'/state.sqlite','wb') as stream:stream.write(snapshot)
            db=sqlite3.connect(tmp+'/state.sqlite');db.row_factory=sqlite3.Row
            tasks=list(db.execute('SELECT * FROM tasks'));callbacks=list(db.execute('SELECT * FROM owner_callback_requests'))
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts={r[0]:r[1] for r in db.execute('SELECT state,count(*) FROM tasks GROUP BY state')}
            require(all(r['lease_owner'] is None and r['lease_until'] is None and r['state']!='RUNNING' for r in tasks),'OLD_EXECUTION_LEASE_NOT_EMPTY')
            native=[]
            for row in tasks:
                checkpoint=json.loads(row['checkpoint'] or '{}')
                if isinstance(checkpoint,dict) and checkpoint.get('native_execution'):native.append(row['id'])
            db.close()
            from execution_ledger import ExecutionLedger
            ledger=ExecutionLedger(tmp+'/state.sqlite',['huhongchuan0422-creator/Repository-name-xuanjun-ai-control'])
            # No paid model or external tools: only the existing admission method on scratch.
            claim=ledger.claim('readiness-isolated-fixture')
            require(claim is None,'IMPORTED_OLD_TASK_CLAIMABLE')
            expired=0;denied=0
            for row in callbacks:
                if row['consumed']!=0:continue
                require(row['expires_at']<=datetime.datetime.utcnow().timestamp(),'OLD_OWNER_REQUEST_STILL_VALID')
                expired+=1
                try:ledger.owner_decision(row['task_id'],row['fence'],'APPROVE',row['request_id'],2147483647,row['owner_id'],row['owner_chat'],'readiness-fixture',True)
                except PermissionError:denied+=1
                else:raise ValueError('EXPIRED_CALLBACK_ACCEPTED')
            require(expired==denied,'EXPIRED_CALLBACK_PROOF_FAILED')
            require(not native,'LEGACY_NATIVE_EXECUTION_RECONCILIATION_REQUIRED')
            return {'old_task_count':len(tasks),'state_counts':counts,'old_lease_count':0,'native_execution_records':0,
                    'original_execution_specs_table_present':'execution_specs' in tables,'fixture_claim_result':'NONE',
                    'unconsumed_expired_requests':expired,'expired_request_denials':denied,
                    'canonical_fence_changed':False,'historical_external_delivery':'UNKNOWN_NO_REPLAY',
                    'fixture_only':True}
    section('legacy_authority_and_expiry_fixture',authority_fixture)

    def references():
        checked=[]
        for kind in ('auth','tls'):
            for ref in plan[kind]['references']:
                require(digest(ref['path'])==ref['sha256'],'PROTECTED_REFERENCE_DRIFT')
                i=os.lstat(ref['path']);require(i.st_uid==ref['owner_uid'] and stat.S_IMODE(i.st_mode)==ref['mode'],'PROTECTED_REFERENCE_PERMISSION')
                checked.append({'kind':kind,'path':ref['path'],'sha256':ref['sha256']})
        for key in ('bootstrap','publisher','sandbox_policy','rpm','auxiliary_isolation'):
            ref=plan['runtime'][key];b=raw(ref['path'],private=True)
            require(hashlib.sha256(b).hexdigest()==ref['sha256'],'PREPARATION_RECEIPT_DRIFT')
            checked.append({'kind':key,'path':ref['path'],'sha256':ref['sha256']})
        for binary in plan['runtime']['prerequisites']['binaries']:
            require(digest(binary['source'])==binary['sha256'],'PINNED_BINARY_DRIFT')
        return {'references':checked,'pinned_binaries_verified':2,'secret_values_exported':False}
    section('protected_references_and_binaries',references)

    def tls():
        cert=plan['tls']['references'][0]['path'];key=plan['tls']['references'][1]['path']
        command(['/usr/bin/openssl','x509','-in',cert,'-noout','-checkend','86400'])
        cpub=command(['/usr/bin/openssl','x509','-in',cert,'-pubkey','-noout'])
        kpub=command(['/usr/bin/openssl','pkey','-in',key,'-pubout'])
        require(cpub==kpub,'TLS_KEY_PAIR_MISMATCH')
        require(b'uk.wenwenwenyiyiyi.work' in command(['/usr/bin/openssl','x509','-in',cert,'-noout','-text']),'TLS_DOMAIN_MISMATCH')
        ips=sorted({r[4][0] for r in socket.getaddrinfo('uk.wenwenwenyiyiyi.work',443,socket.AF_INET)})
        require('8.208.119.115' in ips,'TLS_DNS_MISMATCH')
        return {'checkend_86400':True,'key_pair_match':True,'domain_match':True,'dns_ipv4':ips,
                'https_runtime':'NOT_INSTALLED','renewal_runtime':'NOT_ACCEPTED'}
    section('fresh_tls_and_dns',tls)

    def nss():
        result={}
        for name,v in plan['runtime']['prerequisites']['users'].items():
            try:row=pwd.getpwnam(name)
            except KeyError:row=None
            try:byid=pwd.getpwuid(v['uid'])
            except KeyError:byid=None
            require(row is None and byid is None,'PLANNED_UID_ALREADY_OCCUPIED')
            result[name]={'uid':v['uid'],'available':True,'created':False}
        for name,gid in plan['runtime']['prerequisites']['groups'].items():
            try:row=grp.getgrnam(name)
            except KeyError:row=None
            try:byid=grp.getgrgid(gid)
            except KeyError:byid=None
            require(row is None and byid is None,'PLANNED_GID_ALREADY_OCCUPIED')
        return {'planned_users':result,'groups_available':6,'production_permissions':'NOT_INSTALLED'}
    section('nss_identity_availability',nss)

    def control_entries():
        inventory=command(['/usr/bin/systemctl','list-unit-files','--no-legend','--no-pager']).decode().splitlines()
        names=[r.split()[0] for r in inventory if r.split() and (r.split()[0].startswith(('xj-','xuanjun-')))]
        units={}
        for unit in names:
            output=command(['/usr/bin/systemctl','show',unit,'--property=Id,FragmentPath,ActiveState,SubState,MainPID,UnitFileState']).decode()
            row=dict(x.split('=',1) for x in output.splitlines() if '=' in x)
            path=row.get('FragmentPath','')
            if path.startswith('/etc/systemd/system/') and os.path.realpath(path)==path and os.path.isfile(path):
                b=raw(path,262144);row['unit_sha256']=hashlib.sha256(b).hexdigest()
                row['script_metadata']=[]
                for line in b.decode().splitlines():
                    if not line.startswith('ExecStart='):continue
                    for token in shlex.split(line.split('=',1)[1]):
                        if token.startswith(('/home/xuanjun_dev/','/opt/xuanjun-')) and token.endswith(('.py','.sh')) and os.path.isfile(token):
                            data=raw(token);text=data.decode()
                            row['script_metadata'].append({'path':token,'sha256':hashlib.sha256(data).hexdigest(),
                                'canonical_db_literal':DB in text,'sqlite_reference':'sqlite' in text.lower(),
                                'sql_mutation_tokens':any(s in text.upper() for s in ('INSERT INTO','UPDATE ','DELETE FROM','CREATE TABLE'))})
            units[unit]=row
        processes=[]
        for pid in os.listdir('/proc'):
            if not pid.isdigit():continue
            try:
                status=raw('/proc/'+pid+'/status',65536)
            except (ValueError,FileNotFoundError):
                # proc pseudo-files are not normal files; inspect directly bounded.
                try:
                    with open('/proc/'+pid+'/status','rb') as f:status=f.read(65537)
                except FileNotFoundError:continue
            if any(line.startswith(b'Uid:') and line.split()[1]==b'1002' for line in status.splitlines()):
                try:exe=os.readlink('/proc/'+pid+'/exe')
                except FileNotFoundError:continue
                processes.append({'pid':int(pid),'exe':exe})
        return {'registered_control_units':units,'uid1002_processes':processes,
                'cron_and_user_schedulers':'NOT_YET_FULLY_CLASSIFIED','global_exclusion':'NOT_CLAIMED'}
    section('remaining_control_entry_inventory',control_entries)

    def fd_scope():
        info=os.stat(DB);holders=[];count=0;races=0;denied=0
        for pid in os.listdir('/proc'):
            if not pid.isdigit() or int(pid)==os.getpid():continue
            try:fd=os.open('/proc/'+pid+'/fd',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            except FileNotFoundError:races+=1;continue
            except PermissionError:denied+=1;continue
            try:
                for n in os.listdir(fd):
                    count+=1;require(count<=1000000,'FD_BOUND')
                    try:target=os.readlink(n,dir_fd=fd);i=os.stat(n,dir_fd=fd)
                    except FileNotFoundError:races+=1;continue
                    except PermissionError:denied+=1;continue
                    if target.replace(' (deleted)','') in (DB,DB+'-wal',DB+'-shm') or (i.st_dev,i.st_ino)==(info.st_dev,info.st_ino):holders.append(int(pid))
            finally:os.close(fd)
        return {'fd_checked':count,'holders':holders,'races':races,'denied':denied,
                'complete_no_holders':not holders and not races and not denied}
    section('fresh_canonical_db_fd_scope',fd_scope)
    require(digest(DB)==DB_SHA,'DATABASE_CHANGED_DURING_READINESS_AUDIT')
    result['canonical_database_unchanged']=True
    result['measurement_errors']=len(result['errors'])
    # Snapshot is new preparation evidence only, never a release grant.
    directory=BASE+'/consolidated-readiness-'+run
    os.mkdir(directory,0o700)
    data=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
    fd=os.open(directory+'/protected-readiness-snapshot.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    print('CONSOLIDATED_READINESS_RESULT='+json.dumps(result,sort_keys=True))
    print('CONSOLIDATED_READINESS_RECEIPT_PATH='+directory+'/protected-readiness-snapshot.json')
    print('CONSOLIDATED_READINESS_RECEIPT_SHA256='+hashlib.sha256(data).hexdigest())
    return 0


if __name__=='__main__':sys.exit(execute())
