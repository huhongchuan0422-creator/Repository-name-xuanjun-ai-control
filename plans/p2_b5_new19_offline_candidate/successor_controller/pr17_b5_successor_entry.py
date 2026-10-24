"""Fixed, default-closed B5 maintenance entry for the original UK operator.

The CLI accepts only batch selectors, never paths, tokens, approval booleans,
or receipt dictionaries.  The original two stores and release gate decide
admission.  `review.main` remains a rejecting review entry.
"""
import argparse
import json
import os
import re
import stat
import sys

LOCAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _root in (LOCAL_ROOT, LOCAL_ROOT+'/reused-6825', LOCAL_ROOT+'/new19-source'):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from pr17_b5_successor_fixed_io import FixedR2IO
import pr17_b5_successor_review as c53

ROOT = '/opt/xuanjun-cloud-connection/b5-successor-controller-staged-f0fe0d3978b7'
SOURCE = ROOT + '/new19-source'
SPEC = ROOT + '/SUCCESSOR_SPEC.json'
BINDER = ROOT + '/EXTERNAL_SUCCESSOR_DEPLOYMENT_BINDER.json'
MANIFEST = ROOT + '/SUCCESSOR_CONTROLLER_SOURCE_MANIFEST.json'
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')


def _source_modules():
    """Only the in-release original modules are importable; no user path."""
    c53.require(os.path.abspath(__file__) ==
                ROOT+'/successor_controller/pr17_b5_successor_entry.py',
                'ENTRY_NOT_FIXED_DEPLOYMENT')
    c53.require(LOCAL_ROOT == ROOT, 'ENTRY_IMPORT_ROOT')


def _read(path, limit=262144, runtime=False):
    """Fixed-root descriptor walk; no source symlink or writable ancestor."""
    allowed = path.startswith(ROOT+'/') or (runtime and any(
        path.startswith(base+'/releases/'+c53.COMMIT+'/') for base in c53.BASES))
    c53.require(type(path) is str and allowed and
                os.path.normpath(path) == path and '..' not in path.split('/'),
                'ENTRY_READ_SCOPE')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = path.split('/')[1:]
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY |
                          os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
            st = os.fstat(fd)
            c53.require(st.st_uid == 0 and not st.st_mode & 0o022 and
                        stat.S_ISDIR(st.st_mode), 'ENTRY_PARENT_PROTECTION')
        item = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW |
                       os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(item)
            c53.require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
                        before.st_nlink == 1 and
                        stat.S_IMODE(before.st_mode) in (0o600,0o644) and
                        before.st_size <= limit, 'ENTRY_FILE_PROTECTION')
            raw = os.read(item, limit+1)
            after = os.fstat(item)
            named = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            identity = lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_uid,x.st_gid,
                                  x.st_nlink,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
            c53.require(len(raw) == before.st_size and
                        identity(before) == identity(after) == identity(named),
                        'ENTRY_FILE_CHANGED')
            return raw
        finally:
            os.close(item)
    finally:
        os.close(fd)


def _current():
    result = {}
    io = FixedR2IO(c53.binder.verify_spec_bytes(_read(SPEC)))
    for base in c53.BASES:
        fd = io.parent(base)
        try:
            directory = os.fstat(fd)
            st = os.stat('current', dir_fd=fd, follow_symlinks=False)
            c53.require(directory.st_uid == 0 and
                        not directory.st_mode & 0o022 and
                        stat.S_ISLNK(st.st_mode) and st.st_uid == 0 and
                        st.st_nlink == 1, 'ENTRY_CURRENT_IDENTITY')
            result[base] = os.readlink('current', dir_fd=fd)
        finally:
            os.close(fd)
    return result


def _binding(spec, batch, attempt, start, catalog_sha):
    from pr17_b5_successor_witness import WitnessStore
    c53.require(all(type(x) is str and TOKEN.fullmatch(x)
                    for x in (batch, attempt)) and type(start) is int,
                'ENTRY_BATCH_SELECTOR')
    result = {'batch':batch, 'job':spec['fixed_paths']['job_proposed'],
              'attempt':attempt, 'ids':spec['batch']['draft_request_ids'],
              'catalog_sha256':catalog_sha, 'recipient':c53.RECIP,
              'project':c53.PROJ, 'subject':c53.SUBJECT,
              'commit':c53.COMMIT, 'valid_from':start,
              'valid_until':start+3600}
    WitnessStore._binding(result)
    return result


