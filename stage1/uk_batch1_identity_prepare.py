#!/usr/bin/env python3
"""Prepare UK Owner identity config from registered coordinator identity. No bot secrets."""
import os
import sqlite3
import sys
import tempfile

def main():
    dbpath, destination = sys.argv[1:]
    db = sqlite3.connect('file:' + dbpath + '?mode=ro', uri=True)
    try:
        rows = db.execute("""SELECT DISTINCT owner_id,owner_chat
           FROM owner_callback_requests
           WHERE owner_id IS NOT NULL AND owner_chat IS NOT NULL
           AND owner_chat!=''""").fetchall()
    finally:
        db.close()
    if len(rows) != 1:
        raise SystemExit('STOP_OWNER_IDENTITY_AMBIGUOUS')
    owner, chat = map(str, rows[0])
    if not owner.isdigit() or not chat.lstrip('-').isdigit():
        raise SystemExit('STOP_OWNER_IDENTITY_INVALID')
    if os.path.lexists(destination):
        raise SystemExit('STOP_IDENTITY_CONFIG_EXISTS')
    folder = os.path.dirname(destination)
    if not os.path.isdir(folder):
        os.makedirs(folder, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix='.owner-id-', dir=folder)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write('OWNER_USER_ID=' + owner + '\\nOWNER_CHAT_ID=' + chat + '\\n')
        os.rename(tmp, destination)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print('OWNER_IDENTITY_CONFIG=PASS')
if __name__ == '__main__':
    main()
