"""Pure, fail-closed derivation of the finite epoch7 service observation contract.

No host calls, shell, imports of supplied source, process launch or admission.
The loader authenticates the private input bundle. This compiler checks its
internal bindings and reports what is genuinely derivable while the host is
stopped. Unknown /proc argv or cached manager state never becomes a wildcard.
The current stopped evidence cannot close nginx/OpenClaw process-title rules or
source-backed topology recipes; cached-unit ambiguity uses owned CAS/reload proof.
An incomplete result cannot feed the host factory.
"""
import ast
import base64
import copy
import hashlib
import json
import os.path
import re

import epoch7_delta as d
import epoch7_snapshot as snap
import epoch7_live_controls as live
from epoch7_recovery_sequence import PHASES

GATEWAY = 'xuanjun-uk-openclaw.service'
NGINX = 'nginx.service'
UNIT_ROOT = '/etc/systemd/system/'
OWNER = '/etc/xuanjun-development/p2-owner-process-identity.json'
CONTROLLER = '/etc/xuanjun-development/p2-native-controller.binding.json'
DIRECT = {
    'xj-root-broker.service': ('root_broker.py','root','root',('xuanjun-ledger-client',)),
    'xuanjun-ledger.service': ('ledger_service.py','xuanjun-dispatcher','xuanjun-control-db',('xuanjun-dispatcher',)),
    'xuanjun-p2-gateway-relay.service': ('p2_gateway_relay.py','xuanjun_dev','xuanjun_dev',()),
    'xuanjun-development-dispatcher.service': ('development_service.py','xuanjun-dispatcher','xuanjun-dispatcher',('xuanjun-ledger-client',)),
    'xuanjun-uk-owner-callback.service': ('owner_callback_server.py','xuanjun-callback','xuanjun-control-db',('xuanjun-ledger-client',)),
    'xuanjun-uk-owner-dashboard.service': ('owner_dashboard.py','xuanjun-callback','xuanjun-control-db',('xuanjun-ledger-client',)),
}
FACT_FIELDS = frozenset(('schema','unit_states','nss','executables','runtime_manifest_bytes',
                         'background_processes','source_bytes','boot_before','dropin_inventory','command_resolutions'))
MAX_SOURCE = 1048576
TOKEN = re.compile(r'[A-Za-z0-9_./:@=,+-]+')


def need(ok, code):
    if not ok: raise ValueError('EPOCH7_SERVICE_' + code)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def raw_bytes(value):
    if type(value) is str: value = value.encode('utf-8')
    need(type(value) is bytes and len(value) <= MAX_SOURCE, 'BOUNDED_SOURCE_BYTES')
    return value


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_JSON_KEY'); result[key] = value
        return result
    def constant(unused): raise ValueError('EPOCH7_SERVICE_NONFINITE_JSON')
    return json.loads(raw_bytes(raw).decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)


def unit_sections(raw):
    """Supported literal grammar only; not a replacement systemd parser."""
    text = raw_bytes(raw).decode('ascii')
    need('\0' not in text and '\\' not in text and '\r' not in text, 'UNIT_LITERAL_GRAMMAR')
    result, section = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('#',';')): continue
        if re.fullmatch(r'\[[A-Za-z]+\]',line):
            section = line[1:-1]; result.setdefault(section,{}); continue
        need(section is not None and '=' in line, 'UNIT_LINE')
        key, value = line.split('=',1)
        need(re.fullmatch(r'[A-Za-z][A-Za-z0-9]*',key) is not None, 'UNIT_KEY')
        result[section].setdefault(key,[]).append(value)
    return result


def literal_argv(value):
    need(type(value) is str and 0 < len(value) <= 16384, 'ARGV_BOUND')
    parts = value.split(' ')
    need(1 <= len(parts) <= 128 and all(TOKEN.fullmatch(x) for x in parts), 'ARGV_LITERAL_ONLY')
    need(parts[0].startswith('/') and os.path.normpath(parts[0]) == parts[0], 'ARGV_ABSOLUTE_EXECUTABLE')
    return parts


def cmdline_sha256(argv):
    need(type(argv) is list and 1 <= len(argv) <= 128 and all(type(x) is str and x and
         '\0' not in x for x in argv), 'ARGV_LIST')
    raw = b'\0'.join(x.encode('utf-8') for x in argv) + b'\0'
    need(len(raw) <= 1048576, 'CMDLINE_BOUND')
    return sha(raw)


def one(section,key,default=None):
    values = section.get(key)
    if values is None:
        need(default is not None, 'MISSING_LITERAL_' + key.upper()); return default
    need(len(values) == 1 and values[0] != '', 'DUPLICATE_OR_RESET_' + key.upper())
    return values[0]


def _groups(nss,user,group,supplements):
    need(type(nss) is dict and set(nss) == {'accounts','groups','initgroups'}, 'NSS_SCHEMA')
    account = nss['accounts'][user]; gid = nss['groups'][group]
    need(type(account) is dict and set(account) == {'uid','primary_gid','global_group_gids'}, 'ACCOUNT_SCHEMA')
    uid = account['uid']
    for value in (uid,gid,account['primary_gid']): live._integer(value)
    # This is getgrouplist(user, the Unit Group= gid), NOT the account's own
    # getgrouplist(user, passwd gid). Those can differ after a primary override.
    key = user + ':' + str(gid)
    actual = nss['initgroups'][key]
    need(type(actual) is list and actual == sorted(set(actual)) and gid in actual and
         len(actual) <= 128, 'UNIT_PRIMARY_INITGROUPS_REQUIRED')
    for value in actual: live._integer(value)
    groups = sorted(set(actual + [nss['groups'][name] for name in supplements]))
    for value in groups: live._integer(value)
    return uid,gid,groups,key