def _gate(store, binding):
    from pr17_b5_successor_release_gate import ExternalReleaseGate
    def installed(base, name):
        c53.require(base in c53.BASES and type(name) is str and
                    name in {r['path'] for r in
                             c53.binder.verify_spec_bytes(_read(SPEC))[
                                 'source']['source_records']} |
                    {c53.binder.MANIFEST_PATH},
                    'ENTRY_RUNTIME_SCOPE')
        return _read(base+'/releases/'+c53.COMMIT+'/'+name,runtime=True)
    return ExternalReleaseGate.from_registered(
        store,binding,read_binder=lambda:_read(BINDER,16384),
        read_manifest=lambda:_read(MANIFEST,16384),
        read_source=lambda name:_read(ROOT+'/'+name),
        read_current=_current,read_installed_runtime=installed)


def _stores():
    from pr17_b5_successor_witness import WitnessStore, SuccessorEvidenceStore
    # Constructors have no side effects.  The first inspect insists on an
    # existing protected root and valid independent records.
    return WitnessStore(enabled=True), SuccessorEvidenceStore(enabled=True)


def _identity():
    c53.require(os.uname().nodename == c53.HOST and
                os.geteuid() == os.getegid() == 0 and
                os.environ.get('SUDO_UID') == '1000', 'ENTRY_UK_IDENTITY')


def _prepare(batch, attempt, approval, start):
    from pr17_b5_successor_authority import prepare_maintenance_candidate
    _identity()
    _source_modules()
    c53.require(type(approval) is str and TOKEN.fullmatch(approval),
                'ENTRY_APPROVAL_SELECTOR')
    spec_raw = _read(SPEC)
    spec = c53.binder.verify_spec_bytes(spec_raw)
    io = FixedR2IO(spec)
    witness,evidence = _stores()
    transaction = prepare_maintenance_candidate(
        spec_raw=spec_raw,source_root=SOURCE,legacy_io=io,
        batch_id=batch,approval_ref=approval,window_start=start,
        attempt_id=attempt,witness_store=witness,evidence_store=evidence)
    binding = _binding(spec,batch,attempt,start,
                       transaction.bundle['catalog_sha'])
    c53.require(transaction.b.authority._witness_binding() == binding,
                'ENTRY_BINDING_CHANGED')
    witness.inspect(binding)
    gate = _gate(evidence,binding)
    gate.check('preflight',spec)
    transaction.b.release_gate = gate
    transaction.b.authority.release_gate = gate
    return transaction


def _recover():
    from pr17_b5_successor_authority import reconstruct_recovery_candidate
    _identity()
    _source_modules()
    spec_raw = _read(SPEC)
    spec = c53.binder.verify_spec_bytes(spec_raw)
    io = FixedR2IO(spec)
    raw,_ = io.read(spec['fixed_paths']['job_proposed']+'/reservation.json')
    reservation = c53.strict_json(raw)
    c53.require(type(reservation) is dict and
                set(('batch','attempt_id','window_start','catalog_sha256')) <=
                    set(reservation), 'ENTRY_RESERVATION')
    witness,evidence = _stores()
    binding = _binding(spec,reservation['batch'],reservation['attempt_id'],
                       reservation['window_start'],reservation['catalog_sha256'])
    witness.inspect(binding)
    gate = _gate(evidence,binding)
    gate.check('recover',spec)
    return reconstruct_recovery_candidate(
        spec_raw=spec_raw,source_root=SOURCE,legacy_io=io,
        witness_store=witness,release_gate=gate,evidence_store=evidence)


def _verified_window(transaction):
    """Read-only exact window and journal observation before any first POST."""
    backend = transaction.b
    io = backend.legacy
    job = backend.job
    reservation = c53.strict_json(io.read(job+'/reservation.json')[0])
    window = c53.strict_json(io.read(job+'/window-open.json')[0])
    c53.require(reservation.get('state') == 'RESERVED_NOT_SUBMITTED' and
                reservation.get('request_set_sha256') ==
                    c53.sha(c53.canon(transaction.bundle['requests'])) and
                window.get('state') == 'ACTIVE_NOT_DELIVERED' and
                window.get('window_start') == transaction.bundle['window_start'] and
                window.get('window_end') == transaction.bundle['window_end'],
                'ENTRY_WINDOW_NOT_BOUND')
    phases = []
    missing = False
    for number in range(1,65):
        try:
            raw,_ = io.read(job+'/checkpoint-%03d.json'%number)
        except FileNotFoundError:
            missing = True
            continue
        c53.require(not missing, 'ENTRY_CHECKPOINT_GAP')
        row = c53.strict_json(raw)
        c53.require(row == {'schema':1,'sequence':number,
                    'release_commit':c53.COMMIT,'project':c53.PROJ,
                    'phase':row.get('phase')} and type(row['phase']) is str,
                    'ENTRY_CHECKPOINT_CHANGED')
        phases.append(row['phase'])
    c53.require(phases and len(phases)<64 and phases[-1]=='WINDOW_ENABLED' and
                'INTAKE_19' not in phases and
                not any(phase.startswith('FAILURE_') for phase in phases),
                'ENTRY_INTAKE_ALREADY_ATTEMPTED')
    for rid in backend.expected_ids:
        for suffix in ('.intent.json','.sent.json'):
            io.absent(job+'/intake-'+rid+suffix)
    return len(phases)


