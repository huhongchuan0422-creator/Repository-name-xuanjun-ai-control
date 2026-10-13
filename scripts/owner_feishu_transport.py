"""Feishu OWNER transport for ExecutionSupervisor.deliver_once; no new outbox."""
import json
import re
import uuid

class OwnerFeishuTransport:
    def __init__(self, verified_chat_id, package_sha256, api, authorize_claim):
        if not isinstance(verified_chat_id,str) or re.fullmatch(r'oc_[A-Za-z0-9_-]{1,128}',verified_chat_id) is None:
            raise ValueError('VERIFIED_PRIVATE_CHAT_REQUIRED')
        if not isinstance(package_sha256,str) or re.fullmatch(r'[a-f0-9]{64}',package_sha256) is None:
            raise ValueError('EXACT_PACKAGE_REQUIRED')
        if not callable(api) or not callable(authorize_claim):
            raise ValueError('TRUSTED_RUNTIME_ADAPTERS_REQUIRED')
        self.chat_id,self.package_sha256=verified_chat_id,package_sha256
        self.api,self.authorize=api,authorize_claim

    def _bound(self, destination, identity, kind, claim):
        if (destination!='OWNER' or not isinstance(identity,str) or
            re.fullmatch(r'[A-Za-z0-9_.:-]{1,300}',identity) is None or
            not isinstance(kind,str) or re.fullmatch(r'[A-Z0-9_]{1,80}',kind) is None or
            not isinstance(claim,dict) or claim.get('destination')!=destination or
            claim.get('event_key')!=identity or claim.get('delivery_identity')!=identity):
            raise ValueError('FEISHU_DELIVERY_BINDING_MISMATCH')
        if any(type(claim.get(key)) is not int or claim[key]<1 for key in
               ('authority_fence','authority_epoch','claim_epoch','claim_attempt')):
            raise ValueError('FEISHU_AUTHORITY_UNKNOWN')
        if self.authorize(claim) is not True:
            raise ValueError('FEISHU_CANONICAL_CLAIM_NOT_CURRENT')

    def _body(self, identity, kind):
        # Never export arbitrary event details, error strings, credentials or links.
        text='玄钧 P2 通知\n状态：'+kind+'\n事件：'+identity+'\n包摘要：'+self.package_sha256
        return json.dumps({'text':text},ensure_ascii=False,separators=(',',':'))

    def __call__(self, destination, identity, kind, details, claim):
        self._bound(destination,identity,kind,claim)
        # The existing supervisor durably commits SENDING before this call.
        # Stable UUID does not include mutable claim_attempt or claim_token.
        event_uuid=str(uuid.uuid5(uuid.NAMESPACE_URL,'xuanjun/OWNER/'+self.chat_id+'/'+identity))
        content=self._body(identity,kind)
        body={'receive_id':self.chat_id,'msg_type':'text','content':content,'uuid':event_uuid}
        try:
            result=self.api('im/v1/messages?receive_id_type=chat_id',body)
        except Exception:
            raise RuntimeError('FEISHU_SEND_UNCERTAIN_NO_BLIND_RETRY')
        data=result.get('data') if isinstance(result,dict) else None
        if (not isinstance(data,dict) or type(result.get('code')) is not int or result['code']!=0 or
            not isinstance(data.get('message_id'),str) or
            re.fullmatch(r'om_[A-Za-z0-9_-]{1,128}',data['message_id']) is None or
            data.get('chat_id')!=self.chat_id or data.get('msg_type')!='text' or
            not isinstance(data.get('body'),dict)):
            raise RuntimeError('FEISHU_RECEIPT_UNCONFIRMED')
        try:
            expected=json.loads(content)
            actual=json.loads(data['body'].get('content',''))
        except (ValueError,TypeError):
            raise RuntimeError('FEISHU_RECEIPT_CONTENT_UNCONFIRMED')
        if actual!=expected:
            raise RuntimeError('FEISHU_RECEIPT_CONTENT_MISMATCH')
        self._bound(destination,identity,kind,claim)
        return data['message_id']

    def reconcile(self, identity, kind, lookup, claim=None):
        # Trusted lookup must read the same private chat and compare exact text.
        # Absence in bounded/paginated history can NEVER prove NOT_SENT.
        if not callable(lookup):
            return 'UNKNOWN'
        try:
            self._bound('OWNER',identity,kind,claim)
        except ValueError:
            return 'UNKNOWN'
        result=lookup(self.chat_id,identity,self._body(identity,kind))
        try:
            self._bound('OWNER',identity,kind,claim)
        except ValueError:
            return 'UNKNOWN'
        if (isinstance(result,dict) and result.get('chat_id')==self.chat_id and
            result.get('content')==self._body(identity,kind) and
            isinstance(result.get('message_id'),str) and
            re.fullmatch(r'om_[A-Za-z0-9_-]{1,128}',result['message_id'])):
            return result['message_id']
        return 'UNKNOWN'
