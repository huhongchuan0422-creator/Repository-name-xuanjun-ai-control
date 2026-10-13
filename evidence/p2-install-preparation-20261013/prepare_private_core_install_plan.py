"""Render an exact private core install plan; this program never applies it."""
import os, sys, stat, socket, json, hashlib, uuid, re
DURABLE='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
MANIFEST='dbe785330e881224bd16c3554a45a0a38bd8f88cb777ffa16fa35440a881efaf'
SOURCE='932a52a5aa35d1528546bb0ae3a4d13413dae8f6'
TREE='1a1e987c6098333b72e715c588ad3b73a45db1d1'
BASE='/tmp/p2pkg-38365394514-1'
BUNDLE='/tmp/p2pkg-38371013936-1/protected-install-preparation-bundle.json'
SDK='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/'
DEV='/etc/xuanjun-development/'
VAR='/var/lib/xuanjun-development'
RELNAME='integration-'+MANIFEST[:16]
RELEASE='/opt/xuanjun-control-releases/'+RELNAME
def sha(data):return hashlib.sha256(data).hexdigest()
def pack(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def protected(path,expected=None):
    assert os.path.realpath(path)==path
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o077
        raw=f.read(1048577);assert len(raw)<=1048576
    if expected:assert sha(raw)==expected
    return json.loads(raw.decode())
def reference(path,uid,mode):
    assert os.path.realpath(path)==path
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode) and s.st_uid==uid and stat.S_IMODE(s.st_mode)==mode
        h=hashlib.sha256()
        for x in iter(lambda:f.read(65536),b''):h.update(x)
        end=os.fstat(f.fileno());assert (s.st_size,s.st_mtime_ns)==(end.st_size,end.st_mtime_ns)
    return {'path':path,'sha256':h.hexdigest(),'owner_uid':uid,'mode':mode}
