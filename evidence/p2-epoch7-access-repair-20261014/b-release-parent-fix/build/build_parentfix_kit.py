#!/usr/bin/env python3
"""Offline, exact-input R7 compiler-kit overlay. Never installs or resumes a host.

Source commit/tree must be independently verified publication identities supplied
by the caller. This program does not access Git or the network to establish them.
"""
import argparse
import ast
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tarfile

BASELINE_ROOT = 'epoch7-recovery-candidate-r7'
OUTPUT_ROOT = 'epoch7-recovery-candidate-r7-parentfix'
ARCHIVE_SIZE = 1041263
ARCHIVE_SHA256 = 'e9841797571b3f039af8782b0aa1051c11c4b7938a2287abfd433e394b3d1645'
MANIFEST_SHA256 = '7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4'
OVERLAY_MAP_SHA256 = 'e46daccb06e7b616e9f8d0bfd20dc085a4e84cbb2a25f555636fd5bcce1b8763'
ORIGINAL_MAP_SHA256 = 'd50fe46d90a7d1fe0ca2c437e4c2abd64ab1a7602f6766fd54e4df5fb10f8295'
MANIFEST = 'recovery-kit-manifest.json'
RUNTIME = 'xuanjun-p2-package/'
NEW_TEST = 'tests/host_factory/test_fresh_release_parent.py'
OVERLAY_SOURCES = {
    'epoch7_recovery_entry.py': 'kit-overlay/epoch7_recovery_entry.py',
    'helpers/epoch7_host_factory.py': 'kit-overlay/helpers/epoch7_host_factory.py',
    'helpers/epoch7_resource_plan.py': 'kit-overlay/helpers/epoch7_resource_plan.py',
    'tests/host_factory/test_epoch7_full_factory.py': 'kit-overlay/tests/host_factory/test_epoch7_full_factory.py',
    'tests/host_factory/test_epoch7_full_factory_fixture.py': 'kit-overlay/tests/host_factory/test_epoch7_full_factory_fixture.py',
    'tests/host_factory/test_epoch7_host_factory.py': 'kit-overlay/tests/host_factory/test_epoch7_host_factory.py',
    'tests/resource_plan/test_epoch7_python_resource.py': 'kit-overlay/tests/resource_plan/test_epoch7_python_resource.py',
    'tests/resource_plan/test_epoch7_resource_plan.py': 'kit-overlay/tests/resource_plan/test_epoch7_resource_plan.py',
    NEW_TEST: 'tests/test_fresh_release_parent.py',
}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')


def strict_json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def invalid_constant(unused):
        raise ValueError('NONFINITE_JSON')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=invalid_constant)


def relative(name):
    need(type(name) is str and name and not name.startswith('/') and
         '\\' not in name and all(32 <= ord(c) < 127 for c in name) and
         all(part not in ('', '.', '..') for part in name.split('/')),
         'UNSAFE_RELATIVE_PATH')
    return name


def directories(names):
    return {name.rsplit('/', i)[0] for name in names
            for i in range(1, name.count('/') + 1)}


def _archive_files(raw):
    """Parse in memory only; structural checks remain independent of digest pins."""
    files, dirs, seen = {}, set(), set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        need(len(members) == 295, 'ARCHIVE_HEADER_COUNT')
        for member in members:
            name = relative(member.name)
            need(name not in seen, 'ARCHIVE_DUPLICATE_PATH')
            seen.add(name)
            need(name == BASELINE_ROOT or name.startswith(BASELINE_ROOT + '/'),
                 'ARCHIVE_ROOT')
            need(not member.pax_headers and not member.linkname, 'ARCHIVE_EXTENDED_OR_LINK')
            if member.isdir():
                need(member.size == 0, 'DIRECTORY_BYTES')
                dirs.add(name)
                continue
            need(member.isreg() and 0 <= member.size <= 33554432 and
                 name != BASELINE_ROOT, 'ARCHIVE_FILE_TYPE_OR_SIZE')
            with archive.extractfile(member) as stream:
                body = stream.read(member.size + 1)
            need(len(body) == member.size, 'ARCHIVE_FILE_BYTES')
            files[name[len(BASELINE_ROOT) + 1:]] = body
    need(len(files) == 253, 'ARCHIVE_FILE_COUNT')
    full_names = {BASELINE_ROOT + '/' + name for name in files}
    need(dirs == directories(full_names) and not dirs.intersection(full_names),
         'ARCHIVE_DIRECTORY_CLOSURE')
    return files


