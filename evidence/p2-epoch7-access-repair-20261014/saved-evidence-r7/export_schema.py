"""Pure, fail-closed public-metadata schema for the one saved R7 probe.

This adds export safety to the authenticated frozen topology projection; it is
not provenance, review, approval, or permission to collect or resume anything.
The caller must authenticate the modules, run project_topology on the ORIGINAL
full observation, and prove canonical(receipt)+LF equals the protected original
receipt bytes before calling. No values are redacted, rewritten, or returned.
Python 3.6.8 compatible. This module performs no I/O and imports no host adapter.
"""
import hashlib
import json
import re

NONCE = 'cee45858d9d19863e977e2648bc2196a'
NODE_PATH = '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node'
SDK_ROOT = '/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/'
# Exact fixed public source paths are populated from the reviewed source profile.
SDK_PATHS = frozenset((SDK_ROOT + 'dist/context-Dt2Gy7El.mjs',
    SDK_ROOT + 'dist/context-DyPstb2Q.mjs',
    SDK_ROOT + 'dist/agent-tools.before-tool-call.runtime-DrbwqsOU.mjs',
    SDK_ROOT + 'dist/error-runtime-B-G5NrRT.mjs',
    SDK_ROOT + 'dist/runtime-BgTk9ZFM.mjs'))
CANDIDATE_PINS = {
    'stage1/ledger_service.py': '6c254ed8d36f1eac692636ad482924a9cfb0d4567831aaa67814275ef68388ef',
    'stage1/ledger_server_identity.py': 'c18b35dcaa1c9abb0ce926e5e044e131b222c3b6960af6aa40ce451c3502cd33',
    'stage1/activation_control.py': '169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4'}
META = frozenset(('dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns'))
ATTEMPT = frozenset(('schema', 'nonce', 'stage', 'operator_acknowledgement_is_external_approval_proof',
    'resume_authority', 'policy', 'policy_sha256', 'result'))
RESULT = frozenset(('schema', 'cases', 'node_sqlite', 'created_receipt', 'server_observations',
    'failure', 'cleanup', 'last_command_cleanup', 'intentionally_retained', 'production_acceptance',
    'resume_authority', 'operator_acknowledgement_is_external_approval_proof'))
RECEIPT = frozenset(('schema', 'purpose', 'nonce', 'policy_sha256', 'operator_acknowledged',
    'external_approval_authenticated', 'attempt_consumed', 'connections_reserved', 'accepted_connections',
    'stage', 'resources', 'events', 'cleanup', 'socket_identity'))
ACTIVE_STATES = frozenset(('active', 'reloading', 'inactive', 'failed', 'activating', 'deactivating'))
SUB_STATES = frozenset(('dead', 'start-pre', 'start', 'start-post', 'running', 'exited', 'reload',
    'stop', 'stop-watchdog', 'stop-sigterm', 'stop-sigkill', 'stop-post', 'final-sigterm',
    'final-sigkill', 'failed', 'auto-restart', 'listening', 'stop-pre', 'stop-pre-sigterm',
    'stop-pre-sigkill', 'stop-post-sigterm', 'stop-post-sigkill'))
RACE_REASONS = frozenset((
    'BrokenPipeError:[Errno 32] Broken pipe',
    'ConnectionResetError:[Errno 104] Connection reset by peer',
    'ConnectionAbortedError:[Errno 103] Software caused connection abort',
    'TimeoutError:timed out', 'timeout:timed out', 'TimeoutError:HELPER_DEADLINE',
    'ValueError:EARLY_EOF', 'ValueError:FRAME_BOUND', 'ValueError:ONE_FRAME_REQUIRED',
    'ValueError:NONCE_RESPONSE', 'ValueError:TRAILING_RESPONSE',
    'ValueError:SESSION_IDENTITY_CHANGED', 'ValueError:RELEASE_BINDING'))


def need(condition, label):
    if not condition:
        # Never include any input bytes, input keys, path, or exception text.
        raise ValueError('EXPORT_SCHEMA_' + label)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def same(left, right):
    return canonical(left) == canonical(right)


def keys(value, expected, label):
    need(type(value) is dict and set(value) == set(expected), label)


def integer(value, minimum=0, maximum=(1 << 63) - 1):
    need(type(value) is int and minimum <= value <= maximum, 'INTEGER')


