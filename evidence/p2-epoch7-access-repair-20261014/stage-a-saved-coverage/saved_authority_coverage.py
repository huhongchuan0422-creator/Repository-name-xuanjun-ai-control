"""Pure saved-authority coverage map. Local reconstruction, not approval.

The caller MUST first authenticate the ORIGINAL complete raw observation and
source/host/attempt/nonce chain, then run the genuine fixed full validators and
projection. A public exported subset cannot substitute for that input. This
module checks and maps saved fields; no return value authenticates provenance.

Evidence layers follow PR58 comments 6197750473 and 6197897838. Historical
per-call ancestor descriptors and cross-scan object joins were not retained.
Source-enforced guarantees are conditional on the caller's independently
validated successful collector chain. No fresh read, import of a host adapter,
probe, prepare, installation, or approval occurs here. Python 3.6.8 compatible.
"""
import hashlib
import json
import re

MAX_OUTPUT_BYTES = 131072
SAVED = 'SAVED_VALUE'
SOURCE = 'SOURCE_ENFORCED_ONLY'
MISSING = 'NOT_RETAINED'
DROPIN_ROOTS = ('/etc/systemd/system', '/run/systemd/system', '/usr/lib/systemd/system')
SERVICE_UNITS = ('xuanjun-uk-openclaw.service','xuanjun-p2-gateway-relay.service',
    'xuanjun-development-dispatcher.service','xuanjun-ledger.service',
    'xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service','xj-root-broker.service','nginx.service')
SOCKET_UNITS = ('xj-root-broker.socket','xuanjun-ledger.socket','xuanjun-p2-gateway-relay.socket')
DROPIN_UNITS = SERVICE_UNITS + SOCKET_UNITS
UNIT_SECTIONS = {'unit_nss','python_reference','native_gateway','legacy_gateway','launcher',
    'nginx_binary','runuser_binary','nginx_config','online_cpus','dropins','boot_links','command_resolutions'}
META = {'dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'}


def need(value, label):
    if not value: raise ValueError('SAVED_AUTHORITY_' + label)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(raw): return hashlib.sha256(raw).hexdigest()
def same(left, right): return canonical(left) == canonical(right)
def keys(value, expected, label): need(type(value) is dict and set(value) == set(expected), label)
def sha(value): need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value), 'HASH')
def integer(value, minimum=0): need(type(value) is int and minimum <= value < 2**63, 'INTEGER')


