"""Finite phase-aware live guards; no command runner, host defaults or entrypoint.

The exact read-only observation backend and measured process pins are mandatory.
This module validates actual observation structures, not caller success booleans.
It never reuses the epoch7 all-stopped snapshot after allowed runtime mutations.
The live_controls contract must be inside the exact independently approved plan.
"""
import copy
import hashlib
import json
import os.path
import time
import uuid

import epoch7_delta as d
import epoch7_snapshot as snap
from epoch7_recovery_sequence import PHASES, STOP_UNITS, CLEANUP, ADAPTER_BOUNDS, observation, check_observation


SECTIONS = frozenset(('historical', 'release', 'activation', 'targets', 'identities',
    'generation', 'access', 'native', 'tls', 'sandbox', 'plugin', 'database',
    'gateway', 'boot', 'runtime_access'))
MUTATIONS = {
    'stage_exact_release': frozenset(('release',)),
    'preserve_prior_receipts': frozenset(),
    # This phase also exclusively publishes the fixed epoch8 TLS candidate.
    'rebind_prepared_epoch': frozenset(('activation', 'native', 'tls')),
    'quiesce_exact_epoch': frozenset(('activation',)),
    'replace_retained_targets': frozenset(('targets',)),
    'publish_reviewed_identities': frozenset(('identities',)),
    'change_generation_access': frozenset(('generation',)),
    # The exact client FILE lives in targets and the release parent DIRECTORY
    # lives in release; their ACL fields legitimately change in this phase.
    'apply_reviewed_access': frozenset(('access', 'targets', 'release')),
    'rebind_tls_metadata_only': frozenset(('tls',)),
    'apply_fresh_sandbox': frozenset(('sandbox',)),
    'install_verified_plugin': frozenset(('sandbox', 'plugin')),
    'reopen_existing_database': frozenset(('database',)),
    'verify_runtime_access': frozenset(('runtime_access',)),
    'activate_exact_epoch': frozenset(('activation',)),
    'activate_new_services': frozenset(('gateway', 'boot', 'database', 'sandbox')),
    # Only the separately reviewed retained timer tail changes scheduling here.
    'post_install_checks': frozenset(('boot',)),
}
WRITER_UIDS = frozenset((1002, 1003, 1004, 1005, 1008))
FORBIDDEN_ACTIVE = snap.WRITER_UNITS - frozenset(STOP_UNITS)
REQUIRED_ACTIVE = frozenset(STOP_UNITS) - {'xuanjun-github-intake.service', 'xuanjun-p2-tls-renew.service'}
DEFERRED_TIMER = 'xuanjun-p2-tls-renew.timer'
# Fixed Accept=no endpoints. Their rendered declarations are checked by the compiler.
SOCKET_SERVICES = {
    'xj-root-broker.socket': ('xj-root-broker.service', '/run/xuanjun-development/broker.sock'),
    'xuanjun-ledger.socket': ('xuanjun-ledger.service', '/run/xuanjun-development/ledger.sock'),
    'xuanjun-p2-gateway-relay.socket': ('xuanjun-p2-gateway-relay.service', '/run/xuanjun-development/p2-gateway.sock'),
}
UNIT_FIELDS = frozenset(('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID',
    'ControlPID', 'ControlGroup', 'UnitFileState', 'NeedDaemonReload', 'ConditionResult'))
STATIC_UNIT_FIELDS = UNIT_FIELDS - {'MainPID', 'ControlPID', 'ControlGroup'}
IDENTITY_FIELDS = frozenset(('pid', 'starttime', 'uids', 'gids', 'groups', 'comm',
    'executable', 'executable_sha256', 'argv_sha256', 'unit', 'kernel_thread'))
ROLE_FIELDS = IDENTITY_FIELDS - {'pid', 'starttime', 'comm', 'kernel_thread'}
MAX_PLAN_BYTES = 2097152
MAX_VIEW_BYTES = 33554432
MAX_PROCESSES = 65536
MAX_CGROUP_FILES = 1024
MAX_FD_ROWS = 1000000
DATABASE_SUFFIXES = ('-wal', '-shm', '-journal')
DATABASE_PATHS = frozenset(path + suffix for path in snap.DATABASES
                           for suffix in ('',) + DATABASE_SUFFIXES)
SIDECAR_POLICY = {'paths': [d.DB + suffix for suffix in DATABASE_SUFFIXES],
                  'uid': 1003, 'gid': 1006, 'mode': 0o600, 'nlink': 1}
DATABASE_FILE_FIELDS = frozenset(('kind', 'dev', 'ino', 'uid', 'gid', 'mode', 'nlink'))
RETAINED_SIDECAR_PATHS = frozenset(path + suffix for path in snap.DATABASES if path != d.DB
                                  for suffix in DATABASE_SUFFIXES)
RETAINED_SIDECAR_FIELDS = DATABASE_FILE_FIELDS | {'size','mtime_ns','ctime_ns','sha256'}


def need(value, label):
    if not value: raise ValueError('EPOCH7_LIVE_' + label)


def canonical(value, maximum=MAX_VIEW_BYTES):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    need(len(raw) <= maximum, 'EVIDENCE_BOUND')
    return raw


def digest(value): return hashlib.sha256(canonical(value)).hexdigest()


def _integer(value, minimum=0):
    need(type(value) is int and minimum <= value < 2**63, 'INTEGER')


