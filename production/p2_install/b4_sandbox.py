"""CP10 finite adapter: real ledger preparation consumer + original sandbox policy.

Never builds ledger service. Existing B3 bytes and normal startup guards are
unchanged. UID1002 is a finite verifier role, never the unknown service UID.
"""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import time
import uuid

from .initialize import need,read,encode,sha,publish,directory

B3='/var/lib/xuanjun-p2-isolated-test/b3-initialize'
B4='/var/lib/xuanjun-p2-isolated-test/b4-sandbox'
B3_RECEIPT='34d1530271efaabb4b65c5c44d2e76bd04258247dfc36a9a613aa829ec18dc8b'
RUNTIME_SHA='3993ab9bd0073a91d8110814e694b2c402ef5b53efb544a3bc44a1debd4231a1'
ROLES=('developer','platform-engineer')

def _checkpoint(name):pass  # deterministic offline interruption injection only


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m);return m


def checked_request(req):
    need(set(req)=={'schema','scope','b3_root','root','application','b3_receipt_sha256','binary',
                    'installation_id','attempt_id','sources','runtime_sha256'},'CP10_REQUEST_FIELDS')
    need(req['schema']==1 and req['scope']=='ISOLATED_TEST_ONLY','CP10_SCOPE')
    root=Path(req['root']);prior=Path(req['b3_root'])
    fixed=(str(root)==B4 and str(prior)==B3)
    fixture=str(root).startswith('/tmp/p2-b3-test-b4-') and root.name=='b4-sandbox' and prior==root.parent/'b3-initialize'
    need(fixed or fixture,'CP10_ROOT_SCOPE')
    need(os.getuid()==os.geteuid() and os.getgid()==os.getegid(),'CP10_SUBJECT')
    if fixed:
        need(os.geteuid()==os.getegid()==1002 and req['b3_receipt_sha256']==B3_RECEIPT
             and req['application']=='/application/stage1','CP10_FIXED_BINDING')
    for path in (root,prior,Path(req['application'])):
        need(path.is_absolute() and str(path.resolve())==str(path),'CP10_CANONICAL_PATH')
    info=os.lstat(str(root))
    need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o700,'CP10_PRIVATE_ROOT')
    need(req['binary']['path']==os.path.realpath(sys.executable),'CP10_BINARY_PATH')
    raw=read(Path(req['binary']['path']),32*1024*1024)
    need(len(raw)==req['binary']['bytes'] and sha(raw)==req['binary']['sha256'],'CP10_BINARY_SHA')
    app=Path(req['application'])
    need(set(req['sources'])=={'ledger_service.py','ledger_prepared.py','activation_control.py','p2_sandbox_profile.py'},'CP10_SOURCE_FIELDS')
    for name,pin in req['sources'].items():need(sha(read(app/name))==pin,'CP10_SOURCE_SHA')
    import production.p2_runtime as runtime
    need(sha(read(Path(runtime.__file__)))==req['runtime_sha256']==RUNTIME_SHA,'CP10_RUNTIME_SHA')
    return root,prior,app