def sha(value):
    need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value), 'SHA256')


def bounded_json(value, depth=0, budget=None):
    """Complexity/type guard only. This DOES NOT authorize any string export."""
    if budget is None:
        budget = [0]
    budget[0] += 1
    need(depth <= 24 and budget[0] <= 45000, 'JSON_COMPLEXITY')
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        integer(value, -1, (1 << 64) - 1)
    elif type(value) is str:
        need(len(value) <= 2048 and '\x00' not in value, 'JSON_STRING_BOUND')
    elif type(value) is list:
        need(len(value) <= 512, 'JSON_LIST_BOUND')
        for item in value:
            bounded_json(item, depth + 1, budget)
    elif type(value) is dict:
        need(len(value) <= 64 and all(type(k) is str and len(k) <= 512 for k in value), 'JSON_OBJECT_BOUND')
        for item in value.values():
            bounded_json(item, depth + 1, budget)
    else:
        need(False, 'JSON_TYPE')


def metadata(value, file_mode=None):
    keys(value, META, 'METADATA_KEYS')
    for key, item in value.items():
        integer(item, 1 if key in ('ino', 'nlink') else 0, (1 << 64) - 1)
    integer(value['mode'], 0, 0o7777)
    for key in ('uid', 'gid'):
        integer(value[key], 0, (1 << 32) - 1)
    if file_mode is not None:
        need((value['uid'], value['gid'], value['mode'], value['nlink']) == (0, 0, file_mode, 1), 'FILE_AUTHORITY')


def resources_for(policy, probe):
    paths = probe.scope(policy)
    root = paths['root']
    units = set([paths['socket_unit'], paths['service_unit']] + list(paths['client_units'].values()))
    leaves = {'probe_helpers.py', 'node-sqlite-probe.cjs', 'connection-budget.json', 'probe-policy.json',
        'fixture-activation.json', 'fixture-epochs.jsonl', 'fixture-activation.lock',
        'fixture-dispatcher.json', 'release-06.json', 'release-08.json'}
    leaves.update('candidate-' + relative.rsplit('/', 1)[1] for relative in probe.CANDIDATE_SOURCES)
    for role in probe.ROLES:
        leaves.add('helper-' + role + ('-server.json' if role == 'ledger' else '-client.json'))
        leaves.add('output-' + role + '.jsonl')
        leaves.add('error-' + role + '.txt')
    files = set(root + '/' + leaf for leaf in leaves)
    files.update('/run/systemd/system/' + unit for unit in units)
    return paths, files, units


def policy_schema(value, t):
    p = t.probe
    p.validate_policy(value)
    need(value['nonce'] == NONCE and value['hostname'] == p.EXPECTED_HOST, 'FIXED_PROBE_SCOPE')
    need(value['driver_sha256'] == t.SOURCE_PINS['probe_driver.py'] and
         value['helper_sha256'] == t.SOURCE_PINS['probe_helpers.py'], 'SOURCE_BINDING')
    need(same(value['candidate_sources'], CANDIDATE_PINS), 'CANDIDATE_SOURCE_BINDING')
    need(value['node_sqlite']['node']['path'] == NODE_PATH, 'NODE_PATH')
    metadata(value['node_sqlite']['node']['metadata'])
    sdk = value['sdk_bindings']
    need(len(sdk) == 5 and {row['path'] for row in sdk} == SDK_PATHS, 'EXACT_SDK_PATHS')
    for row in sdk:
        integer(row['uid'], 1002, 1002)
        integer(row['gid'], 0, (1 << 32) - 1)
        integer(row['size'], 1, 8 * 1024 * 1024)
    for profile in value['profiles'].values():
        integer(profile['gid'], 0, (1 << 32) - 1)
        for gid in profile['supplementary_groups'].values():
            integer(gid, 0, (1 << 32) - 1)
    # Frozen validator is exact and recursively typed for the measured Python
    # pair (files, ancestors, xattr booleans and fixed public source/report pins).
    if 'python_identity' in value['python']:
        p.epoch7_python_identity.validate_pair_proof(value['python']['python_identity'])
    return resources_for(value, p)


