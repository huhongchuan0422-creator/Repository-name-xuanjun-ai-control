"""SQLite request registry for Telegram callback identifiers. Local candidate only."""
import secrets
import sqlite3
import time

def create(dbpath, task_id, fence, owner_user_id, owner_chat_id, ttl=600, now=None):
    if not task_id or type(fence) is not int or fence < 1 or ttl < 1:
        raise ValueError("invalid request")
    now = int(time.time() if now is None else now)
    ident = secrets.token_hex(16)
    with sqlite3.connect(dbpath, timeout=10) as db:
        db.execute("CREATE TABLE IF NOT EXISTS owner_callback_requests(request_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,fence INTEGER NOT NULL,owner_id TEXT NOT NULL,owner_chat TEXT NOT NULL,expires_at REAL NOT NULL,consumed INTEGER NOT NULL DEFAULT 0)")
        db.execute("INSERT INTO owner_callback_requests(request_id,task_id,fence,owner_id,owner_chat,expires_at) VALUES(?,?,?,?,?,?)",(ident,task_id,fence,str(owner_user_id),str(owner_chat_id),now+ttl))
    return ident

def lookup(dbpath, request_id):
    with sqlite3.connect("file:"+dbpath+"?mode=ro",uri=True) as db:
        row=db.execute("SELECT task_id,fence,owner_id,owner_chat,expires_at,consumed FROM owner_callback_requests WHERE request_id=?",(request_id,)).fetchone()
    if not row: return None
    return dict(zip(("task_id","fence","owner_id","owner_chat","expires_at","consumed"),row))
