"""Pure, finite OpenClaw2026.9.9 startup profile. No package/source execution.

This profile covers only the reviewed launcher/title/respawn process families.
It does not claim that all transitive business modules were audited. Unlisted
children remain forbidden. Concrete admission must derive every measurement
from the authenticated collector and separately reviewed finite probe receipt.
"""
import copy
import re

VERSION='2026.9.9'
UPSTREAM='bcfc88812a35243893585dbeca87ca41b48272ca'
TARBALL='a46df5fc5e4d73837d5b3eeebc286e64a85dffc429c30f3a07f6398e2a9423f7'
GATEWAY='xuanjun-uk-openclaw.service'
RELAY='xuanjun-p2-gateway-relay.service'
LAUNCHER='/home/xuanjun_dev/.openclaw/bin/openclaw'
ABSENT=('.git','src/entry.ts','.openclaw-lifecycle-pending','dist/openclaw-install-guard','dist/entry.mjs')
ENV_KEYS=('NODE_OPTIONS','BUN_OPTIONS','OPENCLAW_PROFILE','OPENCLAW_LOAD_SHELL_ENV',
          'OPENCLAW_SERVICE_MARKER','OPENCLAW_CONTAINER','HOME','OPENCLAW_HOME',
          'OPENCLAW_STATE_DIR','OPENCLAW_CONFIG_PATH','OPENCLAW_PROXY_URL','OPENCLAW_INCLUDE_ROOTS')
SOURCE_HASHES = {'openclaw.mjs': 'aa8606ca0d62ff133ef5b7bd2323ec8ff3f8eb384404399cd5e742918d63b0a1', 'node-host-launcher.mjs': 'b5e6a4c7f6ff08ef4ee4feb091054bada9577108edb3f0071870356ab3c28ab8', 'node-runtime-recovery.mjs': '2b2912ac98fb309d0948bb2218dd108da85eabfc71ec39870f01bc53cadbe579', 'node-sqlite.mjs': 'ef9e2430552069dfa8a8eb0900fd053ef6dc4218c5841693f3a0f9c8dae59aba', 'node-version.mjs': 'dfe6682632f769468297d877e2eab95212113cb37a7bdf5268795a838e49b26d', 'node-compile-cache.mjs': '4b8842b79af6812f2e895ef458777db43591e96048859e3412717c28462fa9f7', 'gateway-run-argv.mjs': 'aa1787742da5e06cef78d0fcdcd70932e3bab6a11b114a662355c57bd9fdc07a', 'dist/entry.js': '043980dff22859cd96fef04fe00d26c395a7ef8d2f67463777758c2987145a41', 'dist/entry.respawn-3dMNRLSy.mjs': '7b240a4c78e35f1ef0ff404ec2b96a9f6ed89a4417ef89a10ed2cf382aa4181e', 'dist/gateway-run-argv-DFDqy1EF.mjs': '038cc3f634aaab022f8adb8e541b2b6f5245fe08ad50d5b412899d85a3af57f1', 'dist/runtime-guard-BavKlA92.mjs': 'e226a9f84ad87249fe25619b1cf41c3e01f1e1a897feece811070971733bed77', 'dist/runtime-guard-BRBHlR8W.mjs': 'c35961cf02388fff4958c78fcfb8d39b412b148c37217b869ac9ec43368bf38a', 'dist/node-version-DdJ6cN09.mjs': 'b3d6d9d11f313ae70042380340f688a1db52e506c894b6b4dfdca11d56a85c0e', 'dist/cli/run-main.js': 'f03b82c2aedf493f3e1ddfda2fd46e2d0d38163127d1987827546b70058636ca', 'dist/run-command-DZaWbUcA.mjs': 'b0b889bbf65757684fc5b052965526a4362e31c1be0ba176bca7d1692c189fdc', 'dist/run-command-D-K_dOJ-.mjs': 'a582d782e039327d2584c118517ca257aaeaf15e019bab520485764bd27edc8b', 'dist/run-BNH_gC9b.mjs': '55673f688f7e455cd1bfdaf6a0f26270ff5e6565881403c1b066a82530ab810f', 'dist/pre-bootstrap-qgGGBbez.mjs': '01c4e4e21872b7da6483e37c21ef43f9e4c48b0d9ad71935dd88eb529e0510eb', 'dist/pre-bootstrap-8enrRXrE.mjs': '82f668899640e0748f920e771cfabdd28589c68a044f1ba3ba41f5a6f00b43c8', 'dist/shell-env-Cxj7hKd1.mjs': '37f49b3b8654ceef1b17aeac0c5483baa7eee93e4ac006b5151ed5a542c7038b', 'dist/shell-env-Dc8Sl1Pk.mjs': '091a2a5ad70945a2c4ecd2825d9f5ab080292206f54e849bc274200b995ab626', 'package.json': '214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95', 'dist/build-info.json': '6550ed6d598ceeab9dcbd94aa01c21337cabc35031e8891c699ae96fb333f58b', 'dist/dotenv-BAzkwZo-.mjs': 'a6ef09086515a1cf6d97aa8a2a4f87584685e0d0189cd80a7c18c3889c64b0ca', 'dist/dotenv-global-CP3dmTvh.mjs': '414082ecd363c4ba15f46e25075b3d75434b3e366a015e0ce7207b17cea910c3', 'dist/state-dir-CfAW6S2K.mjs': '09c4aeab9d9b6bfd37a4990b9c0489bffcd1f2a303d0f312f7515ad4d5c35854', 'dist/paths-CtO6iw0c.mjs': '0fcef768ea381d210de1044327b4afb4602c76d1167a6f7147c729e7fd579b70', 'dist/home-dir-D0b-ywue.mjs': '5fcab562e46b4b88dfea7d630ea621eee80bd6185e52895e6b08befa4d2e4a3c', 'dist/utils-DUAwk2p5.mjs': 'a0ad72edaa78c5f486c81e7a6c4ca954a860943d5e0675437f685d30f349f4c2', 'dist/config-env-vars-CFjF0--K.mjs': '29f159448563ce483e436cf8bb901f19ff4d94084320fa3e3479c51a808ebd4b', 'dist/proxy-lifecycle-Dl57fEmL.mjs': 'de283d5f397582801b5f35b43ffbe17cb4f49e70c14233a7d6bac2ac3fb794f6'}


