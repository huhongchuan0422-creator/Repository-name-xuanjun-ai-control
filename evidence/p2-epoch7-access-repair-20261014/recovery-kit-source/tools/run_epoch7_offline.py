#!/usr/bin/env python3
"""Unprivileged hosted-CI unit runner. No observation, probe or resume operation.

This runner and interpreter are trusted CI bootstrap. Authenticate the entry
before executing it, then verify every kit byte under root/current-UID ownership.
All required portable suites run; absent/disabled suites or imports fail closed.
"""
import argparse
import errno
import hashlib
import importlib
import json
import os
import re
import stat
import sys
import types

PORTABLE_SUITES = ('access_plan', 'approval', 'command', 'diagnostics', 'recovery',
                  'sequence', 'host_containment', 'live_controls', 'runtime_acceptance',
                  'runtime_projection', 'runtime_process', 'runtime_identity', 'runtime_wiring',
                  'acceptance_rows', 'snapshot_portable', 'host_factory', 'probe', 'service_contract',
                  'host_filesystem', 'host_observer', 'recovery_filesystem', 'resource_plan',
                  'host_stager', 'runtime_effects')
REQUIRED_HELPERS = ('epoch7_approval', 'epoch7_complete_approval', 'epoch7_command_runner',
    'protected_command_evidence', 'epoch7_delta', 'epoch7_injected_recovery',
    'epoch7_recovery_sequence', 'epoch7_live_controls', 'epoch7_snapshot', 'snapshot_io',
    'probe_metadata', 'observe_epoch7', 'epoch7_host_driver', 'epoch7_host_factory',
    'epoch7_host_observer', 'epoch7_resource_observer', 'epoch7_pre_active_guards',
    'epoch7_timer_tail', 'epoch7_resource_plan', 'epoch7_quiet_startup',
    'epoch7_runtime_effects', 'epoch7_runtime_acceptance', 'epoch7_bindings',
    'probe_driver', 'probe_helpers', 'node_sqlite_probe', 'unit_metadata', 'openclaw_metadata', 'epoch7_acceptance_rows',
    'epoch7_service_roles', 'epoch7_service_contract', 'epoch7_unit_transitions', 'epoch7_nginx_recipe',
    'epoch7_openclaw_recipe')


def need(value, label):
    if not value: raise ValueError('EPOCH7_OFFLINE_' + label)


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def bootstrap_entry(path, owners):
    """No-follow descriptor-bound read before importing any entry code."""
    need(type(path) is str and path.startswith('/') and os.path.normpath(path) == path,
         'ABSOLUTE_ENTRY')
    held = []
    def authority(fd, directory):
        info = os.fstat(fd)
        need((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) and
             (info.st_uid, info.st_gid) in owners and not info.st_mode & 0o7022, 'BOOTSTRAP_AUTHORITY')
        if not directory: need(info.st_nlink == 1 and info.st_size <= 1048576, 'ENTRY_BOUND')
        for key in ('system.posix_acl_access', 'system.posix_acl_default'):
            try: os.getxattr(fd, key)
            except OSError as error: need(error.errno in (errno.ENODATA, errno.ENOTSUP), 'ACL_READ')
            else: need(False, 'UNREVIEWED_ACL')
        return info
    try:
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        held.append([fd, None, None, None]); held[-1][3] = stamp(authority(fd, True))
        pieces = path[1:].split('/')
        for name in pieces[:-1]:
            parent = fd
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            held.append([fd, parent, name, None]); held[-1][3] = stamp(authority(fd, True))
            need(stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == held[-1][3], 'OPEN_RACE')
        parent = fd; leaf = pieces[-1]
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = stamp(authority(fd, False))
            with os.fdopen(os.dup(fd), 'rb') as stream: raw = stream.read(1048577)
            need(before == stamp(authority(fd, False)) ==
                 stamp(os.stat(leaf, dir_fd=parent, follow_symlinks=False)) and
                 len(raw) == before[6], 'ENTRY_READ_RACE')
        finally: os.close(fd)
        for fd, parent, name, before in held:
            need(before == stamp(authority(fd, True)), 'ANCESTRY_RACE')
            if parent is not None:
                need(before == stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'BINDING_RACE')
        return raw
    finally:
        for row in reversed(held): os.close(row[0])


