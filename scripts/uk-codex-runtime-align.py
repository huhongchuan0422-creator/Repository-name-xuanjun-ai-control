#!/usr/bin/env python3
"""One backed-up, pinned native runtime replacement and one isolated 5.6 probe.

Root/UK only. Never restarts a service, logs credentials, replays an uncertain
install, or sends a channel message. Native install owns drain and publication.
"""
import fcntl
import hashlib
import json
import os
import pwd
import socket
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path('/home/xuanjun_dev')
CONFIG = ROOT / '.openclaw/openclaw.json'
PROJECT = ROOT / '.openclaw/npm/projects/openclaw-codex-8902d781d4'
ALLOW = ['openai/gpt-6.1-sol', 'openai/gpt-5.6-sol']
PROBE_HASH = '89045f207dea08c3e31d6bfb2f342635c600b8e3239736306146cc71285a2e60'


def policy_ok(cfg):
    defaults = cfg.get('agents', {}).get('defaults', {})
    model = defaults.get('model')
    return (isinstance(model, dict)
            and model.get('primary') == ALLOW[0]
            and model.get('fallbacks', []) == []
            and defaults.get('modelPolicy', {}).get('allow') == ALLOW
            and cfg.get('plugins', {}).get('entries', {}).get('codex', {}).get('enabled') is True)


def versions():
    plugin = json.loads((PROJECT / 'node_modules/@openclaw/codex/package.json').read_bytes())
    cli = json.loads((PROJECT / 'node_modules/@openai/codex/package.json').read_bytes())
    return plugin.get('version'), plugin.get('dependencies', {}).get('@openai/codex'), cli.get('version')