# This second profile is selected only by the exact retained188-byte wrapper.
# It bypasses openclaw.mjs, so it grants no packaged-cache Gateway child.
DIRECT_WRAPPER_SHA='b6aff1f40be0d46330c167e44525ef9080d66e40bb36dbb66c3811b4103fe3f2'
DIRECT_NODE_REFERENCE='/home/xuanjun_dev/.openclaw/tools/node/bin/node'
DIRECT_NODE_PATH='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node'
DIRECT_PACKAGE_ROOT='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw'
DIRECT_ENTRY=DIRECT_PACKAGE_ROOT+'/dist/entry.js'
DIRECT_SOURCE_HASHES=dict(SOURCE_HASHES,**{
    'dist/is-main-DYSvvM1W.mjs':'cedd59a24eadaaf873515fabea73b776a66d40773c8ee5298f4946b9eef10469'})


def source_hashes(launcher_sha256):
    return copy.deepcopy(DIRECT_SOURCE_HASHES if launcher_sha256==DIRECT_WRAPPER_SHA else SOURCE_HASHES)


def need(value,label):
    if not value:raise ValueError('EPOCH7_OPENCLAW_'+label)


def profile(launcher_sha256=None):
    result={'schema':1,'version':VERSION,'upstream_commit':UPSTREAM,'npm_tar_sha256':TARBALL,
            'source_hashes':source_hashes(launcher_sha256),'scope':'FINITE_LINUX_QUIET_START_PROCESS_FAMILIES'}
    if launcher_sha256==DIRECT_WRAPPER_SHA:
        result['entry_variant']='EXACT_RETAINED_DIRECT_DIST_ENTRY'
        result['launcher_sha256']=DIRECT_WRAPPER_SHA
    return result


