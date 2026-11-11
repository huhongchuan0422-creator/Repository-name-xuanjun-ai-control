"""Read-transaction adapters for reviewed foundations; no runtime authority.

Dependencies are SHA-pinned by bootstrap.py. The trusted caller owns SQLite
and authenticates external receipt envelopes; this module never opens a DB,
creates tables, sends alerts, assigns leases, or approves execution.
"""
import hashlib
import json
import math
import re

from task_cost_projection import project_costs
from run_usage_projection import usage_projection
from dependency_evidence_view import dependency_view
from resume_prerequisite_view import resume_view
from human_alert_payload import alert_payload
from handoff_evidence_view import handoff_view
from canary_evidence_coverage import evaluate_coverage

KINDS = ('costs', 'usage', 'dependencies', 'resume', 'alert', 'handoff', 'canary')
BINDING = {'task_id', 'spec_sha256', 'checkpoint_sha256', 'commit',
           'artifact_sha256', 'fence', 'epoch'}
LABELS = {'costs': '任务费用', 'usage': '运行用量', 'dependencies': '依赖证据',
          'resume': '恢复前置', 'alert': '人工告警', 'handoff': '执行权交接',
          'canary': '端到端验收'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value)


def validate_binding(binding):
    if not isinstance(binding, dict) or set(binding) != BINDING:
        raise ValueError('INVALID_BINDING')
    for key, value in binding.items():
        if key in ('fence', 'epoch'):
            valid = type(value) is int and 0 <= value <= 2 ** 63 - 1
        elif key == 'task_id':
            valid = _identifier(value)
        else:
            valid = isinstance(value, str) and re.fullmatch(
                '[a-f0-9]{%d}' % (40 if key == 'commit' else 64), value)
        if not valid:
            raise ValueError('INVALID_BINDING')


def _strict_json(raw):
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 65536:
        raise ValueError('INVALID_CANONICAL_JSON')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_CANONICAL_KEY')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError('NON_FINITE')))
    except (RecursionError, UnicodeError):
        raise ValueError('INVALID_CANONICAL_JSON')


def _transaction(db):
    if not db.in_transaction or db.execute('PRAGMA query_only').fetchone()[0] != 1:
        raise ValueError('CALLER_READ_TRANSACTION_REQUIRED')
    schema = list(db.execute('PRAGMA table_info(tasks)'))
    columns = {row[1] for row in schema}
    if not {'id', 'state', 'fence', 'checkpoint', 'depends'} <= columns:
        raise ValueError('CANONICAL_SCHEMA_UNAVAILABLE')
    if not any(row[1] == 'id' and row[2].upper() == 'TEXT' and row[5] == 1 for row in schema):
        raise ValueError('CANONICAL_UNIQUE_TASK_ID_REQUIRED')
    if not {'task_id', 'hash'} <= {row[1] for row in db.execute('PRAGMA table_info(execution_specs)')}:
        raise ValueError('CANONICAL_SPEC_SCHEMA_UNAVAILABLE')


def canonical_page(db, after_id=None, limit=100):
    """Keyset page in caller's SAME transaction, never a persisted new queue."""
    _transaction(db)
    if type(limit) is not int or not 1 <= limit <= 200 or (
            after_id is not None and not _identifier(after_id)):
        raise ValueError('INVALID_PAGE')
    rows = db.execute('SELECT id,state,fence,checkpoint,depends FROM tasks '
                      'WHERE id>? ORDER BY id LIMIT ?',
                      (after_id or '', limit + 1)).fetchall()
    result = []
    for identity, state, fence, checkpoint, depends in rows[:limit]:
        # Invalid rows remain visible and cannot hide subsequent pages.
        valid_id = bool(_identifier(identity))
        result.append({'id': identity if valid_id else None,
                       'state': state if isinstance(state, str) and re.fullmatch('[A-Z_]{1,40}', state) else 'UNKNOWN',
                       'fence': fence if type(fence) is int and 0 <= fence <= 2 ** 63 - 1 else None,
                       'checkpoint_sha256': hashlib.sha256(checkpoint.encode()).hexdigest()
                           if isinstance(checkpoint, str) and len(checkpoint.encode()) <= 65536 else None,
                       'depends': _dependencies(depends),
                       'row_valid': valid_id and type(fence) is int and fence >= 0})
    more = len(rows) > limit
    cursor = rows[limit - 1][0] if more else None
    if more and not _identifier(cursor):
        raise ValueError('INVALID_CANONICAL_CURSOR')
    return {'tasks': result, 'has_more': more, 'next_after_id': cursor,
            'snapshot_scope': 'CALLER_SAME_READ_TRANSACTION',
            'execution_granted': False}


