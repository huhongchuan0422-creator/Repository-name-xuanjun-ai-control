"""Fixed OpenClaw2026.9.9 observation/profile adapter. Never executes Node or JS."""
import copy
import os
import re
import shlex

import epoch7_delta as d
import epoch7_snapshot as c
from probe_metadata import stable_read,protected,error_label,need,PROVISION
from unit_metadata import LAUNCHER,GATEWAY,UNITS,user_program,launcher_recipe
from unit_metadata import (NODE_REFERENCE_PATH,NODE_CANONICAL_PATH,NODE_PACKAGE_ROOT,
    DIRECT_DIST_WRAPPER,DIRECT_DIST_WRAPPER_SHA,validate_node_reference)

VERSION='2026.9.9'
SOURCE_HASHES={'dist/build-info.json': '6550ed6d598ceeab9dcbd94aa01c21337cabc35031e8891c699ae96fb333f58b', 'dist/cli/run-main.js': 'f03b82c2aedf493f3e1ddfda2fd46e2d0d38163127d1987827546b70058636ca', 'dist/config-env-vars-CFjF0--K.mjs': '29f159448563ce483e436cf8bb901f19ff4d94084320fa3e3479c51a808ebd4b', 'dist/dotenv-BAzkwZo-.mjs': 'a6ef09086515a1cf6d97aa8a2a4f87584685e0d0189cd80a7c18c3889c64b0ca', 'dist/dotenv-global-CP3dmTvh.mjs': '414082ecd363c4ba15f46e25075b3d75434b3e366a015e0ce7207b17cea910c3', 'dist/entry.js': '043980dff22859cd96fef04fe00d26c395a7ef8d2f67463777758c2987145a41', 'dist/entry.respawn-3dMNRLSy.mjs': '7b240a4c78e35f1ef0ff404ec2b96a9f6ed89a4417ef89a10ed2cf382aa4181e', 'dist/gateway-run-argv-DFDqy1EF.mjs': '038cc3f634aaab022f8adb8e541b2b6f5245fe08ad50d5b412899d85a3af57f1', 'dist/home-dir-D0b-ywue.mjs': '5fcab562e46b4b88dfea7d630ea621eee80bd6185e52895e6b08befa4d2e4a3c', 'dist/node-version-DdJ6cN09.mjs': 'b3d6d9d11f313ae70042380340f688a1db52e506c894b6b4dfdca11d56a85c0e', 'dist/paths-CtO6iw0c.mjs': '0fcef768ea381d210de1044327b4afb4602c76d1167a6f7147c729e7fd579b70', 'dist/pre-bootstrap-8enrRXrE.mjs': '82f668899640e0748f920e771cfabdd28589c68a044f1ba3ba41f5a6f00b43c8', 'dist/pre-bootstrap-qgGGBbez.mjs': '01c4e4e21872b7da6483e37c21ef43f9e4c48b0d9ad71935dd88eb529e0510eb', 'dist/proxy-lifecycle-Dl57fEmL.mjs': 'de283d5f397582801b5f35b43ffbe17cb4f49e70c14233a7d6bac2ac3fb794f6', 'dist/run-BNH_gC9b.mjs': '55673f688f7e455cd1bfdaf6a0f26270ff5e6565881403c1b066a82530ab810f', 'dist/run-command-D-K_dOJ-.mjs': 'a582d782e039327d2584c118517ca257aaeaf15e019bab520485764bd27edc8b', 'dist/run-command-DZaWbUcA.mjs': 'b0b889bbf65757684fc5b052965526a4362e31c1be0ba176bca7d1692c189fdc', 'dist/runtime-guard-BRBHlR8W.mjs': 'c35961cf02388fff4958c78fcfb8d39b412b148c37217b869ac9ec43368bf38a', 'dist/runtime-guard-BavKlA92.mjs': 'e226a9f84ad87249fe25619b1cf41c3e01f1e1a897feece811070971733bed77', 'dist/shell-env-Cxj7hKd1.mjs': '37f49b3b8654ceef1b17aeac0c5483baa7eee93e4ac006b5151ed5a542c7038b', 'dist/shell-env-Dc8Sl1Pk.mjs': '091a2a5ad70945a2c4ecd2825d9f5ab080292206f54e849bc274200b995ab626', 'dist/state-dir-CfAW6S2K.mjs': '09c4aeab9d9b6bfd37a4990b9c0489bffcd1f2a303d0f312f7515ad4d5c35854', 'dist/utils-DUAwk2p5.mjs': 'a0ad72edaa78c5f486c81e7a6c4ca954a860943d5e0675437f685d30f349f4c2', 'gateway-run-argv.mjs': 'aa1787742da5e06cef78d0fcdcd70932e3bab6a11b114a662355c57bd9fdc07a', 'node-compile-cache.mjs': '4b8842b79af6812f2e895ef458777db43591e96048859e3412717c28462fa9f7', 'node-host-launcher.mjs': 'b5e6a4c7f6ff08ef4ee4feb091054bada9577108edb3f0071870356ab3c28ab8', 'node-runtime-recovery.mjs': '2b2912ac98fb309d0948bb2218dd108da85eabfc71ec39870f01bc53cadbe579', 'node-sqlite.mjs': 'ef9e2430552069dfa8a8eb0900fd053ef6dc4218c5841693f3a0f9c8dae59aba', 'node-version.mjs': 'dfe6682632f769468297d877e2eab95212113cb37a7bdf5268795a838e49b26d', 'openclaw.mjs': 'aa8606ca0d62ff133ef5b7bd2323ec8ff3f8eb384404399cd5e742918d63b0a1', 'package.json': '214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95'}
ABSENT=('.git','src/entry.ts','.openclaw-lifecycle-pending','dist/openclaw-install-guard','dist/entry.mjs')
ENV_KEYS=('NODE_OPTIONS','BUN_OPTIONS','OPENCLAW_PROFILE','OPENCLAW_LOAD_SHELL_ENV','OPENCLAW_SERVICE_MARKER','OPENCLAW_CONTAINER','HOME','OPENCLAW_HOME','OPENCLAW_STATE_DIR','OPENCLAW_CONFIG_PATH','OPENCLAW_PROXY_URL','OPENCLAW_INCLUDE_ROOTS')
SELECTORS=('HOME','OPENCLAW_HOME','OPENCLAW_STATE_DIR','OPENCLAW_CONFIG_PATH')
META=('kind','dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns')
NODE_META=tuple(k for k in META if k!='kind')
RELAY='/etc/xuanjun-development/p2-gateway-relay.json'
DIRECT_ONLY_SOURCE_HASHES={'dist/is-main-DYSvvM1W.mjs':
    'cedd59a24eadaaf873515fabea73b776a66d40773c8ee5298f4946b9eef10469'}