def _path(value):
    need(type(value) is str and value.startswith('/') and os.path.normpath(value) == value and
         '\0' not in value and len(value) <= 4096, 'CANONICAL_PATH')


def _role(role):
    need(type(role) is dict and set(role) == ROLE_FIELDS, 'PROCESS_ROLE_SCHEMA')
    for key in ('uids', 'gids'):
        need(type(role[key]) is list and len(role[key]) == 4, 'PROCESS_ROLE_IDS')
        for value in role[key]: _integer(value)
    need(type(role['groups']) is list and role['groups'] == sorted(set(role['groups'])) and
         len(role['groups']) <= 128, 'PROCESS_ROLE_GROUPS')
    for value in role['groups']: _integer(value)
    _path(role['executable'])
    for key in ('executable_sha256', 'argv_sha256'): d.hash_value(role[key])
    need(role['unit'] is None or role['unit'] in STOP_UNITS and role['unit'].endswith('.service'), 'PROCESS_ROLE_UNIT')


def _identity(value):
    need(type(value) is dict and set(value) == IDENTITY_FIELDS, 'PROCESS_IDENTITY_SCHEMA')
    _integer(value['pid'], 1); _integer(value['starttime'], 1)
    need(type(value['comm']) is str and len(value['comm']) <= 256 and '\0' not in value['comm'],
         'PROCESS_COMM')
    need(not value['comm'].startswith(('Runner.Listener', 'Runner.Worker')), 'RUNNER_PROCESS_PRESENT')
    need(type(value['kernel_thread']) is bool, 'KERNEL_THREAD_FLAG')
    if value['kernel_thread']:
        need(value['uids'] == value['gids'] == [0]*4 and
             all(type(x) is int for x in value['uids'] + value['gids']) and
             value['executable'] is None and value['executable_sha256'] is None and
             value['argv_sha256'] == hashlib.sha256(b'').hexdigest() and value['unit'] is None,
             'KERNEL_THREAD_IDENTITY')
        need(type(value['groups']) is list and value['groups'] in ([], [0]) and
             all(type(x) is int for x in value['groups']), 'KERNEL_THREAD_GROUPS')
        return
    _role({k: value[k] for k in ROLE_FIELDS})


