"""Artifact-bound r7 saved-evidence projection for one complete recovery audit.

Probe source pins bind the reviewed corrected driver/helper and Node validator
in the immutable r7 artifact. The saved-only reader authenticates that artifact before projection.
This schema2 body binds saved eleven-unit inventory semantics, not fresh
directory identity. The future private-plan/fresh-authority consumer is pending
separate adaptation and admission; this module does not make it runnable.

The caller authenticates the kit/cache and reads the root-owned nonce receipt
through the existing protected loader. Saved inventory contains no fabricated
parent or directory metadata and is bound to the original complete observation. This module performs no host I/O. A
synthetic object cannot establish that authority. The proposed exclusivity claim
requires a genuine source/mechanism review; a successful probe alone cannot
approve it. The resulting topology receipt authorizes no production operation.

One complete audit, two mechanically linked receipts:
1. Authenticate the existing kit, this separate preparation source manifest and
   protected inputs; project the unsigned first review body.
2. A genuine reviewer checks the entire packet, including exclusive inherited
   manager delivery, and publishes that exact topology-only body.
3. Existing authenticated fetch obtains its real ID and exact body digest.
4. Compile the final plan using that three-field topology review provenance.
5. The same complete audit can reproduce that plan and issue the existing exact
   complete machine approval. Its plan hash binds the first receipt transitively.
The first body contains neither its own ID/body hash nor the later plan hash;
no placeholder review is accepted and the final production gate is unchanged.
"""
import copy
import hashlib
import json
import re
import types

import epoch7_approval as approval
import node_sqlite_probe as node
import probe_driver as probe
import probe_helpers as helper
from ledger_server_identity import normalize_exec_start

SOURCE_PINS = {
    'unit_metadata.py': 'ebc126a70a7876b5521d0331a0a45334c371e3e0f8a2e3fac93a3d110f37bea0',
    'snapshot_io.py': '3f24884eaee91e9738397a952927c1be324350f88c631ff546a11efc259c8f85',
    'probe_driver.py': '18bdc9ed897a084e69aaf7da80763b4f43f3298f0b79f7b35e8a04e5dcbd6808',
    'probe_helpers.py': '0b62410b57193eb7ce984f5002bf71e1c31242e37e58f6296ad74da247cc1468',
    'node_sqlite_probe.py': 'c2f580021c36e72574e3a67201c90a9fc09f22ee7ede396650dc970757151f7a',
    'deploy/integration-manifest.json': '0ac28c96636ee63364015b375202779e2ef1dd0bd9f1b81e77d4387b6754316c'}
DECISION = 'ACCEPTED_EXACT_EPOCH7_ROOT_MANAGER_TOPOLOGY_ONLY'
STATUS_FIELDS = {'Uid', 'Gid', 'Groups', 'CapEff', 'CapBnd', 'CapAmb', 'NoNewPrivs', 'Seccomp'}
BINDING_FIELDS = {'recovery_kit_manifest_sha256', 'runtime_manifest_sha256',
    'observation_sha256', 'probe_policy_sha256', 'probe_receipt_sha256',
    'probe_input_sha256', 'source_files', 'evidence_records_sha256', 'saved_unit_dropins_sha256', 'saved_projection_source_manifest_sha256'}
DROPIN_ROOTS = ('/etc/systemd/system', '/run/systemd/system', '/usr/lib/systemd/system')
SERVICE_UNITS = ('xuanjun-uk-openclaw.service','xuanjun-p2-gateway-relay.service',
    'xuanjun-development-dispatcher.service','xuanjun-ledger.service',
    'xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service','xj-root-broker.service','nginx.service')
SOCKET_UNITS = ('xj-root-broker.socket','xuanjun-ledger.socket','xuanjun-p2-gateway-relay.socket')
DROPIN_UNITS = SERVICE_UNITS + SOCKET_UNITS
UNIT_SECTIONS = {'unit_nss','python_reference','native_gateway','legacy_gateway','launcher',
    'nginx_binary','runuser_binary','nginx_config','online_cpus','dropins','boot_links','command_resolutions'}
SAVED_PRODUCER_PINS = {name:SOURCE_PINS[name] for name in ('unit_metadata.py','snapshot_io.py')}
META = {'dev','ino','mode','uid','gid','nlink','size','mtime_ns','ctime_ns'}
PROPOSAL_FIELDS = {'schema', 'kind', 'topology', 'topology_raw', 'topology_sha256',
                   'bindings', 'expected_review_body'}


