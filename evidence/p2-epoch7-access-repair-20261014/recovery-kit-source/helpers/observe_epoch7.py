"""Single fixed-scope observation-only collector; never install admission.

Missing hashes are measured under protected ancestry rather than invented.
Historical immutable manifests/native sidefile/baseline are still pinned. The
resulting policy is explicitly UNREVIEWED and must be independently accepted
before strict replay or a new recovery approval. No host action on import.
"""
import argparse
import contextlib
import json
import os
import socket
import stat
import sys
import time

import epoch7_delta as d
import epoch7_snapshot as c
import snapshot_io as concrete
import reviewed_scanner as reviewed

RELEASE_MANIFESTS = (
    '9bb1d7ae186e43b4ea9fa720f7368475af3979d225bee830db4ac90b5083b1e3',
    c.RETAINED_NATIVE_RELEASE, d.OLD_MANIFEST)
READINESS = c.BASE + '/consolidated-readiness-38503324102/protected-readiness-snapshot.json'
READINESS_SHA = '2eeb429cc186b25f41f00217b6710a0a055d00058418ded0c187e350c6f27fab'
ORIGINAL_PLAN_SHA = 'ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a'
OWNER_PASSIVE_SHA = '84547f6ae1aafd37962daf21518def24994557dae60c00533bc1228564686049'
BOOTSTRAP = frozenset('/etc/xuanjun-owner-callback/' + n for n in (
    'owner-user-id', 'owner-chat-id', 'owner-callback-auth', 'owner-callback-hmac', 'owner-dashboard-token')) | {
    '/etc/xuanjun-development/github-intake-token', c.NATIVE}
TOOLS = {'systemctl': '/usr/bin/systemctl', 'openssl': '/usr/bin/openssl', 'rpm': '/usr/bin/rpm', 'systemd': '/usr/lib/systemd/systemd', 'git': '/usr/bin/git'}


def authority(logical, info, declared=None):
    """Directory owners are scoped to existing user-private subtrees only."""
    if declared and logical in declared:
        row = declared[logical]
        c.need(logical.startswith(('/var/lib/xuanjun-development/', '/etc/xuanjun-', '/opt/xuanjun-')) and
               row['uid'] in (0,1003,1004,1005,1008) and not row['mode'] & 0o7022 and
               stat.S_ISDIR(info.st_mode) and
               (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)) == (row['uid'],row['gid'],row['mode']),
               'OBSERVATION_DECLARED_DIRECTORY_AUTHORITY')
        return {k:row[k] for k in ('uid','gid','mode')}
    uid = 0
    if logical == '/home/xuanjun_dev' or logical.startswith('/home/xuanjun_dev/'):
        uid = 1002
    elif any(logical == root or logical.startswith(root + '/') for root in (
            '/var/lib/xuanjun-development/control.git', '/var/lib/xuanjun-development/service-home')):
        uid = 1003
    elif logical == d.GENERATION:
        uid = 1003
    elif logical.startswith('/var/lib/xuanjun-development/') and any(
            logical == root or logical.startswith(root + '/') for root in (
                '/var/lib/xuanjun-development/worker-home', '/var/lib/xuanjun-development/nginx-home')):
        uid = 1005 if '/worker-home' in logical else 1008
    c.need(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and not info.st_mode & 0o7022,
           'OBSERVATION_ANCESTOR_AUTHORITY')
    if logical == c.TRANSACTION or logical.startswith(c.TRANSACTION + '/') or logical == c.TLS:
        c.need((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o700), 'OBSERVATION_PRIVATE_DIRECTORY')
    return {k: concrete.metadata(info)[k] for k in ('uid', 'gid', 'mode')}


class ObservationReader(concrete.DescriptorReader):
    def _authority(self, fd, logical):
        info = os.fstat(fd); measured = authority(logical, info, getattr(self,'declared_directories',None))
        c.need(concrete.xattr(fd, 'system.posix_acl_access') is None and
               concrete.xattr(fd, 'system.posix_acl_default') is None, 'OBSERVATION_UNREVIEWED_ACL')
        if logical in self.pins:
            c.need(self.pins[logical] == measured, 'OBSERVATION_ANCESTOR_CHANGED')
        else:
            c.need(len(self.pins) < 4096, 'OBSERVATION_DIRECTORY_BOUND'); self.pins[logical] = measured
        return info


