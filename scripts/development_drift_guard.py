"""Pure budget/identity drift preflight; no authority or runtime side effects."""
import math
import re


IDENTITY = ('task_id', 'spec_sha256', 'checkpoint_sha256', 'base_commit',
            'run_id', 'lease_owner', 'epoch', 'fence')
BUDGETS = ('active_agents', 'heavy_agents', 'delegation_depth', 'patch_attempts',
           'model_calls', 'cpu_seconds', 'memory_mib')


def _integer(value):
    return type(value) is int and 0 <= value <= 2 ** 63 - 1


def _time(value):
    return (type(value) in (int, float) and 0 <= value <= 10 ** 15
            and math.isfinite(value))


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value)


def _identity(value):
    if not isinstance(value, dict) or set(value) != set(IDENTITY):
        return False
    for key in IDENTITY:
        entry = value[key]
        if key in ('epoch', 'fence'):
            if not _integer(entry):
                return False
        elif key in ('spec_sha256', 'checkpoint_sha256', 'base_commit'):
            length = 40 if key == 'base_commit' else 64
            if not isinstance(entry, str) or not re.fullmatch('[a-f0-9]{%s}' % length, entry):
                return False
        elif not _identifier(entry):
            return False
    return True


def _budgets(value):
    return (isinstance(value, dict) and set(value) == set(BUDGETS)
            and all(_integer(value[key]) for key in BUDGETS)
            and value['heavy_agents'] <= value['active_agents'])


def _permissions(value):
    return (isinstance(value, list) and len(value) <= 100
            and all(_identifier(item) for item in value)
            and len(set(value)) == len(value))


def evaluate_drift(contract, observation, now):
    """Fail closed on malformed, incomplete, stale or mismatched observations.

    Trusted caller supplies verified contract and fresh complete counters from
    existing canonical collector, including stopped/completed patch attempts.
    Permissions are exact capability IDs, never prefix/glob expressions.
    MATCH is informational; this module cannot authenticate or admit a writer.
    """
    reasons = []
    contract_keys = {'schema', 'identity', 'limits', 'allowed_permissions', 'max_age_seconds'}
    observed_keys = {'schema', 'identity', 'usage', 'permissions', 'observed_at', 'complete'}
    contract_valid = (isinstance(contract, dict) and set(contract) == contract_keys
                      and contract.get('schema') == 'DRIFT_CONTRACT_V1'
                      and _identity(contract.get('identity'))
                      and _budgets(contract.get('limits'))
                      and _permissions(contract.get('allowed_permissions'))
                      and type(contract.get('max_age_seconds')) is int
                      and 1 <= contract['max_age_seconds'] <= 3600)
    observed_valid = (isinstance(observation, dict) and set(observation) == observed_keys
                      and observation.get('schema') == 'DRIFT_OBSERVATION_V1'
                      and _identity(observation.get('identity'))
                      and _budgets(observation.get('usage'))
                      and _permissions(observation.get('permissions'))
                      and _time(observation.get('observed_at'))
                      and observation.get('complete') is True)
    if not contract_valid:
        reasons.append('INVALID_CONTRACT')
    if not observed_valid:
        reasons.append('INCOMPLETE_OR_INVALID_OBSERVATION')
    if not _time(now):
        reasons.append('INVALID_CLOCK')
    if contract_valid and observed_valid and _time(now):
        age = now - observation['observed_at']
        if age < 0 or age > contract['max_age_seconds']:
            reasons.append('STALE_OR_FUTURE_OBSERVATION')
        for key in IDENTITY:
            if contract['identity'][key] != observation['identity'][key]:
                reasons.append('IDENTITY_MISMATCH_' + key.upper())
        for key in BUDGETS:
            if observation['usage'][key] > contract['limits'][key]:
                reasons.append('BUDGET_EXCEEDED_' + key.upper())
        if not set(observation['permissions']) <= set(contract['allowed_permissions']):
            reasons.append('PERMISSION_EXPANSION')
    return {'schema': 'DRIFT_RESULT_V1', 'status': 'HOLD' if reasons else 'MATCH',
            'reasons': sorted(reasons), 'execution_granted': False,
            'dispatch_performed': False, 'runtime_enforcement': 'NOT_PERFORMED',
            'authority_verification': 'CALLER_REQUIRED',
            'path_and_signature_review': 'EXISTING_ENTRY_REVIEW_GATE_REQUIRED'}
