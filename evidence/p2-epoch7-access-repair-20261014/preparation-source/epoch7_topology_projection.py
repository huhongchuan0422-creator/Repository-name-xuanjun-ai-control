"""Pure projection and first-receipt validation for one complete recovery audit.

The caller authenticates the kit/cache and reads the root-owned nonce receipt
through the existing protected loader. This module performs no host I/O. A
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
    'probe_driver.py': '369978247a4cc5d27aca3fc7ae2dae8484ab4217f4ac9256cad2bcd94105caa3',
    'probe_helpers.py': '1d58d66efad61341cb3f6ff9d8ed6cc2c497c4261224d3a4b6fe6eb7ef18efe5',
    'node_sqlite_probe.py': '50fc45de2684e8542cb61d773f8cea044ee9b3b4c61d7b9f00ff555b56817d2c',
    'deploy/integration-manifest.json': '26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa'}
DECISION = 'ACCEPTED_EXACT_EPOCH7_ROOT_MANAGER_TOPOLOGY_ONLY'
STATUS_FIELDS = {'Uid', 'Gid', 'Groups', 'CapEff', 'CapBnd', 'CapAmb', 'NoNewPrivs', 'Seccomp'}
BINDING_FIELDS = {'recovery_kit_manifest_sha256', 'runtime_manifest_sha256',
    'observation_sha256', 'probe_policy_sha256', 'probe_receipt_sha256',
    'probe_input_sha256', 'source_files', 'evidence_records_sha256', 'socket_dropins_sha256', 'preparation_source_manifest_sha256'}
SOCKET_DROPIN_PATHS = tuple(root + '/xuanjun-ledger.socket.d' for root in
    ('/etc/systemd/system', '/run/systemd/system', '/usr/lib/systemd/system'))
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


def validate_socket_dropins(value):
    """Pure proof shape; protected no-follow sampling remains the caller's job."""
    keys(value, ('schema','unit','roots','reread'), 'SOCKET_DROPIN_FIELDS')
    need(type(value['schema']) is int and value['schema']==1 and
         value['unit']=='xuanjun-ledger.socket' and value['reread']=='EXACT_PRE_POST', 'SOCKET_DROPIN_SCOPE')
    keys(value['roots'], SOCKET_DROPIN_PATHS, 'SOCKET_DROPIN_ROOTS')
    for path,row in value['roots'].items():
        keys(row, ('present','metadata','parent_metadata','files'), 'SOCKET_DROPIN_ROW')
        need(type(row['present']) is bool and type(row['files']) is dict and not row['files'],
             'SOCKET_DROPIN_UNSUPPORTED_CONTENT')
        if not row['present']: need(row['metadata'] is None, 'ABSENT_DROPIN_METADATA')
        for info in [row['parent_metadata']] + ([row['metadata']] if row['present'] else []):
            keys(info, META, 'SOCKET_DROPIN_METADATA')
            for key,item in info.items(): integer(item, 1 if key in ('ino','nlink') else 0)
            need(info['uid']==info['gid']==0 and info['mode']<=0o777 and not info['mode']&0o022,
                 'SOCKET_DROPIN_AUTHORITY')
    return copy.deepcopy(value)


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
    return dict(copy.deepcopy(bindings), schema=1, reviewer='CHATGPT_NATIVE_TASK5', decision=DECISION,
        transaction_id=approval.TX, topology_sha256=topology_sha,
        exclusive_delivery_accepted=True, systemd_version_evidence='PINNED_DRIVER_CHECK_HOST_BEFORE_RECEIPT',
        production_resume_authorized=False, production_acceptance='PENDING')


def project_topology(observation, receipt_raw, receipt_metadata, authenticated_kit_sha256, source_files, socket_dropins,
                     preparation_source_manifest_sha256):
    """No effects. The kit digest and receipt buffers originate protected reads.

    systemd239 is a source-enforced precondition: the pinned driver's check_host
    must finish before receipt creation. The receipt does not retain version
    stdout; the review body explicitly records this limit rather than inventing
    a second measurement. All namespace/readpath rows are actual receipt data.
    """
    sha(authenticated_kit_sha256); keys(source_files, SOURCE_PINS, 'SOURCE_FILE_SET')
    socket_dropins=validate_socket_dropins(socket_dropins)
    sha(preparation_source_manifest_sha256)
    for name, pin in SOURCE_PINS.items():
        raw = source_files[name]
        need(type(raw) is bytes and 0 < len(raw) <= 1048576 and digest(raw) == pin, 'REVIEWED_SOURCE_PIN')
    need(type(observation) is dict and len(canonical(observation)) <= 64*1024*1024, 'OBSERVATION_BOUND')
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
    evidence_sha=digest(canonical({'events':events,'resources':receipt['resources'],'socket_identity':socket,'socket_dropins':socket_dropins}))
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
        'socket_dropins_sha256':digest(canonical(socket_dropins)),
        'preparation_source_manifest_sha256':preparation_source_manifest_sha256}
    return {'schema':1,'kind':'UNSIGNED_TOPOLOGY_PROPOSAL_NO_RESUME_AUTHORITY','topology':topology,
        'topology_raw':raw,'topology_sha256':digest(raw),'bindings':bindings,
        'expected_review_body':expected_review_body(digest(raw),bindings)}


def _wanted(proposal):
    keys(proposal,PROPOSAL_FIELDS,'PROPOSAL_FIELDS')
    _topology(proposal['topology'])
    need(type(proposal['schema']) is int and proposal['schema']==1 and
         proposal['kind']=='UNSIGNED_TOPOLOGY_PROPOSAL_NO_RESUME_AUTHORITY' and
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
