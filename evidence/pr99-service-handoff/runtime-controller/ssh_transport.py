"""Bounded transport for the existing Tokyo -> domestic fixed helper channel.

Only existing read-only operations are enabled here. Mutating operations must be
implemented by the target's owned helper before being added; no shell payloads,
remote Python, sudo wildcard, or fabricated success receipts are accepted.
"""
import json
import subprocess

SOURCE = 'iZ6wee8q9z4t03hvqumwfhZ'
TARGET = 'iZvt5t8tlrm8oiZ'
SSH = (
    '/usr/bin/sudo', '-n', '-u', 'admin', '/usr/bin/ssh', '-T',
    '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', 'ConnectTimeout=10', '-o', 'ConnectionAttempts=1',
    '-o', 'ClearAllForwardings=yes', '-o', 'ForwardAgent=no',
    '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=2',
    'binance-ops',
)
COMMANDS = {
    name: '/usr/bin/sudo -n /usr/local/sbin/pr99-migration-target ' + name
    for name in ('status', 'verify-unit', 'nginx-test')
}


class ChannelHold(RuntimeError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ChannelHold('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


class ExistingSSHChannel:
    def __init__(self, hostname, runner=subprocess.run):
        if hostname.split('.')[0] != SOURCE:
            raise ChannelHold('SOURCE_HOST_MISMATCH')
        self.runner = runner

    def query(self, operation):
        if operation not in COMMANDS:
            raise ChannelHold('OPERATION_NOT_INSTALLED')
        # One invocation, never automatically retry an ambiguous SSH outcome.
        try:
            result = self.runner(
                [*SSH, COMMANDS[operation]], input=b'', capture_output=True,
                timeout=45, check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            raise ChannelHold('CHANNEL_UNKNOWN_NO_REPLAY') from None
        if result.returncode:
            # Never echo remote stderr: it may include private configuration.
            raise ChannelHold('CHANNEL_NONZERO_NO_REPLAY')
        if len(result.stdout) > 262144 or len(result.stderr) > 262144:
            raise ChannelHold('CHANNEL_OUTPUT_LIMIT')
        try:
            response = json.loads(result.stdout, object_pairs_hook=unique_object)
        except (ValueError, UnicodeError):
            raise ChannelHold('CHANNEL_INVALID_JSON') from None
        if (type(response) is not dict or response.get('host') != TARGET
                or response.get('operation') != operation):
            raise ChannelHold('CHANNEL_RESPONSE_BINDING')
        return response
