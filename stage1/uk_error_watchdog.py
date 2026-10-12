"""Zero-inference repetition watchdog; pure advisory decision for existing ledger.

No retries, model invocations, notifications, writes, or privileged actions.
Caller verifies evidence provenance from the *existing* canonical task ledger,
then persists verdict and routes one idempotent Owner alert via existing outbox.
"""
import datetime
import hashlib
import json
import re

POLICY = 'UK_ERROR_30M_ALERT_60M_HOLD_V1'
OWNER_ALERT_SECONDS = 30 * 60
METHOD_HOLD_SECONDS = 60 * 60
UTC = datetime.timezone.utc

def _timestamp(value):
    """Offset-aware ISO 8601 timestamps; Python 3.6 compatible."""
    if not isinstance(value, str):
        raise ValueError('TIMESTAMP_REQUIRED')
    match = re.fullmatch(
        r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})',
        value)
    if not match:
        raise ValueError('TIMESTAMP_FORMAT_INVALID')
    stamp = datetime.datetime.strptime(match.group(1) + 'T' + match.group(2),
                                       '%Y-%m-%dT%H:%M:%S')
    if match.group(3):
        stamp = stamp.replace(microsecond=int(match.group(3).ljust(6, '0')))
    suffix = match.group(4)
    if suffix == 'Z':
        offset = datetime.timedelta(0)
    else:
        hours, minutes = int(suffix[1:3]), int(suffix[4:6])
        if hours > 23 or minutes > 59:
            raise ValueError('INVALID_UTC_OFFSET')
        offset = datetime.timedelta(hours=hours, minutes=minutes)
        if suffix[0] == '-':
            offset = -offset
    return stamp.replace(tzinfo=datetime.timezone(offset)).astimezone(UTC)


def _verdict(status, reason, elapsed=None, keys=None, alternative=False):
    return {
        'schema': 1, 'policy': POLICY, 'status': status, 'reason': reason,
        'elapsed_seconds': elapsed, 'notify_owner_keys': keys or [],
        'must_assess_alternative': alternative,
        'may_retry_same_method': status in ('OBSERVE', 'ALERT_30M'),
        'model_inference_calls': 0
    }


def evaluate(evidence, now=None):
    """Always fail closed on inconsistent root-cause or canonical-ledger evidence."""
    now = now or datetime.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError('NOW_MUST_HAVE_TIMEZONE')
    try:
        if not isinstance(evidence, dict) or evidence.get('schema') != 1:
            raise ValueError('SCHEMA_INVALID')
        if evidence.get('ledger_verified') is not True:
            raise ValueError('CANONICAL_LEDGER_NOT_VERIFIED')
        task = evidence.get('task_id')
        if not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', task):
            raise ValueError('TASK_INVALID')
        spec = evidence.get('spec_sha256')
        failure = evidence.get('failure_sha256')
        if not isinstance(spec, str) or re.fullmatch(r'[0-9a-f]{64}', spec) is None:
            raise ValueError('SPEC_HASH_INVALID')
        if not isinstance(failure, str) or re.fullmatch(r'[0-9a-f]{64}', failure) is None:
            raise ValueError('ROOT_CAUSE_HASH_INVALID')
        first = _timestamp(evidence.get('first_seen_at'))
        last = _timestamp(evidence.get('last_seen_at'))
        if last < first or last > now.astimezone(UTC) + datetime.timedelta(seconds=60):
            raise ValueError('INCIDENT_TIME_INCONSISTENT')
        if first > now.astimezone(UTC) + datetime.timedelta(seconds=60):
            raise ValueError('FUTURE_INCIDENT')
        attempts = evidence.get('attempt_count')
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
            raise ValueError('ATTEMPT_COUNT_INVALID')
        if not isinstance(evidence.get('resolved'), bool):
            raise ValueError('RESOLUTION_STATUS_INVALID')
        sent30 = evidence.get('alert30_delivered')
        sent60 = evidence.get('alert60_delivered')
        if not isinstance(sent30, bool) or not isinstance(sent60, bool):
            raise ValueError('DELIVERY_STATE_INVALID')
        if sent60 and not sent30:
            # 60m report can replace a missed 30m report but delivery bookkeeping
            # must remain explicit; do not invent 30m acknowledgment.
            pass
    except (ValueError, TypeError, OverflowError) as error:
        return _verdict('HOLD_ERROR_EVIDENCE_INVALID', str(error))

    elapsed = max(0, int((now - first).total_seconds()))
    if evidence['resolved']:
        # A source flag alone is NOT a durable resolution proof.
        if not isinstance(evidence.get('resolution_evidence_sha256'), str) or not re.fullmatch(
                r'[0-9a-f]{64}', evidence['resolution_evidence_sha256']):
            return _verdict('HOLD_ERROR_EVIDENCE_INVALID',
                            'RESOLUTION_NOT_EVIDENCED', elapsed)
        return _verdict('RESOLVED', 'DURABLE_RESOLUTION_EVIDENCE_RECORDED', elapsed)

    keybase = (task + '\n' + spec + '\n' + failure + '\n' +
               first.isoformat()).encode('utf-8')
    def key(minutes):
        return hashlib.sha256(keybase + ('\nMILESTONE_%d' % minutes).encode('ascii')).hexdigest()

    if elapsed >= METHOD_HOLD_SECONDS:
        notify = []
        if not sent30:
            notify.append(key(30))
        if not sent60:
            notify.append(key(60))
        return _verdict('HOLD_METHOD_CHANGE_REQUIRED', 'SAME_ROOT_CAUSE_60_MINUTES',
                        elapsed, notify, alternative=True)

    if elapsed >= OWNER_ALERT_SECONDS:
        return _verdict('ALERT_30M', 'SAME_ROOT_CAUSE_30_MINUTES', elapsed,
                        [] if sent30 else [key(30)], alternative=True)

    return _verdict('OBSERVE', 'UNDER_30_MINUTES', elapsed)