def quiet_policy(value):
    quiet=value['quiet_bootstrap']
    return dict({key:copy.deepcopy(quiet[key]) for key in ('schema','selected_environment','config_projection',
        'package_absence','node_exec_argv','relay_environment')},package_root=value['package_root'])


def validate_quiet_startup(value):
    need(type(value) is dict and set(value)=={'schema','package_root','selected_environment','config_projection',
         'package_absence','node_exec_argv','relay_environment'} and type(value['schema']) is int and value['schema']==1,
         'QUIET_LIVE_POLICY_SCHEMA')
    root=value['package_root']
    need(type(root) is str and root.startswith('/home/xuanjun_dev/') and root.endswith('/lib/node_modules/openclaw') and
         re.fullmatch(r'/[A-Za-z0-9_./+@-]+',root) and '..' not in root.split('/') and '//' not in root,
         'QUIET_PACKAGE_ROOT')
    env=value['selected_environment'];config=value['config_projection']
    need(type(env) is dict and set(env)==set(ENV_KEYS) and all(env[key] is None for key in
         ('NODE_OPTIONS','BUN_OPTIONS','OPENCLAW_SERVICE_MARKER','OPENCLAW_CONTAINER','OPENCLAW_PROXY_URL','OPENCLAW_INCLUDE_ROOTS')),
         'QUIET_ENVIRONMENT_REQUIRED')
    need(env['HOME']=='/home/xuanjun_dev' and env['OPENCLAW_HOME'] in (None,'/home/xuanjun_dev') and
         env['OPENCLAW_STATE_DIR'] in (None,'/home/xuanjun_dev/.openclaw') and
         env['OPENCLAW_CONFIG_PATH'] in (None,'/home/xuanjun_dev/.openclaw/openclaw.json') and
         env['OPENCLAW_PROFILE'] in (None,'default') and env['OPENCLAW_LOAD_SHELL_ENV'] in (None,'','0','false','no','off'),
         'EXACT_EFFECTIVE_CONFIG_PATH_SELECTION')
    need(type(config) is dict and set(config)=={'env_shell_enabled','proxy_enabled','proxy_url_present','include_present'} and
         all(config[key] is None or config[key] is False for key in ('env_shell_enabled','proxy_enabled')) and
         config['proxy_url_present'] is False and config['include_present'] is False,'QUIET_CONFIG_REQUIRED')
    need(value['package_absence']=={name:'ABSENT' for name in ABSENT} and
         type(value['node_exec_argv']) is list and value['node_exec_argv']==[],'QUIET_ABSENCE_OR_EXEC_FLAGS')
    env=value['relay_environment']
    need(type(env) is dict and set(env)=={'HOME','PATH','LANG'} and env['HOME']=='/home/xuanjun_dev' and
         env['LANG']=='C.UTF-8' and type(env['PATH']) is str and 0<len(env['PATH'])<=4096,'QUIET_RELAY_ENVIRONMENT')
    return copy.deepcopy(value)


