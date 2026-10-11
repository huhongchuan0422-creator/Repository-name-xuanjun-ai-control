#!/usr/bin/env python3
"""Fixed read-only model routing diagnostic; no login, inference or cutover."""
import json
import os
import re
import socket
import subprocess
import urllib.parse

ROOT = '/home/xuanjun_dev'
CLI = ROOT + '/.openclaw/bin/openclaw'
TARGET = 'openai/gpt-6.1-sol'
SAFE_VALUES = {'openai', 'openai-codex', 'oauth', 'api_key', 'api-key', 'token',
               'usable', 'unavailable', 'missing', 'expired', 'ok', 'auth',
               'rate_limit', 'billing', 'timeout', 'format', 'unknown', 'no_model',
               'missing_credential', 'excluded_by_auth_order', 'invalid_expires',
               'unresolved_ref', 'ineligible_profile', 'ready', 'disabled', 'enabled'}
SAFE_KEYS = {'provider', 'type', 'mode', 'status', 'authStatus', 'runtimeStatus',
             'reason', 'code', 'model', 'resolvedDefault', 'defaultModel'}


def summarize(value):
    """Emit only known enum values and the exact requested model, never IDs."""
    found = []
    def visit(obj, depth=0):
        if depth > 12 or len(found) >= 100:
            return
        if isinstance(obj, dict):
            for key, item in list(obj.items())[:200]:
                if key in SAFE_KEYS and isinstance(item, str):
                    if item in SAFE_VALUES or item in (TARGET, 'gpt-6.1-sol'):
                        row = {'field': key, 'value': item}
                        if row not in found:
                            found.append(row)
                if isinstance(item, (dict, list)):
                    visit(item, depth + 1)
        elif isinstance(obj, list):
            for item in obj[:200]:
                visit(item, depth + 1)
    visit(value)
    return found


def main():
    if (os.geteuid() != 0 or socket.gethostname().split('.')[0] != 'iZd7oeikknn1z21sq6ji6zZ'):
        raise SystemExit('STOP_FIXED_UK_ROOT_SCOPE')
    env = {'HOME': ROOT, 'LANG': 'C.UTF-8',
           'PATH': ROOT + '/.openclaw/tools/node-v24.21.0/bin:/usr/local/bin:/usr/bin:/bin'}
    result = {'production_mutation': False, 'inference_executed': False,
              'subscription_access': 'NOT_VERIFIED', 'target': TARGET}
    try:
        with open(ROOT + '/.openclaw/openclaw.json') as stream:
            cfg = json.load(stream)
        defaults = cfg.get('agents', {}).get('defaults', {}).get('model', {})
        model = defaults if isinstance(defaults, str) else defaults.get('primary')
        result['target_configured'] = model == TARGET
        result['fallback_count'] = (len(defaults.get('fallbacks', []))
                                    if isinstance(defaults, dict) else None)
        codex = cfg.get('plugins', {}).get('entries', {}).get('codex', {})
        result['codex_plugin_enabled'] = codex.get('enabled') is True
        allow = cfg.get('plugins', {}).get('allow')
        result['codex_plugin_allowed'] = allow is None or 'codex' in allow
        provider = cfg.get('models', {}).get('providers', {}).get('openai', {})
        host = urllib.parse.urlparse(provider.get('baseUrl', '')).hostname
        result['provider_origin'] = ('UNSPECIFIED' if not host else
                                     'OPENAI_OFFICIAL' if host == 'api.openai.com' else 'OTHER_ORIGIN')
        runtime = provider.get('agentRuntime', {}).get('id')
        result['runtime_override'] = runtime if runtime in ('openclaw', 'codex') else 'UNKNOWN'
        result['declared_auth'] = summarize(cfg.get('auth', {}).get('profiles', {}))
        result['agent_model_overrides'] = [summarize(a.get('model', {}))
                                           for a in cfg.get('agents', {}).get('list', [])
                                           if isinstance(a, dict) and a.get('model')]
    except (OSError, ValueError, TypeError, AttributeError):
        result['configuration_status'] = 'UNKNOWN'
    for label, args in [('status', ['models', '--json']),
                        ('auth', ['models', 'auth', 'list', '--provider', 'openai', '--json']),
                        ('catalog', ['models', 'list', '--json'])]:
        try:
            p = subprocess.run(['/usr/sbin/runuser', '-u', 'xuanjun_dev', '--', CLI] + args,
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=30, check=False)
            data = json.loads(p.stdout.decode('utf-8')) if p.returncode == 0 else None
            result[label] = {'exit_code': p.returncode, 'summary': summarize(data),
                             'parsed': data is not None}
        except (OSError, ValueError, subprocess.SubprocessError):
            result[label] = {'status': 'UNKNOWN'}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