def _executable(facts,reference):
    pin = facts['executables'][reference]
    need(type(pin) is dict and set(pin) in ({'path','sha256','format'},{'path','sha256','format','dev','ino'}) and
         pin['format'] == 'ELF', 'MEASURED_ELF_REQUIRED')
    live._path(pin['path']); d.hash_value(pin['sha256'])
    return pin


def _role(facts,user,group,supplements,argv,unit):
    uid,gid,groups,key = _groups(facts['nss'],user,group,supplements)
    executable = _executable(facts,argv[0])
    result = {'uids':[uid]*4,'gids':[gid]*4,'groups':groups,
        'executable':executable['path'],'executable_sha256':executable['sha256'],
        'argv_sha256':cmdline_sha256(argv),'unit':unit}
    live._role(result)
    return result,key


def _fingerprint(value):
    if type(value) is bytes: return ['bytes',len(value),sha(value)]
    if type(value) is dict:
        need(all(type(k) is str for k in value),'STRING_INPUT_KEYS')
        return ['dict',[[k,_fingerprint(v)] for k,v in sorted(value.items())]]
    if type(value) in (list,tuple): return ['list',[_fingerprint(v) for v in value]]
    need(type(value) in (str,int,bool,type(None)), 'FINITE_INPUT_TYPES')
    return [type(value).__name__,value]


