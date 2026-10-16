#!/usr/bin/env python3
"""Fixed successor preparation only. No claim, lock, phase, resume or review signing.

New artifact pins are deliberately UNBOUND. The future protected invocation may
only read the fixed original inputs/kit and predecessor, and exclusively create
three new private files. Local tests explicitly replace source/host boundaries.
"""
import argparse
import builtins
import contextlib
import copy
import errno
import hashlib
import importlib
import json
import os
import re
import signal
import socket
import stat
import sys
import time
import types

HOST = 'iZd7oeikknn1z21sq6ji6zZ'
BASE = '/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
CAND = BASE + '/complete-install-candidate-38503014520'
OLD_ROOT = CAND + '/epoch7-recovery-candidate-r7-resourcebind'
OLD_ENTRY_SHA = '071ed5ffc57956269fe8cfdbb9095e40414ded091bae888a3fe76dc9a64d70d5'
OLD_ENTRY_BYTES = 55774
OLD_KIT_SHA = '6c269db1e20d3cab9877eaa6bde2240ad8a7ffaca3e183fd1180011a4e244030'
OLD_SOURCE = 'ef21ca95331769622c294c65bb60ec7ceed0c392'
OLD_TREE = '5a70c5627afe75fcd475c20e71ee9bfb0b6a156d'
NEW_ROOT = CAND + '/epoch7-recovery-candidate-r7-claim-lifecycle'
# Publication and a separate source review must establish these; no CLI overrides.
NEW_KIT_SHA = '91252ba75c38b4a6d12f9b64eb06cb8793fabd97f03646bece97224178c28392'
NEW_ENTRY_SHA = '21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890'
NEW_ENTRY_BYTES = 56593
NEW_SOURCE = '105996ed06a0bdb5d025914cf08ebd448425f739'
NEW_TREE = '343d315b3ead6266a626b5875dbdd6c2fa0309af'
FILES = (
    ('seed', 'epoch7-resume-inputs-6de7d12246826388.private.json', 769086,
     '6de7d12246826388949723e9238cd464686e6e86847187946837df927c97a550'),
    ('plan', 'epoch7-approved-plan-eae1e341408b821a.private.json', 140648,
     'eae1e341408b821af0902a225021394d6f2e91a6c557bafe3dcd67a29c3b08da'),
    ('packet', 'epoch7-review-packet-c762ecddbdae50c7.private.json', 20089,
     'c762ecddbdae50c78557e753f76705c6ae521aa007c6e6ca4155e1acf5d9f9d2'))
OLD_BODY_SHA = 'bc0ab80b60c3c662b7960f68b1ce7fc57e62ee39ecb819a3b8ece239d1dba6f1'
OLD_OBSERVATION_SHA = 'f03fed248eaed766cce97eaa691aaf0f2132269d17bcbe8a7969464a2eb82fea'
SHA = re.compile(r'^[0-9a-f]{64}$')
SECONDS = 120
MAX_TOTAL = 128 * 1024 * 1024

class Hold(Exception): pass
class Deadline(Exception): pass
class CleanupError(Exception): pass

def need(value, code):
    if not value: raise Hold(code)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def packed(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii') + b'\n'
def check_time(end): need(time.monotonic() < end, 'DEADLINE')
def require_binding():
    need(all(type(v) is str and SHA.fullmatch(v) for v in (NEW_KIT_SHA, NEW_ENTRY_SHA)) and
         all(type(v) is str and re.fullmatch('[0-9a-f]{40}', v) for v in (NEW_SOURCE, NEW_TREE)) and
         type(NEW_ENTRY_BYTES) is int and 0 < NEW_ENTRY_BYTES <= 1024 * 1024,
         'SUCCESSOR_ARTIFACT_UNBOUND')

def stamp(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def attributes(fd):
    for key in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
        try:os.getxattr(fd,key)
        except OSError as e:need(e.errno in (errno.ENODATA,errno.ENOTSUP),'ATTRIBUTES')
        else:raise Hold('ATTRIBUTES')

def close_all(fds,primary=None):
    failed=False
    for fd in reversed(fds):
        try:os.close(fd)
        except BaseException:failed=True
    if failed:
        if primary is None:raise CleanupError()
        primary.cleanup_unknown=True

@contextlib.contextmanager
def budget(seconds):
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'EXISTING_TIMER')
    previous=signal.getsignal(signal.SIGALRM);primary=None;end=time.monotonic()+seconds
    def expired(unused_signum,unused_frame):raise Deadline()
    try:
        signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,seconds,0)
        yield
        if time.monotonic()>=end:raise Deadline()
    except BaseException as e:primary=e;raise
    finally:
        failed=False
        try:signal.setitimer(signal.ITIMER_REAL,0)
        except BaseException:failed=True
        try:signal.signal(signal.SIGALRM,previous)
        except BaseException:failed=True
        if failed:
            if primary is None:raise CleanupError()
            primary.cleanup_unknown=True

