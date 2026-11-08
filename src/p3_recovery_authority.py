"""Candidate signed recovery lease/CAS primitive for an existing SQLite store.

No database, key, authority, timer, or service is created at import. The host
must explicitly migrate its authorized store and provide a trusted clock and
configured Ed25519 TrustStore. Install and signed install recovery use the
guard; rollback remains outside this recovery-only slice.
"""
import contextlib
import errno
import fcntl
import hashlib
import json
import os
import stat
try:
    from p3_admission_v2 import TrustStore, exact, text, window, HEX
except ImportError:
    from .p3_admission_v2 import TrustStore, exact, text, window, HEX

OWNERSHIP_MIGRATION = '''CREATE TABLE p3_operation_ownership (
 operation_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, owner_token TEXT NOT NULL,
 epoch INTEGER NOT NULL, fence TEXT NOT NULL, lease_expires_at INTEGER NOT NULL,
 heartbeat_seq INTEGER NOT NULL, heartbeat_at INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('OWNER_ACTIVE','RECOVERY_CLAIMED','COMPLETED')),
 recovery_owner_token TEXT
)'''
ADMISSION_KEYS = frozenset(('operation_id','attempt_id','observed_owner_token','observed_epoch',
    'observed_fence','observed_lease_expires_at','observed_heartbeat_seq',
    'observed_heartbeat_at','authority_identity','reason','proof_kind',
    'issued_at','expires_at','key_id','signature'))
STOP_KEYS = frozenset(('operation_id','attempt_id','owner_token','epoch','fence',
    'heartbeat_seq','stopped_at','authority_identity','key_id','signature'))


def _token():
    return os.urandom(32).hex()


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