def need(value, label):
    if not value: raise ValueError('TOPOLOGY_' + label)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(raw): return hashlib.sha256(raw).hexdigest()
def same(left, right): return canonical(left) == canonical(right)
def keys(value, expected, label): need(type(value) is dict and set(value) == set(expected), label)
def sha(value): need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value), 'HASH')
def integer(value, minimum=0): need(type(value) is int and minimum <= value < 2**63, 'INTEGER')


def _status(value, uid=None, gid=None):
    keys(value, STATUS_FIELDS, 'PROCESS_STATUS_FIELDS')
    for name in ('Uid', 'Gid'):
        need(type(value[name]) is str and re.fullmatch(r'[0-9]+(?:[ \t]+[0-9]+){3}', value[name]), 'PROCESS_IDS')
        ids = [int(x) for x in value[name].split()]
        need(len(set(ids)) == 1, 'PROCESS_MIXED_IDS')
        expected = uid if name == 'Uid' else gid
        if expected is not None: need(ids == [expected] * 4, 'PROCESS_ID_BINDING')
    need(type(value['Groups']) is str and re.fullmatch(r'(?:[0-9]+(?:[ \t]+[0-9]+)*)?', value['Groups']), 'PROCESS_GROUPS')
    for name in ('CapEff', 'CapBnd', 'CapAmb'):
        need(type(value[name]) is str and re.fullmatch(r'[0-9a-f]{16}', value[name]), 'PROCESS_CAPABILITIES')
    need(value['NoNewPrivs'] in ('0', '1') and value['Seccomp'] in ('0', '1', '2'), 'PROCESS_SECURITY_FIELDS')


def _process(value, pid=None, uid=None, gid=None):
    keys(value, ('pid', 'starttime', 'status', 'cgroup_sha256'), 'PROCESS_FIELDS')
    integer(value['pid'], 1); integer(value['starttime']); sha(value['cgroup_sha256'])
    if pid is not None: need(value['pid'] == pid, 'PROCESS_PID_BINDING')
    _status(value['status'], uid, gid)
    return value


def _namespace(value):
    keys(value, ('pid', 'namespace', 'manager_namespace', 'helper_proc_view',
                 'same_pid_namespace', 'same_proc_namespace'), 'NAMESPACE_FIELDS')
    integer(value['pid'], 2)
    need(type(value['namespace']) is str and re.fullmatch(r'pid:\[[0-9]+\]', value['namespace']) and
         value['namespace'] == value['manager_namespace'] == value['helper_proc_view'] and
         value['same_pid_namespace'] is True and value['same_proc_namespace'] is True, 'NAMESPACE_UNVERIFIED')


def _unit(value, suffix, policy, paths):
    keys(value, helper.PROPS[suffix], 'UNIT_FIELDS')
    need(all(type(v) is str and len(v) <= 8192 and '\n' not in v and '[unprintable]' not in v
             for v in value.values()), 'UNIT_VALUE')
    unit = paths[suffix + '_unit']; expected = {
        'Id': unit, 'LoadState': 'loaded', 'NeedDaemonReload': 'no',
        'FragmentPath': '/run/systemd/system/' + unit, 'DropInPaths': ''}
    if suffix == 'socket':
        expected.update(Listen=paths['socket'] + ' (Stream)', Accept='no',
            Triggers=paths['service_unit'], SocketUser=policy['profiles']['ledger']['user'],
            SocketGroup='xuanjun-ledger-client', SocketMode='0660', DirectoryMode='0755', RemoveOnStop='yes')
    else:
        expected.update(User=policy['profiles']['ledger']['user'], Group=policy['profiles']['ledger']['group'],
            WorkingDirectory=paths['root'], TriggeredBy=paths['socket_unit'])
        command = (policy['python']['path'] + ' -B ' + paths['root'] + '/probe_helpers.py --config ' +
                   paths['root'] + '/helper-ledger-server.json --mode server')
        need(normalize_exec_start(value['ExecStart']) == 'path=' + policy['python']['path'] +
             ';argv[]=' + command + ';ignore_errors=no', 'UNIT_COMMAND')
        need(re.fullmatch(r'[0-9]+', value['MainPID']) and
             re.fullmatch(r'(?:[0-9a-f]{32})?', value['InvocationID']), 'UNIT_DYNAMIC_FORMAT')
    need(all(value[k] == v for k, v in expected.items()), 'UNIT_MECHANISM_BINDING')
    # Stop/restart cases deliberately observe different dynamic states. These
    # fields prove readable typed output, never a production activity approval.
    need(re.fullmatch(r'[a-z-]{1,32}', value['ActiveState']) and
         re.fullmatch(r'[a-z-]{1,32}', value['SubState']), 'UNIT_DYNAMIC_STATE')


