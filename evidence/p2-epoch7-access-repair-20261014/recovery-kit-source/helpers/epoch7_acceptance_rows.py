"""Pure exact six-role access rows. No filesystem/NSS/command observations.

Inputs are authenticated proposed bytes and fresh snapshot facts, not authority.
The protected host factory binds every input to its complete reviewed plan.
"""
import copy
import hashlib
import json
import re

from activation_control import ActivationStore, _dump
from epoch7_runtime_acceptance import required_paths, validate_access, ROLES, MANIFEST, RELEASE
from epoch7_delta import TARGETS

CONFIG='/etc/xuanjun-development/'
ACTIVE='/var/lib/xuanjun-development/activation/active.json'
GATEWAY='xuanjun-uk-openclaw.service'
GATEWAY_DROPIN='/etc/systemd/system/'+GATEWAY+'.d/20-p2-docker.conf'
ADDITIONS=frozenset((CONFIG+'p2-owner-process-identity.json',CONFIG+'p2-ledger-server-identity.json'))
OWNER_PRIVATE=frozenset('/etc/xuanjun-owner-callback/'+name for name in
    ('owner-callback-auth','owner-callback-hmac','owner-user-id','owner-chat-id','owner-dashboard-token'))
ACCOUNTS=frozenset(row[1] for row in ROLES.values())
GROUP_NAMES={'gateway':'xuanjun_dev','relay':'xuanjun_dev','dispatcher':'xuanjun-dispatcher',
    'ledger':'xuanjun-control-db','callback':'xuanjun-control-db','dashboard':'xuanjun-control-db'}
NSS_PAIRS={'xuanjun_dev':frozenset(('1002',)),
    'xuanjun-dispatcher':frozenset(('1003','1006')),
    'xuanjun-callback':frozenset(('1006',))}
FACTS=frozenset(('accounts','nss_by_primary','group_ids','gateway_base_unit','unit_dropins','bootstrap'))
SHA=re.compile(r'^[0-9a-f]{64}$')
NAME=re.compile(r'^[a-z_][a-z0-9_-]{0,63}$')


def need(value,label):
    if not value:raise ValueError('ACCEPTANCE_ROWS_'+label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',', ':'),allow_nan=False).encode())
def hash_value(value):need(type(value) is str and SHA.fullmatch(value),'EXACT_HASH')
def keys(value,expected,label):need(type(value) is dict and set(value)==set(expected),label)
def gids(value):
    need(type(value) is list and len(value)<=32 and value==sorted(set(value)) and
         all(type(gid) is int and 0<gid<65536 for gid in value),'EXACT_NONROOT_GROUPS')
def missing_inputs(facts):
    need(type(facts) is dict,'FACTS_MAPPING')
    return sorted(key for key in FACTS if key not in facts or facts[key] is None)


def public_fields(value,gateway=False):
    expected={'Type','User','Group','SupplementaryGroups'}
    if gateway:expected.add('ExecStart')
    keys(value,expected,'PUBLIC_UNIT_FIELDS')
    for key in ('Type','User','Group','SupplementaryGroups'):
        values=value[key];need(type(values) is list and len(values)<=32,'UNIT_FIELD_BOUND')
        for text in values:
            need(type(text) is str and len(text)<=2048,'UNIT_FIELD_TEXT')
            if key=='Type':need(text in ('','simple','exec','forking','notify','oneshot','dbus','idle'),'UNIT_TYPE')
            elif key=='SupplementaryGroups':need(all(NAME.fullmatch(name) for name in text.split()),'UNIT_LITERAL_GROUPS')
            else:need(not text or NAME.fullmatch(text),'UNIT_LITERAL_IDENTITY')
    if gateway:
        rows=value['ExecStart'];need(type(rows) is list and 1<=len(rows)<=8,'GATEWAY_EXEC_ROWS')
        for row in rows:
            need(type(row) is list and len(row)<=16 and all(type(arg) is str and len(arg)<=1024 for arg in row),'GATEWAY_EXEC_FIELDS')
        need(rows[-1] and rows[-1][0]=='/home/xuanjun_dev/.openclaw/bin/openclaw','GATEWAY_EXEC_PATH')
    return copy.deepcopy(value)


