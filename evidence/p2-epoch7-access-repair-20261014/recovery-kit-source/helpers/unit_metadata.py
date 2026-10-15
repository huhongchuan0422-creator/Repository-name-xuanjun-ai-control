"""Finite read-only unit facts; public parsed fields/digests only, no admission."""
import re
import shlex
import copy

import epoch7_snapshot as c
import epoch7_delta as d
import epoch7_python_identity as python_identity
from probe_metadata import stable_read,protected,error_label,need,PROVISION

GATEWAY='xuanjun-uk-openclaw.service'
LAUNCHER='/home/xuanjun_dev/.openclaw/bin/openclaw'
NODE_TOOLS='/home/xuanjun_dev/.openclaw/tools'
NODE_ALIAS_PATH=NODE_TOOLS+'/node'
NODE_REFERENCE_PATH=NODE_ALIAS_PATH+'/bin/node'
NODE_VERSION_DIRECTORY=NODE_TOOLS+'/node-v24.21.0'
NODE_CANONICAL_PATH=NODE_VERSION_DIRECTORY+'/bin/node'
NODE_PACKAGE_ROOT=NODE_VERSION_DIRECTORY+'/lib/node_modules/openclaw'
NODE_REFERENCE_ANCESTORS=('/', '/home', '/home/xuanjun_dev', '/home/xuanjun_dev/.openclaw',
    NODE_TOOLS, NODE_VERSION_DIRECTORY, NODE_VERSION_DIRECTORY+'/bin')
NODE_MAXIMUM=268435456
DIRECT_DIST_WRAPPER=(
    '#!/usr/bin/env bash\nset -euo pipefail\nexec "'+NODE_REFERENCE_PATH+'" "'+
    NODE_PACKAGE_ROOT+'/dist/entry.js" "$@"\n').encode('ascii')
DIRECT_DIST_WRAPPER_SHA='b6aff1f40be0d46330c167e44525ef9080d66e40bb36dbb66c3811b4103fe3f2'
UNITS=(GATEWAY,'xuanjun-p2-gateway-relay.service','xuanjun-development-dispatcher.service',
       'xuanjun-ledger.service','xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service',
       'xj-root-broker.service','nginx.service')
NGINX_CONFIG='/etc/xuanjun-development/nginx-main.conf'
SAFE_FIELDS=('Type','User','Group','SupplementaryGroups')
NAME=re.compile(r'[a-z_][a-z0-9_-]*')
BOOT_ROOTS=('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system',
    '/run/systemd/system.control','/run/systemd/transient','/run/systemd/generator.early',
    '/run/systemd/generator','/run/systemd/generator.late')


def install_fields(raw):
    need(type(raw) is bytes and len(raw)<=65536,'INSTALL_TEXT_BOUND')
    result={key:[] for key in ('WantedBy','RequiredBy','Alias','Also')};section=None
    for line in raw.decode('utf-8','strict').splitlines():
        line=line.strip()
        if not line or line.startswith(('#',';')):continue
        if line.startswith('[') and line.endswith(']'):section=line[1:-1];continue
        if section!='Install':continue
        need('=' in line and not line.endswith('\\'),'INSTALL_LINE_UNSUPPORTED')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        need(key in result and all(re.fullmatch(r'[A-Za-z0-9_.@-]+\.(?:service|target|socket|timer)',x)
                                  for x in value.split()),'INSTALL_DIRECTIVE_UNSUPPORTED')
        result[key].append(value)
    return result


def path_override_evidence(raw):
    """Deliberately narrow subset of v239 unit syntax; no environment values returned."""
    need(type(raw) is bytes and len(raw)<=65536,'PATH_UNIT_BOUND');section=None;names=[]
    for line in raw.decode('utf-8','strict').splitlines():
        line=line.strip()
        if not line or line.startswith(('#',';')):continue
        if line.startswith('[') and line.endswith(']'):section=line[1:-1];continue
        if section!='Service':continue
        need('=' in line and not line.endswith('\\'),'PATH_UNIT_SYNTAX_UNSUPPORTED')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if key in ('PassEnvironment','EnvironmentFile','UnsetEnvironment','PAMName','RootDirectory','RootImage',
                   'BindPaths','BindReadOnlyPaths','ExecSearchPath'):
            need(not value,'PATH_UNIT_OVERRIDE_UNSUPPORTED')
        if key=='Environment':
            need(not any(ch in value for ch in '\\$`'),'PATH_UNIT_ENVIRONMENT_SYNTAX')
            for entry in shlex.split(value):
                name,sep,unused=entry.partition('=')
                need(sep and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name),'PATH_UNIT_ENVIRONMENT_SYNTAX')
                need(name!='PATH','PATH_UNIT_OVERRIDE_PRESENT');names.append(name)
    return {'environment_names':sorted(set(names)),'path_overrides':'PROVEN_ABSENT_IN_SUPPORTED_SYNTAX'}