def _readpaths(row, role, policy, paths, policy_sha):
    context = types.SimpleNamespace(policy=policy, paths=paths, policy_sha=policy_sha)
    config = probe.HostOps.helper_config(context, role, row['case'])
    public = {x['path']: x for x in config['public_files']}
    expected = {'manager-process', 'boot-id', 'self-pid-namespace',
                'metadata-only:fixture-activation.lock', 'metadata-only:fixture-dispatcher.json',
                'manager-unit:socket', 'manager-unit:service', 'manager-channel:/run/dbus/system_bus_socket'}
    if role == 'broker': expected.add('manager-channel:/run/systemd/private')
    expected.update('public:' + name for name in public)
    values = row['readpaths']
    need(type(values) is list and len(values) == len(expected), 'EXACT_READPATH_COUNT')
    by_name = {}
    for item in values:
        keys(item, ('path_class', 'status', 'evidence'), 'READPATH_FIELDS')
        name = item['path_class']
        need(type(name) is str and name in expected and name not in by_name and
             item['status'] == 'PASS_OBSERVED', 'READPATH_UNVERIFIED')
        by_name[name] = item['evidence']
    need(set(by_name) == expected, 'READPATH_COVERAGE')
    manager = _process(by_name['manager-process'], 1, 0)
    keys(by_name['boot-id'], ('sha256',), 'BOOT_FIELDS'); sha(by_name['boot-id']['sha256'])
    keys(by_name['self-pid-namespace'], ('link',), 'SELF_NAMESPACE_FIELDS')
    need(by_name['self-pid-namespace']['link'] == row['namespace_proof']['namespace'], 'SELF_NAMESPACE_BINDING')
    for name, value in by_name.items():
        if name.startswith('public:'):
            pin = public[name[7:]]; keys(value, ('sha256', 'size'), 'PUBLIC_FIELDS')
            integer(value['size']); need(value['sha256'] == pin['sha256'] and
                value['size'] <= pin['maximum'], 'PUBLIC_SOURCE_BINDING')
        elif name.startswith('manager-channel:'):
            keys(value, ('dev', 'ino', 'acl_sha256'), 'CHANNEL_FIELDS')
            integer(value['dev']); integer(value['ino'], 1); sha(value['acl_sha256'])
        elif name.startswith('metadata-only:'):
            keys(value, ('uid', 'gid', 'mode', 'acl_sha256', 'content_opened'), 'METADATA_FIELDS')
            need(type(value['uid']) is int and type(value['gid']) is int and type(value['mode']) is int and
                 (value['uid'], value['gid'], value['mode']) == (0, 0, 0o644) and
                 value['content_opened'] is False, 'METADATA_AUTHORITY')
            sha(value['acl_sha256'])
    for suffix in ('socket', 'service'): _unit(by_name['manager-unit:' + suffix], suffix, policy, paths)
    return manager, by_name['boot-id']['sha256']


def _resource_sources(receipt, policy, paths, source_files):
    context = types.SimpleNamespace(created=receipt['resources'], paths=paths)
    probe.HostOps.validate_created_scope(context)
    rows = {x['path']: x for x in receipt['resources']}
    expected = {paths['root'] + '/probe_helpers.py': policy['helper_sha256'],
                paths['root'] + '/probe-policy.json': digest(canonical(policy) + b'\n'),
                '/run/systemd/system/' + paths['socket_unit']: digest(probe.render_socket(policy))}
    expected.update({paths['root'] + '/candidate-' + name.rsplit('/', 1)[1]: pin
                     for name, pin in policy['candidate_sources'].items()})
    for role in probe.ROLES:
        name, raw = probe.render_unit(policy, role)
        expected['/run/systemd/system/' + name] = digest(raw)
    for path, pin in expected.items():
        need(path in rows and rows[path]['kind'] == 'FILE' and rows[path]['sha256'] == pin, 'CREATED_SOURCE_BINDING')
        info = rows[path]['identity']
        need((info['uid'], info['gid'], info['mode'], info['nlink']) == (0, 0, 0o644, 1), 'CREATED_SOURCE_AUTHORITY')


