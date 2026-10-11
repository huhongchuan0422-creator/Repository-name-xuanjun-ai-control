"""Inference-free, fail-closed UK development model quota admission.

This module NEVER makes model/API calls, schedules work or mutates a ledger.
The trusted runtime must verify provenance of canonical metering exports and
call decide() BEFORE EVERY model inference (including QA/retries/coordination).
"""
from __future__ import print_function
import argparse
import datetime
import json
import math
import os
import re
import stat
import sys

POLICY_ID = 'UK_MODEL_QUOTA_30_CHAT_50_DAILY_V1'
MODEL = 'openai/gpt-5.6-sol'
DAILY_STOP_PCT = 50.0
CODEX_SWITCH_PCT = 30.0
MAX_EVIDENCE_AGE_SECONDS = 600
MAX_BYTES = 16384
TZ = datetime.timezone(datetime.timedelta(hours=8))


def _parse_instant(value):
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)', value):
        raise ValueError('INVALID_TIMESTAMP')
    match = re.fullmatch(
        r'(\\d{4}-\\d{2}-\\d{2})T(\\d{2}:\\d{2}:\\d{2})(?:\\.(\\d{1,6}))?(Z|[+-]\\d{2}:\\d{2})',
        value)
    if not match:
        raise ValueError('INVALID_TIMESTAMP')
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
    return stamp.replace(tzinfo=datetime.timezone(offset))


def _pct(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('UNKNOWN_QUOTA_PERCENT')
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise ValueError('INVALID_QUOTA_PERCENT')
    return number


def _result(status, route, reason, next_day=None):
    return {'schema': 1, 'policy': POLICY_ID, 'status': status,
            'route': route, 'reason': reason, 'may_infer': status == 'ALLOW',
            'resume_not_before': next_day, 'gate_inference_calls': 0}


def _stop_date(now):
    next_day = now.astimezone(TZ).date() + datetime.timedelta(days=1)
    return next_day.isoformat() + 'T00:00:00+08:00'


def decide(evidence, now=None):
    """Pure decision: route is permission, not proof that an inference occurred."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        raise ValueError('NOW_MUST_BE_AWARE')
    if not isinstance(evidence, dict) or evidence.get('schema') != 1:
        return _result('HOLD', 'NONE', 'EVIDENCE_SCHEMA_INVALID')
    try:
        if evidence.get('model') != MODEL or evidence.get('fallbacks') != []:
            return _result('HOLD', 'NONE', 'MODEL_POLICY_MISMATCH')
        stamp = _parse_instant(evidence.get('observed_at'))
        age = (now - stamp).total_seconds()
        if age < -60 or age > MAX_EVIDENCE_AGE_SECONDS:
            return _result('HOLD', 'NONE', 'QUOTA_EVIDENCE_STALE_OR_FUTURE')
        if evidence.get('day') != now.astimezone(TZ).date().isoformat():
            return _result('HOLD', 'NONE', 'NEW_DAY_REQUIRES_FRESH_EVIDENCE')
        if (evidence.get('quota_source') != 'AUTHORITATIVE' or
                not isinstance(evidence.get('evidence_ref'), str) or
                not re.fullmatch(r'[A-Za-z0-9._:/#-]{8,256}', evidence['evidence_ref'])):
            return _result('HOLD', 'NONE', 'QUOTA_SOURCE_NOT_ATTESTED')
        codex = _pct(evidence.get('codex_period_used_pct'))
        daily = _pct(evidence.get('daily_total_used_pct'))
        if evidence.get('daily_total_meter_verified') is not True:
            return _result('HOLD', 'NONE', 'DAILY_TOTAL_NOT_COMPARABLE')
    except (TypeError, ValueError, OverflowError) as error:
        reason = str(error)
        return _result('HOLD', 'NONE', reason if reason.isupper() else 'INVALID_EVIDENCE')

    if daily >= DAILY_STOP_PCT:
        return _result('HOLD', 'NONE', 'DAILY_50_PERCENT_LIMIT', _stop_date(now))

    if codex < CODEX_SWITCH_PCT:
        if evidence.get('codex_status') == 'AVAILABLE':
            return _result('ALLOW', 'CODEX_OAUTH', 'CODEX_BELOW_30_PERCENT')
        return _result('HOLD', 'NONE', 'CODEX_NOT_VERIFIED_AVAILABLE')

    if (evidence.get('chat_status') == 'AVAILABLE' and
            evidence.get('chat_non_codex_verified') is True and
            evidence.get('chat_entrypoint') == 'CHATGPT_NON_CODEX_CHAT' and
            isinstance(evidence.get('chat_evidence_ref'), str) and
            re.fullmatch(r'[A-Za-z0-9._:/#-]{8,256}', evidence['chat_evidence_ref'])):
        return _result('ALLOW', 'CHATGPT_NON_CODEX_CHAT', 'SWITCH_AT_CODEX_30_PERCENT')

    # Only verified chat quota exhaustion can permit a return to Codex.
    if (evidence.get('chat_status') == 'EXHAUSTED' and
            evidence.get('chat_exhaustion_verified') is True and
            isinstance(evidence.get('chat_evidence_ref'), str) and
            re.fullmatch(r'[A-Za-z0-9._:/#-]{8,256}', evidence['chat_evidence_ref']) and
            evidence.get('codex_status') == 'AVAILABLE'):
        return _result('ALLOW', 'CODEX_OAUTH', 'CHAT_EXHAUSTED_CODEX_UNDER_DAILY_CAP')

    return _result('HOLD', 'NONE', 'CHAT_ROUTE_OR_EXHAUSTION_UNVERIFIED')


def _check_path(path):
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise ValueError('UNSAFE_EVIDENCE_PATH')
    allowed = {0, os.geteuid()}
    current = '/'
    for part in path.strip('/').split('/'):
        current = os.path.join(current, part)
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or info.st_uid not in allowed:
            raise ValueError('UNTRUSTED_EVIDENCE_PATH')
        if info.st_mode & 0o022:
            raise ValueError('WRITABLE_EVIDENCE_PATH')
    if not stat.S_ISREG(os.lstat(current).st_mode):
        raise ValueError('EVIDENCE_NOT_REGULAR')


def _load_evidence(path):
    _check_path(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                 getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.geteuid()) or
                info.st_mode & 0o027 or info.st_size > MAX_BYTES):
            raise ValueError('UNSAFE_EVIDENCE_FILE')
        raw = os.read(fd, MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError('EVIDENCE_TOO_LARGE_OR_EMPTY')
        return json.loads(raw.decode('utf-8'))
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Zero-inference quota admission; exit 0 only on ALLOW')
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args(argv)
    try:
        verdict = decide(_load_evidence(args.evidence))
    except (OSError, ValueError, UnicodeError, TypeError):
        verdict = _result('HOLD', 'NONE', 'EVIDENCE_INVALID_OR_UNREADABLE')
    print(json.dumps(verdict, sort_keys=True, separators=(',', ':')))
    return 0 if verdict['may_infer'] else 3


if __name__ == '__main__':
    sys.exit(main())