def unit_evidence(row,expected_path,gateway=False):
    keys(row,('path','sha256','public_service_fields'),'UNIT_FILE_SCHEMA')
    need(row['path']==expected_path,'UNIT_FILE_SCOPE');hash_value(row['sha256'])
    # Fresh collector authenticates exact protected bytes before parsing only
    # these public fields. Its full observation digest is bound by the factory.
    return public_fields(row['public_service_fields'],gateway)


def unit_fields(raw):
    """Parse identity occurrences from exact new-plan bytes, no execution."""
    need(type(raw) is bytes and len(raw)<=65536,'UNIT_BYTES')
    fields={name:[] for name in ('Type','User','Group','SupplementaryGroups')};section=None
    for text in raw.decode('utf-8','strict').splitlines():
        line=text.strip()
        if not line or line.startswith(('#',';')):continue
        need(not line.endswith('\\'),'UNIT_CONTINUATION_UNSUPPORTED')
        need(not line.startswith('.include'),'UNIT_INCLUDE_UNSUPPORTED')
        if line.startswith('[') and line.endswith(']'):section=line[1:-1];continue
        if section!='Service' or '=' not in line:continue
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if key in fields:fields[key].append(value)
    return public_fields(fields)


def identity_from_fields(parts):
    selected={};supplements=[]
    for fields in parts:
        for key in ('User','Group'):
            for value in fields[key]:
                if value:selected[key]=value
                else:selected.pop(key,None)
        for value in fields['SupplementaryGroups']:
            if not value:supplements=[]
            else:supplements+=value.split();need(len(supplements)<=32,'UNIT_GROUP_BOUND')
    need('User' in selected,'UNIT_USER_REQUIRED')
    return selected,sorted(set(supplements))


def unit_identity(parts):
    return identity_from_fields([unit_fields(raw) for raw in parts])


def quiesced_descriptor_bytes(proposed):
    value=ActivationStore.validate(copy.deepcopy(proposed))
    need(value['epoch']==8 and value['state']=='PREPARED' and value['release_sha256']==MANIFEST,
         'EXACT_EPOCH8_PREPARED_PROPOSAL')
    value['state']='QUIESCED'
    # This is exactly the existing _write_descriptor serialization. There is no
    # speculative future journal record, proof timestamp, sequence or inode.
    return (_dump(ActivationStore.validate(value))+'\n').encode('utf-8')


