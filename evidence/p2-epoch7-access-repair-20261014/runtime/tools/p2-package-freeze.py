#!/usr/bin/env python3
"""Build and verify a deterministic, immutable P2 manual-install archive.

The archive is deliberately data-only: it contains the exact files named by
the reviewed runtime manifest plus provenance and this verifier.  It never
reads credentials, calls a model, installs a service, or mutates a lease.
"""
from __future__ import print_function

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
import tarfile


SHA1 = re.compile(r'^[0-9a-f]{40}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
PREFIX = 'xuanjun-p2-package/'
PROVENANCE = 'P2_PACKAGE_PROVENANCE.json'
VERIFIER = 'tools/p2-package-freeze.py'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_json(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def load_json(data):
    return json.loads(data.decode('utf-8'), object_pairs_hook=no_duplicates)


def safe_relative(path):
    return (isinstance(path, str) and path and not path.startswith('/')
            and '\\' not in path and '' not in path.split('/')
            and '.' not in path.split('/') and '..' not in path.split('/'))


def read_regular(root, relative, maximum=536870912):
    if not safe_relative(relative):
        raise ValueError('UNSAFE_PACKAGE_PATH')
    root = os.path.realpath(root)
    path = os.path.join(root, relative)
    if os.path.realpath(path) != path or not path.startswith(root + os.sep):
        raise ValueError('PACKAGE_PATH_ESCAPE')
    info = os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_size > maximum):
        raise ValueError('BOUNDED_REGULAR_PACKAGE_FILE_REQUIRED')
    with open(path, 'rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('PACKAGE_FILE_TOO_LARGE')
    return data


def checked_inputs(root, manifest_relative, verifier_relative):
    manifest_bytes = read_regular(root, manifest_relative, 4 * 1024 * 1024)
    manifest = load_json(manifest_bytes)
    files = manifest.get('files')
    if (manifest.get('schema') != 2 or not isinstance(files, dict)
            or not files):
        raise ValueError('REVIEWED_RUNTIME_MANIFEST_REQUIRED')
    if 'stage1/native_child_adapter.py' not in files:
        raise ValueError('NATIVE_CHILD_ADAPTER_MUST_BE_FROZEN')
    if manifest_relative in files or verifier_relative in files:
        raise ValueError('PACKAGE_METADATA_MUST_NOT_DUPLICATE_RUNTIME_FILE')
    payload = {}
    for relative in sorted(files):
        expected = files[relative]
        if not safe_relative(relative) or not SHA256.fullmatch(expected or ''):
            raise ValueError('INVALID_RUNTIME_MANIFEST_ENTRY')
        data = read_regular(root, relative)
        if digest(data) != expected:
            raise ValueError('RUNTIME_FILE_HASH_MISMATCH:' + relative)
        payload[relative] = data
    verifier = read_regular(root, verifier_relative, 4 * 1024 * 1024)
    return manifest_bytes, manifest, payload, verifier


def tar_entry(archive, name, data, mode=0o444):
    info = tarfile.TarInfo(PREFIX + name)
    info.size = len(data)
    info.mode = mode
    info.uid = info.gid = 0
    info.uname = info.gname = 'root'
    info.mtime = 0
    archive.addfile(info, io.BytesIO(data))


def build(root, manifest_relative, verifier_relative, output,
          source_commit, source_tree):
    if not SHA1.fullmatch(source_commit or '') or not SHA1.fullmatch(source_tree or ''):
        raise ValueError('EXACT_GIT_COMMIT_AND_TREE_REQUIRED')
    manifest_bytes, manifest, payload, verifier = checked_inputs(
        root, manifest_relative, verifier_relative)
    provenance = {
        'schema': 2,
        'source_repository': 'huhongchuan0422-creator/Repository-name-xuanjun-ai-control',
        'source_commit': source_commit,
        'source_tree': source_tree,
        'runtime_manifest_path': manifest_relative,
        'runtime_manifest_sha256': digest(manifest_bytes),
        'runtime_files': manifest['files'],
        'verifier_path': VERIFIER,
        'verifier_sha256': digest(verifier),
        'oauth_content_included': False,
        'tls_private_key_included': False,
        'new_paid_api_usage': 'NONE',
        'operations': {
            'verify_only': ['scripts/uk-p2-install.py', '--operation', 'verify-only'],
            'install': ['scripts/uk-p2-install.py', '--operation', 'install'],
            'rollback': ['scripts/uk-p2-install.py', '--operation', 'rollback'],
        },
        'rollback_map': [
            'ACTIVATION_FENCED_EPOCH',
            'NEW_RUNTIME_STOPPED',
            'PROVISIONING_RESTORED',
            'LEGACY_FILES_RESTORED_NOT_RESTARTED',
            'RECONCILE_DATABASE_AND_EPOCH_BEFORE_ANY_RESTART',
        ],
    }
    raw_tar = io.BytesIO()
    with tarfile.open(fileobj=raw_tar, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for relative in sorted(payload):
            tar_entry(archive, relative, payload[relative])
        tar_entry(archive, manifest_relative, manifest_bytes)
        tar_entry(archive, VERIFIER, verifier, 0o555)
        tar_entry(archive, PROVENANCE, canonical_json(provenance))
    raw_tar.seek(0)
    with open(output, 'wb') as target:
        with gzip.GzipFile(filename='', mode='wb', fileobj=target, mtime=0) as compressed:
            compressed.write(raw_tar.read())
    with open(output, 'rb') as stream:
        archive_sha256 = digest(stream.read())
    return {'archive_sha256': archive_sha256, 'provenance': provenance,
            'file_count': len(payload)}


def verify(archive_path, expected_sha256=None, expected_commit=None,
           expected_tree=None):
    with open(archive_path, 'rb') as stream:
        archive_bytes = stream.read()
    actual_archive = digest(archive_bytes)
    if expected_sha256 and actual_archive != expected_sha256:
        raise ValueError('ARCHIVE_SHA256_MISMATCH')
    values = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        for member in archive.getmembers():
            if (not member.isfile() or not member.name.startswith(PREFIX)
                    or member.uid != 0 or member.gid != 0 or member.mtime != 0
                    or member.name in values):
                raise ValueError('UNSAFE_OR_DUPLICATE_ARCHIVE_MEMBER')
            relative = member.name[len(PREFIX):]
            if not safe_relative(relative):
                raise ValueError('UNSAFE_ARCHIVE_MEMBER_PATH')
            values[relative] = archive.extractfile(member).read()
    if PROVENANCE not in values:
        raise ValueError('PACKAGE_PROVENANCE_MISSING')
    provenance = load_json(values[PROVENANCE])
    required = {'schema', 'source_repository', 'source_commit', 'source_tree',
                'runtime_manifest_path', 'runtime_manifest_sha256',
                'runtime_files', 'verifier_path', 'verifier_sha256',
                'oauth_content_included', 'tls_private_key_included',
                'new_paid_api_usage', 'operations', 'rollback_map'}
    if set(provenance) != required or provenance.get('schema') != 2:
        raise ValueError('EXACT_PACKAGE_PROVENANCE_REQUIRED')
    if expected_commit and provenance['source_commit'] != expected_commit:
        raise ValueError('SOURCE_COMMIT_MISMATCH')
    if expected_tree and provenance['source_tree'] != expected_tree:
        raise ValueError('SOURCE_TREE_MISMATCH')
    if (provenance['oauth_content_included'] is not False
            or provenance['tls_private_key_included'] is not False
            or provenance['new_paid_api_usage'] != 'NONE'):
        raise ValueError('PACKAGE_SECRET_OR_PAID_API_POLICY_VIOLATION')
    expected_operations = {
        'verify_only': ['scripts/uk-p2-install.py', '--operation', 'verify-only'],
        'install': ['scripts/uk-p2-install.py', '--operation', 'install'],
        'rollback': ['scripts/uk-p2-install.py', '--operation', 'rollback'],
    }
    expected_rollback = [
        'ACTIVATION_FENCED_EPOCH', 'NEW_RUNTIME_STOPPED',
        'PROVISIONING_RESTORED', 'LEGACY_FILES_RESTORED_NOT_RESTARTED',
        'RECONCILE_DATABASE_AND_EPOCH_BEFORE_ANY_RESTART']
    if (provenance['operations'] != expected_operations
            or provenance['rollback_map'] != expected_rollback):
        raise ValueError('VERIFY_INSTALL_ROLLBACK_MAP_MISMATCH')
    manifest_path = provenance['runtime_manifest_path']
    if (manifest_path not in values
            or digest(values[manifest_path]) != provenance['runtime_manifest_sha256']):
        raise ValueError('PACKAGED_MANIFEST_IDENTITY_MISMATCH')
    manifest = load_json(values[manifest_path])
    if manifest.get('files') != provenance['runtime_files']:
        raise ValueError('MANIFEST_PROVENANCE_DISAGREEMENT')
    if 'stage1/native_child_adapter.py' not in provenance['runtime_files']:
        raise ValueError('PACKAGED_NATIVE_CHILD_ADAPTER_MISSING')
    for relative, expected in provenance['runtime_files'].items():
        if relative not in values or digest(values[relative]) != expected:
            raise ValueError('PACKAGED_RUNTIME_FILE_MISMATCH:' + relative)
    verifier_path = provenance['verifier_path']
    if verifier_path not in values or digest(values[verifier_path]) != provenance['verifier_sha256']:
        raise ValueError('PACKAGED_VERIFIER_MISMATCH')
    expected_names = set(provenance['runtime_files']) | {
        manifest_path, verifier_path, PROVENANCE}
    if set(values) != expected_names:
        raise ValueError('UNDECLARED_ARCHIVE_MEMBER')
    return {'archive_sha256': actual_archive,
            'source_commit': provenance['source_commit'],
            'source_tree': provenance['source_tree'],
            'file_count': len(provenance['runtime_files'])}


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='operation')
    make = sub.add_parser('build')
    make.add_argument('--source-root', required=True)
    make.add_argument('--manifest', default='deploy/integration-manifest.json')
    make.add_argument('--verifier', default='tools/p2-package-freeze.py')
    make.add_argument('--output', required=True)
    make.add_argument('--source-commit', required=True)
    make.add_argument('--source-tree', required=True)
    check = sub.add_parser('verify')
    check.add_argument('--archive', required=True)
    check.add_argument('--sha256')
    check.add_argument('--source-commit')
    check.add_argument('--source-tree')
    args = parser.parse_args(argv)
    if args.operation == 'build':
        result = build(args.source_root, args.manifest, args.verifier,
                       args.output, args.source_commit, args.source_tree)
    elif args.operation == 'verify':
        result = verify(args.archive, args.sha256, args.source_commit,
                        args.source_tree)
    else:
        parser.error('operation required')
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
