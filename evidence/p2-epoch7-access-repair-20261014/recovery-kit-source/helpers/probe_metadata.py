"""Read-only finite-probe ingredients. No policy approval, nonce or effects.

Only this module's fixed files, protected binding-declared SDK/Python paths and
an explicitly supplied protected staged public runtime are read. Components are
reported together, so unsupported fields do not require serial manual probes.
"""
import copy
import re

import epoch7_delta as d
import epoch7_snapshot as c
import epoch7_python_identity as python_identity

MACHINE_ID = '/etc/machine-id'
CONTROLLER = '/etc/xuanjun-development/p2-native-controller.binding.json'
PROVISION = c.TRANSACTION + '/epoch6-runtime-provisioning.json'
RUNTIME_MANIFEST = '26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa'
CANDIDATE_SOURCES = ('stage1/ledger_service.py', 'stage1/ledger_server_identity.py', 'stage1/activation_control.py')
INGREDIENT_FIELDS = frozenset(('hostname','machine_id_sha256','python','systemctl','profiles','sdk_bindings','manager'))
PYTHON = re.compile(r'/usr/(?:bin/python3(?:\.6)?|libexec/platform-python(?:3\.6)?)')
SDK_PREFIX = '/home/xuanjun_dev/.openclaw/tools/'
SDK_MAXIMUM = 8 * 1024 * 1024
PUBLIC_MAXIMUM = 32 * 1024 * 1024


def need(value, label):
    if not value: raise ValueError(label)


def error_label(error):
    if isinstance(error, PermissionError): return 'READ_PERMISSION_UNAVAILABLE'
    if isinstance(error, FileNotFoundError): return 'EXPECTED_PATH_MISSING'
    if isinstance(error, OSError): return 'READ_OR_METADATA_UNAVAILABLE'
    if isinstance(error, KeyError): return 'EXPECTED_FIELD_OR_NSS_RECORD_MISSING'
    value = str(error) if isinstance(error, ValueError) else ''
    return value if re.fullmatch(r'[A-Z0-9_]{1,128}', value) else 'INVALID_OR_UNSUPPORTED_EVIDENCE'


def protected(row, maximum=PUBLIC_MAXIMUM):
    need(row.get('kind') == 'FILE' and row.get('uid') == 0 and row.get('gid') == 0 and
         row.get('nlink') == 1 and type(row.get('size')) is int and 0 <= row['size'] <= maximum and
         type(row.get('mode')) is int and not row['mode'] & 0o7022, 'PROBE_PROTECTED_FILE')


def stable_read(io, path, maximum):
    first, row = io.read(path, maximum=maximum)
    again, last = io.read(path, maximum=maximum)
    need(first == again and row == last, 'PROBE_FILE_CHANGED')
    need(isinstance(first, bytes) and len(first) == row.get('size') and
         c.sha(first) == row.get('sha256') and len(first) <= maximum, 'PROBE_FILE_CONTENT_METADATA')
    return first, row


def binding(io):
    receipt_raw, receipt = stable_read(io, PROVISION, 1048576)
    protected(receipt, 1048576)
    need(receipt['mode'] == 0o600, 'PROBE_PROVISION_AUTHORITY')
    value = c.decode(receipt_raw); rows = value.get('targets')
    need(value.get('schema') == 1 and value.get('failure_policy') == 'FENCE_STOP_RETAIN_NO_REPLAY' and
         value.get('rollback_complete') is False and isinstance(rows, list) and len(rows) == 24 and
         {r.get('target') for r in rows} == d.TARGETS, 'PROBE_RETAINED_PROVISION_CONTRACT')
    selected = next(r for r in rows if r['target'] == CONTROLLER)
    # The controller binding is the fixed root:dev 0640 target. Its private
    # provisioning receipt remains root:root 0600; protected() is unchanged.
    need(all(type(selected[k]) is int for k in ('uid','gid','mode')) and
         tuple(selected[k] for k in ('uid','gid','mode')) == (0,1002,0o640),
         'PROBE_CONTROLLER_RETAINED_AUTHORITY')
    raw, meta = stable_read(io, CONTROLLER, 65536)
    need(meta.get('kind') == 'FILE' and meta.get('nlink') == 1 and
         c.sha(raw) == selected['rendered_sha256'] and
         all(type(meta[k]) is int and meta[k] == selected[k] for k in ('uid','gid','mode')),
         'PROBE_CONTROLLER_RECEIPT_BINDING')
    settings = c.decode(raw)
    need(isinstance(settings, dict) and isinstance(settings.get('ledger'),dict), 'PROBE_CONTROLLER_SCHEMA')
    return settings, {'path':CONTROLLER,'sha256':c.sha(raw),'metadata':meta,
                      'receipt_sha256':c.sha(receipt_raw)}, (receipt_raw,receipt,raw,meta)