class OwnershipStore:
    """Owner / recovery CAS sharing the same SQLite write lock as effect code."""
    def __init__(self, connect, trust_store, clock, stale_seconds):
        if not callable(connect) or not isinstance(trust_store, TrustStore) or not callable(clock):
            raise PermissionError('TRUSTED_AUTHORITY_AND_STORE_REQUIRED')
        if not _integer(stale_seconds, 1):
            raise ValueError('STALE_THRESHOLD_REQUIRED')
        self.connect, self.trust, self.clock, self.stale_seconds = connect, trust_store, clock, stale_seconds

    def _now(self):
        value = self.clock()
        if not _integer(value): raise ValueError('TRUSTED_INTEGER_CLOCK_REQUIRED')
        return value

    def claim_initial(self, operation_id, attempt_id, lease_seconds):
        now = self._now()
        if not text(operation_id) or not text(attempt_id) or not _integer(lease_seconds, 1):
            raise ValueError('VALID_OWNER_CLAIM_REQUIRED')
        token, fence = _token(), _token()
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO p3_operation_ownership VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (operation_id,attempt_id,token,1,fence,now+lease_seconds,0,now,'OWNER_ACTIVE',None))
            db.commit()
            return {'owner_token':token,'epoch':1,'fence':fence}
        except BaseException:
            db.rollback(); raise
        finally:
            db.close()

    def read(self, operation_id):
        db = self.connect()
        try:
            row = db.execute('SELECT operation_id,attempt_id,owner_token,epoch,fence,lease_expires_at,heartbeat_seq,heartbeat_at,state,recovery_owner_token FROM p3_operation_ownership WHERE operation_id=?',(operation_id,)).fetchone()
            if row is None:return None
            return dict(zip(('operation_id','attempt_id','owner_token','epoch','fence','lease_expires_at','heartbeat_seq','heartbeat_at','state','recovery_owner_token'),row))
        finally:db.close()

    def heartbeat(self, operation_id, owner, expected_seq, lease_seconds):
        now = self._now()
        if not _integer(expected_seq) or not _integer(lease_seconds,1): raise ValueError('INVALID_HEARTBEAT')
        db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            n=db.execute('UPDATE p3_operation_ownership SET heartbeat_seq=heartbeat_seq+1,heartbeat_at=?,lease_expires_at=? WHERE operation_id=? AND owner_token=? AND epoch=? AND fence=? AND heartbeat_seq=? AND state=? AND lease_expires_at>=? AND heartbeat_at<=?',
                (now,now+lease_seconds,operation_id,owner['owner_token'],owner['epoch'],owner['fence'],expected_seq,'OWNER_ACTIVE',now,now)).rowcount
            db.commit();return n==1
        except BaseException:db.rollback();raise
        finally:db.close()

    def _assert_tx(self, db, operation_id, owner):
        now=self._now()
        row=db.execute('SELECT 1 FROM p3_operation_ownership WHERE operation_id=? AND owner_token=? AND epoch=? AND fence=? AND state=? AND lease_expires_at>=? AND heartbeat_seq>=0 AND heartbeat_at<=? AND heartbeat_at+?>=?',
            (operation_id,owner['owner_token'],owner['epoch'],owner['fence'],'OWNER_ACTIVE',now,now,self.stale_seconds,now)).fetchone()
        if not row:raise PermissionError('OWNER_FENCED_OR_LEASE_EXPIRED')

    @contextlib.contextmanager
    def owner_effect_transaction(self, operation_id, owner):
        """Caller must perform fd rename, fsync and journal write within yield.

        Recovery CAS also uses BEGIN IMMEDIATE, so it cannot claim between
        assertion and effect/commit when all writers use this same database.
        """
        db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            self._assert_tx(db,operation_id,owner)
            yield db
            self._assert_tx(db,operation_id,owner)
            db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    def _assert_recovery_tx(self, db, operation_id, owner):
        row = db.execute('SELECT 1 FROM p3_operation_ownership WHERE operation_id=? AND owner_token=? AND epoch=? AND fence=? AND state=? AND recovery_owner_token=?',
                         (operation_id,owner['owner_token'],owner['epoch'],owner['fence'],
                          'RECOVERY_CLAIMED',owner['owner_token'])).fetchone()
        if not row:
            raise PermissionError('RECOVERY_OWNER_FENCED')

    @contextlib.contextmanager
    def recovery_effect_transaction(self, operation_id, owner):
        """Permit journal reconciliation only under the new recovery epoch."""
        db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            self._assert_recovery_tx(db,operation_id,owner)
            yield db
            self._assert_recovery_tx(db,operation_id,owner)
            db.commit()
        except BaseException:
            db.rollback();raise
        finally:
            db.close()

    def _claim_recovery_under_guard(self, admission, stop_receipt=None):
        now=self._now();exact(admission,ADMISSION_KEYS);window(admission,now)
        for key in ('operation_id','attempt_id','observed_owner_token','observed_fence','authority_identity','reason','proof_kind'):
            if not text(admission[key]):raise ValueError('INVALID_RECOVERY_ADMISSION')
        for key in ('observed_epoch','observed_lease_expires_at','observed_heartbeat_seq','observed_heartbeat_at'):
            if not _integer(admission[key]):raise ValueError('INVALID_RECOVERY_ADMISSION')
        self.trust.verify(admission,'recovery',admission['authority_identity'],b'P3-RECOVERY-ADMISSION-V2\x00')
        stopped=admission['proof_kind']=='STOP_RECEIPT'
        if stopped:
            exact(stop_receipt,STOP_KEYS)
            self.trust.verify(stop_receipt,'stop',admission['authority_identity'],b'P3-OWNER-STOP-V2\x00')
            expected={'operation_id':admission['operation_id'],'attempt_id':admission['attempt_id'],
                'owner_token':admission['observed_owner_token'],'epoch':admission['observed_epoch'],
                'fence':admission['observed_fence'],'heartbeat_seq':admission['observed_heartbeat_seq'],
                'authority_identity':admission['authority_identity']}
            if any(type(stop_receipt.get(k)) is not type(v) or stop_receipt[k] != v for k,v in expected.items()):
                raise PermissionError('STOP_RECEIPT_BINDING_MISMATCH')
            if not _integer(stop_receipt['stopped_at']) or not admission['observed_heartbeat_at'] <= stop_receipt['stopped_at'] <= now:
                raise PermissionError('STOP_RECEIPT_TIME_INVALID')
        elif admission['proof_kind'] == 'EXPIRED_STALE':
            if not (admission['observed_lease_expires_at'] < now and
                    admission['observed_heartbeat_at'] + self.stale_seconds < now):
                raise PermissionError('LEASE_OR_HEARTBEAT_STILL_ACTIVE')
        else:raise PermissionError('RECOVERY_PROOF_REQUIRED')
        new_owner,new_fence=_token(),_token()
        db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            locked_now = self._now()
            window(admission, locked_now)
            self.trust.verify(admission,'recovery',admission['authority_identity'],b'P3-RECOVERY-ADMISSION-V2\x00')
            if stopped:
                self.trust.verify(stop_receipt,'stop',admission['authority_identity'],b'P3-OWNER-STOP-V2\x00')
            if stopped and stop_receipt['stopped_at'] > locked_now:
                raise PermissionError('STOP_RECEIPT_TIME_INVALID')
            if not stopped and not (admission['observed_lease_expires_at'] < locked_now and
                                    admission['observed_heartbeat_at'] + self.stale_seconds < locked_now):
                raise PermissionError('LEASE_OR_HEARTBEAT_STILL_ACTIVE')
            count=db.execute('UPDATE p3_operation_ownership SET owner_token=?,epoch=epoch+1,fence=?,state=?,recovery_owner_token=? WHERE operation_id=? AND attempt_id=? AND owner_token=? AND epoch=? AND fence=? AND lease_expires_at=? AND heartbeat_seq=? AND heartbeat_at=? AND state=?',
                (new_owner,new_fence,'RECOVERY_CLAIMED',new_owner,admission['operation_id'],admission['attempt_id'],
                 admission['observed_owner_token'],admission['observed_epoch'],admission['observed_fence'],
                 admission['observed_lease_expires_at'],admission['observed_heartbeat_seq'],
                 admission['observed_heartbeat_at'],'OWNER_ACTIVE')).rowcount
            if count != 1:
                db.rollback();raise PermissionError('RECOVERY_OBSERVATION_STALE')
            db.commit()
            return {'owner_token':new_owner,'epoch':admission['observed_epoch']+1,'fence':new_fence}
        except BaseException:db.rollback();raise
        finally:db.close()