class ObservationIO(ObservationReader, concrete.LocalReadOnlyIO):
    def __init__(self, directories, locks):
        c.need(os.geteuid() == 0 and socket.gethostname().split('.')[0] == c.HOST, 'FIXED_HOST_ROOT_REQUIRED')
        concrete.DescriptorReader.__init__(self, directories)
        self.policy = {'files': {}, 'executables': {}, 'directories': directories}
        self.locks = locks; self.deadline = time.monotonic() + 600
        self.observed_metadata = {}

    def read(self, name, maximum=16777216):
        result = concrete.LocalReadOnlyIO.read(self, name, maximum=maximum)
        self.observed_metadata[name] = result[1]
        return result


def measured_policy(io):
    """Bounded discovery from fixed roots and protected journal-declared whitelists.

    Does not label measured data as approved. Any unknown path/type/effect or
    incompatible retained state rejects the observation instead of broadening scope.
    """
    files, raw = {}, {}
    def measure(name, maximum=16777216):
        data, row = io.read(name, maximum=maximum)
        files[name] = {k: row[k] for k in ('sha256', 'uid', 'gid', 'mode')}; raw[name] = data
        return data, row
    for name in sorted(c.MANDATORY_FILES | BOOTSTRAP | {READINESS}): measure(name)
    c.need(c.sha(raw[c.PLAN]) == ORIGINAL_PLAN_SHA, 'OBSERVATION_ORIGINAL_PLAN_PIN')
    c.need(c.sha(raw[READINESS]) == READINESS_SHA, 'OBSERVATION_READINESS_PIN')
    c.need(c.sha(raw[c.NATIVE]) == c.RETAINED_NATIVE_SHA, 'OBSERVATION_RETAINED_NATIVE_PIN')
    transaction = io.inventory(c.TRANSACTION)
    c.need(0 < len(transaction) <= 4096, 'OBSERVATION_TRANSACTION_BOUND')
    for name, digest in transaction.items():
        c.need(name.startswith(c.TRANSACTION + '/'), 'OBSERVATION_TRANSACTION_SCOPE')
        c.relative(name[len(c.TRANSACTION)+1:]); measure(name)
        c.need(files[name]['sha256'] == digest, 'OBSERVATION_TRANSACTION_RACE')
        c.need((files[name]['uid'], files[name]['gid'], files[name]['mode']) == (0,0,0o600),
               'OBSERVATION_TRANSACTION_FILE_AUTHORITY')
    plan = c.decode(raw[c.PLAN]); baseline = c.decode(raw[READINESS])['sections']['remaining_control_entry_inventory']
    io.declared_directories = {r['path']: r for r in plan['runtime']['prerequisites'].get('directories', [])}
    bootstrap = c.decode(raw[c.TRANSACTION + '/bootstrap-files.json'])['files']
    c.need(len(bootstrap) == 7 and {r['target'] for r in bootstrap} == BOOTSTRAP, 'OBSERVATION_BOOTSTRAP_SCOPE')
    # Commands are local read-only queries, executed only by observe_host on UK.
    executables = {}
    for label, name in TOOLS.items():
        unused, row = measure(name)
        c.need(row['uid'] == row['gid'] == 0 and row['mode'] & 0o111, 'OBSERVATION_TOOL_AUTHORITY')
        executables[label] = {'path': name, 'sha256': row['sha256']}
    io.policy['files'], io.policy['executables'] = files, executables
    releases = {}
    for digest in RELEASE_MANIFESTS:
        root = '/opt/xuanjun-control-releases/integration-' + digest[:16]
        manifest_raw, meta = io.read(root + '/INTEGRATION_MANIFEST.json')
        c.need(meta['sha256'] == digest, 'OBSERVATION_HISTORICAL_MANIFEST')
        manifest = c.decode(manifest_raw); payloads = manifest.get('files')
        c.need(isinstance(payloads, dict) and len(payloads) == 102, 'OBSERVATION_HISTORICAL_PAYLOAD_SET')
        inventory = io.inventory(root); observed, caches, staging = {}, {}, set()
        expected = set(root + '/' + c.relative(n) for n in payloads) | {root + '/INTEGRATION_MANIFEST.json'}
        identities = set(manifest['rendering']['identity_files'])
        for rel, expected_hash in payloads.items():
            data, row = io.read(root + '/' + rel)
            c.need((row['uid'], row['gid'], row['mode']) == (0,0,0o555 if rel in {'scripts/xj-root-broker-client','scripts/uk-owner-workbench-config.py'} else 0o444), 'OBSERVATION_RELEASE_AUTHORITY')
            if rel in identities:
                # Reverse exactly the two immutable typed substitutions. Hashing
                # the reconstructed source binds bytes to the historical manifest.
                restored = data.replace(('integration-' + digest[:16]).encode(), b'@@RELEASE_DIRECTORY@@').replace(
                    digest.encode(), b'@@ARTIFACT_SHA256@@')
                c.need(c.sha(restored) == expected_hash, 'OBSERVATION_RENDERED_SOURCE_HASH')
            else: c.need(row['sha256'] == expected_hash, 'OBSERVATION_SOURCE_HASH')
            observed[rel] = row['sha256']
        for name in set(inventory) - expected:
            c.need(name.startswith(root + '/stage1/__pycache__/'), 'OBSERVATION_UNCLASSIFIED_RELEASE_FILE')
            rel = name[len(root)+1:]
            c.need(__import__('re').fullmatch(r'stage1/__pycache__/[a-z][a-z0-9_]*\.cpython-36\.pyc', rel), 'OBSERVATION_CACHE_SCOPE')
            data, row = io.read(name)
            c.need((row['uid'], row['gid'], row['mode']) == (0,0,0o444), 'OBSERVATION_CACHE_AUTHORITY')
            source_rel = 'stage1/' + os.path.basename(name)[:-len('.cpython-36.pyc')] + '.py'
            c.need(source_rel in observed, 'OBSERVATION_CACHE_SOURCE')
            source, source_meta = io.read(root + '/' + source_rel)
            staging.add(io.cache_staging(root, source_rel, data, source, source_meta)); caches[rel] = row['sha256']
        c.need(len(staging) == 1 and caches and io.inventory(root) == inventory, 'OBSERVATION_CACHE_SET_OR_RACE')
        io.directory_inventory(root)
        releases[root] = dict(manifest_sha256=digest, payloads=observed, caches=caches, cache_staging=next(iter(staging)))
    databases = {}
    for name in c.DATABASES:
        data, meta = io.read(name, maximum=67108864); logical = io.logical_manifest(data)
        sides = {}
        for suffix in ('-wal','-shm','-journal'):
            if io.absent(name + suffix): continue
            c.need(name == c.SOURCE_DB and suffix in ('-wal','-shm'), 'OBSERVATION_UNCLASSIFIED_DB_SIDECAR')
            content, row = io.read(name + suffix)
            c.need((suffix != '-wal' or content == b'') and (suffix != '-shm' or len(content) == 32768),
                   'OBSERVATION_SOURCE_SIDECAR_STATE')
            sides[suffix] = {k:row[k] for k in ('sha256','uid','gid','mode')}
        databases[name] = dict({k:meta[k] for k in ('sha256','uid','gid','mode')},
                               sidecars=sides, logical_manifest_sha256=d.digest(logical))
    scheduler = {}
    for root in sorted(c.SCHEDULER_ROOTS): scheduler.update(io.scheduler_inventory(root))
    c.need(scheduler == {r['path']:r['sha256'] for r in baseline['scheduler_metadata']}, 'OBSERVATION_SCHEDULER_BASELINE_DRIFT')
    old_units = baseline['registered_control_units']
    expected_names = set(old_units) | {n for n in c.WRITER_UNITS if n.startswith(('xj-','xuanjun-'))}
    listing = io.command('systemctl', ['list-unit-files','--no-legend','--no-pager']).decode('utf-8','strict')
    actual_names = {line.split()[0] for line in listing.splitlines() if line.split() and line.split()[0].startswith(('xj-','xuanjun-'))}
    c.need(actual_names == expected_names, 'OBSERVATION_CONTROL_UNIT_SET')
    control = {}
    for name in sorted(actual_names):
        paths = {'/etc/systemd/system/' + name}
        for script in old_units.get(name, {}).get('script_metadata', []):
            script_path = script['path']; c.path(script_path)
            c.need(script_path.startswith(('/home/xuanjun_dev/', '/usr/local/bin/', '/opt/', '/etc/')),
                   'OBSERVATION_CONTROL_SCRIPT_SCOPE')
            data, unused = measure(script_path)
            c.need(c.sha(data) == script['sha256'], 'OBSERVATION_CONTROL_SCRIPT_PIN'); paths.add(script_path)
        control[name] = {}
        for file_name in paths:
            if file_name in c.LEGACY_MASKS:
                io.mask(file_name); control[name][file_name] = c.sha(b'/dev/null')
            else:
                unused, row = measure(file_name); control[name][file_name] = row['sha256']
    io.directory_inventory(c.TRANSACTION)
    io.native_identity(c.decode(raw[c.NATIVE]), c.decode(raw['/etc/xuanjun-development/p2-native-controller.binding.json']))
    # Populate exact measured ancestry for future strict replay, including private
    # TLS paths and prerequisite declarations. No secrets enter the policy.
    io.directory(d.GENERATION); io.tls(io.policy)
    io.prerequisites(plan['runtime']['prerequisites'], c.decode(raw[c.TRANSACTION+'/prerequisites.json']),
                     c.decode(raw[c.TRANSACTION+'/rpm-prerequisites.json']))
    for root in c.PUBLISHERS: io.directory(root)
    publisher_rows = c.decode(raw[c.TRANSACTION+'/publisher-bootstrap.json'])['directories']
    control_row = next(row for row in publisher_rows if row['target'] == concrete.CONTROL_GIT)
    io.control_git_source(plan['runtime']['publisher'], control_row,
        c.sha(raw[c.TRANSACTION+'/publisher-bootstrap.json']))
    io._manager()  # Fresh per-observation identity, never persisted as an immutable boot pin.
    policy = dict(schema=1, kind='EPOCH7_MEASURED_READ_ONLY_PINS', hostname=c.HOST, transaction_id=d.TX,
        owner_evidence_sha256=OWNER_PASSIVE_SHA, files=files, directories=io.pins,
        transaction_inventory={n[len(c.TRANSACTION)+1:]:v for n,v in transaction.items()},
        releases=releases, databases=databases, scheduler_files=scheduler, control_units=control,
        executables=executables)
    return c.validate_policy(policy)


