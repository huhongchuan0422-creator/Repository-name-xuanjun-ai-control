"""Unwired P3 candidate: atomic ledger authority check and receipt consumption.

NOT an endpoint or signature verifier. Caller MUST first verify the complete P3
receipt and its trust/owner/issuer binding. Never use until that binding and the
cross-role exclusion protocol are implemented and independently reviewed.
Schema installation is explicit and must not be run against production here.
"""
import re
import sqlite3

from development_authority import authority_payload


def install_candidate_schema(db):
    db.execute('''CREATE TABLE p3_consumed_receipts_candidate (
        nonce TEXT PRIMARY KEY, receipt_sha256 TEXT NOT NULL UNIQUE,
        task_id TEXT NOT NULL, attempt_id TEXT NOT NULL, lease_id TEXT NOT NULL,
        fence INTEGER NOT NULL, epoch INTEGER NOT NULL, consumed_at REAL NOT NULL,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id))''')


def consume_verified_receipt_candidate(db, *, nonce, receipt_sha256, request,
                                       trust, assignment, now):
    """Serialize nonce/digest CAS with task/claim check in the SAME SQLite DB.

    Preconditions: db is the canonical writable ledger, no active transaction;
    caller has independently verified P3 signature and all bindings. A commit
    means consumed even if the caller subsequently crashes; never retry effects
    without reconciliation. This alone does not grant registration authority.
    """
    if db.in_transaction:
        raise ValueError('TRANSACTION_MUST_BE_OWNED')
    if (not isinstance(nonce, str) or not nonce or len(nonce) > 512 or
            not isinstance(receipt_sha256, str) or
            not re.fullmatch(r'[0-9a-f]{64}', receipt_sha256)):
        raise ValueError('INVALID_RECEIPT_IDENTITY')
    fields = {'attempt_id', 'lease_id', 'fence', 'epoch', 'resource_scope_digest'}
    if not isinstance(assignment, dict) or set(assignment) != fields:
        raise ValueError('EXACT_ASSIGNMENT_REQUIRED')
    try:
        db.execute('BEGIN IMMEDIATE')
        payload = authority_payload(db, request, trust, now=now)
        if not payload['authority']['authorized']:
            raise ValueError('AUTHORITY_NOT_VALID')
        if any(payload['assignment'][k] != assignment[k] for k in fields):
            raise ValueError('ASSIGNMENT_MISMATCH')
        db.execute('INSERT INTO p3_consumed_receipts_candidate VALUES(?,?,?,?,?,?,?,?)',
                   (nonce, receipt_sha256, request['task_id'], assignment['attempt_id'],
                    assignment['lease_id'], assignment['fence'], assignment['epoch'], now))
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise ValueError('RECEIPT_ALREADY_CONSUMED') from exc
    except BaseException:
        db.rollback()
        raise
