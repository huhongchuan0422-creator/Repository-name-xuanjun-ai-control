#!/usr/bin/env python3
"""Offline deterministic builder using an explicit SHA-bound input map only.

No source globbing, private-plan inference, network, host admission or upload.
Input map and entry are local bootstrap tooling, not production approval.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import tarfile

from epoch7_recovery_entry import (DescriptorTree, ENTRY, MANIFEST, RUNTIME,
    MAX_TOTAL, MAX_FILES, need, sha, decode, relative, directories, validate_manifest, validate_runtime,
    PUBLIC_FIXTURE_SOURCES, MODE_STATUS, RESUME_REFUSED)

ROOT_NAME = 'epoch7-recovery-candidate-r3'
ARCHIVE = 'epoch7-recovery-kit.tar.gz'


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')


def validate_input(value):
    required = {'schema', 'files', 'modules',
         'test_suites', 'runtime_manifest_sha256', 'runtime_source_commit', 'runtime_source_tree',
         'kit_source_commit', 'kit_source_tree'}
    need(type(value) is dict and set(value) in (required, required | {'production_resume'}),
         'INPUT_MAP_SCHEMA')
    need(type(value['schema']) is int and value['schema'] == 1 and
         type(value['files']) is dict and len(value['files']) < MAX_FILES,
         'INPUT_MAP_SCOPE')
    sources = set()
    output = dict(value)
    mode = value.get('production_resume', RESUME_REFUSED)
    need(type(mode) is str and mode in MODE_STATUS, 'EXPLICIT_RESUME_MODE')
    output.update(epoch=7, status=MODE_STATUS[mode], production_resume=mode)
    output['files'] = {}
    for target, row in value['files'].items():
        relative(target)
        need(type(row) is dict and set(row) == {'source', 'sha256'}, 'INPUT_FILE_SCHEMA')
        relative(row['source'])
        need(row['source'] not in sources, 'INPUT_SOURCE_ALIAS')
        # Defense in depth. Explicit maps never authorize packing host evidence,
        # secret material, logs or compiled plans, even by naming them.
        low = row['source'].lower()
        need(not any(part in low for part in ('private', 'token', 'credential',
             'owner-evidence', 'host-evidence', 'compiled-plan', '/evidence/')),
             'PRIVATE_INPUT_FORBIDDEN')
        need('/fixtures/' not in low or (target in PUBLIC_FIXTURE_SOURCES and
             row['source'] in (PUBLIC_FIXTURE_SOURCES[target],
                 'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source/' + target)),
             'PRIVATE_INPUT_FORBIDDEN')
        need(target == ENTRY or target.startswith(('helpers/', 'tests/', RUNTIME)),
             'OUTPUT_SCOPE')
        sources.add(row['source']); output['files'][target] = row['sha256']
    return validate_manifest(output)


def archive_bytes(files):
    """Epoch5 TarInfo pattern: stable ordering, names, modes, owners and times."""
    sink = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=sink, mtime=0) as gz:
        # USTAR's prefix/name fields represent the reviewed runtime unit paths
        # without extension headers. The extractor deliberately rejects PAX.
        # An unrepresentable future path fails before any output is created.
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.USTAR_FORMAT) as tar:
            for name in [''] + sorted(directories(files) | set(files)):
                info = tarfile.TarInfo(ROOT_NAME + ('/' + name if name else ''))
                info.uid = info.gid = 0
                info.uname = info.gname = 'root'
                info.mtime = 0
                if not name or name not in files:
                    info.type = tarfile.DIRTYPE; info.mode = 0o700
                    tar.addfile(info)
                else:
                    info.mode = 0o444; info.size = len(files[name])
                    tar.addfile(info, io.BytesIO(files[name]))
    return sink.getvalue()


def _write(parent_fd, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=parent_fd)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            need(count > 0, 'OUTPUT_SHORT_WRITE')
            offset += count
        os.fchmod(fd, 0o444); os.fsync(fd)
    finally: os.close(fd)


def build(source_root, input_map, output, owners=None):
    """Explicit inputs only; source snapshots validated before creating output."""
    owners = owners or tuple(sorted(set(((0, 0), (os.geteuid(), os.getegid())))))
    manifest = validate_input(input_map)
    files, total = {}, 0
    with DescriptorTree(source_root, owners) as source:
        for target, row in sorted(input_map['files'].items()):
            raw = source.read(row['source'])
            need(sha(raw) == row['sha256'], 'SOURCE_CHANGED')
            if target.endswith('.py'): compile(raw, target, 'exec', dont_inherit=True)
            total += len(raw); need(total <= MAX_TOTAL, 'TOTAL_BOUND')
            files[target] = raw
        source.recheck()
    validate_runtime(manifest, files)
    raw_manifest = canonical(manifest)
    files[MANIFEST] = raw_manifest
    packed = archive_bytes(files)
    receipt = {'schema': 1, 'archive_sha256': sha(packed),
        'kit_manifest_sha256': sha(raw_manifest), 'entry_sha256': sha(files[ENTRY]),
        'input_map_sha256': sha(canonical(input_map)), 'files': len(files),
        'runtime_files': 107, 'runtime_manifest_sha256': manifest['runtime_manifest_sha256'],
        'runtime_source_commit': manifest['runtime_source_commit'], 'runtime_source_tree': manifest['runtime_source_tree'],
        'kit_source_commit': manifest['kit_source_commit'], 'kit_source_tree': manifest['kit_source_tree'],
        'production_execution': 'NOT_RUN', 'production_resume': manifest['production_resume'],
        'independent_review': 'PENDING', 'status': manifest['status']}
    need(type(output) is str and output.startswith('/') and
         os.path.normpath(output) == output and output != '/', 'ABSOLUTE_OUTPUT')
    parent, leaf = os.path.split(output)
    # Output is exclusive. A failed build is retained for diagnosis, never reused.
    with DescriptorTree(parent, owners) as destination:
        os.mkdir(leaf, 0o700, dir_fd=destination.fd)
        out = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                      dir_fd=destination.fd)
        fds = {None: out}
        try:
            os.mkdir(ROOT_NAME, 0o700, dir_fd=out)
            fds[''] = os.open(ROOT_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=out)
            for name in sorted(directories(files), key=lambda p: (p.count('/'), p)):
                parent_name, _, base = name.rpartition('/')
                os.mkdir(base, 0o700, dir_fd=fds[parent_name])
                fds[name] = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=fds[parent_name])
            for name, data in sorted(files.items()):
                parent_name, _, base = name.rpartition('/')
                _write(fds[parent_name], base, data)
            _write(out, ARCHIVE, packed)
            _write(out, 'kit-receipt.json', canonical(receipt))
            for fd in fds.values(): os.fsync(fd)
        finally:
            for fd in reversed(list(fds.values())): os.close(fd)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--input-map', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    path = os.path.abspath(args.input_map)
    owners = tuple(sorted(set(((0, 0), (os.geteuid(), os.getegid())))))
    with DescriptorTree(os.path.dirname(path), owners) as tree:
        raw = tree.read(os.path.basename(path)); tree.recheck()
    result = build(os.path.abspath(args.source_root), decode(raw), os.path.abspath(args.output), owners)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__': sys.exit(main())