def activate_fallback(ns):
    original = CONFIG.read_bytes()
    cfg = json.loads(original)
    if not policy_ok(cfg):
        raise RuntimeError('STOP_CONCURRENT_POLICY_CHANGE')
    info = CONFIG.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
        raise RuntimeError('STOP_UNSAFE_CONFIG')
    cfg['agents']['defaults']['model']['fallbacks'] = [ALLOW[1]]
    raw = (json.dumps(cfg, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    fd, name = tempfile.mkstemp(prefix='.xj-verified-fallback-', suffix='.json', dir=str(CONFIG.parent))
    try:
        os.fchmod(fd, stat.S_IMODE(info.st_mode))
        os.fchown(fd, info.st_uid, info.st_gid)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        env = {'HOME': str(ROOT), 'LANG': 'C.UTF-8',
               'PATH': str(ROOT) + '/.openclaw/tools/node-v24.21.0/bin:/usr/local/bin:/usr/bin:/bin',
               'OPENCLAW_CONFIG_PATH': name}
        result = subprocess.run(['/usr/sbin/runuser', '-u', 'xuanjun_dev', '--',
                                 ns['CLI'], 'config', 'validate', '--json'], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
        if result.returncode != 0 or json.loads(result.stdout).get('valid') is not True:
            raise RuntimeError('STOP_FALLBACK_VALIDATION_FAILED')
        if CONFIG.read_bytes() != original:
            raise RuntimeError('STOP_CONCURRENT_CONFIG_CHANGE')
        os.replace(name, str(CONFIG))
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0 or socket.gethostname().split('.')[0] != 'iZd7oeikknn1z21sq6ji6zZ':
        raise SystemExit('STOP_WRONG_SERVER_USER_OR_ARGUMENTS')
    os.umask(0o077)
    lock_fd = os.open('/run/lock/xuanjun-uk-model-runtime.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('STOP_RUNTIME_OPERATION_ALREADY_ACTIVE')
    probe = Path(__file__).with_name('uk-56-canary.py')
    source = probe.read_bytes()
    if hashlib.sha256(source).hexdigest() != PROBE_HASH:
        raise SystemExit('STOP_PROBE_HASH_MISMATCH')
    ns = {'__name__': 'alignment_probe', '__file__': str(probe)}
    exec(compile(source, str(probe), 'exec'), ns)
    config_before = CONFIG.read_bytes()
    if not policy_ok(json.loads(config_before)) or versions() != ('2026.9.8', '0.158.0', '0.158.0'):
        raise SystemExit('STOP_BASELINE_CHANGED_NO_REPEAT_INSTALL')
    code, data, _ = ns['command'](['models', 'auth', 'list', '--provider', 'openai', '--json'])
    types = ns['auth_types_for_provider'](data)
    if code != 0 or not types or any(t != 'oauth' for t in types):
        raise SystemExit('STOP_EXISTING_OAUTH_ROUTE_NOT_VERIFIED')
    backup = ROOT / ('.xj-runtime-backup-' + uuid.uuid4().hex)
    backup.mkdir(mode=0o700)
    user = pwd.getpwnam('xuanjun_dev')
    os.chown(str(backup), user.pw_uid, user.pw_gid)
    code, _, error = ns['command'](['backup', 'create', '--output', str(backup),
                                    '--verify', '--no-include-workspace'], timeout=180)
    if code != 0:
        print(json.dumps({'status': 'STOP_VERIFIED_BACKUP_FAILED', 'error_code': error,
                          'diagnostic': ns['command'].last_error, 'runtime_install_executed': False}))
        return
    if CONFIG.read_bytes() != config_before:
        raise SystemExit('STOP_CONCURRENT_CONFIG_CHANGE_BEFORE_INSTALL')
    print('UK_VERIFIED_STATE_BACKUP=' + str(backup), flush=True)
    code, _, error = ns['command'](['plugins', 'install', 'npm:@openclaw/codex@2026.9.9',
                                    '--force', '--pin', '--no-enable'], timeout=180)
    if code != 0:
        print(json.dumps({'status': 'INSTALL_FAILED_OR_EFFECT_UNKNOWN_NO_RETRY', 'error_code': error,
                          'diagnostic': ns['command'].last_error, 'backup': str(backup),
                          'inference_executed': False, 'production_pass': False}))
        return
    if versions() != ('2026.9.9', '0.160.0', '0.160.0') or not policy_ok(json.loads(CONFIG.read_bytes())):
        raise SystemExit('STOP_INSTALLED_VERSION_OR_POLICY_NOT_VERIFIED_NO_INFERENCE')
    code, data, _ = ns['command'](['models', 'auth', 'list', '--provider', 'openai', '--json'])
    types = ns['auth_types_for_provider'](data)
    if code != 0 or not types or any(t != 'oauth' for t in types):
        raise SystemExit('STOP_POST_INSTALL_OAUTH_ROUTE_NOT_VERIFIED_NO_INFERENCE')
    marker = 'XJ_56_ALIGNED_' + uuid.uuid4().hex
    code, data, error = ns['command']([
        'agent', '--agent', 'main', '--session-key', 'agent:main:56-aligned-' + uuid.uuid4().hex,
        '--model', ALLOW[1], '--message', 'Reply with exactly ' + marker +
        '. Do not call tools, delegate, read files, or send messages.',
        '--thinking', 'low', '--timeout', '40', '--json'], timeout=55)
    result = ns['evaluate'](data, code, marker)
    messages = []
    for obj in ns['objects'](data):
        item = obj.get('error')
        if isinstance(item, dict) and isinstance(item.get('message'), str):
            messages.append(ns['safe_diagnostic']('Error: ' + item['message']))
    result.update({'server': 'UK', 'runtime_install_executed': True,
                   'installed_plugin': '2026.9.9', 'installed_codex': '0.160.0',
                   'backup': str(backup), 'error_code': 'NONE' if result['inference_verified'] else error,
                   'diagnostic': ns['command'].last_error, 'error_messages': messages[:3],
                   'sole_fallback_configured': False, 'channel_delivery': False,
                   'feishu_e2e': 'NOT_VERIFIED', 'primary_recovery': 'NOT_VERIFIED'})
    if result['inference_verified']:
        try:
            activate_fallback(ns)
            result['sole_fallback_configured'] = True
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            result['fallback_activation'] = str(exc) if isinstance(exc, RuntimeError) else 'FAILED_NO_RETRY'
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
