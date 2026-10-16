"""Production-shaped public inventory fixture; no production/host authority.

All historical payload/cache metadata, topology review and tool/host facts are
synthetic. The current 107-file runtime, every pure compiler, all validators,
seed hydration and serializers are real. Only the existing four historical
private-byte test pins are mapped by native_pins; no compiler result is mocked.

The fixture is portable in kit/tests or with explicit environment paths. It
never guesses another checkout, contacts a host, or executes Python 3.6.
"""
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import types

HERE = pathlib.Path(__file__).resolve().parent


def selected_root(variable, marker, candidates):
    supplied = os.environ.get(variable)
    paths = [pathlib.Path(supplied)] if supplied else candidates
    for path in paths:
        if (path / marker).is_file():
            return path.resolve()
    raise RuntimeError('Set %s to a directory containing %s' % (variable, marker))


KIT = selected_root('EPOCH7_RESOURCE_TEST_KIT_ROOT', 'epoch7_recovery_entry.py', list(HERE.parents))
CODE = pathlib.Path(os.environ.get('EPOCH7_RESOURCE_TEST_HELPERS', str(KIT / 'helpers'))).resolve()
PATHS = [CODE, KIT / 'helpers', KIT / 'xuanjun-p2-package/stage1', KIT / 'xuanjun-p2-package/scripts']
PATHS += sorted(path for path in (KIT / 'tests').iterdir() if path.is_dir())
sys.path[:0] = [str(path) for path in PATHS]

import epoch7_delta as d
import epoch7_host_factory as factory
import epoch7_resource_observer as observer
import epoch7_resource_plan as resource
import epoch7_additive_identity as owner
import epoch7_additive_server as server
import node_sqlite_probe as node
from test_epoch7_full_factory_fixture import make_seed, native_pins, directory, meta, packed
from test_node_sqlite_probe import fixture_proof

