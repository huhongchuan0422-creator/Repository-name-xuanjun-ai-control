"""Candidate operation fence for an existing, authorized SQLite authority.

No database is opened, migrated, or enabled by import. The host must apply the
migration in its existing authority transaction after approval and provide fresh
identity policy and authenticated adapter/receipt verification. Not wired to
legacy controllers; do not use as a production entry point without review.
"""
import hashlib
import json
import sqlite3

MIGRATION = '''CREATE TABLE p3_effect_operations (
 operation_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL,
 identity_json TEXT NOT NULL, request_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RESERVED','RUNNING','SUCCEEDED','FAILED','UNKNOWN')),
 receipt_json TEXT, adapter_correlation TEXT,
 UNIQUE(request_digest)
)'''

REQUIRED_IDENTITY = frozenset(('task_id', 'spec_hash', 'artifact', 'run_id',
    'session_id', 'attempt_id', 'lease_id', 'fence', 'epoch', 'generation',
    'resume_generation'))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _identity(identity):
    if not isinstance(identity, dict) or set(identity) != REQUIRED_IDENTITY:
        raise ValueError('EXACT_OPERATION_IDENTITY_REQUIRED')
    for key, value in identity.items():
        if key in ('fence', 'epoch', 'generation', 'resume_generation'):
            if type(value) is not int or value < (1 if key == 'fence' else 0):
                raise ValueError('INVALID_IDENTITY')
        elif not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ValueError('INVALID_IDENTITY')
    if len(identity['spec_hash']) != 64 or any(c not in '0123456789abcdef' for c in identity['spec_hash']):
        raise ValueError('INVALID_IDENTITY')
    return _json(identity)


class OperationKernel:
    """One-shot effect reservation. All unknown outcomes remain no-redial.

    connect returns a connection to an already-provisioned canonical DB. Policy
    must authenticate adapter and evidence against the frozen operation, not
    rely on self-declared IDs. Both policy and adapter are host integrations.
    """
    def __init__(self, connect, adapter, policy, enabled=False):
        if enabled is not True:
            raise PermissionError('DEFAULT_OFF')
        if not callable(connect) or not callable(getattr(policy, 'verify_adapter', None)) or not callable(getattr(policy, 'verify_receipt', None)):
            raise PermissionError('AUTHENTICATED_TRUST_POLICY_REQUIRED')
        if not callable(getattr(adapter, 'identity', None)) or not callable(getattr(adapter, 'invoke', None)) or not callable(getattr(adapter, 'reconcile', None)):
            raise TypeError('ADAPTER_CONTRACT_REQUIRED')
        self.connect, self.adapter, self.policy = connect, adapter, policy

    def _read(self, connection, operation_id):
        row = connection.execute('SELECT request_digest,identity_json,request_json,state,receipt_json,adapter_correlation FROM p3_effect_operations WHERE operation_id=?', (operation_id,)).fetchone()
        if row is None:
            return None
        return dict(zip(('request_digest','identity_json','request_json','state','receipt_json','adapter_correlation'), row))

    def reserve(self, operation_id, identity, admission, request):
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 512:
            raise ValueError('OPERATION_ID_REQUIRED')
        identity_json = _identity(identity)
        if not isinstance(admission, dict) or any(type(admission.get(k)) is not type(v) or admission.get(k) != v for k,v in identity.items()):
            raise PermissionError('ADMISSION_IDENTITY_MISMATCH')
        body = _json({'identity': identity, 'admission': admission, 'request': request})
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row = self._read(db, operation_id)
            if row:
                if row['request_digest'] != digest or row['identity_json'] != identity_json or row['request_json'] != body:
                    raise ValueError('OPERATION_ID_CONFLICT')
                db.commit()
                return False, row
            try:
                db.execute('INSERT INTO p3_effect_operations(operation_id,request_digest,identity_json,request_json,state) VALUES(?,?,?,?,?)', (operation_id,digest,identity_json,body,'RESERVED'))
            except sqlite3.IntegrityError:
                raise ValueError('REQUEST_DIGEST_CONFLICT')
            db.commit()
            return True, self._row(operation_id)
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _row(self, operation_id):
        db = self.connect()
        try:
            return self._read(db, operation_id)
        finally:
            db.close()

    def _transition(self, operation_id, source, target, receipt=None, correlation=None):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            cursor = db.execute('UPDATE p3_effect_operations SET state=?,receipt_json=?,adapter_correlation=? WHERE operation_id=? AND state=?', (target, _json(receipt) if receipt is not None else None, correlation, operation_id, source))
            db.commit()
            return cursor.rowcount == 1
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def invoke(self, operation_id, identity, admission, request):
        # The policy must itself re-read authority and authenticate this adapter.
        declaration = self.adapter.identity()
        if self.policy.verify_adapter(declaration, identity, admission) is not True:
            raise PermissionError('ADAPTER_IDENTITY_NOT_TRUSTED')
        created, row = self.reserve(operation_id, identity, admission, request)
        if not created:
            return row
        if not self._transition(operation_id, 'RESERVED', 'RUNNING'):
            raise RuntimeError('RESERVATION_LOST')
        try:
            evidence = self.adapter.invoke(operation_id, row['request_digest'], identity, request)
            if self.policy.verify_receipt(evidence, declaration, operation_id, row['request_digest'], identity) is not True:
                raise ValueError('UNTRUSTED_RECEIPT')
            if not isinstance(evidence, dict) or evidence.get('outcome') not in ('SUCCEEDED', 'FAILED') or not isinstance(evidence.get('correlation'), str) or not evidence['correlation']:
                raise ValueError('INVALID_RECEIPT')
            self._transition(operation_id, 'RUNNING', evidence['outcome'], evidence, evidence['correlation'])
        except Exception:
            self._transition(operation_id, 'RUNNING', 'UNKNOWN')
        return self._row(operation_id)

    def reconcile(self, operation_id):
        row = self._row(operation_id)
        if not row or row['state'] not in ('RUNNING', 'UNKNOWN'):
            raise ValueError('RECONCILABLE_OPERATION_REQUIRED')
        identity = json.loads(row['identity_json'])
        admission = json.loads(row['request_json'])['admission']
        declaration = self.adapter.identity()
        if self.policy.verify_adapter(declaration, identity, admission) is not True:
            raise PermissionError('ADAPTER_IDENTITY_NOT_TRUSTED')
        try:
            evidence = self.adapter.reconcile(operation_id, row['request_digest'], identity)
            if self.policy.verify_receipt(evidence, declaration, operation_id, row['request_digest'], identity) is not True:
                raise ValueError('UNTRUSTED_RECEIPT')
            if not isinstance(evidence, dict) or evidence.get('outcome') not in ('SUCCEEDED', 'FAILED') or not isinstance(evidence.get('correlation'), str) or not evidence['correlation']:
                raise ValueError('INVALID_RECEIPT')
        except Exception:
            if row['state'] == 'RUNNING':
                self._transition(operation_id, 'RUNNING', 'UNKNOWN')
            return self._row(operation_id)
        self._transition(operation_id, row['state'], evidence['outcome'], evidence, evidence['correlation'])
        return self._row(operation_id)