# Inventory and late-check validation mirror the fixed 609407 projector.
# This is a narrow validation layer, not a replacement for its full validators.
def _saved_dropin_section(row):
    keys(row, ('state','evidence'), 'SAVED_DROPIN_SECTION_FIELDS')
    need(row['state']=='MEASURED_UNREVIEWED','SAVED_DROPIN_SECTION_STATE')
    value=row['evidence'];keys(value,('units','unsupported','raw_unit_bytes_returned'),'SAVED_DROPIN_EVIDENCE')
    need(value['unsupported']==[] and value['raw_unit_bytes_returned'] is False,'SAVED_DROPIN_UNSUPPORTED')
    keys(value['units'],DROPIN_UNITS,'SAVED_ELEVEN_UNIT_SET')
    for unit, roots in value['units'].items():
        keys(roots,tuple(root+'/'+unit+'.d' for root in DROPIN_ROOTS),'SAVED_THREE_ROOT_SET')
        for root,item in roots.items():
            keys(item,('present','files'),'SAVED_ROOT_FIELDS')
            need(type(item['present']) is bool and type(item['files']) is dict and len(item['files'])<=16 and
                 (item['present'] or not item['files']),'SAVED_ROOT_PRESENCE')
            # The fixed socket mechanism supports no active socket override.
            if unit in SOCKET_UNITS: need(not item['files'],'SAVED_SOCKET_CONTENT_UNSUPPORTED')
            for path,info in item['files'].items():
                need(type(path) is str and path.startswith(root+'/') and
                     re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.conf',path[len(root)+1:]),'SAVED_FILE_PATH')
                keys(info,('sha256','metadata','public_service_fields'),'SAVED_FILE_FIELDS');sha(info['sha256'])
                meta=info['metadata'];keys(meta,META|{'kind','sha256'},'SAVED_FILE_METADATA')
                for name in META:integer(meta[name],1 if name in ('ino','nlink') else 0)
                need(meta['kind']=='FILE' and meta['sha256']==info['sha256'] and
                     (meta['uid'],meta['gid'],meta['nlink'])==(0,0,1) and meta['size']<=65536 and
                     meta['mode']<=0o7777 and not meta['mode']&0o7022,'SAVED_FILE_AUTHORITY')
                fields=info['public_service_fields'];keys(fields,('Type','User','Group','SupplementaryGroups'),'SAVED_PUBLIC_FIELDS')
                for name,values in fields.items():
                    need(type(values) is list and len(values)<=32,'SAVED_PUBLIC_LIST')
                    for text in values:
                        need(type(text) is str and len(text)<=2048,'SAVED_PUBLIC_TEXT')
                        if name=='Type':need(text in ('','simple','exec','forking','notify','oneshot','dbus','idle'),'SAVED_PUBLIC_TYPE')
                        elif name=='SupplementaryGroups':need(all(re.fullmatch(r'[a-z_][a-z0-9_-]*',x) for x in text.split()),'SAVED_PUBLIC_GROUPS')
                        else:need(not text or re.fullmatch(r'[a-z_][a-z0-9_-]*',text),'SAVED_PUBLIC_ACCOUNT')


def _saved_latecheck_section(row, inventory):
    keys(row,('state','evidence'),'SAVED_LATECHECK_SECTION_FIELDS')
    need(row['state']=='MEASURED_UNREVIEWED','SAVED_LATECHECK_SECTION_STATE')
    value=row['evidence'];keys(value,('unit','resolution','provenance','collector_path_used'),'SAVED_LATECHECK_FIELDS')
    unit='xuanjun-development-dispatcher.service'
    need(value['unit']==unit and value['collector_path_used'] is False,'SAVED_LATECHECK_SCOPE')
    resolution=value['resolution'];keys(resolution,('command','path_environment','entries'),'SAVED_RESOLUTION_FIELDS')
    need(resolution['command']=='git' and type(resolution['path_environment']) is str,'SAVED_RESOLUTION_COMMAND')
    names=resolution['path_environment'].split(':')
    need(0<len(names)<=6 and len(set(names))==len(names) and
         all(name in ('/usr/local/sbin','/usr/local/bin','/usr/sbin','/usr/bin','/sbin','/bin') for name in names),'SAVED_PATH_SCOPE')
    entries=resolution['entries'];need(type(entries) is list and len(entries)==len(names),'SAVED_PATH_ENTRIES')
    found=[]
    for name,entry in zip(names,entries):
        keys(entry,('directory','uid','gid','mode','dev','ino','git'),'SAVED_PATH_ENTRY_FIELDS')
        need(entry['directory']==name,'SAVED_PATH_ENTRY_SCOPE')
        for key in ('uid','gid','mode','dev','ino'):integer(entry[key],1 if key=='ino' else 0)
        need(entry['uid']==entry['gid']==0 and entry['mode']<=0o7777 and not entry['mode']&0o7022,'SAVED_PATH_AUTHORITY')
        if entry['git'] is not None:
            git=entry['git'];keys(git,('path','sha256','dev','ino'),'SAVED_GIT_FIELDS')
            need(git['path']==name+'/git'=='/usr/bin/git','SAVED_GIT_PATH');sha(git['sha256'])
            integer(git['dev']);integer(git['ino'],1);found.append(git['path'])
    need(found==['/usr/bin/git'],'SAVED_GIT_REQUIRED')
    provenance=value['provenance'];keys(provenance,('source','systemctl_sha256','manager_sha256','upstream_version',
        'distro_matching_build','unit_sha256','dropins_sha256','public_unit_environment'),'SAVED_LATECHECK_PROVENANCE')
    need(provenance['source']=='SYSTEM_MANAGER_CHILD_ENVIRONMENT' and provenance['upstream_version']=='239' and
         provenance['distro_matching_build']=='NOT_VERIFIED','SAVED_LATECHECK_SOURCE')
    for key in ('systemctl_sha256','manager_sha256','unit_sha256','dropins_sha256'):sha(provenance[key])
    need(provenance['dropins_sha256']==digest(canonical(inventory[unit])),'SAVED_LATECHECK_DROPIN_BINDING')
    environment=provenance['public_unit_environment'];keys(environment,('environment_names','path_overrides'),'SAVED_ENVIRONMENT_FIELDS')
    names=environment['environment_names'];need(type(names) is list and len(names)<=128 and names==sorted(set(names)) and
        all(type(name) is str and len(name)<=128 and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) and name!='PATH' for name in names) and
        environment['path_overrides']=='PROVEN_ABSENT_IN_SUPPORTED_SYNTAX','SAVED_ENVIRONMENT_SCOPE')


BOOT_ROOTS = DROPIN_ROOTS + ('/run/systemd/system.control',
    '/run/systemd/transient', '/run/systemd/generator.early',
    '/run/systemd/generator', '/run/systemd/generator.late')
