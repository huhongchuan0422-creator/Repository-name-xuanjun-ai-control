"""Pure source/provenance compiler for the chosen reboot-capable server policy.
No measurements, approval authentication, publication, service or socket calls.
"""
import copy
import re
import os.path
import json
import epoch7_delta as d
import epoch7_additive_identity as a

VALIDATOR_CONTRACT_SHA256 = 'bb47927facbd55589aed2303d0cd201a071cad4de41d71f1dcb150287bd8cbab'
PATH = '/etc/xuanjun-development/p2-ledger-server-identity.json'
SOCKET_PATH = '/run/xuanjun-development/ledger.sock'
CONFIG_PATH = '/etc/xuanjun-development/dispatcher.json'
SOCKET_UNIT = 'xuanjun-ledger.socket'
SERVICE_UNIT = 'xuanjun-ledger.service'
COMMON = ('Id', 'LoadState', 'NeedDaemonReload', 'FragmentPath', 'DropInPaths')
UNIT_PROPERTIES = {
    SOCKET_UNIT: COMMON + ('Listen', 'Accept', 'Triggers', 'SocketUser', 'SocketGroup',
                          'SocketMode', 'DirectoryMode', 'RemoveOnStop'),
    SERVICE_UNIT: COMMON + ('User', 'Group', 'ExecStart', 'WorkingDirectory', 'TriggeredBy')}
HEX = re.compile(r'^[0-9a-f]{64}$')
POLICY_KEYS = {'schema', 'trust_model', 'exclusive_delivery_reviewed', 'activation_binding',
               'creator', 'endpoint', 'files', 'units'}
CREATOR_KEYS = {'pid', 'uid', 'gid', 'exe', 'cgroup_sha256',
                'pid_namespace_role', 'topology_evidence_sha256'}
ENDPOINT_KEYS = {'path', 'uid', 'gid', 'mode'}
BINDING_KEYS = {'release_sha256', 'binary_sha256', 'ledger_uuid', 'generation',
                'epoch', 'instance', 'db_path', 'ledger_socket'}
PROFILES = frozenset(('broker', 'dashboard', 'callback', 'native'))


def _fail(reason): raise ValueError('SERVER_POLICY_' + reason)
def _canonical(path):
    return type(path) is str and path.startswith('/') and '\x00' not in path and len(path) <= 4096 and os.path.normpath(path) == path

