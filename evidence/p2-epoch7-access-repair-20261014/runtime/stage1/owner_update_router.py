"""Owner-only routing AFTER existing Telegram webhook authentication.

Customer routing stays with the original webhook. The injected callback must
be the validated existing UK Callback V7 transport, not a replacement core.
"""
import math
import re
import sqlite3
import time
from pathlib import Path


def classify(update, owner_user_id, owner_chat_id):
    if not isinstance(update, dict):
        return 'CUSTOMER', None
    message = update.get('message')
    if not isinstance(message, dict):
        return 'CUSTOMER', None
    chat, sender = message.get('chat'), message.get('from')
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        return 'CUSTOMER', None
    if (type(chat.get('id')) is not int or type(sender.get('id')) is not int
            or str(chat['id']) != str(owner_chat_id)
            or str(sender['id']) != str(owner_user_id)
            or chat.get('type') != 'private' or sender.get('is_bot') is True):
        return 'CUSTOMER', None
    text = message.get('text')
    if not isinstance(text, str):
        return 'CUSTOMER', None
    command = text.split(None, 1)[0] if text.strip() else ''
    if command not in ('/approve', '/reject'):
        return 'CUSTOMER', None
    args = text.split()
    if len(args) != 2 or not re.fullmatch(r'[a-f0-9]{32}', args[1]):
        return 'OWNER', None
    return 'OWNER', (args[0][1:].upper(), args[1])


def process(dbpath, update, owner_user_id, owner_chat_id, callback, now=None):
    if not str(owner_user_id).isdigit() or not str(owner_chat_id).isdigit():
        raise ValueError('OWNER_BINDING_REQUIRED')
    route, command = classify(update, owner_user_id, owner_chat_id)
    if route == 'CUSTOMER':
        return {'route': 'CUSTOMER', 'status': 'UNCHANGED'}
    if command is None or type(update.get('update_id')) is not int or update['update_id'] < 0:
        return {'route': 'OWNER', 'status': 'REJECTED', 'reason': 'INVALID_COMMAND'}
    decision, request_id = command
    now = time.time() if now is None else now
    db = sqlite3.connect(Path(dbpath).resolve().as_uri() + '?mode=ro', uri=True, timeout=3)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        row = db.execute('''SELECT r.task_id,r.fence,r.owner_id,r.owner_chat,r.expires_at,r.consumed,
                                  t.state,t.fence,a.decision
                           FROM owner_callback_requests r JOIN tasks t ON t.id=r.task_id
                           JOIN approvals a ON a.task_id=t.id WHERE r.request_id=?''', (request_id,)).fetchone()
    finally:
        db.close()
    if (row is None or row[2] != str(owner_user_id) or row[3] != str(owner_chat_id)
            or type(row[1]) is not int or row[1] < 1
            or not isinstance(row[4], (int, float)) or not math.isfinite(row[4])
            or row[4] <= now or row[5] != 0 or row[6] != 'WAITING_HUMAN'
            or row[7] != row[1] or row[8] != 'PENDING'):
        return {'route': 'OWNER', 'status': 'REJECTED', 'reason': 'STALE_OR_INVALID_REQUEST'}
    event = {'request_id': request_id, 'task_id': row[0], 'fence': row[1],
             'owner_user_id': str(owner_user_id), 'owner_chat_id': str(owner_chat_id),
             'update_id': update['update_id'], 'decision': decision}
    # Callback is the final transactional authority for TTL, replay and fence.
    # A concurrent change after this read must be rejected there.
    try:
        result = callback(event)
    except Exception:
        return {'route': 'OWNER', 'status': 'RETRY', 'reason': 'CALLBACK_UNCONFIRMED'}
    if isinstance(result, dict) and result.get('accepted') is True:
        return {'route': 'OWNER', 'status': 'ACCEPTED'}
    return {'route': 'OWNER', 'status': 'REJECTED', 'reason': 'CALLBACK_REJECTED'}
