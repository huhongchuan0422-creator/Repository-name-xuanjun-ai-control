#!/usr/bin/env python3
"""Hosted offline source-index verification, reproducible build and unit gate.

Trust: this checked-out script, /usr/bin/git and isolated Python/stdlib. All
published sources, including runtime files, must match actual HEAD Git blobs.
No package installation, upload, host observation, probe or resume operation.
"""
import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import types

PREFIX = 'evidence/p2-epoch7-access-repair-20261014/recovery-kit-source'
RUNTIME = 'evidence/p2-epoch7-access-repair-20261014/runtime'
RUNTIME_COMMIT = '101b465ca3554bf34fef2d53d6006b96d85c4a63'
RUNTIME_TREE = '3ae50b40c38d9a807876c175818299e344d53134'
RUNTIME_MANIFEST = '26ae77d8fff38c8a69ddcf3e35caeb18d4724ab17eca8fbecf9dc4f76bc797aa'
MAX_FILE = 16 * 1024 * 1024
REQUIRED_TOOLS = frozenset(('build_epoch7_kit.py', 'extract_epoch7_kit.py',
    'run_epoch7_offline.py', 'audit_epoch7_imports.py', 'run_published_kit_ci.py', 'test_epoch7_kit.py'))
DEADLINE = None
PHASE = 'ARGUMENTS'
LAST_CHILD_CLEANUP = 'NOT_STARTED'


def remaining(maximum):
    value = maximum if DEADLINE is None else min(maximum, DEADLINE - time.monotonic())
    need(value > 0, 'OVERALL_TIME_BOUND')
    return value


def need(value, code):
    if not value: raise ValueError('EPOCH7_PUBLISHED_CI_' + code)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')


def decode(raw):
    def pairs(items):
        result = {}
        for name, value in items:
            need(name not in result, 'DUPLICATE_JSON_KEY'); result[name] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: need(False, 'NONFINITE_JSON'))


def relative(value):
    need(type(value) is str and 0 < len(value) <= 512 and
         re.fullmatch(r'[A-Za-z0-9_.\-/]+', value) and all(part not in ('', '.', '..', '__pycache__') and
         not part.endswith(('.pyc', '.pyo')) for part in value.split('/')), 'RELATIVE_PATH')
    return value


def bounded_child(command, cwd, env, stdout, stderr, timeout, stdout_limit, stderr_limit):
    """Finite regular-file capture; unreaped leader pins our process group.

    No PIPE/communicate or unbounded wait. Even a normally exited leader remains
    unreaped until its still-owned group has been stopped. Unknown ownership or
    reap outcome fails CI; it never becomes a successful command result.
    """
    global LAST_CHILD_CLEANUP
    process = None
    cleanup_ok = True
    primary = None
    cleanup_error = None
    code = None
    deadline = time.monotonic() + timeout
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
            stdin=subprocess.DEVNULL, close_fds=True, start_new_session=True)
        while True:
            need(os.fstat(stdout.fileno()).st_size <= stdout_limit and
                 os.fstat(stderr.fileno()).st_size <= stderr_limit, 'COMMAND_OUTPUT_BOUND')
            status = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if status is not None: break
            need(time.monotonic() < deadline, 'COMMAND_TIME_BOUND')
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
    except BaseException as error:
        primary = error
    finally:
        if process is not None:
            LAST_CHILD_CLEANUP = 'UNKNOWN'
            try:
                # ECHILD means ownership was lost; never use a reused PID/PGID.
                os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                owned = os.getpgid(process.pid) == process.pid and os.getsid(process.pid) == process.pid
                if owned: os.killpg(process.pid, signal.SIGKILL)
                else: cleanup_ok = False
            except BaseException as error:
                cleanup_ok = False; cleanup_error = error
            try: code = process.wait(timeout=2)
            except BaseException as error:
                cleanup_ok = False
                if cleanup_error is None: cleanup_error = error
            if cleanup_ok: LAST_CHILD_CLEANUP = 'OWNED_GROUP_SIGNALLED_LEADER_REAPED'
    if primary is not None: raise primary
    if cleanup_error is not None: raise cleanup_error
    need(cleanup_ok and type(code) is int, 'COMMAND_CLEANUP_UNKNOWN')
    need(os.fstat(stdout.fileno()).st_size <= stdout_limit and
         os.fstat(stderr.fileno()).st_size <= stderr_limit, 'COMMAND_OUTPUT_BOUND')
    return code


