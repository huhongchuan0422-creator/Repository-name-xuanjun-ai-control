"""Explicit root-admin register/query CLI; never creates a ledger or Grant."""
import argparse
import hashlib
import json
import os
import stat
import sys
import types

_parser = argparse.ArgumentParser()
_parser.add_argument('operation', choices=('register', 'query'))
_parser.add_argument('--registry-root', default='/etc/xuanjun-p2/registry')
_parser.add_argument('--registration-id', required=True)
_parser.add_argument('--record-sha256', required=True)
_parser.add_argument('--assembly-sha256', required=True)
_parser.add_argument('--registry-code-sha256', required=True)
_parser.add_argument('--binding-file')
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

_registry = _assembly.pinned_module(_here + '/registry.py', _args.registry_code_sha256)


def main():
    if _args.operation == 'register':
        _registry.need(bool(_args.binding_file), 'BINDING_FILE_REQUIRED')
        # Verify exact ID before any write; registration ID cannot redirect the
        # immutable record name away from the approved request.
        raw, value = _registry.read(_args.binding_file, _args.record_sha256)
        _registry.need(value.get('registration_id') == _args.registration_id,
                       'REGISTER_REQUEST_ID')
        result = _registry.register(_args.registry_root, _args.binding_file,
                                    _args.record_sha256)
    else:
        _registry.need(_args.binding_file is None, 'QUERY_HAS_NO_WRITE_INPUT')
        result = _registry.query(_args.registry_root, _args.registration_id,
                                 _args.record_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        print('{"state":"HOLD","reason":"REGISTRY_VALIDATION_OR_IO_FAILED"}')
        sys.exit(2)