class OwnershipGuard:
    """Per-acquisition flock plus same-database SQLite ownership transaction.

    ``lock_dir_fd`` and ``lock_name`` must come from host-protected directory
    configuration. A distinct open file description is acquired each time, so
    concurrent threads and processes cannot share a reentrant flock. All host
    writers and claimants must use this same configured lock inode and DB.
    """
    def __init__(self, ownership_store, lock_dir_fd, lock_name, install_authority_reader=None):
        if not isinstance(ownership_store, OwnershipStore):
            raise TypeError('OWNERSHIP_STORE_REQUIRED')
        if not isinstance(lock_name,str) or not lock_name or lock_name in ('.','..') or '/' in lock_name or '\x00' in lock_name:
            raise ValueError('SINGLE_LOCK_NAME_REQUIRED')
        directory=os.fstat(lock_dir_fd)
        if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid() or directory.st_mode & 0o022:
            raise PermissionError('PROTECTED_LOCK_DIRECTORY_REQUIRED')
        self.store=ownership_store
        self.install_authority_reader=install_authority_reader
        self.lock_dir_fd=os.dup(lock_dir_fd)
        self.lock_name=lock_name
        try:
            fd=self._open_lock()
            try:
                info=os.fstat(fd)
                self.lock_identity=(info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
            finally:os.close(fd)
            self._bind_lock_to_database()
        except BaseException:
            os.close(self.lock_dir_fd)
            raise

    def _bind_lock_to_database(self):
        """Persist one lock identity for every guarded actor on this DB."""
        operation_id='p3:ownership-guard-lock:v1'
        body=json.dumps({'kind':'ownership-guard-lock','identity':self.lock_identity},
                        sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(body.encode('utf-8')).hexdigest()
        db=self.store.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT request_digest,request_json,state FROM p3_effect_operations WHERE operation_id=?',
                           (operation_id,)).fetchone()
            if row is None:
                db.execute('INSERT INTO p3_effect_operations(operation_id,request_digest,identity_json,request_json,state) VALUES(?,?,?,?,?)',
                           (operation_id,digest,'{"kind":"ownership-guard-lock"}',body,'SUCCEEDED'))
            elif row!=(digest,body,'SUCCEEDED'):
                raise PermissionError('GUARD_DATABASE_BINDING_MISMATCH')
            db.commit()
        except BaseException:
            db.rollback();raise
        finally:
            db.close()

    def close(self):
        os.close(self.lock_dir_fd)

    def _open_lock(self):
        fd=os.open(self.lock_name,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.lock_dir_fd)
        try:
            info=os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or info.st_mode & 0o077):
                raise PermissionError('PROTECTED_LOCK_FILE_REQUIRED')
            return fd
        except BaseException:
            os.close(fd);raise

    @contextlib.contextmanager
    def _exclusive(self, blocking=False):
        fd=self._open_lock()
        try:
            info=os.fstat(fd)
            identity=(info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
            if identity != self.lock_identity:
                raise PermissionError('LOCK_FILE_IDENTITY_CHANGED')
            try:
                fcntl.flock(fd,fcntl.LOCK_EX if blocking else fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EACCES,errno.EAGAIN):
                    raise PermissionError('OWNERSHIP_LOCK_BUSY')
                raise
            try:yield
            finally:fcntl.flock(fd,fcntl.LOCK_UN)
        finally:os.close(fd)

    def verify_install_authority(self, operation_id, attempt_id, authority_context):
        if not callable(self.install_authority_reader):
            raise PermissionError('SIGNED_INSTALL_AUTHORITY_REQUIRED')
        exact(authority_context,{'manifest_sha256','artifact_digest'})
        if any(not isinstance(authority_context[k],str) or not HEX.fullmatch(authority_context[k]) for k in authority_context):
            raise ValueError('VALID_INSTALL_ARTIFACT_CONTEXT_REQUIRED')
        proof=self.install_authority_reader(operation_id,attempt_id,dict(authority_context))
        keys={'operation_id','attempt_id','manifest_sha256','artifact_digest','authority_identity','issued_at','expires_at','key_id','signature'}
        exact(proof,keys)
        if (proof['operation_id'] != operation_id or proof['attempt_id'] != attempt_id
                or any(proof[k] != authority_context[k] for k in authority_context)
                or not text(proof['authority_identity'])):
            raise PermissionError('INSTALL_AUTHORITY_BINDING_MISMATCH')
        window(proof,self.store._now())
        self.store.trust.verify(proof,'install',proof['authority_identity'],b'P3-INSTALL-OWNER-V1\x00')

    def claim_owner(self, operation_id, attempt_id, lease_seconds, authority_context):
        self.verify_install_authority(operation_id,attempt_id,authority_context)
        with self._exclusive():
            self.verify_install_authority(operation_id,attempt_id,authority_context)
            return self.store.claim_initial(operation_id,attempt_id,lease_seconds)

    def assert_owner(self, operation_id, owner):
        with self._exclusive(blocking=True):
            with self.store.owner_effect_transaction(operation_id,owner):
                pass

    def is_current_owner(self, operation_id, owner):
        try:
            self.assert_owner(operation_id,owner)
            return True
        except (PermissionError,KeyError):
            return False

    @contextlib.contextmanager
    def with_owner_lock(self, operation_id, owner):
        """Keep claimants out while the owner performs non-transactional steps."""
        with self._exclusive(blocking=True):
            with self.store.owner_effect_transaction(operation_id,owner):
                pass
            yield

    @contextlib.contextmanager
    def with_exclusive_side_effect(self, operation_id, owner, attempt_id=None, authority_context=None):
        """Hold flock and DB write lock through caller's effect and journal CAS."""
        with self._exclusive(blocking=True):
            with self.store.owner_effect_transaction(operation_id,owner) as db:
                if attempt_id is not None:
                    self.verify_install_authority(operation_id,attempt_id,authority_context)
                yield db

    def claim_recovery(self, admission, stop_receipt=None):
        # An effect holding this lock must finish its DB commit before takeover.
        with self._exclusive(blocking=True):
            return self.store._claim_recovery_under_guard(admission,stop_receipt)

    @contextlib.contextmanager
    def with_exclusive_reconciliation(self, operation_id, recovery_owner):
        with self._exclusive():
            with self.store.recovery_effect_transaction(operation_id,recovery_owner) as db:
                yield db

class HeartbeatLease:
    """Managed heartbeat for a claimed owner; host must stop it on all exits."""
    def __init__(self, store, operation_id, owner, lease_seconds, interval_seconds):
        import threading
        if not isinstance(store, OwnershipStore) or not _integer(lease_seconds,2):
            raise ValueError('VALID_HEARTBEAT_LEASE_REQUIRED')
        if type(interval_seconds) not in (int,float) or not 0 < interval_seconds < lease_seconds:
            raise ValueError('VALID_HEARTBEAT_INTERVAL_REQUIRED')
        self.store,self.operation_id,self.owner=store,operation_id,dict(owner)
        self.lease_seconds,self.interval_seconds=lease_seconds,interval_seconds
        self._stop=threading.Event();self._lost=threading.Event()
        self._thread=threading.Thread(target=self._run,name='p3-owner-heartbeat')
        self._thread.daemon=True
        self._started=False
    def start(self):
        if self._started:raise RuntimeError('HEARTBEAT_ALREADY_STARTED')
        self._started=True;self._thread.start();return self
    def _run(self):
        while not self._stop.wait(self.interval_seconds):
            try:
                row=self.store.read(self.operation_id)
                if (not row or row['owner_token'] != self.owner['owner_token']
                        or row['epoch'] != self.owner['epoch'] or row['fence'] != self.owner['fence']
                        or not self.store.heartbeat(self.operation_id,self.owner,row['heartbeat_seq'],self.lease_seconds)):
                    self._lost.set();return
            except Exception:
                self._lost.set();return
    def assert_live(self):
        if not self._started or self._lost.is_set() or self._stop.is_set():
            raise PermissionError('HEARTBEAT_NOT_LIVE')
    def stop(self):
        self._stop.set()
        if self._started:self._thread.join()
