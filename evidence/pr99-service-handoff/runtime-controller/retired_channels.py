"""Owner-retired WeCom units: exact-unit isolation, no dependency shutdown.

Invoked only by the admitted source controller. No data deletion, shared bridge,
DB fencing, nginx changes, broad name matching, or autonomous retry.
"""
import os
import subprocess

SOURCE = 'iZ6wee8q9z4t03hvqumwfhZ'
UNITS = (
    'xuanjun-wecom-customer-service.service',
    'xuanjun-wecom-customer-contact.service',
    'xuanjun-wecom-novel-ingress.service',
)
STOP_EDGES = ('RequiredBy', 'RequisiteOf', 'BoundBy', 'ConsistsOf', 'PropagatesStopTo')


class RetirementHold(RuntimeError):
    pass


def isolate_retired_units(admit, runner=subprocess.run):
    """Check all dependency edges before stopping any of the three exact units.

    Caller owns original intent/result journaling and source-host admission.
    Nonzero/timeout after a mutation remains UNKNOWN for original reconciliation.
    """
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != SOURCE:
        raise RetirementHold('SOURCE_HOST_ROOT_REQUIRED')
    if not callable(admit) or admit(SOURCE, UNITS) is not True:
        raise RetirementHold('ORIGINAL_SOURCE_ADMISSION_REQUIRED')
    observed = {}
    for unit in UNITS:
        result = runner(
            ['/usr/bin/systemctl', 'show', unit, '--no-pager',
             '--property=' + ','.join(('LoadState', 'ActiveState', 'MainPID', *STOP_EDGES))],
            capture_output=True, timeout=15, check=False)
        if result.returncode:
            raise RetirementHold('DEPENDENCY_QUERY_FAILED_NO_STOP')
        values = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
        if values.get('LoadState') not in ('loaded', 'not-found', 'masked'):
            raise RetirementHold('UNRESOLVED_UNIT_LOAD_STATE')
        if any(key not in values for key in STOP_EDGES):
            raise RetirementHold('DEPENDENCY_PROPERTIES_INCOMPLETE')
        foreign = {name for key in STOP_EDGES for name in values[key].split() if name not in UNITS}
        if foreign:
            raise RetirementHold('STOP_COULD_PROPAGATE_TO_OTHER_UNITS')
        observed[unit] = values
    # These are the retired units only. No --recursive, dependencies or glob.
    for unit in UNITS:
        if observed[unit]['LoadState'] == 'not-found':
            continue
        if admit(SOURCE, UNITS) is not True:
            raise RetirementHold('SOURCE_ADMISSION_CHANGED')
        for operation in (['stop', '--', unit],):
            try:
                result = runner(['/usr/bin/systemctl', *operation],
                                capture_output=True, timeout=30, check=False)
            except (subprocess.TimeoutExpired, OSError):
                raise RetirementHold('RETIREMENT_EFFECT_UNKNOWN_NO_REPLAY') from None
            if result.returncode:
                raise RetirementHold('RETIREMENT_EFFECT_UNKNOWN_NO_REPLAY')
    states = {}
    for unit in UNITS:
        if observed[unit]['LoadState'] == 'not-found':
            states[unit] = 'NOT_PRESENT'
            continue
        result = runner(
            ['/usr/bin/systemctl', 'show', unit, '--no-pager',
             '--property=ActiveState,MainPID,ControlPID'],
            capture_output=True, timeout=15, check=False)
        values = dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)
        if (result.returncode or values.get('ActiveState') not in ('inactive', 'failed')
                or values.get('MainPID') != '0' or values.get('ControlPID') != '0'):
            raise RetirementHold('RETIREMENT_NOT_CONFIRMED_NO_REPLAY')
        states[unit] = 'STOPPED_AT_CHECK'
    return {'scope': 'OWNER_RETIRED_WECOM_ONLY', 'units': states,
            'data_deleted': False, 'shared_services_touched': False,
            'database_fenced': False, 'reactivation_fenced': False,
            'production_cutover': False}
