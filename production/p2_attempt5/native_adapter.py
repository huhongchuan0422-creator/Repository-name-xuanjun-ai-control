"""Explicit native composition and authenticated host-receipt reader.

No deployment, key generation, database initialization, approval creation or
receipt synthesis. Missing live evidence fails closed. Used only after entry
has verified the complete deployment Manifest and the private binding digest.
"""
import base64
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import time
import types

MAX = 262144
FIELDS = {'schema', 'hostname', 'principal', 'issuer',
          'public_key', 'receipt_public_key', 'receipt_issuer', 'receipt_socket',
          'legacy_manifest_sha256', 'approved_plan', 'private_seed',
          'legacy_review_id', 'legacy_approval_body_sha256'}
_context = None
_observer_session = None


def need(value, code):
    if not value:
        raise RuntimeError('P2_NATIVE_ADAPTER_' + code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'DUPLICATE_KEY')
            value[key] = item
        return value
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
        parse_constant=lambda unused: need(False, 'NONFINITE_JSON'))


def pin(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'SHA256')
    return value


def path(value):
    need(type(value) is str and value.startswith('/') and
         not value.startswith('//') and value != '/' and
         os.path.normpath(value) == value and
         not any(ord(c) < 32 or ord(c) == 127 for c in value) and
         '\\' not in value, 'CANONICAL_PATH')
    return value