def _dependencies(raw):
    try:
        value = _strict_json(raw)
        if (isinstance(value, list) and len(value) <= 100 and
                all(_identifier(x) for x in value) and len(set(value)) == len(value)):
            return value
    except (ValueError, TypeError):
        pass
    return None


def _hold(reason):
    return {'status': 'HOLD', 'reasons': [reason], 'execution_granted': False}


def bound_receipt(kind, binding, envelope, verifier, now):
    """Verifier comes from trusted runtime, NEVER from uploaded JSON."""
    validate_binding(binding)
    if kind not in KINDS or type(now) not in (int, float) or not math.isfinite(now) or now < 0:
        raise ValueError('INVALID_RECEIPT_CONTEXT')
    if (not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'}
            or not callable(verifier)):
        raise ValueError('AUTHENTICATED_RECEIPT_REQUIRED')
    payload = envelope['payload']
    if isinstance(payload, dict):
        validate_binding(payload.get('binding'))
    if (not isinstance(payload, dict) or set(payload) != {'binding', 'kind', 'observed_at', 'data'}
            or payload['binding'] != binding or payload['kind'] != kind):
        raise ValueError('RECEIPT_BINDING_MISMATCH')
    stamp = payload['observed_at']
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or not 0 <= stamp <= now or now - stamp > 300:
        raise ValueError('RECEIPT_STALE')
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False,
                     separators=(',', ':')).encode()
    if len(raw) > 262144:
        raise ValueError('RECEIPT_TOO_LARGE')
    if verifier(raw, envelope['signature']) is not True:
        raise ValueError('RECEIPT_UNAUTHENTICATED')
    return payload['data']