def validate_contract(contract, context):
    need(type(contract) is dict and type(contract.get('schema')) is int and contract['schema'] in (1,2), 'CONTRACT_VERSION')
    extra = {'service_role_contract','unit_transition_contract'} if contract['schema'] == 2 else set()
    need(set(contract) == {'schema', 'snapshot_sha256',
        'runtime_manifest_sha256', 'manager', 'checkpoints', 'process_roles', 'database_identities',
        'database_sidecar_policy', 'retained_sidecar_pins'} | extra,
        'CONTRACT_SCHEMA')
    need(
         contract['snapshot_sha256'] == context['snapshot_sha256'] and
         contract['runtime_manifest_sha256'] == context['runtime_manifest_sha256'], 'CONTRACT_BINDING')
    manager = contract['manager']
    need(type(manager) is dict and set(manager) == {'pid', 'uids', 'starttime', 'boot_id',
        'executable', 'executable_sha256', 'channels_sha256'}, 'MANAGER_SCHEMA')
    need(type(manager['pid']) is int and manager['pid'] == 1 and manager['uids'] == [0,0,0,0] and
         all(type(x) is int for x in manager['uids']), 'ROOT_MANAGER_REQUIRED')
    _integer(manager['starttime'], 1); _path(manager['executable'])
    need(str(uuid.UUID(manager['boot_id'])) == manager['boot_id'], 'BOOT_ID')
    for key in ('executable_sha256', 'channels_sha256'): d.hash_value(manager[key])
    checkpoints = contract['checkpoints']
    need(type(checkpoints) is list and len(checkpoints) == len(PHASES) + 1, 'FINITE_CHECKPOINTS')
    for index, point in enumerate(checkpoints):
        need(type(point) is dict and set(point) == {'resources', 'units'}, 'CHECKPOINT_SCHEMA')
        need(type(point['resources']) is dict and set(point['resources']) == SECTIONS,
             'RESOURCE_SECTION_SET')
        for value in point['resources'].values(): d.hash_value(value)
        need(type(point['units']) is dict and set(point['units']) == snap.WRITER_UNITS,
             'EXACT_UNIT_POLICY_SET')
        for unit, policy in point['units'].items():
            need(type(policy) is dict and set(policy) == {'properties', 'main_required', 'main_role_sha256'}, 'UNIT_POLICY_SCHEMA')
            props = policy['properties']
            need(type(props) is dict and set(props) == STATIC_UNIT_FIELDS and
                 props['Id'] == unit and all(type(x) is str and len(x) <= 8192 for x in props.values()),
                 'UNIT_STATIC_PROPERTIES')
            need(type(policy['main_required']) is bool and props['LoadState'] in ('loaded','masked') and
                 props['NeedDaemonReload'] in ('yes','no'), 'UNIT_POLICY_VALUES')
            active = props['ActiveState'] == 'active'
            need(props['ActiveState'] in ('inactive','failed','active') and
                 (active or policy['main_required'] is False), 'UNIT_ACTIVE_POLICY')
            if index <= PHASES.index('activate_new_services') or unit in FORBIDDEN_ACTIVE:
                need(not active, 'PREMATURE_OR_LEGACY_WRITER_ACTIVE')
            else:
                required = REQUIRED_ACTIVE - {DEFERRED_TIMER} if index == len(PHASES)-1 else REQUIRED_ACTIVE
                need(active is (unit in required), 'FINAL_ACTIVE_UNIT_SET')
            need(policy['main_required'] is (active and unit.endswith('.service')), 'MAIN_PID_REQUIRED_FOR_SERVICE')
            if policy['main_required']: d.hash_value(policy['main_role_sha256'])
            else: need(policy['main_role_sha256'] is None, 'INACTIVE_MAIN_ROLE')
            if unit == snap.RUNNER:
                need(props['ConditionResult'] == 'no', 'RUNNER_CONDITION_REQUIRED')
        if index > PHASES.index('activate_new_services'):
            for socket_unit, (service_unit, unused_path) in SOCKET_SERVICES.items():
                socket_props = point['units'][socket_unit]['properties']
                service_props = point['units'][service_unit]['properties']
                need((socket_props['ActiveState'], socket_props['SubState']) == ('active','running') and
                     (service_props['ActiveState'], service_props['SubState']) == ('active','running'),
                     'FINAL_ACCEPT_NO_SOCKET_SERVICE_STATE')
        if index:
            changed = {name for name in SECTIONS if point['resources'][name] !=
                       checkpoints[index-1]['resources'][name]}
            need(changed <= MUTATIONS[PHASES[index-1]], 'UNREVIEWED_CROSS_PHASE_MUTATION')
    roles = contract['process_roles']
    need(type(roles) is list and 1 <= len(roles) <= 128 and
         len({digest(x) for x in roles}) == len(roles), 'EXACT_PROCESS_ROLE_LIST')
    for role in roles:
        _role(role)
        if role['unit'] is None:
            need(role['uids'] == [1002]*4 and role['executable'] == '/usr/bin/ssh',
                 'BACKGROUND_ROLE_SCOPE')
    by_hash = {digest(role): role for role in roles}
    if contract['schema'] == 2:
        import epoch7_service_roles as scoped_roles
        extended = scoped_roles.validate_contract(contract['service_role_contract'],digest,_path,_role)
        import epoch7_unit_transitions as unit_transitions
        unit_transitions.validate_contract(contract['unit_transition_contract'],STATIC_UNIT_FIELDS,snap.WRITER_UNITS,d.hash_value)
        for unit,policy in contract['unit_transition_contract']['units'].items():
            need(policy['before']==checkpoints[0]['units'][unit]['properties'],'CACHE_BASELINE_BINDING')
        restored=contract['unit_transition_contract'].get('gateway_restoration')
        if restored is not None:
            need(restored['before']==checkpoints[0]['units']['xuanjun-uk-openclaw.service']['properties'],
                 'RESTORE_BASELINE_BINDING')
        scoped = set(contract['service_role_contract']['units'])
        need(not any(r['unit'] in scoped for r in roles), 'SCOPED_ROLE_NO_EXACT_BYPASS')
        need(not set(by_hash) & set(extended), 'SCOPED_ROLE_HASH_ALIAS')
        by_hash.update(extended)
    for point in checkpoints:
        for unit, policy in point['units'].items():
            if policy['main_required']:
                need(policy['main_role_sha256'] in by_hash and
                     by_hash[policy['main_role_sha256']]['unit'] == unit, 'MAIN_PROCESS_ROLE_REQUIRED')
    identities = contract['database_identities']
    need(type(identities) is dict and set(identities) == set(snap.DATABASES), 'EXACT_DATABASE_IDENTITIES')
    for row in identities.values():
        need(type(row) is dict and set(row) == {'dev', 'ino'}, 'DATABASE_IDENTITY_SCHEMA')
        _integer(row['dev']); _integer(row['ino'], 1)
    need(len({(row['dev'], row['ino']) for row in identities.values()}) == len(identities),
         'DATABASE_ALIAS_IDENTITY')
    # These dynamic files cannot have future inodes pre-pinned. Their exact
    # paths/owner/mode/link policy is explicit in the independently approved
    # plan; each census binds actual stable identities and exact FD holders.
    need(d.same(contract['database_sidecar_policy'], SIDECAR_POLICY), 'EXACT_DATABASE_SIDECAR_POLICY')
    retained = contract['retained_sidecar_pins']
    need(type(retained) is dict and set(retained) == RETAINED_SIDECAR_PATHS, 'EXACT_RETAINED_SIDECAR_PINS')
    for row in retained.values():
        if row is None: continue
        need(type(row) is dict and set(row) == RETAINED_SIDECAR_FIELDS and row['kind'] == 'REGULAR',
             'RETAINED_SIDECAR_PIN_SCHEMA')
        for key in RETAINED_SIDECAR_FIELDS - {'kind','sha256'}:
            _integer(row[key],1 if key in ('ino','nlink') else 0)
        need(row['nlink'] == 1 and row['size'] <= 16777216 and row['mode'] <= 0o777 and
             not row['mode'] & 0o022, 'RETAINED_SIDECAR_PIN_AUTHORITY')
        d.hash_value(row['sha256'])
    canonical(contract, MAX_PLAN_BYTES)
    return copy.deepcopy(contract)


