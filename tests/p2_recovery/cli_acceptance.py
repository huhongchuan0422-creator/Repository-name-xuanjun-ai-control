"""Real isolated CLI in a test container with synthetic UK hostname, NOT UK."""
import importlib.util,json,os,subprocess,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('fixtures',str(Path(__file__).with_name('test_recovery.py')))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
r=f.r
assert os.environ.get('P2_SYNTHETIC_CLI')=='1' and os.uname().nodename==r.HOST
f.RecoveryTests.setUpClass()
t=f.RecoveryTests()
t.setUp()
try:
    now=int(time.time());t.body['issued_utc']=now-1;t.body['expires_utc']=now+120
    refs={}
    refs['request']=t.write('request.json',r.canonical(t.request))
    refs['evidence']=t.write('evidence.json',r.canonical(t.signed()))
    refs['trust']=t.write('trust.json',r.canonical({'schema':1,'host':r.HOST,'keys':t.refs}))
    args=[sys.executable,'-I','-B','-S',str(f.MODULE)]
    inputs=[]
    for name,ref in refs.items():inputs+=['--'+name,ref['path'],'--'+name+'-sha256',ref['sha256']]
    def invoke(op,extra=()):
        return subprocess.run(args+[op]+inputs+list(extra),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
    q=invoke('assess');assert q.returncode==0,q.stdout
    result=json.loads(q.stdout);assert result['state']=='RECOVERY_EVIDENCE_VALIDATED_NOT_ACTIVATED'
    assert not result['authority_initialized'] and not result['writer_started']
    q=invoke('checkpoint',['--checkpoint-root',t.root]);assert q.returncode==0,q.stdout
    assert json.loads(q.stdout)['checkpoint']=='COMMITTED_DECISION_NOT_ACTIVATION'
    q=invoke('checkpoint',['--checkpoint-root',t.root]);assert q.returncode==0,q.stdout
    assert json.loads(q.stdout)['checkpoint']=='ALREADY_COMMITTED'
    t.body['expires_utc']=now-1;t.body['issued_utc']=now-120
    ref=t.write('evidence.json',r.canonical(t.signed()))
    inputs[inputs.index('--evidence-sha256')+1]=ref['sha256']
    q=invoke('assess');assert q.returncode==2 and json.loads(q.stdout)['reason']=='EVIDENCE_EXPIRED',q.stdout
    print('SYNTHETIC_CONTAINER_FORMAL_CLI=PASS assess/checkpoint/restart/expired')
    print('UK_EXECUTION=NOT_EXECUTED AUTHORITY_INITIALIZED=NO WRITER_STARTED=NO')
finally:
    t.doCleanups();f.RecoveryTests.tearDownClass()