def _denials(value):
    keys(value, ('results', 'child_memory_unchanged', 'target', 'denied_callers', 'cleanup_errors', 'cleanup_state'), 'DENIAL_FIELDS')
    need(value['child_memory_unchanged'] is True and value['target'] == 'OWN_NONSECRET_FORK_CHILD' and
         value['denied_callers'] == 'THREE_TRACKED_FORK_CHILDREN' and value['cleanup_errors'] == [] and
         value['cleanup_state'] == 'REAPED', 'DENIAL_CLEANUP_OR_SENTINEL')
    rows = value['results']; need(type(rows) is list and len(rows) == 3, 'DENIAL_COUNT')
    for name, item in zip(('ptrace', 'process_vm_readv', 'process_vm_writev'), rows):
        extra = ('signal',) if type(item) is dict and 'signal' in item else ('return', 'errno')
        keys(item, ('syscall', 'status', 'cleanup_errors', 'cleanup_state') + extra, 'DENIAL_RESULT_FIELDS')
        need(item['syscall'] == name and item['status'] == 'PASS_OBSERVED' and
             item['cleanup_errors'] == [] and item['cleanup_state'] == 'REAPED', 'DENIAL_NOT_VERIFIED')
        if extra == ('signal',): need(type(item['signal']) is int and item['signal'] == 31, 'SIGSYS_REQUIRED')
        else: need(type(item['return']) is int and type(item['errno']) is int and
                   item['return'] == -1 and item['errno'] == 1, 'EPERM_REQUIRED')


def _server_records(records, cases, policy, paths, endpoint):
    need(type(records) is list and 1 <= len(records) <= 128, 'SERVER_RECORDS_BOUND')
    ready = 0; peers = {}
    for row in records:
        need(type(row) is dict, 'SERVER_RECORD')
        if row.get('event') == 'SERVER_READY':
            keys(row, ('event', 'own', 'listener', 'syscall_denials'), 'SERVER_READY_FIELDS'); ready += 1
            ledger = policy['profiles']['ledger']; own = _process(row['own'], uid=ledger['uid'], gid=ledger['gid'])
            need(own['pid'] > 1 and all(int(own['status'][k], 16) == 1 << 19 for k in ('CapEff','CapBnd','CapAmb')) and
                 own['status']['NoNewPrivs'] == '1' and own['status']['Seccomp'] == '2', 'LEDGER_SANDBOX')
            listener = row['listener']; keys(listener, ('dev','ino','uid','gid','mode','acl_sha256'), 'LISTENER_FIELDS')
            for name in ('dev','ino','uid','gid','mode'): integer(listener[name], 1 if name == 'ino' else 0)
            sha(listener['acl_sha256']); need(all(listener[k] == v for k,v in endpoint.items()), 'LISTENER_IDENTITY')
            _denials(row['syscall_denials'])
        elif row.get('event') == 'PEER_ACCESS_PROOF':
            keys(row, ('event', 'case', 'proof'), 'PEER_FIELDS'); case = row['case']
            need(type(case) is int and 1 <= case <= 8 and case not in peers, 'PEER_CASE')
            proof = row['proof']; keys(proof, ('status','pid','uid','argv_sha256','cgroup_sha256',
                'owner_fixture_criterion','production_owner_verifier'), 'PEER_PROOF_FIELDS')
            role = probe.CASES[case-1][1]; integer(proof['pid'], 2); sha(proof['cgroup_sha256'])
            argv = [policy['python']['path'], '-B', paths['root']+'/probe_helpers.py', '--config',
                    paths['root']+'/helper-'+role+'-client.json', '--mode', 'client']
            need(proof['status'] == 'PASS_OBSERVED' and type(proof['uid']) is int and
                 proof['uid'] == policy['profiles'][role]['uid'] and proof['pid'] == cases[case-1]['namespace_proof']['pid'] and
                 proof['argv_sha256'] == digest(b'\0'.join(x.encode() for x in argv)+b'\0') and
                 proof['owner_fixture_criterion'] is (role == 'callback') and
                 proof['production_owner_verifier'] == 'NOT_VERIFIED', 'PEER_ACCESS_UNVERIFIED')
            peers[case] = proof
        else:
            # Unknown diagnostics, child cleanup errors and SERVER_REJECT must
            # not be hidden behind the successful connection challenge.
            need(False, 'SERVER_DIAGNOSTIC_NOT_VERIFIED')
    need(1 <= ready <= 8 and set(peers).issuperset({1,2,3,4,5,7}), 'SERVER_PROOF_COVERAGE')


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