def process_schema(value, t):
    t._process(value)
    integer(value['pid'], 1, (1 << 31) - 1)
    status = value['status']
    for key in ('Uid', 'Gid'):
        need(re.fullmatch(r'[0-9]{1,10}(?:[ \t][0-9]{1,10}){3}', status[key]), 'STATUS_IDS')
        for item in status[key].split():
            integer(int(item), 0, (1 << 32) - 1)
    need(re.fullmatch(r'(?:[0-9]{1,10}(?:[ \t][0-9]{1,10}){0,31})?', status['Groups']), 'STATUS_GROUPS')
    for item in status['Groups'].split():
        integer(int(item), 0, (1 << 32) - 1)


def unit_schema(value, suffix, policy, paths, t):
    t._unit(value, suffix, policy, paths)
    need(value['ActiveState'] in ACTIVE_STATES and value['SubState'] in SUB_STATES, 'UNIT_STATE')
    if suffix == 'service':
        need(re.fullmatch(r'[0-9]{1,10}', value['MainPID']), 'UNIT_PID')
        integer(int(value['MainPID']), 0, (1 << 31) - 1)
        # The frozen normalizer discards these runtime fields. Export must not:
        # each timestamp/code/status in the ORIGINAL string has a finite shape.
        stamp = (r'(?:n/a|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) '
            r'[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01]) '
            r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})? '
            r'(?:UTC|GMT|CST|[+-][0-9]{4}))?')
        command = (policy['python']['path'] + ' -B ' + paths['root'] + '/probe_helpers.py --config ' +
            paths['root'] + '/helper-ledger-server.json --mode server')
        pattern = (r'\{ path=' + re.escape(policy['python']['path']) + r' ; argv\[\]=' + re.escape(command) +
            r' ; ignore_errors=no ; start_time=\[' + stamp + r'\] ; stop_time=\[' + stamp +
            r'\] ; pid=([0-9]{1,10}) ; code=(?:\(null\)|exited|killed|dumped|stopped|trapped|continued) ; '
            r'status=(?:-?[0-9]{1,3}|[0-9]{1,3}/(?:[0-9]{1,3}|SUCCESS|FAILURE|TERM|KILL|ABRT|SEGV|SYS)) \}')
        matched = re.fullmatch(pattern, value['ExecStart'])
        need(matched, 'UNIT_EXEC_RUNTIME_SUFFIX')
        integer(int(matched.group(1)), 0, (1 << 31) - 1)


def case_schema(value, number, role, policy, paths, policy_sha, t):
    fields = {'case', 'status', 'production_verifier_admission', 'readpaths', 'owner_process_gate', 'namespace_proof'}
    fields.update(('reason', 'bound_before_failure', 'expected_rejection_observed') if number in (6, 8) else ('mechanism', 'peer'))
    if role == 'native':
        fields.add('sdk')
    keys(value, fields, 'CASE_KEYS')
    integer(value['case'], number, number)
    need(value['production_verifier_admission'] == 'NOT_VERIFIED' and
        value['owner_process_gate'] == 'NOT_VERIFIED_FIXED_PRODUCTION_PROCESS_PINS_NOT_REMAPPED', 'CASE_AUTHORITY')
    t._namespace(value['namespace_proof'])
    integer(value['namespace_proof']['pid'], 2, (1 << 31) - 1)
    need(re.fullmatch(r'pid:\[[0-9]{1,20}\]', value['namespace_proof']['namespace']), 'NAMESPACE_BOUND')
    if number in (6, 8):
        need(value['status'] == 'FAIL_OBSERVED' and value['bound_before_failure'] is True and
            value['expected_rejection_observed'] is True and value['reason'] in RACE_REASONS, 'RACE_REASON')
    else:
        need(value['status'] == 'PASS_OBSERVED' and value['mechanism'] == 'INHERITED_MANAGER_CHALLENGE', 'CASE_STATUS')
        need(type(value['peer']) is list and len(value['peer']) == 3, 'PEER_SHAPE')
        for item in value['peer']:
            integer(item, 0, (1 << 32) - 1)
        need(value['peer'][0:2] == [1, 0], 'PEER_IDENTITY')
    manager, boot = t._readpaths(value, role, policy, paths, policy_sha)
    if number not in (6, 8):
        need(value['peer'][2] == int(manager['status']['Gid'].split()[0]), 'PEER_MANAGER_GID')
    for row in value['readpaths']:
        if row['path_class'] == 'manager-process':
            process_schema(row['evidence'], t)
        elif row['path_class'] in ('manager-unit:socket', 'manager-unit:service'):
            unit_schema(row['evidence'], row['path_class'].split(':')[1], policy, paths, t)
    if role == 'native':
        need(same(value['sdk'], [dict(path=row['path'], status='PASS_OBSERVED', size=row['size'], sha256=row['sha256'])
            for row in policy['sdk_bindings']]), 'SDK_BINDING')
    return manager, boot, value['namespace_proof']['namespace']