def source_hashes(launcher_sha256):
    values=dict(SOURCE_HASHES)
    if launcher_sha256==DIRECT_DIST_WRAPPER_SHA:values.update(DIRECT_ONLY_SOURCE_HASHES)
    return values


def package_root(recipe):
    entry=recipe['entry_script']
    if entry==NODE_PACKAGE_ROOT+'/dist/entry.js':
        need(recipe['executable']==NODE_REFERENCE_PATH,'OPENCLAW_DIRECT_LITERAL_SCOPE')
        return NODE_PACKAGE_ROOT
    root=os.path.dirname(entry);c.path(root)
    need(root.startswith('/home/xuanjun_dev/') and root.endswith('/lib/node_modules/openclaw') and
         entry==root+'/openclaw.mjs','OPENCLAW_FIXED_PACKAGE_SCOPE')
    return root


def quiet_environment(value):
    need(type(value) is dict and set(value)==set(ENV_KEYS),'OPENCLAW_SELECTED_ENVIRONMENT_KEYS')
    need(all(value[k] is None for k in ('NODE_OPTIONS','BUN_OPTIONS','OPENCLAW_SERVICE_MARKER','OPENCLAW_CONTAINER','OPENCLAW_PROXY_URL','OPENCLAW_INCLUDE_ROOTS')) and
         value['OPENCLAW_PROFILE'] in (None,'default') and
         value['OPENCLAW_LOAD_SHELL_ENV'] in (None,'','0','false','no','off') and
         value['HOME']=='/home/xuanjun_dev' and value['OPENCLAW_HOME'] in (None,'/home/xuanjun_dev') and
         value['OPENCLAW_STATE_DIR'] in (None,'/home/xuanjun_dev/.openclaw') and
         value['OPENCLAW_CONFIG_PATH'] in (None,c.PROFILE),'OPENCLAW_SELECTED_ENVIRONMENT_UNSUPPORTED')
    return copy.deepcopy(value)