def validate_saved_unit_dropins(value):
    """A saved content/presence proof, never fresh directory authority metadata."""
    keys(value,('schema','kind','unit_metadata_sha256','dropins_section','dropins_section_sha256',
        'latecheck_section','latecheck_section_sha256','producer_sources','reread_provenance',
        'fresh_directory_authority','collection'),'SAVED_INVENTORY_FIELDS')
    need(type(value['schema']) is int and value['schema']==2 and value['kind']=='SAVED_R7_UNIT_DROPIN_INVENTORY' and
        value['reread_provenance']=='PINNED_COLLECTOR_TWO_READS_AND_FULL_ELEVEN_UNIT_LATE_RECHECK' and
        value['fresh_directory_authority']=='NOT_REPRESENTED_BY_SAVED_INVENTORY' and value['collection']=='NOT_RUN','SAVED_INVENTORY_SCOPE')
    for key in ('unit_metadata_sha256','dropins_section_sha256','latecheck_section_sha256'):sha(value[key])
    need(same(value['producer_sources'],SAVED_PRODUCER_PINS),'SAVED_PRODUCER_PINS')
    _saved_dropin_section(value['dropins_section'])
    _saved_latecheck_section(value['latecheck_section'],value['dropins_section']['evidence']['units'])
    for name in ('dropins','latecheck'):
        need(digest(canonical(value[name+'_section']))==value[name+'_section_sha256'],'SAVED_SECTION_DIGEST')
    need(len(canonical(value))<=262144,'SAVED_INVENTORY_BOUND')
    return copy.deepcopy(value)


def project_saved_unit_dropins(observation):
    """Derive only from the original authenticated complete observation in RAM."""
    metadata=observation.get('unit_metadata');need(type(metadata) is dict,'SAVED_METADATA_REQUIRED')
    need(type(metadata.get('schema')) is int and metadata['schema']==1 and
        metadata.get('kind')=='PRIVATE_UNIT_FACTS_UNREVIEWED' and metadata.get('state')=='COMPLETE_UNREVIEWED' and
        metadata.get('unsupported_sections')==[] and metadata.get('install_admission')=='NOT_GRANTED' and
        metadata.get('independent_acceptance')=='PENDING','SAVED_COMPLETE_METADATA')
    sha(observation.get('unit_metadata_sha256'))
    need(digest(canonical(metadata))==observation['unit_metadata_sha256'],'SAVED_METADATA_DIGEST')
    sections=metadata.get('sections');keys(sections,UNIT_SECTIONS,'SAVED_COMPLETE_SECTIONS')
    need(all(type(row) is dict and row.get('state')=='MEASURED_UNREVIEWED' and type(row.get('evidence')) is dict
             for row in sections.values()),'SAVED_ALL_SECTIONS_MEASURED')
    value={'schema':2,'kind':'SAVED_R7_UNIT_DROPIN_INVENTORY','unit_metadata_sha256':observation['unit_metadata_sha256'],
        'dropins_section':copy.deepcopy(sections['dropins']),'latecheck_section':copy.deepcopy(sections['command_resolutions']),
        'dropins_section_sha256':digest(canonical(sections['dropins'])),
        'latecheck_section_sha256':digest(canonical(sections['command_resolutions'])),
        'producer_sources':dict(SAVED_PRODUCER_PINS),
        'reread_provenance':'PINNED_COLLECTOR_TWO_READS_AND_FULL_ELEVEN_UNIT_LATE_RECHECK',
        'fresh_directory_authority':'NOT_REPRESENTED_BY_SAVED_INVENTORY','collection':'NOT_RUN'}
    validate_saved_unit_dropins(value)
    provenance=value['latecheck_section']['evidence']['provenance']
    need(provenance['manager_sha256']==digest(canonical(observation['evidence']['writers']['manager'])) and
        provenance['systemctl_sha256']==observation['policy']['executables']['systemctl']['sha256'],
        'SAVED_MANAGER_TOOL_BINDING')
    return value