BOOT_UNITS = {'xuanjun-uk-openclaw.service', 'xuanjun-uk-owner-callback.service',
              'xuanjun-uk-owner-dashboard.service'}


def _hash(value):
    return digest(canonical(value))


def _authority(pin):
    keys(pin, ('uid', 'gid', 'mode'), 'DIRECTORY_POLICY_FIELDS')
    for name in pin:
        integer(pin[name])
    # Exact original selected-directory invariant: UID 0; GID is retained.
    need(pin['uid'] == 0 and pin['gid'] < 2**32 and
         pin['mode'] <= 0o7777 and not pin['mode'] & 0o7022,
         'DIRECTORY_POLICY_AUTHORITY')


def _directory_metadata(meta):
    keys(meta, META, 'DIRECTORY_METADATA_FIELDS')
    for name in META:
        integer(meta[name], 1 if name in ('ino', 'nlink') else 0)
    _authority({name: meta[name] for name in ('uid', 'gid', 'mode')})


def _ancestors(path):
    parts = path.strip('/').split('/')
    return ['/'] + ['/' + '/'.join(parts[:i]) for i in range(1, len(parts)+1)]


def _policy_rows(directories, path):
    result = []
    for index, parent in enumerate(_ancestors(path)):
        if parent not in directories:
            result.append({'ancestor_index': index, 'evidence': MISSING})
            continue
        pin = directories[parent]
        _authority(pin)
        result.append({'ancestor_index': index, 'evidence': SAVED,
                       'authority_sha256': _hash(pin)})
    return result


def _boot_evidence(section):
    keys(section, ('state', 'evidence'), 'BOOT_SECTION_FIELDS')
    need(section['state'] == 'MEASURED_UNREVIEWED', 'BOOT_SECTION_STATE')
    boot = section['evidence']
    keys(boot, ('units', 'roots', 'unsupported_roots', 'restored_enablement',
                'runtime_alias_semantics'), 'BOOT_EVIDENCE_FIELDS')
    need(type(boot['units']) is list and len(boot['units']) == 3 and
         set(boot['units']) == BOOT_UNITS and boot['unsupported_roots'] == [] and
         boot['restored_enablement'] == 'NOT_INFERRED' and
         boot['runtime_alias_semantics'] == 'REQUIRES_SYSTEMD239_REVIEW', 'BOOT_SCOPE')
    # A complete successful collector retains all eight scan-root entries.
    # Three are the selected drop-in base roots; missing rows are evidence gaps.
    need(type(boot['roots']) is dict and set(boot['roots']) <= set(BOOT_ROOTS),
         'BOOT_ROOT_SCOPE')
    return boot


def _base_scan(boot, base):
    if base not in boot['roots']:
        return None
    scan = boot['roots'][base]
    keys(scan, ('present', 'directories', 'links', 'selected_nonlinks',
                'scan_scope', 'all_link_inventory_sha256'), 'BOOT_ROOT_FIELDS')
    need(scan['present'] is True and scan['scan_scope'] == 'BOUNDED_RECURSIVE_NOFOLLOW',
         'BOOT_SELECTED_ROOT_STATE')
    need(type(scan['directories']) is dict and len(scan['directories']) <= 1024 and
         type(scan['links']) is list and len(scan['links']) <= 16384 and
         type(scan['selected_nonlinks']) is dict, 'BOOT_DIRECTORY_BOUND')
    sha(scan['all_link_inventory_sha256'])
    # Validate retained directory rows, without equating their identities to
    # an earlier drop-in read. The original serialized mode has no S_IFMT bits.
    for path, row in scan['directories'].items():
        need(type(path) is str and (path == base or path.startswith(base+'/')) and
             len(path) <= 4096 and all(part not in ('', '.', '..') for part in
             path.split('/')[1:]), 'BOOT_DIRECTORY_PATH')
        keys(row, ('metadata', 'entry_count', 'inventory_sha256'), 'BOOT_DIRECTORY_FIELDS')
        _directory_metadata(row['metadata'])
        integer(row['entry_count'])
        need(row['entry_count'] <= 4096, 'BOOT_ENTRY_BOUND')
        sha(row['inventory_sha256'])
    return scan