def public_metadata(row):
    need(set(row)>=set(META) and row['kind']=='FILE' and row['uid']==1002 and row['nlink']==1 and
         type(row['mode']) is int and not row['mode']&0o7022 and 0<row['size']<=8388608,'OPENCLAW_PROFILE_SOURCE_AUTHORITY')
    return {k:row[k] for k in META}


def literal_unit_environment(raw):
    """Supported systemd239 literal subset; never returns unrelated env values."""
    need(type(raw) is bytes and len(raw)<=65536,'OPENCLAW_UNIT_BOUND')
    section=None;selected={};selectors={};working=None
    for line in raw.decode('utf-8','strict').splitlines():
        line=line.strip()
        if not line or line.startswith(('#',';')):continue
        if line.startswith('[') and line.endswith(']'):section=line[1:-1];continue
        if section!='Service':continue
        need('=' in line and not line.endswith('\\'),'OPENCLAW_UNIT_SYNTAX_UNSUPPORTED')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if key in ('PassEnvironment','UnsetEnvironment','EnvironmentFile','PAMName','RootDirectory','RootImage','BindPaths','BindReadOnlyPaths','TemporaryFileSystem'):
            need(not value,'OPENCLAW_UNIT_ENVIRONMENT_OR_NAMESPACE_OVERRIDE')
        elif key=='WorkingDirectory':
            need(value in ('','/','/home/xuanjun_dev','/home/xuanjun_dev/.openclaw'),'OPENCLAW_WORKING_DIRECTORY_SCOPE')
            working=value or '/'
        elif key=='Environment':
            if not value:selected={};selectors={};continue
            need(not any(ch in value for ch in '\\$`%'),'OPENCLAW_UNIT_ENVIRONMENT_SYNTAX')
            for item in shlex.split(value):
                name,sep,text=item.partition('=')
                need(sep and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name),'OPENCLAW_UNIT_ENVIRONMENT_SYNTAX')
                if name in ENV_KEYS:selected[name]=text
                if name in SELECTORS:selectors[name]=text
    return {'selected':selected,'selectors':selectors,'working_directory':working or '/'}


def literal_wrapper_environment(raw,node,node_reference=None,node_sha256=None):
    recipe=launcher_recipe(raw,node);need(set(recipe['environment_names'])<={'HOME','PATH','LANG'},'OPENCLAW_WRAPPER_ENVIRONMENT_NAMES')
    if recipe['executable']!=node:
        need(raw==DIRECT_DIST_WRAPPER and node_sha256 is not None,'OPENCLAW_DIRECT_NODE_PROOF_REQUIRED')
        validate_node_reference(node_reference,node,node_sha256)
    else:need(node_reference is None,'OPENCLAW_ROOT_PROFILE_ALIAS_PROOF_FORBIDDEN')
    values={};executed=False
    for line in raw.decode('utf-8','strict').splitlines()[1:]:
        line=line.strip()
        if not line or line.startswith('#'):continue
        need(not executed,'OPENCLAW_WRAPPER_TRAILING_STATEMENT')
        if line.startswith('exec '):executed=True
        if line.startswith('export '):
            token=shlex.split(line)[1];name,unused,value=token.partition('=');values[name]=value
    need('HOME' not in values or values['HOME']=='/home/xuanjun_dev','OPENCLAW_WRAPPER_HOME')
    return recipe,values


def config_projection(raw):
    """Parse the fixed JSON profile, retaining no credentials or unrelated values."""
    need(type(raw) is bytes and len(raw)<=1048576,'OPENCLAW_CONFIG_BOUND')
    value=c.decode(raw);need(type(value) is dict,'OPENCLAW_CONFIG_OBJECT')
    def includes(item,depth=0):
        need(depth<=32,'OPENCLAW_CONFIG_DEPTH')
        if type(item) is dict:
            need(not any(k in ('$include','includeRoots','includeRoot') for k in item),'OPENCLAW_CONFIG_INCLUDE_UNSUPPORTED')
            for child in item.values():includes(child,depth+1)
        elif type(item) is list:
            for child in item:includes(child,depth+1)
    includes(value)
    env=value.get('env',{});proxy=value.get('proxy',{})
    need(type(env) is dict and type(proxy) is dict,'OPENCLAW_CONFIG_SELECTED_OBJECTS')
    variables=env.get('vars',{});shell=env.get('shellEnv',{})
    need(type(variables) is dict and type(shell) is dict,'OPENCLAW_CONFIG_ENV_OBJECTS')
    need(not set(ENV_KEYS+SELECTORS)&{key.strip().upper() for key in set(env)|set(variables)},
         'OPENCLAW_CONFIG_SELECTED_ENV_DECLARATION')
    shell_enabled=shell.get('enabled');proxy_enabled=proxy.get('enabled');url=proxy.get('proxyUrl')
    need((shell_enabled is None or shell_enabled is False) and
         (proxy_enabled is None or proxy_enabled is False) and
         (url is None or type(url) is str and not url.strip()),'OPENCLAW_CONFIG_QUIET_REQUIRED')
    return {'env_shell_enabled':shell_enabled,'proxy_enabled':proxy_enabled,
            'proxy_url_present':False,'include_present':False}


