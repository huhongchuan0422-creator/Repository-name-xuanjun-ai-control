"""Export exact existing Stage B artifact as bytes; never install or rebuild it."""
import hashlib,json,os,pwd,re,socket,stat,subprocess,sys,tarfile,io
HOME_PATH='/home/xuanjun_dev'
COMMIT='f840b2e98724a9e5b940f73606ee0687b6ba98c8'
TREE='2810ad1e2c596796469c75999f8d1d62ecb74d2d'
JOB='a96b9a83-5e58-412c-ab66-ba3bf0add8b9'
WORK=HOME_PATH+'/xuanjun-p2-native-adapter-6121230482'
ENV={'HOME':HOME_PATH,'PATH':HOME_PATH+'/.openclaw/tools/node-v24.21.0/bin:/usr/bin:/bin','LANG':'C.UTF-8'}
def main():
    if os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid or os.geteuid()==0 or socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ':raise SystemExit('HOLD_FIXED_NONROOT')
    p=subprocess.run([HOME_PATH+'/.openclaw/bin/openclaw','automations','scratch',JOB,'--json'],env=ENV,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
    if p.returncode or len(p.stdout)>1048576:raise SystemExit('HOLD_SCRATCH_UNAVAILABLE')
    wrapper=json.loads(p.stdout.decode())
    state=wrapper['scratch']
    if isinstance(state,dict) and 'content' in state:state=state['content']
    if isinstance(state,str):state=json.loads(state)
    active=state['stage_b_active']
    if state['task']!='XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1' or active['state']!='COMPLETED' or active['result_commit']!=COMMIT or active['result_tree']!=TREE or active['run_id']!='b8c58d93-1089-4440-adf9-b40030ca05e2':raise SystemExit('HOLD_RESULT_BINDING_CHANGED')
    artifact=active['artifact']
    path=HOME_PATH+'/p2-stage-b-artifacts/xuanjun-p2-installable-'+COMMIT+'.tar.gz'
    if artifact['path']!=path:raise SystemExit('HOLD_PACKAGE_PATH_CHANGED')
    info=os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_size>16777216 or info.st_nlink!=1:raise SystemExit('HOLD_UNSAFE_PACKAGE')
    with open(path,'rb') as f:raw=f.read(16777217)
    sha=hashlib.sha256(raw).hexdigest()
    if sha!=artifact['sha256']:raise SystemExit('HOLD_PACKAGE_HASH_MISMATCH')
    manifests=[];names=[];total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
        members=tar.getmembers()
        if len(members)>2048:raise SystemExit('HOLD_PACKAGE_FILE_LIMIT')
        for member in members:
            name=member.name
            pieces=name.rstrip('/').split('/')
            if name.startswith('/') or any(x in ('','..') for x in pieces) or not(member.isfile() or member.isdir()):raise SystemExit('HOLD_UNSAFE_TAR_MEMBER')
            if re.search(r'(^|/)(auth.json|credentials[^/]*|id_rsa|id_ed25519|tokens?\.json|\.env)$',name,re.I):raise SystemExit('HOLD_PROTECTED_PACKAGE_FILE')
            total+=member.size
            if member.size>2097152 or total>33554432:raise SystemExit('HOLD_PACKAGE_EXPANSION_LIMIT')
            names.append(name)
            if member.isfile():
                data=tar.extractfile(member).read(2097153)
                if re.search(br'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=\r\n]{64,}',data) or re.search(br'\bsk-[A-Za-z0-9_-]{32,}\b',data):raise SystemExit('HOLD_CREDENTIAL_PATTERN')
                if hashlib.sha256(data).hexdigest()==artifact['manifest_sha256']:manifests.append(name)
    if len(manifests)!=1:raise SystemExit('HOLD_EXACT_MANIFEST_NOT_FOUND')
    def git(args):
        p=subprocess.run(['/usr/bin/git','--no-optional-locks','-C',WORK]+args,env=ENV,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        if p.returncode:raise SystemExit('HOLD_SOURCE_OBJECT_UNAVAILABLE')
        return p.stdout.decode().strip()
    if git(['rev-parse',COMMIT+'^{tree}'])!=TREE:raise SystemExit('HOLD_SOURCE_TREE_MISMATCH')
    native=[x for x in git(['ls-tree','-r','--name-only',COMMIT]).splitlines() if x.endswith('native_child_adapter.py')]
    changes=git(['diff','--name-status','3888f859eeb440a63602b2e9822823447ea8294c',COMMIT]).splitlines()
    report={'state':'EXACT_EXISTING_PACKAGE_RETAINED_NOT_RELEASED','scratch_revision':wrapper.get('currentRevision'),'run_id':active['run_id'],'commit':COMMIT,'tree':TREE,'archive_sha256':sha,'manifest_sha256':artifact['manifest_sha256'],'manifest_path':manifests[0],'file_count':len(names),'bytes':len(raw),'native_adapter_source_paths':native,'diff_from_retained_3888':changes[:100],'diff_count':len(changes),'install':'NO','model_calls':0,'authority_mutation':'NONE'}
    if '--bytes' in sys.argv:sys.stdout.buffer.write(raw)
    else:print(json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