def _scan_coverage(boot):
    result = []
    for index, base in enumerate(BOOT_ROOTS):
        if base not in boot['roots']:
            result.append({'scan_root_index': index, 'evidence': MISSING})
            continue
        scan = boot['roots'][base]
        need(type(scan) is dict, 'BOOT_ROOT_TYPE')
        if index >= 3 and scan.get('present') is False:
            keys(scan, ('present', 'directories', 'links'), 'BOOT_ABSENT_FIELDS')
            need(scan['directories'] == {} and scan['links'] == [], 'BOOT_ABSENT_CONTENT')
            state = 'ABSENT'
        else:
            _base_scan(boot, base)
            state = 'PRESENT'
        result.append({'scan_root_index': index, 'evidence': SAVED,
                       'presence': state, 'record_sha256': _hash(scan)})
    return result


def _later_directory(scan, path, policy, count=None):
    if scan is None or path not in scan['directories']:
        return {'evidence': MISSING, 'policy_agreement': 'NOT_AVAILABLE'}
    row = scan['directories'][path]
    meta = row['metadata']
    pin = policy.get(path)
    agreement = 'NOT_AVAILABLE'
    if pin is not None:
        _authority(pin)
        need(all(meta[name] == pin[name] for name in ('uid', 'gid', 'mode')),
             'BOOT_POLICY_AUTHORITY_MISMATCH')
        agreement = 'MATCH'
    if count is not None:
        need(row['entry_count'] == count, 'BOOT_DROPIN_ENTRY_COUNT_MISMATCH')
    return {'evidence': SAVED, 'authority_record_sha256': _hash(meta),
            'listing_sha256': row['inventory_sha256'],
            'entry_count': row['entry_count'], 'policy_agreement': agreement,
            'object_type_check': SOURCE}