def _unit_path(path, unit):
    prefix = '/etc/systemd/system/' + unit
    return path == prefix or (path.startswith(prefix + '.d/') and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.conf', path[len(prefix) + 3:]))

def expected_exec_start(release):
    return 'path=/usr/bin/python3;argv[]=/usr/bin/python3 ' + release + '/ledger_service.py --config ' + CONFIG_PATH + ';ignore_errors=no'

def _json(raw): return a.strict_json(raw, 65536)

def validate_policy(value):
    if (type(value) is not dict or set(value) != POLICY_KEYS or type(value['schema']) is not int
            or value['schema'] != 2 or value['trust_model'] != 'ROOT_MANAGER_DELIVERY_V1'
            or value['exclusive_delivery_reviewed'] is not True): _fail('EXACT_POLICY_REQUIRED')
    binding = value['activation_binding']
    if type(binding) is not dict or set(binding) != BINDING_KEYS: _fail('ACTIVATION_BINDING')
    # The aggregate config hash may include this policy. Pin relevant config
    # files directly instead, avoiding a recursive hash; full ACTIVE descriptor
    # (including config_sha256) must remain identical throughout each session.
    active = dict(binding, schema=1, state='PREPARED', config_sha256='0' * 64)
    d.validate_activation(active, 8, binding['release_sha256'])
    if active['ledger_socket'] != SOCKET_PATH: _fail('ACTIVE_BINDING_REQUIRED')
    creator = value['creator']
    if type(creator) is not dict or set(creator) != CREATOR_KEYS: _fail('CREATOR_FIELDS')
    for field in ('pid', 'uid', 'gid'):
        minimum = 1 if field == 'pid' else 0
        if type(creator[field]) is not int or not minimum <= creator[field] < 2**63: _fail('CREATOR_INTEGER')
    # Explicit values are mandatory; zero UID is a constraint, never a default.
    if (creator['pid'] != 1 or creator['uid'] != 0 or not _canonical(creator['exe'])
            or creator['pid_namespace_role'] != 'SYSTEM_INIT_SHARED_WITH_CLIENTS'
            or not isinstance(creator['topology_evidence_sha256'], str)
            or not HEX.fullmatch(creator['topology_evidence_sha256'])): _fail('MEASURED_INIT_MANAGER_REQUIRED')
    if creator['exe'] not in ('/usr/lib/systemd/systemd', '/lib/systemd/systemd'):
        _fail('MANAGER_IMAGE_PATH')
    if not isinstance(creator['cgroup_sha256'], str) or not HEX.fullmatch(creator['cgroup_sha256']):
        _fail('CREATOR_CGROUP')
    endpoint = value['endpoint']
    if (type(endpoint) is not dict or set(endpoint) != ENDPOINT_KEYS or endpoint['path'] != SOCKET_PATH
            or type(endpoint['mode']) is not int or endpoint['mode'] != 0o660): _fail('ENDPOINT_FIELDS')
    for field in ('uid', 'gid'):
        if type(endpoint[field]) is not int or endpoint[field] < 0:
            _fail('ENDPOINT_INTEGER')
    units, files = value['units'], value['files']
    if type(units) is not dict or set(units) != set(UNIT_PROPERTIES) or type(files) is not dict:
        _fail('UNITS_FILES')
    release = '/opt/xuanjun-control-releases/integration-' + active['release_sha256'][:16] + '/stage1'
    needed = {release + '/ledger_service.py', '/usr/bin/systemctl', creator['exe']}
    for unit, fields in UNIT_PROPERTIES.items():
        item = units[unit]
        if type(item) is not dict or set(item) != set(fields): _fail('UNIT_PROPERTIES')
        if any(type(v) is not str or len(v) > 8192 or '\n' in v or '[unprintable]' in v
               for v in item.values()): _fail('UNIT_VALUE')
        if (item['Id'] != unit or item['LoadState'] != 'loaded' or item['NeedDaemonReload'] != 'no'
                or item['FragmentPath'] != '/etc/systemd/system/' + unit): _fail('UNIT_LOADED_BINDING')
        paths = [item['FragmentPath']] + item['DropInPaths'].split()
        if len(paths) > 9 or len(paths) != len(set(paths)) or any(not _unit_path(p, unit) for p in paths):
            _fail('UNIT_FILE_PATHS')
        needed.update(paths)
    socket_unit = units[SOCKET_UNIT]
    if any(socket_unit[key] != expected for key, expected in {
            'Listen': SOCKET_PATH + ' (Stream)', 'Accept': 'no', 'Triggers': SERVICE_UNIT,
            'SocketUser': 'xuanjun-dispatcher', 'SocketGroup': 'xuanjun-ledger-client',
            'SocketMode': '0660', 'DirectoryMode': '0711', 'RemoveOnStop': 'yes'}.items()):
        _fail('SOCKET_UNIT_BINDING')
    service = units[SERVICE_UNIT]
    if (service['User'] != 'xuanjun-dispatcher' or service['Group'] != 'xuanjun-control-db'
            or service['TriggeredBy'] != SOCKET_UNIT or service['WorkingDirectory'] != release
            or service['ExecStart'] != expected_exec_start(release)): _fail('SERVICE_UNIT_BINDING')
    if set(files) != needed or any(not isinstance(v, str) or not HEX.fullmatch(v) for v in files.values()):
        _fail('EXACT_FILE_PINS')
    # Defensive deep copy: caller mutations never change an admitted policy.
    return _json(json.dumps(value, sort_keys=True, allow_nan=False).encode('utf-8'))


def validate_absence(before):
    clone = copy.deepcopy(before)
    d.need(isinstance(clone, dict) and clone.get('path') == PATH, 'SERVER_EXACT_ABSENCE')
    clone['path'] = a.PATH; a.validate_absence(clone)


def compile_addition(raw, expected_sha256, manifest_raw, manifest_sha256,
                     sources, topology_raw, topology_review, absence):
    """Sources are exact nonsecret pinned file bytes; topology is separately reviewed.

    This proves input consistency only. The external loader authenticates the
    topology review and verifies measured evidence, never just these assertions.
    """
    d.hash_value(expected_sha256); d.hash_value(manifest_sha256)
    d.need(a.raw_sha(raw) == expected_sha256 and a.raw_sha(manifest_raw) == manifest_sha256,
           'SERVER_EXACT_INPUT_HASHES')
    policy = validate_policy(_json(raw))
    d.need(policy['activation_binding']['release_sha256'] == manifest_sha256 and manifest_sha256 != d.OLD_MANIFEST,
           'SERVER_NEW_RELEASE_BINDING')
    manifest = a.strict_json(manifest_raw, 1048576)
    d.need(isinstance(manifest, dict) and isinstance(manifest.get('files'), dict), 'SERVER_SOURCE_MANIFEST')
    service = '/opt/xuanjun-control-releases/integration-' + manifest_sha256[:16] + '/stage1/ledger_service.py'
    d.need(manifest['files'].get('stage1/ledger_service.py') == policy['files'][service], 'SERVER_SERVICE_SOURCE')
    validator_sha = manifest['files'].get('stage1/ledger_server_identity.py'); d.hash_value(validator_sha)
    d.need(validator_sha == VALIDATOR_CONTRACT_SHA256, 'SERVER_REVIEWED_VALIDATOR_CONTRACT')
    d.keys(sources, policy['files'], 'SERVER_EXACT_SOURCE_BYTES')
    for path, payload in sources.items():
        maximum = 32 * 1024 * 1024 if path in (policy['creator']['exe'], '/usr/bin/systemctl') else 262144
        d.need(isinstance(payload, bytes) and len(payload) <= maximum and
               a.raw_sha(payload) == policy['files'][path], 'SERVER_SOURCE_HASH_OR_BOUND')
    topology = a.strict_json(topology_raw, 131072)
    d.keys(topology, ('schema', 'purpose', 'creator', 'endpoint_identity', 'clients',
                     'exclusive_delivery_reviewed', 'systemd_version', 'evidence_records_sha256'), 'SERVER_TOPOLOGY_KEYS')
    d.need(type(topology['schema']) is int and topology['schema'] == 1 and
           topology['purpose'] == 'ROOT_MANAGER_SHARED_INIT_PROOF' and
           topology['exclusive_delivery_reviewed'] is True and
           type(topology['systemd_version']) is int and topology['systemd_version'] == 239,
           'SERVER_TOPOLOGY_CONTRACT')
    d.hash_value(topology['evidence_records_sha256'])
    d.need(d.same(topology['creator'], {k: v for k, v in policy['creator'].items() if k != 'topology_evidence_sha256'})
           and d.same(topology['endpoint_identity'], {k: policy['endpoint'][k] for k in ('uid', 'gid', 'mode')}),
           'SERVER_MEASURED_CREATOR_ENDPOINT')
    d.keys(topology['clients'], PROFILES, 'SERVER_ALL_CLIENT_PROFILES')
    for row in topology['clients'].values():
        d.keys(row, ('same_pid_namespace', 'same_proc_namespace', 'readpaths_verified'), 'SERVER_CLIENT_PROOF_KEYS')
        d.need(all(value is True for value in row.values()), 'SERVER_CLIENT_CONTEXT_UNVERIFIED')
    topology_sha = a.raw_sha(topology_raw)
    d.need(policy['creator']['topology_evidence_sha256'] == topology_sha, 'SERVER_TOPOLOGY_EXACT_HASH')
    d.keys(topology_review, ('review_id', 'approval_body_sha256', 'evidence_sha256'), 'SERVER_TOPOLOGY_REVIEW_KEYS')
    d.need(type(topology_review['review_id']) is int and topology_review['review_id'] > 0 and
           topology_review['review_id'] not in d.CONSUMED and topology_review['evidence_sha256'] == topology_sha,
           'SERVER_INDEPENDENT_TOPOLOGY_REVIEW')
    d.hash_value(topology_review['approval_body_sha256'])
    validate_absence(absence)
    return {'schema': 1, 'kind': 'OFFLINE_ADDITIVE_IDENTITY_NOT_INSTALL_PLAN',
        'purpose': 'LEDGER_SERVER_IDENTITY_PINS', 'path': PATH,
        'operation': 'CREATE_EXCLUSIVE_PROTECTED_FILE', 'before': copy.deepcopy(absence),
        'after': {'kind': 'FILE', 'uid': 0, 'gid': 0, 'mode': 0o644, 'sha256': expected_sha256},
        'provenance': {'runtime_manifest_sha256': manifest_sha256,
            'activation_binding_sha256': d.digest(policy['activation_binding']),
            'validator_source_sha256': validator_sha, 'source_files': copy.deepcopy(policy['files']),
            'topology_evidence_sha256': topology_sha, 'topology_review': copy.deepcopy(topology_review),
            'config_schema': 2},
        'actual_host_pins_verified': False, 'permission_applied': False,
        'requires_complete_new_review': True, 'install_admission': 'NOT_GRANTED'}


def validate_compiled(addition, manifest_sha256):
    d.keys(addition, ('schema', 'kind', 'purpose', 'path', 'operation', 'before', 'after', 'provenance',
        'actual_host_pins_verified', 'permission_applied', 'requires_complete_new_review', 'install_admission'),
        'SERVER_COMPILED_SCHEMA')
    d.need(type(addition['schema']) is int and addition['schema'] == 1 and
        addition['kind'] == 'OFFLINE_ADDITIVE_IDENTITY_NOT_INSTALL_PLAN' and
        addition['purpose'] == 'LEDGER_SERVER_IDENTITY_PINS' and addition['path'] == PATH and
        addition['operation'] == 'CREATE_EXCLUSIVE_PROTECTED_FILE' and addition['permission_applied'] is False and
        addition['actual_host_pins_verified'] is False and addition['requires_complete_new_review'] is True and
        addition['install_admission'] == 'NOT_GRANTED', 'SERVER_COMPILED_SCOPE')
    d.validate_file(addition['after'], observed=False)
    d.need((addition['after']['uid'], addition['after']['gid'], addition['after']['mode']) == (0, 0, 0o644),
           'SERVER_EXACT_METADATA')
    p = addition['provenance']
    d.keys(p, ('runtime_manifest_sha256', 'activation_binding_sha256', 'validator_source_sha256',
        'source_files', 'topology_evidence_sha256', 'topology_review', 'config_schema'), 'SERVER_PROVENANCE')
    for key in ('runtime_manifest_sha256', 'activation_binding_sha256', 'validator_source_sha256',
                'topology_evidence_sha256'): d.hash_value(p[key])
    d.need(p['runtime_manifest_sha256'] == manifest_sha256 and type(p['config_schema']) is int and
           p['config_schema'] == 2 and p['validator_source_sha256'] == VALIDATOR_CONTRACT_SHA256 and isinstance(p['source_files'], dict) and p['source_files'], 'SERVER_PROVENANCE_BINDING')
    for path, sha in p['source_files'].items(): a.lexical_path(path); d.hash_value(sha)
    review = p['topology_review']; d.keys(review, ('review_id', 'approval_body_sha256', 'evidence_sha256'), 'SERVER_TOPOLOGY_REVIEW_KEYS')
    d.need(type(review['review_id']) is int and review['review_id'] > 0 and review['review_id'] not in d.CONSUMED and
           review['evidence_sha256'] == p['topology_evidence_sha256'], 'SERVER_INDEPENDENT_TOPOLOGY_REVIEW')
    d.hash_value(review['approval_body_sha256']); validate_absence(addition['before'])
    return copy.deepcopy(addition)