def validate_file_closure(files, manifest):
    pins = manifest['files']
    need(type(pins) is dict and len(pins) == 252, 'BASELINE_PIN_COUNT')
    need(set(files) == set(pins) | {MANIFEST}, 'BASELINE_FILE_CLOSURE')
    for name, pin in pins.items():
        relative(name)
        need(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and
             sha(files[name]) == pin, 'BASELINE_FILE_HASH')


def authenticate_archive(raw):
    need(type(raw) is bytes and len(raw) == ARCHIVE_SIZE and
         sha(raw) == ARCHIVE_SHA256, 'BASELINE_ARCHIVE_PIN')
    files = _archive_files(raw)
    need(sha(files[MANIFEST]) == MANIFEST_SHA256, 'BASELINE_MANIFEST_PIN')
    manifest = strict_json(files[MANIFEST])
    validate_file_closure(files, manifest)
    return files, manifest


def authenticate_map(raw):
    need(type(raw) is bytes and sha(raw) == OVERLAY_MAP_SHA256, 'OVERLAY_MAP_PIN')
    mapping = strict_json(raw)
    need(mapping['schema'] == 1 and mapping['compiler_root_leaf'] == OUTPUT_ROOT and
         mapping['baseline_root_leaf'] == BASELINE_ROOT and
         mapping['original_overlay_map_sha256'] == ORIGINAL_MAP_SHA256,
         'OVERLAY_MAP_SCOPE')
    rows = mapping['files']
    need(type(rows) is list and len(rows) == 9, 'OVERLAY_ROW_COUNT')
    need({row['kit_target'] for row in rows} == set(OVERLAY_SOURCES), 'OVERLAY_TARGET_CLOSURE')
    for row in rows:
        target, source = relative(row['kit_target']), relative(row['source'])
        need(source == OVERLAY_SOURCES[target], 'OVERLAY_SOURCE_PATH')
        need(type(row['bytes']) is int and 0 < row['bytes'] <= 1048576,
             'OVERLAY_SIZE')
        need(re.fullmatch('[0-9a-f]{64}', row['sha256']) and
             re.fullmatch('[0-9a-f]{40}', row['git_blob_sha1']), 'OVERLAY_HASH_SHAPE')
        old = row['baseline_sha256']
        need((target == NEW_TEST and old is None) or
             (target != NEW_TEST and type(old) is str and
              re.fullmatch('[0-9a-f]{64}', old)), 'OVERLAY_BASELINE_HASH')
    return mapping


def validate_identity(commit, tree, fixture_source=False):
    need(type(fixture_source) is bool, 'FIXTURE_FLAG')
    need(all(type(value) is str and re.fullmatch('[0-9a-f]{40}', value)
             for value in (commit, tree)), 'SOURCE_IDENTITY_FORMAT')
    zero = '0' * 40
    if fixture_source:
        need(commit == tree == zero, 'FIXTURE_REQUIRES_EXPLICIT_ZERO_IDENTITIES')
    else:
        need(commit != zero and tree != zero, 'SOURCE_IDENTITY_UNPUBLISHED')


def update_test_suites(manifest, files):
    """Add one declared test; check affected suites without widening other suites."""
    suite = manifest['test_suites']['host_factory']
    need(NEW_TEST not in suite['tests'], 'NEW_TEST_ALREADY_PRESENT')
    suite['tests'].append(NEW_TEST)
    suite['imports']['test_fresh_release_parent'] = NEW_TEST
    aliases = {}
    for path in files:
        if path.startswith('tests/') and path.rsplit('/', 1)[-1].startswith('test_') and path.endswith('.py'):
            alias = path.rsplit('/', 1)[-1][:-3]
            need(alias not in aliases, 'TEST_ALIAS_COLLISION')
            aliases[alias] = path
    for suite_name in ('host_factory', 'resource_plan'):
        row = manifest['test_suites'][suite_name]
        pending, visited = list(row['imports'].values()), set()
        while pending:
            path = pending.pop()
            if path in visited:
                continue
            visited.add(path)
            tree = ast.parse(files[path], filename=path)
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.append(node.module.split('.')[0])
            for alias in imported:
                if not alias.startswith('test_'):
                    continue
                need(alias in aliases, 'UNRESOLVED_STATIC_TEST_IMPORT')
                target = aliases[alias]
                need(row['imports'].get(alias) == target, 'UNDECLARED_STATIC_TEST_IMPORT')
                if target not in visited:
                    pending.append(target)