def service_fields(raw, gateway=False):
    need(type(raw) is bytes and len(raw)<=65536,'UNIT_TEXT_BOUND')
    result={name:[] for name in SAFE_FIELDS};section=None;exec_rows=[]
    for line in raw.decode('utf-8','strict').splitlines():
        value=line.strip()
        if not value or value.startswith(('#',';')):continue
        need(not value.endswith('\\'),'UNIT_CONTINUATION_UNSUPPORTED')
        if value.startswith('[') and value.endswith(']'):section=value[1:-1];continue
        if section!='Service':continue
        need('=' in value,'UNIT_SERVICE_LINE')
        key,value=value.split('=',1);key=key.strip();value=value.strip()
        if key in SAFE_FIELDS:
            if key=='Type':need(value in ('','simple','exec','forking','notify','oneshot','dbus','idle'),'UNIT_TYPE')
            elif key=='SupplementaryGroups':need(all(NAME.fullmatch(x) for x in value.split()),'UNIT_GROUP_NAMES')
            else:need(not value or NAME.fullmatch(value),'UNIT_ACCOUNT_NAME')
            result[key].append(value)
        elif not gateway:
            need(False,'DROPIN_SERVICE_DIRECTIVE_UNSUPPORTED')
        elif key=='ExecStart' and gateway:
            need(not any(ch in value for ch in '$%\\`;&|<>\n'),'GATEWAY_EXEC_DYNAMIC')
            args=shlex.split(value)
            allowed={'gateway','run','--bind','loopback','--port','--allow-unconfigured','--verbose'}
            need(not args or args[0]==LAUNCHER and all(x in allowed or re.fullmatch(r'[0-9]{1,5}',x) for x in args[1:]),
                 'GATEWAY_EXEC_SCOPE')
            exec_rows.append(args)
    if gateway:
        need(exec_rows and exec_rows[-1] and len([x for x in exec_rows if x])==1,'GATEWAY_EXEC_REQUIRED')
        result['ExecStart']=exec_rows
    return result


def user_program(io,path,maximum=8388608):
    raw,row=stable_read(io,path,maximum)
    need(row.get('kind')=='FILE' and row.get('uid')==1002 and row.get('nlink')==1 and
         type(row.get('mode')) is int and not row['mode']&0o7022,'LAUNCHER_FILE_AUTHORITY')
    return raw,row


def _validate_node_reference(proof, expected_exe, expected_sha256, measurement_only=False):
    """Pure fixed directory-alias proof; caller supplies the retained native pin."""
    integers=('uid','gid','mode','dev','ino','nlink','size','mtime_ns','ctime_ns')
    attrs=('access_acl','default_acl','capability')
    def fields(value,names,label):need(type(value) is dict and set(value)==set(names),label)
    def meta(row,kind,extra=()):
        fields(row,integers+('kind',)+extra,'NODE_REFERENCE_METADATA_FIELDS')
        need(row['kind']==kind and all(type(row[k]) is int and 0<=row[k]<2**64 for k in integers) and
             row['dev']>0 and row['ino']>0 and row['nlink']>0 and row['mode']<=0o7777 and
             row['uid']<2**32 and row['gid']<2**32,'NODE_REFERENCE_TYPED_METADATA')
    d.hash_value(expected_sha256)
    need(expected_exe==NODE_CANONICAL_PATH,'NODE_REFERENCE_CANONICAL_SCOPE')
    extras=('admission','unsafe_ancestors') if measurement_only else ()
    fields(proof,('schema','kind','reference_path','link','final','ancestors','reread')+extras,'NODE_REFERENCE_FIELDS')
    kind='FIXED_NODE_DIRECTORY_ALIAS_MEASUREMENT' if measurement_only else 'FIXED_NODE_DIRECTORY_ALIAS'
    need(type(proof['schema']) is int and proof['schema']==1 and proof['kind']==kind and
         proof['reference_path']==NODE_REFERENCE_PATH and proof['reread']=='EXACT_PRE_POST','NODE_REFERENCE_SCOPE')
    link=proof['link'];fields(link,('path','target','metadata'),'NODE_REFERENCE_LINK_FIELDS')
    need(link['path']==NODE_ALIAS_PATH and link['target'] in ('node-v24.21.0',NODE_VERSION_DIRECTORY),
         'NODE_REFERENCE_EXACT_TARGET')
    meta(link['metadata'],'SYMLINK');row=link['metadata']
    need((row['uid'],row['gid']) in ((0,0),(1002,1002)) and (row['mode'],row['nlink'])==(0o777,1) and
         row['size']==len(link['target'].encode('ascii')),'NODE_REFERENCE_LINK_AUTHORITY')
    final=proof['final'];fields(final,('path','sha256','metadata'),'NODE_REFERENCE_FINAL_FIELDS')
    need(final['path']==expected_exe and final['sha256']==expected_sha256,'NODE_REFERENCE_RETAINED_HASH')
    meta(final['metadata'],'FILE',('sha256','elf_header')+attrs);row=final['metadata']
    need((row['uid'],row['gid'],row['nlink'])==(1002,1002,1) and row['mode']&0o100 and
         not row['mode']&0o7022 and 0<row['size']<=NODE_MAXIMUM and row['sha256']==expected_sha256 and
         row['elf_header'] is True and all(row[k] is False for k in attrs),'NODE_REFERENCE_ELF_AUTHORITY')
    fields(proof['ancestors'],NODE_REFERENCE_ANCESTORS,'NODE_REFERENCE_ANCESTOR_SET')
    unsafe=[]
    for path,row in proof['ancestors'].items():
        meta(row,'DIRECTORY',attrs)
        allowed=(0,) if path in ('/','/home') else (0,1002)
        narrowable=(measurement_only and path in (NODE_TOOLS,NODE_VERSION_DIRECTORY) and
                    (row['uid'],row['gid'],row['mode'])==(1002,1002,0o775))
        if narrowable:unsafe.append(path)
        need(row['uid'] in allowed and row['gid'] in (0,1002) and (not row['mode']&0o7022 or narrowable) and
             row['mode']&0o100 and (row['mode']&1 or row['uid']==1002 or row['gid']==1002 and row['mode']&0o10) and
             all(row[k] is False for k in attrs),'NODE_REFERENCE_ANCESTOR_AUTHORITY')
    if measurement_only:
        need(proof['admission']=='NOT_GRANTED' and proof['unsafe_ancestors']==sorted(unsafe),
             'NODE_REFERENCE_MEASUREMENT_ONLY')
    return copy.deepcopy(proof)