def socket_schema(value):
    keys(value, ('dev', 'ino', 'uid', 'gid', 'mode'), 'SOCKET_KEYS')
    for key, item in value.items():
        integer(item, 1 if key == 'ino' else 0)
    integer(value['mode'], 0, 0o777)
    integer(value['uid'], 0, (1 << 32) - 1)
    integer(value['gid'], 0, (1 << 32) - 1)


def cleanup_schema(value, files, units):
    need(type(value) is list and len(value) == len(files) + len(units), 'CLEANUP_COUNT')
    seen_files, seen_units = set(), set()
    for row in value:
        if type(row) is dict and 'unit' in row:
            keys(row, ('unit', 'status'), 'CLEANUP_UNIT_KEYS')
            need(row['unit'] in units and row['unit'] not in seen_units and
                row['status'] in ('STOPPED_AND_EMPTY', 'ALREADY_ABSENT_STOPPED'), 'CLEANUP_UNIT')
            seen_units.add(row['unit'])
        else:
            keys(row, ('path', 'status'), 'CLEANUP_FILE_KEYS')
            need(row['path'] in files and row['path'] not in seen_files and row['status'] in ('REMOVED', 'ABSENT'), 'CLEANUP_FILE')
            seen_files.add(row['path'])
    need(seen_files == files and seen_units == units, 'CLEANUP_COVERAGE')