def run(kit_root, entry_sha256, manifest_sha256, kit_source_commit, kit_source_tree):
    need(os.geteuid() != 0 and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and not sys.flags.optimize,
         'UNPRIVILEGED_ISOLATED_NO_SITE_NO_BYTECODE_REQUIRED')
    for value in (entry_sha256, manifest_sha256):
        need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value), 'EXACT_HASH_REQUIRED')
    for value in (kit_source_commit, kit_source_tree):
        need(type(value) is str and re.fullmatch(r'[0-9a-f]{40}', value), 'EXACT_SOURCE_REQUIRED')
    need(type(kit_root) is str and kit_root.startswith('/') and os.path.normpath(kit_root) == kit_root,
         'ABSOLUTE_KIT_ROOT')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    owners = tuple(sorted(set(((0, 0), (os.geteuid(), os.getegid())))))
    entry_path = kit_root + '/epoch7_recovery_entry.py'
    raw = bootstrap_entry(entry_path, owners)
    need(hashlib.sha256(raw).hexdigest() == entry_sha256, 'ENTRY_HASH')
    entry = types.ModuleType('_epoch7_offline_authenticated_entry')
    entry.__file__ = entry_path
    exec(compile(raw, entry_path, 'exec', dont_inherit=True), entry.__dict__)
    kit = entry._verify(kit_root, manifest_sha256, owners)
    need(kit.manifest['kit_source_commit'] == kit_source_commit and
         kit.manifest['kit_source_tree'] == kit_source_tree, 'KIT_SOURCE_BINDING')
    enabled = {name for name, row in kit.manifest['test_suites'].items() if row['enabled']}
    need(enabled == set(PORTABLE_SUITES), 'EXACT_PORTABLE_SUITE_SET')
    need(set(REQUIRED_HELPERS) <= set(kit.manifest['modules']), 'REQUIRED_HELPERS_MISSING')
    # Fixed pure-import closure. Factories/collectors are imported, never called.
    # This catches a missing or misspelled transitive helper before reporting tests.
    with kit.imports():
        for name in REQUIRED_HELPERS: importlib.import_module(name)
    result = kit.tests(list(PORTABLE_SUITES))
    complete = all(row['tests'] > 0 and row['skipped'] == 0 for row in result['suites'])
    result['portable_tests_complete'] = complete
    result['success'] = result['success'] and complete
    result.update(kind='HOSTED_OFFLINE_UNIT_EVIDENCE_ONLY', python_version=sys.version.split()[0],
        runner_uid=os.geteuid(), entry_sha256=entry_sha256,
        kit_source_commit=kit_source_commit, kit_source_tree=kit_source_tree,
        runtime_source_commit=kit.manifest['runtime_source_commit'],
        runtime_source_tree=kit.manifest['runtime_source_tree'],
        runtime_manifest_sha256=kit.manifest['runtime_manifest_sha256'],
        host_observation='NOT_RUN', isolated_probe='NOT_RUN', production_execution='NOT_RUN',
        production_acceptance='NOT_VERIFIED', unavailable_suites={name: row['reason']
            for name, row in kit.manifest['test_suites'].items() if not row['enabled']})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('kit-root', 'entry-sha256', 'kit-manifest-sha256', 'kit-source-commit', 'kit-source-tree'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    result = run(args.kit_root, args.entry_sha256, args.kit_manifest_sha256,
                 args.kit_source_commit, args.kit_source_tree)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['success'] else 1


if __name__ == '__main__': sys.exit(main())
