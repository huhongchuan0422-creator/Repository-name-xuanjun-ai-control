#!/usr/bin/env python3
"""One authorized Sol-only Gateway canary; no delivery or production cutover."""
import json
import os
import socket
import subprocess
import uuid

ROOT = '/home/xuanjun_dev'
CLI = ROOT + '/.openclaw/bin/openclaw'
TARGET = 'openai/gpt-6.1-sol'


def objects(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            for obj in objects(item):
                yield obj
    elif isinstance(value, list):
        for item in value:
            for obj in objects(item):
                yield obj


def catalog_summary(data):
    rows = []
    for obj in objects(data):
        if any(obj.get(k) in (TARGET, 'gpt-6.1-sol')
               for k in ('key', 'id', 'slug', 'model')):
            row = {'target': TARGET}
            for k in ('available', 'missing', 'configured'):
                if type(obj.get(k)) is bool:
                    row[k] = obj[k]
            rows.append(row)
    outcomes = []
    for obj in objects(data):
        if obj.get('provider') == 'openai' and obj.get('status') in ('ready', 'auth-rejected', 'unavailable'):
            outcomes.append(obj['status'])
    return {'target_rows': rows[:10], 'provider_outcomes': outcomes[:10]}


def evaluate(data, exit_code, marker):
    # Only returned output and returned model metadata count as inference evidence.
    records = list(objects(data))
    reply = any(isinstance(obj.get(k), str) and obj[k].strip() == marker
                for obj in records for k in ('text', 'final'))
    models = [obj['model'] for obj in records if isinstance(obj.get('model'), str)]
    providers = [obj['provider'] for obj in records if isinstance(obj.get('provider'), str)]
    model_ok = bool(models) and all(m in (TARGET, 'gpt-6.1-sol') for m in models)
    provider_ok = bool(providers) and all(p == 'openai' for p in providers)
    failed = any(obj.get('status') in ('error', 'timeout', 'failed')
                 or obj.get('aborted') is True or obj.get('error')
                 for obj in records)
    return {'exit_code': exit_code, 'exact_reply': reply,
            'returned_model': TARGET if model_ok else 'OTHER_OR_UNKNOWN',
            'returned_provider': 'openai' if provider_ok else 'OTHER_OR_UNKNOWN',
            'inference_verified': exit_code == 0 and reply and model_ok and provider_ok and not failed,
            'subscription_quota_pool': 'UNKNOWN', 'production_pass': False}


def classify_error(raw):
    lower = raw.lower()
    checks = [('MODEL_UNAVAILABLE', ('selected model is unavailable', 'model_not_found', 'unknown model')),
              ('QUOTA_OR_USAGE_LIMIT', ('usage_limit', 'quota exceeded')),
              ('AUTH_REJECTED', ('unauthorized', 'invalid_api_key', 'authentication failed')),
              ('STATE_LOCKED', ('state lock', 'exclusive ownership')),
              ('UNSUPPORTED_COMMAND', ('unknown option', 'unknown command'))]
    for label, needles in checks:
        if any(n in lower for n in needles):
            return label
    return 'UNKNOWN'


def command(args, timeout=40):
    env = {'HOME': ROOT, 'LANG': 'C.UTF-8',
           'PATH': ROOT + '/.openclaw/tools/node-v24.21.0/bin:/usr/local/bin:/usr/bin:/bin'}
    try:
        p = subprocess.run(['/usr/sbin/runuser', '-u', 'xuanjun_dev', '--', CLI] + args,
                           env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, check=False)
        raw = p.stdout.decode('utf-8', 'replace')
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        diagnostic = raw + p.stderr.decode('utf-8', 'replace')
        return p.returncode, data, classify_error(diagnostic)
    except subprocess.TimeoutExpired:
        # Gateway acceptance is ambiguous; never retry this canary automatically.
        return None, None, 'TIMEOUT_EFFECT_UNKNOWN_NO_RETRY'
    except OSError:
        return None, None, 'CLI_UNAVAILABLE'


def main():
    if os.geteuid() != 0 or socket.gethostname().split('.')[0] != 'iZd7oeikknn1z21sq6ji6zZ':
        raise SystemExit('STOP_FIXED_UK_ROOT_SCOPE')
    with open(ROOT + '/.openclaw/openclaw.json') as stream:
        cfg = json.load(stream)
    model = cfg.get('agents', {}).get('defaults', {}).get('model')
    primary = model if isinstance(model, str) else model.get('primary') if isinstance(model, dict) else None
    fallbacks = model.get('fallbacks', []) if isinstance(model, dict) else []
    if primary != TARGET or fallbacks != []:
        raise SystemExit('STOP_SOL_ONLY_CONFIG_REQUIRED')
    result = {'target': TARGET, 'fallbacks': 0, 'channel_delivery': False,
              'production_cutover': False, 'catalog_refresh': 'NOT_EXECUTED'}
    code, data, error = command(['models', 'list', '--agent', 'main', '--provider', 'openai', '--json'])
    result['catalog_before'] = dict(catalog_summary(data), exit_code=code, error_code=error)
    # Refresh provider inventory through the live Gateway; never offline models refresh.
    code, data, error = command(['models', 'list', '--agent', 'main', '--provider', 'openai', '--refresh', '--json'])
    result['catalog_after'] = dict(catalog_summary(data), exit_code=code, error_code=error)
    result['catalog_refresh'] = 'REQUESTED'
    if code != 0 or data is None:
        result['inference'] = {'status': 'NOT_STARTED_CATALOG_UNCONFIRMED'}
        print(json.dumps(result, sort_keys=True))
        return
    marker = 'XJ_SOL_CANARY_' + uuid.uuid4().hex
    session = 'agent:main:sol-canary-' + uuid.uuid4().hex
    # A new explicit session isolates this test from Feishu and Owner main chat.
    args = ['agent', '--agent', 'main', '--session-key', session,
            '--model', TARGET, '--message',
            'Reply with exactly ' + marker + '. Do not call tools, delegate, read files, or send messages.',
            '--thinking', 'low', '--timeout', '40', '--json']
    code, data, error = command(args, timeout=55)
    result['inference'] = evaluate(data, code, marker)
    result['inference']['error_code'] = 'NONE' if result['inference']['inference_verified'] else error
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
