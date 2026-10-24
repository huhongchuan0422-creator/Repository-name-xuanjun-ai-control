"""Non-secret expiry watch using the existing Queue/outbox, not key creation.

The caller supplies approved metadata, not a secret or a browser session. No
rotation, permission grant, perpetual expiry or provider API is performed here.
"""
import calendar
import datetime
import hashlib
import json

from .queue import Hold, SHA, TOKEN, canonical
from .private_transfer import strict, check


def utc(text):
    check(type(text) is str, 'UTC_REQUIRED')
    try:
        d = datetime.datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        raise Hold('EXACT_UTC_REQUIRED') from None
    check(d.strftime('%Y-%m-%dT%H:%M:%SZ') == text, 'EXACT_UTC_REQUIRED')
    return calendar.timegm(d.timetuple())


def evaluate(raw, approved_sha, now):
    check(type(raw) is bytes and len(raw) <= 131072 and type(approved_sha) is str and SHA.fullmatch(approved_sha)
          and hashlib.sha256(raw).hexdigest() == approved_sha, 'EXPIRY_METADATA_BINDING')
    v = strict(raw)
    check(type(v) is dict and set(v) == {'schema', 'credential_ref', 'generation',
          'expiry_date', 'expires_at_utc', 'verified_at_utc', 'source_ref'}, 'EXPIRY_METADATA_FIELDS')
    check(type(v['schema']) is int and v['schema'] == 1 and type(now) is int, 'EXPIRY_SCHEMA')
    for k in ('credential_ref', 'generation', 'source_ref'):
        check(type(v[k]) is str and TOKEN.fullmatch(v[k]), 'EXPIRY_REFERENCE')
    verified = utc(v['verified_at_utc'])
    check(verified <= now and now - verified <= 45 * 86400, 'EXPIRY_EVIDENCE_STALE_OR_FUTURE')
    date = v['expiry_date']
    check(type(date) is str, 'EXPIRY_DATE')
    midnight = utc(date + 'T00:00:00Z')
    if v['expires_at_utc'] is None:
        # Display timezone and time-of-day are unknown. Stop conservatively one
        # UTC day earlier; do not invent an exact provider expiry timestamp.
        stop, precision = midnight - 86400, 'DATE_ONLY_CONSERVATIVE_STOP'
    else:
        stop, precision = utc(v['expires_at_utc']), 'EXACT_UTC'
        check(abs(stop - midnight) <= 2 * 86400, 'EXPIRY_DATE_CONFLICT')
    remaining = stop - now
    if remaining <= 0:
        level = 'STOP_EXPIRED_OR_CONSERVATIVE_BOUND'
    elif remaining <= 86400:
        level = 'WARN_1_DAY'
    elif remaining <= 3 * 86400:
        level = 'WARN_3_DAYS'
    elif remaining <= 7 * 86400:
        level = 'WARN_7_DAYS'
    elif remaining <= 14 * 86400:
        level = 'WARN_14_DAYS'
    else:
        level = 'TRACKED_NOT_DUE'
    return {'schema': 1, 'credential_ref': v['credential_ref'], 'generation': v['generation'],
            'precision': precision, 'provider_expiry_date': date,
            'conservative_stop_unix': stop, 'observed_unix': now, 'state': level,
            'automatic_rotation': 'NOT_IMPLEMENTED', 'source_ref': v['source_ref']}


def record_on_existing_queue(db, raw, approved_sha, now):
    """Persist alert once per generation/threshold into original outbox.

    No POST here: original Loop.flush owns delivery and UNKNOWN handling. The
    installed daemon does not call this candidate until normal source admission.
    """
    result = evaluate(raw, approved_sha, now)
    check(not db.in_transaction, 'CALLER_TRANSACTION_ACTIVE')
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('SELECT request_id FROM connection_jobs LIMIT 1')
        db.execute('SELECT request_id FROM connection_outbox LIMIT 1')
        db.execute('CREATE TABLE IF NOT EXISTS connection_credential_watch '
                   '(credential_ref TEXT NOT NULL,generation TEXT NOT NULL,metadata_sha TEXT NOT NULL,last_seen INTEGER NOT NULL,'
                   'PRIMARY KEY(credential_ref,generation))')
        db.execute('CREATE TRIGGER IF NOT EXISTS connection_credential_no_replace BEFORE INSERT ON connection_credential_watch '
                   'WHEN EXISTS(SELECT 1 FROM connection_credential_watch WHERE credential_ref=NEW.credential_ref AND generation=NEW.generation) '
                   "BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CREDENTIAL_HISTORY'); END")
        db.execute('CREATE TRIGGER IF NOT EXISTS connection_credential_no_rebind BEFORE UPDATE OF credential_ref,generation,metadata_sha '
                   "ON connection_credential_watch BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CREDENTIAL_HISTORY'); END")
        db.execute('CREATE TRIGGER IF NOT EXISTS connection_credential_no_delete BEFORE DELETE ON connection_credential_watch '
                   "BEGIN SELECT RAISE(ABORT,'IMMUTABLE_CREDENTIAL_HISTORY'); END")
        db.execute('CREATE TRIGGER IF NOT EXISTS connection_credential_no_clock_rollback BEFORE UPDATE OF last_seen ON connection_credential_watch '
                   "WHEN NEW.last_seen<OLD.last_seen BEGIN SELECT RAISE(ABORT,'CREDENTIAL_CLOCK_ROLLBACK'); END")
        key = (result['credential_ref'], result['generation'])
        row = db.execute('SELECT metadata_sha,last_seen FROM connection_credential_watch '
                         'WHERE credential_ref=? AND generation=?', key).fetchone()
        if row:
            check(row[0] == approved_sha, 'CREDENTIAL_GENERATION_REBOUND')
            check(now >= row[1], 'CLOCK_ROLLBACK_HOLD')
            db.execute('UPDATE connection_credential_watch SET last_seen=? WHERE credential_ref=? AND generation=?', (now,) + key)
        else:
            db.execute('INSERT INTO connection_credential_watch VALUES(?,?,?,?)', key + (approved_sha, now))
        if result['state'] != 'TRACKED_NOT_DUE':
            outkey = 'credential-' + hashlib.sha256(canonical([key, result['state']]).encode()).hexdigest()
            old = db.execute('SELECT state FROM connection_outbox WHERE request_id=?', (outkey,)).fetchone()
            if old is None:
                db.execute("INSERT INTO connection_outbox VALUES(?,?,'READY',NULL)",
                           (outkey, 'XJ_CREDENTIAL_EXPIRY_V1\n' + canonical(result)))
            # In particular, never turn POSTING/UNKNOWN into READY after restart.
        db.commit()
        return result
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
