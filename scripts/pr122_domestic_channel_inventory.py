#!/usr/bin/env python3
"""Bounded non-root, no-secrets inventory for PR122's existing host channel."""
import json
import os
import pwd
import re
import subprocess


def command(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=15)


def main():
    if os.uname().nodename != 'iZvt5t8tlrm8oiZ' or pwd.getpwuid(os.geteuid()).pw_name != 'githubrunner':
        raise SystemExit('STOP_WRONG_HOST_OR_IDENTITY')
    out = {'schema_version': 1, 'host': os.uname().nodename,
           'user': 'githubrunner', 'production_mutation': False}
    fields = ('Id', 'ActiveState', 'SubState', 'User', 'MainPID', 'WorkingDirectory', 'FragmentPath')
    services = {}
    for name in ('provider-neutral-domestic-bridge.service', 'nginx.service'):
        result = command(['systemctl', 'show', name] + ['--property='+f for f in fields])
        services[name] = dict(line.split('=', 1) for line in result.stdout.splitlines()
                              if '=' in line and line.split('=', 1)[0] in fields)
        services[name]['query_exit'] = result.returncode
    out['services'] = services
    result = command(['ss', '-H', '-lnt'])
    out['loopback_tcp_ports'] = sorted(set(int(p) for p in re.findall(
        r'(?:127\.0\.0\.1|\[::1\]):(\d+)\s', result.stdout)))
    # Permissions are observed, never exercised. Do not publish command/env text.
    result = command(['sudo', '-n', '-l'])
    out['sudo_policy_visible'] = result.returncode == 0
    out['sudo_general_all_reported'] = bool(re.search(r'NOPASSWD:\s*ALL(?:\s|$)', result.stdout))
    print(json.dumps(out, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