LIMIT = 2 * 1024 * 1024
HISTORICAL_FILES = 102
HISTORICAL_CACHES = 48


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def json_bytes(value):
    """Measurement only: never used instead of production bounded canonical."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def rebind_synthetic_observation(seed):
    """Rebuild all dependent synthetic pins after constructing fixture facts."""
    obs = seed['observation']
    retained = obs['evidence']['retained']
    obs['policy_sha256'] = d.digest(obs['policy'])
    retained['policy_sha256'] = obs['policy_sha256']
    obs['snapshot']['cache_inventories'] = {
        root: d.digest(evidence) for root, evidence in retained['release_evidence'].items()}
    obs['snapshot']['retained_resource_sha256'] = d.digest(retained)
    writers = obs['evidence']['writers']
    obs['snapshot']['writer_exclusion']['evidence_sha256'] = d.digest(writers)
    obs['evidence']['writer_observation_comparison'] = factory.snap.validate_writer_transition(writers, writers)
    obs['snapshot_sha256'] = d.digest(obs['snapshot'])
    obs['evidence']['snapshot_sha256'] = obs['snapshot_sha256']
    for key in ('evidence', 'unit_metadata', 'probe_metadata', 'openclaw_profile'):
        obs[key + '_sha256'] = d.digest(obs[key])
    attempt = obs['finite_probe']
    policy = attempt['policy']
    policy['node_sqlite'] = node.binding_from_observation(obs)
    pin = hashlib.sha256(packed(policy)).hexdigest()
    binding = policy['node_sqlite']
    proof = fixture_proof(binding['node'], policy['nonce'], pin, binding['probe_input_sha256'])
    receipt = packed({'schema': 1, 'nonce': policy['nonce'], 'policy_sha256': pin,
                      'events': [{'event': 'NODE_SQLITE_OBSERVED', 'detail': proof}]})
    attempt['policy_sha256'] = pin
    attempt['result']['node_sqlite'] = proof
    attempt['result']['created_receipt'].update(
        sha256=hashlib.sha256(receipt).hexdigest(), node_sqlite_event_sha256=d.digest(proof),
        metadata={k: v for k, v in meta(receipt, mode=0o600).items() if k not in ('kind', 'sha256')})
    seed['fresh_release_parent'].update(observation_sha256=d.digest(obs), policy_sha256=obs['policy_sha256'])


def large_seed():
    seed = make_seed()
    obs = seed['observation']
    retained = obs['evidence']['retained']
    names = sorted(seed['source_payloads'])[:HISTORICAL_FILES]
    assert len(names) == HISTORICAL_FILES
    py_names = [name for name in names if name.startswith('stage1/') and name.endswith('.py')][:HISTORICAL_CACHES]
    assert len(py_names) == HISTORICAL_CACHES
    for release_index, (root, policy) in enumerate(sorted(obs['policy']['releases'].items())):
        files, caches, directories = {}, {}, {}
        for index, name in enumerate(names):
            # Real current package names give representative path lengths. Old
            # content hashes are explicitly synthetic, never represented as
            # authenticated bytes from the historical 102-file releases.
            raw = ('SYNTHETIC_HISTORICAL_RELEASE_%d:%s' % (release_index, name)).encode('ascii')
            files[name] = meta(raw, mode=0o555 if name in ('scripts/xj-root-broker-client',
                               'scripts/uk-owner-workbench-config.py') else 0o444,
                               ino=10000 + release_index * 1000 + index)
            absolute = root + '/' + name
            if absolute in retained['native_components']['components']:
                component = dict(retained['native_components']['components'][absolute], mode=0o444)
                retained['native_components']['components'][absolute] = copy.deepcopy(component)
                files[name] = component
        for index, name in enumerate(py_names):
            cache = 'stage1/__pycache__/' + pathlib.PurePosixPath(name).stem + '.cpython-36.pyc'
            raw = ('SYNTHETIC_RETAINED_CPYTHON36_CACHE_%d:%s' % (release_index, name)).encode('ascii')
            caches[cache] = {'file': meta(raw, mode=0o444, ino=10500 + release_index * 1000 + index),
                             'source_sha256': files[name]['sha256'], 'staging': policy['cache_staging']}
        for name in list(files) + list(caches):
            parent = os.path.dirname(root + '/' + name)
            while parent == root or parent.startswith(root + '/'):
                if parent not in directories:
                    directories[parent] = directory(mode=0o555, ino=20000 + len(directories) + release_index * 1000)
                obs['policy']['directories'][parent] = {'uid': 0, 'gid': 0, 'mode': 0o555}
                parent = os.path.dirname(parent)
        policy['payloads'] = {name: row['sha256'] for name, row in files.items()}
        policy['caches'] = {name: row['file']['sha256'] for name, row in caches.items()}
        retained['release_evidence'][root] = {'manifest_sha256': policy['manifest_sha256'],
            'files': files, 'caches': caches, 'directories': directories}
    rebind_synthetic_observation(seed)
    return seed


def wrapper_modules():
    root = selected_root('EPOCH7_RESOURCE_TEST_PREPARATION_ROOT', 'epoch7_prepare.py', [KIT / 'preparation'])
    sys.path.insert(0, str(root))
    preparation = load_file(root / 'epoch7_prepare.py', 'resource_test_preparation')
    data = load_file(root / 'epoch7_prepare_data.py', 'resource_test_preparation_data')
    topology = load_file(root / 'epoch7_topology_projection.py', 'epoch7_topology_projection')
    entry_path = pathlib.Path(os.environ.get('EPOCH7_RESOURCE_TEST_ENTRY', str(KIT / 'epoch7_recovery_entry.py')))
    entry = load_file(entry_path, 'resource_test_entry')
    return preparation, data, topology, entry


def wrapper_seed():
    seed = large_seed()
    obs = seed['observation']
    retained = obs['evidence']['retained']
    retained['additive_paths_absent'] = sorted((owner.PATH, server.PATH))
    retained['prerequisites']['directories'][owner.PARENT] = directory()
    tools = {'/usr/lib/systemd/systemd': b'\x7fELFsynthetic manager',
             '/usr/bin/systemctl': b'\x7fELFsynthetic systemctl'}
    manager = obs['evidence']['writers']['manager']
    manager['binary_sha256'] = hashlib.sha256(tools[manager['binary_path']]).hexdigest()
    for path, raw in tools.items():
        retained['files'][path] = meta(raw, mode=0o755)
        obs['policy']['files'][path] = {key: retained['files'][path][key] for key in ('sha256', 'uid', 'gid', 'mode')}
    for label in ('systemctl', 'systemd'):
        tool = obs['policy']['executables'][label]
        tool['sha256'] = retained['files'][tool['path']]['sha256']
    obs['openclaw_profile']['recipe_evidence']['quiet_bootstrap']['manager_sha256'] = d.digest(manager)
    obs['unit_metadata']['sections']['command_resolutions']['evidence']['provenance'].update(
        manager_sha256=d.digest(manager), systemctl_sha256=hashlib.sha256(tools['/usr/bin/systemctl']).hexdigest())
    for unit in server.UNIT_PROPERTIES:
        obs['evidence']['writers']['units'][unit]['state'].update(DropInPaths='', NeedDaemonReload='no')
    rebind_synthetic_observation(seed)
    return seed, tools


def synthetic_topology(topology):
    """Structurally validated public synthetic review; grants no approval."""
    units = {unit: {root + '/' + unit + '.d': {'present': False, 'files': {}}
                   for root in topology.DROPIN_ROOTS} for unit in topology.DROPIN_UNITS}
    dropins = {'state': 'MEASURED_UNREVIEWED', 'evidence': {
        'units': units, 'unsupported': [], 'raw_unit_bytes_returned': False}}
    unit = 'xuanjun-development-dispatcher.service'
    latecheck = {'state': 'MEASURED_UNREVIEWED', 'evidence': {
        'unit': unit, 'collector_path_used': False,
        'resolution': {'command': 'git', 'path_environment': '/usr/bin', 'entries': [{
            'directory': '/usr/bin', 'uid': 0, 'gid': 0, 'mode': 0o755, 'dev': 1, 'ino': 2,
            'git': {'path': '/usr/bin/git', 'sha256': '9' * 64, 'dev': 1, 'ino': 3}}]},
        'provenance': {'source': 'SYSTEM_MANAGER_CHILD_ENVIRONMENT', 'systemctl_sha256': '4' * 64,
            'manager_sha256': '5' * 64, 'upstream_version': '239', 'distro_matching_build': 'NOT_VERIFIED',
            'unit_sha256': '8' * 64, 'dropins_sha256': d.digest(units[unit]),
            'public_unit_environment': {'environment_names': [], 'path_overrides': 'PROVEN_ABSENT_IN_SUPPORTED_SYNTAX'}}}}
    inventory = {'schema': 2, 'kind': 'SAVED_R7_UNIT_DROPIN_INVENTORY', 'unit_metadata_sha256': '6' * 64,
        'dropins_section': dropins, 'dropins_section_sha256': d.digest(dropins),
        'latecheck_section': latecheck, 'latecheck_section_sha256': d.digest(latecheck),
        'producer_sources': dict(topology.SAVED_PRODUCER_PINS),
        'reread_provenance': 'PINNED_COLLECTOR_TWO_READS_AND_FULL_ELEVEN_UNIT_LATE_RECHECK',
        'fresh_directory_authority': 'NOT_REPRESENTED_BY_SAVED_INVENTORY', 'collection': 'NOT_RUN'}
    topology.validate_saved_unit_dropins(inventory)
    value = {'schema': 1, 'purpose': 'ROOT_MANAGER_SHARED_INIT_PROOF',
        'creator': {'pid': 1, 'uid': 0, 'gid': 0, 'exe': '/usr/lib/systemd/systemd',
            'cgroup_sha256': '1' * 64, 'pid_namespace_role': 'SYSTEM_INIT_SHARED_WITH_CLIENTS'},
        'endpoint_identity': {'uid': 1003, 'gid': 1007, 'mode': 0o660},
        'clients': {role: {'same_pid_namespace': True, 'same_proc_namespace': True, 'readpaths_verified': True}
                    for role in server.PROFILES},
        'exclusive_delivery_reviewed': True, 'systemd_version': 239, 'evidence_records_sha256': '2' * 64}
    raw = packed(value)
    proposal = {'topology_raw': raw, 'topology_sha256': hashlib.sha256(raw).hexdigest(),
                'expected_review_body': {'fixture_only': 'SYNTHETIC_REVIEW_NOT_HOST_AUTHORITY'}}
    review = {'review_id': 7000000001, 'approval_body_sha256': '3' * 64,
              'evidence_sha256': proposal['topology_sha256']}
    return inventory, proposal, review


def local_publication_entry(real):
    """Only UID/GID display is mapped; actual no-follow filesystem IO remains."""
    def mapped(info):
        values = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
        values.update(st_uid=0, st_gid=0)
        return types.SimpleNamespace(**values)

    class Tree:
        def __init__(self, path):
            self.real = real.DescriptorTree(path, owners=((0, 0), (os.getuid(), os.getgid())))
            self.fd, self.closed = self.real.fd, False
            self.opened = [[fd, parent, name, logical, tuple(list(stamp[:3]) + [0, 0] + list(stamp[5:]))]
                           for fd, parent, name, logical, stamp in self.real.opened]
        def parent(self, name): return self.real.parent(name)
        def read(self, *args, **kwargs): return self.real.read(*args, **kwargs)
        def _authority(self, *args, **kwargs): return mapped(self.real._authority(*args, **kwargs))
        def recheck(self):
            for fd, parent, name, logical, before in self.opened:
                if real.stamp(self._authority(fd, True)) != before:
                    raise ValueError('SYNTHETIC_PUBLICATION_ANCESTRY_RACE')
                if parent is not None and real.stamp(mapped(os.stat(name, dir_fd=parent, follow_symlinks=False))) != before:
                    raise ValueError('SYNTHETIC_PUBLICATION_BINDING_RACE')

    proxy = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os) if not name.startswith('__')})
    proxy.stat = lambda *args, **kwargs: mapped(os.stat(*args, **kwargs))
    proxy.fstat = lambda *args, **kwargs: mapped(os.fstat(*args, **kwargs))
    return types.SimpleNamespace(DescriptorTree=Tree, stamp=real.stamp), proxy
