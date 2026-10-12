#!/usr/bin/python3
"""Python 3.6 read-only UK consumer metadata; never emit credentials."""
import json
import os
import socket
import stat
import subprocess
import sys

BASE = '/home/xuanjun_dev'
ROOTS = (BASE, '/root', '/var/lib/xuanjun-development')


def safe_path(value):
    if not isinstance(value, str) or not value.startswith('/'):
        return None
    if any(ord(c) < 32 for c in value) or len(value) > 1024:
        return None
    path = os.path.normpath(value)
    return path if any(path == r or path.startswith(r + '/') for r in ROOTS) else None


def metadata(path):
    value = {'path': path}
    try:
        s = os.lstat(path)
        value.update(present=True, uid=s.st_uid, gid=s.st_gid,
                     mode=oct(stat.S_IMODE(s.st_mode)),
                     regular=stat.S_ISREG(s.st_mode), symlink=stat.S_ISLNK(s.st_mode))
    except OSError:
        value['present'] = False
    return value


def audit():
    if os.geteuid() != 0 or socket.gethostname().split('.')[0] != 'iZd7oeikknn1z21sq6ji6zZ':
        raise SystemExit('STOP_FIXED_UK_ROOT_AUDIT')
    result = {'scope': 'READ_ONLY_METADATA_NO_MODEL_NO_INSTALL',
              'python_version': list(sys.version_info[:3]), 'consumers': [], 'units': {}}
    for unit in ('xuanjun-uk-openclaw.service', 'xuanjun-uk-stage1-minimal.service',
                 'xuanjun-development-dispatcher.service', 'xuanjun-github-intake.timer'):
        p = subprocess.run(['/usr/bin/systemctl', 'show', unit,
                            '--property=User,Group,MainPID,ActiveState,WorkingDirectory'],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=8, check=False)
        fields = {}
        for line in p.stdout.decode('utf-8', 'replace').splitlines():
            k, _, v = line.partition('=')
            if k in ('User', 'Group', 'ActiveState') and len(v) <= 80:
                fields[k] = v
            elif k == 'MainPID' and v.isdigit():
                fields[k] = int(v)
            elif k == 'WorkingDirectory':
                fields[k] = safe_path(v) or 'OUTSIDE_ALLOWED_ROOTS'
        result['units'][unit] = fields
    for pid in sorted(os.listdir('/proc')):
        if not pid.isdigit():
            continue
        proc = '/proc/' + pid
        try:
            with open(proc + '/comm') as f:
                name = f.read(64).strip()
            if name not in ('codex', 'openclaw', 'node'):
                continue
            with open(proc + '/cgroup') as f:
                group = f.read(8192)
            if '/xuanjun-uk-openclaw.service' not in group and '/xuanjun-development-dispatcher.service' not in group:
                continue
            row = {'pid': int(pid), 'name': name, 'paths': {}, 'auth_metadata': []}
            for attr in ('cwd', 'exe'):
                try:
                    row['paths'][attr] = safe_path(os.readlink(proc + '/' + attr)) or 'OUTSIDE_ALLOWED_ROOTS'
                except OSError:
                    row['paths'][attr] = 'UNAVAILABLE'
            # Filter at byte-key level. Never decode/emit tokens or other environment values.
            with open(proc + '/environ', 'rb') as f:
                environment = f.read(262145)
            if len(environment) > 262144:
                row['environment_metadata'] = 'OVERSIZE'
            else:
                for item in environment.split(b'\0'):
                    k, _, v = item.partition(b'=')
                    if k in (b'HOME', b'CODEX_HOME', b'OPENCLAW_STATE_DIR', b'OPENCLAW_CONFIG_PATH', b'XDG_CONFIG_HOME'):
                        path = safe_path(v.decode('utf-8', 'replace'))
                        if path:
                            row['paths'][k.decode('ascii')] = path
            codex_home = row['paths'].get('CODEX_HOME')
            if not codex_home and row['paths'].get('HOME'):
                codex_home = row['paths']['HOME'] + '/.codex'
                row['codex_home_source'] = 'DEFAULT_HOME_CONVENTION_NOT_EXPLICIT_BINDING'
            else:
                row['codex_home_source'] = 'OBSERVED_PROCESS_ENVIRONMENT' if codex_home else 'UNKNOWN'
            if codex_home:
                row['auth_metadata'].append(metadata(codex_home + '/auth.json'))
            result['consumers'].append(row)
        except (OSError, ValueError):
            continue
    result['consumer_auth_acceptance'] = 'NOT_PROVEN_BY_FILE_METADATA'
    cli = BASE + '/.openclaw/bin/openclaw'
    node_dir = BASE + '/.openclaw/tools/node-v24.21.0/bin'
    result['openclaw_auth_status'] = {'status': 'CLI_OR_NODE_UNAVAILABLE'}
    if os.path.isfile(cli) and os.path.isfile(node_dir + '/node'):
        env = {'HOME': BASE, 'PATH': node_dir + ':/usr/local/bin:/usr/bin:/bin',
               'LANG': 'C.UTF-8'}
        p = subprocess.run(['/usr/sbin/runuser', '-u', 'xuanjun_dev', '--',
                            cli, 'models', '--status-json'],
                           env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=30, check=False)
        summary = {'exit_code': p.returncode, 'status': 'UNPARSED_NO_RAW_OUTPUT',
                   'safe_fields': [], 'model_inference_requested': False}
        if p.returncode == 0 and len(p.stdout) <= 1048576:
            try:
                data = json.loads(p.stdout.decode('utf-8'))
                def walk(value, route, depth):
                    if depth > 8:
                        return
                    if isinstance(value, dict):
                        for k, v in value.items():
                            if k in ('provider', 'type', 'mode', 'status', 'authMode'):
                                if v in ('openai', 'openai-codex', 'oauth', 'api_key',
                                         'api-key', 'token', 'ok', 'missing', 'expired',
                                         'none', 'profile', 'env', 'runtime'):
                                    summary['safe_fields'].append({'route': route + '/' + k, 'value': v})
                            if k in ('authPath', 'authStorePath', 'profilePath', 'agentDir', 'configPath', 'storePath'):
                                path = safe_path(v)
                                if path:
                                    summary['safe_fields'].append({'route': route + '/' + k,
                                                                  'metadata': metadata(path)})
                            if isinstance(v, (dict, list)) and k not in ('tokens', 'credentials', 'secrets'):
                                walk(v, route + '/object', depth + 1)
                    elif isinstance(value, list):
                        for v in value[:100]:
                            walk(v, route + '/item', depth + 1)
                walk(data, 'models-status', 0)
                summary['status'] = 'PARSED_STRICT_ALLOWLIST'
            except (ValueError, UnicodeError, TypeError):
                pass
        result['openclaw_auth_status'] = summary
    if os.path.isfile(cli) and os.path.isfile(node_dir + '/node'):
        # Discover supported commands from bounded help output, not guessed resume APIs.
        # Output only fixed option presence; never session content or raw CLI output.
        capabilities = {}
        for command in ('agent', 'agents', 'sessions', 'gateway'):
            try:
                p = subprocess.run(['/usr/sbin/runuser', '-u', 'xuanjun_dev', '--',
                                    cli, command, '--help'], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   timeout=20, check=False)
                if len(p.stdout) > 262144:
                    capabilities[command] = {'state': 'HOLD_OVERSIZE_HELP'}
                    continue
                help_text = p.stdout.decode('utf-8', 'replace')
                options = ('--session-id', '--agent', '--message', '--local',
                           '--json', '--timeout', '--deliver', '--thinking')
                capabilities[command] = {
                    'exit_code': p.returncode,
                    'supported_options': [o for o in options if o in help_text],
                    'documented_resume_word': 'resume' in help_text.lower(),
                    'documented_stop_word': 'stop' in help_text.lower(),
                    'raw_output_emitted': False, 'inference_requested': False}
            except (OSError, subprocess.TimeoutExpired):
                capabilities[command] = {'state': 'HOLD_HELP_UNAVAILABLE'}
        result['native_command_capabilities'] = capabilities

    # Inspect installed CODE module metadata, never state/config/credential bytes.
    import hashlib
    import re
    entry = os.path.realpath(cli)
    code_prefix = BASE + '/.openclaw/npm/projects/'
    result['installed_native_code'] = {'state': 'CODE_ROOT_NOT_BOUND'}
    if entry.startswith(code_prefix) and entry.endswith(('.js', '.mjs', '.cjs')):
        parent = os.path.dirname(entry)
        package_root = None
        for unused in range(5):
            package_json = os.path.join(parent, 'package.json')
            if os.path.isfile(package_json):
                package_root = parent
                break
            parent = os.path.dirname(parent)
        if package_root and package_root.startswith(code_prefix):
            modules = []
            examined = 0
            for directory, dirs, names in os.walk(package_root, followlinks=False):
                dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', 'test', 'tests')
                           and not os.path.islink(os.path.join(directory, d))]
                if directory.count('/') - package_root.count('/') > 3:
                    dirs[:] = []
                    continue
                for name in sorted(names):
                    if (not name.endswith(('.js', '.mjs', '.cjs'))
                            or not re.search(r'(auth|oauth|codex|gateway|session)', name, re.I)):
                        continue
                    path = os.path.join(directory, name)
                    if os.path.islink(path) or len(modules) >= 40:
                        continue
                    try:
                        info = os.stat(path)
                        if not stat.S_ISREG(info.st_mode) or info.st_size > 16777216:
                            continue
                        with open(path, 'rb') as stream:
                            raw = stream.read(16777217)
                        examined += len(raw)
                        if examined > 67108864:
                            dirs[:] = []
                            break
                        source = raw.decode('utf-8', 'replace')
                        symbols = sorted(set(re.findall(
                            r'function\s+([A-Za-z_$][A-Za-z0-9_$]{0,100})', source)))
                        methods = sorted(set(re.findall(
                            r'[\\\"\\\']((?:sessions|agents|agent|chat|models)\.[A-Za-z0-9_.]{1,80})[\\\"\\\']',
                            source)))
                        modules.append({'path': path, 'sha256': hashlib.sha256(raw).hexdigest(),
                            'uid': info.st_uid, 'mode': oct(stat.S_IMODE(info.st_mode)),
                            'symbols': [v for v in symbols if re.search(r'(auth|oauth|profile|session|resume|abort|stop|credential)', v, re.I)][:40],
                            'rpc_method_names': methods[:40]})
                    except (OSError, UnicodeError):
                        continue
                if examined > 67108864 or len(modules) >= 40:
                    break
            result['installed_native_code'] = {'state': 'CODE_METADATA_ONLY',
                'entry_path': entry, 'package_root': package_root, 'modules': modules,
                'credential_content_read': False, 'inference_requested': False}


    result['configured_native_roles'] = {'state': 'CLI_UNAVAILABLE', 'agent_ids': []}
    if os.path.isfile(cli) and os.path.isfile(node_dir + '/node'):
        p = subprocess.run(['/usr/sbin/runuser', '-u', 'xuanjun_dev', '--',
                            cli, 'agents', 'list', '--json'], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=20, check=False)
        registry = {'state': 'UNPARSED_NO_RAW_OUTPUT', 'exit_code': p.returncode, 'agent_ids': []}
        if p.returncode == 0 and len(p.stdout) <= 262144:
            try:
                value = json.loads(p.stdout.decode('utf-8'))
                items = value if isinstance(value, list) else value.get('agents', [])
                for item in items[:100]:
                    if isinstance(item, dict):
                        agent_id = item.get('id') or item.get('agentId')
                        if isinstance(agent_id, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', agent_id):
                            registry['agent_ids'].append(agent_id)
                registry['state'] = 'CONFIGURED_ROLE_METADATA_ONLY'
            except (ValueError, TypeError, AttributeError):
                pass
        result['configured_native_roles'] = registry

    import pwd

    result['p2_platform_child_probe'] = {'state': 'SESSION_QUERY_UNAVAILABLE', 'child_started': 'NOT_PROVEN'}
    if os.path.isfile(cli) and os.path.isfile(node_dir + '/node'):
        p = subprocess.run(['/usr/sbin/runuser', '-u', 'xuanjun_dev', '--',
                            cli, 'sessions', '--json', '--agent', 'main'], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, check=False)
        probe = {'state': 'NO_RAW_SESSION_CONTENT', 'exit_code': p.returncode,
                 'main_session_id': 'e2474bef-73d5-4c39-9428-4d610697db29',
                 'matching_sessions': [], 'spawn_tool_calls': [], 'spawn_tool_results': [],
                 'child_started': 'NOT_PROVEN'}
        if p.returncode == 0 and len(p.stdout) <= 1048576:
            try:
                listing = json.loads(p.stdout.decode('utf-8'))
                rows = listing if isinstance(listing, list) else listing.get('sessions', [])
                for row in rows[:1000]:
                    if not isinstance(row, dict):
                        continue
                    session_id = row.get('sessionId')
                    key = row.get('key')
                    if session_id == probe['main_session_id'] or (isinstance(key, str) and 'p2-platform-' in key):
                        clean = {}
                        for field in ('sessionId', 'key', 'model', 'modelProvider', 'kind'):
                            value = row.get(field)
                            if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,250}', value):
                                clean[field] = value
                        for field in ('updatedAt', 'createdAt'):
                            value = row.get(field)
                            if type(value) in (int, float):
                                clean[field] = value
                        probe['matching_sessions'].append(clean)
                probe['registry_schema_keys'] = sorted(k for k in listing if isinstance(k, str) and re.fullmatch(r'[A-Za-z_]{1,40}', k))[:30] if isinstance(listing, dict) else []
                stores = []
                if isinstance(listing, dict):
                    for field in ('path', 'storePath'):
                        candidate = safe_path(listing.get(field))
                        if candidate and candidate.endswith('/sessions.json'):
                            stores.append(candidate)
                    for item in listing.get('stores', [])[:20]:
                        if isinstance(item, dict):
                            for field in ('path', 'storePath'):
                                candidate = safe_path(item.get(field))
                                if candidate and candidate.endswith('/sessions.json'):
                                    stores.append(candidate)
                probe['registry_store_paths'] = sorted(set(stores))
                store = stores[0] if len(set(stores)) == 1 else None
                probe['session_log_probe_state'] = 'STORE_PATH_UNAVAILABLE' if store is None else 'STORE_PATH_OBSERVED'
                if store and store.endswith('/sessions.json'):
                    log_path = os.path.dirname(store) + '/' + probe['main_session_id'] + '.jsonl'
                    info = os.lstat(log_path)
                    if stat.S_ISREG(info.st_mode) and info.st_uid == pwd.getpwnam('xuanjun_dev').pw_uid and info.st_size <= 2097152:
                        with open(log_path, 'r', encoding='utf-8') as stream:
                            for line in stream:
                                record = json.loads(line)
                                message = record.get('message', {})
                                role = message.get('role')
                                content = message.get('content', [])
                                if not isinstance(content, list):
                                    continue
                                for part in content:
                                    if not isinstance(part, dict):
                                        continue
                                    if role == 'assistant' and part.get('type') == 'toolCall' and part.get('name') in ('sessions_spawn', 'subagents'):
                                        arguments = part.get('arguments', {})
                                        label = arguments.get('label') if isinstance(arguments, dict) else None
                                        probe['spawn_tool_calls'].append({'tool': part['name'],
                                            'tool_call_id': part.get('id') if isinstance(part.get('id'), str) else None,
                                            'platform_label_present': isinstance(label, str) and 'PLATFORM' in label.upper()})
                                    if role == 'toolResult' and message.get('toolName') == 'sessions_spawn' and part.get('type') == 'text':
                                        try:
                                            observed = json.loads(part.get('text', ''))
                                            clean = {}
                                            for field in ('status', 'runId', 'childSessionKey'):
                                                value = observed.get(field)
                                                if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,250}', value):
                                                    clean[field] = value
                                            probe['spawn_tool_results'].append(clean)
                                        except (ValueError, TypeError, AttributeError):
                                            pass
                        probe['session_log_metadata'] = metadata(log_path)
                probe['state'] = 'NATIVE_SESSION_METADATA_PROBED_NO_CHILD_START_ATTESTATION'
            except (ValueError, TypeError, AttributeError, OSError):
                probe['state'] = 'HOLD_NATIVE_SESSION_PROBE_SCHEMA_OR_LOG_UNAVAILABLE'
        result['p2_platform_child_probe'] = probe


    # Read-only reconciliation: no reset/clean/stash/commit or host lease mutation.
    reconciliation = {'target_prefix': 'd99b0406', 'repositories': [],
                      'writer_stopped': 'NOT_PROVEN', 'lease_fence': 'NOT_RECONCILED',
                      'side_effects': 'NOT_RECONCILED', 'freeze': 'DENIED_PENDING_RECONCILIATION'}
    roots = ['/home/xuanjun_dev', '/home/githubrunner']
    found = []
    for root in roots:
        for directory, dirs, files in os.walk(root, followlinks=False):
            depth = directory[len(root):].count('/')
            if '.git' in dirs or '.git' in files:
                found.append(directory)
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in ('node_modules', '.npm', '.cache', 'vendor', 'state', 'sessions') and not os.path.islink(os.path.join(directory, d))]
            if depth >= 4 or len(found) >= 40:
                dirs[:] = []
    for directory in found[:40]:
        owner = pwd.getpwuid(os.stat(directory).st_uid).pw_name
        if owner not in ('xuanjun_dev', 'githubrunner'):
            continue
        def git_read(arguments):
            command = ['/usr/sbin/runuser', '-u', owner, '--', '/usr/bin/git', '--no-optional-locks', '-C', directory] + arguments
            environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
            outcome = subprocess.run(command, env=environment, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, timeout=10)
            return outcome.returncode, outcome.stdout[:2097152]
        code, head = git_read(['rev-parse', 'HEAD'])
        if code:
            continue
        code, target = git_read(['rev-parse', '--verify', 'd99b0406^{commit}'])
        row = {'path': directory, 'unix_owner': owner, 'head': head.decode('ascii', 'replace').strip(),
               'target_present': code == 0}
        if code == 0:
            row['target_commit'] = target.decode('ascii', 'replace').strip()
            _, authors = git_read(['show', '-s', '--format=%H%n%T%n%P%n%an%n%cn%n%aI%n%cI', row['target_commit']])
            row['commit_author_metadata'] = authors.decode('utf-8', 'replace').splitlines()
            _, status = git_read(['status', '--porcelain=v1', '-z', '--untracked-files=normal'])
            _, diff = git_read(['diff', '--no-ext-diff', '--no-textconv', '--binary', 'HEAD', '--'])
            _, index = git_read(['diff', '--cached', '--no-ext-diff', '--no-textconv', '--binary', '--'])
            import hashlib
            row['status_sha256'] = hashlib.sha256(status).hexdigest()
            row['diff_sha256'] = hashlib.sha256(diff).hexdigest()
            row['index_diff_sha256'] = hashlib.sha256(index).hexdigest()
            row['diff_bytes_bounded'] = len(diff)
            row['status_entries'] = status.count(b'\\x00')
            row['diff_preserved_in_place'] = True
            row['authors_are_execution_identity'] = False
            _, history = git_read(['log', '--max-count=8', '--format=%H %T %P', row['target_commit'] + '..HEAD'])
            row['subsequent_commit_graph'] = history.decode('ascii', 'replace').splitlines()
            _, names = git_read(['diff', '--name-status', '--no-renames', row['target_commit'] + '^', 'HEAD', '--'])
            row['changed_paths'] = [line for line in names.decode('utf-8', 'replace').splitlines()[:100] if not any(ord(x) < 32 and x != '\\t' for x in line)]
            row['matching_processes'] = []
            for proc_id in os.listdir('/proc'):
                if not proc_id.isdigit():
                    continue
                try:
                    proc_path = '/proc/' + proc_id
                    cwd = os.readlink(proc_path + '/cwd')
                    if not (cwd == directory or cwd.startswith(directory + '/')):
                        continue
                    with open(proc_path + '/comm') as stream:
                        name = stream.read(80).strip()
                    with open(proc_path + '/stat') as stream:
                        fields = stream.read(4096).rsplit(')', 1)[1].split()
                    row['matching_processes'].append({'pid': int(proc_id), 'uid': os.stat(proc_path).st_uid,
                        'cwd': cwd, 'comm': name, 'ppid': int(fields[1]), 'start_ticks': fields[19]})
                except (OSError, ValueError, IndexError):
                    continue
            row['cwd_scan_proves_no_writer'] = False
            row['lease_fence_evidence'] = 'CANONICAL_RECORD_NOT_BOUND'
            row['comparison_exit_codes'] = {}
            for label, left, right in (('d99_to_head', row['target_commit'], 'HEAD'),
                                       ('d99_parent_to_d99', row['target_commit'] + '^', row['target_commit'])):
                ec, changes = git_read(['diff', '--name-status', '--no-renames', left, right, '--'])
                row['comparison_exit_codes'][label] = ec
                row[label + '_paths'] = changes.decode('utf-8', 'replace').splitlines()[:100] if ec == 0 else []
            row['associated_processes_by_cwd'] = []
            for proc_id in os.listdir('/proc'):
                if not proc_id.isdigit():
                    continue
                try:
                    pp = '/proc/' + proc_id
                    cwd = os.readlink(pp + '/cwd')
                    with open(pp + '/comm') as stream:
                        comm = stream.read(80).strip()
                    uid = os.stat(pp).st_uid
                    if uid != pwd.getpwnam('xuanjun_dev').pw_uid or comm not in ('codex', 'node', 'openclaw', 'python3', 'bash'):
                        continue
                    with open(pp + '/stat') as stream:
                        fields = stream.read(4096).rsplit(')', 1)[1].split()
                    row['associated_processes_by_cwd'].append({'pid': int(proc_id), 'ppid': int(fields[1]),
                        'start_ticks': fields[19], 'comm': comm, 'cwd': safe_path(cwd) or 'OUTSIDE_ALLOWED_ROOTS'})
                except (OSError, ValueError, IndexError):
                    continue
            row['canonical_state_metadata'] = [metadata(p) for p in
                ('/var/lib/xuanjun-development', '/etc/xuanjun-development',
                 '/home/xuanjun_dev/p2-platform-delivery-receipts')]


        reconciliation['repositories'].append(row)
    result['p2_unfrozen_code_reconciliation'] = reconciliation

    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    audit()
