"""Ordered non-starting B3 canonical-ledger preparation, CP04--09.

Original CP03 remains read-only. No ActivationStore transition, database open,
listener, permission change or service start. UNKNOWN stops dependent stages.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from .initialize import encode, sha, read, publish, directory, need
from .b3_contracts import cp03_identity, effective_access, unauthorized_access

STAGES=('CP04','CP05','CP06','CP07','CP08','CP09')
BASE='6f2cc6b6fbe6150ac9384cd330854808c419385b'
RECEIPT='bede2ebc9f9c5458c92307c974358eb61947e7ec80a9611cc76735891ffae433'
NAMES=('ledger_service.py','ledger_prepared.py','activation_control.py')


def _checkpoint(_name): pass  # local deterministic interruption tests only


def documents(req, expected):
    root=Path(req['root']);app=Path(req['application'])
    cfg={'schema':1,'scope':'ISOLATED_TEST_ONLY','profile':'ISOLATED_NEW_PREPARE_ONLY',
         'installation_id':expected['installation_id'],
         'activation_descriptor':str(root/'activation/active.json'),
         'activation_epoch_journal':str(root/'activation/epochs.jsonl'),
         'activation_lock':str(root/'activation/activation.lock'),
         'activation_config_sha256':expected['config_sha256'],
         'callback_user':'xuanjun-callback',
         'control_repository':'huhongchuan0422-creator/Repository-name-xuanjun-ai-control',
         'source_commit':BASE,'max_workers':1}
    cfg.update({k:expected[k] for k in ('release_sha256','binary_sha256','ledger_uuid',
                'generation','instance','db_path','ledger_socket')})
    roles={'preparer_uid':os.geteuid(),'service_user':'xuanjun-dispatcher',
           'service_uid':'UNKNOWN','callback_user':'xuanjun-callback','callback_uid':1004,
           'activation_start_owner_uid':0,'socket_activation':'systemd-fd3'}
    profile={'schema':1,'scope':'ISOLATED_TEST_ONLY','profile':'ISOLATED_NEW_PREPARE_ONLY',
             'preparation_uid':os.geteuid(),'config_sha256':sha(encode(cfg)),
             'sources':req['sources'],'binary':req['binary'],'operation_id':req['operation_id'],
             'cp03_receipt_sha256':req['cp03_receipt_sha256'],'roles':roles}
    path=root/'prepared/ledger-config.json';p=root/'prepared/profile.json'
    invocation={'argv':[req['binary']['path'],'-B','-S',str(app/'ledger_service.py'),
                        '--config',str(path)],'cwd':str(app),
                'env':{'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},
                'health':{'type':'process'},'timeout':2.0,
                'execution':'NOT_AUTHORIZED_BY_PREPARATION_PROFILE',
                'health_scope':'PROCESS_EXISTENCE_ONLY_NOT_APPLICATION_READY'}
    check=invocation['argv']+['--check-isolated-prepared','--profile',str(p),
                             '--profile-sha256',sha(encode(profile))]
    identity={'schema':1,'scope':'ISOLATED_TEST_ONLY','expected':expected,
              'configuration_sha256':profile['config_sha256'],
              'profile_sha256':sha(encode(profile)),'consumer_sha256':req['sources']['ledger_service.py'],
              'operation_id':req['operation_id'],'roles':roles,
              'observed_process':{'state':'NOT_STARTED','pid':None,'peer_uid':None}}
    return cfg,profile,invocation,check,identity


def validate(req):
    need(set(req)=={'schema','scope','root','application','binary','sources',
                    'operation_id','cp03_receipt_sha256'},'REQUEST_FIELDS')
    need(req['schema']==1 and req['scope']=='ISOLATED_TEST_ONLY','REQUEST_SCOPE')
    root=Path(req['root']);app=Path(req['application'])
    production=str(root)=='/var/lib/xuanjun-p2-isolated-test/b3-initialize'
    fixture=str(root).startswith('/tmp/p2-b3-test-') and root.name=='b3-initialize'
    need(production or fixture,'ROOT_SCOPE')
    need(root.is_absolute() and str(root.resolve())==str(root) and '..' not in root.parts,'ROOT_CANONICAL')
    s=os.lstat(root)
    need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o700,'ROOT_PRIVATE')
    if production:
        need(os.geteuid()==1002 and req['cp03_receipt_sha256']==RECEIPT,'FIXED_CP03_SUBJECT')
        need(str(app)=='/application/stage1' and req['operation_id']=='p2-uk-isolated-20261020:b3-ledger-prepare-a1','FIXED_APPLICATION')
    need(app.is_absolute() and '..' not in app.parts and str(app.resolve())==str(app),'APPLICATION_CANONICAL')
    need(set(req['sources'])==set(NAMES),'SOURCE_FIELDS')
    for name in NAMES:need(sha(read(app/name))==req['sources'][name],'APPLICATION_SHA')
    need(set(req['binary'])=={'path','bytes','sha256'} and
         os.path.realpath(sys.executable)==req['binary']['path'],'BINARY_FIELDS_OR_PATH')
    raw=read(Path(req['binary']['path']),32*1024*1024)
    need(len(raw)==req['binary']['bytes'] and sha(raw)==req['binary']['sha256'],'BINARY_SHA')
    expected=cp03_identity(root,req['cp03_receipt_sha256'])
    need(expected['binary_sha256']==req['binary']['sha256'],'CP03_BINARY_BINDING')
    return root,expected


def consume(req, check):
    env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
    # Test runners using a byte-identical private interpreter may require its
    # existing prefix. This is never accepted in the production request schema.
    if str(req['root']).startswith('/tmp/p2-b3-test-'):
        env['PYTHONHOME']=sys.prefix
        env['LD_LIBRARY_PATH']=str(Path(sys.prefix)/'lib')
    result=subprocess.run(check,cwd=req['application'],env=env,stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    need(result.returncode==0,'REAL_LEDGER_PREPARED_CONSUMER_FAILED')
    need(len(result.stdout)<=65536,'CONSUMER_OUTPUT_BOUND')
    value=json.loads(result.stdout)
    need(value['status']=='PREPARED_CONFIG_VALIDATED' and
         all(value[k] is False for k in ('service_started','database_opened','socket_bound')),
         'CONSUMER_EFFECT_BOUNDARY')
    return value


def dispatch(req, action, request_sha256):
    result={'status':'HOLD','scope':'ISOLATED_TEST_ONLY','service_started':False,
            'full_b3_complete':False,'completed':[],'observations':[],'receipt':None}
    lock=None
    try:
        need(action in ('execute','inspect','recover'),'ACTION')
        need(sha(encode(req))==request_sha256,'REQUEST_SHA')
        root,expected=validate(req)
        lock=os.open(str(root/'.initialize.lock'),os.O_RDWR|os.O_NOFOLLOW)
        s=os.fstat(lock);need(stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid() and
           s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'LOCK_IDENTITY')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # All revalidation occurs while the same original initializer lock holds.
        need(cp03_identity(root,req['cp03_receipt_sha256'])==expected,'CP03_CHANGED')
        folder=root/'prepared'
        if action=='inspect' and not os.path.lexists(folder):
            result['status']='NOT_EXECUTED';return result
        if action!='inspect':directory(folder)
        else:
            s=os.lstat(folder);need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid()
                and stat.S_IMODE(s.st_mode)==0o700,'PREPARED_DIRECTORY')
        intent=encode({'request_sha256':request_sha256,'request':req})
        if action!='inspect':publish(folder/'intent.json',intent)
        need(read(folder/'intent.json')==intent,'REQUEST_CONFLICT')
        cfg,profile,invocation,check,identity=documents(req,expected)
        consumer=None;previous=req['cp03_receipt_sha256']
        for stage in STAGES:
            result['stage']=stage
            committed=folder/(stage+'-committed.json')
            # Later stage or final records with a missing predecessor are not
            # adopted as permission to skip the original sequence.
            if not os.path.lexists(committed):
                need(not any(os.path.lexists(folder/(later+'-committed.json'))
                     for later in STAGES[STAGES.index(stage)+1:]),'CHECKPOINT_ORDER')
            if stage=='CP04':
                evidence={'status':'VALIDATED','scope':'NEW_PREPARED_NO_RUNTIME_OBJECTS',
                          'cp03_receipt_sha256':req['cp03_receipt_sha256'],
                          'old_instance_stopped':'NOT_CLAIMED'}
            elif stage=='CP05':
                for name,value in [('ledger-config.json',cfg),('profile.json',profile),('runtime-invocation.json',invocation)]:
                    if action!='inspect':publish(folder/name,encode(value));_checkpoint('after_'+name)
                    need(read(folder/name)==encode(value),'CONFIGURATION_CONFLICT')
                consumer=consume(req,check)
                evidence={'status':'VALIDATED','consumer':consumer,'invocation_sha256':sha(encode(invocation))}
            elif stage=='CP06':
                if action!='inspect':publish(folder/'expected-identity.json',encode(identity))
                need(read(folder/'expected-identity.json')==encode(identity),'IDENTITY_CONFLICT')
                evidence={'status':'VALIDATED','identity_sha256':sha(encode(identity)),
                          'process_identity':'NOT_STARTED','start_role_handoff':'NOT_READY'}
            elif stage=='CP07':
                evidence={'status':'VALIDATED','subject_uid':os.geteuid(),
                          'private_root':str(folder),'access':effective_access(folder,os.geteuid(),os.getegid()),
                          'files':{name:sha(read(folder/name)) for name in
                             ('ledger-config.json','profile.json','runtime-invocation.json','expected-identity.json')},
                          'service_uid':'UNKNOWN','callback_uid':1004,
                          'runtime_roles_granted_access':False}
            elif stage=='CP08':
                from .cp08_evidence import load as load_observation
                denied=load_observation(folder,request_sha256,req['cp03_receipt_sha256'])
                if denied['status']=='UNAVAILABLE' and str(root).startswith('/tmp/p2-b3-test-') and not str(root).startswith('/tmp/p2-b3-test-host-'):
                    # Retained local regression-only probe; never a production
                    # fallback and never changes UID inside the UK container.
                    denied=unauthorized_access(folder,os.geteuid(),os.getegid(),65534,65534)
                evidence={'status':'VALIDATED' if denied['status']=='PASS' else 'UNAVAILABLE',
                          'denial':denied,'scope':'PREPARATION_HANDOFF_DIRECTORY_ONLY'}
            else:
                need(consumer is not None and consumer['config_sha256']==sha(encode(cfg)),'TLS_CONSUMER_BINDING')
                evidence={'status':'VALIDATED','tls':consumer['tls'],'global_p2_tls':'NOT_CLAIMED'}
            if evidence['status']!='VALIDATED':
                # Observations and successful terminal receipts occupy distinct
                # immutable names. Same intent may recover after new real proof;
                # a changed request/contract cannot bypass a previous HOLD.
                observation=encode({'stage':stage,'request_sha256':request_sha256,'evidence':evidence})
                if action!='inspect':publish(folder/(stage+'-observation-'+sha(observation)+'.json'),observation)
                result['observations'].append(evidence);return result
            payload=encode({'schema':1,'scope':'ISOLATED_TEST_ONLY','stage':stage,
                            'status':'PREPARATION_CHECKPOINT_COMMITTED','request_sha256':request_sha256,
                            'previous_receipt_sha256':previous,'evidence':evidence})
            if action!='inspect':publish(committed,payload);_checkpoint('after_'+stage)
            if not os.path.lexists(committed):result['status']='NOT_EXECUTED';return result
            need(read(committed)==payload,'CHECKPOINT_CONFLICT')
            previous=sha(payload);result['completed'].append(stage)
        final=encode({'schema':1,'scope':'ISOLATED_TEST_ONLY','status':'PREPARATION_COMMITTED',
                      'request_sha256':request_sha256,'last_checkpoint_sha256':previous,
                      'service_started':False,'production_permission':False,'full_b3_complete':False})
        if action!='inspect':publish(folder/'preparation-receipt.json',final);_checkpoint('after_final')
        need(read(folder/'preparation-receipt.json')==final,'FINAL_RECEIPT_CONFLICT')
        result.update(status='PREPARATION_COMMITTED',receipt={'path':str(folder/'preparation-receipt.json'),
                                                            'sha256':sha(final)})
    except Exception as exc:
        result['error']={'type':type(exc).__name__,'code':str(exc) if isinstance(exc,ValueError) else type(exc).__name__}
    finally:
        if lock is not None:os.close(lock)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('execute','inspect','recover'))
    parser.add_argument('--request-sha256',required=True);args=parser.parse_args()
    raw=sys.stdin.buffer.read(1048577);need(len(raw)<=1048576,'REQUEST_BOUND')
    result=dispatch(json.loads(raw),args.action,args.request_sha256)
    print(json.dumps(result,sort_keys=True));return 0 if result['status']=='PREPARATION_COMMITTED' else 2


if __name__=='__main__':sys.exit(main())
