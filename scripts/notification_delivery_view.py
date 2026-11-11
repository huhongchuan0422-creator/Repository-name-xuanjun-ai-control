"""Read-only diagnostics over existing canonical supervision delivery tables."""
import math
import re


DELIVERY_COLUMNS = ('event_key', 'destination', 'state', 'attempts',
                    'next_attempt_at', 'authority_fence', 'authority_epoch',
                    'receipt_id', 'send_attempts', 'claim_until')
EVENT_COLUMNS = ('event_key', 'task_id', 'kind', 'sequence')
STATES = ('PENDING', 'DELIVERY_FAILED', 'CLAIMED', 'SENDING',
          'SENDING_UNCERTAIN', 'ACKED', 'HELD', 'DEAD_LETTER')


def _integer(value):
    return type(value) is int and 0 <= value <= 2 ** 63 - 1


def _time(value):
    return (type(value) in (int, float) and 0 <= value <= 10 ** 15
            and math.isfinite(value))


def _text(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _cursor(value):
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and _text(value[0], r'[A-Za-z0-9_.:-]{1,300}')
            and _text(value[1], r'[A-Z0-9_]{1,64}'))


def delivery_page(db, now, expected_authority, limit=100, after=None,
                  read_authority=None):
    """Observe a page without claiming, retrying, acknowledging or creating DBs.

    expected_authority is caller-verified generation/epoch. Delivery column
    authority_fence stores tasks.fence; generation is rechecked separately.
    Keep one caller-owned transaction across pages for a consistent scan.
    """
    if not db.in_transaction:
        raise ValueError('CALLER_TRANSACTION_REQUIRED')
    if not _time(now) or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('INVALID_VIEW_BOUND')
    if (not isinstance(expected_authority, dict) or
            set(expected_authority) != {'generation', 'epoch'} or
            any(not _integer(v) or v < 1 for v in expected_authority.values())):
        raise ValueError('VERIFIED_AUTHORITY_REQUIRED')
    expected_authority = dict(expected_authority)
    if after is not None and not _cursor(after):
        raise ValueError('INVALID_CURSOR')
    if not callable(read_authority):
        raise ValueError('ACTIVATION_RECHECK_REQUIRED')
    def check_authority():
        current = read_authority()
        if (not isinstance(current, dict) or set(current) != {'generation', 'epoch'}
                or any(type(v) is not int for v in current.values())
                or current != expected_authority):
            raise ValueError('ACTIVATION_CHANGED')
    check_authority()
    for table, required in (('supervision_delivery', DELIVERY_COLUMNS),
                            ('supervision_events', EVENT_COLUMNS),
                            ('tasks', ('id', 'fence'))):
        columns = {row[1] for row in db.execute('PRAGMA table_info(' + table + ')')}
        if not set(required) <= columns:
            raise ValueError('EXISTING_SUPERVISION_SCHEMA_REQUIRED')
    query = ('SELECT ' + ','.join('d.' + key for key in DELIVERY_COLUMNS) +
             ',e.task_id,e.kind,e.sequence,t.fence FROM supervision_delivery d'
             ' LEFT JOIN supervision_events e ON e.event_key=d.event_key'
             ' LEFT JOIN tasks t ON t.id=e.task_id')
    args = []
    if after is not None:
        query += ' WHERE (d.event_key > ? OR (d.event_key = ? AND d.destination > ?))'
        args.extend((after[0], after[0], after[1]))
    query += ' ORDER BY d.event_key,d.destination LIMIT ?'
    args.append(limit + 1)
    source = db.execute(query, args).fetchall()
    output = []
    for values in source[:limit]:
        row = dict(zip(DELIVERY_COLUMNS + ('task_id', 'kind', 'sequence', 'task_fence'), values))
        if not _cursor((row['event_key'], row['destination'])):
            raise ValueError('CORRUPT_DELIVERY_IDENTITY')
        warnings = []
        task_id = row['task_id']
        if not _text(task_id, r'[A-Za-z0-9_.:-]{1,160}'):
            task_id = None
            warnings.append('MISSING_OR_INVALID_EVENT_TASK')
        if task_id is not None:
            kind, sequence = row['kind'], row['sequence']
            metadata_valid = (_text(kind, r'[A-Za-z0-9_.-]{1,80}') and
                              _integer(sequence) and sequence >= 1)
            key_valid = False
            if metadata_valid:
                prefix = task_id + ':inventory:'
                key_valid = (row['event_key'] == task_id + ':terminal:' + kind or
                             row['event_key'] == '%s:%s:%d' % (task_id, kind, sequence) or
                             (row['event_key'].startswith(prefix) and
                              _text(row['event_key'][len(prefix):], r'[a-f0-9]{64}')))
            if not key_valid:
                warnings.append('EVENT_KEY_BINDING_MISMATCH')
        state = row['state'] if row['state'] in STATES else 'UNKNOWN'
        attempts = row['attempts'] if _integer(row['attempts']) else None
        sends = row['send_attempts'] if _integer(row['send_attempts']) else None
        if state == 'UNKNOWN' or attempts is None or sends is None:
            warnings.append('UNKNOWN_DELIVERY_EVIDENCE')
        authority_ok = (_integer(row['task_fence']) and
                        type(row['authority_fence']) is int and
                        type(row['authority_epoch']) is int and
                        row['authority_fence'] == row['task_fence'] and
                        row['authority_epoch'] == expected_authority['epoch'])
        if not authority_ok:
            warnings.append('STALE_OR_UNKNOWN_AUTHORITY')
        receipt = row['receipt_id']
        receipt_present = isinstance(receipt, str) and 0 < len(receipt.strip()) <= 512
        classification = 'UNKNOWN'
        if state == 'ACKED':
            classification = 'ACK_RECORDED' if receipt_present else 'ACK_EVIDENCE_MISSING'
            if not receipt_present:
                warnings.append('ACK_EVIDENCE_MISSING')
        elif state in ('PENDING', 'DELIVERY_FAILED'):
            due = row['next_attempt_at']
            if _time(due):
                classification = 'RETRY_DUE' if due <= now else 'WAITING_RETRY'
            else:
                warnings.append('UNKNOWN_RETRY_TIME')
        elif state == 'CLAIMED':
            until = row['claim_until']
            if _time(until):
                classification = 'CLAIM_ACTIVE' if until > now else 'CLAIM_EXPIRED'
            else:
                warnings.append('UNKNOWN_CLAIM_TIME')
        elif state in ('SENDING', 'SENDING_UNCERTAIN'):
            classification = 'RECONCILIATION_REQUIRED'
        elif state in ('HELD', 'DEAD_LETTER'):
            classification = 'MANUAL_REVIEW_REQUIRED'
        output.append({'event_key': row['event_key'], 'destination': row['destination'],
                       'task_id': task_id, 'state': state, 'attempts': attempts,
                       'send_attempts': sends, 'classification': classification,
                       'receipt_present': receipt_present, 'warnings': warnings,
                       'status': 'HOLD' if warnings else 'OBSERVED',
                       'external_delivery_verified': False})
    check_authority()
    more = len(source) > limit
    cursor = [output[-1]['event_key'], output[-1]['destination']] if more else None
    return {'schema': 'NOTIFICATION_DELIVERY_VIEW_V1', 'observed_at': now,
            'items': output, 'has_more': more, 'next_cursor': cursor,
            'counts_scope': 'THIS_PAGE_ONLY', 'returned_count': len(output),
            'canonical_mutation': False, 'send_performed': False,
            'authority_verification': 'CALLER_REQUIRED'}