def candidate_sources(io, root):
    need(isinstance(root,str), 'CANDIDATE_ROOT_NOT_SUPPLIED')
    c.path(root)
    need(root == c.CAND+'/epoch7-recovery-candidate-r3/xuanjun-p2-package','PROBE_STAGED_CANDIDATE_SCOPE')
    raw, metadata = stable_read(io, root+'/deploy/integration-manifest.json', 1048576)
    protected(metadata, 1048576)
    need(c.sha(raw) == RUNTIME_MANIFEST, 'PROBE_EXACT_STAGED_RUNTIME')
    manifest = c.decode(raw); hashes, files = {}, {}
    need(isinstance(manifest.get('files'),dict), 'PROBE_STAGED_MANIFEST_SCHEMA')
    for name in CANDIDATE_SOURCES:
        expected = manifest['files'].get(name); d.hash_value(expected)
        raw, row = stable_read(io, root+'/'+name, 1048576); protected(row,1048576)
        need(c.sha(raw) == expected, 'PROBE_STAGED_SOURCE_HASH')
        hashes[name], files[name] = expected, row
    return {'runtime_manifest_sha256':RUNTIME_MANIFEST,'candidate_sources':hashes,
            'root':root,'manifest_metadata':metadata,'file_metadata':files,
            'source_execution':'NOT_PERFORMED'}


def timer_properties(io):
    """Keep v239 formatted USec strings; never guess they are decimal counters."""
    from snapshot_io import TLS_TIMER_FIELDS
    observed=io.timer_schedule()
    need(isinstance(observed,dict) and set(observed)=={'raw','systemctl_sha256'},'TIMER_OBSERVATION_SCHEMA')
    d.hash_value(observed['systemctl_sha256'])
    need(isinstance(observed['raw'],dict) and set(observed['raw'])==set(TLS_TIMER_FIELDS),'TIMER_EXACT_UNITS')
    typed={};missing=[];unsupported=[]
    duration=re.compile(r'(?:0|[0-9]+(?:\.[0-9]+)?(?:y|month|w|d|h|min|s|ms|us|µs|ns)(?: [0-9]+(?:\.[0-9]+)?(?:y|month|w|d|h|min|s|ms|us|µs|ns))*)')
    for unit,fields in sorted(TLS_TIMER_FIELDS.items()):
        values=observed['raw'][unit]
        need(isinstance(values,dict) and set(values)<=set(fields),'TIMER_EXACT_PROPERTY_SCOPE')
        typed[unit]={}
        for name in fields:
            value=values.get(name)
            need(value is None or isinstance(value,str) and len(value)<=128 and
                 not any(ord(ch)<32 for ch in value),'TIMER_RAW_PROPERTY_BOUND')
            if value in (None,''):
                typed[unit][name]={'state':'MISSING','encoding':None,'value':None};missing.append(unit+':'+name)
            elif name=='NextElapseUSecMonotonic' and value=='infinity':
                typed[unit][name]={'state':'MEASURED_RAW_UNREVIEWED',
                    'encoding':'INACTIVE_BASELINE_NOT_SCHEDULED','value':None}
            elif 'USec' in name:
                supported=duration.fullmatch(value) is not None
                typed[unit][name]={'state':'MEASURED_RAW_UNREVIEWED' if supported else 'UNSUPPORTED',
                    'encoding':'SYSTEMD239_FORMAT_TIMESPAN' if supported else 'UNKNOWN_OR_INFINITY',
                    'value':None}
                if not supported:unsupported.append(unit+':'+name)
            else:
                supported=re.fullmatch(r'(?:0|[1-9][0-9]{0,19})',value) and int(value)<2**64
                typed[unit][name]={'state':'MEASURED_UNREVIEWED' if supported else 'UNSUPPORTED',
                    'encoding':'UINT64_DECIMAL_MICROSECONDS' if supported else 'UNKNOWN_OR_INFINITY',
                    'value':int(value) if supported else None}
                if not supported:unsupported.append(unit+':'+name)
    return {'state':'INCOMPLETE' if missing or unsupported else 'MEASURED_RAW_UNREVIEWED',
        'raw':observed['raw'],'typed':typed,'missing_fields':sorted(missing),
        'unsupported_fields':sorted(unsupported),'systemctl_sha256':observed['systemctl_sha256'],
        'timespan_conversion':'DEFERRED_TO_REVIEWED_HOST_PARSER','timer_actions':0,
        'source_format':'systemd/v239/src/shared/bus-util.c:uint64-property-display'}