def validate_node_reference(proof, expected_exe, expected_sha256):
    return _validate_node_reference(proof,expected_exe,expected_sha256)


def validate_node_reference_measurement(proof, expected_exe, expected_sha256):
    """Pre-narrowing diagnostic only; its result cannot pass admission validation."""
    return _validate_node_reference(proof,expected_exe,expected_sha256,measurement_only=True)


def launcher_recipe(raw, expected_exe):
    need(type(raw) is bytes and 0<len(raw)<=65536,'LAUNCHER_SOURCE_BOUND')
    if raw==DIRECT_DIST_WRAPPER:
        need(len(raw)==188 and c.sha(raw)==DIRECT_DIST_WRAPPER_SHA and expected_exe==NODE_CANONICAL_PATH,
             'LAUNCHER_DIRECT_DIST_BINDING')
        return {'executable':NODE_REFERENCE_PATH,'entry_script':NODE_PACKAGE_ROOT+'/dist/entry.js',
            'forwards_unit_arguments':True,'shebang':'#!/usr/bin/env bash','environment_names':[],
            'source_execution':'NOT_PERFORMED'}
    lines=raw.decode('utf-8','strict').splitlines();need(lines and lines[0] in
        ('#!/bin/bash','#!/usr/bin/bash','#!/bin/sh','#!/usr/bin/env bash'),'LAUNCHER_SHEBANG_UNSUPPORTED')
    environment=[];recipe=None
    for line in lines[1:]:
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line in ('set -e','set -eu','set -euo pipefail','set -o pipefail'):continue
        if line.startswith('export '):
            assignment=line[len('export '):];name,separator,value=assignment.partition('=')
            need(separator and re.fullmatch(r'[A-Z_][A-Z0-9_]*',name) and
                 not any(ch in value for ch in '`;\n$&|<>()') and
                 len(shlex.split(line))==2,'LAUNCHER_EXPORT_UNSUPPORTED')
            environment.append(name);continue
        need(line.startswith('exec ') and recipe is None,'LAUNCHER_GRAMMAR_UNSUPPORTED')
        args=shlex.split(line)
        need(re.fullmatch(r'exec '+re.escape(expected_exe)+r' /[A-Za-z0-9_./+@-]+ \"\$@\"',line) and
             len(args)==4 and args[0]=='exec' and args[1]==expected_exe and args[3]=='$@',
             'LAUNCHER_FIXED_EXEC_UNSUPPORTED')
        entry=args[2];c.path(entry)
        need(entry.startswith('/home/xuanjun_dev/') and re.fullmatch(r'/[A-Za-z0-9_./+@-]+\.(?:js|mjs|cjs)',entry),
             'LAUNCHER_ENTRY_SCOPE')
        recipe={'executable':expected_exe,'entry_script':entry,'forwards_unit_arguments':True}
    need(recipe is not None,'LAUNCHER_FIXED_EXEC_MISSING')
    return dict(recipe,shebang=lines[0],environment_names=sorted(set(environment)),source_execution='NOT_PERFORMED')