def acceptance_facts_from_observation(observation):
    """Pure projection of one complete unreviewed collector report.

    Digests establish internal consistency only. The protected loader/factory
    authenticates this same fresh report and binds it to the reviewed plan.
    """
    need(type(observation) is dict and observation.get('schema')==1 and
         observation.get('kind')=='EPOCH7_OBSERVATION_ONLY_UNREVIEWED' and
         observation.get('install_admission')=='NOT_GRANTED','COMPLETE_OBSERVATION_REQUIRED')
    snapshot=observation['snapshot'];evidence=observation['evidence'];metadata=observation['unit_metadata']
    need(digest(snapshot)==observation['snapshot_sha256']==evidence['snapshot_sha256'] and
         digest(evidence)==observation['evidence_sha256'] and
         digest(evidence['retained'])==snapshot['retained_resource_sha256'] and
         digest(metadata)==observation['unit_metadata_sha256'],'OBSERVATION_DIGEST_BINDING')
    need(metadata.get('schema')==1 and metadata.get('kind')=='PRIVATE_UNIT_FACTS_UNREVIEWED' and
         metadata.get('state')=='COMPLETE_UNREVIEWED' and metadata.get('unsupported_sections')==[],
         'COMPLETE_UNIT_METADATA_REQUIRED')
    sections=metadata['sections'];keys(sections,('unit_nss','python_reference','native_gateway',
        'legacy_gateway','launcher','nginx_binary','runuser_binary','nginx_config','online_cpus','dropins',
        'boot_links','command_resolutions'),'COMPLETE_UNIT_SECTION_SET')
    need(
        all(type(row) is dict and row.get('state')=='MEASURED_UNREVIEWED' and type(row.get('evidence')) is dict
            for row in sections.values()),'ALL_UNIT_SECTIONS_MEASURED')
    nss=sections['unit_nss']['evidence'];need(nss.get('unsupported')=={},'NSS_UNSUPPORTED')
    accounts={user:copy.deepcopy(nss['accounts'][user]) for user in ACCOUNTS}
    pairs={user:{gid:copy.deepcopy(nss['nss_by_primary'][user][gid]) for gid in gids_}
           for user,gids_ in NSS_PAIRS.items()}
    named=nss['named_groups'];need(type(named) is dict and len(named)<=32 and
        all(type(gid) is int and 0<=gid<65536 for gid in named.values()),'NAMED_GROUP_FACTS')
    # Root/nginx are independent service facts. Excluding unused root here does
    # not permit a root grant: selected NSS/group lists and declarations reject.
    groups={name:gid for name,gid in named.items() if name not in ('root','nginx')}
    legacy=sections['legacy_gateway']['evidence']
    need(legacy.get('raw_unit_returned') is False,'PUBLIC_GATEWAY_FACTS_ONLY')
    gateway={'path':'/etc/systemd/system/'+GATEWAY,'sha256':legacy['backup_sha256'],
             'public_service_fields':copy.deepcopy(legacy['public_service_fields'])}
    unit_evidence(gateway,gateway['path'],True)
    dropins=sections['dropins']['evidence'];need(dropins.get('unsupported')==[] and
        dropins.get('raw_unit_bytes_returned') is False,'COMPLETE_PUBLIC_DROPINS')
    units={row[0] for row in ROLES.values()};all_units=units|{'xj-root-broker.service','nginx.service'}
    keys(dropins['units'],all_units,'COMPLETE_EIGHT_UNIT_INVENTORY');projected={}
    for unit,roots in dropins['units'].items():
        expected={prefix+'/'+unit+'.d' for prefix in
            ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')}
        keys(roots,expected,'COMPLETE_DROPIN_ROOTS');rows=[]
        for root,item in roots.items():
            keys(item,('present','files'),'MEASURED_DROPIN_ROOT')
            need(type(item['present']) is bool and type(item['files']) is dict and len(item['files'])<=16 and
                 (item['present'] or not item['files']),'DROPIN_ROOT_PRESENCE')
            for path,row in item['files'].items():
                need(type(path) is str and path.startswith(root+'/') and
                    re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.conf',path[len(root)+1:]),'DROPIN_OCCURRENCE_PATH')
                keys(row,('sha256','metadata','public_service_fields'),'MEASURED_DROPIN_FILE')
                meta=row['metadata'];need(type(meta) is dict and meta.get('kind')=='FILE' and
                    (meta.get('uid'),meta.get('gid'),meta.get('nlink'))==(0,0,1) and
                    type(meta.get('mode')) is int and not meta['mode']&0o022 and
                    meta.get('sha256')==row['sha256'],'DROPIN_METADATA_BINDING')
                projected_row={'path':path,'sha256':row['sha256'],
                               'public_service_fields':copy.deepcopy(row['public_service_fields'])}
                unit_evidence(projected_row,path);rows.append(projected_row)
        if unit in units:projected[unit]=sorted(rows,key=lambda row:row['path'])
    bootstrap={path:copy.deepcopy(evidence['retained']['bootstrap'][path]) for path in OWNER_PRIVATE}
    result={'accounts':accounts,'nss_by_primary':pairs,'group_ids':groups,
        'gateway_base_unit':gateway,'unit_dropins':projected,'bootstrap':bootstrap}
    need(not missing_inputs(result),'MISSING_FRESH_FACTS')
    return result


def compile_access_rows(compiled,identity_payloads,manifest_raw,rendered_payload_sha256,fresh_facts):
    need(type(compiled) is dict and compiled.get('kind')=='PRIVATE_RETAINED_BINDINGS_NOT_INSTALL_PLAN' and
         compiled.get('install_admission') is False and compiled.get('manifest_sha256')==MANIFEST,'COMPILED_PROPOSAL')
    need(type(manifest_raw) is bytes and len(manifest_raw)<=1048576 and sha(manifest_raw)==MANIFEST,'EXACT_RUNTIME_MANIFEST')
    manifest=json.loads(manifest_raw.decode('utf-8'));files=manifest['files']
    need(type(files) is dict and len(files)==107,'EXACT107_MANIFEST')
    keys(rendered_payload_sha256,files,'EXACT107_RENDERED_PAYLOAD_SET')
    rendered=set(manifest['rendering']['identity_files'])
    for relative,value in rendered_payload_sha256.items():
        hash_value(value)
        if relative not in rendered:need(value==files[relative],'UNRENDERED_PAYLOAD_HASH')
    targets=compiled['rendered_targets'];before=compiled['old_rendered_targets']
    need(type(targets) is dict and set(targets)==set(TARGETS) and set(before)==set(targets),'EXACT24_TARGETS')
    provision=compiled['runtime']['provisioning']
    need(type(provision) is list and len(provision)==24 and {r['target'] for r in provision}==set(targets),'EXACT24_PROVISION_ROWS')
    rows={row['target']:row for row in provision};pins={}
    for path,raw in targets.items():
        need(type(raw) is bytes and len(raw)<=1048576 and sha(raw)==rows[path]['rendered_sha256'],'TARGET_RENDERED_BYTES')
        pins[path]=sha(raw)
    keys(identity_payloads,ADDITIONS,'EXACT_TWO_IDENTITIES')
    for path,raw in identity_payloads.items():
        need(type(raw) is bytes and 0<len(raw)<=65536,'IDENTITY_BYTES');pins[path]=sha(raw)
    for relative,value in rendered_payload_sha256.items():pins[RELEASE+'/'+relative]=value
    need(compiled['activation_proposal']['binary_sha256']==files['stage1/native_gateway_controller.py'],
         'ACTIVATION_CONTROLLER_BYTES')
    active=quiesced_descriptor_bytes(compiled['activation_proposal'])
    need(compiled['activation_proposal']['config_sha256']==pins[CONFIG+'dispatcher.json'],'ACTIVATION_CONFIG_BYTES')
    pins[ACTIVE]=sha(active)

    keys(fresh_facts,FACTS,'EXACT_FRESH_FACTS');need(not missing_inputs(fresh_facts),'MISSING_FRESH_FACTS')
    accounts=fresh_facts['accounts'];groups=fresh_facts['group_ids']
    keys(accounts,ACCOUNTS,'EXACT_NSS_ACCOUNTS')
    need(type(groups) is dict and 1<=len(groups)<=32 and all(type(name) is str and NAME.fullmatch(name) and
         type(gid) is int and 0<gid<65536 for name,gid in groups.items()),'MEASURED_NAMED_GROUPS')
    for name,row in accounts.items():
        keys(row,('uid','primary_gid','global_group_gids'),'NSS_ACCOUNT_SCHEMA')
        need(type(row['uid']) is int and type(row['primary_gid']) is int and 0<row['primary_gid']<65536,'NSS_ACCOUNT_IDS')
        gids(row['global_group_gids']);need(row['primary_gid'] in row['global_group_gids'],'NSS_PRIMARY_GROUP_REQUIRED')
    by_primary=fresh_facts['nss_by_primary'];keys(by_primary,NSS_PAIRS,'EXACT_UNIT_PRIMARY_USERS')
    for user,required in NSS_PAIRS.items():
        keys(by_primary[user],required,'EXACT_UNIT_PRIMARY_PAIRS')
        for primary,members in by_primary[user].items():
            gids(members);need(int(primary) in members,'UNIT_PRIMARY_GROUP_REQUIRED')
    bootstrap=fresh_facts['bootstrap'];keys(bootstrap,OWNER_PRIVATE,'FIVE_OWNER_PRIVATE_FACTS')
    for path,row in bootstrap.items():
        need(type(row) is dict and row.get('kind')=='FILE' and
             (row.get('uid'),row.get('gid'),row.get('mode'),row.get('nlink'))==(1004,1006,0o600,1) and
             all(type(row.get(k)) is int for k in ('uid','gid','mode','nlink')),'OWNER_PRIVATE_METADATA')
        hash_value(row.get('sha256'));pins[path]=row['sha256']
    units={row[0] for row in ROLES.values()};keys(fresh_facts['unit_dropins'],units,'COMPLETE_UNIT_DROPIN_INVENTORY')
    gateway_base=unit_evidence(fresh_facts['gateway_base_unit'],'/etc/systemd/system/'+GATEWAY,True)
    dropins={}
    # Unit-name drop-ins from the three measured v239 roots. Same basename
    # selects /etc over /run over /usr/lib; selected basenames sort lexically.
    roots=('/usr/lib/systemd/system','/run/systemd/system','/etc/systemd/system')
    for unit,entries in fresh_facts['unit_dropins'].items():
        need(type(entries) is list and len(entries)<=48,'UNIT_DROPIN_BOUND')
        paths=[row.get('path') for row in entries]
        need(all(type(path) is str for path in paths) and paths==sorted(set(paths)),'SORTED_UNIQUE_UNIT_DROPINS')
        mapped={}
        for row in entries:
            path=row['path'];matches=[(rank,root+'/'+unit+'.d/') for rank,root in enumerate(roots)
                if path.startswith(root+'/'+unit+'.d/')]
            need(len(matches)==1,'FIXED_UNIT_DROPIN_PATH');rank,prefix=matches[0];leaf=path[len(prefix):]
            need(re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.conf',leaf),'FIXED_UNIT_DROPIN_PATH')
            fields=unit_evidence(row,path)
            if path in before:need(row['sha256']==sha(before[path]) and fields==unit_fields(before[path]),'RETAINED_DROPIN_BEFORE_BYTES')
            if leaf not in mapped or rank>mapped[leaf][0]:mapped[leaf]=(rank,fields)
        prefix='/etc/systemd/system/'+unit+'.d/'
        for path,raw in targets.items():
            if path.startswith(prefix):mapped[path[len(prefix):]]=(2,unit_fields(raw))
        dropins[unit]=[value[1] for leaf,value in sorted(mapped.items())]

    output=[]
    for role,(unit,user,uid,gid) in sorted(ROLES.items()):
        base=gateway_base if unit==GATEWAY else unit_fields(targets['/etc/systemd/system/'+unit])
        identity,names=identity_from_fields([base]+dropins[unit])
        account=accounts[user]
        need(identity['User']==user and account['uid']==uid,'EXACT_ROLE_UID')
        group=identity.get('Group')
        if group is None:need(account['primary_gid']==gid,'IMPLICIT_PRIMARY_GROUP')
        else:need(group==GROUP_NAMES[role] and groups.get(group)==gid,'EXACT_ROLE_GROUP')
        need(all(name in groups for name in names),'MISSING_NAMED_GROUP_GID')
        supplements=sorted(set(groups[name] for name in names));gids(supplements)
        # initgroups uses the unit's resolved Group, not passwd's old primary.
        nss=by_primary[user][str(gid)];union=sorted(set(nss+supplements+[gid]));gids(union)
        role_paths=[]
        for path,kind in sorted(required_paths()[role].items()):
            need(kind=='directory' or path in pins,'MISSING_REQUIRED_FILE_PIN')
            role_paths.append({'path':path,'kind':kind,'sha256':None if kind=='directory' else pins[path]})
        output.append({'role':role,'identity':{'unit':unit,'user':user,'uid':uid,'gid':gid,
            'nss_groups':copy.deepcopy(nss),'unit_supplementary_groups':supplements,'groups':union},'paths':role_paths})
    return validate_access(output)