def _topology(value):
    keys(value, ('schema','purpose','creator','endpoint_identity','clients',
        'exclusive_delivery_reviewed','systemd_version','evidence_records_sha256'), 'TOPOLOGY_FIELDS')
    need(type(value['schema']) is int and value['schema']==1 and value['purpose']=='ROOT_MANAGER_SHARED_INIT_PROOF' and
         value['exclusive_delivery_reviewed'] is True and type(value['systemd_version']) is int and
         value['systemd_version']==239, 'TOPOLOGY_CONTRACT')
    sha(value['evidence_records_sha256'])
    creator=value['creator'];keys(creator,('pid','uid','gid','exe','cgroup_sha256','pid_namespace_role'),'CREATOR_FIELDS')
    for name in ('pid','uid','gid'):integer(creator[name])
    need(creator['pid']==1 and creator['uid']==0 and creator['exe'] in ('/usr/lib/systemd/systemd','/lib/systemd/systemd') and
         creator['pid_namespace_role']=='SYSTEM_INIT_SHARED_WITH_CLIENTS','CREATOR_CONTRACT')
    sha(creator['cgroup_sha256'])
    endpoint=value['endpoint_identity'];keys(endpoint,('uid','gid','mode'),'ENDPOINT_FIELDS')
    for item in endpoint.values():integer(item)
    need(endpoint['uid']==1003 and endpoint['mode']==0o660,'ENDPOINT_CONTRACT')
    keys(value['clients'],('broker','dashboard','callback','native'),'CLIENTS')
    for row in value['clients'].values():
        keys(row,('same_pid_namespace','same_proc_namespace','readpaths_verified'),'CLIENT_FIELDS')
        need(all(item is True for item in row.values()),'CLIENT_UNVERIFIED')


def expected_review_body(topology_sha, bindings):
    sha(topology_sha); keys(bindings, BINDING_FIELDS, 'BINDING_FIELDS')
    for key,value in bindings.items():
        if key != 'source_files': sha(value)
    need(same(bindings['source_files'], SOURCE_PINS) and
         bindings['runtime_manifest_sha256'] == SOURCE_PINS['deploy/integration-manifest.json'], 'REVIEW_SOURCE_BINDING')
    return dict(copy.deepcopy(bindings), schema=2, reviewer='CHATGPT_NATIVE_TASK5', decision=DECISION,
        transaction_id=approval.TX, topology_sha256=topology_sha,
        evidence_mode='SAVED_R7_COMPLETE_OBSERVATION', future_fresh_preparation_checks='PENDING_SEPARATE_ADMISSION',
        exclusive_delivery_accepted=True, systemd_version_evidence='PINNED_DRIVER_CHECK_HOST_BEFORE_RECEIPT',
        production_resume_authorized=False, production_acceptance='PENDING')