def validate_export(attempt, receipt, receipt_metadata, topology_module):
    """Validate only; caller retains the exact original objects and bytes.

    Requires an authenticated frozen topology module and a successful original
    project_topology invocation, not a substitute/shadow observation. Success
    returns None. A failed check raises a static label with no input content.
    """
    t = topology_module
    for value in (attempt, receipt, receipt_metadata):
        bounded_json(value)
    need(len(canonical(attempt)) <= 262144 and len(canonical(receipt)) + 1 <= 131072, 'DOCUMENT_BOUND')
    keys(attempt, ATTEMPT, 'ATTEMPT_KEYS')
    integer(attempt['schema'], 1, 1)
    need(attempt['nonce'] == NONCE and attempt['stage'] == 'RESULT_RECORDED' and
        attempt['resume_authority'] is False and attempt['operator_acknowledgement_is_external_approval_proof'] is False,
        'ATTEMPT_SCOPE')
    policy = attempt['policy']
    paths, files, units = policy_schema(policy, t)
    policy_sha = hashlib.sha256(canonical(policy) + b'\n').hexdigest()
    need(attempt['policy_sha256'] == policy_sha, 'POLICY_HASH')
    result = attempt['result']
    keys(result, RESULT | ({'incomplete_case'} if type(result) is dict and 'incomplete_case' in result else set()), 'RESULT_KEYS')
    integer(result['schema'], 1, 1)
    need(result['failure'] is None and result.get('incomplete_case') is None and
        type(result['last_command_cleanup']) is list and result['last_command_cleanup'] == [] and
        result['production_acceptance'] == 'NOT_VERIFIED' and result['resume_authority'] is False and
        result['operator_acknowledgement_is_external_approval_proof'] is False and
        same(result['intentionally_retained'], [paths['root'], paths['receipt']]), 'RESULT_SCOPE')
    cases = result['cases']
    need(type(cases) is list and len(cases) == 8, 'EIGHT_CASES')
    lifetimes = [case_schema(row, number, role, policy, paths, policy_sha, t)
        for row, (number, role, unused) in zip(cases, t.probe.CASES)]
    need(all(same(item, lifetimes[0]) for item in lifetimes), 'MANAGER_BOOT_NAMESPACE_LIFETIME')
    proof = result['node_sqlite']
    t.node.validate_node_sqlite_proof(proof, policy['node_sqlite']['node'], policy_sha,
        policy['node_sqlite']['probe_input_sha256'])
    need(proof['nonce'] == NONCE, 'NODE_NONCE')
    reported = result['created_receipt']
    keys(reported, ('path', 'sha256', 'metadata', 'node_sqlite_event_sha256'), 'REPORTED_RECEIPT_KEYS')
    sha(reported['sha256']); sha(reported['node_sqlite_event_sha256'])
    metadata(reported['metadata'], 0o600); metadata(receipt_metadata, 0o600)
    need(reported['path'] == paths['receipt'] and same(reported['metadata'], receipt_metadata), 'RECEIPT_METADATA_BINDING')
    raw = canonical(receipt) + b'\n'
    need(hashlib.sha256(raw).hexdigest() == reported['sha256'] and len(raw) == receipt_metadata['size'] and
        reported['node_sqlite_event_sha256'] == hashlib.sha256(canonical(proof)).hexdigest(), 'RECEIPT_HASH_BINDING')
    keys(receipt, RECEIPT | ({'incomplete_case'} if type(receipt) is dict and 'incomplete_case' in receipt else set()), 'RECEIPT_KEYS')
    integer(receipt['schema'], 1, 1)
    need(receipt['purpose'] == 'ISOLATED_PROBE_CREATION_RECEIPT' and receipt['nonce'] == NONCE and
        receipt['policy_sha256'] == policy_sha and receipt['operator_acknowledged'] is True and
        receipt['external_approval_authenticated'] is False and receipt['attempt_consumed'] is True and
        receipt['stage'] == 'CLEANUP_OBSERVED' and receipt.get('incomplete_case') is None, 'RECEIPT_SCOPE')
    integer(receipt['connections_reserved'], 8, 8); integer(receipt['accepted_connections'], 8, 8)
    need(type(receipt['resources']) is list and len(receipt['resources']) == len(files) + 1, 'RESOURCE_COUNT')
    seen = set()
    for row in receipt['resources']:
        need(type(row) is dict and row.get('path') in files | {paths['root']} and row['path'] not in seen, 'RESOURCE_PATH')
        seen.add(row['path'])
        directory = row['path'] == paths['root']
        keys(row, ('path', 'kind', 'identity') if directory else ('path', 'kind', 'identity', 'sha256'), 'RESOURCE_KEYS')
        need(row['kind'] == ('DIRECTORY' if directory else 'FILE'), 'RESOURCE_KIND')
        metadata(row['identity'], None if directory else (0o600 if row['path'].endswith('/connection-budget.json') else 0o644))
        if directory:
            need((row['identity']['uid'], row['identity']['gid'], row['identity']['mode']) == (0, 0, 0o755), 'RESOURCE_ROOT')
        else:
            sha(row['sha256'])
            integer(row['identity']['size'], 0, 1048576)
    cleanup_schema(receipt['cleanup'], files, units)
    need(same(receipt['cleanup'], result['cleanup']), 'CLEANUP_BINDING')
    # This frozen routine is pure despite its HostOps name. It uses only scope,
    # source rendering and supplied resource metadata, never a host instance.
    t._resource_sources(receipt, policy, paths, None)
    script = next(row for row in receipt['resources']
        if row['path'] == paths['root'] + '/node-sqlite-probe.cjs')
    need(script['sha256'] == hashlib.sha256(t.node.SOURCE).hexdigest() and
        script['identity']['size'] == len(t.node.SOURCE), 'NODE_SCRIPT_RESOURCE')
    socket_schema(receipt['socket_identity'])
    socket = receipt['socket_identity']
    endpoint = {key: socket[key] for key in ('uid', 'gid', 'mode')}
    need(endpoint == {'uid': policy['profiles']['ledger']['uid'],
        'gid': policy['profiles']['broker']['supplementary_groups']['xuanjun-ledger-client'], 'mode': 0o660}, 'SOCKET_BINDING')
    t._server_records(result['server_observations'], cases, policy, paths, endpoint)
    for row in result['server_observations']:
        if row['event'] == 'SERVER_READY':
            process_schema(row['own'], t)
    events = receipt['events']
    need(type(events) is list and 1 <= len(events) <= 512, 'EVENT_COUNT')
    intents, observed, starts, records, created = [], [], [], [], set()
    node_intents, node_observed, loaded, recreated, recreated_during = 0, 0, 0, 0, 0
    output_paths = {paths['root'] + '/' + prefix + role + suffix for role in t.probe.ROLES
        for prefix, suffix in (('output-', '.jsonl'), ('error-', '.txt'))}
    replace_paths = output_paths | {paths['root'] + '/helper-' + role + '-client.json'
        for role in t.probe.ROLES if role != 'ledger'}
    for event in events:
        keys(event, ('event', 'detail'), 'EVENT_KEYS')
        name, detail = event['event'], event['detail']
        if name == 'CREATE_INTENT':
            keys(detail, ('path', 'sha256'), 'CREATE_INTENT_KEYS')
            need(detail['path'] in files and detail['path'] not in created, 'CREATE_INTENT_PATH')
            sha(detail['sha256']); created.add(detail['path'])
        elif name == 'REPLACE_INTENT':
            keys(detail, ('path', 'before_sha256', 'after_sha256'), 'REPLACE_INTENT_KEYS')
            need(detail['path'] in replace_paths, 'REPLACE_INTENT_PATH')
            sha(detail['before_sha256']); sha(detail['after_sha256'])
        elif name == 'UNITS_LOADED':
            need(detail is None, 'UNITS_LOADED_DETAIL'); loaded += 1
        elif name == 'NODE_SQLITE_INTENT':
            keys(detail, ('diagnostic_sha256', 'node_sha256', 'probe_input_sha256'), 'NODE_INTENT_KEYS')
            need(same(detail, {'diagnostic_sha256': proof['diagnostic_sha256'],
                'node_sha256': proof['node']['sha256'], 'probe_input_sha256': proof['probe_input_sha256']}), 'NODE_INTENT_BINDING')
            node_intents += 1
        elif name == 'NODE_SQLITE_OBSERVED':
            need(same(detail, proof), 'NODE_OBSERVED_BINDING'); node_observed += 1
        elif name == 'CASE_INTENT':
            need(len(intents) == len(observed) and len(intents) < 8, 'CASE_INTENT_ORDER')
            number, role, kind = t.probe.CASES[len(intents)]
            need(same(detail, {'case': number, 'role': role, 'kind': kind}), 'CASE_INTENT_BINDING')
            intents.append(detail)
        elif name == 'CASE_OBSERVED':
            need(len(intents) == len(observed) + 1 and same(detail, cases[len(observed)]), 'CASE_OBSERVED_BINDING')
            observed.append(detail)
        elif name == 'CLIENT_START_INTENT':
            keys(detail, ('case', 'unit'), 'CLIENT_START_KEYS')
            need(len(starts) < 8, 'CLIENT_START_COUNT')
            number, role, unused = t.probe.CASES[len(starts)]
            need(same(detail, {'case': number, 'unit': paths['client_units'][role]}), 'CLIENT_START_BINDING')
            starts.append(detail)
        elif name in ('SOCKET_RECREATED', 'SOCKET_RECREATED_DURING'):
            keys(detail, ('before', 'after'), 'SOCKET_EVENT_KEYS')
            socket_schema(detail['before']); socket_schema(detail['after'])
            for item in detail.values():
                need(all(item[key] == endpoint[key] for key in endpoint), 'SOCKET_EVENT_BINDING')
            if name == 'SOCKET_RECREATED': recreated += 1
            else: recreated_during += 1
        elif name == 'OUTPUT_CAPTURED':
            need(type(detail) is dict and detail.get('path') in output_paths, 'OUTPUT_PATH')
            ledger = detail['path'] == paths['root'] + '/output-ledger.jsonl'
            keys(detail, ('path', 'sha256', 'bytes', 'observations') if ledger else ('path', 'sha256', 'bytes'), 'OUTPUT_KEYS')
            sha(detail['sha256']); integer(detail['bytes'], 0, 65536)
            if ledger:
                need(type(detail['observations']) is list and len(detail['observations']) <= 128, 'OUTPUT_RECORDS')
                records.extend(detail['observations'])
        else:
            need(False, 'UNKNOWN_EVENT')
    need(created == files and len(intents) == len(observed) == len(starts) == 8 and
        node_intents == node_observed == loaded == recreated == recreated_during == 1, 'EVENT_COVERAGE')
    need(same(records, result['server_observations']), 'SERVER_RECORD_BINDING')
    # All records in captures are exactly the previously typed successful list;
    # no ignored diagnostics or otherwise unused payload can survive.
    return None