def collect_probe_ingredients(io, candidate_root=None):
    """Return one private digest/metadata report; never return executable policy.

    ingredients exists only when every exact compiler input is measured. The
    caller must supply separately reviewed offline hashes/nonce/security consent
    to the probe compiler. Measured host data cannot set those approval flags.
    """
    sections, ingredients = {}, {}
    def section(name, callback):
        try:
            value = callback()
            sections[name] = {'state':'MEASURED_UNREVIEWED','evidence':value}
            return value
        except (KeyboardInterrupt,SystemExit): raise
        except Exception as error:
            sections[name] = {'state':'UNSUPPORTED','reason':error_label(error)}
            return None
    def hostname():
        value=io.full_hostname()
        need(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9.-]{1,253}',value) and
             value.split('.')[0] == c.HOST, 'PROBE_FULL_HOSTNAME')
        need(io.full_hostname() == value,'PROBE_HOSTNAME_CHANGED')
        return value
    host=section('hostname',hostname)
    if host is not None:ingredients['hostname']=host
    def machine():
        raw,row=stable_read(io,MACHINE_ID,4096);protected(row,4096)
        need(re.fullmatch(br'[0-9a-f]{32}\n?',raw), 'PROBE_MACHINE_ID_FORMAT')
        return {'sha256':c.sha(raw),'metadata':row}
    value=section('machine_id',machine)
    if value is not None:ingredients['machine_id_sha256']=value['sha256']
    bound=section('protected_controller_binding',lambda:binding(io))
    if bound is not None:
        settings,proof,held=bound
        # Raw protected contents are internal only. Replace the temporary section
        # before any report can be returned or persisted.
        sections['protected_controller_binding']['evidence']=proof
        def python():
            ledger=settings['ledger'];ref=ledger['python'];expected=ledger['pythonSha256']
            need(isinstance(ref,str) and PYTHON.fullmatch(ref),'PROBE_PYTHON_REFERENCE_SCOPE');d.hash_value(expected)
            resolved=io.canonical_python(ref)
            need(PYTHON.fullmatch(resolved),'PROBE_PYTHON_CANONICAL_SCOPE')
            if resolved in python_identity.PYTHON_PATHS:
                need(resolved==python_identity.PYTHON_PATHS[0] and expected==python_identity.RETAINED_SHA256,
                     'PROBE_EXACT_PYTHON_PAIR_BINDING')
                raw,row=io.read_python(resolved,maximum=PUBLIC_MAXIMUM)
                again,last=io.read_python(resolved,maximum=PUBLIC_MAXIMUM)
                need(raw==again and row==last,'PROBE_PYTHON_PAIR_CHANGED')
                pair=python_identity.validate_pair_proof(row.get('python_identity'))
                need(row==dict(pair['sample']['files'][resolved],python_identity=pair) and len(raw)==row['size'],
                     'PROBE_PYTHON_PAIR_METADATA_BINDING')
            else:
                raw,row=stable_read(io,resolved,PUBLIC_MAXIMUM);protected(row)
                need('python_identity' not in row,'PROBE_UNSCOPED_PYTHON_PAIR_PROOF')
            need(row['mode'] & 0o111 and c.sha(raw)==expected and io.canonical_python(ref)==resolved,'PROBE_PYTHON_PIN_OR_RACE')
            value={'path':resolved,'sha256':expected,'metadata':row,'reference_path':ref}
            if 'python_identity' in row:value['python_identity']=row['python_identity']
            return value
        value=section('python',python)
        if value is not None:
            ingredients['python']={k:value[k] for k in ('path','sha256')}
            if 'python_identity' in value:ingredients['python']['python_identity']=value['python_identity']
        def sdk():
            entries=settings.get('contextFiles');context=settings.get('contextPath')
            need(isinstance(entries,dict) and 1<=len(entries)<=5 and context in entries,'PROBE_SDK_BINDING_SET')
            output=[];metadata={};unsupported={}
            for name,pin in sorted(entries.items()):
                c.path(name)
                need(name.startswith(SDK_PREFIX) and re.fullmatch(r'/[A-Za-z0-9_.+/-]+',name),'PROBE_SDK_PATH_SCOPE')
                need(isinstance(pin,dict) and set(pin)=={'sha256','uid'} and pin['uid']==1002 and type(pin['uid']) is int,'PROBE_SDK_PIN_SCHEMA')
                d.hash_value(pin['sha256'])
                try:
                    info=io.file_info(name);metadata[name]=info
                    need(info.get('uid')==1002 and type(info.get('size')) is int,'PROBE_SDK_METADATA')
                    need(0<info['size']<=SDK_MAXIMUM,'PROBE_SDK_EXCEEDS_8MIB_OR_EMPTY')
                    raw,row=stable_read(io,name,SDK_MAXIMUM)
                    need(all(row.get(k)==v for k,v in info.items()),'PROBE_SDK_METADATA_CHANGED')
                    need(row.get('kind')=='FILE' and row.get('uid')==1002 and row.get('nlink')==1 and
                         type(row.get('gid')) is int and row['gid']>=0 and len(raw)==row.get('size') and
                         0<len(raw)<=SDK_MAXIMUM and not row.get('mode',0o7777)&0o7022 and
                         c.sha(raw)==pin['sha256'],'PROBE_SDK_CONTENT_AUTHORITY_OR_BOUND')
                    output.append({'path':name,'sha256':pin['sha256'],'uid':1002,'gid':row['gid'],'size':len(raw)})
                    metadata[name]=row
                except (KeyboardInterrupt,SystemExit):raise
                except Exception as error:unsupported[name]=error_label(error)
            return {'bindings':output,'metadata':metadata,'unsupported_files':unsupported,'sdk_import':'NOT_PERFORMED'}
        value=section('sdk',sdk)
        if value is not None and not value['unsupported_files']:ingredients['sdk_bindings']=value['bindings']
        elif value is not None:
            sections['sdk']['state']='UNSUPPORTED';sections['sdk']['reason']='PROBE_SDK_FILES_UNSUPPORTED'
        try:
            need((io.read(PROVISION,maximum=1048576)+io.read(CONTROLLER,maximum=65536)) == held,'PROBE_BINDING_LATE_RACE')
        except (KeyboardInterrupt,SystemExit):raise
        except Exception as error:
            sections['protected_controller_binding']={'state':'UNSUPPORTED','reason':error_label(error)}
            ingredients.pop('python',None);ingredients.pop('sdk_bindings',None)
    else:
        sections['python']={'state':'UNSUPPORTED','reason':'PROTECTED_BINDING_UNAVAILABLE'}
        sections['sdk']={'state':'UNSUPPORTED','reason':'PROTECTED_BINDING_UNAVAILABLE'}
    def systemctl():
        raw,row=stable_read(io,'/usr/bin/systemctl',PUBLIC_MAXIMUM);protected(row)
        need(row['mode'] & 0o111,'PROBE_SYSTEMCTL_EXECUTABLE')
        return {'path':'/usr/bin/systemctl','sha256':c.sha(raw),'metadata':row}
    value=section('systemctl',systemctl)
    if value is not None:ingredients['systemctl']={k:value[k] for k in ('path','sha256')}
    def manager():
        first=io.probe_manager();second=io.probe_manager()
        need(first==second and first['binary_path'] in ('/usr/lib/systemd/systemd','/lib/systemd/systemd'),'PROBE_MANAGER_CHANGED')
        d.hash_value(first['binary_sha256'])
        return {'path':first['binary_path'],'sha256':first['binary_sha256'],'observation':first}
    value=section('manager',manager)
    if value is not None:ingredients['manager']={k:value[k] for k in ('path','sha256')}
    def roles():
        first=io.probe_nss();need(io.probe_nss()==first,'PROBE_NSS_CHANGED')
        profiles=copy.deepcopy(first['profiles'])
        need(set(profiles)=={'ledger','broker','dashboard','callback','native'},'PROBE_ROLE_SET')
        specs={
            'ledger':('xuanjun-dispatcher',1003,'xuanjun-control-db',{'xuanjun-dispatcher'}),
            'broker':('root',0,'root',{'xuanjun-ledger-client'}),
            'dashboard':('xuanjun-callback',1004,'xuanjun-control-db',{'xuanjun-ledger-client'}),
            'callback':('xuanjun-callback',1004,'xuanjun-control-db',{'xuanjun-ledger-client'}),
            'native':('xuanjun_dev',1002,'xuanjun_dev',{'docker','xuanjun-ledger-client'})}
        for role,row in profiles.items():
            row.pop('protect_home',None)
            d.keys(row,('user','uid','group','gid','supplementary_groups'),'PROBE_PROFILE_KEYS')
            expected=specs[role]
            need((row['user'],row['uid'],row['group']) == expected[:3] and
                 type(row['uid']) is int and type(row['gid']) is int and row['gid']>=0 and
                 isinstance(row['supplementary_groups'],dict) and
                 set(row['supplementary_groups']) == expected[3] and
                 all(type(gid) is int and gid>=0 for gid in row['supplementary_groups'].values()),
                 'PROBE_EXACT_EXISTING_ROLE_SCOPE')
        return {'profiles':profiles,'existing_accounts':first['existing_accounts'],
                'profile_group_semantics':'PROPOSED_UNIT_SCOPED_GROUPS_NO_NSS_CHANGE'}
    value=section('profiles',roles)
    if value is not None:ingredients['profiles']=value['profiles']
    schedule=section('retained_tls_schedule',lambda:timer_properties(io))
    if schedule is not None and schedule['state']=='INCOMPLETE':
        sections['retained_tls_schedule']['state']='UNSUPPORTED'
        sections['retained_tls_schedule']['reason']='TIMER_FIELDS_MISSING_OR_UNSUPPORTED'
    staged=section('staged_candidate',lambda:candidate_sources(io,candidate_root))
    missing=sorted(INGREDIENT_FIELDS-set(ingredients))
    result={'schema':1,'kind':'PRIVATE_FINITE_PROBE_INGREDIENTS_UNREVIEWED',
        'ingredient_state':'INCOMPLETE' if missing else 'COMPLETE_UNREVIEWED',
        'missing_fields':missing,'unsupported_sections':sorted(k for k,v in sections.items() if v['state']=='UNSUPPORTED'),
        'sections':sections,'candidate_source_evidence':staged,'retained_tls_schedule':schedule,
        'independent_acceptance':'PENDING','probe_execution':'NOT_PERFORMED','install_admission':'NOT_GRANTED'}
    if not missing:result['ingredients']=ingredients
    return result
