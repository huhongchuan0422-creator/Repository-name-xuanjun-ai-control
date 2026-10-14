"""Pure compiler for the one proposed nonsecret additive peer-pin target.

No production pins are inferred. Exact candidate/source bytes and measured
interpreter/absence metadata must be supplied and included in the new review.
No file publication backend is provided here. This is separate from retained 24.
"""
import copy
import hashlib
import json
import re

import epoch7_delta as d

PATH = '/etc/xuanjun-development/p2-owner-process-identity.json'
PARENT = '/etc/xuanjun-development'
UNIT = '/etc/systemd/system/xuanjun-uk-owner-callback.service'
CGROUP = '/system.slice/xuanjun-uk-owner-callback.service'
SCRIPT_REL = 'stage1/owner_callback_server.py'
CONFIG_KEYS = frozenset(('schema', 'callback_uid', 'release_sha256', 'python_exe',
    'python_sha256', 'script', 'script_sha256', 'unit_file', 'unit_sha256', 'argv', 'cgroup'))


def expected_argv(script):
    return ['/usr/bin/python3', script,
        '--activation-descriptor', '/var/lib/xuanjun-development/activation/active.json',
        '--activation-epoch-journal', '/var/lib/xuanjun-development/activation/epochs.jsonl',
        '--activation-lock', '/var/lib/xuanjun-development/activation/activation.lock',
        '--auth-file', '/etc/xuanjun-owner-callback/owner-callback-auth',
        '--hmac-key-file', '/etc/xuanjun-owner-callback/owner-callback-hmac',
        '--owner-id-file', '/etc/xuanjun-owner-callback/owner-user-id',
        '--owner-chat-id-file', '/etc/xuanjun-owner-callback/owner-chat-id',
        '--port', '18557', '--socket-timeout', '5', '--max-workers', '8']