def observe_with_io(io):
    """Dependency-injected observation, for fixture tests and the fixed host wrapper."""
    policy = measured_policy(io)
    io.policy = policy
    snapshot, evidence = c.collect(policy, io)
    return {'schema': 1, 'kind': 'EPOCH7_OBSERVATION_ONLY_UNREVIEWED',
        'independent_acceptance': 'PENDING', 'install_admission': 'NOT_GRANTED',
        'policy': policy, 'policy_sha256': d.digest(policy), 'snapshot': snapshot,
        'snapshot_sha256': d.digest(snapshot), 'evidence': evidence, 'evidence_sha256': d.digest(evidence)}


def observe_host(candidate_root=None):
    c.need(os.geteuid() == 0 and socket.gethostname().split('.')[0] == c.HOST, 'FIXED_HOST_ROOT_REQUIRED')
    reader = ObservationReader({})
    pins = {}
    for name, mode in ((c.INSTALL_LOCK,0o600),(c.ACTIVATION_LOCK,0o644)):
        raw, info = reader.read(name)
        c.need((info['uid'],info['gid'],info['mode']) == (0,0,mode), 'OBSERVATION_EXISTING_LOCK_AUTHORITY')
        pins[name] = {k:info[k] for k in ('sha256','uid','gid','mode')}
    with concrete.existing_locks(reader, {'files':pins}) as locks:
        backend = ObservationIO(reader.pins, locks)
        from probe_metadata import collect_probe_ingredients
        probe_metadata=collect_probe_ingredients(backend,candidate_root=candidate_root)
        from unit_metadata import collect_unit_facts
        unit_metadata=collect_unit_facts(backend)
        from unit_metadata import collect_source_review_inputs
        source_review_inputs=collect_source_review_inputs(backend,unit_metadata)
        from openclaw_metadata import prime_profile_scope,collect_openclaw_profile
        prime_profile_scope(backend,unit_metadata,candidate_root)
        try:
            value=observe_with_io(backend)
        except (KeyboardInterrupt, SystemExit): raise
        except Exception as error:
            label = str(error) if isinstance(error, ValueError) else 'READ_OR_QUERY_UNAVAILABLE'
            if not __import__('re').fullmatch(r'[A-Z0-9_]{1,128}', label): label = 'INVALID_OR_UNSUPPORTED_EVIDENCE'
            value={'schema':1, 'kind':'EPOCH7_OBSERVATION_ONLY_HOLD',
                'failure_code':label, 'independent_acceptance':'PENDING', 'install_admission':'NOT_GRANTED',
                'observed_file_metadata':backend.observed_metadata, 'observed_directories':backend.pins}
        value['probe_metadata']=probe_metadata
        value['probe_metadata_sha256']=d.digest(probe_metadata)
        value['unit_metadata']=unit_metadata
        value['unit_metadata_sha256']=d.digest(unit_metadata)
        value['source_review_inputs']=source_review_inputs
        value['source_review_inputs_sha256']=d.digest(source_review_inputs)
        value['openclaw_profile']=collect_openclaw_profile(backend,unit_metadata,value,candidate_root)
        value['openclaw_profile_sha256']=d.digest(value['openclaw_profile'])
        return value


