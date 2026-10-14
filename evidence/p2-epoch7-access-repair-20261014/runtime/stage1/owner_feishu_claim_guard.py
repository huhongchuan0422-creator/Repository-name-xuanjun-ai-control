"""Canonical authorization for the existing Feishu transport; no new state.

Use the installed ExecutionLedger instance with its active generation binding.
All reads use the ledger's inode-pinned transaction, never a supplied DB path.
"""
import math


class OwnerFeishuClaimGuard:
    def __init__(self, ledger):
        from execution_ledger import ExecutionLedger
        if (not isinstance(ledger, ExecutionLedger) or ledger.activation_store is None or
                not isinstance(ledger.activation_binding, dict)):
            raise ValueError('ACTIVE_CANONICAL_LEDGER_REQUIRED')
        self.ledger = ledger
        with ledger._pinned_transaction() as value:
            self.db_identity = value[1]

    def __call__(self, claim):
        if (not isinstance(claim, dict) or claim.get('destination') != 'OWNER' or
                not isinstance(claim.get('event_key'), str) or
                claim.get('delivery_identity') != claim['event_key']):
            return False
        try:
            with self.ledger._pinned_transaction() as value:
                db, identity = value
                if identity != self.db_identity:
                    return False
                now = self.ledger._now()
                row = db.execute('''SELECT d.*,e.task_id,t.fence AS current_fence
                    FROM supervision_delivery d
                    JOIN supervision_events e ON e.event_key=d.event_key
                    JOIN tasks t ON t.id=e.task_id
                    WHERE d.event_key=? AND d.destination='OWNER' ''',
                    (claim['event_key'],)).fetchone()
                if row is None:
                    return False
                keys = ('claim_owner', 'claim_token', 'claim_epoch', 'claim_attempt',
                        'authority_fence', 'authority_epoch')
                if any(row[key] != claim.get(key) for key in keys):
                    return False
                for key in ('claim_epoch', 'claim_attempt', 'authority_fence', 'authority_epoch'):
                    if type(claim.get(key)) is not int or claim[key] < 1:
                        return False
                if (row['current_fence'] != row['authority_fence'] or
                        row['authority_epoch'] != self.ledger.activation_binding['epoch']):
                    return False
                if row['state'] == 'SENDING':
                    until = row['claim_until']
                    return type(until) in (int, float) and math.isfinite(until) and until > now
                if row['state'] != 'SENDING_UNCERTAIN':
                    return False
                # Only the supervisor's currently held reconciliation CAS can read receipts.
                recon_keys = ('reconciliation_owner', 'reconciliation_epoch')
                until = row['reconciliation_until']
                return (isinstance(row['reconciliation_owner'], str) and bool(row['reconciliation_owner']) and
                        type(claim.get('reconciliation_epoch')) is int and
                        claim['reconciliation_epoch'] > 0 and
                        all(row[key] == claim.get(key) for key in recon_keys) and
                        type(until) in (int, float) and math.isfinite(until) and until > now)
        except Exception:
            return False