def deterministic_archive(files):
    """Stable USTAR headers and gzip header; all file content comes from memory."""
    full = {OUTPUT_ROOT + '/' + name: raw for name, raw in files.items()}
    dirs = directories(full)
    need(not dirs.intersection(full), 'OUTPUT_FILE_DIRECTORY_COLLISION')
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, filename='', mode='wb', mtime=0, compresslevel=9) as zipped:
        with tarfile.open(fileobj=zipped, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            for name in sorted(set(full) | dirs):
                relative(name)
                info = tarfile.TarInfo(name)
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                info.mode = 0o700 if name in dirs else 0o444
                if name in dirs:
                    info.type = tarfile.DIRTYPE
                    archive.addfile(info)
                else:
                    info.size = len(full[name])
                    archive.addfile(info, io.BytesIO(full[name]))
    return buffer.getvalue()


def compile_artifact(archive_raw, map_raw, sources, source_commit, source_tree,
                     fixture_source=False):
    validate_identity(source_commit, source_tree, fixture_source)
    old_files, old_manifest = authenticate_archive(archive_raw)
    mapping = authenticate_map(map_raw)
    need(set(sources) == set(OVERLAY_SOURCES.values()), 'OVERLAY_SOURCE_CLOSURE')
    files = dict(old_files)
    for row in mapping['files']:
        target, source = row['kit_target'], row['source']
        body = sources[source]
        need(type(body) is bytes and len(body) == row['bytes'] and
             sha(body) == row['sha256'], 'OVERLAY_SOURCE_PIN')
        blob = hashlib.sha1(('blob %d\0' % len(body)).encode('ascii') + body).hexdigest()
        need(blob == row['git_blob_sha1'], 'OVERLAY_GIT_BLOB_PIN')
        need((row['baseline_sha256'] is None and target not in old_files) or
             (target in old_files and sha(old_files[target]) == row['baseline_sha256']),
             'OVERLAY_BASELINE_PIN')
        files[target] = body
    manifest = copy.deepcopy(old_manifest)
    manifest['files'] = {name: sha(body) for name, body in files.items() if name != MANIFEST}
    manifest['kit_source_commit'] = source_commit
    manifest['kit_source_tree'] = source_tree
    update_test_suites(manifest, files)
    files[MANIFEST] = canonical(manifest)
    need(len(files) == 254 and len(manifest['files']) == 253, 'OUTPUT_FILE_COUNT')
    need(manifest['modules'] == old_manifest['modules'], 'MODULES_CHANGED')
    for key in old_manifest:
        if key not in ('files', 'kit_source_commit', 'kit_source_tree', 'test_suites'):
            need(manifest[key] == old_manifest[key], 'MANIFEST_POLICY_CHANGED')
    runtime_names = {name for name in old_files if name.startswith(RUNTIME)}
    runtime = strict_json(old_files[RUNTIME + 'deploy/integration-manifest.json'])
    need(len(runtime_names) == 110 and len(runtime['files']) == 107, 'RUNTIME_COUNT')
    need(all(files[name] == old_files[name] for name in runtime_names), 'RUNTIME_CHANGED')
    need(all(sha(files[RUNTIME + name]) == pin for name, pin in runtime['files'].items()),
         'RUNTIME_FILE_PIN')
    modified = sorted(name for name in old_files if files[name] != old_files[name])
    need(set(modified) == (set(OVERLAY_SOURCES) - {NEW_TEST}) | {MANIFEST},
         'UNEXPECTED_MODIFIED_FILE')
    need(set(files) - set(old_files) == {NEW_TEST}, 'UNEXPECTED_ADDED_FILE')
    archive = deterministic_archive(files)
    file_pins = lambda values: {name: sha(body) for name, body in values.items()}
    metadata = {
        'schema': 1,
        'purpose': 'OFFLINE_COMPILER_KIT_OVERLAY_NOT_HOST_INSTALLER',
        'source_identity': 'SYNTHETIC_TEST_FIXTURE_NOT_PUBLISHED' if fixture_source else
                           'CALLER_SUPPLIED_PUBLICATION_IDENTITY_EXTERNAL_VERIFICATION_REQUIRED',
        'host_collection': 'NOT_RUN', 'production_resume_authorized': False,
        'baseline': {'root': BASELINE_ROOT, 'archive_sha256': ARCHIVE_SHA256,
                     'archive_bytes': len(archive_raw), 'manifest_sha256': MANIFEST_SHA256,
                     'source_commit': old_manifest['kit_source_commit'],
                     'source_tree': old_manifest['kit_source_tree'],
                     'file_count': len(old_files), 'files': file_pins(old_files)},
        'output': {'root': OUTPUT_ROOT, 'archive_sha256': sha(archive),
                   'archive_bytes': len(archive), 'manifest_sha256': sha(files[MANIFEST]),
                   'source_commit': source_commit, 'source_tree': source_tree,
                   'file_count': len(files), 'manifest_pin_count': len(manifest['files']),
                   'files': file_pins(files)},
        'overlay_map_sha256': sha(map_raw), 'original_overlay_map_sha256': ORIGINAL_MAP_SHA256,
        'overlays': mapping['files'], 'modified_files': modified, 'added_files': [NEW_TEST],
        'unchanged_files': sorted(name for name in old_files if files[name] == old_files[name]),
        'runtime_files_preserved': 107, 'runtime_package_files_preserved': len(runtime_names),
        'modules_unchanged': True,
        'test_suite_imports_added': {
            name: {alias: path for alias, path in row['imports'].items()
                   if alias not in old_manifest['test_suites'][name]['imports']}
            for name, row in manifest['test_suites'].items()
            if set(row['imports']) != set(old_manifest['test_suites'][name]['imports'])},
        'archive_format': {'tar': 'USTAR', 'gzip_mtime': 0, 'uid': 0, 'gid': 0,
                           'mtime': 0, 'file_mode': '0444', 'directory_mode': '0700'},
    }
    return archive, metadata


def read_regular(path, maximum):
    path = Path(os.path.abspath(str(path)))
    need(path.resolve() == path, 'INPUT_PATH_SYMLINK')
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             before.st_size <= maximum, 'INPUT_FILE_TYPE_OR_BOUND')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
                       s.st_mtime_ns, s.st_ctime_ns)
    need(len(raw) <= maximum and stamp(before) == stamp(after) == stamp(os.lstat(str(path))),
         'INPUT_FILE_CHANGED')
    return raw


