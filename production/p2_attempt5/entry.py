"""Explicit deployment entry. No default paths, credentials, or permission."""
import argparse
import hashlib
import json
import os
import signal
import socket
import sys

# -I -S excludes the script directory: load the sibling by descriptor only.
# The exact entry/assembly hashes must both be included in the deployment permit.
import types
import stat
_parser = argparse.ArgumentParser()
_parser.add_argument('operation', choices=('serve', 'run'))
for _option in ('kit-root', 'loader-sha256', 'manifest-sha256', 'config',
                'config-sha256', 'assembly-sha256', 'assembly-manifest',
                'assembly-manifest-sha256'):
    _parser.add_argument('--' + _option, required=True)
_args = _parser.parse_args()
if (os.geteuid() != 0 or not sys.flags.isolated or not sys.flags.no_site or
        not sys.dont_write_bytecode):
    raise RuntimeError('P2_PRODUCTION_ISOLATED_ROOT_REQUIRED')
_here = os.path.dirname(os.path.abspath(__file__))
_directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for _part in _here.strip('/').split('/'):
        _child = os.open(_part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=_directory)
        os.close(_directory)
        _directory = _child
        _info = os.fstat(_directory)
        if _info.st_uid != 0 or _info.st_mode & 0o022:
            raise RuntimeError('P2_PRODUCTION_BOOTSTRAP_PARENT')
    _fd = os.open('assembly.py', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=_directory)
finally:
    os.close(_directory)
try:
    _info = os.fstat(_fd)
    if (not stat.S_ISREG(_info.st_mode) or _info.st_nlink != 1 or
            _info.st_uid != 0 or _info.st_mode & 0o022):
        raise RuntimeError('P2_PRODUCTION_ASSEMBLY_FILE')
    _raw = os.read(_fd, 1048577)
finally:
    os.close(_fd)
if (len(_raw) > 1048576 or
        hashlib.sha256(_raw).hexdigest() != _args.assembly_sha256):
    raise RuntimeError('P2_PRODUCTION_ASSEMBLY_SHA')
_assembly = types.ModuleType('_p2_production_assembly')
exec(compile(_raw, _here + '/assembly.py', 'exec'), _assembly.__dict__)
OpenSSLSigner, ProductionIssuer = _assembly.OpenSSLSigner, _assembly.ProductionIssuer
native_cycle, pinned_module = _assembly.native_cycle, _assembly.pinned_module
protected_file, require = _assembly.protected_file, _assembly.require


def configuration(path, expected):
    fd = protected_file(path, private=True)
    try:
        raw = os.read(fd, 65537)
    finally:
        os.close(fd)
    require(len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == expected,
            'DEPLOYMENT_CONFIG_PIN')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'CONFIG_DUPLICATE_KEY')
            value[key] = item
        return value
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
    require(type(value) is dict and set(value) == {
        'schema', 'database', 'socket', 'principal', 'key', 'public_der_sha256',
        'issuer', 'adapter_path', 'adapter_sha256', 'ledger_directory', 'grant',
        'review_id', 'cycle_policy', 'command_sha256'}, 'DEPLOYMENT_FIELDS')
    require(type(value['schema']) is int and value['schema'] == 1,
            'DEPLOYMENT_VERSION')
    require(value['principal']['host'] == os.uname().nodename ==
            value['grant']['target_host'] and
            value['principal']['actor_id'] == value['grant']['actor_id'],
            'CONFIG_HOST_ACTOR')
    return value


def main():
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
            'ISOLATED_INTERPRETER')
    args = _args
    cfg = configuration(args.config, args.config_sha256)
    identity, manifest = _assembly.release_identity(
        args.assembly_manifest, args.assembly_manifest_sha256, cfg['grant'],
        os.path.abspath(__file__), args.assembly_sha256, args.manifest_sha256)
    loader = pinned_module(args.kit_root + '/attempt5/runtime/versioned_entry.py',
                           args.loader_sha256)
    with loader.imports(args.kit_root, args.manifest_sha256) as inherited:
        require(inherited['source_commit'] == manifest['reviewed_core_commit'] and
                inherited['source_tree'] == manifest['reviewed_core_tree'],
                'INHERITED_CORE_SOURCE')
        adapter = pinned_module(cfg['adapter_path'], cfg['adapter_sha256'])
        if args.operation == 'run':
            cycle = native_cycle(lambda: adapter.build_driver(cfg),
                                 cfg['ledger_directory'], cfg['grant'],
                                 cfg['socket'], adapter.public_modulus(cfg),
                                 cfg['issuer'], cfg['review_id'], identity,
                                 cfg['cycle_policy'])
            result = cycle.run(cfg['command_sha256'])
            # Full private report is durably emitted by PermitCycle. No secrets,
            # raw host receipts or local paths are printed into public logs.
            print(json.dumps({'status': result['status']}))
            return 0 if result['status'] == 'SUCCEEDED' else 2
        signer = OpenSSLSigner(cfg['key'], cfg['public_der_sha256'])
        server = None
        try:
            server = ProductionIssuer(cfg['database'], cfg['socket'],
                                      cfg['principal'], signer, cfg['issuer'],
                                      adapter.build_host_readback(cfg), cfg['grant'])
            def stop(signum, frame):
                raise KeyboardInterrupt()
            signal.signal(signal.SIGTERM, stop)
            while True:
                try:
                    server.serve_one()
                except socket.timeout:
                    continue
                except (ValueError, RuntimeError, OSError):
                    # Malformed/disconnected client cannot reset quota/history.
                    # Do not print exception text containing private host data.
                    continue
        except KeyboardInterrupt:
            return 0
        finally:
            if server is not None:
                server.close()
            signer.close()


if __name__ == '__main__':
    sys.exit(main())