def validate_unit_row(unit, row, policy=None, stopped=False):
    """Require type-applicable properties and the complete cgroup inventory.

    The concrete reader must obtain manager state before/after recursive cgroup
    traversal and report absent cgroups explicitly. is-active alone cannot fit
    this interface and cannot become an OBSERVED stop result.
    """
    need(unit in snap.WRITER_UNITS and type(row) is dict and set(row) ==
         {'before', 'after', 'cgroup_present', 'cgroups'}, 'UNIT_OBSERVATION_SCHEMA')
    before, after = row['before'], row['after']
    required,optional = snap.unit_process_fields(unit)
    need(type(before) is dict and STATIC_UNIT_FIELDS | required <= set(before) <= UNIT_FIELDS and before == after,
         'UNIT_STATE_RACE_OR_MISSING_PID')
    need(before['Id'] == unit, 'UNIT_PID_TYPES')
    main_pid,control_pid = snap.validate_unit_process_fields(unit,before,pid_type=int)
    need(control_pid == 0, 'UNIT_CONTROL_OR_CGROUP')
    need(before['LoadState'] in ('loaded','masked','not-found'), 'UNIT_LOAD_STATE_UNKNOWN')
    if policy is not None:
        need({k: before[k] for k in STATIC_UNIT_FIELDS} == policy['properties'], 'UNIT_PROPERTIES_DRIFT')
        need((main_pid > 0) is policy['main_required'], 'UNIT_MAIN_PID_POLICY')
    if stopped or before['ActiveState'] in ('inactive', 'failed'):
        need(before['ActiveState'] in ('inactive','failed') and main_pid == 0,
             'UNIT_NOT_STOPPED')
    groups = row['cgroups']
    need(type(row['cgroup_present']) is bool and type(groups) is dict and len(groups) <= MAX_CGROUP_FILES,
         'CGROUP_INVENTORY_BOUND')
    root = '/sys/fs/cgroup/systemd/system.slice/' + unit
    need((row['cgroup_present'] and root + '/cgroup.procs' in groups) or
         (not row['cgroup_present'] and not groups), 'CGROUP_PRESENCE_PROOF')
    pids = []
    for path, entries in groups.items():
        _path(path)
        need(path.startswith(root + '/') and path.endswith('/cgroup.procs') and
             type(entries) is list and entries == sorted(set(entries)), 'CGROUP_SCOPE')
        for pid in entries: _integer(pid, 1)
        pids.extend(entries)
    need(len(pids) == len(set(pids)) and len(pids) <= MAX_PROCESSES, 'CGROUP_DUPLICATE_OR_BOUND')
    if stopped or before['ActiveState'] != 'active' or unit in snap.TIMER_UNITS:
        need(not pids, 'CGROUP_NOT_EMPTY')
    if main_pid: need(main_pid in pids, 'MAIN_PID_NOT_IN_CGROUP')
    return set(pids)


