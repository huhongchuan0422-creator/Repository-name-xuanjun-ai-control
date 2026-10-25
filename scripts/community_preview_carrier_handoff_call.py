"""Thin call adapter for the fixed original installation entry.

This is intentionally not a CLI. The trusted original entry must pass its already
acquired FDs, identity witnesses, historical bindings and fixed candidate bytes.
This module creates no authority, opens no production path and never calls B/C.
"""
from __future__ import print_function
from scripts import community_preview_carrier_handoff_admission as handoff

REQUIRED_CONTEXT = (
    'host_id', 'authority_check', 'parent_fd', 'journal_fd', 'entry_fd',
    'lease_fd', 'uid', 'parent_identity', 'journal_identity', 'entry_identity',
    'lock_identity', 'history_refs', 'old_archive_bytes', 'new_archive_bytes',
    'attempt'
)

def _context(ctx):
    for name in REQUIRED_CONTEXT:
        if not hasattr(ctx, name):
            raise handoff.Hold('ORIGINAL_ENTRY_CONTEXT_INCOMPLETE')
    if ctx.host_id != handoff.HOST:
        raise handoff.Hold('FIXED_HOST_IDENTITY_MISMATCH')
    # Must be the original entry's own operator/authority verifier. This adapter
    # deliberately does not recreate loginuid, sudo, writer lease or approval logic.
    check = ctx.authority_check
    if not callable(check) or check() is not True:
        raise handoff.Hold('ORIGINAL_ENTRY_AUTHORITY_NOT_PROVEN')
    return ctx

def invoke(ctx, operation):
    """Call only from the original authorized entry; operation is status/execute/rollback."""
    ctx = _context(ctx)
    old_entries = handoff.members(
        ctx.old_archive_bytes, handoff.OLD_MANIFEST, handoff.OLD_ARCHIVE)
    new_entries = handoff.members(
        ctx.new_archive_bytes, handoff.NEW_MANIFEST, handoff.NEW_ARCHIVE)
    args = (ctx.parent_fd, ctx.journal_fd, ctx.entry_fd, ctx.lease_fd,
            ctx.uid, old_entries, new_entries, ctx.parent_identity,
            ctx.journal_identity, ctx.entry_identity, ctx.lock_identity,
            ctx.history_refs)
    if operation == 'status':
        return handoff.status(*args)
    if operation == 'execute':
        return handoff.execute(
            ctx.parent_fd, ctx.journal_fd, ctx.entry_fd, ctx.lease_fd,
            old_entries, ctx.new_archive_bytes, ctx.uid, ctx.parent_identity,
            ctx.journal_identity, ctx.entry_identity, ctx.lock_identity,
            ctx.attempt, history_refs=ctx.history_refs)
    if operation == 'rollback':
        return handoff.rollback(*args)
    raise handoff.Hold('UNKNOWN_HANDOFF_OPERATION')

def call_once_from_original_entry(ctx):
    """Fixed call: one attempt only; never auto-retries after UNKNOWN."""
    result = invoke(ctx, 'execute')
    if result.get('state') != 'SWAPPED_OLD_RETAINED_IN_STAGE' or result.get('retry_safe') is not False:
        raise handoff.Hold('HANDOFF_RESULT_NOT_ACCEPTED_INSPECT_ONLY')
    return result

def reconcile_from_original_entry(ctx):
    """Read-only status after an interrupted/unknown operation."""
    return invoke(ctx, 'status')

def rollback_from_original_entry(ctx):
    """Rollback only when the transaction's own exact conditions pass."""
    return invoke(ctx, 'rollback')
