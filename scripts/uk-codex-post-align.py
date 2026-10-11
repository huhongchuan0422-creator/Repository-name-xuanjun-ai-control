#!/usr/bin/env python3
"""Verify the selected generation; never reinstall a published runtime."""
def main():
    import fcntl, hashlib, json, os, socket, uuid
    from pathlib import Path
    if os.geteuid() != 0 or socket.gethostname().split('.')[0] != 'iZd7oeikknn1z21sq6ji6zZ':
        raise SystemExit('STOP_WRONG_SERVER_OR_USER')
    p = Path('/tmp/xuanjun-uk-integration-9bc1eca92d7fcf4b6fb4d68b3d0338f1c10a7cc4/scripts/uk-codex-runtime-align.py')
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != '6da7dba69e7b0c30ba407d6c9e1be71da887681be84878c6a0e352cbb0342fde':
        raise SystemExit('STOP_SOURCE_HASH_MISMATCH')
    control = {'__name__': 'verify_existing_only', '__file__': str(p)}
    exec(compile(raw, str(p), 'exec'), control)
    probe = p.with_name('uk-56-canary.py')
    raw_probe = probe.read_bytes()
    if hashlib.sha256(raw_probe).hexdigest() != control['PROBE_HASH']:
        raise SystemExit('STOP_PROBE_HASH_MISMATCH')
    ns = {'__name__': 'existing_runtime_probe', '__file__': str(probe)}
    exec(compile(raw_probe, str(probe), 'exec'), ns)
    fd = os.open('/run/lock/xuanjun-uk-model-runtime.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('STOP_RUNTIME_OPERATION_ALREADY_ACTIVE')
    cfg = json.loads(control['CONFIG'].read_bytes())
    code, data, error = ns['command'](['plugins', 'inspect', 'codex', '--json'], timeout=40)
    data = data if isinstance(data, dict) else {}
    plugin = data.get('plugin', {})
    install = data.get('install', {})
    source = plugin.get('source')
    selected = plugin.get('id') == 'codex' and plugin.get('version') == '2026.9.9'
    policy = control['policy_ok'](cfg)
    versions = None
    if selected and isinstance(source, str) and source.startswith('/home/xuanjun_dev/.openclaw/'):
        source_path = Path(source).resolve()
        if str(source_path).startswith('/home/xuanjun_dev/.openclaw/'):
            for directory in source_path.parents:
                if str(directory) == '/home/xuanjun_dev/.openclaw':
                    break
                package = directory / 'package.json'
                if not package.is_file():
                    continue
                try:
                    item = json.loads(package.read_bytes())
                    if item.get('name') != '@openclaw/codex':
                        continue
                    native = directory.parent.parent / '@openai/codex/package.json'
                    cli = json.loads(native.read_bytes())
                    versions = (item.get('version'), item.get('dependencies', {}).get('@openai/codex'), cli.get('version'))
                    break
                except (OSError, ValueError):
                    continue
    print(json.dumps({'server': 'UK', 'install_repeated': False,
                      'inspect_exit_code': code, 'selected_plugin_20260909': selected,
                      'policy_ok': policy, 'selected_dependency_versions': versions,
                      'inspect_diagnostic': ns['command'].last_error}, ensure_ascii=False), flush=True)
    if code != 0 or not policy or versions != ('2026.9.9', '0.160.0', '0.160.0'):
        raise SystemExit('STOP_CURRENT_SELECTION_NOT_VERIFIED_NO_INSTALL_OR_INFERENCE')
    code, data, _ = ns['command'](['models', 'auth', 'list', '--provider', 'openai', '--json'])
    types = ns['auth_types_for_provider'](data)
    if code != 0 or not types or any(t != 'oauth' for t in types):
        raise SystemExit('STOP_OAUTH_ROUTE_NOT_VERIFIED')
    fingerprint = hashlib.sha256((json.dumps(versions) + str(source_path) + hashlib.sha256(control['CONFIG'].read_bytes()).hexdigest()).encode()).hexdigest()
    attempt = Path('/home/.xuanjun-root-private-backups') / ('56-post-alignment-' + fingerprint + '.attempt')
    try:
        attempt_fd = os.open(str(attempt), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise SystemExit('STOP_IDENTICAL_PROBE_ALREADY_ATTEMPTED_NO_RETRY')
    os.close(attempt_fd)
    marker = 'XJ_56_POST_ALIGN_' + uuid.uuid4().hex
    code, data, error = ns['command']([
        'agent', '--agent', 'main', '--session-key', 'agent:main:56-post-align-' + uuid.uuid4().hex,
        '--model', 'openai/gpt-5.6-sol', '--message',
        'Reply with exactly ' + marker + '. Do not call tools, delegate, read files, or send messages.',
        '--thinking', 'low', '--timeout', '40', '--json'], timeout=55)
    result = ns['evaluate'](data, code, marker)
    messages = []
    for obj in ns['objects'](data):
        item = obj.get('error')
        if isinstance(item, dict) and isinstance(item.get('message'), str):
            messages.append(ns['safe_diagnostic']('Error: ' + item['message']))
    result.update({'error_code': 'NONE' if result['inference_verified'] else error,
                   'diagnostic': ns['command'].last_error, 'error_messages': messages[:3],
                   'install_repeated': False, 'sole_fallback_configured': False,
                   'channel_delivery': False, 'feishu_e2e': 'NOT_VERIFIED'})
    if result['inference_verified']:
        try:
            control['activate_fallback'](ns)
            result['sole_fallback_configured'] = True
        except Exception as exc:
            result['fallback_activation'] = str(exc) if isinstance(exc, RuntimeError) else 'FAILED_NO_RETRY'
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()