def directory(fd):
    s=os.fstat(fd)
    need(stat.S_ISDIR(s.st_mode) and (s.st_uid,s.st_gid) in ((0,0),(0,1002)) and not s.st_mode&0o022,'DIRECTORY')
    attributes(fd);return stamp(s)

def open_chain():
    held=[];rows=[];primary=None
    try:
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);held.append(fd)
        rows.append((None,'/',fd,directory(fd)))
        for name in CAND[1:].split('/'):
            parent=fd;fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);held.append(fd)
            before=directory(fd);need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==before,'PATH_IDENTITY');rows.append((parent,name,fd,before))
        recheck(rows);return held,rows,fd
    except BaseException as e:primary=e;raise
    finally:
        if primary is not None:close_all(held,primary)

def recheck(rows):
    for parent,name,fd,before in rows:
        need(directory(fd)==before,'PATH_IDENTITY')
        linked=os.stat(name,follow_symlinks=False) if parent is None else os.stat(name,dir_fd=parent,follow_symlinks=False)
        need(stamp(linked)==before,'PATH_IDENTITY')

def read_exact(parent,leaf,size,pin,private=True):
    fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent);primary=None
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and (before.st_uid,before.st_gid,stat.S_IMODE(before.st_mode),before.st_nlink)==(0,0,0o600 if private else 0o444,1),'FILE_AUTHORITY')
        attributes(fd);need(before.st_size==size,'FILE_SIZE')
        need(stamp(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==stamp(before),'PATH_IDENTITY')
        chunks=[];total=0
        while total<=size:
            data=os.read(fd,min(65536,size+1-total))
            if not data:break
            chunks.append(data);total+=len(data)
        raw=b''.join(chunks);need(len(raw)==size,'FILE_SIZE');need(hashlib.sha256(raw).hexdigest()==pin,'FILE_HASH')
        need(stamp(os.fstat(fd))==stamp(before) and stamp(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==stamp(before),'FILE_CHANGED')
        attributes(fd);return raw,stamp(before)
    except BaseException as e:primary=e;raise
    finally:close_all([fd],primary)

def cold_uuid_parser():
    """Use real stdlib UUID parsing; refuse its optional native-library discovery."""
    need('uuid' not in sys.modules,'UUID_PRELOADED')
    original=builtins.__import__;primary=None
    def guarded(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='ctypes' or name.startswith('ctypes.'):
            raise ImportError('optional ctypes disabled for UUID parsing')
        return original(name,globals,locals,fromlist,level)
    try:
        builtins.__import__=guarded
        module=importlib.import_module('uuid')
        need(str(module.UUID('c529c379-9341-4510-8384-fc6be1e412e5'))=='c529c379-9341-4510-8384-fc6be1e412e5','UUID_PARSER')
        if sys.version_info[:2]==(3,6):
            need(module._uuid_generate_time is None and module._UuidCreate is None,'UUID_IMPORT_GUARD')
        return module
    except BaseException as error:primary=error;raise
    finally:
        changed=builtins.__import__ is not guarded
        builtins.__import__=original
        if changed:
            if primary is None:raise Hold('UUID_IMPORT_GUARD')
            primary.cleanup_unknown=True

@contextlib.contextmanager
def authenticated_imports(kit):
    """Preserve primary failure and independently close the frozen loader scope."""
    before_path=list(sys.path);before_meta=list(sys.meta_path)
    names=set(kit.manifest['modules']);before_modules={name:sys.modules[name] for name in names if name in sys.modules}
    scope=kit.imports();entered=False;primary=None
    try:
        scope.__enter__();entered=True
        yield
    except BaseException as error:primary=error;raise
    finally:
        failed=False
        if entered:
            try:
                suppressed=scope.__exit__(type(primary) if primary else None,primary,
                    primary.__traceback__ if primary else None)
                if suppressed:failed=True
            except BaseException:failed=True
        try:
            if sys.path!=before_path or sys.meta_path!=before_meta:failed=True
            if {name:sys.modules[name] for name in names if name in sys.modules}!=before_modules:failed=True
            sys.path[:]=before_path;sys.meta_path[:]=before_meta
            for name in names:
                if name in before_modules:sys.modules[name]=before_modules[name]
                else:sys.modules.pop(name,None)
        except BaseException:failed=True
        if failed:
            if primary is None:raise CleanupError()
            primary.cleanup_unknown=True

def stamps(info):
    return {'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,
        'mode':stat.S_IMODE(info.st_mode),'nlink':info.st_nlink,'size':info.st_size,
        'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns}

def no_attributes(fd):
    for name in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
        try:os.getxattr(fd,name)
        except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP),'XATTR_UNKNOWN')
        else:raise ValueError('EPOCH7_PREP_UNREVIEWED_XATTR')

def close_fd(fd,primary=None):
    try:os.close(fd)
    except BaseException:
        if primary is None:raise CleanupError()
        primary.preparation_cleanup_failed=True

class Publication(list):
    """Internal own-write proof; only list elements are emitted as JSON."""
    pass

def parent_inventory(fd):
    names=os.listdir(fd)
    need(len(names)<=1024 and all(type(name) is str and 0<len(name)<=255 and
         '/' not in name and '\x00' not in name for name in names),'OUTPUT_PARENT_INVENTORY_BOUND')
    need(len(names)==len(set(names)),'OUTPUT_PARENT_INVENTORY_DUPLICATE')
    return tuple(sorted(names))

def bootstrap(rows, held, parent, successor):
    root, size, pin = ((NEW_ROOT, NEW_ENTRY_BYTES, NEW_ENTRY_SHA) if successor else
                      (OLD_ROOT, OLD_ENTRY_BYTES, OLD_ENTRY_SHA))
    leaf = os.path.basename(root)
    fd = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    held.append(fd)
    before = directory(fd)
    need(stamp(os.stat(leaf, dir_fd=parent, follow_symlinks=False)) == before, 'PATH_IDENTITY')
    rows.append((parent, leaf, fd, before))
    raw, metadata = read_exact(fd, 'epoch7_recovery_entry.py', size, pin, private=False)
    module = types.ModuleType('successor_preparation_entry' if successor else 'original_preparation_entry')
    module.__file__ = root + '/epoch7_recovery_entry.py'
    exec(compile(raw, module.__file__, 'exec', dont_inherit=True), module.__dict__)
    kit = module.verify_kit(root, NEW_KIT_SHA if successor else OLD_KIT_SHA)
    verify_kit_identity(kit, successor)
    return module, kit, (fd, raw, metadata)


def verify_kit_identity(kit, successor):
    root, digest, entry_sha, source, tree = ((NEW_ROOT, NEW_KIT_SHA, NEW_ENTRY_SHA, NEW_SOURCE, NEW_TREE)
        if successor else (OLD_ROOT, OLD_KIT_SHA, OLD_ENTRY_SHA, OLD_SOURCE, OLD_TREE))
    need(kit.root == root and kit.digest == digest and
         sha(kit.cache['epoch7_recovery_entry.py']) == entry_sha and
         kit.manifest['kit_source_commit'] == source and kit.manifest['kit_source_tree'] == tree,
         'FIXED_KIT_IDENTITY')


def validate_original(entry, kit, raws):
    """Authenticate original byte pins, then reproduce the old real pure compiler."""
    need(type(raws) is dict and set(raws) == {row[0] for row in FILES}, 'ORIGINAL_INPUT_SET')
    for role, leaf, size, pin in FILES:
        need(type(raws[role]) is bytes and len(raws[role]) == size and sha(raws[role]) == pin,
             'ORIGINAL_INPUT_PIN')
    envelope, plan, packet = [entry.decode(raws[key]) for key in ('seed', 'plan', 'packet')]
    need(type(envelope) is dict and set(envelope) == {'schema', 'seed'} and
         type(envelope['schema']) is int and envelope['schema'] == 1 and
         type(envelope['seed']) is dict and set(envelope['seed']) == entry.PRIVATE_SEED_FIELDS,
         'ORIGINAL_SEED_SCHEMA')
    private = envelope['seed']
    need('claim_successor' not in private and private['activate_retained_renewal_timer'] is True and
         type(packet) is dict and packet['final_review_id'] is None and
         packet['final_review_body_sha256'] is None and
         sha(packed(packet['final_review_body'])[:-1]) == OLD_BODY_SHA and
         sha(packed(private['observation'])[:-1]) == OLD_OBSERVATION_SHA and
         packet['compiler_kit_manifest_sha256'] == OLD_KIT_SHA and
         packet['summary']['plan_sha256'] == sha(raws['plan']) and
         packet['summary']['seed_sha256'] == sha(raws['seed']) and
         private['fresh_release_parent'] == packet['fresh_release_parent'], 'ORIGINAL_PACKET_BINDING')
    before = packed(private)
    with authenticated_imports(kit):
        factory = importlib.import_module('epoch7_host_factory')
        approval = importlib.import_module('epoch7_complete_approval')
        seed = kit._hydrate_seed(copy.deepcopy(private), factory)
        result = factory.prepare_host_inputs(seed)
        need(result['state'] == 'COMPILED_NOT_ADMITTED' and result['unresolved'] == [] and
             result['install_admission'] is False, 'ORIGINAL_COMPILER_HOLD')
        inputs = result['inputs']
        need(packed(factory.compile_host_contract(inputs)) == raws['plan'], 'ORIGINAL_PLAN_RECOMPILE')
        delta = factory.d.build_delta(inputs['snapshot'], factory.d.digest(inputs['snapshot']), inputs['candidate'])
        authorization = factory.required_authorization(delta, kit.digest, factory.d.digest(inputs['access_rows']),
                                                       inputs['additive_deltas'])
        body = approval.expected_complete_from_inputs(sha(raws['plan']), delta, authorization)
        need(body == packet['final_review_body'], 'ORIGINAL_BODY_RECOMPILE')
    need(before == packed(private), 'ORIGINAL_INPUT_MUTATION')
    return copy.deepcopy(private)


def validate_transaction_relation(measurement, directories, inventory, private, snapshot, claim):
    """Finite current relation only; it makes no claim about timestamp causality."""
    policy = private['observation']['policy']
    retained = private['observation']['evidence']['retained']
    snapshot.validate_predecessor_measurement(measurement, policy, claim.predecessor_contract())
    expected = {claim.TRANSACTION + '/' + name: pin for name, pin in policy['transaction_inventory'].items()}
    need(expected == retained['transaction_inventory'], 'HISTORICAL_INVENTORY_BINDING')
    expected[claim.TRANSACTION + '/' + claim.OLD_OUTER] = claim.PREDECESSOR_SHA256
    need(expected == inventory, 'TRANSACTION_INVENTORY_CHANGED')
    old_dirs = retained['transaction_directories']
    need(set(old_dirs) == set(directories), 'TRANSACTION_DIRECTORY_SET_CHANGED')
    changes = {}
    for name, historical in old_dirs.items():
        live = directories[name]
        snapshot._directory_authority(name, live, policy)
        if name == claim.TRANSACTION:
            mutable = claim.predecessor_contract()['parent_mutable_fields']
            need({k:v for k,v in historical.items() if k not in mutable} ==
                 {k:v for k,v in live.items() if k not in mutable}, 'TRANSACTION_PARENT_IDENTITY_CHANGED')
            need(live == measurement['ancestors'][name], 'TRANSACTION_PARENT_MEASUREMENT_CHANGED')
            changes = {k: {'historical': historical[k], 'live': live[k]} for k in mutable}
        else:
            need(historical == live, 'OTHER_TRANSACTION_DIRECTORY_CHANGED')
    return changes


def measure_predecessor(entry, private, end):
    """Actual bounded descriptor reads. Called only inside new authenticated imports.

    No observation is fabricated or rewritten; no process, DB query, probe,
    command, lock acquisition, or recovery driver is run in preparation.
    """
    snapshot = importlib.import_module('epoch7_snapshot')
    claim = importlib.import_module('epoch7_claim_successor')
    reader_type = importlib.import_module('snapshot_io').DescriptorReader
    policy = private['observation']['policy']
    reader = reader_type(policy['directories'])
    check_time(end)
    measurement = snapshot._read_predecessor(policy, reader, claim.predecessor_contract())
    # The reader enforces exact original directory pins. Retain the loader's
    # descriptor inventory too, so no original child is filtered or hidden.
    owners = tuple(sorted({(0, pin['gid']) for pin in policy['directories'].values() if pin['uid'] == 0}))
    tree = entry.DescriptorTree(claim.TRANSACTION, owners=owners)
    primary = None
    try:
        files, dirs = tree.inventory()
        expected_names = set(policy['transaction_inventory']) | {claim.OLD_OUTER}
        need(files == expected_names, 'TRANSACTION_FILE_SET_CHANGED')
        inventory = {}; total = 0
        for name in sorted(files):
            check_time(end)
            path = claim.TRANSACTION + '/' + name
            raw, metadata = reader.read(path, 64 * 1024 * 1024)
            total += len(raw); need(total <= MAX_TOTAL, 'TRANSACTION_TOTAL_BOUND')
            inventory[path] = sha(raw)
            # Freshly exclude capabilities as well as extended ACLs.
            with reader.parent(path) as (parent, leaf):
                fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
                file_primary = None
                try:
                    attributes(fd)
                    actual = stamps(os.fstat(fd))
                    need(actual == {k:metadata[k] for k in actual},
                         'TRANSACTION_FILE_REPEAT_CHANGED')
                except BaseException as error:
                    file_primary = error; raise
                finally: close_fd(fd, file_primary)
        directories = {path: reader.directory(path) for path in
            sorted({claim.TRANSACTION} | {claim.TRANSACTION + '/' + name for name in dirs})}
        for fd, parent, name, path, before in tree.opened:
            attributes(fd)
        changes = validate_transaction_relation(measurement, directories, inventory, private, snapshot, claim)
        need(snapshot._read_predecessor(policy, reader, claim.predecessor_contract()) == measurement,
             'PREDECESSOR_FINAL_DRIFT')
        need(tree.inventory() == (files, dirs), 'TRANSACTION_FINAL_INVENTORY_DRIFT')
        tree.recheck(); check_time(end)
        return {'measurement': measurement, 'transaction_inventory': inventory,
                'transaction_directories': directories, 'transaction_parent_delta': changes}
    except BaseException as error:
        primary = error; raise
    finally:
        close_all([row[0] for row in tree.opened], primary); tree.closed = True


def compile_successor_bundle(kit, original_private, measured, admission_expires_at_utc):
    """Pure new-loader call contract; no driver assembly or approval authentication.

    Caller owns authenticated kit imports, original authentication, actual protected
    measurement, final rereads and exclusive publication. Proof hashes are data,
    never an admission capability. Original private values are copied unchanged.
    """
    factory = importlib.import_module('epoch7_host_factory')
    approval = importlib.import_module('epoch7_complete_approval')
    claim = importlib.import_module('epoch7_claim_successor')
    snapshot = importlib.import_module('epoch7_snapshot')
    need(type(original_private) is dict and 'claim_successor' not in original_private and
         type(measured) is dict and set(measured) == {'measurement', 'transaction_inventory',
             'transaction_directories', 'transaction_parent_delta'}, 'SUCCESSOR_PREPARATION_INPUTS')
    before = packed(original_private)
    changes = validate_transaction_relation(measured['measurement'], measured['transaction_directories'],
                                           measured['transaction_inventory'], original_private, snapshot, claim)
    need(changes == measured['transaction_parent_delta'], 'PREDECESSOR_DELTA_CHANGED')
    contract = claim.validate_contract({'schema': 1, 'kind': 'EXACT_CLAIM_ONLY_SUCCESSOR',
        'timing_policy': 'PREPARED_START_30S_ORDERED_GUARDS_PUBLICATION_MIN_V1',
        'predecessor': claim.predecessor_contract(),
        'implementation': {'source_commit': kit.manifest['kit_source_commit'],
            'source_tree': kit.manifest['kit_source_tree'], 'kit_manifest_sha256': kit.digest},
        'admission_expires_at_utc': admission_expires_at_utc,
        'authorized_successors': 1, 'automatic_retry': False,
        'effect_scope': 'UNCHANGED_107_PAYLOADS_16_PHASES',
        'measured_predecessor_sha256': claim.digest(measured['measurement'])})
    private = copy.deepcopy(original_private); private['claim_successor'] = contract
    seed = kit._hydrate_seed(private, factory)
    result = factory.prepare_host_inputs(seed)
    need(result['state'] == 'COMPILED_NOT_ADMITTED' and result['unresolved'] == [] and
         result['install_admission'] is False, 'SUCCESSOR_COMPILER_HOLD')
    inputs = result['inputs']; plan_raw = packed(factory.compile_host_contract(inputs))
    delta = factory.d.build_delta(inputs['snapshot'], factory.d.digest(inputs['snapshot']), inputs['candidate'])
    authorization = factory.required_authorization(delta, kit.digest, factory.d.digest(inputs['access_rows']),
        inputs['additive_deltas'], claim_successor=contract)
    body = approval.expected_complete_from_inputs(sha(plan_raw), delta, authorization)
    seed_raw = packed({'schema': 2, 'seed': private})
    need(len(plan_raw) <= 2 * 1024 * 1024 and len(seed_raw) <= 64 * 1024 * 1024,
         'SUCCESSOR_PRIVATE_BOUNDS')
    need(before == packed(original_private) and
         before == packed({k:v for k,v in private.items() if k != 'claim_successor'}), 'ORIGINAL_INPUT_MUTATION')
    packet = {'schema': 2, 'state': 'PREPARED_NOT_ADMITTED',
        'original_inputs': {role: {'path': CAND + '/' + leaf, 'bytes': size, 'sha256': pin}
                            for role, leaf, size, pin in FILES},
        'original_kit_manifest_sha256': OLD_KIT_SHA, 'original_body_sha256': OLD_BODY_SHA,
        'claim_successor': contract, 'measured_predecessor': copy.deepcopy(measured),
        'plan_sha256': sha(plan_raw), 'seed_sha256': sha(seed_raw),
        'compiler_kit_manifest_sha256': kit.digest, 'final_review_body': body,
        'final_review_id': None, 'final_review_body_sha256': None,
        'install_admission': 'NOT_GRANTED', 'production_resume': 'NOT_EXECUTED',
        'production_acceptance': 'PENDING'}
    packet_raw = packed(packet); need(len(packet_raw) <= 2 * 1024 * 1024, 'SUCCESSOR_PACKET_BOUND')
    return {'plan_raw': plan_raw, 'seed_raw': seed_raw, 'packet_raw': packet_raw,
            'claim_successor': contract}


def verify_publication(entry, publication, end):
    need(isinstance(publication, Publication) and len(publication) == 3, 'COMPLETE_PUBLICATION_REQUIRED')
    tree = entry.DescriptorTree(CAND); primary = None
    try:
        need(entry.stamp(tree._authority(tree.fd, True)) == publication.parent_after,
             'PUBLICATION_PARENT_CHANGED')
        need(parent_inventory(tree.fd) == publication.parent_names_after, 'PUBLICATION_PARENT_INVENTORY_CHANGED')
        for row in publication:
            check_time(end); path = row['path']
            raw = tree.read(os.path.basename(path), publication.bounds[path], private=True)
            need(raw == publication.raws[path] and sha(raw) == row['sha256'] and
                 stamps(os.stat(os.path.basename(path), dir_fd=tree.fd, follow_symlinks=False)) ==
                 {k:publication.metadata[path][k] for k in stamps(os.fstat(tree.fd))}, 'PUBLICATION_BYTES_CHANGED')
        tree.recheck(); check_time(end)
    except BaseException as error: primary = error; raise
    finally: close_all([row[0] for row in tree.opened], primary); tree.closed = True


def publish_bundle(entry,bundle,end):
    """Create three new protected outputs; never overwrite or remove any file.

    The caller has completed collection, original-input authentication and all
    pure compilation. The prospective new review body remains unsigned. Partial creation remains protected and is reported HOLD.
    The final receipt is written last and is not an installation authority.
    """
    rows=[('epoch7-lifecycle-approved-plan-',bundle['plan_raw'],2*1024*1024),
          ('epoch7-lifecycle-resume-inputs-',bundle['seed_raw'],64*1024*1024),
          ('epoch7-lifecycle-review-packet-',bundle['packet_raw'],2*1024*1024)]
    need(all(type(raw) is bytes and 0<len(raw)<=maximum for prefix,raw,maximum in rows),'ALL_OUTPUT_BOUNDS')
    names=[prefix+sha(raw)[:16]+'.private.json' for prefix,raw,maximum in rows]
    tree=entry.DescriptorTree(CAND);primary=None;outputs=Publication();created=[]
    outputs.metadata={};outputs.raws={};outputs.bounds={}
    try:
        outputs.parent_before=entry.stamp(tree._authority(tree.fd,True))
        outputs.parent_names_before=parent_inventory(tree.fd)
        need(entry.stamp(tree._authority(tree.fd,True))==outputs.parent_before,'OUTPUT_PARENT_INVENTORY_RACE')
        for name in names:
            try:os.stat(name,dir_fd=tree.fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise ValueError('EPOCH7_PREP_OUTPUT_EXISTS')
        tree.recheck()
        for name,(prefix,raw,maximum) in zip(names,rows):
            need(type(raw) is bytes and 0<len(raw)<=maximum and time.monotonic()<end,'OUTPUT_BOUND')
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=tree.fd)
            created.append(CAND+'/'+name)
            file_primary=None
            try:
                info=os.fstat(fd)
                need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o600,1),
                     'OUTPUT_AUTHORITY');no_attributes(fd)
                offset=0
                while offset<len(raw):
                    need(time.monotonic()<end,'OUTPUT_DEADLINE')
                    count=os.write(fd,raw[offset:offset+65536]);need(count>0,'OUTPUT_SHORT_WRITE');offset+=count
                os.fsync(fd);need(time.monotonic()<end,'OUTPUT_DEADLINE')
                after=os.fstat(fd);linked=os.stat(name,dir_fd=tree.fd,follow_symlinks=False)
                need(after.st_ino==info.st_ino and after.st_dev==info.st_dev and after.st_size==len(raw) and
                     stamps(after)==stamps(linked),'OUTPUT_BINDING')
            except BaseException as error:file_primary=error;raise
            finally:close_fd(fd,file_primary)
            readback=tree.read(name,maximum,private=True)
            need(readback==raw and time.monotonic()<end,'OUTPUT_READBACK')
            outputs.append({'path':CAND+'/'+name,'sha256':sha(raw),'bytes':len(raw)})
            outputs.metadata[CAND+'/'+name]=dict(stamps(after),kind='FILE',sha256=sha(raw))
            outputs.raws[CAND+'/'+name]=raw;outputs.bounds[CAND+'/'+name]=maximum
        os.fsync(tree.fd);need(time.monotonic()<end,'OUTPUT_DEADLINE')
        # CAND's own size/times changed only through exclusive creations. Keep
        # its identity/mode/owner and every ancestor/path binding exact.
        for fd,parent,name,path,before in tree.opened:
            now=entry.stamp(tree._authority(fd,True))
            need((now[:6]==before[:6] if path==CAND else now==before),'OUTPUT_PARENT_CHANGED')
            if parent is not None:need(entry.stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==now,'OUTPUT_PARENT_LINK')
        outputs.parent_after=entry.stamp(tree._authority(tree.fd,True))
        outputs.parent_names_after=tuple(sorted(outputs.parent_names_before+tuple(names)))
        need(parent_inventory(tree.fd)==outputs.parent_names_after and
             entry.stamp(tree._authority(tree.fd,True))==outputs.parent_after,'OUTPUT_UNOWNED_DIRECTORY_CHANGE')
        verify_publication(entry,outputs,end)
        return outputs
    except BaseException as error:
        primary=error;error.preparation_outputs=copy.deepcopy(list(outputs));error.preparation_created_paths=list(created);raise
    finally:
        failed=False
        for row in reversed(tree.opened):
            try:os.close(row[0])
            except BaseException:failed=True
        tree.closed=True
        if failed:
            if primary is None:
                error=CleanupError();error.preparation_outputs=copy.deepcopy(list(outputs));error.preparation_created_paths=list(created);raise error
            primary.preparation_cleanup_failed=True

