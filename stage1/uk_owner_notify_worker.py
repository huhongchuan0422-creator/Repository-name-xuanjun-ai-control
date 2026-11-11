#!/usr/bin/env python3
"""UK Owner Telegram notifier. One-shot worker, safe for systemd timer.
Only sends registered, unexpired requests from the existing coordinator DB.
No webhook changes, no getUpdates, no credential disclosure. Python 3.6.
"""
import argparse
import fcntl
import json
import os
import sqlite3
import stat
import urllib.request

from owner_approval_dispatch import prepare, ready
from owner_notification_outbox import ack

def private_text(path):
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode) or (info.st_mode & 0o077):
        raise ValueError('STOP_UNSAFE_CREDENTIAL_PERMISSIONS')
    with open(path, 'r') as stream:
        value = stream.read().strip()
    if not value:
        raise ValueError('STOP_EMPTY_CREDENTIAL')
    return value

def deliver(token, chat_id, request_id, opener=None):
    message = ('[XuanJun UK] Owner approval request: ' + request_id +
               '\\n/approve ' + request_id + '\\n/reject ' + request_id)
    body = json.dumps({'chat_id': str(chat_id), 'text': message},
                      separators=(',', ':')).encode('utf-8')
    req = urllib.request.Request(
        'https://api.telegram.org/bot' + token + '/sendMessage',
        data=body, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with (opener or urllib.request.urlopen)(req, timeout=12) as response:
            data = json.loads(response.read(65536).decode('utf-8'))
    except Exception:
        raise RuntimeError('TELEGRAM_DELIVERY_UNCONFIRMED')
    result = data.get('result') or {}
    if data.get('ok') is not True or type(result.get('message_id')) is not int:
        raise RuntimeError('TELEGRAM_NO_ACK')
    if str((result.get('chat') or {}).get('id')) != str(chat_id):
        raise RuntimeError('TELEGRAM_CHAT_MISMATCH')
    return result['message_id']

def once(dbpath, token_path, owner_id, chat_id, lock_path):
    # flock stays held across network send and durable ACK, forbidding
    # concurrent timer runs. Lost ACK after send can still cause a duplicate;
    # approval request_id remains stable and replay is rejected by callback.
    with open(lock_path, 'a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        token = private_text(token_path)
        created = prepare(dbpath, owner_id, chat_id)
        processed = 0
        for item in ready(dbpath):
            message_id = deliver(token, chat_id, item['request_id'])
            if not ack(dbpath, item['task_id'], item['fence'], message_id):
                raise RuntimeError('STOP_ACK_CONFLICT')
            processed += 1
        return created, processed

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--owner-user-id', required=True)
    parser.add_argument('--owner-chat-id', required=True)
    parser.add_argument('--lock-file', required=True)
    args = parser.parse_args()
    if not args.owner_user_id.isdigit() or not args.owner_chat_id.lstrip('-').isdigit():
        raise SystemExit('STOP_BAD_OWNER_BINDING')
    try:
        created, sent = once(args.db, args.token_file, args.owner_user_id,
                             args.owner_chat_id, args.lock_file)
    except (ValueError, RuntimeError, BlockingIOError, OSError, sqlite3.Error) as exc:
        # Never include URLs (with bot token), response bodies or secret values.
        print('OWNER_SEND=STOP_' + type(exc).__name__)
        raise SystemExit(2)
    print('OWNER_REQUESTS_CREATED=' + str(created))
    print('OWNER_SEND_ACKED=' + str(sent))

if __name__ == '__main__':
    main()