def git(repo, arguments, maximum=MAX_FILE):
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'HOME': '/nonexistent',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'}
    command = ['/usr/bin/git', '--no-pager', '-c', 'core.fsmonitor=false',
        '-c', 'core.hooksPath=/dev/null', '-c', 'credential.helper='] + list(arguments)
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        code = bounded_child(command, repo, env, output, error, remaining(15), maximum, 65536)
        need(code == 0, 'LOCAL_GIT_READ_FAILED')
        output.seek(0); raw = output.read(maximum + 1)
        need(len(raw) <= maximum, 'LOCAL_GIT_OUTPUT_BOUND')
        return raw


def git_blob(repo, head, path, maximum=MAX_FILE):
    relative(path)
    spec = head + ':' + path
    size_raw = git(repo, ['cat-file', '-s', spec], 32)
    need(re.fullmatch(rb'[0-9]+\n', size_raw) is not None and int(size_raw) <= maximum, 'GIT_BLOB_BOUND')
    raw = git(repo, ['cat-file', 'blob', spec], maximum)
    need(len(raw) == int(size_raw), 'GIT_BLOB_SIZE')
    return raw


def validate_index(index):
    need(type(index) is dict and set(index) == {'schema', 'kind', 'files', 'tools', 'modules',
         'test_suites', 'production_resume', 'runtime_source_commit', 'runtime_source_tree',
         'runtime_manifest_sha256'}, 'INDEX_SCHEMA')
    need(type(index['schema']) is int and index['schema'] == 1 and
         index['kind'] == 'EPOCH7_EXPLICIT_PUBLIC_SOURCE_INDEX' and
         index['runtime_source_commit'] == RUNTIME_COMMIT and index['runtime_source_tree'] == RUNTIME_TREE and
         index['runtime_manifest_sha256'] == RUNTIME_MANIFEST, 'FIXED_RUNTIME_PROVENANCE')
    need(type(index['files']) is dict and 1 <= len(index['files']) <= 512 and
         'epoch7_recovery_entry.py' in index['files'] and type(index['tools']) is dict and
         REQUIRED_TOOLS <= set(index['tools']) and len(index['tools']) <= 32, 'INDEX_FILE_SCOPE')
    seen = set()
    for kind in ('files', 'tools'):
        for target, row in index[kind].items():
            relative(target)
            need(type(row) is dict and set(row) == {'source', 'sha256'} and
                 type(row['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}', row['sha256']), 'INDEX_ROW')
            relative(row['source'])
            expected = PREFIX + ('/tools/' if kind == 'tools' else '/') + target
            need(row['source'] == expected and row['source'] not in seen, 'INDEX_EXACT_PUBLISHED_PATH')
            need(kind == 'tools' or target == 'epoch7_recovery_entry.py' or target.startswith(('helpers/', 'tests/')),
                 'INDEX_PUBLIC_KIT_SCOPE')
            seen.add(row['source'])
    return index


def load_module(name, raw, path):
    need(name not in sys.modules, 'PRELOADED_BOOTSTRAP')
    module = types.ModuleType(name); module.__file__ = path
    sys.modules[name] = module
    exec(compile(raw, path, 'exec', dont_inherit=True), module.__dict__)
    return module


def write_exclusive(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); need(count > 0, 'SHORT_WRITE'); offset += count
        os.fsync(fd)
    finally: os.close(fd)


BOOTSTRAP_LAUNCHER = r'''
import hashlib, importlib, json, os, sys, types, unittest
root, wanted = sys.argv[1:]
def read(name, expected):
    fd=os.open(root+'/'+name,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        with os.fdopen(fd,'rb') as stream: raw=stream.read(16777217)
    except BaseException: raise
    if len(raw)>16777216 or hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('BOOTSTRAP_SOURCE_CHANGED')
    return raw
manifest=read('bootstrap-source-map.json',wanted)
pins=json.loads(manifest.decode('ascii'))
cache={name:read(name,digest) for name,digest in pins.items()}
entry=types.ModuleType('epoch7_recovery_entry');entry.__file__=root+'/epoch7_recovery_entry.py'
sys.modules[entry.__name__]=entry
exec(compile(cache['epoch7_recovery_entry.py'],entry.__file__,'exec',dont_inherit=True),entry.__dict__)
modules={name[:-3]:name for name in cache if name.endswith('.py') and '/' not in name}
finder=entry.CachedSources(root,cache,modules,entry.BOOTSTRAP_PATH)
sys.meta_path.insert(0,finder)
try:
    tests=unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module('test_epoch7_kit'))
    result=unittest.TextTestRunner(verbosity=2).run(tests)
finally:sys.meta_path.remove(finder)
success=result.wasSuccessful() and result.testsRun>0 and not result.skipped
print(json.dumps({'kind':'EXACT_PUBLISHED_BOOTSTRAP_UNIT_EVIDENCE_ONLY','tests':result.testsRun,
    'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
    'success':success,'source_map_sha256':wanted,'python_version':sys.version.split()[0],
    'runner_uid':os.geteuid(),'host_operations':'NOT_RUN'},sort_keys=True))
sys.exit(0 if success else 1)
'''


def run_bootstrap_tests(entry, output, cache, tools, entry_raw, owners):
    """Exact published tool bytes in a verified disposable fixture directory."""
    root = output + '/bootstrap-tools'
    os.mkdir(root, 0o700)
    files = {name: cache[row['source']] for name, row in tools.items()}
    files['epoch7_recovery_entry.py'] = entry_raw
    for name in sorted(entry.directories(files), key=lambda path: (path.count('/'), path)):
        os.mkdir(root + '/' + name, 0o700)
    for name, data in sorted(files.items()): write_exclusive(root + '/' + name, data)
    pins = {name: sha(data) for name, data in files.items()}
    raw_pins = canonical(pins)
    files['bootstrap-source-map.json'] = raw_pins
    write_exclusive(root + '/bootstrap-source-map.json', raw_pins)
    def verify():
        with entry.DescriptorTree(root, owners) as source:
            need(source.inventory() == (set(files), entry.directories(files)), 'BOOTSTRAP_TEST_INVENTORY')
            for name, data in files.items(): need(source.read(name) == data, 'BOOTSTRAP_TEST_SOURCE_CHANGED')
            source.recheck()
    verify()
    path = output + '/bootstrap-tests.log'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            code = bounded_child([sys.executable, '-I', '-B', '-S', '-c', BOOTSTRAP_LAUNCHER, root, sha(raw_pins)],
                output, dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), stream, stream, remaining(120), MAX_FILE, MAX_FILE)
            stream.flush(); os.fsync(stream.fileno())
    finally: verify()
    with entry.DescriptorTree(output, owners) as logs:
        raw_log = logs.read('bootstrap-tests.log'); logs.recheck()
    try: report = decode(raw_log.rstrip().split(b'\n')[-1])
    except Exception: report = None
    need(type(report) is dict and report.get('kind') == 'EXACT_PUBLISHED_BOOTSTRAP_UNIT_EVIDENCE_ONLY' and
         report.get('source_map_sha256') == sha(raw_pins), 'BOOTSTRAP_TEST_TERMINAL')
    report['success'] = (code == 0 and report.get('success') is True and type(report.get('tests')) is int and
        report['tests'] > 0 and all(type(report.get(name)) is int and report[name] == 0
                                  for name in ('failures', 'errors', 'skipped')))
    report.update(log_sha256=sha(raw_log), exit_code=code, source_sha256=pins)
    return report


