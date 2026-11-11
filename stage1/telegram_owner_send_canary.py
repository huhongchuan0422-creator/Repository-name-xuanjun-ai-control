#!/usr/bin/env python3
"""One-shot Telegram delivery canary. Never stores or prints Bot token."""
import getpass
import json
import re
import sys
import urllib.request

def send(token, chat_id, opener=None):
    if not re.match(r'^[0-9]{5,15}:[A-Za-z0-9_-]{20,}$', token):
        raise ValueError('invalid Bot token format')
    if not re.match(r'^-?[0-9]{1,20}$', chat_id):
        raise ValueError('invalid chat id')
    body=json.dumps({'chat_id':chat_id,'text':'[XuanJun UK Stage1] Owner Telegram DELIVERY CANARY. No approval requested. No production action.'}).encode()
    req=urllib.request.Request('https://api.telegram.org/bot{}/sendMessage'.format(token),data=body,headers={'Content-Type':'application/json'},method='POST')
    try:
        with (opener or urllib.request.urlopen)(req,timeout=12) as resp:
            data=json.loads(resp.read(65536).decode())
    except Exception:
        raise RuntimeError('TELEGRAM_SEND_REQUEST_FAILED')
    if data.get('ok') is not True or type((data.get('result') or {}).get('message_id')) is not int:
        raise RuntimeError('TELEGRAM_SEND_NO_ACK')
    return data['result']['message_id']

if __name__=='__main__':
    print('TARGET=Existing Telegram Bot; credentials not stored')
    try:
        token=getpass.getpass('Existing Bot Token (hidden): ').strip()
        chat_id=input('Verified Owner private chat ID: ').strip()
        print('TELEGRAM_DELIVERY_ACK_MESSAGE_ID={}'.format(send(token,chat_id)))
        print('TELEGRAM_REAL_SEND=PASS')
    except (ValueError,RuntimeError) as err:
        print('STOP={}'.format(err))
        sys.exit(2)
