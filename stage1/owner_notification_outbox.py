"""Durable Owner Telegram notification outbox; no polling and no live send by default.

Operates on existing UK coordinator SQLite. Fail-closed and Python 3.6 compatible.
Only prepares pending notifications; delivery and ACK require separate trusted worker.
"""
import json
import sqlite3
import time

SCHEMA = """CREATE TABLE IF NOT EXISTS owner_notification_outbox(
 task_id TEXT NOT NULL, fence INTEGER NOT NULL, channel TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'PENDING', created_at REAL NOT NULL,
 ack_message_id TEXT, last_error TEXT,
 PRIMARY KEY(task_id,fence,channel))"""

def stage(dbpath, now=None):
    now=time.time() if now is None else now
    db=sqlite3.connect(dbpath,timeout=10,isolation_level=None)
    try:
        db.execute('PRAGMA busy_timeout=10000')
        db.execute('BEGIN IMMEDIATE')
        db.execute(SCHEMA)
        rows=db.execute("""SELECT t.id,t.fence FROM tasks t
          JOIN approvals a ON a.task_id=t.id
          WHERE t.state='WAITING_HUMAN' AND a.decision='PENDING'
          AND t.fence>0""").fetchall()
        added=0
        for task_id,fence in rows:
            cur=db.execute("""INSERT OR IGNORE INTO owner_notification_outbox
              (task_id,fence,channel,created_at) VALUES(?,?,'TELEGRAM',?)""",
              (task_id,fence,now))
            added+=cur.rowcount
        db.execute('COMMIT')
        return added
    except BaseException:
        db.execute('ROLLBACK')
        raise
    finally:
        db.close()

def pending(dbpath, limit=50):
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError('invalid limit')
    db=sqlite3.connect('file:'+dbpath+'?mode=ro',uri=True)
    try:
        return [dict(zip(('task_id','fence','channel'),r)) for r in db.execute(
          """SELECT task_id,fence,channel FROM owner_notification_outbox
          WHERE state='PENDING' ORDER BY created_at,task_id LIMIT ?""",(limit,))]
    finally:
        db.close()

def ack(dbpath, task_id, fence, message_id):
    if type(fence) is not int or fence<1 or not str(message_id).isdigit():
        raise ValueError('invalid ack')
    db=sqlite3.connect(dbpath,timeout=10)
    try:
        cur=db.execute("""UPDATE owner_notification_outbox
          SET state='ACKED',ack_message_id=? WHERE task_id=? AND fence=?
          AND channel='TELEGRAM' AND state='PENDING'""",
          (str(message_id),task_id,fence))
        db.commit()
        return cur.rowcount==1
    finally:
        db.close()
