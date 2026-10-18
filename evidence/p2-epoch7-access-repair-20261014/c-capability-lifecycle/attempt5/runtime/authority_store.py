"""Durable service-side quota and lease/fence store for one trusted issuer.

Not a UK deployment or self-issued approval. Registration is an administrative
operation after exact independent grant authentication. All clients must use the
same protected service/database; local copies are not global Writer proof.
"""
import json
import os
import sqlite3
import stat
import time
from receipt_provider import need, digest, canonical

class AuthorityStore(object):
    def __init__(self, path, initialize=False, clock=None):
        need(os.path.isabs(path), 'ABSOLUTE_STORE_PATH')
        parent = os.path.dirname(path)
        info = os.lstat(parent)
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and
             stat.S_IMODE(info.st_mode) == 0o700, 'STORE_DIRECTORY')
        self.path, self.clock = path, clock or time.time
        if initialize:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            os.fsync(fd); os.close(fd)
        info = os.lstat(path)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
             info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600, 'STORE_AUTHORITY')
        self.identity = (info.st_dev, info.st_ino)
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA journal_mode=DELETE')
        if initialize:
            self.db.executescript('''
            BEGIN IMMEDIATE;
            CREATE TABLE grants(id TEXT PRIMARY KEY,binding TEXT NOT NULL,body TEXT NOT NULL,approval TEXT NOT NULL UNIQUE,
                consumed INTEGER NOT NULL DEFAULT 0,terminal INTEGER NOT NULL DEFAULT 0,
                writer TEXT,epoch INTEGER NOT NULL DEFAULT 0,fence INTEGER NOT NULL DEFAULT 0,
                expiry INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE attempts(id TEXT PRIMARY KEY,grant_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                operation TEXT NOT NULL,state TEXT NOT NULL,proof TEXT,
                UNIQUE(grant_id,ordinal));
            CREATE TABLE audit(id INTEGER PRIMARY KEY,grant_id TEXT NOT NULL,event TEXT NOT NULL,
                at INTEGER NOT NULL,body TEXT NOT NULL);
            COMMIT;
            ''')
            fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY); os.fsync(fd); os.close(fd)
        # Missing/corrupt/deleted history is never silently initialized.
        self.db.execute('SELECT consumed FROM grants LIMIT 1')

    def close(self): self.db.close()
    def transaction(self, operation):
        info = os.lstat(self.path)
        need((info.st_dev,info.st_ino) == self.identity and info.st_nlink == 1 and
             stat.S_IMODE(info.st_mode) == 0o600, 'STORE_REPLACED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result = operation()
            self.db.execute('COMMIT')
            return result
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
    def audit(self, gid, event, body):
        self.db.execute('INSERT INTO audit(grant_id,event,at,body) VALUES(?,?,?,?)',
                        (gid,event,int(self.clock()),canonical(body).decode('utf-8')))
    def register(self, grant):
        from attempt_ledger import _valid_grant
        _valid_grant(grant)
        def action():
            self.db.execute('INSERT INTO grants(id,binding,body,approval) VALUES(?,?,?,?)',
                (grant['grant_id'],digest(grant),canonical(grant).decode('utf-8'),grant['approval_body_sha256']))
            self.audit(grant['grant_id'],'REGISTER',{'binding':digest(grant)})
        return self.transaction(action)
    def _grant(self, grant):
        rows = self.db.execute('SELECT binding,body,consumed,terminal,writer,epoch,fence,expiry FROM grants WHERE id=?',
                               (grant['grant_id'],)).fetchall()
        need(len(rows)==1 and rows[0][0]==digest(grant) and self.clock()<grant['expires_utc'], 'GRANT_UNKNOWN_OR_EXPIRED')
        return rows[0]
    def lease(self, grant, writer, ttl=30):
        need(type(writer) is str and 0<len(writer)<=128 and type(ttl) is int and 0<ttl<=60,'LEASE_REQUEST')
        def action():
            row=self._grant(grant);now=int(self.clock())
            need(not row[3] and (row[7]<=now or row[4]==writer),'CONCURRENT_WRITER')
            # A re-acquisition after expiry always advances epoch/fence. Old
            # tokens cannot be revived, even when the writer name is the same.
            fresh=row[7]<=now
            epoch,fence=row[5]+int(fresh),row[6]+int(fresh)
            expiry=min(now+ttl,grant['expires_utc'])
            self.db.execute('UPDATE grants SET writer=?,epoch=?,fence=?,expiry=? WHERE id=?',
                            (writer,epoch,fence,expiry,grant['grant_id']))
            result={'writer':writer,'lease_epoch':epoch,'fence':fence,'expiry':expiry}
            self.audit(grant['grant_id'],'LEASE',result);return result
        return self.transaction(action)
    def _fence(self, grant, token):
        row=self._grant(grant)
        need(type(token) is dict and set(token)=={'writer','lease_epoch','fence','expiry'} and
             (token['writer'],token['lease_epoch'],token['fence'],token['expiry'])==
             (row[4],row[5],row[6],row[7]) and self.clock()<row[7], 'LEASE_LOST')
        return row
    def consume(self, grant, attempt, ordinal, operation_sha, token):
        from attempt_ledger import HEX64
        need(type(attempt) is str and bool(attempt) and type(ordinal) is int and 1<=ordinal<=5 and
             type(operation_sha) is str and HEX64.fullmatch(operation_sha), 'ATTEMPT_REQUEST')
        def action():
            row=self._fence(grant,token);need(not row[3],'TERMINAL')
            prior=self.db.execute('SELECT grant_id,ordinal,operation FROM attempts WHERE id=?',(attempt,)).fetchall()
            if prior:
                need(prior==[(grant['grant_id'],ordinal,operation_sha)],'ATTEMPT_CONFLICT')
                return ordinal
            need(row[2]<5 and ordinal==row[2]+1,'QUOTA_OR_ORDINAL')
            if row[2]:
                last=self.db.execute('SELECT state FROM attempts WHERE grant_id=? AND ordinal=?',
                                     (grant['grant_id'],row[2])).fetchone()
                need(last is not None and last[0] in ('NO_WRITE','SAFE_CHECKPOINT'),'UNRECONCILED')
            self.db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,NULL)',
                            (attempt,grant['grant_id'],ordinal,operation_sha,'UNKNOWN'))
            self.db.execute('UPDATE grants SET consumed=? WHERE id=?',(ordinal,grant['grant_id']))
            self.audit(grant['grant_id'],'CONSUME',{'attempt':attempt,'ordinal':ordinal});return ordinal
        return self.transaction(action)
    def reconcile(self, grant, attempt, outcome, proof_sha, token, verify):
        need(outcome in ('NO_WRITE','SAFE_CHECKPOINT','SUCCESS') and callable(verify), 'RECOVERY_PROOF')
        need(verify(grant,attempt,outcome,proof_sha) is True,'RECOVERY_UNVERIFIED')
        def action():
            row=self._fence(grant,token)
            prior=self.db.execute('SELECT ordinal,state FROM attempts WHERE id=? AND grant_id=?',
                                 (attempt,grant['grant_id'])).fetchone()
            need(prior is not None and prior[0]==row[2] and prior[1]=='UNKNOWN','RECOVERY_STATE')
            self.db.execute('UPDATE attempts SET state=?,proof=? WHERE id=?',(outcome,proof_sha,attempt))
            if outcome=='SUCCESS':self.db.execute('UPDATE grants SET terminal=1 WHERE id=?',(grant['grant_id'],))
            self.audit(grant['grant_id'],'RECONCILE',{'attempt':attempt,'outcome':outcome,'proof':proof_sha})
        return self.transaction(action)