def protected(pathname, directory=False):
    path(pathname)
    need(os.geteuid() == 0, 'ROOT_REQUIRED')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = pathname.strip('/').split('/')
        for index, component in enumerate(parts):
            is_dir = index < len(parts) - 1 or directory
            child = os.open(component, os.O_RDONLY | os.O_NOFOLLOW |
                os.O_NONBLOCK | (os.O_DIRECTORY if is_dir else 0), dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            need(info.st_uid == 0 and not info.st_mode & 0o022 and
                 (stat.S_ISDIR(info.st_mode) if is_dir else
                  stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                  stat.S_IMODE(info.st_mode) == 0o600), 'PROTECTION')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read(pathname, expected=None, bound=MAX):
    fd = protected(pathname)
    try:
        before = os.fstat(fd)
        need(before.st_size <= bound, 'FILE_BOUND')
        raw = os.read(fd, bound + 1)
        after = os.fstat(fd)
        stamp = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        need(stamp(before) == stamp(after) and len(raw) == before.st_size, 'READ_RACE')
        if expected is not None:
            need(hashlib.sha256(raw).hexdigest() == pin(expected), 'FILE_SHA')
        return raw
    finally:
        os.close(fd)


def reference(value):
    need(type(value) is dict and set(value) == {'path', 'sha256'}, 'REFERENCE')
    path(value['path'])
    pin(value['sha256'])
    return value


def public_key(value):
    """Read an independently pinned PUBLIC PEM, never the private Signer key."""
    reference(value)
    raw = read(value['path'], value['sha256'])
    need(raw.startswith(b'-----BEGIN PUBLIC KEY-----\n') and
         b'PRIVATE KEY' not in raw, 'PUBLIC_PEM_REQUIRED')
    def openssl(arguments):
        return subprocess.check_output(['/usr/bin/openssl'] + arguments,
            input=raw, stderr=subprocess.DEVNULL, timeout=10,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    der = openssl(['pkey', '-pubin', '-outform', 'DER'])
    detail = openssl(['rsa', '-pubin', '-text', '-noout']).decode('ascii')
    need(re.search(r'(?m)^\s*Exponent: 65537 \(0x10001\)\s*$', detail),
         'RSA_EXPONENT')
    output = openssl(['rsa', '-pubin', '-modulus', '-noout']).decode('ascii').strip()
    need(re.fullmatch('Modulus=[0-9A-Fa-f]+', output), 'RSA_MODULUS')
    modulus = int(output.split('=')[1], 16)
    need(2048 <= modulus.bit_length() <= 4096 and modulus % 2 == 1, 'RSA_WIDTH')
    return modulus, hashlib.sha256(der).hexdigest()


def bind_deployment(cfg, raw, expected_sha256, kit_root, loader):
    """entry supplies bytes pinned in the NEW Grant-bound release Manifest."""
    global _context
    need(_context is None, 'ALREADY_BOUND')
    need(type(raw) is bytes and hashlib.sha256(raw).hexdigest() ==
         pin(expected_sha256), 'DEPLOYMENT_BINDING_SHA')
    value = decode(raw)
    need(type(value) is dict and type(value.get('schema')) is int and
         ((value['schema'] == 1 and set(value) == FIELDS) or
          (value['schema'] == 2 and set(value) == FIELDS | {'observer_service'})),
         'BINDING_FIELDS')
    need(value['hostname'] == os.uname().nodename == cfg['principal']['host'] ==
         cfg['grant']['target_host'] and value['principal'] == cfg['principal'] and
         value['issuer'] == cfg['issuer'], 'BINDING_SCOPE')
    for name in ('public_key', 'receipt_public_key', 'approved_plan', 'private_seed'):
        reference(value[name])
    for name in ('legacy_manifest_sha256', 'legacy_approval_body_sha256'):
        pin(value[name])
    need(type(value['legacy_review_id']) is int and value['legacy_review_id'] > 0,
         'LEGACY_REVIEW')
    need(type(value['receipt_issuer']) is str and
         re.fullmatch('[A-Za-z0-9_.-]{1,80}', value['receipt_issuer']) and
         value['receipt_issuer'].upper() != 'UNKNOWN', 'RECEIPT_ISSUER')
    path(value['receipt_socket'])
    path(kit_root)
    need(callable(getattr(loader, 'pinned_module', None)), 'PINNED_MODULE_LOADER')
    if value['schema'] == 2:
        spec = value['observer_service']
        need(type(spec) is dict and set(spec) == {
            'socket','key','public_der_sha256','issuer','attestor_public_key',
            'context_directory','configuration_payloads'}, 'OBSERVER_SPEC_FIELDS')
        for name in ('socket','key','context_directory'):
            path(spec[name])
        pin(spec['public_der_sha256'])
        reference(spec['attestor_public_key'])
        need(spec['socket'] == value['receipt_socket'] and
             spec['issuer'] == value['receipt_issuer'] and
             spec['public_der_sha256'] != cfg['public_der_sha256'], 'OBSERVER_TRUST_BINDING')
        unused_modulus, observer_der = public_key(value['receipt_public_key'])
        need(observer_der == spec['public_der_sha256'], 'OBSERVER_KEY_PIN')
        fd = protected(spec['context_directory'], directory=True)
        try:
            need(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700, 'CONTEXT_DIRECTORY')
        finally:
            os.close(fd)
        need(type(spec['configuration_payloads']) is dict and
             set(spec['configuration_payloads']) <=
             {action['id'] for action in cfg['cycle_policy']['configuration_actions']},
             'OBSERVER_CONFIG_SCOPE')
        for ref in spec['configuration_payloads'].values():
            reference(ref)
    _context = (copy.deepcopy(cfg), value, kit_root, loader)


def bound(cfg):
    need(_context is not None and cfg == _context[0], 'DEPLOYMENT_NOT_BOUND')
    return _context[1:]


def public_modulus(cfg):
    value, unused_root, unused_loader = bound(cfg)
    modulus, der_sha = public_key(value['public_key'])
    need(der_sha == cfg['public_der_sha256'], 'ISSUER_PUBLIC_KEY_PIN')
    return modulus


def private_resume_inputs(kit, plan_ref, seed_ref):
    """Read the published lifecycle pair without renaming immutable inputs.

    Successor inputs retain their original frozen loader validation. Lifecycle
    publication uses a distinct filename family; SHA-bound binding selects one
    exact pair, and the frozen hydrator still validates the full seed contract.
    """
    reference(plan_ref)
    reference(seed_ref)
    parent = ('/var/lib/xuanjun-p2-preparation/'
              'artifact-11796280855-p2pkg-38372304180-1/'
              'complete-install-candidate-38503014520')
    lifecycle = (
        'epoch7-lifecycle-approved-plan-' + plan_ref['sha256'][:16] + '.private.json',
        'epoch7-lifecycle-resume-inputs-' + seed_ref['sha256'][:16] + '.private.json')
    names = (os.path.basename(plan_ref['path']), os.path.basename(seed_ref['path']))
    if names != lifecycle:
        return kit._private_resume_inputs(plan_ref['path'], plan_ref['sha256'],
                                          seed_ref['path'], seed_ref['sha256'])
    need(os.path.dirname(plan_ref['path']) == parent and
         os.path.dirname(seed_ref['path']) == parent, 'PRIVATE_INPUT_PATH')
    plan_raw = read(plan_ref['path'], plan_ref['sha256'], bound=2 * 1024 * 1024)
    seed_raw = read(seed_ref['path'], seed_ref['sha256'], bound=64 * 1024 * 1024)
    plan, envelope = decode(plan_raw), decode(seed_raw)
    need(type(plan) is dict and type(envelope) is dict and
         set(envelope) == {'schema', 'seed'} and
         type(envelope['schema']) is int and envelope['schema'] == 2 and
         type(envelope['seed']) is dict, 'PRIVATE_SEED_SCHEMA')
    return plan_raw, plan, envelope['seed']


def build_driver(cfg):
    """Reuse the reviewed private-seed compiler and concrete 16-phase factory.

    Verifies the old Kit, exact private inputs and original probe receipt.
    Does not call resume, Prepare, observer/probe or install; NativeRecovery
    remains the only coordinator and retains independent approval validation.
    """
    value, root, loader = bound(cfg)
    import epoch7_host_factory as factory
    import epoch7_recovery_sequence as sequence
    # The legacy entry bytes were already authenticated by Attempt5 imports.
    LEGACY_ENTRY_SHA = '21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890'
    bootstrap = loader.pinned_module(root + '/legacy/epoch7_recovery_entry.py',
                                     LEGACY_ENTRY_SHA)
    kit = bootstrap.verify_kit(root + '/legacy', value['legacy_manifest_sha256'])
    plan_ref, seed_ref = value['approved_plan'], value['private_seed']
    plan_raw, plan, private = private_resume_inputs(kit, plan_ref, seed_ref)
    seed = kit._hydrate_seed(private, factory)
    evidence = kit._authenticate_probe_receipt(seed['observation'])
    prepared = factory.prepare_host_inputs(seed)
    need(prepared.get('state') == 'COMPILED_NOT_ADMITTED' and
         prepared.get('install_admission') is False and prepared.get('unresolved') == [],
         'HOST_INPUTS_UNRESOLVED')
    inputs = prepared['inputs']
    contract = factory.compile_host_contract(inputs)
    need(all(canonical(plan.get(k)) == canonical(v) for k, v in contract.items()),
         'APPROVED_CONTRACT_CHANGED')
    private_resume_inputs(kit, plan_ref, seed_ref)
    need(kit._authenticate_probe_receipt(seed['observation']) == evidence,
         'PROBE_RECEIPT_CHANGED')
    driver = factory.assemble_host_driver(plan_raw, inputs, value['legacy_review_id'],
                                         value['legacy_approval_body_sha256'])
    need(isinstance(driver, sequence.InjectedDriver), 'CONCRETE_DRIVER_REQUIRED')
    if _observer_session is not None:
        _observer_session.attach(driver)
    return driver


class SignedHostReadback(object):
    """Authenticated live readback over a separately bound root Unix socket.

    The existing trusted transaction observer must answer each fresh nonce.
    No receipt generation, root command dispatch, retries, or synthetic facts.
    Missing observer capability remains an external deployment blocker.
    """
    def __init__(self, cfg, value):
        from receipt_provider import ReceiptProvider
        self.grant = copy.deepcopy(cfg['grant'])
        self.socket_path = value['receipt_socket']
        self.issuer = value['receipt_issuer']
        modulus, unused = public_key(value['receipt_public_key'])
        self.verifier = ReceiptProvider(lambda unused: None, modulus, 65537, self.issuer)

    def __call__(self, grant, attempt, operation, payload):
        from issuer_service import HOST_OPERATIONS
        need(grant == self.grant and operation in HOST_OPERATIONS and
             type(attempt) is str and 0 < len(attempt) <= 128 and
             type(payload) is dict, 'HOST_REQUEST_SCOPE')
        binding = {'grant_sha256': digest(grant), 'attempt_id': attempt,
                   'operation': operation, 'payload_sha256': digest(payload)}
        # Reuse the reviewed kernel-peer-authenticated bounded transport.
        # No missing socket is created and no request is automatically retried.
        value, unused_root, loader = bound(_context[0])
        request = {'schema': 1, 'nonce': os.urandom(16).hex(),
                   'binding': binding, 'payload': copy.deepcopy(payload)}
        started = int(time.time())
        envelope = loader.UnixTransport(self.socket_path)(request)
        need(type(envelope) is dict and set(envelope) == {'body', 'signature'},
             'HOST_ENVELOPE')
        body = envelope['body']
        need(type(body) is dict and set(body) ==
             {'schema', 'issuer', 'request', 'issued_utc', 'expires_utc', 'receipt'} and
             type(body['schema']) is int and body['schema'] == 1 and
             body['issuer'] == self.issuer and body['request'] == request,
             'HOST_REPLY_BINDING')
        now = int(time.time())
        need(type(body['issued_utc']) is int and type(body['expires_utc']) is int and
             started <= body['issued_utc'] <= now <
             body['expires_utc'] <= min(body['issued_utc'] + 30, grant['expires_utc']),
             'HOST_REPLY_EXPIRED')
        self.verifier._signature(body, envelope['signature'])
        receipt = body['receipt']
        need(type(receipt) is dict and set(receipt) == set(binding) |
             {'run_id', 'job_id', 'invoke_id', 'backup_sha256', 'checkpoint_sha256',
              'log_sha256', 'result'} and
             all(receipt.get(k) == v for k, v in binding.items()), 'HOST_RECEIPT_BINDING')
        for name in ('run_id', 'job_id', 'invoke_id'):
            need(type(receipt[name]) is str and
                 re.fullmatch('[A-Za-z0-9_.:/-]{1,128}', receipt[name]) and
                 receipt[name].upper() != 'UNKNOWN', 'TRANSACTION_UNKNOWN')
        for name in ('backup_sha256', 'checkpoint_sha256', 'log_sha256'):
            pin(receipt[name])
        need(type(receipt['result']) is dict and
             receipt['result'].get('status') not in (None, 'UNKNOWN'), 'HOST_RESULT_UNKNOWN')
        return copy.deepcopy(receipt)


def build_host_readback(cfg):
    value, unused_root, unused_loader = bound(cfg)
    return SignedHostReadback(cfg, value)


def observer_spec(cfg):
    value, unused_root, unused_loader = bound(cfg)
    return copy.deepcopy(value.get('observer_service'))


def build_observer_session(cfg, module, source_check):
    global _observer_session
    value, unused_root, assembly = bound(cfg)
    need(value['schema'] == 2 and _observer_session is None, 'OBSERVER_SESSION_SCOPE')
    import types
    api = types.SimpleNamespace(decode=decode,read=read,reference=reference,
                                public_key=public_key,protected=protected)
    _observer_session = module.ObserverSession(api,assembly,cfg,value['observer_service'],source_check)
    return _observer_session