def generate(repo, index_path, runtime_path, output, expected_head):
    global DEADLINE, PHASE
    DEADLINE = time.monotonic() + 540
    PHASE = 'SOURCE_INDEX'
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and
         not sys.flags.optimize and os.geteuid() != 0, 'UNPRIVILEGED_ISOLATED_FLAGS')
    need(os.path.isabs(repo) and os.path.realpath(repo) == repo and
         index_path == PREFIX + '/public-source-index.json' and runtime_path == RUNTIME,
         'EXACT_CHECKOUT_PATHS')
    need(type(expected_head) is str and re.fullmatch(r'[0-9a-f]{40}', expected_head), 'EXPECTED_HEAD')
    head = git(repo, ['rev-parse', '--verify', 'HEAD'], 64).decode('ascii').strip()
    tree = git(repo, ['rev-parse', '--verify', 'HEAD^{tree}'], 64).decode('ascii').strip()
    need(head == expected_head and re.fullmatch(r'[0-9a-f]{40}', tree), 'HEAD_OR_TREE_CHANGED')
    raw_index = git_blob(repo, head, index_path, 4 * 1024 * 1024)
    index = validate_index(decode(raw_index))
    # The entry is executed from the exact indexed HEAD blob, never from a
    # mutable import path. It supplies the already-tested protected reader.
    row = index['files']['epoch7_recovery_entry.py']
    entry_raw = git_blob(repo, head, row['source'])
    need(sha(entry_raw) == row['sha256'], 'ENTRY_GIT_SHA')
    entry = load_module('epoch7_recovery_entry', entry_raw, repo + '/' + row['source'])
    owners = tuple(sorted(set(((0, 0), (os.geteuid(), os.getegid())))))
    cache = {}
    PHASE = 'PUBLIC_GIT_BYTES'
    with entry.DescriptorTree(repo, owners) as source:
        need(source.read(index_path) == raw_index, 'INDEX_WORKTREE_CHANGED')
        for rows in (index['files'], index['tools']):
            for target, row in sorted(rows.items()):
                raw = source.read(row['source'])
                need(sha(raw) == row['sha256'] and raw == git_blob(repo, head, row['source']),
                     'PUBLIC_FILE_GIT_MISMATCH')
                cache[row['source']] = raw
        PHASE = 'RUNTIME_GIT_BYTES'
        runtime_raw = source.read(runtime_path + '/deploy/integration-manifest.json')
        need(sha(runtime_raw) == RUNTIME_MANIFEST, 'RUNTIME_MANIFEST')
        manifest = decode(runtime_raw)
        need(type(manifest.get('files')) is dict and len(manifest['files']) == 107, 'RUNTIME107')
        runtime_names = set(manifest['files']) | {'deploy/integration-manifest.json',
            'P2_PACKAGE_PROVENANCE.json', 'tools/p2-package-freeze.py'}
        runtime_rows = {}
        for name in sorted(runtime_names):
            relative(name); path = runtime_path + '/' + name; raw = source.read(path)
            need(raw == git_blob(repo, head, path), 'RUNTIME_GIT_MISMATCH')
            runtime_rows['xuanjun-p2-package/' + name] = {'source': path, 'sha256': sha(raw)}
        source.recheck()
    with entry.DescriptorTree(repo + '/' + runtime_path, owners) as runtime:
        need(runtime.inventory() == (runtime_names, entry.directories(runtime_names)), 'RUNTIME_EXACT_INVENTORY')
        runtime.recheck()
    tools = index['tools']
    builder = load_module('build_epoch7_kit', cache[tools['build_epoch7_kit.py']['source']],
                          repo + '/' + tools['build_epoch7_kit.py']['source'])
    auditor = load_module('audit_epoch7_imports', cache[tools['audit_epoch7_imports.py']['source']],
                          repo + '/' + tools['audit_epoch7_imports.py']['source'])
    value = {key: index[key] for key in ('modules', 'test_suites', 'production_resume',
        'runtime_source_commit', 'runtime_source_tree', 'runtime_manifest_sha256')}
    value.update(schema=1, files=dict(index['files'], **runtime_rows), kit_source_commit=head, kit_source_tree=tree)
    PHASE = 'IMPORT_CLOSURE'
    builder.validate_input(value)
    closure = auditor.audit(repo, value); need(closure['success'], 'REQUIRED_IMPORT_CLOSURE')
    parent = os.environ.get('RUNNER_TEMP')
    need(type(parent) is str and os.path.isabs(output) and os.path.normpath(output) == output and
         os.path.dirname(output) == os.path.normpath(parent), 'RUNNER_TEMP_OUTPUT_REQUIRED')
    with entry.DescriptorTree(parent, owners) as destination:
        os.mkdir(os.path.basename(output), 0o700, dir_fd=destination.fd)
    write_exclusive(output + '/generated-input-map.json', canonical(value))
    write_exclusive(output + '/import-closure.json', canonical(closure))
    PHASE = 'BOOTSTRAP_TESTS'
    bootstrap = run_bootstrap_tests(entry, output, cache, tools, entry_raw, owners)
    PHASE = 'BUILD_A'
    first = builder.build(repo, value, output + '/build-a', owners)
    PHASE = 'BUILD_B'
    second = builder.build(repo, value, output + '/build-b', owners)
    with entry.DescriptorTree(output, owners) as products:
        archive = products.read('build-a/' + builder.ARCHIVE)
        need(first == second and archive == products.read('build-b/' + builder.ARCHIVE),
             'REPRODUCIBLE_BUILD_MISMATCH')
        products.recheck()
    PHASE = 'ARCHIVE_ROUNDTRIP'
    extractor = load_module('extract_epoch7_kit', cache[tools['extract_epoch7_kit.py']['source']],
                            repo + '/' + tools['extract_epoch7_kit.py']['source'])
    os.mkdir(output + '/verified-extract', 0o700)
    extracted_root = output + '/verified-extract/' + builder.ROOT_NAME
    extractor.extract(archive, extracted_root, first['archive_sha256'], first['entry_sha256'],
                      first['kit_manifest_sha256'], owners=owners)
    need(git(repo, ['rev-parse', '--verify', 'HEAD'], 64).decode('ascii').strip() == head, 'HEAD_CHANGED')
    runner = output + '/run_epoch7_offline.py'
    write_exclusive(runner, cache[tools['run_epoch7_offline.py']['source']])
    command = [sys.executable, '-I', '-B', '-S', runner, '--kit-root', extracted_root,
        '--entry-sha256', first['entry_sha256'], '--kit-manifest-sha256', first['kit_manifest_sha256'],
        '--kit-source-commit', head, '--kit-source-tree', tree]
    log_path = output + '/mandatory-tests.log'
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    PHASE = 'MANDATORY_TESTS'
    with os.fdopen(fd, 'wb') as log_stream:
        code = bounded_child(command, output, env, log_stream, log_stream, remaining(480), MAX_FILE, MAX_FILE)
        log_stream.flush(); os.fsync(log_stream.fileno())
    with entry.DescriptorTree(output, owners) as products:
        log = products.read('mandatory-tests.log'); products.recheck()
    report = {'kind': 'EXACT_PUBLISHED_OFFLINE_KIT_CI', 'kit_source_commit': head, 'kit_source_tree': tree,
        'runtime_source_commit': RUNTIME_COMMIT, 'runtime_source_tree': RUNTIME_TREE,
        'runtime_manifest_sha256': RUNTIME_MANIFEST, 'source_index_sha256': sha(raw_index),
        'archive_sha256': first['archive_sha256'], 'kit_manifest_sha256': first['kit_manifest_sha256'],
        'entry_sha256': first['entry_sha256'], 'mandatory_test_log_sha256': sha(log),
        'reproducible_build': True, 'verified_archive_roundtrip': True,
        'required_import_closure': True, 'test_exit_code': code,
        'host_operations': 'NOT_RUN', 'production_acceptance': 'NOT_VERIFIED',
        'bootstrap_tests': bootstrap, 'success': code == 0 and bootstrap['success'] is True}
    # The authenticated runner's terminal JSON supplies exact test/skip counts.
    PHASE = 'TEST_TERMINAL'
    try: terminal = decode(log.rstrip().split(b'\n')[-1])
    except Exception: terminal = None
    need(type(terminal) is dict and terminal.get('kind') == 'HOSTED_OFFLINE_UNIT_EVIDENCE_ONLY', 'RUNNER_TERMINAL')
    expected = {'kit_source_commit': head, 'kit_source_tree': tree,
        'kit_manifest_sha256': first['kit_manifest_sha256'], 'entry_sha256': first['entry_sha256'],
        'runtime_source_commit': RUNTIME_COMMIT, 'runtime_source_tree': RUNTIME_TREE,
        'runtime_manifest_sha256': RUNTIME_MANIFEST}
    need(all(terminal.get(name) == value for name, value in expected.items()), 'RUNNER_TERMINAL_BINDING')
    rows = terminal.get('suites')
    enabled = {name for name, row in index['test_suites'].items() if row['enabled']}
    need(type(rows) is list and len(rows) == len(enabled) and
         all(type(row) is dict for row in rows) and {row.get('suite') for row in rows} == enabled,
         'RUNNER_TERMINAL_SUITE_SET')
    complete = all(type(row.get('tests')) is int and row['tests'] > 0 and
        type(row.get('skipped')) is int and row['skipped'] == 0 and row.get('success') is True for row in rows)
    report['success'] = bool(report['success'] and complete and terminal.get('success') is True and
                             terminal.get('portable_tests_complete') is True)
    report['tests'] = terminal
    write_exclusive(output + '/ci-summary.json', canonical(report))
    return report


def failure_report(error):
    name = type(error).__name__
    if name not in ('ValueError', 'OSError', 'FileNotFoundError', 'PermissionError',
                    'TimeoutExpired', 'UnicodeDecodeError', 'SyntaxError', 'KeyError', 'TypeError'):
        name = 'Exception'
    code = None
    if isinstance(error, ValueError) and len(error.args) == 1 and type(error.args[0]) is str and re.fullmatch(
            r'EPOCH7_(?:PUBLISHED_CI|KIT|EXTRACT)_[A-Z0-9_]{1,128}', error.args[0]): code = error.args[0]
    return {'kind': 'EXACT_PUBLISHED_OFFLINE_KIT_CI', 'success': False, 'phase': PHASE,
        'error_class': name, 'error_code': code, 'child_cleanup': LAST_CHILD_CLEANUP,
        'reason': 'SOURCE_BUILD_OR_TEST_GATE_FAILED', 'host_operations': 'NOT_RUN'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository', 'source-index', 'runtime-dir', 'output', 'expected-head'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    report = generate(os.path.abspath(args.repository), args.source_index, args.runtime_dir,
                      os.path.abspath(args.output), args.expected_head)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as error:
        print(json.dumps(failure_report(error), sort_keys=True))
        sys.exit(2)
