"""Atomically register a trusted Owner approval request and durable outbox.

Python 3.6 compatible. No Telegram API calls or production changes here.
The notifier may send only after a registered request exists, and must ACK
the actual Telegram message_id. Retries reuse the same request_id.
"""
import secrets
import sqlite3
import time

def prepare(dbpath, owner_id, owner_chat, now=None, ttl=900):
    if not str(owner_id).isdigit() or not str(owner_chat).lstrip('-').isdigit():
        raise ValueError('owner identity missing')
    if type(ttl) is not int or not 60<=ttl<=3600:
        raise ValueError('bad ttl')
    now=time.time() if now is None else now
    db=sqlite3.connect(dbpath,timeout=15,isolation_level=None)
    try:
        db.execute('PRAGMA busy_timeout=15000')
        db.execute('BEGIN IMMEDIATE')
        db.execute("""CREATE TABLE IF NOT EXISTS owner_callback_requests(
          request_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,fence INTEGER NOT NULL,
          owner_id TEXT NOT NULL,owner_chat TEXT NOT NULL,expires_at REAL NOT NULL,
          consumed INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS owner_notification_outbox(
          task_id TEXT NOT NULL,fence INTEGER NOT NULL,channel TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'PENDING',created_at REAL NOT NULL,
          ack_message_id TEXT,last_error TEXT,request_id TEXT,
          PRIMARY KEY(task_id,fence,channel))""")
        columns=[r[1] for r in db.execute('PRAGMA table_info(owner_notification_outbox)')]
        if 'request_id' not in columns:
            db.execute('ALTER TABLE owner_notification_outbox ADD COLUMN request_id TEXT')
        cols=[r[1] for r in db.execute('PRAGMA table_info(owner_callback_requests)')]
        if 'owner_chat' not in cols:
            db.execute('ALTER TABLE owner_callback_requests ADD COLUMN owner_chat TEXT')
        rows=db.execute("""SELECT t.id,t.fence FROM tasks t
          JOIN approvals a ON a.task_id=t.id
          WHERE t.state='WAITING_HUMAN' AND a.decision='PENDING' AND t.fence>0""").fetchall()
        created=0
        for task_id,fence in rows:
            old=db.execute("""SELECT request_id,expires_at FROM owner_callback_requests
              WHERE task_id=? AND fence=? AND consumed=0 AND expires_at>?
              ORDER BY expires_at DESC LIMIT 1""",(task_id,fence,now)).fetchone()
            if old:
                request_id=old[0]
            else:
                request_id=secrets.token_hex(16)
                db.execute("""INSERT INTO owner_callback_requests
                  (request_id,task_id,fence,owner_id,owner_chat,expires_at)
                  VALUES(?,?,?,?,?,?)""",
                  (request_id,task_id,fence,str(owner_id),str(owner_chat),now+ttl))
            current=db.execute("""SELECT state,request_id FROM owner_notification_outbox
              WHERE task_id=? AND fence=? AND channel='TELEGRAM'""",(task_id,fence)).fetchone()
            if not current:
                db.execute("""INSERT INTO owner_notification_outbox
                  (task_id,fence,channel,created_at,request_id)
                  VALUES(?,?,'TELEGRAM',?,?)""",(task_id,fence,now,request_id))
                created+=1
            elif current[1]!=request_id:
                # A delivered request can expire while its task remains pending.
                # Reopen outbox ONLY for a new registered request; never resend
                # an already ACKED, still-valid request on each scheduler tick.
                db.execute("""UPDATE owner_notification_outbox
                   SET request_id=?,state='PENDING',ack_message_id=NULL,last_error=NULL,
                       created_at=?
                   WHERE task_id=? AND fence=? AND channel='TELEGRAM'""",
                   (request_id,now,task_id,fence))
                created+=1
        db.execute('COMMIT')
        return created
    except BaseException:
        db.execute('ROLLBACK')
        raise
    finally:
        db.close()

def ready(dbpath):
    db=sqlite3.connect('file:'+dbpath+'?mode=ro',uri=True)
    try:
        return [dict(zip(('task_id','fence','request_id'),r))
          for r in db.execute("""SELECT o.task_id,o.fence,o.request_id
          FROM owner_notification_outbox o JOIN owner_callback_requests r
          ON o.request_id=r.request_id JOIN tasks t ON t.id=o.task_id
          JOIN approvals a ON a.task_id=t.id
          WHERE o.state='PENDING' AND o.request_id IS NOT NULL
          AND t.state='WAITING_HUMAN' AND t.fence=o.fence
          AND a.decision='PENDING' AND r.consumed=0 AND r.expires_at>?
          ORDER BY o.created_at LIMIT 50""",(time.time(),))]
    finally:
        db.close()
