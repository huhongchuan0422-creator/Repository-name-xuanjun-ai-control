"""Read-only, fail-closed Feishu receipt lookup. Never proves NOT_SENT.

get must be the credential-owning relay's fixed-host authenticated GET adapter.
No credentials, DB, queue, sender or model are owned by this module.
"""
import json
import re
from urllib.parse import urlencode


class OwnerFeishuHistory:
    def __init__(self, get, verified_chat_id, verified_sender_id, max_pages=30):
        if (not callable(get) or not isinstance(verified_chat_id, str) or
                re.fullmatch(r'oc_[A-Za-z0-9_-]{1,128}', verified_chat_id) is None or
                not isinstance(verified_sender_id, str) or not verified_sender_id or
                type(max_pages) is not int or not 1 <= max_pages <= 100):
            raise ValueError('VERIFIED_HISTORY_PROVIDER_REQUIRED')
        self.get = get
        self.chat_id = verified_chat_id
        self.sender_id = verified_sender_id
        self.max_pages = max_pages

    @staticmethod
    def _data(response):
        if (not isinstance(response, dict) or type(response.get('code')) is not int or
                response['code'] != 0 or not isinstance(response.get('data'), dict)):
            raise ValueError('HISTORY_UNCONFIRMED')
        return response['data']

    def _match(self, item, content):
        if not isinstance(item, dict):
            return False
        sender = item.get('sender')
        body = item.get('body')
        if (item.get('chat_id') != self.chat_id or item.get('msg_type') != 'text' or
                item.get('deleted') is True or not isinstance(sender, dict) or
                sender.get('sender_type') != 'app' or sender.get('id') != self.sender_id or
                not isinstance(body, dict) or not isinstance(body.get('content'), str) or
                not isinstance(item.get('message_id'), str) or
                re.fullmatch(r'om_[A-Za-z0-9_-]{1,128}', item['message_id']) is None):
            return False
        return body['content'] == content

    def __call__(self, chat_id, identity, content):
        if chat_id != self.chat_id:
            return 'UNKNOWN'
        try:
            expected = json.loads(content)
            if (not isinstance(expected, dict) or set(expected) != {'text'} or
                    not isinstance(expected['text'], str) or
                    '\n事件：' + identity + '\n' not in expected['text']):
                return 'UNKNOWN'
            token = None
            seen_tokens = set()
            matches = set()
            complete = False
            for unused in range(self.max_pages):
                params = {'container_id_type': 'chat', 'container_id': self.chat_id,
                          'page_size': 50, 'sort_type': 'ByCreateTimeAsc'}
                if token is not None:
                    params['page_token'] = token
                data = self._data(self.get('im/v1/messages?' + urlencode(params)))
                items = data.get('items')
                if (not isinstance(items, list) or len(items) > 50 or
                        type(data.get('has_more')) is not bool):
                    return 'UNKNOWN'
                for item in items:
                    if self._match(item, content):
                        matches.add(item['message_id'])
                if len(matches) > 1:
                    return 'UNKNOWN'
                if not data['has_more']:
                    complete = True
                    break
                token = data.get('page_token')
                if (not isinstance(token, str) or not token or len(token) > 4096 or
                        token in seen_tokens):
                    return 'UNKNOWN'
                seen_tokens.add(token)
            if not complete or len(matches) != 1:
                return 'UNKNOWN'
            receipt = next(iter(matches))
            # Re-read the unique receipt; stale/deleted/history-only matches cannot ACK.
            items = self._data(self.get('im/v1/messages/' + receipt)).get('items')
            if (not isinstance(items, list) or len(items) != 1 or
                    items[0].get('message_id') != receipt or
                    not self._match(items[0], content)):
                return 'UNKNOWN'
            return {'chat_id': self.chat_id, 'msg_type': 'text',
                    'message_id': receipt, 'content': items[0]['body']['content']}
        except Exception:
            # Never leak credential-bearing exception messages or authorize retry.
            return 'UNKNOWN'