def collect_unit_facts(io):
    sections={};dropin_observed={}
    def measure(name,fn):
        try:
            value=fn();sections[name]={'state':'MEASURED_UNREVIEWED','evidence':value};return value
        except (KeyboardInterrupt,SystemExit):raise
        except Exception as error:
            sections[name]={'state':'UNKNOWN','reason':error_label(error)};return None
    def nss():
        first=io.unit_nss();need(io.unit_nss()==first,'UNIT_NSS_CHANGED')
        need(type(first) is dict and set(first)=={'accounts','named_groups','nss_by_primary','unit_pairs','unsupported'} and
             all(type(first[k]) is dict for k in ('accounts','named_groups','nss_by_primary','unsupported')) and
             type(first['unit_pairs']) is list,'UNIT_NSS_SCHEMA')
        return first
    value=measure('unit_nss',nss)
    if value is not None and value['unsupported']:
        sections['unit_nss']['state']='UNKNOWN';sections['unit_nss']['reason']='NSS_PAIRS_OR_GROUPS_UNAVAILABLE'
    def python_reference():
        value=io.python_reference();final=value['final'];row=final['metadata']
        if final['path'] in python_identity.PYTHON_PATHS:
            need(final['path']==python_identity.PYTHON_PATHS[0] and
                 final['sha256']==python_identity.RETAINED_SHA256,'UNIT_EXACT_PYTHON_PAIR_BINDING')
            proof=python_identity.validate_pair_proof(row.get('python_identity'))
            need(row==dict(proof['sample']['files'][final['path']],python_identity=proof),
                 'UNIT_PYTHON_PAIR_METADATA_BINDING')
        else:need('python_identity' not in row and row.get('nlink')==1,'UNIT_UNSCOPED_PYTHON_PAIR_PROOF')
        return value
    measure('python_reference',python_reference)
    def native():
        raw,row=stable_read(io,c.NATIVE,65536);protected(row,65536)
        need(row['mode']==0o644,'UNIT_NATIVE_CURRENT_AUTHORITY')
        buffers=[]
        for path,maximum in ((c.NATIVE_PRIOR,65536),(c.NATIVE_ORIGINAL,65536),(c.NATIVE_ATTEMPT,1048576)):
            data,meta=stable_read(io,path,maximum);protected(meta,maximum)
            need(meta['mode']==0o600,'UNIT_NATIVE_RECEIPT_AUTHORITY');buffers.append(data)
        transition=c.validate_native_transition(raw,*buffers)
        fields=c.decode(raw)['gatewayIdentity']
        d.keys(fields,('user','exe','sha256','cgroup'),'UNIT_NATIVE_FIELDS')
        need(fields['user']=='xuanjun_dev' and fields['cgroup']=='/system.slice/'+GATEWAY,'UNIT_NATIVE_ROLE')
        c.path(fields['exe']);d.hash_value(fields['sha256'])
        return {'source_path':c.NATIVE,'source_sha256':c.sha(raw),'gateway_identity':fields,'native_binding_transition':transition,
                'executable_evidence':'retained.native_components.components[exe]'}
    native_value=measure('native_gateway',native)
    def backup():
        path=c.TRANSACTION+'/legacy-units.json';raw,row=stable_read(io,path,1048576);protected(row,1048576)
        need(row['mode']==0o600,'LEGACY_JOURNAL_AUTHORITY');receipt=c.decode(raw)
        need(receipt.get('schema')==1 and set(receipt.get('units',{}))=={GATEWAY,'xuanjun-uk-stage1-minimal.service'},'LEGACY_UNIT_SET')
        target=receipt['units'][GATEWAY];name=c.TRANSACTION+'/'+GATEWAY+'.backup'
        need(target['path']=='/etc/systemd/system/'+GATEWAY and target['backup']==name,'LEGACY_BACKUP_SCOPE')
        need(target['uid']==target['gid']==0 and type(target['mode']) is int and
             not target['mode']&0o7022,'LEGACY_ORIGINAL_UNIT_AUTHORITY')
        data,meta=stable_read(io,name,65536);protected(meta,65536)
        need(meta['mode']==0o600 and c.sha(data)==target['sha256'],'LEGACY_BACKUP_BINDING')
        result={'backup_path':name,'backup_sha256':c.sha(data),'journal_sha256':c.sha(raw),
                'metadata':meta,'raw_unit_returned':False,
                'original_unit':{k:target[k] for k in ('path','sha256','uid','gid','mode')}}
        try:result.update(public_service_fields=service_fields(data,gateway=True),
                          public_install_fields=install_fields(data),public_fields_state='PARSED_UNREVIEWED')
        except Exception as error:result.update(public_fields_state='UNKNOWN',reason=error_label(error))
        return result
    value=measure('legacy_gateway',backup)
    if value is not None and value['public_fields_state']=='UNKNOWN':
        sections['legacy_gateway'].update(state='UNKNOWN',reason=value['reason'])
    def launcher():
        raw,row=user_program(io,LAUNCHER,65536)
        result={'path':LAUNCHER,'sha256':c.sha(raw),'metadata':row,
                'raw_source_returned':False,'future_process_argv':'NOT_INFERRED'}
        try:
            need(native_value is not None,'LAUNCHER_NATIVE_PIN_UNAVAILABLE')
            recipe=launcher_recipe(raw,native_value['gateway_identity']['exe'])
            result['recipe']=recipe
            if recipe['executable']!=native_value['gateway_identity']['exe']:
                need(raw==DIRECT_DIST_WRAPPER,'LAUNCHER_DIRECTORY_ALIAS_SCOPE')
                result['node_reference']=validate_node_reference(io.node_directory_reference(
                    native_value['gateway_identity']['exe'],native_value['gateway_identity']['sha256']),
                    native_value['gateway_identity']['exe'],native_value['gateway_identity']['sha256'])
            entry,entry_meta=user_program(io,recipe['entry_script'])
            result['entry_script']={'path':recipe['entry_script'],'sha256':c.sha(entry),'metadata':entry_meta}
            result['recipe_state']='PARSED_UNREVIEWED'
        except Exception as error:result.update(recipe_state='UNKNOWN',reason=error_label(error))
        need(stable_read(io,LAUNCHER,65536)==(raw,row),'LAUNCHER_LATE_RACE')
        if 'node_reference' in result:
            need(io.node_directory_reference(native_value['gateway_identity']['exe'],
                 native_value['gateway_identity']['sha256'])==result['node_reference'],'LAUNCHER_NODE_ALIAS_LATE_RACE')
        return result
    value=measure('launcher',launcher)
    if value is not None and value['recipe_state']=='UNKNOWN':
        sections['launcher'].update(state='UNKNOWN',reason=value['reason'])
    def public_binary(path):
        proof=io.executable_reference(path)
        return dict(proof['final'],reference=proof)
    measure('nginx_binary',lambda:public_binary('/usr/sbin/nginx'))
    measure('runuser_binary',lambda:public_binary('/usr/sbin/runuser'))
    def nginx_config():
        receipt_raw,receipt_meta=stable_read(io,PROVISION,1048576);protected(receipt_meta,1048576)
        receipt=c.decode(receipt_raw);rows=receipt.get('targets',[])
        need(len(rows)==24 and {r['target'] for r in rows}==d.TARGETS,'NGINX_PROVISION_SCOPE')
        pin=next(r for r in rows if r['target']==NGINX_CONFIG)
        raw,row=stable_read(io,NGINX_CONFIG,65536);protected(row,65536)
        need(c.sha(raw)==pin['rendered_sha256'] and all(row[k]==pin[k] for k in ('uid','gid','mode')),'NGINX_RETAINED_CONFIG')
        declarations=re.findall(r'^\s*user\s+([a-z_][a-z0-9_-]*)(?:\s+([a-z_][a-z0-9_-]*))?\s*;',raw.decode(),re.M)
        need(declarations==[('nginx','')],'NGINX_EXACT_USER_DIRECTIVE')
        need(re.findall(r'^\s*worker_processes\s+([^;]+);',raw.decode(),re.M)==['auto'],'NGINX_WORKER_MODE')
        return {'path':NGINX_CONFIG,'sha256':c.sha(raw),'user':'nginx','explicit_group':None,
                'worker_processes':'auto','provision_sha256':c.sha(receipt_raw)}
    measure('nginx_config',nginx_config)
    def cpus():
        first=io.online_cpus();need(type(first) is int and 1<=first<=4096 and io.online_cpus()==first,'ONLINE_CPU_RACE')
        return {'online_count':first,'source':'sysconf_SC_NPROCESSORS_ONLN','future_worker_count':'BOUND_ONLY_NOT_INFERRED'}
    measure('online_cpus',cpus)
    def dropins():
        first=io.unit_dropins(UNITS);need(io.unit_dropins(UNITS)==first,'UNIT_DROPIN_INVENTORY_RACE')
        dropin_observed['raw']=first
        need(type(first) is dict and set(first)==set(UNITS),'UNIT_DROPIN_UNIT_SET')
        result={};unsupported=[]
        for unit,roots in first.items():
            expected={prefix+'/'+unit+'.d' for prefix in
                ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')}
            need(type(roots) is dict and set(roots)==expected,'UNIT_DROPIN_ROOT_SET')
            result[unit]={}
            for root,item in roots.items():
                need(type(item['files']) is dict and len(item['files'])<=16,'UNIT_DROPIN_FILE_BOUND')
                need(item['present'] is True or item['present'] is False or
                     item['present'] is None and item.get('state')=='UNKNOWN','UNIT_DROPIN_PRESENCE')
                need(item['present'] is True or not item['files'],'UNIT_DROPIN_ABSENCE_CONTENT')
                result[unit][root]={'present':item['present'],'files':{}}
                if item.get('state')=='UNKNOWN':
                    result[unit][root].update(state='UNKNOWN',reason=item['reason']);unsupported.append(root)
                for path,(raw,row) in item['files'].items():
                    try:
                        need(path.startswith(root+'/') and '/' not in path[len(root)+1:] and
                             re.fullmatch(r'[A-Za-z0-9_.-]+\.conf',path[len(root)+1:]),'UNIT_DROPIN_FILE_SCOPE')
                        protected(row,65536);need(row['sha256']==c.sha(raw) and row['size']==len(raw),'UNIT_DROPIN_DIGEST')
                        fields=service_fields(raw)
                        result[unit][root]['files'][path]={'sha256':c.sha(raw),'metadata':row,'public_service_fields':fields}
                    except Exception as error:
                        result[unit][root]['files'][path]={'sha256':c.sha(raw),'metadata':row,'state':'UNKNOWN','reason':error_label(error)}
                        unsupported.append(path)
        return {'units':result,'unsupported':sorted(unsupported),'raw_unit_bytes_returned':False}
    value=measure('dropins',dropins)
    if value is not None and value['unsupported']:
        sections['dropins']['state']='UNKNOWN';sections['dropins']['reason']='DROPIN_PUBLIC_FIELDS_UNSUPPORTED'
    def boot():
        value=io.boot_links()
        need(set(value['roots'])==set(BOOT_ROOTS) and set(value['units'])==
             {GATEWAY,'xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service'},'BOOT_COMPLETE_SCOPE')
        need(type(value['unsupported_roots']) is list and set(value['unsupported_roots'])<=set(BOOT_ROOTS),'BOOT_UNKNOWN_ROOT_SCOPE')
        return value
    value=measure('boot_links',boot)
    if value is not None and value['unsupported_roots']:
        sections['boot_links'].update(state='UNKNOWN',reason='BOOT_LINK_ROOTS_UNAVAILABLE')
    def resolution():
        unit='xuanjun-development-dispatcher.service';path='/etc/systemd/system/'+unit
        receipt_raw,receipt_meta=stable_read(io,PROVISION,1048576);protected(receipt_meta,1048576)
        rows=c.decode(receipt_raw).get('targets',[])
        need(len(rows)==24 and {r['target'] for r in rows}==d.TARGETS,'PATH_UNIT_PROVISION_SCOPE')
        pin=next(row for row in rows if row['target']==path)
        raw,meta=stable_read(io,path,65536);protected(meta,65536)
        need(c.sha(raw)==pin['rendered_sha256'] and all(meta[k]==pin[k] for k in ('uid','gid','mode')),'PATH_UNIT_RETAINED_PIN')
        public=path_override_evidence(raw)
        drop=sections['dropins'];need(drop['state']=='MEASURED_UNREVIEWED','PATH_DROPINS_UNAVAILABLE')
        # The only supported drop-in Service directives are the safe account/group/type fields.
        inventory=drop['evidence']['units'][unit]
        first=io.dispatcher_manager_path();need(io.dispatcher_manager_path()==first,'PATH_COMMAND_RESOLUTION_CHANGED')
        need(stable_read(io,path,65536)==(raw,meta) and stable_read(io,PROVISION,1048576)==(receipt_raw,receipt_meta),
             'PATH_UNIT_LATE_RACE')
        need(io.unit_dropins(UNITS)==dropin_observed['raw'],'PATH_UNIT_DROPIN_LATE_RACE')
        return {'unit':unit,'resolution':{k:first[k] for k in ('command','path_environment','entries')},
            'provenance':dict(first['provenance'],unit_sha256=c.sha(raw),dropins_sha256=d.digest(inventory),
                public_unit_environment=public),'collector_path_used':False}
    measure('command_resolutions',resolution)
    missing=sorted(name for name,row in sections.items() if row['state']=='UNKNOWN')
    def evidence(name):return sections[name].get('evidence',{})
    launcher=evidence('launcher');native=evidence('native_gateway').get('gateway_identity',{})
    gateway=evidence('legacy_gateway');nginx=evidence('nginx_binary');config=evidence('nginx_config')
    recipes={
        'openclaw':{'launcher_sha256':launcher.get('sha256'),
            'entry_script_path':launcher.get('entry_script',{}).get('path'),
            'entry_script_sha256':launcher.get('entry_script',{}).get('sha256'),
            'native_executable_path':native.get('exe'),'native_executable_sha256':native.get('sha256'),
            'unit_sha256':gateway.get('backup_sha256'),
            'literal_unit_argv':gateway.get('public_service_fields',{}).get('ExecStart'),
            'topology_state':'ISOLATED_STARTUP_VERIFICATION_REQUIRED',
            'missing_semantics':['final_process_title_literals','whether_entry_respawns_Node',
                'child_executable_and_argument_transformation','parent_wait_exit_and_reparenting',
                'maximum_startup_children','whether_child_detaches_or_changes_credentials']},
        'nginx':{'binary_path':nginx.get('path'),'binary_sha256':nginx.get('sha256'),
            'installed_version_and_build_provenance':{'state':'UNKNOWN','evidence_reference':'retained prerequisites RPM evidence if measured'},
            'main_config_sha256':config.get('sha256'),'literal_user':config.get('user'),
            'literal_worker_processes':config.get('worker_processes'),
            'online_cpu_count':evidence('online_cpus').get('online_count'),
            'topology_state':'OFFICIAL_MATCHING_SOURCE_REVIEW_REQUIRED',
            'missing_semantics':['ngx_daemon_parent_lifecycle','ngx_setproctitle_exact_format',
                'master_worker_creation_and_credentials']}}
    return {'schema':1,'kind':'PRIVATE_UNIT_FACTS_UNREVIEWED','state':'INCOMPLETE' if missing else 'COMPLETE_UNREVIEWED',
        'sections':sections,'unsupported_sections':missing,'independent_acceptance':'PENDING',
        'install_admission':'NOT_GRANTED','source_execution':'NOT_PERFORMED','future_argv_hashes':'NOT_INFERRED',
        'startup_recipes':recipes,'source_closure':'NOT_VERIFIED'}


def collect_source_review_inputs(io, unit_facts):
    """Private bounded source inputs. No launcher exports, environment or execution.

    Source bytes are an explicit private-review exception to digest-only metadata.
    Conservative literal scanning is not a JavaScript semantic proof.
    """
    import base64
    import os
    result={'schema':1,'kind':'PRIVATE_SOURCE_REVIEW_INPUTS_UNREVIEWED','sections':{},
        'source_execution':'NOT_PERFORMED','public_source_output':'FORBIDDEN',
        'source_closure':'NOT_VERIFIED','install_admission':'NOT_GRANTED'}
    def measure(name,fn):
        try:result['sections'][name]={'state':'MEASURED_UNREVIEWED','evidence':fn()}
        except (KeyboardInterrupt,SystemExit):raise
        except Exception as error:result['sections'][name]={'state':'UNKNOWN','reason':error_label(error)}
    def mime():
        path='/etc/nginx/mime.types';raw,row=stable_read(io,path,65536);protected(row,65536)
        text=raw.decode('ascii','strict');text=re.sub(r'#[^\n]*','',text)
        match=re.fullmatch(r'\s*types\s*\{([^{}]*)\}\s*',text);need(match is not None,'MIME_TYPES_BLOCK_REQUIRED')
        need(match.group(1).strip().endswith(';'),'MIME_TYPES_TERMINATOR_REQUIRED')
        mappings=[]
        for statement in match.group(1).split(';'):
            fields=statement.split()
            if not fields:continue
            need(len(fields)>=2 and re.fullmatch(r'[A-Za-z0-9.+_-]+/[A-Za-z0-9.+_-]+',fields[0]) and
                 all(re.fullmatch(r'[A-Za-z0-9.+_-]+',x) for x in fields[1:]),'MIME_TYPES_MAPPING_ONLY')
            mappings.append(fields)
        need(mappings and len(mappings)<=2048,'MIME_TYPES_MAPPING_BOUND')
        return {'path':path,'sha256':c.sha(raw),'metadata':row,'mappings':mappings,
                'private_content_base64':base64.b64encode(raw).decode('ascii')}
    measure('nginx_mime_types',mime)
    def openclaw():
        launcher=unit_facts['sections']['launcher'].get('evidence',{})
        recipe=launcher.get('recipe');need(type(recipe) is dict,'OPENCLAW_LITERAL_ENTRY_UNAVAILABLE')
        entry=recipe['entry_script'];directory=os.path.dirname(entry)
        candidates=(directory+'/package.json',os.path.dirname(directory)+'/package.json');packages=[];absent=[]
        for path in candidates:
            need(path.startswith('/home/xuanjun_dev/'),'OPENCLAW_PACKAGE_SCOPE')
            if io.absent(path):absent.append(path);continue
            raw,row=user_program(io,path,1048576);value=c.decode(raw)
            if value.get('name')!='openclaw':continue
            public={k:value[k] for k in ('name','version','bin','engines') if k in value}
            need(re.fullmatch(r'[0-9A-Za-z.+_-]{1,128}',value.get('version','')),'OPENCLAW_PACKAGE_VERSION')
            bins=value.get('bin',{});bins={'openclaw':bins} if type(bins) is str else bins
            need(type(bins) is dict and len(bins)<=4 and all(re.fullmatch(r'[A-Za-z0-9_-]{1,64}',k) and
                 type(v) is str and re.fullmatch(r'(?:\./)?[A-Za-z0-9_./+@-]{1,512}',v) and
                 not v.startswith('/') and '..' not in v.split('/') for k,v in bins.items()),'OPENCLAW_PACKAGE_BIN')
            engines=value.get('engines',{})
            need(type(engines) is dict and len(engines)<=8 and all(re.fullmatch(r'[A-Za-z0-9_-]{1,32}',k) and
                 type(v) is str and re.fullmatch(r'[A-Za-z0-9<>=~^|.* +_-]{1,128}',v) for k,v in engines.items()),
                 'OPENCLAW_PACKAGE_ENGINES')
            packages.append({'path':path,'sha256':c.sha(raw),'metadata':row,'public_fields':public})
        need(len(packages)==1,'OPENCLAW_EXACT_PACKAGE_REQUIRED');package=packages[0];root=os.path.dirname(package['path'])
        files={};pending=[(entry,0)];unresolved=[];total=package['metadata']['size']
        known={'state':'NOT_APPLICABLE'}
        package_public=package['public_fields'];bin_spec=package_public.get('bin',{})
        bin_spec={'openclaw':bin_spec} if type(bin_spec) is str else bin_spec
        exact_version=package_public['version']=='2026.9.9'
        exact_entry=bin_spec.get('openclaw') in ('openclaw.mjs','./openclaw.mjs') and (
            entry==root+'/openclaw.mjs' or launcher.get('sha256')==DIRECT_DIST_WRAPPER_SHA and
            entry==NODE_PACKAGE_ROOT+'/dist/entry.js' and root==NODE_PACKAGE_ROOT and
            recipe['executable']==NODE_REFERENCE_PATH and 'node_reference' in launcher)
        if exact_version:
            known={'state':'UNKNOWN','reason':'OPENCLAW_2026_9_9_BIN_OR_LITERAL_ENTRY_UNVERIFIED'}
        while pending:
            path,depth=pending.pop(0)
            if path in files:continue
            if depth>3 or len(files)>=16:
                unresolved.append({'path':path,'reason':'OPENCLAW_CLOSURE_COUNT_OR_DEPTH_BOUND'});continue
            c.path(path);need(path.startswith(root+'/') and 'node_modules' not in path[len(root)+1:].split('/'),
                              'OPENCLAW_LITERAL_IMPORT_ESCAPE')
            need(re.fullmatch(r'/[A-Za-z0-9_./+@-]+\.(?:js|mjs|cjs)',path),'OPENCLAW_LITERAL_IMPORT_TYPE')
            if total>=33554432:
                files[path]={'state':'UNKNOWN','reason':'OPENCLAW_TOTAL_SOURCE_BOUND'}
                unresolved.append({'path':path,'reason':'OPENCLAW_TOTAL_SOURCE_BOUND'});continue
            try:raw,row=user_program(io,path,min(8388608,33554432-total))
            except (KeyboardInterrupt,SystemExit):raise
            except Exception as error:
                files[path]={'state':'UNKNOWN','reason':error_label(error)}
                unresolved.append({'path':path,'reason':error_label(error)});continue
            total+=len(raw)
            text=raw.decode('utf-8','strict');need('\0' not in text,'OPENCLAW_SOURCE_TEXT')
            # Refuse private source publication when a literal credential assignment is apparent.
            secret=re.search(r'''(?i)(?:token|secret|password|api[_-]?key|credential)\s*[:=]\s*["'][^"'\n]{8,}["']''',text)
            item={'sha256':c.sha(raw),'metadata':row}
            if secret:
                item.update(state='UNKNOWN',reason='OPENCLAW_LITERAL_SECRET_PATTERN');files[path]=item
                unresolved.append({'path':path,'reason':'OPENCLAW_LITERAL_SECRET_PATTERN'});continue
            item['private_content_base64']=base64.b64encode(raw).decode('ascii');files[path]=item
            if path==entry and exact_version and exact_entry:
                edges=set(re.findall(r'''\btryImport\s*\(\s*["']\./dist/entry\.(js|mjs)["']\s*\)''',text))
                direct=(launcher.get('sha256')==DIRECT_DIST_WRAPPER_SHA and entry==NODE_PACKAGE_ROOT+'/dist/entry.js')
                if edges=={'js','mjs'} or direct:
                    known={'state':'MEASURED_DIRECT_ENTRY_UNREVIEWED' if direct else 'MEASURED_LITERAL_CANDIDATES_UNREVIEWED',
                           'entry_candidates':{},'build_info':{}}
                    for suffix in ('js','mjs'):
                        candidate=root+'/dist/entry.'+suffix
                        if io.absent(candidate):known['entry_candidates'][candidate]={'state':'ABSENT'}
                        else:
                            known['entry_candidates'][candidate]={'state':'PRESENT_PENDING_CAPTURE'}
                            pending.append((candidate,1))
                    if all(row['state']=='ABSENT' for row in known['entry_candidates'].values()):
                        unresolved.append({'path':entry,'reason':'OPENCLAW_2026_9_9_BOTH_ENTRIES_ABSENT'})
                    build_path=root+'/dist/build-info.json'
                    if io.absent(build_path):known['build_info']={'path':build_path,'state':'ABSENT'}
                    else:
                        try:
                            need(total<33554432,'OPENCLAW_TOTAL_SOURCE_BOUND')
                            build_raw,build_meta=user_program(io,build_path,min(65536,33554432-total));build=c.decode(build_raw)
                            total+=len(build_raw);need(total<=33554432,'OPENCLAW_TOTAL_SOURCE_BOUND')
                            public={k:build[k] for k in ('version','commit') if k in build}
                            need(public.get('version')=='2026.9.9' and type(public.get('commit')) is str and
                                 re.fullmatch(r'[0-9a-f]{40}',public['commit']),'OPENCLAW_BUILD_INFO_PUBLIC_FIELDS')
                            known['build_info']={'path':build_path,'state':'MEASURED_UNREVIEWED','sha256':c.sha(build_raw),
                                'metadata':build_meta,'public_fields':public}
                        except (KeyboardInterrupt,SystemExit):raise
                        except Exception as error:known['build_info']={'path':build_path,'state':'UNKNOWN','reason':error_label(error)}
            patterns=(r'''\b(?:import|export)\s+[^;\n]{0,4096}?\bfrom\s*["']([^"'\n]{1,512})["']''',
                r'''\bimport\s*["']([^"'\n]{1,512})["']''',
                r'''\b(?:import|require)\s*\(\s*["']([^"'\n]{1,512})["']\s*\)''')
            imports=set(target for pattern in patterns for target in re.findall(pattern,text))
            need(len(imports)<=256 and len(pending)<=256,'OPENCLAW_IMPORT_COUNT_BOUND')
            for target in sorted(imports):
                if not target.startswith('./') and not target.startswith('../'):
                    if not target.startswith('node:'):unresolved.append({'path':path,'reason':'OPENCLAW_EXTERNAL_DEPENDENCY_NOT_FOLLOWED'})
                    continue
                resolved=os.path.normpath(os.path.join(os.path.dirname(path),target))
                if not resolved.startswith(root+'/') or 'node_modules' in resolved[len(root)+1:].split('/'):
                    unresolved.append({'path':path,'reason':'OPENCLAW_LITERAL_IMPORT_ESCAPE'});continue
                if not re.fullmatch(r'/[A-Za-z0-9_./+@-]+\.(?:js|mjs|cjs)',resolved):
                    unresolved.append({'path':path,'reason':'OPENCLAW_LITERAL_IMPORT_TYPE'});continue
                pending.append((resolved,depth+1))
            if re.search(r'''\b(?:import|require)\s*\(\s*[^\s"']''',text):
                unresolved.append({'path':path,'reason':'OPENCLAW_COMPUTED_IMPORT_UNSUPPORTED'})
        need(stable_read(io,package['path'],1048576)[1]==package['metadata'],'OPENCLAW_PACKAGE_LATE_RACE')
        for path,item in files.items():
            if 'metadata' in item:
                need(stable_read(io,path,8388608)[1]==item['metadata'],'OPENCLAW_SOURCE_LATE_RACE')
        for path,row in known.get('entry_candidates',{}).items():
            if row['state']=='ABSENT':need(io.absent(path),'OPENCLAW_OPTIONAL_ENTRY_ABSENCE_RACE')
            else:row.update(state='CAPTURED_UNREVIEWED' if 'private_content_base64' in files.get(path,{}) else 'UNKNOWN',
                            evidence_reference='files['+path+']')
        build=known.get('build_info',{})
        if build.get('state')=='MEASURED_UNREVIEWED':
            need(stable_read(io,build['path'],65536)[1]==build['metadata'],'OPENCLAW_BUILD_INFO_LATE_RACE')
        elif build.get('state')=='ABSENT':need(io.absent(build['path']),'OPENCLAW_BUILD_INFO_ABSENCE_RACE')
        return {'launcher_sha256':launcher['sha256'],'entry_path':entry,'package':package,
            'package_candidates_absent':absent,'files':files,'source_bytes':total,'unresolved':unresolved,
            'known_2026_9_9_inputs':known,
            'literal_scan':'BOUNDED_NON_SEMANTIC','topology_state':'ISOLATED_STARTUP_VERIFICATION_REQUIRED',
            'source_closure':'NOT_VERIFIED','maximum_files':16,'maximum_depth':3,'maximum_total_bytes':33554432}
    measure('openclaw_literal_sources',openclaw)
    missing=sorted(name for name,row in result['sections'].items() if row['state']=='UNKNOWN')
    result.update(unsupported_sections=missing,state='INCOMPLETE' if missing else 'COMPLETE_UNREVIEWED')
    return result