ObservationIO.scheduler_inventory = staticmethod(lambda root: reviewed.bounded_file_inventory(root, optional=True))


def persist_private(path, value):
    """Only new private observation output under existing protected candidate dir."""
    c.path(path)
    c.need(os.path.dirname(path) == c.CAND and __import__('re').fullmatch(
        r'epoch7-observation-[0-9a-f]{16}\.private\.json', os.path.basename(path)), 'OBSERVATION_OUTPUT_SCOPE')
    raw = d.canonical(value) + b'\n'
    c.need(len(raw)<=67108864,'OBSERVATION_PRIVATE_OUTPUT_BOUND')
    # Reader pins protected no-follow ancestors independently; no mkdir/chmod.
    reader = ObservationReader({})
    with reader.parent(path) as (parent, leaf):
        fd = os.open(leaf, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC, 0o600, dir_fd=parent)
        try:
            offset=0
            while offset < len(raw):
                size=os.write(fd,raw[offset:]);c.need(size>0,'OBSERVATION_OUTPUT_SHORT_WRITE');offset+=size
            os.fsync(fd)
        finally:os.close(fd)
        os.fsync(parent)
    c.need(reader.read(path,maximum=67108864)[0] == raw,'OBSERVATION_OUTPUT_READBACK')
    return c.sha(raw)


def main():
    parser=argparse.ArgumentParser(description='Fixed UK epoch7 read-only observation, no admission')
    parser.add_argument('--output',required=True)
    parser.add_argument('--candidate-root',help='Exact authenticated staged public runtime root')
    args=parser.parse_args()
    try:
        value=observe_host(candidate_root=args.candidate_root);digest=persist_private(args.output,value)
    except (KeyboardInterrupt,SystemExit):raise
    except Exception:
        # Never print private exception text, filenames, stdout, credentials or argv.
        print('EPOCH7_OBSERVATION_HOLD_NOT_INSTALL_ADMISSION',file=sys.stderr)
        return 1
    print(json.dumps({'schema':1,'kind':value['kind'],'private_file_sha256':digest,
        'snapshot_sha256':value.get('snapshot_sha256'),'policy_sha256':value.get('policy_sha256'),
        'probe_ingredient_state':value['probe_metadata']['ingredient_state'],
        'independent_acceptance':'PENDING','install_admission':'NOT_GRANTED'},sort_keys=True))
    return 0 if value['kind']=='EPOCH7_OBSERVATION_ONLY_UNREVIEWED' else 2


if __name__=='__main__':sys.exit(main())