def write_new(path, raw):
    path = Path(os.path.abspath(str(path)))
    need(path.parent.resolve() == path.parent, 'OUTPUT_PARENT_SYMLINK')
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--candidate-root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--overlay-map', type=Path, default=Path(__file__).resolve().with_name('OVERLAY_INPUTS.json'))
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--source-tree', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--metadata', required=True, type=Path)
    args = parser.parse_args()
    validate_identity(args.source_commit, args.source_tree)
    need(args.output.absolute() != args.metadata.absolute(), 'OUTPUT_PATH_COLLISION')
    need(not args.output.exists() and not args.metadata.exists(), 'OUTPUT_ALREADY_EXISTS')
    archive_raw = read_regular(args.archive, ARCHIVE_SIZE)
    map_raw = read_regular(args.overlay_map, 65536)
    mapping = authenticate_map(map_raw)
    sources = {row['source']: read_regular(args.candidate_root / row['source'], row['bytes'])
               for row in mapping['files']}
    archive, metadata = compile_artifact(archive_raw, map_raw, sources,
                                         args.source_commit, args.source_tree)
    write_new(args.output, archive)
    write_new(args.metadata, canonical(metadata))
    print(json.dumps({key: value for key, value in metadata['output'].items() if key != 'files'},
                     sort_keys=True))


if __name__ == '__main__':
    main()