def accept_owned_publication(rows, publication):
    need(publication.parent_before[:6] == publication.parent_after[:6], 'OWNED_PARENT_BINDING')
    matched = False
    for index, (parent, name, fd, before) in enumerate(rows):
        if fd == rows[len(CAND.strip('/').split('/'))][2]:
            need(before == publication.parent_before and directory(fd) == publication.parent_after,
                 'OWNED_PARENT_CHANGED')
            rows[index] = (parent, name, fd, publication.parent_after); matched = True
    need(matched, 'OWNED_PARENT_CAPTURE_REQUIRED')


def prepare(admission_expires_at_utc, end):
    require_binding()  # Refuse UNBOUND source before any host read.
    need(os.geteuid() == 0 and socket.gethostname() == HOST, 'EXACT_ROOT_HOST')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, 'ISOLATED_NO_BYTECODE')
    cold_uuid_parser()
    held, rows, parent = open_chain(); primary = None; outputs = None
    try:
        old_entry, old_kit, old_boot = bootstrap(rows, held, parent, False)
        entry, kit, new_boot = bootstrap(rows, held, parent, True)
        # No selected runtime source may drift while replacing compiler helpers.
        old_runtime = {k:v for k,v in old_kit.cache.items() if k.startswith(old_entry.RUNTIME)}
        new_runtime = {k:v for k,v in kit.cache.items() if k.startswith(entry.RUNTIME)}
        need(old_runtime == new_runtime, 'ORIGINAL_RUNTIME_CHANGED')
        initial = {role: read_exact(parent, leaf, size, pin) for role, leaf, size, pin in FILES}
        private = validate_original(old_entry, old_kit, {role: pair[0] for role,pair in initial.items()})
        with authenticated_imports(kit):
            claim = importlib.import_module('epoch7_claim_successor')
            need(time.time() < claim.parse_expiry(admission_expires_at_utc), 'ADMISSION_EXPIRY_PASSED')
            measured = measure_predecessor(entry, private, end)
            bundle = compile_successor_bundle(kit, private, measured, admission_expires_at_utc)
        def final_read():
            check_time(end); recheck(rows)
            for role, leaf, size, pin in FILES:
                need(read_exact(parent, leaf, size, pin) == initial[role], 'ORIGINAL_FINAL_CHANGED')
            for successor, loader, selected, boot in ((False, old_entry, old_kit, old_boot), (True, entry, kit, new_boot)):
                fd, raw, metadata = boot
                size, pin = (NEW_ENTRY_BYTES, NEW_ENTRY_SHA) if successor else (OLD_ENTRY_BYTES, OLD_ENTRY_SHA)
                need(read_exact(fd, 'epoch7_recovery_entry.py', size, pin, private=False) == (raw, metadata),
                     'ENTRY_FINAL_CHANGED')
                again = loader.verify_kit(selected.root, selected.digest); verify_kit_identity(again, successor)
                need(again.raw_manifest == selected.raw_manifest and again.cache == selected.cache, 'KIT_FINAL_CHANGED')
            with authenticated_imports(kit):
                need(time.time() < importlib.import_module('epoch7_claim_successor').parse_expiry(admission_expires_at_utc),
                     'ADMISSION_EXPIRY_PASSED')
                need(measure_predecessor(entry, private, end) == measured, 'PREDECESSOR_FINAL_CHANGED')
            recheck(rows); check_time(end)
        final_read()
        outputs = publish_bundle(entry, bundle, end)
        accept_owned_publication(rows, outputs)
        final_read(); verify_publication(entry, outputs, end)
        return {'schema': 1, 'state': 'PREPARED_NOT_ADMITTED', 'outputs': list(outputs),
            'kit_manifest_sha256': kit.digest, 'measured_predecessor_sha256': bundle['claim_successor']['measured_predecessor_sha256'],
            'admission_expires_at_utc': admission_expires_at_utc, 'final_review': 'NEW_EXACT_APPROVAL_REQUIRED',
            'install_admission': 'NOT_GRANTED', 'production_resume': 'NOT_EXECUTED'}
    except BaseException as error:
        primary = error
        if outputs is not None:
            error.preparation_outputs = copy.deepcopy(list(outputs))
            error.preparation_created_paths = [row['path'] for row in outputs]
        raise
    finally:
        try: close_all(held, primary)
        except BaseException as error:
            if outputs is not None:
                error.preparation_outputs = copy.deepcopy(list(outputs))
                error.preparation_created_paths = [row['path'] for row in outputs]
            raise


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, unused): raise Hold('ARGUMENTS')
    parser = Parser(description=__doc__, add_help=False)
    parser.add_argument('--operation', choices=('input-contract', 'prepare'), required=True)
    parser.add_argument('--admission-expires-at-utc')
    args = parser.parse_args(argv)
    if args.operation == 'input-contract':
        result = {'schema': 1, 'state': 'SUCCESSOR_PREPARATION_REQUIRES_BINDING',
            'new_kit_root': NEW_ROOT, 'new_kit_manifest_sha256': NEW_KIT_SHA,
            'new_source_commit': NEW_SOURCE, 'new_source_tree': NEW_TREE,
            'original_inputs': {role: {'path': CAND + '/' + leaf, 'bytes': size, 'sha256': pin}
                                for role,leaf,size,pin in FILES},
            'install_admission': 'NOT_GRANTED', 'production_resume': 'NOT_EXECUTED'}
    else:
        result = None
        try:
            with budget(SECONDS):
                result = prepare(args.admission_expires_at_utc, time.monotonic() + SECONDS)
        except BaseException as error:
            if result is not None:
                error.preparation_outputs = result['outputs']
                error.preparation_created_paths = [row['path'] for row in result['outputs']]
            raise
    try:
        raw = packed(result); need(len(raw) <= 65536, 'STATUS_BOUND')
        with budget(5):
            offset = 0
            while offset < len(raw):
                count = os.write(1, raw[offset:]); need(count > 0, 'STATUS_WRITE'); offset += count
    except BaseException as error:
        if type(result) is dict and type(result.get('outputs')) is list:
            error.preparation_outputs = copy.deepcopy(result['outputs'])
            error.preparation_created_paths = [row['path'] for row in result['outputs']]
        raise
    return 0


