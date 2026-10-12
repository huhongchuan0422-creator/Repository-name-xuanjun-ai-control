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
                            if k in ('authPath', 'authStorePath', 'profilePath', 'agentDir', 'configPath'):
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
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    audit()
