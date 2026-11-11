"""Sanitized, read-only systemd observations. No service mutation or model call."""
import math
import subprocess
import time


UNITS = ('xuanjun-uk-openclaw.service', 'xuanjun-development-dispatcher.service',
         'xuanjun-p2-gateway-relay.service')
PROPERTIES = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'Result')
ACTIVE = ('active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading')
SUB = ('running', 'exited', 'dead', 'failed', 'start', 'start-pre', 'start-post',
       'stop', 'stop-sigterm', 'stop-sigkill', 'stop-post', 'auto-restart', 'reload')
RESULT = ('success', 'resources', 'timeout', 'exit-code', 'signal', 'core-dump',
          'watchdog', 'start-limit-hit', 'protocol')


def _time(value):
    return (type(value) in (int, float) and 0 <= value <= 10 ** 15
            and math.isfinite(value))


def parse_properties(unit, raw):
    """Reject incomplete, duplicate, unexpected or nonsanitized properties."""
    if unit not in UNITS or not isinstance(raw, bytes) or len(raw) > 8192:
        raise ValueError('INVALID_HEALTH_INPUT')
    values = {}
    for line in raw.decode('utf-8', 'strict').splitlines():
        key, separator, value = line.partition('=')
        if not separator or key not in PROPERTIES or key in values:
            raise ValueError('INVALID_HEALTH_PROPERTIES')
        values[key] = value
    if set(values) != set(PROPERTIES) or values['Id'] != unit:
        raise ValueError('INCOMPLETE_HEALTH_PROPERTIES')
    if (values['LoadState'] not in ('loaded', 'not-found', 'masked', 'error') or
            values['ActiveState'] not in ACTIVE or values['SubState'] not in SUB or
            values['Result'] not in RESULT):
        raise ValueError('UNKNOWN_HEALTH_ENUM')
    pid = values['MainPID']
    if not pid or len(pid) > 10 or any(ch not in '0123456789' for ch in pid):
        raise ValueError('INVALID_PID')
    pid = int(pid)
    if pid > 2 ** 31 - 1:
        raise ValueError('INVALID_PID')
    values['MainPID'] = pid
    return values


def observe_service(unit, run=None, clock=None):
    """One fixed systemctl show; no shell, sudo, environment dump or logs.

    Invoke only on an authorized observation host after integration review.
    Unit activity is not evidence of model readiness or actual task progress.
    """
    if unit not in UNITS:
        raise ValueError('UNREVIEWED_UNIT')
    run = subprocess.run if run is None else run
    clock = time.time if clock is None else clock
    start = clock()
    result = {'schema': 'CONTROL_SERVICE_OBSERVATION_V1', 'unit': unit,
              'state': 'UNKNOWN', 'reason': 'OBSERVATION_UNAVAILABLE',
              'observed_at': None, 'properties': None,
              'model_readiness': 'UNKNOWN', 'task_progress': 'UNKNOWN',
              'service_mutation_performed': False}
    if not _time(start):
        result['reason'] = 'INVALID_CLOCK'
        return result
    try:
        completed = run(['/usr/bin/systemctl', 'show', unit, '--no-pager',
                         '--property=' + ','.join(PROPERTIES)],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL, timeout=3, check=False,
                        env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                             'SYSTEMD_COLORS': '0', 'SYSTEMD_PAGER': ''})
        if type(completed.returncode) is not int or completed.returncode != 0:
            result['reason'] = 'SYSTEMCTL_FAILED'
            return result
        values = parse_properties(unit, completed.stdout)
        end = clock()
        if not _time(end) or end < start or end - start > 5:
            result['reason'] = 'INVALID_OBSERVATION_TIME'
            return result
        result.update(state='OBSERVED', reason='SYSTEMD_PROPERTIES_ONLY',
                      observed_at=end, properties=values)
    except subprocess.TimeoutExpired:
        result['reason'] = 'SYSTEMCTL_TIMEOUT'
    except (OSError, ValueError, TypeError, AttributeError):
        result['reason'] = 'INVALID_OR_UNAVAILABLE_PROPERTIES'
    return result