def check_inputs(compiled,facts,gateway_derivation):
    import epoch7_service_contract as sc
    from node_sqlite_probe import validate_node_sqlite_proof
    value=facts['openclaw_recipe_evidence']
    need(type(value) is dict and set(value)=={'schema','package_root','files','launcher','node',
         'quiet_bootstrap','node_probe'} and type(value['schema']) is int and value['schema']==1,'FACT_SCHEMA')
    root=value['package_root'];sc.live._path(root)
    need(root.startswith('/home/xuanjun_dev/') and root.endswith('/lib/node_modules/openclaw'),'FIXED_PACKAGE_SCOPE')
    launcher=value['launcher']
    need(type(launcher) is dict,'FIXED_LAUNCHER')
    direct=launcher.get('sha256')==DIRECT_WRAPPER_SHA
    pins=source_hashes(launcher.get('sha256'))
    files=value['files'];need(type(files) is dict and set(files)==set(pins),'EXACT_REVIEWED_FILE_SET')
    for name,pin in pins.items():
        row=files[name]
        need(type(row) is dict and set(row)=={'sha256','metadata'} and row['sha256']==pin,'INSTALLED_SOURCE_MATCH')
        meta=row['metadata']
        need(type(meta) is dict and set(meta)=={'kind','dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns'} and
             meta['kind']=='FILE' and meta['uid']==1002 and meta['nlink']==1 and
             all(type(meta[k]) is int and meta[k]>=0 for k in meta if k!='kind') and
             meta['ino']>0 and 0<meta['size']<=8388608 and not meta['mode']&0o7022,'SOURCE_FILE_AUTHORITY')
    recipe=launcher.get('recipe')
    fields={'path','sha256','recipe','entry_realpath'}
    if direct:fields.add('node_reference')
    need(set(launcher)==fields and
         launcher['path']==LAUNCHER,'FIXED_LAUNCHER')
    sc.d.hash_value(launcher['sha256'])
    need(type(recipe) is dict and set(recipe)=={'executable','entry_script','forwards_unit_arguments',
         'shebang','environment_names','source_execution'} and recipe['forwards_unit_arguments'] is True and
         recipe['source_execution']=='NOT_PERFORMED' and
         recipe['entry_script']==(DIRECT_ENTRY if direct else root+'/openclaw.mjs') and
         launcher['entry_realpath']==recipe['entry_script'] and recipe['shebang'] in
         ('#!/bin/bash','#!/usr/bin/bash','#!/bin/sh','#!/usr/bin/env bash'),'FIXED_EXEC_RECIPE')
    names=recipe['environment_names']
    need(type(names) is list and names==sorted(set(names)) and set(names)<={'HOME','PATH','LANG'},
         'WRAPPER_NO_EXTRA_NODE_FLAGS_OR_CACHE_EXPORTS')
    node=value['node'];native=gateway_derivation['native_identity']
    need(node['path']==native['exe'] and node['sha256']==native['sha256'] and
         node['path'].endswith('/node'),'NATIVE_EXECUTABLE_BINDING')
    if direct:
        from unit_metadata import validate_node_reference
        need(root==DIRECT_PACKAGE_ROOT and recipe['executable']==DIRECT_NODE_REFERENCE and
             recipe['shebang']=='#!/usr/bin/env bash' and names==[] and node['path']==DIRECT_NODE_PATH,
             'EXACT_DIRECT_ENTRY_RECIPE')
        reference=validate_node_reference(launcher['node_reference'],native['exe'],native['sha256'])
        final=reference['final']['metadata']
        need(node['metadata']=={key:final[key] for key in
             ('dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns')},
             'DIRECT_NODE_DESCRIPTOR_BINDING')
    else:
        need(node['path']==recipe['executable'],'NATIVE_EXECUTABLE_BINDING')
    probe=value['node_probe']
    need(type(probe) is dict and set(probe)=={'proof','policy_sha256','input_sha256'},'NODE_PROBE_ENVELOPE')
    result=validate_node_sqlite_proof(probe['proof'],node,probe['policy_sha256'],probe['input_sha256'])
    quiet=value['quiet_bootstrap']
    need(type(quiet) is dict and set(quiet)=={'schema','selected_environment','config_projection','source_bindings',
         'manager_sha256','package_absence','node_exec_argv','relay_environment'} and
         type(quiet['schema']) is int and quiet['schema']==1,'QUIET_MEASUREMENT_SCHEMA')
    env=quiet['selected_environment']
    need(type(env) is dict and set(env)==set(ENV_KEYS),'EXACT_SELECTED_ENVIRONMENT')
    need(all(env[key] is None for key in ('NODE_OPTIONS','BUN_OPTIONS','OPENCLAW_SERVICE_MARKER','OPENCLAW_CONTAINER',
         'OPENCLAW_PROXY_URL','OPENCLAW_INCLUDE_ROOTS')) and
         env['OPENCLAW_PROFILE'] in (None,'default') and
         env['OPENCLAW_LOAD_SHELL_ENV'] in (None,'','0','false','no','off'),'QUIET_ENVIRONMENT_REQUIRED')
    need(env['HOME']=='/home/xuanjun_dev' and env['OPENCLAW_HOME'] in (None,'/home/xuanjun_dev') and
         env['OPENCLAW_STATE_DIR'] in (None,'/home/xuanjun_dev/.openclaw') and
         env['OPENCLAW_CONFIG_PATH'] in (None,'/home/xuanjun_dev/.openclaw/openclaw.json'),
         'EXACT_EFFECTIVE_CONFIG_PATH_SELECTION')
    config=quiet['config_projection']
    need(type(config) is dict and set(config)=={'env_shell_enabled','proxy_enabled','proxy_url_present','include_present'} and
         all(config[key] is None or config[key] is False for key in ('env_shell_enabled','proxy_enabled')) and
         config['proxy_url_present'] is False and config['include_present'] is False,'QUIET_CONFIG_REQUIRED')
    need(quiet['node_exec_argv']==[] and type(quiet['node_exec_argv']) is list,'NO_NODE_PRELOAD_FLAGS')
    need(quiet['package_absence']=={name:'ABSENT' for name in ABSENT},'PACKAGE_ABSENCE_REQUIRED')
    sc.d.hash_value(quiet['manager_sha256'])
    bindings=quiet['source_bindings']
    need(type(bindings) is dict and 3<=len(bindings)<=16 and
         bindings.get(sc.UNIT_ROOT+GATEWAY)==gateway_derivation['unit_sha256'] and
         bindings.get(LAUNCHER)==launcher['sha256'],'QUIET_SOURCE_BINDINGS')
    for path,pin in bindings.items():sc.live._path(path);sc.d.hash_value(pin)
    relay=sc.decode(compiled['rendered_targets']['/etc/xuanjun-development/p2-gateway-relay.json'])
    need(quiet['relay_environment']=={'HOME':relay['gateway_home'],'PATH':relay['gateway_path'],'LANG':'C.UTF-8'} and
         relay['openclaw_bin']==LAUNCHER and relay['openclaw_sha256']==launcher['sha256'] and
         relay['openclaw_owner_uid']==1002,'EXACT_CLEAN_RELAY_ENVIRONMENT')
    need(type(relay['gateway_home']) is str and relay['gateway_home']=='/home/xuanjun_dev' and
         type(relay['gateway_path']) is str and len(relay['gateway_path'])<=4096,'RELAY_ENVIRONMENT_BOUND')
    sources={root+'/'+name:pin for name,pin in pins.items()}
    sources.update({LAUNCHER:launcher['sha256'],node['path']:node['sha256']})
    return value,sources,result