def _summarize(observation):
    need(type(observation) is dict and type(observation.get('schema')) is int and
         observation['schema'] == 1 and
         observation.get('kind') == 'EPOCH7_OBSERVATION_ONLY_UNREVIEWED' and
         observation.get('independent_acceptance') == 'PENDING' and
         observation.get('install_admission') == 'NOT_GRANTED', 'FULL_OBSERVATION_REQUIRED')
    metadata = observation.get('unit_metadata')
    need(type(metadata) is dict and type(metadata.get('schema')) is int and
         metadata['schema'] == 1 and metadata.get('kind') == 'PRIVATE_UNIT_FACTS_UNREVIEWED' and
         metadata.get('state') == 'COMPLETE_UNREVIEWED' and
         metadata.get('unsupported_sections') == [] and
         metadata.get('independent_acceptance') == 'PENDING' and
         metadata.get('install_admission') == 'NOT_GRANTED', 'COMPLETE_UNIT_METADATA_REQUIRED')
    sha(observation.get('unit_metadata_sha256'))
    need(_hash(metadata) == observation['unit_metadata_sha256'], 'UNIT_METADATA_DIGEST')
    sections = metadata.get('sections')
    keys(sections, UNIT_SECTIONS, 'COMPLETE_UNIT_SECTIONS')
    need(all(type(row) is dict and row.get('state') == 'MEASURED_UNREVIEWED' and
             type(row.get('evidence')) is dict for row in sections.values()),
         'ALL_SECTIONS_MEASURED')
    _saved_dropin_section(sections['dropins'])
    inventory = sections['dropins']['evidence']['units']
    _saved_latecheck_section(sections['command_resolutions'], inventory)
    policy = observation.get('policy')
    need(type(policy) is dict and type(policy.get('directories')) is dict and
         len(policy['directories']) <= 4096, 'POLICY_DIRECTORIES_REQUIRED')
    sha(observation.get('policy_sha256'))
    need(_hash(policy) == observation['policy_sha256'], 'POLICY_DIGEST')
    late = sections['command_resolutions']['evidence']['provenance']
    need(late['manager_sha256'] == _hash(observation['evidence']['writers']['manager']) and
         late['systemctl_sha256'] == policy['executables']['systemctl']['sha256'],
         'LATECHECK_MANAGER_TOOL_BINDING')
    boot = _boot_evidence(sections['boot_links'])
    scan_coverage = _scan_coverage(boot)
    scans = [_base_scan(boot, base) for base in DROPIN_ROOTS]
    directories = policy['directories']
    bases = []
    incomplete = len(boot['roots']) != len(BOOT_ROOTS)
    policy_complete = True
    for index, base in enumerate(DROPIN_ROOTS):
        ancestors = _policy_rows(directories, base)
        later = _later_directory(scans[index], base, directories)
        policy_complete = policy_complete and all(row['evidence'] == SAVED for row in ancestors)
        incomplete = incomplete or not policy_complete
        incomplete = incomplete or later['evidence'] == MISSING
        bases.append({'root_index': index, 'policy_ancestors': ancestors,
                      'later_directory_record': later})
    counts = {'unit_count': 11, 'root_count': 3, 'scope_count': 33,
              'present_count': 0, 'absent_count': 0, 'empty_present_count': 0,
              'nonempty_present_count': 0, 'file_count': 0}
    rows = []
    for unit_index, unit in enumerate(sorted(DROPIN_UNITS)):
        for root_index, base in enumerate(DROPIN_ROOTS):
            path = base+'/'+unit+'.d'
            item = inventory[unit][path]
            files = item['files']
            scan = scans[root_index]
            present = item['present']
            if not present:
                need(scan is None or path not in scan['directories'],
                     'BOOT_DROPIN_PRESENCE_MISMATCH')
            ancestors = _policy_rows(directories, path if present else base)
            later = (_later_directory(scan, path, directories, len(files)) if present else
                     {'evidence': MISSING, 'policy_agreement': 'NOT_APPLICABLE_ABSENT'})
            policy_complete = policy_complete and all(row['evidence'] == SAVED for row in ancestors)
            incomplete = incomplete or not policy_complete
            if present:
                incomplete = incomplete or later['evidence'] == MISSING
            records = []
            for file_index, name in enumerate(sorted(files)):
                record = files[name]
                records.append({'file_index': file_index, 'content_sha256': record['sha256'],
                    'saved_metadata_sha256': _hash(record['metadata']),
                    'saved_authority': SAVED, 'saved_file_metadata': SAVED,
                    'file_type_check': SOURCE, 'content_bytes': MISSING})
            state = 'ABSENT' if not present else ('NONEMPTY' if files else 'EMPTY')
            rows.append({'unit_index': unit_index, 'root_index': root_index,
                'presence': 'PRESENT' if present else 'ABSENT', 'content_state': state,
                'inventory_evidence': SAVED, 'inventory_sha256': _hash(item),
                'file_count': len(files), 'file_records': records,
                'policy_ancestors': ancestors, 'later_directory_record': later})
            counts['present_count' if present else 'absent_count'] += 1
            if present:
                counts['nonempty_present_count' if files else 'empty_present_count'] += 1
            counts['file_count'] += len(files)
    result = {'schema': 1, 'kind': 'SAVED_AUTHORITY_COVERAGE',
        'status': 'HOLD' if incomplete else 'MAPPED_UNAPPROVED',
        'source_chain_validation': 'CALLER_REQUIRED',
        'full_observation_validation': 'CALLER_REQUIRED',
        'unit_metadata_sha256': observation['unit_metadata_sha256'],
        'policy_sha256': observation['policy_sha256'],
        'dropins_section_sha256': _hash(sections['dropins']),
        'latecheck_section_sha256': _hash(sections['command_resolutions']),
        'boot_section_sha256': _hash(sections['boot_links']),
        'counts': counts, 'scan_roots': scan_coverage, 'base_roots': bases, 'rows': rows,
        'evidence_layers': {
            'saved_presence_inventory_file_metadata': SAVED,
            'saved_policy_ancestor_authority': SAVED if policy_complete else MISSING,
            'no_symlink_checks': SOURCE, 'directory_type_checks': SOURCE,
            'fd_path_object_consistency': SOURCE, 'inventory_late_recheck': SOURCE,
            'per_check_ancestor_fd_dev_ino_records': MISSING,
            'dropin_to_boot_object_identity_join': MISSING},
        'historical_failure': 'PRESERVE_ORIGINAL_HOLD',
        'fresh_directory_authority': 'NOT_ASSESSED', 'fresh_collection': 'NOT_RUN',
        'topology_approval': 'NOT_GRANTED', 'prepare': 'NOT_AUTHORIZED',
        'install_resume': 'NOT_AUTHORIZED'}
    need(len(canonical(result)) <= MAX_OUTPUT_BYTES, 'OUTPUT_BOUND')
    return result


def summarize_saved_authority(observation):
    """Map authenticated full saved input; never authenticate or approve it.

    All exceptions expose only a fixed finite category, never input keys/values.
    Missing retained boot/policy rows are explicit NOT_RETAINED plus HOLD.
    Missing/unknown 33 inventory rows or contradictions reject entirely.
    """
    try:
        return _summarize(observation)
    except ValueError as error:
        if error.args and type(error.args[0]) is str and re.fullmatch(r'SAVED_AUTHORITY_[A-Z0-9_]+', error.args[0]):
            raise
        raise ValueError('SAVED_AUTHORITY_INVALID_VALUE') from None
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, IndexError):
        raise ValueError('SAVED_AUTHORITY_INVALID_STRUCTURE') from None