def _first_intake(transaction):
    """Only the exact fresh window checkpoint can enter the original POST path."""
    count = _verified_window(transaction)
    backend = transaction.b
    backend.seq = count
    backend.reserved = True
    backend.bundle = transaction.bundle
    backend.window_open = True
    backend.activation_committed = True
    # The actual original Queue, OAuth resource and approval are reattached
    # and verified before any POST; this is not a synthetic recovery receipt.
    backend.authority.attach_original_after_worker_start()
    transaction.stage = 'WINDOW_ENABLED'
    return transaction.run_19_after_window()


def dispatch(action, *, batch=None, attempt=None, approval=None, start=None):
    c53.require(action in ('execute','intake','query','recover','close'), 'ENTRY_ACTION')
    if action == 'execute':
        transaction = _prepare(batch,attempt,approval,start)
        return transaction.execute()
    c53.require(all(value is None for value in (batch,attempt,approval,start)),
                'ENTRY_RECOVERY_SELECTORS_FORBIDDEN')
    transaction = _recover()
    if action == 'intake':
        return _first_intake(transaction)
    try:
        _verified_window(transaction)
    except c53.Hold as exc:
        if str(exc) not in ('ENTRY_INTAKE_ALREADY_ATTEMPTED',
                            'FIXED_IO_PRESENT'):
            raise
    else:
        return {'state':'WINDOW_ENABLED_NO_POST','received':0,
                'mutation_allowed':False}
    from pr17_b5_successor_authority import inspect_recovered_candidate_readonly
    observed = inspect_recovered_candidate_readonly(transaction)
    if action == 'query':
        return observed
    if action == 'recover':
        if observed.get('state') == 'B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY':
            return transaction.resume_recovered_b5_http_wait()
        if observed.get('state') == 'SUCCESS_SNAPSHOT_READONLY':
            return transaction.resume_recovered_custody()
        return observed  # UNKNOWN/PENDING is query-only, never another POST.
    transaction.resume_recovered_b5_http_wait()
    binding = transaction.b.authority._witness_binding()
    row,_ = transaction.b.authority.evidence_store.read_exact(binding,'b5_http')
    proof = {'state':'B5_HTTP_BYTES_VALIDATED_SOURCE_ATTESTATION_PENDING',
             'bytes':93592,'objects':19,'close_approval':'NOT_PROVEN',
             'proof_sha256':row['payload']['proof_sha256']}
    return transaction.close_after_b5_http(proof)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Default-closed fixed UK B5 successor entry')
    sub = parser.add_subparsers(dest='action')
    execute = sub.add_parser('execute',help='first admission; selectors must match registered records')
    execute.add_argument('--batch',required=True)
    execute.add_argument('--attempt',required=True)
    execute.add_argument('--approval-ref',required=True)
    execute.add_argument('--window-start',required=True,type=int)
    for action in ('intake','query','recover','close'):
        sub.add_parser(action,help='fixed protected job; no caller paths or bearer')
    args = parser.parse_args(argv)
    if args.action is None:
        parser.error('action required')
    try:
        result = dispatch(args.action,batch=getattr(args,'batch',None),
                          attempt=getattr(args,'attempt',None),
                          approval=getattr(args,'approval_ref',None),
                          start=getattr(args,'window_start',None))
        print(json.dumps(result,sort_keys=True))
        return 0 if result.get('state') in (
            'WINDOW_ENABLED_NOT_DELIVERED','WINDOW_ENABLED_NO_POST',
            'UNKNOWN_OR_PENDING_NO_REPOST','WAIT_ORIGINAL_SUCCESS_NO_REPOST',
            'B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY',
            'RECEIVED_VERIFIED_19_CLOSED') else 2
    except Exception as exc:
        print(json.dumps({'state':'HOLD','reason':str(exc)[:120],
                          'installation':'NOT_EXECUTED'},sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
