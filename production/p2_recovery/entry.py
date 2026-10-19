"""Official controlled recovery apply/serve/run. No implicit production defaults."""
import argparse
import hashlib
import json
import os
import signal
import stat
import sys
import types


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('apply', 'serve', 'run'))
    for name in ('request', 'request-sha256', 'evidence', 'evidence-sha256',
                 'trust', 'trust-sha256', 'plan', 'plan-sha256',
                 'bootstrap-sha256', 'recovery-code-sha256', 'executor-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    if (os.getuid() != 0 or os.geteuid() != 0 or not sys.flags.isolated or
            not sys.flags.no_site or not sys.dont_write_bytecode or
            os.uname().nodename.split('.')[0] != 'iZd7oeikknn1z21sq6ji6zZ'):
        raise RuntimeError('ISOLATED_UK_ROOT_REQUIRED')
    # Read the small sibling bootstrap without trusting sys.path or following
    # writable/symlink ancestry. Its exact SHA is supplied by the Owner command.
    here = os.path.dirname(os.path.abspath(__file__))
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in here.strip('/').split('/'):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
            info = os.fstat(directory)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise RuntimeError('BOOTSTRAP_PARENT')
        fd = os.open('bootstrap.py', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o022:
            raise RuntimeError('BOOTSTRAP_FILE')
        raw = os.read(fd, 1048577)
    finally:
        os.close(fd)
    if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != args.bootstrap_sha256:
        raise RuntimeError('BOOTSTRAP_SHA')
    bootstrap = types.ModuleType('_p2_recovery_bootstrap')
    exec(compile(raw, here + '/bootstrap.py', 'exec'), bootstrap.__dict__)
    r = bootstrap.load(here + '/recovery.py', args.recovery_code_sha256)
    executor = bootstrap.load(here + '/executor.py', args.executor_sha256)
    executor.r = r
    request = r.decode(r.read(args.request, args.request_sha256))
    packet = r.decode(r.read(args.evidence, args.evidence_sha256))
    keys = r.load_trust(args.trust, args.trust_sha256)
    r.decide(request, packet, keys)
    ref = {'path': args.plan, 'sha256': args.plan_sha256}
    plan = executor.signed_plan(request, packet, ref)
    manifest = r.decode(r.read(plan['assembly_manifest']['path'], plan['assembly_manifest']['sha256']))
    root = plan['assembly_root']
    def pinned(relative):
        return bootstrap.load(root + '/' + relative, manifest['files'][relative])
    assembly = pinned('production/p2_attempt5/assembly.py')
    registry = pinned('production/p2_attempt5/registry.py')
    gate = executor.RecoveryGate(request, packet, keys, ref, registry, assembly)
    record, cfg, unused = gate.verify('recovery_apply' if args.operation == 'apply' else 'execution_gate',
                                    require_committed=args.operation != 'apply')
    loader = bootstrap.load(plan['kit_root'] + '/attempt5/runtime/versioned_entry.py',
                            plan['loader_sha256'])
    if args.operation == 'apply':
        with loader.imports(plan['kit_root'], plan['kit_manifest_sha256']):
            import authority_store
            import authorization
            import receipt_provider
            result = executor.apply(gate, {'authority_store': authority_store,
                'authorization': authorization, 'receipt_provider': receipt_provider})
        print(json.dumps(result, sort_keys=True))
        return 0
    # Execute the original formal entry, its Registry/Manifest checks, native
    # driver, Observer session and PermitCycle. Inject only additional gates.
    values = {'kit-root': plan['kit_root'], 'loader-sha256': plan['loader_sha256'],
        'manifest-sha256': plan['kit_manifest_sha256'], 'config': plan['config']['path'],
        'config-sha256': plan['config']['sha256'],
        'assembly-sha256': manifest['files']['production/p2_attempt5/assembly.py'],
        'assembly-manifest': plan['assembly_manifest']['path'],
        'assembly-manifest-sha256': plan['assembly_manifest']['sha256'],
        'registry-root': plan['registry_root'], 'registry-id': record['registration_id'],
        'registry-record-sha256': plan['registry_record']['sha256']}
    argv = [root + '/production/p2_attempt5/entry.py', args.operation]
    for key, value in values.items():
        argv.extend(['--' + key, value])
    previous = sys.argv
    try:
        sys.argv = argv
        original = pinned('production/p2_attempt5/entry.py')
        original_issuer = original.ProductionIssuer
        class GuardedIssuer(original_issuer):
            def __init__(self, *pos, **kw):
                gate.verify()
                super(GuardedIssuer, self).__init__(*pos, **kw)
            def serve_one(self):
                gate.verify()
                return super(GuardedIssuer, self).serve_one()
        # Gate at the actual handle boundary too: a client arriving after
        # accept must not use a stale pre-accept attestation.
        class GuardedService(object):
            def __init__(self, service): self.service = service
            def handle(self, *pos, **kw):
                gate.verify()
                return self.service.handle(*pos, **kw)
        old_init = GuardedIssuer.__init__
        def init(self, *pos, **kw):
            old_init(self, *pos, **kw)
            self.service = GuardedService(self.service)
        GuardedIssuer.__init__ = init
        original.ProductionIssuer = GuardedIssuer
        transport = original._assembly.UnixTransport
        class GuardedTransport(transport):
            def __call__(self, request):
                gate.verify()
                return super(GuardedTransport, self).__call__(request)
        original._assembly.UnixTransport = GuardedTransport
        native = original.native_cycle
        def cycle(factory, *pos, **kw):
            gate.verify()
            return native(lambda: executor.guarded_driver(factory(), gate), *pos, **kw)
        original.native_cycle = cycle
        signal.alarm(0)  # Original bounded native controls govern the execution.
        return original.main()
    finally:
        sys.argv = previous


if __name__ == '__main__':
    signal.signal(signal.SIGALRM, lambda unused_a, unused_b: sys.exit('RECOVERY_TIMEOUT_HOLD_RETAIN_OUTPUT'))
    signal.alarm(120)
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({'state': 'HOLD_RETAIN_OUTPUT', 'reason': type(exc).__name__,
                          'activation_success': False}))
        sys.exit(2)