def cleanup_unknown(error):
    """Bounded classification of inherited cleanup causes; never disclose text."""
    pending = [error]; seen = set()
    while pending and len(seen) < 8:
        current = pending.pop()
        if id(current) in seen: continue
        seen.add(id(current))
        if isinstance(current, (CleanupError, OSError)) or getattr(current, 'cleanup_unknown', False) or \
                getattr(current, 'preparation_cleanup_failed', False):
            return True  # Unclassified I/O failure is conservatively UNKNOWN.
        if type(current) in (ValueError, Hold) and current.args in (
                ('READER_PARENT_CLEANUP_UNKNOWN',), ('IMPORT_CLEANUP',), ('CLEANUP',)):
            return True
        pending.extend(value for value in (current.__cause__, current.__context__)
                       if value is not None and id(value) not in seen)
    return bool(pending)


def entrypoint(argv=None):
    try: return main(argv)
    except BaseException as error:
        # Never echo private helper exceptions or input data. Partial files stay.
        result = {'state': 'HOLD', 'failure_type': type(error).__name__,
            'cleanup_unknown': cleanup_unknown(error),
            'completed_outputs': getattr(error, 'preparation_outputs', []),
            'created_output_paths': getattr(error, 'preparation_created_paths', []),
            'install_admission': 'NOT_GRANTED', 'production_resume': 'NOT_EXECUTED'}
        try:
            with budget(5):
                raw = packed(result); offset = 0
                while offset < len(raw):
                    count = os.write(1, raw[offset:]); need(count > 0, 'STATUS_WRITE'); offset += count
        except BaseException: pass
        return 2


if __name__ == '__main__': sys.exit(entrypoint())