def handoff(req):
    root,prior,app=checked_request(req);folder=prior/'prepared'
    raw=read(folder/'preparation-receipt.json')
    need(sha(raw)==req['b3_receipt_sha256'],'CP10_B3_RECEIPT_SHA')
    final=json.loads(raw)
    need(final['status']=='PREPARATION_COMMITTED' and final['scope']=='ISOLATED_TEST_ONLY'
         and final['full_b3_complete'] is False and final['service_started'] is False,'CP10_B3_BOUNDARY')
    profile_raw=read(folder/'profile.json');profile=json.loads(profile_raw)
    need(profile['sources']=={k:req['sources'][k] for k in ('ledger_service.py','ledger_prepared.py','activation_control.py')}
         and profile['binary']==req['binary'] and profile['preparation_uid']==os.geteuid(),'CP10_B3_IDENTITY')
    previous=profile['cp03_receipt_sha256']
    need(sha(read(prior/'commit-receipt.json'))==previous,'CP10_CP03')
    for stage in ('CP04','CP05','CP06','CP07','CP08','CP09'):
        checkpoint=read(folder/(stage+'-committed.json'));row=json.loads(checkpoint)
        need(row['schema']==1 and row['scope']=='ISOLATED_TEST_ONLY' and row['stage']==stage
             and row['status']=='PREPARATION_CHECKPOINT_COMMITTED'
             and row['request_sha256']==final['request_sha256'] and row['previous_receipt_sha256']==previous,
             'CP10_B3_CHECKPOINT_CHAIN')
        if stage=='CP08':need(row['evidence']['denial']['status']=='PASS','CP10_B3_ACCESS_EVIDENCE')
        previous=sha(checkpoint)
    need(previous==final['last_checkpoint_sha256'],'CP10_B3_FINAL_CHAIN')
    command=[req['binary']['path'],'-B','-S',str(app/'ledger_service.py'),'--config',str(folder/'ledger-config.json'),
             '--check-isolated-prepared','--profile',str(folder/'profile.json'),'--profile-sha256',sha(profile_raw)]
    result=subprocess.run(command,cwd=str(app),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,timeout=5)
    need(result.returncode==0 and len(result.stdout)<=65536,'CP10_REAL_LEDGER_CONSUMER')
    consumed=json.loads(result.stdout)
    need(consumed['status']=='PREPARED_CONFIG_VALIDATED' and consumed['config_sha256']==profile['config_sha256']
         and all(consumed[k] is False for k in ('service_started','database_opened','socket_bound')),'CP10_REAL_CONSUMPTION')
    # Load the exact original policy consumer; do not modify the real profile.
    sys.path.insert(0,str(app))
    policy=load_module('cp10_original_sandbox_policy',app/'p2_sandbox_profile.py')
    old={'agents':{'entries':{'developer':{},'platform-engineer':{}}}}
    candidate=copy.deepcopy(old)
    for name,access in (('developer','rw'),('platform-engineer','ro')):
        candidate['agents']['entries'][name]['sandbox']={'mode':'all','workspaceAccess':access,'scope':'agent',
          'docker':{'image':policy.IMAGE,'user':'1002:1002','network':'none','readOnlyRoot':True,
                    'capDrop':['ALL'],'binds':[],'tmpfs':[]}}
    need(policy.policy(old,candidate)==candidate,'CP10_ORIGINAL_SANDBOX_POLICY')
    return {'b3_receipt_sha256':sha(raw),'config_sha256':consumed['config_sha256'],
            'profile_sha256':sha(profile_raw),'sandbox_policy_sha256':sha(encode(candidate)),
            'policy':candidate,'real_consumer':consumed,'consumer_argv':command}


def expected_response(req,role,value):
    return {'schema':1,'scope':'ISOLATED_TEST_ONLY','status':'CP10_FINITE_READY','role':role,
            'request_sha256':sha(encode(req)),'b3_receipt_sha256':req['b3_receipt_sha256'],
            'config_sha256':value['config_sha256'],'sandbox_policy_sha256':value['sandbox_policy_sha256'],
            'service_started':False,'database_opened':False}


