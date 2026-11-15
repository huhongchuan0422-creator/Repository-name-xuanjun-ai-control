# Fixed host-supplied offline HTTP observer. No candidate imports.
import hashlib, json, os, socket, subprocess, sys, tarfile, time, urllib.request
os.umask(0o077)
os.mkdir('/work/pkg',0o755)
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|*') as archive:
    for item in archive:
        name=item.name
        if not item.isfile() or name.startswith('/') or any(x in ('','..','.') for x in name.split('/')):
            raise RuntimeError('UNSAFE_TEST_PAYLOAD')
        target=('/libs/'+name if name.startswith('deps/') else '/work/pkg/'+name)
        os.makedirs(os.path.dirname(target),mode=0o755,exist_ok=True)
        with open(target,'wb') as out: out.write(archive.extractfile(item).read())
        os.chmod(target,0o644)
for base in ('/work/pkg','/libs'):
    for root,dirs,files in os.walk(base):
        os.chmod(root,0o755)

def demote():
    os.setgroups([]);os.setgid(65534);os.setuid(65534)

port=19273
env={'PATH':'/usr/local/bin:/usr/bin:/bin','PYTHONPATH':'/libs/deps','HOME':'/nonexistent','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
cmd=['python','-B','/work/pkg/scripts/task_center_app.py','--db','/work/pkg/fixture.sqlite',
     '--test-authority-key','0123456789abcdef0123456789abcdef','--tenant','tenant-a','--principal','fixture-viewer','--port',str(port)]
with open(os.devnull,'wb') as devnull, open('/work/service-error.log','w+b') as err:
    child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=devnull,stderr=err,preexec_fn=demote,env=env)
    state='UNAVAILABLE'; detail='NO_RESPONSE'; doc=None
    try:
        until=time.monotonic()+8
        while time.monotonic()<until:
            if child.poll() is not None: break
            try:
                request=urllib.request.Request('http://127.0.0.1:%s/api/public-projection'%port,headers={'Connection':'close'})
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=0.5) as response:
                    body=response.read(65537)
                    if response.status!=200 or len(body)>65536: raise ValueError('HTTP_STATUS_OR_SIZE')
                    doc=json.loads(body.decode('utf-8'))
                break
            except (OSError,ValueError): time.sleep(.1)
        if doc is not None:
            try:
                old={k:doc[k] for k in ('mode','production_status','observed_at','boards')}
                expected=hashlib.sha256(json.dumps(old,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
                assert set(doc)=={'mode','production_status','observed_at','boards','source','schema_version','snapshot_sha256','observed_at_unit','observed_at_semantics','valid_until','freshness'}
                assert doc['mode']=='TEST_ONLY' and doc['production_status']=='NOT_IMPLEMENTED'
                assert doc['source']=='task-center-public-projection' and doc['schema_version']==1 and doc['snapshot_sha256']==expected
                assert doc['observed_at_unit']=='unix_seconds' and doc['observed_at_semantics']=='MAX_CANONICAL_TASK_LAST_EVENT_AT'
                assert doc['freshness']=='UNKNOWN' and doc['valid_until'] is None
                assert isinstance(doc['observed_at'],(int,float)) and not isinstance(doc['observed_at'],bool)
                assert isinstance(doc['boards'],list) and any(b['task_count']>0 for b in doc['boards'])
                for board in doc['boards']:
                    assert set(board)=={'board_id','task_count','active_count','blocked_count','health'}
                assert 'fixture-private-sentinel' not in json.dumps(doc)
                state='PASS';detail='HTTP_PUBLIC_CONTRACT'
            except (AssertionError,KeyError,TypeError,ValueError): state='FAIL';detail='HTTP_CONTRACT_MISMATCH'
    finally:
        if child.poll() is None:
            subprocess.run(['python','-c','import os,signal;os.kill(int(os.environ["PID"]),signal.SIGTERM)'],env=dict(env,PID=str(child.pid)),preexec_fn=demote,stdout=devnull,stderr=devnull,timeout=2)
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                subprocess.run(['python','-c','import os,signal;os.kill(int(os.environ["PID"]),signal.SIGKILL)'],env=dict(env,PID=str(child.pid)),preexec_fn=demote,stdout=devnull,stderr=devnull,timeout=2)
                child.wait(timeout=3)
print(json.dumps({'state':state,'detail':detail},sort_keys=True),flush=True)