def validate_process_view(value, contract, checkpoint, observer_pid, allow_observer_db=False,
                          allow_inactive_sidecars=False, context_sha256=None,
                          allow_pending_service_receipts=False, checkpoint_index=None):
    need(type(allow_observer_db) is bool and type(allow_inactive_sidecars) is bool, 'PROCESS_SCOPE_BOOLEAN')
    extra = {'service_role_evidence','unit_transition_evidence'} if contract.get('schema') == 2 else set()
    need(type(value) is dict and set(value) == {'manager_before','manager_after','units',
        'pids_before','pids_after','processes','database_fds','database_files','observer_pid'} | extra, 'PROCESS_VIEW_SCHEMA')
    need(type(observer_pid) is int and observer_pid > 1 and value['observer_pid'] == observer_pid and
         type(value['observer_pid']) is int, 'OBSERVER_PID_BINDING')
    need(value['manager_before'] == value['manager_after'] == contract['manager'], 'MANAGER_OR_BOOT_CHANGED')
    need(type(value['units']) is dict and set(value['units']) == snap.WRITER_UNITS, 'EXACT_UNIT_OBSERVATIONS')
    policies = checkpoint['units']
    if contract.get('schema') == 2:
        import epoch7_unit_transitions as unit_transitions
        policies = unit_transitions.effective_policies(value['unit_transition_evidence'],
            contract['unit_transition_contract'],checkpoint,checkpoint_index,context_sha256,value['units'],d.hash_value,
            allow_pending=allow_pending_service_receipts)
    memberships = {}
    for unit, row in value['units'].items():
        for pid in validate_unit_row(unit, row, policies[unit]):
            need(pid not in memberships, 'PROCESS_MULTIPLE_UNITS'); memberships[pid] = unit
    pids = value['pids_before']
    need(type(pids) is list and pids == sorted(set(pids)) and pids == value['pids_after'] and
         len(pids) <= MAX_PROCESSES, 'PROCESS_CENSUS_RACE_OR_BOUND')
    for pid in pids: _integer(pid, 1)
    rows = value['processes']
    need(type(rows) is dict and set(rows) == {str(pid) for pid in pids}, 'INCOMPLETE_PROCESS_CENSUS')
    scoped_assignments = {}
    if contract.get('schema') == 2:
        import epoch7_service_roles as scoped_roles
        scoped_assignments = scoped_roles.validate_evidence(value['service_role_evidence'],
            contract['service_role_contract'],checkpoint,rows,memberships,value['units'],
            context_sha256,digest,allow_pending=allow_pending_service_receipts)
    allowed = {}
    for text, row in rows.items():
        need(type(row) is dict and set(row) == {'before','after'} and row['before'] == row['after'],
             'PROCESS_IDENTITY_RACE')
        identity = row['before']; _identity(identity)
        need(identity['pid'] == int(text), 'PID_KEY_MISMATCH')
        unit = identity['unit']
        need(memberships.get(identity['pid']) == unit, 'UNIT_PROCESS_DELIVERY')
        if unit is not None or WRITER_UIDS & set(identity['uids']):
            role = {k: identity[k] for k in ROLE_FIELDS}
            need(role in contract['process_roles'] or identity['pid'] in scoped_assignments, 'UNREVIEWED_WRITER_PROCESS')
            if unit is not None:
                need(checkpoint['units'][unit]['properties']['ActiveState'] == 'active', 'WRITER_UNIT_NOT_ALLOWED')
                if snap.validate_unit_process_fields(unit,value['units'][unit]['before'],pid_type=int)[0] == identity['pid']:
                    role_hash = scoped_assignments.get(identity['pid'],digest(role))
                    need(role_hash == checkpoint['units'][unit]['main_role_sha256'], 'MAIN_PROCESS_IDENTITY_DRIFT')
            allowed[identity['pid']] = identity
        if identity['pid'] == observer_pid:
            need(not identity['kernel_thread'] and identity['uids'] == [0]*4 and
                 identity['gids'] == [0]*4 and unit is None, 'OBSERVER_ROOT_IDENTITY')
            allowed[observer_pid] = identity
    need(set(memberships) <= {int(x) for x in rows}, 'CGROUP_PROCESS_UNOBSERVED')
    need(str(observer_pid) in rows, 'OBSERVER_MISSING_FROM_CENSUS')
    need('1' in rows, 'MANAGER_MISSING_FROM_CENSUS')
    manager_identity = rows['1']['before']
    need(not manager_identity['kernel_thread'] and manager_identity['unit'] is None and
         all(manager_identity[k] == contract['manager'][k] for k in
             ('pid','uids','starttime','executable','executable_sha256')), 'MANAGER_CENSUS_IDENTITY')
    files = value['database_files']
    need(type(files) is dict and set(files) == DATABASE_PATHS, 'EXACT_DATABASE_FILE_CENSUS')
    ledger_active = checkpoint['units']['xuanjun-ledger.service']['properties']['ActiveState'] == 'active'
    observed_identities = set()
    for path, row in files.items():
        base = path in contract['database_identities']
        retained = path in RETAINED_SIDECAR_PATHS
        if retained:
            need(d.same(row,contract['retained_sidecar_pins'][path]), 'RETAINED_SIDECAR_DRIFT')
        if row is None:
            need(not base, 'BASE_DATABASE_MISSING')
            continue
        fields = RETAINED_SIDECAR_FIELDS if retained else DATABASE_FILE_FIELDS
        need(type(row) is dict and set(row) == fields and row['kind'] == 'REGULAR',
             'DATABASE_FILE_SCHEMA')
        for key in DATABASE_FILE_FIELDS - {'kind'}: _integer(row[key], 1 if key in ('ino','nlink') else 0)
        need(row['nlink'] == 1, 'DATABASE_HARDLINK')
        identity = (row['dev'], row['ino'])
        need(identity not in observed_identities, 'DATABASE_FILE_ALIAS'); observed_identities.add(identity)
        if base:
            need({k:row[k] for k in ('dev','ino')} == contract['database_identities'][path],
                 'BASE_DATABASE_IDENTITY')
        elif not retained:
            need(path in contract['database_sidecar_policy']['paths'] and
                 (ledger_active or allow_inactive_sidecars) and
                 all(row[k] == contract['database_sidecar_policy'][k] for k in ('uid','gid','mode','nlink')),
                 'UNREVIEWED_DATABASE_SIDECAR')
    fds = value['database_fds']
    need(type(fds) is list and len(fds) <= MAX_FD_ROWS, 'DATABASE_FD_BOUND')
    seen_fds = set()
    for row in fds:
        need(type(row) is dict and set(row) == {'pid','fd','path','storage_path','dev','ino','flags'}, 'DATABASE_FD_SCHEMA')
        for key in ('pid','fd','dev','ino','flags'): _integer(row[key], 1 if key in ('pid','ino') else 0)
        need((row['pid'],row['fd']) not in seen_fds, 'DATABASE_FD_DUPLICATE')
        seen_fds.add((row['pid'],row['fd']))
        need(row['path'] in contract['database_identities'] and
             row['storage_path'] in (row['path'],) + tuple(row['path']+s for s in DATABASE_SUFFIXES),
             'DATABASE_FD_STORAGE_SCOPE')
        actual = files[row['storage_path']]
        need(actual is not None and all(row[k] == actual[k] for k in ('dev','ino')), 'DATABASE_FD_IDENTITY')
        identity = allowed.get(row['pid'])
        if allow_observer_db and row['pid'] == observer_pid:
            need(row['path'] == row['storage_path'] == d.DB and identity is not None and
                 row['flags'] & os.O_ACCMODE == os.O_RDONLY and not row['flags'] & getattr(os,'O_PATH',0),
                 'OBSERVER_DATABASE_FD_SCOPE')
            continue
        need(row['path'] == d.DB and identity is not None and identity['unit'] == 'xuanjun-ledger.service' and
             identity['uids'] == [1003]*4 and ledger_active,
             'UNAUTHORIZED_DATABASE_FD_HOLDER')
    canonical(value)
    return digest(value)