class RunnerOperationStore:
    """Durable reservation against an existing DB with MIGRATION applied.

    This legacy-field bridge is not a replacement for authenticated V2
    admission, adapter identity verification, or canonical authority fencing.
    The caller must supply a connection to the same durable DB after restart.
    """
    def __init__(self, connect):
        if not callable(connect):
            raise TypeError('CONNECTION_FACTORY_REQUIRED')
        self.connect = connect

    def get(self, operation_id):
        db = self.connect()
        try:
            return OperationKernel._read(self, db, operation_id)
        finally:
            db.close()

    def reserve(self, operation_id, subject, admission, operation):
        body = _json({'subject': subject, 'admission': admission, 'operation': operation})
        identity = _json(subject)
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row = OperationKernel._read(self, db, operation_id)
            if row:
                if row['request_digest'] != digest or row['identity_json'] != identity or row['request_json'] != body:
                    raise ValueError('OPERATION_ID_CONFLICT')
                db.commit()
                return False, row
            try:
                db.execute('INSERT INTO p3_effect_operations(operation_id,request_digest,identity_json,request_json,state) VALUES(?,?,?,?,?)', (operation_id, digest, identity, body, 'RESERVED'))
            except sqlite3.IntegrityError:
                raise ValueError('REQUEST_DIGEST_CONFLICT')
            db.commit()
            return True, self.get(operation_id)
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def transition(self, operation_id, source, target, receipt=None, correlation=None):
        return OperationKernel._transition(self, operation_id, source, target, receipt, correlation)

    def reserve_owned(self, operation_id, subject, admission, operation, owner_fence):
        """Atomically create a RUNNING reservation owned by one fencing token."""
        if not isinstance(owner_fence, str) or len(owner_fence) != 64 or any(c not in '0123456789abcdef' for c in owner_fence):
            raise ValueError('VALID_OWNER_FENCE_REQUIRED')
        body = _json({'subject': subject, 'admission': admission, 'operation': operation})
        identity = _json(subject)
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row = OperationKernel._read(self, db, operation_id)
            if row:
                if row['request_digest'] != digest or row['identity_json'] != identity or row['request_json'] != body:
                    raise ValueError('OPERATION_ID_CONFLICT')
                db.commit()
                return False, row
            try:
                db.execute('INSERT INTO p3_effect_operations(operation_id,request_digest,identity_json,request_json,state,receipt_json,adapter_correlation) VALUES(?,?,?,?,?,?,?)',
                           (operation_id,digest,identity,body,'RUNNING',_json({'phase':'STAGING'}),owner_fence))
            except sqlite3.IntegrityError:
                raise ValueError('REQUEST_DIGEST_CONFLICT')
            db.commit()
            return True, None
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def transition_owned(self, operation_id, owner_fence, source, target, receipt=None):
        """Compare-and-swap guarded by both operation state and owner fence."""
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            cursor = db.execute('UPDATE p3_effect_operations SET state=?,receipt_json=? WHERE operation_id=? AND state=? AND adapter_correlation=?',
                                (target,_json(receipt) if receipt is not None else None,operation_id,source,owner_fence))
            db.commit()
            return cursor.rowcount == 1
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _guard_binding(guard_id, guard_scope):
        body = _json({'kind':'exclusive-recovery-guard', 'guard_id':guard_id, 'scope':guard_scope})
        return body, hashlib.sha256(body.encode('utf-8')).hexdigest()

    def _acquire_guard_tx(self, db, guard_id, guard_scope, owner_fence):
        body, digest = self._guard_binding(guard_id, guard_scope)
        row = OperationKernel._read(self, db, guard_id)
        if row:
            if row['request_digest'] != digest or row['request_json'] != body:
                raise ValueError('GUARD_SCOPE_CONFLICT')
            if row['state'] != 'SUCCEEDED':
                return False
            changed = db.execute('UPDATE p3_effect_operations SET state=?, receipt_json=?, adapter_correlation=? WHERE operation_id=? AND state=?',
                ('RUNNING', _json({'phase':'GUARD_HELD'}), owner_fence, guard_id, 'SUCCEEDED')).rowcount
            return changed == 1
        db.execute('INSERT INTO p3_effect_operations(operation_id,request_digest,identity_json,request_json,state,receipt_json,adapter_correlation) VALUES(?,?,?,?,?,?,?)',
            (guard_id, digest, _json({'kind':'guard'}), body, 'RUNNING', _json({'phase':'GUARD_HELD'}), owner_fence))
        return True

    def acquire_guard(self, guard_id, guard_scope, owner_fence):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            acquired = self._acquire_guard_tx(db, guard_id, guard_scope, owner_fence)
            db.commit()
            return acquired
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve_owned_with_guard(self, operation_id, subject, admission, operation,
                                 owner_fence, guard_id, guard_scope):
        if not isinstance(owner_fence, str) or len(owner_fence) != 64 or any(c not in '0123456789abcdef' for c in owner_fence):
            raise ValueError('VALID_OWNER_FENCE_REQUIRED')
        body = _json({'subject':subject, 'admission':admission, 'operation':operation})
        identity = _json(subject)
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row = OperationKernel._read(self, db, operation_id)
            if row:
                if row['request_digest'] != digest or row['identity_json'] != identity or row['request_json'] != body:
                    raise ValueError('OPERATION_ID_CONFLICT')
                db.commit()
                return False, row
            if not self._acquire_guard_tx(db, guard_id, guard_scope, owner_fence):
                db.rollback()
                return False, None
            db.execute('INSERT INTO p3_effect_operations(operation_id,request_digest,identity_json,request_json,state,receipt_json,adapter_correlation) VALUES(?,?,?,?,?,?,?)',
                (operation_id,digest,identity,body,'RUNNING',_json({'phase':'ROLLBACK_OWNER'}),owner_fence))
            db.commit()
            return True, None
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def claim_guard_recovery(self, guard_id, owner_fence, recovery_token):
        """Single reconciler for a stopped fenced owner; never changes owner fence."""
        if not isinstance(recovery_token, str) or len(recovery_token) != 64:
            raise ValueError('RECOVERY_TOKEN_REQUIRED')
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row = OperationKernel._read(self, db, guard_id)
            if (not row or row['state'] not in ('RUNNING','UNKNOWN')
                    or row['adapter_correlation'] != owner_fence
                    or row['receipt_json'] not in (_json({'phase':'GUARD_HELD'}), _json({'phase':'RECOVERY_UNKNOWN'}))):
                db.rollback()
                return False
            changed = db.execute('UPDATE p3_effect_operations SET receipt_json=? WHERE operation_id=? AND state=? AND adapter_correlation=? AND receipt_json=?',
                (_json({'phase':'RECOVERING','token':recovery_token}),guard_id,row['state'],owner_fence,row['receipt_json'])).rowcount
            db.commit()
            return changed == 1
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def finish_guard_recovery(self, guard_id, owner_fence, recovery_token):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute('UPDATE p3_effect_operations SET state=?,receipt_json=? WHERE operation_id=? AND state IN (?,?) AND adapter_correlation=? AND receipt_json=?',
                ('SUCCEEDED',_json({'phase':'GUARD_RELEASED'}),guard_id,'RUNNING','UNKNOWN',owner_fence,
                 _json({'phase':'RECOVERING','token':recovery_token}))).rowcount
            db.commit()
            return changed == 1
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