def dotenv_names(raw):
    """Finite literal declarations only; no values are returned or interpolated."""
    need(type(raw) is bytes and len(raw)<=65536,'OPENCLAW_DOTENV_BOUND')
    names=[]
    for line in raw.decode('utf-8','strict').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('export '):line=line[7:].lstrip()
        match=re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)',line)
        need(match is not None,'OPENCLAW_DOTENV_SYNTAX_UNSUPPORTED')
        name,value=match.groups()
        # Multiline/escaped quote grammar is intentionally unsupported. Refuse
        # ambiguity rather than overlooking a selected declaration on a line.
        if value[:1] in ('"',"'"):
            quote=value[0];end=value.find(quote,1)
            need(end>=1 and '\\' not in value[:end] and
                 (not value[end+1:].strip() or value[end+1:].lstrip().startswith('#')),
                 'OPENCLAW_DOTENV_SYNTAX_UNSUPPORTED')
        need(name.upper() not in ENV_KEYS+SELECTORS,'OPENCLAW_DOTENV_SELECTED_DECLARATION')
        names.append(name)
    return sorted(set(names))


def dotenv_paths(unit_raw):
    working=literal_unit_environment(unit_raw)['working_directory']
    return tuple(sorted(set(('/home/xuanjun_dev/.openclaw/.env',
        '/home/xuanjun_dev/.config/openclaw/gateway.env',working.rstrip('/')+'/.env'))))


def quiet_projection(manager_selected,account,unit_raw,wrapper_raw,node_path,config_raw,
                     dotenv_raw_by_path,relay_config_raw,dropin_raws=(),node_reference=None,node_sha256=None):
    """Pure source-reviewed projection shared with fresh post-edit live guards.

    Inputs are private bytes from separately protected readers. None of the raw
    bytes or unrelated environment/configuration values are returned. A None
    dotenv value means the caller separately proved that exact path absent.
    """
    from unit_metadata import service_fields
    need(type(manager_selected) is dict and set(manager_selected)==set(ENV_KEYS),'OPENCLAW_MANAGER_SELECTED_KEYS')
    need(account=={'user':'xuanjun_dev','uid':1002,'gid':1002,'home':'/home/xuanjun_dev'},'OPENCLAW_ACCOUNT_HOME_REQUIRED')
    fields=service_fields(unit_raw,gateway=True)
    need(fields['User'] and fields['User'][-1]=='xuanjun_dev','OPENCLAW_UNIT_USER')
    for raw in dropin_raws:
        fields=service_fields(raw)
        need(not fields['User'] and not fields['Group'],'OPENCLAW_DROPIN_CREDENTIAL_OVERRIDE')
    unit=literal_unit_environment(unit_raw);recipe,wrapper=literal_wrapper_environment(
        wrapper_raw,node_path,node_reference,node_sha256)
    selected=copy.deepcopy(manager_selected)
    # v239 synthesizes HOME for the explicit User before literal unit env wins.
    selected['HOME']=account['home'];selected.update(unit['selected'])
    if 'HOME' in wrapper:selected['HOME']=wrapper['HOME']
    selected=quiet_environment(selected)
    need(type(dotenv_raw_by_path) is dict and set(dotenv_raw_by_path)==set(dotenv_paths(unit_raw)),
         'OPENCLAW_DOTENV_EXACT_PATHS')
    declarations={path:None if raw is None else dotenv_names(raw) for path,raw in dotenv_raw_by_path.items()}
    config=config_projection(config_raw);relay=c.decode(relay_config_raw)
    need(type(relay) is dict and set(relay)=={'openclaw_bin','openclaw_sha256','openclaw_owner_uid',
         'gateway_home','gateway_path','dispatcher_user'},'OPENCLAW_RELAY_SCHEMA')
    need(relay['openclaw_bin']==LAUNCHER and relay['openclaw_sha256']==c.sha(wrapper_raw) and
         relay['openclaw_owner_uid']==1002 and relay['gateway_home']=='/home/xuanjun_dev' and
         type(relay['gateway_path']) is str and 0<len(relay['gateway_path'])<=4096 and
         '\x00' not in relay['gateway_path'],'OPENCLAW_RELAY_BINDING')
    return {'selected_environment':selected,'config_projection':config,'node_exec_argv':[],
        'relay_environment':{'HOME':relay['gateway_home'],'PATH':relay['gateway_path'],'LANG':'C.UTF-8'},
        'dotenv_declarations':declarations}