def project_topology(observation, receipt_raw, receipt_metadata, authenticated_kit_sha256, source_files, saved_unit_dropins,
                     saved_projection_source_manifest_sha256):
    """No effects. The kit digest and receipt buffers originate protected reads.

    systemd239 is a source-enforced precondition: the pinned driver's check_host
    must finish before receipt creation. The receipt does not retain version
    stdout; the review body explicitly records this limit rather than inventing
    a second measurement. All namespace/readpath rows are actual receipt data.
    """
    sha(authenticated_kit_sha256); keys(source_files, SOURCE_PINS, 'SOURCE_FILE_SET')
    saved_unit_dropins=validate_saved_unit_dropins(saved_unit_dropins)
    need(same(saved_unit_dropins,project_saved_unit_dropins(observation)),'ORIGINAL_SAVED_INVENTORY_BINDING')
    sha(saved_projection_source_manifest_sha256)
    for name, pin in SOURCE_PINS.items():
        raw = source_files[name]
        need(type(raw) is bytes and 0 < len(raw) <= 1048576 and digest(raw) == pin, 'REVIEWED_SOURCE_PIN')
    need(type(observation) is dict and len(canonical(observation)) <= 64*1024*1024, 'OBSERVATION_BOUND')
    attempt = observation.get('finite_probe')
    result = attempt.get('result') if type(attempt) is dict else None
    need(type(result) is dict and result.get('incomplete_case') is None, 'INCOMPLETE_CASE')
    binding = node.authenticate_receipt_binding(receipt_raw, receipt_metadata, observation)
    receipt = node.parse(receipt_raw); attempt = observation['finite_probe']; policy = probe.validate_policy(attempt['policy'])
    need(policy['driver_sha256'] == SOURCE_PINS['probe_driver.py'] and
         policy['helper_sha256'] == SOURCE_PINS['probe_helpers.py'], 'PROBE_SOURCE_BINDING')
    manifest = probe.parse(source_files['deploy/integration-manifest.json'])
    need(type(manifest.get('files')) is dict and len(manifest['files']) == 107 and
         same(policy['candidate_sources'], {k:manifest['files'][k] for k in probe.CANDIDATE_SOURCES}), 'RUNTIME_SOURCE_BINDING')
    paths = probe.scope(policy); _resource_sources(receipt, policy, paths, source_files)
    events = receipt['events']; cases = attempt['result']['cases']
    observed = []; intents = []; records = []
    for event in events:
        keys(event, ('event','detail'), 'EVENT_FIELDS')
        name = event['event']; need(type(name) is str and re.fullmatch(r'[A-Z_]{1,64}',name), 'EVENT_NAME')
        if name == 'CASE_INTENT': intents.append(event['detail'])
        if name == 'CASE_OBSERVED':
            need(len(intents) == len(observed)+1, 'CASE_EVENT_ORDER'); observed.append(event['detail'])
        if name == 'OUTPUT_CAPTURED' and type(event['detail']) is dict and 'observations' in event['detail']:
            item = event['detail']; keys(item, ('path','sha256','bytes','observations'), 'CAPTURE_FIELDS')
            sha(item['sha256']); integer(item['bytes']); need(item['bytes'] <= 65536 and
                item['path'] == paths['root']+'/output-ledger.jsonl' and type(item['observations']) is list, 'CAPTURE_SCOPE')
            records.extend(item['observations'])
    need(same(intents,[{'case':i,'role':r,'kind':k} for i,r,k in probe.CASES]) and
         same(observed,cases), 'CASE_RECEIPT_BINDING')
    need(same(records,attempt['result'].get('server_observations')), 'SERVER_RECEIPT_BINDING')
    managers=[]; boots=[]; namespaces=[]
    for row,(number,role,kind) in zip(cases,probe.CASES):
        common={'case','status','production_verifier_admission','readpaths','owner_process_gate','namespace_proof'}
        common.update(('reason','bound_before_failure','expected_rejection_observed') if number in (6,8) else ('mechanism','peer'))
        if role == 'native': common.add('sdk')
        keys(row,common,'CASE_FIELDS'); _namespace(row['namespace_proof']); namespaces.append(row['namespace_proof']['namespace'])
        need(row['production_verifier_admission'] == 'NOT_VERIFIED' and
             row['owner_process_gate'] == 'NOT_VERIFIED_FIXED_PRODUCTION_PROCESS_PINS_NOT_REMAPPED', 'NO_PRODUCTION_VERIFIER_CLAIM')
        manager,boot = _readpaths(row,role,policy,paths,binding['policy_sha256']); managers.append(manager); boots.append(boot)
        gid=int(manager['status']['Gid'].split()[0])
        if number not in (6,8):
            need(row['mechanism']=='INHERITED_MANAGER_CHALLENGE' and type(row['peer']) is list and
                 all(type(v) is int for v in row['peer']) and row['peer']==[1,0,gid], 'KERNEL_PEER_IDENTITY')
        else: need(row['bound_before_failure'] is True and type(row['reason']) is str and len(row['reason'])<=200,'BOUNDED_RACE_RESULT')
        if role == 'native':
            expected=[{'path':x['path'],'status':'PASS_OBSERVED','size':x['size'],'sha256':x['sha256']} for x in policy['sdk_bindings']]
            need(same(row['sdk'],expected),'SDK_ACCESS_NOT_VERIFIED')
    need(all(same(x,managers[0]) for x in managers) and len(set(boots))==len(set(namespaces))==1, 'MANAGER_LIFETIME_OR_NAMESPACE_CHANGED')
    socket = receipt.get('socket_identity'); keys(socket,('dev','ino','uid','gid','mode'),'ENDPOINT_FIELDS')
    for key,value in socket.items(): integer(value,1 if key=='ino' else 0)
    endpoint={k:socket[k] for k in ('uid','gid','mode')}
    need(endpoint=={'uid':policy['profiles']['ledger']['uid'],
        'gid':policy['profiles']['broker']['supplementary_groups']['xuanjun-ledger-client'],'mode':0o660}, 'ENDPOINT_IDENTITY')
    _server_records(records,cases,policy,paths,endpoint)
    evidence_sha=digest(canonical({'events':events,'resources':receipt['resources'],'socket_identity':socket,'saved_unit_dropins':saved_unit_dropins}))
    creator={'pid':1,'uid':0,'gid':int(managers[0]['status']['Gid'].split()[0]),
        'exe':next(x['path'] for x in policy['public_files'] if x['path']!='/usr/bin/systemctl'),
        'cgroup_sha256':managers[0]['cgroup_sha256'],'pid_namespace_role':'SYSTEM_INIT_SHARED_WITH_CLIENTS'}
    topology={'schema':1,'purpose':'ROOT_MANAGER_SHARED_INIT_PROOF','creator':creator,
        'endpoint_identity':endpoint,'clients':{role:{'same_pid_namespace':True,'same_proc_namespace':True,
        'readpaths_verified':True} for role in ('broker','dashboard','callback','native')},
        'exclusive_delivery_reviewed':True,'systemd_version':239,'evidence_records_sha256':evidence_sha}
    raw=canonical(topology)+b'\n'; bindings={'recovery_kit_manifest_sha256':authenticated_kit_sha256,
        'runtime_manifest_sha256':policy['runtime_manifest_sha256'],'observation_sha256':digest(canonical(observation)),
        'probe_policy_sha256':binding['policy_sha256'],'probe_receipt_sha256':digest(receipt_raw),
        'probe_input_sha256':binding['input_sha256'],'source_files':dict(SOURCE_PINS),'evidence_records_sha256':evidence_sha,
        'saved_unit_dropins_sha256':digest(canonical(saved_unit_dropins)),
        'saved_projection_source_manifest_sha256':saved_projection_source_manifest_sha256}
    return {'schema':2,'kind':'UNSIGNED_R7_SAVED_TOPOLOGY_PROPOSAL_NO_RESUME_AUTHORITY','topology':topology,
        'topology_raw':raw,'topology_sha256':digest(raw),'bindings':bindings,
        'expected_review_body':expected_review_body(digest(raw),bindings)}