def foundation_snapshot(db, binding, now, receipts, verifier, workspace_origin=None, max_tasks=1000):
    """One task's seven views from existing ledger + authenticated receipts.

    Missing producer evidence stays HOLD. Receipt evidence is not accepted
    merely because its digest exists. Results are display-only, even when all
    inputs are valid; existing canonical controller must recheck before writes.
    """
    validate_binding(binding)
    _transaction(db)
    if (type(now) not in (int, float) or not math.isfinite(now) or now < 0 or
            type(max_tasks) is not int or not 1 <= max_tasks <= 1000 or
            not isinstance(receipts, dict) or set(receipts) - set(KINDS)):
        raise ValueError('INVALID_SNAPSHOT_INPUT')
    query = ('SELECT t.fence,t.checkpoint,s.hash FROM tasks t '
             'LEFT JOIN execution_specs s ON s.task_id=t.id WHERE t.id=?')
    row = db.execute(query, (binding['task_id'],)).fetchone()
    if row is None or type(row[0]) is not int or row[0] != binding['fence'] or not isinstance(row[1], str) or len(row[1].encode()) > 65536:
        raise ValueError('CANONICAL_TASK_BINDING_MISMATCH')
    if hashlib.sha256(row[1].encode()).hexdigest() != binding['checkpoint_sha256']:
        raise ValueError('CANONICAL_CHECKPOINT_CHANGED')
    if row[2] != binding['spec_sha256']:
        raise ValueError('CANONICAL_SPEC_CHANGED')
    # Canonical checkpoint hashes do not authenticate spec/release/epoch.
    # Those dimensions remain trusted caller binding + verified receipt input.
    tasks = []; after = None; complete = False
    while len(tasks) < max_tasks:
        page = canonical_page(db, after, min(100, max_tasks - len(tasks)))
        tasks.extend(page['tasks'])
        if not page['has_more']:
            complete = True; break
        after = page['next_after_id']
    views = {}
    for kind in KINDS:
        try:
            data = bound_receipt(kind, binding, receipts[kind], verifier, now) if kind in receipts else None
            if kind == 'costs':
                views[kind] = project_costs(binding['task_id'], [] if data is None else data)
            elif kind == 'usage':
                views[kind] = usage_projection([] if data is None else data)
            elif kind == 'dependencies':
                if not complete:
                    views[kind] = _hold('DEPENDENCY_GRAPH_INCOMPLETE')
                else:
                    # No canonical acceptance producer in frozen102. DO NOT
                    # promote DONE or a supplied digest to ACCEPTED.
                    nodes = {t['id']: {'dependencies': t['depends'], 'state': t['state'],
                                      'evidence_sha256': None} for t in tasks if t['id'] is not None}
                    views[kind] = dependency_view(binding['task_id'], nodes)
            elif data is None:
                views[kind] = _hold('AUTHENTICATED_PRODUCER_MISSING')
            elif kind == 'resume':
                if not isinstance(data, dict) or data.get('binding_sha256') != digest(binding):
                    raise ValueError('RESUME_BINDING_MISMATCH')
                views[kind] = resume_view(data, now)
            elif kind == 'alert':
                if not isinstance(data, dict) or set(data) != {'reason', 'deadline'} or workspace_origin is None:
                    raise ValueError('ALERT_CONTEXT_MISSING')
                views[kind] = alert_payload(binding['task_id'], data['reason'], data['deadline'], workspace_origin)
                views[kind]['status'] = 'PAYLOAD_READY_NOT_SENT'
            elif kind == 'handoff':
                expected = {key: binding[key] for key in ('task_id', 'spec_sha256', 'checkpoint_sha256', 'commit', 'artifact_sha256')}
                views[kind] = handoff_view(expected, data)
            elif kind == 'canary':
                views[kind] = evaluate_coverage(binding['commit'], binding['artifact_sha256'], data)
        except (ValueError, TypeError, KeyError, RecursionError):
            # Parser/verification messages and arbitrary source fields are not
            # reflected into Owner/notification output.
            views[kind] = _hold('INVALID_OR_UNVERIFIED_' + kind.upper() + '_EVIDENCE')
    _transaction(db)
    if db.execute(query, (binding['task_id'],)).fetchone() != row:
        raise ValueError('CANONICAL_BINDING_CHANGED_DURING_READ')
    return {'schema': 'WORK_FOUNDATION_INTEGRATION_V1', 'binding_sha256': digest(binding),
            'views': views, 'task_count_observed': len(tasks), 'scan_complete': complete,
            'remaining_count': None if not complete else 0, 'next_after_id': after if not complete else None,
            'status': 'HOLD' if any(v.get('status') == 'HOLD' for v in views.values()) else 'VIEWS_READY_NOT_ADMITTED',
            'execution_granted': False, 'resume_granted': False, 'release_granted': False,
            'send_performed': False, 'snapshot_scope': 'CALLER_SAME_READ_TRANSACTION'}


def chinese_summary(snapshot):
    """Fixed Chinese labels/statuses only; never interpolate free-form data."""
    if not isinstance(snapshot, dict) or snapshot.get('schema') != 'WORK_FOUNDATION_INTEGRATION_V1' or not isinstance(snapshot.get('views'), dict) or set(snapshot['views']) != set(KINDS):
        raise ValueError('INVALID_FOUNDATION_SNAPSHOT')
    return [{'项目': LABELS[kind], '状态': '待核验' if snapshot['views'][kind].get('status') == 'HOLD' else '证据视图已生成',
             '执行授权': False} for kind in KINDS]
