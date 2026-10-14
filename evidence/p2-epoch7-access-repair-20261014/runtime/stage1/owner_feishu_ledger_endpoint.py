"""Typed OWNER delivery operations behind the existing authenticated bridge.

Uses only existing supervision tables. Feishu credentials never enter this role.
"""
import math
import re
from owner_feishu_claim_guard import OwnerFeishuClaimGuard


CLAIM_FIELDS = ('event_key', 'destination', 'claim_owner', 'claim_until',
                'claim_token', 'claim_epoch', 'claim_attempt', 'authority_fence',
                'authority_epoch', 'reconciliation_owner', 'reconciliation_epoch')


class OwnerFeishuLedgerEndpoint:
    def __init__(self, ledger):
        self.ledger = ledger
        self.guard = OwnerFeishuClaimGuard(ledger)
        self.supervisor = ledger.supervisor()

    def _package(self):
        value = self.ledger.activation_store.read(require_active=True).get('release_sha256')
        if not isinstance(value,str) or re.fullmatch(r'[a-f0-9]{64}',value) is None:
            raise ValueError('ACTIVE_PACKAGE_BINDING_REQUIRED')
        return value

    def _bound(self, db, identity, claim):
        if (identity != self.guard.db_identity or not isinstance(claim, dict) or
                claim.get('package_sha256') != self._package()):
            return None
        if claim.get('destination') != 'OWNER' or claim.get('delivery_identity') != claim.get('event_key'):
            return None
        row = db.execute('''SELECT d.*,e.task_id,e.kind,t.fence AS current_fence
            FROM supervision_delivery d JOIN supervision_events e ON e.event_key=d.event_key
            JOIN tasks t ON t.id=e.task_id WHERE d.event_key=? AND d.destination='OWNER' ''',
            (claim.get('event_key'),)).fetchone()
        if row is None or any(row[key] != claim.get(key) for key in
                ('claim_owner','claim_token','claim_epoch','claim_attempt','authority_fence','authority_epoch')):
            return None
        if (any(type(claim.get(key)) is not int or claim[key] < 1 for key in
                ('claim_epoch','claim_attempt','authority_fence','authority_epoch')) or
                row['current_fence'] != row['authority_fence'] or
                row['authority_epoch'] != self.ledger.activation_binding['epoch'] or
                claim.get('event_kind') != row['kind']):
            return None
        return row

    def _live(self, row, claim, now):
        if row['state'] == 'SENDING':
            until = row['claim_until']
        elif row['state'] == 'SENDING_UNCERTAIN':
            if (not isinstance(row['reconciliation_owner'],str) or not row['reconciliation_owner'] or
                    type(claim.get('reconciliation_epoch')) is not int or claim['reconciliation_epoch'] < 1 or
                    any(row[key] != claim.get(key) for key in ('reconciliation_owner','reconciliation_epoch'))):
                return False
            until = row['reconciliation_until']
        else:
            return False
        return type(until) in (int,float) and math.isfinite(until) and until > now

    def _claim(self, row):
        claim = {key:row[key] for key in CLAIM_FIELDS}
        claim['delivery_identity'] = row['event_key']
        claim['event_kind'] = row['kind']
        claim['package_sha256'] = self._package()
        return claim

    def begin(self):
        # Reconcile expired uncertain sends first. Never re-claim them as new sends.
        with self.ledger._pinned_transaction() as value:
            db, identity = value
            if identity != self.guard.db_identity:
                raise ValueError('CANONICAL_DATABASE_REPLACED')
            now = self.ledger._now()
            self._package()
            row = db.execute('''SELECT d.*,e.kind,t.fence AS current_fence FROM supervision_delivery d
                JOIN supervision_events e ON e.event_key=d.event_key JOIN tasks t ON t.id=e.task_id
                WHERE d.destination='OWNER' AND d.state IN ('SENDING','SENDING_UNCERTAIN')
                AND d.claim_until<=? AND (d.reconciliation_owner IS NULL OR d.reconciliation_until<=?)
                ORDER BY d.event_key LIMIT 1''', (now,now)).fetchone()
            if row is not None:
                if (row['current_fence']!=row['authority_fence'] or
                        row['authority_epoch']!=self.ledger.activation_binding['epoch']):
                    db.execute("UPDATE supervision_delivery SET state='HELD',last_error='STALE_DELIVERY_AUTHORITY' WHERE event_key=? AND destination='OWNER'",(row['event_key'],))
                    return {'mode':'HELD'}
                db.execute('''UPDATE supervision_delivery SET state='SENDING_UNCERTAIN',
                    reconciliation_owner='gateway-feishu-reconciler', reconciliation_until=?,
                    reconciliation_epoch=reconciliation_epoch+1
                    WHERE event_key=? AND destination='OWNER' ''',
                    (now+self.supervisor.claim_ttl,row['event_key']))
                row = db.execute('''SELECT d.*,e.kind FROM supervision_delivery d
                    JOIN supervision_events e ON e.event_key=d.event_key
                    WHERE d.event_key=? AND d.destination='OWNER' ''', (row['event_key'],)).fetchone()
                return {'mode':'RECONCILE','claim':self._claim(row)}
            row = db.execute("""SELECT d.*,e.kind,t.fence AS current_fence FROM supervision_delivery d
                JOIN supervision_events e ON e.event_key=d.event_key JOIN tasks t ON t.id=e.task_id
                WHERE d.destination='OWNER' AND d.attempts<? AND d.send_attempts<? AND d.next_attempt_at<=?
                AND (d.state IN ('PENDING','DELIVERY_FAILED') OR (d.state='CLAIMED' AND d.claim_until<=?))
                ORDER BY d.next_attempt_at,d.event_key LIMIT 1""",
                (self.supervisor.max_delivery_attempts,self.supervisor.max_delivery_attempts,now,now)).fetchone()
            if row is None:
                return {'mode':'IDLE'}
            if (row['current_fence']!=row['authority_fence'] or
                    row['authority_epoch']!=self.ledger.activation_binding['epoch']):
                db.execute("UPDATE supervision_delivery SET state='HELD',last_error='STALE_DELIVERY_AUTHORITY' WHERE event_key=? AND destination='OWNER'",(row['event_key'],))
                return {'mode':'HELD'}
            epoch, attempt = row['claim_epoch']+1,(row['claim_attempt'] or 0)+1
            token = self.supervisor._claim_token(row,epoch,attempt)
            changed = db.execute("""UPDATE supervision_delivery SET state='SENDING',
                claim_owner='gateway-feishu-sender',claim_until=?,claim_epoch=?,claim_token=?,claim_attempt=?,
                send_attempts=send_attempts+1,sent_at=? WHERE event_key=? AND destination='OWNER' AND claim_epoch=?""",
                (now+self.supervisor.claim_ttl,epoch,token,attempt,now,row['event_key'],row['claim_epoch'])).rowcount
            if changed!=1:raise ValueError('OWNER_CLAIM_CAS_LOST')
            row = db.execute("""SELECT d.*,e.kind FROM supervision_delivery d
                JOIN supervision_events e ON e.event_key=d.event_key
                WHERE d.event_key=? AND d.destination='OWNER' """,(row['event_key'],)).fetchone()
            return {'mode':'SEND','claim':self._claim(row)}

    def execute(self, request):
        if not isinstance(request,dict):
            raise ValueError('OWNER_REQUEST_REJECTED')
        op = request.get('operation')
        keys = {'begin':{'operation'}, 'guard':{'operation','claim'},
                'finish':{'operation','claim','status','receipt_id'}}
        if op not in keys or set(request) != keys[op]:
            raise ValueError('OWNER_OPERATION_REJECTED')
        if op == 'begin':
            return self.begin()
        with self.ledger._pinned_transaction() as value:
            db, identity = value
            row = self._bound(db,identity,request['claim'])
            live = row is not None and self._live(row,request['claim'],self.ledger._now())
            if op == 'guard':
                return bool(live)
            if not live:
                raise ValueError('OWNER_CLAIM_NOT_CURRENT')
            status, receipt = request['status'], request['receipt_id']
            if status not in ('ACK','UNCERTAIN','UNKNOWN'):
                raise ValueError('OWNER_RECEIPT_STATUS_REJECTED')
            if status == 'ACK':
                if not isinstance(receipt,str) or re.fullmatch(r'om_[A-Za-z0-9_-]{1,128}',receipt) is None:
                    raise ValueError('OWNER_RECEIPT_REJECTED')
                state = 'ACKED'
            else:
                if receipt is not None:
                    raise ValueError('OWNER_UNKNOWN_RECEIPT_REJECTED')
                state = 'HELD' if row['state']=='SENDING_UNCERTAIN' else 'SENDING_UNCERTAIN'
            db.execute('''UPDATE supervision_delivery SET state=?,receipt_id=?,
                reconciliation_owner=NULL,reconciliation_until=NULL,last_error=?
                WHERE event_key=? AND destination='OWNER' ''',
                (state,receipt,None if state=='ACKED' else 'FEISHU_EXTERNAL_RECEIPT_UNCONFIRMED',row['event_key']))
            return {'state':state,'receiver_ack':state=='ACKED','model_calls':0}