def _wanted(proposal):
    keys(proposal,PROPOSAL_FIELDS,'PROPOSAL_FIELDS')
    _topology(proposal['topology'])
    need(type(proposal['schema']) is int and proposal['schema']==2 and
         proposal['kind']=='UNSIGNED_R7_SAVED_TOPOLOGY_PROPOSAL_NO_RESUME_AUTHORITY' and
         type(proposal['topology_raw']) is bytes and len(proposal['topology_raw'])<=131072 and
         proposal['topology_raw']==canonical(proposal['topology'])+b'\n' and
         digest(proposal['topology_raw'])==proposal['topology_sha256'] and
         proposal['topology']['evidence_records_sha256']==proposal['bindings']['evidence_records_sha256'], 'PROPOSAL_BINDING')
    wanted=expected_review_body(proposal['topology_sha256'],proposal['bindings'])
    need(same(wanted,proposal['expected_review_body']),'PROPOSAL_REVIEW_BINDING')
    return wanted


def authenticate_topology_review(raw_github_response, real_id, proposal):
    """Existing account/destination/ID/body authentication; no new reviewer ID.

    A raw response must originate the existing authenticated fetch (or an
    equivalently authenticated reader). This pure check cannot authenticate a
    caller-created JSON response, nor replace genuine independent review.
    """
    value=approval.validate(raw_github_response,real_id,_wanted(proposal))
    return {'review_id':value['review_id'],'approval_body_sha256':value['body_sha256'],
            'evidence_sha256':proposal['topology_sha256']}


def fetch_topology_review(real_id, proposal):
    """Explicit existing bounded HTTPS fetch; never called during projection."""
    value=approval.fetch(real_id,_wanted(proposal))
    return {'review_id':value['review_id'],'approval_body_sha256':value['body_sha256'],
            'evidence_sha256':proposal['topology_sha256']}