def raw_sha(raw):
    d.need(isinstance(raw, bytes), 'ADDITIVE_BYTES_REQUIRED')
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw, maximum):
    d.need(isinstance(raw, bytes) and len(raw) <= maximum, 'ADDITIVE_INPUT_BOUND')
    def pairs(items):
        result = {}
        for key, value in items:
            d.need(key not in result, 'ADDITIVE_DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def reject(unused): raise ValueError('ADDITIVE_NONFINITE_JSON')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject)


def lexical_path(path):
    d.need(isinstance(path, str) and path.startswith('/') and len(path) <= 1024 and
           all(x and x not in ('.', '..') for x in path.split('/')[1:]) and
           '\x00' not in path, 'ADDITIVE_CANONICAL_PATH')


def validate_absence(absence):
    d.keys(absence, ('path', 'kind', 'parent'), 'ADDITIVE_ABSENCE_KEYS')
    d.need(absence['path'] == PATH and absence['kind'] == 'ABSENT', 'ADDITIVE_EXACT_ABSENCE_REQUIRED')
    parent = absence['parent']
    d.keys(parent, ('path', 'kind', 'uid', 'gid', 'mode', 'dev', 'ino', 'acl_sha256'),
           'ADDITIVE_PARENT_KEYS')
    for key in ('uid', 'gid', 'mode', 'dev', 'ino'):
        d.integer(parent[key], 1 if key == 'ino' else 0)
    d.hash_value(parent['acl_sha256'])
    d.need(parent['path'] == PARENT and parent['kind'] == 'DIRECTORY' and
           (parent['uid'], parent['gid'], parent['mode']) == (0, 0, 0o755),
           'ADDITIVE_PROTECTED_EXISTING_PARENT')


def compile_addition(raw, expected_sha256, manifest_raw, manifest_sha256,
                     unit_raw, interpreter, absence):
    d.hash_value(expected_sha256); d.hash_value(manifest_sha256)
    d.need(manifest_sha256 != d.OLD_MANIFEST, 'ADDITIVE_NEW_MANIFEST_REQUIRED')
    d.need(raw_sha(raw) == expected_sha256 and raw_sha(manifest_raw) == manifest_sha256,
           'ADDITIVE_EXACT_SOURCE_HASH')
    config = strict_json(raw, 65536)
    d.keys(config, CONFIG_KEYS, 'ADDITIVE_EXACT_CONFIG_SCHEMA')
    d.need(type(config['schema']) is int and config['schema'] == 1 and
           type(config['callback_uid']) is int and config['callback_uid'] == 1004,
           'ADDITIVE_CALLBACK_IDENTITY')
    d.need(config['release_sha256'] == manifest_sha256 and config['unit_file'] == UNIT and
           config['cgroup'] == CGROUP, 'ADDITIVE_RELEASE_UNIT_CGROUP')
    script = '/opt/xuanjun-control-releases/integration-' + manifest_sha256[:16] + '/' + SCRIPT_REL
    d.need(config['script'] == script, 'ADDITIVE_EXACT_SCRIPT_PATH')
    for name in ('python_sha256', 'script_sha256', 'unit_sha256'):
        d.hash_value(config[name])
    lexical_path(config['python_exe'])
    manifest = strict_json(manifest_raw, 1048576)
    d.need(isinstance(manifest, dict) and isinstance(manifest.get('files'), dict) and
           manifest['files'].get(SCRIPT_REL) == config['script_sha256'], 'ADDITIVE_SCRIPT_SOURCE_BINDING')
    d.need(isinstance(unit_raw, bytes) and len(unit_raw) <= 65536 and
           raw_sha(unit_raw) == config['unit_sha256'], 'ADDITIVE_RENDERED_UNIT_HASH')
    # Deliberately support the current literal ExecStart grammar only. No
    # specifier/environment expansion, prefixes, quoting or shell interpretation.
    lines = unit_raw.decode('utf-8').splitlines()
    section = None; critical = {}; service_sections = 0
    for line in lines:
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            section = line
            if section == '[Service]': service_sections += 1
        elif section == '[Service]' and '=' in line and not line.startswith(('#', ';')):
            key, value = line.split('=', 1)
            if key in ('User', 'Group', 'ExecStart'):
                d.need(key not in critical, 'ADDITIVE_DUPLICATE_UNIT_DIRECTIVE')
                critical[key] = value
    d.need(service_sections == 1 and critical.get('User') == 'xuanjun-callback' and
           critical.get('Group') == 'xuanjun-control-db', 'ADDITIVE_EXACT_UNIT_IDENTITY')
    commands = [critical['ExecStart']] if 'ExecStart' in critical else []
    d.need(len(commands) == 1 and re.fullmatch(r'[A-Za-z0-9_./:=@+\-]+(?: [A-Za-z0-9_./:=@+\-]+)*', commands[0]),
           'ADDITIVE_LITERAL_EXECSTART_REQUIRED')
    argv = config['argv']
    d.need(isinstance(argv, list) and 2 <= len(argv) <= 64 and
           all(isinstance(x, str) and 0 < len(x) <= 1024 for x in argv) and
           argv == commands[0].split(' ') and argv == expected_argv(script),
           'ADDITIVE_EXACT_ARGV_BINDING')
    d.keys(interpreter, ('path', 'kind', 'sha256', 'uid', 'gid', 'mode', 'dev', 'ino', 'nlink'),
           'ADDITIVE_INTERPRETER_OBSERVATION_KEYS')
    lexical_path(interpreter['path'])
    for key in ('uid', 'gid', 'mode', 'dev', 'ino', 'nlink'):
        d.integer(interpreter[key], 1 if key in ('ino', 'nlink') else 0)
    d.need(interpreter['kind'] == 'FILE' and interpreter['path'] == config['python_exe'] and
           interpreter['sha256'] == config['python_sha256'] and interpreter['uid'] == 0 and
           not interpreter['mode'] & 0o022 and interpreter['mode'] & 0o111,
           'ADDITIVE_MEASURED_INTERPRETER_BINDING')
    validate_absence(absence)
    return {'schema': 1, 'kind': 'OFFLINE_ADDITIVE_IDENTITY_NOT_INSTALL_PLAN',
        'purpose': 'OWNER_PROCESS_IDENTITY_PINS', 'path': PATH,
        'operation': 'CREATE_EXCLUSIVE_PROTECTED_FILE', 'before': copy.deepcopy(absence),
        'after': {'kind': 'FILE', 'uid': 0, 'gid': 0, 'mode': 0o644, 'sha256': expected_sha256},
        'provenance': {'runtime_manifest_sha256': manifest_sha256,
            'callback_script_sha256': config['script_sha256'],
            'rendered_unit_sha256': config['unit_sha256'],
            'interpreter_observation_sha256': d.digest(interpreter),
            'config_schema': 1},
        'actual_host_pins_verified': False, 'permission_applied': False,
        'requires_complete_new_review': True, 'install_admission': 'NOT_GRANTED'}


def validate_compiled(addition, manifest_sha256):
    """Structural binding only; compile_addition must check actual source bytes."""
    d.keys(addition, ('schema', 'kind', 'purpose', 'path', 'operation', 'before', 'after',
        'provenance', 'actual_host_pins_verified', 'permission_applied',
        'requires_complete_new_review', 'install_admission'), 'ADDITIVE_COMPILED_SCHEMA')
    d.need(type(addition['schema']) is int and addition['schema'] == 1 and
           addition['kind'] == 'OFFLINE_ADDITIVE_IDENTITY_NOT_INSTALL_PLAN' and
           addition['purpose'] == 'OWNER_PROCESS_IDENTITY_PINS' and addition['path'] == PATH and
           addition['operation'] == 'CREATE_EXCLUSIVE_PROTECTED_FILE' and
           addition['permission_applied'] is False and addition['actual_host_pins_verified'] is False and
           addition['requires_complete_new_review'] is True and addition['install_admission'] == 'NOT_GRANTED',
           'ADDITIVE_COMPILED_SCOPE')
    d.validate_file(addition['after'], observed=False)
    d.need((addition['after']['uid'], addition['after']['gid'], addition['after']['mode']) == (0, 0, 0o644),
           'ADDITIVE_EXACT_METADATA')
    d.keys(addition['provenance'], ('runtime_manifest_sha256', 'callback_script_sha256',
        'rendered_unit_sha256', 'interpreter_observation_sha256', 'config_schema'), 'ADDITIVE_PROVENANCE')
    for key in set(addition['provenance']) - {'config_schema'}:
        d.hash_value(addition['provenance'][key])
    d.need(addition['provenance']['runtime_manifest_sha256'] == manifest_sha256 and
           type(addition['provenance']['config_schema']) is int and addition['provenance']['config_schema'] == 1,
           'ADDITIVE_MANIFEST_BINDING')
    validate_absence(addition['before'])
    return copy.deepcopy(addition)