def consume_finite(req,role):
    need(role in ROLES,'CP10_ROLE');value=handoff(req);root=Path(req['root'])/role
    workspace=Path(req['root'])/'workspace';probe=workspace/'developer-probe.json'
    wanted=encode({'scope':'ISOLATED_TEST_ONLY','request_sha256':sha(encode(req))})
    status=Path('/proc/self/status').read_text()
    need('CapEff:\t0000000000000000' in status and 'NoNewPrivs:\t1' in status,'CP10_PROCESS_ISOLATION')
    readonly=bool(os.statvfs(workspace).f_flag & os.ST_RDONLY)
    if role=='developer':
        need(not readonly,'CP10_DEVELOPER_RW')
        if os.path.lexists(probe):need(read(probe)==wanted,'CP10_WORKSPACE_CONFLICT')
        else:
            fd=os.open(str(probe),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(wanted);stream.flush();os.fsync(stream.fileno())
        need(read(probe)==wanted,'CP10_WORKSPACE_READBACK');denied=None
    else:
        need(readonly and read(probe)==wanted,'CP10_ENGINEER_RO')
        try:fd=os.open(str(probe),os.O_WRONLY|os.O_NOFOLLOW)
        except OSError as exc:denied=exc.errno
        else:os.close(fd);raise ValueError('CP10_ENGINEER_WRITE_ALLOWED')
        need(denied==30,'CP10_EXPECT_EROFS')
    response=expected_response(req,role,value)
    observation={'pid':os.getpid(),'uid':os.getuid(),'gid':os.getgid(),'role':role,
                 'response':response,'workspace_readonly':readonly,'write_errno':denied,
                 'deadline_seconds':8,'consumer':value}
    publish(root/'consumer-observation.json',encode(observation))
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    endpoint=root/'ready.sock';need(not os.path.lexists(endpoint),'CP10_SOCKET_ALREADY_PRESENT')
    sock.bind(str(endpoint));sock.listen(2);sock.settimeout(.1)
    deadline=time.monotonic()+8;stopping=[False]
    signal.signal(signal.SIGTERM,lambda *_:stopping.__setitem__(0,True))
    signal.signal(signal.SIGINT,lambda *_:stopping.__setitem__(0,True))
    try:
        while not stopping[0] and time.monotonic()<deadline:
            try:connection,_=sock.accept()
            except socket.timeout:continue
            with connection:
                connection.settimeout(.1)
                try:
                    if connection.recv(64)==b'CP10_READY\n':connection.sendall(encode(response)+b'\n')
                except (socket.timeout,BrokenPipeError,ConnectionResetError):pass
    finally:sock.close()  # Retain endpoint metadata; do not erase crash evidence.
    publish(root/'consumer-exit.json',encode({'pid':os.getpid(),'reason':'SIGNAL' if stopping[0] else 'DEADLINE',
               'service_started':False,'request_sha256':sha(encode(req))}))
    return 0


def runtime_request(req,role,value):
    root=Path(req['root'])/role
    return {'schema':1,'scope':'ISOLATED_TEST_ONLY','installation_id':req['installation_id'],
      'batch_id':'CP10-'+role,'attempt_id':req['attempt_id'],'root':str(root),
      'inputs':{'operation':'start','argv':[req['binary']['path'],'-B','-S','-m',
        'production.p2_install.b4_sandbox','_consumer','--request',str(root/'request.json'),'--role',role],
        'cwd':str(Path(__file__).resolve().parents[2]),'env':{'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},
        'timeout':1.0,'health':{'type':'unix_socket','path':str(root/'ready.sock'),'request':'CP10_READY\n',
           'expect':(encode(expected_response(req,role,value))+b'\n').decode(),
           'connect_timeout':.1,'read_timeout':.1,'total_timeout':2.0,'max_response':4096}}}


def runtime_cli(request,action,folder):
    path=folder/('runtime-'+action+'-'+sha(encode(request))+'.json');publish(path,encode(request))
    # The unchanged component is a file CLI, not a newly invented entrypoint.
    import production.p2_runtime as runtime
    command=[sys.executable,'-B','-S',str(Path(runtime.__file__)),action,'--request',str(path)]
    result=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    token=uuid.uuid4().hex
    publish(folder/('cli-'+action+'-'+token+'.stdout'),result.stdout)
    publish(folder/('cli-'+action+'-'+token+'.stderr'),result.stderr)
    need(len(result.stdout)<=65536 and result.stdout.strip(),'CP10_RUNTIME_OUTPUT')
    return json.loads(result.stdout)


def dispatch(req,role,action):
    need(role in ROLES and action in ('execute','inspect','recover'),'CP10_ACTION')
    root,prior,app=checked_request(req);folder=root/role
    need(folder.is_dir() and folder.stat().st_uid==os.geteuid() and stat.S_IMODE(folder.stat().st_mode)==0o700,'CP10_ROLE_DIRECTORY')
    lock=os.open(str(folder/'.cp10.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);value=handoff(req)
        intent=encode({'request_sha256':sha(encode(req)),'request':req,'role':role})
        final=folder/'CP10-committed.json'
        if os.path.lexists(final):
            need(read(folder/'intent.json')==intent,'CP10_INTENT_CONFLICT')
            row=json.loads(read(final));need(row['request_sha256']==sha(encode(req)) and row['role']==role,'CP10_FINAL_IDENTITY')
            for name,pin in row['files'].items():need(sha(read(folder/name))==pin,'CP10_FINAL_EVIDENCE_CHANGED')
            observation=json.loads(read(folder/'consumer-observation.json'))
            import production.p2_runtime as runtime
            journal=json.loads(read(folder/('batch-CP10-'+role+'.json')))
            need(journal['phase']=='STOPPED' and runtime.process_set(journal)[0]=='GONE','CP10_FINAL_PROCESS_NOT_GONE')
            need(observation['response']==expected_response(req,role,value),'CP10_FINAL_READINESS_BINDING')
            return {'status':'CP10_FINITE_COMMITTED','receipt':{'path':str(final),'sha256':sha(read(final))},'role':role,'service_started':False}
        if action=='inspect' and not os.path.lexists(folder/'intent.json'):
            return {'status':'NOT_EXECUTED','role':role,'service_started':False}
        if action=='execute' and not os.path.lexists(folder/'intent.json'):publish(folder/'intent.json',intent)
        need(read(folder/'intent.json')==intent,'CP10_INTENT_CONFLICT')
        publish(folder/'request.json',encode(req));publish(folder/'sandbox-policy.json',encode(value['policy']))
        rt=runtime_request(req,role,value)
        import production.p2_runtime as runtime
        journal=folder/('batch-CP10-'+role+'.json')
        if journal.exists():
            started=runtime_cli(rt,'recover',folder)
            need(started['status']=='COMMITTED' and started['commit_receipt'] is not None,'CP10_INTERRUPTED_START_HOLD')
        else:
            need(action=='execute','CP10_NO_START_REPLAY')
            started=runtime_cli(rt,'execute',folder)
        _checkpoint('after_start')
        try:
            need(started['status']=='COMMITTED' and started['commit_receipt'] is not None,'CP10_START_NOT_READY')
            observation=json.loads(read(folder/'consumer-observation.json'));entry=json.loads(read(journal))
            need(observation['pid']==entry['pid'] and observation['uid']==observation['gid']==os.geteuid()
                 and runtime.process_match({'pid':entry['pid'],'start':entry['start'],'session':entry['session']})=='LIVE',
                 'CP10_PROCESS_IDENTITY')
            need(observation['response']==expected_response(req,role,value),'CP10_READINESS_BINDING')
            inspected=runtime_cli(rt,'inspect',folder)
            need(inspected['status']=='COMMITTED' and inspected['commit_receipt']==started['commit_receipt'],'CP10_INSPECT_READY')
        finally:
            stop=copy.deepcopy(rt);stop['inputs']={'operation':'stop','timeout':2}
            stopped=runtime_cli(stop,'execute',folder)
        _checkpoint('after_stop')
        need(stopped['status']=='COMMITTED','CP10_STOP_NOT_CONFIRMED')
        recovered=runtime_cli(stop,'recover',folder)
        need(recovered['status']=='NO_EFFECT' and recovered['commit_receipt']==started['commit_receipt'],'CP10_EXIT_RECOVERY')
        entry=json.loads(read(journal));need(runtime.process_set(entry)[0]=='GONE','CP10_PROCESS_NOT_GONE')
        names=['consumer-observation.json','consumer-exit.json','sandbox-policy.json']
        files={name:sha(read(folder/name)) for name in names}
        for reference in (started['commit_receipt'],inspected['receipt'],stopped['receipt'],recovered['receipt']):
            path=Path(reference['path']);need(path.parent==folder and sha(read(path))==reference['sha256'],'CP10_RUNTIME_RECEIPT')
            files[path.name]=reference['sha256']
        row={'schema':1,'scope':'ISOLATED_TEST_ONLY','stage':'CP10','status':'CP10_FINITE_COMMITTED',
             'request_sha256':sha(encode(req)),'b3_receipt_sha256':req['b3_receipt_sha256'],'role':role,
             'files':files,'start_receipt':started['commit_receipt'],'process':{k:entry[k] for k in ('pid','start','pgid','session')},
             'service_started':False,'database_opened':False,'full_original_host_sandbox':'NOT_CLAIMED'}
        publish(final,encode(row))
        return {'status':'CP10_FINITE_COMMITTED','receipt':{'path':str(final),'sha256':sha(read(final))},'role':role,'service_started':False}
    finally:os.close(lock)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('execute','inspect','recover','_consumer'))
    parser.add_argument('--request',required=True);parser.add_argument('--role',choices=ROLES,required=True);args=parser.parse_args()
    req=json.loads(read(Path(args.request)))
    if args.action=='_consumer':return consume_finite(req,args.role)
    try:result=dispatch(req,args.role,args.action)
    except Exception as exc:
        result={'status':'HOLD_RETAINED','error_type':type(exc).__name__,'reason':str(exc), 'service_started':False}
    print(json.dumps(result,sort_keys=True));return 0 if result['status']=='CP10_FINITE_COMMITTED' else 2


if __name__=='__main__':sys.exit(main())