def main(package,output):
    assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
    assert os.path.realpath(package)==package
    assert re.fullmatch(r'/tmp/p2pkg-[0-9]+-[0-9]+/protected-core-install-plan.json',output)
    assert not os.path.lexists(VAR+'/activation/active.json'),'EXISTING_ACTIVATION_REQUIRES_REPLAN'
    with open(package+'/deploy/integration-manifest.json','rb') as f:assert sha(f.read())==MANIFEST
    prerequisites=protected(BASE+'/protected-prerequisites-subplan.json','9fbe85c665824a2c7b362dfb010fa47d3f144b67cd8dffa5b153efc4f64334a4')
    assert set(prerequisites['groups'])=={'xuanjun-dispatcher','xuanjun-callback','xj_codex_worker','xuanjun-control-db'}
    prerequisites['groups']['xuanjun-ledger-client']=1007  # Unreserved; real preflight checks NSS conflicts.

    bundle=protected(BUNDLE,'9bc378238ca9906420685c1940dd7c97511b0f022bcbd56c9471ef2cc7e09af7')
    transaction=str(uuid.uuid4());ledger=str(uuid.uuid4());instance=str(uuid.uuid4())
    dirs=[('/etc/xuanjun-development',0,0,0o755),('/etc/xuanjun-owner-callback',0,1006,0o750),
          (VAR,0,0,0o755),(VAR+'/activation',0,0,0o755),(VAR+'/generations',0,1006,0o750),
          (VAR+'/generations/1',1003,1006,0o750),(VAR+'/backups',0,0,0o700),
          (VAR+'/worktrees',1003,1003,0o755),(VAR+'/service-home',1003,1003,0o700),
          (VAR+'/worker-home',1005,1005,0o700),(VAR+'/codex-home',1005,1005,0o700),
          (VAR+'/users',0,0,0o755)]
    existing={x['path']:x for x in prerequisites['directories']}
    for p,u,g,m in dirs:existing[p]={'path':p,'uid':u,'gid':g,'mode':m}
    prerequisites['directories']=sorted(existing.values(),key=lambda x:(x['path'].count('/'),x['path']))
    tls_paths={}
    wanted_tls={'cert':'c4bfb6265349780c22c346657096291a96db804c2a3eac9b3ee0b62a2492a71d','key':'0910affcb259decf8bf5ae8d9079bcc95831fadb24de422fcbbb5ab1330615ea'}
    names=os.listdir(DURABLE);assert len(names)<128
    for name in names:
        path=DURABLE+'/'+name;info=os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>16384:continue
        ref=reference(path,0,0o600)
        for role,digest in wanted_tls.items():
            if ref['sha256']==digest:
                assert role not in tls_paths;tls_paths[role]=path
    assert set(tls_paths)=={'cert','key'}
    tokens={'@@SOURCE_COMMIT@@':SOURCE,'@@GENERATION@@':'1','@@RELEASE_DIRECTORY@@':RELNAME,
            '@@ARTIFACT_SHA256@@':MANIFEST,'@@LEDGER_UUID@@':ledger,'@@INSTANCE_UUID@@':instance,
            '@@CODEX_SHA256@@':'12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad',
            '@@LEDGER_SERVER_UID@@':'1003','@@PYTHON_SHA256@@':'ba19929d7038d0c2304f528213fa11e5f10c1ce65f0a891afa459bd167c7e5f6',
            '@@LEDGER_BRIDGE_PATH@@':RELEASE+'/stage1/native_ledger_bridge.py',
            '@@LEDGER_BRIDGE_CONFIG_PATH@@':DEV+'p2-native-ledger-client.json',
            '@@WORKSPACE_ROOT@@':VAR+'/worktrees','@@OWNER_HOST@@':'uk.wenwenwenyiyiyi.work',
            '@@TLS_CERT@@':tls_paths['cert'],'@@TLS_KEY@@':tls_paths['key']}
    roles=[('SANDBOX_CONTEXT','context-DyPstb2Q.mjs'),('SANDBOX_PREPARE','context-Dt2Gy7El.mjs'),
           ('SUBAGENT_RUNTIME','runtime-BgTk9ZFM.mjs'),('BEFORE_TOOL_HOOK','agent-tools.before-tool-call.runtime-DrbwqsOU.mjs'),
           ('REQUEST_SCOPED_ERROR','error-runtime-B-G5NrRT.mjs')]
    for key,name in roles:
        path=SDK+name;ref=reference(path,1002,0o644)
        tokens['@@'+key+'_PATH@@']=path;tokens['@@'+key+'_SHA256@@']=ref['sha256']
    with open(package+'/stage1/native_ledger_bridge.py','rb') as f:tokens['@@LEDGER_BRIDGE_SHA256@@']=sha(f.read())
    bindings=[];rendered={}
    def bind(source,target,mode=0o644,gid=0,extras=None):
        with open(package+'/'+source,'rb') as f:raw=f.read()
        wanted=set(x.decode() for x in re.findall(br'@@[A-Z0-9_]+@@',raw))
        all_tokens=dict(tokens);all_tokens.update(extras or {})
        replacements={x:all_tokens[x] for x in wanted}
        result=raw
        for key in sorted(replacements):result=result.replace(key.encode(),replacements[key].encode())
        assert not re.search(br'@@[A-Z0-9_]+@@',result)
        item={'source':source,'target':target,'source_sha256':sha(raw),'rendered_sha256':sha(result),
              'mode':mode,'owner_uid':0,'group_gid':gid,'replacements':replacements}
        bindings.append(item);rendered[target]=result
        return item
    bind('deploy/p2-native-ledger-client.json.template',DEV+'p2-native-ledger-client.json',0o640,1002)
    tokens['@@LEDGER_BRIDGE_CONFIG_SHA256@@']=sha(rendered[DEV+'p2-native-ledger-client.json'])
    bind('deploy/p2-native-controller.binding.json.template',DEV+'p2-native-controller.binding.json',0o640,1002)
    bind('deploy/p2-gateway-relay.json.template',DEV+'p2-gateway-relay.json',0o640,1002)
    bind('deploy/dispatcher.example.json',DEV+'dispatcher.json',0o640,1003)
    bind('deploy/root-broker.example.json',DEV+'root-broker.json',0o600)
    owner=bundle['owner_provisioning']
    owner_replacements=dict(owner['replacements']);owner_replacements['@@PACKAGE_SHA256@@']=MANIFEST
    bind(owner['source'],owner['target'],owner['mode'],owner['group_gid'],owner_replacements)
    bind('deploy/xuanjun-uk-openclaw-p2-docker.conf','/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf')
    bind('deploy/uk-owner-workbench/nginx.conf.template','/etc/nginx/conf.d/xuanjun-p2-owner.conf')
    sys.path.insert(0,package+'/stage1')
    from p2_fixed_host_runtime import ALLOWED_SERVICES
    for service in list(ALLOWED_SERVICES)+['xuanjun-github-intake.service']:
        path='deploy/'+service
        if not os.path.isfile(package+'/'+path):path='deploy/uk-owner-workbench/'+service
        bind(path,'/etc/systemd/system/'+service)
    def rh(name):return sha(rendered[DEV+name])
    plugin={'id':'xuanjun-p2-native-controller','source':'plugins/p2-native-controller',
            'binding_file':DEV+'p2-native-controller.binding.json','binding_sha256':rh('p2-native-controller.binding.json'),
            'ledger_client_config':DEV+'p2-native-ledger-client.json','ledger_client_sha256':rh('p2-native-ledger-client.json'),
            'gateway_service':'xuanjun-uk-openclaw.service','openclaw_bin':'/home/xuanjun_dev/.openclaw/bin/openclaw',
            'service_user':'xuanjun_dev','docker_dropin':'/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf',
            'gateway_relay_config':DEV+'p2-gateway-relay.json','gateway_relay_sha256':rh('p2-gateway-relay.json'),
            'gateway_relay_socket':'/run/xuanjun-development/p2-gateway.sock'}
    legacy={}
    for name,expected in [('xuanjun-uk-stage1-minimal.service','5fcf0cd435a1d1cc37c7721648376f04af7a82defa83936097f28084595187da'),
                          ('xuanjun-uk-openclaw.service','6ae3a87b472242e26347de88f6ed882ed3641b3bdfa7ab9eae9e355399b23348')]:
        path='/etc/systemd/system/'+name;ref=reference(path,0,0o644);assert ref['sha256']==expected
        legacy[name]={'fragment_path':path,'sha256':expected,'cgroup':'/system.slice/'+name}
    auth=[reference(x['path'],x['owner_uid'],x['mode']) for x in bundle['auth_references']]
    plan={'schema':1,'transaction_id':transaction,
          'artifact':{'root':package,'manifest':package+'/deploy/integration-manifest.json','source_commit':SOURCE,
                      'source_tree':TREE,'manifest_sha256':MANIFEST,'releases':'/opt/xuanjun-control-releases'},
          'cutover':{'schema':1,'transaction_id':transaction,'source':'/home/xuanjun_dev/uk-stage1-minimal/state.sqlite',
                     'rollback_snapshot':VAR+'/backups/'+transaction+'.sqlite','staged_generation':VAR+'/generations/1/state.sqlite',
                     'repository':'huhongchuan0422-creator/Repository-name-xuanjun-ai-control','legacy_bindings':legacy},
          'activation':{'release_sha256':MANIFEST,'config_sha256':rh('dispatcher.json'),
                        'binary_sha256':'d3d546fa491596cc4d82feac9746f0368eb65f20f3fd134164dca8055337dd3e',
                        'ledger_uuid':ledger,'generation':1,'instance':instance,'db_path':VAR+'/generations/1/state.sqlite',
                        'ledger_socket':'/run/xuanjun-development/ledger.sock','expected_epoch':0},
          'runtime':{'release_directory':RELNAME,'provisioning':bindings,'services':list(ALLOWED_SERVICES),
                     'prerequisites':prerequisites,'plugin':plugin},
          'auth':{'mode':'EXISTING_OAUTH_REFERENCE','references':auth},
          'tls':{'mode':'EXISTING_TLS_REFERENCE','references':[reference(tls_paths['cert'],0,0o600),reference(tls_paths['key'],0,0o600)]}}
    from p2_install_entrypoint import validate_plan
    from p2_prerequisites import validate as validate_prerequisites
    validate_plan(plan);validate_prerequisites(prerequisites)
    raw=pack(plan);fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    print('CORE_PLAN_SCHEMA_AND_PREREQUISITES_SCHEMA=PASS')
    print('CORE_PLAN_SHA256='+sha(raw))
    print('CORE_PLAN_BINDINGS='+str(len(bindings)))
    print('FULL_INSTALL_ADMISSION=NO; CORE_PLAN_PREFLIGHT=NOT_RUN; INSTALL=NO')
if __name__=='__main__':
    assert len(sys.argv)==3
    main(sys.argv[1],sys.argv[2])
