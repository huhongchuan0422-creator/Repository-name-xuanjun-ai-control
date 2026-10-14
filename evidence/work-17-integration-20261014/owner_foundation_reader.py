"""Unified read entry for the EXISTING trusted Owner controller."""
import copy
import os
from activation_control import ActivationStore
from foundation_integration import foundation_snapshot, chinese_summary, validate_binding
from producer_inventory import complete_producer_view


def read_authorized_owner_foundations(owner_authorizer, **reader_arguments):
    """Gate the read using the existing controller's authenticated session.

    The controller supplies a trusted closure, never a request-body callback or
    authenticated flag. It must enforce the pinned Owner principal and task
    scope. This adapter does not authenticate a login or mint a session.
    """
    binding = copy.deepcopy(reader_arguments.get('binding'))
    validate_binding(binding)
    if not callable(owner_authorizer):
        raise ValueError('TRUSTED_OWNER_AUTHORIZER_REQUIRED')
    def authorized():
        try:
            accepted = owner_authorizer(copy.deepcopy(binding))
        except Exception:
            raise ValueError('OWNER_READ_ACCESS_DENIED') from None
        if accepted is not True:
            raise ValueError('OWNER_READ_ACCESS_DENIED')
    authorized()
    arguments = dict(reader_arguments)
    arguments['binding'] = copy.deepcopy(binding)
    result = read_owner_foundations(**arguments)
    authorized()
    return result


def read_owner_foundations(db, binding, now, activation_reader, expected_activation,
                          receipts, receipt_verifier, producer_envelopes,
                          inventory_verifier, records_verifier,
                          workspace_origin=None, max_tasks=1000):
    """No HTTP server, new database, dispatch, signing or activation authority.

    The callback is the trusted runtime's original ActivationStore.read;
    expected descriptor/provenance is pinned by that runtime, not a client.
    SQL path congruence is not a claim of SQLite descriptor/VFS inode pinning.
    Caller retains protected connection provenance and live authority checks.
    """
    validate_binding(binding)
    expected = copy.deepcopy(expected_activation)
    ActivationStore.validate(expected)
    if expected['state'] != 'ACTIVE' or expected['epoch'] != binding['epoch']:
        raise ValueError('OWNER_ACTIVE_EPOCH_REQUIRED')
    if not callable(activation_reader):
        raise ValueError('TRUSTED_ACTIVATION_READER_REQUIRED')
    if (not isinstance(producer_envelopes, dict) or
            set(producer_envelopes) - {'costs', 'usage'}):
        raise ValueError('INVALID_PRODUCER_ENVELOPES')
    before = activation_reader(require_active=True)
    ActivationStore.validate(before)
    if before != expected:
        raise ValueError('OWNER_ACTIVATION_BINDING_MISMATCH')
    databases = list(db.execute('PRAGMA database_list'))
    main = [row[2] for row in databases if row[1] == 'main']
    if len(main) != 1 or not main[0] or os.path.realpath(main[0]) != expected['db_path']:
        raise ValueError('OWNER_CANONICAL_DATABASE_PATH_MISMATCH')
    # Costs/usage are exclusively routed through the complete inventory path;
    # no partial old-style input can bypass it through the generic receipt map.
    if not isinstance(receipts, dict) or set(receipts) & {'costs', 'usage'}:
        raise ValueError('COMPLETE_PRODUCER_PATH_REQUIRED')
    result = foundation_snapshot(db, binding, now, receipts, receipt_verifier,
                                 workspace_origin, max_tasks)
    for kind in ('costs', 'usage'):
        pair = producer_envelopes.get(kind)
        if pair is not None and (not isinstance(pair, dict) or set(pair) != {'inventory', 'records'}):
            raise ValueError('INVALID_PRODUCER_PAIR')
        result['views'][kind] = complete_producer_view(
            kind, binding, None if pair is None else pair['inventory'],
            None if pair is None else pair['records'], inventory_verifier,
            records_verifier, now)
    after = activation_reader(require_active=True)
    ActivationStore.validate(after)
    if after != expected:
        raise ValueError('OWNER_ACTIVATION_CHANGED_DURING_READ')
    # Do not expose internal paths, UUIDs, raw descriptor or free-form receipts.
    result['activation_epoch'] = expected['epoch']
    result['activation_binding_status'] = 'TRUSTED_READER_MATCH_NOT_EXECUTION_AUTHORITY'
    result['status'] = ('HOLD' if any(v.get('status') == 'HOLD' for v in result['views'].values())
                        else 'VIEWS_READY_NOT_ADMITTED')
    result['summary'] = chinese_summary(result)
    return result