def validate_cleanup_process_view(value, contract, observer_pid):
    """Validate final stopped census without reusing obsolete resource pins.

    Residual canonical sidecars may remain after stop, under the same reviewed
    metadata policy, but no process may hold any database/sidecar FD. Unit-file
    inhibition/mask proof is separately checked by independent cleanup groups.
    Approved background roles and manager/process identities remain exact.
    """
    need(type(value) is dict and type(value.get('units')) is dict and
         set(value['units']) == snap.WRITER_UNITS, 'CLEANUP_EXACT_UNIT_SET')
    point = {'units':{}}
    for unit,row in value['units'].items():
        validate_unit_row(unit,row,stopped=True)
        props = {key:row['before'][key] for key in STATIC_UNIT_FIELDS}
        if unit == snap.RUNNER: need(props['ConditionResult'] == 'no', 'RUNNER_CONDITION_REQUIRED')
        point['units'][unit] = {'properties':props,'main_required':False,'main_role_sha256':None}
    need(value.get('database_fds') == [], 'CLEANUP_DATABASE_FD_PRESENT')
    # Cleanup proves complete stop independently; it must not demand an unfinished
    # target receipt after a failed write. Strip only the opt-in cache scope.
    checked=contract
    if contract.get('schema')==2:
        checked=copy.deepcopy(contract)
        checked['unit_transition_contract']={'schema':1,'targets':{},'units':{}}
        value=copy.deepcopy(value);value['unit_transition_evidence']=None
    return validate_process_view(value,checked,point,observer_pid,allow_inactive_sidecars=True,checkpoint_index=0)


