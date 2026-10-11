"""Fail-closed UK owner callback core, transport-independent. Python 3.6 compatible."""
import hashlib
import hmac
import json
import sqlite3
import time

def apply(dbpath, body, auth, signature, expected_token, secret, owner_id, now=None):
    if not hmac.compare_digest(auth or '', 'Bearer '+expected_token):
        raise ValueError('bad service auth')
    if not hmac.compare_digest(signature or '', hmac.new(secret, body, hashlib.sha256).hexdigest()):
        raise ValueError('bad signature')
    event=json.loads(body.decode('utf-8'))
    if event.get('decision') not in ('APPROVE','REJECT'):
        raise ValueError('bad decision')
    if str(event.get('owner_user_id')) != str(owner_id):
        raise ValueError('bad owner')
    if type(event.get('fence')) is not int or type(event.get('update_id')) is not int:
        raise ValueError('bad fence/update')
    if not isinstance(event.get('request_id'),str) or not isinstance(event.get('task_id'),str):
        raise ValueError('bad request')
    now=time.time() if now is None else now
    db=sqlite3.connect(dbpath,timeout=10,isolation_level=None)
    try:
        db.execute('BEGIN IMMEDIATE')
        # Registrations are created only by trusted UK Coordinator, NOT Telegram.
        row=db.execute('SELECT task_id,fence,owner_id,expires_at,consumed FROM owner_callback_requests WHERE request_id=?',(event['request_id'],)).fetchone()
        if row is None or row[0]!=event['task_id'] or row[1]!=event['fence'] or row[2]!=str(owner_id) or row[3]<=now or row[4]:
            raise ValueError('missing/expired/used request')
        state=db.execute('SELECT t.state,t.fence,a.decision FROM tasks t JOIN approvals a ON t.id=a.task_id WHERE t.id=?',(event['task_id'],)).fetchone()
        if state!=('WAITING_HUMAN',event['fence'],'PENDING'):
            raise ValueError('stale task')
        db.execute('INSERT INTO owner_callback_replays(update_id,request_id) VALUES(?,?)',(event['update_id'],event['request_id']))
        db.execute('UPDATE owner_callback_requests SET consumed=1 WHERE request_id=? AND consumed=0',(event['request_id'],))
        new_state='PENDING' if event['decision']=='APPROVE' else 'FAILED'
        db.execute('UPDATE approvals SET decision=?,decided_at=? WHERE task_id=?',(event['decision'],now,event['task_id']))
        db.execute("UPDATE tasks SET state=?,updated=? WHERE id=? AND state='WAITING_HUMAN' AND fence=?",(new_state,now,event['task_id'],event['fence']))
        db.execute('INSERT INTO events(task_id,event,created,details) VALUES(?,?,?,?)',(event['task_id'],'TELEGRAM_OWNER_'+event['decision'],now,'{}'))
        db.execute('COMMIT')
        return {'accepted':True}
    except BaseException:
        db.execute('ROLLBACK')
        raise
    finally:
        db.close()

def install_schema(dbpath):
    db=sqlite3.connect(dbpath)
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS owner_callback_requests(
          request_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,fence INTEGER NOT NULL,
          owner_id TEXT NOT NULL,expires_at REAL NOT NULL,consumed INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS owner_callback_replays(
          update_id INTEGER PRIMARY KEY,request_id TEXT NOT NULL UNIQUE);
        """)
        db.commit()
    finally:
        db.close()