def compile_service_contract(compiled, identity_payloads, native_before,
                             retained_gateway_unit_bytes, fresh_facts, *, candidate_delta):
    """Return derived facts plus explicit HOLDs, never a guessed complete plan.

    Missing measured ingredients are reported together. Contradictory/malformed
    supplied inputs raise. require_complete_service_contract is the sole adapter
    that may hand unit_checkpoints/process_roles to a concrete factory.
    """
    need(type(fresh_facts) is dict and FACT_FIELDS<=set(fresh_facts)<=
         FACT_FIELDS|{'nginx_recipe_evidence','gateway_restoration','openclaw_recipe_evidence'} and
         type(fresh_facts['schema']) is int and fresh_facts['schema'] == 1, 'FACT_SCHEMA')
    need(type(compiled) is dict and compiled.get('kind') == 'PRIVATE_RETAINED_BINDINGS_NOT_INSTALL_PLAN'
         and compiled.get('install_admission') is False, 'COMPILED_BINDINGS')
    manifest_sha = compiled['manifest_sha256']; d.hash_value(manifest_sha)
    manifest_raw = raw_bytes(fresh_facts['runtime_manifest_bytes'])
    need(sha(manifest_raw) == manifest_sha, 'MANIFEST_BYTES_BINDING')
    manifest = decode(manifest_raw)
    need(type(manifest) is dict and type(manifest.get('files')) is dict, 'MANIFEST_SCHEMA')
    targets = {p:raw_bytes(v) for p,v in compiled['rendered_targets'].items()}
    rows = {r['target']:r for r in compiled['runtime']['provisioning']}
    need(set(rows) == set(targets) and all(rows[p]['rendered_sha256'] == sha(raw)
         for p,raw in targets.items()), 'RENDERED_TARGET_BINDING')
    need(type(identity_payloads) is dict and len(identity_payloads) <= 2, 'IDENTITY_PAYLOADS')
    need(type(fresh_facts['source_bytes']) is dict and len(fresh_facts['source_bytes']) <= 128,
         'SOURCE_SET_BOUND')
    for name,raw in fresh_facts['source_bytes'].items():
        need(name in manifest['files'] and sha(raw_bytes(raw)) == manifest['files'][name], 'SOURCE_MANIFEST_PIN')
    release = '/opt/xuanjun-control-releases/integration-' + manifest_sha[:16]
    problems,derivations,main_roles,roles = [],{},{},[]
    def missing(code,unit=None,fields=None):
        row = {'code':code,'unit':unit,'fields':sorted(fields or [])}
        if row not in problems: problems.append(row)
    states = fresh_facts['unit_states']
    need(type(states) is dict and set(states) == snap.WRITER_UNITS, 'EXACT_BASELINE_UNITS')
    baseline = {}
    for unit,state in states.items():
        need(type(state) is dict and live.STATIC_UNIT_FIELDS <= set(state) <= live.UNIT_FIELDS | {'FragmentPath','DropInPaths'},
             'BASELINE_UNIT_FIELDS')
        props = {k:state[k] for k in live.STATIC_UNIT_FIELDS}
        need(props['Id'] == unit and props['ActiveState'] in ('inactive','failed') and
             props['LoadState'] in ('loaded','masked') and props['NeedDaemonReload'] == 'no' and
             all(type(x) is str for x in props.values()), 'STOPPED_BASELINE_REQUIRED')
        need(unit != snap.RUNNER or props['ConditionResult'] == 'no', 'RUNNER_BASELINE')
        pid_type=int if any(type(state.get(key)) is int for key in ('MainPID','ControlPID')) else str
        main_pid,control_pid=snap.validate_unit_process_fields(unit,state,pid_type=pid_type)
        need(main_pid==control_pid==0, 'BASELINE_LIVE_PROCESS')
        baseline[unit] = {'properties':props,'main_required':False,'main_role_sha256':None}
    # systemd239 Accept=no uses listening before activation, then running while
    # the exact related service runs. Prove the finite association from rendered
    # source; a different Service/Accept/listener cannot borrow this lifecycle.
    need({path[len(UNIT_ROOT):] for path in targets if path.startswith(UNIT_ROOT) and
          path.endswith('.socket')} == set(live.SOCKET_SERVICES), 'EXACT_SOCKET_UNIT_SET')
    for socket_unit,(service_unit,endpoint) in sorted(live.SOCKET_SERVICES.items()):
        section = unit_sections(targets[UNIT_ROOT+socket_unit]).get('Socket',{})
        need(one(section,'Accept','no') == 'no' and
             one(section,'Service',socket_unit[:-7]+'.service') == service_unit and
             one(section,'ListenStream') == endpoint and
             {name for name in section if name.startswith('Listen')} == {'ListenStream'},
             'EXACT_ACCEPT_NO_SOCKET_ASSOCIATION')
        inventory=fresh_facts['dropin_inventory'].get(socket_unit)
        roots={prefix+'/'+socket_unit+'.d' for prefix in ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')}
        closed=(type(inventory) is dict and set(inventory)==roots and
            all(type(row) is dict and row.get('present') in (True,False) and type(row.get('files')) is dict and
                row['files']=={} and row.get('state')!='UNKNOWN' for row in inventory.values()))
        if states[socket_unit].get('DropInPaths') != '' or not closed:
            missing('EFFECTIVE_UNIT_DROPIN_CLOSURE',socket_unit,['DropInPaths'])
        derivations[socket_unit]={'kind':'FIXED_ACCEPT_NO_SOCKET_LIFECYCLE',
            'unit_sha256':sha(targets[UNIT_ROOT+socket_unit]),'service':service_unit,'endpoint':endpoint,
            'preactivation_substate':'listening','active_service_substate':'running'}
    for unit,(script,user,group,supplements) in sorted(DIRECT.items()):
        path = UNIT_ROOT + unit; raw = targets[path]
        service = unit_sections(raw).get('Service',{})
        need(one(service,'Type') == 'simple' and one(service,'User') == user and
             one(service,'Group') == group, 'EXACT_DIRECT_SERVICE_IDENTITY')
        need(set(one(service,'SupplementaryGroups','NONE').split()) == (set(supplements) or {'NONE'}),
             'EXACT_UNIT_SUPPLEMENTARY_GROUPS')
        need(not set(service) & {'DynamicUser','PAMName','RootDirectory','RootImage','ExecSearchPath'},
             'UNSUPPORTED_EXECUTION_IDENTITY_DIRECTIVE')
        argv = literal_argv(one(service,'ExecStart'))
        need(argv[:2] == ['/usr/bin/python3',release+'/stage1/'+script], 'DIRECT_PYTHON_SCRIPT')
        script_sha = manifest['files'].get('stage1/'+script); d.hash_value(script_sha)
        dropins = states[unit].get('DropInPaths')
        inventory=fresh_facts['dropin_inventory'].get(unit)
        roots={prefix+'/'+unit+'.d' for prefix in ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')}
        closed=(type(inventory) is dict and set(inventory)==roots and
            all(type(row) is dict and row.get('present') in (True,False) and type(row.get('files')) is dict and
                row['files']=={} and row.get('state')!='UNKNOWN' for row in inventory.values()))
        if dropins is None or dropins != '' or not closed:
            missing('EFFECTIVE_UNIT_DROPIN_CLOSURE',unit,['DropInPaths']); continue
        try: role,group_key = _role(fresh_facts,user,group,supplements,argv,unit)
        except KeyError:
            missing('MEASURED_INTERPRETER_OR_UNIT_INITGROUPS',unit,
                    ['/usr/bin/python3',user,group]+list(supplements)); continue
        expected_uid = {'root':0,'xuanjun_dev':1002,'xuanjun-dispatcher':1003,'xuanjun-callback':1004}[user]
        need(role['uids'] == [expected_uid]*4, 'EXISTING_SERVICE_UID')
        roles.append(role); main_roles[unit] = live.digest(role)
        derivations[unit] = {'kind':'DIRECT_LITERAL_PYTHON','argv':argv,
            'unit_sha256':sha(raw),'script_sha256':script_sha,'initgroups_key':group_key,
            'main_role_sha256':live.digest(role)}
        if unit == 'xuanjun-uk-owner-callback.service':
            if OWNER not in identity_payloads: missing('OWNER_IDENTITY_PAYLOAD',unit,[OWNER])
            else:
                owner = decode(identity_payloads[OWNER])
                need(owner.get('argv') == argv and owner.get('python_exe') == role['executable'] and
                     owner.get('python_sha256') == role['executable_sha256'] and
                     owner.get('unit_file') == path and owner.get('unit_sha256') == sha(raw) and
                     owner.get('script') == argv[1] and owner.get('script_sha256') == script_sha and
                     owner.get('release_sha256') == manifest_sha and owner.get('callback_uid') == 1004,
                     'OWNER_POLICY_CONTRADICTION')
    # A raw launcher is evidence about invocation, not its final /proc title or
    # descendants. Preserve its pin and parsed argv without declaring a role.
    if retained_gateway_unit_bytes is None:
        missing('RETAINED_GATEWAY_UNIT_BYTES',GATEWAY)
    else:
        if type(retained_gateway_unit_bytes) is dict:
            parsed=retained_gateway_unit_bytes
            need(set(parsed)=={'path','sha256','public_service_fields'} and parsed['path']==UNIT_ROOT+GATEWAY,
                 'PARSED_GATEWAY_UNIT_FIELDS')
            d.hash_value(parsed['sha256']);fields=parsed['public_service_fields']
            need(type(fields) is dict and set(fields)<={'Type','User','Group','SupplementaryGroups','ExecStart'} and
                 type(fields.get('ExecStart')) is list and 1<=len(fields['ExecStart'])<=16 and
                 all(type(x) is list and len(x)<=128 and all(type(a) is str for a in x) for x in fields['ExecStart']),
                 'PARSED_GATEWAY_EXECSTART')
            commands=[x for x in fields['ExecStart'] if x]
            need(len(commands)==1 and fields['ExecStart'][-1]==commands[0],'PARSED_GATEWAY_COMMAND_RESET')
            gateway_argv=commands[0]
            need(literal_argv(' '.join(gateway_argv))==gateway_argv,'PARSED_GATEWAY_LITERAL_ARGV')
            for name in ('User','Group'):
                values=fields.get(name,[])
                need(type(values) is list and len(values)<=16 and all(type(x) is str and
                     (x=='' or re.fullmatch(r'[a-z_][a-z0-9_-]{0,63}',x)) for x in values),
                     'PARSED_GATEWAY_ACCOUNT_OCCURRENCES')
            users=fields.get('User',[]);groups=fields.get('Group',[])
            need(users and users[-1]=='xuanjun_dev' and (not groups or groups[-1] in ('','xuanjun_dev')),
                 'PARSED_GATEWAY_ACCOUNT')
            gateway_sha=parsed['sha256']
        else:
            gateway_raw = raw_bytes(retained_gateway_unit_bytes)
            gateway_service = unit_sections(gateway_raw).get('Service',{})
            gateway_argv = literal_argv(one(gateway_service,'ExecStart'))
            gateway_sha=sha(gateway_raw)
        need(gateway_argv[0]=='/home/xuanjun_dev/.openclaw/bin/openclaw','RETAINED_GATEWAY_LAUNCHER_SCOPE')
        derivations[GATEWAY] = {'kind':'LAUNCHER_ONLY_NOT_PROC_ROLE','unit_sha256':gateway_sha,
                                'launcher_argv':gateway_argv}
    if native_before is None: missing('RETAINED_NATIVE_IDENTITY_BYTES',GATEWAY)
    else:
        native = decode(native_before); gateway = native.get('gatewayIdentity')
        need(type(gateway) is dict and set(gateway) == {'user','exe','sha256','cgroup'} and
             gateway['user'] == 'xuanjun_dev' and gateway['cgroup'] == '/system.slice/'+GATEWAY,
             'NATIVE_GATEWAY_IDENTITY')
        live._path(gateway['exe']); d.hash_value(gateway['sha256'])
        derivations.setdefault(GATEWAY,{}).update(native_identity=copy.deepcopy(gateway),
                                                 native_binding_sha256=sha(raw_bytes(native_before)))
    nginx_raw = targets[UNIT_ROOT+NGINX]; nginx = unit_sections(nginx_raw).get('Service',{})
    need(one(nginx,'Type') == 'forking', 'NGINX_FORKING_CONTRACT')
    derivations[NGINX] = {'kind':'FORKING_LAUNCHER_NOT_PROC_ROLE','unit_sha256':sha(nginx_raw),
                         'launcher_argv':literal_argv(one(nginx,'ExecStart'))}
    # No broad same-UID roles. Only exact stable SSH identities in the supplied
    # fresh full census may be copied; they remain independent of service roles.
    background = fresh_facts['background_processes']
    need(type(background) is list and len(background) <= 128, 'BACKGROUND_BOUND')
    for row in background:
        need(type(row) is dict and set(row) == {'before','after'} and row['before'] == row['after'],
             'BACKGROUND_STABLE_IDENTITY')
        live._identity(row['before']); value = row['before']
        need(value['uids'] == [1002]*4 and value['executable'] == '/usr/bin/ssh' and value['unit'] is None,
             'BACKGROUND_EXACT_SSH_ONLY')
        roles.append({k:value[k] for k in live.ROLE_FIELDS})
    need(type(candidate_delta) is dict and candidate_delta.get('kind')=='OFFLINE_EPOCH7_DELTA_NOT_INSTALL_PLAN' and
         candidate_delta.get('runtime_manifest_sha256')==manifest_sha and type(candidate_delta.get('changes')) is list,
         'VALIDATED_CANDIDATE_DELTA_REQUIRED')
    changes={row['path']:row for row in candidate_delta['changes']}
    need(len(changes)==len(candidate_delta['changes']) and set(changes)==set(targets),'EXACT_DELTA_TARGETS')
    for path,row in changes.items():
        need(set(row)=={'path','operation','before','after'} and
             row['operation'] in ('RETAIN','REPLACE_EXACT_FILE','REPLACE_EXACT_OWNER_MASK'),'DELTA_OPERATION')
        proposal={'kind':'FILE','sha256':sha(targets[path]),'uid':rows[path]['owner_uid'],
                  'gid':rows[path]['group_gid'],'mode':rows[path]['mode']}
        need(row['after']==proposal,'DELTA_TARGET_PROPOSAL')
        if row['operation']=='REPLACE_EXACT_OWNER_MASK':
            need(path in d.OWNER_MASKS and row['before'].get('kind')=='MASK','DELTA_EXACT_OWNER_MASK')
        else:
            need(row['before'].get('kind')=='FILE' and
                 (row['before'].get('sha256')==proposal['sha256']) is (row['operation']=='RETAIN'),
                 'DELTA_RETAIN_OR_REPLACE_BINDING')
    # Exact own target-CAS + reload evidence resolves manager-cache ambiguity.
    # No future inode/timestamp, process title or manager property is invented.
    from epoch7_unit_transitions import affected_unit
    unit_targets={p:{'uid':rows[p]['owner_uid'],'gid':rows[p]['group_gid'],'mode':rows[p]['mode']}
                  for p in targets if p.startswith(UNIT_ROOT) and changes[p]['operation']!='RETAIN'}
    for path,pin in unit_targets.items():pin['sha256']=sha(targets[path])
    affected={affected_unit(path) for path in unit_targets}
    boot=fresh_facts['boot_before']
    boot_units=set(compiled['runtime']['services'])|{GATEWAY,NGINX,live.DEFERRED_TIMER}
    need(type(boot) is dict and set(boot)==boot_units and all(v in ('enabled','disabled') for v in boot.values()),
         'EXACT_RESTORED_BOOT_BASELINE')
    transitions={'schema':1,'targets':unit_targets,'units':{}}
    for unit in sorted(affected):
        before=copy.deepcopy(baseline[unit]['properties']);after=copy.deepcopy(before)
        after.update(LoadState='loaded',UnitFileState=boot.get(unit,'static'),NeedDaemonReload='no')
        transitions['units'][unit]={'before':before,'reloaded':after}
    if 'gateway_restoration' in fresh_facts:
        restoration=copy.deepcopy(fresh_facts['gateway_restoration'])
        need(type(restoration) is dict and set(restoration)=={'path','sha256','uid','gid','mode','legacy_receipt_sha256'} and
             restoration['path']==UNIT_ROOT+GATEWAY and
             restoration['sha256']==derivations[GATEWAY]['unit_sha256'],'GATEWAY_RESTORE_SOURCE_BINDING')
        restoration.update(boot_before=fresh_facts['boot_before'][GATEWAY],before=copy.deepcopy(baseline[GATEWAY]['properties']))
        transitions['gateway_restoration']=restoration
    else:missing('GATEWAY_RESTORATION_SOURCE_EVIDENCE',GATEWAY,['original_unit_metadata','legacy_receipt_sha256'])
    derived=[copy.deepcopy(baseline) for unused in range(len(PHASES)+1)]
    for index in (len(PHASES)-1,len(PHASES)):
        required=live.REQUIRED_ACTIVE-{live.DEFERRED_TIMER} if index==len(PHASES)-1 else live.REQUIRED_ACTIVE
        for unit,policy in transitions['units'].items():
            derived[index][unit]['properties']=copy.deepcopy(policy['reloaded'])
        for unit in live.REQUIRED_ACTIVE:
            props=derived[index][unit]['properties']
            props.update(LoadState='loaded',UnitFileState='enabled',NeedDaemonReload='no')
            if unit in required:
                props.update(ActiveState='active',SubState=('waiting' if unit.endswith('.timer') else 'running'),ConditionResult='yes')
                if unit.endswith('.service'):
                    derived[index][unit].update(main_required=True,main_role_sha256=main_roles.get(unit))
        for unit in set(states)-live.REQUIRED_ACTIVE:
            derived[index][unit]['properties']['NeedDaemonReload']='no'
    # Known startup calls must not disappear from the review merely because
    # their lifetime is short. The current strict census may observe them.
    partial_scoped={'schema':1,'units':{}}
    relay_unit='xuanjun-p2-gateway-relay.service'
    relay_main=next((r for r in roles if r['unit']==relay_unit),None)
    try:
        from epoch7_openclaw_recipe import derive_openclaw_families
        if relay_main is None:raise KeyError('relay_main')
        recipe=derive_openclaw_families(compiled,fresh_facts,manifest,derivations[GATEWAY],relay_main)
        partial_scoped['units'].update(recipe['contract']['units'])
        derivations[GATEWAY]['startup_recipe']=recipe
        roles.remove(relay_main)
        for unit,block in recipe['contract']['units'].items():
            for point in derived:
                if point[unit]['main_required']:
                    point[unit]['main_role_sha256']=live.digest(block['roles'][0])
    except KeyError:
        missing('OPENCLAW_PINNED_SOURCE_TOPOLOGY_RECIPE',GATEWAY,
                ['exact_installed_source_profile','quiet_bootstrap_projection','reviewed_Node_SQLite_probe'])
        missing('RELAY_PREFLIGHT_OPENCLAW_CHILD_RECIPE',relay_unit,
                ['same_source_profile','exact_clean_environment','finite_preflight_ancestry'])
    try:
        from epoch7_nginx_recipe import derive_nginx_family
        nginx_recipe=derive_nginx_family(compiled,fresh_facts,manifest)
        block=nginx_recipe['block'];partial_scoped['units'][NGINX]=block
        derivations[NGINX].update(nginx_recipe)
        for point in derived:
            if point[NGINX]['main_required']:
                point[NGINX]['main_role_sha256']=live.digest(block['roles'][0])
        if not nginx_recipe['deployed_source_match']:
            missing('NGINX_DEPLOYED_SOURCE_MATCH',NGINX,['vendor_patch_review_or_isolated_exact_binary_evidence'])
    except KeyError:
        missing('NGINX_PINNED_SOURCE_TOPOLOGY_RECIPE',NGINX,
            ['measured_ELF_inode','nginx_nss','manager_credentials','online_cpu_count','mime_types','RPM_NEVRA','source_match'])
    dispatcher='xuanjun-development-dispatcher.service'
    main=next((r for r in roles if r['unit']==dispatcher),None)
    if main is not None:
        try:
            block=compile_dispatcher_git_family(compiled,fresh_facts,main,manifest)
            partial_scoped['units'][dispatcher]=block
            roles.remove(main)
            for point in derived:
                if point[dispatcher]['main_required']:
                    point[dispatcher]['main_role_sha256']=live.digest(block['roles'][0])
        except KeyError:
            missing('DISPATCHER_STARTUP_GIT_RESOLUTION',dispatcher,
                    ['pinned_startup_source','effective_nonsecret_PATH','resolved_git_executable_pin'])
    else:
        missing('DISPATCHER_STARTUP_GIT_RESOLUTION',dispatcher,
                ['direct_main_role','pinned_startup_source','effective_nonsecret_PATH','resolved_git_executable_pin'])
    if CONTROLLER in targets:
        ledger=decode(targets[CONTROLLER]).get('ledger',{})
        expected=release+'/stage1/native_ledger_bridge.py'
        need(ledger.get('bridge')==expected and ledger.get('config')=='/etc/xuanjun-development/p2-native-ledger-client.json',
             'BRIDGE_LITERAL_BINDING')
        live._path(ledger['python']);d.hash_value(ledger['pythonSha256'])
        argv=[ledger['python'],'-B',expected,'--config',ledger['config']]
        derivations.setdefault(GATEWAY,{})['bridge_launch']={'argv':argv,'argv_sha256':cmdline_sha256(argv),
            'python_sha256':ledger['pythonSha256'],'launcher_source_sha256':manifest['files']['plugins/p2-native-controller/ledger.mjs'],
            'parent_role':'SERVING_GATEWAY_MAIN_OR_CACHE_CHILD' if GATEWAY in partial_scoped['units'] else
                          'UNRESOLVED_GATEWAY_TOPOLOGY','admission':GATEWAY in partial_scoped['units']}
    # Jobs/CLI children are request-dependent, outside a finite quiet-start
    # role set. Unknown children are rejected by the unchanged live validator.
    child_limits = {u:'UNKNOWN_CHILD_FAILS_CLOSED' for u in (GATEWAY,NGINX,
        'xuanjun-development-dispatcher.service','xj-root-broker.service','xuanjun-p2-gateway-relay.service')}
    unique = {live.digest(r):r for r in roles}
    return {'schema':1,'kind':'OFFLINE_SERVICE_CONTRACT_DERIVATION','state':'HOLD' if problems else 'COMPLETE',
        'install_admission':False,'input_sha256':d.digest(_fingerprint([compiled,identity_payloads,native_before,
            retained_gateway_unit_bytes,fresh_facts,candidate_delta])),
        'unit_checkpoints':None if problems else derived,'derived_unit_checkpoints':derived,
        'process_roles':[unique[k] for k in sorted(unique)],'unit_transition_contract':transitions,
        'service_role_contract':None if problems else partial_scoped,'derived_service_role_contract':partial_scoped,'derivations':derivations,
        'unresolved':sorted(problems,key=lambda r:(r['unit'] or '',r['code'])),
        'child_policy':child_limits,'production_acceptance':'NOT_VERIFIED'}


def require_complete_service_contract(result):
    need(type(result) is dict and result.get('kind') == 'OFFLINE_SERVICE_CONTRACT_DERIVATION' and
         result.get('state') == 'COMPLETE' and result.get('unresolved') == [] and
         type(result.get('unit_checkpoints')) is list and len(result['unit_checkpoints']) == len(PHASES)+1,
         'UNRESOLVED_DERIVATION_HOLD')
    need(type(result.get('service_role_contract')) is dict, 'UNRESOLVED_SOURCE_RECIPE_HOLD')
    import epoch7_service_roles as scoped_roles
    extended=scoped_roles.validate_contract(result['service_role_contract'],live.digest,live._path,live._role)
    import epoch7_unit_transitions as unit_transitions
    unit_transitions.validate_contract(result['unit_transition_contract'],live.STATIC_UNIT_FIELDS,snap.WRITER_UNITS,d.hash_value)
    need(type(result['unit_transition_contract'].get('gateway_restoration')) is dict,'GATEWAY_RESTORE_POLICY_REQUIRED')
    # Recheck the structural policy, rather than accepting a renamed HOLD report.
    need(result['unit_checkpoints'] == result.get('derived_unit_checkpoints'), 'DERIVATION_CHECKPOINT_BINDING')
    for point in result['unit_checkpoints']:
        need(set(point) == snap.WRITER_UNITS,'EXACT_OUTPUT_UNITS')
        for policy in point.values():
            need(all(type(v) is str for v in policy['properties'].values()),'UNRESOLVED_OUTPUT_PROPERTIES')
            if policy['main_required']: d.hash_value(policy['main_role_sha256'])
    for role in result['process_roles']: live._role(role)
    known={live.digest(r):r for r in result['process_roles']}
    known.update(extended)
    for point in result['unit_checkpoints']:
        for unit,policy in point.items():
            if policy['main_required']:
                need(policy['main_role_sha256'] in known and known[policy['main_role_sha256']]['unit']==unit,
                     'MAIN_ROLE_SOURCE_BINDING')
    return {'unit_checkpoints':copy.deepcopy(result['unit_checkpoints']),
            'process_roles':copy.deepcopy(result['process_roles']),
            'service_role_contract':copy.deepcopy(result['service_role_contract']),
            'unit_transition_contract':copy.deepcopy(result['unit_transition_contract'])}


def service_facts_from_observation(observation, runtime_manifest_bytes, boot_before,
                                   background_processes=None, source_bytes=None):
    """Adapt one collector bundle to compiler ingredients; no manual role hashes.

    The bundle is still UNREVIEWED. The caller authenticates it and includes its
    digest in the independent plan review. Missing measured sections stay absent
    and become compiler HOLDs; no process title or unit property is invented.
    """
    need(type(observation) is dict and type(observation.get('unit_metadata')) is dict,
         'UNIT_METADATA_BUNDLE_REQUIRED')
    metadata=observation['unit_metadata']
    need(d.digest(metadata)==observation.get('unit_metadata_sha256'),'UNIT_METADATA_DIGEST')
    process_evidence=observation['evidence']['writers']['processes']
    measured_background=process_evidence.get('background_processes')
    need(type(measured_background) is list and len(measured_background)<=128 and
         d.digest(measured_background)==process_evidence.get('background_processes_sha256'),
         'MEASURED_BACKGROUND_PROJECTION_REQUIRED')
    need(background_processes is None or background_processes==measured_background,
         'BACKGROUND_PROJECTION_CONTRADICTION')
    sections=metadata['sections']
    need(type(sections) is dict and len(sections)<=32,'METADATA_SECTION_BOUND')
    def evidence(name):
        row=sections.get(name,{})
        return row.get('evidence') if type(row.get('evidence')) is dict else {}
    nss=evidence('unit_nss');initgroups={}
    for user,values in nss.get('nss_by_primary',{}).items():
        for gid,groups in values.items():
            need(type(gid) is str and re.fullmatch(r'0|[1-9][0-9]*',gid),'NSS_PRIMARY_GID_TEXT')
            initgroups[user+':'+gid]=copy.deepcopy(groups)
    executables={}
    for name,reference in (('python_reference','/usr/bin/python3'),('nginx_binary','/usr/sbin/nginx')):
        data=evidence(name)
        final=data.get('final',data)
        if all(key in final for key in ('path','sha256','format')):
            pin={key:final[key] for key in ('path','sha256','format')}
            if all(key in final.get('metadata',{}) for key in ('dev','ino')):
                pin.update({key:final['metadata'][key] for key in ('dev','ino')})
            executables[reference]=pin
    states={u:copy.deepcopy(row['state']) for u,row in observation['evidence']['writers']['units'].items()}
    legacy=evidence('legacy_gateway')
    gateway=({'path':UNIT_ROOT+GATEWAY,'sha256':legacy['backup_sha256'],'public_service_fields':copy.deepcopy(legacy['public_service_fields'])}
             if all(k in legacy for k in ('backup_sha256','public_service_fields')) else None)
    resolutions={};resolution=evidence('command_resolutions')
    if resolution:
        unit='xuanjun-development-dispatcher.service';proof=resolution.get('provenance')
        need(resolution.get('unit')==unit and resolution.get('collector_path_used') is False and
             type(proof) is dict and proof.get('source')=='SYSTEM_MANAGER_CHILD_ENVIRONMENT' and
             proof.get('manager_sha256')==d.digest(observation['evidence']['writers']['manager']) and
             proof.get('dropins_sha256')==d.digest(evidence('dropins')['units'][unit]),
             'MANAGER_CHILD_PATH_PROVENANCE')
        d.hash_value(proof['systemctl_sha256']);d.hash_value(proof['unit_sha256'])
        resolutions[unit]=copy.deepcopy(resolution['resolution'])
        candidates=[row['git'] for row in resolution['resolution']['entries'] if row['git'] is not None]
        if candidates:executables['git']=dict(candidates[0],format='ELF')
    facts={'schema':1,'unit_states':states,
        'nss':{'accounts':copy.deepcopy(nss.get('accounts',{})),
               'groups':copy.deepcopy(nss.get('named_groups',{})),'initgroups':initgroups},
        'executables':executables,'runtime_manifest_bytes':raw_bytes(runtime_manifest_bytes),
        'background_processes':copy.deepcopy(measured_background),
        'source_bytes':copy.deepcopy(source_bytes or {}),'boot_before':copy.deepcopy(boot_before),
        'dropin_inventory':copy.deepcopy(evidence('dropins').get('units',{})),
        'command_resolutions':resolutions}
    original=legacy.get('original_unit')
    if original is not None:
        need(type(original) is dict and set(original)=={'path','sha256','uid','gid','mode'} and
             original['path']==UNIT_ROOT+GATEWAY and original['sha256']==legacy['backup_sha256'],
             'LEGACY_RESTORE_PUBLIC_PROJECTION')
        facts['gateway_restoration']=dict(copy.deepcopy(original),legacy_receipt_sha256=legacy['journal_sha256'])
    source_review=observation.get('source_review_inputs')
    if source_review is not None:
        need(type(source_review) is dict and d.digest(source_review)==observation.get('source_review_inputs_sha256'),
             'SOURCE_REVIEW_INPUT_DIGEST')
        row=source_review.get('sections',{}).get('nginx_mime_types',{})
        if row.get('state')=='MEASURED_UNREVIEWED':
            mime=row['evidence'];encoded=mime['private_content_base64']
            need(type(encoded) is str and len(encoded)<=131072,'MIME_BASE64_BOUND')
            raw=base64.b64decode(encoded.encode('ascii'),validate=True)
            need(len(raw)<=65536 and sha(raw)==mime['sha256'],'MIME_SOURCE_BYTES_BINDING')
            manager=observation['evidence']['writers']['manager']
            cpus=evidence('online_cpus')
            rpm=observation['evidence']['retained']['prerequisites'].get('rpm_nevra',{})
            if all(k in manager for k in ('uids','gids','groups')) and 'online_count' in cpus and 'nginx' in rpm:
                facts['nginx_recipe_evidence']={'schema':1,'online_cpu_count':cpus['online_count'],
                    'manager_credentials':{k:copy.deepcopy(manager[k]) for k in ('uids','gids','groups')},
                    'mime_types':{'path':mime['path'],'sha256':mime['sha256'],'raw':raw},
                    'rpm_nevra':copy.deepcopy(rpm['nginx']),'source_match':None}
    if 'openclaw_profile' in observation:
        from openclaw_metadata import recipe_from_observation
        recipe=recipe_from_observation(observation)
        if recipe is not None:facts['openclaw_recipe_evidence']=recipe
    return {'fresh_facts':facts,
        'retained_gateway_unit':gateway,
        'measurement_sha256':observation['unit_metadata_sha256'],
        'unsupported_sections':copy.deepcopy(metadata.get('unsupported_sections',[]))}


def compile_dispatcher_git_family(compiled,facts,main_role,manifest):
    """One exact read-only startup child, derived from pinned Python AST.

    Missing source/search facts raise KeyError for the aggregate missing list.
    No subprocess is run and no Git/model/network operation is performed.
    """
    unit='xuanjun-development-dispatcher.service'
    relative='stage1/development_service.py';source=raw_bytes(facts['source_bytes'][relative])
    need(sha(source)==manifest['files'][relative],'STARTUP_SOURCE_PIN')
    tree=ast.parse(source.decode('utf-8'))
    functions=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='load_config']
    need(len(functions)==1,'STARTUP_LOAD_CONFIG_FUNCTION')
    argv=['git','-c','core.hooksPath=/dev/null','rev-parse','HEAD']
    calls=[node for node in ast.walk(functions[0]) if isinstance(node,ast.Call) and
           isinstance(node.func,ast.Name) and node.func.id=='runner']
    need(len(calls)==1 and calls[0].args and isinstance(calls[0].args[0],ast.List) and
         all(isinstance(x,ast.Str) for x in calls[0].args[0].elts) and
         [x.s for x in calls[0].args[0].elts]==argv and
         {x.arg for x in calls[0].keywords}=={'cwd','stdout','stderr','timeout','check'},'EXACT_STARTUP_GIT_AST')
    git=_executable(facts,'git');python=_executable(facts,'/usr/bin/python3')
    need(git['path']=='/usr/bin/git','STARTUP_GIT_CANONICAL_PATH')
    for pin in (git,python):live._integer(pin['dev']);live._integer(pin['ino'],1)
    resolution=facts['command_resolutions'][unit]
    need(type(resolution) is dict and set(resolution)=={'command','path_environment','entries'} and
         resolution['command']=='git','STARTUP_EXEC_RESOLUTION_SCHEMA')
    paths=resolution['path_environment'].split(':')
    need(1<=len(paths)<=32 and len(paths)==len(set(paths)) and len(resolution['entries'])==len(paths),
         'STARTUP_SEARCH_BOUND')
    first=None
    for directory,row in zip(paths,resolution['entries']):
        live._path(directory)
        need(type(row) is dict and set(row)=={'directory','uid','gid','mode','dev','ino','git'} and
             row['directory']==directory and row['uid']==0 and type(row['mode']) is int and
             not row['mode']&0o022,'STARTUP_PROTECTED_SEARCH_DIRECTORY')
        for key in ('uid','gid','mode','dev','ino'):live._integer(row[key],1 if key=='ino' else 0)
        if row['git'] is not None:
            candidate=row['git']
            need(type(candidate) is dict and set(candidate)=={'path','sha256','dev','ino'} and
                 candidate['path']==directory+'/git','STARTUP_SEARCH_ENTRY')
            d.hash_value(candidate['sha256']);live._integer(candidate['dev']);live._integer(candidate['ino'],1)
            if first is None:first=candidate
    need(type(first) is dict and first=={k:git[k] for k in ('path','sha256','dev','ino')},
         'STARTUP_FIRST_EXECUTABLE_BINDING')
    release='/opt/xuanjun-control-releases/integration-'+compiled['manifest_sha256'][:16]
    unit_path=UNIT_ROOT+unit;config='/etc/xuanjun-development/dispatcher.json'
    unit_raw=raw_bytes(compiled['rendered_targets'][unit_path])
    service=unit_sections(unit_raw)['Service']
    need(one(service,'Type')=='simple' and not set(service)&{'Environment','EnvironmentFile',
         'PassEnvironment','UnsetEnvironment','PAMName'},'STARTUP_DIRECT_MANAGER_LAUNCH')
    sources={unit_path:sha(unit_raw),release+'/'+relative:sha(source),git['path']:git['sha256'],
             python['path']:python['sha256'],config:sha(raw_bytes(compiled['rendered_targets'][config]))}
    identity={k:main_role[k] for k in ('uids','gids','groups','executable','executable_sha256')}
    main={'unit':unit,'name':'main','identity':identity,'executable_dev':python['dev'],
          'executable_ino':python['ino'],'command':{'mode':'EXACT_ARGV_SHA256','sha256':main_role['argv_sha256']},
          'parent':{'kind':'MANAGER','pid':1},'maximum':1,'main':True}
    child=copy.deepcopy(main);child.update(name='startup_git',main=False,
        executable_dev=git['dev'],executable_ino=git['ino'],parent={'kind':'ROLE','role':'main'},
        command={'mode':'EXACT_ARGV_SHA256','sha256':cmdline_sha256(argv)})
    child['identity'].update(executable=git['path'],executable_sha256=git['sha256'])
    block={'sources':sources,'topology_source_sha256':sha(unit_raw),'roles':[main,child]}
    import epoch7_service_roles as scoped
    scoped.validate_contract({'schema':1,'units':{unit:block}},live.digest,live._path,live._role)
    return block