def derive_openclaw_families(compiled,facts,manifest,gateway_derivation,relay_main):
    import epoch7_service_contract as sc
    import epoch7_service_roles as sr
    value,common,probe_result=check_inputs(compiled,facts,gateway_derivation)
    node=value['node'];root=value['package_root'];recipe=value['launcher']['recipe'];meta=node['metadata']
    direct=value['launcher']['sha256']==DIRECT_WRAPPER_SHA
    dropin='/etc/systemd/system/'+GATEWAY+'.d/20-p2-docker.conf'
    dropin_raw=sc.raw_bytes(compiled['rendered_targets'][dropin])
    fields=sc.unit_sections(dropin_raw)['Service']
    need(fields=={'SupplementaryGroups':['docker xuanjun-ledger-client']},'EXACT_GATEWAY_SUPPLEMENTARY_GROUPS')
    uid,gid,groups,unused=sc._groups(facts['nss'],'xuanjun_dev','xuanjun_dev',('docker','xuanjun-ledger-client'))
    need(uid==1002,'GATEWAY_UID')
    identity={'uids':[uid]*4,'gids':[gid]*4,'groups':groups,'executable':node['path'],
              'executable_sha256':node['sha256']}
    def role(unit,name,ident,exe_meta,command,parent,main=False):
        return {'unit':unit,'name':name,'identity':copy.deepcopy(ident),
            'executable_dev':exe_meta['dev'],'executable_ino':exe_meta['ino'],
            'command':command,'parent':parent,'main':main,'maximum':1}
    def exact(argv):return {'mode':'EXACT_ARGV_SHA256','sha256':sr.argv_hash(argv)}
    def union(argv,titles):return dict(exact(argv),mode='EXACT_ARGV_OR_NUL_PADDED_TITLES',values=titles)
    unit_argv=gateway_derivation['launcher_argv'];args=unit_argv[1:]
    # The public unit parser already refuses dynamic shell syntax. This profile
    # additionally recognizes only the source's foreground Gateway invocation.
    need(args and args[0]=='gateway','FOREGROUND_GATEWAY_ARGV')
    rest=args[1:]
    if rest[:1]==['run']:rest=rest[1:]
    seen=set();index=0
    while index<len(rest):
        flag=rest[index];need(flag in ('--port','--bind','--allow-unconfigured','--verbose') and flag not in seen,
                             'FINITE_GATEWAY_ARGUMENTS');seen.add(flag);index+=1
        if flag in ('--port','--bind'):
            need(index<len(rest),'GATEWAY_FLAG_VALUE');item=rest[index];index+=1
            need(item=='loopback' if flag=='--bind' else type(item) is str and
                 re.fullmatch(r'[1-9][0-9]{0,4}',item) and int(item)<=65535,'GATEWAY_FLAG_VALUE')
    initial=[recipe['executable'],recipe['entry_script']]+args
    # resolveCompileCacheRespawnLauncher preserves the invoked lexical entry
    # only when its freshly checked realpath is the reviewed root module.
    child_launcher=recipe['entry_script'] if value['launcher']['entry_realpath']==root+'/openclaw.mjs' else root+'/openclaw.mjs'
    child=None if direct else [node['path']]+value['quiet_bootstrap']['node_exec_argv']+[child_launcher]+args
    main=role(GATEWAY,'main',identity,meta,union(initial,['openclaw','openclaw-gateway']),{'kind':'MANAGER','pid':1},True)
    cache=None if direct else role(GATEWAY,'compile_cache_child',identity,meta,
        union(child,['openclaw','openclaw-gateway']),{'kind':'ROLE','role':'main'})
    gateway_sources=dict(common);gateway_sources[sc.UNIT_ROOT+GATEWAY]=gateway_derivation['unit_sha256']
    gateway_sources[dropin]=sc.sha(dropin_raw)
    gateway_sources[sc.CONTROLLER]=sc.sha(sc.raw_bytes(compiled['rendered_targets'][sc.CONTROLLER]))
    quiet=validate_quiet_startup(quiet_policy(value))
    gateway={'sources':gateway_sources,'topology_source_sha256':SOURCE_HASHES['dist/entry.js' if direct else 'openclaw.mjs'],
             'roles':[main] if direct else [main,cache],
             'quiet_startup':copy.deepcopy(quiet)}
    release='/opt/xuanjun-control-releases/integration-'+compiled['manifest_sha256'][:16]
    ledger=sc.decode(compiled['rendered_targets'][sc.CONTROLLER])['ledger']
    python=sc._executable(facts,'/usr/bin/python3')
    bridge=release+'/stage1/native_ledger_bridge.py';client='/etc/xuanjun-development/p2-native-ledger-client.json'
    need(ledger['python']==python['path'] and ledger['pythonSha256']==python['sha256'] and
         ledger['bridge']==bridge and ledger['config']==client and
         ledger['files']=={bridge:manifest['files']['stage1/native_ledger_bridge.py'],
             client:sc.sha(sc.raw_bytes(compiled['rendered_targets'][client]))},'EXACT_NATIVE_BRIDGE_BINDING')
    launch_relative='plugins/p2-native-controller/ledger.mjs'
    launch_raw=sc.raw_bytes(facts['source_bytes'][launch_relative])
    need(sc.sha(launch_raw)==manifest['files'][launch_relative] and
         b"this.invoke(this.python,['-B',this.bridge,'--config',this.config]" in launch_raw,
         'EXACT_NATIVE_BRIDGE_LAUNCHER')
    bridge_ident=dict(identity,executable=python['path'],executable_sha256=python['sha256'])
    bridge_argv=[python['path'],'-B',bridge,'--config',client]
    gateway['roles'].extend([role(GATEWAY,name,bridge_ident,python,exact(bridge_argv),{'kind':'ROLE','role':parent})
        for name,parent in ((('bridge_main','main'),) if direct else
            (('bridge_main','main'),('bridge_child','compile_cache_child')))])
    gateway_sources.update({python['path']:python['sha256'],bridge:manifest['files']['stage1/native_ledger_bridge.py'],
        client:ledger['files'][client],release+'/'+launch_relative:sc.sha(launch_raw)})
    # Fixed readonly preflight CLI child; source hashes are checked before AST
    # shape claims, and the exact transport implementation is manifest-bound.
    relative='stage1/native_gateway_controller.py';raw=sc.raw_bytes(facts['source_bytes'][relative])
    need(sc.sha(raw)==manifest['files'][relative],'RELAY_TRANSPORT_SOURCE')
    need(b"self.executable, 'gateway', 'call', method" in raw and b"return self._call('preflight')" in raw and
         b"'PATH': self.config['gateway_path'], 'LANG': 'C.UTF-8'" in raw,'EXACT_RELAY_CALL_SOURCE')
    argv=[recipe['executable'],recipe['entry_script'],'gateway','call','xuanjun.execution.inspect','--params','{"operation":"preflight"}','--json']
    respawn=[node['path'],'--disable-warning=ExperimentalWarning']+argv[1:]
    py=sc._executable(facts,'/usr/bin/python3')
    relay_identity={k:relay_main[k] for k in ('uids','gids','groups','executable','executable_sha256')}
    relay_node=dict(identity,**{k:copy.deepcopy(relay_identity[k]) for k in ('uids','gids','groups')})
    need(relay_node['uids']==[1002]*4,'RELAY_GATEWAY_CREDENTIALS')
    relay_roles=[role(RELAY,'main',relay_identity,py,{'mode':'EXACT_ARGV_SHA256','sha256':relay_main['argv_sha256']},
                      {'kind':'MANAGER','pid':1},True),
        role(RELAY,'cli',relay_node,meta,exact(argv),{'kind':'ROLE','role':'main'}),
        role(RELAY,'cli_respawn',relay_node,meta,union(respawn,['openclaw']),{'kind':'ROLE','role':'cli'})]
    relay_sources=dict(common);relay_sources.update({sc.UNIT_ROOT+RELAY:sc.sha(sc.raw_bytes(compiled['rendered_targets'][sc.UNIT_ROOT+RELAY])),
        '/etc/xuanjun-development/p2-gateway-relay.json':sc.sha(sc.raw_bytes(compiled['rendered_targets']['/etc/xuanjun-development/p2-gateway-relay.json'])),
        release+'/'+relative:sc.sha(raw),py['path']:py['sha256']})
    relay_block={'sources':relay_sources,'topology_source_sha256':sc.sha(raw),'roles':relay_roles,
                 'quiet_startup':copy.deepcopy(quiet)}
    contract={'schema':1,'units':{GATEWAY:gateway,RELAY:relay_block}}
    sr.validate_contract(contract,sc.live.digest,sc.live._path,sc.live._role)
    selected_profile=profile(value['launcher']['sha256'])
    result={'contract':contract,'source_profile':selected_profile,'source_profile_sha256':sc.d.digest(selected_profile),
        'quiet_projection_sha256':sc.d.digest(value['quiet_bootstrap']),
        'probe_receipt_sha256':sc.d.digest(value['node_probe']['proof']),
        'gateway_argv':initial,'cache_child_argv':child,'relay_cli_argv':argv,'relay_respawn_argv':respawn,
        'detached_relay_child_requires_full_cgroup_containment':True,'node_probe_result':probe_result}
    if direct:result['node_reference']=copy.deepcopy(value['launcher']['node_reference'])
    return result