class FiniteLiveControls(object):
    """Exact approved checkpoints plus mandatory real read-only observations.

    observer.preflight(context) -> (delta_snapshot, supporting_evidence)
    observer.bind_plan(plan) -> True after binding all concrete observer inputs
    observer.begin_guard(absolute_monotonic_deadline) -> None
    observer.resources(context, phase, boundary, names) -> exact name/value map
    observer.processes(context, phase, boundary) -> validate_process_view input
    observer.unit(context, operation, unit) -> validate_unit_row input
    observer.tls_contents(context) -> exact certificate/tree hashes

    No default observer exists. A concrete scanner must prove complete census,
    bounded reads, descriptor/path identity and before/after consistency. The
    pre-active snapshot scanner is not an acceptable post-ACTIVE substitute.
    """
    def __init__(self, approved_plan_raw, context, verifier, lock, authority, observer):
        need(type(approved_plan_raw) is bytes and len(approved_plan_raw) <= MAX_PLAN_BYTES, 'PLAN_BYTES')
        plan = snap.decode(approved_plan_raw)
        need(type(plan) is dict and 'live_controls' in plan, 'MISSING_REVIEWED_LIVE_CONTRACT')
        verifier._bound()
        need(hashlib.sha256(approved_plan_raw).hexdigest() == verifier.wanted['recovery_plan_sha256'],
             'APPROVED_PLAN_RAW_HASH')
        need(d.same(context, verifier.context), 'APPROVED_CONTEXT')
        need(d.same(context.get('adapter_bounds'), ADAPTER_BOUNDS), 'REVIEWED_ADAPTER_BOUNDS')
        need(observer is not None and all(callable(getattr(observer, name, None)) for name in
             ('bind_plan','begin_guard','preflight','resources','processes','unit','tls_contents')),
             'CONCRETE_OBSERVER_REQUIRED')
        need(authority is not None and all(callable(getattr(authority,name,None)) for name in
             ('phase','receipt','cleanup')), 'EXACT_CLAIM_AUTHORITY_REQUIRED')
        self.context, self.contract = copy.deepcopy(context), validate_contract(plan['live_controls'], context)
        self.verifier, self.lock, self.authority, self.observer = verifier, lock, authority, observer
        self.contract_digest, self.context_digest = digest(self.contract), digest(context)
        self.next_index, self.open_phase = 0, None
        self.owner_pid = os.getpid()
        self.phase_deadline = None
        need(observer.bind_plan(copy.deepcopy(plan)) is True, 'OBSERVER_APPROVED_PLAN_BINDING')

    def _begin_guard(self, phase_bound=True):
        deadline = time.monotonic() + ADAPTER_BOUNDS['guard_timeout_seconds']
        if phase_bound and self.phase_deadline is not None: deadline = min(deadline,self.phase_deadline)
        need(time.monotonic() < deadline, 'PHASE_OR_GUARD_DEADLINE')
        self.observer.begin_guard(deadline)
        return deadline

    @staticmethod
    def _finish_guard(deadline):
        need(time.monotonic() < deadline, 'PHASE_OR_GUARD_DEADLINE')

    def _bound(self, context):
        need(digest(self.context) == self.context_digest and digest(self.contract) == self.contract_digest and
             d.same(context, self.context), 'CONTROL_BINDING_MUTATED')
        self.verifier._bound()

    def install_lock(self): return self.lock

    def verify_outer_review(self, context):
        self._bound(context)
        return self.verifier.verify_outer_review(context)

    def preflight(self, context):
        self._bound(context); need(self.lock.held() is True, 'INSTALL_LOCK_REQUIRED')
        deadline = self._begin_guard(False)
        snapshot, evidence = self.observer.preflight(copy.deepcopy(context))
        d.validate_snapshot(snapshot, context['snapshot_sha256'])
        need(type(evidence) is dict and set(evidence) == {'schema','kind','snapshot_sha256','retained','writers',
             'install_admission','production_acceptance','target_mutations','fresh_snapshot_sha256',
             'fresh_writer_exclusion','fresh_process_proof','writer_observation_comparison'} and type(evidence['schema']) is int and
             evidence['schema'] == 1 and evidence['kind'] == 'PRIVATE_EPOCH7_ADMISSION_SPLIT_EVIDENCE' and
             evidence.get('snapshot_sha256') == context['snapshot_sha256'] and
             digest(evidence.get('retained')) == snapshot['retained_resource_sha256'], 'SNAPSHOT_SUPPORT_BINDING')
        snap.validate_writer_comparison(evidence['writer_observation_comparison'],evidence['writers'])
        need(evidence['install_admission'] == 'NOT_GRANTED' and
             evidence['production_acceptance'] == 'NOT_VERIFIED' and
             type(evidence['target_mutations']) is int and evidence['target_mutations'] == 0,
             'PREFLIGHT_OBSERVATION_ONLY')
        fresh = copy.deepcopy(snapshot)
        fresh['writer_exclusion'] = copy.deepcopy(evidence['fresh_writer_exclusion'])
        d.validate_snapshot(fresh,evidence['fresh_snapshot_sha256'])
        baseline_writer = {k:v for k,v in snapshot['writer_exclusion'].items() if k != 'evidence_sha256'}
        current_writer = {k:v for k,v in fresh['writer_exclusion'].items() if k != 'evidence_sha256'}
        need(d.same(baseline_writer,current_writer) and type(evidence['writers']) is dict and
             bool(evidence['writers']) and digest(evidence['writers']) == fresh['writer_exclusion']['evidence_sha256'],
             'FRESH_WRITER_EXCLUSION_BINDING')
        validate_process_view(evidence['fresh_process_proof'], self.contract,
                              self.contract['checkpoints'][0],self.owner_pid,context_sha256=self.context['context_sha256'],checkpoint_index=0)
        self._finish_guard(deadline)
        return observation(context, 'preflight', digest(evidence))

    def _resources(self, phase, boundary, index, names):
        values = self.observer.resources(copy.deepcopy(self.context), phase, boundary, tuple(sorted(names)))
        need(type(values) is dict and set(values) == set(names), 'EXACT_RESOURCE_OBSERVATIONS')
        for name, value in values.items():
            need(type(value) in (dict,list) and bool(value), 'MEASURED_RESOURCE_VALUE_REQUIRED')
            need(digest(value) == self.contract['checkpoints'][index]['resources'][name], 'RESOURCE_DRIFT')
        canonical(values)
        return digest(values)

    def _boundary(self, context, phase, boundary, index):
        self._bound(context); self.authority.phase(phase)
        deadline = self._begin_guard()
        resources = self._resources(phase, boundary, index, SECTIONS)
        processes = validate_process_view(self.observer.processes(copy.deepcopy(context), phase, boundary),
                                          self.contract, self.contract['checkpoints'][index], self.owner_pid,
                                          context_sha256=self.context['context_sha256'],checkpoint_index=index)
        # Re-read protected resources after process/cgroup collection.
        need(self._resources(phase, boundary, index, SECTIONS) == resources, 'RESOURCE_SCAN_RACE')
        self.authority.phase(phase)
        self._finish_guard(deadline)
        return observation(context, boundary + ':' + phase, digest({'resources':resources,'processes':processes}))

    def before_phase(self, context, phase):
        need(self.open_phase is None and self.next_index < len(PHASES) and
             phase == PHASES[self.next_index], 'PHASE_ORDER_OR_REPLAY')
        self.phase_deadline = time.monotonic() + ADAPTER_BOUNDS['phase_timeout_seconds']
        result = self._boundary(context, phase, 'before', self.next_index)
        self.open_phase = phase
        return result

    def after_phase(self, context, phase, effect_observation):
        need(self.open_phase == phase and phase == PHASES[self.next_index], 'PHASE_NOT_OPEN')
        check_observation(effect_observation, context, phase)
        result = self._boundary(context, phase, 'after', self.next_index + 1)
        self.next_index += 1; self.open_phase = None
        self.phase_deadline = None
        return result

    def effect_check(self, context, phase):
        self._bound(context)
        need(self.open_phase == phase and phase == PHASES[self.next_index], 'NO_OPEN_EFFECT_PHASE')
        self.authority.phase(phase)
        deadline = self._begin_guard()
        # A primitive may be between its exact before/after CAS (e.g. CLI
        # capture-finally). Only that phase's finite mutable domains are omitted;
        # it must enforce their immediate CAS and postconditions itself.
        names = SECTIONS - MUTATIONS[phase]
        resource_digest = self._resources(phase, 'effect', self.next_index, names)
        measured = self.observer.processes(copy.deepcopy(context), phase, 'effect')
        point = copy.deepcopy(self.contract['checkpoints'][self.next_index])
        if phase in ('activate_new_services','post_install_checks'):
            # Only exact before/after unit-property values are possible during
            # daemon-reload/enable/ordered starts. No arbitrary activating state,
            # unknown unit, UID-only process or new executable is accepted.
            after = self.contract['checkpoints'][self.next_index + 1]
            need(type(measured) is dict and type(measured.get('units')) is dict and
                 set(measured['units']) == snap.WRITER_UNITS, 'EXACT_INTERMEDIATE_UNITS')
            for unit, row in measured['units'].items():
                need(type(row) is dict and type(row.get('before')) is dict, 'INTERMEDIATE_UNIT_ROW')
                actual = row['before']; old = point['units'][unit]; new = after['units'][unit]
                choices_by_key={k:{old['properties'][k],new['properties'][k]} for k in STATIC_UNIT_FIELDS}
                socket_start = phase == 'activate_new_services' and unit in SOCKET_SERVICES
                if socket_start:
                    choices_by_key['SubState'].add('listening')
                if self.contract.get('schema')==2:
                    cached=self.contract['unit_transition_contract']['units'].get(unit)
                    if cached is not None:
                        for key in ('LoadState','UnitFileState','NeedDaemonReload'):
                            choices_by_key[key].update((cached['before'][key],cached['reloaded'][key]))
                        choices_by_key['NeedDaemonReload'].update(('yes','no'))
                    restored=self.contract['unit_transition_contract'].get('gateway_restoration')
                    if unit=='xuanjun-uk-openclaw.service' and restored is not None:
                        choices_by_key['LoadState'].update(('masked','loaded'))
                        choices_by_key['UnitFileState'].update(('masked',restored['boot_before'],'enabled'))
                        choices_by_key['NeedDaemonReload'].update(('yes','no'))
                need(all(actual.get(k) in choices_by_key[k] for k in STATIC_UNIT_FIELDS),
                     'UNREVIEWED_INTERMEDIATE_PROPERTY')
                pair = (actual.get('ActiveState'), actual.get('SubState'))
                choices = [(p['properties']['ActiveState'], p['properties']['SubState']) for p in (old,new)]
                if socket_start:
                    service_unit = SOCKET_SERVICES[unit][0]
                    service_props = measured['units'][service_unit]['before']
                    service_pair = (service_props.get('ActiveState'), service_props.get('SubState'))
                    if pair == ('active','listening'):
                        expected = self.contract['checkpoints'][self.next_index]['units'][service_unit]['properties']
                        need(service_pair == (expected['ActiveState'], expected['SubState']) and
                             service_pair[0] in ('inactive','failed'), 'SOCKET_LISTENING_BEFORE_SERVICE_ONLY')
                        choices.append(pair)
                    elif pair == ('active','running'):
                        need(service_pair == ('active','running'), 'SOCKET_RUNNING_SERVICE_REQUIRED')
                    elif service_pair == ('active','running'):
                        need(False, 'ACTIVE_SERVICE_SOCKET_REQUIRED')
                need(pair in choices, 'UNREVIEWED_INTERMEDIATE_STATE')
                chosen = new if pair == choices[1] or socket_start and pair == ('active','listening') else old
                point['units'][unit] = {'properties':{k:actual[k] for k in STATIC_UNIT_FIELDS},
                    'main_required':chosen['main_required'], 'main_role_sha256':chosen['main_role_sha256']}
        validate_process_view(measured, self.contract, point, self.owner_pid,
                              allow_observer_db=phase == 'reopen_existing_database',
                              context_sha256=self.context['context_sha256'],
                              allow_pending_service_receipts=phase == 'activate_new_services',
                              checkpoint_index=self.next_index)
        need(self._resources(phase, 'effect', self.next_index, names) == resource_digest, 'EFFECT_RESOURCE_RACE')
        self.authority.phase(phase)
        self._finish_guard(deadline)
        return True

    def check(self, phase): return self.effect_check(self.context, phase)

    def cleanup_check(self, context, operation, unit=None):
        self._bound(context)
        need((operation, unit) in CLEANUP, 'CLEANUP_SCOPE')
        # Independent claim/lock authority intentionally survives runtime drift.
        # receipt() alone proves approval/lock, not that the outer claim exists.
        self.authority.cleanup(operation,unit)
        return True

    def observe_stopped_unit(self, context, operation, unit):
        need(operation in ('observe_stopped_before','observe_stopped_after'), 'STOP_OBSERVATION_SCOPE')
        self.cleanup_check(context, operation, unit)
        deadline = self._begin_guard(False)
        row = self.observer.unit(copy.deepcopy(context), operation, unit)
        validate_unit_row(unit, row, stopped=True)
        self.authority.receipt()
        self._finish_guard(deadline)
        return observation(context, operation + ':' + unit, digest(row))

    def tls_contents(self):
        self.authority.receipt()
        deadline = self._begin_guard(False)
        value = self.observer.tls_contents(copy.deepcopy(self.context))
        wanted = {k: self.context['tls_change'][k] for k in ('certificate_sha256',)}
        need(type(value) is dict and set(value) == {'certificate_sha256','tree_fingerprint_sha256'} and
             value['certificate_sha256'] == wanted['certificate_sha256'], 'TLS_CERTIFICATE_DRIFT')
        # Tree fingerprint is separately bound in the approved TLS resource view.
        for digest_value in value.values(): d.hash_value(digest_value)
        self.authority.receipt(); self._finish_guard(deadline)
        return copy.deepcopy(value)

    def quiescence(self):
        phase = 'quiesce_exact_epoch'
        self.effect_check(self.context, phase)
        # effect_check already validates the exact all-stopped checkpoint; a
        # second independent census would silently double the guard budget.
        return {k:True for k in ('identity_verified','coordinator_inactive','parent_unit_inactive',
                                 'cgroups_empty','restart_inhibited')}