def collect_openclaw_profile(io,unit_facts,observation,candidate_root=None):
    """One bounded fixed-file observation. Complete facts are still unreviewed."""
    sections={};values={};captures={};absence=set()
    def section(name,fn):
        try:
            value=fn();values[name]=value;sections[name]={'state':'MEASURED_UNREVIEWED'};return value
        except (KeyboardInterrupt,SystemExit):raise
        except Exception as error:sections[name]={'state':'UNKNOWN','reason':error_label(error)};return None
    def read(path,maximum,uid=1002):
        raw,row=stable_read(io,path,maximum)
        if uid==0:protected(row,maximum)
        else:
            need(row['kind']=='FILE' and row['uid']==uid and row['nlink']==1 and
                 not row['mode']&0o7022,'OPENCLAW_PRIVATE_FILE_AUTHORITY')
        captures[path]=(raw,row,maximum);return raw,row
    def missing(path):
        need(io.absent(path) is True and io.absent(path) is True,'OPENCLAW_REQUIRED_ABSENCE')
        absence.add(path);return 'ABSENT'
    def measured(name):
        row=unit_facts['sections'][name];need(row['state']=='MEASURED_UNREVIEWED','OPENCLAW_UNIT_FACT_UNAVAILABLE')
        return row['evidence']
    identity=section('native_identity',lambda:measured('native_gateway')['gateway_identity'])
    def launcher():
        need(identity is not None,'OPENCLAW_NATIVE_UNAVAILABLE')
        raw,row=read(LAUNCHER,65536);original=measured('launcher');reference=original.get('node_reference')
        recipe,unused=literal_wrapper_environment(raw,identity['exe'],reference,identity['sha256'])
        need(row['sha256']==original['sha256'] and recipe==original['recipe'],'OPENCLAW_LAUNCHER_BINDING')
        root=package_root(recipe)
        public={'path':LAUNCHER,'sha256':row['sha256'],'recipe':recipe,'entry_realpath':recipe['entry_script']}
        if reference is not None:
            need(io.node_directory_reference(identity['exe'],identity['sha256'])==reference,'OPENCLAW_NODE_REFERENCE_CHANGED')
            public['node_reference']=copy.deepcopy(reference)
        return {'raw':raw,'root':root,'public':public}
    launch=section('launcher',launcher)
    files={};total=[0]
    expected_sources=source_hashes(c.sha(launch['raw']) if launch is not None else None)
    for relative,pin in sorted(expected_sources.items()):
        def source(relative=relative,pin=pin):
            need(launch is not None,'OPENCLAW_PACKAGE_ROOT_UNAVAILABLE')
            need(total[0]<33554432,'OPENCLAW_PROFILE_AGGREGATE_BOUND')
            raw,row=read(launch['root']+'/'+relative,min(8388608,33554432-total[0]));total[0]+=len(raw)
            need(total[0]<=33554432,'OPENCLAW_PROFILE_AGGREGATE_BOUND')
            need(row['sha256']==pin,'OPENCLAW_INSTALLED_SOURCE_MISMATCH')
            if relative=='package.json':
                package=c.decode(raw);need(package.get('name')=='openclaw' and package.get('version')==VERSION and
                    package.get('bin')=={'openclaw':'openclaw.mjs'},'OPENCLAW_EXACT_PACKAGE')
            files[relative]={'sha256':pin,'metadata':public_metadata(row)}
            return files[relative]
        section('source:'+relative,source)
    for relative in ABSENT:
        section('absence:'+relative,lambda relative=relative:missing(launch['root']+'/'+relative)
                if launch is not None else need(False,'OPENCLAW_PACKAGE_ROOT_UNAVAILABLE'))
    def node():
        need(identity is not None,'OPENCLAW_NATIVE_UNAVAILABLE')
        row=observation['evidence']['retained']['native_components']['components'][identity['exe']]
        need(row['sha256']==identity['sha256'],'OPENCLAW_NATIVE_HASH_BINDING')
        if launch is not None and 'node_reference' in launch['public']:
            referenced=launch['public']['node_reference']['final']['metadata']
            need(all(referenced[key]==row[key] for key in META+('sha256',)), 'OPENCLAW_ALIAS_NATIVE_DESCRIPTOR_BINDING')
        return io.verify_node_descriptor(identity['exe'],row)
    descriptor=section('node',node)
    def manager():
        value=io.gateway_manager_environment()
        need(value['source']=='SYSTEM_MANAGER_CHILD_ENVIRONMENT' and
             set(value['selectors'])==set(SELECTORS) and
             all(value['selectors'][key]==value['selected'][key] for key in SELECTORS),'OPENCLAW_MANAGER_SELECTOR_UNSUPPORTED')
        need(value['manager_sha256']==d.digest(observation['evidence']['writers']['manager']),
             'OPENCLAW_MANAGER_OBSERVATION_BINDING')
        return value
    manager_value=section('manager',manager)
    account=section('account',lambda:io.gateway_account_home())
    def unit():
        legacy=measured('legacy_gateway');raw,row=read(legacy['backup_path'],65536,0)
        need(row['sha256']==legacy['backup_sha256']==legacy['original_unit']['sha256'],'OPENCLAW_RESTORED_UNIT_BINDING')
        literal_unit_environment(raw)
        return {'raw':raw,'target':legacy['original_unit']['path'],'sha256':row['sha256']}
    unit_value=section('unit',unit)
    def dropins():
        inventory=measured('dropins')['units'][GATEWAY];raws=[]
        need(set(inventory)=={root+'/'+GATEWAY+'.d' for root in
             ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')},'OPENCLAW_DROPIN_ROOTS')
        for root,item in sorted(inventory.items()):
            need(item.get('state')!='UNKNOWN' and type(item['present']) is bool,'OPENCLAW_DROPIN_UNKNOWN')
            for path,pin in sorted(item['files'].items()):
                raw,row=read(path,65536,0);need(row['sha256']==pin['sha256'] and row==pin['metadata'],'OPENCLAW_DROPIN_CHANGED')
                # No credentials/environment changes are allowed, so precedence
                # and basename shadowing do not affect the quiet projection.
                from unit_metadata import service_fields
                fields=service_fields(raw);need(not fields['User'] and not fields['Group'],'OPENCLAW_DROPIN_CREDENTIAL_OVERRIDE')
                raws.append(raw)
        current=io.unit_dropins(UNITS)
        for root,item in inventory.items():
            actual=current[GATEWAY][root]
            need(actual['present']==item['present'] and set(actual['files'])==set(item['files']),'OPENCLAW_DROPIN_INVENTORY_CHANGED')
            for path,pin in item['files'].items():need(actual['files'][path][1]==pin['metadata'],'OPENCLAW_DROPIN_CHANGED')
        return raws
    dropin_value=section('dropins',dropins)
    profile=section('config',lambda:read(c.PROFILE,1048576))
    dotenv={}
    paths=dotenv_paths(unit_value['raw']) if unit_value else (
        '/home/xuanjun_dev/.openclaw/.env','/home/xuanjun_dev/.config/openclaw/gateway.env','/.env')
    for path in paths:
        def envfile(path=path):
            if io.absent(path):missing(path);dotenv[path]=None;return {'state':'ABSENT'}
            raw,row=read(path,65536,0 if path=='/.env' else 1002)
            declarations=dotenv_names(raw);dotenv[path]=raw
            return {'state':'PRESENT','sha256':row['sha256'],'declarations':declarations}
        section('dotenv:'+path,envfile)
    def relay():
        receipt_raw,receipt=read(PROVISION,1048576,0)
        need(receipt['mode']==0o600,'OPENCLAW_PROVISION_AUTHORITY')
        rows=c.decode(receipt_raw)['targets'];need(len(rows)==24 and {x['target'] for x in rows}==d.TARGETS,'OPENCLAW_PROVISION_SCOPE')
        pin=next(x for x in rows if x['target']==RELAY)
        # This one retained target is intentionally root:dev 0640. Do not
        # weaken protected() or extend this receipt-scoped exception to units,
        # backups, journals or other root:root files.
        need(all(type(pin[k]) is int for k in ('uid','gid','mode')) and
             tuple(pin[k] for k in ('uid','gid','mode'))==(0,1002,0o640),'OPENCLAW_RELAY_RETAINED_AUTHORITY')
        raw,row=stable_read(io,RELAY,65536)
        need(row['kind']=='FILE' and row['nlink']==1 and pin['rendered_sha256']==row['sha256'] and
             all(type(row[k]) is int and row[k]==pin[k] for k in ('uid','gid','mode')),
             'OPENCLAW_RELAY_PROVISION_BINDING')
        captures[RELAY]=(raw,row,65536)
        return raw
    relay_value=section('relay',relay)
    def staged_cwd():
        from probe_metadata import RUNTIME_MANIFEST
        need(candidate_root==c.CAND+'/epoch7-recovery-candidate-r6/xuanjun-p2-package','OPENCLAW_STAGED_CWD_REQUIRED')
        raw,row=read(candidate_root+'/deploy/integration-manifest.json',1048576,0)
        need(row['sha256']==RUNTIME_MANIFEST and 'stage1/.env' not in c.decode(raw)['files'],'OPENCLAW_STAGED_MANIFEST')
        missing(candidate_root+'/stage1/.env')
        return {'runtime_manifest_sha256':RUNTIME_MANIFEST,'staged_dotenv':'ABSENT'}
    section('relay_cwd',staged_cwd)
    def quiet():
        need(all(x is not None for x in (manager_value,account,unit_value,launch,profile,relay_value,dropin_value)),
             'OPENCLAW_QUIET_INPUT_UNAVAILABLE')
        return quiet_projection(manager_value['selected'],account,unit_value['raw'],launch['raw'],identity['exe'],
            profile[0],dotenv,relay_value,dropin_value,launch['public'].get('node_reference'),identity['sha256'])
    projected=section('quiet_projection',quiet)
    def stable():
        if dropin_value is not None:need(dropins()==dropin_value,'OPENCLAW_LATE_DROPIN_RACE')
        if descriptor is not None:need(node()==descriptor,'OPENCLAW_LATE_NODE_RACE')
        if launch is not None and 'node_reference' in launch['public']:
            need(io.node_directory_reference(identity['exe'],identity['sha256'])==launch['public']['node_reference'],
                 'OPENCLAW_LATE_NODE_REFERENCE_RACE')
        if 'policy' in observation:
            directories=observation['policy']['directories']
            for path in captures:
                parent=os.path.dirname(path)
                while True:
                    need(parent in directories and directories[parent]==io.pins[parent],
                         'OPENCLAW_ANCESTOR_NOT_IN_FROZEN_POLICY')
                    if parent=='/':break
                    parent=os.path.dirname(parent)
        for path,(raw,row,maximum) in sorted(captures.items()):
            need(io.read(path,maximum=maximum)==(raw,row),'OPENCLAW_LATE_FILE_RACE')
        for path in sorted(absence):need(io.absent(path) is True,'OPENCLAW_LATE_ABSENCE_RACE')
        if manager_value is not None:need(io.gateway_manager_environment()==manager_value,'OPENCLAW_LATE_MANAGER_RACE')
        if account is not None:need(io.gateway_account_home()==account,'OPENCLAW_LATE_ACCOUNT_RACE')
        return True
    section('stability',stable)
    unknown=sorted(name for name,row in sections.items() if row['state']=='UNKNOWN')
    result={'schema':1,'state':'UNKNOWN' if unknown else 'COMPLETE_UNREVIEWED','sections':sections,
        'missing_fields':unknown,'source_execution':'NOT_PERFORMED','install_admission':'NOT_GRANTED',
        'node_probe_state':'SEPARATE_REVIEWED_PROBE_REQUIRED'}
    # Values with private bytes or unsafe manager values are NEVER copied out.
    if not unknown:
        bindings={unit_value['target']:unit_value['sha256'],LAUNCHER:c.sha(launch['raw']),c.PROFILE:c.sha(profile[0]),RELAY:c.sha(relay_value)}
        for path,raw in dotenv.items():
            if raw is not None:bindings[path]=c.sha(raw)
        result['recipe_evidence']={'schema':1,'package_root':launch['root'],'files':files,
            'launcher':launch['public'],'node':descriptor,'quiet_bootstrap':{
                'schema':1,'selected_environment':projected['selected_environment'],
                'config_projection':projected['config_projection'],'source_bindings':bindings,
                'manager_sha256':manager_value['manager_sha256'],
                'package_absence':{name:'ABSENT' for name in ABSENT},'node_exec_argv':[],
                'relay_environment':projected['relay_environment']}}
        result['supporting_evidence']={'dotenv':{path:{'state':'ABSENT'} if raw is None else
            {'state':'PRESENT','sha256':c.sha(raw),'declarations':projected['dotenv_declarations'][path]} for path,raw in dotenv.items()},
            'account':account,'staged_cwd':values['relay_cwd'],'systemctl_sha256':manager_value['systemctl_sha256']}
    return result


def recipe_from_observation(observation):
    """Attach only the original full reviewed probe chain, never a leaf shortcut.

    The enclosing private observation and expected policy digest are protected
    and separately bound by the kit/admission; internal hashes are consistency
    evidence, not independent authorization.
    """
    profile=observation.get('openclaw_profile')
    if profile is None:return None
    need(d.digest(profile)==observation['openclaw_profile_sha256'],'OPENCLAW_PROFILE_DIGEST')
    if profile.get('state')=='UNKNOWN':return None
    need(profile.get('state')=='COMPLETE_UNREVIEWED' and profile.get('missing_fields')==[] and
         all(row['state']=='MEASURED_UNREVIEWED' for row in profile['sections'].values()),'OPENCLAW_PROFILE_INCOMPLETE')
    if 'finite_probe' not in observation:return None
    from node_sqlite_probe import binding_from_observation,validated_proof_from_attempt
    binding=binding_from_observation(observation)
    value=copy.deepcopy(profile['recipe_evidence']);need(value['node']==binding['node'],'OPENCLAW_PROFILE_NODE_BINDING')
    need(value['quiet_bootstrap']['manager_sha256']==d.digest(observation['evidence']['writers']['manager']),
         'OPENCLAW_PROFILE_MANAGER_BINDING')
    attempt=observation['finite_probe']
    if attempt.get('stage') in ('HOLD_NOT_EXECUTED','HOLD_AFTER_ATTEMPT'):return None
    policy=attempt['policy']
    # Original pre-probe snapshot resources are immutable and copied into the
    # post-probe envelope; the helper validates exact original context digests.
    original={key:item for key,item in observation.items() if key!='finite_probe'}
    proof=validated_proof_from_attempt(attempt,policy,original,attempt['policy_sha256'])
    value['node_probe']=proof
    return value


def prime_profile_scope(io,unit_facts,candidate_root=None):
    """Measure only fixed ancestors before the strict policy digest is frozen.

    No discovery walk or missing-file trust: final collection rereads all bytes,
    metadata and absences. Missing or unsafe ancestors are reported there.
    """
    failures={}
    try:
        recipe=unit_facts['sections']['launcher']['evidence']['recipe']
        root=package_root(recipe)
        launcher=unit_facts['sections']['launcher']['evidence']
        paths={root+'/'+name for name in tuple(source_hashes(launcher['sha256']))+ABSENT}
        legacy=unit_facts['sections']['legacy_gateway']['evidence']
        raw,row=stable_read(io,legacy['backup_path'],65536);protected(row,65536)
        need(row['sha256']==legacy['backup_sha256'],'OPENCLAW_RESTORED_UNIT_BINDING')
        paths.update(dotenv_paths(raw))
        if candidate_root==c.CAND+'/epoch7-recovery-candidate-r6/xuanjun-p2-package':paths.add(candidate_root+'/stage1/.env')
        for path in sorted(paths):
            try:io.absent(path)
            except (KeyboardInterrupt,SystemExit):raise
            except Exception as error:failures[path]=error_label(error)
    except (KeyboardInterrupt,SystemExit):raise
    except Exception as error:failures['fixed_scope']=error_label(error)
    return failures
